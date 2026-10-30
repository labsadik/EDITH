import platform as _platform
import subprocess as _subprocess
import sys as _sys

# ── Make stdout/stderr UTF-8 tolerant ────────────────────────────────────────
# On non-UTF-8 Windows consoles (cp1254/cp1252/cp936...) any print() containing
# an emoji raises UnicodeEncodeError.  Several of those prints sit inside except
# handlers, so the handler itself would blow up and skip the recovery code that
# follows it — turning a recoverable error into a silent hang.  errors="replace"
# makes every print safe.
for _stream in (_sys.stdout, _sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass   # frozen builds may have no real stream attached

# ── Nuclear: force CREATE_NO_WINDOW on EVERY subprocess call on Windows ───────
# This patches Popen itself, so no per-file flag is needed anywhere.
if _platform.system() == "Windows":
    _OrigPopen = _subprocess.Popen

    class _Popen(_OrigPopen):
        def __init__(self, args, **kw):
            kw["creationflags"] = kw.get("creationflags", 0) | _subprocess.CREATE_NO_WINDOW
            kw.pop("startupinfo", None)   # drop any stale/shared STARTUPINFO
            super().__init__(args, **                       kw)

    _subprocess.Popen = _Popen

# ─────────────────────────────────────────────────────────────────────────────

import asyncio
import re
import threading
import time
import json
import secrets
import sys
import traceback
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from core.startup_check import check_startup_dependencies
check_startup_dependencies()

import sounddevice as sd
from google import genai
from google.genai import types
from ui import EdithUI
from memory.memory_manager import (
    load_memory, update_memory, format_memory_for_prompt,
    save_session_summary, pop_last_session,
)

def _load_action_modules():
    """Import desktop automation after QApplication owns Windows DPI awareness."""
    global file_processor, flight_finder, open_app, weather_action, send_message, reminder, computer_settings, _capture_camera, _capture_screen, youtube_video, desktop_control, browser_control, file_controller, code_helper, dev_agent, web_search_action, computer_control, game_updater, SystemMonitor, get_system_status, ProactiveEngine, add_monitor, remove_monitor, list_monitors, monitor_check_all, _fetch_news_sync
    from actions.file_processor import file_processor
    from actions.flight_finder     import flight_finder
    from actions.open_app          import open_app
    from actions.weather_report    import weather_action
    from actions.send_message      import send_message
    from actions.reminder          import reminder
    from actions.computer_settings import computer_settings
    from actions.screen_processor  import _capture_camera, _capture_screen
    from actions.youtube_video     import youtube_video
    from actions.desktop           import desktop_control
    from actions.browser_control   import browser_control
    from actions.file_controller   import file_controller
    from actions.code_helper       import code_helper
    from actions.dev_agent         import dev_agent
    from actions.web_search        import web_search as web_search_action
    from actions.computer_control  import computer_control
    from actions.game_updater      import game_updater
    from actions.system_monitor    import SystemMonitor, get_system_status
    from actions.proactive         import ProactiveEngine
    from actions.background_monitor import (
        add_monitor, remove_monitor, list_monitors, check_all as monitor_check_all,
    )
    from actions.web_search        import _news as _fetch_news_sync

from memory.config_manager     import get_brief_enabled
from core.plugin_loader        import discover_plugins
from core.action_activity      import describe_tool_activity, activity_outcome
from core.action_guard         import confirmation_requirement
from edith.platform.audit      import redact
from edith.platform.permissions import ActionCancelled, PermissionDenied, tool_tier
from core.realtime_audio      import enqueue_latest_audio
from core.narration_audio     import SpeechBuffer, SpeechPlayer
from core.live_audio import response_pcm
from core.voice_intent import requested_voice_mode
from core.execution import SERVICE as EXECUTION, configure_execution, run_code_tool
from core.device_tools import DeviceToolService, format_device_result
from core.latency_metrics import LatencyMetrics
from core.reconnect_policy import retry_delay
from core.secrets import get_gemini_api_key
from core.audio_meter          import pcm16_level
from core.product_identity import PRODUCT_IDENTITY
from core.task_scheduler      import TaskScheduler, TaskSpec, TaskReportedFailure, parallel_read_only
from core.tool_registry       import ToolRegistry
from core.task_view           import compact_task_view
from core.voice_approval      import is_interrupt_phrase
from core.agent_reliability import (
    ActionDeduplicator, ActionEvidence, AgentTaskJournal,
    assess_action_evidence, format_task_history,
)

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.5-flash-native-audio-preview-12-2025"


def _get_live_voice_model() -> str:
    """Read the selected Voice model; preserve the current Live default."""
    try:
        from core.provider_registry import load_voice_settings
        return load_voice_settings(API_CONFIG_PATH)["model"] or LIVE_MODEL
    except Exception:
        return LIVE_MODEL
VOICE_PRESETS       = {"female": "Kore", "male": "Orus"}
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    key = get_gemini_api_key(API_CONFIG_PATH)
    if not key:
        raise RuntimeError("Gemini API key is not configured in the OS keychain or legacy config.")
    return key


def _save_config_value(key: str, value) -> None:
    """Atomically save one app setting without overwriting unrelated configuration."""
    API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    data[key] = value
    temp_path = API_CONFIG_PATH.with_suffix(".json.tmp")
    temp_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    temp_path.replace(API_CONFIG_PATH)


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8") + "\n" + PRODUCT_IDENTITY.instruction()
    except Exception:
        return (
            "You are a professional, general-purpose AI assistant. "
            "Be concise, direct, and use available tools to complete actionable tasks. "
            "Never simulate actions or claim success without tool confirmation."
            + "\n" + PRODUCT_IDENTITY.instruction()
        )

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def _exception_summary(error: BaseException) -> str:
    """Flatten TaskGroup errors without printing a duplicate exception tree."""
    parts: list[str] = []

    def collect(item: BaseException) -> None:
        nested = getattr(item, "exceptions", None)
        if isinstance(nested, tuple):
            for child in nested:
                if isinstance(child, BaseException):
                    collect(child)
            return
        text = f"{type(item).__name__}: {item}".strip()
        if text not in parts:
            parts.append(text)

    collect(error)
    return " | ".join(parts)[:1500] or type(error).__name__

TOOL_DECLARATIONS = [
    {
        "name":"shell_execute",
        "description":"Execute an exact command in the current OS shell with working directory, streamed stdout/stderr, exit code and timeout. Report the intended command before running it; cancellation stops the owned process. Do not treat a timeout as success.",
        "parameters":{"type":"OBJECT","properties":{
            "command":{"type":"STRING"},"cwd":{"type":"STRING"},
            "timeout":{"type":"NUMBER","description":"Timeout in seconds; default 60"}},"required":["command"]}
    },
    {
        "name": "set_voice_mode",
        "description": (
            "Switch the assistant's output voice ONLY when the user explicitly requests a female/woman's "
            "voice or male/man's voice. Understand these direct requests in ANY language, including "
            "English and Bengali, and equivalent phrases such as 'female voice', 'speak like a woman', "
            "'male voice', 'speak like a man', 'মেয়েদের কণ্ঠে কথা বলো', 'মেয়েলি ভয়েস', 'পুরুষ কণ্ঠ', "
            "or 'ছেলেদের ভয়েস'. Choose mode=female for the female preset or mode=male for the male preset. "
            "Do not call when a user is merely asking about voice options or discussing another person's voice."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "mode": {
                    "type": "STRING",
                    "enum": ["female", "male"],
                    "description": "female = female output voice; male = male output voice",
                },
            },
            "required": ["mode"],
        },
    },
    {
        "name": "open_app",
        "description": (
            "Cross-app desktop launcher and installed-app discovery tool for the user's local OS. "
            "Use action='list' to enumerate visible OS desktop-app launcher entries, or action='search' "
            "with query to find installed apps by name. Use action='open' (the default) with app_name to "
            "launch any requested native GUI app, including messaging apps, databases, API clients, IDEs, "
            "containers, creative tools, and apps not in the alias list. Discovery reads OS launcher metadata "
            "and does not execute app entries. After a launch request, inspect the real visible desktop with "
            "screen_process, then use computer_control one step at a time. Never claim the app is ready unless "
            "foreground-window verification or subsequent screen inspection supports that."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "enum": ["open", "list", "search"],
                    "description": "open (default) launches app_name; list shows installed app launchers; search filters launchers by query"
                },
                "app_name": {
                    "type": "STRING",
                    "description": "Application name to launch, e.g. WhatsApp, Docker Desktop, Android Studio, or a name discovered by action=list/search"
                },
                "query": {
                    "type": "STRING",
                    "description": "Name filter for action=search (e.g. MongoDB, Postman, messaging)"
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum app names to return for list/search, from 1 to 100 (default 30)"
                }
            },
            "required": []
        }
    },
    {
        "name": "web_search",
        "description": (
            "Searches the web. Use for ANY question about current facts, events, prices, "
            "or topics — always prefer this over guessing. "
            "Modes: 'search' (default), 'news' (latest headlines on a topic), "
            "'research' (deep comprehensive answer), 'price' (product cost lookup), "
            "'compare' (side-by-side comparison of items)."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query or topic"},
                "mode":   {"type": "STRING", "description": "search | news | research | price | compare"},
                "items":  {"type": "ARRAY",  "items": {"type": "STRING"}, "description": "Items to compare (compare mode)"},
                "aspect": {"type": "STRING", "description": "Comparison aspect: price | specs | reviews | features"},
            },
            "required": ["query"]
        }
    },
    {
        "name": "system_status",
        "description": (
            "Returns real-time system metrics: CPU usage, RAM, GPU load, CPU temperature, "
            "uptime, and process count. Use when the user asks about computer performance, "
            "temperature, memory, or resource usage."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "performance_metrics",
        "description": (
            "Returns local observed latency statistics (sample count, p50, p95 and range) "
            "for Live connection, text-to-first-audio and completed tools. These are diagnostics, "
            "not a promise of future response speed."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "platform_system",
        "description": (
            "Use only for local-device diagnostics or a direct local OS control request. "
            "Read-only operations: system_info, telemetry, network_info, process_list, "
            "window_list, installed_apps, capabilities, hardware_inventory, display_list, audio_devices, theme. Controls include "
            "process_kill, app_launch, volume, brightness and power. Announce the target before acting. "
            "This is not a network scanner, remote access tool, or command shell."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "operation": {
                    "type": "STRING",
                    "enum": [
                        "system_info", "telemetry", "network_info", "process_list",
                        "window_list", "installed_apps", "capabilities", "hardware_inventory", "display_list", "audio_devices", "theme",
                        "process_kill", "app_launch", "volume", "brightness", "power",
                    ],
                },
                "arguments": {
                    "type": "OBJECT",
                    "description": (
                        "Only as needed: process_kill={pid}; app_launch={app}; "
                        "volume/brightness={value 0..100}; power={action sleep|restart|shutdown}."
                    ),
                },
            },
            "required": ["operation"],
        },
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {"type": "STRING", "description": "The message to send"},
                "platform":     {"type": "STRING", "description": "Platform: WhatsApp, Telegram, etc."}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time":    {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "enum": ["play", "channel", "summarize", "get_info", "trending"], "description": "play | channel | summarize | get_info | trending. Use channel for a channel search; it must not play a video."},
                "query":  {"type": "STRING", "description": "Video search query for play, or channel name for channel"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad (summarize only)"},
                "region": {"type": "STRING", "description": "Country code for trending e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL for get_info action"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": (
            "Captures the screen or webcam image and lets you analyze it. "
            "MUST be called when user asks what is on screen, what you see, "
            "look at camera, analyze my screen, etc. "
            "You have NO visual ability without this tool. "
            "After the image is captured it is sent directly to you — describe what you see and answer the user's question. "
            "When using camera: the live view stays open until user says close it or calls close_camera."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'"},
                "text":  {"type": "STRING", "description": "The question or instruction about the captured image"},
                "force": {"type": "BOOLEAN", "description": "Bypass only the duplicate-call cooldown for explicit post-action verification; never bypass an image request already in progress"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "close_camera",
        "description": (
            "Closes the live camera view shown on screen. "
            "Call when user says: close camera, stop camera, turn off camera, "
            "kamerayı kapat, kapat, creepy, etc."
        ),
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "The action to perform"},
                "description": {"type": "STRING", "description": "Natural language description of what to do"},
                "value":       {"type": "STRING", "description": "Optional value: volume level, text to type, etc."}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": (
            "Controls websites and browser tabs: navigation, search, click, type, forms, scroll, and screenshots. "
            "Use this for web tasks. For a native desktop application such as WhatsApp, Telegram, Postman, "
            "MongoDB Compass, Android Studio, or Docker Desktop, first call open_app, then use computer_control "
            "for visible GUI actions and screen_process to inspect the current screen. "
            "Use mode=embedded to open EDITH's persistent inbuilt browser with its own resizable window and saved cookies. "
            "Use external mode for the existing Playwright/browser automation session. "
            "Always honor an explicitly requested browser."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser."},
                "mode":        {"type": "STRING", "enum": ["external", "embedded"], "description": "Use embedded for EDITH's persistent inbuilt browser; external for Playwright/browser sessions."},
                "url":         {"type": "STRING", "description": "URL for go_to / new_tab action"},
                "query":       {"type": "STRING", "description": "Search query for search action"},
                "engine":      {"type": "STRING", "description": "Search engine: google | bing | duckduckgo | yandex (default: google)"},
                "selector":    {"type": "STRING", "description": "CSS selector for click/type"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart_click/smart_type"},
                "direction":   {"type": "STRING", "description": "up | down for scroll"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount in pixels (default: 500)"},
                "key":         {"type": "STRING", "description": "Key name for press action (e.g. Enter, Escape, F5)"},
                "path":        {"type": "STRING", "description": "Save path for screenshot"},
                "incognito":   {"type": "BOOLEAN", "description": "Open in private/incognito mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Use for ordinary filesystem tasks: list, create a file, create one or many folders, move, copy, rename, read, write, find, and delete. For basic file/folder operations, always use file_controller rather than code_helper; do not generate or run a script just to create folders.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | create_folders | delete | delete_permanent | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "File/folder path or shortcut: desktop, downloads, documents, home"},
                "destination": {"type": "STRING", "description": "Destination path for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name, folder name, or search name for single-item actions"},
                "names":       {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Names of multiple immediate child folders for create_folders; provide each exact folder name"},
                "extension":   {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
                "count":       {"type": "INTEGER", "description": "Number of results for largest"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path for wallpaper"},
                "url":    {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode":   {"type": "STRING", "description": "by_type or by_date for organize"},
                "task":   {"type": "STRING", "description": "Natural language desktop task"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "ONLY for programming tasks: write/edit/explain/run/build/optimize source code. Never use for ordinary file or folder management (creating/listing/moving/copying/renaming/deleting folders or files); route those requests to file_controller.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto (default: auto)"},
                "description": {"type": "STRING", "description": "What the code should do or what change to make"},
                "language":    {"type": "STRING", "description": "Programming language (default: python)"},
                "output_path": {"type": "STRING", "description": "Where to save the file"},
                "file_path":   {"type": "STRING", "description": "Path to existing file for edit/explain/run/build"},
                "code":        {"type": "STRING", "description": "Raw code string for explain"},
                "args":        {"type": "STRING", "description": "CLI arguments for run/build"},
                "timeout":     {"type": "INTEGER", "description": "Execution timeout in seconds (default: 30)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What the project should do"},
                "language":     {"type": "STRING", "description": "Programming language (default: python)"},
                "project_name": {"type": "STRING", "description": "Optional project folder name"},
                "timeout":      {"type": "INTEGER", "description": "Run timeout in seconds (default: 30)"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "computer_control",
        "description": "Controls the visible OS desktop across installed GUI apps, not just the browser. Use after open_app for native apps (messaging, database, API, IDE, container, design, and other software). Supports clicks, typing, shortcuts, window focus, screenshots, and visual element search. Actions affect the real foreground desktop; inspect the screen and proceed step by step. Never assume an app action succeeded without tool feedback.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type or paste"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "Key combination e.g. 'ctrl+c'"},
                "key":         {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount (default: 3)"},
                "seconds":     {"type": "NUMBER",  "description": "Seconds to wait"},
                "title":       {"type": "STRING",  "description": "Window title for focus_window"},
                "description": {"type": "STRING",  "description": "Element description for screen_find/screen_click"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "Field for user_data: name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
                "path":        {"type": "STRING",  "description": "Save path for screenshot"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both (default: both)"},
                "game_name": {"type": "STRING",  "description": "Game name (partial match supported)"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID for install (optional)"},
                "hour":      {"type": "INTEGER", "description": "Hour for scheduled update 0-23 (default: 3)"},
                "minute":    {"type": "INTEGER", "description": "Minute for scheduled update 0-59 (default: 0)"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shut down PC when download finishes"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport code"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport code"},
                "date":        {"type": "STRING",  "description": "Departure date (any format)"},
                "return_date": {"type": "STRING",  "description": "Return date for round trips"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers (default: 1)"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "manage_monitor",
        "description": (
            "Add, remove, or list background monitoring topics. "
            "EDITH checks these topics once a day and alerts the user when there is a new development. "
            "Use 'add' when the user says 'monitor X', 'track X', 'follow X'. "
            "Use 'remove' when the user says 'stop monitoring X'. "
            "Use 'list' when the user asks what is being monitored. "
            "Do NOT add crypto, financial, or trading topics."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type":        "STRING",
                    "description": "add | remove | list",
                },
                "topic": {
                    "type":        "STRING",
                    "description": "Topic to monitor or stop monitoring (e.g. 'space exploration', 'AI news')",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "project_manager",
        "description": "Creates a project plan using Powerful Brain and saves it locally; lists project/task status; updates a task as pending, in_progress, blocked or completed. Actions: plan, status/list, update, complete, start, block.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["plan", "status", "list", "update", "complete", "start", "block"]},
            "project_id": {"type": "STRING", "description": "Short local id for the project; required except when listing all projects."},
            "goal": {"type": "STRING", "description": "Project objective; required for plan."},
            "task_id": {"type": "STRING", "description": "Task id such as T001; required for task updates."},
            "status": {"type": "STRING", "enum": ["pending", "in_progress", "blocked", "completed"]},
            "notes": {"type": "STRING", "description": "Optional task progress note."}
        }, "required": ["action"]}
    },
    {
        "name": "devsecops_audit",
        "description": "Runs an offline static DevSecOps review of an existing project under the EDITH Projects folder. Reports hard-coded credential patterns, dynamic eval/exec, unsafe deserialization, shell=True, disabled TLS verification and unsafe YAML loading. It does not alter files or perform a penetration test.",
        "parameters": {"type": "OBJECT", "properties": {
            "project_name": {"type": "STRING", "description": "Existing project folder name under EDITH Projects."}
        }, "required": ["project_name"]}
    },
    {
        "name": "agent_manager",
        "description": "Lists every installed EDITH agent with its exact version and enabled state. Use action=list or status to inspect. Use action=enable or disable with agent_id to toggle a specialist agent. Agent toggles are stored locally.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["list", "status", "enable", "disable"]},
            "agent_id": {"type": "STRING", "description": "Agent id from the catalog, e.g. software_development, device_security, smart_network"}
        }, "required": ["action"]}
    },
    {
        "name": "device_security",
        "description": "Runs a read-only local device security posture audit: firewall/endpoint protection status where the OS exposes it, hardware inventory and platform capabilities. It never changes security settings or accesses kernel memory.",
        "parameters": {"type": "OBJECT", "properties": {}, "required": []}
    },
    {
        "name": "smart_network",
        "description": "Discovers OS-known local network neighbors and reads or controls entities on the user's paired Home Assistant instance. Actions: discover, status, entities, read, control. Control is limited to allowlisted light, switch, climate, cover and scene services; local confirmation is required for every write. Never scan, log in to or control unpaired devices.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["discover", "status", "entities", "read", "control"]},
            "entity_id": {"type": "STRING", "description": "Exact paired Home Assistant entity id such as light.living_room."},
            "service": {"type": "STRING", "description": "Allowlisted service such as light.turn_on, switch.turn_off, climate.set_temperature."},
            "service_data": {"type": "OBJECT", "properties": {
                "brightness": {"type": "NUMBER"}, "brightness_pct": {"type": "NUMBER"},
                "color_temp": {"type": "NUMBER"}, "color_temp_kelvin": {"type": "NUMBER"},
                "transition": {"type": "NUMBER"}, "temperature": {"type": "NUMBER"},
                "hvac_mode": {"type": "STRING"}, "position": {"type": "NUMBER"},
                "tilt_position": {"type": "NUMBER"}
            }, "description": "Only these validated Home Assistant service values are accepted."}
        }, "required": ["action"]}
    },
    {
        "name": "knowledge_base",
        "description": "Manage EDITH's local document knowledge base. Actions: index_file (extract, chunk and locally embed a document), search (semantic retrieval), stats. Uses local Ollama embeddings and local LanceDB storage; does not upload document contents to a cloud vector service.",
        "parameters": {"type": "OBJECT", "properties": {
            "action": {"type": "STRING", "enum": ["index_file", "search", "stats"]},
            "file_path": {"type": "STRING", "description": "Path to a supported local text, Markdown, PDF, DOCX, CSV, JSON or source-code file. Use the currently uploaded file when omitted."},
            "query": {"type": "STRING", "description": "Question or query for semantic search."},
            "limit": {"type": "INTEGER", "description": "Maximum number of relevant chunks (1-20)."}
        }, "required": ["action"]}
    },
    {
        "name": "agent_supervisor",
        "description": "Run a LangGraph multi-agent workflow using Powerful Brain. It retrieves relevant local RAG context, delegates bounded planning/research/developer/security tasks to specialist roles and synthesizes their results. It does not execute external tools or claim that devices/files were changed.",
        "parameters": {"type": "OBJECT", "properties": {
            "request": {"type": "STRING", "description": "Complex request to plan and analyze."}
        }, "required": ["request"]}
    },
    {
        "name": "task_history",
        "description": (
            "Show a short privacy-safe history of recent EDITH task outcomes, "
            "including interrupted or unverified actions. Read-only; never "
            "reveals commands, file paths, messages or credentials."
        ),
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "shutdown_edith",
        "description": (
            "Shuts down the assistant completely. "
            "Call this when the user expresses intent to end the conversation, "
            "close the assistant, say goodbye, or stop EDITH. "
            "The user can say this in ANY language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
    "name": "file_processor",
    "description": (
        "Processes any file that the user has uploaded or dropped onto the interface. "
        "Use this when the user refers to an uploaded file and wants an action on it. "
        "Supports: images (describe/ocr/resize/compress/convert), "
        "PDFs (summarize/extract_text/to_word), "
        "Word docs & text files (summarize/fix/reformat/translate), "
        "CSV/Excel (analyze/stats/filter/sort/convert), "
        "JSON/XML (validate/format/analyze), "
        "code files (explain/review/fix/optimize/run/document/test), "
        "audio (transcribe/trim/convert/info), "
        "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
        "archives (list/extract), "
        "presentations (summarize/extract_text). "
        "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
        "If the user's command is ambiguous, pick the most logical action for that file type."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "file_path": {
                "type": "STRING",
                "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file."
            },
            "action": {
                "type": "STRING",
                "description": (
                    "What to do with the file. Examples by type:\n"
                    "image: describe | ocr | resize | compress | convert | info\n"
                    "pdf: summarize | extract_text | to_word | info\n"
                    "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                    "csv/excel: analyze | stats | filter | sort | convert | info\n"
                    "json: validate | format | analyze | to_csv\n"
                    "code: explain | review | fix | optimize | run | document | test\n"
                    "audio: transcribe | trim | convert | info\n"
                    "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                    "archive: list | extract\n"
                    "pptx: summarize | extract_text | analyze"
                )
            },
            "instruction": {
                "type": "STRING",
                "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'"
            },
            "format": {
                "type": "STRING",
                "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'"
            },
            "width":     {"type": "INTEGER", "description": "Target width for image resize"},
            "height":    {"type": "INTEGER", "description": "Target height for image resize"},
            "scale":     {"type": "NUMBER",  "description": "Scale factor for image resize (e.g. 0.5)"},
            "quality":   {"type": "INTEGER", "description": "Quality 1-100 for image/video compress"},
            "start":     {"type": "STRING",  "description": "Start time for trim: seconds or HH:MM:SS"},
            "end":       {"type": "STRING",  "description": "End time for trim: seconds or HH:MM:SS"},
            "timestamp": {"type": "STRING",  "description": "Timestamp for video frame extraction HH:MM:SS"},
            "column":    {"type": "STRING",  "description": "Column name for CSV filter/sort"},
            "value":     {"type": "STRING",  "description": "Filter value for CSV filter"},
            "condition": {"type": "STRING",  "description": "Filter condition: equals|contains|gt|lt"},
            "ascending": {"type": "BOOLEAN", "description": "Sort order for CSV sort (default: true)"},
            "save":      {"type": "BOOLEAN", "description": "Save result to file (default: true)"},
            "destination": {"type": "STRING", "description": "Output folder for archive extract"},
        },
        "required": []
    }
},
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    )
                },
                "key":   {"type": "STRING", "description": "Short snake_case key (e.g. name, favorite_food, sister_name)"},
                "value": {"type": "STRING", "description": "Concise value in English (e.g. Fatih, pizza, older sister)"},
            },
            "required": ["category", "key", "value"]
        }
    },
]

class EdithLive:

    def __init__(self, ui: EdithUI):
        _load_action_modules()
        self.ui             = ui
        configure_execution(ui)
        # Reuse execution's broker/audit so device tools cannot bypass the
        # dispatcher confirmation, activity receipts or global interrupt.
        self._device_tools = DeviceToolService(EXECUTION.controller)
        self._latency_metrics = LatencyMetrics()
        self._asst_name     = "EDITH"
        try:
            _saved_cfg = json.loads(API_CONFIG_PATH.read_text(encoding="utf-8"))
            self._voice_mode = str(_saved_cfg.get("voice_mode") or "female").lower()
        except Exception:
            self._voice_mode = "female"
        if self._voice_mode not in VOICE_PRESETS:
            self._voice_mode = "female"
        self._voice_confirmation: str | None = None
        self._recent_voice_intent: tuple[str, float] | None = None
        self._reconfigure_reason: str | None = None
        self._reconfigure_event: asyncio.Event | None = None
        self._api_key_update_event: asyncio.Event | None = None
        self._connecting = False
        self.session              = None
        self.audio_in_queue       = None
        self._speech_player       = None
        self._tool_call_queue     = None
        self.out_queue            = None
        self._pending_text_started_at: float | None = None
        self._loop                = None
        self._response_pending    = False
        self._is_speaking         = False
        self._speaking_lock       = threading.Lock()
        self._phone_active        = False   # True while phone mic is streaming; pauses PC mic
        self._last_mic_meter_at   = 0.0  # throttle UI samples; no audio history retained
        self._mic_resume_at = 0.0  # keep playback tails out of Live's interruption detector
        self._pending_vision       = None    # (img_bytes, mime_type, question, angle) to inject after tool response
        self._vision_cam_active    = False   # True if camera was opened for vision → auto-close after response
        self._vision_close_pending = False   # True after vision injected; next turn_complete closes camera
        self._vision_last_time     = 0.0     # monotonic time of last screen_process call (cooldown guard)
        self._vision_busy          = False   # True while a vision capture/inject cycle is in flight
        self._interrupted          = False   # True while draining audio after user interrupt
        self._kill_switch_generation = 0     # invalidates stale tool-batch completions
        self._task_input_locked = False      # one user task batch owns input until it settles
        self.ui.on_text_command   = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self.ui._win.on_api_key_saved = self._request_api_key_reconnect
        self.ui.on_voice_mode_clicked = self._request_voice_mode_from_ui
        self.ui._win.voice_mode_signal.emit(self._voice_mode)
        self.ui.on_interrupt      = self.interrupt
        self._task_scheduler = TaskScheduler(
            max_concurrency=4, on_update=self._notify_task_status
        )
        self._task_batch_sequence = 0
        self._agent_run_id = secrets.token_hex(6)
        self._action_deduplicator = ActionDeduplicator()
        self._agent_journal = AgentTaskJournal()
        if not self._agent_journal.available:
            self.ui.write_log("TASKS: Task history storage unavailable; no private actions are logged to disk.")
        self._task_evidence: dict[str, tuple[ActionEvidence, int]] = {}
        self.ui._win.on_cancel_queued_tasks = self._cancel_pending_tasks
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard     = None
        self._briefing_sent    = False          # morning briefing fires once per process
        self._sys_monitor      = SystemMonitor()  # persistent cooldown state
        self._proactive        = ProactiveEngine()
        self._last_user_speech = time.monotonic()  # updated on every user utterance
        self._session_log: list[str] = []          # conversation turns for end-of-session summary

        self._enhanced_live = True  # affective dialog + proactive audio; auto-disabled if the server rejects them
        _core_names = {t["name"] for t in TOOL_DECLARATIONS}
        self._plugin_registry = discover_plugins(
            plugins_dir=Path(__file__).resolve().parent / "plugins",
            core_tool_names=_core_names,
            logger=lambda msg: (print(f"[Plugins] {msg}"), self.ui.write_log(f"SYS: {msg}")),
        )
        self._tool_registry = ToolRegistry(
            TOOL_DECLARATIONS, self._plugin_registry.get_tool_declarations
        )
        self.ui.get_plugins = self._list_plugin_manager_items
        self.ui.request_say = self.plugin_say   # plugins: mid-task speech channel

    def plugin_say(self, instruction: str) -> None:
        """
        Thread-safe speech channel for plugins: lets a plugin ask EDITH to
        say something short WHILE its run() is still executing (plugins block
        their executor thread, so they can't speak through the tool response
        until they finish). The instruction is injected into the Live session
        exactly like a proactive check-in; Gemini phrases it naturally in the
        user's language. Silently a no-op when no session is connected.
        """
        loop = getattr(self, "_loop", None)
        if not loop or not self.session:
            return

        async def _say():
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": instruction}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[PluginSay] {e}")

        try:
            asyncio.run_coroutine_threadsafe(_say(), loop)
        except Exception as e:
            print(f"[PluginSay] {e}")

    def _list_plugin_manager_items(self) -> list[dict]:
        """Combine configured plugins/MCP servers with the versioned local agents."""
        from core.agent_registry import plugin_manager_records

        return [
            *self._plugin_registry.list_for_ui(),
            *plugin_manager_records(self._on_agent_registry_changed),
        ]

    def _on_agent_registry_changed(self, item: dict) -> None:
        """Persisted agent toggles from Qt must reconfigure Live on its own loop."""
        self.ui.write_log(
            f"AGENT: {item['id']} {item['status']} · v{item['version']}"
        )
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def _request_reconfigure() -> None:
            self._reconfigure_reason = "Agent registry changed from Plugins manager"
            if self._reconfigure_event is not None:
                self._reconfigure_event.set()

        try:
            loop.call_soon_threadsafe(_request_reconfigure)
        except RuntimeError:
            # The Live loop may be shutting down while the Qt window is closing.
            pass

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                "Run: pip install fastapi \"uvicorn[standard]\" cryptography"
            )
            return None
        key    = self._dashboard.new_key()
        url    = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _notify_task_status(self, states: list[dict]) -> None:
        """Publish bounded task metadata to the existing Qt UI; never tool args."""
        view = compact_task_view(states)
        self.ui._emit_if_open(
            "task_status_signal", view["running"], view["queued"], view["completed"]
        )
        self.ui._emit_if_open("task_detail_signal", view)

    def _audit_tool_event(self, phase: str, name: str, args: dict, tier: int, result_value=None) -> None:
        """Write dispatcher start/finish receipts through the shared redactor."""
        safe_args = redact(dict(args or {}))
        # Keep large user/code payloads out of the local audit file while
        # retaining enough shape to diagnose which tool was called.
        if isinstance(safe_args, dict):
            for key in ("code", "source", "message_text", "text", "value"):
                value = safe_args.get(key)
                if isinstance(value, str) and len(value) > 1000:
                    safe_args[key] = f"[omitted {len(value)} characters]"
        safe_result = result_value
        if isinstance(safe_result, str) and len(safe_result) > 2000:
            safe_result = safe_result[:2000] + "…"
        success = None if phase == "start" else activity_outcome(str(safe_result or "")) != "error"
        try:
            EXECUTION.audit.write(
                "agent", f"tool.{phase}", safe_args, int(tier),
                {"ok": success, "result": safe_result}
            )
        except Exception as exc:
            # Audit failure must never prevent the actual tool result from
            # reaching the model; the platform audit layer records its own error.
            print(f"[Audit] Dispatcher receipt unavailable: {type(exc).__name__}")

    def _cancel_pending_tasks(self) -> None:
        """Qt callback: only pending work is cancelled, never running OS actions."""
        loop = self._loop
        if not loop or not loop.is_running():
            self.ui.write_log("TASKS: Task scheduler is not connected.")
            return

        def _cancel():
            count = self._task_scheduler.cancel_queued()
            self.ui.write_log(
                f"TASKS: Cancelled {count} queued task(s). "
                "Running actions were not interrupted."
            )

        loop.call_soon_threadsafe(_cancel)

    def _cancel_global_tasks(self) -> None:
        """Run on the Live loop: cancel queued and active scheduler wrappers."""
        stats = self._task_scheduler.cancel_all()
        dropped = 0
        queue = self._tool_call_queue
        if queue is not None:
            while True:
                try:
                    queue.get_nowait()
                    dropped += 1
                except asyncio.QueueEmpty:
                    break
        self.ui.write_log(
            "TASKS: Global interrupt — cancelled "
            f"{stats['queued']} queued, {stats['running']} active task(s); "
            f"discarded {dropped} pending tool batch(es)."
        )

    def _handle_busy_input(self, text: str, source: str = "voice") -> bool:
        """A running batch accepts only a narrow local stop command."""
        if is_interrupt_phrase(text):
            self.ui.write_log(f"TASKS: {source.title()} interrupt accepted while work was active.")
            self.interrupt()
            return True
        self.ui.write_log("TASKS: Current work is still active; new commands were not queued. Use Interrupt to stop it.")
        return False

    async def _run_checked_tool(self, fc, task_id: str) -> types.FunctionResponse:
        """Deduplicate side effects and attach honest, privacy-safe evidence."""
        self._agent_journal.started(task_id)
        started = time.perf_counter()
        arguments = dict(fc.args or {})
        if not parallel_read_only(fc.name, arguments):
            claim = self._action_deduplicator.reserve(fc.id, fc.name, arguments)
            if claim in {"duplicate", "conflict"}:
                note = (
                    "Repeated tool-call ID suppressed; nothing executed again. "
                    "Verify the earlier action with a separate read-only check."
                    if claim == "duplicate" else
                    "Conflicting tool-call ID suppressed; nothing executed. "
                    "Request a new action after checking the current state."
                )
                evidence = ActionEvidence("unverified", "not_verified", True)
                elapsed = int((time.perf_counter() - started) * 1000)
                self._task_evidence[task_id] = (evidence, elapsed)
                response = types.FunctionResponse(
                    id=fc.id, name=fc.name,
                    response={"result": note, "execution_verification": evidence.response_metadata()},
                )
                raise TaskReportedFailure(response)

        # Only registry-classified read-only tools may be retried.  This is
        # deliberately local to the checked execution path so a tool-reported
        # failure has an honest final response rather than being discarded by
        # the generic scheduler.
        retry_safe, retry_limit = self._tool_registry.policy(fc.name)
        attempt = 0
        while True:
            response = await self._execute_tool(fc)
            evidence = assess_action_evidence(
                fc.name, arguments, response.response.get("result", "")
            )
            if not (evidence.blocks_dependents and evidence.status == "failed"
                    and retry_safe and attempt < retry_limit):
                break
            attempt += 1
            self.ui.write_log(
                f"TASKS: Read-only {fc.name} did not succeed; retrying "
                f"({attempt}/{retry_limit})."
            )
            await asyncio.sleep(min(0.20 * attempt, 0.50))

        # A fallback is an explicit, fixed read-only alternative from the
        # registry.  It never carries user/model arguments across tools and it
        # never retries a mutating operation.  Preserve the original call ID
        # and name in the final model response so Gemini can match the reply.
        fallback = self._tool_registry.fallback_for(fc.name) if evidence.blocks_dependents else None
        if fallback is not None:
            self.ui.write_log(
                f"TASKS: {fc.name} failed; trying read-only fallback {fallback.name}."
            )
            fallback_call = SimpleNamespace(
                id=fc.id, name=fallback.name, args=fallback.arguments
            )
            fallback_response = await self._execute_tool(fallback_call)
            fallback_result = fallback_response.response.get("result", "")
            fallback_evidence = assess_action_evidence(
                fallback.name, fallback.arguments, fallback_result
            )
            result = (
                f"Primary read-only tool '{fc.name}' failed. "
                f"Fallback '{fallback.name}' result:\n{fallback_result}"
            )
            response = types.FunctionResponse(
                id=fc.id,
                name=fc.name,
                response={"result": result, "fallback": fallback.name},
            )
            evidence = fallback_evidence
        elapsed = int((time.perf_counter() - started) * 1000)
        self._task_evidence[task_id] = (evidence, elapsed)
        annotated = types.FunctionResponse(
            id=fc.id, name=fc.name,
            response={**response.response, "execution_verification": evidence.response_metadata()},
        )
        if evidence.blocks_dependents:
            raise TaskReportedFailure(
                annotated, status="cancelled" if evidence.status == "cancelled" else "failed"
            )
        return annotated

    async def _execute_tool_batch(self, calls) -> list[types.FunctionResponse]:
        """Parallelize independent read-only calls while preserving action order.

        Every write/desktop/unknown tool is a barrier. Calls after that barrier
        cannot start until it succeeds. Results are returned in model call order.
        """
        calls = list(calls)
        if not calls:
            return []
        self._task_batch_sequence += 1
        batch = self._task_batch_sequence
        specs = []
        barrier: tuple[str, ...] = ()
        current_reads: list[str] = []
        parallel_count = 0
        for index, fc in enumerate(calls):
            task_id = f"{self._agent_run_id}-{batch}-{index + 1}"
            safe = parallel_read_only(fc.name, dict(fc.args or {}))
            if safe:
                dependencies = barrier
                current_reads.append(task_id)
                parallel_count += 1
            else:
                dependencies = tuple(dict.fromkeys((*barrier, *current_reads)))
                barrier = (task_id,)
                current_reads.clear()
            specs.append(TaskSpec(
                task_id=task_id,
                label=describe_tool_activity(fc.name, dict(fc.args or {})),
                run=lambda call=fc, tid=task_id: self._run_checked_tool(call, tid),
                priority=0 if fc.name == "system_status" else 10,
                depends_on=dependencies,
                exclusive=not safe,
                retry_safe=self._tool_registry.policy(fc.name)[0],
                retry_limit=self._tool_registry.policy(fc.name)[1],
            ))

        self.ui.write_log(
            f"TASKS: {len(specs)} action(s) queued; "
            f"{parallel_count} read-only action(s) eligible for concurrency (max 4)."
        )
        self._agent_journal.plan([(spec.task_id, calls[i].name) for i, spec in enumerate(specs)])
        try:
            outcomes = await self._task_scheduler.run_batch(specs)
        except asyncio.CancelledError:
            # Live disconnects must not leave in-flight work marked successful.
            # Background OS operations may continue; never replay them.
            states = {item["id"]: item["status"]
                      for item in self._task_scheduler.snapshot()}
            for spec in specs:
                interrupted = states.get(spec.task_id) in {"running", "interrupted"}
                self._agent_journal.finished(
                    spec.task_id, "interrupted" if interrupted else "cancelled",
                    "not_verified",
                )
            raise
        responses = []
        for fc, outcome in zip(calls, outcomes):
            evidence, duration_ms = self._task_evidence.pop(
                outcome.task_id, (None, None)
            )
            verification = evidence.verification if evidence else "not_verified"
            self._agent_journal.finished(
                outcome.task_id, outcome.status, verification, duration_ms
            )
            if evidence and evidence.verification == "follow_up_required":
                self.ui.write_log(
                    f"TASKS: {fc.name} reported a result; independent verification still required."
                )
            if outcome.status == "succeeded":
                responses.append(outcome.value)
            elif outcome.value is not None:
                # Tool reported its own error/cancellation; return its exact
                # result to the model, without allowing dependent actions.
                responses.append(outcome.value)
            else:
                # Explicitly report a skipped/failed action to Gemini rather
                # than inventing a successful tool response.
                reason = {
                    "cancelled": "Cancelled while queued; no action started.",
                    "blocked": "Not run because a prerequisite failed or was cancelled.",
                    "failed": "Task failed before returning a tool result.",
                    "interrupted": "Task interrupted; completion cannot be verified.",
                }.get(outcome.status, "Task did not complete.")
                self.ui.write_log(f"TASKS: {fc.name} — {outcome.status}.")
                responses.append(types.FunctionResponse(
                    id=fc.id, name=fc.name, response={"result": reason}
                ))
        return responses

    def _on_text_command(self, text: str) -> bool:
        """Queue text input; tell Qt whether it is safe to clear the draft."""
        from core.voice_intent import requested_voice_mode
        if not self._loop or not self._loop.is_running() or not self.session:
            self.ui.write_log("NET: Gemini Live is not connected; command kept for retry.")
            return False
        if getattr(self, "_task_input_locked", False):
            # An active batch accepts only an interrupt; discard new tasks.
            self._loop.call_soon_threadsafe(self._handle_busy_input, text, "text")
            return True
        mode = requested_voice_mode(text)
        if mode:
            # Switch directly instead of relying on Gemini to remember to call a tool.
            self._request_voice_mode_from_ui(mode)
            return True
        self._recent_voice_intent = None
        self._response_pending = True
        self.ui.set_state("THINKING")
        self._pending_text_started_at = time.perf_counter()
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.session.send_client_content(
                    turns={"parts": [{"text": text}]},
                    turn_complete=True,
                ),
                self._loop,
            )
        except RuntimeError as exc:
            self._response_pending = False
            self.ui.set_state("LISTENING")
            self._pending_text_started_at = None
            self.ui.write_log(
                f"ERR: Could not queue Gemini Live text ({type(exc).__name__})."
            )
            return False

        def _check_send(result):
            try:
                result.result()
            except Exception as exc:
                self._response_pending = False
                self.ui.set_state("LISTENING")
                self._pending_text_started_at = None
                self.ui.write_log(
                    f"ERR: Could not send text to Gemini Live ({type(exc).__name__})."
                )
                # Restore only when the user has not already typed a new draft.
                self.ui._win.text_send_failed_signal.emit(text)

        future.add_done_callback(_check_send)
        return True

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            if getattr(self, "_is_speaking", False) and not value:
                self._mic_resume_at = time.monotonic() + .35
            self._is_speaking = value
        publish = getattr(self.ui, "show_playback_state", None)
        if publish:
            publish(value)
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("THINKING" if getattr(self, "_response_pending", False) else "LISTENING")

    def _mic_can_send(self) -> bool:
        """Suppress speaker echo, including the first/last playback packets."""
        with self._speaking_lock:
            if self._is_speaking:
                return False
        player = getattr(self, "_speech_player", None)
        return not (player and player.snapshot()["playing"]) and time.monotonic() >= self._mic_resume_at

    def interrupt(self) -> None:
        """Cancel queued narration and signal the native writer to abort playback."""
        self._interrupted = True
        self._response_pending = False
        self._kill_switch_generation += 1
        EXECUTION.cancel()  # Stop tracked code/shell processes; whole-agent cancellation is a later gate.
        loop = self._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(self._cancel_global_tasks)
        q = self.audio_in_queue
        if q is not None:
            q.clear()  # Thread-safe; also aborts queued device playback on the writer thread.
        self.set_speaking(False)
        if self._turn_done_event:
            self._turn_done_event.clear()
        self._pending_vision = None
        self._vision_busy = False
        self._vision_close_pending = False
        try:
            self.ui.stop_camera_stream()
        except Exception:
            pass
        self.ui.write_log("SYS: Interrupted — listening...")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns={"parts": [{"text": text}]},
                turn_complete=True
            ),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"I couldn't complete {tool_name}. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        # Load customization from config
        try:
            _cfg = json.loads(open(API_CONFIG_PATH, encoding="utf-8").read())
            # The fixed product display name is EDITH; ignore any legacy/custom assistant name.
            self._asst_name = "EDITH"
            _user_name = (_cfg.get("user_name") or "").strip()
            voice_mode = str(_cfg.get("voice_mode") or self._voice_mode).strip().lower()
            self._voice_mode = voice_mode if voice_mode in VOICE_PRESETS else "female"
        except Exception:
            self._asst_name = "EDITH"
            _user_name = ""
            self._voice_mode = "female"

        memory     = load_memory()
        mem_str    = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        # Identity injection — overrides any hardcoded name in prompt.txt
        voice_style = (
            "Use the configured female voice with confident, mature, warm, clear, and decisive delivery."
            if self._voice_mode == "female"
            else "Use the configured male voice with confident, mature, warm, clear, and decisive delivery."
        )
        _addr = (
            f"Address the user by name only when a name is configured: '{_user_name}'."
            if _user_name else
            "Do not use gendered honorifics or fictional-character catchphrases."
        )
        identity_ctx = (
            "[IDENTITY]\n"
            "You are a professional, general-purpose AI assistant operating on the user's own device.\n"
            f"Your display name is {self._asst_name}. Do not imitate fictional characters or use third-party product branding.\n"
            f"{voice_style} Keep speech natural and concise; avoid theatrical role-play or long preambles.\n"
            f"{_addr}\n\n"
        )

        parts = [time_ctx, identity_ctx]
        if mem_str:
            parts.append(mem_str)
        from core.agent_registry import build_agent_prompt_context
        parts.append(build_agent_prompt_context())
        parts.append(sys_prompt)

        voice_name = VOICE_PRESETS[self._voice_mode]
        cfg = dict(
            response_modalities=["AUDIO"],
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": __import__("core.agent_registry", fromlist=["filter_tool_declarations"]).filter_tool_declarations(self._tool_registry.declarations())}],
            session_resumption=types.SessionResumptionConfig(),
            # Sliding-window compression: session never dies from a full context
            # window — EDITH can stay in one conversation for hours
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=voice_name
                    )
                )
            ),
        )
        if self._enhanced_live:
            # Affective dialog: EDITH hears tone/emotion and adapts its voice.
            # Proactive audio: EDITH stays silent when speech isn't addressed
            # to it (background chatter, talking to someone else in the room).
            cfg["enable_affective_dialog"] = True
            cfg["proactivity"] = types.ProactivityConfig(proactive_audio=True)
        return types.LiveConnectConfig(**cfg)

    def _request_voice_mode_from_ui(self, mode: str) -> None:
        """Thread-safe bridge from the desktop voice buttons to the Live event loop."""
        if not self._loop or not self._loop.is_running():
            try:
                mode = str(mode).lower()
                if mode not in VOICE_PRESETS:
                    return
                _save_config_value("voice_mode", mode)
                self._voice_mode = mode
                self.ui._win.voice_mode_signal.emit(mode)
                self.ui.write_log(f"SYS: {mode.capitalize()} voice saved for the next session.")
            except Exception as exc:
                self.ui.write_log(f"ERR: Voice preference could not be saved ({type(exc).__name__}).")
            return
        asyncio.run_coroutine_threadsafe(self._set_voice_mode(mode), self._loop)

    def _request_api_key_reconnect(self) -> None:
        """Receive a key editor save event from the Qt thread without exposing the key."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._api_key_saved_on_loop(), self._loop)

    async def _api_key_saved_on_loop(self) -> None:
        if self._api_key_update_event:
            self._api_key_update_event.set()
        if self._connecting or self.session:
            self._reconfigure_reason = "Gemini API key updated"
            if self._reconfigure_event:
                self._reconfigure_event.set()
        self.ui.write_log("SYS: Tested API key saved; Gemini Live will use the updated key.")

    async def _set_voice_mode(self, mode: str, defer_reconnect: bool = False) -> str:
        mode = (mode or "").strip().lower()
        if mode not in VOICE_PRESETS:
            return "Voice mode must be female or male."
        if mode == self._voice_mode:
            self.ui._win.voice_mode_signal.emit(mode)
            return f"The {mode} voice is already selected."
        try:
            _save_config_value("voice_mode", mode)
        except Exception as exc:
            return f"Could not save voice preference: {type(exc).__name__}."
        self._voice_mode = mode
        self.ui._win.voice_mode_signal.emit(mode)
        self._voice_confirmation = (
            f"The user's requested voice has now been changed to {mode}. "
            "Confirm this very briefly and naturally in the user's language using the newly configured voice. "
            "Do not mention technical reconnection or internal tools."
        )
        self._reconfigure_reason = f"voice changed to {mode}"
        self.ui.write_log(
            f"SYS: {mode.capitalize()} voice selected ({VOICE_PRESETS[mode]}); switching Live session."
        )
        if not defer_reconnect and self._reconfigure_event:
            self._reconfigure_event.set()
        return f"Saved the {mode} voice preference. Reconnecting so the new voice takes effect."

    def _model_voice_change_allowed(self, mode: str) -> bool:
        recent = self._recent_voice_intent
        self._recent_voice_intent = None
        return bool(recent and recent[0] == mode and time.monotonic() - recent[1] < 45)

    async def _watch_session_reconfigure(self) -> None:
        if self._reconfigure_event is None:
            return
        await self._reconfigure_event.wait()
        raise RuntimeError("Live session reconfiguration requested")

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})
        tool_started_at = time.perf_counter()
        approval_scope = None
        # Internal foreground-target fields are dispatcher-owned, never model-authorized.
        args.pop("_confirmation_window_target", None)
        args.pop("_confirmed_window_target", None)

        activity_label = describe_tool_activity(name, args)
        print(f"[Assistant] 🔧 {name} — {activity_label}")
        self.ui.set_state("WORKING")
        self.ui.write_log(f"ACTIVITY ▶ {activity_label}")

        # Tier labels remain in the audit receipt even in hands-free mode.
        backend_tier = tool_tier(name, args)
        self._audit_tool_event("start", name, args, backend_tier)

        def _completed(response):
            metrics = getattr(self, "_latency_metrics", None)
            if metrics is not None:
                metrics.record(f"tool.{name}", (time.perf_counter() - tool_started_at) * 1000)
            self._audit_tool_event(
                "finish", name, args, backend_tier,
                (response.response or {}).get("result") if response else None,
            )
            return response

        from core.agent_registry import TOOL_AGENT_MAP, is_agent_enabled
        bound_agent = TOOL_AGENT_MAP.get(name)
        if bound_agent and not is_agent_enabled(bound_agent):
            result = f"Agent '{bound_agent}' is disabled. Enable it with agent_manager before requesting this capability."
            self.ui.write_log(f"AGENT: {bound_agent} is disabled; tool was not run.")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))

        confirmation_reason = confirmation_requirement(name, args)
        if backend_tier >= 2 and not confirmation_reason:
            confirmation_reason = f"Tier {backend_tier} operation '{name}'"
        close_confirmation = bool(
            confirmation_reason and name == "computer_settings"
            and (
                confirmation_reason.startswith("Close/terminate")
                or confirmation_reason.startswith("Close the window")
            )
        )
        restore_foreground = bool(confirmation_reason and name == "computer_control")
        if close_confirmation:
            try:
                from core.action_guard import _explicit_window_target
                from actions.open_app import _active_window_description

                requested_target = _explicit_window_target(args)
                if not requested_target:
                    foreground_title = await asyncio.to_thread(_active_window_description)
                    foreground_key = str(foreground_title or "").casefold()
                    # Do not interpret a generic request as permission to close
                    # EDITH itself when its window currently has focus.
                    if foreground_title and (
                        "edith" in foreground_key or "personal assistant" in foreground_key
                    ):
                        foreground_title = ""
                    requested_target = foreground_title
                if not requested_target:
                    result = (
                        "Could not identify the exact app/window to close. Nothing was closed; "
                        "please name the app or window explicitly."
                    )
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label} — target not identified")
                    return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))
                args["_confirmation_window_target"] = requested_target
                confirmation_reason = confirmation_requirement(name, args)
            except Exception as exc:
                print(f"[Confirmation] Window target unavailable: {type(exc).__name__}")
                result = "Could not identify the exact window target; nothing was closed."
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label} — target not identified")
                return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))
        elif restore_foreground:
            # Capture the foreground window before desktop input changes focus.
            try:
                from actions.open_app import _active_window_description
                foreground = await asyncio.to_thread(_active_window_description)
                if not foreground:
                    result = (
                        "Could not identify the target desktop window before this operation. "
                        "Nothing was executed; specify the target app/window explicitly."
                    )
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label} — target not identified")
                    return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))
                foreground_key = foreground.casefold()
                if "edith" in foreground_key or "personal assistant" in foreground_key:
                    result = (
                        "The EDITH window is currently active, so I will not type a destructive command into it. "
                        "Focus the intended target app/terminal, then repeat the request."
                    )
                    if not self.ui.muted:
                        self.ui.set_state("LISTENING")
                    self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label} — EDITH is foreground")
                    return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))
                args["_confirmation_window_target"] = foreground
                confirmation_reason += f"\nTarget desktop window: {foreground}"
            except Exception as exc:
                result = f"Could not identify the target desktop window ({type(exc).__name__}); nothing was executed."
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label} — target not identified")
                return _completed(types.FunctionResponse(id=fc.id, name=name, response={"result": result}))

        if confirmation_reason:
            self.ui.write_log(f"ACTIVITY RUNNING: {activity_label}")
            try:
                EXECUTION.broker.authorize(name, args, minimum=backend_tier)
            except (PermissionDenied, ActionCancelled) as exc:
                result = f"Action could not start. ({exc})"
                if not self.ui.muted:
                    self.ui.set_state("LISTENING")
                self.ui.write_log(f"ACTIVITY CANCELLED: {activity_label}")
                return _completed(types.FunctionResponse(
                    id=fc.id, name=name, response={"result": result}
                ))
            # Carry the dispatcher context into the controlled worker while
            # preserving the broker's cancellation and audit checks.
            approved_ops = {name}
            if name in {"shell_execute", "code_helper", "dev_agent", "desktop_control", "file_processor"}:
                approved_ops.add("shell")
            if name == "platform_system":
                approved_ops.add(str(args.get("operation") or ""))
            approval_scope = EXECUTION.broker.approved_context(*approved_ops)
            approval_scope.__enter__()
            if args.get("_confirmation_window_target"):
                args["_confirmed_window_target"] = args.pop("_confirmation_window_target")
            # Resolve natural-language power requests before invoking the OS.
            if name == "computer_settings":
                selected_action = str(args.get("action") or "").lower().replace("-", "_")
                if selected_action not in {"restart", "shutdown"}:
                    if confirmation_reason.startswith("Restart this computer?"):
                        selected_action = "restart"
                    elif confirmation_reason.startswith("Shut down this computer?"):
                        selected_action = "shutdown"
                if selected_action in {"restart", "shutdown"}:
                    args["action"] = selected_action

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] save_memory: category={category!r} (stored value redacted)")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            self.ui.write_log(f"ACTIVITY ✓ {activity_label}")
            return _completed(types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            ))

        loop   = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "set_voice_mode":
                requested_mode = str(args.get("mode") or "").strip().lower()
                result = (await self._set_voice_mode(requested_mode, defer_reconnect=True)
                          if self._model_voice_change_allowed(requested_mode)
                          else "Voice unchanged. A direct user request is required to switch voices.")

            elif name == "open_app":
                r = await loop.run_in_executor(None, lambda: open_app(parameters=args, response=None, player=self.ui))
                result = r or "App action completed without a detailed result."
                if str(args.get("action") or "open").lower() in {"list", "list_installed", "discover", "search", "find"}:
                    self.ui.show_content("INSTALLED DESKTOP APPS", result)

            elif name == "weather_report":
                r = await loop.run_in_executor(None, lambda: weather_action(parameters=args, player=self.ui))
                result = r or "Weather delivered."

            elif name == "browser_control":
                if str(args.get("mode") or "external").lower() == "embedded":
                    action = str(args.get("action") or "go_to").lower()
                    if action == "search":
                        from urllib.parse import quote
                        engines = {
                            "google": "https://www.google.com/search?q=",
                            "bing": "https://www.bing.com/search?q=",
                            "duckduckgo": "https://duckduckgo.com/?q=",
                            "yandex": "https://yandex.com/search/?text=",
                        }
                        engine = str(args.get("engine") or "google").lower()
                        target = engines.get(engine, engines["google"]) + quote(str(args.get("query") or ""))
                    else:
                        target = str(args.get("url") or "about:blank")
                    self.ui.open_embedded_browser(target)
                    result = f"Opened EDITH's embedded browser: {target}"
                else:
                    r = await loop.run_in_executor(None, lambda: browser_control(parameters=args, player=self.ui))
                    result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(None, lambda: file_controller(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(None, lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None))
                result = r or "Message tool returned no delivery receipt. Delivery is unverified; do not resend automatically."

            elif name == "reminder":
                r = await loop.run_in_executor(None, lambda: reminder(parameters=args, response=None, player=self.ui))
                result = r or "Reminder tool returned no receipt; completion is not independently verified."

            elif name == "youtube_video":
                r = await loop.run_in_executor(None, lambda: youtube_video(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "screen_process":
                import time as _t_mod
                _now = _t_mod.monotonic()
                _cooldown = 4.0  # seconds — covers echo window after speaking ends
                _force_verify = bool(args.get("force", False))
                if self._vision_busy or (
                    (_now - self._vision_last_time) < _cooldown and not _force_verify
                ):
                    _wait = max(0, _cooldown - (_now - self._vision_last_time))
                    print(f"[Vision] ⏳ Cooldown active ({_wait:.1f}s remaining) — ignoring duplicate call")
                    result = "Vision is still processing the previous request. I will not call this again."
                else:
                    self._vision_busy      = True
                    self._vision_last_time = _now
                    angle     = args.get("angle", "screen").lower()
                    user_text = args.get("text", "What do you see?")
                    if angle == "camera":
                        img_b, mime_t = await loop.run_in_executor(None, _capture_camera)
                        self.ui.start_camera_stream()
                        self._vision_cam_active = True
                        print(f"[Vision] 📷 Camera: {len(img_b):,} bytes")
                        _stall = "camera"
                    else:
                        img_b, mime_t = await loop.run_in_executor(None, _capture_screen)
                        print(f"[Vision] 🖥️  Screen: {len(img_b):,} bytes")
                        _stall = "screen"
                    self._pending_vision = (img_b, mime_t, user_text, angle)
                    result = (
                        f"[VISION_ACTIVE] {_stall.capitalize()} captured. "
                        f"Immediately say ONE short natural sentence in the user's own language, "
                        f"telling them you are looking at their {_stall} right now. "
                        f"Do NOT describe or guess content — the actual image arrives in the NEXT message."
                    )

            elif name == "close_camera":
                self.ui.stop_camera_stream()
                result = "Camera closed."

            elif name == "computer_settings":
                r = await loop.run_in_executor(None, lambda: computer_settings(parameters=args, response=None, player=self.ui))
                result = r or "Done."

            elif name == "desktop_control":
                r = await run_code_tool(desktop_control, parameters=args, player=self.ui)
                result = r or "Done."

            elif name == "shell_execute":
                r = await run_code_tool(EXECUTION.shell, command=args.get("command", ""),
                    cwd=args.get("cwd"), timeout=args.get("timeout", 60))
                from core.execution import format_execution
                result = format_execution(r)

            elif name == "code_helper":
                r = await run_code_tool(code_helper, parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "dev_agent":
                r = await run_code_tool(dev_agent, parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "web_search":
                r = await loop.run_in_executor(None, lambda: web_search_action(parameters=args, player=self.ui))
                result = r or "Done."
                # Mirror results to the on-screen content panel
                _mode = args.get("mode", "search")
                if r and not r.startswith("No results") and not r.startswith("Search failed"):
                    _query = args.get("query") or ", ".join(args.get("items", []))
                    _label = f"{_mode.upper()} — {_query[:38]}" if _query else _mode.upper()
                    self.ui.show_content(_label, r)
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await run_code_tool(file_processor, parameters=args, player=self.ui, speak=self.speak)
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(None, lambda: computer_control(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(None, lambda: game_updater(parameters=args, player=self.ui, speak=self.speak))
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(None, lambda: flight_finder(parameters=args, player=self.ui))
                result = r or "Done."

            elif name == "project_manager":
                from agents.project_manager import run_project_manager
                result = await asyncio.to_thread(
                    run_project_manager,
                    str(args.get("action") or "status"),
                    str(args.get("project_id") or ""),
                    str(args.get("goal") or ""),
                    str(args.get("task_id") or ""),
                    str(args.get("status") or ""),
                    str(args.get("notes") or ""),
                )
                self.ui.show_content("PROJECT MANAGER", result)

            elif name == "devsecops_audit":
                from agents.devsecops import scan_project, format_report
                from core.branding import prepare_projects_dir
                project_name = str(args.get("project_name") or "").strip()
                if not project_name or Path(project_name).name != project_name or project_name in {".", ".."}:
                    result = "Specify an existing project folder name under EDITH Projects."
                else:
                    project_root = prepare_projects_dir().resolve()
                    project_path = (project_root / project_name).resolve()
                    if project_path.parent != project_root or not project_path.is_dir():
                        result = "Project not found inside EDITH Projects; no files were read."
                    else:
                        report = await asyncio.to_thread(scan_project, project_path)
                        result = format_report(report)
                        self.ui.show_content("DEVSECOPS STATIC REVIEW", result)

            elif name == "agent_manager":
                from core.agent_registry import format_agent_catalog, set_agent_enabled
                action = str(args.get("action") or "list").strip().lower()
                if action in {"list", "status"}:
                    result = format_agent_catalog()
                elif action in {"enable", "disable"}:
                    agent_id = str(args.get("agent_id") or "").strip().lower()
                    item = set_agent_enabled(agent_id, action == "enable")
                    result = f"{item['name']} ({item['id']}) is now {item['status']} · version {item['version']}."
                    self.ui.write_log(f"AGENT: {item['id']} {item['status']} · v{item['version']}")
                    self._reconfigure_reason = "Agent registry changed"
                    if self._reconfigure_event:
                        self._reconfigure_event.set()
                else:
                    result = "Use agent_manager action=list, status, enable or disable."

            elif name == "device_security":
                from agents.device_security import run_security_audit
                result = await loop.run_in_executor(None, run_security_audit, self._device_tools)
                self.ui.show_content("DEVICE SECURITY AUDIT", result)

            elif name == "smart_network":
                from agents.smart_network import run_smart_network
                action = str(args.get("action") or "discover")
                result = await asyncio.to_thread(
                    run_smart_network, action,
                    str(args.get("entity_id") or ""),
                    str(args.get("service") or ""),
                    args.get("service_data") if isinstance(args.get("service_data"), dict) else {},
                )
                self.ui.show_content("SMART HOME / LOCAL NETWORK", result)

            elif name == "knowledge_base":
                from memory.rag_store import index_file, search_knowledge, knowledge_stats
                action = str(args.get("action") or "stats").strip().lower()
                if action == "index_file":
                    file_path = str(args.get("file_path") or getattr(self.ui, "current_file", "") or "").strip()
                    if not file_path:
                        result = "Choose or upload a local document before indexing."
                    else:
                        receipt = await asyncio.to_thread(index_file, file_path)
                        result = json.dumps(receipt, ensure_ascii=False, indent=2)
                elif action == "search":
                    matches = await asyncio.to_thread(
                        search_knowledge, str(args.get("query") or ""), int(args.get("limit") or 6)
                    )
                    result = json.dumps(matches, ensure_ascii=False, indent=2) if matches else "No matching local knowledge chunks were found."
                elif action == "stats":
                    result = json.dumps(await asyncio.to_thread(knowledge_stats), ensure_ascii=False, indent=2)
                else:
                    result = "Use knowledge_base action=index_file, search or stats."
                self.ui.show_content("LOCAL KNOWLEDGE BASE", result)

            elif name == "agent_supervisor":
                from core.agent_supervisor import run_agent_supervisor
                result = await asyncio.to_thread(
                    run_agent_supervisor, str(args.get("request") or "")
                )
                self.ui.show_content("MULTI-AGENT SUPERVISOR", result)

            elif name == "task_history":
                result = format_task_history(self._agent_journal.recent(limit=10))

            elif name == "system_status":
                r = await loop.run_in_executor(None, get_system_status)
                result = str(r)

            elif name == "performance_metrics":
                result = self._latency_metrics.format()

            elif name == "platform_system":
                receipt = await loop.run_in_executor(None, self._device_tools.execute, args)
                result = format_device_result(receipt)

            elif name == "manage_monitor":
                action = args.get("action", "").lower().strip()
                topic  = args.get("topic", "").strip()
                if action == "add" and topic:
                    result = await asyncio.to_thread(add_monitor, topic)
                elif action == "remove" and topic:
                    result = await asyncio.to_thread(remove_monitor, topic)
                elif action == "list":
                    topics = await asyncio.to_thread(list_monitors)
                    result = ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
                else:
                    result = "Specify action (add/remove/list) and a topic."

            elif name == "shutdown_edith":
                self.ui.write_log("SYS: Shutdown requested.")
                async def _do_shutdown():
                    await self._save_session_summary()
                    if self.session:
                        try:
                            await self.session.send_client_content(
                                turns={"parts": [{"text": "Say a brief natural goodbye to the user."}]},
                                turn_complete=True,
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(1.5)
                    import os as _os
                    _os._exit(0)
                asyncio.create_task(_do_shutdown())

            else:
                if self._plugin_registry.has(name):
                    r = await loop.run_in_executor(
                        None,
                        lambda: self._plugin_registry.run(name, args, player=self.ui, session_memory=None)
                    )
                    result = r or "Done."
                else:
                    result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if approval_scope is not None:
            approval_scope.__exit__(None, None, None)
        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        outcome = activity_outcome(result)
        if outcome == "error":
            self.ui.write_log(f"ACTIVITY ERROR: {activity_label}")
        elif outcome == "warning":
            self.ui.write_log(f"ACTIVITY NOTE: {activity_label}")
        else:
            self.ui.write_log(f"ACTIVITY ✓ {activity_label}")
        print(f"[Assistant] Tool completed: {name}; outcome={outcome}")
        return _completed(types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        ))

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            # Do not send microphone packets captured just before playback began.
            # They can echo the assistant into Live's automatic interruption detector.
            gate = getattr(self, "_mic_can_send", None)
            player = getattr(self, "_speech_player", None)
            if (not gate() if gate else self._is_speaking or
                    bool(player and player.snapshot()["playing"])):
                continue
            await self.session.send_realtime_input(media=msg)

    def _publish_mic_activity(self, data: bytes, source: str = "PC") -> None:
        """Ignore late PCM meter callbacks after the Qt interface has closed."""
        if getattr(self.ui, "closed", False):
            return
        self.ui.show_input_level(pcm16_level(data), source)

    async def _listen_audio(self):
        """Use the default PC microphone when available, without taking down
        text input, phone input or the cloud session if hardware is missing.
        Re-probe periodically so plugging a microphone back in can recover.
        """
        print("[Assistant] 🎤 Mic started")
        loop = asyncio.get_running_loop()

        def callback(indata, frames, time_info, status):
            if self._mic_can_send() and not self.ui.muted and not self._phone_active:
                data = indata.tobytes()
                now = time.monotonic()
                if now - self._last_mic_meter_at >= 0.10:
                    self._last_mic_meter_at = now
                    loop.call_soon_threadsafe(
                        self._publish_mic_activity, data, "PC"
                    )
                loop.call_soon_threadsafe(
                    enqueue_latest_audio,
                    self.out_queue,
                    {"data": data, "mime_type": "audio/pcm"},
                )

        unavailable = False
        while True:
            try:
                with sd.InputStream(
                    samplerate=SEND_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    blocksize=CHUNK_SIZE,
                    callback=callback,
                ):
                    print("[Assistant] 🎤 Mic stream open")
                    if unavailable:
                        self.ui.write_log("AUDIO: Microphone available again.")
                    unavailable = False
                    while True:
                        await asyncio.sleep(0.1)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                print(f"[Assistant] Microphone unavailable: {type(exc).__name__}: {exc}")
                if not unavailable:
                    self.ui.write_log(
                        "AUDIO: Microphone unavailable or sample rate unsupported. "
                        "Text and phone input remain available; retrying automatically."
                    )
                unavailable = True
                await asyncio.sleep(5)

    async def _receive_audio(self):
        print("[Assistant] 👂 Recv started")
        from core.voice_intent import requested_voice_mode
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    sc = response.server_content
                    server_interrupted = bool(sc and getattr(sc, "interrupted", False))
                    if server_interrupted:
                        self.audio_in_queue.clear()
                        self._interrupted = False
                        self._response_pending = False
                        out_buf = []
                        self.set_speaking(False)
                        self.ui.write_log("AUDIO: Provider interrupted the response; cancelled audio was cleared.")

                    pcm = response_pcm(response)
                    if pcm:
                        if self._interrupted or server_interrupted:
                            pass  # discard: interrupted
                        else:
                            if self._pending_text_started_at is not None:
                                elapsed_ms = round(
                                    (time.perf_counter() - self._pending_text_started_at) * 1000
                                )
                                self._pending_text_started_at = None
                                metrics = getattr(self, "_latency_metrics", None)
                                if metrics is not None:
                                    metrics.record("text_to_first_audio", elapsed_ms)
                                self.ui.write_log(
                                    f"PERF: Gemini Live first audio after text request: {elapsed_ms} ms."
                                )
                            if self._turn_done_event and self._turn_done_event.is_set():
                                self._turn_done_event.clear()
                            # Preserve every byte, including audio received before the
                            # device opens. Only microphone traffic may drop stale chunks.
                            self.audio_in_queue.put_nowait(pcm)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt and txt != (out_buf[-1] if out_buf else ""):
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                self._last_user_speech = time.monotonic()
                                if getattr(self, "_task_input_locked", False):
                                    # Work is exclusive from the user's point of
                                    # view.  This path accepts only consent or
                                    # stop, never a competing voice task.
                                    self._handle_busy_input(txt, "voice")
                                else:
                                    self._response_pending = True
                                    if not self._is_speaking:
                                        self.ui.set_state("THINKING")
                                    if not in_buf:
                                        self._recent_voice_intent = None
                                    in_buf.append(txt)
                                    mode = requested_voice_mode(" ".join(in_buf))
                                    if mode:
                                        self._recent_voice_intent = (mode, time.monotonic())

                        if sc.turn_complete:
                            self.audio_in_queue.finish_turn()
                            self._response_pending = False
                            if not self._is_speaking and self.audio_in_queue.empty():
                                self.ui.set_state("LISTENING")
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            # If this turn_complete ends an interrupted response, clear the
                            # flag and skip all further processing for that turn.
                            if self._interrupted:
                                self._interrupted = False
                                in_buf  = []
                                out_buf = []
                                continue

                            full_in = " ".join(in_buf).strip()
                            spoken_voice_mode = requested_voice_mode(full_in)
                            if spoken_voice_mode:
                                await self._set_voice_mode(spoken_voice_mode)
                                in_buf = []
                                out_buf = []
                                continue
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                self._session_log.append(f"User: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "user",
                                        "text": full_in,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"{self._asst_name}: {full_out}")
                                self._session_log.append(f"{self._asst_name}: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(self._dashboard.broadcast({
                                        "type": "log", "speaker": "jarvis",
                                        "text": full_out,
                                        "ts": datetime.now().isoformat(),
                                    }))
                            out_buf = []

                            # Vision injection: model finished tool-response turn → now send the image
                            if self._pending_vision and self.session:
                                import base64 as _b64
                                img_b, mime_t, question, angle = self._pending_vision
                                self._pending_vision = None
                                b64 = _b64.b64encode(img_b).decode("ascii")
                                print(f"[Vision] 📤 {len(img_b):,} bytes (angle={angle}) → main session")
                                self._response_pending = True
                                self.ui.set_state("THINKING")
                                await self.session.send_client_content(
                                    turns={"parts": [
                                        {"inline_data": {"mime_type": mime_t, "data": b64}},
                                        {"text": question},
                                    ]},
                                    turn_complete=True,
                                )
                                # Mark next turn_complete behaviour depending on angle
                                if self._vision_cam_active:
                                    # Camera: keep busy until EDITH finishes speaking the answer
                                    self._vision_cam_active    = False
                                    self._vision_close_pending = True
                                else:
                                    # Screen-only: no camera to close; release busy flag now
                                    self._vision_busy = False
                            elif self._vision_close_pending:
                                # This turn_complete IS the vision answer — close camera + release busy flag
                                self._vision_close_pending = False
                                self._vision_busy = False
                                async def _cam_close():
                                    await asyncio.sleep(2.0)
                                    self.ui.stop_camera_stream()
                                asyncio.create_task(_cam_close())

                    if response.tool_call:
                        self._response_pending = True
                        # Tools have their own serial consumer. Receiving PCM/control
                        # events must continue while a tool is running or speaking.
                        self._tool_call_queue.put_nowait(response.tool_call.function_calls)
        except Exception as e:
            # The session owner converts this into one concise reconnect event.
            # Printing here as well previously produced the same 1011 traceback
            # twice (once here and once in the TaskGroup exception tree).
            print(f"[Assistant] Live receive ended: {type(e).__name__}: {e}")
            raise

    async def _process_tool_calls(self):
        """Keep batch ordering and existing approvals without blocking receive."""
        while True:
            calls = await self._tool_call_queue.get()
            if getattr(self, "_task_input_locked", False):
                # A model can still emit calls from audio received while a task
                # is active. Acknowledge them explicitly without queueing a
                # competing action; only the current approval/interrupt reply
                # may affect the active batch.
                blocked = [types.FunctionResponse(
                    id=fc.id, name=fc.name,
                    response={"result": "EDITH is still completing the current task. This new action was not queued."},
                ) for fc in calls]
                self.ui.write_log(f"TASKS: Ignored {len(blocked)} competing tool request(s) while work was active.")
                await self.session.send_tool_response(function_responses=blocked)
                continue
            self._task_input_locked = True
            try:
                fn_responses = await self._execute_tool_batch(calls)
                self._response_pending = True
                if not self._is_speaking:
                    self.ui.set_state("THINKING")
                await self.session.send_tool_response(function_responses=fn_responses)
                # voiceName is fixed at setup; reconnect only after delivering the response.
                if self._reconfigure_reason and self._reconfigure_event:
                    self._reconfigure_event.set()
            finally:
                self._task_input_locked = False

    async def _play_audio(self):
        """Observe a dedicated writer; no per-chunk executor/scheduler handoff."""
        player = SpeechPlayer(self.audio_in_queue, sd.RawOutputStream)
        self._speech_player = player
        player.start()
        was_playing = False
        try:
            while True:
                state = player.snapshot()
                self._audio_output_ready = state["ready"]
                playing = state["playing"] and not self._interrupted
                if playing != was_playing:
                    self.set_speaking(playing)
                    was_playing = playing
                self.ui.show_output_level(state["level"] if playing else 0.)
                while not player.events.empty():
                    self.ui.write_log(player.events.get_nowait())
                await asyncio.sleep(.025)
        finally:
            player.stop()
            # Normal PortAudio writes are 50 ms. Bound teardown if a driver hangs.
            for _ in range(40):
                if player.stopped.is_set():
                    break
                await asyncio.sleep(.025)
            self._speech_player = None
            self._audio_output_ready = False
            self.set_speaking(False)
            self.ui.show_output_level(0.)

    async def _wait_for_narration_end(self, timeout=30.) -> bool:
        """Wait for generation AND hardware drain, with a stable idle boundary."""
        buffer = self.audio_in_queue
        deadline = time.monotonic() + timeout
        idle_since = None
        while self.session and self.audio_in_queue is buffer:
            if self._interrupted:
                return False
            player = self._speech_player
            playing = player is not None and player.snapshot()["playing"]
            now = time.monotonic()
            done = (self._turn_done_event.is_set() and buffer.finished
                    and buffer.empty() and not playing)
            if done:
                if idle_since is not None and now - idle_since >= .1:
                    return True
                if idle_since is None:
                    idle_since = now
            else:
                idle_since = None
            if now >= deadline:
                return False
            await asyncio.sleep(.025)
        return False

    # ── Morning briefing ────────────────────────────────────────────────────────

    async def _send_startup_briefing(self) -> None:
        """
        Two-phase briefing optimized for speed:
          Phase 1 — greeting (no tools) → stream speech as soon as available
          Phase 2 — news pre-fetched in a background thread while Phase 1 plays,
                    delivered as ready text (no Gemini tool-call round-trip) and
                    shown on the UI content panel. Waits for turn_complete event
                    instead of a fixed sleep so there is no unnecessary gap.
        """
        memory   = load_memory()
        identity = memory.get("identity", {})

        def _val(k: str) -> str:
            e = identity.get(k, {})
            return (e.get("value", "") if isinstance(e, dict) else str(e)).strip()

        lang = _val("language")
        name = _val("name")
        time_str = datetime.now().strftime("%H:%M")

        # Start fetching news immediately — runs in parallel while phase 1 plays
        loop = asyncio.get_event_loop()
        news_future = loop.run_in_executor(None, _fetch_news_sync, "top world news today")

        if not self.session:
            return
        briefing_session = self.session

        # ── Phase 1: instant greeting ─────────────────────────────────────────
        lang_clause = f" Respond in {lang}." if lang else ""
        name_clause = f" Address the user as {name}." if name else ""

        # Inject last session context if available — pop removes it so it's never repeated
        last = await asyncio.to_thread(pop_last_session)
        session_clause = ""
        if last:
            try:
                _delta = (datetime.now() - datetime.strptime(last["date"], "%Y-%m-%d")).days
                _when  = "earlier today" if _delta == 0 else ("yesterday" if _delta == 1 else f"{_delta} days ago")
            except Exception:
                _when = "last time"
            session_clause = (
                f" Also briefly and naturally mention that {_when}: {last['summary']}"
            )

        p1 = (
            f"Greet the user warmly, mention it is {time_str}, and say you are fetching today's news now.{session_clause} "
            f"Keep it to 2 short sentences max. Do not call any tools.{lang_clause}{name_clause}"
        )

        # Clear the turn-done event so we can wait for Phase 1 to finish
        if self._turn_done_event:
            self._turn_done_event.clear()

        await self.session.send_client_content(
            turns={"parts": [{"text": p1}]},
            turn_complete=True,
        )
        self.ui.write_log("SYS: Briefing phase 1 (greeting) sent.")

        # ── Phase 2: fire as soon as Phase 1 audio is done ───────────────────
        async def _deliver_news():
            try:
                lang_str = f" Respond in {lang}." if lang else ""

                # News is already fetching. Never send another prompt while the
                # greeting is still queued/playing, even after generation ends.
                news_done   = asyncio.wrap_future(news_future)
                if not await self._wait_for_narration_end() or self.session is not briefing_session:
                    self.ui.write_log("SYS: News narration skipped because greeting was interrupted, timed out or session changed.")
                    return

                try:
                    news_text = await asyncio.wait_for(news_done, timeout=8.0)
                except Exception as e:
                    self.ui.write_log(f"SYS: News fetch timed out/failed: {e!r}")
                    news_text = ""

                if self.session is not briefing_session:
                    return

                failed = (not news_text) or news_text.startswith(
                    ("No news found", "Search failed", "Please provide")
                )
                if not failed:
                    # Show on UI content panel immediately
                    self.ui.show_content("NEWS — top world news today", news_text)

                    p2 = (
                        f"[BRIEFING] Here are today's top news headlines:\n{news_text}\n\n"
                        "Pick ONE headline, summarise it in one sentence, then say the full list "
                        f"is displayed on screen. Do not call any tools.{lang_str}"
                    )
                else:
                    self.ui.write_log(
                        f"SYS: News unavailable — backend returned: {news_text[:120]!r}"
                    )
                    p2 = (
                        "News headlines could not be fetched right now. "
                        f"Let the user know briefly.{lang_str}"
                    )

                await self.session.send_client_content(
                    turns={"parts": [{"text": p2}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Briefing phase 2 (news) sent.")
            except Exception as e:
                print(f"[Briefing] Phase 2 error: {e}")
                self.ui.write_log(f"SYS: Briefing phase 2 failed: {e}")

        asyncio.create_task(_deliver_news())

    # ── Session memory ──────────────────────────────────────────────────────────

    async def _save_session_summary(self) -> None:
        """Summarise the current session in 1-2 sentences and save to long_term.json."""
        log = self._session_log
        if len(log) < 3:          # need at least one exchange to be worth saving
            return
        self._session_log = []    # reset immediately so the next session starts clean

        memory = load_memory()
        lang_entry = memory.get("identity", {}).get("language", {})
        lang = (lang_entry.get("value", "") if isinstance(lang_entry, dict) else str(lang_entry)).strip()
        lang = lang or "English"

        convo = "\n".join(log[-40:])   # cap at last 40 turns to stay within token budget
        prompt = (
            f"Summarize this conversation in 1-2 sentences in {lang}. "
            "Focus on what the user accomplished or discussed. "
            "Output ONLY the summary text, nothing else:\n\n" + convo
        )
        try:
            from google import genai as _genai
            client = _genai.Client(api_key=_get_api_key())
            resp   = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-flash-latest",
                contents=prompt,
            )
            summary = (resp.text or "").strip()
            if summary:
                save_session_summary(summary, lang)
        except Exception as e:
            print(f"[Memory] ⚠️ Session summary failed: {e}")

    # ── System monitor ──────────────────────────────────────────────────────────

    async def _run_system_monitor(self) -> None:
        """Background task: voice alerts when metrics exceed thresholds."""
        while True:
            await asyncio.sleep(10)
            alert = await asyncio.to_thread(self._sys_monitor.check)
            if not alert or not self.session:
                continue
            # Don't interrupt an active conversation
            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking or (time.monotonic() - self._last_user_speech) < 10:
                continue
            try:
                await self.session.send_client_content(
                    turns={"parts": [{"text": alert}]},
                    turn_complete=True,
                )
            except Exception as e:
                print(f"[Monitor] ⚠️ Could not send alert: {e}")

    # ── Background monitor ──────────────────────────────────────────────────────

    async def _run_background_monitor(self) -> None:
        """Check user-configured topics once per day; speak alerts when new headlines appear."""
        await asyncio.sleep(300)          # wait 5 min after startup before first check
        while True:
            if self.session:
                # Don't interrupt if user spoke recently or EDITH is mid-sentence
                with self._speaking_lock:
                    speaking = self._is_speaking
                recent_speech = (time.monotonic() - self._last_user_speech) < 30
                if not speaking and not recent_speech:
                    try:
                        alerts = await asyncio.to_thread(monitor_check_all)
                        memory = load_memory()
                        lang_e = memory.get("identity", {}).get("language", {})
                        lang   = (lang_e.get("value", "") if isinstance(lang_e, dict) else str(lang_e)).strip() or "English"
                        for alert in alerts:
                            msg = (
                                f"{alert}\n\n"
                                f"Inform the user about this development naturally in {lang}. "
                                "One brief sentence only."
                            )
                            await self.session.send_client_content(
                                turns={"parts": [{"text": msg}]},
                                turn_complete=True,
                            )
                            self.ui.write_log(f"SYS: Monitor alert sent.")
                            await asyncio.sleep(6)   # gap between consecutive alerts
                    except Exception as e:
                        print(f"[Monitor] ⚠️ Background check error: {e}")
            await asyncio.sleep(1800)     # check every 30 minutes

    # ── Proactive mode ──────────────────────────────────────────────────────────

    async def _run_proactive_mode(self) -> None:
        """
        Background task: periodically checks if the user has been silent long enough,
        then hands time + memory context to Gemini so it can decide what (if anything)
        to say proactively. No hardcoded rules — Gemini makes the call.
        """
        while True:
            await asyncio.sleep(60)   # evaluate once per minute

            if not self.session:
                continue

            with self._speaking_lock:
                speaking = self._is_speaking
            if speaking:
                continue

            if not self._proactive.should_trigger(self._last_user_speech):
                continue

            self._proactive.mark_triggered()

            try:
                memory       = await asyncio.to_thread(load_memory)
                monitors     = await asyncio.to_thread(list_monitors)
                recent_turns = self._session_log[-8:] if self._session_log else []
                prompt = self._proactive.build_prompt(
                    memory       = memory,
                    monitors     = monitors or None,
                    recent_turns = recent_turns or None,
                )
                await self.session.send_client_content(
                    turns={"parts": [{"text": prompt}]},
                    turn_complete=True,
                )
                self.ui.write_log("SYS: Proactive check-in.")
            except Exception as e:
                print(f"[Proactive] ⚠️ {e}")

    # ── Phone audio relay ────────────────────────────────────────────────────────

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True   # phone is streaming — silence PC mic
            if self._mic_can_send() and not self.ui.muted:
                enqueue_latest_audio(self.out_queue, chunk)
                now = time.monotonic()
                if now - self._last_mic_meter_at >= 0.10:
                    self._last_mic_meter_at = now
                    data = chunk.get("data", b"")
                    if isinstance(data, (bytes, bytearray, memoryview)):
                        self._publish_mic_activity(data, "PHONE")

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()

    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                if getattr(self, "_task_input_locked", False):
                    self._handle_busy_input(str(text), "remote text")
                    if self._dashboard:
                        await self._dashboard.broadcast({
                            "type": "sys",
                            "text": "EDITH is completing the active task; new commands are not queued.",
                        })
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    self._response_pending = True
                    self.ui.set_state("THINKING")
                    await self.session.send_client_content(
                        turns={"parts": [{"text": text}]},
                        turn_complete=True,
                    )
                    self.ui.write_log("NET: Remote command delivered to Gemini Live.")
                else:
                    print("[Dashboard] Remote command not delivered (no Live session).")
                    await self._dashboard.broadcast({
                        "type": "sys",
                        "text": "Remote command was not delivered; check EDITH before retrying.",
                    })
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                self._response_pending = False
                if not self._is_speaking:
                    self.ui.set_state("LISTENING")
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()
        self._reconfigure_event = asyncio.Event()
        self._api_key_update_event = asyncio.Event()

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer
            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            self._dashboard.set_live_ready_callback(lambda: self.session is not None)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        while True:
            try:
                print("[Assistant] Connecting...")
                self._connecting = True
                self.ui.set_state("THINKING")
                connect_started_at = time.perf_counter()
                # Memory/config file reads must not block remote commands or
                # other async operations on the Live session event loop.
                config = await asyncio.to_thread(self._build_config)

                # Fresh client on every reconnect — avoids stale HTTP session state
                # v1alpha carries the enhanced audio features (affective dialog,
                # proactive audio); if they get rejected we fall back to v1beta.
                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1alpha" if self._enhanced_live else "v1beta"}
                )

                async with (
                    client.aio.live.connect(model=_get_live_voice_model(), config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session          = session
                    self._connecting       = False
                    self.audio_in_queue   = SpeechBuffer()  # Lossless narration; explicit byte budget.
                    self._tool_call_queue = asyncio.Queue(maxsize=16)
                    self._audio_output_ready = False
                    # 1024 samples / 16 kHz ≈ 64 ms per microphone chunk.
                    # 32 chunks cap stale audio at ~2 s instead of ~12.8 s.
                    self.out_queue        = asyncio.Queue(maxsize=32)
                    self._turn_done_event = asyncio.Event()

                    # Reset transient state that must not carry over from a previous session
                    self._pending_vision       = None
                    self._vision_cam_active    = False
                    self._vision_close_pending = False
                    self._vision_busy          = False
                    self._vision_last_time     = 0.0
                    self._interrupted          = False
                    self._pending_text_started_at = None

                    print("[Assistant] Connected.")
                    # A healthy connection starts a fresh retry sequence. In
                    # particular, do not carry an old 60-second delay forward.
                    self._conn_backoff = 0
                    live_connect_ms = round((time.perf_counter() - connect_started_at) * 1000)
                    self._latency_metrics.record("live_connect", live_connect_ms)
                    self.ui.write_log(
                        f"PERF: Gemini Live session ready in "
                        f"{live_connect_ms} ms."
                    )
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: Assistant ready.")

                    if self._dashboard:
                        await self._dashboard.broadcast({"type": "status", "state": "active"})

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._process_tool_calls())
                    tg.create_task(self._play_audio())
                    tg.create_task(self._run_system_monitor())
                    tg.create_task(self._run_background_monitor())
                    tg.create_task(self._run_proactive_mode())
                    tg.create_task(self._watch_session_reconfigure())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

                    # Confirm a voice change only after the selected preset is connected.
                    if self._voice_confirmation:
                        voice_message = self._voice_confirmation
                        self._voice_confirmation = None
                        await session.send_client_content(
                            turns={"parts": [{"text": voice_message}]},
                            turn_complete=True,
                        )

                    # Morning briefing — fires once per process launch (if enabled)
                    if not self._briefing_sent and get_brief_enabled():
                        self._briefing_sent = True
                        tg.create_task(self._send_startup_briefing())

            except asyncio.CancelledError:
                # asyncio.run() shutdown must not be swallowed by the broad
                # TaskGroup error handler and turned into another connection.
                raise
            except KeyboardInterrupt:
                raise
            except SystemExit:
                raise
            except BaseException as e:
                self._connecting = False
                # Catches both Exception and BaseExceptionGroup (Python 3.11+
                # TaskGroup raises BaseExceptionGroup when tasks are cancelled
                # externally, which `except Exception` would miss, letting the
                # exception escape the while-loop and causing asyncio.run() to
                # start shutdown — resulting in "executor after shutdown" errors).
                err_str = _exception_summary(e)
                if self._reconfigure_reason:
                    reason = self._reconfigure_reason
                    self._reconfigure_reason = None
                    if self._reconfigure_event:
                        self._reconfigure_event.clear()
                    self._conn_backoff = 0
                    self.ui.write_log(f"SYS: Applying {reason}; opening a fresh Gemini Live session.")
                    continue

                transient_live_disconnect = any(token in err_str.casefold() for token in (
                    "1011", "connectionclosed", "internal error occurred",
                    "websocket", "connection closed",
                ))
                if transient_live_disconnect:
                    print(f"[Assistant] Live session disconnected: {err_str}")
                    self.ui.write_log("NET: Gemini Live session disconnected; reconnecting automatically.")
                else:
                    print(f"[Assistant] Error ({type(e).__name__}): {err_str}")
                    traceback.print_exc()

                # Enhanced audio features rejected by the server (preview API
                # drift) — drop them and reconnect with the plain config.
                if self._enhanced_live and (
                    "INVALID_ARGUMENT" in err_str
                    or "affective" in err_str.lower()
                    or "proactiv" in err_str.lower()
                    or "Unknown name" in err_str
                    or "unexpected keyword" in err_str
                ):
                    self._enhanced_live = False
                    self.ui.write_log(
                        "SYS: Advanced audio features unavailable — reconnecting without them."
                    )
                    continue

                # Invalid API key — stop hammering the API, prompt re-configuration
                if "API key not valid" in err_str or "1007" in err_str:
                    self.ui.write_log("ERR: Gemini rejected the saved API key. Test and save a replacement in Settings.")
                    self._response_pending = False
                    self.ui.set_state("SLEEPING")
                    if self._api_key_update_event:
                        self._api_key_update_event.clear()
                    self.ui._win.open_api_key_settings_signal.emit()
                    if self._api_key_update_event:
                        await self._api_key_update_event.wait()
                        self._api_key_update_event.clear()
                    self._conn_backoff = 0
                    continue

                # Network / timeout errors — log clearly and back off
                is_net_err = any(k in err_str for k in (
                    "TimeoutError", "timed out", "getaddrinfo", "CancelledError",
                    "ConnectionRefusedError", "OSError", "Cannot connect",
                    "1011", "ConnectionClosed", "Internal error occurred", "WebSocket",
                ))
                if is_net_err:
                    _conn_backoff = retry_delay(getattr(self, "_conn_backoff", 0))
                    self._conn_backoff = _conn_backoff
                    self.ui.write_log(
                        f"NET: Bağlantı kurulamadı — {_conn_backoff}s sonra tekrar deneniyor. "
                        "(VPN gerekiyor olabilir)"
                    )
                else:
                    self._conn_backoff = 3
            finally:
                self._connecting = False
                self.session = None
                # Only save if there was a real conversation (≥3 turns)
                if len(self._session_log) >= 3:
                    asyncio.create_task(self._save_session_summary())

            self.set_speaking(False)
            self._response_pending = False
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            # A clean close or an explicit reset also needs a nonzero pause;
            # otherwise a closing transport can spin the connect loop.
            delay = getattr(self, "_conn_backoff", 0) or 3
            self._latency_metrics.record("live_reconnect_wait", delay * 1000)
            print(f"[Assistant] Reconnecting in {delay}s...")
            await asyncio.sleep(delay)

def main():
    from core.runtime_diagnostics import install_diagnostics, record_exit
    install_diagnostics()
    ui = EdithUI("face.png")
    ui._app.aboutToQuit.connect(lambda: record_exit("Qt aboutToQuit"))

    def runner():
        if not ui.wait_for_api_key():
            return  # User closed setup before initialization; do not start Live/audio.
        edith = EdithLive(ui)
        try:
            asyncio.run(edith.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    exit_code = ui.root.mainloop()
    record_exit(f"Qt event loop returned: {exit_code}")

if __name__ == "__main__":
    main()

