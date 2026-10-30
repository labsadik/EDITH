"""Pair a trusted MQTT broker and an exact topic allowlist for EDITH."""
from __future__ import annotations

import argparse
from getpass import getpass

from agents.mqtt_bridge import configure_mqtt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--broker", required=True, help="mqtts://broker.example:8883 (or mqtt:// on a private LAN)")
    parser.add_argument("--topic", action="append", required=True, help="Exact topic to allow; repeat for more topics")
    parser.add_argument("--username", default="", help="Optional MQTT username")
    args = parser.parse_args()
    password = getpass("MQTT password (input hidden): ") if args.username else ""
    result = configure_mqtt(args.broker, args.topic, args.username, password)
    print(f"MQTT paired: {result['host']}:{result['port']} TLS={result['tls']}")
    print("Allowed exact topics: " + ", ".join(result["topics"]))
    print("Password storage: " + result["credential_storage"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
