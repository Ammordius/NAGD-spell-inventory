"""Tests for lore tracked-item reacquire guards."""

import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from gear_event_storage import (  # noqa: E402
    append_day_events_from_deltas,
    build_possession_map,
    cancel_paired_unique_events,
    diff_absolute_possession_maps,
    filter_inv_deltas_for_display,
    filter_unique_reacquires_in_inv_deltas,
    get_range_delta_from_events,
    load_gear_events,
)
from generate_spell_page import (  # noqa: E402
    load_lore_item_ids,
    load_unique_tracked_item_ids,
)


LORE_ITEM = "90001"
NON_LORE_ITEM = "90002"


class TestUniqueLootReacquire(unittest.TestCase):
    def test_cancel_paired_unique_events_drops_both(self):
        existing = [
            {"d": "2026-06-01", "c": "Audacious", "i": LORE_ITEM, "s": -1, "n": 1},
        ]
        new_events = [
            {"d": "2026-06-02", "c": "Audacious", "i": LORE_ITEM, "s": 1, "n": 1},
        ]
        pruned, filtered = cancel_paired_unique_events(
            existing,
            new_events,
            {LORE_ITEM},
            window_days=14,
            current_date="2026-06-02",
        )
        self.assertEqual(pruned, [])
        self.assertEqual(filtered, [])

    def test_append_day_cancels_prior_loss_in_shard(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(base)
        append_day_events_from_deltas(
            {},
            {"Audacious": {"added": {}, "removed": {LORE_ITEM: 1}, "item_names": {}}},
            "2026-06-01",
            base,
            unique_tracked_ids={LORE_ITEM},
        )
        append_day_events_from_deltas(
            {},
            {"Audacious": {"added": {LORE_ITEM: 1}, "removed": {}, "item_names": {}}},
            "2026-06-02",
            base,
            unique_tracked_ids={LORE_ITEM},
        )
        events = load_gear_events(base)
        self.assertEqual(events, [])

    def test_filter_unique_reacquires_when_already_owned(self):
        inv = {
            "Audacious": {
                "added": {LORE_ITEM: 1},
                "removed": {},
                "item_names": {},
            }
        }
        possession = {"Audacious": {LORE_ITEM: 1}}
        filter_unique_reacquires_in_inv_deltas(inv, possession, {LORE_ITEM})
        self.assertNotIn("Audacious", inv)

    def test_endpoint_range_diff_ignores_midrange_noise(self):
        baseline_inv = {"Audacious": [{"item_id": LORE_ITEM, "item_name": "Wristband"}]}
        gear_events = [
            {"d": "2026-06-02", "c": "Audacious", "i": LORE_ITEM, "s": -1, "n": 1},
            {"d": "2026-06-03", "c": "Audacious", "i": LORE_ITEM, "s": 1, "n": 1},
            {"d": "2026-06-04", "c": "Audacious", "i": LORE_ITEM, "s": -1, "n": 1},
            {"d": "2026-06-05", "c": "Audacious", "i": LORE_ITEM, "s": 1, "n": 1},
        ]
        abs_start = build_possession_map(baseline_inv, gear_events, "2026-06-01")
        abs_end = build_possession_map(baseline_inv, gear_events, "2026-06-05")
        inv_deltas = diff_absolute_possession_maps(abs_start, abs_end)
        filter_inv_deltas_for_display(inv_deltas, abs_start, abs_end, {LORE_ITEM})
        self.assertEqual(inv_deltas, {})

    def test_true_first_acquisition_still_counts(self):
        baseline_inv = {}
        gear_events = [
            {"d": "2026-06-02", "c": "Audacious", "i": LORE_ITEM, "s": 1, "n": 1},
        ]
        abs_start = build_possession_map(baseline_inv, gear_events, "2026-06-01")
        abs_end = build_possession_map(baseline_inv, gear_events, "2026-06-02")
        inv_deltas = diff_absolute_possession_maps(abs_start, abs_end)
        self.assertEqual(inv_deltas["Audacious"]["added"][LORE_ITEM], 1)

    def test_non_lore_item_unaffected_by_reacquire_filter(self):
        inv = {
            "Bob": {
                "added": {NON_LORE_ITEM: 2},
                "removed": {},
                "item_names": {},
            }
        }
        possession = {"Bob": {NON_LORE_ITEM: 1}}
        filter_unique_reacquires_in_inv_deltas(inv, possession, {LORE_ITEM})
        self.assertEqual(inv["Bob"]["added"][NON_LORE_ITEM], 2)

    def test_get_range_delta_from_events_endpoint_reconstruction(self):
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


class TestLoreMetadataHelpers(unittest.TestCase):
    def test_load_lore_item_ids_returns_set(self):
        lore = load_lore_item_ids()
        self.assertIsInstance(lore, set)

    def test_unique_tracked_subset_of_tracked_and_lore(self):
        from generate_spell_page import load_tracked_item_ids

        tracked, _, _, _ = load_tracked_item_ids()
        unique = load_unique_tracked_item_ids(tracked)
        self.assertTrue(unique.issubset(tracked))
        lore = load_lore_item_ids()
        self.assertTrue(unique.issubset(lore))


if __name__ == "__main__":
    unittest.main()
