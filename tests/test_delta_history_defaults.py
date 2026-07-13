"""Default date range for delta-history.html (avoid sparse multi-month gaps)."""

import gzip
import json
import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from gear_event_storage import list_available_event_dates  # noqa: E402
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

    def test_skips_empty_dates_as_range_end(self):
        """Zero-event days (e.g. Jul 6) must not become DEFAULT_RANGE_END."""
        d = ["2026-07-05", "2026-07-06", "2026-07-07"]
        self.assertEqual(
            default_delta_history_range_endpoints(
                d, max_gap_days=14, empty_dates={"2026-07-06"}
            ),
            ("2026-07-05", "2026-07-07"),
        )

    def test_list_available_skips_zero_event_manifest_days(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        ge = os.path.join(base, "gear_events")
        os.makedirs(ge)
        manifest = {
            "version": 1,
            "days": {
                "2026-07-05": {"gear": 10, "char": 2},
                "2026-07-06": {"gear": 0, "char": 0},
                "2026-07-07": {"gear": 8, "char": 1},
            },
            "eras": [],
        }
        with open(os.path.join(ge, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        with gzip.open(os.path.join(ge, "gear_2026-07.json.gz"), "wt", encoding="utf-8") as f:
            json.dump([], f)
        dates = list_available_event_dates(base)
        self.assertEqual(dates, ["2026-07-05", "2026-07-07"])
        self.assertEqual(
            default_delta_history_range_endpoints(dates, max_gap_days=14),
            ("2026-07-05", "2026-07-07"),
        )


if __name__ == "__main__":
    unittest.main()
