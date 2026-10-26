"""One shared telemetry worker; Qt/audio consumers only read its cached snapshot."""
import atexit
import threading
from . import get_controller
from .base import result
from .telemetry import TelemetryService

_lock = threading.Lock()
_service = None

def telemetry_service():
    global _service
    with _lock:
        if _service is None:
            _service = TelemetryService(get_controller())
            _service.start()
            atexit.register(_service.stop)
        return _service

def cached_telemetry():
    return telemetry_service().snapshot().get('data') or {}
