"""Regression tests for launch-era Mod2 scoring."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mod2_scoring as m  # noqa: E402


class Mod2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table = m.load_item_table()
        cls.config = m.load_config()

    def test_all_nine_stats_and_caps(self):
        self.assertEqual(set(m.STATS), set(m.CAPS))
        self.assertEqual(m.CAPS["accuracy"], 150)
        self.assertEqual(m.CAPS["avoidance"], 100)
        self.assertEqual(m.CAPS["combat_effects"], 100)
        self.assertEqual(m.CAPS["damage_shield"], 25)
        self.assertEqual(m.CAPS["shielding"], 35)
        self.assertEqual(m.CAPS["spell_shielding"], 35)
        self.assertEqual(m.CAPS["dot_shielding"], 35)
        self.assertEqual(m.CAPS["strikethrough"], 35)
        self.assertEqual(m.CAPS["stun_resist"], 35)

    def test_aliases_and_malformed(self):
        mods = m.normalize_mods({
            "Spell Shield": 4,
            "spellshield": 1,
            "Combat Effects": 5,
            "DS": "nope",
            "stun resist": 3,
        })
        self.assertEqual(mods["spell_shielding"], 5)
        self.assertEqual(mods["combat_effects"], 5)
        self.assertEqual(mods["stun_resist"], 3)
        self.assertEqual(mods["damage_shield"], 0)

    def test_launch_file_scope(self):
        self.assertEqual(len(self.table["items"]), 63)
        names = {row["name"] for row in self.table["unresolved"]}
        self.assertIn("Galladan's Stormwrath Tunic", names)
        self.assertEqual(m.lookup_mods(999999, self.table)["shielding"], 0)

    def test_known_items_and_dual_mods(self):
        by_name = {row["name"]: (item_id, row) for item_id, row in self.table["items"].items()}
        self.assertEqual(by_name["Greaves of Furious Might"][0], "28650")
        self.assertEqual(by_name["Greaves of Furious Might"][1]["mods"], {"shielding": 4})
        self.assertEqual(by_name["Pants of Furious Might"][1]["mods"], {"avoidance": 25})
        self.assertEqual(by_name["Shield of Strife"][1]["mods"], {"shielding": 3})
        shroud = by_name["Shroud of Eternity"][1]["mods"]
        self.assertEqual(shroud["shielding"], 4)
        self.assertEqual(shroud["damage_shield"], 5)
        self.assertEqual(by_name["Ultor's Chestguard of Faith"][1]["mods"], {"stun_resist": 7})
        self.assertNotIn("Chestugard", by_name)

    def test_idempotent_merge(self):
        once = m.merge_mods({}, {"shielding": 4, "avoidance": 10})
        twice = m.merge_mods(once, {"shielding": 4, "avoidance": 10, "accuracy": 5})
        self.assertEqual(twice["shielding"], 4)
        self.assertEqual(twice["avoidance"], 10)
        self.assertEqual(twice["accuracy"], 5)

    def test_caps_and_no_bonus_at_cap(self):
        raw = m.empty_mods()
        raw["shielding"] = 40
        raw["stun_resist"] = 35
        capped = m.cap_mods(raw)
        self.assertEqual(capped["shielding"], 35)
        self.assertEqual(m.utility("shielding", 35), 1)
        self.assertEqual(m.utility("shielding", 40), 1)
        self.assertEqual(m.utility("stun_resist", 34.9) < 1, True)
        weights = { "Warrior": self.config["classes"]["Warrior"]["weights"] }
        at_cap = m.mod2_points("Warrior", {"stun_resist": 35}, weights)
        over = m.mod2_points("Warrior", {"stun_resist": 50}, weights)
        self.assertAlmostEqual(at_cap, over)

    def test_quarm_shielding(self):
        db, di = m.quarm_db_di()
        self.assertAlmostEqual(db, 1000)
        self.assertAlmostEqual(di, 140)
        self.assertAlmostEqual(m.shielding_prevented_per_hit(db, 1), 10)
        self.assertAlmostEqual(m.shielding_prevented_per_hit(db, 2), 20)
        self.assertAlmostEqual(m.shielding_prevented_per_hit(db, 4), 40)
        self.assertAlmostEqual(100 * m.shielding_prevented_per_hit(db, 4), 4000)
        self.assertAlmostEqual(m.shielding_prevented_per_hit(db, 40), m.shielding_prevented_per_hit(db, 35))

    def test_stun_threat_scenarios(self):
        capped = {"stun_resist": 35, "combat_effects": 100}
        secure = m.threat_component("Warrior", capped, self.config, {"threat_limitation": 0})
        self.assertEqual(secure, 0)
        absent = m.threat_component("Warrior", capped, self.config, {"stun_exposure": 0, "threat_limitation": 1})
        default = m.threat_component("Warrior", capped, self.config, {})
        constrained = m.threat_component(
            "Warrior", capped, self.config, {"threat_limitation": 1, "stun_exposure": 0.8}
        )
        self.assertGreater(default, 0)
        self.assertGreater(constrained, default)
        # No stun exposure removes the stun threat term; combat-effects threat can remain.
        self.assertLess(absent, default)
        stun_only = m.threat_component("Warrior", {"stun_resist": 35}, self.config, {"stun_exposure": 0})
        self.assertEqual(stun_only, 0)

    def test_negative_and_two_hand_delta(self):
        table = {"items": {
            "1": {"mods": {"shielding": 4}},
            "2": {"mods": {"shielding": 2}},
            "3": {"mods": {"shielding": 1}},
            "9": {"mods": {"shielding": 10}},
        }}
        down = m.upgrade_delta("Warrior", ["1", "2"], ["3"], self.config, table)
        up = m.upgrade_delta("Warrior", ["1", "2"], ["9"], self.config, table)
        self.assertLess(down["display_delta"], 0)
        self.assertGreater(up["display_delta"], 0)
        self.assertGreater(up["item_delta"], 0)

    def test_every_class_reference_scale(self):
        for class_name, row in self.config["classes"].items():
            self.assertIn(class_name, m.REFERENCES)
            weights = row["weights"]
            self.assertEqual(set(weights), set(m.STATS))
            full = m.empty_mods()
            for stat, cap in m.CAPS.items():
                full[stat] = cap
            points = m.mod2_points(class_name, full, {class_name: weights})
            # Full caps are a fraction of the 100-point reference, not raw HP or AC units.
            self.assertGreater(points, 0)
            self.assertLess(points, 40)
            ref_pts = row["reference_mod2_points"]
            shown = m.displayed_score(100, ref_pts, ref_pts, True)
            self.assertAlmostEqual(shown, 100)
            self.assertAlmostEqual(m.displayed_score(91.79, 5, 3, False), 91.79)

    def test_flag_leaves_core_untouched(self):
        char = {"class": "Warrior", "overall_score": 91.79, "inventory": [{"slot_id": 17, "item_id": 28650}]}
        m.annotate_character(char, self.config, self.table)
        self.assertEqual(char["overall_score"], 91.79)
        self.assertGreater(char["mod2"]["points"], 0)

    def test_shielding_beats_avoidance_for_warriors(self):
        weights = self.config["classes"]["Warrior"]["weights"]
        shield = weights["shielding"]["other"] + weights["shielding"]["threat"]
        avoid = weights["avoidance"]["other"] + weights["avoidance"]["threat"]
        self.assertGreater(shield, avoid)
        self.assertGreater(shield, weights["stun_resist"]["threat"])

    def test_config_matches_derive(self):
        fresh = m.build_config()
        for class_name in m.REFERENCES:
            for stat in m.STATS:
                for part in ("other", "threat"):
                    self.assertAlmostEqual(
                        fresh["classes"][class_name]["weights"][stat][part],
                        self.config["classes"][class_name]["weights"][stat][part],
                        places=6,
                    )

    def test_item_json_roundtrip(self):
        raw = json.loads((ROOT / "data" / "item_mod2.json").read_text(encoding="utf-8"))
        self.assertIn("28652", raw["items"])
        self.assertEqual(raw["items"]["28652"]["name"], "Pants of Furious Might")


if __name__ == "__main__":
    unittest.main()
