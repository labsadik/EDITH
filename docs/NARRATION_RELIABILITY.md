# Narration reliability

This reliability work preserves the existing UI and bundled visual; it does not introduce a layout redesign.

## Why speech could skip

The receiver split generated PCM into 50 ms slices and put them into the same
drop-oldest helper used for microphone upload. Its 120-entry output queue retained
only about six seconds. Bursty/long responses could silently replace earlier words.
Audio arriving before the output stream was ready was also discarded.

The receive coroutine additionally awaited complete tool batches inline. A long
tool could prevent subsequent audio/control packets from being consumed. Playback
submitted each batch to a shared executor and ignored PortAudio's underrun result.
The startup briefing also guessed when playback ended using a fixed delay after
model generation completed, rather than waiting for actual speaker drain.

These are verified code defects; they do not prove that every audible gap on a
particular device had the same cause.

## Implementation

- Keep microphone upload bounded with its existing freshness policy. Generated
  narration has a separate thread-safe PCM FIFO with a 14.4 MB pending-byte budget
  (five minutes at 24 kHz mono PCM16). Overflow is reported as an error, never
  handled by silently replacing earlier speech. Odd packet boundaries are joined
  correctly; an incomplete final sample is explicitly rejected.
- A dedicated output thread owns the PortAudio stream and writes at most 50 ms at
  once. Host-selected block size and the device's high-latency preset favor stable
  playback. Initial and underrun recovery prefill is 150 ms; a finished short tail
  plays without waiting for that threshold. Prolonged network starvation can still
  cause silence, but retained speech stays ordered and is not skipped or replayed.
- A serial tool worker retains existing batch scheduling and approval behavior.
  The receive coroutine keeps consuming audio and control events during tools.
  Both workers belong to the session lifecycle; reconnect does not replay queued
  tool requests. Existing running-action journal/cancellation semantics remain.
- Microphone packets already queued when playback begins are suppressed to reduce
  assistant echo triggering the provider's interruption detector. Explicit local
  and provider interruptions invalidate queued narration and abort the old native
  playback buffer. A new turn can then play normally.
- Keep Speaking active through device drain, publish real PCM output levels, and
  report underruns, buffering and device failures. Speaker failures leave text and
  remote controls alive and retry automatically. Speech accumulated during a device
  outage is intentionally cleared, with a recovery notice, instead of being replayed
  minutes later. No automatic replay follows a failed write, which might otherwise
  duplicate partially spoken words.
- Startup news waits for model turn completion, an empty PCM queue and a drained
  output device. An interrupted/timed-out greeting or changed session skips stale
  news delivery. Session teardown requests writer shutdown with a bounded wait.

## Verification

Automated regressions cover byte-identical output for a 10.67-second burst, odd
packet boundaries, jitter and final tails, explicit overflow, native-buffer abort,
underrun without replay, device recovery without stale speech, actual runtime
status publication, audio receive during a blocked tool, ordered tool responses,
stale microphone suppression, and narration boundaries across interruption/reconnect.
They use synthetic PCM and fake devices/sessions; they do not measure live provider
latency or certify physical audio hardware.

On the target device, restart the app after pulling and test:

1. Ask for a continuous two-minute explanation, then a longer multi-part explanation.
   Check for missing/repeated words, especially when tools run mid-response.
2. Start a task that speaks progress while a tool runs. Check that progress audio
   continues and Working/Speaking reflect actual activity.
3. Interrupt via the existing control, then request another response. Cancelled
   speech must not resume. Voice-only approval/stop is a later stage.
4. Verify the greeting finishes before startup news begins.
5. Disconnect/reconnect a speaker. Text must remain usable and old speech must not
   replay on recovery. Test both the default output and any Bluetooth headset.
6. If gaps remain, capture the `AUDIO:` and `PERF:` log lines with OS/audio-device
   details. Provider interruptions, network starvation and driver underruns need
   different follow-up fixes. Avoid sharing API keys or private transcripts.

## Next implementation gates

1. Validate this audio change on the owner's device and address reproduced failures.
2. Implement explicit task lifecycle and voice input routing for stop, approval and
   clarification during a job; verify multi-step completion and cancellation.
3. Add voice approval bound to one pending action/target, with expiry and rejection
   handling; keep existing confirmation until the replacement is verified.
4. Add independently configured provider adapters and capability-based audio paths,
   retaining Gemini and existing Ollama configuration. Test real responses/tools
   for each provider before declaring support.
5. Add structured memory and authorized OS/device/monitor diagnostics incrementally,
   with real capability reporting and post-action verification.
6. Run target-platform, network-failure and performance tests. Merge to `main` only
   after the owner tests the branch and explicitly requests the merge.
