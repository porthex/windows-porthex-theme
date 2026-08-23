import importlib.util
import unittest
from datetime import date
from pathlib import Path

MODULE = Path(__file__).parents[1] / "@Resources" / "ServerMonitor.py"
spec = importlib.util.spec_from_file_location("server_monitor", MODULE)
server_monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server_monitor)


class RenewalStatusTests(unittest.TestCase):
    def test_missing_date_requests_configuration(self):
        self.assertEqual(
            server_monitor.renewal_status("", date(2026, 8, 16)),
            {
                "AvoroState": "SET RENEWAL DATE",
                "AvoroColor": "218,168,92,255",
                "AvoroRenewal": "RENEW --",
            },
        )

    def test_date_shows_days_left_and_warning_color(self):
        self.assertEqual(
            server_monitor.renewal_status("2026-08-23", date(2026, 8, 16)),
            {
                "AvoroState": "7 DAYS LEFT",
                "AvoroColor": "218,168,92,255",
                "AvoroRenewal": "RENEW AUG 23",
            },
        )

    def test_expired_date_is_red(self):
        self.assertEqual(
            server_monitor.renewal_status("2026-08-14", date(2026, 8, 16)),
            {
                "AvoroState": "EXPIRED 2D",
                "AvoroColor": "184,104,88,255",
                "AvoroRenewal": "RENEW AUG 14",
            },
        )


if __name__ == "__main__":
    unittest.main()
