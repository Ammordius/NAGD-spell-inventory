"""
Regression tests for Class Rankings gear plans / My Toons feature gates.

Manual checklist (browser): persist A/B, refresh, top-N extras, Magelo acquire,
2H/OH, resets, DKP/Mod2 stay gated, no server writes; viewing vs auto-claim vs unclaim.

Run:
  python -m unittest tests.test_class_rankings_gear_plans
  node --test tests/js/class_rankings_gear_plans.test.js
"""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "class_rankings.html"
JS = ROOT / "class_rankings_gear_plans.js"
NODE_TEST = ROOT / "tests" / "js" / "class_rankings_gear_plans.test.js"
WORKFLOW = ROOT / ".github" / "workflows" / "daily-update.yml"


class TestClassRankingsGearPlansStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.js = JS.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_module_and_html_exist(self):
        self.assertTrue(HTML.is_file())
        self.assertTrue(JS.is_file())
        self.assertIn("class_rankings_gear_plans.js", self.html)
        self.assertIn("ClassRankingsGearPlans", self.js)

    def test_public_my_toons_and_targets_not_behind_dkp_gate(self):
        # Entry controls are always present (display:flex), not gated by dkpValEnabled.
        self.assertIn('id="showMyToons"', self.html)
        self.assertIn('id="showMyGearTargets"', self.html)
        self.assertIn('id="myGearPlansSection"', self.html)
        self.assertIn('id="myToonsPanel"', self.html)
        self.assertIn('id="myGearTargetsPanel"', self.html)
        # toon list section remains DKP-gated
        self.assertIn("if (dkpValEnabled && toonListSection)", self.html)
        self.assertIn('id="toonListSection"', self.html)

    def test_dkp_and_mod2_gates_still_present(self):
        self.assertIn("dkp_val", self.html)
        self.assertIn("dkpValEnabled", self.html)
        self.assertIn("mod2Enabled", self.html)
        self.assertIn("if (dkpValEnabled)", self.html)
        self.assertIn("if (mod2Enabled)", self.html)

    def test_multislot_best_slot_across_toon_helper(self):
        # dkp_val across-toon comparison picks highest-delta slot for multislot items.
        self.assertIn("function evaluateItemUpgradeForCharacter(", self.html)
        start_cmp = self.html.find("function openItemComparison(")
        start_lookup = self.html.find("function openItemComparisonByItemId(")
        self.assertGreater(start_cmp, 0)
        self.assertGreater(start_lookup, start_cmp)
        cmp_block = self.html[start_cmp:start_lookup]
        lookup_block = self.html[start_lookup:start_lookup + 8000]
        self.assertIn("evaluateItemUpgradeForCharacter", cmp_block)
        self.assertIn("evaluateItemUpgradeForCharacter", lookup_block)
        self.assertIn("best.isUpgrade", cmp_block)

    def test_public_targets_render_path_omits_dkp_mod2_helpers(self):
        # The My Gear Targets renderer must not call gated helpers.
        start = self.html.find("function renderGearTargets()")
        self.assertGreater(start, 0)
        end = self.html.find("function openMyToons()", start)
        self.assertGreater(end, start)
        block = self.html[start:end]
        self.assertNotIn("getDkpForItemId", block)
        self.assertNotIn("getHpPerDkp", block)
        self.assertNotIn("Mod2Scoring", block)
        self.assertNotIn("hp_dkp", block)
        self.assertNotIn("dkpPricesCache", block)

    def test_record_view_and_persist_user_edit_wiring(self):
        self.assertIn("ClassRankingsGearPlans.recordView", self.html)
        self.assertIn("persistUserGearEdit", self.html)
        self.assertIn("pickerUserEdited", self.html)
        self.assertIn("loadToonList", self.html)
        self.assertIn("saveToonList", self.html)

    def test_deploy_copies_gear_plans_js(self):
        self.assertIn("class_rankings_gear_plans.js", self.workflow)
        self.assertIn("cp class_rankings_gear_plans.js deploy/class_rankings_gear_plans.js", self.workflow)

    def test_storage_keys_versioned(self):
        self.assertIn("classRankings:gearPlans:v1", self.js)
        self.assertIn("classRankings:recentChars:v1", self.js)
        self.assertIn("classRankings:charClaims:v1", self.js)
        self.assertIn("classRankings:toonList:v1", self.js)

    def test_multi_seeking_schema_and_apis(self):
        self.assertIn("PLAN_VERSION", self.js)
        self.assertIn("preferredItemId", self.js)
        self.assertIn("candidates", self.js)
        self.assertIn("function setPreferred", self.js)
        self.assertIn("function toggleSeeking", self.js)
        self.assertIn("function setBid", self.js)
        self.assertIn("function markSeeking", self.js)
        self.assertIn("function buildSeekingIndex", self.js)
        self.assertIn("normalizeSlotInterest", self.js)

    def test_seeking_bid_ui_wiring(self):
        self.assertIn('id="rupSeekingFilter"', self.html)
        self.assertIn("formatSeekingControls", self.html)
        self.assertIn("filterAndPinSeekingRows", self.html)
        self.assertIn("item-picker-bid", self.html)
        self.assertIn("gear-target-bid", self.html)
        self.assertIn("markSeeking", self.html)
        # Bid editing in gear targets / raid planner is gated by dkp_val
        self.assertIn("const showBid = !!dkpValEnabled", self.html)
        self.assertIn("rup-seek-bid", self.html)
        # Raid toon Seek lives in Actions; Compare modal has per-toon Seek
        self.assertIn("formatRaidToonActions", self.html)
        self.assertIn("bindComparisonSeekingControls", self.html)
        self.assertIn("cmp-seek-toggle", self.html)
        self.assertIn("formatComparisonSeekControls", self.html)


class TestClassRankingsGearPlansNode(unittest.TestCase):
    def test_node_unit_suite(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not available")
        self.assertTrue(NODE_TEST.is_file())
        proc = subprocess.run(
            [node, "--test", str(NODE_TEST)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(
                "node --test failed\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )


if __name__ == "__main__":
    unittest.main()
