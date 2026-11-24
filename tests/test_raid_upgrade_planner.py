"""
Static / regression gates for Raid Upgrade Planner UI.

Run:
  python -m unittest tests.test_raid_upgrade_planner
  node --test tests/js/raid_upgrade_planner.test.js
"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "class_rankings.html"
JS = ROOT / "raid_upgrade_planner.js"
NODE_TEST = ROOT / "tests" / "js" / "raid_upgrade_planner.test.js"
WORKFLOW = ROOT / ".github" / "workflows" / "daily-update.yml"
CATALOG = ROOT / "data" / "raid_upgrade_catalog.json"


class TestRaidUpgradePlannerStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = HTML.read_text(encoding="utf-8")
        cls.js = JS.read_text(encoding="utf-8")
        cls.workflow = WORKFLOW.read_text(encoding="utf-8")

    def test_module_and_html_exist(self):
        self.assertTrue(HTML.is_file())
        self.assertTrue(JS.is_file())
        self.assertTrue(CATALOG.is_file())
        self.assertIn("raid_upgrade_planner.js", self.html)
        self.assertIn("RaidUpgradePlanner", self.js)

    def test_raid_upgrades_button_inside_dkp_toon_list_section(self):
        start = self.html.find('id="toonListSection"')
        self.assertGreater(start, 0)
        end = self.html.find('id="myGearPlansSection"', start)
        self.assertGreater(end, start)
        section = self.html[start:end]
        self.assertIn('id="showRaidUpgrades"', section)
        self.assertIn('id="showToonUpgrades"', section)
        self.assertIn("if (dkpValEnabled && toonListSection)", self.html)

    def test_catalog_fetch_only_under_dkp_gate(self):
        # Lazy loader rejects without dkp_val and is only opened from gated button path.
        self.assertIn("function loadRaidUpgradeCatalog()", self.html)
        loader_start = self.html.find("function loadRaidUpgradeCatalog()")
        loader = self.html[loader_start : loader_start + 600]
        self.assertIn("if (!dkpValEnabled)", loader)
        self.assertIn("data/raid_upgrade_catalog.json", loader)
        self.assertIn("if (dkpValEnabled && document.getElementById('showRaidUpgrades'))", self.html)

    def test_shared_roster_helper_and_comparison_sync(self):
        self.assertIn("function resolveToonRoster(", self.html)
        self.assertIn("function ensureToonRosterAndUpgradeData(", self.html)
        self.assertIn("toonUpgradesMatchedChars = matched", self.html)
        self.assertIn("useClaimed", self.html)
        # Claimed fallback path must not write the saved toon list
        open_fn = self.html.find("function openRaidUpgradesPlanner(")
        self.assertGreater(open_fn, 0)
        open_block = self.html[open_fn : open_fn + 2500]
        self.assertIn("useClaimed", open_block)
        self.assertNotIn("saveToonList(", open_block)
        self.assertIn("Using claimed toons does not modify your saved toon list", self.html)

    def test_uses_existing_evaluator_not_reimplemented_comparison(self):
        self.assertIn("evaluateItemUpgradeForCharacter", self.html)
        self.assertIn("evaluateFn: evaluateItemUpgradeForCharacter", self.html)
        self.assertIn("openItemComparisonByItemId", self.html)
        # Existing by-item APIs still present
        self.assertIn("function openItemComparison(", self.html)
        self.assertIn("function openItemComparisonByItemId(", self.html)

    def test_planner_compare_guards_missing_equipped_stats(self):
        self.assertIn("evaluateItemUpgradeForCharacterGuarded", self.html)
        self.assertIn("guardMissingEquipped: true", self.html)
        self.assertIn("Unresolved: equipped item stats missing", self.html)
        self.assertIn("DKP unknown", self.html)
        self.assertIn('data-rup-view="zone"', self.html)
        self.assertIn('data-rup-view="character"', self.html)
        self.assertIn("function syncRaidPlannerChrome(", self.html)
        self.assertIn("mod2Enabled", self.html)
        self.assertIn("e.key !== 'Escape'", self.html)
        self.assertIn("raidUpgradesPanel.style.display = 'none'", self.html)

    def test_workflow_runs_planner_and_catalog_tests(self):
        self.assertIn("tests.test_raid_upgrade_catalog", self.workflow)
        self.assertIn("tests.test_raid_upgrade_planner", self.workflow)

    def test_deploy_copies_planner_js(self):
        self.assertIn("raid_upgrade_planner.js", self.workflow)
        self.assertIn("cp raid_upgrade_planner.js deploy/raid_upgrade_planner.js", self.workflow)

    def test_planner_js_contracts(self):
        self.assertIn("resolveWearableForCharacter", self.js)
        self.assertIn("checkMissingEquippedStats", self.js)
        self.assertIn("unresolved_missing_equipped_stats", self.js)
        self.assertIn("computeAllUpgrades", self.js)
        self.assertIn("groupByZoneTarget", self.js)
        self.assertIn("groupByCharacter", self.js)
        self.assertIn("groupZoneByCharacter", self.js)
        self.assertIn("armor_pattern", self.js)


class TestRaidUpgradePlannerNode(unittest.TestCase):
    def test_node_unit_tests(self):
        if not NODE_TEST.is_file():
            self.skipTest("node test file missing")
        proc = subprocess.run(
            ["node", "--test", str(NODE_TEST)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            self.fail(proc.stdout + "\n" + proc.stderr)


if __name__ == "__main__":
    unittest.main()
