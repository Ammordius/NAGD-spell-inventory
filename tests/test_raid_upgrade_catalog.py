"""
Tests for the offline raid upgrade catalog generator.

Run:
  python -m unittest tests.test_raid_upgrade_catalog
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_raid_upgrade_catalog as catalog  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "daily-update.yml"


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class TestZoneAllowlistAndAliases(unittest.TestCase):
    def test_six_zones_defined(self):
        self.assertEqual(len(catalog.ZONE_DEFS), 6)
        ids = [z["zone_id"] for z in catalog.ZONE_DEFS]
        self.assertEqual(
            ids,
            [
                "plane_of_time",
                "plane_of_water",
                "plane_of_fire",
                "vex_thal",
                "temple_of_ssraeshza",
                "sanctus_seru",
            ],
        )

    def test_vex_thall_alias(self):
        self.assertEqual(catalog.resolve_zone_id("Vex Thall"), "vex_thal")
        self.assertEqual(catalog.resolve_zone_id("vex thall"), "vex_thal")
        self.assertEqual(catalog.resolve_zone_id("Vex Thal"), "vex_thal")

    def test_ssra_aliases(self):
        self.assertEqual(catalog.resolve_zone_id("ssra"), "temple_of_ssraeshza")
        self.assertEqual(catalog.resolve_zone_id("Temple of Ssraeshza"), "temple_of_ssraeshza")
        self.assertEqual(catalog.resolve_zone_id("Ssraeshza Temple"), "temple_of_ssraeshza")

    def test_seru_aliases(self):
        self.assertEqual(catalog.resolve_zone_id("seru"), "sanctus_seru")
        self.assertEqual(catalog.resolve_zone_id("Sanctus Seru"), "sanctus_seru")

    def test_never_infers_zone_from_mob_name(self):
        # Mob names that mention gods/zones must not resolve without a zone string.
        self.assertIsNone(catalog.resolve_zone_id(""))
        self.assertIsNone(catalog.resolve_zone_id("Bertoxxulous"))
        self.assertIsNone(catalog.resolve_zone_id("Lord Inquisitor Seru"))
        self.assertIsNone(catalog.resolve_zone_id("Crypt of Decay"))
        self.assertIsNone(catalog.resolve_zone_id("Temple of Veeshan"))


class TestCatalogBuildFixtures(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.root = Path(self.td.name)
        self.raid = {
            "15927": {
                "mob": "Bertoxxulous",
                "zone": "Plane of Time",
                "name": "Belt of Temporal Bindings",
            },
            "99901": {
                "mob": "Aten_Ha_Ra",
                "zone": "Vex Thall",
                "name": "Alias Zone Test Item",
            },
            "99902": {
                "mob": "Emperor_Ssraeshza_",
                "zone": "Ssraeshza Temple",
                "name": "Ssra Alias Item",
            },
            "99903": {
                "mob": "Lord_Inquisitor_Seru",
                "zone": "seru",
                "name": "Seru Alias Item",
            },
            "99904": {
                "mob": "Coirnav_the_Avatar_of_Water",
                "zone": "Plane of Water",
                "name": "Water Direct Drop",
            },
            "99905": {
                "mob": "Fennin_Ro_the_Tyrant_of_Fire",
                "zone": "Plane of Fire",
                "name": "Fire Direct Drop",
            },
            # Duplicate source record (same mob/zone/item) — must dedupe.
            # Out-of-scope zone — must not enter catalog via zone inference.
            "1547": {
                "mob": "Cazic_Thule",
                "zone": "Plane of Fear",
                "name": "Eye of Cazic Thule",
            },
            # Ambiguous: empty zone
            "88801": {
                "mob": "Someone",
                "zone": "",
                "name": "No Zone Item",
            },
            # Ambiguous unknown zone label
            "88802": {
                "mob": "Emperor_Ssraeshza_",
                "zone": "Other / Unknown",
                "name": "Unknown Zone Emperor Drop",
            },
        }
        self.dkp = {
            "Bertoxxulous|Plane of Time": {
                "mob": "Bertoxxulous",
                "mobs": ["Bertoxxulous"],
                "zone": "Plane of Time",
                "loot": [
                    {
                        "item_id": 15927,
                        "name": "Belt of Temporal Bindings",
                        "sources": ["dkp", "raid_item_sources"],
                    },
                    {
                        "item_id": 16377,
                        "name": "Timeless Leather Tunic Pattern",
                        "sources": ["dkp", "elemental_armor"],
                    },
                ],
            },
            "Quarm|Plane of Time": {
                "mob": "Quarm",
                "mobs": ["Quarm"],
                "zone": "Plane of Time",
                "loot": [
                    {
                        "item_id": 16377,
                        "name": "Timeless Leather Tunic Pattern",
                        "sources": ["dkp", "elemental_armor"],
                    },
                    {
                        "item_id": 16363,
                        "name": "Timeless Chain Tunic Pattern",
                        "sources": ["dkp"],
                    },
                ],
            },
            # Same god, different instance — must NOT fold into Plane of Time.
            "Bertoxxulous|Crypt of Decay": {
                "mob": "Bertoxxulous",
                "mobs": ["Bertoxxulous"],
                "zone": "Crypt of Decay",
                "loot": [
                    {
                        "item_id": 15927,
                        "name": "Belt of Temporal Bindings",
                        "sources": ["dkp"],
                    },
                    {
                        "item_id": 77777,
                        "name": "Decay Only Item",
                        "sources": ["dkp"],
                    },
                ],
            },
            "General_Reparm|Plane of Fire": {
                "mob": "General_Reparm",
                "mobs": ["General_Reparm"],
                "zone": "Plane of Fire",
                "loot": [
                    {
                        "item_id": 16362,
                        "name": "Elemental Chain Coif Pattern",
                        "sources": ["elemental_armor"],
                    }
                ],
            },
            "Aten_Ha_Ra|Vex Thal": {
                "mob": "Aten_Ha_Ra",
                "mobs": ["Aten_Ha_Ra"],
                "zone": "Vex Thal",
                "loot": [
                    {
                        "item_id": 99901,
                        "name": "Alias Zone Test Item",
                        "sources": ["dkp"],
                    }
                ],
            },
            "Lord_Inquisitor_Seru|Sanctus Seru": {
                "mob": "Lord_Inquisitor_Seru",
                "mobs": ["Lord_Inquisitor_Seru"],
                "zone": "Sanctus Seru",
                "loot": [
                    {
                        "item_id": 99903,
                        "name": "Seru Alias Item",
                        "sources": ["dkp"],
                    }
                ],
            },
            # Null item id — coverage, not silent drop from report.
            "BadMob|Plane of Water": {
                "mob": "BadMob",
                "mobs": ["BadMob"],
                "zone": "Plane of Water",
                "loot": [
                    {"item_id": None, "name": "Unidentified Water Loot", "sources": ["dkp"]}
                ],
            },
        }
        self.purchases = {
            "16362": {
                "name": "Elemental Chain Coif Pattern",
                "slot": "head",
                "armor_type": "chain",
                "magelo_item_ids_by_class": {"rog": "9806", "shm": "9830", "rng": "9821"},
            },
            "16363": {
                "name": "Timeless Chain Tunic Pattern",
                "slot": "chest",
                "armor_type": "chain",
                "magelo_item_ids_by_class": {"rog": "32130", "shm": "32138", "rng": "32604"},
            },
            "16377": {
                "name": "Timeless Leather Tunic Pattern",
                "slot": "chest",
                "armor_type": "leather",
                "magelo_item_ids_by_class": {"dru": "32140", "mnk": "32141", "bst": "32142"},
            },
            # Pattern with empty class map → unresolved / missing armor mapping
            "16999": {
                "name": "Broken Pattern",
                "slot": "head",
                "armor_type": "silk",
                "magelo_item_ids_by_class": {},
            },
        }
        self.item_stats = {
            "15927": {"name": "Belt of Temporal Bindings", "slot": "WAIST", "ac": 10},
            "99901": {"name": "Alias Zone Test Item", "slot": "PRIMARY"},
            "99902": {"name": "Ssra Alias Item", "slot": "FINGER"},
            "99903": {"name": "Seru Alias Item", "slot": "NECK"},
            "99904": {"name": "Water Direct Drop", "slot": "PRIMARY"},
            "99905": {"name": "Fire Direct Drop", "slot": "PRIMARY"},
            "16362": {"name": "Elemental Chain Coif Pattern"},
            "16363": {"name": "Timeless Chain Tunic Pattern"},
            "16377": {"name": "Timeless Leather Tunic Pattern"},
            "9806": {"name": "Rogue Coif"},
            "9830": {"name": "Shaman Coif"},
            "9821": {"name": "Ranger Coif"},
            "32130": {"name": "Rogue Timeless"},
            "32138": {"name": "Shaman Timeless"},
            "32604": {"name": "Ranger Timeless"},
            "32140": {"name": "Druid Timeless"},
            "32141": {"name": "Monk Timeless"},
            "32142": {"name": "Beastlord Timeless"},
            # 77777 intentionally missing stats
        }
        # Inject broken pattern as Fire drop for unresolved armor mapping coverage.
        self.dkp["Broken|Plane of Fire"] = {
            "mob": "Broken_Boss",
            "mobs": ["Broken_Boss"],
            "zone": "Plane of Fire",
            "loot": [
                {"item_id": 16999, "name": "Broken Pattern", "sources": ["dkp"]},
                {"item_id": 77777, "name": "No Stats Fire Item", "sources": ["dkp"]},
            ],
        }

    def tearDown(self):
        self.td.cleanup()

    def _purchases_normalized(self):
        # Mimic load_elemental_purchases output shape.
        out = {}
        for pid, entry in self.purchases.items():
            by_class = {
                k.upper(): str(v)
                for k, v in (entry.get("magelo_item_ids_by_class") or {}).items()
                if v
            }
            out[pid] = {
                "name": entry["name"],
                "slot": entry.get("slot", ""),
                "armor_type": entry.get("armor_type", ""),
                "class_wearables": dict(sorted(by_class.items())),
                "provenance": "dkp_elemental_to_magelo",
            }
        return out

    def test_covers_all_six_zones_and_aliases(self):
        cat, cov = catalog.build_catalog(
            self.raid, self.dkp, self._purchases_normalized(), self.item_stats
        )
        zone_ids = {z["zone_id"] for z in cat["zones"]}
        self.assertEqual(len(zone_ids), 6)
        items_by_id = {i["item_id"]: i for i in cat["items"]}

        self.assertIn("15927", items_by_id)
        self.assertIn("99901", items_by_id)
        self.assertEqual(items_by_id["99901"]["sources"][0]["zone_id"], "vex_thal")
        self.assertIn("99902", items_by_id)
        self.assertEqual(items_by_id["99902"]["sources"][0]["zone_id"], "temple_of_ssraeshza")
        self.assertIn("99903", items_by_id)
        self.assertEqual(items_by_id["99903"]["sources"][0]["zone_id"], "sanctus_seru")
        self.assertIn("99904", items_by_id)
        self.assertIn("99905", items_by_id)

        # Fear Cazic item must not appear via mob-name inference.
        self.assertNotIn("1547", items_by_id)
        # 77777 drops in Crypt of Decay and Plane of Fire; only Fire is allowlisted.
        self.assertIn("77777", items_by_id)
        self.assertEqual(items_by_id["77777"]["acquisition_type"], "unresolved")
        self.assertTrue(
            all(s["zone_id"] == "plane_of_fire" for s in items_by_id["77777"]["sources"])
        )
        # Belt must only have PoT source, not Crypt of Decay.
        belt_zones = {s["zone_id"] for s in items_by_id["15927"]["sources"]}
        self.assertEqual(belt_zones, {"plane_of_time"})

        reasons = {a["reason"] for a in cov["ambiguous_source_assignments"]}
        self.assertIn("empty_zone", reasons)
        self.assertIn("ambiguous_zone", reasons)
        self.assertIn("null_item_id", reasons)

    def test_multi_source_loot_and_dedupe(self):
        cat, _cov = catalog.build_catalog(
            self.raid, self.dkp, self._purchases_normalized(), self.item_stats
        )
        timeless = next(i for i in cat["items"] if i["item_id"] == "16377")
        targets = {s["target_id"] for s in timeless["sources"]}
        self.assertEqual(
            targets,
            {"bertoxxulous|plane_of_time", "quarm|plane_of_time"},
        )
        # Duplicate raid+dkp provenance merges into one Bertoxxulous source.
        ber = [s for s in timeless["sources"] if s["mob"] == "Bertoxxulous"][0]
        self.assertIn("dkp", ber["provenance"])
        self.assertIn("elemental_armor", ber["provenance"])

    def test_class_specific_armor_mappings(self):
        cat, cov = catalog.build_catalog(
            self.raid, self.dkp, self._purchases_normalized(), self.item_stats
        )
        by_id = {i["item_id"]: i for i in cat["items"]}
        coif = by_id["16362"]
        self.assertEqual(coif["acquisition_type"], "armor_pattern")
        self.assertEqual(coif["purchase_item_id"], "16362")
        self.assertIsNone(coif["wearable_item_id"])
        self.assertEqual(coif["class_wearables"]["ROG"], "9806")
        self.assertEqual(coif["conversion_provenance"], "dkp_elemental_to_magelo")

        chain = by_id["16363"]
        self.assertEqual(chain["acquisition_type"], "armor_pattern")
        self.assertIn("ROG", chain["class_wearables"])

        broken = by_id["16999"]
        self.assertEqual(broken["acquisition_type"], "unresolved")
        self.assertTrue(
            any(m["item_id"] == "16999" for m in cov["missing_armor_mappings"])
        )
        self.assertIn("16999", cov["unresolved_ids"])

    def test_unresolved_missing_stats(self):
        cat, cov = catalog.build_catalog(
            self.raid, self.dkp, self._purchases_normalized(), self.item_stats
        )
        by_id = {i["item_id"]: i for i in cat["items"]}
        self.assertEqual(by_id["77777"]["acquisition_type"], "unresolved")
        self.assertIn("77777", cov["unresolved_ids"])
        self.assertTrue(any(m["item_id"] == "77777" for m in cov["missing_stats"]))

    def test_idempotent_generation(self):
        purchases = self._purchases_normalized()
        cat1, cov1 = catalog.build_catalog(self.raid, self.dkp, purchases, self.item_stats)
        cat2, cov2 = catalog.build_catalog(self.raid, self.dkp, purchases, self.item_stats)
        self.assertEqual(cat1, cat2)
        # Coverage input_notes are filled by run_build; build_catalog leaves [].
        self.assertEqual(cov1, cov2)

    def test_end_to_end_cli_writes_stable_output(self):
        raid_path = self.root / "raid_item_sources.json"
        dkp_path = self.root / "dkp_mob_loot.json"
        el_path = self.root / "dkp_elemental_to_magelo.json"
        stats_path = self.root / "data" / "item_stats.json"
        out_path = self.root / "data" / "raid_upgrade_catalog.json"
        cov_path = self.root / "data" / "raid_upgrade_catalog_coverage.json"
        _write(raid_path, self.raid)
        _write(dkp_path, self.dkp)
        _write(el_path, {"dkp_purchases": self.purchases, "by_class": {}, "magelo_item_to_dkp": {}})
        _write(stats_path, self.item_stats)

        rc = catalog.main(
            [
                "--raid-sources",
                str(raid_path),
                "--dkp-loot",
                str(dkp_path),
                "--elemental",
                str(el_path),
                "--item-stats",
                str(stats_path),
                "--output",
                str(out_path),
                "--coverage-output",
                str(cov_path),
            ]
        )
        self.assertEqual(rc, 0)
        self.assertTrue(out_path.is_file())
        cat = json.loads(out_path.read_text(encoding="utf-8"))
        self.assertEqual(catalog.validate_catalog_schema(cat), [])

        rc2 = catalog.main(
            [
                "--raid-sources",
                str(raid_path),
                "--dkp-loot",
                str(dkp_path),
                "--elemental",
                str(el_path),
                "--item-stats",
                str(stats_path),
                "--output",
                str(out_path),
                "--coverage-output",
                str(cov_path),
                "--validate",
            ]
        )
        self.assertEqual(rc2, 0)


class TestElementalFallbackAndWorkflow(unittest.TestCase):
    def test_elemental_slot_options_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            slot_path = root / "elemental_slot_options.json"
            _write(
                slot_path,
                {
                    "by_slot_id": {
                        "2": [
                            {
                                "pattern_name": "Elemental Chain Coif Pattern",
                                "pattern_id": "16362",
                                "by_class": {"ROG": "9806", "SHM": "9830"},
                            }
                        ]
                    }
                },
            )
            purchases = catalog.load_elemental_purchases(None, slot_path)
            self.assertIn("16362", purchases)
            self.assertEqual(purchases["16362"]["class_wearables"]["ROG"], "9806")
            self.assertEqual(purchases["16362"]["provenance"], "elemental_slot_options")

    def test_workflow_deploys_and_validates_catalog(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("raid_upgrade_catalog.json", text)
        self.assertIn("build_raid_upgrade_catalog.py", text)
        self.assertIn(
            "cp data/raid_upgrade_catalog.json deploy/data/raid_upgrade_catalog.json",
            text,
        )


class TestCommittedCatalogSmoke(unittest.TestCase):
    def test_committed_catalog_has_six_zones_if_present(self):
        path = ROOT / "data" / "raid_upgrade_catalog.json"
        if not path.is_file():
            self.skipTest("catalog not generated yet")
        cat = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(catalog.validate_catalog_schema(cat), [])
        self.assertEqual(len(cat["zones"]), 6)
        # Spot-check each zone has at least one item when using real data.
        by_zone = {z: 0 for z in (x["zone_id"] for x in cat["zones"])}
        for item in cat["items"]:
            for src in item["sources"]:
                by_zone[src["zone_id"]] += 1
        for zid, n in by_zone.items():
            self.assertGreater(n, 0, msg=f"{zid} has no source links")


if __name__ == "__main__":
    unittest.main()
