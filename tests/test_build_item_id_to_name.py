"""Tests for item_id_to_name.json builder and char page embed."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_MAGelo_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGelo_ROOT not in sys.path:
    sys.path.insert(0, _MAGelo_ROOT)

from generate_spell_page import (  # noqa: E402
    generate_char_timeline,
    load_item_id_to_name,
)
from gear_event_storage import (  # noqa: E402
    build_item_name_map_for_char,
    load_item_id_to_name_map,
    populate_item_names_for_inv_deltas,
)

_SCRIPTS = os.path.join(_MAGelo_ROOT, "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)
import build_item_id_to_name as builder  # noqa: E402


class TestBuildItemIdToName(unittest.TestCase):
    def test_merge_fill_gaps(self):
        base = {"1": "Sword"}
        added = builder.merge_fill_gaps(base, {"2": "Shield", "1": "Other"})
        self.assertEqual(added, 1)
        self.assertEqual(base["1"], "Sword")
        self.assertEqual(base["2"], "Shield")

    def test_merge_override(self):
        base = {"1": "db name"}
        updated = builder.merge_override(base, {"1": "Magelo Name"})
        self.assertEqual(updated, 1)
        self.assertEqual(base["1"], "Magelo Name")

    def test_scan_inventory_names(self):
        td = tempfile.mkdtemp()
        inv = Path(td) / "inv.txt"
        inv.write_text(
            "char_id\tslot_id\titem_id\titem_name\n"
            "1\t0\t10037\tDiamond\n"
            "2\t1\t14299\t5 Dose Potion\n",
            encoding="utf-8",
        )
        names = builder.scan_inventory_names(inv)
        self.assertEqual(names["10037"], "Diamond")
        self.assertEqual(names["14299"], "5 Dose Potion")

    def test_build_with_overlays(self):
        td = tempfile.mkdtemp()
        root = Path(td)
        (root / "data").mkdir()
        (root / "data" / "item_stats.json").write_text(
            json.dumps({"999": {"name": "Test Item"}}),
            encoding="utf-8",
        )
        name_map, stats = builder.build_item_id_to_name(root, skip_db=True)
        self.assertIn("999", name_map)
        self.assertEqual(name_map["999"], "Test Item")
        self.assertGreaterEqual(stats["from_item_stats"], 1)

    def test_load_item_id_to_name_from_repo(self):
        names = load_item_id_to_name(_MAGelo_ROOT)
        if os.path.isfile(os.path.join(_MAGelo_ROOT, "data", "item_id_to_name.json")):
            self.assertGreater(len(names), 1000)
            self.assertIn("10037", names)

    def test_char_timeline_embeds_full_map(self):
        td = tempfile.mkdtemp()
        base = Path(td)
        (base / "delta_snapshots" / "gear_events").mkdir(parents=True)
        (base / "delta_snapshots" / "gear_events" / "manifest.json").write_text(
            '{"version":1,"days":{},"eras":[]}',
            encoding="utf-8",
        )
        src = Path(_MAGelo_ROOT) / "data" / "item_id_to_name.json"
        if not src.is_file():
            self.skipTest("item_id_to_name.json not present")
        (base / "data").mkdir()
        (base / "data" / "item_id_to_name.json").write_text(
            src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        path = generate_char_timeline(str(base))
        html = Path(path).read_text(encoding="utf-8")
        self.assertIn('"10037": "Diamond"', html)

    def test_build_item_name_map_uses_global_map(self):
        baseline = {
            "inventories": {
                "Alice": [{"item_id": "100", "item_name": "Baseline Sword"}],
            }
        }
        with mock.patch(
            "gear_event_storage.load_item_id_to_name_map",
            return_value={"200": "Global Shield"},
        ):
            name_map = build_item_name_map_for_char(baseline, "Alice")
        self.assertEqual(name_map["100"], "Baseline Sword")
        self.assertEqual(name_map["200"], "Global Shield")

    def test_populate_item_names_prefers_global_map(self):
        inv_deltas = {"Bob": {"added": {"300": 1}, "removed": {}}}
        with mock.patch(
            "gear_event_storage.load_item_id_to_name_map",
            return_value={"300": "Global Item"},
        ):
            populate_item_names_for_inv_deltas(inv_deltas, None)
        self.assertEqual(inv_deltas["Bob"]["item_names"]["300"], "Global Item")


if __name__ == "__main__":
    unittest.main()
