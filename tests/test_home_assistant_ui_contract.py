"""Smart Network UI exposes verified Home Assistant pairing."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeAssistantUiContractTests(unittest.TestCase):
    def test_smart_network_has_pair_and_update_controls(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('PAIR HA', source)
        self.assertIn('UPDATE HA', source)
        self.assertIn('SCAN WI-FI', source)
        self.assertIn('scan_wifi_networks()', source)
        self.assertIn('pair_home_assistant(url, token, timeout=5.0)', source)

    def test_pairing_runs_off_ui_thread_and_verifies_before_saving(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        verify = source.index('pair_home_assistant(url, token, timeout=5.0)')
        worker = source.rfind('def pair_worker()', 0, verify)
        worker_end = source.index('    def _on_home_assistant_pair_finished', worker)
        self.assertGreater(worker, -1)
        self.assertIn('threading.Thread(', source[worker:worker_end])
        self.assertIn('QLineEdit.EchoMode.Password', source[worker - 800:worker])


if __name__ == "__main__":
    unittest.main()
