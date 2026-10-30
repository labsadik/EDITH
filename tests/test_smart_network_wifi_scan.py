"""OS-native Wi-Fi scan parsing and adapter discovery regression tests."""
import unittest
from unittest.mock import patch

from agents import smart_network


WINDOWS_SCAN = """SSID 1 : Home WiFi
    Network type            : Infrastructure
    Authentication         : WPA2-Personal
    Encryption             : CCMP
    BSSID 1                 : aa:bb:cc:dd:ee:01
         Signal             : 88%
         Radio type         : 802.11ax
         Channel            : 44
    BSSID 2                 : aa:bb:cc:dd:ee:02
         Signal             : 74%
         Radio type         : 802.11ac
         Channel            : 36
SSID 2 : Cafe Guest
    Network type            : Infrastructure
    Authentication         : Open
    Encryption             : None
    BSSID 1                 : aa:bb:cc:dd:ee:03
         Signal             : 41%
         Radio type         : 802.11n
         Channel            : 6
"""


class WifiScanParserTests(unittest.TestCase):
    def test_windows_scan_keeps_each_adapter_and_each_bssid(self):
        with patch.object(smart_network.platform, "system", return_value="Windows"), \
             patch.object(smart_network, "_run_fixed", side_effect=[
                 {"available": True, "output": "    Name : Wi-Fi USB\n    Name : Wi-Fi 2"},
                 {"available": True, "output": "The scan request was successfully completed."},
                 {"available": True, "output": WINDOWS_SCAN},
                 {"available": True, "output": "The scan request was successfully completed."},
                 {"available": True, "output": "SSID 1 : Second AP\n  Authentication : WPA2-Personal\n  Encryption : CCMP\n  BSSID 1 : aa:bb:cc:dd:ee:04\n    Signal : 90%\n    Channel : 11"},
             ]), patch.object(smart_network.time, "sleep") as sleep:
            result = smart_network.scan_wifi_networks()
        self.assertTrue(result["ok"])
        self.assertEqual([item["name"] for item in result["adapters"]], ["Wi-Fi USB", "Wi-Fi 2"])
        self.assertEqual(result["count"], 4)
        self.assertEqual(result["networks"][0]["ssid"], "Home WiFi")
        self.assertEqual(result["networks"][0]["signal_percent"], 88)
        self.assertEqual(result["networks"][1]["bssid"], "aa:bb:cc:dd:ee:02")
        self.assertEqual(run.call_count, 5)
        self.assertEqual(sleep.call_count, 2)

    def test_windows_scan_request_failure_is_reported_per_adapter(self):
        with patch.object(smart_network.platform, "system", return_value="Windows"), \
             patch.object(smart_network, "_run_fixed", side_effect=[
                 {"available": True, "output": "Name : USB Wi-Fi"},
                 {"available": False, "reason": "WLAN is disabled"},
             ]):
            result = smart_network.scan_wifi_networks()
        self.assertFalse(result["ok"])
        self.assertEqual(result["adapters"][0]["name"], "USB Wi-Fi")
        self.assertIn("WLAN is disabled", result["adapters"][0]["error"])

    def test_windows_reports_missing_dongle_or_driver_as_actionable(self):
        with patch.object(smart_network.platform, "system", return_value="Windows"), \
             patch.object(smart_network, "_run_fixed", return_value={
                 "available": True, "output": "There is no wireless interface on the system."
             }):
            result = smart_network.scan_wifi_networks()
        self.assertFalse(result["ok"])
        self.assertIn("USB Wi-Fi dongle driver", result["error"])

    def test_windows_reports_unavailable_wlan_service(self):
        with patch.object(smart_network.platform, "system", return_value="Windows"), \
             patch.object(smart_network, "_run_fixed", return_value={
                 "available": False, "reason": "netsh is not installed"
             }):
            result = smart_network.scan_wifi_networks()
        self.assertFalse(result["ok"])
        self.assertIn("WLAN service", result["error"])

    def test_nmcli_parser_preserves_escaped_colon_inside_ssid(self):
        rows = smart_network._parse_nmcli_wifi_networks(
            "*:Cafe\\:Guest:aa:bb:cc:dd:ee:ff:44:5180 MHz:300 Mbit/s:82:WPA2"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ssid"], "Cafe:Guest")
        self.assertEqual(rows[0]["signal_percent"], 82)
        self.assertEqual(rows[0]["channel"], 44)

    def test_linux_scan_uses_networkmanager_rescan_without_connecting(self):
        expected = {
            "available": True,
            "output": "*:Home:aa:bb:cc:dd:ee:ff:6:2437 MHz:72 Mbit/s:91:WPA2",
        }
        with patch.object(smart_network.platform, "system", return_value="Linux"), \
             patch.object(smart_network, "_run_fixed", return_value=expected) as run:
            result = smart_network.scan_wifi_networks()
        self.assertTrue(result["ok"])
        self.assertEqual(result["networks"][0]["ssid"], "Home")
        args = run.call_args.args[0]
        self.assertIn("--rescan", args)
        self.assertIn("yes", args)
        self.assertIn("wifi", args)

    def test_linux_without_networkmanager_does_not_claim_scan_success(self):
        with patch.object(smart_network.platform, "system", return_value="Linux"), \
             patch.object(smart_network, "_run_fixed", return_value={
                 "available": False, "reason": "nmcli is not installed"
             }):
            result = smart_network.scan_wifi_networks()
        self.assertFalse(result["ok"])
        self.assertIn("NetworkManager nmcli is unavailable", result["error"])

    def test_macos_parser_extracts_network_identity_and_signal(self):
        row = smart_network._parse_macos_wifi_networks(
            "Coffee Shop  aa:bb:cc:dd:ee:ff  -51  149  Y  US  WPA2(PSK/AES/AES)"
            , "en0"
        )
        self.assertEqual(len(row), 1)
        self.assertEqual(row[0]["ssid"], "Coffee Shop")
        self.assertEqual(row[0]["rssi_dbm"], -51)

    def test_smart_network_wifi_scan_action_uses_native_scanner(self):
        expected = {"ok": True, "platform": "Windows", "networks": [], "count": 0}
        with patch.object(smart_network, "scan_wifi_networks", return_value=expected) as scan:
            result = smart_network.run_smart_network("wifi_scan")
        self.assertEqual(__import__("json").loads(result), expected)
        scan.assert_called_once_with()

    def test_unsupported_platform_is_explicit(self):
        with patch.object(smart_network.platform, "system", return_value="FreeBSD"):
            result = smart_network.scan_wifi_networks()
        self.assertFalse(result["ok"])
        self.assertIn("not implemented", result["error"])


if __name__ == "__main__":
    unittest.main()
