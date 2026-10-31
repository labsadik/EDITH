# Cross-platform glass desktop implementation plan

Written after `AUDIT.md` and before implementation. Baseline:
`a21c4b8ba59b7c96088349db2358a14d121fea34` (an earlier UI development snapshot).
The audit is a baseline, not a claim that unimplemented features already work.

## Targets and compatibility

Windows 10/11, macOS 13+, Ubuntu 22.04+ and other Linux distributions with the
same Qt/PortAudio/desktop libraries. Python 3.11+. Platform selection uses the
runtime `platform.system()`, never a stale saved OS value. Unknown OS uses a
structured generic fallback. Permissions are OS capabilities, not kernel bypasses.
Existing native OS title controls remain. No React or application framework is added.

Desktop uses locally bundled Tailwind CSS, GSAP and Three.js inside PyQt6-WebEngine.
Retain native Qt backend and EdithUI facade, existing signals and callback names.
Retain native implementation as compatibility/fallback and its regression suite;
the normal desktop entrypoint selects the new web surface when installed. A
restricted QWebChannel exposes named actions only, not arbitrary Python evaluation.
Remote FastAPI protocol/DOM are separate and remain compatible.

Geometry is frozen from the measured 1366×697 client baseline in AUDIT.md: header
54, footer 24, left 160, right 340, center fills remaining width. Baseline action
rectangles/positions stay fixed; glass borders/shadows do not change box sizing.
At smaller sizes, retain the existing minimum/side-panel rules rather than hide
controls. New sheets are overlays, not layout-affecting rows. No supplied current
screenshot exists for an external pixel comparison, so report that acceptance limit.
The new stateful sphere supersedes the previously requested looping video; retain
the asset/legacy path for compatibility. This is the latest requested animation.

## Ordered implementation

1. **Backend contracts:** structured `{ok,data,error,unsupported}` results,
   SystemController and runtime OS selection, read-only diagnostics and cached
   sampling. Implement OS adapters with explicit unavailable results for missing
   libraries, permissions, sensors and desktop services.
2. **Execution boundary:** permission tiers enforced by backend, exact one-use
   pending confirmations, redacted rotating JSONL audit and streamed entries;
   tracked shell/subprocess ownership, timeout/streamed output/cancellation.
   Integrate existing tool dispatcher, shell/generated-code paths and kill switch.
   Do not permit a model `confirmed=true` flag to authorize an operation.
3. **Secrets:** OS keyring, fail closed if no secure backend, atomic migration of
   existing known API-key fields only after verifying keychain writes. Preserve
   non-secret Ollama/provider preferences. No plaintext password collection/logging.
4. **Web surface:** plain HTML/JS, compiled Tailwind tokens, local GSAP transitions
   and Three.js shader sphere. Retain fixed panel/control geometry. Keyboard/focus,
   file dialog, camera/content/task/remote/API/settings and confirmations map to
   the existing callbacks through a compatibility host. Escape closes top sheet;
   the explicit Interrupt action always invokes global cancellation. Escape with
   no sheet invokes global cancellation, matching the specified popup behavior.
5. **Theme:** backend system probe/cache every two seconds, persistent System/Dark/
   Light override; root data-theme and win/mac/linux class; all application web
   colors under the two theme-token selectors, including shader inputs and SVGs.
   Do not scan/alter third-party library internal color constants as app tokens.
6. **Verification:** unit tests with mocked three-OS calls, permission denial/
   approval/expiry and no-auto Tier 3, keychain failure/migration, real disposable
   subprocess tree cancellation/streaming, JS/bridge/button tests, geometry and
   theme contrast checks, headless WebEngine screenshots/console checks where
   supported, existing tests, updated CI and install/run documentation.

## Files to create

| Path | Reason |
| --- | --- |
| `AUDIT.md` | Pre-change full-file/contract/OS inventory and evidence |
| `PLAN.md` | Ordered scope, file plan, risks and acceptance gates |
| `CAPABILITY_MATRIX.md` | OS prerequisites, fallback and validation limits |
| `edith/__init__.py`, `edith/platform/__init__.py` | New package and OS controller factory |
| `edith/platform/base.py` | Public SystemController interface and enforced dispatch boundary |
| `edith/platform/windows.py`, `macos.py`, `linux.py`, `generic.py` | Platform-specific capabilities/commands/theme/elevation |
| `edith/platform/telemetry.py` | Fault-isolated psutil/sensor collection and cached worker |
| `edith/platform/permissions.py` | Tier classifier, settings, pending approvals and cancellation context |
| `edith/platform/processes.py` | Owned subprocess registry, streaming shell and process-tree stop |
| `edith/platform/audit.py` | Redaction, bounded rotating local JSONL and Activity stream |
| `edith/platform/runtime.py` | Shared controller, legacy execution hooks and tool integration |
| `core/secret_store.py` | Keyring persistence and verified JSON credential migration |
| `desktop/__init__.py`, `desktop/host.py` | Restricted WebEngine/QWebChannel compatibility host |
| `desktop/frontend/index.html`, `app.js`, `orb.js`, `styles.css` | Fixed-layout glass UI, callbacks/sheets/theme and sphere |
| `desktop/frontend/dist/*` | Offline-ready compiled local assets (no runtime CDN) |
| `package.json`, `package-lock.json`, `tools/build_desktop.mjs` | Pinned reproducible JS/CSS build and license provenance |
| `tests/test_platform_*.py`, `tests/test_secret_store.py`, `tests/test_desktop_*.py`, `tests/check_desktop_js.js` | New behavior/bridge/OS/geometry/contrast regressions |
| `VERIFICATION.md` | Each acceptance item pass/fail/not verified with evidence |

## Files to modify

| Path | Reason |
| --- | --- |
| `main.py` | Shared controller/tool authorization/audit/cancellation, platform shell tool, keychain reads; preserve audio transport |
| `ui.py` | Select web host through unchanged EdithUI facade, keychain helpers and compatibility signal routing |
| `memory/config_manager.py`, `config/__init__.py` | Secure-key access, atomic settings and runtime OS truth |
| `actions/*.py`, `core/llm_client.py`, `core/tts.py`, `dashboard/server.py` | Replace independent plaintext-key reads and integrate controlled execution where needed |
| `actions/system_monitor.py` | Reuse fault-isolated telemetry without blocking UI/audio |
| `core/startup_check.py`, `requirements.txt` | WebEngine/keyring/optional sensor dependencies and startup diagnostics |
| `.gitignore` | JS build/cache and local audit exclusions; keep compiled distribution |
| `.github/workflows/*.yml` | Install required dependencies and verify new portable/desktop contracts |
| `readme.md`, `TESTING.md`, `docs/UPGRADE_STATUS.md` | Three-OS setup/permissions, manual checks and accurate feature status |
| `tests/test_action_guard.py` and affected contract tests | Update obsolete ordinary-shell-no-confirmation expectation; preserve meaningful action regressions |

Other baseline files remain unchanged unless a reproduced integration regression
requires a small compatibility fix. In particular retain `core/narration_audio.py`,
`core/realtime_audio.py`, `core/audio_meter.py`, `core/product_identity.py`, the
scheduler/evidence journal, existing model IDs/Ollama configuration, remote HTML
IDs/data attributes/event names, media assets, icon set and license. Full baseline
path list is in AUDIT.md; no unrelated source or temporary directories are published.

## Permission design

Tier 0: diagnostic reads. Tier 1: app/URL launch, new file/folder and explicitly
non-destructive application preferences. Tier 2: delete/overwrite, process kill,
install/remove/system settings and arbitrary shell. Tier 3: power, disk format,
registry/system configuration and elevation. Backend can raise configured tiers,
but Tier 2/3 always require a live exact-action confirmation and Tier 3 can never
be auto-approved. A stronger classification overrides a looser setting. Unknown
mutating legacy/plugin actions default to sensitive. Elevation uses OS prompts
(UAC, Apple authorization or polkit) and never accepts a password in app fields.
OS denial/unsupported results are visible. Critical/raw command detection is
conservative; arbitrary code is not claimed to be an impenetrable sandbox.

## Additive bridge contract

`edithBridge.ready()` and `edithBridge.request(action, json_payload)`;
`event(name,json_payload)` → `window.edith.receive(name,payload)`.
Events: `theme.changed`, `platform.info`, `metrics.snapshot`, `permission.request`,
`permission.closed`, `audit.entry`, `status.changed`, `audio.level`, `tasks.changed`,
`content.changed`, `file.changed`, `config.changed`, `connection.test`,
`camera.frame`, `remote.ready`, `command.draft`, `error`.
All existing Qt signal/callback names, remote JS functions/IDs and HTTP/WS event
names in AUDIT.md are unchanged. No action may supply trusted approval in payload.
New desktop IDs and data-action attributes will be appended to AUDIT.md after
implementation; trusted callback names remain stable.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Replacing native UI breaks clicks/signals | Retain facade/Qt handlers, whitelist bridge, real callback tests, no model transport rewrite |
| Chromium/WebGL not available | Required install diagnostics; accessible static sphere and working controls if WebGL denied; native fallback if WebEngine missing; report limitations |
| FPS/power/voice contention | One GSAP ticker, bounded DPR/particle counts, pause hidden/minimized, reduced motion, cached telemetry off Qt/audio loops; measure rather than promise 60fps |
| Platform permissions/Wayland | Explicit unsupported/capability results; OS prompts and documented accessibility/screen/mic prerequisites |
| Cancel leaves running thread | Cancellation token at subsequent side-effect boundaries, cancel asyncio work and owned subprocess descendants; move generated execution out of GUI process; report uninterruptible external calls accurately |
| Secret leakage/config migration | No keychain fallback to plaintext; verify before deleting legacy secret fields, redact logs and errors, preserve unrelated settings |
| Destructive/cross-OS tests | Mock OS actions and use only disposable local processes/files; never invoke real shutdown/elevation/delete during verification |
| Glass contrast/light theme | Central token palette, automated text/surface contrast checks plus screenshots in both themes |
| Remote privilege exposure | Desktop bridge local-only, prevent remote navigation and arbitrary method evaluation; keep remote auth/confirmations |
| Layout drift/fonts | Measured rectangle contract and box-sizing; screenshots and geometry tests, external screenshot match remains not verified |

Publication should use the repository's active default branch. Merge decisions
follow target-device testing and explicit project-owner approval; real OS/API/hardware
checks must never be reported as passed without evidence.

## Owner constraint update: preserve reference video

The latest owner instruction supersedes replacement of the center visual with a
procedural sphere. Keep the exact bundled `assets/hud_reference.mp4`, its origin
URL, loop and framing. Any future Tailwind/GSAP/Three.js work must preserve that
video content; shader or library adoption does not authorize changing the visual.
The unfinished web/platform prototype is not part of the published CI/runtime fix.

## Later owner update: hands-free execution and audio continuity

The owner subsequently requested no separate EDITH confirmation for a direct
instruction. The app logs the action and target, then dispatches it. Audit
tiers, task cancellation, argument checks and native OS authorization remain.
The voice pipeline suppresses microphone packets during speaker playback and
its short output tail; a model tool may change the configured voice only after
a direct recent user request. The bundled video content remains unchanged and
its immediate stage background is black in both themes. Physical audio and
OS permission behavior still require target-device verification.

## Active hardware expansion

The current implementation unit adds normalized local hardware discovery before
adding more controls. EDITH can now identify CPU, memory, storage, network,
display, audio, battery, graphics and connected USB information where each OS
exposes it. Each result is bounded and has a documented unsupported fallback.
The next unit will add dedicated adapters only for hardware with a documented
local control API; capability discovery determines which adapter can run.

## Active MCP plugin expansion

The HexStrike or exploit-tool expansion is deferred by the owner and is not part
of the active branch plan.  The current replacement is a standards-based MCP
plugin host.  Each server is declared in `config/mcp_servers.json`, has an
independent Plugins-panel ON/OFF toggle, and is never advertised to the model
while OFF.  The host accepts only explicit, owner-configured stdio commands; it
does not execute a command supplied in an assistant request.

The starter catalog contains Gmail, GitHub and filesystem entries, but commands
are deliberately blank until the owner selects and installs a trusted MCP
server.  A server exposes its own tools through `tools/list`; EDITH invokes only
those declared tool names.  If that server reports a login/OAuth requirement,
EDITH opens the configured browser URL and retains the tool request for the
`resume` action after login.  Fully automatic OAuth callback completion is
server-specific work and is not claimed by the generic host.

