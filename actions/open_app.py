import time
import os
import subprocess
import platform
import re
import shlex
import shutil
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "docker":              {"Windows": "Docker Desktop",      "Darwin": "Docker",             "Linux": "docker-desktop"},
    "docker desktop":      {"Windows": "Docker Desktop",      "Darwin": "Docker",             "Linux": "docker-desktop"},
    "android studio":      {"Windows": "Android Studio",      "Darwin": "Android Studio",     "Linux": "android-studio"},
    "mongodb compass":     {"Windows": "MongoDB Compass",     "Darwin": "MongoDB Compass",    "Linux": "mongodb-compass"},
    "mongo db compass":    {"Windows": "MongoDB Compass",     "Darwin": "MongoDB Compass",    "Linux": "mongodb-compass"},
    "mongodb":             {"Windows": "MongoDB Compass",     "Darwin": "MongoDB Compass",    "Linux": "mongodb-compass"},
    "mongosh":             {"Windows": "mongosh",             "Darwin": "mongosh",            "Linux": "mongosh"},
    "intellij idea":       {"Windows": "IntelliJ IDEA",       "Darwin": "IntelliJ IDEA",      "Linux": "idea"},
    "pycharm":             {"Windows": "PyCharm",             "Darwin": "PyCharm",            "Linux": "pycharm"},
    "visual studio":       {"Windows": "devenv.exe",          "Darwin": "Visual Studio",      "Linux": "visual-studio"},
    "dbeaver":             {"Windows": "DBeaver",             "Darwin": "DBeaver",            "Linux": "dbeaver"},
    "pgadmin":             {"Windows": "pgAdmin 4",           "Darwin": "pgAdmin 4",          "Linux": "pgadmin4"},
    "redisinsight":        {"Windows": "RedisInsight",        "Darwin": "RedisInsight",       "Linux": "redisinsight"},
    "github desktop":      {"Windows": "GitHub Desktop",      "Darwin": "GitHub Desktop",     "Linux": "github-desktop"},
    "jetbrains toolbox":   {"Windows": "JetBrains Toolbox",   "Darwin": "JetBrains Toolbox",  "Linux": "jetbrains-toolbox"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

def _launch_windows(app_name: str) -> bool | None:

    executable = shutil.which(app_name) or shutil.which(app_name.split(".")[0])
    if executable:
        try:
            subprocess.Popen(
                [executable],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {type(e).__name__}")

    # Open OS URI handlers without passing model/user text through a shell.
    if ":" in app_name:
        try:
            os.startfile(app_name)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        # Keyboard search requested the launch, but does not prove the app opened.
        return None
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool | None:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        # Spotlight search is visible, but launching cannot be verified here.
        return None
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str) -> bool | None:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    desktop_id = _find_linux_desktop_id(app_name)
    gtk_launch = shutil.which("gtk-launch")
    if desktop_id and gtk_launch:
        try:
            subprocess.Popen(
                [gtk_launch, desktop_id],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.0)
            return True
        except Exception as exc:
            print(f"[open_app] Desktop-entry launch failed: {type(exc).__name__}")

    try:
        launch_parts = shlex.split(app_name)
    except ValueError:
        launch_parts = []
    binary = (
        shutil.which(launch_parts[0]) or
        shutil.which(launch_parts[0].lower()) or
        shutil.which(launch_parts[0].lower().replace(" ", "-")) or
        shutil.which(launch_parts[0].lower().replace(" ", "_"))
    ) if launch_parts else None
    if binary:
        try:
            subprocess.Popen(
                [binary, *launch_parts[1:]],
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception as exc:
            print(f"[open_app] Linux launch failed: {type(exc).__name__}")

    try:
        result = subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


def _search_key(value: object) -> str:
    """Normalize an application label for language-tolerant name matching."""
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def filter_app_names(app_names, query: str = "", limit: int = 30) -> list[str]:
    """Deduplicate, filter, and cap discovered app labels in a deterministic way."""
    try:
        cap = max(1, min(int(limit), 3000))
    except (TypeError, ValueError):
        cap = 30
    unique = {}
    for item in app_names or ():
        name = re.sub(r"\s+", " ", str(item or "")).strip()
        if not name:
            continue
        key = name.casefold()
        if key not in unique or name < unique[key]:
            unique[key] = name
    names = sorted(unique.values(), key=lambda item: (item.casefold(), item))
    query_key = _search_key(query)
    if query_key:
        tokens = query_key.split()
        names = [
            name for name in names
            if query_key in _search_key(name)
            or all(token in _search_key(name) for token in tokens)
        ]
    return names[:cap]


def _windows_start_menu_roots() -> list[Path]:
    roots = []
    appdata = os.environ.get("APPDATA")
    programdata = os.environ.get("PROGRAMDATA")
    if appdata:
        roots.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    if programdata:
        roots.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
    return roots


def _start_menu_app_names() -> list[str]:
    """Read Windows Start Menu shortcuts without executing them."""
    names = []
    for root in _windows_start_menu_roots():
        if not root.is_dir():
            continue
        for current, _directories, files in os.walk(root):
            for filename in files:
                if Path(filename).suffix.casefold() not in {".lnk", ".url"}:
                    continue
                label = Path(filename).stem.strip()
                if label and not label.casefold().startswith(("uninstall ", "readme ")):
                    names.append(label)
                if len(names) >= 3000:
                    return names
    return names


def _mac_application_names() -> list[str]:
    """Find .app bundles in common macOS application directories."""
    home = Path.home()
    roots = [Path("/Applications"), Path("/System/Applications"), home / "Applications"]
    names = []
    for root in roots:
        if not root.is_dir():
            continue
        for current, directories, _files in os.walk(root):
            bundles = [d for d in directories if d.casefold().endswith(".app")]
            names.extend(Path(d).stem for d in bundles)
            directories[:] = [d for d in directories if not d.casefold().endswith(".app")]
            if len(names) >= 3000:
                return names
    return names


def _linux_application_roots() -> list[Path]:
    home = Path.home()
    return [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        home / ".local" / "share" / "applications",
        Path("/var/lib/flatpak/exports/share/applications"),
        home / ".local" / "share" / "flatpak" / "exports" / "share" / "applications",
        Path("/var/lib/snapd/desktop/applications"),
    ]


def _read_desktop_entry(path: Path) -> dict[str, str]:
    """Read launcher metadata only; never execute its Exec= command."""
    fields = {}
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return fields
    for line in content.splitlines():
        if "=" not in line or line.startswith(("#", "[")):
            continue
        key, _, value = line.partition("=")
        if key in {"Name", "Hidden", "NoDisplay", "Exec", "TryExec"}:
            fields[key] = value.strip()
    return fields


def _linux_desktop_app_names() -> list[str]:
    names = []
    seen_files = set()
    for root in _linux_application_roots():
        if not root.is_dir():
            continue
        for current, _directories, files in os.walk(root):
            for filename in files:
                if not filename.casefold().endswith(".desktop"):
                    continue
                entry = Path(current) / filename
                if entry in seen_files:
                    continue
                seen_files.add(entry)
                fields = _read_desktop_entry(entry)
                if fields.get("Hidden", "").casefold() == "true":
                    continue
                if fields.get("NoDisplay", "").casefold() == "true":
                    continue
                label = fields.get("Name", "").strip()
                if label:
                    names.append(label)
                if len(names) >= 3000:
                    return names
    return names


def _find_linux_desktop_id(app_name: str) -> str:
    """Resolve a display name to an installed desktop-launcher ID."""
    target = _search_key(app_name)
    if not target:
        return ""
    partial_match = ""
    for root in _linux_application_roots():
        if not root.is_dir():
            continue
        for current, _directories, files in os.walk(root):
            for filename in files:
                if not filename.casefold().endswith(".desktop"):
                    continue
                entry = Path(current) / filename
                fields = _read_desktop_entry(entry)
                if fields.get("Hidden", "").casefold() == "true" or fields.get("NoDisplay", "").casefold() == "true":
                    continue
                label_key = _search_key(fields.get("Name") or entry.stem)
                if label_key == target:
                    return entry.stem
                if target in label_key or label_key in target:
                    if not partial_match:
                        partial_match = entry.stem
    return partial_match


def discover_installed_apps() -> list[str]:
    """Discover app labels from OS launchers, desktop entries, and known PATH executables."""
    candidates = []
    try:
        if _SYSTEM == "Windows":
            candidates = _start_menu_app_names()
        elif _SYSTEM == "Darwin":
            candidates = _mac_application_names()
        elif _SYSTEM == "Linux":
            candidates = _linux_desktop_app_names()
    except Exception as exc:
        print(f"[open_app] App discovery warning: {type(exc).__name__}")

    # Supplement OS launcher metadata with known aliases whose executable exists on PATH.
    for alias, os_map in _APP_ALIASES.items():
        target = os_map.get(_SYSTEM, "")
        try:
            parts = shlex.split(target) if target else []
            if parts and shutil.which(parts[0]):
                candidates.append(alias.title())
        except (ValueError, OSError):
            continue
    return filter_app_names(candidates, limit=3000)


def list_installed_apps(query: str = "", limit: int = 30) -> str:
    """Format a discovered-app inventory or filtered search."""
    apps = discover_installed_apps()
    matching = filter_app_names(apps, query=query, limit=3000)
    try:
        display_limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        display_limit = 30
    shown = matching[:display_limit]
    if not shown:
        if query.strip():
            return (
                f"No desktop-app launcher entries matched '{query.strip()[:80]}'. "
                "The app may still be installed without a standard launcher; try its exact name."
            )
        return (
            "No standard desktop-app launcher entries were found. "
            "This does not prove that no applications are installed."
        )
    title = f"Installed desktop apps matching '{query.strip()[:60]}'" if query.strip() else "Installed desktop apps"
    lines = [f"{title} — showing {len(shown)} of {len(matching)} match(es):"]
    lines.extend(f"• {name}" for name in shown)
    if len(matching) > len(shown):
        lines.append("Use action='search' with a query to narrow the list.")
    lines.append("Discovery reads OS launcher metadata only; it does not open apps or execute desktop-entry commands.")
    return "\n".join(lines)


def _active_window_description() -> str:
    """Get a best-effort foreground application/window label via read-only OS APIs."""
    try:
        if _SYSTEM == "Windows":
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return ""
            length = user32.GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(max(1, length + 1))
            user32.GetWindowTextW(hwnd, buffer, len(buffer))
            return buffer.value.strip()
        if _SYSTEM == "Darwin":
            result = subprocess.run(
                ["osascript", "-e", 'tell application "System Events" to get name of first application process whose frontmost is true'],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
        if _SYSTEM == "Linux" and shutil.which("xdotool"):
            result = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True, text=True, timeout=2,
            )
            return result.stdout.strip() if result.returncode == 0 else ""
    except Exception as exc:
        print(f"[open_app] Foreground verification unavailable: {type(exc).__name__}")
    return ""


def _foreground_matches(requested_name: str, normalized_name: str, foreground: str) -> bool:
    """Return true only if the foreground label contains a requested app/alias."""
    title_key = _search_key(foreground)
    if not title_key:
        return False
    candidates = [requested_name, normalized_name]
    normalized_target = _search_key(normalized_name)
    for alias, mapping in _APP_ALIASES.items():
        if _search_key(mapping.get(_SYSTEM, alias)) == normalized_target:
            candidates.append(alias)
    for candidate in candidates:
        key = _search_key(candidate)
        # Only accept a candidate phrase contained in the title; allowing the reverse
        # substring would falsely verify an app from a one-letter/short window title.
        if key and key in title_key:
            return True
    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = parameters or {}
    action = str(params.get("action") or "open").strip().lower()
    query = str(params.get("query") or "").strip()
    app_name = str(params.get("app_name") or "").strip()

    if action in {"list", "list_installed", "discover", "search", "find"}:
        effective_query = query or (app_name if action in {"search", "find"} else "")
        try:
            result = list_installed_apps(query=effective_query, limit=params.get("limit", 30))
        except Exception as exc:
            result = f"Installed-app discovery failed: {type(exc).__name__}"
        if player:
            label = "Search" if effective_query else "List"
            player.write_log(
                f"[Apps] {label} installed app launchers"
                + (f" matching {_search_key(effective_query)[:50]}" if effective_query else "")
            )
        return result

    if action not in {"open", "launch", "start"}:
        return "Unknown open_app action. Use open, list, or search."
    if not app_name:
        return "No application name provided. Use action='list' or action='search' to discover installed apps."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Launch request: '{app_name}' → '{normalized}' ({_SYSTEM})")
    if player:
        player.write_log(f"[Apps] Launch request: {_search_key(app_name)[:70]}")

    try:
        status = launcher(normalized)
        if status is False and normalized.casefold() != app_name.casefold():
            status = launcher(app_name)
        if status is False:
            return (
                f"Could not submit a launch request for {app_name}. "
                "It may not be installed or may not have a standard OS launcher."
            )

        # A launcher accepting a request does not prove its target is ready.
        time.sleep(0.35)
        foreground = _active_window_description()
        if _foreground_matches(app_name, normalized, foreground):
            return f"Opened {app_name}; foreground window verified: {foreground[:100]}."

        foreground_hint = (
            f" The current foreground window is '{foreground[:80]}'."
            if foreground else
            " The operating system did not provide a foreground-window title."
        )
        return (
            f"Launch request submitted for {app_name}, but the requested app is not confirmed "
            f"as the foreground window.{foreground_hint} Inspect the visible screen before further interaction."
        )
    except Exception as e:
        print(f"[open_app] Launch error: {type(e).__name__}")
        return f"Failed to submit launch request for {app_name}: {type(e).__name__}"
