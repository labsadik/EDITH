"""Smart Network UI exposes verified Home Assistant pairing."""
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HomeAssistantUiContractTests(unittest.TestCase):
    def test_smart_network_has_pair_and_update_controls(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        self.assertIn('PAIR HA', source)
        self.assertIn('UPDATE HA', source)
        self.assertIn('test_home_assistant_connection(url, token, timeout=5.0)', source)
        self.assertIn('configure_home_assistant(url, token)', source)

    def test_pairing_runs_off_ui_thread_and_verifies_before_saving(self):
        source = (ROOT / "ui.py").read_text(encoding="utf-8")
        verify = source.index('test_home_assistant_connection(url, token, timeout=5.0)')
        save = source.index('configure_home_assistant(url, token)', verify)
        worker = source.rfind('def pair_worker()', 0, verify)
        self.assertGreater(worker, -1)
        self.assertLess(verify, save)
        self.assertIn('threading.Thread(', source[worker:save + 200])


if __name__ == "__main__":
    unittest.main()
