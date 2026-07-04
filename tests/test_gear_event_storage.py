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
    guard_gear_event_write,
    inv_deltas_to_gear_events,
    list_available_event_dates,
    load_gear_events,
    manifest_median_day_total,
    reconstruct_char_data_at_date,
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

    def test_reconstruct_char_data_at_date(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        ge = os.path.join(base, "gear_events")
        os.makedirs(ge)
        baseline = {
            "baseline_date": "2026-02-09",
            "characters": {
                "Alice": {
                    "level": 60,
                    "aa_unspent": 5,
                    "aa_spent": 95,
                    "hp_max_total": 1000,
                    "class": "Wizard",
                }
            },
        }
        with gzip.open(os.path.join(ge, "char_2026-05.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(
                [
                    {"d": "2026-05-10", "c": "Alice", "f": "aa", "n": 5, "aa": 105},
                    {"d": "2026-05-11", "c": "Alice", "f": "lvl", "n": 1, "lv": 61},
                ],
                f,
            )
        with open(os.path.join(ge, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "days": {"2026-05-10": {"gear": 0, "char": 1}}}, f)
        got = reconstruct_char_data_at_date(baseline, base, "2026-05-11")
        self.assertEqual(got["Alice"]["level"], 61)
        self.assertEqual(
            int(got["Alice"]["aa_unspent"]) + int(got["Alice"]["aa_spent"]),
            105,
        )

    def test_load_gear_events_spans_months_with_start_date(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        ge = os.path.join(base, "gear_events")
        os.makedirs(ge)
        with gzip.open(os.path.join(ge, "gear_2026-06.json.gz"), "wt", encoding="utf-8") as f:
            json.dump([{"d": "2026-06-30", "c": "Alice", "i": "1", "s": 1, "n": 1}], f)
        with gzip.open(os.path.join(ge, "gear_2026-07.json.gz"), "wt", encoding="utf-8") as f:
            json.dump([{"d": "2026-07-03", "c": "Bob", "i": "2", "s": 1, "n": 1}], f)
        end_only = load_gear_events(base, end_date="2026-07-03")
        era = load_gear_events(
            base, start_date="2026-02-09", end_date="2026-07-03"
        )
        self.assertEqual(len(end_only), 1)
        self.assertEqual(len(era), 2)


class TestGearEventInflationGuard(unittest.TestCase):
    def test_manifest_median_ignores_target_day(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots", "gear_events")
        os.makedirs(base)
        days = {}
        for i in range(1, 15):
            d = f"2026-06-{i:02d}"
            days[d] = {"gear": 900, "char": 100}
        days["2026-06-15"] = {"gear": 50000, "char": 8000}
        with open(os.path.join(base, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "days": days}, f)
        med = manifest_median_day_total(os.path.join(td, "delta_snapshots"), "2026-06-15")
        self.assertAlmostEqual(med, 1000.0)

    def test_guard_rejects_inflated_write(self):
        td = tempfile.mkdtemp()
        snap = os.path.join(td, "delta_snapshots")
        ge = os.path.join(snap, "gear_events")
        os.makedirs(ge)
        days = {f"2026-06-{i:02d}": {"gear": 900, "char": 100} for i in range(1, 15)}
        with open(os.path.join(ge, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "days": days}, f)
        huge_inv = {
            f"Char{n}": {"added": {str(i): 1 for i in range(200)}, "removed": {}, "item_names": {}}
            for n in range(300)
        }
        gear_n, char_n = append_day_events_from_deltas(
            {}, huge_inv, "2026-06-15", snap, "2026-02-09"
        )
        self.assertEqual((gear_n, char_n), (0, 0))

    def test_guard_keeps_existing_sane_day(self):
        td = tempfile.mkdtemp()
        snap = os.path.join(td, "delta_snapshots")
        ge = os.path.join(snap, "gear_events")
        os.makedirs(ge)
        days = {f"2026-06-{i:02d}": {"gear": 900, "char": 100} for i in range(1, 15)}
        days["2026-06-15"] = {"gear": 920, "char": 130}
        with open(os.path.join(ge, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"version": 1, "days": days}, f)
        with gzip.open(os.path.join(ge, "gear_2026-06.json.gz"), "wt", encoding="utf-8") as f:
            json.dump([{"d": "2026-06-15", "c": "A", "i": "1", "s": 1, "n": 1, "v": 0}], f)
        huge_inv = {
            f"Char{n}": {"added": {str(i): 1 for i in range(200)}, "removed": {}, "item_names": {}}
            for n in range(300)
        }
        gear_n, char_n = append_day_events_from_deltas(
            {}, huge_inv, "2026-06-15", snap, "2026-02-09"
        )
        self.assertEqual((gear_n, char_n), (0, 0))
        with gzip.open(os.path.join(ge, "gear_2026-06.json.gz"), "rt", encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 1)


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
