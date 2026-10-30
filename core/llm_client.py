"""
Local LLM client for EDITH.

Supports local and cloud backends — selected via ``llm_provider`` plus the
optional ``provider_profile`` in config/api_keys.json. Existing Ollama and
OpenAI-compatible local configurations remain backward compatible.

  "llm_provider": "ollama"   (default)
        Uses Ollama's native /api/chat endpoint.
        Download: https://ollama.com
        Default port: 11434

  "llm_provider": "openai"
        Uses any OpenAI-compatible server: LM Studio, Jan, LocalAI,
        llama.cpp server, vLLM, etc.
        LM Studio download: https://lmstudio.ai   (default port: 1234)
        Set  "llm_url": "http://localhost:1234"  in config.
        Note: tool-calling support depends on the model; use a model that
        supports function/tool calls (e.g. Qwen2.5, Llama-3.1, Mistral).
"""
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Generator

import requests
from core.provider_registry import load_provider_settings, provider_api_key

# Matches a sentence boundary: [.!?] followed by whitespace, or a blank line.
# Avoids splitting on decimals (3.5) because those have no space after the dot.
_SENT_END = re.compile(r'(?<=[.!?])\s+|(?<=\n)\s*\n')

def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR    = get_base_dir()
CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_DEFAULTS = {
    "llm_url":      "http://localhost:11434",
    "llm_model":    "llama3.2",
    "llm_provider": "ollama",   # "ollama" | "openai"
}


def get_llm_provider(profile: str = "main") -> str:
    """Return the active protocol, preserving legacy local OpenAI aliases."""
    cfg = _load_config()
    selected = load_provider_settings(CONFIG_PATH, profile)["provider"]
    if selected in {"anthropic", "xai", "groq"}:
        return selected
    return "openai" if selected in ("openai", "openai_compatible") else "ollama"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_ollama_running(timeout: int = 15, profile: str = "main") -> bool:
    """
    For Ollama: ping /api/tags; auto-launch 'ollama serve' if not running.
    For OpenAI-compatible providers: just ping /v1/models (server must be started manually).
    Returns True if the LLM server is reachable.
    """
    url, _   = get_llm_settings(profile)
    provider = get_llm_provider(profile)

    if provider in {"openai", "xai", "groq"}:
        # Local OpenAI-compatible servers must be started manually; cloud
        # provider reachability is verified by the real inference probe.
        # by the user — we just check if they're reachable.
        health = _openai_endpoint(url, "/models")
        try:
            ok = requests.get(health, timeout=5, headers=_cloud_headers(provider, url)).status_code == 200
            if ok:
                print(f"[LLM] OpenAI-compatible server reachable at {url}")
            else:
                print(f"[LLM] Server at {url} returned non-200.  Is it running?")
            return ok
        except Exception as e:
            print(
                f"[LLM] Cannot reach OpenAI-compatible server at {url}.\n"
                "      Make sure LM Studio / LocalAI / Jan is running and the server is started."
            )
            return False

    if provider == "anthropic":
        # Anthropic has no unauthenticated model-list endpoint. A real request
        # is made by warmup/call instead of declaring it available here.
        return bool(_cloud_headers(provider, url))

    # ── Ollama ──────────────────────────────────────────────────────────────
    health = f"{url}/api/tags"

    def _is_up() -> bool:
        try:
            return requests.get(health, timeout=3).status_code == 200
        except Exception:
            return False

    if _is_up():
        return True

    print("[LLM] Ollama not running — launching 'ollama serve'…")
    try:
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        subprocess.Popen(["ollama", "serve"], **kwargs)
    except FileNotFoundError:
        print("[LLM] 'ollama' command not found. Install Ollama from https://ollama.com")
        return False
    except Exception as e:
        print(f"[LLM] Could not launch Ollama: {e}")
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.0)
        if _is_up():
            print("[LLM] Ollama started successfully.")
            return True

    print("[LLM] Ollama did not respond within the timeout.")
    return False


def warmup_model(system_prompt: str | None = None, profile: str = "main") -> bool:
    """
    Pre-load the model AND prime Ollama's KV prefix cache.

    Why the system_prompt matters
    ─────────────────────────────
    Ollama caches the KV attention state of the prompt prefix across requests.
    If warmup includes the same system prompt that real requests will use, Ollama
    evaluates those tokens ONCE at startup.  Every subsequent request only needs
    to evaluate the small delta (user message ± time context) instead of the full
    300-500 token system prompt → drops first-token latency from ~17 s to <1 s.

    Pass the *static* part of the system prompt (the JARVIS protocol text, without
    timestamps or per-minute context) so the prefix stays valid across calls.
    """
    url, model = get_llm_settings(profile)
    provider   = get_llm_provider(profile)
    print(f"[LLM] Warming up '{model}' ({provider})…")

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": "hi"})

    if provider in {"openai", "xai"}:
        # OpenAI-compatible: just fire a minimal request to ensure the model is loaded.
        # No keep_alive or KV-cache priming available — server manages this internally.
        payload = {
            "model":      model,
            "messages":   messages,
            "stream":     False,
            "max_tokens": 1,
        }
        try:
            resp = requests.post(_openai_endpoint(url, "/chat/completions"), json=payload,
                                 headers=_cloud_headers(provider, url), timeout=180)
            resp.raise_for_status()
            print(f"[LLM] '{model}' ready (OpenAI-compatible server).")
            return True
        except Exception as e:
            print(f"[LLM] Warmup failed (non-fatal): {e}")
            return False

    if provider == "anthropic":
        system, chat = _anthropic_messages(messages)
        payload = {"model": model, "max_tokens": 1, "messages": chat}
        if system:
            payload["system"] = system
        try:
            resp = requests.post(f"{url}/messages", json=payload,
                                 headers=_cloud_headers(provider, url), timeout=180)
            resp.raise_for_status()
            print(f"[LLM] '{model}' ready (Anthropic).")
            return True
        except Exception as e:
            print(f"[LLM] Warmup failed (non-fatal): {e}")
            return False

    # ── Ollama ──────────────────────────────────────────────────────────────
    payload = {
        "model":      model,
        "messages":   messages,
        "stream":     False,
        "keep_alive": -1,
        # num_gpu:99 → push ALL transformer layers to GPU (Ollama caps at available)
        # This is safe even without a GPU — Ollama silently ignores if n_gpu_layers=0
        "options":    {"num_predict": 1, "num_gpu": 99},
    }
    try:
        resp = requests.post(f"{url}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        print(f"[LLM] '{model}' loaded and KV cache primed.")
        return True
    except Exception as e:
        print(f"[LLM] Warmup failed (non-fatal): {e}")
        return False


def check_model_available(log: Callable | None = None, profile: str = "main") -> bool:
    """
    Returns True if the configured model is already pulled in Ollama.
    Logs an actionable warning (to console + optional UI callback) if not.
    Always returns True for non-Ollama providers (cannot inspect their model list).
    """
    if get_llm_provider(profile) != "ollama":
        return True

    url, model = get_llm_settings()
    try:
        resp = requests.get(f"{url}/api/tags", timeout=5)
        resp.raise_for_status()
        pulled = [m.get("name", "") for m in resp.json().get("models", [])]
        model_base = model.split(":")[0]
        found = any(
            m == model or m == model_base or m.startswith(model_base + ":")
            for m in pulled
        )
        if not found:
            available = ", ".join(pulled) if pulled else "none"
            warn = (
                f"WRN: Model '{model}' is not pulled in Ollama.\n"
                f"     Available: {available}\n"
                f"     Fix: ollama pull {model}"
            )
            print(warn)
            if log:
                log(f"WRN: '{model}' not found — run: ollama pull {model}")
        return found
    except Exception:
        return True   # Ollama might still be starting up; non-blocking


def get_llm_settings(profile: str = "main") -> tuple[str, str]:
    """Returns the selected profile's (base_url, model_name)."""
    settings = load_provider_settings(CONFIG_PATH, profile)
    return settings["url"].rstrip("/"), settings["model"]


def _openai_endpoint(url: str, suffix: str) -> str:
    """Accept both legacy host URLs and provider URLs already ending in /v1."""
    base = str(url).rstrip("/")
    return base + suffix if base.endswith("/v1") else base + "/v1" + suffix


def _cloud_headers(provider: str, url: str, profile: str = "main") -> dict[str, str]:
    """Return credentials only for configured cloud profiles, never logs them."""
    try:
        selected = load_provider_settings(CONFIG_PATH, profile)["provider"]
        # A local OpenAI-compatible server is intentionally keyless.
        if provider == "openai" and selected == "openai_compatible":
            return {}
        key = provider_api_key(selected, CONFIG_PATH, profile)
        if provider in {"anthropic", "xai", "groq"} or (provider == "openai" and selected == "openai"):
            if not key:
                raise RuntimeError(f"{selected} API key is not configured in local credential storage")
        if provider == "anthropic":
            return {"x-api-key": key or "", "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {key}"} if key else {}
    except RuntimeError:
        raise
    except Exception:
        return {}


def _anthropic_messages(messages: list) -> tuple[str, list[dict]]:
    system = "\n".join(str(item.get("content") or "") for item in messages if item.get("role") == "system")
    chat = [{"role": "assistant" if item.get("role") == "assistant" else "user",
             "content": str(item.get("content") or "")}
            for item in messages if item.get("role") != "system"]
    return system, chat or [{"role": "user", "content": "Hello"}]


def call_llm(
    messages: list,
    tools:    list | None = None,
    timeout:  int = 120,
    max_tokens: int = 150,
    profile: str = "main",
) -> dict:
    """
    Non-streaming chat request.  Routes to Ollama or OpenAI-compatible backend.

    Returns:
        {"content": str, "tool_calls": list}
    """
    url, model = get_llm_settings(profile)
    provider   = get_llm_provider(profile)

    if provider in {"openai", "xai", "groq"}:
        endpoint = _openai_endpoint(url, "/chat/completions")
        payload: dict = {
            "model":      model,
            "messages":   messages,
            "stream":     False,
            "max_tokens": max_tokens,
        }
        if tools:
            payload["tools"]       = tools
            payload["tool_choice"] = "auto"
        try:
            resp = requests.post(endpoint, json=payload, headers=_cloud_headers(provider, url, profile), timeout=timeout)
            resp.raise_for_status()
            choice = resp.json().get("choices", [{}])[0]
            msg    = choice.get("message", {})
            # OpenAI tool_calls format → normalise to Ollama-style
            raw_tc  = msg.get("tool_calls") or []
            tc_list = [
                {
                    "id":       t.get("id", ""),
                    "function": {
                        "name":      t["function"]["name"],
                        "arguments": (
                            json.loads(t["function"]["arguments"])
                            if isinstance(t["function"].get("arguments"), str)
                            else t["function"].get("arguments", {})
                        ),
                    },
                }
                for t in raw_tc
            ]
            return {
                "content":    (msg.get("content") or "").strip(),
                "tool_calls": tc_list,
            }
        except Exception as e:
            raise RuntimeError(f"OpenAI-compatible LLM call failed: {e}")

    if provider == "anthropic":
        system, chat = _anthropic_messages(messages)
        payload: dict = {"model": model, "max_tokens": max_tokens, "messages": chat}
        if system:
            payload["system"] = system
        try:
            resp = requests.post(f"{url}/messages", json=payload,
                                 headers=_cloud_headers(provider, url), timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            content = "".join(str(part.get("text") or "") for part in data.get("content", [])
                              if isinstance(part, dict) and part.get("type") == "text")
            return {"content": content.strip(), "tool_calls": []}
        except Exception as e:
            raise RuntimeError(f"Anthropic LLM call failed: {e}")

    # ── Ollama ──────────────────────────────────────────────────────────────
    endpoint = f"{url}/api/chat"
    payload = {
        "model":      model,
        "messages":   messages,
        "stream":     False,
        "keep_alive": -1,
        "options":    {"num_predict": max_tokens, "num_gpu": 99},
    }
    if tools:
        payload["tools"] = tools

    try:
        resp = requests.post(endpoint, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        msg  = data.get("message", {})
        return {
            "content":    (msg.get("content") or "").strip(),
            "tool_calls": msg.get("tool_calls") or [],
        }
    except requests.exceptions.ConnectionError as e:
        print(f"[LLM] ConnectionError — trying to restart Ollama… ({e})")
        if ensure_ollama_running(profile=profile):
            try:
                resp = requests.post(endpoint, json=payload, timeout=timeout)
                resp.raise_for_status()
                data = resp.json()
                msg  = data.get("message", {})
                return {
                    "content":    (msg.get("content") or "").strip(),
                    "tool_calls": msg.get("tool_calls") or [],
                }
            except Exception:
                pass
        raise RuntimeError(
            f"Cannot connect to Ollama at {url}. "
            "Make sure Ollama is installed and run: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Ollama request timed out after {timeout} s.")
    except requests.exceptions.HTTPError as e:
        print(f"[LLM] HTTPError: {e.response.status_code} — {e.response.text[:200]}")
        raise RuntimeError(f"Ollama HTTP error: {e.response.status_code}")
    except Exception as e:
        print(f"[LLM] Unexpected error: {type(e).__name__}: {e}")
        raise RuntimeError(f"LLM call failed: {e}")


def call_llm_text(
    prompt:  str,
    system:  str | None = None,
    model:   str | None = None,
    timeout: int = 120,
    profile: str = "main",
) -> str:
    """Text-only generation using the configured local provider.

    Explicit model overrides are supported for both Ollama and OpenAI-compatible
    servers. The shared call_llm path handles default-model requests.
    """
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    if model is None:
        # Preserve the original 600-token budget for planning and coding tasks.
        # Short conversational requests retain call_llm's 150-token default.
        return call_llm(messages, timeout=timeout, max_tokens=600, profile=profile)["content"]

    url, _ = get_llm_settings(profile)
    provider = get_llm_provider(profile)
    if provider in {"openai", "xai", "groq"}:
        endpoint = _openai_endpoint(url, "/chat/completions")
        payload = {"model": model, "messages": messages, "stream": False, "max_tokens": 600}
    elif provider == "anthropic":
        system, chat = _anthropic_messages(messages)
        payload = {"model": model, "messages": chat, "max_tokens": 600}
        if system:
            payload["system"] = system
        try:
            resp = requests.post(f"{url}/messages", json=payload,
                                 headers=_cloud_headers(provider, url), timeout=timeout)
            resp.raise_for_status()
            return "".join(str(part.get("text") or "") for part in resp.json().get("content", [])
                           if isinstance(part, dict) and part.get("type") == "text").strip()
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Anthropic text call failed: {exc}") from exc
    else:
        endpoint = f"{url}/api/chat"
        payload = {
            "model": model, "messages": messages, "stream": False,
            "keep_alive": -1, "options": {"num_predict": 600},
        }
    try:
        headers = _cloud_headers(provider, url, profile) if provider in {"openai", "xai", "groq"} else None
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if provider in {"openai", "xai"}:
            return (data["choices"][0]["message"].get("content") or "").strip()
        return (data.get("message", {}).get("content") or "").strip()
    except requests.exceptions.ConnectionError as exc:
        if provider == "ollama" and ensure_ollama_running():
            try:
                resp = requests.post(endpoint, json=payload, timeout=timeout)
                resp.raise_for_status()
                return (resp.json().get("message", {}).get("content") or "").strip()
            except requests.exceptions.RequestException as retry_exc:
                raise RuntimeError(f"LLM text call failed after Ollama restart: {retry_exc}") from retry_exc
        raise RuntimeError(f"Cannot connect to configured {provider} LLM at {url}") from exc
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"LLM text call failed: {exc}") from exc


def _stream_openai(
    messages: list,
    tools:    list | None,
    timeout:  int,
    profile:  str = "main",
) -> Generator[dict, None, None]:
    """
    Streaming backend for OpenAI-compatible servers (LM Studio, LocalAI, Jan…).

    Parses Server-Sent Events (SSE) and accumulates streaming tool-call fragments
    so the output format is identical to the Ollama backend.
    """
    url, model = get_llm_settings(profile)
    endpoint   = _openai_endpoint(url, "/chat/completions")

    payload: dict = {
        "model":      model,
        "messages":   messages,
        "stream":     True,
        "max_tokens": 150,
    }
    if tools:
        payload["tools"]       = tools
        payload["tool_choice"] = "auto"

    try:
        with requests.post(endpoint, json=payload, headers=_cloud_headers(get_llm_provider(profile), url, profile),
                           timeout=timeout, stream=True) as resp:
            resp.raise_for_status()
            full_content = ""
            buf          = ""
            # tool_call fragments: index → {"id", "function": {"name", "arguments"}}
            tc_fragments: dict[int, dict] = {}

            for raw in resp.iter_lines():
                if not raw:
                    continue
                # SSE lines look like: b"data: {...}" or b"data: [DONE]"
                line = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choice = chunk.get("choices", [{}])[0]
                delta  = choice.get("delta", {})
                text   = delta.get("content") or ""

                full_content += text
                buf          += text

                # Accumulate sentence boundaries for streaming TTS
                while True:
                    m = _SENT_END.search(buf)
                    if not m:
                        break
                    sentence = buf[: m.start() + 1].strip()
                    buf      = buf[m.end():]
                    if sentence:
                        yield {"type": "sentence", "text": sentence}

                # Accumulate streaming tool-call fragments
                for tc in (delta.get("tool_calls") or []):
                    idx = tc.get("index", 0)
                    if idx not in tc_fragments:
                        tc_fragments[idx] = {"id": "", "function": {"name": "", "arguments": ""}}
                    frag = tc_fragments[idx]
                    frag["id"] = frag["id"] or tc.get("id", "")
                    fn = tc.get("function", {})
                    frag["function"]["name"]      += fn.get("name") or ""
                    frag["function"]["arguments"] += fn.get("arguments") or ""

                finish = choice.get("finish_reason")
                if finish in ("stop", "tool_calls", "length"):
                    break

            # Flush any trailing content
            if buf.strip():
                yield {"type": "sentence", "text": buf.strip()}

            # Parse accumulated tool-call argument strings → dicts
            tool_calls: list = []
            for idx in sorted(tc_fragments):
                frag = tc_fragments[idx]
                args = frag["function"]["arguments"]
                try:
                    args = json.loads(args)
                except Exception:
                    pass   # leave as raw string; _execute_tool handles it
                tool_calls.append({
                    "id":       frag["id"],
                    "function": {"name": frag["function"]["name"], "arguments": args},
                })

            yield {
                "type":       "done",
                "content":    full_content.strip(),
                "tool_calls": tool_calls,
            }

    except requests.exceptions.ConnectionError:
        raise RuntimeError(
            f"Cannot reach OpenAI-compatible server at {url}.\n"
            "Make sure LM Studio / LocalAI / Jan is running and the server is started."
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("OpenAI-compatible stream timed out.")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"OpenAI-compatible HTTP error: {e.response.status_code}")
    except Exception as e:
        raise RuntimeError(f"OpenAI-compatible stream failed: {e}")


def call_llm_stream(
    messages: list,
    tools:    list | None = None,
    timeout:  int = 120,
    profile:  str = "main",
) -> Generator[dict, None, None]:
    """
    Streaming chat request.  Routes to Ollama or OpenAI-compatible backend.

    Yields:
        {"type": "sentence", "text": str}   — each complete sentence as it arrives
        {"type": "done", "content": str, "tool_calls": list}  — when stream ends

    Sentences are split on [.!?] + whitespace so TTS can start immediately.
    Tool calls always appear in the final "done" event.
    """
    provider = get_llm_provider(profile)
    if provider in {"openai", "xai", "groq"}:
        yield from _stream_openai(messages, tools, timeout, profile)
        return

    if provider == "anthropic":
        # Text providers without a streaming transport still expose the same
        # public generator contract. Narration receives the complete response
        # as one sentence rather than pretending it streamed token-by-token.
        response = call_llm(messages, tools=tools, timeout=timeout, profile=profile)
        if response["content"]:
            yield {"type": "sentence", "text": response["content"]}
        yield {"type": "done", **response}
        return

    url, model = get_llm_settings(profile)
    endpoint   = f"{url}/api/chat"

    payload: dict = {
        "model":      model,
        "messages":   messages,
        "stream":     True,
        "keep_alive": -1,
        # 150 tokens ≈ 100 words ≈ 3-4 sentences — enough for any voice reply.
        # num_gpu:99 pushes all layers to GPU; num_thread removed (Ollama auto-tunes).
        "options":    {"num_predict": 150, "num_gpu": 99},
    }
    if tools:
        payload["tools"] = tools

    def _do_stream() -> Generator[dict, None, None]:
        with requests.post(endpoint, json=payload, timeout=timeout, stream=True) as resp:
            resp.raise_for_status()
            full_content = ""
            tool_calls:  list = []
            buf          = ""

            for raw in resp.iter_lines():
                if not raw:
                    continue
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                msg   = chunk.get("message", {})
                delta = msg.get("content") or ""

                full_content += delta
                buf          += delta

                # Yield complete sentences as they accumulate
                while True:
                    m = _SENT_END.search(buf)
                    if not m:
                        break
                    sentence = buf[: m.start() + 1].strip()
                    buf      = buf[m.end() :]
                    if sentence:
                        yield {"type": "sentence", "text": sentence}

                tc = msg.get("tool_calls")
                if tc:
                    tool_calls.extend(tc)

                if chunk.get("done"):
                    if buf.strip():
                        yield {"type": "sentence", "text": buf.strip()}

                    yield {
                        "type":       "done",
                        "content":    full_content.strip(),
                        "tool_calls": tool_calls,
                    }
                    return

    try:
        yield from _do_stream()
    except requests.exceptions.ConnectionError as e:
        print(f"[LLM] Stream ConnectionError — trying to restart Ollama… ({e})")
        if ensure_ollama_running():
            yield from _do_stream()
            return
        raise RuntimeError(
            f"Cannot connect to Ollama at {url}. "
            "Make sure Ollama is installed and run: ollama serve"
        )
    except requests.exceptions.Timeout:
        raise RuntimeError("Ollama stream timed out.")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP error: {e.response.status_code}")
    except Exception as e:
        print(f"[LLM] Stream error: {type(e).__name__}: {e}")
        raise RuntimeError(f"LLM stream failed: {e}")
