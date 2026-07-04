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
    build_char_guild_map,
    build_range_filter_index,
    build_tracked_item_id_to_name,
    filter_tracked_deltas,
    filter_zone_entries,
    generate_char_timeline,
    generate_delta_history,
    item_matches_loot_filters,
    normalize_loot_filters,
    _count_meaningful_char_deltas,
    _resolve_day_over_day_deltas,
    _warn_if_event_dump_divergence,
)
from gear_event_storage import (  # noqa: E402
    append_day_events_from_deltas,
    char_deltas_to_stat_events,
    char_events_to_char_deltas,
    populate_item_names_for_inv_deltas,
)


class TestBuildCharGuildMap(unittest.TestCase):
    @staticmethod
    def _char_row(name, guild, level=65, klass="Wizard"):
        parts = [""] * 29
        parts[0] = name
        parts[2] = guild
        parts[3] = str(level)
        parts[5] = klass
        parts[10] = "0"
        parts[11] = "0"
        parts[28] = "1000"
        return "\t".join(parts)

    def test_returns_nonempty_guilds_only(self):
        td = tempfile.mkdtemp()
        char_path = os.path.join(td, "chars.txt")
        with open(char_path, "w", encoding="utf-8") as f:
            f.write(self._char_row("name", "guild") + "\n")
            f.write(self._char_row("Clickie", "Destiny") + "\n")
            f.write(self._char_row("Unguilded", "") + "\n")
        guild_map = build_char_guild_map(char_path)
        self.assertEqual(guild_map.get("Clickie"), "Destiny")
        self.assertNotIn("Unguilded", guild_map)

    def test_missing_file_returns_empty(self):
        self.assertEqual(build_char_guild_map("/nonexistent/path.txt"), {})


class TestGenerateDeltaHistoryGuildEmbed(unittest.TestCase):
    def test_embeds_char_guild_map_script(self):
        td = tempfile.mkdtemp()
        char_dir = os.path.join(td, "character")
        os.makedirs(char_dir)
        char_path = os.path.join(char_dir, "TAKP_character.txt")
        with open(char_path, "w", encoding="utf-8") as f:
            f.write(TestBuildCharGuildMap._char_row("name", "guild") + "\n")
            f.write(TestBuildCharGuildMap._char_row("Alice", "Temerity") + "\n")
        out_path = generate_delta_history(td)
        self.assertTrue(os.path.isfile(out_path))
        with open(out_path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="char-guild-map"', html)
        self.assertIn('"Alice": "Temerity"', html)
        self.assertIn("function formatCharDisplay", html)
        self.assertIn("CHAR_GUILD_MAP", html)
        self.assertIn('id="unique-tracked-ids"', html)
        self.assertIn("UNIQUE_TRACKED_IDS", html)
        self.assertIn("buildInventoryAbsMapFromEvents", html)
        self.assertIn("indexGearEventsByChar", html)
        self.assertIn("eventsByChar", html)
        self.assertIn("Computing inventory snapshots", html)
        self.assertIn("loadGearEventsUpTo", html)
        self.assertIn('id="report-filters"', html)
        self.assertIn("buildReportHTML", html)
        self.assertIn("buildRangeFilterIndex", html)
        self.assertIn("loot-filter-zone", html)


class TestLootFilterHelpers(unittest.TestCase):
    """Python mirrors of delta-history loot filter JS helpers."""

    ZONE_MAP = {"100": "Plane of Time", "200": "Praesterium", "300": "Kunark"}
    MOB_MAP = {"100": "Emperor Salaris", "200": "", "300": "Trakanon"}
    NAME_MAP = {"100": "Crown of Deceit", "200": "Shard of the Hand", "300": "Bone Chips"}

    def _sample_zone_entries(self):
        return {
            "Plane of Time": {
                "Emperor Salaris": [
                    {"charName": "Alice", "itemId": "100", "name": "Crown of Deceit"},
                ],
            },
            "Praesterium": {
                "": [
                    {"charName": "Bob", "itemId": "200", "name": "Shard of the Hand"},
                ],
            },
        }

    def _sample_tracked_deltas(self):
        return {
            "Alice": {
                "added": {"100": 1},
                "removed": {},
                "item_names": {"100": "Crown of Deceit"},
                "is_visibility_change": False,
            },
            "Bob": {
                "added": {"200": 1, "300": 2},
                "removed": {"100": 1},
                "item_names": {
                    "200": "Shard of the Hand",
                    "300": "Bone Chips",
                    "100": "Crown of Deceit",
                },
                "is_visibility_change": False,
            },
            "Ghost": {
                "added": {"100": 1},
                "removed": {},
                "item_names": {"100": "Crown of Deceit"},
                "is_visibility_change": True,
            },
        }

    def test_build_range_filter_index_from_zone_entries(self):
        idx = build_range_filter_index(
            self._sample_zone_entries(),
            self._sample_tracked_deltas(),
            self.NAME_MAP,
            self.ZONE_MAP,
            self.MOB_MAP,
        )
        self.assertEqual(idx["zones"], ["Plane of Time", "Praesterium"])
        self.assertIn("Emperor Salaris", idx["mobsByZone"]["Plane of Time"])
        names = {it["name"] for it in idx["items"]}
        self.assertIn("Crown of Deceit", names)
        self.assertIn("Shard of the Hand", names)
        self.assertIn("Bone Chips", names)

    def test_filter_zone_by_zone_substring(self):
        filtered = filter_zone_entries(
            self._sample_zone_entries(),
            {"zone": "plane"},
            self.ZONE_MAP,
            self.MOB_MAP,
            self.NAME_MAP,
        )
        self.assertEqual(list(filtered.keys()), ["Plane of Time"])
        self.assertNotIn("Praesterium", filtered)

    def test_filter_zone_by_mob_and_item_combined(self):
        filtered = filter_zone_entries(
            self._sample_zone_entries(),
            {"mob": "emperor", "itemId": "100"},
            self.ZONE_MAP,
            self.MOB_MAP,
            self.NAME_MAP,
        )
        self.assertEqual(len(filtered), 1)
        entries = filtered["Plane of Time"]["Emperor Salaris"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["itemId"], "100")

    def test_filter_tracked_deltas_by_item_name(self):
        filtered = filter_tracked_deltas(
            self._sample_tracked_deltas(),
            {"itemName": "shard"},
            self.ZONE_MAP,
            self.MOB_MAP,
            self.NAME_MAP,
        )
        self.assertEqual(list(filtered.keys()), ["Bob"])
        self.assertIn("200", filtered["Bob"]["added"])
        self.assertNotIn("300", filtered["Bob"]["added"])

    def test_filter_no_matches_empty(self):
        filtered = filter_zone_entries(
            self._sample_zone_entries(),
            {"zone": "Velious"},
            self.ZONE_MAP,
            self.MOB_MAP,
            self.NAME_MAP,
        )
        self.assertEqual(filtered, {})
        tracked = filter_tracked_deltas(
            self._sample_tracked_deltas(),
            {"itemId": "999"},
            self.ZONE_MAP,
            self.MOB_MAP,
            self.NAME_MAP,
        )
        self.assertEqual(tracked, {})

    def test_item_matches_and_normalize(self):
        lf = normalize_loot_filters(
            {"itemName": "Crown of Deceit"},
            self.NAME_MAP,
        )
        self.assertEqual(lf["itemId"], "100")
        self.assertTrue(
            item_matches_loot_filters(
                "100",
                {"zone": "time", "mob": "salaris"},
                self.ZONE_MAP,
                self.MOB_MAP,
                self.NAME_MAP,
            )
        )
        self.assertFalse(
            item_matches_loot_filters(
                "200",
                {"zone": "Plane of Time"},
                self.ZONE_MAP,
                self.MOB_MAP,
                self.NAME_MAP,
            )
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


def _enrich_char_changes_from_states(char_changes, start_state, end_state, range_char_deltas):
    """Python mirror of delta-history JS enrichCharChangesFromStates."""
    names = set(char_changes) | set(start_state) | set(end_state)
    for char_name in names:
        s = start_state.get(char_name)
        e = end_state.get(char_name)
        if not s or not e:
            continue
        rd = (range_char_deltas or {}).get(char_name, {})
        existing = char_changes.get(char_name, {})
        char_changes[char_name] = {
            "level": e["level"] - s["level"],
            "aa": e["aa_total"] - s["aa_total"],
            "hp": e["hp"] - s["hp"],
            "current_level": e["level"],
            "previous_level": s["level"],
            "current_aa_total": e["aa_total"],
            "class": e.get("class") or rd.get("class") or existing.get("class", ""),
            "is_new": bool(rd.get("is_new") or existing.get("is_new")),
            "is_deleted": bool(rd.get("is_deleted") or existing.get("is_deleted")),
            "is_visibility_change": bool(
                rd.get("is_visibility_change") or existing.get("is_visibility_change")
            ),
        }


class TestEnrichCharChangesFromStates(unittest.TestCase):
    def test_endpoint_diff_for_leaderboard(self):
        start_state = {
            "Alice": {"level": 65, "aa_total": 100, "hp": 2000, "class": "Wizard"},
        }
        end_state = {
            "Alice": {"level": 65, "aa_total": 108, "hp": 2100, "class": "Wizard"},
        }
        char_changes = {}
        _enrich_char_changes_from_states(char_changes, start_state, end_state, {})
        c = char_changes["Alice"]
        self.assertEqual(c["current_level"], 65)
        self.assertEqual(c["aa"], 8)
        self.assertEqual(c["hp"], 100)
        self.assertEqual(c["current_aa_total"], 108)

    def test_visibility_flag_from_range_events(self):
        start_state = {"Bob": {"level": 65, "aa_total": 0, "hp": 0}}
        end_state = {"Bob": {"level": 65, "aa_total": 500, "hp": 3000}}
        char_changes = {}
        _enrich_char_changes_from_states(
            char_changes,
            start_state,
            end_state,
            {"Bob": {"is_visibility_change": True}},
        )
        self.assertTrue(char_changes["Bob"]["is_visibility_change"])


class TestCharSnapshotOnEvents(unittest.TestCase):
    def test_stat_events_carry_absolutes(self):
        row = {
            "level_change": 0,
            "aa_total_change": 5,
            "hp_change": 50,
            "current_level": 65,
            "previous_level": 65,
            "current_aa_total": 115,
            "previous_aa_total": 110,
            "current_hp": 5050,
            "previous_hp": 5000,
            "class": "Warrior",
        }
        events = char_deltas_to_stat_events({"Hammurabi": row}, "2026-07-01")
        aa_ev = next(e for e in events if e["f"] == "aa")
        self.assertEqual(aa_ev["n"], 5)
        self.assertEqual(aa_ev["lv"], 65)
        self.assertEqual(aa_ev["aa"], 115)
        self.assertEqual(aa_ev["hp"], 5050)
        self.assertEqual(aa_ev["plv"], 65)
        self.assertEqual(aa_ev["paa"], 110)
        self.assertEqual(aa_ev["php"], 5000)

    def test_fold_propagates_latest_absolutes(self):
        events = [
            {
                "d": "2026-07-01",
                "c": "Alice",
                "f": "aa",
                "n": 3,
                "lv": 60,
                "aa": 103,
                "hp": 1000,
                "plv": 59,
                "paa": 100,
                "php": 950,
            },
            {
                "d": "2026-07-02",
                "c": "Alice",
                "f": "aa",
                "n": 2,
                "lv": 61,
                "aa": 105,
                "hp": 1100,
            },
        ]
        folded = char_events_to_char_deltas(events)
        self.assertEqual(folded["Alice"]["aa_total_change"], 5)
        self.assertEqual(folded["Alice"]["current_level"], 61)
        self.assertEqual(folded["Alice"]["current_aa_total"], 105)
        self.assertEqual(folded["Alice"]["previous_level"], 59)
        self.assertEqual(folded["Alice"]["previous_aa_total"], 100)


class TestResolveDayOverDayDeltas(unittest.TestCase):
    def test_falls_back_to_delta_daily_when_dump_diff_inflated(self):
        td = tempfile.mkdtemp()
        snap = os.path.join(td, "delta_snapshots")
        os.makedirs(snap)
        prev_date, curr_date = "2026-07-02", "2026-07-03"
        baseline = {
            "baseline_date": "2026-02-09",
            "characters": {"Alice": {"level": 65, "aa_unspent": 0, "aa_spent": 0, "hp_max_total": 1000}},
        }
        daily_prev = {
            "baseline_date": "2026-02-09",
            "char_deltas": {"Alice": {"level": 65, "aa_total_change": 0}},
            "inv_deltas": {"Alice": {"added": {"100": 1}, "removed": {}}},
        }
        daily_curr = {
            "baseline_date": "2026-02-09",
            "char_deltas": {"Alice": {"level": 65, "aa_total_change": 1}},
            "inv_deltas": {"Alice": {"added": {"200": 1}, "removed": {}}},
        }
        import gzip

        for d, payload in ((prev_date, daily_prev), (curr_date, daily_curr)):
            with gzip.open(os.path.join(snap, f"delta_daily_{d}.json.gz"), "wt", encoding="utf-8") as f:
                json.dump(payload, f)
        with open(os.path.join(td, ".magelo_previous_dump_date.txt"), "w", encoding="utf-8") as f:
            f.write("Thu Jul  2 16:30:25 UTC 2026\n")
        huge_inv = {
            f"Char{i}": [{"item_id": str(1000 + i)}]
            for i in range(600)
        }
        char_d, inv_d = _resolve_day_over_day_deltas(
            {},
            {},
            {"Alice": {"level": 65}},
            huge_inv,
            curr_date,
            td,
            baseline,
        )
        self.assertIn("Alice", inv_d)
        self.assertIn("200", inv_d["Alice"]["added"])


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
