"""Security and adapter tests for the locally paired MQTT bridge."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agents import mqtt_bridge


class MQTTBridgeTests(unittest.TestCase):
    def test_remote_broker_requires_tls_but_private_lan_is_allowed(self):
        self.assertEqual(mqtt_bridge._broker_parts("mqtt://192.168.1.8:1883"),
                         ("192.168.1.8", 1883, False))
        self.assertEqual(mqtt_bridge._broker_parts("mqtts://broker.example"),
                         ("broker.example", 8883, True))
        with self.assertRaises(ValueError):
            mqtt_bridge._broker_parts("mqtt://broker.example:1883")

    def test_topic_allowlist_rejects_wildcards_and_system_topics(self):
        with self.assertRaises(ValueError):
            mqtt_bridge._normalise_topics(["home/+/lamp"])
        with self.assertRaises(ValueError):
            mqtt_bridge._normalise_topics(["$SYS/broker/version"])
        with self.assertRaises(PermissionError):
            mqtt_bridge._require_topic("home/office/lamp", ["home/living/lamp"])

    def test_pairing_saves_password_via_secret_helper_and_only_exact_topics(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            status = SimpleNamespace(storage="keyring")
            with patch("core.secrets.save_config_secret", return_value=status) as save:
                result = mqtt_bridge.configure_mqtt(
                    "mqtts://broker.example:8883", ["home/living/light"],
                    "edith", "do-not-log-this", config_path=path,
                )
            save.assert_called_once_with("mqtt_password", "do-not-log-this", path)
            saved = mqtt_bridge._read_config(path)
            self.assertNotIn("mqtt_password", saved)
            self.assertEqual(saved["mqtt_topics"], ["home/living/light"])
            self.assertEqual(result["credential_storage"], "keyring")

    def test_publish_is_qos_one_and_never_retained(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "api_keys.json"
            path.write_text('{"mqtt_broker_url":"mqtts://broker.example","mqtt_topics":["home/living/light"]}', encoding="utf-8")
            fake_publish = Mock()
            fake_api = (Mock(), SimpleNamespace(single=fake_publish), Mock())
            with patch.object(mqtt_bridge, "_pairing", return_value=(
                {"mqtt_username": ""}, "broker.example", 8883, True, ""
            )), patch.object(mqtt_bridge, "_mqtt_api", return_value=fake_api):
                result = mqtt_bridge.run_mqtt_action(
                    "mqtt_publish", topic="home/living/light", payload="ON", config_path=path
                )
            self.assertTrue(result["ok"])
            self.assertEqual(fake_publish.call_args.kwargs["qos"], 1)
            self.assertFalse(fake_publish.call_args.kwargs["retain"])

    def test_publish_cannot_target_unpaired_topic_or_oversized_payload(self):
        with patch.object(mqtt_bridge, "_pairing", return_value=(
            {"mqtt_topics": ["home/living/light"]}, "broker.example", 8883, True, ""
        )), patch.object(mqtt_bridge, "_mqtt_api") as api:
            with self.assertRaises(PermissionError):
                mqtt_bridge.run_mqtt_action("mqtt_publish", topic="home/garage/door", payload="OPEN")
            with self.assertRaises(ValueError):
                mqtt_bridge.run_mqtt_action("mqtt_publish", topic="home/living/light", payload="x" * 5000)
            api.assert_not_called()

    def test_read_returns_one_message_from_allowlisted_topic(self):
        message = SimpleNamespace(payload=b"temperature=21", qos=1)
        fake_api = (Mock(), Mock(), SimpleNamespace(simple=Mock(return_value=message)))
        with patch.object(mqtt_bridge, "_pairing", return_value=(
            {"mqtt_topics": ["home/living/sensor"]}, "broker.example", 8883, True, ""
        )), patch.object(mqtt_bridge, "_mqtt_api", return_value=fake_api):
            result = mqtt_bridge.run_mqtt_action("mqtt_read", topic="home/living/sensor")
        self.assertEqual(result["payload"], "temperature=21")
        self.assertEqual(result["qos"], 1)


if __name__ == "__main__":
    unittest.main()
