# EDITH — Final Full-Stack Acceptance Tests

Run these checks after updating main. CI tests and local preflight are separate from the final tests that require the owner's API key, microphone, speaker, Ollama, browser profile, Home Assistant or MQTT broker.

## 1. Update and install

From the repository root on Windows PowerShell:

~~~powershell
git status
git switch main
git fetch origin
git pull --ff-only origin main

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cargo --version
cargo build --release --manifest-path sandbox-rs/Cargo.toml
.\sandbox-rs\target\release\edith-sandbox.exe --version

python -m compileall -q main.py ui.py setup.py actions core agents dashboard memory plugins tests config tools scripts
python -m unittest discover -s tests -v
python tests/check_inline_js.py
node tests/check_phase5_js.js
node tests/check_workspace_js.js
~~~

Linux/macOS use git switch main, python3 -m venv .venv, activate with source .venv/bin/activate, then run the same pip/compile/unittest/Node commands. Build the Rust binary with cargo build --release --manifest-path sandbox-rs/Cargo.toml; on Linux verify bwrap --version, on macOS verify command -v sandbox-exec.

## 2. Device preflight

Run the read-only check first:

~~~powershell
python scripts/edith_preflight.py
~~~

It reports the configured Main/Powerful Brain profiles, presence (never the value) of Gemini credentials, current Kore/Orus voice setting, microphone/output-device enumeration, WebEngine, LangChain/LanceDB, LangGraph, agent registry, Ollama embedding model, Home Assistant and MQTT pairing, Rust helper and startup-news preference.

Optional hardware/live checks are explicit because they use the actual devices and account:

~~~powershell
python scripts/edith_preflight.py --run-sandbox-test
python scripts/edith_preflight.py --live-voice-test
python scripts/edith_preflight.py --record-mic-test --seconds 2
python scripts/edith_preflight.py --speaker-test
~~~

--live-voice-test sends a short test prompt to Gemini Live using both Kore (female) and Orus (male) and checks that audio output is received. --record-mic-test records up to five seconds, computes a signal level and does not save the recording. --speaker-test plays a short tone. Run these only when you are ready to use the microphone, speaker and API quota. Missing Ollama, Home Assistant or MQTT is shown as a warning, not hidden as a pass.

## 3. Powerful Brain and provider routing

In EDITH → Controls → API Providers:
1. Select the Main Brain provider, load/select a model, run Test, then Save.
2. Separately configure Powerful Brain, run Test, then Save. Confirm Main and Powerful profiles have the intended independent provider/model/credential.
3. Ask EDITH a normal factual question, then ask it to produce a multi-step implementation plan. The second request should use Powerful Brain.
4. Do not paste API keys into chat or Activity Log. Use the settings UI; it stores secrets via EDITH's credential helper.

## 4. Agents and LangGraph supervisor

Ask EDITH: "list agents and versions". Confirm each built-in specialist has a version/status. Disable one non-critical agent in Plugins → Agents, confirm it is disabled, then enable it again.

Ask: "Use the multi-agent supervisor to plan a secure notes app with tests and acceptance criteria." Confirm the supervisor retrieves local context when available, creates bounded specialist tasks, and returns one synthesized answer. It must not claim it changed files or devices. CI now has deterministic LangGraph graph-path tests; this owner test checks your configured Powerful Brain account.

## 5. LangChain + local RAG + persistent LanceDB

Install/start Ollama, then:

~~~powershell
ollama pull nomic-embed-text
ollama list
~~~

Create a harmless test file named edith-rag-test.md containing a unique sentence, for example: "EDITH-RAG-CHECK-2026: the blue comet stores notes locally."

Ask EDITH to index that file into the local knowledge base (approve the local indexing prompt), then ask: "Search my local knowledge for EDITH-RAG-CHECK-2026 and quote the matching test sentence." Confirm the correct filename/source and text are returned. Exit and restart EDITH; repeat the search. The same entry should still be present after restart. Delete only the disposable test file when finished; remove the test record from the local vector database only using a documented index-management operation (do not delete the entire database to clean up one test).

## 6. Embedded browser

Ask EDITH to open https://example.com in embedded mode. Then test:
- get_url and get_text return the current page URL and visible text.
- Click the visible "More information..." link by a unique visible label or CSS selector, then confirm the URL changes.
- Navigate back, forward and reload.
- On a disposable test page with a non-sensitive form, use type or fill_form with CSS selectors. Verify values are populated but not submitted.
- Resize the embedded browser, close it, reopen it and confirm the persistent browser profile directory still exists.

Do not use real login credentials in automation tests. Persistent browser cookies are sensitive: only sign in to accounts you intend to keep signed in on this device.

## 7. Smart Network — Home Assistant and MQTT

**Home Assistant:** pair the intended local HA instance using python scripts/configure_home_assistant.py. Ask EDITH to list entities and read one harmless test entity. For writes, use a disposable test light/switch: ask EDITH to change it and confirm the local approval dialog names the exact entity/service before approving. Reject a write once and verify the state does not change.

**MQTT:** install paho-mqtt (included in requirements) and pair only a broker and exact test topic that you control:

~~~powershell
python scripts/configure_mqtt.py --broker mqtts://YOUR-BROKER:8883 --username YOUR-USERNAME --topic edith/test
~~~

The password is requested through a hidden prompt. On a private trusted LAN only, mqtt://192.168.x.x:1883 may be used. Public/remote brokers must use mqtts:// TLS. Ask EDITH for MQTT status, then read from the exact test topic. Publish hello to that disposable test topic: a local confirmation must appear, publish is QoS 1 and non-retained. Confirm an unpaired topic is rejected. Never point the tests at a production control topic such as a garage door, lock or alarm.

## 8. Rust sandbox

Run the optional sandbox preflight:

~~~powershell
python scripts/edith_preflight.py --run-sandbox-test
~~~

Confirm it prints EDITH_SANDBOX_OK from the isolated child process. The Python bridge provides three resource presets: safe, standard, and build; all cap timeout, CPU and memory and default to network denied. Run a disposable project build through the EDITH development agent and confirm it runs within the workspace using its own .venv. If the native Rust helper or OS backend is unavailable, execution must fail closed; it must never fall back to the host shell.

Do not use a production project or valuable folder for this test. CI compiles the Rust helper for Windows, macOS and Linux, but only this local run can verify the actual machine's AppContainer / Seatbelt / bubblewrap policy.

## 9. Microphone and female/male voice

Run the opt-in tests:

~~~powershell
python scripts/edith_preflight.py --record-mic-test --seconds 2
python scripts/edith_preflight.py --speaker-test
python scripts/edith_preflight.py --live-voice-test
~~~

Then start EDITH and say each command distinctly:
- "Switch to female voice."
- "Switch to male voice."
- "মেয়েদের কণ্ঠে কথা বলো।"
- "পুরুষ কণ্ঠে কথা বলো।"

After each change, wait for a new PERF: Gemini Live session ready and SYS: Assistant ready, then listen to EDITH's confirmation. If speech recognition produces a garbled sentence, repeat using the text input with the exact command. Voice preference should still save when the Live session is reconnecting; ordinary text chat still requires the Live session to be connected.

The preflight Live test checks Gemini's Kore/Orus audio output; the separate microphone test checks local capture. Passing them does not establish that every accent/noisy-room transcription will be perfect.

## 10. Startup news and MCP plugins

On a clean config, startup news should be OFF. If the owner explicitly enables it, that saved preference should remain ON after restart. The plugin discovery log confirms only that endpoints were discovered; separately test each enabled MCP connector with a harmless read-only operation and verify its own authentication/permissions.

## Report results

Record the preflight output and test command outcomes. Do not paste credentials, browser cookies, MQTT passwords, HA tokens, raw private documents or private microphone recordings into GitHub issues or chat. A CI pass proves deterministic tests/builds; live integrations must pass on the computer and accounts where EDITH will be used.
