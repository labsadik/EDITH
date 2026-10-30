"""Single text-reasoning brain router for EDITH's specialist agents."""
from __future__ import annotations

from typing import Any

CANONICAL_BRAIN_PROFILE = "powerful"
CANONICAL_BRAIN_NAME = "Powerful Brain"
VOICE_RUNTIME = "gemini_live"


def resolve_brain_profile(role: str | None = None, workload: str | None = None) -> str:
    """All non-voice text reasoning converges on one configured model profile."""
    selected = str(role or "").strip().lower()
    if selected in {"voice", "audio", "gemini_live"}:
        raise ValueError("Voice/audio sessions use the dedicated Live voice transport, not the text brain router")
    return CANONICAL_BRAIN_PROFILE


def call_brain_text(
    prompt: str, *, system: str | None = None, model: str | None = None,
    timeout: int = 120, role: str | None = None, workload: str | None = None,
) -> str:
    """Generate text through Powerful Brain regardless of legacy Main Brain labels."""
    from core.llm_client import call_llm_text
    return call_llm_text(
        str(prompt), system=system, model=model, timeout=timeout,
        profile=resolve_brain_profile(role, workload),
    )


def call_brain(
    messages: list[dict[str, Any]], *, tools: list | None = None,
    timeout: int = 120, max_tokens: int = 150,
    role: str | None = None, workload: str | None = None,
) -> dict[str, Any]:
    """Chat/tool call through the single Powerful Brain profile."""
    from core.llm_client import call_llm
    return call_llm(
        messages, tools=tools, timeout=timeout, max_tokens=max_tokens,
        profile=resolve_brain_profile(role, workload),
    )


__all__ = [
    "CANONICAL_BRAIN_NAME", "CANONICAL_BRAIN_PROFILE", "VOICE_RUNTIME",
    "call_brain", "call_brain_text", "resolve_brain_profile",
]
