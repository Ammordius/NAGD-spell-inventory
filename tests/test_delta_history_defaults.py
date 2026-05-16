"""Default date range for delta-history.html (avoid sparse multi-month gaps)."""

import os
import sys
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from generate_spell_page import default_delta_history_range_endpoints  # noqa: E402


class TestDefaultDeltaHistoryRange(unittest.TestCase):
    def test_consecutive_latest_pair(self):
        d = ["2026-05-13", "2026-05-14", "2026-05-15"]
        self.assertEqual(
            default_delta_history_range_endpoints(d, max_gap_days=14),
            ("2026-05-14", "2026-05-15"),
        )

    def test_sparse_repo_collapses_to_single_day(self):
        """Only Feb and May files: second-newest is far from end; do not default that range."""
        d = ["2026-02-07", "2026-05-15"]
        self.assertEqual(
            default_delta_history_range_endpoints(d, max_gap_days=14),
            ("2026-05-15", "2026-05-15"),
        )

    def test_picks_latest_start_within_gap(self):
        d = ["2026-05-01", "2026-05-08", "2026-05-15"]
        self.assertEqual(
            default_delta_history_range_endpoints(d, max_gap_days=14),
            ("2026-05-08", "2026-05-15"),
        )

    def test_single_date(self):
        self.assertEqual(
            default_delta_history_range_endpoints(["2026-05-15"], max_gap_days=14),
            ("2026-05-15", "2026-05-15"),
        )

    def test_empty(self):
        self.assertEqual(default_delta_history_range_endpoints([], max_gap_days=14), ("", ""))


if __name__ == "__main__":
    unittest.main()
