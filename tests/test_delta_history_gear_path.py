"""Tests for delta-history gear-events path helpers (Python side)."""

import json
import os
import sys
import tempfile
import unittest

_MAGelo_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGelo_ROOT not in sys.path:
    sys.path.insert(0, _MAGelo_ROOT)

from generate_spell_page import (  # noqa: E402
    build_tracked_item_id_to_name,
    _count_meaningful_char_deltas,
    _warn_if_event_dump_divergence,
)
from gear_event_storage import (  # noqa: E402
    append_day_events_from_deltas,
    char_events_to_char_deltas,
    populate_item_names_for_inv_deltas,
)


class TestBuildTrackedItemIdToName(unittest.TestCase):
    def test_praesterium_names_from_loot_json(self):
        td = tempfile.mkdtemp()
        pr_path = os.path.join(td, "praesterium_loot.json")
        with open(pr_path, "w", encoding="utf-8") as f:
            json.dump(
                {"29883": {"category": "praesterium", "name": "Shard of the Hand"}},
                f,
            )
        tracked = {"29883"}
        names = build_tracked_item_id_to_name(td, tracked)
        self.assertEqual(names.get("29883"), "Shard of the Hand")


class TestPopulateItemNamesExtended(unittest.TestCase):
    def test_praesterium_fallback(self):
        td = tempfile.mkdtemp()
        pr_path = os.path.join(td, "praesterium_loot.json")
        with open(pr_path, "w", encoding="utf-8") as f:
            json.dump(
                {"29884": {"category": "praesterium", "name": "Shard of the Heart"}},
                f,
            )
        inv = {"Alice": {"added": {"29884": 1}, "removed": {}, "item_names": {}}}
        orig_base = os.path.dirname(os.path.abspath(__file__))
        # populate_item_names uses module dir for praesterium; patch via temp copy in repo root test
        import gear_event_storage as ges

        old_dir = os.path.dirname(os.path.abspath(ges.__file__))
        pr_repo = os.path.join(old_dir, "praesterium_loot.json")
        had = os.path.isfile(pr_repo)
        backup = None
        if had:
            with open(pr_repo, "r", encoding="utf-8") as f:
                backup = f.read()
        try:
            with open(pr_repo, "w", encoding="utf-8") as f:
                json.dump(
                    {"29884": {"category": "praesterium", "name": "Shard of the Heart"}},
                    f,
                )
            populate_item_names_for_inv_deltas(inv, None)
            self.assertEqual(
                inv["Alice"]["item_names"]["29884"], "Shard of the Heart"
            )
        finally:
            if had and backup is not None:
                with open(pr_repo, "w", encoding="utf-8") as f:
                    f.write(backup)


class TestCharStateFromEvents(unittest.TestCase):
    """Mirror JS buildCharacterStateFromEvents using Python folding."""

    def test_baseline_plus_events_gives_guild(self):
        baseline = {
            "characters": {
                "Hammurabi": {
                    "level": 65,
                    "aa_unspent": 10,
                    "aa_spent": 100,
                    "hp_max_total": 5000,
                    "class": "Warrior",
                    "guild": "Imperium",
                }
            }
        }
        char_events = [
            {"d": "2026-07-01", "c": "Hammurabi", "f": "aa", "n": 5},
        ]
        folded = char_events_to_char_deltas(char_events)
        bc = baseline["characters"]["Hammurabi"]
        state = {
            "level": bc["level"],
            "aa_total": bc["aa_unspent"] + bc["aa_spent"] + folded["Hammurabi"]["aa_total_change"],
            "guild": bc["guild"],
        }
        self.assertEqual(state["guild"], "Imperium")
        self.assertEqual(state["aa_total"], 115)


class TestDeltaHtmlDumpFirstHelpers(unittest.TestCase):
    def test_divergence_warning_threshold(self):
        dump_char = {"A": {"aa_total_change": 1}}
        event_char = {f"C{i}": {"aa_total_change": 100} for i in range(600)}
        event_day = {"char_deltas": event_char}
        _warn_if_event_dump_divergence(event_day, dump_char, {}, "2026-07-03")
        self.assertEqual(_count_meaningful_char_deltas(dump_char), 1)
        self.assertEqual(_count_meaningful_char_deltas(event_char), 600)


class TestGearEventsItemsByZoneInputs(unittest.TestCase):
    """Ensure gear event fold + tracked filter produces zone-eligible rows when state exists."""

    def test_tracked_praesterium_item_in_folded_delta(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(base)
        append_day_events_from_deltas(
            {},
            {
                "Hammurabi": {
                    "added": {"29883": 1},
                    "removed": {},
                    "item_names": {},
                }
            },
            "2026-07-03",
            base,
        )
        from gear_event_storage import get_day_delta_from_events

        day = get_day_delta_from_events("2026-07-03", base)
        self.assertIn("Hammurabi", day["inv_deltas"])
        self.assertIn("29883", day["inv_deltas"]["Hammurabi"]["added"])


if __name__ == "__main__":
    unittest.main()
