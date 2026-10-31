# Local LLM, hardware and multimodal use with EDITH

EDITH supports a hybrid AI setup: keep the integrated cloud services for the workflows where they are currently strongest, and use a local model when the computer has enough memory and acceleration. Local and cloud are options, not competing product editions.

## Recommended setup for most users

The recommended starting point is:

- **Gemini Live** for EDITH's current real-time voice/audio conversation and the current screen/webcam vision session.
- **Powerful Brain** connected to a capable hosted text/reasoning provider such as OpenAI, Anthropic Claude, Groq or xAI, selected in **Controls → API Providers → Powerful Brain**.
- A provider/model with reliable reasoning and tool/function calling, sufficient context/output capacity and an API quota that fits the expected workload.

This avoids requiring a powerful local GPU, downloading model weights or tuning local inference before EDITH can be used. It still depends on internet access, valid provider credentials, API billing/quota and provider availability. Gemini Live credentials and Powerful Brain credentials are separate settings.

## When a local LLM makes sense

Choose a local model when you want more control over where text prompts are processed, prefer not to send that text to a hosted text-model API, have a capable computer, or want to avoid per-request cloud text-model charges. Local inference has no per-token provider bill, but it uses your own hardware, electricity, memory and storage. Model downloads and updates still need internet access.

EDITH's current **Powerful Brain** text path supports:

- **Ollama (local):** the native Ollama chat API, normally at `http://localhost:11434`.
- **OpenAI-compatible local servers:** for example LM Studio, Jan, LocalAI, llama.cpp server or vLLM, provided the selected server exposes a compatible chat/tool-call API. A common LM Studio endpoint is `http://localhost:1234/v1`.

In EDITH, open **Controls → API Providers → Powerful Brain**, select the local provider, set its endpoint and exact model identifier, then run the real response test before saving. A local endpoint on the computer does not need a cloud API key. OpenAI-compatible compatibility does not guarantee that every model supports tool/function calls: choose a model that supports the schema EDITH sends and test an actual agent/tool workflow.

### Quick Ollama setup

1. Install Ollama from the [official download page](https://ollama.com/download).
2. Check the machine's GPU and memory against the [Ollama hardware support guide](https://docs.ollama.com/gpu).
3. Choose a text model from the Ollama model library and download it. Replace the placeholder with the exact model name:

```bash
ollama pull <MODEL_NAME>
ollama list
```

4. Confirm the Ollama service is running, then configure EDITH's Powerful Brain provider as **Ollama**, endpoint `http://localhost:11434`, and the downloaded model name.
5. Run the provider's real response test. Then test a multi-step plan and a harmless tool-assisted task. A successful short chat does not by itself prove the model can follow EDITH's tool schema.

For an OpenAI-compatible local server, start the server in its own application, load a model there, copy its local API endpoint and model identifier into the Powerful Brain settings, and run the same tests.

## Hardware: how to decide whether the computer is powerful enough

There is no single RAM or VRAM number that guarantees a good experience. The answer depends on model size, quantization, context length, image/audio modality, number of concurrent requests and the backend's hardware support.

| Hardware factor | Why it matters |
| --- | --- |
| **GPU VRAM** | The main constraint for keeping model weights and the inference cache on a discrete GPU. More available VRAM can let you run a larger model, a larger context or more work without moving layers back to system memory. |
| **System RAM / unified memory** | Needed for CPU inference, model loading and partial GPU offload. Apple silicon uses unified memory and Ollama supports Apple GPU acceleration through Metal. |
| **GPU model and driver** | NVIDIA, AMD, Intel and Apple acceleration depend on the exact backend, GPU generation and installed driver/runtime. Check the current backend compatibility list rather than assuming every GPU is accelerated. |
| **CPU** | Affects CPU-only inference and any model layers that cannot stay in GPU memory. CPU inference is possible but larger models can be slow. |
| **Context length** | A longer context uses additional memory. Agent plans and code tasks need room for system instructions, tool definitions, conversation and project context. The Ollama guide recommends at least 64K context for large-context work such as agents and coding tools, where the hardware can support it. |
| **SSD capacity and speed** | Model files can occupy substantial disk space. Keep enough free space for model downloads, caches and updates. |

A practical guide:

- **Entry-level or laptop hardware:** use the cloud recommendation for demanding coding, multi-agent and long-context tasks. A small quantized local model may still be useful for simple private text tasks, but expect slower replies or reduced reasoning quality.
- **A capable desktop/laptop with a supported GPU and sufficient memory:** try a quantized local text model for everyday reasoning and keep Gemini Live or a hosted provider available for heavier tasks.
- **A workstation with generous VRAM/RAM and a supported accelerator:** larger local models, longer context and more simultaneous local workloads become more practical. Benchmark the exact model and workload; high hardware specifications do not automatically make a weak or tool-incompatible model better.

After loading a model, run `ollama ps` and inspect the **PROCESSOR** and **CONTEXT** columns. This helps confirm whether the model is actually using the GPU or being offloaded to CPU, and what context has been allocated. Increasing context or running several requests in parallel increases memory use. See the official [Ollama context-length guide](https://docs.ollama.com/context-length).

## Local voice: speech recognition and speech output

A local text LLM does not automatically provide a complete microphone-to-voice conversation. Speech recognition and speech synthesis are separate components.

EDITH's source includes these speech engines:

- **faster-whisper — local speech-to-text (STT):** transcribes audio on the computer. The selected Whisper model may need a one-time download; after it is cached, transcription can run offline.
- **Vosk — local streaming STT:** a lighter offline speech-recognition option when its language model is installed.
- **Kokoro — local text-to-speech (TTS):** generates spoken audio locally. Its voice model is downloaded on first use and then cached. GPU acceleration can improve generation speed; CPU use remains possible but may be slower.
- **Edge TTS and ElevenLabs — network/cloud TTS options:** these are not offline local synthesis engines.

A local-oriented speech setup can therefore combine a local Powerful Brain model with faster-whisper or Vosk for input and Kokoro for output. The exact STT/TTS choice is configured separately from the Powerful Brain model.

**Important distinction:** EDITH's current integrated real-time conversational voice transport is Gemini Live. Selecting Ollama for Powerful Brain does not replace that live audio session or remove its Gemini API requirement. Local STT/TTS engines provide local speech recognition and synthesis paths; they are not the same as a fully local, end-to-end streaming audio LLM. Test microphone input, transcription, TTS playback and Gemini Live independently.

## Vision: local vision models versus EDITH's current vision path

Local vision-capable models do exist. For example, Ollama's [Vision capability](https://docs.ollama.com/capabilities/vision) accepts image input together with text, but the selected model must explicitly support images.

There is an important EDITH integration boundary today:

- EDITH can capture screen/webcam images in its screen-processing feature.
- The current `actions/screen_processor.py` analysis session connects to the Gemini Live API and sends image data through that session.
- The Powerful Brain local text-model route does **not** automatically receive those screenshots or webcam frames just because Ollama is selected.

So a local vision model is a valid option in the local-model ecosystem, but **local screen/webcam analysis is not currently enabled end-to-end by changing the Powerful Brain provider alone**. It needs a dedicated image-input adapter and a routed local vision workflow. Until that integration is added and tested, use the configured Gemini Live vision path for EDITH's current screen/webcam analysis. Do not treat ordinary camera capture or an installed vision model as proof that local vision reasoning is connected.

## Hybrid profiles: a sensible balance

For a computer with good hardware, a useful hybrid arrangement is:

1. Run **Powerful Brain** locally through Ollama or an OpenAI-compatible local server for text reasoning and tasks that fit the chosen model.
2. Use **local faster-whisper/Vosk and Kokoro** when local speech input/output is preferred and the machine can run them comfortably.
3. Keep **Gemini Live** enabled for the current integrated real-time voice and screen/webcam vision features.
4. Switch to a hosted Powerful Brain provider for a task when the local model is too small, too slow, lacks reliable tool calling, or runs out of context/memory.

This setup can reduce text-model API usage while retaining the cloud multimodal features that are already integrated. It is still a hybrid system, not a fully offline system.

## Reliability, privacy and safety

- A local endpoint must be running and the selected model must be installed; EDITH cannot infer model quality from the endpoint name.
- Check the model's tool/function-call support, context and output-token limit, memory use and actual response before relying on it for agent work.
- Local inference avoids sending those model requests to a cloud text API only when the endpoint is genuinely local. Web search, MCP services, Gemini Live, Edge TTS, ElevenLabs and other enabled external tools may still send data to external services.
- Keep local model servers bound to localhost unless you deliberately need LAN access and have configured appropriate network protection.
- Model output never bypasses EDITH's tool policy, local action checks, DevSecOps scans or Rust sandbox.

## Further reading

- [Ollama downloads](https://ollama.com/download)
- [Ollama hardware support](https://docs.ollama.com/gpu)
- [Ollama context length and memory](https://docs.ollama.com/context-length)
- [Ollama vision and image input](https://docs.ollama.com/capabilities/vision)
- [EDITH testing checklist](../TESTING.md)
