"""Pair EDITH with a user-owned Home Assistant instance."""
from __future__ import annotations

import getpass

from agents.smart_network import pair_home_assistant


def main() -> int:
    url = input("Home Assistant URL (for example http://homeassistant.local:8123): ").strip()
    token = getpass.getpass("Long-lived access token (hidden): ").strip()
    try:
        result = pair_home_assistant(url, token, timeout=5.0)
    except Exception as exc:
        print(f"Pairing failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"Paired: {result['url']}")
    print(f"Token storage: {result['token_storage']}")
    warning = getattr(result, "warning", None)
    if warning:
        print(f"Warning: {warning}")
    if result.get("token_storage") == "legacy":
        print("Warning: OS keychain unavailable. Secure config/api_keys.json and migrate the token to an OS keychain.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
