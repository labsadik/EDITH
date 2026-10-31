# Local LLM, Vision and Voice Options

EDITH supports a hybrid design: use hosted AI for the features that benefit from a
large provider model, use local models for workloads your computer can handle, or
combine both. Local inference is an advanced option whose quality and speed depend on
the selected model, runtime, installed dependencies and available hardware.

## Recommended everyday configuration

For most users, the simplest starting point is:

- **Gemini Live for integrated real-time voice and visual interaction.** The current
  screen/camera analysis path captures an image on the local computer and sends it
  through the Gemini Live session for interpretation and spoken response.
- **A hosted Powerful Brain provider for text reasoning and agent work.** Choose a
  model with strong reasoning/coding ability and support for the tool/function-call
  format EDITH uses. Keep the provider credential, account quota and token limits
  healthy; see the LLM guidance in the root README.

This hybrid setup avoids requiring a large local GPU while retaining the local
desktop tools, workspace and sandbox. Gemini Live and Powerful Brain are separate
provider paths, so test them separately.

## Local text LLM

The current text-model client supports:

- **Ollama:** native local API, normally at `http://localhost:11434`. EDITH can check
  whether the service is running and try to start `ollama serve`.
- **OpenAI-compatible local servers:** examples include LM Studio, Jan, LocalAI and
  llama.cpp server. Configure the local server endpoint and the exact model identifier
  it exposes. The server must be started on the computer before EDITH can connect.

Use **Controls → API Providers → Powerful Brain** and select the local provider/server
profile. For a local OpenAI-compatible server, use its local endpoint and model ID.
A local-only endpoint normally does not need a cloud API key. Download the model and
any required runtime files first; after that, local text inference can run without
sending those prompts to a hosted LLM provider.

For agents and software development, choose a local model that supports the expected
tool/function-call format and can return a normal final answer. A model that can chat
but cannot make compatible tool calls may answer ordinary questions while failing
agent delegation or tool-assisted coding. Test a real response, a multi-step plan and
a harmless tool call before relying on it.

## Local Voice: Speech-to-Text and Text-to-Speech

The source includes optional local speech engine implementations:

| Task | Local engine | Runtime behavior |
| --- | --- | --- |
| Speech-to-Text (STT) | faster-whisper / Whisper | Runs locally after the speech model has been downloaded and cached. It prefers CUDA when available; otherwise it can use CPU with an integer compute mode. |
| Speech-to-Text (STT) | Vosk | Offline streaming recognition using a locally installed Vosk language model. |
| Text-to-Speech (TTS) | Kokoro | Local neural speech generation after its model has been downloaded and cached. It prefers CUDA when available and can fall back to CPU. |

Other TTS choices are not fully local: **Edge TTS** requires an internet connection,
and **ElevenLabs** uses a cloud API and API key.

These STT/TTS engines are separate building blocks; they are not the same thing as a
single integrated, full-duplex conversational voice model. EDITH's current primary
real-time conversation and audio transport remains **Gemini Live**. Installing a
local STT or TTS package does not by itself switch the whole live conversation to a
fully local voice pipeline. Check the relevant configuration/integration before
assuming that every voice interaction is offline. Optional engines and model files
are not all installed by the base `requirements.txt`.

## Local Vision and multimodal models

A local vision-language model (VLM) can, in principle, interpret screenshots, camera
frames and images on the computer without sending those images to a cloud provider.
It must be a genuinely multimodal model with image-input support, and the local model
runtime must expose an image-capable API.

**Current EDITH status:** the application can capture the screen or webcam locally,
but the existing `screen_process` image-analysis path sends the captured image into
the Gemini Live session. The Powerful Brain text LLM route is not currently a
selectable local VLM backend for that screen/camera workflow. Configuring a text-only
Ollama model or a local OpenAI-compatible text server therefore does not make screen
and camera understanding local.

To offer fully local visual analysis, EDITH needs a compatible local VLM plus an
image-routing adapter that sends the captured image and question to that local
multimodal endpoint and handles its response. Treat this as a hardware-ready
extension path, not as a feature that is automatically enabled by selecting Ollama.

## Hardware planning

Local model capacity is primarily a memory and compute decision:

- **GPU VRAM** determines how much of a model can be loaded and accelerated on the
  GPU. Larger models, higher-precision weights, longer context windows and concurrent
  requests generally need more memory.
- **System RAM** matters for CPU inference, partial GPU offload, model loading and
  the operating system. A CPU can run smaller/quantized models, but response speed
  may be slower.
- **Quantization** reduces model memory requirements and can make local models fit
  on ordinary hardware; there may be a trade-off in output quality or capability.
- **Vision models** add image-processing and visual-token memory costs. A local VLM
  may need substantially more memory than a similarly sized text-only model.
- **GPU acceleration** depends on the installed runtime and compatible drivers.
  The local Whisper and Kokoro code paths detect CUDA where available and otherwise
  have CPU paths; actual speed varies by device, model and workload.
- **Storage and network** are needed for initial model downloads. Model weights,
  embeddings and caches can occupy several gigabytes depending on the choices made.

Do not choose a model by parameter count alone. Check its actual memory requirements,
quantization, context window, supported languages, tool-call compatibility and
benchmark results on the target device. A smaller model that fits comfortably and
returns reliable tool calls can be more useful than a larger model that constantly
runs out of memory or responds too slowly.

## Privacy, offline use and trade-offs

- Local text inference can keep prompts on the local machine when the endpoint is
  truly local and no external tool/provider is called.
- Local STT/TTS can reduce dependence on hosted speech services after all required
  models are cached.
- Initial model downloads, package installation and model updates require internet
  unless the assets have already been obtained.
- Local inference is not automatically private if a configured endpoint points to a
  remote server. Verify the endpoint host before using sensitive material.
- Local models do not remove EDITH's tool policy, permissions or Rust sandbox. Model
  output is not authorization to perform an action.
- Cloud models may still be preferable for high-end reasoning, long-context tasks or
  reliable tool calling when local hardware is insufficient.

## Practical selection

| User setup | Suggested approach |
| --- | --- |
| Typical laptop or desktop | Gemini Live for integrated voice/vision plus a hosted Powerful Brain provider; use a small local text model only where it performs adequately. |
| Desktop with capable GPU and sufficient RAM/VRAM | Run a local Ollama or OpenAI-compatible text model for private/offline text tasks; retain Gemini Live for the current integrated vision/voice path if needed. |
| High-end workstation | Use larger local reasoning/coding models and local speech engines; a local VLM can be added once EDITH has a local image-routing adapter. Keep a hosted provider available as a fallback for tasks beyond local capacity. |
| Fully offline requirement | Local text inference, cached local Whisper/Vosk and Kokoro can provide local building blocks. The current integrated Gemini Live voice and screen/camera visual-analysis path is cloud-dependent, so a fully offline end-to-end voice/vision setup is not yet provided by the current default pipeline. |

See [README.md](../README.md) for the general provider setup and
[TESTING.md](../TESTING.md) for local device checks.
