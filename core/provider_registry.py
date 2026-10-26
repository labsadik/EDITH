"""Provider settings, credentials and connection probes for EDITH text models.

This registry does not replace the Gemini Live voice transport.  It owns the
configurable text/model-provider path used by local agents, so selecting a
provider cannot silently alter the live voice session.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
import time
from typing import Any, Mapping

import requests

from core.secrets import get_config_secret, save_config_secret


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
    "openai": ProviderSpec("openai", "OpenAI / ChatGPT", "https://api.openai.com/v1", "gpt-4.1-mini", "openai_api_key"),
    "anthropic": ProviderSpec("anthropic", "Anthropic Claude", "https://api.anthropic.com/v1", "claude-sonnet-4-20250514", "anthropic_api_key", "anthropic"),
    "xai": ProviderSpec("xai", "xAI Grok", "https://api.x.ai/v1", "grok-3-mini", "xai_api_key"),
    "openai_compatible": ProviderSpec("openai_compatible", "OpenAI-compatible local server", "http://localhost:1234/v1", "local-model", protocol="openai"),
    "gemini": ProviderSpec("gemini", "Google Gemini Live", "", "models/gemini-2.5-flash-native-audio-preview-12-2025", "gemini_api_key", "gemini_live"),
}

_ALIASES = {
    "lmstudio": "openai_compatible", "localai": "openai_compatible", "jan": "openai_compatible",
    "llamacpp": "openai_compatible", "chatgpt": "openai", "claude": "anthropic", "grok": "xai",
}


def normalize_provider(value: object) -> str:
    name = str(value or "ollama").strip().lower().replace("-", "_")
    name = _ALIASES.get(name, name)
    return name if name in SPECS else "ollama"


def provider_spec(value: object) -> ProviderSpec:
    return SPECS[normalize_provider(value)]


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".edith-provider-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(dict(data), stream, indent=4)
            stream.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_provider_settings(config_path: Path) -> dict[str, str]:
    data = _read(Path(config_path))
    # Preserve the historic openai+localhost configuration as an OpenAI-
    # compatible local endpoint rather than suddenly asking it for a cloud key.
    raw = str(data.get("llm_provider") or "ollama")
    provider = normalize_provider(raw)
    url = str(data.get("llm_url") or "").rstrip("/")
    if raw.strip().lower() == "openai" and ("localhost" in url or "127.0.0.1" in url):
        provider = "openai_compatible"
    spec = provider_spec(provider)
    return {
        "provider": provider,
        "url": url or spec.default_url,
        "model": str(data.get("llm_model") or spec.default_model),
    }


def provider_api_key(provider: object, config_path: Path) -> str | None:
    spec = provider_spec(provider)
    return get_config_secret(spec.secret_name, Path(config_path)).value if spec.secret_name else None


def save_provider_settings(config_path: Path, provider: object, url: str, model: str,
                           api_key: str = "") -> dict[str, str]:
    """Save non-secret selection atomically; secrets use OS keychain storage."""
    spec = provider_spec(provider)
    clean_url = str(url or spec.default_url).strip().rstrip("/")
    clean_model = str(model or spec.default_model).strip()
    if spec.protocol != "gemini_live" and (not clean_url or not clean_model):
        raise ValueError("Provider endpoint and model are required")
    data = _read(Path(config_path))
    # Existing callers understand ``openai`` as any OpenAI-compatible protocol.
    # The richer identifier stays in provider_profile for the settings UI.
    data["llm_provider"] = "openai" if spec.protocol == "openai" else spec.identifier
    data["llm_url"] = clean_url
    data["llm_model"] = clean_model
    data["provider_profile"] = spec.identifier
    _write(Path(config_path), data)
    if spec.secret_name and str(api_key or "").strip():
        save_config_secret(spec.secret_name, str(api_key).strip(), Path(config_path))
    return {"provider": spec.identifier, "url": clean_url, "model": clean_model}


def _headers(spec: ProviderSpec, key: str | None) -> dict[str, str]:
    if not key:
        return {}
    if spec.protocol == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {key}"}


def probe_provider(provider: object, url: str, model: str, api_key: str | None = None,
                   timeout: float = 20.0) -> dict[str, Any]:
    """Make one real, minimal request and return a structured, redacted result."""
    spec = provider_spec(provider)
    base = str(url or spec.default_url).rstrip("/")
    started = time.perf_counter()
    try:
        if spec.protocol == "gemini_live":
            raise RuntimeError("Gemini Live is tested by the existing Live API test button")
        if spec.secret_name and not api_key:
            raise RuntimeError("An API key is required for this provider")
        if spec.protocol == "ollama":
            response = requests.post(f"{base}/api/chat", json={"model": model, "stream": False,
                                     "messages": [{"role": "user", "content": "Reply only OK."}]}, timeout=timeout)
            response.raise_for_status()
            content = response.json().get("message", {}).get("content", "")
        elif spec.protocol == "anthropic":
            response = requests.post(f"{base}/messages", headers=_headers(spec, api_key), json={
                "model": model, "max_tokens": 8, "messages": [{"role": "user", "content": "Reply only OK."}],
            }, timeout=timeout)
            response.raise_for_status()
            content = "".join(str(part.get("text") or "") for part in response.json().get("content", []) if isinstance(part, dict))
        else:
            response = requests.post(f"{base}/chat/completions", headers=_headers(spec, api_key), json={
                "model": model, "messages": [{"role": "user", "content": "Reply only OK."}], "max_tokens": 8,
            }, timeout=timeout)
            response.raise_for_status()
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        if not str(content).strip():
            raise RuntimeError("Provider returned no text response")
        return {"ok": True, "provider": spec.identifier, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000), "error": None}
    except Exception as exc:
        detail = str(exc).replace(str(api_key or ""), "[REDACTED]")
        return {"ok": False, "provider": spec.identifier, "model": model,
                "latency_ms": int((time.perf_counter() - started) * 1000),
                "error": f"{type(exc).__name__}: {detail[:180]}"}


__all__ = ["SPECS", "ProviderSpec", "normalize_provider", "provider_spec", "load_provider_settings",
           "provider_api_key", "save_provider_settings", "probe_provider"]
