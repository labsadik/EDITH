# EDITH — Full Verification Checklist

This checklist separates automated repository checks from manual tests that must be
run on the computer where EDITH will be used. Passing CI does **not** prove that
every OS-specific GUI action works on every machine. See [VERIFICATION.md](VERIFICATION.md)
for the release acceptance ledger.

## 1. Get the source and prepare the environment

### Copy the clone URL

1. Open this project's repository page in GitHub.
2. Select **Code → HTTPS → Copy URL**.
3. Paste the copied URL into the placeholder below. The documentation does not
   store a fixed owner/repository URL; use the URL shown on your own repository page.

```bash
git clone "<COPIED_HTTPS_REPOSITORY_URL>"
cd "<CLONED_REPOSITORY_DIRECTORY>"
```

Replace both placeholders before running the commands. Git creates the checkout
folder from the repository URL; use the folder name printed by Git.

For an existing checkout, first protect or commit any uncommitted work, then update
the default branch:

```bash
git status
git switch main
git fetch origin
git pull --ff-only origin main
```

### Windows

Use PowerShell with Python 3.11 (64-bit) and Rust stable installed. Rust native
builds require the MSVC toolchain and the appropriate Visual Studio C++ Build Tools.

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cargo build --release --manifest-path sandbox-rs/Cargo.toml
```

### macOS

Use macOS 13+, Python 3.11 and Rust stable. Grant microphone, camera, Screen
Recording and Accessibility permissions only when testing the associated feature.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cargo build --release --manifest-path sandbox-rs/Cargo.toml
```

### Linux

Use Ubuntu 22.04+ or a compatible distribution, Python 3.11 and Rust stable.
Install bubblewrap and enable unprivileged user namespaces for sandbox checks;
install NetworkManager for Wi-Fi scan checks. Screen/window features differ between
X11 and Wayland.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cargo build --release --manifest-path sandbox-rs/Cargo.toml
```

## 2. Run automated checks first

Run these from the project root, in the activated environment:

```bash
python -m compileall -q main.py ui.py actions core agents dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
```

**Pass criteria:** all commands exit with code 0; the unit-test output ends with `OK`. If any command fails, stop here, save the error output with credentials and private text removed, and fix it before live testing.

The GitHub Actions Quality checks workflow runs the repository checks on supported CI runners.

## 3. Start the app and check basics

1. Start EDITH with `python main.py`.
2. Complete initial setup with your own API key in the local setup window. Keep the key private.
3. Open the API-key settings. Verify the panel shows the Gemini Live provider/model and also the local-agent provider, endpoint, and model read from the existing `llm_provider`, `llm_url`, and `llm_model` values in `config/api_keys.json`.
4. The local-agent connection check should run automatically. With the configured local server running and model installed, it should show the endpoint online and the configured model available. Stop Ollama (or the configured compatible server) and reopen Settings to verify it reports that the endpoint cannot be reached; then restart the server and reopen to verify recovery.
5. Click **TEST LOCAL LLM**. The test should make an actual short inference through `core.llm_client.call_llm` and show success plus response time. Check the configured model is the same one shown by the panel. If using `llm_provider=openai`, make sure the configured OpenAI-compatible server and model are running.
6. Run **TEST KEY**. The test should open a Gemini Live session, send a short prompt, wait for the first actual model output, and show the time to first response. A successful handshake without model output must not be reported as a passed test.
7. Save/reconnect only if the Gemini model-response test succeeds. The local status check must not overwrite existing local-LLM settings.

8. Confirm that the main EDITH UI opens, text input works, the microphone can be enabled/muted, the interrupt control responds, and the Activity Log remains visible.
9. Inspect the main controls and file cards: icons should render as line icons rather than emoji placeholders.
10. Close and restart EDITH normally once to check that the local configuration remains available.


### Model quality, token capacity and provider reliability

The configured model is a major quality dependency for planning, research synthesis,
tool selection and software-development tasks. A capable reasoning/coding model with
compatible tool/function calling generally handles complex workflows better than a
small or tool-incompatible model, but model strength alone does not make an external
action succeed.

Project testing showed that application-side fixes and provider reliability are both
necessary: the LLM-dependent part of a task can complete only when the provider
accepts the credential, the configured model is available, the request fits the
model's context and output-token limits, and the provider returns a response. Check
both types of token:

- The **API credential** (API key/access token) authenticates the account and must
  be valid for the selected provider/model.
- The **model token budget** must leave enough context for system instructions,
  conversation, tool schemas and relevant project/document content, with enough
  output capacity for a complete plan or generated file.

For regular multi-step use, choose a model that supports EDITH's tool/function-call
format and consider a paid provider API tier with quota appropriate to the expected
workload. Free tiers may be sufficient for experiments but can have restrictive
quotas. Paid access is not unlimited: requests-per-minute, tokens-per-minute,
model-specific caps, spending limits and provider outages can still affect service.
Verify the current limits in the provider's own account dashboard.

**API billing note:** a paid consumer chat subscription does not necessarily include API credits for EDITH. EDITH uses the selected provider's API account, so check API billing, credits and quota separately.

A successful provider check should receive an actual model response. Also test a
multi-step plan and a representative tool-assisted task. An HTTP 200 or a reachable
endpoint alone is not proof that the selected model can complete EDITH's workflow.
HTTP 429 / rate-limit / quota errors are provider-capacity failures; record the
sanitized status and retry only after the provider permits it. Do not include keys
or access tokens in test output.

Gemini Live is checked separately with **TEST KEY** because it supplies the live
voice/audio session; a successful Powerful Brain text-model test does not certify
the microphone, speaker or Gemini Live connection.

### Native glass appearance check

1. In Preferences choose **System**. Switch the OS between Light and Dark. Within two seconds, verify the header, both side panels, metric cards, Activity Log, input, existing log text and popups switch together. The center reference video should continue playing on its dark stage.
2. Open the command field's right-click menu and the provider/settings popups in each mode. Check text, selection, placeholder, disabled controls and buttons remain readable; the OS title-bar controls remain native.
3. Choose **Light** and **Dark** manually, restart EDITH, and verify the saved choice overrides the OS until **System** is selected again. Repeat with a news/content panel open and at the minimum supported window size.

## 4. Voice and identity

- Ask a harmless question and confirm EDITH answers.
- Request the female voice; verify the UI indicates the change and wait for the session to reconnect before judging the voice.
- Request the male voice and repeat.
- Ask what model/provider/engine powers EDITH. The conversational prompt asks it to respond with the product identity, **Neural Intelligence Model**. Treat this as a product-prompt behavior check, not a cryptographic guarantee that backend implementation details can never be disclosed.

## 5. Desktop app discovery and visible control

Use harmless apps first.

- Ask EDITH to list installed desktop apps.
- Search for a known installed app by name.
- Open a harmless app and check that its real foreground window appears.
- Ask EDITH to inspect the screen after launch. Verify it describes the visible app, not a guessed state.
- Try one harmless action such as scrolling or focusing a text field, and verify the screen again afterward.
- Repeat only for the OS/app combinations you actually use. Some apps may not be discoverable if they lack a standard launcher, and focus verification depends on OS permissions and available window tools.

## 6. YouTube channel search

- Ask EDITH to search for a known creator's **channel**.
- Expected: YouTube opens channel-filtered results; no video should auto-play from a channel-only request.
- Separately ask EDITH to play a specific video. Expected: the video-play action runs only for the play request.

## 7. Confirm/cancel behavior — use disposable targets only

Create a temporary test directory and a disposable text file inside your own user profile. Do not point these tests at Desktop, Downloads, a project, a database, or real work files.

For example, from Python:

```python
from pathlib import Path
import tempfile

root = Path(tempfile.mkdtemp(prefix="edith-safe-test-", dir=str(Path.home())))
test_file = root / "disposable-test.txt"
test_file.write_text("EDITH deletion test only", encoding="utf-8")
print("Temporary test folder:", root)
print("Temporary test file:", test_file)
```

Keep the printed path so you can identify the exact test target.

### A. Cancel a file deletion

1. Ask EDITH to delete only the disposable test file.
2. Verify the dialog names the correct target.
3. Choose **Cancel**.
4. Confirm the file still exists. If it disappeared, mark the test failed and stop further destructive tests.

### B. Approve a normal deletion

1. Ask EDITH to move the disposable file to the system Trash/Recycle Bin.
2. Read the dialog and confirm the correct path.
3. Choose **Confirm and Execute**.
4. Confirm the tool reports the result accurately. If the platform's Trash integration is unavailable, note the exact error; do not switch to permanent delete automatically.

### C. Permanent deletion (optional, disposable file only)

1. Create a new disposable file inside the temporary test folder.
2. Explicitly request **permanent** deletion of that exact file.
3. Check the dialog says this cannot be undone and displays the right target.
4. Choose **Cancel** first and confirm the file remains.
5. Repeat with a newly created disposable file; approve and verify that only that test file was removed.
6. Confirm EDITH refuses any attempt to delete the user-profile root.

Never test permanent deletion on a real app installation or a folder containing useful data.

### D. Close/terminate confirmation

1. Open a harmless test app (not EDITH) with no unsaved work.
2. Ask EDITH to close that named app.
3. Confirm the dialog identifies the intended target.
4. Cancel once and verify the app remains open.
5. Repeat and approve; verify the named app closes.
6. If EDITH cannot identify or verify the target window, it should stop instead of closing an arbitrary window.

### E. Outbound message confirmation (optional)

Use a test account or a consenting recipient. Ask EDITH to prepare a harmless message. Verify the local dialog displays the intended platform, recipient, and complete body. Cancel and verify no message is sent. Only repeat with approval if you are comfortable sending that exact message. Do not use a real sensitive conversation to test this.

### F. Destructive terminal command detection (optional)

Do not execute a destructive command against the real system. Test only with a disposable text editor or terminal sandbox, and cancel the confirmation dialog. Verify the dialog displays the exact command to be typed. Never approve a command that removes data, changes production resources, or affects another user's machine.

## 8. Activity Log and privacy

- Verify the log shows action start, confirmation requested/approved/cancelled, and outcome.
- Verify ordinary logs do not contain typed text, message bodies, API values, or arbitrary tool output.
- The local confirmation dialog intentionally previews the exact message/command so you can review it before execution; keep screenshots of that dialog private if it contains personal information.

## 9. Record the results

For each item mark **PASS**, **FAIL**, or **NOT TESTED**. Record OS/version, Python version, app name/version, and a short sanitized error when something fails. Do not include API keys, passwords, personal message bodies, or access tokens.

A full machine-level pass requires all relevant manual tests above to pass on the target OS. The automated CI suite alone is not a substitute for this machine-specific check.

## 10. Phase 2 — Fast Response Engine acceptance checks

**Phase 2 preserves both providers.** Gemini Live continues to handle the real-time
voice session; the configured local agent still uses the existing `llm_provider`,
`llm_url`, and `llm_model` settings. Do not replace one with the other.

### Automated tests

Run from the project root with the activated environment:

```powershell
python -m py_compile main.py ui.py core/llm_client.py core/realtime_audio.py tools/phase2_benchmark.py
python -m unittest discover -s tests -v
python tests/check_inline_js.py
```

**Pass:** all three commands succeed. The Phase 2 tests exercise the bounded audio
backlog and mocked Ollama/OpenAI-compatible text agents without internet access.

### On-device latency benchmark

1. Start your already-configured Ollama or OpenAI-compatible local server and ensure
   its configured model is available. Do not change `config/api_keys.json`.
2. Run `python tools/phase2_benchmark.py --iterations 3` on the actual PC.
   Record **first sentence** and **total** latency, without storing model output.
   First sentence is not first token. Repeat with the same local model/hardware
   settings when comparing improvements.
3. Start EDITH using `python main.py`. In the current UI's Activity Log find
   `PERF: Gemini Live session ready in ... ms`; this includes preparation
   and the cloud session handshake, not a response to a user message.
4. Send a short **text** query and look for
   `PERF: Gemini Live first audio after text request: ... ms`. This measures
   the text-send to first-audio interval, not voice-to-voice latency.
5. Open the existing API settings and run **TEST KEY**. Confirm the live model
   actually responds. Then use **TEST LOCAL LLM** to confirm real local inference
   still succeeds on the configured backend.
6. Ask a question through the microphone and verify no clipped speech, doubled
   responses, or lost words during a normal connection.
7. Test network recovery on a disposable/no-risk session. Briefly disconnect
   and restore the network and verify status/reconnection are truthful. A slow
   network may force the input queue to discard **oldest unsent audio** to limit
   stale backlog; check whether speech becomes clipped under sustained overload.
8. Test typing several short prompts, camera/screen use, remote/phone input
   (if enabled), interrupt, and local agent tool calls. Confirm the UI remains
   responsive and all existing confirmation dialogs still appear when required.

### Phase 2 completion gate

Mark **PASS** only when automated checks pass **and** the user has verified
Gemini Live, Local LLM, desktop UI, and input/reconnection on their actual
machine. Report measured before/after latency for comparable conditions;
performance improvements are not guaranteed for every device or network.
Do not start Phase 3 until the user explicitly accepts Phase 2.


## Phase 3 — Autonomous multitasking release gate

Phase 3 extends the existing EDITH UI and Gemini Live tool-response path. It does
not replace or overwrite the Ollama/OpenAI-compatible local LLM configuration,
the Gemini Live model, or the sensitive-action confirmation rules.

### Automated checks

Run the existing automated commands in section 2 from the current default-branch checkout.
The new tests in tests/test_task_scheduler.py cover four simultaneous independent
jobs, worker limits, priorities, dependency barriers, queued cancellation,
failure propagation, missing prerequisites, read-only classification, and
opt-in safe retries. These are simulated tasks, not Windows GUI tests.

### Windows UI and live-operation checks

1. Start EDITH on the actual Windows PC. The **existing UI** should be retained.
   Above Activity Log, TASKS should start at zero running and zero waiting.
   CANCEL WAITING should be disabled initially.
2. Ask for four unrelated **read-only** lookups (four distinct web searches).
   If Gemini Live emits multiple function calls in one batch, check Activity Log
   for TASKS batch entries. Running actions must never exceed four. If the model
   issues one call per turn, mark simultaneous execution **NOT TESTED** rather
   than claiming the test passed.
3. With a batch larger than the available workers, click CANCEL WAITING.
   Only jobs not yet started may be cancelled. Running actions must continue;
   the UI must not claim they were stopped or undone.
4. Use a disposable folder. Request a listing, then creation of one specifically
   named disposable folder, then another listing. The creation must happen only
   after its prerequisite work; no folder may be created twice. Do not use
   valuable files for this test.
5. Request a harmless nonexistent-file read as a prerequisite to another task.
   If the prerequisite fails, the dependent task must not run or report success.
6. Check dangerous-action confirmation dialogs on disposable targets only, as
   documented in section 7; verify that cancellation prevents execution.
7. Re-run both TEST KEY (Gemini Live) and TEST LOCAL LLM. Check that the
   provider, model, endpoint and API key settings have not changed.
8. Restart EDITH, test text/voice input and optional phone dashboard. Note any
   stuck RUNNING indicator, duplicate action or wrong-window interaction.

### Phase 3 completion gate

CI must pass AND the user must report PASS on relevant Windows tests. Do not
start Phase 4 until the user explicitly approves Phase 3.

Limitations: this phase can parallelize independent read-only tool calls within
one Gemini Live batch; it does not execute four desktop mouse/keyboard operations
concurrently, nor four independent Live conversations. When a session disconnects
during an OS action, inspect the actual outcome before attempting it again.


## Phase 4 — Original EDITH UI refinement acceptance checks

Phase 4 keeps the **existing EDITH HUD, desktop window, controls and voice
workflow**. It is not the separate dashboard concept. The UI receives only
bounded task metadata; no new cloud/local model settings are introduced.

### Automated checks

With an activated environment, run:

```powershell
python -m compileall -q main.py ui.py setup.py actions core dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
```

GitHub Actions also executes the new Phase 4 Qt smoke tests with
`QT_QPA_PLATFORM=offscreen`; these exercise the real PyQt6 window without
requesting audio hardware or connecting to Gemini/Local LLM.

### Windows visual and accessibility verification

1. Run EDITH normally from the **same** current default-branch checkout. Confirm
   the recognizable original HUD, existing colors, title, microphone control,
   file upload, Activity Log, quick drawer, and voice controls are unchanged.
2. Resize the window to its minimum size. Check neither side panel overlaps
   the HUD or input, and camera preview (if used) stays aligned to the HUD.
3. Click inside another control, then press **Ctrl+K**. The command text field
   should receive focus. Type a draft; press Ctrl+K again and verify its text
   is selected, not silently submitted. **Enter** still sends messages.
4. In Controls, turn on **REDUCED LOG ANIMATION**. Trigger several harmless
   responses/Activity Log entries. Lines should appear quickly, the interface
   should not freeze, and the toggle should survive restarting EDITH. Disable
   it to retain the original animated style (now batched for speed).
5. Above Activity Log, the existing **TASKS** count and **CANCEL WAITING**
   must remain. Before tasks start, the details icon is disabled.
6. Start a harmless read-only batch (for example, unrelated web searches).
   Click the details chevron after tasks have been queued; observe up to four
   current/recent status labels (**RUNNING**, **QUEUED**, **SUCCEEDED**,
   **FAILED**, etc.). The view does **not** invent percentages and should
   reflect the true Task Scheduler.
7. Test a queued cancellation only, verifying running actions continue.
   Close and reopen task details; the original Activity Log must remain usable.
   Run several batches and verify the UI remains responsive and does not
   continuously expand its log history without bound.
8. Test a short microphone conversation, one local LLM inference and
   Gemini Live TEST KEY again. Check both providers' settings/behavior are
   unchanged and confirmations still appear for sensitive actions.
9. If optional phone/remote dashboard is used, confirm the desktop UI
   updates have not changed its access or pairing protocol.

### Phase 4 completion gate

The Phase 4 automated suite and Qt offscreen smoke tests must pass, and the
user must verify the visual layout and usability on their own Windows PC
before declaring Phase 4 **100% complete**. Do **not** begin Phase 5 before
that explicit approval.


## Phase 5 — Cross-device and network acceptance checks

This phase keeps the original EDITH desktop and mobile UI, the existing
Gemini Live session, and the already configured local LLM. It does not add a
public-internet relay, replace the authentication/encryption protocol, or
create a new branch.

### Automated tests

Run in your active project environment:

```powershell
python -m compileall -q main.py ui.py setup.py actions core dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
```

The GitHub Actions workflow also runs Phase 5 HTTP/WebSocket tests with
FastAPI and its TestClient installed. Tests check authorized session probes,
WebSocket heartbeat ping/pong, stable replay IDs, and refusal to queue remote
commands while Gemini Live is disconnected. Passing CI does not prove that
your phone and Windows networking function together.

### Windows PC and phone testing (trusted LAN only)

1. Update the current default branch, activate the same Python environment used
   in Phase 1, and start EDITH. Do not modify `config/api_keys.json` or
   re-enter previously saved credentials just to test this phase.
2. Connect the phone to the PC's **trusted local Wi-Fi/LAN**, open Remote
   Control, pair with the existing code/QR flow and confirm the remote page
   still looks familiar and reports a truthful connection status. Do not port
   forward EDITH or expose its dashboard to public internet.
3. Send a harmless text query. Confirm it appears in the phone chat only
   after an accepted HTTP response and produces a real result on the desktop.
   Verify API settings and local-agent settings remain untouched.
4. Briefly disconnect the phone from Wi-Fi, reconnect to the same network,
   and observe the phone page **without manually refreshing**. It should
   report lost/reconnecting state, then recover automatically. Verify old
   received messages and file cards are **not duplicated** after replay.
5. Try a harmless command while disconnected. The draft must not disappear
   or be silently resent later. After reconnect, inspect EDITH first to
   ensure it did not run; if delivery was unconfirmed, manually decide
   whether resending is safe. Never use a destructive command for this test.
6. Check browser pairing after a temporary network outage. It must remain
   saved; an explicit invalid/expired pairing code can still ask for a new
   code. A full EDITH server restart can invalidate in-memory pairing and
   legitimately require a new QR login.
7. Test remote phone audio with a short, harmless request. If network
   throttling is available in your test tools, try a slow connection:
   audio must not build a long delayed backlog. Some words may be dropped
   during severe congestion—note these as limitations rather than success.
   Check that the phone microphone releases after disconnecting.
8. Upload a disposable non-sensitive file from the phone. Verify successful
   upload on the PC. With the network interrupted, verify an upload failure
   shows an error rather than claiming success; retry manually only.
9. Keep the phone page open and trigger many harmless log updates. The page
   should remain responsive on the device. The UI still shows the original
   EDITH theme and supports narrow phone screens.
10. Repeat separate **TEST KEY** for Gemini Live and **TEST LOCAL LLM**.
    Neither the cloud API key nor `llm_provider`, `llm_url` and `llm_model`
    should have been overwritten by this phase.

### Phase 5 completion gate

Mark each relevant test **PASS**, **FAIL** or **NOT TESTED**. Complete
Phase 5 only when GitHub CI is green **and** you confirm the real Windows
and phone checks. Do not start Phase 6 before this approval. A private VPN
can make a trusted remote path reachable from elsewhere, but arbitrary
internet access is not guaranteed or implicitly enabled.

## Phase 6 — Agent execution reliability release gate

**Do not mark Phase 6 complete based only on CI.** Complete the on-device
checks below, then approve Phase 6 explicitly. Use the current default-branch checkout for these checks; do not mix unrelated
feature work into the test run. Preserve both Gemini Live and
the existing local Ollama/OpenAI-compatible agent settings.

### Automated checks

Run from the repository root in the activated Python environment:

```powershell
python -m compileall -q main.py ui.py setup.py actions core dashboard memory plugins tests config tools
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
```

Verify `tests/test_phase6_reliability.py` passes. It tests same-ID duplicate
suppression, conflicting IDs, privacy-safe SQLite history, restart recovery,
bounded storage, truthful side-effect receipts, and cancellation dependencies.
These are mocked/local tests; they cannot confirm actual Windows GUI results.

### Windows and live-provider verification

1. Update the current default branch, install dependencies into the selected
   Python environment, and run `python -m core.startup_check`.
2. Run `python main.py`. Confirm the **original** EDITH UI, name, icon,
   microphone, text input, settings and desktop shortcut all work as before.
3. Test **TEST KEY** (Gemini Live) and **TEST LOCAL LLM** separately. The
   previously selected `llm_provider`, `llm_url`, `llm_model` and
   `gemini_api_key` must still work without being overwritten.
4. Use a harmless, disposable directory. Ask EDITH to create one folder and
   verify it exists independently in Explorer. A successful tool receipt alone
   does not prove the folder exists. Ask for task status/history: EDITH should
   show task names and states without displaying original paths or file data.
5. Ask EDITH to prepare a harmless outbound message to a test recipient. Choose
   **Cancel** in the local confirmation dialog. Confirm that the message was
   **not sent** and cancellation is not presented as successful delivery.
   Do not approve a real external send merely to check this.
6. With a disposable read-only lookup running, close/restart EDITH to test
   interrupted history. The previous queued/running task should be reported
   as **interrupted**, never automatically resumed. Do not terminate EDITH
   during a file write, message send, deletion or other side effect.
7. Inspect `memory/agent_history.sqlite3` using a local SQLite viewer or
   Python. The only saved columns must be task ID, tool name, status,
   verification, duration and timestamps. No API key, path, message body or
   raw tool output should appear. This private local file is not committed.
8. Repeat a harmless read-only lookup and verify the app still responds,
   cancellation of queued work still works, and a fresh user command is not
   mistaken for an automatic replay.
9. Test Local LLM planning/coding workflows and the Gemini Live voice session
   again. Phase 6 cannot be marked complete if either provider regresses.

### What is verified and what is not

Duplicate detection applies to repeated **model function call IDs during the
same EDITH process**. It does not deduplicate unrelated new user commands
or guarantee exactly-once delivery across OS crashes/external services.
A tool-reported success is not independent proof of an external side effect;
the follow-up observation must still be performed where possible.

**Gate:** report PASS/FAIL for startup, both model paths, harmless file action,
cancelled message, history privacy, crash recovery and normal UI behavior.
Do not claim Phase 6 is 100% complete until the user approves the on-device
results. Do not store or send any private API keys or message contents in logs.


## UI-only voice input feedback (post-phase UX upgrade)

This is a display-only audio meter; it shows captured PCM activity, **not** proof
that Gemini transcribed, received, or understood an utterance. It does not
record or save microphone samples.

1. Start EDITH normally on Windows; grant microphone permission and select
   the correct input device if prompted. The existing UI layout remains intact.
2. With no microphone stream yet, the HUD should say **WAITING FOR MIC AUDIO**.
   When the PC microphone is streaming silently, it should say
   **PC MIC RECEIVING** and show a low or flat waveform.
3. Speak near the microphone. The HUD should change to **PC AUDIO DETECTED**
   and show a stronger waveform plus responsive green orbital heartbeat.
   Speaking more loudly should generally increase meter intensity.
4. Stop talking; the green heartbeat should decay. Disconnect the mic or
   stop its stream: after a short timeout the HUD must stop claiming input.
5. Mute the mic; the HUD must show **MIC MUTED** and no input heartbeat.
   Unmute and verify the input meter recovers.
6. While EDITH plays its reply, the original **SPEAKING** output visual remains
   dominant and microphone input does not masquerade as user speech.
7. If you use the remote phone microphone, verify **PHONE MIC RECEIVING**
   and **PHONE AUDIO DETECTED** while the phone streams audio. A dropped phone
   stream must not remain marked as active indefinitely.
8. Resize the EDITH window and drag the HUD splitter to its minimum height.
   Confirm the status and waveform remain visible and animation is responsive.
9. Verify normal text input, file uploads, Gemini Live test, Local LLM test,
   task scheduler, and desktop-action confirmation still work as before.

Automated checks: run \`python -m unittest discover -s tests -v\` and
\`python -m py_compile main.py ui.py core/audio_meter.py\`.
Record PASS/FAIL and relevant device/microphone details, never voice contents
or keys. Windows audio-driver testing cannot be replaced by CI.


## Cross-platform and hardware compatibility gate (Windows, macOS, Linux)

The portable-core GitHub Actions matrix now runs SQLite-journal, task-scheduler,
and audio-failure regression tests on all three OS families. These are simulated
hardware checks and do **not** prove that a physical microphone, speaker, camera,
GPU, window manager, or remote phone works on every device.

On **each real machine**, from the activated virtual environment run:

```bash
python -m core.startup_check
python -m core.hardware_check
python -m unittest discover -s tests -v
python main.py
```

Read the hardware report without posting private configuration. It checks whether
the **default** microphone can accept mono 16 kHz PCM16 and the default speaker
can play mono 24 kHz PCM16, the existing Gemini Live voice formats. If an audio
device is absent or does not support the needed rate, EDITH now keeps text and
remote interaction alive and periodically retries the audio device. This does
**not** resample incompatible hardware automatically; use a compatible device
or OS audio configuration before declaring voice support as passed. Hot-plug a
test microphone/speaker, recheck logs and verify the live audio actually works.

OS-specific manual checks:
- **Windows:** Confirm normal DPI scaling and taskbar icon on 100%, 125%, and
  150% display scaling where available; test OneDrive Desktop shortcut handling,
  microphone privacy permission, speaker unplug/replug, and Bengali text. Qt
  DPI-awareness or OpenType warnings alone do not mean the app failed if GUI
  and text/audio functions work normally. A wrong-size/clipped UI or missing
  glyph is a real FAIL and should be reported with a screenshot.
- **macOS:** Test Apple Silicon and Intel only where machines are available.
  Check Microphone, Accessibility, Screen Recording and Camera permissions;
  verify default audio formats and that window focus/action results are honest.
- **Linux:** Distinguish X11 from Wayland. Some global screen, keyboard, mouse,
  window focus, capture and desktop-control operations are restricted by
  Wayland compositors. Do not claim unsupported actions completed. Check ALSA/
  PulseAudio/PipeWire audio devices, installed display/fonts and screen portal.
  A headless Linux server does not provide a functional graphical desktop.

CPU-only systems remain eligible for the local provider if the selected model
fits RAM and its inference server supports the CPU. GPU acceleration is
**optional**, not presumed; NVIDIA/AMD/Intel GPU support depends on drivers,
runtimes and the chosen LLM backend. Cloud Gemini Live still requires network
access and a valid API key. These two modes remain separate; do not alter
`gemini_api_key`, `llm_provider`, `llm_url` or `llm_model` while testing.

A portability PASS requires working real hardware and explicit user approval
on each OS/device class of interest. A green CI matrix is only a baseline.

## Release gate — local-device bridge and latency evidence

Run this only on a machine you own or are authorized to administer. It verifies
local operating-system capabilities; it does not test remote machines, scan a
network, or authorize security assessment tooling.

1. Start EDITH and ask for local system information, telemetry, network
   interfaces, open windows and installed applications. Unsupported capability
   must be shown as unavailable/N/A rather than invented.
2. After one text request and one harmless tool request, ask for **performance
   metrics**. Record `live_connect`, `text_to_first_audio` and `tool.*` sample
   counts/p50/p95 alongside OS version, provider and network type. They are
   observed measurements on that machine, not a speed commitment.
3. For a Tier 2 control, request a harmless volume change, cancel the local
   confirmation, and verify the setting did not change. Repeat only when you
   approve the displayed value. For Tier 3 power, cancel the dialog; do not
   approve shutdown or restart merely to complete this checklist.
4. Only with a disposable non-system process and its verified exact PID, test
   termination. Never target EDITH, a shell, a service or an unknown process.
5. Press **Interrupt** during a confirmed long-running owned test command and
   verify cancellation is reported instead of success. Never substitute an
   arbitrary system command for this test.

Report PASS/FAIL/NOT TESTED for every target OS with sanitized errors only.
Release remains pending until target-device results and GitHub CI are green.

