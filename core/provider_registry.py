"""Provider discovery, profile-specific credentials, probes and real-time search.

Main Brain and Powerful Brain are kept as separate local profiles. Secrets are
stored through the OS keychain helper and never written into activity logs.
"""
from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping
from urllib.parse import quote, urlencode

import requests

from core.secrets import (
    get_config_secret,
    get_gemini_api_key,
    save_config_secret,
    save_gemini_api_key,
)

VOICE_DEFAULT_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"

@dataclass(frozen=True)
class ProviderSpec:
    identifier: str
    label: str
    default_url: str
    default_model: str
    secret_name: str | None = None
    protocol: str = "openai"  # openai | anthropic | ollama | gemini_live


SPECS: dict[str, ProviderSpec] = {
    "ollama": ProviderSpec("ollama", "Ollama (local)", "http://localhost:11434", "llama3.2", protocol="ollama"),
    "openai": ProviderSpec("openai", "OpenAI", "https://api.openai.com/v1", "gpt-4.1-mini", "openai_api_key"),
    "anthropic": ProviderSpec("anthropic", "Anthropic Claude", "https://api.anthropic.com/v1", "claude-sonnet-4-20250514", "anthropic_api_key", "anthropic"),
    "groq": ProviderSpec("groq", "Groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", "groq_api_key"),
    "xai": ProviderSpec("xai", "xAI Grok", "https://api.x.ai/v1", "grok-4.7", "xai_api_key"),
    "openai_compatible": ProviderSpec("openai_compatible", "OpenAI-compatible local server", "http://localhost:1234/v1", "local-model", protocol="openai"),
    "gemini": ProviderSpec("gemini", "Google Gemini Live", "", VOICE_DEFAULT_MODEL, "gemini_api_key", "gemini_live"),
}

_ALIASES = {
    "lmstudio": "openai_compatible", "localai": "openai_compatible",
    "jan": "openai_compatible", "llamacpp": "openai_compatible",
    "chatgpt": "openai", "claude": "anthropic", "grok": "xai",
}
_SEARCH_SECRET_NAMES = {
    "tavily": "tavily_api_key",
    "brave": "brave_search_api_key",
    "serpapi": "serpapi_api_key",
    "exa": "exa_api_key",
}


def normalize_provider(value: object) -> str:
    name = str(value or "ollama").strip().lower().replace("-", "_")
    name = _ALIASES.get(name, name)
    return name if name in SPECS else "ollama"


def provider_spec(value: object) -> ProviderSpec:
    return SPECS[normalize_provider(value)]


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(path: Path, data: Mapping[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                         prefix=".edith-provider-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(data), stream, indent=4)
            stream.write("\n")
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _profile_fields(profile: str) -> tuple[str, str, str, str]:
    value = str(profile or "main").strip().lower()
    if value == "main":
        return "llm_provider", "llm_url", "llm_model", "provider_profile"
    if value == "powerful":
        return "powerful_llm_provider", "powerful_llm_url", "powerful_llm_model", "powerful_provider_profile"
    raise ValueError("Provider profile must be 'main' or 'powerful'")


def has_provider_profile(config_path: Path, profile: str = "main") -> bool:
    provider_key, url_key, model_key, profile_key = _profile_fields(profile)
    data = _read(config_path)
    return any(key in data for key in (provider_key, url_key, model_key, profile_key))


def load_provider_settings(config_path: Path, profile: str = "main") -> dict[str, str]:
    data = _read(Path(config_path))
    provider_key, url_key, model_key, profile_key = _profile_fields(profile)
    if profile == "powerful" and not any(key in data for key in (provider_key, url_key, model_key, profile_key)):
        # Until Powerful Brain is configured independently, it explicitly
        # inherits Main Brain rather than silently selecting a different model.
        return load_provider_settings(config_path, "main")

    raw = str(data.get(profile_key) or data.get(provider_key) or "ollama")
    provider = normalize_provider(raw)
    url = str(data.get(url_key) or "").rstrip("/")
    if raw.strip().lower() == "openai" and ("localhost" in url or "127.0.0.1" in url):
        provider = "openai_compatible"
    spec = provider_spec(provider)
    return {
        "provider": provider,
        "url": url or spec.default_url,
        "model": str(data.get(model_key) or spec.default_model),
    }


def _profile_secret_name(spec: ProviderSpec, profile: str) -> str | None:
    if not spec.secret_name:
        return None
    if profile == "powerful":
        return f"powerful_{spec.secret_name}"
    return spec.secret_name


def provider_api_key(provider: object, config_path: Path, profile: str = "main") -> str | None:
    spec = provider_spec(provider)
    secret_name = _profile_secret_name(spec, profile)
    if not secret_name:
        return None
    status = get_config_secret(secret_name, Path(config_path))
    if status.value:
        return status.value
    if profile == "powerful" and not has_provider_profile(config_path, "powerful"):
        return provider_api_key(provider, config_path, "main")
    return None


def save_provider_settings(config_path: Path, provider: object, url: str, model: str,
                           api_key: str = "", profile: str = "main") -> dict[str, str]:
    """Save one Brain profile; keep credentials separate between Main and Powerful."""
    spec = provider_spec(provider)
    if spec.protocol == "gemini_live":
        raise ValueError("Gemini Live is configured in the Voice tab")
    clean_url = str(url or spec.default_url).strip().rstrip("/")
    clean_model = str(model or spec.default_model).strip()
    if not clean_url or not clean_model:
        raise ValueError("Provider endpoint and model are required")
    provider_key, url_key, model_key, profile_key = _profile_fields(profile)
    data = _read(Path(config_path))
    data[provider_key] = "openai" if spec.protocol == "openai" else spec.identifier
    data[url_key] = clean_url
    data[model_key] = clean_model
    data[profile_key] = spec.identifier
    _write(Path(config_path), data)
    secret_name = _profile_secret_name(spec, profile)
    if secret_name and str(api_key or "").strip():
        save_config_secret(secret_name, str(api_key).strip(), Path(config_path))
    return {"provider": spec.identifier, "url": clean_url, "model": clean_model, "profile": profile}


def _openai_models_url(base_url: str) -> str:
    base = str(base_url).strip().rstrip("/")
    return base + "/models" if base.endswith("/v1") else base + "/v1/models"


def _headers(spec: ProviderSpec, key: str | None) -> dict[str, str]:
    if not key:
        return {}
    if spec.protocol == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {key}"}


def _extract_text_content(value: Any) -> str:
    """Normalize provider text blocks without exposing private reasoning fields."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                text = item.get("text") or item.get("content") or ""
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(x.strip() for x in parts if x and x.strip()).strip()
    if isinstance(value, dict):
        nested = value.get("text") or value.get("output_text") or value.get("content")
        if isinstance(nested, (str, list)):
            return _extract_text_content(nested)
    return ""


def _chat_completions_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        raise ValueError("Provider endpoint is required")
    return base + "/chat/completions" if base.endswith("/v1") else base + "/v1/chat/completions"

def list_provider_models(provider: object, url: str = "", api_key: str | None = None,
                         timeout: float = 15.0) -> list[str]:
    """Fetch models available to this exact provider account (or local Ollama host)."""
    spec = provider_spec(provider)
    base = str(url or spec.default_url).strip().rstrip("/")
    if spec.secret_name and not api_key:
        raise RuntimeError(f"Add the {spec.label} API key before loading its models")

    if spec.protocol == "ollama":
        endpoint = f"{base}/api/tags"
        headers = {}
    elif spec.protocol == "anthropic":
        endpoint = base + "/models" if base.endswith("/v1") else base + "/v1/models"
        headers = {**_headers(spec, api_key), "anthropic-version": "2023-06-01"}
    else:
        endpoint = _openai_models_url(base)
        headers = _headers(spec, api_key)

    try:
        response = requests.get(endpoint, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        items = payload.get("models") or payload.get("data") or []
        models: list[str] = []
        for item in items:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("id") or item.get("name") or "").strip()
                if item.get("active") is False or item.get("deleted") is True:
                    continue
            else:
                continue
            if name and name not in models:
                models.append(name)
        if not models:
            raise RuntimeError("The provider returned no available models for this API key")
        return models
    except Exception as exc:
        detail = str(exc).replace(str(api_key or ""), "[REDACTED]")
        raise RuntimeError(f"{spec.label} model list failed: {type(exc).__name__}: {detail[:180]}") from exc


def probe_provider(provider: object, url: str, model: str, api_key: str | None = None,
                   timeout: float = 20.0) -> dict[str, Any]:
    """Verify endpoint authentication and a user-visible model response."""
    spec = provider_spec(provider)
    base = str(url or spec.default_url).rstrip("/")
    started = time.perf_counter()
    try:
        if spec.protocol == "gemini_live":
            raise RuntimeError("Gemini Live is tested from the Voice tab")
        if spec.secret_name and not api_key:
            raise RuntimeError("An API key is required for this provider")
        prompt = "Reply with the single word OK. Do not provide analysis."
        if spec.protocol == "ollama":
            payload = {
                "model": model, "stream": False, "think": False,
                "options": {"num_predict": 64, "temperature": 0},
                "messages": [{"role": "user", "content": prompt}],
            }
            response = requests.post(f"{base}/api/chat", json=payload, timeout=timeout)
            if response.status_code == 400:
                payload.pop("think", None)
                response = requests.post(f"{base}/api/chat", json=payload, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            message = data.get("message") if isinstance(data, dict) else {}
            content = _extract_text_content((message or {}).get("content"))
            if not content and (message or {}).get("thinking"):
                raise RuntimeError("Provider connected, but returned reasoning without a final text response; choose a model that supports a final response or check think:false support")
        elif spec.protocol == "anthropic":
            endpoint = base + "/messages" if base.endswith("/v1") else base + "/v1/messages"
            response = requests.post(endpoint, headers=_headers(spec, api_key), json={
                "model": model, "max_tokens": 64,
                "messages": [{"role": "user", "content": prompt}],
            }, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            content = _extract_text_content(data.get("content", []))
        else:
            response = requests.post(_chat_completions_url(base), headers=_headers(spec, api_key), json={
                "model": model, "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64, "stream": False,
            }, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise RuntimeError("Provider authenticated, but returned no completion choices")
            choice = choices[0] if isinstance(choices[0], dict) else {}
            message = choice.get("message") or {}
            content = _extract_text_content(message.get("content") or message.get("refusal") or choice.get("text"))
        if not content:
            raise RuntimeError("Provider connected, but returned no user-visible text response")
        return {"ok": True, "provider": spec.identifier, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000), "error": None}
    except Exception as exc:
        detail = str(exc).replace(str(api_key or ""), "[REDACTED]")
        return {"ok": False, "provider": spec.identifier, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": f"{type(exc).__name__}: {detail[:220]}"}

def _search_headers(provider: str, api_key: str) -> dict[str, str]:
    if provider == "brave":
        return {"X-Subscription-Token": api_key, "Accept": "application/json"}
    if provider == "exa":
        return {"x-api-key": api_key, "Content-Type": "application/json"}
    return {"Content-Type": "application/json"}


def run_realtime_search(provider: str, query: str, api_key: str,
                        max_results: int = 6, timeout: float = 15.0) -> list[dict[str, str]]:
    """Query Tavily, Brave, SerpAPI or Exa and normalize results for EDITH."""
    name = str(provider or "").strip().lower()
    if name not in _SEARCH_SECRET_NAMES:
        raise ValueError("Unsupported real-time search provider")
    key = str(api_key or "").strip()
    if not key:
        raise RuntimeError("A real-time search API key is required")
    q = str(query or "").strip()
    if not q:
        raise ValueError("Search query is required")
    limit = max(1, min(int(max_results), 10))

    if name == "tavily":
        response = requests.post("https://api.tavily.com/search", json={
            "api_key": key, "query": q, "max_results": limit, "search_depth": "basic",
        }, timeout=timeout)
        response.raise_for_status()
        raw = response.json().get("results", [])
        results = [{"title": str(x.get("title") or ""), "snippet": str(x.get("content") or ""),
                    "url": str(x.get("url") or ""), "source": "Tavily"}
                   for x in raw if isinstance(x, dict)]
    elif name == "brave":
        response = requests.get("https://api.search.brave.com/res/v1/web/search",
                                params={"q": q, "count": limit},
                                headers=_search_headers(name, key), timeout=timeout)
        response.raise_for_status()
        raw = response.json().get("web", {}).get("results", [])
        results = [{"title": str(x.get("title") or ""), "snippet": str(x.get("description") or ""),
                    "url": str(x.get("url") or ""), "source": "Brave Search"}
                   for x in raw if isinstance(x, dict)]
    elif name == "serpapi":
        response = requests.get("https://serpapi.com/search.json",
                                params={"engine": "google", "q": q, "num": limit, "api_key": key},
                                timeout=timeout)
        response.raise_for_status()
        raw = response.json().get("organic_results", [])
        results = [{"title": str(x.get("title") or ""), "snippet": str(x.get("snippet") or ""),
                    "url": str(x.get("link") or ""), "source": "SerpAPI"}
                   for x in raw if isinstance(x, dict)]
    else:
        response = requests.post("https://api.exa.ai/search",
                                  headers=_search_headers(name, key),
                                  json={"query": q, "numResults": limit, "contents": {"text": True}},
                                  timeout=timeout)
        response.raise_for_status()
        raw = response.json().get("results", [])
        results = [{"title": str(x.get("title") or ""), "snippet": str(x.get("text") or ""),
                    "url": str(x.get("url") or ""), "source": "Exa"}
                   for x in raw if isinstance(x, dict)]

    normalized = [item for item in results if item.get("url") or item.get("title")]
    return normalized[:limit]


def load_realtime_search_settings(config_path: Path) -> dict[str, str]:
    data = _read(config_path)
    provider = str(data.get("realtime_search_provider") or "tavily").strip().lower()
    return {"provider": provider if provider in _SEARCH_SECRET_NAMES else "tavily"}


def realtime_search_api_key(provider: str, config_path: Path) -> str | None:
    secret_name = _SEARCH_SECRET_NAMES.get(str(provider or "").strip().lower())
    return get_config_secret(secret_name, Path(config_path)).value if secret_name else None


def save_realtime_search_settings(config_path: Path, provider: str, api_key: str):
    name = str(provider or "").strip().lower()
    secret_name = _SEARCH_SECRET_NAMES.get(name)
    if not secret_name:
        raise ValueError("Unsupported real-time search provider")
    key = str(api_key or "").strip()
    if not key:
        raise ValueError("A real-time search API key is required")
    status = save_config_secret(secret_name, key, Path(config_path))
    data = _read(config_path)
    data["realtime_search_provider"] = name
    _write(Path(config_path), data)
    return status


def probe_realtime_search(provider: str, api_key: str, timeout: float = 15.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        results = run_realtime_search(provider, "EDITH real-time search API connectivity test",
                                      api_key, max_results=1, timeout=timeout)
        if not results:
            raise RuntimeError("The search API connected but returned no test result")
        return {"ok": True, "provider": provider, "result_count": len(results),
                "latency_ms": int((time.perf_counter() - started) * 1000), "error": None}
    except Exception as exc:
        key = str(api_key or "")
        detail = str(exc).replace(key, "[REDACTED]")
        return {"ok": False, "provider": provider,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": f"{type(exc).__name__}: {detail[:180]}"}


def load_voice_settings(config_path: Path) -> dict[str, str]:
    data = _read(config_path)
    return {
        "provider": str(data.get("voice_provider") or "gemini_live"),
        "model": str(data.get("voice_model") or VOICE_DEFAULT_MODEL),
    }


def list_voice_models(api_key: str) -> list[str]:
    if not api_key:
        raise RuntimeError("Add the Voice API key before loading models")
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        names = []
        for model in client.models.list():
            name = str(getattr(model, "name", "") or "").strip()
            if name and ("live" in name.lower() or "native-audio" in name.lower()):
                names.append(name if name.startswith("models/") else f"models/{name}")
        return list(dict.fromkeys(names))
    except Exception as exc:
        detail = str(exc).replace(str(api_key), "[REDACTED]")
        raise RuntimeError(f"Voice model list failed: {type(exc).__name__}: {detail[:160]}") from exc


def probe_voice_provider(provider: str, model: str, api_key: str, timeout: float = 22.0) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if str(provider) != "gemini_live":
            raise RuntimeError("This Voice provider is not supported by the current audio transport")
        if not api_key:
            raise RuntimeError("A Gemini Live API key is required")
        from google import genai
        from google.genai import types

        async def _probe() -> bool:
            client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                    )
                ),
            )
            async with client.aio.live.connect(model=model, config=config) as session:
                await session.send_client_content(
                    turns={"parts": [{"text": "Say only: OK."}]}, turn_complete=True,
                )
                async def _wait() -> bool:
                    async for response in session.receive():
                        if getattr(response, "data", None):
                            return True
                        content = getattr(response, "server_content", None)
                        turn = getattr(content, "model_turn", None) if content else None
                        parts = getattr(turn, "parts", None) or []
                        if any(getattr(part, "inline_data", None) is not None or bool(getattr(part, "text", None))
                               for part in parts):
                            return True
                        if content and getattr(content, "turn_complete", False):
                            return False
                    return False
                return await asyncio.wait_for(_wait(), timeout=18.0)

        ok = asyncio.run(asyncio.wait_for(_probe(), timeout=timeout))
        if not ok:
            raise RuntimeError("Live session opened but the model returned no output")
        return {"ok": True, "provider": provider, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000), "error": None}
    except Exception as exc:
        detail = str(exc).replace(str(api_key or ""), "[REDACTED]")
        return {"ok": False, "provider": provider, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": f"{type(exc).__name__}: {detail[:180]}"}


def save_voice_settings(config_path: Path, provider: str, model: str, api_key: str):
    if str(provider) != "gemini_live":
        raise ValueError("Unsupported Voice provider")
    if not str(model or "").strip():
        raise ValueError("Choose a Voice model before saving")
    status = save_gemini_api_key(str(api_key or "").strip(), Path(config_path))
    data = _read(config_path)
    data["voice_provider"] = "gemini_live"
    data["voice_model"] = str(model).strip()
    _write(Path(config_path), data)
    return status


__all__ = [
    "SPECS", "ProviderSpec", "normalize_provider", "provider_spec",
    "load_provider_settings", "has_provider_profile", "provider_api_key",
    "save_provider_settings", "list_provider_models", "probe_provider",
    "run_realtime_search", "probe_realtime_search", "load_realtime_search_settings",
    "realtime_search_api_key", "save_realtime_search_settings",
    "VOICE_DEFAULT_MODEL", "load_voice_settings", "list_voice_models",
    "probe_voice_provider", "save_voice_settings",
]
