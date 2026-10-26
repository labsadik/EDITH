"""OS-keychain backed secrets with a one-time, atomic legacy migration.

Configuration continues to hold non-secret preferences (provider, model, voice,
etc.).  New API keys go to the OS keychain whenever it is available.  A legacy
plaintext key is read only to migrate it; if a machine has no usable keychain,
the old configuration remains usable and is explicitly reported as legacy so a
user is never silently locked out or falsely told the key is secure.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile
from typing import Any

from edith.platform.audit import register_secret

SERVICE_NAME = "EDITH"
GEMINI_SECRET = "gemini_api_key"


@dataclass(frozen=True)
class SecretStatus:
    value: str | None
    storage: str                 # keyring | migrated | legacy | missing
    warning: str | None = None


def _keyring_backend():
    """Return a real OS keyring module, never keyring's fail backend."""
    try:
        import keyring
        backend = keyring.get_keyring()
        module = type(backend).__module__.lower()
        priority = float(getattr(backend, "priority", 0) or 0)
        if priority <= 0 or ".fail" in module:
            return None
        return keyring
    except Exception:
        return None


def _read_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_config(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".edith-config-", suffix=".tmp", delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(value, stream, indent=4)
            stream.write("\n")
        temp_path.replace(path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _keyring_get(name: str) -> str | None:
    backend = _keyring_backend()
    if backend is None:
        return None
    try:
        value = backend.get_password(SERVICE_NAME, name)
        if value:
            register_secret(value)
            return value
    except Exception:
        return None
    return None


def _keyring_set(name: str, value: str) -> bool:
    backend = _keyring_backend()
    if backend is None:
        return False
    try:
        backend.set_password(SERVICE_NAME, name, value)
        register_secret(value)
        return True
    except Exception:
        return False


def get_config_secret(name: str, config_path: Path) -> SecretStatus:
    """Read keychain first; migrate an old config value only after keychain save."""
    current = _keyring_get(name)
    if current:
        return SecretStatus(current, "keyring")

    config = _read_config(config_path)
    legacy = str(config.get(name) or "").strip()
    if not legacy:
        return SecretStatus(None, "missing")

    # Never remove plaintext until the keyring has acknowledged storage.
    if _keyring_set(name, legacy):
        config.pop(name, None)
        config["secret_storage"] = "os_keyring"
        _write_config(config_path, config)
        return SecretStatus(legacy, "migrated")

    register_secret(legacy)
    return SecretStatus(
        legacy, "legacy",
        "No usable OS keychain is available; the existing local key was not removed.",
    )


def save_config_secret(name: str, value: str, config_path: Path) -> SecretStatus:
    """Persist a secret to keychain and scrub plaintext only after success."""
    clean = str(value or "").strip()
    if not clean:
        return SecretStatus(None, "missing", "A secret value is required.")
    if _keyring_set(name, clean):
        config = _read_config(config_path)
        config.pop(name, None)
        config["secret_storage"] = "os_keyring"
        _write_config(config_path, config)
        return SecretStatus(clean, "keyring")

    # Compatibility fallback for existing headless/Linux installations.  It is
    # deliberately labelled, never logged, and will auto-migrate on a later
    # run when an OS keychain becomes available.
    config = _read_config(config_path)
    config[name] = clean
    config["secret_storage"] = "legacy_pending_keyring"
    _write_config(config_path, config)
    register_secret(clean)
    return SecretStatus(
        clean, "legacy",
        "OS keychain unavailable; saved as legacy local configuration pending migration.",
    )


def get_gemini_api_key(config_path: Path) -> str | None:
    return get_config_secret(GEMINI_SECRET, Path(config_path)).value


def save_gemini_api_key(value: str, config_path: Path) -> SecretStatus:
    return save_config_secret(GEMINI_SECRET, value, Path(config_path))


def gemini_key_status(config_path: Path) -> SecretStatus:
    return get_config_secret(GEMINI_SECRET, Path(config_path))
