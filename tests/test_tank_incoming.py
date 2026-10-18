"""Tank incoming simulator checks.

The fight math lives in tank_simulator.js. This module checks the rankings
sheet pass-through and drives the Node assertions.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _rankings():
    spec = importlib.util.spec_from_file_location(
        "generate_class_rankings", ROOT / "generate_class_rankings.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TankSheetTests(unittest.TestCase):
    def test_sheet_keeps_present_columns_only(self):
        rankings = _rankings()
        sheet = rankings.tank_sheet_from_row({
            "ac_item": "949",
            "ac_shield": "0",
            "ac_avoidance": "501",
            "ac_mitigation": "1368",
            "ac_total": "2206",
            "weight": "197",
            "hp_max_item": "1200",
            "AGI_base": "100",
            "AGI_item": "200",
            "AGI_aa": "98",
            "AGI_total": "398",
            "name": "Voracious",
        })
        self.assertEqual(sheet["ac_shield"], 0)
        self.assertEqual(sheet["ac_mitigation"], 1368)
        self.assertEqual(sheet["ac_total"], 2206)
        self.assertEqual(sheet["AGI_total"], 398)
        self.assertNotIn("name", sheet)

    def test_missing_column_is_omitted(self):
        rankings = _rankings()
        sheet = rankings.tank_sheet_from_row({"ac_total": "10"})
        self.assertEqual(sheet, {"ac_total": 10})


class TankEngineTests(unittest.TestCase):
    def test_node_runner(self):
        node = shutil.which("node")
        if not node:
            self.fail("node is required to run tank_simulator.js")
        completed = subprocess.run(
            [node, str(ROOT / "tests" / "tank_incoming_runner.js")],
            cwd=str(ROOT),
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn('"ok":true', completed.stdout.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
