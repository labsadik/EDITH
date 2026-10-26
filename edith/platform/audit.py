"""Redacted, rotating local action receipts; never persist credentials."""
from __future__ import annotations
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import threading
from datetime import datetime, timezone

_SECRET = re.compile(r'(?i)(api.?key|token|password|secret|authorization|cookie|credential)')
_INLINE = re.compile(r'(?i)((?:api[_-]?key|token|password|secret|authorization)[\s=:]+)[^\s,;]+')
_KNOWN_SECRETS = set()

def register_secret(value):
    if isinstance(value,str) and len(value)>=6:
        _KNOWN_SECRETS.add(value)

def redact(value):
    if isinstance(value, dict):
        return {str(k): '[REDACTED]' if _SECRET.search(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value[:200]]
    if isinstance(value, str):
        value = _INLINE.sub(r'\1[REDACTED]', value)
        for secret in tuple(_KNOWN_SECRETS):
            value = value.replace(secret,'[REDACTED]')
        return value[:12000]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(type(value).__name__)

class AuditLog:
    def __init__(self, path=None, listener=None):
        self.path = Path(path or Path.home() / '.edith' / 'logs' / 'actions.jsonl')
        self.listener = listener
        self._lock = threading.Lock()
        self._logger = None
        self.error = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.parent.chmod(0o700)
            handler = RotatingFileHandler(self.path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
            self.path.chmod(0o600)
            logger = logging.Logger('edith.audit.' + str(id(self)))
            logger.addHandler(handler)
            self._logger = logger
        except OSError as exc:
            self.error = type(exc).__name__

    def write(self, actor, operation, arguments, tier, result, **extra):
        entry = redact({'timestamp': datetime.now(timezone.utc).isoformat(), 'actor': actor,
                        'operation': operation, 'arguments': arguments, 'tier': int(tier),
                        'result': result, **extra})
        with self._lock:
            if self._logger:
                self._logger.info(json.dumps(entry, ensure_ascii=False, default=str))
        if self.listener:
            try:
                self.listener(entry)
            except Exception:
                pass
        return entry
