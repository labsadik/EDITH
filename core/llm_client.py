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


def get_llm_provider(profile: str = "powerful") -> str:
    """Return the active protocol, preserving legacy local OpenAI aliases."""
    selected = load_provider_settings(CONFIG_PATH, profile)["provider"]
    if selected in {"anthropic", "xai", "groq"}:
        return selected
    return "openai" if selected in ("openai", "openai_compatible") else "ollama"


def _load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_ollama_running(timeout: int = 15, profile: str = "powerful") -> bool:
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
            ok = requests.get(health, timeout=5, headers=_cloud_headers(provider, url, profile)).status_code == 200
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
        return bool(_cloud_headers(provider, url, profile))

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


def warmup_model(system_prompt: str | None = None, profile: str = "powerful") -> bool:
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

    if provider in {"openai", "xai", "groq"}:
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
                                 headers=_cloud_headers(provider, url, profile), timeout=180)
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
                                 headers=_cloud_headers(provider, url, profile), timeout=180)
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
        "think": False,
        # num_gpu:99 → push ALL transformer layers to GPU (Ollama caps at available)
        # This is safe even without a GPU — Ollama silently ignores if n_gpu_layers=0
        "think": False,
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


def check_model_available(log: Callable | None = None, profile: str = "powerful") -> bool:
    """
    Returns True if the configured model is already pulled in Ollama.
    Logs an actionable warning (to console + optional UI callback) if not.
    Always returns True for non-Ollama providers (cannot inspect their model list).
    """
    if get_llm_provider(profile) != "ollama":
        return True

    url, model = get_llm_settings(profile)
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


def get_llm_settings(profile: str = "powerful") -> tuple[str, str]:
    """Returns the selected profile's (base_url, model_name)."""
    settings = load_provider_settings(CONFIG_PATH, profile)
    return settings["url"].rstrip("/"), settings["model"]


def _openai_endpoint(url: str, suffix: str) -> str:
    """Accept both legacy host URLs and provider URLs already ending in /v1."""
    base = str(url).rstrip("/")
    return base + suffix if base.endswith("/v1") else base + "/v1" + suffix


def _cloud_headers(provider: str, url: str, profile: str = "powerful") -> dict[str, str]:
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
    """Convert EDITH/OpenAI-style history into Anthropic Messages content blocks."""
    system = "\n".join(
        str(item.get("content") or "")
        for item in messages if item.get("role") == "system"
    )
    chat: list[dict] = []
    for item in messages:
        role = str(item.get("role") or "user")
        if role == "system":
            continue
        if role == "tool":
            tool_call_id = str(item.get("tool_call_id") or item.get("id") or "")
            if not tool_call_id:
                # Preserve the result as ordinary user text if an upstream caller
                # supplied incomplete tool metadata.
                chat.append({"role": "user", "content": str(item.get("content") or "")})
            else:
                chat.append({"role": "user", "content": [{
                    "type": "tool_result", "tool_use_id": tool_call_id,
                    "content": str(item.get("content") or ""),
                }]})
            continue
        content = str(item.get("content") or "")
        if role == "assistant" and item.get("tool_calls"):
            blocks: list[dict] = []
            if content.strip():
                blocks.append({"type": "text", "text": content})
            for call in item.get("tool_calls") or []:
                function = call.get("function") or {}
                arguments = function.get("arguments") or {}
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                blocks.append({
                    "type": "tool_use",
                    "id": str(call.get("id") or ""),
                    "name": str(function.get("name") or ""),
                    "input": arguments if isinstance(arguments, dict) else {},
                })
            chat.append({"role": "assistant", "content": blocks})
        else:
            chat.append({
                "role": "assistant" if role == "assistant" else "user",
                "content": content,
            })
    return system, chat or [{"role": "user", "content": "Hello"}]


def _anthropic_tools(tools: list | None) -> list[dict]:
    """Convert OpenAI function declarations into Anthropic input_schema tools."""
    converted = []
    for item in tools or []:
        if not isinstance(item, dict):
            continue
        function = item.get("function") if item.get("type") == "function" else item
        if not isinstance(function, dict):
            continue
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        schema = function.get("parameters") or {"type": "object", "properties": {}}
        if not isinstance(schema, dict) or schema.get("type") != "object":
            schema = {"type": "object", "properties": {}}
        converted.append({
            "name": name,
            "description": str(function.get("description") or "")[:1000],
            "input_schema": schema,
        })
    return converted


def _text_from_content(value) -> str:
    """Read visible text blocks from OpenAI-compatible and Anthropic responses."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks = []
        for part in value:
            if isinstance(part, str):
                chunks.append(part)
            elif isinstance(part, dict) and part.get("type") in {"text", "output_text"}:
                text = part.get("text") or part.get("content") or ""
                if isinstance(text, str):
                    chunks.append(text)
        return " ".join(x.strip() for x in chunks if x and x.strip()).strip()
    if isinstance(value, dict):
        nested = value.get("text") or value.get("output_text") or value.get("content")
        if isinstance(nested, (str, list)):
            return _text_from_content(nested)
    return ""


def _ollama_chat(url: str, payload: dict, timeout: int) -> dict:
    """Call Ollama and retry once without think:false for older API versions."""
    endpoint = f"{url.rstrip('/')}/api/chat"
    response = requests.post(endpoint, json=payload, timeout=timeout)
    if response.status_code == 400 and "think" in payload:
        retry_payload = dict(payload)
        retry_payload.pop("think", None)
        response = requests.post(endpoint, json=retry_payload, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    message = data.get("message") or {}
    content = _text_from_content(message.get("content"))
    calls = message.get("tool_calls") or []
    if not content and not calls:
        if message.get("thinking"):
            raise RuntimeError(
                "Ollama returned reasoning but no final text. The request was retried "
                "with think:false; choose a model that supports a final text response."
            )
        raise RuntimeError("Ollama connected but returned an empty final response.")
    return {"content": content, "tool_calls": calls}


def call_llm(
    messages: list,
    tools: list | None = None,
    timeout: int = 120,
    max_tokens: int = 150,
    profile: str = "powerful",
) -> dict:
    """Non-streaming chat routed through the selected profile and provider."""
    url, model = get_llm_settings(profile)
    provider = get_llm_provider(profile)

    if provider in {"openai", "xai", "groq"}:
        payload: dict = {"model": model, "messages": messages, "stream": False,
                         "max_tokens": max(32, int(max_tokens))}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            resp = requests.post(_openai_endpoint(url, "/chat/completions"), json=payload,
                                 headers=_cloud_headers(provider, url, profile), timeout=timeout)
            resp.raise_for_status()
            choices = resp.json().get("choices") or []
            if not choices:
                raise RuntimeError("Provider returned no completion choices")
            msg = choices[0].get("message") or {}
            raw_calls = msg.get("tool_calls") or []
            tc_list = []
            for tool_call in raw_calls:
                function = tool_call.get("function") or {}
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                tc_list.append({"id": tool_call.get("id", ""),
                                "function": {"name": function.get("name", ""),
                                             "arguments": arguments if isinstance(arguments, dict) else {}}})
            content = _text_from_content(msg.get("content") or msg.get("refusal"))
            if not content and not tc_list:
                raise RuntimeError("Provider returned an empty user-visible response")
            return {"content": content, "tool_calls": tc_list}
        except Exception as exc:
            raise RuntimeError(f"{provider} LLM call failed: {type(exc).__name__}: {exc}") from exc

    if provider == "anthropic":
        system, chat = _anthropic_messages(messages)
        payload = {"model": model, "max_tokens": max(32, int(max_tokens)), "messages": chat}
        anthropic_tools = _anthropic_tools(tools)
        if system:
            payload["system"] = system
        if anthropic_tools:
            payload["tools"] = anthropic_tools
        try:
            resp = requests.post(f"{url.rstrip('/')}/messages", json=payload,
                                 headers=_cloud_headers(provider, url, profile), timeout=timeout)
            resp.raise_for_status()
            blocks = resp.json().get("content", [])
            content = _text_from_content(blocks)
            tool_calls = []
            for block in blocks if isinstance(blocks, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                arguments = block.get("input") or {}
                tool_calls.append({
                    "id": str(block.get("id") or ""),
                    "function": {
                        "name": str(block.get("name") or ""),
                        "arguments": arguments if isinstance(arguments, dict) else {},
                    },
                })
            if not content and not tool_calls:
                raise RuntimeError("Anthropic returned an empty user-visible response")
            return {"content": content, "tool_calls": tool_calls}
        except Exception as exc:
            raise RuntimeError(f"Anthropic LLM call failed: {type(exc).__name__}: {exc}") from exc

    payload = {
        "model": model, "messages": messages, "stream": False,
        "keep_alive": -1, "think": False,
        "options": {"num_predict": max(32, int(max_tokens)), "num_gpu": 99},
    }
    if tools:
        payload["tools"] = tools
    try:
        return _ollama_chat(url, payload, timeout)
    except requests.exceptions.ConnectionError as exc:
        print(f"[LLM] Ollama connection failed; checking service and retrying ({type(exc).__name__}).")
        if ensure_ollama_running(profile=profile):
            try:
                return _ollama_chat(url, payload, timeout)
            except Exception as retry_exc:
                raise RuntimeError(f"Ollama retry failed: {type(retry_exc).__name__}: {retry_exc}") from retry_exc
        raise RuntimeError(f"Cannot connect to Ollama at {url}. Install Ollama and run: ollama serve") from exc
    except requests.exceptions.Timeout as exc:
        raise RuntimeError(f"Ollama request timed out after {timeout} seconds.") from exc
    except requests.exceptions.HTTPError as exc:
        status = getattr(exc.response, "status_code", "unknown")
        raise RuntimeError(f"Ollama HTTP error: {status}") from exc
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(f"Ollama LLM call failed: {type(exc).__name__}: {exc}") from exc

def call_llm_text(
    prompt: str,
    system: str | None = None,
    model: str | None = None,
    timeout: int = 120,
    profile: str = "powerful",
) -> str:
    """Generate visible text through the selected provider; omit hidden reasoning."""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    if model is None:
        return call_llm(messages, timeout=timeout, max_tokens=600, profile=profile)["content"]

    url, _selected_model = get_llm_settings(profile)
    provider = get_llm_provider(profile)
    if provider in {"openai", "xai", "groq"}:
        endpoint = _openai_endpoint(url, "/chat/completions")
        payload = {"model": model, "messages": messages, "stream": False, "max_tokens": 600}
        headers = _cloud_headers(provider, url, profile)
    elif provider == "anthropic":
        system_text, chat = _anthropic_messages(messages)
        payload = {"model": model, "messages": chat, "max_tokens": 600}
        if system_text:
            payload["system"] = system_text
        try:
            resp = requests.post(f"{url.rstrip('/')}/messages", json=payload,
                                 headers=_cloud_headers(provider, url, profile), timeout=timeout)
            resp.raise_for_status()
            text = _text_from_content(resp.json().get("content", []))
            if not text:
                raise RuntimeError("Anthropic returned an empty user-visible response")
            return text
        except Exception as exc:
            raise RuntimeError(f"Anthropic text call failed: {type(exc).__name__}: {exc}") from exc
    else:
        payload = {"model": model, "messages": messages, "stream": False,
                   "keep_alive": -1, "think": False,
                   "options": {"num_predict": 600, "num_gpu": 99}}
        try:
            return _ollama_chat(url, payload, timeout)["content"]
        except requests.exceptions.ConnectionError as exc:
            if ensure_ollama_running(profile=profile):
                try:
                    return _ollama_chat(url, payload, timeout)["content"]
                except Exception as retry_exc:
                    raise RuntimeError(f"Ollama text retry failed: {type(retry_exc).__name__}: {retry_exc}") from retry_exc
            raise RuntimeError(f"Cannot connect to configured Ollama LLM at {url}") from exc

    try:
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        choices = resp.json().get("choices") or []
        if not choices:
            raise RuntimeError("Provider returned no completion choices")
        msg = choices[0].get("message") or {}
        content = _text_from_content(msg.get("content") or msg.get("refusal"))
        if not content:
            raise RuntimeError("Provider returned an empty user-visible response")
        return content
    except Exception as exc:
        raise RuntimeError(f"{provider} text call failed: {type(exc).__name__}: {exc}") from exc

def _stream_openai(
    messages: list,
    tools:    list | None,
    timeout:  int,
    profile:  str = "powerful",
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
    profile:  str = "powerful",
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
        "think": False,
        # 150 tokens ≈ 100 words ≈ 3-4 sentences — enough for any voice reply.
        # num_gpu:99 pushes all layers to GPU; num_thread removed (Ollama auto-tunes).
        "options":    {"num_predict": 150, "num_gpu": 99},
    }
    if tools:
        payload["tools"] = tools

    def _do_stream() -> Generator[dict, None, None]:
        response = requests.post(endpoint, json=payload, timeout=timeout, stream=True)
        if response.status_code == 400 and "think" in payload:
            response.close()
            retry_payload = dict(payload)
            retry_payload.pop("think", None)
            response = requests.post(endpoint, json=retry_payload, timeout=timeout, stream=True)
        with response as resp:
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
                delta = _text_from_content(msg.get("content"))

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
        if ensure_ollama_running(profile=profile):
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
