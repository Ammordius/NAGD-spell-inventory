"""Tests for gear_event_storage append/load and parity with compare_delta_to_delta."""

import gzip
import json
import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from delta_storage import compare_delta_to_delta  # noqa: E402
from gear_event_storage import (  # noqa: E402
    append_day_events_from_deltas,
    char_deltas_to_stat_events,
    char_events_to_char_deltas,
    detect_oscillations,
    events_to_delta_shape,
    gear_events_to_inv_deltas,
    get_day_delta_from_events,
    get_range_delta_from_events,
    inv_deltas_to_gear_events,
    list_available_event_dates,
    load_gear_events,
)


class TestGearEventRoundTrip(unittest.TestCase):
    def test_inv_deltas_round_trip(self):
        inv = {
            "Alice": {
                "added": {"100": 2, "200": 1},
                "removed": {"50": 1},
                "item_names": {"100": "Sword", "200": "Shield", "50": "Old"},
                "is_visibility_change": False,
            }
        }
        events = inv_deltas_to_gear_events(inv, "2026-05-14", "2026-02-09")
        self.assertEqual(len(events), 3)
        back = gear_events_to_inv_deltas(events, {"100": "Sword", "200": "Shield", "50": "Old"})
        self.assertEqual(back["Alice"]["added"]["100"], 2)
        self.assertEqual(back["Alice"]["removed"]["50"], 1)

    def test_append_and_load_single_day(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(base)
        char_deltas = {
            "Bob": {
                "name": "Bob",
                "level_change": 1,
                "aa_total_change": 5,
                "hp_change": 0,
                "class": "Warrior",
            }
        }
        inv_deltas = {
            "Bob": {
                "added": {"999": 1},
                "removed": {},
                "item_names": {"999": "Test Item"},
            }
        }
        append_day_events_from_deltas(char_deltas, inv_deltas, "2026-05-10", base, "2026-02-09")
        self.assertIn("2026-05-10", list_available_event_dates(base))
        day = get_day_delta_from_events("2026-05-10", base)
        self.assertIn("Bob", day["inv_deltas"])
        self.assertIn("Bob", day["char_deltas"])
        self.assertEqual(day["char_deltas"]["Bob"]["level_change"], 1)

    def test_append_emits_snapshot_fields(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(base)
        char_deltas = {
            "Bob": {
                "name": "Bob",
                "level_change": 0,
                "aa_total_change": 5,
                "hp_change": 100,
                "current_level": 65,
                "previous_level": 65,
                "current_aa_total": 205,
                "previous_aa_total": 200,
                "current_hp": 5100,
                "previous_hp": 5000,
                "class": "Warrior",
            }
        }
        append_day_events_from_deltas(char_deltas, {}, "2026-05-10", base, "2026-02-09")
        events = char_deltas_to_stat_events(char_deltas, "2026-05-10", "2026-02-09")
        aa_ev = next(e for e in events if e["f"] == "aa")
        self.assertEqual(aa_ev.get("lv"), 65)
        self.assertEqual(aa_ev.get("aa"), 205)
        folded = get_day_delta_from_events("2026-05-10", base)
        self.assertEqual(folded["char_deltas"]["Bob"]["current_aa_total"], 205)

    def test_range_exclusive_start(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(base)
        for d, iid in [("2026-05-10", "1"), ("2026-05-11", "2"), ("2026-05-12", "3")]:
            append_day_events_from_deltas(
                {},
                {"X": {"added": {iid: 1}, "removed": {}, "item_names": {}}},
                d,
                base,
            )
        r = get_range_delta_from_events("2026-05-10", "2026-05-12", base)
        added = r["inv_deltas"]["X"]["added"]
        self.assertNotIn("1", added)
        self.assertIn("2", added)
        self.assertIn("3", added)

    def test_detect_oscillations(self):
        hist = [
            {"d": "2026-05-01", "c": "A", "i": "1", "s": 1},
            {"d": "2026-05-02", "c": "A", "i": "1", "s": -1},
            {"d": "2026-05-03", "c": "A", "i": "1", "s": 1},
        ]
        flags = detect_oscillations(hist, window_days=7)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["pattern"], [1, -1, 1])


class TestGearEventParityWithRepo(unittest.TestCase):
    """Parity against committed delta_snapshots when present."""

    @classmethod
    def setUpClass(cls):
        cls.snap = os.path.join(_MAGELO_ROOT, "delta_snapshots")
        cls.has_dailies = os.path.isdir(cls.snap) and sum(
            1
            for f in os.listdir(cls.snap)
            if f.startswith("delta_daily_") and f.endswith(".json.gz")
        ) >= 2

    @unittest.skipUnless(
        os.path.isdir(os.path.join(_MAGELO_ROOT, "delta_snapshots")),
        "delta_snapshots not present",
    )
    def test_backfill_parity_sample(self):
        if not self.has_dailies:
            self.skipTest("delta_daily_*.json.gz not in repo (archived offline; gear_events is canonical)")
        from scripts.backfill_gear_events_from_dailies import backfill, parity_check

        td = tempfile.mkdtemp()
        import shutil

        snap = os.path.join(td, "delta_snapshots")
        shutil.copytree(self.snap, snap, dirs_exist_ok=True)
        backfill(os.path.join(snap), clear=True)
        issues = parity_check(os.path.join(snap), sample_count=8)
        self.assertEqual(issues, [], issues)


if __name__ == "__main__":
    unittest.main()
