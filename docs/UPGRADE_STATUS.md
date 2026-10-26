# EDITH upgrade status

All implementation remains on `ui/edith-interface`. Do not merge this branch into
`main` until the owner has tested a pull of the branch and explicitly requests merge.

## Current UI after owner feedback

- Restore the layout, desktop palette and remote page appearance from `938ffe5`,
  before the two UI redesign commits `8219027` and `7eb2ab4`.
- Play the user-selected bundled video in a silent infinite loop with soft edge blending;
  retain independent real input/output feedback and activity labels.
- Retain native OS window controls and screen-aware startup geometry; remove duplicate
  in-app window buttons.
- Retain confirmation expiry/serialization, selected-file clearing, newer remote
  command/pairing behavior and Neuron Intelligence product metadata.
- Remove the Apple light theme and separate conversation/context-tab layout.
- This is a forward UI restoration commit, not a branch reset or a merge to main.

## Remaining stages

Audio/runtime reliability implementation has started. Generated narration now uses
a lossless PCM FIFO, a dedicated device writer, startup/rebuffer prefill and explicit
underrun diagnostics. Tool execution no longer blocks the audio receiver. Startup
news waits for generation **and** hardware playback to finish instead of a fixed
delay. See [NARRATION_RELIABILITY.md](NARRATION_RELIABILITY.md) for the failure,
implementation boundaries and target-device checks. This stage does not implement
the later provider, voice approval or device-control features.

| Stage | Implementation and acceptance gate |
| --- | --- |
| Full branch audit | Inventory both branches and every tool/sub-command; reproduce failures; record dependencies, supported OS and real execution evidence. Earlier UI tests are not a full runtime certification. |
| Narration reliability — implemented, device test pending | Byte-for-byte burst/jitter tests, ordered tool execution while audio receive continues, speaker recovery and interruption checks pass with simulated streams. Confirm long spoken responses with the owner's actual API key, network and speaker. |
| Task/session control | Explicit Working, Awaiting approval, Stopping and Sleeping lifecycle; accept stop/clarification/approval while rejecting unrelated new tasks during a job; verify cancellation semantics. |
| Voice approval | Bind a spoken reply to one pending action and target; exclude assistant output and untrusted content; expiry, rejection and microphone-unavailable behavior; destructive tests only with disposable targets. Existing local confirmation remains active until this is implemented and verified. |
| Provider adapters | Separate Gemini, Ollama, Anthropic, xAI and OpenAI settings and runtime adapters. Preserve existing Ollama settings. Real key/response/voice/tool tests per provider; no unsupported native audio capability claims. |
| Memory | Transactional storage, structured project/task facts, summaries, retrieval, provenance and migration from the bounded JSON store. |
| Device/tool coverage | Hardware/network diagnostics, multi-monitor/window targeting, terminal/code workflows and authorized security diagnostics; OS capability/permission reporting and post-action verification. |
| Latency and resilience | Measure input, first audio, tool start and verified completion separately; p50/p95 benchmarks, network interruptions, hardware recovery and duplicate-action handling. |
| Release | Target Windows/macOS/Linux and phone-browser checks, user's pull/test feedback, fixes, then explicit authorization before merging into main. |

API-provider access, real microphones, cameras, screen permissions and OS window
managers must be tested on target devices. Headless GUI tests validate application
behavior; they do not certify those external integrations. No universal sub-second
task-completion or unrestricted access to arbitrary devices is claimed.

## CI/runtime follow-up

- GitHub Actions failure reproduced from job 120833033039: Qt Multimedia could
  not import because the Ubuntu runner lacked `libpulse.so.0`. Add libpulse0 and
  font prerequisites; retain real video decoding tests. Check missing asset before
  importing the optional media backend so errors identify the actual missing file.
- Defer desktop action imports until after QApplication initialization, avoiding
  automation libraries setting Windows DPI mode before Qt. Add Bengali font fallback.
- Consume PCM inline parts directly instead of the Gemini SDK's mixed-part `.data`
  convenience accessor; thought/text parts are not audio.
- Add bounded runtime/exit and fatal-stack diagnostics. The supplied Windows log
  contains no traceback, so an actual crash cause is not established by that log.
- Keep the reference video byte-for-byte. The broader platform/web prototype remains
  incomplete and is not included in this focused patch. No merge to main.

## Platform/telemetry implementation checkpoint

The runtime-selected SystemController adapters and structured results are now
implemented in `edith/platform/`. The native telemetry UI consumes the shared
background collector cache, including cached uptime/process count; it no longer
samples these on the Qt timer. Missing individual sensors remain null/N/A.

Controller methods already reject unconfirmed sensitive operations, but this is
not yet the complete legacy tool/Settings permission migration or global ESC
integration. The scoped Step 7 execution layer is now wired into shell, coding,
generated desktop-code and code-file paths: every such command gets an exact
confirmation, streams output, records a redacted receipt and honors timeout or
interrupt. Media/FFmpeg and other independent subprocess paths still require
the later tool-by-tool migration. See [IMPLEMENTATION_PROGRESS.md](IMPLEMENTATION_PROGRESS.md)
for the ordered completion ledger.

The Step 8 dispatcher layer now applies backend `tool_tier` floors to legacy
tools. Tier 2 and Tier 3 calls cannot be authorized by model-supplied flags:
the local dialog approves a redacted argument preview, the broker re-checks
the floor, and a dispatcher-owned context is propagated to controlled worker
threads. Native OS elevation and independent legacy subprocesses are still
explicitly pending.

The Step 9 global interrupt now cancels queued and active scheduler wrappers,
drains pending tool batches, invalidates the current turn, clears queued audio
and vision state, and stops owned shell/code child processes. A cancelled
wrapper returns an interrupted result rather than a stale success. Subprocesses
started by independent legacy paths are not falsely claimed as killable until
they are migrated into the owned registry. No UI redesign or video asset
replacement is included.

Step 10 now connects the shared redacted `AuditLog` to the existing Activity
Log and records dispatcher `tool.start`/`tool.finish` receipts for routed tools,
including tier and outcome metadata. Large code/message payloads are omitted
from dispatcher receipts; provider keys and registered secrets are redacted.
Tool paths invoked outside the dispatcher still need their own migration before
they can be claimed as complete.

Step 11 stores newly saved Gemini credentials in the OS keychain through
`keyring`, then atomically removes the plaintext field only after keychain
storage succeeds. Existing plaintext installations are migrated on read when a
usable keychain appears. A headless system with no secure backend retains an
explicitly-labelled legacy key rather than silently losing connectivity or
claiming secure storage. Gemini runtime readers and the ElevenLabs TTS path use
the shared secret layer; keys are registered with the log redactor.
