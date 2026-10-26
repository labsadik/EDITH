# Repository audit — pre-implementation baseline

Baseline: `a21c4b8ba59b7c96088349db2358a14d121fea34`, branch `ui/edith-interface`.
Scope: all 100 committed files (1,227,566 local UTF-8 bytes plus the video). Every
committed text file was read in full by the audit scanner, Python was parsed with
AST, HTML/JS contracts were inventoried, and entry/dispatch/UI/platform paths were
reviewed. One binary was inspected with Qt/FFmpeg. Local copies differ from GitHub
only in materialization-added final newlines. Generated local test directories,
credentials and caches are not committed source and are excluded. No application
source changed during Phase 0. Line references below refer to this baseline.

## Findings and evidence

- Desktop is **native PyQt6**, not a web UI: 4,654-line `ui.py`, painter HUD and
  Qt Multimedia. There is **no desktop Python ↔ JavaScript bridge** and no React,
  Tailwind, Three.js, GSAP, npm build or WebEngine dependency. Remote HTML is a
  separate FastAPI client, not the desktop shell.
- Current 1366×697 client geometry was rendered offscreen: header 54 px, footer
  24 px, left 160 px, center x=160 width=866, right x=1026 width=340. Log is
  (1038,124,316,210), file zone (1038,380,316,90), input (1038,539,274,36),
  interrupt (1038,585,316,34), mic (1038,629,316,32). These rectangles are the
  migration baseline; no new user screenshot is attached to this request.
- Existing 188 tests passed before this request (synthetic PCM, headless Qt,
  mocked integrations). They establish regressions, not physical Windows/macOS/
  Linux, API-key, microphone, permission or 60 FPS certification.
- OS support exists piecemeal in actions, with broad exception handling, optional
  dependencies and Linux desktop assumptions. No single SystemController exists.
- Permission policy is selective (`core/action_guard.py`): ordinary arbitrary
  terminal commands are intentionally unconfirmed in the baseline test. Four
  enforced tiers, Tier settings and native elevation abstraction are absent.
- ESC stops narration only; cancel-waiting stops queued scheduler tasks only.
  Running executor functions and child process trees are not centrally cancelled.
- API keys are plaintext JSON (`config/api_keys.json`) read independently by many
  modules. OS keychain migration is absent. Task journal stores metadata only;
  complete redacted per-action audit records/streaming are absent.
- Telemetry is duplicated in UI/system monitor. Some sampling is background,
  but uptime/process reads still run in Qt's update slot. GPU/temperature can be
  N/A. Total/per-core/frequency/load/swap/disk/battery detail is incomplete in UI.
- Theme is fixed dark/accent-recolored Qt. System detection/live override and
  light theme are absent; component colors are frequently hardcoded.
- Narration burst loss and receive-blocking were addressed in the preceding
  commit. Keep this isolated writer and its lossless semantics during migration.
- Generated desktop code uses in-process exec; generated projects/installers and
  game/reminder schedulers use subprocesses without one process registry. This
  prevents the requested complete kill-switch guarantee in the baseline.
- GUI automation and upload flows remain best-effort; coordinate upload is fragile.
  Wayland screen/window/keyboard control requires supported compositor APIs/portals;
  it must not be advertised as equivalent to X11 or given blanket kernel access.

## Entry point and startup flow

`python main.py` → Windows subprocess-console patch → UTF-8 streams → startup
preflight → action imports → `EdithUI('face.png')` creates QApplication/MainWindow,
read config, native timers/clipboard and setup if needed → Qt event loop on main
thread. A daemon runner waits for setup then constructs EdithLive and starts an
asyncio loop. EdithLive discovers plugins and creates scheduler/journal/monitors;
`run()` initializes optional remote dashboard then connects Gemini Live. A session
TaskGroup owns microphone send/capture, audio receive, serial tool consumer, audio
writer observer, monitors and reconnect watcher. Tools mostly use executor threads.
`core/llm_client.py` is a separate internal-agent text path (Ollama or compatible
HTTP); it is not the Gemini native audio transport. `setup.py` explicitly installs
requirements/Playwright when run; optional installer/TTS modules can also install.

## Existing bridge contract — preserve names

Desktop UI → Python: `on_text_command(text)`, `on_interrupt()`,
`on_cancel_queued_tasks()`, `on_remote_clicked()`, `on_api_key_saved()`,
`on_voice_mode_clicked(mode)`, `get_plugins()`, plus native control handlers below.
Python → desktop uses Qt signals, **no JS functions**. EdithUI's facade is retained:
`set_state`, `show_input_level`, `show_playback_state`, `show_output_level`,
`write_log`, `show_content`, `wait_for_api_key`, `confirm_sensitive_action`,
`prompt_reconfig`, `show_camera_frame`, `start_camera_stream`, `stop_camera_stream`,
`notify_phone_connected`, `start_speaking`, `stop_speaking`, and properties
`muted`, `current_file`, `assistant_name`, `closed` and callback properties.

Qt signal names/signatures:
- `_url_prompt_sig(object)`
- `voice_mode_signal(str)`
- `open_api_key_settings_signal()`
- `_log_sig(str)`
- `_state_sig(str)`
- `_playback_sig(bool)`
- `_output_level_sig(float)`
- `_mic_level_sig(float, str)`
- `_content_sig(str, str)`
- `_reconfig_sig()`
- `_camera_sig(bytes)`
- `_cam_stream_sig(bool)`
- `_cam_frame_sig(bytes)`
- `_clipboard_sig(str)`
- `_confirm_action_sig(str, str, object)`
- `task_status_signal(int, int, int)`
- `task_detail_signal(object)`
- `text_send_failed_signal(str)`

Native components: header/clock/gear, SYS MONITOR MetricBars and info/badges,
HudCanvas/camera stack/content splitter, task counter/cancel/chevron/detail rows,
LogWidget, FileDropZone/hint, input/send, interrupt, mic/footer. Native overlays:
ApiKeyOverlay, SetupOverlay, CustomizeOverlay/HueWheel, PluginManagerOverlay,
ClipboardPanel, RemoteKeyOverlay, camera preview, sensitive-action QDialog and URL
QInputDialog. Existing object names: `TaskDetailsPanel`, `QuickDrawer`,
`ContentPanel`, `confirmAction`; dynamic property `role=danger` is retained.

Control handlers (including secondary settings actions) are preserved below:
- `MainWindow._show_url_prompt` at `ui.py:2580`
- `MainWindow._clear_selected_file` at `ui.py:2596`
- `MainWindow._escape_action` at `ui.py:2601`
- `MainWindow._create_desktop_shortcut` at `ui.py:2873`
- `MainWindow._toggle_fullscreen` at `ui.py:2985`
- `MainWindow._request_cancel_queued` at `ui.py:3242`
- `MainWindow._toggle_task_details` at `ui.py:3246`
- `MainWindow._toggle_reduced_motion` at `ui.py:3598`
- `MainWindow._request_voice_mode` at `ui.py:3608`
- `MainWindow._open_api_key_settings` at `ui.py:3640`
- `MainWindow._toggle_drawer` at `ui.py:3662`
- `MainWindow._focus_command_input` at `ui.py:3716`
- `MainWindow._show_action_confirmation` at `ui.py:3812`
- `MainWindow._on_file_selected` at `ui.py:3966`
- `MainWindow._open_remote` at `ui.py:3991`
- `MainWindow._toggle_autostart` at `ui.py:4097`
- `MainWindow._toggle_brief` at `ui.py:4182`
- `MainWindow._open_customize` at `ui.py:4218`
- `MainWindow._open_plugin_manager` at `ui.py:4279`
- `MainWindow._do_interrupt` at `ui.py:4327`
- `MainWindow._toggle_mute` at `ui.py:4331`
- `MainWindow._send` at `ui.py:4372`

Remote contract: existing HTTP `/login`, `/auto-login`, `/api/device-login`,
`/api/revoke-devices`, `/api/session`, `/api/command`, `/api/wake`, `/api/upload`,
`/api/files`, `/uploads/{filename}`, WS `/ws`, `/ws/phone-audio` and
`/static/crypto.js` remain. Existing payload/event names include `log`, `sys`,
`status`, `file_received`, `ping`, `pong`, stable event `id`, `speaker`, `text`,
`state`, `ts`; audio PCM transport and pairing/session token headers remain.
Remote page JS functions and DOM inventory are listed in the full inventory below.

### `dashboard/static/app.html`

- IDs: `${id}_bar`, `${id}_st`, `enc`, `feed`, `file-inp`, `inp`, `mic-btn`, `pill`, `send-btn`, `st`, `toast`, `wake`
- Data attributes: none
- DOM event names: change, keydown, offline, online, visibilitychange
- Named JS functions: `_authHeader`, `_authFetch`, `_initCrypto`, `_encrypt`, `_setLinkStatus`, `_clearRemoteAuth`, `_verifyRemoteSession`, `_stopHeartbeat`, `_scheduleReconnect`, `_connectRemote`, `setStatus`, `_appendFeed`, `append`, `sys`, `esc`, `_fileIcon`, `_fmtSize`, `_uploadFile`, `_onFileReceived`, `doSend`, `doWake`, `toast`, `_sendVoicePacket`, `_micIdle`, `_f32toPcm16`, `_showVoiceSetup`, `doMic`, `_stopVoice`

### `dashboard/static/login.html`

- IDs: `card`, `connect-btn`, `err`, `key`, `reconnecting`
- Data attributes: none
- DOM event names: input, keydown
- Named JS functions: `doLogin`, `shake`

## Proposed additive desktop bridge (implementation pending at audit time)

QWebChannel object `edithBridge`; whitelisted `request(action, payload)` and
`ready()` slots. Python emits `event(name, json_payload)`; JS receives through
`window.edith.receive(name,payload)`. Additive events: `theme.changed`,
`platform.info`, `metrics.snapshot`, `permission.request`, `permission.closed`,
`audit.entry`, `status.changed`, `audio.level`, `tasks.changed`, `content.changed`,
`file.changed`, `config.changed`, `connection.test`, `camera.frame`, `remote.ready`,
`command.draft`, `error`. Existing Qt signals/callbacks map into these events;
remote protocol is not renamed. UI requests cannot assert approval by setting a
boolean: backend owns a pending request ID, exact action, expiry and one-use result.

## Complete committed file tree and purpose

| File | Purpose |
| --- | --- |
| `.github/workflows/platform-smoke.yml` | Windows/macOS/Linux core smoke workflow; not full hardware verification. |
| `.github/workflows/quality-checks.yml` | Ubuntu compilation, Qt/unit and dashboard JavaScript checks. |
| `.gitignore` | Generated state, credentials, models, caches and environment exclusions. |
| `LICENSE` | Repository license terms. |
| `TESTING.md` | Existing phased regression and target-device/manual validation instructions. |
| `actions/background_monitor.py` | Persist and periodically check user-selected topics. |
| `actions/browser_control.py` | Browser discovery/native launch plus persistent Playwright sessions. |
| `actions/code_helper.py` | Generate/edit/explain/run code and screenshot-assisted debugging. |
| `actions/computer_control.py` | Mouse/keyboard/clipboard/screenshot and verified window focus. |
| `actions/computer_settings.py` | Volume/brightness/window/network/theme and OS/power settings. |
| `actions/desktop.py` | Desktop listing/organizing/wallpaper and generated Python automation. |
| `actions/dev_agent.py` | Generate projects, install dependencies, run and iteratively repair code. |
| `actions/file_controller.py` | Home-scoped file/folder read/create/move/copy/delete operations. |
| `actions/file_processor.py` | Transform/summarize image/document/data/code/media/archive files. |
| `actions/flight_finder.py` | Browser flight search, model interpretation and desktop report. |
| `actions/game_updater.py` | Steam/Epic discovery, updates/install and scheduled tasks/power actions. |
| `actions/open_app.py` | OS launcher inventory, app launch and foreground verification. |
| `actions/proactive.py` | Generate optional context-aware proactive prompts. |
| `actions/pushup_counter.py` | Optional camera exercise-counting plugin with local session data. |
| `actions/reminder.py` | OS notification scripts and platform scheduler integration. |
| `actions/screen_processor.py` | MSS/camera capture and legacy vision/audio session helper. |
| `actions/send_message.py` | Foreground GUI automation for requested outbound messages. |
| `actions/system_monitor.py` | CPU/RAM/GPU/temperature sampling and threshold alerts. |
| `actions/upload_video.py` | Hardcoded coordinate-based browser upload workflow; fragile and optional. |
| `actions/weather_report.py` | Open weather URL for a requested location. |
| `actions/web_search.py` | Gemini-grounded/DDG search/news/research with quota fallback. |
| `actions/youtube_video.py` | Channel/video search, transcript summarization and URL opening. |
| `assets/README.md` | Reference video origin and remux provenance. |
| `assets/hud_reference.mp4` | Bundled 10.01-second silent H264 reference animation; inspected as media, not text. |
| `config/__init__.py` | Python package marker. |
| `core/__init__.py` | Python package marker. |
| `core/action_activity.py` | Redacted activity descriptions and outcome classifier. |
| `core/action_guard.py` | Existing selective local-confirmation rules; not a full permission-tier engine. |
| `core/agent_reliability.py` | Deduplication, action evidence and SQLite task metadata journal. |
| `core/app_icon.py` | Local multi-resolution icon generation. |
| `core/audio_meter.py` | Safe normalized mono PCM16 intensity calculation. |
| `core/branding.py` | Migrate legacy uploads/projects/profile directory names without overwriting. |
| `core/dark_theme.py` | Native dark Qt palette/context-menu styling. |
| `core/energy_ring.py` | Cached painter-based energy-ring alternative. |
| `core/hardware_check.py` | Read-only audio/desktop capability diagnostics. |
| `core/icons.py` | Local SVG icon definitions and Qt icon generation. |
| `core/installer.py` | Optional local/STT/TTS dependency installation. |
| `core/llm_client.py` | Ollama and OpenAI-compatible internal text-agent adapters. |
| `core/narration_audio.py` | Lossless speech FIFO and dedicated blocking device writer. |
| `core/plugin_loader.py` | Validate/discover/toggle/run local Python plugins. |
| `core/product_identity.py` | Code-owned EDITH / Neuron Intelligence / creator identity. |
| `core/prompt.txt` | Main Live agent instructions. |
| `core/realtime_audio.py` | Drop-oldest microphone transport FIFO helper. |
| `core/startup_check.py` | Early dependency preflight and installation help. |
| `core/stt.py` | Optional Whisper/Vosk input adapters. |
| `core/task_scheduler.py` | Bounded dependency/priority scheduler and queued-only cancellation. |
| `core/task_view.py` | Metadata-only compact task summaries. |
| `core/tts.py` | Optional Edge/Kokoro/ElevenLabs speech adapters. |
| `core/ui_design.py` | Unused/optional Qt design primitives from preceding redesign. |
| `core/video_visual.py` | Qt Multimedia looping local video and painter edge blend. |
| `core/window_controls.py` | Screen-aware native title-bar-safe window positioning. |
| `dashboard/__init__.py` | Python package marker. |
| `dashboard/server.py` | Authenticated FastAPI remote UI, pairing, command/file and phone-audio transports. |
| `dashboard/static/app.html` | Remote dashboard DOM, command/files/voice capture and reconnect protocol. |
| `dashboard/static/crypto-js.min.js` | Vendored CryptoJS browser encryption dependency. |
| `dashboard/static/login.html` | Remote pairing/login form and session recovery. |
| `docs/NARRATION_RELIABILITY.md` | Narration defects, dedicated audio writer, tests and device acceptance steps. |
| `docs/UPGRADE_STATUS.md` | Published UI changes and outstanding multi-stage agent work. |
| `main.py` | Voice/Live entry point, tool declarations/dispatch, task orchestration, remote relay and audio lifecycle. |
| `memory/__init__.py` | Python package marker. |
| `memory/config_manager.py` | JSON API/profile/voice/plugin preferences and first-run persistence. |
| `memory/memory_manager.py` | Bounded JSON long-term facts and previous-session summaries. |
| `plugins/__init__.py` | Python package marker. |
| `plugins/_template.py` | Optional plugin declaration/run interface example. |
| `readme.md` | Installation, architecture, features and known validation limits. |
| `requirements.txt` | Python runtime dependencies and Windows-specific environment markers. |
| `setup.py` | Explicit dependency/Playwright installation script; not a packaging configuration. |
| `tests/check_inline_js.py` | JavaScript/HTML validation harness. |
| `tests/check_phase5_js.js` | JavaScript/HTML validation harness. |
| `tests/check_workspace_js.js` | JavaScript/HTML validation harness. |
| `tests/test_action_activity.py` | Regression tests: action activity. |
| `tests/test_action_guard.py` | Regression tests: action guard. |
| `tests/test_audio_hardware_fallback.py` | Regression tests: audio hardware fallback. |
| `tests/test_computer_control_target.py` | Regression tests: computer control target. |
| `tests/test_energy_ring.py` | Regression tests: energy ring. |
| `tests/test_enterprise_ui.py` | Regression tests: enterprise ui. |
| `tests/test_fast_response.py` | Regression tests: fast response. |
| `tests/test_file_controller.py` | Regression tests: file controller. |
| `tests/test_icons.py` | Regression tests: icons. |
| `tests/test_installer_failures.py` | Regression tests: installer failures. |
| `tests/test_narration_audio.py` | Regression tests: narration audio. |
| `tests/test_phase1_setup.py` | Regression tests: phase1 setup. |
| `tests/test_phase4_qt.py` | Regression tests: phase4 qt. |
| `tests/test_phase4_ui.py` | Regression tests: phase4 ui. |
| `tests/test_phase5_remote.py` | Regression tests: phase5 remote. |
| `tests/test_phase6_reliability.py` | Regression tests: phase6 reliability. |
| `tests/test_product_contract.py` | Regression tests: product contract. |
| `tests/test_product_identity.py` | Regression tests: product identity. |
| `tests/test_response_status.py` | Regression tests: response status. |
| `tests/test_task_scheduler.py` | Regression tests: task scheduler. |
| `tests/test_video_visual.py` | Regression tests: video visual. |
| `tests/test_voice_input_ui.py` | Regression tests: voice input ui. |
| `tests/test_youtube_channels.py` | Regression tests: youtube channels. |
| `tools/phase2_benchmark.py` | Synthetic scheduler concurrency/performance benchmark. |
| `ui.py` | Native PyQt desktop, overlays, telemetry, keyboard controls and EdithUI compatibility facade. |

## Hardware / OS / shell / file / process call-site inventory

This conservative static inventory includes reads, mutations, generated code,
network/browser/device calls and test fakes. Each expression is a candidate call
site, **not proof of runtime success**. Repeated wrappers and tests are retained so
no inspected file is silently omitted. Platform classification: Windows API/registry
and Win32 modules = Windows; osascript/defaults/launchctl/pmset/open = macOS;
gsettings/wmctrl/xdotool/systemctl/nmcli/brightnessctl/sysfs/XDG = Linux; generic
Python/psutil/Qt/Path = cross-platform subject to OS permissions/dependencies. A
mixed function uses its surrounding platform guards; unknown is explicitly marked
conditional rather than certified cross-platform.

### `actions/background_monitor.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 50 | `MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 51 | `MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |

### `actions/browser_control.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 23 | `platform.system()` | cross-platform / OS-conditional |
| 63 | `Path.home()` | cross-platform / OS-conditional |
| 71 | `Path(local)` | cross-platform / OS-conditional |
| 72 | `Path(local)` | cross-platform / OS-conditional |
| 73 | `Path(local)` | cross-platform / OS-conditional |
| 74 | `Path(local)` | cross-platform / OS-conditional |
| 75 | `Path(roam)` | cross-platform / OS-conditional |
| 76 | `Path(local)` | cross-platform / OS-conditional |
| 77 | `Path(roam)` | cross-platform / OS-conditional |
| 78 | `Path(local)` | cross-platform / OS-conditional |
| 107 | `p.exists()` | cross-platform / OS-conditional |
| 112 | `fallback.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 117 | `Path.home()` | cross-platform / OS-conditional |
| 120 | `Path(os.environ.get('APPDATA', ''))` | cross-platform / OS-conditional |
| 127 | `ini.exists()` | cross-platform / OS-conditional |
| 133 | `ini.read_text(encoding='utf-8', errors='ignore').splitlines()` | cross-platform / OS-conditional |
| 133 | `ini.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 150 | `Path(default_path).exists()` | cross-platform / OS-conditional |
| 150 | `Path(default_path)` | cross-platform / OS-conditional |
| 161 | `Path(local)` | cross-platform / OS-conditional |
| 162 | `Path(local)` | cross-platform / OS-conditional |
| 163 | `Path(prog)` | cross-platform / OS-conditional |
| 164 | `Path(prog86)` | cross-platform / OS-conditional |
| 167 | `p.exists()` | cross-platform / OS-conditional |
| 182 | `winreg.OpenKey(hive, key_path)` | Windows |
| 183 | `winreg.QueryValue(k, None)` | Windows |
| 184 | `winreg.CloseKey(k)` | Windows |
| 186 | `Path(exe).exists()` | cross-platform / OS-conditional |
| 186 | `Path(exe)` | cross-platform / OS-conditional |
| 194 | `shutil.which('opera')` | cross-platform / OS-conditional |
| 206 | `winreg.OpenKey(hive, key_path)` | Windows |
| 207 | `winreg.QueryValue(k, None)` | Windows |
| 208 | `winreg.CloseKey(k)` | Windows |
| 210 | `Path(exe).exists()` | cross-platform / OS-conditional |
| 210 | `Path(exe)` | cross-platform / OS-conditional |
| 284 | `shutil.which(b)` | cross-platform / OS-conditional |
| 299 | `Path('/Applications')` | macOS |
| 300 | `app_dir.exists()` | cross-platform / OS-conditional |
| 301 | `app_dir.iterdir()` | cross-platform / OS-conditional |
| 316 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\Shell\\Associations\\UrlAssociations\\http\\UserChoice')` | Windows |
| 321 | `winreg.QueryValueEx(k, 'ProgId')[0].lower()` | Windows |
| 321 | `winreg.QueryValueEx(k, 'ProgId')` | Windows |
| 322 | `winreg.CloseKey(k)` | Windows |
| 327 | `subprocess.run(['defaults', 'read', 'com.apple.LaunchServices/com.apple.launchservices.secure', 'LSHandlers'], capture_output=True, text=True, timeout=5).stdout.lower()` | macOS |
| 327 | `subprocess.run(['defaults', 'read', 'com.apple.LaunchServices/com.apple.launchservices.secure', 'LSHandlers'], capture_output=True, text=True, timeout=5)` | macOS |
| 337 | `subprocess.run(['xdg-settings', 'get', 'default-web-browser'], capture_output=True, text=True, timeout=5).stdout.lower()` | Linux |
| 337 | `subprocess.run(['xdg-settings', 'get', 'default-web-browser'], capture_output=True, text=True, timeout=5)` | Linux |
| 398 | `subprocess.run(cmd, check=True, timeout=10)` | cross-platform / OS-conditional |
| 412 | `subprocess.Popen([exe, url] if url else [exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 427 | `os.startfile(url)` | cross-platform / OS-conditional |
| 429 | `subprocess.run(['open', url], check=True, timeout=10)` | cross-platform / OS-conditional |
| 431 | `subprocess.Popen(['xdg-open', url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | Linux |
| 438 | `webbrowser.open(url)` | cross-platform / OS-conditional |
| 492 | `asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)` | cross-platform / OS-conditional |
| 549 | `engine_obj.launch_persistent_context(profile, **kwargs)` | cross-platform / OS-conditional |
| 553 | `Path(edith).mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 553 | `Path(edith)` | cross-platform / OS-conditional |
| 554 | `engine_obj.launch_persistent_context(edith, **kwargs)` | cross-platform / OS-conditional |
| 562 | `Path(safari_profile).mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 562 | `Path(safari_profile)` | cross-platform / OS-conditional |
| 570 | `engine_obj.launch_persistent_context(safari_profile, **kwargs)` | cross-platform / OS-conditional |
| 604 | `engine_obj.launch_persistent_context(profile, **kwargs)` | cross-platform / OS-conditional |
| 616 | `Path(edith_profile).mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 616 | `Path(edith_profile)` | cross-platform / OS-conditional |
| 620 | `engine_obj.launch_persistent_context(edith_profile, **kwargs)` | cross-platform / OS-conditional |
| 676 | `page.get_by_text(text, exact=False).first.click(timeout=8000)` | cross-platform / OS-conditional |
| 679 | `page.click(selector, timeout=8000)` | cross-platform / OS-conditional |
| 711 | `page.keyboard.press(key)` | cross-platform / OS-conditional |
| 747 | `loc.first.click(timeout=5000)` | cross-platform / OS-conditional |
| 752 | `page.get_by_text(description, exact=False).first.click(timeout=5000)` | cross-platform / OS-conditional |
| 753 | `page.get_by_placeholder(description, exact=False).first.click(timeout=5000)` | cross-platform / OS-conditional |
| 754 | `page.locator(f'[alt*="{description}" i],[title*="{description}" i],[aria-label*="{description}" i]').first.click(timeout=5000)` | cross-platform / OS-conditional |
| 809 | `Path.home()` | cross-platform / OS-conditional |
| 810 | `page.screenshot(path=save_path, full_page=False)` | cross-platform / OS-conditional |
| 971 | `sess.run(sess.search(params.get('query', ''), params.get('engine', 'google')))` | cross-platform / OS-conditional |
| 974 | `sess.run(sess.new_tab(params.get('url', '')))` | cross-platform / OS-conditional |
| 976 | `sess.run(sess.go_to(params.get('url', '')))` | cross-platform / OS-conditional |
| 1012 | `sess.run(sess.go_to(last))` | cross-platform / OS-conditional |
| 1017 | `sess.run(sess.click(params.get('selector'), params.get('text')))` | cross-platform / OS-conditional |
| 1017 | `sess.click(params.get('selector'), params.get('text'))` | cross-platform / OS-conditional |
| 1019 | `sess.run(sess.type_text(params.get('selector'), params.get('text', ''), params.get('clear_first', True)))` | cross-platform / OS-conditional |
| 1022 | `sess.run(sess.scroll(params.get('direction', 'down'), int(params.get('amount', 500))))` | cross-platform / OS-conditional |
| 1024 | `sess.run(sess.fill_form(params.get('fields', {})))` | cross-platform / OS-conditional |
| 1026 | `sess.run(sess.smart_click(params.get('description', '')))` | cross-platform / OS-conditional |
| 1028 | `sess.run(sess.smart_type(params.get('description', ''), params.get('text', '')))` | cross-platform / OS-conditional |
| 1030 | `sess.run(sess.get_text())` | cross-platform / OS-conditional |
| 1032 | `sess.run(sess.get_url())` | cross-platform / OS-conditional |
| 1034 | `sess.run(sess.press(params.get('key', 'Enter')))` | cross-platform / OS-conditional |
| 1034 | `sess.press(params.get('key', 'Enter'))` | cross-platform / OS-conditional |
| 1036 | `sess.run(sess.close_tab())` | cross-platform / OS-conditional |
| 1038 | `sess.run(sess.screenshot(params.get('path')))` | cross-platform / OS-conditional |
| 1038 | `sess.screenshot(params.get('path'))` | cross-platform / OS-conditional |
| 1040 | `sess.run(sess.back())` | cross-platform / OS-conditional |
| 1042 | `sess.run(sess.forward())` | cross-platform / OS-conditional |
| 1044 | `sess.run(sess.reload())` | cross-platform / OS-conditional |

### `actions/code_helper.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 11 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 12 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 12 | `Path(__file__)` | cross-platform / OS-conditional |
| 16 | `Path.home()` | cross-platform / OS-conditional |
| 22 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 55 | `Path(output_path)` | cross-platform / OS-conditional |
| 64 | `Path(file_path)` | cross-platform / OS-conditional |
| 65 | `p.exists()` | cross-platform / OS-conditional |
| 68 | `p.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 75 | `path.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 76 | `path.write_text(content, encoding='utf-8')` | cross-platform / OS-conditional |
| 98 | `Path.home()` | cross-platform / OS-conditional |
| 99 | `pyautogui.screenshot()` | cross-platform / OS-conditional |
| 100 | `screenshot.save(str(screenshot_path))` | cross-platform / OS-conditional |
| 110 | `base64.b64encode(path.read_bytes()).decode('utf-8')` | cross-platform / OS-conditional |
| 110 | `path.read_bytes()` | cross-platform / OS-conditional |
| 124 | `Path(file_path).exists()` | cross-platform / OS-conditional |
| 124 | `Path(file_path)` | cross-platform / OS-conditional |
| 221 | `subprocess.run(interp + [str(path)] + (args or []), capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, cwd=str(path.parent))` | cross-platform / OS-conditional |
| 339 | `Path(file_path)` | cross-platform / OS-conditional |
| 375 | `Path(file_path)` | cross-platform / OS-conditional |
| 376 | `p.exists()` | cross-platform / OS-conditional |
| 420 | `Path(file_path)` | cross-platform / OS-conditional |
| 464 | `screenshot_path.read_bytes()` | cross-platform / OS-conditional |
| 499 | `screenshot_path.unlink()` | cross-platform / OS-conditional |
| 508 | `Path(file_path)` | cross-platform / OS-conditional |
| 518 | `screenshot_path.unlink()` | cross-platform / OS-conditional |

### `actions/computer_control.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 11 | `platform.system()` | cross-platform / OS-conditional |
| 35 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 36 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 36 | `Path(__file__)` | cross-platform / OS-conditional |
| 45 | `_CONFIG_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 51 | `platform.system()` | cross-platform / OS-conditional |
| 62 | `Path.home()` | cross-platform / OS-conditional |
| 66 | `Path.home()` | cross-platform / OS-conditional |
| 70 | `Path(requested).expanduser().resolve()` | cross-platform / OS-conditional |
| 70 | `Path(requested).expanduser()` | cross-platform / OS-conditional |
| 70 | `Path(requested)` | cross-platform / OS-conditional |
| 72 | `root.resolve()` | cross-platform / OS-conditional |
| 73 | `p.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 150 | `_MEMORY_PATH.exists()` | cross-platform / OS-conditional |
| 151 | `_MEMORY_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 161 | `pyautogui.typewrite(text, interval=interval)` | cross-platform / OS-conditional |
| 172 | `pyperclip.copy(text)` | cross-platform / OS-conditional |
| 175 | `pyautogui.hotkey(paste_key, 'v')` | cross-platform / OS-conditional |
| 178 | `pyautogui.typewrite(text, interval=0.04)` | cross-platform / OS-conditional |
| 185 | `pyautogui.click(x, y, button=button, clicks=clicks)` | cross-platform / OS-conditional |
| 187 | `pyautogui.click(button=button, clicks=clicks)` | cross-platform / OS-conditional |
| 193 | `pyautogui.hotkey(*keys)` | cross-platform / OS-conditional |
| 199 | `pyautogui.press(key)` | cross-platform / OS-conditional |
| 207 | `pyautogui.scroll(clicks)` | cross-platform / OS-conditional |
| 207 | `pyautogui.hscroll(clicks)` | cross-platform / OS-conditional |
| 213 | `pyautogui.moveTo(x, y, duration=duration)` | cross-platform / OS-conditional |
| 219 | `pyautogui.moveTo(x1, y1, duration=0.2)` | cross-platform / OS-conditional |
| 220 | `pyautogui.dragTo(x2, y2, duration=duration, button='left')` | cross-platform / OS-conditional |
| 226 | `pyperclip.paste()` | cross-platform / OS-conditional |
| 234 | `pyperclip.copy(text)` | cross-platform / OS-conditional |
| 238 | `pyautogui.hotkey(paste_key, 'v')` | cross-platform / OS-conditional |
| 246 | `pyautogui.screenshot()` | cross-platform / OS-conditional |
| 254 | `pyautogui.hotkey(select_key, 'a')` | cross-platform / OS-conditional |
| 256 | `pyautogui.press('delete')` | cross-platform / OS-conditional |
| 277 | `ctypes.create_unicode_buffer(length + 1)` | cross-platform / OS-conditional |
| 281 | `ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)` | cross-platform / OS-conditional |
| 323 | `subprocess.run(['osascript', '-e', script, target], capture_output=True, text=True, timeout=5)` | macOS |
| 337 | `shutil.which('wmctrl')` | Linux |
| 339 | `subprocess.run(['wmctrl', '-a', target], capture_output=True, text=True, timeout=5)` | Linux |
| 345 | `shutil.which('xdotool')` | Linux |
| 346 | `subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=3).stdout.strip()` | Linux |
| 346 | `subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=3)` | Linux |
| 356 | `shutil.which('xdotool')` | Linux |
| 358 | `subprocess.run(['xdotool', 'search', '--name', target], capture_output=True, text=True, timeout=5)` | Linux |
| 364 | `subprocess.run(['xdotool', 'windowactivate', '--sync', window_ids[0]], capture_output=True, text=True, timeout=5)` | Linux |
| 370 | `subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=3).stdout.strip()` | Linux |
| 370 | `subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=3)` | Linux |
| 393 | `pyautogui.size()` | cross-platform / OS-conditional |
| 394 | `pyautogui.screenshot()` | cross-platform / OS-conditional |

### `actions/computer_settings.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 24 | `platform.system()` | cross-platform / OS-conditional |
| 34 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 35 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 35 | `Path(__file__)` | cross-platform / OS-conditional |
| 39 | `open(path, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 44 | `subprocess.run(['networksetup', '-listallhardwareports'], capture_output=True, text=True, timeout=5)` | cross-platform / OS-conditional |
| 60 | `pyautogui.press('volumeup')` | cross-platform / OS-conditional |
| 62 | `subprocess.run(['osascript', '-e', 'set volume output volume (output volume of (get volume settings) + 10)'], capture_output=True)` | macOS |
| 66 | `subprocess.run(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '+10%'], capture_output=True)` | Linux |
| 71 | `pyautogui.press('volumedown')` | cross-platform / OS-conditional |
| 73 | `subprocess.run(['osascript', '-e', 'set volume output volume (output volume of (get volume settings) - 10)'], capture_output=True)` | macOS |
| 77 | `subprocess.run(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', '-10%'], capture_output=True)` | Linux |
| 82 | `pyautogui.press('volumemute')` | cross-platform / OS-conditional |
| 84 | `subprocess.run(['osascript', '-e', 'set volume with output muted'], capture_output=True)` | macOS |
| 87 | `subprocess.run(['pactl', 'set-sink-mute', '@DEFAULT_SINK@', 'toggle'], capture_output=True)` | Linux |
| 106 | `pyautogui.press('volumemute')` | cross-platform / OS-conditional |
| 107 | `pyautogui.press('volumemute')` | cross-platform / OS-conditional |
| 109 | `subprocess.run(['osascript', '-e', f'set volume output volume {value}'], capture_output=True)` | macOS |
| 113 | `subprocess.run(['pactl', 'set-sink-volume', '@DEFAULT_SINK@', f'{value}%'], capture_output=True)` | Linux |
| 119 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 144'], capture_output=True)` | macOS |
| 123 | `subprocess.run(['which', 'brightnessctl'], capture_output=True)` | Linux |
| 125 | `subprocess.run(['brightnessctl', 'set', '+10%'], capture_output=True)` | Linux |
| 127 | `subprocess.run('xrandr --output $(xrandr \| grep " connected" \| head -1 \| cut -d " " -f1) --brightness $(python3 -c "import subprocess; b=float(subprocess.check_output(["xrandr","--verbose"]).decode().split("Brightness:")[1].split()[0]); print(min(1.0,b+0.1))")', shell=True, capture_output=True)` | Linux |
| 136 | `subprocess.run(['powershell', '-Command', '(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, [math]::Min(100, (Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness + 10))'], capture_output=True, timeout=5, **_WIN_HIDE)` | Windows |
| 148 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to key code 145'], capture_output=True)` | macOS |
| 152 | `subprocess.run(['which', 'brightnessctl'], capture_output=True)` | Linux |
| 154 | `subprocess.run(['brightnessctl', 'set', '10%-'], capture_output=True)` | Linux |
| 156 | `subprocess.run('xrandr --output $(xrandr \| grep " connected" \| head -1 \| cut -d " " -f1) --brightness $(python3 -c "import subprocess; b=float(subprocess.check_output(["xrandr","--verbose"]).decode().split("Brightness:")[1].split()[0]); print(max(0.1,b-0.1))")', shell=True, capture_output=True)` | Linux |
| 165 | `subprocess.run(['powershell', '-Command', '(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1, [math]::Max(0, (Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightness).CurrentBrightness - 10))'], capture_output=True, timeout=5, **_WIN_HIDE)` | Windows |
| 176 | `pyautogui.hotkey('command', 'q')` | cross-platform / OS-conditional |
| 177 | `pyautogui.hotkey('alt', 'f4')` | cross-platform / OS-conditional |
| 180 | `pyautogui.hotkey('command', 'w')` | cross-platform / OS-conditional |
| 181 | `pyautogui.hotkey('ctrl', 'w')` | cross-platform / OS-conditional |
| 184 | `pyautogui.hotkey('ctrl', 'command', 'f')` | cross-platform / OS-conditional |
| 185 | `pyautogui.press('f11')` | cross-platform / OS-conditional |
| 188 | `pyautogui.hotkey('command', 'm')` | cross-platform / OS-conditional |
| 189 | `pyautogui.hotkey('win', 'down')` | cross-platform / OS-conditional |
| 193 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to keystroke "f" using {control down, command down}'], capture_output=True)` | macOS |
| 198 | `pyautogui.hotkey('win', 'up')` | cross-platform / OS-conditional |
| 201 | `subprocess.run(['wmctrl', '-r', ':ACTIVE:', '-b', 'add,maximized_vert,maximized_horz'], capture_output=True)` | Linux |
| 204 | `pyautogui.hotkey('super', 'up')` | cross-platform / OS-conditional |
| 208 | `pyautogui.hotkey('win', 'left')` | cross-platform / OS-conditional |
| 212 | `subprocess.run(['open', '-a', 'Rectangle'], capture_output=True, timeout=1)` | cross-platform / OS-conditional |
| 215 | `pyautogui.hotkey('ctrl', 'option', 'left')` | cross-platform / OS-conditional |
| 218 | `subprocess.run(['wmctrl', '-r', ':ACTIVE:', '-e', '0,0,0,960,1080'], capture_output=True)` | Linux |
| 225 | `pyautogui.hotkey('win', 'right')` | cross-platform / OS-conditional |
| 228 | `subprocess.run(['open', '-a', 'Rectangle'], capture_output=True, timeout=1)` | cross-platform / OS-conditional |
| 231 | `pyautogui.hotkey('ctrl', 'option', 'right')` | cross-platform / OS-conditional |
| 234 | `subprocess.run(['wmctrl', '-r', ':ACTIVE:', '-e', '0,960,0,960,1080'], capture_output=True)` | Linux |
| 240 | `pyautogui.hotkey('command', 'tab')` | cross-platform / OS-conditional |
| 241 | `pyautogui.hotkey('alt', 'tab')` | cross-platform / OS-conditional |
| 244 | `pyautogui.hotkey('fn', 'f11')` | cross-platform / OS-conditional |
| 245 | `pyautogui.hotkey('win', 'd')` | cross-platform / OS-conditional |
| 246 | `pyautogui.hotkey('super', 'd')` | cross-platform / OS-conditional |
| 250 | `pyautogui.hotkey('ctrl', 'shift', 'esc')` | cross-platform / OS-conditional |
| 252 | `subprocess.Popen(['open', '-a', 'Activity Monitor'])` | cross-platform / OS-conditional |
| 255 | `subprocess.run(['which', cmd[0]], capture_output=True)` | cross-platform / OS-conditional |
| 256 | `subprocess.Popen(cmd)` | cross-platform / OS-conditional |
| 261 | `pyautogui.hotkey('command', 'l')` | cross-platform / OS-conditional |
| 262 | `pyautogui.hotkey('ctrl', 'l')` | cross-platform / OS-conditional |
| 264 | `pyautogui.press('space')` | cross-platform / OS-conditional |
| 267 | `pyautogui.hotkey('command', 'r')` | cross-platform / OS-conditional |
| 268 | `pyautogui.press('f5')` | cross-platform / OS-conditional |
| 271 | `pyautogui.hotkey('command', 'w')` | cross-platform / OS-conditional |
| 272 | `pyautogui.hotkey('ctrl', 'w')` | cross-platform / OS-conditional |
| 275 | `pyautogui.hotkey('command', 't')` | cross-platform / OS-conditional |
| 276 | `pyautogui.hotkey('ctrl', 't')` | cross-platform / OS-conditional |
| 279 | `pyautogui.hotkey('command', 'shift', 'bracketright')` | cross-platform / OS-conditional |
| 280 | `pyautogui.hotkey('ctrl', 'tab')` | cross-platform / OS-conditional |
| 283 | `pyautogui.hotkey('command', 'shift', 'bracketleft')` | cross-platform / OS-conditional |
| 284 | `pyautogui.hotkey('ctrl', 'shift', 'tab')` | cross-platform / OS-conditional |
| 287 | `pyautogui.hotkey('command', 'left')` | cross-platform / OS-conditional |
| 288 | `pyautogui.hotkey('alt', 'left')` | cross-platform / OS-conditional |
| 291 | `pyautogui.hotkey('command', 'right')` | cross-platform / OS-conditional |
| 292 | `pyautogui.hotkey('alt', 'right')` | cross-platform / OS-conditional |
| 295 | `pyautogui.hotkey('command', 'equal')` | cross-platform / OS-conditional |
| 296 | `pyautogui.hotkey('ctrl', 'equal')` | cross-platform / OS-conditional |
| 299 | `pyautogui.hotkey('command', 'minus')` | cross-platform / OS-conditional |
| 300 | `pyautogui.hotkey('ctrl', 'minus')` | cross-platform / OS-conditional |
| 303 | `pyautogui.hotkey('command', '0')` | cross-platform / OS-conditional |
| 304 | `pyautogui.hotkey('ctrl', '0')` | cross-platform / OS-conditional |
| 307 | `pyautogui.hotkey('command', 'f')` | cross-platform / OS-conditional |
| 308 | `pyautogui.hotkey('ctrl', 'f')` | cross-platform / OS-conditional |
| 316 | `pyautogui.scroll(amount)` | cross-platform / OS-conditional |
| 317 | `pyautogui.scroll(-amount)` | cross-platform / OS-conditional |
| 320 | `pyautogui.hotkey('command', 'up')` | cross-platform / OS-conditional |
| 321 | `pyautogui.hotkey('ctrl', 'home')` | cross-platform / OS-conditional |
| 324 | `pyautogui.hotkey('command', 'down')` | cross-platform / OS-conditional |
| 325 | `pyautogui.hotkey('ctrl', 'end')` | cross-platform / OS-conditional |
| 327 | `pyautogui.press('pageup')` | cross-platform / OS-conditional |
| 328 | `pyautogui.press('pagedown')` | cross-platform / OS-conditional |
| 332 | `pyautogui.hotkey('command', 'c')` | cross-platform / OS-conditional |
| 333 | `pyautogui.hotkey('ctrl', 'c')` | cross-platform / OS-conditional |
| 336 | `pyautogui.hotkey('command', 'v')` | cross-platform / OS-conditional |
| 337 | `pyautogui.hotkey('ctrl', 'v')` | cross-platform / OS-conditional |
| 340 | `pyautogui.hotkey('command', 'x')` | cross-platform / OS-conditional |
| 341 | `pyautogui.hotkey('ctrl', 'x')` | cross-platform / OS-conditional |
| 344 | `pyautogui.hotkey('command', 'z')` | cross-platform / OS-conditional |
| 345 | `pyautogui.hotkey('ctrl', 'z')` | cross-platform / OS-conditional |
| 348 | `pyautogui.hotkey('command', 'shift', 'z')` | cross-platform / OS-conditional |
| 349 | `pyautogui.hotkey('ctrl', 'y')` | cross-platform / OS-conditional |
| 352 | `pyautogui.hotkey('command', 'a')` | cross-platform / OS-conditional |
| 353 | `pyautogui.hotkey('ctrl', 'a')` | cross-platform / OS-conditional |
| 356 | `pyautogui.hotkey('command', 's')` | cross-platform / OS-conditional |
| 357 | `pyautogui.hotkey('ctrl', 's')` | cross-platform / OS-conditional |
| 359 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 360 | `pyautogui.press('escape')` | cross-platform / OS-conditional |
| 361 | `pyautogui.press(key)` | cross-platform / OS-conditional |
| 367 | `pyperclip.copy(str(text))` | cross-platform / OS-conditional |
| 369 | `paste()` | cross-platform / OS-conditional |
| 371 | `pyautogui.write(str(text), interval=0.03)` | cross-platform / OS-conditional |
| 374 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 378 | `pyautogui.hotkey('win', 'shift', 's')` | cross-platform / OS-conditional |
| 380 | `pyautogui.hotkey('command', 'shift', '3')` | cross-platform / OS-conditional |
| 383 | `subprocess.run(['which', cmd[0]], capture_output=True)` | cross-platform / OS-conditional |
| 384 | `subprocess.Popen(cmd)` | cross-platform / OS-conditional |
| 386 | `pyautogui.hotkey('ctrl', 'print_screen')` | cross-platform / OS-conditional |
| 390 | `pyautogui.hotkey('win', 'l')` | cross-platform / OS-conditional |
| 392 | `subprocess.run(['pmset', 'displaysleepnow'], capture_output=True)` | macOS |
| 399 | `subprocess.run(['which', cmd[0]], capture_output=True)` | cross-platform / OS-conditional |
| 400 | `subprocess.run(cmd, capture_output=True)` | cross-platform / OS-conditional |
| 405 | `pyautogui.hotkey('win', 'i')` | cross-platform / OS-conditional |
| 407 | `subprocess.Popen(['open', '-a', 'System Preferences'])` | cross-platform / OS-conditional |
| 410 | `subprocess.run(['which', cmd[0]], capture_output=True)` | cross-platform / OS-conditional |
| 411 | `subprocess.Popen(cmd)` | cross-platform / OS-conditional |
| 416 | `pyautogui.hotkey('win', 'e')` | cross-platform / OS-conditional |
| 418 | `subprocess.Popen(['open', str(Path.home())])` | cross-platform / OS-conditional |
| 418 | `Path.home()` | cross-platform / OS-conditional |
| 421 | `subprocess.run(['which', cmd[0]], capture_output=True)` | cross-platform / OS-conditional |
| 422 | `subprocess.Popen(cmd)` | cross-platform / OS-conditional |
| 424 | `subprocess.Popen(['xdg-open', str(Path.home())])` | Linux |
| 424 | `Path.home()` | cross-platform / OS-conditional |
| 430 | `ctypes.windll.user32.SendMessageW(65535, 274, 61808, 2)` | Windows |
| 434 | `subprocess.run(['pmset', 'displaysleepnow'], capture_output=True)` | macOS |
| 436 | `subprocess.run(['xset', 'dpms', 'force', 'off'], capture_output=True)` | Linux |
| 440 | `pyautogui.hotkey('win', 'r')` | cross-platform / OS-conditional |
| 444 | `subprocess.run(['osascript', '-e', 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'], capture_output=True)` | macOS |
| 452 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)` | Windows |
| 453 | `winreg.QueryValueEx(key, 'AppsUseLightTheme')` | Windows |
| 454 | `winreg.SetValueEx(key, 'AppsUseLightTheme', 0, winreg.REG_DWORD, 1 - current)` | Windows |
| 455 | `winreg.SetValueEx(key, 'SystemUsesLightTheme', 0, winreg.REG_DWORD, 1 - current)` | Windows |
| 456 | `winreg.CloseKey(key)` | Windows |
| 461 | `subprocess.run(['gsettings', 'get', 'org.gnome.desktop.interface', 'color-scheme'], capture_output=True, text=True)` | Linux |
| 467 | `subprocess.run(['gsettings', 'set', 'org.gnome.desktop.interface', 'color-scheme', new_scheme], capture_output=True)` | Linux |
| 477 | `subprocess.run(['networksetup', '-getairportpower', iface], capture_output=True, text=True)` | cross-platform / OS-conditional |
| 482 | `subprocess.run(['networksetup', '-setairportpower', iface, state], capture_output=True)` | cross-platform / OS-conditional |
| 486 | `subprocess.run(['powershell', '-Command', "$adapter = Get-NetAdapter \| Where-Object {$_.PhysicalMediaType -eq 'Native 802.11'};if ($adapter.Status -eq 'Up') { Disable-NetAdapter -Name $adapter.Name -Confirm:$false }else { Enable-NetAdapter -Name $adapter.Name -Confirm:$false }"], capture_output=True, timeout=10, **_WIN_HIDE)` | Windows |
| 497 | `subprocess.run(['nmcli', 'radio', 'wifi'], capture_output=True, text=True)` | Linux |
| 499 | `subprocess.run(['nmcli', 'radio', 'wifi', state], capture_output=True)` | Linux |
| 505 | `subprocess.run(['shutdown', '/r', '/t', '10'], capture_output=True, **_WIN_HIDE)` | cross-platform / OS-conditional |
| 507 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to restart'], capture_output=True)` | macOS |
| 511 | `subprocess.run(['systemctl', 'reboot'], capture_output=True)` | Linux |
| 515 | `subprocess.run(['shutdown', '/s', '/t', '10'], capture_output=True)` | cross-platform / OS-conditional |
| 517 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to shut down'], capture_output=True)` | macOS |
| 521 | `subprocess.run(['systemctl', 'poweroff'], capture_output=True)` | Linux |
| 699 | `press_key(key)` | cross-platform / OS-conditional |

### `actions/desktop.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 18 | `platform.system()` | cross-platform / OS-conditional |
| 23 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 24 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 24 | `Path(__file__)` | cross-platform / OS-conditional |
| 28 | `open(path, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 34 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 34 | `Path(xdg)` | cross-platform / OS-conditional |
| 35 | `Path(xdg)` | cross-platform / OS-conditional |
| 36 | `Path.home()` | cross-platform / OS-conditional |
| 55 | `type('shutil', (), {'copy2': shutil.copy2, 'copytree': shutil.copytree, 'disk_usage': shutil.disk_usage})()` | cross-platform / OS-conditional |
| 71 | `type('winreg', (), {'OpenKey': winreg.OpenKey, 'QueryValueEx': winreg.QueryValueEx, 'HKEY_CURRENT_USER': winreg.HKEY_CURRENT_USER})()` | Windows |
| 97 | `exec(compile(code, '<edith_desktop>', 'exec'), sandbox)` | cross-platform / OS-conditional |
| 155 | `Path(image_path).expanduser().resolve()` | cross-platform / OS-conditional |
| 155 | `Path(image_path).expanduser()` | cross-platform / OS-conditional |
| 155 | `Path(image_path)` | cross-platform / OS-conditional |
| 156 | `path.exists()` | cross-platform / OS-conditional |
| 167 | `Path(tempfile.mktemp(suffix='.bmp'))` | cross-platform / OS-conditional |
| 168 | `Image.open(path).convert('RGB').save(bmp_path, 'BMP')` | cross-platform / OS-conditional |
| 168 | `Image.open(path).convert('RGB')` | cross-platform / OS-conditional |
| 168 | `Image.open(path)` | cross-platform / OS-conditional |
| 172 | `ctypes.windll.user32.SystemParametersInfoW(20, 0, str(path), 3)` | Windows |
| 180 | `subprocess.run(['osascript', '-e', script], capture_output=True)` | macOS |
| 188 | `subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri', uri], capture_output=True)` | Linux |
| 192 | `subprocess.run(['gsettings', 'set', 'org.gnome.desktop.background', 'picture-uri-dark', uri], capture_output=True)` | Linux |
| 208 | `subprocess.run(['qdbus', 'org.kde.plasmashell', '/PlasmaShell', 'org.kde.PlasmaShell.evaluateScript', script], capture_output=True)` | Linux |
| 215 | `subprocess.run(['xfconf-query', '-c', 'xfce4-desktop', '-p', '/backdrop/screen0/monitor0/workspace0/last-image', '-s', str(path)], capture_output=True)` | Linux |
| 222 | `subprocess.run(['feh', '--bg-scale', str(path)], capture_output=True)` | Linux |
| 241 | `Path(url.split('?')[0])` | cross-platform / OS-conditional |
| 242 | `Path(tempfile.mktemp(suffix=suffix))` | cross-platform / OS-conditional |
| 246 | `tmp.unlink()` | cross-platform / OS-conditional |
| 258 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Control Panel\\Desktop')` | Windows |
| 261 | `winreg.QueryValueEx(key, 'Wallpaper')` | Windows |
| 262 | `winreg.CloseKey(key)` | Windows |
| 269 | `subprocess.run(['osascript', '-e', script], capture_output=True, text=True)` | macOS |
| 278 | `subprocess.run(['gsettings', 'get', 'org.gnome.desktop.background', 'picture-uri'], capture_output=True, text=True)` | Linux |
| 312 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 313 | `item.is_dir()` | cross-platform / OS-conditional |
| 319 | `item.stat()` | cross-platform / OS-conditional |
| 330 | `target_dir.mkdir(exist_ok=True)` | cross-platform / OS-conditional |
| 333 | `new_path.exists()` | cross-platform / OS-conditional |
| 337 | `shutil.move(str(item), str(new_path))` | cross-platform / OS-conditional |
| 353 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 356 | `item.is_dir()` | cross-platform / OS-conditional |
| 358 | `item.iterdir()` | cross-platform / OS-conditional |
| 363 | `item.stat()` | cross-platform / OS-conditional |
| 380 | `archive_dir.mkdir(exist_ok=True)` | cross-platform / OS-conditional |
| 383 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 384 | `item.is_dir()` | cross-platform / OS-conditional |
| 389 | `new_path.exists()` | cross-platform / OS-conditional |
| 390 | `shutil.move(str(item), str(new_path))` | cross-platform / OS-conditional |
| 398 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 398 | `i.is_file()` | cross-platform / OS-conditional |
| 399 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 399 | `i.is_dir()` | cross-platform / OS-conditional |
| 400 | `f.stat()` | cross-platform / OS-conditional |
| 400 | `f.exists()` | cross-platform / OS-conditional |

### `actions/dev_agent.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 12 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 13 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 13 | `Path(__file__)` | cross-platform / OS-conditional |
| 18 | `Path.home()` | cross-platform / OS-conditional |
| 24 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 57 | `Path(raw_path)` | cross-platform / OS-conditional |
| 59 | `Path(pf)` | cross-platform / OS-conditional |
| 227 | `full_path.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 228 | `full_path.write_text(code, encoding='utf-8')` | cross-platform / OS-conditional |
| 245 | `subprocess.run([sys.executable, '-m', 'pip', 'show', pkg_name], capture_output=True, text=True)` | cross-platform / OS-conditional |
| 259 | `subprocess.run([sys.executable, '-m', 'pip', 'install'] + to_install, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120, cwd=str(project_dir))` | cross-platform / OS-conditional |
| 276 | `Path.home()` | cross-platform / OS-conditional |
| 281 | `subprocess.Popen([cmd, str(project_dir)], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 301 | `subprocess.run(parts, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=timeout, cwd=str(project_dir))` | cross-platform / OS-conditional |
| 339 | `subprocess.run([sys.executable, '-m', 'pip', 'install', pkg], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, cwd=str(project_dir))` | cross-platform / OS-conditional |
| 425 | `full_path.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 426 | `full_path.write_text(fixed, encoding='utf-8')` | cross-platform / OS-conditional |
| 467 | `project_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |

### `actions/file_controller.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 13 | `platform.system()` | cross-platform / OS-conditional |
| 16 | `Path.home()` | cross-platform / OS-conditional |
| 22 | `target.resolve()` | cross-platform / OS-conditional |
| 24 | `resolved.is_relative_to(root.resolve())` | cross-platform / OS-conditional |
| 24 | `root.resolve()` | cross-platform / OS-conditional |
| 24 | `root.resolve()` | cross-platform / OS-conditional |
| 33 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 33 | `Path(xdg)` | cross-platform / OS-conditional |
| 34 | `Path(xdg)` | cross-platform / OS-conditional |
| 35 | `Path.home()` | cross-platform / OS-conditional |
| 40 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 40 | `Path(xdg)` | cross-platform / OS-conditional |
| 41 | `Path(xdg)` | cross-platform / OS-conditional |
| 42 | `Path.home()` | cross-platform / OS-conditional |
| 47 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 47 | `Path(xdg)` | cross-platform / OS-conditional |
| 48 | `Path(xdg)` | cross-platform / OS-conditional |
| 49 | `Path.home()` | cross-platform / OS-conditional |
| 54 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 54 | `Path(xdg)` | cross-platform / OS-conditional |
| 55 | `Path(xdg)` | cross-platform / OS-conditional |
| 56 | `Path.home()` | cross-platform / OS-conditional |
| 61 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 61 | `Path(xdg)` | cross-platform / OS-conditional |
| 62 | `Path(xdg)` | cross-platform / OS-conditional |
| 63 | `Path.home()` | cross-platform / OS-conditional |
| 68 | `Path(xdg).exists()` | cross-platform / OS-conditional |
| 68 | `Path(xdg)` | cross-platform / OS-conditional |
| 69 | `Path(xdg)` | cross-platform / OS-conditional |
| 70 | `Path.home()` | cross-platform / OS-conditional |
| 81 | `Path.home()` | cross-platform / OS-conditional |
| 93 | `raw.replace('\\', '/').partition('/')` | cross-platform / OS-conditional |
| 98 | `Path(raw).expanduser()` | cross-platform / OS-conditional |
| 98 | `Path(raw)` | cross-platform / OS-conditional |
| 115 | `send2trash.send2trash(str(target))` | cross-platform / OS-conditional |
| 124 | `target.exists()` | cross-platform / OS-conditional |
| 126 | `target.is_dir()` | cross-platform / OS-conditional |
| 130 | `target.iterdir()` | cross-platform / OS-conditional |
| 133 | `item.is_dir()` | cross-platform / OS-conditional |
| 136 | `item.stat()` | cross-platform / OS-conditional |
| 156 | `target.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 157 | `target.write_text(content, encoding='utf-8')` | cross-platform / OS-conditional |
| 169 | `target.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 184 | `base.exists()` | cross-platform / OS-conditional |
| 184 | `base.is_dir()` | cross-platform / OS-conditional |
| 186 | `base.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 203 | `Path(folder_name).is_absolute()` | cross-platform / OS-conditional |
| 203 | `Path(folder_name)` | cross-platform / OS-conditional |
| 213 | `target.exists()` | cross-platform / OS-conditional |
| 214 | `target.is_dir()` | cross-platform / OS-conditional |
| 219 | `target.mkdir(exist_ok=False)` | cross-platform / OS-conditional |
| 242 | `target.exists()` | cross-platform / OS-conditional |
| 248 | `Path.home()` | cross-platform / OS-conditional |
| 250 | `target.resolve()` | cross-platform / OS-conditional |
| 250 | `p.resolve()` | cross-platform / OS-conditional |
| 268 | `target.exists()` | cross-platform / OS-conditional |
| 273 | `Path.home()` | cross-platform / OS-conditional |
| 274 | `target.resolve()` | cross-platform / OS-conditional |
| 274 | `p.resolve()` | cross-platform / OS-conditional |
| 278 | `target.unlink()` | cross-platform / OS-conditional |
| 279 | `target.is_dir()` | cross-platform / OS-conditional |
| 280 | `shutil.rmtree(target)` | cross-platform / OS-conditional |
| 282 | `target.unlink()` | cross-platform / OS-conditional |
| 297 | `src.exists()` | cross-platform / OS-conditional |
| 306 | `dst.is_dir()` | cross-platform / OS-conditional |
| 309 | `dst.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 310 | `shutil.move(str(src), str(dst))` | cross-platform / OS-conditional |
| 323 | `src.exists()` | cross-platform / OS-conditional |
| 332 | `dst.is_dir()` | cross-platform / OS-conditional |
| 335 | `dst.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 337 | `src.is_dir()` | cross-platform / OS-conditional |
| 338 | `shutil.copytree(str(src), str(dst))` | cross-platform / OS-conditional |
| 340 | `shutil.copy2(str(src), str(dst))` | cross-platform / OS-conditional |
| 354 | `target.exists()` | cross-platform / OS-conditional |
| 360 | `new_path.exists()` | cross-platform / OS-conditional |
| 363 | `target.rename(new_path)` | cross-platform / OS-conditional |
| 376 | `target.exists()` | cross-platform / OS-conditional |
| 378 | `target.is_file()` | cross-platform / OS-conditional |
| 381 | `target.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 397 | `target.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 399 | `open(target, mode, encoding='utf-8')` | cross-platform / OS-conditional |
| 400 | `f.write(content)` | cross-platform / OS-conditional |
| 413 | `search_path.exists()` | cross-platform / OS-conditional |
| 420 | `search_path.rglob('*')` | cross-platform / OS-conditional |
| 421 | `item.is_dir()` | cross-platform / OS-conditional |
| 426 | `item.is_file()` | cross-platform / OS-conditional |
| 432 | `item.stat()` | cross-platform / OS-conditional |
| 453 | `search_path.exists()` | cross-platform / OS-conditional |
| 457 | `search_path.rglob('*')` | cross-platform / OS-conditional |
| 458 | `item.is_file()` | cross-platform / OS-conditional |
| 460 | `item.stat()` | cross-platform / OS-conditional |
| 483 | `shutil.disk_usage(target)` | cross-platform / OS-conditional |
| 511 | `desktop.iterdir()` | cross-platform / OS-conditional |
| 513 | `item.is_dir()` | cross-platform / OS-conditional |
| 525 | `target_dir.mkdir(exist_ok=True)` | cross-platform / OS-conditional |
| 528 | `new_path.exists()` | cross-platform / OS-conditional |
| 532 | `shutil.move(str(item), str(new_path))` | cross-platform / OS-conditional |
| 555 | `target.exists()` | cross-platform / OS-conditional |
| 558 | `target.stat()` | cross-platform / OS-conditional |
| 561 | `target.is_dir()` | cross-platform / OS-conditional |
| 607 | `move_file(path, name=name, destination=params.get('destination', ''))` | cross-platform / OS-conditional |
| 610 | `copy_file(path, name=name, destination=params.get('destination', ''))` | cross-platform / OS-conditional |
| 613 | `rename_file(path, name=name, new_name=params.get('new_name', ''))` | cross-platform / OS-conditional |
| 619 | `write_file(path, name=name, content=params.get('content', ''), append=params.get('append', False))` | cross-platform / OS-conditional |

### `actions/file_processor.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 29 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 29 | `Path(__file__)` | cross-platform / OS-conditional |
| 30 | `open(config_path, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 72 | `path.stat()` | cross-platform / OS-conditional |
| 94 | `Image.open(path)` | cross-platform / OS-conditional |
| 111 | `out.write_text(result, encoding='utf-8')` | cross-platform / OS-conditional |
| 122 | `Image.open(path)` | cross-platform / OS-conditional |
| 146 | `Image.open(path).convert('RGB')` | cross-platform / OS-conditional |
| 146 | `Image.open(path)` | cross-platform / OS-conditional |
| 146 | `Image.open(path)` | cross-platform / OS-conditional |
| 156 | `Image.open(path).convert('RGB')` | cross-platform / OS-conditional |
| 156 | `Image.open(path)` | cross-platform / OS-conditional |
| 167 | `Image.open(path)` | cross-platform / OS-conditional |
| 182 | `pdfplumber.open(path)` | cross-platform / OS-conditional |
| 188 | `open(path, 'rb')` | cross-platform / OS-conditional |
| 203 | `out.write_text(text, encoding='utf-8')` | cross-platform / OS-conditional |
| 218 | `out.write_text(result, encoding='utf-8')` | cross-platform / OS-conditional |
| 227 | `pdfplumber.open(path)` | cross-platform / OS-conditional |
| 267 | `path.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 282 | `out.write_text(content, encoding='utf-8')` | cross-platform / OS-conditional |
| 308 | `out.write_text(result, encoding='utf-8')` | cross-platform / OS-conditional |
| 416 | `path.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 426 | `out.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |
| 457 | `path.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 463 | `subprocess.run(['python', str(path)], capture_output=True, text=True, timeout=30)` | cross-platform / OS-conditional |
| 507 | `out.write_text(code_to_save, encoding='utf-8')` | cross-platform / OS-conditional |
| 534 | `path.read_bytes()` | cross-platform / OS-conditional |
| 547 | `out.write_text(result, encoding='utf-8')` | cross-platform / OS-conditional |
| 590 | `subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=3)` | cross-platform / OS-conditional |
| 597 | `subprocess.run(['ffprobe', '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', str(path)], capture_output=True, text=True, timeout=10)` | cross-platform / OS-conditional |
| 621 | `subprocess.run(['ffmpeg', '-i', str(path), '-q:a', '0', '-map', 'a', str(out), '-y'], capture_output=True, timeout=300)` | cross-platform / OS-conditional |
| 640 | `subprocess.run(cmd, capture_output=True, timeout=600)` | cross-platform / OS-conditional |
| 651 | `subprocess.run(['ffmpeg', '-i', str(path), '-ss', timestamp, '-vframes', '1', str(out), '-y'], capture_output=True, timeout=30)` | cross-platform / OS-conditional |
| 666 | `subprocess.run(['ffmpeg', '-i', str(path), '-c:v', 'libx264', '-crf', str(crf), '-preset', 'medium', '-c:a', 'copy', str(out), '-y'], capture_output=True, timeout=1800)` | cross-platform / OS-conditional |
| 682 | `Path(tempfile.mktemp(suffix='.mp3'))` | cross-platform / OS-conditional |
| 684 | `subprocess.run(['ffmpeg', '-i', str(path), '-q:a', '0', '-map', 'a', str(tmp_audio), '-y'], capture_output=True, timeout=300)` | cross-platform / OS-conditional |
| 694 | `tmp_audio.exists()` | cross-platform / OS-conditional |
| 695 | `tmp_audio.unlink()` | cross-platform / OS-conditional |
| 703 | `subprocess.run(['ffmpeg', '-i', str(path), str(out), '-y'], capture_output=True, timeout=1800)` | cross-platform / OS-conditional |
| 724 | `tarfile.open(path)` | cross-platform / OS-conditional |
| 735 | `Path(params.get('destination', str(path.parent / path.stem)))` | cross-platform / OS-conditional |
| 736 | `dest.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 738 | `shutil.unpack_archive(path, dest)` | cross-platform / OS-conditional |
| 767 | `out.write_text(text, encoding='utf-8')` | cross-platform / OS-conditional |
| 784 | `Path(file_path_str)` | cross-platform / OS-conditional |
| 785 | `path.exists()` | cross-platform / OS-conditional |
| 787 | `path.is_file()` | cross-platform / OS-conditional |
| 802 | `path.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |

### `actions/flight_finder.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 13 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 14 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 14 | `Path(__file__)` | cross-platform / OS-conditional |
| 22 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 281 | `Path.home()` | cross-platform / OS-conditional |
| 282 | `desktop.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 285 | `filepath.write_text(content, encoding='utf-8')` | cross-platform / OS-conditional |
| 290 | `subprocess.Popen(['notepad.exe', str(filepath)])` | Windows |
| 292 | `subprocess.Popen(['open', '-t', str(filepath)])` | cross-platform / OS-conditional |
| 294 | `subprocess.Popen(['xdg-open', str(filepath)])` | Linux |

### `actions/game_updater.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 16 | `platform.system()` | cross-platform / OS-conditional |
| 77 | `winreg.OpenKey(hive, key_path)` | Windows |
| 78 | `winreg.QueryValueEx(key, 'InstallPath')` | Windows |
| 79 | `winreg.CloseKey(key)` | Windows |
| 80 | `Path(val)` | cross-platform / OS-conditional |
| 81 | `p.exists()` | cross-platform / OS-conditional |
| 81 | `(p / 'steam.exe').exists()` | cross-platform / OS-conditional |
| 88 | `Path(os.environ.get('ProgramFiles(x86)', ''))` | cross-platform / OS-conditional |
| 89 | `Path(os.environ.get('ProgramFiles', ''))` | cross-platform / OS-conditional |
| 90 | `Path('C:/Steam')` | cross-platform / OS-conditional |
| 90 | `Path('D:/Steam')` | cross-platform / OS-conditional |
| 90 | `Path('E:/Steam')` | cross-platform / OS-conditional |
| 90 | `Path('F:/Steam')` | cross-platform / OS-conditional |
| 92 | `p.exists()` | cross-platform / OS-conditional |
| 92 | `(p / 'steam.exe').exists()` | cross-platform / OS-conditional |
| 99 | `Path.home()` | cross-platform / OS-conditional |
| 100 | `Path('/Applications/Steam.app/Contents/MacOS')` | macOS |
| 102 | `p.exists()` | cross-platform / OS-conditional |
| 109 | `Path.home()` | cross-platform / OS-conditional |
| 110 | `Path.home()` | cross-platform / OS-conditional |
| 111 | `Path.home()` | cross-platform / OS-conditional |
| 112 | `Path('/usr/share/steam')` | cross-platform / OS-conditional |
| 113 | `Path('/opt/steam')` | cross-platform / OS-conditional |
| 115 | `p.exists()` | cross-platform / OS-conditional |
| 122 | `Path('/Applications/Steam.app/Contents/MacOS/steam_osx')` | macOS |
| 128 | `subprocess.Popen(['open', url])` | cross-platform / OS-conditional |
| 130 | `subprocess.Popen(['xdg-open', url])` | Linux |
| 132 | `subprocess.Popen([str(exe), url])` | cross-platform / OS-conditional |
| 137 | `vdf_path.exists()` | cross-platform / OS-conditional |
| 140 | `vdf_path.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 142 | `Path(raw_path.replace('\\\\', '/'))` | cross-platform / OS-conditional |
| 143 | `lib.exists()` | cross-platform / OS-conditional |
| 153 | `lib.glob('appmanifest_*.acf')` | cross-platform / OS-conditional |
| 155 | `acf.read_text(encoding='utf-8', errors='ignore')` | cross-platform / OS-conditional |
| 164 | `state.group(1)` | cross-platform / OS-conditional |
| 176 | `subprocess.run(['tasklist', '/FI', 'IMAGENAME eq steam.exe'], capture_output=True, text=True, **_CNW)` | cross-platform / OS-conditional |
| 180 | `subprocess.run(['pgrep', '-x', proc], capture_output=True, text=True).stdout.strip()` | cross-platform / OS-conditional |
| 180 | `subprocess.run(['pgrep', '-x', proc], capture_output=True, text=True)` | cross-platform / OS-conditional |
| 209 | `pyautogui.screenshot(region=(wx, wy, ww, wh))` | cross-platform / OS-conditional |
| 224 | `pyautogui.click(wx + ww // 2 - ww // 6, wy + wh // 2)` | cross-platform / OS-conditional |
| 239 | `pyautogui.click(abs_x, abs_y)` | cross-platform / OS-conditional |
| 259 | `pyautogui.screenshot(region=(wx, wy, ww, wh))` | cross-platform / OS-conditional |
| 284 | `os.path.exists(drive_path)` | cross-platform / OS-conditional |
| 286 | `shutil.disk_usage(drive_path)` | cross-platform / OS-conditional |
| 300 | `ctrl.click_input()` | cross-platform / OS-conditional |
| 323 | `ctrl.click_input()` | cross-platform / OS-conditional |
| 336 | `btn.click_input()` | cross-platform / OS-conditional |
| 378 | `pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))` | cross-platform / OS-conditional |
| 380 | `pyautogui.typewrite(best_drive['letter'], interval=0.05)` | cross-platform / OS-conditional |
| 382 | `pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))` | cross-platform / OS-conditional |
| 406 | `Application(backend='uia').connect(handle=hwnd)` | cross-platform / OS-conditional |
| 451 | `exe.exists()` | cross-platform / OS-conditional |
| 457 | `subprocess.Popen(['open', '-a', 'Steam'])` | cross-platform / OS-conditional |
| 459 | `subprocess.Popen([str(exe)])` | cross-platform / OS-conditional |
| 630 | `subprocess.run(['shutdown', '/s', '/t', '10'], **_CNW)` | cross-platform / OS-conditional |
| 632 | `subprocess.run(['osascript', '-e', 'tell app "System Events" to shut down'])` | macOS |
| 634 | `subprocess.run(['systemctl', 'poweroff'])` | Linux |
| 681 | `winreg.OpenKey(hive, key_path)` | Windows |
| 682 | `winreg.QueryValueEx(key, 'AppDataPath')` | Windows |
| 683 | `winreg.CloseKey(key)` | Windows |
| 684 | `Path(val)` | cross-platform / OS-conditional |
| 685 | `exe.exists()` | cross-platform / OS-conditional |
| 692 | `Path(os.environ.get('ProgramFiles(x86)', ''))` | cross-platform / OS-conditional |
| 693 | `Path(os.environ.get('ProgramFiles', ''))` | cross-platform / OS-conditional |
| 694 | `Path(os.environ.get('LOCALAPPDATA', ''))` | cross-platform / OS-conditional |
| 696 | `candidate.exists()` | cross-platform / OS-conditional |
| 702 | `Path('/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher')` | macOS |
| 703 | `p.exists()` | cross-platform / OS-conditional |
| 707 | `Path('/usr/bin/heroic')` | cross-platform / OS-conditional |
| 707 | `Path.home()` | cross-platform / OS-conditional |
| 708 | `c.exists()` | cross-platform / OS-conditional |
| 715 | `Path(os.environ.get('PROGRAMDATA', 'C:/ProgramData'))` | cross-platform / OS-conditional |
| 717 | `p.exists()` | cross-platform / OS-conditional |
| 719 | `Path.home()` | cross-platform / OS-conditional |
| 721 | `p.exists()` | cross-platform / OS-conditional |
| 730 | `manifests.glob('*.item')` | cross-platform / OS-conditional |
| 732 | `item_file.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 744 | `subprocess.run(['tasklist', '/FI', 'IMAGENAME eq EpicGamesLauncher.exe'], capture_output=True, text=True, **_CNW)` | cross-platform / OS-conditional |
| 750 | `subprocess.run(['pgrep', '-x', proc], capture_output=True, text=True).stdout.strip()` | cross-platform / OS-conditional |
| 750 | `subprocess.run(['pgrep', '-x', proc], capture_output=True, text=True)` | cross-platform / OS-conditional |
| 767 | `subprocess.Popen(['open', url])` | cross-platform / OS-conditional |
| 769 | `subprocess.Popen([str(epic_exe), url] if epic_exe else ['xdg-open', url])` | Linux |
| 771 | `subprocess.Popen([str(epic_exe), url])` | cross-platform / OS-conditional |
| 778 | `subprocess.Popen(['open', '-a', 'Epic Games Launcher'])` | cross-platform / OS-conditional |
| 781 | `subprocess.Popen([str(epic_exe)])` | cross-platform / OS-conditional |
| 789 | `subprocess.Popen([str(epic_exe), f"com.epicgames.launcher://apps/{g['id']}?action=launch&silent=true"])` | cross-platform / OS-conditional |
| 794 | `subprocess.Popen([str(epic_exe)])` | cross-platform / OS-conditional |
| 810 | `subprocess.run(['schtasks', '/Query', '/TN', old_name, '/FO', 'LIST', '/V'], capture_output=True, text=True, **_CNW)` | Windows |
| 815 | `subprocess.run(['schtasks', '/Delete', '/TN', old_name, '/F'], capture_output=True, **_CNW)` | Windows |
| 823 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 823 | `Path(__file__)` | cross-platform / OS-conditional |
| 824 | `subprocess.run(['schtasks', '/Delete', '/TN', task_name, '/F'], capture_output=True, **_CNW)` | Windows |
| 829 | `subprocess.run(cmd, capture_output=True, text=True, **_CNW)` | cross-platform / OS-conditional |
| 837 | `Path.home()` | cross-platform / OS-conditional |
| 838 | `plist_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 840 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 840 | `Path(__file__)` | cross-platform / OS-conditional |
| 861 | `plist_path.write_text(plist_content, encoding='utf-8')` | cross-platform / OS-conditional |
| 862 | `subprocess.run(['launchctl', 'unload', str(plist_path)], capture_output=True)` | macOS |
| 863 | `subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True, text=True)` | macOS |
| 866 | `legacy_path.is_file()` | cross-platform / OS-conditional |
| 866 | `legacy_path.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 867 | `subprocess.run(['launchctl', 'unload', str(legacy_path)], capture_output=True)` | macOS |
| 868 | `legacy_path.unlink()` | cross-platform / OS-conditional |
| 876 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 876 | `Path(__file__)` | cross-platform / OS-conditional |
| 880 | `subprocess.run(['crontab', '-l'], capture_output=True, text=True)` | Linux |
| 884 | `subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n', text=True, capture_output=True)` | Linux |
| 897 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 897 | `Path(__file__)` | cross-platform / OS-conditional |
| 900 | `subprocess.run(['schtasks', '/Query', '/TN', task_name, '/FO', 'LIST', '/V'], capture_output=True, text=True, **_CNW)` | Windows |
| 906 | `subprocess.run(['schtasks', '/Delete', '/TN', task_name, '/F'], capture_output=True, text=True, **_CNW)` | Windows |
| 913 | `Path.home()` | cross-platform / OS-conditional |
| 917 | `path.exists()` | cross-platform / OS-conditional |
| 918 | `path.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 918 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 918 | `Path(__file__)` | cross-platform / OS-conditional |
| 920 | `subprocess.run(['launchctl', 'unload', str(path)], capture_output=True)` | macOS |
| 921 | `path.unlink()` | cross-platform / OS-conditional |
| 926 | `subprocess.run(['crontab', '-l'], capture_output=True, text=True)` | Linux |
| 929 | `subprocess.run(['crontab', '-'], input='\n'.join(lines) + '\n', text=True, capture_output=True)` | Linux |
| 943 | `subprocess.run(['schtasks', '/Query', '/TN', name, '/FO', 'LIST'], capture_output=True, text=True, **_CNW)` | Windows |
| 956 | `Path.home()` | cross-platform / OS-conditional |
| 958 | `(folder / name).exists()` | cross-platform / OS-conditional |
| 963 | `subprocess.run(['crontab', '-l'], capture_output=True, text=True)` | Linux |

### `actions/open_app.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 16 | `platform.system()` | cross-platform / OS-conditional |
| 101 | `shutil.which(app_name)` | cross-platform / OS-conditional |
| 101 | `shutil.which(app_name.split('.')[0])` | cross-platform / OS-conditional |
| 104 | `subprocess.Popen([executable], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 118 | `os.startfile(app_name)` | cross-platform / OS-conditional |
| 127 | `pyautogui.press('win')` | cross-platform / OS-conditional |
| 129 | `pyautogui.write(app_name, interval=0.05)` | cross-platform / OS-conditional |
| 131 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 144 | `subprocess.run(['open', '-a', app_name], capture_output=True, timeout=8)` | cross-platform / OS-conditional |
| 155 | `subprocess.run(['open', '-a', f'{app_name}.app'], capture_output=True, timeout=8)` | macOS |
| 165 | `shutil.which(app_name)` | cross-platform / OS-conditional |
| 165 | `shutil.which(app_name.lower())` | cross-platform / OS-conditional |
| 168 | `subprocess.Popen([binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 180 | `pyautogui.hotkey('command', 'space')` | cross-platform / OS-conditional |
| 182 | `pyautogui.write(app_name, interval=0.05)` | cross-platform / OS-conditional |
| 184 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 204 | `shutil.which(term)` | cross-platform / OS-conditional |
| 206 | `subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 213 | `shutil.which('gtk-launch')` | cross-platform / OS-conditional |
| 216 | `subprocess.Popen([gtk_launch, desktop_id], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 232 | `shutil.which(launch_parts[0])` | cross-platform / OS-conditional |
| 233 | `shutil.which(launch_parts[0].lower())` | cross-platform / OS-conditional |
| 233 | `launch_parts[0].lower()` | cross-platform / OS-conditional |
| 234 | `shutil.which(launch_parts[0].lower().replace(' ', '-'))` | cross-platform / OS-conditional |
| 234 | `launch_parts[0].lower()` | cross-platform / OS-conditional |
| 235 | `shutil.which(launch_parts[0].lower().replace(' ', '_'))` | cross-platform / OS-conditional |
| 235 | `launch_parts[0].lower()` | cross-platform / OS-conditional |
| 239 | `subprocess.Popen([binary, *launch_parts[1:]], shell=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 251 | `subprocess.run(['xdg-open', app_name], capture_output=True, timeout=5)` | Linux |
| 266 | `subprocess.run(['gtk-launch', desktop_name], capture_output=True, timeout=5)` | cross-platform / OS-conditional |
| 314 | `Path(appdata)` | cross-platform / OS-conditional |
| 316 | `Path(programdata)` | cross-platform / OS-conditional |
| 324 | `root.is_dir()` | cross-platform / OS-conditional |
| 326 | `os.walk(root)` | cross-platform / OS-conditional |
| 328 | `Path(filename).suffix.casefold()` | cross-platform / OS-conditional |
| 328 | `Path(filename)` | cross-platform / OS-conditional |
| 330 | `Path(filename).stem.strip()` | cross-platform / OS-conditional |
| 330 | `Path(filename)` | cross-platform / OS-conditional |
| 340 | `Path.home()` | cross-platform / OS-conditional |
| 341 | `Path('/Applications')` | macOS |
| 341 | `Path('/System/Applications')` | macOS |
| 344 | `root.is_dir()` | cross-platform / OS-conditional |
| 346 | `os.walk(root)` | cross-platform / OS-conditional |
| 348 | `Path(d)` | cross-platform / OS-conditional |
| 356 | `Path.home()` | cross-platform / OS-conditional |
| 358 | `Path('/usr/share/applications')` | macOS |
| 359 | `Path('/usr/local/share/applications')` | macOS |
| 361 | `Path('/var/lib/flatpak/exports/share/applications')` | macOS |
| 363 | `Path('/var/lib/snapd/desktop/applications')` | macOS |
| 371 | `path.read_text(encoding='utf-8', errors='replace')` | cross-platform / OS-conditional |
| 387 | `root.is_dir()` | cross-platform / OS-conditional |
| 389 | `os.walk(root)` | cross-platform / OS-conditional |
| 393 | `Path(current)` | cross-platform / OS-conditional |
| 417 | `root.is_dir()` | cross-platform / OS-conditional |
| 419 | `os.walk(root)` | cross-platform / OS-conditional |
| 423 | `Path(current)` | cross-platform / OS-conditional |
| 454 | `shutil.which(parts[0])` | cross-platform / OS-conditional |
| 499 | `ctypes.create_unicode_buffer(max(1, length + 1))` | cross-platform / OS-conditional |
| 503 | `subprocess.run(['osascript', '-e', 'tell application "System Events" to get name of first application process whose frontmost is true'], capture_output=True, text=True, timeout=2)` | macOS |
| 508 | `shutil.which('xdotool')` | Linux |
| 509 | `subprocess.run(['xdotool', 'getactivewindow', 'getwindowname'], capture_output=True, text=True, timeout=2)` | Linux |
| 584 | `launcher(normalized)` | cross-platform / OS-conditional |
| 586 | `launcher(app_name)` | cross-platform / OS-conditional |

### `actions/pushup_counter.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 31 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 31 | `Path(__file__)` | cross-platform / OS-conditional |
| 77 | `(BASE_DIR / 'config' / 'api_keys.json').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 86 | `platform.system()` | cross-platform / OS-conditional |
| 89 | `cv2.VideoCapture(int(_config().get('camera_index', 0)), backend)` | cross-platform / OS-conditional |
| 91 | `cv2.VideoCapture(0)` | cross-platform / OS-conditional |
| 206 | `frame.copy()` | cross-platform / OS-conditional |
| 233 | `path.exists()` | cross-platform / OS-conditional |
| 235 | `path.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 244 | `path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |

### `actions/reminder.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 12 | `platform.system()` | cross-platform / OS-conditional |
| 17 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 18 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 18 | `Path(__file__)` | cross-platform / OS-conditional |
| 22 | `platform.system()` | cross-platform / OS-conditional |
| 31 | `Path.home()` | cross-platform / OS-conditional |
| 32 | `d.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 38 | `text.replace('\\', '').replace('"', '').replace("'", '').replace('\n', ' ').replace('\r', '').strip()` | cross-platform / OS-conditional |
| 142 | `script_path.write_text(script_body, encoding='utf-8')` | cross-platform / OS-conditional |
| 143 | `script_path.chmod(384)` | cross-platform / OS-conditional |
| 148 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 150 | `pythonw.exists()` | cross-platform / OS-conditional |
| 181 | `xml_path.write_text(xml_content, encoding='utf-16')` | cross-platform / OS-conditional |
| 183 | `subprocess.run(['schtasks', '/Create', '/TN', task_name, '/XML', str(xml_path), '/F'], capture_output=True, text=True, **_CNW)` | Windows |
| 189 | `xml_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 194 | `script_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 204 | `Path.home()` | cross-platform / OS-conditional |
| 205 | `agents_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 235 | `plist_path.write_text(plist_content, encoding='utf-8')` | cross-platform / OS-conditional |
| 236 | `plist_path.chmod(420)` | cross-platform / OS-conditional |
| 238 | `subprocess.run(['launchctl', 'load', str(plist_path)], capture_output=True, text=True)` | macOS |
| 244 | `plist_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 245 | `script_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 255 | `shutil.which('systemd-run')` | cross-platform / OS-conditional |
| 257 | `subprocess.run(['systemd-run', '--user', f'--on-calendar={on_calendar}', f'--unit={task_name}', '--', sys.executable, str(script_path)], capture_output=True, text=True)` | cross-platform / OS-conditional |
| 272 | `shutil.which('at')` | cross-platform / OS-conditional |
| 275 | `subprocess.run(['at', at_time], input=cmd_str, capture_output=True, text=True)` | cross-platform / OS-conditional |
| 326 | `script_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |

### `actions/screen_processor.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 41 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 42 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 42 | `Path(__file__)` | cross-platform / OS-conditional |
| 51 | `_CONFIG_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 60 | `_CONFIG_PATH.write_text(json.dumps(cfg, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 101 | `PIL.Image.open(io.BytesIO(img_bytes)).convert('RGB')` | cross-platform / OS-conditional |
| 101 | `PIL.Image.open(io.BytesIO(img_bytes))` | cross-platform / OS-conditional |
| 115 | `mss.mss()` | cross-platform / OS-conditional |
| 118 | `sct.grab(target)` | cross-platform / OS-conditional |
| 119 | `mss.tools.to_png(shot.rgb, shot.size)` | cross-platform / OS-conditional |
| 140 | `cv2.VideoCapture(index, backend)` | cross-platform / OS-conditional |
| 182 | `cv2.VideoCapture(index, backend)` | cross-platform / OS-conditional |
| 278 | `client.aio.live.connect(model=_LIVE_MODEL, config=config)` | cross-platform / OS-conditional |
| 363 | `sd.RawOutputStream(samplerate=_RECEIVE_SAMPLE_RATE, channels=_CHANNELS, dtype='int16', blocksize=_CHUNK_SIZE)` | cross-platform / OS-conditional |

### `actions/send_message.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 23 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 24 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 24 | `Path(__file__)` | cross-platform / OS-conditional |
| 29 | `(_base_dir() / 'config' / 'api_keys.json').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 48 | `pyperclip.copy(text)` | cross-platform / OS-conditional |
| 50 | `pyautogui.hotkey(*paste_hotkey)` | cross-platform / OS-conditional |
| 53 | `pyautogui.write(text, interval=0.03)` | cross-platform / OS-conditional |
| 60 | `pyautogui.hotkey(*select_all)` | cross-platform / OS-conditional |
| 62 | `pyautogui.press('delete')` | cross-platform / OS-conditional |
| 72 | `pyautogui.press('win')` | cross-platform / OS-conditional |
| 76 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 81 | `subprocess.run(['open', '-a', app_name], capture_output=True, text=True, timeout=10)` | cross-platform / OS-conditional |
| 86 | `subprocess.run(['open', '-a', f'{app_name}.app'], capture_output=True, text=True, timeout=10)` | macOS |
| 100 | `subprocess.Popen(launcher, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` | cross-platform / OS-conditional |
| 120 | `webbrowser.open(url)` | cross-platform / OS-conditional |
| 132 | `pyautogui.hotkey(*search_hotkey)` | cross-platform / OS-conditional |
| 143 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 148 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 175 | `pyautogui.press('down')` | cross-platform / OS-conditional |
| 177 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 181 | `pyautogui.press('tab')` | cross-platform / OS-conditional |
| 183 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 188 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 203 | `pyautogui.press('down')` | cross-platform / OS-conditional |
| 205 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 210 | `pyautogui.press('enter')` | cross-platform / OS-conditional |

### `actions/system_monitor.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 11 | `platform.system()` | cross-platform / OS-conditional |
| 61 | `ctypes.c_void_p()` | cross-platform / OS-conditional |
| 62 | `ctypes.byref(dev)` | cross-platform / OS-conditional |
| 64 | `ctypes.byref(u)` | cross-platform / OS-conditional |
| 88 | `psutil.sensors_temperatures()` | cross-platform / OS-conditional |
| 115 | `psutil.cpu_percent(interval=0.2)` | cross-platform / OS-conditional |
| 116 | `psutil.virtual_memory()` | cross-platform / OS-conditional |
| 120 | `psutil.boot_time()` | cross-platform / OS-conditional |
| 133 | `psutil.pids()` | cross-platform / OS-conditional |
| 156 | `psutil.cpu_percent(interval=None)` | cross-platform / OS-conditional |
| 157 | `psutil.virtual_memory()` | cross-platform / OS-conditional |

### `actions/upload_video.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 88 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 89 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 89 | `Path(__file__)` | cross-platform / OS-conditional |
| 97 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 110 | `pyperclip.copy(text)` | cross-platform / OS-conditional |
| 112 | `pyautogui.hotkey('ctrl', 'v')` | cross-platform / OS-conditional |
| 114 | `pyautogui.typewrite(text, interval=0.02)` | cross-platform / OS-conditional |
| 158 | `pyautogui.size()` | cross-platform / OS-conditional |
| 161 | `pyautogui.press('win')` | cross-platform / OS-conditional |
| 163 | `pyautogui.write('opera gx', interval=0.05)` | cross-platform / OS-conditional |
| 165 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 169 | `pyautogui.hotkey('ctrl', 't')` | cross-platform / OS-conditional |
| 173 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 178 | `pyautogui.click(w // 2, h // 2)` | cross-platform / OS-conditional |
| 180 | `pyautogui.press('tab')` | cross-platform / OS-conditional |
| 182 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 187 | `pyautogui.hotkey('ctrl', 'f')` | cross-platform / OS-conditional |
| 189 | `pyautogui.write('video', interval=0.03)` | cross-platform / OS-conditional |
| 195 | `pyautogui.doubleClick(int(w * 240 / 1920), int(h * 135 / 1080))` | cross-platform / OS-conditional |
| 204 | `pyautogui.press('tab')` | cross-platform / OS-conditional |
| 205 | `pyautogui.press('tab')` | cross-platform / OS-conditional |
| 206 | `pyautogui.hotkey('ctrl', 'a')` | cross-platform / OS-conditional |
| 214 | `pyautogui.press('tab')` | cross-platform / OS-conditional |
| 217 | `pyautogui.press('enter')` | cross-platform / OS-conditional |
| 219 | `pyautogui.click(int(w * 1089 / 1920), int(h * 653 / 1080))` | cross-platform / OS-conditional |
| 220 | `pyautogui.click(int(w * 1200 / 1920), int(h * 655 / 1080))` | cross-platform / OS-conditional |

### `actions/weather_report.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 25 | `webbrowser.open(url)` | cross-platform / OS-conditional |

### `actions/web_search.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 68 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 69 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 69 | `Path(__file__)` | cross-platform / OS-conditional |
| 77 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |

### `actions/youtube_video.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 41 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 42 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 42 | `Path(__file__)` | cross-platform / OS-conditional |
| 61 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 68 | `subprocess.Popen(['open', url])` | cross-platform / OS-conditional |
| 70 | `subprocess.Popen(['xdg-open', url])` | Linux |
| 72 | `subprocess.Popen(['cmd', '/c', 'start', '', url], shell=False)` | cross-platform / OS-conditional |
| 200 | `Path.home()` | cross-platform / OS-conditional |
| 201 | `desktop.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 211 | `filepath.write_text(header + content, encoding='utf-8')` | cross-platform / OS-conditional |
| 215 | `subprocess.Popen(['notepad.exe', str(filepath)])` | Windows |
| 217 | `subprocess.Popen(['open', '-t', str(filepath)])` | cross-platform / OS-conditional |
| 219 | `subprocess.Popen(['xdg-open', str(filepath)])` | Linux |

### `config/__init__.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 5 | `Path(__file__)` | cross-platform / OS-conditional |
| 10 | `platform.system()` | cross-platform / OS-conditional |
| 15 | `open(_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |

### `core/agent_reliability.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 134 | `Path(path)` | cross-platform / OS-conditional |
| 135 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 136 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 136 | `Path(__file__)` | cross-platform / OS-conditional |
| 142 | `sqlite3.connect(str(self.path), timeout=1.0)` | cross-platform / OS-conditional |
| 146 | `self.path.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 149 | `connection.execute("CREATE TABLE IF NOT EXISTS tasks (task_id TEXT PRIMARY KEY, tool TEXT NOT NULL, status TEXT NOT NULL, verification TEXT NOT NULL DEFAULT 'not_verified', duration_ms INTEGER, created_at REAL NOT NULL, updated_at REAL NOT NULL)")` | cross-platform / OS-conditional |
| 157 | `connection.execute("UPDATE tasks SET status='interrupted', verification='not_verified', updated_at=? WHERE status IN ('queued', 'running')", (time.time(),))` | cross-platform / OS-conditional |
| 172 | `connection.executemany("INSERT INTO tasks (task_id, tool, status, created_at, updated_at) VALUES (?, ?, 'queued', ?, ?)", [(str(task_id)[:96], _safe_tool_name(tool), now, now) for task_id, tool in tasks])` | cross-platform / OS-conditional |
| 200 | `connection.execute('UPDATE tasks SET status=?, verification=?, duration_ms=?, updated_at=? WHERE task_id=?', (status, verification, duration_ms, time.time(), task_id))` | cross-platform / OS-conditional |
| 205 | `connection.execute("DELETE FROM tasks WHERE task_id IN (SELECT task_id FROM tasks WHERE status IN ('succeeded','failed','cancelled','blocked','interrupted') ORDER BY updated_at DESC, rowid DESC LIMIT -1 OFFSET ?)", (self.retention,))` | cross-platform / OS-conditional |
| 222 | `connection.execute('SELECT tool, status, verification, duration_ms FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT ?', (size,)).fetchall()` | cross-platform / OS-conditional |
| 222 | `connection.execute('SELECT tool, status, verification, duration_ms FROM tasks ORDER BY created_at DESC, rowid DESC LIMIT ?', (size,))` | cross-platform / OS-conditional |

### `core/app_icon.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 42 | `out_path.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 49 | `out_path.is_file()` | cross-platform / OS-conditional |
| 49 | `out_path.stat()` | cross-platform / OS-conditional |

### `core/branding.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 16 | `target.exists()` | cross-platform / OS-conditional |
| 20 | `candidate.exists()` | cross-platform / OS-conditional |
| 29 | `legacy.is_dir()` | cross-platform / OS-conditional |
| 30 | `target.exists()` | cross-platform / OS-conditional |
| 30 | `legacy.iterdir()` | cross-platform / OS-conditional |
| 31 | `legacy.rename(target)` | cross-platform / OS-conditional |
| 33 | `target.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 34 | `target.is_dir()` | cross-platform / OS-conditional |
| 36 | `legacy.iterdir()` | cross-platform / OS-conditional |
| 39 | `entry.rename(_collision_free_path(target / entry.name))` | cross-platform / OS-conditional |
| 41 | `legacy.rmdir()` | cross-platform / OS-conditional |
| 44 | `target.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 57 | `Path.home()` | cross-platform / OS-conditional |
| 62 | `legacy.is_dir()` | cross-platform / OS-conditional |
| 72 | `Path.home()` | cross-platform / OS-conditional |
| 74 | `desktop.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 80 | `Path.home()` | cross-platform / OS-conditional |
| 81 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 81 | `Path(__file__)` | cross-platform / OS-conditional |
| 83 | `parent.is_dir()` | cross-platform / OS-conditional |
| 90 | `fallback.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |

### `core/hardware_check.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 53 | `platform.system()` | cross-platform / OS-conditional |
| 72 | `platform.system()` | cross-platform / OS-conditional |

### `core/installer.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 76 | `subprocess.run([sys.executable, '-m', 'pip', 'install', package, '--quiet', '--disable-pip-version-check'], capture_output=True)` | cross-platform / OS-conditional |
| 105 | `platform.system()` | cross-platform / OS-conditional |
| 139 | `subprocess.run([sys.executable, '-m', 'playwright', 'install', 'chromium'], capture_output=True)` | cross-platform / OS-conditional |

### `core/llm_client.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 35 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 36 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 36 | `Path(__file__)` | cross-platform / OS-conditional |
| 57 | `CONFIG_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 106 | `subprocess.Popen(['ollama', 'serve'], **kwargs)` | cross-platform / OS-conditional |

### `core/narration_audio.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 195 | `stream.write(chunk)` | cross-platform / OS-conditional |

### `core/plugin_loader.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 97 | `run_fn(parameters, **kwargs)` | cross-platform / OS-conditional |
| 104 | `Path(filename)` | cross-platform / OS-conditional |
| 109 | `Path(filename)` | cross-platform / OS-conditional |
| 141 | `plugins_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 145 | `plugins_dir.glob('*.py')` | cross-platform / OS-conditional |
| 157 | `spec.loader.exec_module(module)` | cross-platform / OS-conditional |

### `core/startup_check.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 57 | `sys.executable.lower().endswith('pythonw.exe')` | cross-platform / OS-conditional |
| 57 | `sys.executable.lower()` | cross-platform / OS-conditional |
| 60 | `ctypes.windll.user32.MessageBoxW(None, message, 'EDITH — Setup Required', 48)` | Windows |

### `core/task_scheduler.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 131 | `spec.run()` | cross-platform / OS-conditional |
| 133 | `spec.run()` | cross-platform / OS-conditional |
| 232 | `running.pop(task)` | cross-platform / OS-conditional |

### `core/tts.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 171 | `subprocess.run([sys.executable, '-m', 'pip', 'install', 'kokoro>=0.9', '--upgrade', '--quiet', '--disable-pip-version-check'], capture_output=True)` | cross-platform / OS-conditional |

### `core/ui_design.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 122 | `close.clicked.connect(self.reject)` | cross-platform / OS-conditional |
| 155 | `self.move(max(screen.left() + 8, min(center.x() - self.width() // 2, screen.right() - self.width() - 8)), max(screen.top() + 8, min(center.y() - self.height() // 2, screen.bottom() - self.height() - 8)))` | cross-platform / OS-conditional |
| 221 | `cursor.movePosition(QTextCursor.MoveOperation.End)` | cross-platform / OS-conditional |

### `core/video_visual.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 18 | `path.is_file()` | cross-platform / OS-conditional |
| 25 | `self.sink.videoFrameChanged.connect(self._receive_frame)` | cross-platform / OS-conditional |
| 26 | `self.player.errorOccurred.connect(self._error)` | cross-platform / OS-conditional |
| 27 | `path.resolve()` | cross-platform / OS-conditional |

### `dashboard/server.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 38 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 38 | `Path(__file__)` | cross-platform / OS-conditional |
| 39 | `Path(__file__)` | cross-platform / OS-conditional |
| 53 | `open(BASE_DIR / 'config' / 'api_keys.json', 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 110 | `subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule', f'name={name}'], capture_output=True, text=True, timeout=5)` | Windows |
| 120 | `subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', "(Get-NetConnectionProfile \| Where-Object {$_.NetworkCategory -eq 'Public'} \| Measure-Object).Count"], capture_output=True, text=True, timeout=6)` | Windows |
| 163 | `os.write(fd, bat_body.encode('mbcs'))` | cross-platform / OS-conditional |
| 174 | `subprocess.run([bat_path], capture_output=True, timeout=8, shell=True)` | cross-platform / OS-conditional |
| 180 | `os.unlink(bat_path)` | cross-platform / OS-conditional |
| 193 | `ctypes.windll.shell32.ShellExecuteW(None, 'runas', bat_path, None, None, 0)` | Windows |
| 217 | `os.unlink(path)` | cross-platform / OS-conditional |
| 227 | `subprocess.run([fw_ctl, '--getglobalstate'], capture_output=True, text=True, timeout=5)` | cross-platform / OS-conditional |
| 234 | `subprocess.run([fw_ctl, '--listapps'], capture_output=True, text=True, timeout=5)` | cross-platform / OS-conditional |
| 241 | `subprocess.run(['osascript', '-e', f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}" with administrator privileges'], timeout=60)` | macOS |
| 255 | `subprocess.run(prefix + cmd, capture_output=True, timeout=30)` | cross-platform / OS-conditional |
| 263 | `subprocess.run(['ufw', 'status'], capture_output=True, text=True, timeout=5)` | cross-platform / OS-conditional |
| 274 | `subprocess.run(['firewall-cmd', '--state'], capture_output=True, text=True, timeout=5)` | cross-platform / OS-conditional |
| 289 | `subprocess.run(['iptables', '-L', 'INPUT', '-n'], capture_output=True, timeout=5)` | cross-platform / OS-conditional |
| 300 | `_CRYPTOJS_FILE.exists()` | cross-platform / OS-conditional |
| 322 | `socket.socket(socket.AF_INET, socket.SOCK_DGRAM)` | cross-platform / OS-conditional |
| 324 | `s.connect((probe, 80))` | cross-platform / OS-conditional |
| 334 | `socket.gethostbyname(socket.gethostname())` | cross-platform / OS-conditional |
| 334 | `socket.gethostname()` | cross-platform / OS-conditional |
| 342 | `socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)` | cross-platform / OS-conditional |
| 342 | `socket.gethostname()` | cross-platform / OS-conditional |
| 356 | `key_p.exists()` | cross-platform / OS-conditional |
| 356 | `crt_p.exists()` | cross-platform / OS-conditional |
| 359 | `old_key.exists()` | cross-platform / OS-conditional |
| 359 | `old_crt.exists()` | cross-platform / OS-conditional |
| 360 | `key_p.exists()` | cross-platform / OS-conditional |
| 360 | `crt_p.exists()` | cross-platform / OS-conditional |
| 362 | `old_key.rename(key_p)` | cross-platform / OS-conditional |
| 364 | `old_crt.rename(crt_p)` | cross-platform / OS-conditional |
| 366 | `key_p.rename(old_key)` | cross-platform / OS-conditional |
| 390 | `key_p.exists()` | cross-platform / OS-conditional |
| 390 | `crt_p.exists()` | cross-platform / OS-conditional |
| 406 | `certs.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 441 | `key_p.write_bytes(key.private_bytes(encoding=serialization.Encoding.PEM, format=serialization.PrivateFormat.TraditionalOpenSSL, encryption_algorithm=serialization.NoEncryption()))` | cross-platform / OS-conditional |
| 446 | `crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))` | cross-platform / OS-conditional |
| 450 | `_os.chmod(key_p, 384)` | cross-platform / OS-conditional |
| 462 | `(STATIC_DIR / name).read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 503 | `p.exists()` | cross-platform / OS-conditional |
| 575 | `_CRYPTOJS_FILE.exists()` | cross-platform / OS-conditional |
| 741 | `websocket.close(code=4001)` | cross-platform / OS-conditional |
| 743 | `websocket.accept()` | cross-platform / OS-conditional |
| 749 | `websocket.receive_bytes()` | cross-platform / OS-conditional |
| 778 | `Path(raw)` | cross-platform / OS-conditional |
| 790 | `Path(safe)` | cross-platform / OS-conditional |
| 790 | `Path(safe)` | cross-platform / OS-conditional |
| 792 | `dest.exists()` | cross-platform / OS-conditional |
| 799 | `open(dest, 'wb')` | cross-platform / OS-conditional |
| 807 | `dest.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 812 | `fout.write(chunk)` | cross-platform / OS-conditional |
| 815 | `dest.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 842 | `self._uploads_dir.iterdir()` | cross-platform / OS-conditional |
| 842 | `p.is_file()` | cross-platform / OS-conditional |
| 843 | `p.stat()` | cross-platform / OS-conditional |
| 846 | `f.stat()` | cross-platform / OS-conditional |
| 859 | `path.exists()` | cross-platform / OS-conditional |
| 859 | `path.is_file()` | cross-platform / OS-conditional |
| 867 | `websocket.close(code=4001)` | cross-platform / OS-conditional |
| 869 | `websocket.accept()` | cross-platform / OS-conditional |
| 873 | `websocket.send_json(entry)` | cross-platform / OS-conditional |
| 878 | `websocket.receive_json()` | cross-platform / OS-conditional |
| 882 | `websocket.send_json({'type': 'pong'})` | cross-platform / OS-conditional |
| 905 | `asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT + 1)` | cross-platform / OS-conditional |
| 921 | `asyncio.get_event_loop().run_in_executor(None, _ensure_network_access, PORT)` | cross-platform / OS-conditional |

### `main.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 19 | `_platform.system()` | cross-platform / OS-conditional |
| 95 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 96 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 96 | `Path(__file__)` | cross-platform / OS-conditional |
| 109 | `open(API_CONFIG_PATH, 'r', encoding='utf-8')` | cross-platform / OS-conditional |
| 115 | `API_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 117 | `API_CONFIG_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 124 | `temp_path.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 130 | `PROMPT_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 652 | `API_CONFIG_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 709 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 709 | `Path(__file__)` | cross-platform / OS-conditional |
| 861 | `self._task_scheduler.run_batch(specs)` | cross-platform / OS-conditional |
| 868 | `states.get(spec.task_id)` | cross-platform / OS-conditional |
| 993 | `open(API_CONFIG_PATH, encoding='utf-8').read()` | cross-platform / OS-conditional |
| 993 | `open(API_CONFIG_PATH, encoding='utf-8')` | cross-platform / OS-conditional |
| 1289 | `open_app(parameters=args, response=None, player=self.ui)` | cross-platform / OS-conditional |
| 1443 | `self._plugin_registry.run(name, args, player=self.ui, session_memory=None)` | cross-platform / OS-conditional |
| 1514 | `sd.InputStream(samplerate=SEND_SAMPLE_RATE, channels=CHANNELS, dtype='int16', blocksize=CHUNK_SIZE, callback=callback)` | cross-platform / OS-conditional |
| 2093 | `client.aio.live.connect(model=LIVE_MODEL, config=config)` | cross-platform / OS-conditional |
| 2198 | `self.ui._win.open_api_key_settings_signal.emit()` | cross-platform / OS-conditional |
| 2245 | `asyncio.run(edith.run())` | cross-platform / OS-conditional |
| 2245 | `edith.run()` | cross-platform / OS-conditional |

### `memory/config_manager.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 7 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 8 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 8 | `Path(__file__)` | cross-platform / OS-conditional |
| 15 | `CONFIG_DIR.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 18 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 24 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 26 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 32 | `CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')` | cross-platform / OS-conditional |
| 46 | `CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 47 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 48 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 64 | `Path(stream.name)` | cross-platform / OS-conditional |
| 66 | `stream.write('\n')` | cross-platform / OS-conditional |
| 70 | `temp_path.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 74 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 77 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 104 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 106 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 111 | `CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 121 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 123 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 127 | `CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 138 | `CONFIG_FILE.exists()` | cross-platform / OS-conditional |
| 140 | `CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 148 | `CONFIG_FILE.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |

### `memory/memory_manager.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 10 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 11 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 11 | `Path(__file__)` | cross-platform / OS-conditional |
| 31 | `MEMORY_PATH.exists()` | cross-platform / OS-conditional |
| 35 | `MEMORY_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 74 | `MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 76 | `MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |
| 139 | `key.replace('_', ' ').title()` | cross-platform / OS-conditional |
| 148 | `key.replace('_', ' ').title()` | cross-platform / OS-conditional |
| 157 | `key.replace('_', ' ').title()` | cross-platform / OS-conditional |
| 166 | `key.replace('_', ' ').title()` | cross-platform / OS-conditional |
| 175 | `key.replace('_', ' ').title()` | cross-platform / OS-conditional |
| 241 | `MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 242 | `MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |
| 255 | `MEMORY_PATH.exists()` | cross-platform / OS-conditional |
| 258 | `MEMORY_PATH.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 264 | `MEMORY_PATH.write_text(json.dumps(memory, indent=2, ensure_ascii=False), encoding='utf-8')` | cross-platform / OS-conditional |

### `setup.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 7 | `subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], check=True)` | cross-platform / OS-conditional |
| 10 | `subprocess.run([sys.executable, '-m', 'playwright', 'install'], check=True)` | cross-platform / OS-conditional |
| 12 | `platform.system()` | cross-platform / OS-conditional |
| 16 | `Path(sys.executable)` | cross-platform / OS-conditional |

### `tests/check_inline_js.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 7 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 7 | `Path(__file__)` | cross-platform / OS-conditional |
| 39 | `(ROOT / relative).read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 41 | `Path(tmp)` | cross-platform / OS-conditional |
| 41 | `Path(relative)` | cross-platform / OS-conditional |
| 42 | `script_path.write_text(script, encoding='utf-8')` | cross-platform / OS-conditional |
| 43 | `subprocess.run(['node', '--check', str(script_path)], check=True)` | cross-platform / OS-conditional |

### `tests/test_action_activity.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 85 | `app_module.open_app({'app_name': 'Docker Desktop'})` | cross-platform / OS-conditional |
| 97 | `app_module.open_app({'app_name': 'Docker Desktop'})` | cross-platform / OS-conditional |
| 107 | `Path.home()` | cross-platform / OS-conditional |
| 108 | `Path(tmp)` | cross-platform / OS-conditional |
| 109 | `target.write_text('remove me', encoding='utf-8')` | cross-platform / OS-conditional |
| 112 | `target.exists()` | cross-platform / OS-conditional |
| 118 | `Path.home()` | cross-platform / OS-conditional |
| 119 | `Path(tmp)` | cross-platform / OS-conditional |
| 120 | `child.write_text('remove me', encoding='utf-8')` | cross-platform / OS-conditional |
| 123 | `Path(tmp).exists()` | cross-platform / OS-conditional |
| 123 | `Path(tmp)` | cross-platform / OS-conditional |
| 124 | `child.exists()` | cross-platform / OS-conditional |
| 129 | `Path.home()` | cross-platform / OS-conditional |
| 139 | `app_module.open_app({'action': 'list'})` | cross-platform / OS-conditional |
| 141 | `launchers.__getitem__.assert_not_called()` | cross-platform / OS-conditional |

### `tests/test_audio_hardware_fallback.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 14 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 14 | `Path(__file__)` | cross-platform / OS-conditional |
| 61 | `statuses.values()` | cross-platform / OS-conditional |
| 77 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 93 | `exec(compile(module, str(ROOT / 'main.py'), 'exec'), scope)` | cross-platform / OS-conditional |

### `tests/test_enterprise_ui.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 25 | `Path(cls.tmp.name)` | cross-platform / OS-conditional |
| 26 | `ui.API_FILE.write_text(json.dumps({'gemini_api_key': 'test', 'os_system': 'Linux'}))` | cross-platform / OS-conditional |
| 58 | `state['event'].is_set()` | cross-platform / OS-conditional |

### `tests/test_fast_response.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 103 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 103 | `Path(__file__)` | cross-platform / OS-conditional |
| 104 | `(root / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 105 | `(root / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_file_controller.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 10 | `Path.home()` | cross-platform / OS-conditional |
| 12 | `Path(self.temp.name)` | cross-platform / OS-conditional |
| 13 | `self.parent.mkdir()` | cross-platform / OS-conditional |
| 21 | `(self.parent / name).is_dir()` | cross-platform / OS-conditional |
| 24 | `(self.parent / '1').mkdir()` | cross-platform / OS-conditional |
| 28 | `(self.parent / '1').is_dir()` | cross-platform / OS-conditional |
| 29 | `(self.parent / '2').is_dir()` | cross-platform / OS-conditional |
| 36 | `(self.parent / '3').is_dir()` | cross-platform / OS-conditional |
| 37 | `(self.parent / 'nested').exists()` | cross-platform / OS-conditional |
| 38 | `(Path(self.temp.name).parent / 'outside').exists()` | cross-platform / OS-conditional |
| 38 | `Path(self.temp.name)` | cross-platform / OS-conditional |

### `tests/test_narration_audio.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 107 | `self.run_player(buffer, stream)` | cross-platform / OS-conditional |
| 118 | `self.run_player(buffer, stream)` | cross-platform / OS-conditional |
| 136 | `self.run_player(buffer, stream)` | cross-platform / OS-conditional |
| 183 | `state.copy()` | cross-platform / OS-conditional |

### `tests/test_phase1_setup.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 15 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 15 | `Path(__file__)` | cross-platform / OS-conditional |
| 21 | `Path(tmp)` | cross-platform / OS-conditional |
| 24 | `old.mkdir(parents=True)` | cross-platform / OS-conditional |
| 25 | `(old / 'notes.txt').write_text('keep me', encoding='utf-8')` | cross-platform / OS-conditional |
| 26 | `Path(tmp)` | cross-platform / OS-conditional |
| 28 | `(target / 'notes.txt').read_text()` | cross-platform / OS-conditional |
| 29 | `old.exists()` | cross-platform / OS-conditional |
| 33 | `Path(tmp)` | cross-platform / OS-conditional |
| 36 | `old.mkdir(parents=True)` | cross-platform / OS-conditional |
| 37 | `new.mkdir()` | cross-platform / OS-conditional |
| 38 | `(old / 'report.pdf').write_text('old', encoding='utf-8')` | cross-platform / OS-conditional |
| 39 | `(new / 'report.pdf').write_text('new', encoding='utf-8')` | cross-platform / OS-conditional |
| 40 | `Path(tmp)` | cross-platform / OS-conditional |
| 42 | `(new / 'report.pdf').read_text()` | cross-platform / OS-conditional |
| 43 | `(new / 'report_migrated_1.pdf').read_text()` | cross-platform / OS-conditional |
| 44 | `old.exists()` | cross-platform / OS-conditional |
| 48 | `Path(tmp)` | cross-platform / OS-conditional |
| 51 | `old.mkdir(parents=True)` | cross-platform / OS-conditional |
| 52 | `Path(tmp)` | cross-platform / OS-conditional |
| 53 | `outside.write_text('outside', encoding='utf-8')` | cross-platform / OS-conditional |
| 58 | `Path(tmp)` | cross-platform / OS-conditional |
| 59 | `outside.read_text()` | cross-platform / OS-conditional |
| 60 | `(path / 'linked.txt').exists()` | cross-platform / OS-conditional |
| 64 | `Path(tmp)` | cross-platform / OS-conditional |
| 65 | `Path(tmp)` | cross-platform / OS-conditional |
| 67 | `path.is_dir()` | cross-platform / OS-conditional |
| 71 | `Path(tmp)` | cross-platform / OS-conditional |
| 73 | `source.mkdir(parents=True)` | cross-platform / OS-conditional |
| 74 | `(source / 'Cookies').write_bytes(b'retained browser data')` | cross-platform / OS-conditional |
| 77 | `(target / 'chrome' / 'Cookies').read_bytes()` | cross-platform / OS-conditional |
| 82 | `Path(tmp)` | cross-platform / OS-conditional |
| 84 | `source.mkdir(parents=True)` | cross-platform / OS-conditional |
| 85 | `(source / 'main.py').write_text("print('keep')", encoding='utf-8')` | cross-platform / OS-conditional |
| 89 | `(target / 'sample' / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 119 | `Path(tmp)` | cross-platform / OS-conditional |
| 121 | `Image.open(dest)` | cross-platform / OS-conditional |
| 123 | `icon.ico.sizes()` | cross-platform / OS-conditional |
| 124 | `icon.ico.sizes()` | cross-platform / OS-conditional |
| 125 | `icon.ico.sizes()` | cross-platform / OS-conditional |
| 134 | `(ROOT / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 151 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 152 | `(ROOT / 'dashboard' / 'server.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 162 | `Path(tmp)` | cross-platform / OS-conditional |
| 173 | `config_manager.CONFIG_FILE.write_text(json.dumps(saved), encoding='utf-8')` | cross-platform / OS-conditional |
| 189 | `Path(tmp)` | cross-platform / OS-conditional |
| 191 | `config_manager.CONFIG_FILE.write_text(bad_data, encoding='utf-8')` | cross-platform / OS-conditional |
| 195 | `config_manager.CONFIG_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 204 | `Path(tmp)` | cross-platform / OS-conditional |
| 214 | `Path(tmp)` | cross-platform / OS-conditional |
| 215 | `config_manager.CONFIG_FILE.write_text('{"gemini_api_key":"secret","llm_provider":"openai","llm_url":"http://127.0.0.1:1234","llm_model":"local-model"}', encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_phase4_qt.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 28 | `Path(cls.tmp.name)` | cross-platform / OS-conditional |
| 29 | `ui.API_FILE.write_text(json.dumps({'gemini_api_key': 'test-only-not-valid', 'os_system': 'Windows'}), encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_phase4_ui.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 11 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 11 | `Path(__file__)` | cross-platform / OS-conditional |
| 74 | `(ROOT / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 75 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 76 | `(ROOT / 'core' / 'llm_client.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_phase5_remote.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 17 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 17 | `Path(__file__)` | cross-platform / OS-conditional |
| 23 | `Path(self.temp.name)` | cross-platform / OS-conditional |
| 49 | `asyncio.run(self.server.broadcast({'type': 'sys', 'text': 'Safe test event'}))` | cross-platform / OS-conditional |
| 52 | `socket.receive_json()` | cross-platform / OS-conditional |
| 55 | `socket.send_json({'type': 'ping'})` | cross-platform / OS-conditional |
| 56 | `socket.receive_json()` | cross-platform / OS-conditional |
| 58 | `socket.receive_json()` | cross-platform / OS-conditional |
| 93 | `(ROOT / 'dashboard' / 'static' / 'app.html').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 94 | `(ROOT / 'dashboard' / 'static' / 'login.html').read_text(encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_phase6_reliability.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 15 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 15 | `Path(__file__)` | cross-platform / OS-conditional |
| 85 | `Path(temp)` | cross-platform / OS-conditional |
| 102 | `Path(temp)` | cross-platform / OS-conditional |
| 113 | `sqlite3.connect(path)` | cross-platform / OS-conditional |
| 114 | `db.execute('SELECT * FROM tasks')` | cross-platform / OS-conditional |
| 123 | `Path(temp)` | cross-platform / OS-conditional |
| 127 | `sqlite3.connect(journal.path)` | cross-platform / OS-conditional |
| 128 | `db.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'").fetchone()` | cross-platform / OS-conditional |
| 128 | `db.execute("SELECT COUNT(*) FROM tasks WHERE status='queued'")` | cross-platform / OS-conditional |
| 129 | `db.execute("SELECT COUNT(*) FROM tasks WHERE status='succeeded'").fetchone()` | cross-platform / OS-conditional |
| 129 | `db.execute("SELECT COUNT(*) FROM tasks WHERE status='succeeded'")` | cross-platform / OS-conditional |
| 135 | `Path(temp)` | cross-platform / OS-conditional |
| 136 | `file_path.write_text('occupied', encoding='utf-8')` | cross-platform / OS-conditional |
| 153 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 160 | `(ROOT / 'core' / 'llm_client.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 179 | `scheduler.run_batch([TaskSpec('a', 'Send message', cancelled, exclusive=True, retry_limit=5), TaskSpec('b', 'More changes', dependent, exclusive=True, depends_on=('a',))])` | cross-platform / OS-conditional |

### `tests/test_product_contract.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 4 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 4 | `Path(__file__)` | cross-platform / OS-conditional |
| 10 | `(ROOT / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 11 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 12 | `(ROOT / 'core' / 'llm_client.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 13 | `(ROOT / 'core' / 'task_scheduler.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 14 | `(ROOT / 'core' / 'prompt.txt').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 15 | `(ROOT / 'dashboard' / 'static' / 'app.html').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 16 | `(ROOT / 'dashboard' / 'static' / 'login.html').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 17 | `(ROOT / 'readme.md').read_text(encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_product_identity.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 20 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 20 | `Path(__file__)` | cross-platform / OS-conditional |
| 21 | `source.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 27 | `exec(compile(module, str(source), 'exec'), namespace)` | cross-platform / OS-conditional |

### `tests/test_response_status.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 15 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 15 | `Path(__file__)` | cross-platform / OS-conditional |
| 16 | `source.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 21 | `exec(compile(ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[])), str(source), 'exec'), scope)` | cross-platform / OS-conditional |

### `tests/test_task_scheduler.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 35 | `scheduler.run_batch(specs)` | cross-platform / OS-conditional |
| 57 | `scheduler.run_batch([TaskSpec(str(n), 'Read', work) for n in range(7)])` | cross-platform / OS-conditional |
| 82 | `scheduler.run_batch(tasks)` | cross-platform / OS-conditional |
| 95 | `scheduler.run_batch([TaskSpec('low', 'Low', lambda: work('low'), priority=20), TaskSpec('high', 'High', lambda: work('high'), priority=0), TaskSpec('medium', 'Medium', lambda: work('medium'), priority=10)])` | cross-platform / OS-conditional |
| 118 | `scheduler.run_batch([TaskSpec('one', 'One', first), TaskSpec('two', 'Two', second)])` | cross-platform / OS-conditional |
| 140 | `scheduler.run_batch([TaskSpec('a', 'Fail', fail), TaskSpec('b', 'Unsafe', dependent, depends_on=('a',), exclusive=True)])` | cross-platform / OS-conditional |
| 158 | `scheduler.run_batch([TaskSpec('a', 'Confirm', cancelled_action, exclusive=True), TaskSpec('b', 'Next', dependent, depends_on=('a',), exclusive=True)])` | cross-platform / OS-conditional |
| 181 | `scheduler.run_batch([TaskSpec('a', 'Unsafe', unsafe, retry_limit=3, retry_safe=False), TaskSpec('b', 'Safe', safe, retry_limit=1, retry_safe=True)])` | cross-platform / OS-conditional |
| 194 | `scheduler.run_batch([TaskSpec('a', 'Unknown dependency', perform, depends_on=('missing',))])` | cross-platform / OS-conditional |

### `tests/test_video_visual.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 20 | `staticmethod(draw_blended_video)` | cross-platform / OS-conditional |
| 21 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 21 | `Path(__file__)` | cross-platform / OS-conditional |
| 41 | `visual.player.position()` | cross-platform / OS-conditional |

### `tests/test_voice_input_ui.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 11 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 11 | `Path(__file__)` | cross-platform / OS-conditional |
| 40 | `(ROOT / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 41 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 74 | `(ROOT / 'ui.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 82 | `exec(compile(module, str(ROOT / 'ui.py'), 'exec'), namespace)` | cross-platform / OS-conditional |
| 83 | `staticmethod(namespace['_emit_if_open'])` | cross-platform / OS-conditional |
| 84 | `(ROOT / 'main.py').read_text(encoding='utf-8')` | cross-platform / OS-conditional |

### `tests/test_youtube_channels.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 16 | `open_url.assert_called_once()` | cross-platform / OS-conditional |
| 28 | `open_url.assert_not_called()` | cross-platform / OS-conditional |

### `tools/phase2_benchmark.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 17 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 17 | `Path(__file__)` | cross-platform / OS-conditional |
| 58 | `run_benchmark(args.iterations, args.timeout)` | cross-platform / OS-conditional |
| 63 | `statistics.median((item['total_ms'] for item in results))` | cross-platform / OS-conditional |
| 68 | `statistics.median(firsts)` | cross-platform / OS-conditional |

### `ui.py`

| Line | Call/expression | Platform |
| --- | --- | --- |
| 16 | `platform.system()` | cross-platform / OS-conditional |
| 43 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 44 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 44 | `Path(__file__)` | cross-platform / OS-conditional |
| 51 | `platform.system()` | cross-platform / OS-conditional |
| 52 | `platform.system()` | cross-platform / OS-conditional |
| 57 | `API_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 66 | `platform.system()` | cross-platform / OS-conditional |
| 209 | `ctypes.WinDLL(dll_name)` | Windows |
| 223 | `ctypes.c_void_p()` | cross-platform / OS-conditional |
| 224 | `ctypes.byref(dev)` | cross-platform / OS-conditional |
| 226 | `ctypes.byref(util)` | cross-platform / OS-conditional |
| 243 | `psutil.net_io_counters()` | cross-platform / OS-conditional |
| 260 | `psutil.cpu_percent(interval=None)` | cross-platform / OS-conditional |
| 261 | `psutil.virtual_memory()` | cross-platform / OS-conditional |
| 264 | `psutil.net_io_counters()` | cross-platform / OS-conditional |
| 307 | `ctypes.CDLL(_lib)` | cross-platform / OS-conditional |
| 309 | `ctypes.c_void_p()` | cross-platform / OS-conditional |
| 310 | `ctypes.byref(dev)` | cross-platform / OS-conditional |
| 312 | `ctypes.byref(u)` | cross-platform / OS-conditional |
| 321 | `psutil.sensors_temperatures()` | cross-platform / OS-conditional |
| 364 | `self._video.frame_ready.connect(self.update)` | cross-platform / OS-conditional |
| 397 | `self._tmr.timeout.connect(self._step)` | cross-platform / OS-conditional |
| 432 | `Image.open(path).convert('RGBA')` | cross-platform / OS-conditional |
| 432 | `Image.open(path)` | cross-platform / OS-conditional |
| 535 | `self.state.upper()` | cross-platform / OS-conditional |
| 647 | `self._tmr.timeout.connect(self._step)` | cross-platform / OS-conditional |
| 648 | `self._sig.connect(self._enqueue)` | cross-platform / OS-conditional |
| 694 | `cur.movePosition(cur.MoveOperation.End)` | cross-platform / OS-conditional |
| 702 | `cur.movePosition(cur.MoveOperation.End)` | cross-platform / OS-conditional |
| 761 | `self._anim_tmr.timeout.connect(self._animate)` | cross-platform / OS-conditional |
| 786 | `Path(path).is_file()` | cross-platform / OS-conditional |
| 786 | `Path(path)` | cross-platform / OS-conditional |
| 809 | `Path.home()` | cross-platform / OS-conditional |
| 892 | `Path(self._z._current_file)` | cross-platform / OS-conditional |
| 895 | `path.stat()` | cross-platform / OS-conditional |
| 981 | `close_btn.clicked.connect(self.hide)` | cross-platform / OS-conditional |
| 992 | `self._timer.timeout.connect(self.hide)` | cross-platform / OS-conditional |
| 1056 | `status_card.setStyleSheet(f'QFrame {{ background: {C.PANEL2}; border: 1px solid {C.BORDER}; border-radius: 7px; }}')` | cross-platform / OS-conditional |
| 1060 | `status_layout.setContentsMargins(8, 6, 8, 6)` | cross-platform / OS-conditional |
| 1061 | `status_layout.setSpacing(2)` | cross-platform / OS-conditional |
| 1078 | `status_layout.addWidget(info)` | cross-platform / OS-conditional |
| 1090 | `self._local_test_btn.clicked.connect(self._test_local_llm)` | cross-platform / OS-conditional |
| 1136 | `self._reveal_btn.clicked.connect(self._toggle_reveal)` | cross-platform / OS-conditional |
| 1142 | `self._test_btn.clicked.connect(self._test_key)` | cross-platform / OS-conditional |
| 1157 | `self._save_btn.clicked.connect(self._save_key)` | cross-platform / OS-conditional |
| 1164 | `close_btn.clicked.connect(self.hide)` | cross-platform / OS-conditional |
| 1167 | `self._key_input.textChanged.connect(self._on_key_edited)` | cross-platform / OS-conditional |
| 1168 | `self._test_result.connect(self._finish_test)` | cross-platform / OS-conditional |
| 1169 | `self._local_connection_result.connect(self._finish_local_connection)` | cross-platform / OS-conditional |
| 1170 | `self._local_test_result.connect(self._finish_local_test)` | cross-platform / OS-conditional |
| 1438 | `client.aio.live.connect(model='models/gemini-2.5-flash-native-audio-preview-12-2025', config=config)` | cross-platform / OS-conditional |
| 1471 | `asyncio.run(asyncio.wait_for(_probe(), timeout=22.0))` | cross-platform / OS-conditional |
| 1524 | `tmp_path.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 1611 | `btn.clicked.connect(lambda _, k=key: self._sel(k))` | cross-platform / OS-conditional |
| 1631 | `init_btn.clicked.connect(self._submit)` | cross-platform / OS-conditional |
| 1741 | `e.position()` | cross-platform / OS-conditional |
| 1747 | `e.position()` | cross-platform / OS-conditional |
| 1822 | `df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))` | cross-platform / OS-conditional |
| 1834 | `self._wheel.hue_picked.connect(self._on_wheel_pick)` | cross-platform / OS-conditional |
| 1835 | `self._wheel.hue_committed.connect(self._on_wheel_commit)` | cross-platform / OS-conditional |
| 1842 | `self._hex_input.textEdited.connect(self._on_hex_edited)` | cross-platform / OS-conditional |
| 1859 | `save_btn.clicked.connect(self._save)` | cross-platform / OS-conditional |
| 1873 | `cancel_btn.clicked.connect(self._cancel)` | cross-platform / OS-conditional |
| 1972 | `close_btn.clicked.connect(self.hide)` | cross-platform / OS-conditional |
| 2002 | `btn.clicked.connect(lambda _, name=p['name'], b=btn: self._toggle(name, b))` | cross-platform / OS-conditional |
| 2066 | `x_btn.clicked.connect(self.hide)` | cross-platform / OS-conditional |
| 2095 | `b.clicked.connect(lambda _, c=cmd_fmt: self._trigger(c))` | cross-platform / OS-conditional |
| 2101 | `self._dismiss_timer.timeout.connect(self.hide)` | cross-platform / OS-conditional |
| 2224 | `new_btn.clicked.connect(self._refresh_key)` | cross-platform / OS-conditional |
| 2238 | `close_btn.clicked.connect(self._do_close)` | cross-platform / OS-conditional |
| 2243 | `self._ctimer.timeout.connect(self._tick)` | cross-platform / OS-conditional |
| 2374 | `self._url_prompt_sig.connect(self._show_url_prompt)` | cross-platform / OS-conditional |
| 2377 | `self.voice_mode_signal.connect(self.set_voice_mode_display)` | cross-platform / OS-conditional |
| 2378 | `self.task_status_signal.connect(self._update_task_status)` | cross-platform / OS-conditional |
| 2379 | `self.task_detail_signal.connect(self._update_task_details)` | cross-platform / OS-conditional |
| 2380 | `self.text_send_failed_signal.connect(self._restore_unsent_command)` | cross-platform / OS-conditional |
| 2381 | `self.open_api_key_settings_signal.connect(self._open_api_key_settings)` | cross-platform / OS-conditional |
| 2478 | `_cam_x.clicked.connect(self.stop_camera_stream)` | cross-platform / OS-conditional |
| 2528 | `self._clock_tmr.timeout.connect(self._tick_clock)` | cross-platform / OS-conditional |
| 2534 | `self._mic_status_tmr.timeout.connect(self._refresh_mic_status)` | cross-platform / OS-conditional |
| 2540 | `self._metric_tmr.timeout.connect(self._update_metrics)` | cross-platform / OS-conditional |
| 2544 | `self._log_sig.connect(self._log.append_log)` | cross-platform / OS-conditional |
| 2545 | `self._state_sig.connect(self._apply_state)` | cross-platform / OS-conditional |
| 2546 | `self._playback_sig.connect(self._on_playback_state)` | cross-platform / OS-conditional |
| 2547 | `self._output_level_sig.connect(self.hud.set_output_level)` | cross-platform / OS-conditional |
| 2548 | `self._mic_level_sig.connect(self._on_mic_level)` | cross-platform / OS-conditional |
| 2549 | `self._content_sig.connect(self._show_content)` | cross-platform / OS-conditional |
| 2550 | `self._reconfig_sig.connect(self._show_setup)` | cross-platform / OS-conditional |
| 2551 | `self._camera_sig.connect(self._show_camera_frame)` | cross-platform / OS-conditional |
| 2552 | `self._cam_stream_sig.connect(self._on_cam_stream)` | cross-platform / OS-conditional |
| 2553 | `self._cam_frame_sig.connect(self._on_cam_frame)` | cross-platform / OS-conditional |
| 2554 | `self._clipboard_sig.connect(self._show_clipboard_panel)` | cross-platform / OS-conditional |
| 2555 | `self._confirm_action_sig.connect(self._show_action_confirmation)` | cross-platform / OS-conditional |
| 2563 | `self._clipboard_panel.action_requested.connect(self._on_clipboard_action)` | cross-platform / OS-conditional |
| 2564 | `QApplication.clipboard().dataChanged.connect(self._on_clipboard_changed)` | cross-platform / OS-conditional |
| 2572 | `sc_mute.activated.connect(self._toggle_mute)` | cross-platform / OS-conditional |
| 2574 | `sc_full.activated.connect(self._toggle_fullscreen)` | cross-platform / OS-conditional |
| 2576 | `sc_intr.activated.connect(self._escape_action)` | cross-platform / OS-conditional |
| 2578 | `sc_focus.activated.connect(self._focus_command_input)` | cross-platform / OS-conditional |
| 2588 | `timer.timeout.connect(dialog.reject)` | cross-platform / OS-conditional |
| 2590 | `dialog.exec()` | cross-platform / OS-conditional |
| 2663 | `(CONFIG_DIR / 'api_keys.json').read_text()` | cross-platform / OS-conditional |
| 2671 | `cv2.VideoCapture(cam_idx, backend)` | cross-platform / OS-conditional |
| 2673 | `cv2.VideoCapture(0)` | cross-platform / OS-conditional |
| 2712 | `Dispatch('WScript.Shell')` | cross-platform / OS-conditional |
| 2740 | `f.write(vbs)` | cross-platform / OS-conditional |
| 2741 | `subprocess.Popen(['wscript.exe', '/nologo', tmp], creationflags=subprocess.DETACHED_PROCESS \| subprocess.CREATE_NO_WINDOW)` | cross-platform / OS-conditional |
| 2748 | `os.unlink(tmp)` | cross-platform / OS-conditional |
| 2763 | `Path.home()` | cross-platform / OS-conditional |
| 2764 | `platform.system()` | cross-platform / OS-conditional |
| 2781 | `(ctypes.c_ubyte * 8)(176, 41, 127, 233, 154, 135, 198, 65)` | cross-platform / OS-conditional |
| 2783 | `ctypes.c_wchar_p()` | cross-platform / OS-conditional |
| 2784 | `ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(buf))` | Windows |
| 2785 | `ctypes.byref(fid)` | cross-platform / OS-conditional |
| 2785 | `ctypes.byref(buf)` | cross-platform / OS-conditional |
| 2786 | `Path(buf.value)` | cross-platform / OS-conditional |
| 2787 | `ctypes.windll.ole32.CoTaskMemFree(buf)` | Windows |
| 2788 | `p.is_dir()` | cross-platform / OS-conditional |
| 2796 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders')` | Windows |
| 2800 | `winreg.QueryValueEx(key, 'Desktop')` | Windows |
| 2801 | `Path(os.path.expandvars(val))` | cross-platform / OS-conditional |
| 2802 | `p.is_dir()` | cross-platform / OS-conditional |
| 2810 | `subprocess.run(['xdg-user-dir', 'DESKTOP'], capture_output=True, text=True, timeout=5)` | Linux |
| 2812 | `Path(out.stdout.strip())` | cross-platform / OS-conditional |
| 2813 | `p.is_dir()` | cross-platform / OS-conditional |
| 2819 | `cfg.read_text(encoding='utf-8').splitlines()` | cross-platform / OS-conditional |
| 2819 | `cfg.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 2823 | `Path(val.replace('$HOME', str(home)))` | cross-platform / OS-conditional |
| 2824 | `p.is_dir()` | cross-platform / OS-conditional |
| 2841 | `str(script.resolve()).casefold()` | cross-platform / OS-conditional |
| 2841 | `script.resolve()` | cross-platform / OS-conditional |
| 2842 | `platform.system()` | cross-platform / OS-conditional |
| 2845 | `Dispatch('WScript.Shell')` | cross-platform / OS-conditional |
| 2848 | `desktop.glob('*.lnk')` | cross-platform / OS-conditional |
| 2858 | `shortcut.unlink()` | cross-platform / OS-conditional |
| 2862 | `platform.system()` | cross-platform / OS-conditional |
| 2866 | `old.is_file()` | cross-platform / OS-conditional |
| 2866 | `old.read_text(encoding='utf-8').casefold()` | cross-platform / OS-conditional |
| 2866 | `old.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 2867 | `old.unlink()` | cross-platform / OS-conditional |
| 2879 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 2879 | `Path(__file__)` | cross-platform / OS-conditional |
| 2880 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 2884 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 2884 | `Path(__file__)` | cross-platform / OS-conditional |
| 2885 | `ico_path.exists()` | cross-platform / OS-conditional |
| 2890 | `platform.system()` | cross-platform / OS-conditional |
| 2895 | `pythonw.exists()` | cross-platform / OS-conditional |
| 2897 | `ico_path.exists()` | cross-platform / OS-conditional |
| 2906 | `mac_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 2907 | `res_dir.mkdir(exist_ok=True)` | cross-platform / OS-conditional |
| 2912 | `launcher.write_text(f'#!/usr/bin/env bash\ncd "{script.parent}"\nexec "{python}" "{script}"\n')` | cross-platform / OS-conditional |
| 2917 | `launcher.chmod(launcher.stat().st_mode \| _stat.S_IEXEC \| _stat.S_IXGRP \| _stat.S_IXOTH)` | cross-platform / OS-conditional |
| 2917 | `launcher.stat()` | cross-platform / OS-conditional |
| 2921 | `(app / 'Contents' / 'Info.plist').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n  <key>CFBundleExecutable</key><string>EDITH</string>\n  <key>CFBundleIdentifier</key><string>app.edith.assistant</string>\n  <key>CFBundleName</key><string>EDITH</string>\n  <key>CFBundlePackageType</key><string>APPL</string>\n  <key>CFBundleVersion</key><string>1.0</string>\n</dict></plist>\n')` | cross-platform / OS-conditional |
| 2939 | `PIL.Image.open(ico_path).save(icns, format='ICNS')` | cross-platform / OS-conditional |
| 2939 | `PIL.Image.open(ico_path)` | cross-platform / OS-conditional |
| 2942 | `plist.read_text()` | cross-platform / OS-conditional |
| 2943 | `plist.write_text(txt.replace('</dict></plist>', '  <key>CFBundleIconFile</key><string>AppIcon</string>\n</dict></plist>\n'))` | cross-platform / OS-conditional |
| 2957 | `ico_path.exists()` | cross-platform / OS-conditional |
| 2957 | `png_path.exists()` | cross-platform / OS-conditional |
| 2960 | `PIL.Image.open(ico_path).resize((256, 256), PIL.Image.LANCZOS).save(png_path, format='PNG')` | cross-platform / OS-conditional |
| 2960 | `PIL.Image.open(ico_path).resize((256, 256), PIL.Image.LANCZOS)` | cross-platform / OS-conditional |
| 2960 | `PIL.Image.open(ico_path)` | cross-platform / OS-conditional |
| 2966 | `png_path.exists()` | cross-platform / OS-conditional |
| 2968 | `desk.write_text(f'[Desktop Entry]\nName=EDITH\nExec={python} {script}\nPath={script.parent}\nType=Application\nTerminal=false\nCategories=Utility;\n' + icon_line)` | cross-platform / OS-conditional |
| 2978 | `desk.chmod(desk.stat().st_mode \| 493)` | cross-platform / OS-conditional |
| 2978 | `desk.stat()` | cross-platform / OS-conditional |
| 3077 | `psutil.boot_time()` | cross-platform / OS-conditional |
| 3086 | `psutil.pids()` | cross-platform / OS-conditional |
| 3126 | `self._drawer_btn.clicked.connect(self._toggle_drawer)` | cross-platform / OS-conditional |
| 3278 | `status.setText(state.upper())` | cross-platform / OS-conditional |
| 3278 | `state.upper()` | cross-platform / OS-conditional |
| 3279 | `status.setStyleSheet(f'color: {colors.get(state, C.TEXT_MED)}; background: transparent;')` | cross-platform / OS-conditional |
| 3330 | `self._cancel_queued_btn.clicked.connect(self._request_cancel_queued)` | cross-platform / OS-conditional |
| 3350 | `self._task_details_btn.toggled.connect(self._toggle_task_details)` | cross-platform / OS-conditional |
| 3404 | `self._drop_zone.file_selected.connect(self._on_file_selected)` | cross-platform / OS-conditional |
| 3405 | `self._drop_zone.file_cleared.connect(self._clear_selected_file)` | cross-platform / OS-conditional |
| 3439 | `self._interrupt_btn.clicked.connect(self._do_interrupt)` | cross-platform / OS-conditional |
| 3446 | `self._mute_btn.clicked.connect(self._toggle_mute)` | cross-platform / OS-conditional |
| 3498 | `remote_btn.clicked.connect(self._open_remote)` | cross-platform / OS-conditional |
| 3508 | `fs_btn.clicked.connect(self._toggle_fullscreen)` | cross-platform / OS-conditional |
| 3516 | `sc_btn.clicked.connect(self._create_desktop_shortcut)` | cross-platform / OS-conditional |
| 3523 | `self._autostart_btn.clicked.connect(self._toggle_autostart)` | cross-platform / OS-conditional |
| 3533 | `cust_btn.clicked.connect(self._open_customize)` | cross-platform / OS-conditional |
| 3547 | `self._motion_btn.toggled.connect(self._toggle_reduced_motion)` | cross-platform / OS-conditional |
| 3555 | `key_btn.clicked.connect(self._open_api_key_settings)` | cross-platform / OS-conditional |
| 3567 | `self._voice_female_btn.clicked.connect(lambda: self._request_voice_mode('female'))` | cross-platform / OS-conditional |
| 3574 | `self._voice_male_btn.clicked.connect(lambda: self._request_voice_mode('male'))` | cross-platform / OS-conditional |
| 3582 | `self._brief_btn.clicked.connect(self._toggle_brief)` | cross-platform / OS-conditional |
| 3592 | `plugin_btn.clicked.connect(self._open_plugin_manager)` | cross-platform / OS-conditional |
| 3646 | `ov.saved.connect(self._on_api_key_saved)` | cross-platform / OS-conditional |
| 3675 | `self._quick_drawer.sizeHint().height()` | cross-platform / OS-conditional |
| 3675 | `self._quick_drawer.sizeHint()` | cross-platform / OS-conditional |
| 3695 | `self._input.returnPressed.connect(self._send)` | cross-platform / OS-conditional |
| 3712 | `send.clicked.connect(self._send)` | cross-platform / OS-conditional |
| 3773 | `dismiss.clicked.connect(w.hide)` | cross-platform / OS-conditional |
| 3819 | `state.get('deadline', time.monotonic() + state.get('timeout', 180))` | cross-platform / OS-conditional |
| 3819 | `state.get('timeout', 180)` | cross-platform / OS-conditional |
| 3887 | `cancel_btn.clicked.connect(dialog.reject)` | cross-platform / OS-conditional |
| 3888 | `confirm_btn.clicked.connect(dialog.accept)` | cross-platform / OS-conditional |
| 3896 | `timer.timeout.connect(dialog.reject)` | cross-platform / OS-conditional |
| 3898 | `dialog.exec()` | cross-platform / OS-conditional |
| 3904 | `state.get('event')` | cross-platform / OS-conditional |
| 3918 | `self._content_display.moveCursor(self._content_display.textCursor().MoveOperation.Start)` | cross-platform / OS-conditional |
| 3968 | `Path(path)` | cross-platform / OS-conditional |
| 3970 | `p.stat()` | cross-platform / OS-conditional |
| 4015 | `ov.closed.connect(lambda: setattr(self, '_remote_overlay', None))` | cross-platform / OS-conditional |
| 4028 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 4028 | `Path(__file__)` | cross-platform / OS-conditional |
| 4032 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_READ \| winreg.KEY_SET_VALUE)` | Windows |
| 4038 | `winreg.QueryValueEx(reg, 'JARVIS_AI')` | Windows |
| 4044 | `winreg.QueryValueEx(reg, 'EDITH')` | Windows |
| 4046 | `winreg.SetValueEx(reg, 'EDITH', 0, winreg.REG_SZ, command)` | Windows |
| 4047 | `winreg.DeleteValue(reg, 'JARVIS_AI')` | Windows |
| 4049 | `Path.home()` | cross-platform / OS-conditional |
| 4052 | `old.is_file()` | cross-platform / OS-conditional |
| 4053 | `old.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 4055 | `new.exists()` | cross-platform / OS-conditional |
| 4056 | `new.write_text(content.replace('local.aiassistant.desktop', 'app.edith.assistant'), encoding='utf-8')` | cross-platform / OS-conditional |
| 4060 | `old.unlink()` | cross-platform / OS-conditional |
| 4062 | `Path.home()` | cross-platform / OS-conditional |
| 4065 | `old.is_file()` | cross-platform / OS-conditional |
| 4066 | `old.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 4068 | `new.exists()` | cross-platform / OS-conditional |
| 4069 | `new.write_text(content.replace('Name=JARVIS', 'Name=EDITH').replace('Name=Jarvis', 'Name=EDITH'), encoding='utf-8')` | cross-platform / OS-conditional |
| 4074 | `old.unlink()` | cross-platform / OS-conditional |
| 4083 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_READ)` | Windows |
| 4088 | `winreg.QueryValueEx(reg, 'EDITH')` | Windows |
| 4091 | `(Path.home() / 'Library' / 'LaunchAgents' / 'app.edith.assistant.plist').exists()` | cross-platform / OS-conditional |
| 4091 | `Path.home()` | cross-platform / OS-conditional |
| 4093 | `(Path.home() / '.config' / 'autostart' / 'edith.desktop').exists()` | cross-platform / OS-conditional |
| 4093 | `Path.home()` | cross-platform / OS-conditional |
| 4100 | `Path(__file__).resolve()` | cross-platform / OS-conditional |
| 4100 | `Path(__file__)` | cross-platform / OS-conditional |
| 4103 | `winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Software\\Microsoft\\Windows\\CurrentVersion\\Run', 0, winreg.KEY_READ \| winreg.KEY_SET_VALUE)` | Windows |
| 4109 | `winreg.DeleteValue(reg, 'EDITH')` | Windows |
| 4111 | `Path(sys.executable)` | cross-platform / OS-conditional |
| 4112 | `pythonw.exists()` | cross-platform / OS-conditional |
| 4113 | `winreg.SetValueEx(reg, 'EDITH', 0, winreg.REG_SZ, f'"{exe}" "{script}"')` | Windows |
| 4118 | `Path.home()` | cross-platform / OS-conditional |
| 4119 | `plist_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 4122 | `plist.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 4124 | `plist.write_text(f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n  <key>Label</key><string>app.edith.assistant</string>\n  <key>ProgramArguments</key><array>\n    <string>{sys.executable}</string>\n    <string>{script}</string>\n  </array>\n  <key>RunAtLoad</key><true/>\n</dict></plist>\n', encoding='utf-8')` | cross-platform / OS-conditional |
| 4139 | `Path.home()` | cross-platform / OS-conditional |
| 4140 | `desk_dir.mkdir(parents=True, exist_ok=True)` | cross-platform / OS-conditional |
| 4143 | `desk.unlink(missing_ok=True)` | cross-platform / OS-conditional |
| 4145 | `desk.write_text(f'[Desktop Entry]\nName=EDITH\nExec={sys.executable} {script}\nType=Application\nTerminal=false\nX-GNOME-Autostart-enabled=true\n', encoding='utf-8')` | cross-platform / OS-conditional |
| 4237 | `ov.saved.connect(self._apply_name_update)` | cross-platform / OS-conditional |
| 4272 | `API_FILE.write_text(json.dumps(data, indent=4), encoding='utf-8')` | cross-platform / OS-conditional |
| 4310 | `self._clipboard_panel.sizeHint().height()` | cross-platform / OS-conditional |
| 4310 | `self._clipboard_panel.sizeHint()` | cross-platform / OS-conditional |
| 4424 | `state.upper()` | cross-platform / OS-conditional |
| 4446 | `API_FILE.exists()` | cross-platform / OS-conditional |
| 4448 | `API_FILE.read_text(encoding='utf-8')` | cross-platform / OS-conditional |
| 4462 | `ov.done.connect(self._on_setup_done)` | cross-platform / OS-conditional |
| 4489 | `self._app.exec()` | cross-platform / OS-conditional |
| 4496 | `platform.system()` | cross-platform / OS-conditional |
| 4500 | `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('EDITH.PersonalAssistant.Desktop')` | Windows |
| 4513 | `self._app.aboutToQuit.connect(self._mark_closed)` | cross-platform / OS-conditional |
| 4514 | `self._win.destroyed.connect(self._mark_closed)` | cross-platform / OS-conditional |
| 4621 | `state['event'].wait(max(1.0, float(timeout)))` | cross-platform / OS-conditional |
| 4624 | `state.get('confirmed', False)` | cross-platform / OS-conditional |

## Hardcoded paths, commands, registry and OS assumptions

The following string inventory includes constants and command arguments, alongside
prompt/test fixtures. Dynamic arguments are captured in the call-site inventory
above. A path containing a user home, quoted shell text, desktop launcher template
or platform-specific directory must stay inside the relevant controller/legacy
compatibility handler. Literal contents are source constants, never user secrets.
Known assumptions include `Path.home()/Desktop` (localized/XDG alternatives),
Windows Start Menu/registry and NVML DLL paths, browser profile locations, Steam/
Epic install paths, scheduled-task names, GNOME/KDE/X11 utilities, macOS Rectangle,
fixed 960×1080 window snapping, positional GUI uploads, `python`/pip executable
names, and setup installing Playwright browsers. Full candidate literals follow.

### `actions/browser_control.py`

- L64: `LOCALAPPDATA`
- L65: `APPDATA`
- L120: `APPDATA`
- L156: `LOCALAPPDATA`
- L157: `PROGRAMFILES`
- L158: `PROGRAMFILES(X86)`
- L161: `opera.exe`
- L162: `opera.exe`
- L163: `opera.exe`
- L164: `opera.exe`
- L174: `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe`
- L175: `SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command`
- L176: `SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command`
- L177: `SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command`
- L200: `SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\`
- L200: `.exe`
- L201: `SOFTWARE\Clients\StartMenuInternet\`
- L201: `\shell\open\command`
- L222: `firefox.exe`
- L223: `opera.exe`
- L225: `brave.exe`
- L226: `vivaldi.exe`
- L291: `Google Chrome.app`
- L292: `Microsoft Edge.app`
- L293: `Firefox.app`
- L294: `Opera.app`
- L294: `Opera GX.app`
- L295: `Brave Browser.app`
- L296: `Vivaldi.app`
- L318: `Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice`

### `actions/code_helper.py`

- L15: `api_keys.json`
- L39: `^\`\`\`[a-zA-Z]*\n?`
- L40: `\n?\`\`\`$`
- L51: `bash`
- L51: `powershell`
- L52: `.json`
- L211: `bash`
- L212: `powershell`
- L505: `\`\`\`[a-zA-Z]*\n(.*?)\`\`\``

### `actions/computer_control.py`

- L40: `api_keys.json`
- L41: `long_term.json`
- L324: `osascript`
- L419: `(\d+)\s*,\s*(\d+)`

### `actions/computer_settings.py`

- L38: `api_keys.json`
- L62: `osascript`
- L73: `osascript`
- L84: `osascript`
- L109: `osascript`
- L119: `osascript`
- L137: `powershell`
- L148: `osascript`
- L166: `powershell`
- L193: `osascript`
- L392: `displaysleepnow`
- L432: `[Settings] sleep_display failed: `
- L434: `displaysleepnow`
- L444: `osascript`
- L451: `SOFTWARE\Microsoft\Windows\CurrentVersion\Themes\Personalize`
- L462: `gsettings`
- L462: `org.gnome.desktop.interface`
- L468: `gsettings`
- L468: `org.gnome.desktop.interface`
- L487: `powershell`
- L505: `shutdown`
- L507: `osascript`
- L511: `systemctl`
- L515: `shutdown`
- L517: `osascript`
- L521: `systemctl`
- L531: `sleep_display`
- L582: `shutdown`
- L585: `shutdown`
- L663: `shutdown`

### `actions/desktop.py`

- L27: `api_keys.json`
- L33: `XDG_DESKTOP_DIR`
- L71: `winreg`
- L71: `winreg`
- L75: `HKEY_CURRENT_USER`
- L113: `- ctypes (Windows API calls, read-only) ↵ - winreg (registry READ only)`
- L180: `osascript`
- L184: `XDG_CURRENT_DESKTOP`
- L189: `gsettings`
- L189: `org.gnome.desktop.background`
- L193: `gsettings`
- L193: `org.gnome.desktop.background`
- L259: `Control Panel\Desktop`
- L270: `osascript`
- L276: `XDG_CURRENT_DESKTOP`
- L279: `gsettings`
- L279: `org.gnome.desktop.background`
- L295: `.json`
- L297: `.exe`
- L301: `.lnk`
- L303: `.desktop`

### `actions/dev_agent.py`

- L17: `api_keys.json`
- L41: `^\`\`\`[a-zA-Z]*\r?\n?`
- L42: `\r?\n?\`\`\`\s*$`
- L53: `File ["\']([^"\']+\.py)["\'],\s+line\s+(\d+)`
- L276: `C:\Users\`
- L276: `\AppData\Local\Programs\Microsoft VS Code\bin\code.cmd`
- L277: `C:\Program Files\Microsoft VS Code\bin\code.cmd`
- L330: `No module named ['\"]([a-zA-Z0-9_\-\.]+)['\"]`
- L465: `[^\w\-]`

### `actions/file_controller.py`

- L32: `XDG_DESKTOP_DIR`
- L39: `XDG_DOWNLOAD_DIR`
- L46: `XDG_DOCUMENTS_DIR`
- L53: `XDG_PICTURES_DIR`
- L60: `XDG_MUSIC_DIR`
- L67: `XDG_VIDEOS_DIR`
- L93: `\`
- L201: `\`
- L503: `.json`

### `actions/file_processor.py`

- L29: `api_keys.json`
- L52: `bash`
- L367: `.json`
- L425: `.json`
- L505: `\`\`\`(?:\w+)?\n(.*?)\`\`\``

### `actions/flight_finder.py`

- L18: `api_keys.json`
- L47: `\d{4}-\d{2}-\d{2}`
- L76: `\d{4}-\d{2}-\d{2}`
- L83: `\d{1,2}`
- L226: `[^\d]`
- L290: `notepad.exe`

### `actions/game_updater.py`

- L72: `SOFTWARE\WOW6432Node\Valve\Steam`
- L73: `SOFTWARE\Valve\Steam`
- L74: `SOFTWARE\Valve\Steam`
- L81: `steam.exe`
- L88: `ProgramFiles(x86)`
- L89: `ProgramFiles`
- L92: `steam.exe`
- L100: `/Applications/Steam.app/Contents/MacOS`
- L112: `/usr/share/steam`
- L121: `steam.exe`
- L122: `/Applications/Steam.app/Contents/MacOS/steam_osx`
- L141: `"path"\s+"([^"]+)"`
- L142: `\\`
- L156: `"appid"\s+"(\d+)"`
- L157: `"name"\s+"([^"]+)"`
- L158: `"StateFlags"\s+"(\d+)"`
- L159: `"SizeOnDisk"\s+"(\d+)"`
- L176: `IMAGENAME eq steam.exe`
- L178: `steam.exe`
- L283: `:\`
- L630: `shutdown`
- L632: `osascript`
- L634: `systemctl`
- L663: `Download taking too long. Cancelling auto-shutdown.`
- L676: `SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher`
- L677: `SOFTWARE\EpicGames\EpicGamesLauncher`
- L678: `SOFTWARE\EpicGames\EpicGamesLauncher`
- L682: `AppDataPath`
- L684: `EpicGamesLauncher.exe`
- L692: `EpicGamesLauncher.exe`
- L692: `ProgramFiles(x86)`
- L693: `EpicGamesLauncher.exe`
- L693: `ProgramFiles`
- L694: `EpicGamesLauncher.exe`
- L694: `LOCALAPPDATA`
- L702: `/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher`
- L707: `/usr/bin/heroic`
- L733: `DisplayName`
- L745: `IMAGENAME eq EpicGamesLauncher.exe`
- L748: `epicgameslauncher.exe`
- L980: `shutdown_when_done`
- L1046: ` Auto-shutdown enabled.`
- L1066: `Auto-shutdown enabled.`

### `actions/open_app.py`

- L42: `cmd.exe`
- L42: `bash`
- L43: `powershell`
- L43: `powershell.exe`
- L43: `bash`
- L54: `devenv.exe`
- L60: `git-bash`
- L60: `bash`
- L67: `notepad.exe`
- L68: `notepad.exe`
- L69: `explorer.exe`
- L70: `explorer.exe`
- L71: `explorer.exe`
- L72: `taskmgr.exe`
- L74: `calc.exe`
- L75: `mspaint.exe`
- L156: `.app`
- L291: `\s+`
- L311: `APPDATA`
- L328: `.lnk`
- L339: `Find .app bundles in common macOS application directories.`
- L341: `/System/Applications`
- L347: `.app`
- L349: `.app`
- L358: `/usr/share/applications`
- L359: `/usr/local/share/applications`
- L378: `NoDisplay`
- L391: `.desktop`
- L400: `NoDisplay`
- L411: `Resolve a display name to an installed desktop-launcher ID.`
- L421: `.desktop`
- L425: `NoDisplay`
- L504: `osascript`

### `actions/pushup_counter.py`

- L1: ` ↵ EDITH plugin — Pushup Counter (webcam vision). ↵  ↵ Say "EDITH, count my pushups" (any language) — the HUD switches to the ↵ live camera, a 5-second countdown lets you get into position, then EDITH ↵ counts your reps live on screen and finally delivers the result with ↵ playful, teasing motivational commentary in your language. ↵  ↵ Detection (two-tier): ↵   • If \`mediapipe\` is installed (pip install mediapipe): elbow-angle ↵     tracking — accurate from front or side view. ↵   • Otherwise: face-motion tracking with OpenCV only (zero extra ↵     dependencies) — place the camera on the floor in front of you so your ↵     head moves toward/away from it with each rep. ↵  ↵ Session ends automatically: target reached, ~20 s without a rep, or the ↵ 3-minute safety cap. Just stand up when you're done. ↵  ↵ Sessions are saved to memory/long_term.json ("pushup_sessions") so future ↵ versions can track progress over time. ↵ `
- L77: `api_keys.json`
- L231: `long_term.json`

### `actions/reminder.py`

- L38: `\`
- L88: ` ↵ notified = False ↵  ↵ try: ↵     from plyer import notification ↵     notification.notify(title="EDITH Reminder", message=message, timeout=15) ↵     notified = True ↵ except Exception: ↵     pass ↵  ↵ if not notified: ↵     try: ↵         import subprocess ↵         script = 'display notification "{}" with title "EDITH Reminder"'.format( ↵             message.replace('"', '') ↵         ) ↵         subprocess.run(["osascript", "-e", script], check=False) ↵     except Exception: ↵         pass ↵ `
- L149: `pythonw.exe`
- L227: `</integer> ↵   </dict> ↵   <key>RunAtLoad</key>         <false/> ↵   <key>StandardOutPath</key>   <string>/dev/null</string> ↵   <key>StandardErrorPath</key> <string>/dev/null</string> ↵ </dict> ↵ </plist> ↵ `

### `actions/screen_processor.py`

- L46: `api_keys.json`
- L343: `\s+`

### `actions/send_message.py`

- L29: `api_keys.json`
- L87: `.app`

### `actions/system_monitor.py`

- L39: `C:\Windows\System32\nvml.dll`

### `actions/upload_video.py`

- L93: `api_keys.json`

### `actions/web_search.py`

- L73: `api_keys.json`
- L202: ` ↵     Fetches current headlines via Gemini grounded search. ↵     Optimised for speed: minimal prompt + strict token cap. ↵     Returns (headline_list, raw_text_for_display). ↵     `
- L228: `^[\d]+[.\)\-]`
- L230: `^[\d]+[.\)\-]\s*`
- L231: `^\*+\s*`

### `actions/youtube_video.py`

- L46: `api_keys.json`
- L110: `(?:v=\|\/v\/\|youtu\.be\/\|\/embed\/\|\/shorts\/)([A-Za-z0-9_-]{11})`
- L116: `(youtube\.com\|youtu\.be)`
- L215: `notepad.exe`
- L236: `"title":\{"runs":\[\{"text":"([^"]+)"`
- L238: `"viewCount":"(\d+)"`
- L239: `"lengthSeconds":"(\d+)"`
- L267: `"title":\{"runs":\[\{"text":"([^"]+)"\}\]`
- L268: `"ownerText":\{"runs":\[\{"text":"([^"]+)"`

### `config/__init__.py`

- L5: `api_keys.json`

### `core/action_activity.py`

- L14: `[\x00-\x1f\x7f]+`
- L15: `\s+`
- L38: `\`

### `core/action_guard.py`

- L14: `\brm\s+-(?:[a-z]*r[a-z]*f\|[a-z]*f[a-z]*r)\b`
- L15: `\b(?:del\|erase)\b[^\r\n]{0,100}/(?:f\|q\|s)\b`
- L16: `\b(?:rmdir\|rd)\s+/s\b`
- L17: `PowerShell recursive deletion`
- L17: `\bremove-item\b[^\r\n]{0,160}(?:-recurse\|-force)`
- L18: `\b(?:format\s+[a-z]:\|diskpart\b\|clean\s+all\b\|wipefs\b)`
- L19: `system shutdown or restart`
- L19: `\b(?:shutdown(?:\.exe)?\|restart-computer\|stop-computer)\b`
- L20: `\b(?:taskkill\b[^\r\n]{0,100}/f\b\|kill\s+-9\b\|stop-process\b[^\r\n]{0,100}-force\b)`
- L21: `\b(?:docker\|podman)\s+(?:rm\|rmi\|volume\s+rm\|system\s+prune)\b`
- L22: `\bkubectl\s+delete\b\|\bterraform\s+destroy\b`
- L23: `\b(?:delete\s+from\|drop\s+(?:database\|table\|collection\|schema)\|truncate\s+(?:table\|collection))\b\|\bdb\.[\w$]+\.(?:deleteMany\|drop\|remove)\s*\(\|\bdb\.(?:dropDatabase\|dropCollection)\s*\(`
- L24: `\b(?:winget\s+uninstall\|choco\s+uninstall\|brew\s+uninstall\|adb\s+uninstall\|apt(?:-get)?\s+(?:remove\|purge))\b`
- L25: `\bgit\s+(?:push\b[^\r\n]{0,100}--force\|clean\b[^\r\n]{0,50}-[a-z]*f)`
- L26: `\b(?:npm\|pnpm\|yarn)\s+publish\b`
- L30: `\b(delete\|delete permanently\|permanently delete\|remove\|uninstall\|terminate\|kill\|drop database\|drop table\|truncate\|format\|factory reset\|wipe\|erase\|revoke access\|delete account\|close account\|send\|submit\|publish\|deploy)\b`
- L38: `[\x00-\x1f\x7f]+`
- L39: `\s+`
- L50: `/\`
- L51: `/\`
- L68: `^\s*(?:please\s+)?(?:close\|terminate\|kill\|quit\|exit\|stop)\s+(?:(?:the\|my)\s+)?`
- L74: `\s+(?:app\|application\|window\|program\|process)$`
- L98: `\b(shut\s*down\|power\s*off\|turn\s*off\s+(?:the\s+)?computer)\b`
- L99: `shutdown`
- L100: `\b(restart\|reboot)\b`
- L102: `\b(close\|terminate\|kill\|quit\|exit)\b`
- L116: `shutdown`
- L119: `shutdown`

### `core/agent_reliability.py`

- L54: `shutdown_edith`

### `core/audio_meter.py`

- L1: `Tiny, dependency-free UI input meter for 16-bit little-endian PCM. ↵  ↵ This is a display-only intensity estimate, not speech recognition or proof ↵ that a cloud provider received audio. It never stores or logs audio. ↵ `

### `core/hardware_check.py`

- L60: `WAYLAND_DISPLAY`
- L61: `Linux Wayland (some global desktop-control operations are restricted)`
- L62: `DISPLAY`
- L64: `Linux: no active graphical display detected`

### `core/llm_client.py`

- L1: ` ↵ Local LLM client for EDITH. ↵  ↵ Supports two backends — selected via  "llm_provider"  in config/api_keys.json: ↵  ↵   "llm_provider": "ollama"   (default) ↵         Uses Ollama's native /api/chat endpoint. ↵         Download: https://ollama.com ↵         Default port: 11434 ↵  ↵   "llm_provider": "openai" ↵         Uses any OpenAI-compatible server: LM Studio, Jan, LocalAI, ↵         llama.cpp server, vLLM, etc. ↵         LM Studio download: https://lmstudio.ai   (default port: 1234) ↵         Set  "llm_url": "http://localhost:1234"  in config. ↵         Note: tool-calling support depends on the model; use a model that ↵         supports function/tool calls (e.g. Qwen2.5, Llama-3.1, Mistral). ↵ `
- L31: `(?<=[.!?])\s+\|(?<=\n)\s*\n`
- L40: `api_keys.json`

### `core/startup_check.py`

- L57: `pythonw.exe`

### `core/task_view.py`

- L35: `[\x00-\x1f\x7f]+`
- L36: `\s+`

### `core/ui_design.py`

- L59: `^[◉◈▸⊞✕✓●○\s]+`

### `dashboard/server.py`

- L53: `api_keys.json`
- L89: `Cross-platform, best-effort: open port in the OS firewall for LAN access. ↵  ↵     Runs in a background thread — never blocks uvicorn startup. ↵  ↵     Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW ↵               (native UAC dialog, guaranteed to appear). One-time setup. ↵     macOS   : osascript admin dialog if the Application Firewall is on. ↵     Linux   : pkexec GUI → sudo -n → prints manual command as fallback. ↵     `
- L121: `powershell`
- L142: `powershell -NoProfile -NonInteractive -Command "Get-NetConnectionProfile \| Where-Object {$_.NetworkCategory -eq 'Public'} \| Set-NetConnectionProfile -NetworkCategory Private"`
- L225: `/usr/libexec/ApplicationFirewall/socketfilterfw`
- L242: `osascript`
- L253: `sudo`
- L268: `[Dashboard] Run manually:  sudo ufw allow `
- L283: `[Dashboard] Run manually:  sudo firewall-cmd --add-port=`
- L283: `/tcp --permanent && sudo firewall-cmd --reload`
- L294: `[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp --dport `
- L621: `<!DOCTYPE html> ↵ <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"> ↵ <style> ↵   body{background:#07090f;color:#dde3ed;font-family:sans-serif; ↵        display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center} ↵   h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px} ↵ </style></head> ↵ <body><div><h2>Link Expired</h2> ↵ <p>Press <strong style="color:#dde3ed">Remote Control</strong> in EDITH to get a new QR code.</p> ↵ </div></body></html>`
- L646: `<!DOCTYPE html> ↵ <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width"> ↵ <style> ↵   body{background:#07090f;color:#dde3ed;font-family:sans-serif; ↵        display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center} ↵   p{color:#5e6a7e;font-size:14px} ↵ </style></head> ↵ <body> ↵ <script> ↵   sessionStorage.setItem('jarvis_token','`
- L779: `[<>:"/\\\|?*\x00-\x1f]`
- L857: `[/\\]`

### `main.py`

- L99: `api_keys.json`
- L123: `.json.tmp`
- L139: `<ctrl\d+>`
- L143: `[\x00-\x08\x0b-\x1f]`
- L305: `'screen' to capture display, 'camera' for webcam. Default: 'screen'`
- L324: `Controls the computer: volume, brightness, window management, keyboard shortcuts, typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. Use for ANY single computer control command.`
- L479: `shutdown_when_done`
- L536: `shutdown_edith`
- L1028: `[IDENTITY] ↵ You are a professional, general-purpose AI assistant operating on the user's own device. ↵ Your display name is `
- L1157: `shutdown`
- L1257: `shutdown`
- L1261: `shutdown`
- L1262: `shutdown`
- L1422: `shutdown_edith`
- L1423: `SYS: Shutdown requested.`
- L1834: ` ↵  ↵ Pick ONE headline, summarise it in one sentence, then say the full list is displayed on screen. Do not call any tools.`
- L1861: `Summarise the current session in 1-2 sentences and save to long_term.json.`

### `memory/config_manager.py`

- L12: `api_keys.json`
- L79: `❌ Failed to load api_keys.json: `

### `memory/memory_manager.py`

- L15: `long_term.json`
- L224: `Append a 1-2 sentence session summary to long_term.json['sessions'].`

### `tests/test_action_guard.py`

- L27: `shutdown`
- L74: `rm -rf /tmp/build`

### `tests/test_audio_hardware_fallback.py`

- L21: `Wayland`
- L21: `WAYLAND_DISPLAY`
- L21: `wayland-0`
- L22: `DISPLAY`
- L23: `no active graphical display`

### `tests/test_enterprise_ui.py`

- L25: `api_keys.json`

### `tests/test_file_controller.py`

- L32: `nested\\child`

### `tests/test_phase1_setup.py`

- L136: `desktop / "EDITH.lnk"`
- L136: `desktop / "EDITH.app"`
- L137: `desktop / "edith.desktop"`
- L137: `desk_dir / "edith.desktop"`
- L138: `winreg.SetValueEx( ↵                             reg, "EDITH"`
- L143: `desktop / "AI Assistant.lnk"`
- L144: `desktop / "AI Assistant.app"`
- L145: `desk = desktop / "ai-assistant.desktop"`
- L146: `winreg.SetValueEx(reg, "JARVIS_AI"`
- L162: `api_keys.json`
- L189: `api_keys.json`
- L204: `api_keys.json`
- L214: `api_keys.json`

### `tests/test_phase4_qt.py`

- L28: `api_keys.json`

### `tests/test_phase6_reliability.py`

- L145: `never-display`
- L148: `never-display`

### `tests/test_task_scheduler.py`

- L224: `shutdown`

### `tests/test_voice_input_ui.py`

- L1: `Regression coverage for EDITH's real-input, display-only HUD feedback.`

### `tools/phase2_benchmark.py`

- L1: `Measure the configured local model's actual response latency. ↵  ↵ Usage (from project root): ↵     python tools/phase2_benchmark.py --iterations 3 ↵  ↵ This tool uses existing config/api_keys.json provider/model settings only. ↵ It neither displays nor modifies API keys, local configuration, or messages. ↵ Cloud Gemini Live latency is measured via Settings > TEST KEY and the Live ↵ session's PERF entries in EDITH's Activity Log. ↵ `

### `ui.py`

- L48: `api_keys.json`
- L55: `Read api_keys.json config dict. Returns {} on any error.`
- L182: `Return the fixed product display name without exposing old/custom branding.`
- L207: `C:\Windows\System32\nvml.dll`
- L654: `Display new log entries promptly, without the typewriter effect.`
- L810: `All Files (*.*);;Images (*.jpg *.jpeg *.png *.gif *.webp *.bmp *.svg);;Documents (*.pdf *.docx *.txt *.md *.pptx);;Data (*.csv *.xlsx *.json *.xml);;Code (*.py *.js *.ts *.html *.css *.java *.cpp *.go);;Audio (*.mp3 *.wav *.ogg *.m4a *.aac *.flac);;Video (*.mp4 *.avi *.mov *.mkv *.wmv *.webm);;Archives (*.zip *.rar *.tar *.gz *.7z)`
- L1094: `Uses the existing llm_provider / llm_url / llm_model settings from config/api_keys.json. Server reachability and a real model response are checked separately.`
- L1221: `llm_url or llm_model is missing from config/api_keys.json.`
- L1523: `.json.tmp`
- L2619: `Slot — display camera preview overlay (main thread).`
- L2663: `api_keys.json`
- L2704: ` ↵         Create a Windows .lnk shortcut WITHOUT launching PowerShell or cmd. ↵         Tries win32com (pywin32) first; falls back to wscript.exe + VBScript. ↵         wscript.exe is a GUI-mode host — it never opens a console window. ↵         `
- L2742: `wscript.exe`
- L2798: `Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders`
- L2821: `XDG_DESKTOP_DIR`
- L2848: `*.lnk`
- L2863: `ai-assistant.desktop`
- L2863: `jarvis.desktop`
- L2874: ` ↵         Create a desktop shortcut on Windows / macOS / Linux. ↵         Never opens a terminal, console, or PowerShell window on any platform. ↵         `
- L2894: `pythonw.exe`
- L2896: `EDITH.lnk`
- L2903: `EDITH.app`
- L2913: `#!/usr/bin/env bash ↵ cd "`
- L2967: `edith.desktop`
- L4034: `Software\Microsoft\Windows\CurrentVersion\Run`
- L4057: `local.aiassistant.desktop`
- L4063: `jarvis.desktop`
- L4064: `edith.desktop`
- L4085: `Software\Microsoft\Windows\CurrentVersion\Run`
- L4093: `edith.desktop`
- L4105: `Software\Microsoft\Windows\CurrentVersion\Run`
- L4111: `pythonw.exe`
- L4141: `edith.desktop`
- L4501: `EDITH.PersonalAssistant.Desktop`
- L4592: `Display captured input intensity; safe to call from audio threads.`
- L4612: `Thread-safe: display content in the panel below the HUD.`

## Current working / partial / broken or missing

| Area | Baseline status | Evidence/limit |
| --- | --- | --- |
| Classic desktop actions/status/file controls | Working under headless regressions | 188 tests; real clicks/OS integrations need target device |
| Narration FIFO / interruption / hardware recovery | Implemented, live verification pending | Synthetic PCM, device fakes; no live provider result claimed |
| Gemini Live / Ollama internal agent | Implemented, external verification pending | Real credentials/network required |
| Browser/app/desktop control | Partial by OS/display | Optional browser binaries, signed-in sessions, X11/macOS Accessibility; Wayland limitations |
| Telemetry | Partial | Basic metrics; duplicated collectors, optional GPU/temp, some Qt-slot reads |
| Four permission tiers | Missing | Existing selective confirmations do not cover arbitrary shell/settings |
| Complete kill switch | Missing | Narration only; executor tasks and subprocess tree not stopped |
| Per-action redacted audit log | Missing | Activity strings and metadata journal exist; no comprehensive argument/result log |
| Keychain | Missing | Plaintext JSON credentials across readers |
| System/light/live theme | Missing | Dark Qt palette and accent overrides only |
| Three.js + GSAP + Tailwind | Missing | Requires embedded browser migration; current desktop is Qt widgets |
| 1366×697 screenshot equivalence | Baseline captured | Above rectangles; no current user screenshot supplied |
| Physical three-OS / near-60fps certification | Not verified | Headless/mock tests cannot establish these |

No hardware operation, install, file deletion, power change or outbound message was
executed as part of this audit. Read-only test sampling and offscreen rendering only.
