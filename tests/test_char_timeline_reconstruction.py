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
    build_aa_timeline,
    build_gear_event_log_rows,
    build_item_name_map_for_char,
    filter_events_for_char,
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


if __name__ == "__main__":
    unittest.main()
