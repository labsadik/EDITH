"""Optional MCP server catalog and a small, dependency-free stdio MCP client.

Server commands live in ``config/mcp_servers.json`` and are never supplied by
model text. Each configured server becomes an independently toggleable plugin.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from typing import Any, Callable
import urllib.error
import urllib.request
import webbrowser

from core.secrets import get_config_secret, save_config_secret
from core.app_paths import config_path, writable_config_path


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = writable_config_path("mcp_servers.json")
DEFAULT_SECRETS_PATH = config_path()
PROTOCOL_VERSION = "2024-11-05"

DEFAULT_SERVERS = (
    {
        "id": "gmail",
        "name": "Gmail MCP",
        "description": "Google's remote Gmail MCP profile. Configure OAuth before enabling it.",
        "transport": "streamable_http",
        "url": "https://gmailmcp.googleapis.com/mcp/v1",
        "command": [],
        "enabled": False,
        "token_env": "EDITH_GMAIL_MCP_ACCESS_TOKEN",
        "login_url": "https://developers.google.com/workspace/gmail/api/guides/configure-mcp-server",
        "icon": "G",
    },
    {
        "id": "github",
        "name": "GitHub MCP",
        "description": "Use the owner's configured GitHub MCP server for repository work.",
        "command": [],
        "enabled": False,
        "login_url": "https://github.com/login",
        "icon": "GH",
    },
    {
        "id": "filesystem",
        "name": "Filesystem MCP",
        "description": "Use the owner's configured filesystem MCP server for its explicitly configured workspace.",
        "command": [],
        "enabled": False,
        "login_url": "",
        "icon": "FS",
    },
    # Connection templates only: an owner pastes a trusted compatible endpoint
    # in the Plugin Manager. These entries never claim a public endpoint exists.
    {"id": "google_drive", "name": "Google Drive MCP", "description": "Connect a trusted Google Drive-compatible MCP endpoint.", "transport": "streamable_http", "url": "", "command": [], "enabled": False, "login_url": "https://developers.google.com/workspace/drive/api/guides/about-sdk", "icon": "DR"},
    {"id": "google_calendar", "name": "Google Calendar MCP", "description": "Connect a trusted Google Calendar-compatible MCP endpoint.", "transport": "streamable_http", "url": "", "command": [], "enabled": False, "login_url": "https://developers.google.com/workspace/calendar/api/guides/overview", "icon": "CA"},
    {"id": "notion", "name": "Notion MCP", "description": "Connect a trusted Notion-compatible MCP endpoint.", "transport": "streamable_http", "url": "", "command": [], "enabled": False, "login_url": "https://developers.notion.com/", "icon": "NO"},
    {"id": "slack", "name": "Slack MCP", "description": "Connect a trusted Slack-compatible MCP endpoint.", "transport": "streamable_http", "url": "", "command": [], "enabled": False, "login_url": "https://api.slack.com/", "icon": "SL"},
    {"id": "linear", "name": "Linear MCP", "description": "Connect a trusted Linear-compatible MCP endpoint.", "transport": "streamable_http", "url": "", "command": [], "enabled": False, "login_url": "https://linear.app/developers", "icon": "LI"},
)


@dataclass(frozen=True)
class MCPServerSpec:
    id: str
    name: str
    description: str
    command: tuple[str, ...]
    enabled: bool
    transport: str = "stdio"
    url: str = ""
    token_env: str = ""
    login_url: str = ""
    icon: str = "MCP"
    timeout_seconds: float = 25.0

    @property
    def plugin_name(self) -> str:
        return "mcp_" + self.id

    @property
    def token_secret_name(self) -> str:
        return f"mcp_{self.id}_access_token"

    @property
    def configured(self) -> bool:
        return bool(self.url) if self.transport == "streamable_http" else bool(self.command)


class MCPProtocolError(RuntimeError):
    def __init__(self, message: str, *, data: Any = None):
        super().__init__(message)
        self.data = data


class MCPStdioClient:
    """A one-request stdio client. New processes keep plugin calls isolated."""

    def __init__(self, spec: MCPServerSpec):
        self.spec = spec
        self.process: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[str | None] = queue.Queue()
        self._next_id = 0

    def __enter__(self):
        if not self.spec.configured:
            raise MCPProtocolError(
                f"{self.spec.name} has no command configured. Add its trusted server command to config/mcp_servers.json."
            )
        self.process = subprocess.Popen(
            list(self.spec.command), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._read_stdout, daemon=True, name=f"edith-mcp-{self.spec.id}").start()
        self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "EDITH", "version": "1.0"},
        })
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, *_):
        if self.process is None:
            return
        try:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=1)
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass
        finally:
            # Popen owns three file objects.  Explicitly closing them avoids
            # descriptor accumulation when an assistant makes several MCP
            # requests in one session.
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except OSError:
                    pass

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            self._lines.put(line)
        self._lines.put(None)

    def _send(self, payload: dict) -> None:
        if not self.process or not self.process.stdin:
            raise MCPProtocolError("MCP server is not running")
        self.process.stdin.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def notify(self, method: str, params: dict) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + max(1.0, self.spec.timeout_seconds)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MCPProtocolError(f"{self.spec.name} did not respond within {self.spec.timeout_seconds:g} seconds")
            try:
                line = self._lines.get(timeout=remaining)
            except queue.Empty:
                continue
            if line is None:
                raise MCPProtocolError(f"{self.spec.name} exited before responding")
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"] or {}
                raise MCPProtocolError(str(error.get("message") or "MCP request failed"), data=error.get("data"))
            return message.get("result")

    def list_tools(self) -> list[dict]:
        value = self.request("tools/list", {}) or {}
        tools = value.get("tools", []) if isinstance(value, dict) else []
        return [tool for tool in tools if isinstance(tool, dict)][:100]

    def call_tool(self, tool: str, arguments: dict) -> Any:
        return self.request("tools/call", {"name": tool, "arguments": arguments})


class MCPHttpClient:
    """Minimal Streamable-HTTP MCP client for explicitly configured servers.

    The configured token environment variable is intentionally the only
    credential input here. EDITH neither reads browser cookies nor accepts a
    bearer token from model text.
    """

    def __init__(self, spec: MCPServerSpec, *, opener=urllib.request.urlopen,
                 token_provider: Callable[[], str | None] | None = None):
        self.spec = spec
        self._opener = opener
        self._token_provider = token_provider
        self._next_id = 0
        self._session_id = ""

    def __enter__(self):
        if not self.spec.configured:
            raise MCPProtocolError(f"{self.spec.name} has no remote MCP URL configured.")
        self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "EDITH", "version": "1.0"},
        })
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, *_):
        return False

    @staticmethod
    def _decode_body(raw: bytes) -> Any:
        text = raw.decode("utf-8", errors="replace").strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Streamable HTTP servers may reply as an SSE sequence. Only MCP
            # JSON data events are relevant to the request/reply contract.
            for line in text.splitlines():
                if line.startswith("data:"):
                    try:
                        return json.loads(line[5:].strip())
                    except json.JSONDecodeError:
                        continue
        raise MCPProtocolError("MCP HTTP server returned an invalid JSON response")

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        token = ""
        if self.spec.token_env:
            import os
            token = os.environ.get(self.spec.token_env, "").strip()
        if not token and self._token_provider is not None:
            try:
                token = str(self._token_provider() or "").strip()
            except Exception:
                token = ""
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _post(self, payload: dict) -> Any:
        request = urllib.request.Request(
            self.spec.url,
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            headers=self._headers(), method="POST",
        )
        try:
            with self._opener(request, timeout=self.spec.timeout_seconds) as response:
                session = response.headers.get("Mcp-Session-Id", "")
                if session:
                    self._session_id = session
                return self._decode_body(response.read())
        except urllib.error.HTTPError as exc:
            body = exc.read() if hasattr(exc, "read") else b""
            detail = ""
            try:
                decoded = self._decode_body(body)
                detail = str(decoded.get("error", {}).get("message", "")) if isinstance(decoded, dict) else ""
            except MCPProtocolError:
                pass
            message = detail or f"HTTP {exc.code} from {self.spec.name}"
            if exc.code in (401, 403):
                message = f"{message}; authentication is required"
            raise MCPProtocolError(message) from exc
        except (OSError, ValueError) as exc:
            raise MCPProtocolError(f"{self.spec.name} HTTP connection failed: {exc}") from exc

    def notify(self, method: str, params: dict) -> None:
        self._post({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict) -> Any:
        self._next_id += 1
        request_id = self._next_id
        response = self._post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not isinstance(response, dict):
            raise MCPProtocolError("MCP HTTP server returned a non-object response")
        if "error" in response:
            error = response.get("error") or {}
            raise MCPProtocolError(str(error.get("message") or "MCP request failed"), data=error.get("data"))
        if response.get("id") not in (None, request_id):
            raise MCPProtocolError("MCP HTTP server returned a mismatched response id")
        return response.get("result")

    def list_tools(self) -> list[dict]:
        value = self.request("tools/list", {}) or {}
        tools = value.get("tools", []) if isinstance(value, dict) else []
        return [tool for tool in tools if isinstance(tool, dict)][:100]

    def call_tool(self, tool: str, arguments: dict) -> Any:
        return self.request("tools/call", {"name": tool, "arguments": arguments})


class MCPRegistry:
    def __init__(self, config_path: Path = DEFAULT_CONFIG_PATH, logger: Callable[[str], None] = print,
                 secrets_path: Path = DEFAULT_SECRETS_PATH):
        self.config_path = Path(config_path)
        self.secrets_path = Path(secrets_path)
        self.logger = logger
        self._pending: dict[str, tuple[str, dict]] = {}

    def _read_config(self) -> dict:
        if not self.config_path.exists():
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(json.dumps({"servers": list(DEFAULT_SERVERS)}, indent=2) + "\n", encoding="utf-8")
        try:
            data = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"servers": []}
        if not isinstance(data, dict):
            return {"servers": []}
        servers = data.get("servers")
        if not isinstance(servers, list):
            data["servers"] = servers = []
        existing = {str(item.get("id") or "").strip().lower() for item in servers if isinstance(item, dict)}
        additions = [dict(item) for item in DEFAULT_SERVERS if item["id"] not in existing]
        if additions:
            servers.extend(additions)
            self.config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return data

    def specs(self) -> list[MCPServerSpec]:
        data = self._read_config()
        raw = data.get("servers", [])
        if not isinstance(raw, list):
            return []
        seen: set[str] = set()
        result = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            server_id = str(item.get("id") or "").strip().lower().replace("-", "_")
            if not server_id or not server_id.replace("_", "").isalnum() or server_id in seen:
                continue
            transport = str(item.get("transport") or "stdio").strip().lower()
            if transport not in {"stdio", "streamable_http"}:
                continue
            command = item.get("command") or []
            if isinstance(command, str):
                command = [command]
            if not isinstance(command, list) or not all(isinstance(part, str) and part.strip() for part in command):
                command = []
            try:
                timeout_seconds = min(120.0, max(3.0, float(item.get("timeout_seconds", 25))))
            except (TypeError, ValueError):
                timeout_seconds = 25.0
            seen.add(server_id)
            result.append(MCPServerSpec(
                id=server_id,
                name=str(item.get("name") or server_id),
                description=str(item.get("description") or f"MCP server: {server_id}"),
                command=tuple(command), enabled=bool(item.get("enabled", False)),
                transport=transport,
                url=str(item.get("url") or "").strip(),
                token_env=str(item.get("token_env") or "").strip(),
                login_url=str(item.get("login_url") or ""),
                icon=str(item.get("icon") or "MCP")[:4],
                timeout_seconds=timeout_seconds,
            ))
        return result

    def spec(self, server_id: str) -> MCPServerSpec | None:
        return next((item for item in self.specs() if item.id == server_id), None)

    def set_enabled(self, server_id: str, enabled: bool) -> bool:
        data = self._read_config()
        servers = data.get("servers", [])
        for item in servers if isinstance(servers, list) else []:
            if isinstance(item, dict) and str(item.get("id") or "").strip().lower().replace("-", "_") == server_id:
                item["enabled"] = bool(enabled)
                self.config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                return True
        return False

    def configure_remote(self, server_id: str, url: str) -> bool:
        """Persist an owner-provided HTTPS Streamable-HTTP endpoint.

        This path is only called by the local settings UI; model text cannot
        add endpoints or cause EDITH to connect to an arbitrary server.
        """
        from urllib.parse import urlsplit
        clean = str(url or "").strip()
        parsed = urlsplit(clean)
        if parsed.scheme != "https" or not parsed.netloc:
            raise MCPProtocolError("MCP endpoint must be a complete HTTPS URL.")
        data = self._read_config()
        for item in data.get("servers", []):
            if isinstance(item, dict) and str(item.get("id") or "").strip().lower().replace("-", "_") == server_id:
                item["transport"] = "streamable_http"
                item["url"] = clean
                self.config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
                return True
        return False

    def token_status(self, server_id: str) -> str:
        spec = self.spec(server_id)
        if spec is None:
            return "missing"
        if spec.token_env:
            import os
            if os.environ.get(spec.token_env, "").strip():
                return "environment"
        return get_config_secret(spec.token_secret_name, self.secrets_path).storage

    def save_access_token(self, server_id: str, token: str) -> str:
        spec = self.spec(server_id)
        if spec is None:
            raise MCPProtocolError(f"Unknown MCP server '{server_id}'.")
        status = save_config_secret(spec.token_secret_name, token, self.secrets_path)
        if not status.value:
            raise MCPProtocolError(status.warning or "An access token is required.")
        return status.storage

    def connection_info(self, server_id: str) -> dict[str, str]:
        spec = self.spec(server_id)
        if spec is None:
            raise MCPProtocolError(f"Unknown MCP server '{server_id}'.")
        return {
            "server": spec.id,
            "endpoint": spec.url,
            "configured": str(spec.configured).lower(),
            "token_storage": self.token_status(spec.id),
            "setup_url": spec.login_url,
        }

    def _require_enabled(self, server_id: str) -> MCPServerSpec:
        spec = self.spec(server_id)
        if spec is None:
            raise MCPProtocolError(f"Unknown MCP server '{server_id}'.")
        if not spec.enabled:
            raise MCPProtocolError(f"{spec.name} is OFF. Enable its toggle in Plugins first.")
        return spec

    def list_tools(self, server_id: str) -> list[dict]:
        spec = self._require_enabled(server_id)
        with self._client(spec) as client:
            return client.list_tools()

    def call(self, server_id: str, tool: str, arguments: dict) -> Any:
        spec = self._require_enabled(server_id)
        try:
            with self._client(spec) as client:
                return client.call_tool(tool, arguments)
        except MCPProtocolError as exc:
            text = str(exc).lower()
            if "auth" not in text and "login" not in text and "oauth" not in text:
                raise
            self._pending[server_id] = (tool, dict(arguments))
            if spec.login_url:
                webbrowser.open(spec.login_url)
            raise MCPProtocolError(
                f"{spec.name} requires login. The browser login page was opened; use action=resume after login.",
                data={"login_url": spec.login_url},
            ) from exc

    def _client(self, spec: MCPServerSpec):
        return (MCPHttpClient(
            spec,
            token_provider=lambda: get_config_secret(spec.token_secret_name, self.secrets_path).value,
        ) if spec.transport == "streamable_http" else MCPStdioClient(spec))

    def begin_login(self, server_id: str) -> dict[str, str]:
        """Open the owner's configured authorization/setup URL, never a browser session."""
        spec = self._require_enabled(server_id)
        if not spec.login_url:
            raise MCPProtocolError(f"{spec.name} has no login URL configured.")
        opened = bool(webbrowser.open(spec.login_url))
        return {
            "server": spec.id,
            "url": spec.login_url,
            "opened": str(opened).lower(),
            "next": "Complete provider setup, paste the issued access token in Plugin Manager, then test the connection.",
        }

    def resume(self, server_id: str) -> Any:
        pending = self._pending.get(server_id)
        if pending is None:
            raise MCPProtocolError(f"No pending login task for MCP server '{server_id}'.")
        tool, arguments = pending
        value = self.call(server_id, tool, arguments)
        self._pending.pop(server_id, None)
        return value


__all__ = ["MCPRegistry", "MCPServerSpec", "MCPStdioClient", "MCPHttpClient", "MCPProtocolError"]
