"""Tests for per-character timeline reconstruction (mirrors char.html client logic)."""

import os
import sys
import tempfile
import unittest

_MAGelo_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGelo_ROOT not in sys.path:
    sys.path.insert(0, _MAGelo_ROOT)

from generate_spell_page import (  # noqa: E402
    char_timeline_link,
    generate_char_timeline,
)
from gear_event_storage import (  # noqa: E402
    baseline_only_item_ids,
    baseline_only_tracked_item_ids,
    build_aa_timeline,
    build_gear_event_log_rows,
    build_item_name_map_for_char,
    build_tracked_gear_event_log_rows,
    filter_events_for_char,
    group_tracked_rows_by_date,
    group_tracked_rows_by_zone,
    load_item_id_to_name_map,
    reconstruct_holdings_for_char,
)


class TestCharTimelineReconstruction(unittest.TestCase):
    BASELINE = {
        "baseline_date": "2026-02-09",
        "characters": {
            "Alice": {
                "level": 65,
                "aa_unspent": 5,
                "aa_spent": 195,
                "class": "Wizard",
                "guild": "TestGuild",
            }
        },
        "inventories": {
            "Alice": [
                {"slot_id": 1, "item_id": "100", "item_name": "Old Sword"},
                {"slot_id": 2, "item_id": "200", "item_name": "Old Shield"},
            ]
        },
    }

    CHAR_EVENTS = [
        {"d": "2026-05-10", "c": "Alice", "f": "aa", "n": 5, "aa": 205},
        {"d": "2026-05-14", "c": "Alice", "f": "aa", "n": 3, "aa": 208},
    ]

    GEAR_EVENTS = [
        {"d": "2026-05-10", "c": "Alice", "i": "999", "s": 1, "n": 1, "v": 0},
        {"d": "2026-05-12", "c": "Alice", "i": "100", "s": -1, "n": 1, "v": 0},
        {"d": "2026-05-14", "c": "Alice", "i": "100", "s": 1, "n": 1, "v": 0},
    ]

    def test_filter_events_for_char(self):
        events = self.CHAR_EVENTS + [{"d": "2026-05-10", "c": "Bob", "f": "aa", "n": 1}]
        filtered = filter_events_for_char(events, "Alice")
        self.assertEqual(len(filtered), 2)
        self.assertTrue(all(e["c"] == "Alice" for e in filtered))

    def test_build_aa_timeline(self):
        rows = build_aa_timeline(self.BASELINE, self.CHAR_EVENTS, "Alice")
        self.assertEqual(rows[0]["date"], "2026-02-09")
        self.assertEqual(rows[0]["total"], 200)
        self.assertEqual(rows[1]["delta"], 5)
        self.assertEqual(rows[1]["total"], 205)
        self.assertEqual(rows[2]["delta"], 3)
        self.assertEqual(rows[2]["total"], 208)

    def test_reconstruct_holdings_for_char(self):
        holdings = reconstruct_holdings_for_char(self.BASELINE, self.GEAR_EVENTS, "Alice")
        self.assertEqual(holdings["100"], 1)
        self.assertEqual(holdings["200"], 1)
        self.assertEqual(holdings["999"], 1)

    def test_baseline_only_item_ids(self):
        holdings = reconstruct_holdings_for_char(self.BASELINE, self.GEAR_EVENTS, "Alice")
        only = baseline_only_item_ids(holdings, self.GEAR_EVENTS, "Alice")
        self.assertEqual(only, {"200": 1})

    def test_build_gear_event_log_rows(self):
        name_map = build_item_name_map_for_char(self.BASELINE, "Alice", {"999": "New Item"})
        rows = build_gear_event_log_rows(self.GEAR_EVENTS, "Alice", name_map)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["item_name"], "New Item")
        self.assertEqual(rows[0]["sign"], 1)

    def test_build_item_name_map_from_global_file(self):
        names = load_item_id_to_name_map(_MAGelo_ROOT)
        if not names:
            self.skipTest("item_id_to_name.json not present")
        name_map = build_item_name_map_for_char({"inventories": {}}, "Nobody")
        self.assertIn("10037", name_map)

    def test_char_timeline_link(self):
        link = char_timeline_link("Alice Test")
        self.assertIn("char.html?c=", link)
        self.assertIn("Δ", link)
        self.assertIn("Alice%20Test", link)

    def test_generate_char_timeline_writes_html(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(os.path.join(base, "gear_events"), exist_ok=True)
        with open(os.path.join(base, "gear_events", "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"version":1,"days":{},"eras":[]}')
        path = generate_char_timeline(td)
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("buildAaTimeline", html)
        self.assertIn("GEAR_EVENT_SHARD_MONTHS", html)
        self.assertIn("char.html?c=", html)
        self.assertIn('id="tracked-items"', html)
        self.assertIn("buildTrackedGearEventLog", html)
        self.assertIn("tracked-tab", html)
        self.assertIn("TRACKED_ITEM_IDS", html)
        self.assertIn("tracked-source-label", html)
        self.assertIn("fetchGzJsonCached", html)
        self.assertIn("GEAR_EVENT_CACHE_TTL_MS", html)
        self.assertIn("caches.open", html)
        self.assertIn("your browser caches it for 24 hours", html)


class TestTrackedGearTimeline(unittest.TestCase):
    BASELINE = {
        "baseline_date": "2026-02-09",
        "characters": {"Alice": {"level": 65}},
        "inventories": {
            "Alice": [
                {"slot_id": 1, "item_id": "100", "item_name": "Raid Sword"},
                {"slot_id": 2, "item_id": "500", "item_name": "Random Item"},
            ]
        },
    }
    TRACKED = {"100", "200", "999"}
    SOURCE = {"100": "Boss (Plane of Time)", "200": "elemental armor", "999": "praesterium"}
    ZONE = {"100": "Plane of Time", "200": "Elemental", "999": "Praesterium"}
    MOB = {"100": "Boss"}

    def test_tracked_filter_excludes_non_tracked(self):
        events = [
            {"d": "2026-05-10", "c": "Alice", "i": "999", "s": 1, "n": 1, "v": 0},
            {"d": "2026-05-11", "c": "Alice", "i": "500", "s": 1, "n": 1, "v": 0},
        ]
        rows = build_tracked_gear_event_log_rows(
            events, "Alice", self.TRACKED, {"999": "Tracked Item"}, source_label=self.SOURCE
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_id"], "999")

    def test_lore_reacquire_suppressed(self):
        """Spurious + when item already held from baseline is not listed."""
        events = [
            {"d": "2026-05-14", "c": "Alice", "i": "100", "s": 1, "n": 1, "v": 0},
        ]
        rows = build_tracked_gear_event_log_rows(
            events,
            "Alice",
            self.TRACKED,
            {"100": "Raid Sword"},
            unique_tracked_ids={"100"},
            baseline=self.BASELINE,
            source_label=self.SOURCE,
        )
        self.assertEqual(rows, [])

    def test_group_by_date(self):
        rows = [
            {"date": "2026-05-10", "sign": 1, "count": 1, "item_id": "999", "item_name": "X", "source": ""},
            {"date": "2026-05-10", "sign": -1, "count": 1, "item_id": "200", "item_name": "Y", "source": ""},
        ]
        grouped = group_tracked_rows_by_date(rows)
        self.assertEqual(len(grouped["2026-05-10"]["acquired"]), 1)
        self.assertEqual(len(grouped["2026-05-10"]["lost"]), 1)

    def test_group_by_zone(self):
        rows = [
            {
                "date": "2026-05-10",
                "sign": 1,
                "count": 1,
                "item_id": "100",
                "item_name": "Raid Sword",
                "source": "Boss (Plane of Time)",
            },
            {
                "date": "2026-05-12",
                "sign": 1,
                "count": 1,
                "item_id": "200",
                "item_name": "Elem Helm",
                "source": "elemental armor",
            },
        ]
        grouped = group_tracked_rows_by_zone(rows, self.ZONE, self.MOB)
        self.assertIn("Plane of Time", grouped)
        self.assertIn("Boss", grouped["Plane of Time"])
        self.assertEqual(grouped["Plane of Time"]["Boss"][0]["date"], "2026-05-10")
        self.assertIn("Elemental", grouped)

    def test_baseline_only_tracked(self):
        holdings = reconstruct_holdings_for_char(self.BASELINE, [], "Alice")
        only = baseline_only_tracked_item_ids(holdings, [], "Alice", self.TRACKED)
        self.assertEqual(only, {"100": 1})


if __name__ == "__main__":
    unittest.main()
