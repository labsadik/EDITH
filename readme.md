# EDITH — Neuron Intelligence

**EDITH** is a cross-platform desktop AI assistant and local agent platform created by Sadik Laskar. It combines a native desktop HUD, real-time voice, a separate text-reasoning profile, specialist agents, local device tools, a permission-aware automation layer, and an optional phone/remote dashboard.

> **Release:** `1.0.0` · **Primary runtime:** Python 3.11 · **Desktop UI:** PyQt6 · **Local execution boundary:** Rust sandbox  
> This repository is source-available under the proprietary terms in [LICENSE](LICENSE). Public visibility does not grant an open-source, reuse, or redistribution licence.

## Contents

- [Product overview](#product-overview)
- [Features](#features)
- [First launch and setup](#first-launch-and-setup)
- [Architecture: how EDITH works](#architecture-how-edith-works)
- [Agents: roles and capabilities](#agents-roles-and-capabilities)
- [Agent supervisor and local knowledge](#agent-supervisor-and-local-knowledge)
- [Security and execution boundaries](#security-and-execution-boundaries)
- [Voice, audio and speech](#voice-audio-and-speech)
- [Providers, APIs and MCP connectors](#providers-apis-and-mcp-connectors)
- [Smart Network, Wi-Fi and Smart Home](#smart-network-wi-fi-and-smart-home)
- [Desktop, browser and remote dashboard](#desktop-browser-and-remote-dashboard)
- [Frameworks and technology stack](#frameworks-and-technology-stack)
- [Platform support and permissions](#platform-support-and-permissions)
- [Run from source](#run-from-source)
- [Build installers](#build-installers)
- [Configuration and local data](#configuration-and-local-data)
- [Tests and verification](#tests-and-verification)
- [Known capability boundaries](#known-capability-boundaries)
- [License](#license)

## Product overview

EDITH has two distinct AI paths:

1. **Gemini Live** is the current real-time voice/audio session. It handles interactive voice conversation and the live audio transport.
2. **Powerful Brain** is the single configurable text/reasoning profile used for text tasks, planning and specialist-agent reasoning. It can use local Ollama, OpenAI-compatible servers, OpenAI, Anthropic, Groq or xAI.

These are separate responsibilities, not two competing text brains. A generic OpenAI key or a local Ollama endpoint does not replace the Gemini Live audio transport in this build.

The app adapts to the current operating system and exposes structured capability results. Unsupported sensors, OS features, permissions or hardware are reported as unavailable instead of being fabricated.

## Features

### Desktop assistant and interaction
- Native PyQt6 desktop HUD with EDITH branding, theme support, status feedback and a built-in activity view.
- Text input, microphone input and optional paired phone/dashboard input.
- Live states such as Listening, Thinking, Working and Speaking.
- Kore and Orus Gemini Live voice presets.
- Interrupt active speech/work with `ESC`; queue and task controls prevent overlapping user requests from corrupting active work.
- Task history, cancellation, child-process cleanup and bounded retries only for explicitly read-only operations.

### Local computer and device tools
- CPU, per-core load, RAM/swap, disk, process, uptime and network-interface information.
- Hardware inventory, displays and audio-device enumeration where supported by the operating system.
- Local application discovery and launch, window/process inspection, and visible desktop workflows.
- File/folder operations, supported document/media processing, clipboard helpers and bounded host administration tools.
- Screen capture and camera-related UI paths subject to the OS permission model.
- Audit/activity receipts for supported tool actions.

### Browser, research and workspace
- Embedded browser based on Qt WebEngine, with a local EDITH start page and a visible navigation-failure page.
- Web research, current-source lookup and comparison using the configured search path.
- Browser and computer actions use the existing UI/tool verification layer; EDITH reports an action as unverified when the expected window or screen evidence is absent.
- Code/project helper, project workspace, local task plans and supported file conversions.
- Optional remote dashboard for phone pairing, command input and status access.

### Agents and automation
- Ten named agent records in a versioned manifest, each with an ID, version, module, capability list and local enable/disable state.
- Tool declarations are filtered at runtime: when a specialist is disabled, its mapped tools are not offered to the model.
- LangGraph supervisor workflow for retrieval, task planning, bounded specialist-role delegation and final synthesis.
- Local RAG knowledge store using LanceDB and locally generated embeddings when an Ollama embedding service is configured.
- DevSecOps static checks before generated project execution.
- Generated code is executed through the Rust OS sandbox, not directly in EDITH's main process.

### Network and smart-home features
- Smart Network can list OS-known local network neighbours and perform an explicit nearby Wi-Fi scan through visible wireless adapters.
- Windows scanning enumerates OS-visible WLAN interfaces, including supported USB Wi-Fi dongles whose drivers expose them to Windows.
- Linux uses NetworkManager `nmcli`; macOS uses the OS airport scan utility when available.
- Home Assistant pairing verifies the server API and token before credentials are stored.
- Paired Home Assistant reads and a restricted set of entity controls are supported. Every smart-home write requires a separate local confirmation.
- MQTT bridge actions are available through the Smart Network integration subject to its configured broker and action policy.

## First launch and setup

On a fresh install, EDITH opens a focused first-run setup sheet. It asks for:

1. The **Gemini Live API key**.
2. The detected operating-system/device profile: **Windows**, **macOS** or **Linux**. The detected profile is preselected and can be changed before initialisation.

The setup sheet is intended to be the only active UI during this step. The dashboard behind it is covered by a dark, blurred backdrop; pointer interaction is blocked behind the modal, and the API key field receives focus. The key is masked while typing.

The key is saved through the OS credential store when a usable keychain is available. On platforms/configurations without a working keychain, EDITH retains an explicitly identified local-config fallback rather than silently claiming that the key is protected by a keychain.

A successfully saved first-run key and platform profile allow EDITH to continue into the main interface. A later invalid Gemini key opens the provider settings again so it can be replaced and tested.

## Architecture: how EDITH works

At a high level, a request moves through the following local runtime path:

```text
Voice / Text / Remote Dashboard
              |
              v
      Gemini Live or UI entry
              |
              v
       Powerful Brain router
              |
              v
     Agent registry + tool policy
              |
              v
   Enabled specialist / registered tool
              |
              v
  Validation + confirmation + audit layer
              |
       +------+---------------------+
       |                            |
       v                            v
 OS-native adapters           Rust sandbox
 (device/network/UI)      (generated project code)
       |                            |
       +-------------+--------------+
                     |
                     v
        Result, task state and activity
```

The main pieces are:

| Component | Responsibility |
| --- | --- |
| `main.py` / `EdithLive` | Application orchestration, Gemini Live session, conversation loop and tool dispatch. |
| `ui.py` | PyQt6 desktop window, first-run setup, provider workspace, overlays and user confirmations. |
| `core/brain_router.py` | Routes text reasoning to the selected Powerful Brain provider. |
| `core/agent_registry.py` | Reads the agent manifest, stores local enable/disable state and filters each agent's tool declarations. |
| `core/agent_supervisor.py` | LangGraph retrieval → plan → delegate → synthesis workflow. |
| `core/tool_registry.py` | Combines built-in and active plugin/MCP declarations and describes read-only/retry policy. |
| `core/action_guard.py` | Determines when a destructive or externally visible action needs a local confirmation. |
| `core/agent_reliability.py` and task scheduler | Records bounded task state/evidence, deduplicates actions and coordinates queue/cancellation. |
| `edith/platform/` and `core/device_tools.py` | OS-specific adapters and structured local hardware/device capability results. |
| `core/sandbox_runner.py` + `sandbox-rs/` | Starts generated code only inside the OS-enforced Rust sandbox. |
| `core/secrets.py` | Uses the OS keychain for secrets where available and supports a labelled local fallback. |
| `dashboard/server.py` | Optional authenticated remote dashboard service. |

The agent manifest is the source of truth for shipped named agents. The manifest version identifies the implementation version, not a guarantee that every listed capability is available on every operating system or device.

## Agents: roles and capabilities

The shipped catalogue lives in [agents/manifest.json](agents/manifest.json). Agent state is local to the installation and defaults to the manifest's `default_enabled` value.

| Agent | Version | Module | What it does |
| --- | ---: | --- | --- |
| **EDITH Orchestrator** | 1.0.0 | `main.EdithLive` | Receives voice/text requests, routes intent, checks enabled specialists, dispatches tools and tracks task state. |
| **Software Development + DevOps** | 1.0.0 | `actions.dev_agent` | Plans, creates, repairs, reviews, builds and tests local software projects. Generated project commands use the Rust sandbox; unrestricted remote deployment is not enabled. |
| **DevSecOps Security** | 1.0.0 | `agents.devsecops` | Runs offline static checks for secret/private-key patterns and unsafe code/configuration patterns before generated project execution. |
| **Project Manager** | 1.0.0 | `agents.project_manager` | Breaks work into projects, tasks and milestones; saves local progress and reports project status. |
| **Device Security** | 1.0.0 | `agents.device_security` | Performs read-only local security-posture checks, such as available firewall/endpoint-protection status, hardware inventory and process inventory. It does not change security settings. |
| **Smart Network** | **2.1.0** | `agents.smart_network` | Scans nearby Wi-Fi networks through OS-visible adapters, lists OS-known local neighbours and provides paired Home Assistant/MQTT operations behind authentication and confirmation. |
| **Research** | 1.0.0 | `actions.web_search` | Searches and compares current sources, research topics, news and product information. |
| **Browser & Computer Control** | 1.0.0 | `actions.browser_control` + `actions.computer_control` | Operates the embedded/visible browser and supported desktop workflows; uses screen/window checks where available. |
| **File & Workspace** | 1.0.0 | `actions.file_controller` + `actions.file_processor` | Manages local files/folders/workspaces and supported document/media processing. |
| **System Monitor** | 1.0.0 | `actions.system_monitor` + `edith.platform` | Reads system telemetry, hardware inventory, process information and platform capabilities. |

### How the named agents are enabled and used

- `agents/manifest.json` contains agent identity, module, semantic version, description, capabilities and default state.
- `core/agent_registry.py` reads the manifest and local `agents.json` toggles.
- The Plugins → Agents view lets the user enable or disable an agent.
- Tool-to-agent mappings are defined in `TOOL_AGENT_MAP`. Examples: `dev_agent`, `code_helper` and `shell_execute` map to Software Development; `smart_network` maps to Smart Network; `web_search` maps to Research.
- If an agent is disabled, mapped tools are removed from the declarations sent to the model. The agent manager remains available so the user can re-enable it.

Named manifest agents are different from the temporary specialist roles used by the LangGraph supervisor below. The four supervisor roles are not four extra installed agents.

## Agent supervisor and local knowledge

### LangGraph supervisor

The optional multi-role supervisor in `core/agent_supervisor.py` builds a LangGraph state workflow:

1. **Retrieve** — searches the local knowledge base for up to five relevant chunks.
2. **Plan** — asks Powerful Brain for a bounded JSON plan of one to four tasks.
3. **Delegate** — runs the selected short-lived specialist roles: **planner**, **researcher**, **developer** and/or **security**.
4. **Synthesize** — combines the user request, retrieved context and specialist results into one answer that separates facts, assumptions and next steps.

Each role has a focused instruction. The workflow does not claim a file/device was changed merely because a model described a possible action. Actual changes must go through the registered tools and their checks.

### Local RAG knowledge store

`memory/rag_store.py` uses:
- **LangChain Documents** and **RecursiveCharacterTextSplitter** for document representation and chunking.
- **LanceDB** for the local vector store.
- **Ollama embeddings** over a local HTTP endpoint by default: `http://127.0.0.1:11434`.
- Default embedding model: `nomic-embed-text`.

The current splitter uses 900-character chunks with 140-character overlap. Supported text sources include TXT, Markdown, source/config files, CSV, HTML, XML, PDF and DOCX. A document must be selected for indexing; supported content is stored in the local vector database. The embedding endpoint is local by default; configure it explicitly before indexing when Ollama runs elsewhere.

## Security and execution boundaries

EDITH separates reasoning from permission to perform actions. Model output is not itself authorisation.

### Local confirmations and tool policy
- Destructive file removal, restart/shutdown, selected message sends, certain desktop actions, Home Assistant controls and MQTT publishes are routed through a local confirmation step.
- Home Assistant writes are allowlisted and validate the entity/service and accepted service-data fields/ranges before sending.
- Read-only retries are limited to tools whose registry policy explicitly marks them retryable. Mutating actions are not silently retried.
- Secret values are not intended for activity-log output; the credential helper registers saved values for redaction.
- OS-native elevation/permission requests are not bypassed.

### Rust sandbox

The Rust helper source is in `sandbox-rs/`; the Python bridge is `core/sandbox_runner.py`. Generated project execution, dependency installation and generated desktop snippets fail closed if the platform sandbox cannot be applied. EDITH does not fall back to executing generated project source in its normal host process.

| OS | Enforcement mechanism | Network boundary |
| --- | --- | --- |
| **Windows 10/11** | AppContainer, scoped filesystem ACLs, child-process Job Object, filtered environment and process/time/memory limits. | Generated project execution is offline. Dependency installation receives only the configured AppContainer InternetClient capability; it is not granted private-network access. |
| **Linux** | bubblewrap mount namespace, unshared user/PID/IPC/UTS/network namespaces, workspace-only writable mount and read-only runtime mounts. | Network is denied. |
| **macOS** | OS Seatbelt sandbox profile via `sandbox-exec`, restricted writable paths, read-only runtime mounts and filtered environment. | Network is denied. |

Linux requires bubblewrap and usable unprivileged user namespaces. macOS requires the OS sandbox utility on the supported system. If the OS refuses the policy, the operation must stop.

The generic host `shell_execute` tool is a separate, permission-graded and audited owner-requested system administration path. It is not the generated-code sandbox and must not be used as a fallback when sandboxing fails. Generated desktop snippets do not receive unrestricted access to the host keyboard, mouse, desktop session or arbitrary home directories.

## Voice, audio and speech

- The current live voice session uses Google's Gemini Live API.
- The voice presets are **Kore** and **Orus**.
- `sounddevice`/PortAudio and NumPy are used for local audio I/O and signal handling.
- The narration writer uses mono 24 kHz PCM16 and writes in bounded 20 ms chunks.
- The initial speech prebuffer is 60 ms. A genuine device output underrun increases the adaptive prebuffer gradually, up to 300 ms.
- Generated speech chunks remain in order; they are not silently discarded to make the stream appear current.
- A missing/disconnected output device is reported as unavailable. Stale buffered speech is cleared and is not replayed after device recovery.
- Configurable STT engine packages include faster-whisper and Vosk. Configurable TTS package options include Edge TTS, Kokoro and ElevenLabs. These engine options are distinct from the current Gemini Live conversation transport.

Microphone, speaker and OS privacy permissions must be granted on the target device. CI tests use mocks for audio hardware and do not certify a particular audio driver or USB device.

## Providers, APIs and MCP connectors

### Powerful Brain providers

Open **Controls → API Providers → Powerful Brain**. The supported provider paths in the current registry include:

- Ollama (local)
- OpenAI
- Anthropic Claude
- Groq
- xAI / Grok
- OpenAI-compatible local or hosted endpoints

Configure the endpoint and model, enter a provider key when required, run the real minimal connection/response test, and save only after verification. Powerful Brain settings and credentials are separate from Gemini Live voice credentials. A local Ollama profile does not require a cloud API key.

### Gemini Live key

The Gemini Live key is configured in the Voice provider section / first-run wizard. Use **TEST KEY** before saving where the UI offers it; EDITH makes a real minimal provider request and then enables the save action only for a tested key.

### MCP connectors

Open **Controls → Plugins**. The built-in connector profiles include Gmail, GitHub, Filesystem, Google Drive, Google Calendar, Notion, Slack and Linear.

1. Select **CONNECT** for the provider profile.
2. Open its setup instructions and complete the provider's required OAuth/API setup.
3. Enter a trusted Streamable-HTTP MCP endpoint where the provider requires one.
4. Provide the provider-issued token and select **SAVE & TEST**.
5. Keep the connector enabled only after EDITH successfully tests it and discovers its reported tools.

The runtime registers the tools actually returned by a connected MCP server. A catalogue profile is not a promise that a free public endpoint or every expected operation is available. For example, a Gmail MCP server may expose draft/search tools without exposing a direct send operation. EDITH does not reuse ordinary browser login cookies as MCP credentials.

Credentials use the OS keychain when available; connector setup and OAuth must be completed by the owner. Connect only endpoints that you trust.

## Smart Network, Wi-Fi and Smart Home

### Wi-Fi scan

Open **Plugins → Agents → Smart Network → SCAN WI-FI** or ask the Smart Network agent to run `wifi_scan`.

- **Windows:** discovers each WLAN interface visible to Windows, sends a native scan request for each one, then reads the OS scan result. Supported USB Wi-Fi dongles are included when the driver exposes them as WLAN interfaces.
- **Linux:** calls NetworkManager `nmcli` to rescan and list visible access points.
- **macOS:** uses the OS airport scan utility when it is present.

Returned fields can include SSID, BSSID, signal strength, channel, authentication and radio type. Hidden SSIDs may be represented without a name. A USB dongle requires a working driver and an enabled OS wireless service. If a driver, WLAN service, NetworkManager or platform utility is missing, EDITH reports that reason rather than claiming success.

This is an OS-native nearby access-point scan. It reads visible beacon information; it does **not** attempt to join a network, test a Wi-Fi password, capture credentials or perform packet injection. Passive LAN neighbour discovery remains a separate operation and lists entries already known to the operating system; it is not an active port scan.

### Home Assistant

Open **Plugins → Agents → Smart Network → PAIR HA** (or **UPDATE HA** for an existing pairing).

1. Enter the Home Assistant base URL.
2. Paste a Home Assistant long-lived access token into the masked field.
3. EDITH tests the token against the Home Assistant `/api/config` endpoint.
4. Credentials are persisted only after the verification succeeds.

The URL and token are checked for invalid, redirected, unreachable or timed-out responses. The OS keychain is used where available; the UI reports when it must use the local config fallback. Entity reads and controls remain unavailable until pairing succeeds. Supported writes use an allowlist and require a separate local confirmation.

### MQTT

Smart Network also routes its declared `mqtt_*` operations to `agents/mqtt_bridge.py`. It is intended for explicitly configured broker integrations; publishing is a state-changing operation and requires a local confirmation. Do not treat MQTT availability as proof that a broker or device has already been paired on a given machine.

## Desktop, browser and remote dashboard

### Browser and computer workflows
- Embedded browser is powered by PyQt6-WebEngine.
- Opening the browser without a URL displays an EDITH start page; navigation failures display a readable diagnostic page.
- Non-web URL schemes and arbitrary JavaScript execution are restricted.
- Browser/desktop automation is performed through the existing registered tool layer and OS capability checks.
- A successful process launch is not enough to claim an app is ready: EDITH checks the foreground-window label or other available screen evidence.

### Remote phone/dashboard
- `dashboard/server.py` provides an optional FastAPI/Uvicorn service.
- The UI supports QR/manual pairing and short-lived remote access material; the remote client supports reconnect handling and command safety checks.
- Dashboard TLS/authentication material is stored in local writable application data.
- Only enable remote access on a network and device you control. Keep pairing credentials private.

### Special-device integration
The included vehicle adapter is an in-memory simulator used to demonstrate a special-device contract. It is **not** a real vehicle/OEM integration and does not control a car.

## Frameworks and technology stack

This table describes libraries and tools declared or directly used by the current source tree. Optional/platform-specific packages are only required for their corresponding features.

| Area | Frameworks / tools | Purpose |
| --- | --- | --- |
| Language/runtime | Python 3.11; Rust stable | Desktop/runtime services and native sandbox helper. |
| Desktop UI | PyQt6 | Main window, HUD, settings, overlays, modal setup and local confirmation dialogs. |
| Embedded browser | PyQt6-WebEngine | In-app browser component. |
| Live AI | `google-genai` (Google GenAI SDK) | Gemini Live voice/audio session and provider requests. |
| Audio | sounddevice / PortAudio, NumPy, SoundFile, miniaudio | Audio-device I/O, PCM handling and selected audio formats. |
| Text model routing | Ollama and OpenAI-compatible HTTP APIs; OpenAI, Anthropic, Groq and xAI provider adapters | Powerful Brain text/reasoning profile. |
| Agent orchestration | LangGraph | Retrieve, plan, delegate and synthesize graph. |
| RAG/document chunks | LangChain, langchain-core, langchain-text-splitters | Document abstraction and chunk splitting. |
| Local vector database | LanceDB | Local vector storage and semantic retrieval. |
| Local embeddings | Ollama HTTP embedding API; `nomic-embed-text` by default | Embedding documents locally. |
| OS sandbox | Rust; Windows AppContainer, Linux bubblewrap, macOS Seatbelt | Enforced boundaries for generated project execution. |
| Remote dashboard | FastAPI, Uvicorn, python-multipart, cryptography | Optional HTTP/API, upload and TLS-related functionality. |
| Browser/search | Playwright, requests, BeautifulSoup, ddgs | Declared browser automation and search/retrieval utilities. |
| Desktop automation | psutil, PyAutoGUI, Pyperclip, PyGetWindow, MSS, OpenCV | Process, clipboard, screen and supported desktop operations. |
| Windows adapters | pywin32, WMI, pycaw, pywinauto, comtypes, win10toast | Windows COM, hardware/audio and desktop integration where supported. |
| Credentials | keyring | OS credential store integration with a labelled local fallback. |
| Networking | paho-mqtt, requests | MQTT bridge and HTTP integrations. |
| Documents/media | pypdf, python-docx, python-pptx, youtube-transcript-api, Pillow | Document extraction/creation and image/media utilities. |
| Packaging | PyInstaller, Inno Setup 6, Apple `pkgbuild`/`productbuild`/`hdiutil`, tar | Native app and installer artifacts. |
| CI | GitHub Actions | Automated quality checks, cross-platform smoke tests and installer builds. |

The declared Python dependency list is in [requirements.txt](requirements.txt). Platform-specific packages use environment markers. Install only the dependencies needed for your platform and enabled features.

## Platform support and permissions

The platform adapter currently targets:

| Platform | Documented target | Notes |
| --- | --- | --- |
| Windows | Windows 10/11 x64 | Native WLAN, AppContainer sandbox and Windows automation depend on installed drivers and policies. |
| macOS | macOS 13+ | Screen/audio access and sandbox utilities depend on OS permissions and version. |
| Linux | Ubuntu 22.04+ and compatible distributions | bubblewrap, user namespaces, NetworkManager, multimedia libraries and desktop session affect feature availability. |

Grant microphone access for voice input. Grant screen recording/accessibility permission only for the relevant visible-desktop features. Camera permissions are needed only when using the camera features. Some native OS actions may display the operating system's own permission/elevation dialogue.

No application can enumerate hardware that the operating system or its driver does not expose. For example, a USB Wi-Fi adapter must have a working driver and be available to the OS wireless subsystem.

## Run from source

Python **3.11** and Rust stable are the recommended development toolchains for the current CI/package workflow.

### Windows PowerShell

```powershell
git clone https://github.com/WorkRCS/EDITH_v1.git
cd EDITH_v1
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cargo build --release --manifest-path sandbox-rs/Cargo.toml
python main.py
```

A Windows build environment needs the Rust MSVC toolchain and appropriate Visual Studio C++ Build Tools/linker. For Wi-Fi scanning, ensure the WLAN service is running and the adapter driver is installed.

### macOS / Linux

```bash
git clone https://github.com/WorkRCS/EDITH_v1.git
cd EDITH_v1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cargo build --release --manifest-path sandbox-rs/Cargo.toml
python main.py
```

On Linux, install bubblewrap and enable the required unprivileged user namespaces for sandboxed project execution. NetworkManager is used by the Wi-Fi scan implementation. macOS uses the OS Seatbelt utility for generated-code sandboxing.

## Build installers

The repository provides build workflows for native platform artifacts:

- **Windows x64:** Inno Setup 6 interactive `EDITH-Setup-<version>-x64.exe`.
- **macOS:** Installer PKG and optional DMG containing the PKG.
- **Linux x64:** `EDITH-Linux-x64.tar.gz`.

### Windows local build

Run from the repository root in PowerShell with Python 3.11 and Rust stable available:

```powershell
.\scripts\build_windows_installer.ps1
```

The script installs the Python requirements, builds the Rust sandbox, packages the app with PyInstaller, finds or offers to install Inno Setup 6 via user-scope WinGet, then compiles and validates the expected non-empty setup EXE. To open the installer after a successful build:

```powershell
.\scripts\build_windows_installer.ps1 -LaunchInstaller
```

Useful switches:
- `-SkipAppBuild` — use an already-built `dist/EDITH` bundle.
- `-NoInstall` — fail instead of installing Inno Setup when it is missing.
- `-LaunchInstaller` — launch the generated installer after verifying it exists.

The common package script is `python scripts/package_edith.py`; it builds the PyInstaller onedir application for the current OS and includes the native sandbox binary. The generated EDITH monogram icon is reused by the packaged executable and Windows setup wizard.

### CI release artifacts

The GitHub Actions workflow **Build EDITH installers** builds and uploads the Windows EXE, macOS PKG/DMG and Linux tarball. Artifacts have a limited retention period shown on the workflow run; they are not permanent release downloads unless separately published.

## Configuration and local data

Packaged builds keep credentials and mutable configuration outside the installation directory:

| OS | User config root |
| --- | --- |
| Windows | `%APPDATA%\\EDITH` |
| macOS | `~/Library/Application Support/EDITH` |
| Linux | `$XDG_CONFIG_HOME/edith` or `~/.config/edith` |

Examples of local data:
- `config/api_keys.json` — non-secret preferences and compatibility config; secrets use the OS keychain when possible.
- `config/agents.json` — agent enable/disable overrides.
- `config/projects.json` — Project Manager's local plans/tasks.
- `memory/` — persistent local memory and retrieval data.
- Local LanceDB vector store — indexed knowledge chunks.
- Dashboard authentication/TLS material, local plugin/MCP settings and uploads — per-user writable app-data paths for packaged builds.

On first launch after an upgrade, existing install/config data may be copied into the current user's writable data directory without overwriting the destination or deleting the source. Source checkouts keep compatible repository-local config paths.

Do not commit API keys, Home Assistant tokens, MCP credentials, remote pairing material, local databases or personal project data.

## Tests and verification

Run the Python suite and JavaScript contract checks from the repository root:

```powershell
python -m compileall -q main.py ui.py actions core agents dashboard memory plugins tests config tools
python -m unittest discover -s tests -q
node tests/check_workspace_js.js
```

Additional project checks (depending on the change) include:

```powershell
python tests/check_inline_js.py
node tests/check_phase5_js.js
cargo test --manifest-path sandbox-rs/Cargo.toml
```

The automated tests cover platform adapters with mocks, audio chunk ordering/buffering, agent and tool policy, task scheduling/interruption, MCP/provider contracts, UI behaviour and sandbox policy. CI's platform smoke workflow runs on Windows, Ubuntu and macOS; the installer workflow builds the platform artifacts.

**Important:** CI mocks do not certify a specific USB Wi-Fi adapter/driver, microphone, speaker, GPU, Home Assistant server, MQTT broker, provider account, OAuth token or third-party desktop application. Test those integrations on the target machine before relying on them.

## Known capability boundaries

- USB Wi-Fi enumeration depends on the driver exposing the device as a WLAN interface to the OS.
- Wi-Fi scan results are limited to networks visible to the OS at scan time.
- LAN neighbour inventory reads the operating system's existing neighbour cache; it is not a full LAN discovery or vulnerability scan.
- Home Assistant and MQTT operations require separately configured and authenticated services.
- Home Assistant writes remain allowlisted and require local confirmation.
- Generated code cannot execute outside the Rust sandbox. A missing sandbox is an error, not a reason to fall back to host execution.
- Linux/macOS generated-code sandbox execution is offline. Windows dependency installation is limited to the configured AppContainer InternetClient capability.
- Device Security is a read-only posture report, not an endpoint protection replacement.
- The bundled vehicle interface is a simulator and does not control real vehicles.
- Model-generated text is not evidence that an external action succeeded; EDITH relies on tool results and verification.

## License

See [LICENSE](LICENSE). EDITH is distributed under the supplied proprietary commercial source-available agreement. The project must not be described as open source unless the copyright holder separately grants that licence in writing.
