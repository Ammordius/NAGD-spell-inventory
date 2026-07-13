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
    build_tracked_gear_event_log_rows,
    prune_unique_reacquire_events,
)
from generate_spell_page import (  # noqa: E402
    load_lore_item_ids,
    load_unique_tracked_item_ids,
)


LORE_ITEM = "90001"
NON_LORE_ITEM = "90002"


def _build_possession_map_naive(
    baseline_inv: dict,
    gear_events: list[dict],
    up_to_date: str,
    *,
    no_rent: set | None = None,
) -> dict[str, dict[str, int]]:
    """Reference O(chars × events) implementation for parity checks."""
    from collections import defaultdict

    no_rent = no_rent or set()
    counts_by_char: dict[str, dict[str, int]] = {}
    all_chars = set((baseline_inv or {}).keys())
    for ev in gear_events or []:
        d = ev.get("d", "")
        if d and d <= up_to_date and ev.get("c"):
            all_chars.add(ev["c"])

    for char_name in all_chars:
        counts: dict[str, int] = defaultdict(int)
        for item in (baseline_inv or {}).get(char_name, []):
            iid = str(item.get("item_id", "")).strip()
            if not iid or iid.upper() == "NULL":
                continue
            try:
                if int(iid) in no_rent:
                    continue
            except (ValueError, TypeError):
                pass
            try:
                if int(iid) == 0:
                    continue
            except (ValueError, TypeError):
                pass
            counts[iid] += 1

        for ev in sorted(
            gear_events or [],
            key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("i", "")),
        ):
            if ev.get("c") != char_name:
                continue
            d = ev.get("d", "")
            if not d or d > up_to_date:
                continue
            item_id = str(ev.get("i", ""))
            if not item_id:
                continue
            try:
                if int(item_id) in no_rent:
                    continue
            except (ValueError, TypeError):
                pass
            sign = int(ev.get("s") or 0)
            n = int(ev.get("n") or 0)
            if n <= 0 or sign not in (1, -1):
                continue
            if sign > 0:
                counts[item_id] += n
            else:
                counts[item_id] -= n
                if counts[item_id] <= 0:
                    counts.pop(item_id, None)

        cleaned = {k: v for k, v in counts.items() if v > 0}
        if cleaned:
            counts_by_char[char_name] = cleaned
    return counts_by_char


class TestBuildPossessionMapIndexed(unittest.TestCase):
    """Indexed build_possession_map matches naive reference on small fixtures."""

    def test_matches_naive_multi_char_fixture(self):
        baseline_inv = {
            "Alice": [{"item_id": "100"}, {"item_id": "100"}],
            "Bob": [{"item_id": "200"}],
            "Empty": [],
        }
        gear_events = [
            {"d": "2026-06-01", "c": "Alice", "i": "100", "s": -1, "n": 1},
            {"d": "2026-06-02", "c": "Alice", "i": "300", "s": 1, "n": 2},
            {"d": "2026-06-02", "c": "Bob", "i": "200", "s": -1, "n": 1},
            {"d": "2026-06-03", "c": "Bob", "i": "400", "s": 1, "n": 1},
            {"d": "2026-06-04", "c": "Carol", "i": "500", "s": 1, "n": 1},
            {"d": "2026-06-05", "c": "Alice", "i": "300", "s": -1, "n": 1},
        ]
        for up_to in ("2026-06-01", "2026-06-03", "2026-06-05"):
            expected = _build_possession_map_naive(baseline_inv, gear_events, up_to)
            actual = build_possession_map(baseline_inv, gear_events, up_to)
            self.assertEqual(actual, expected, msg=f"up_to={up_to}")


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

    def test_lore_item_flag_matches_lore_item_token(self):
        lore = load_lore_item_ids()
        self.assertGreater(len(lore), 0)
        # Wristband of the Rathe is flagged LORE ITEM in item_stats.json
        self.assertIn("11054", lore)

    def test_unique_tracked_subset_of_tracked_and_lore_or_nodrop(self):
        from generate_spell_page import load_tracked_item_ids, _load_item_ids_with_flag

        tracked, _, _, _ = load_tracked_item_ids()
        unique = load_unique_tracked_item_ids(tracked)
        self.assertTrue(unique.issubset(tracked))
        lore = load_lore_item_ids()
        nodrop = _load_item_ids_with_flag("NO DROP")
        self.assertTrue(unique.issubset(lore | nodrop))
        self.assertGreater(len(unique), 0)
        # Lore raid loot + NO DROP non-lore (e.g. Great Helm) both eligible
        self.assertIn("11054", unique)  # Wristband (LORE ITEM)
        self.assertIn("26581", unique)  # Great Helm (NO DROP)

    def test_double_plus_dump_gap_suppressed_in_timeline(self):
        """Anemal-style: first + kept, second + with no intervening - dropped."""
        baseline = {"inventories": {}, "baseline_date": "2026-02-09"}
        events = [
            {"d": "2026-03-20", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
            {"d": "2026-06-17", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
        ]
        rows = build_tracked_gear_event_log_rows(
            events,
            "Anemal",
            {LORE_ITEM},
            {LORE_ITEM: "Fangs"},
            unique_tracked_ids={LORE_ITEM},
            baseline=baseline,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-03-20")
        self.assertEqual(rows[0]["sign"], 1)

    def test_death_recovery_pair_nulled_in_timeline(self):
        """Baseline-held unique item: - then + within 14d leaves no timeline rows."""
        baseline = {
            "inventories": {
                "Anemal": [{"item_id": LORE_ITEM, "item_name": "Helm"}],
            },
            "baseline_date": "2026-02-09",
        }
        events = [
            {"d": "2026-06-16", "c": "Anemal", "i": LORE_ITEM, "s": -1, "n": 1, "v": 0},
            {"d": "2026-06-17", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
        ]
        rows = build_tracked_gear_event_log_rows(
            events,
            "Anemal",
            {LORE_ITEM},
            {LORE_ITEM: "Helm"},
            unique_tracked_ids={LORE_ITEM},
            baseline=baseline,
        )
        self.assertEqual(rows, [])

    def test_true_acquire_then_death_recovery_keeps_first_plus(self):
        baseline = {"inventories": {}, "baseline_date": "2026-02-09"}
        events = [
            {"d": "2026-05-25", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
            {"d": "2026-06-16", "c": "Anemal", "i": LORE_ITEM, "s": -1, "n": 1, "v": 0},
            {"d": "2026-06-17", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
        ]
        rows = build_tracked_gear_event_log_rows(
            events,
            "Anemal",
            {LORE_ITEM},
            {LORE_ITEM: "Vest"},
            unique_tracked_ids={LORE_ITEM},
            baseline=baseline,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-05-25")
        self.assertEqual(rows[0]["sign"], 1)

    def test_prune_unique_reacquire_events_drops_pairs(self):
        baseline_inv = {"Anemal": [{"item_id": LORE_ITEM}]}
        events = [
            {"d": "2026-06-16", "c": "Anemal", "i": LORE_ITEM, "s": -1, "n": 1, "v": 0},
            {"d": "2026-06-17", "c": "Anemal", "i": LORE_ITEM, "s": 1, "n": 1, "v": 0},
            {"d": "2026-06-17", "c": "Other", "i": NON_LORE_ITEM, "s": 1, "n": 1, "v": 0},
        ]
        pruned = prune_unique_reacquire_events(
            events, {LORE_ITEM}, baseline_inv, window_days=14
        )
        self.assertEqual(len(pruned), 1)
        self.assertEqual(pruned[0]["c"], "Other")


if __name__ == "__main__":
    unittest.main()
