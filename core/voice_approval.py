"""One-time voice/text approval binding for a locally pending action.

The model never supplies an approval bit.  This gate observes only an
input-transcription or typed reply from the active user session and accepts a
small, exact allowlist while one specific action is pending.  It deliberately
does not attempt to infer consent from a longer conversational sentence.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import re
import secrets
import time
from typing import Any, Mapping


_APPROVE = {
    "yes", "yes do it", "confirm", "approve", "proceed", "do it",
    "হ্যাঁ", "হ্যা", "হ্যাঁ করো", "হ্যা করো", "করো", "অনুমোদন", "সম্মতি", "ঠিক আছে",
}
_REJECT = {
    "no", "cancel", "do not", "don't", "stop", "reject",
    "না", "বাতিল", "থামো", "করো না", "না করো",
}
_INTERRUPT = {"stop", "stop now", "cancel task", "থামো", "থেমে যাও", "বন্ধ করো"}


def _clean(value: object) -> str:
    text = str(value or "").casefold().strip()
    # Keep Bengali combining marks explicitly; ``\w`` alone drops several of
    # them and would turn “থেমে যাও” into a different phrase.
    text = re.sub(r"[^\w\s\u0980-\u09ff'’]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def is_interrupt_phrase(utterance: object) -> bool:
    """A narrow local stop command, accepted while a task input gate is closed."""
    return _clean(utterance) in _INTERRUPT


def _fingerprint(operation: str, arguments: Mapping[str, Any]) -> str:
    # Dispatcher-only fields do not identify the requested user operation.
    clean = {str(k): v for k, v in dict(arguments).items() if not str(k).startswith("_")}
    canonical = json.dumps({"operation": str(operation), "arguments": clean},
                           ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class PendingVoiceApproval:
    token: str
    operation: str
    fingerprint: str
    expires_at: float
    event: asyncio.Event
    decision: bool | None = None


class VoiceApprovalGate:
    """Own at most one short-lived consent request per EDITH session."""

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._pending: PendingVoiceApproval | None = None

    @property
    def pending(self) -> PendingVoiceApproval | None:
        pending = self._pending
        if pending and self._clock() >= pending.expires_at:
            self.cancel(pending.token)
            return None
        return self._pending

    def begin(self, operation: str, arguments: Mapping[str, Any], *, timeout: float = 25.0) -> PendingVoiceApproval:
        if self.pending is not None:
            raise RuntimeError("A sensitive-action approval is already pending")
        request = PendingVoiceApproval(
            token=secrets.token_urlsafe(12),
            operation=str(operation),
            fingerprint=_fingerprint(operation, arguments),
            expires_at=self._clock() + max(1.0, float(timeout)),
            event=asyncio.Event(),
        )
        self._pending = request
        return request

    def observe(self, utterance: object) -> bool | None:
        """Resolve only the currently pending action from an exact reply."""
        request = self.pending
        if request is None:
            return None
        phrase = _clean(utterance)
        if phrase in _APPROVE:
            request.decision = True
        elif phrase in _REJECT:
            request.decision = False
        else:
            return None
        request.event.set()
        return request.decision

    async def wait(self, token: str) -> bool | None:
        request = self.pending
        if request is None or request.token != token:
            return None
        try:
            await asyncio.wait_for(request.event.wait(), max(0.0, request.expires_at - self._clock()))
        except asyncio.TimeoutError:
            pass
        if self._pending is request:
            self._pending = None
        return request.decision

    def cancel(self, token: str | None = None) -> bool:
        request = self._pending
        if request is None or (token is not None and request.token != token):
            return False
        self._pending = None
        request.decision = False
        request.event.set()
        return True


__all__ = ["VoiceApprovalGate", "PendingVoiceApproval", "is_interrupt_phrase"]
