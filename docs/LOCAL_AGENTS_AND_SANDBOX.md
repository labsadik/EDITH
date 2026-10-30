# Local Versioned Agents and Rust Sandbox

This stage keeps the agent runtime and code execution on the user's computer. It does not deploy an agent runtime, project workspace, model server or sandbox to Vercel or another hosted service.

## Runtime architecture

EDITH has one text/reasoning model profile: **Powerful Brain**. The provider selected in API Providers is used by the orchestrator's text routing and by specialist agents. Legacy Main Brain values in `config/api_keys.json` are read as a compatibility fallback when no Powerful Brain profile has been saved; there is no second Main Brain UI or active runtime profile.

Gemini Live remains the current real-time audio session. It captures and streams microphone/speaker audio and handles the interactive voice session; it is not a second text/reasoning brain. Multimodal image/audio operations that require a media-capable provider retain their dedicated media path.

Built-in agents are versioned in `agents/manifest.json`. Ask EDITH **"list agents and versions"** to see their active state. `agent_manager` can also list, enable or disable a specialist. Local toggles are stored in `config/agents.json`.

| Agent | Initial version | Responsibility |
| --- | --- | --- |
| EDITH Orchestrator | 1.0.0 | Routes voice/text requests to enabled specialist tools. |
| Software Development + DevOps | 1.0.0 | Plans, writes, repairs, tests and runs project code within the local sandbox. |
| DevSecOps Security | 1.0.0 | Offline static scan for exposed credential patterns, private keys, unsafe dynamic code, deserialization and shell/TLS/YAML risks. Runs before each generated-project execution. |
| Project Manager | 1.0.0 | Creates project plans, milestones and locally persisted task status. |
| Device Security | 1.0.0 | Read-only local OS security posture and hardware/platform diagnostics where available. |
| Smart Network | 1.0.0 | Read-only network-interface and OS neighbor-cache inventory. It does not probe the LAN or control devices. |
| Research | 1.0.0 | Search, news, research and comparison actions. |
| Browser & Computer Control | 1.0.0 | Existing browser, visible desktop and app actions, subject to OS permissions. |
| File & Workspace | 1.0.0 | Local file/workspace actions and document/media processing. |
| System Monitor | 1.0.0 | OS telemetry, platform and hardware inventory. |

The manifest is the version source of truth. A version is the shipped agent implementation version, not a promise that every capability is supported on every OS. Agent enable/disable state is local.

## Rust sandbox

Rust source lives in `sandbox-rs/`. The Python bridge `core/sandbox_runner.py` builds the release helper locally on first use or uses the built binary. All generated project execution, dependency installation and generated desktop snippets fail closed if the platform boundary is unavailable. There is no fallback to running generated source in the normal EDITH process.

| Platform | Enforcement boundary | Network behavior |
| --- | --- | --- |
| Windows 10/11 | AppContainer token, scoped filesystem ACLs, child process Job Object, process/time/memory limits and filtered environment. | Project/build execution has no network capability. A dependency install gets only the AppContainer InternetClient capability; local/private-network access is not granted. |
| Linux | bubblewrap mount namespace, unshared user/PID/IPC/UTS/network namespaces, workspace-only write mount, read-only runtime mounts and bounded timeout. | Network is denied. An internet-enabled sandbox run is blocked until a restricted egress-proxy/firewall backend is provided. |
| macOS | Seatbelt `sandbox-exec` profile, workspace/home/temp write access, read-only runtime mounts and filtered environment. | Network is denied. An internet-enabled sandbox run is blocked until a restricted egress-proxy/firewall backend is provided. |

Linux requires bubblewrap and working unprivileged user namespaces. macOS uses the OS-provided Seatbelt sandbox utility where available. Windows requires a supported AppContainer-capable Windows installation. If the OS refuses to apply the boundary, the command must fail rather than run on the host.

The Windows local dependency-install capability is scoped to the Windows AppContainer InternetClient policy, which does not grant private-network-client access. Linux/macOS dependency installation currently needs a pre-populated local package cache or another explicitly approved offline source; do not enable unrestricted egress as a workaround.

The project virtual environment is created in each workspace as `.venv`. Generated project files are validated against absolute paths, drive/UNC paths, traversal and symlink escape before writing. DevSecOps scans local source before every execution. This is defense in depth, not a substitute for code review or a formal penetration test.

## Local agent data

- `config/agents.json`: enabled/disabled specialist IDs.
- `config/projects.json`: Project Manager plans, milestone/task metadata and progress.
- `config/api_keys.json` and OS credential store: existing provider configuration and secrets.
- `sandbox-rs/target/`: locally built helper binaries and Cargo output; ignored by Git.

These runtime files should remain on the local machine and must not be committed.

## Windows PowerShell setup and test

Run from the repository root. This branch is a feature branch until owner acceptance.

```powershell
git status
git fetch origin
git switch backend/versioned-agents-foundation
git pull --ff-only origin backend/versioned-agents-foundation

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

rustc --version
cargo --version
cargo fmt --manifest-path sandbox-rs/Cargo.toml --all -- --check
cargo check --manifest-path sandbox-rs/Cargo.toml
cargo build --release --manifest-path sandbox-rs/Cargo.toml
.\sandbox-rs\target\release\edith-sandbox.exe --version

python -m compileall -q main.py ui.py setup.py actions core agents dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
node tests/check_workspace_js.js

python -m core.startup_check
python main.py
```

If Rust is not installed, install the stable MSVC toolchain using the official Rust installer/rustup, then reopen PowerShell and confirm `rustc --version` and `cargo --version`. A Windows installation without the required MSVC linker/build tools must install the Visual Studio C++ Build Tools before building the Rust helper. Do not bypass the sandbox build failure.

## Linux

Install Python 3.11/3.12, Rust stable and bubblewrap through the distribution package manager. Confirm that unprivileged user namespaces are enabled and that `bwrap --version` works for the current user.

```bash
git status
git fetch origin
git switch backend/versioned-agents-foundation
git pull --ff-only origin backend/versioned-agents-foundation

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

rustc --version
cargo --version
bwrap --version
cargo fmt --manifest-path sandbox-rs/Cargo.toml --all -- --check
cargo check --manifest-path sandbox-rs/Cargo.toml
cargo build --release --manifest-path sandbox-rs/Cargo.toml
./sandbox-rs/target/release/edith-sandbox --version

python -m compileall -q main.py ui.py setup.py actions core agents dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
node tests/check_workspace_js.js
python main.py
```

## macOS

Install Python 3.11/3.12 and Rust stable. Confirm `sandbox-exec` is available on the supported macOS version.

```bash
git status
git fetch origin
git switch backend/versioned-agents-foundation
git pull --ff-only origin backend/versioned-agents-foundation

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

rustc --version
cargo --version
command -v sandbox-exec
cargo fmt --manifest-path sandbox-rs/Cargo.toml --all -- --check
cargo check --manifest-path sandbox-rs/Cargo.toml
cargo build --release --manifest-path sandbox-rs/Cargo.toml
./sandbox-rs/target/release/edith-sandbox --version

python -m compileall -q main.py ui.py setup.py actions core agents dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
node tests/check_workspace_js.js
python main.py
```

## Acceptance checks in EDITH

1. Ask **"list agents and versions"**. Confirm each agent displays a version and enabled/disabled state.
2. Ask **"disable Smart Network"**, then **"list agents"**. Confirm Smart Network is disabled and its tool is no longer available. Re-enable it.
3. Ask **"run a device security audit"**. Confirm EDITH reports only checks actually available on this computer; it must not change firewall or endpoint-protection settings.
4. Ask **"show my local network devices"**. Only existing OS neighbor-cache entries should be listed. No active LAN scan or login/control should happen.
5. Ask EDITH to **plan a project**. Confirm the project and tasks persist locally, then ask for status and mark one task complete.
6. Ask for a DevSecOps audit of a test project under EDITH Projects. Confirm the offline report lists only file/line/rule metadata, never the credential value.
7. Ask EDITH to build a disposable test project. Confirm the Rust sandbox starts, the project uses its own `.venv`, the DevSecOps scan runs before execution and the project is written under EDITH Projects.
8. On Linux/macOS, confirm sandboxed project execution stays offline. If a requested dependency needs the internet, EDITH must report that the restricted network backend is not available—not silently open the network or execute outside the sandbox.
9. Temporarily rename/remove the Rust helper after closing EDITH and retry a sandbox operation. Confirm it builds or reports a sandbox error; it must never run generated code on the host. Restore the helper source and rebuild.

Use a disposable project and non-sensitive files for tests. Never use real API keys, important workspaces or personal recipient accounts as test fixtures. Passing CI does not prove that the user's microphone, speakers, provider account, permissions or desktop integrations work on their machine.
