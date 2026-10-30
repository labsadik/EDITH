"""Paired, allowlisted MQTT access for EDITH's Smart Network agent.

No discovery scan or arbitrary command channel is provided. Broker endpoints and
exact topics must be paired locally by the owner before the model can read/write.
"""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import ssl
from pathlib import Path
from typing import Any

from core.app_paths import config_path
from urllib.parse import urlsplit

_CONFIG_PATH = config_path()
_TOPIC = re.compile(r"^[A-Za-z0-9_./ -]{1,240}$")
_MAX_PAYLOAD = 4096


def _read_config(path: Path | None = None) -> dict[str, Any]:
    target = path or _CONFIG_PATH
    try:
        value = json.loads(target.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _write_config(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def _broker_parts(value: str) -> tuple[str, int, bool]:
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in {"mqtt", "mqtts"} or not parts.hostname:
        raise ValueError("Broker URL must use mqtt:// or mqtts:// and include a host")
    if parts.username or parts.password or parts.path not in {"", "/"} or parts.query or parts.fragment:
        raise ValueError("Put MQTT credentials in the local pairing form, not the broker URL")
    host = parts.hostname.strip().lower()
    tls = parts.scheme == "mqtts"
    port = parts.port or (8883 if tls else 1883)
    if not 1 <= port <= 65535:
        raise ValueError("MQTT broker port is out of range")
    if not tls:
        local = host in {"localhost", "127.0.0.1", "::1"} or host.endswith((".local", ".lan", ".home"))
        try:
            address = ipaddress.ip_address(host)
            local = local or address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            pass
        if not local:
            raise ValueError("Remote MQTT brokers must use mqtts:// with TLS")
    return host, port, tls


def _normalise_topics(topics: list[str] | tuple[str, ...]) -> list[str]:
    if not isinstance(topics, (list, tuple)):
        raise ValueError("MQTT topic allowlist must be a list of exact topics")
    clean: list[str] = []
    for value in topics:
        topic = str(value or "").strip()
        if (not _TOPIC.fullmatch(topic) or "+" in topic or "#" in topic
                or topic.startswith("$") or "//" in topic):
            raise ValueError(f"Invalid or unsafe MQTT topic: {topic[:80]}")
        if topic not in clean:
            clean.append(topic)
    if not clean:
        raise ValueError("Pair at least one exact MQTT topic")
    return clean[:64]


def configure_mqtt(
    broker_url: str, topics: list[str] | tuple[str, ...],
    username: str = "", password: str = "", *, config_path: Path | None = None,
) -> dict[str, Any]:
    """Pair a broker locally; passwords go through EDITH's OS-keychain helper."""
    host, port, tls = _broker_parts(broker_url)
    allowed = _normalise_topics(topics)
    if password and not username:
        raise ValueError("A broker username is required when a password is supplied")
    target = config_path or _CONFIG_PATH
    data = _read_config(target)
    data["mqtt_broker_url"] = str(broker_url).strip().rstrip("/")
    data["mqtt_username"] = str(username or "").strip()
    data["mqtt_topics"] = allowed
    secret_status = None
    if password:
        from core.secrets import save_config_secret
        secret_status = save_config_secret("mqtt_password", password, target)
    elif username:
        raise ValueError("A password is required when a broker username is supplied")
    _write_config(target, data)
    return {
        "saved": True, "host": host, "port": port, "tls": tls,
        "topics": allowed,
        "credential_storage": getattr(secret_status, "storage", "not required"),
    }


def _pairing(config_path: Path | None = None) -> tuple[dict[str, Any], str, int, bool, str]:
    target = config_path or _CONFIG_PATH
    data = _read_config(target)
    broker = str(data.get("mqtt_broker_url") or "").strip()
    if not broker:
        raise RuntimeError("MQTT is not paired. Run: python scripts/configure_mqtt.py --help")
    host, port, tls = _broker_parts(broker)
    topics = _normalise_topics(data.get("mqtt_topics") or [])
    username = str(data.get("mqtt_username") or "").strip()
    password = ""
    if username:
        from core.secrets import get_config_secret
        password = str(get_config_secret("mqtt_password", target).value or "")
        if not password:
            raise RuntimeError("MQTT password is missing from the OS keychain; pair the broker again")
    return data, host, port, tls, password


def _require_topic(topic: str, allowed: list[str]) -> str:
    clean = str(topic or "").strip()
    if clean not in allowed:
        raise PermissionError("MQTT topic is not in the locally paired exact-topic allowlist")
    return clean


def _mqtt_api():
    try:
        from paho.mqtt import client, publish, subscribe
    except ImportError as exc:
        raise RuntimeError("Install paho-mqtt from requirements.txt to enable MQTT") from exc
    return client, publish, subscribe


def run_mqtt_action(
    action: str, *, topic: str = "", payload: str = "", timeout: float = 5.0,
    config_path: Path | None = None,
) -> dict[str, Any]:
    """Perform a paired MQTT status, one-message read, or non-retained publish."""
    data, host, port, tls, password = _pairing(config_path)
    username = str(data.get("mqtt_username") or "").strip()
    options: dict[str, Any] = {
        "hostname": host, "port": port, "keepalive": 15,
    }
    auth = {"username": username, "password": password} if username else None
    tls_options = {} if tls else None
    if auth:
        options["auth"] = auth
    if tls_options is not None:
        options["tls"] = tls_options
    mode = str(action or "").strip().lower()
    if mode == "mqtt_status":
        from threading import Event
        client_module, _publish, _subscribe = _mqtt_api()
        client = client_module.Client(
            callback_api_version=client_module.CallbackAPIVersion.VERSION2,
            client_id="edith-status-check",
        )
        if auth:
            client.username_pw_set(username, password)
        if tls:
            client.tls_set_context(ssl.create_default_context())
        connected = Event()
        outcome: dict[str, Any] = {}
        def _on_connect(_client, _userdata, _flags, reason_code, _properties):
            outcome["reason_code"] = int(getattr(reason_code, "value", reason_code))
            connected.set()
        client.on_connect = _on_connect
        result = client.connect(host, port, keepalive=15)
        if result != 0:
            raise RuntimeError(f"MQTT broker socket connection failed (code {result})")
        client.loop_start()
        try:
            if not connected.wait(max(1.0, min(float(timeout), 10.0))):
                raise TimeoutError("MQTT broker did not acknowledge the connection")
            if outcome.get("reason_code", 1) != 0:
                raise RuntimeError(f"MQTT broker rejected the connection (code {outcome['reason_code']})")
        finally:
            try:
                client.disconnect()
            finally:
                client.loop_stop()
        return {"ok": True, "broker_reachable": True, "authenticated": True,
                "tls": tls, "host": host, "port": port}
    allowed = _normalise_topics(data.get("mqtt_topics") or [])
    target_topic = _require_topic(topic, allowed)
    if mode == "mqtt_read":
        _client, _publish_api, subscribe_api = _mqtt_api()
        message = subscribe_api.simple(
            target_topic, qos=1, timeout=max(1.0, min(float(timeout), 15.0)), **options
        )
        raw = getattr(message, "payload", b"")
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
        return {"ok": True, "topic": target_topic, "payload": text[:_MAX_PAYLOAD],
                "qos": int(getattr(message, "qos", 0))}
    if mode == "mqtt_publish":
        text = str(payload or "")
        if not text:
            raise ValueError("MQTT publish payload cannot be empty")
        if len(text.encode("utf-8")) > _MAX_PAYLOAD:
            raise ValueError("MQTT publish payload exceeds 4 KB")
        _client, publish_api, _subscribe_api = _mqtt_api()
        # QoS 1 waits for broker acknowledgement; retained messages are never written.
        publish_api.single(
            target_topic, payload=text, qos=1, retain=False, **options
        )
        return {"ok": True, "topic": target_topic, "qos": 1, "retained": False}
    raise ValueError("MQTT action must be mqtt_status, mqtt_read or mqtt_publish")


__all__ = ["configure_mqtt", "run_mqtt_action"]
