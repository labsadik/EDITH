# EDITH — Neuron Intelligence desktop agent

EDITH is a cross-platform desktop AI assistant with real-time voice, a native desktop UI, local-device diagnostics, automation tools, persistent memory, provider settings, optional remote dashboard access, and a plugin/MCP system. Its product identity is **EDITH / Neuron Intelligence (NL)**, built by Sadik Laskar.

EDITH is designed to adapt to the computer on which it runs. It detects the running OS at startup and uses the appropriate Windows, macOS, Linux, or generic platform adapter. Unsupported hardware or OS functions return an explicit unavailable result instead of crashing or inventing a result.

## What it can do

- Real-time Gemini Live voice conversation with selected female/male voice presets.
- Text, microphone and paired remote-dashboard input.
- LIVE status feedback: Listening, Thinking, Working and Speaking; real input and output waveforms remain independent of the visual HUD video.
- Adaptive narration buffering: generated PCM remains ordered; if an output device underruns, EDITH expands its prebuffer rather than skipping or replaying words.
- Local diagnostics: CPU, per-core load, RAM/swap, disk/I/O, network interfaces, battery, uptime, process count, optional GPU/temperature, hardware inventory, displays and audio devices where the OS supports them.
- Local app discovery/launching, window/process inventory, file operations, browser and visible desktop workflows, bounded shell execution, coding helpers and activity/audit receipts.
- Task queue, busy-input gate, interruption with `ESC`, owned child-process cancellation, task history, safe bounded retries for declared read-only tools, and a fixed telemetry fallback.
- Persistent memory with atomic writes and recovery backup.
- One Powerful Brain text/reasoning profile: local Ollama, OpenAI-compatible servers, OpenAI, Anthropic, Groq and xAI/Grok. Gemini Live remains the voice/audio session, not a second text brain.
- Versioned local specialist agents for software development/DevOps, DevSecOps, Project Management, Device Security, Smart Network, research, browser/computer, files/workspace and system monitoring.
- Local Rust OS-enforced code sandbox (Windows AppContainer, Linux bubblewrap, macOS Seatbelt) with fail-closed generated-code execution.
- Optional phone/remote dashboard with pairing and reconnect handling.
- Simulator-first special-device contract. The built-in vehicle adapter is an in-memory simulator only; a real OEM integration must be separately installed, authorised and tested.

## Voice, keys and cross-app desktop control

The voice presets are **Kore** (female) and **Orus** (male). Configure the
Gemini key from Controls, then use **Test the key** to make a real minimal
provider request before relying on voice conversation. This test measures a
real response; it is not a promise of a fixed response time.

### Cross-app desktop control

EDITH can discover and open installed desktop apps, then inspect the visible
desktop before continuing a workflow. Examples:

- “List installed desktop apps.”
- “Find Android Studio.”
- “Open Postman and inspect the screen.”

A launch is only treated as verified when the foreground-window label matches
the intended application; otherwise EDITH reports it as unverified rather than
claiming that the app is ready.

## Device and OS behaviour

`edith.platform` selects a controller for Windows 10/11, macOS 13+, Ubuntu 22.04+ and compatible Linux distributions. It exposes structured results in the form `{ok, data, error, unsupported}` for telemetry, process/window lists, network information, application inventory, displays, audio devices and other platform capabilities.

Features differ by OS, installed dependencies, accessibility/screen-recording permission and available hardware. Missing sensors are shown as `N/A`; EDITH does not claim real network-speed tests, hardware control, remote-device access, or vehicle control when no supported, authorised adapter exists.

## Local agents and sandbox

The agent registry is versioned in `agents/manifest.json`; ask EDITH **"list agents and versions"** to inspect the exact active versions. Agent enable/disable state is saved locally in `config/agents.json`. The Project Manager stores local project/task metadata in `config/projects.json`.

Generated project code, code-file runs and generated desktop snippets are routed through the local Rust sandbox. If the OS cannot enforce the sandbox, execution stops; EDITH does not fall back to host execution. See [docs/LOCAL_AGENTS_AND_SANDBOX.md](docs/LOCAL_AGENTS_AND_SANDBOX.md) for the architecture, platform prerequisites, security boundaries and full PowerShell/macOS/Linux test commands.

Linux/macOS sandbox runs currently deny network access. Windows dependency installation uses the AppContainer InternetClient capability while ordinary generated project execution remains offline. Do not enable unrestricted egress as a workaround.

## MCP connectors

Open **Controls → Plugins**. MCP entries have an initial badge and a **CONNECT** button. The catalog includes Gmail, GitHub, Filesystem, Google Drive, Google Calendar, Notion, Slack and Linear profiles.

1. Click **CONNECT** beside a provider.
2. Click **OPEN SETUP** and complete that provider's OAuth/API setup.
3. Paste a trusted Streamable-HTTP MCP endpoint when the provider requires one.
4. Paste the provider-issued access token, then choose **SAVE & TEST**.
5. When the provider reports its tools, keep its toggle ON. EDITH then exposes that connector to the AI as an MCP plugin.

Tokens are stored in the OS keychain when available; they are not written to activity logs. A connector is not reported as connected until its test returns tools. Existing browser login cookies are not reused as MCP credentials.

The official Gmail MCP connector requires Google Cloud/OAuth setup. Its currently advertised tool set may allow draft/search operations but does not automatically mean it has a direct `send` operation. EDITH only uses the tools a connected server actually reports.

Only connect MCP endpoints you trust. Each connector has its own authentication, tool availability and provider rules; a catalog template is not a promise that a provider supplies a free public MCP endpoint.

## Repository note

The current maintained repository is `WorkRCS/EDITH_v1`. Older setup references may still mention `Upgrade_Autonomous.git`; use the current repository URL below for fresh clones.

## Run locally

```powershell
git clone https://github.com/WorkRCS/EDITH_v1.git
cd EDITH_v1
git switch main
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python main.py
```

On macOS/Linux, activate the environment with `source .venv/bin/activate`. Grant microphone permission for voice input. Screen recording/accessibility permission is needed only for the corresponding screen/desktop features. Native OS elevation dialogs may appear for OS actions that require them.

## Verification

Run the automated suite from the repository root:

```powershell
python -m unittest discover -s tests -q
node tests/check_workspace_js.js
```

The suite covers the platform adapters with mocks, task scheduling, interruption, audio buffering, MCP protocol/configuration, UI smoke behaviour and provider contracts. It does not certify your own microphone, speakers, provider account, OAuth credentials, third-party app layout, vehicle, or physical device. Test those on the target device before relying on them.

For implementation evidence and known target-device gates, see [docs/IMPLEMENTATION_PROGRESS.md](docs/IMPLEMENTATION_PROGRESS.md), [VERIFICATION.md](VERIFICATION.md), [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md), and [TESTING.md](TESTING.md).


## Installers and release metadata

EDITH's release version is maintained in `VERSION`. The Windows installer is built as
`EDITH-Setup-<version>-x64.exe` by the **Build EDITH installers** GitHub Actions workflow.
The installer publisher is **Sadik Laskar** and the product is **EDITH — Neuron Intelligence**.
It opens the proprietary license agreement before the remaining setup pages, then lets the
user choose the install directory and install scope (current user or all users). The
desktop shortcut is optional. The matching application version and publisher are written
to the executable and installer metadata.

The same workflow produces a macOS app package and a Linux x64 archive. Windows produces
the interactive Inno Setup EXE; macOS and Linux use their native application/package
formats rather than pretending the Windows EXE is portable.

Packaged builds keep credentials and preferences outside the installation folder:
- Windows: `%APPDATA%\\EDITH\\config\\api_keys.json`
- macOS: `~/Library/Application Support/EDITH/config/api_keys.json`
- Linux: `$XDG_CONFIG_HOME/edith/config/api_keys.json` (or `~/.config/edith/config/api_keys.json`)

An existing installation config is copied into the current user's data directory on first
launch without deleting or overwriting either copy. Source checkouts continue using the
repository `config/api_keys.json` for developer compatibility.

## Powerful Brain provider setup

Open **Controls → API Providers → Powerful Brain**. Select local Ollama or a cloud/API
provider (OpenAI, Anthropic, Groq, xAI) or an OpenAI-compatible local server. Enter the
endpoint/model and provider key where required, load the available model list, run the
real connection test, and only then save. Powerful Brain settings are stored separately
from Main/legacy settings and from Gemini Live voice credentials. The provider preflight
can make a real, minimal test request:

```powershell
python scripts/edith_preflight.py
python scripts/edith_preflight.py --test-powerful-brain
```

The selected Powerful Brain provider powers the text-reasoning/specialist-agent route.
The current real-time voice transport remains Google Gemini Live; a generic OpenAI API
key or Ollama endpoint does not itself provide the Live audio transport.

## Smart Network Wi-Fi scan and Home Assistant pairing

Open **Plugins → Agents → Smart Network**. Choose **PAIR HA** to enter the
Home Assistant base URL and a long-lived access token. EDITH first verifies
that `/api/config` responds successfully; credentials are not saved when
the URL or token is invalid. On success, the token is stored in the OS keychain
when available. **UPDATE HA** re-verifies and replaces the pairing.

Use the Smart Network action `wifi_scan` to enumerate nearby SSIDs, BSSIDs,
signal and channel information from the Wi-Fi adapters exposed by the OS.
Windows scans every visible WLAN interface (including supported USB dongles),
Linux uses NetworkManager's Wi-Fi rescan, and macOS uses the OS airport scan
utility where present. A dongle must have a working OS driver and its OS WLAN
service must be enabled. EDITH reports a specific unsupported/unavailable
reason instead of claiming a scan succeeded. Scanning only reads beacon
information; it does not join a network or test Wi-Fi passwords.

Home Assistant entity reads and controls remain unavailable until pairing
succeeds. This is separate from local Wi-Fi scanning and LAN-neighbor discovery.

## Smart Network and embedded browser recovery

Passive local network discovery does not require Home Assistant. Home Assistant entity
status/read/control requires an owner-paired Home Assistant URL and long-lived access token.
Run `python scripts/configure_home_assistant.py --help` locally or set
`EDITH_HOME_ASSISTANT_URL` and `EDITH_HOME_ASSISTANT_TOKEN`. An unpaired instance is
reported as a setup-needed state instead of a traceback; writes remain disabled until
pairing is configured and still require local confirmation.

The embedded browser now displays a local EDITH start page when opened without a URL and a
visible diagnostic page when navigation fails. It continues to reject non-web URL schemes
and arbitrary JavaScript execution.

## Restored software license

The repository and Windows setup wizard use the proprietary agreement in [LICENSE](LICENSE).
The repository remains source-available for viewing/auditing only under the supplied terms;
a public repository does not imply an open-source grant.
