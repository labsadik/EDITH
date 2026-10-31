# EDITH verification ledger

This document maps the twelve acceptance items to evidence available in the
repository. It began as an earlier release-verification snapshot; use the root
README for current clone and platform setup instructions. A green hosted runner verifies
the code paths it exercises; it cannot validate the owner's display, audio
devices, API credentials, permissions or network. Record target-device results
in `TESTING.md` before calling this release production ready.

Automated gates:

```text
python -m compileall -q main.py ui.py setup.py actions core dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
node tests/check_workspace_js.js
```

`.github/workflows/quality-checks.yml` runs these on Ubuntu with offscreen Qt.
`.github/workflows/platform-smoke.yml` runs platform, task, hardware-fault,
memory, device-bridge and latency regressions on hosted Windows, macOS and
Ubuntu runners. Check the workflow result at the actual branch head; earlier
runs do not validate a newer commit.

| # | Acceptance item | Current result | Evidence / remaining check |
| --- | --- | --- | --- |
| 1 | 1366×697 layout matches the supplied screenshot | Not verified externally | Native geometry and visibility regressions pass in `tests/test_enterprise_ui.py`. The referenced external screenshot is not available for a pixel comparison. Check the owner's actual display and DPI scaling. |
| 2 | Starts on Windows/macOS/Linux and selects the right OS controller | Partial | `tests/test_platform_layer.py` checks runtime OS selection in mocks; the three hosted runners exercise portable modules. Complete GUI startup and permissions on each target machine are not certified. |
| 3 | Real telemetry where supported; N/A otherwise | Partial | Collector failure isolation and cached UI reads are tested in `tests/test_platform_layer.py`; GPU, temperature, battery and network sensors still need device checks. Link speed is not Internet speed. |
| 4 | Shell/process/file/app/power across all OS with correct tiers | Partial | Disposable shell/file tests and mocked OS power tests pass; `core/execution.py` and `edith/platform/` route controlled work through permission checks. Actual elevation, app launch, power and every independent legacy process path have not been validated on all target OSes. |
| 5 | Tier 2/3 always confirmed before execution | Superseded by owner's hands-free request | The app now runs user-requested actions without its voice or Qt confirmation step. Tier labels remain in audit receipts; cancellation and native OS authorization remain. Tests cover the no-dialog broker path. This intentionally changes the earlier acceptance item. |
| 6 | ESC/Interrupt stops work and child processes | Partial | `tests/test_global_kill_switch.py` and execution tests cover queued tasks and owned process trees. External/legacy subprocesses outside the registry may continue; on-device interrupt must be observed. |
| 7 | Every action in audit and Activity Log | Partial | `tests/test_audit_stream.py` covers routed dispatcher and platform receipts. Legacy actions invoked outside these entry points remain unverified. |
| 8 | System/Dark/Light tracks three OS themes live | Partial | Native Qt startup hint, OS worker, case-insensitive live stylesheet swap, existing log recoloring and dark/light popup/context-menu tests pass. Real OS switching, app restarts and accessibility contrast still need target-device checks. |
| 9 | Every popup uses glass styling and GSAP animation | Partial styling; GSAP absent | Existing native Qt sheets now use theme-aware translucent surfaces, contrast tokens and soft shadows. There is no desktop GSAP runtime or full popup animation; the owner's later instruction preserved the classic layout and video. |
| 10 | Orb is Three.js, stateful, near 60 fps | Superseded visual; FPS unverified | The exact bundled `assets/hud_reference.mp4` loop remains; only its canvas backdrop is pure black in both themes. State labels and audio waveforms are independently tested. Neither Three.js nor a measured 60 fps claim applies. |
| 11 | No console errors and no component hardcoded colors | Not met | Qt/FFmpeg warnings may appear without app failure; native widget colors still include literals. Review actual runtime traceback and both theme contrast modes on the owner's hardware. |
| 12 | Every existing button works | Partial | Headless tests cover major input, settings, interrupt, file, popup and remote actions. Physical microphone, camera, keyboard focus and click paths still need owner validation. |

Additional completion gates from the staged plan:

- Voice narration: synthetic PCM order, buffer/underrun, echo gate, voice-change
  intent and interruption tests pass. Listen to long real responses on the owner's selected speaker and
  report any clipping with sanitized timings.
- Providers: configured text adapters and local/Gemini Live test buttons exist;
  real provider connection, voice and tool responses must be tried using the
  owner's own keys. Never share keys in logs or screenshots. Record the selected
  model, provider response test, tool/function-call behavior, context/output-token
  capacity and available quota. A stronger reasoning/coding model can improve
  multi-step work when it supports EDITH's tool-call format; invalid credentials,
  insufficient token budgets, HTTP 429 responses or exhausted quota can prevent
  completion even when EDITH's local code is correct. A paid tier may be appropriate
  for sustained use but is not unlimited. A paid consumer chat subscription does not
necessarily include API credits for EDITH; verify the API account's billing and quota
separately. Test Gemini Live separately from text LLMs.
- Memory: backup recovery and session replay semantics are covered by
  `tests/test_memory_durability.py`; long sessions and externally modified
  files still need practical validation.
- Device bridge: `tests/test_device_tools.py` validates bounded local calls and
  argument checks. Window targeting and platform-specific sensors need actual
  OS permission and hardware evidence.
- Performance: `tests/test_latency_metrics.py` validates aggregation, while
  the read-only `performance_metrics` tool reports local p50/p95 observations.
  Reconnect regression tests cover zero-delay recovery, bounded exponential
  backoff and cancellation. There is no universal subsecond guarantee; record
  target-device values and retry observations.
- Third-party security tooling and arbitrary vehicle/device takeover are not
  integrated or certified by this branch. Only documented local OS capabilities
  have been wired into the device bridge.

Release status: **pending target-device checks**. This ledger records evidence
requirements, not a prescribed Git branch or merge procedure. Complete the relevant
Windows, macOS and Linux checks on the actual target devices before claiming release readiness.

