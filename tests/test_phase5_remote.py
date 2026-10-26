"""Phase 5: real remote HTTP/WebSocket compatibility and failure-path checks.

No Gemini API key, local model or microphone required.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from dashboard.server import DashboardServer


ROOT = Path(__file__).resolve().parents[1]


class RemoteNetworkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        with patch("dashboard.server._make_uploads_dir", return_value=Path(self.temp.name)):
            self.server = DashboardServer()
        self.token = "test-only-token"
        self.server._tokens.add(self.token)
        self.client = TestClient(self.server.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_session_probe_does_not_expose_credentials(self):
        denied = self.client.get("/api/session")
        self.assertEqual(denied.status_code, 401)
        allowed = self.client.get(
            "/api/session", headers={"Authorization": "Bearer " + self.token}
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json(), {"ok": True})
        self.assertNotIn("token", allowed.text.lower())

    def test_websocket_requires_valid_token(self):
        with self.assertRaises(WebSocketDisconnect):
            with self.client.websocket_connect("/ws?token=invalid"):
                pass

    def test_heartbeat_and_reconnect_replay_use_stable_event_id(self):
        asyncio.run(self.server.broadcast({"type": "sys", "text": "Safe test event"}))
        url = "/ws?token=" + self.token
        with self.client.websocket_connect(url) as socket:
            first = socket.receive_json()
            self.assertEqual(first["text"], "Safe test event")
            self.assertIn("event_id", first)
            socket.send_json({"type": "ping"})
            self.assertEqual(socket.receive_json(), {"type": "pong"})
        with self.client.websocket_connect(url) as socket:
            replay = socket.receive_json()
            self.assertEqual(replay["event_id"], first["event_id"])
        self.assertEqual(len(self.server._history), 1)

    def test_command_http_route_still_accepts_existing_plain_payload(self):
        result = self.client.post(
            "/api/command",
            headers={"Authorization": "Bearer " + self.token},
            json={"text": "show status"},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {"ok": True})
        self.assertEqual(self.server._command_queue.get_nowait(), "show status")

    def test_disconnected_live_session_does_not_accept_remote_commands(self):
        self.server.set_live_ready_callback(lambda: False)
        result = self.client.post(
            "/api/command",
            headers={"Authorization": "Bearer " + self.token},
            json={"text": "do not queue"},
        )
        self.assertEqual(result.status_code, 503)
        self.assertFalse(result.json()["ok"])
        self.assertTrue(self.server._command_queue.empty())

        self.server.set_live_ready_callback(lambda: True)
        result = self.client.post(
            "/api/command",
            headers={"Authorization": "Bearer " + self.token},
            json={"text": "now ready"},
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.server._command_queue.get_nowait(), "now ready")

    def test_browser_has_reconnect_and_no_auto_command_resubmission(self):
        page = (ROOT / "dashboard" / "static" / "app.html").read_text(encoding="utf-8")
        login = (ROOT / "dashboard" / "static" / "login.html").read_text(encoding="utf-8")
        self.assertIn("function _connectRemote()", page)
        self.assertIn("function _scheduleReconnect(", page)
        self.assertIn("if (m.event_id)", page)
        self.assertIn("m.type === 'pong'", page)
        self.assertIn("_VOICE_MAX_BUFFERED_BYTES", page)
        self.assertIn("_commandInFlight", page)
        self.assertIn("Command delivery unconfirmed.", page)
        self.assertIn("command was not queued. Your draft is kept.", page)
        self.assertNotIn("Connection lost — refresh to reconnect.", page)
        self.assertIn("r.status === 401 || r.status === 403", login)
        self.assertIn("pairing saved", login)


if __name__ == "__main__":
    unittest.main()
