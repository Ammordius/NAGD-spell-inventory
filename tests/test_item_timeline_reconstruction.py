"""Tests for per-item ownership timeline reconstruction (mirrors item.html client logic)."""

import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from generate_spell_page import (  # noqa: E402
    generate_item_timeline,
    item_timeline_link,
)
from gear_event_storage import (  # noqa: E402
    baseline_only_holders_for_item,
    build_item_event_log_rows,
    filter_events_for_item,
    reconstruct_holders_for_item,
    resolve_item_id,
)


class TestItemTimelineReconstruction(unittest.TestCase):
    ID_TO_NAME = {
        "100": "Old Sword",
        "200": "Old Shield",
        "999": "New Item",
    }
    NAME_TO_ID = {
        "old sword": "100",
        "old shield": "200",
        "new item": "999",
    }
    BASELINE_INV = {
        "Alice": [
            {"slot_id": 1, "item_id": "100", "item_name": "Old Sword"},
            {"slot_id": 2, "item_id": "200", "item_name": "Old Shield"},
        ],
        "Bob": [
            {"slot_id": 1, "item_id": "100", "item_name": "Old Sword"},
        ],
    }
    GEAR_EVENTS = [
        {"d": "2026-05-10", "c": "Alice", "i": "999", "s": 1, "n": 1, "v": 0},
        {"d": "2026-05-12", "c": "Alice", "i": "100", "s": -1, "n": 1, "v": 0},
        {"d": "2026-05-14", "c": "Carol", "i": "100", "s": 1, "n": 1, "v": 0},
        {"d": "2026-05-15", "c": "Bob", "i": "100", "s": -1, "n": 1, "v": 1},
        {"d": "2026-05-16", "c": "Bob", "i": "100", "s": 1, "n": 1, "v": 1},
        {"d": "2026-05-17", "c": "Dave", "i": "200", "s": 1, "n": 2, "v": 0},
    ]

    def test_filter_events_for_item(self):
        filtered = filter_events_for_item(self.GEAR_EVENTS, "100")
        self.assertEqual(len(filtered), 4)
        self.assertTrue(all(str(e["i"]) == "100" for e in filtered))

    def test_resolve_item_id_by_id(self):
        self.assertEqual(resolve_item_id("100", self.ID_TO_NAME), "100")
        self.assertEqual(resolve_item_id("0100", self.ID_TO_NAME), "100")

    def test_resolve_item_id_case_insensitive_name(self):
        self.assertEqual(
            resolve_item_id("OLD SWORD", self.ID_TO_NAME, self.NAME_TO_ID),
            "100",
        )
        self.assertEqual(
            resolve_item_id("new item", self.ID_TO_NAME),
            "999",
        )
        self.assertIsNone(resolve_item_id("No Such Thing", self.ID_TO_NAME))

    def test_reconstruct_holders_for_item(self):
        events = filter_events_for_item(self.GEAR_EVENTS, "100")
        holders = reconstruct_holders_for_item(self.BASELINE_INV, events, "100")
        # Alice lost her baseline sword; Bob lost then regained (visibility); Carol gained
        self.assertNotIn("Alice", holders)
        self.assertEqual(holders.get("Bob"), 1)
        self.assertEqual(holders.get("Carol"), 1)

    def test_reconstruct_holders_baseline_only_shield(self):
        events = filter_events_for_item(self.GEAR_EVENTS, "200")
        holders = reconstruct_holders_for_item(self.BASELINE_INV, events, "200")
        self.assertEqual(holders.get("Alice"), 1)
        self.assertEqual(holders.get("Dave"), 2)

    def test_baseline_only_holders_for_item(self):
        events = filter_events_for_item(self.GEAR_EVENTS, "200")
        holders = reconstruct_holders_for_item(self.BASELINE_INV, events, "200")
        only = baseline_only_holders_for_item(holders, events, "200")
        self.assertEqual(only, {"Alice": 1})

    def test_build_item_event_log_rows(self):
        rows = build_item_event_log_rows(self.GEAR_EVENTS, "100")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["date"], "2026-05-12")
        self.assertEqual(rows[0]["char"], "Alice")
        self.assertEqual(rows[0]["sign"], -1)
        self.assertTrue(rows[2]["visibility"])

    def test_log_row_ordering(self):
        rows = build_item_event_log_rows(self.GEAR_EVENTS, "100")
        dates = [r["date"] for r in rows]
        self.assertEqual(dates, sorted(dates))

    def test_item_timeline_link(self):
        link = item_timeline_link("100", "Old Sword", color="#2e7d32")
        self.assertIn("item.html?i=100", link)
        self.assertIn("Old Sword", link)
        self.assertIn("Allaclone", link)
        self.assertIn("#2e7d32", link)

    def test_generate_item_timeline_writes_html(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(os.path.join(base, "gear_events"), exist_ok=True)
        with open(os.path.join(base, "gear_events", "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"version":1,"days":{},"eras":[]}')
        path = generate_item_timeline(td)
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("'?i='", html)
        self.assertIn("navigateToItem", html)
        self.assertIn("resolveItemId", html)
        self.assertIn("reconstructHoldersForItem", html)
        self.assertIn("filterEventsForItem", html)
        self.assertIn("buildItemEventLog", html)
        self.assertIn("fetchGzJsonCached", html)
        self.assertIn("item-search", html)
        self.assertIn("Current Holders", html)
        self.assertIn("Ownership Log", html)
        self.assertIn("sortable", html)
        self.assertIn("renderOwnershipLogTable", html)
        self.assertIn("ownSort", html)
        self.assertIn("dir: 'desc'", html)


if __name__ == "__main__":
    unittest.main()
