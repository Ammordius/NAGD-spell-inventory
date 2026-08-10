"""Tests for per-mob loot acquisition timeline (mirrors mob.html client wiring)."""

import json
import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from generate_spell_page import (  # noqa: E402
    build_mob_item_maps,
    generate_mob_timeline,
    mob_timeline_link,
)


class TestMobTimeline(unittest.TestCase):
    def test_mob_timeline_link(self):
        link = mob_timeline_link("#Lady_Mirenilla", color="#555")
        self.assertIn("mob.html?m=", link)
        self.assertIn("Lady_Mirenilla", link)
        self.assertIn("Mob loot timeline", link)
        self.assertIn("#555", link)

    def test_mob_timeline_link_empty(self):
        self.assertEqual(mob_timeline_link(""), "")
        self.assertEqual(mob_timeline_link(None), "")

    def test_build_mob_item_maps(self):
        item_mob = {
            "1097": "#Lady_Mirenilla",
            "2000": "#Lady_Mirenilla",
            "3000": "Emperor_Salaris",
            "4000": "",
        }
        item_zone = {
            "1097": "Temple of Veeshan",
            "2000": "Temple of Veeshan",
            "3000": "Veeshan's Peak",
        }
        mob_items, mob_zones = build_mob_item_maps(item_mob, item_zone)
        self.assertEqual(sorted(mob_items["#Lady_Mirenilla"]), ["1097", "2000"])
        self.assertEqual(mob_items["Emperor_Salaris"], ["3000"])
        self.assertNotIn("", mob_items)
        self.assertEqual(mob_zones["#Lady_Mirenilla"], ["Temple of Veeshan"])
        self.assertEqual(mob_zones["Emperor_Salaris"], ["Veeshan's Peak"])

    def test_generate_mob_timeline_writes_html(self):
        td = tempfile.mkdtemp()
        base = os.path.join(td, "delta_snapshots")
        os.makedirs(os.path.join(base, "gear_events"), exist_ok=True)
        with open(os.path.join(base, "gear_events", "manifest.json"), "w", encoding="utf-8") as f:
            f.write('{"version":1,"days":{},"eras":[]}')
        path = generate_mob_timeline(td)
        self.assertTrue(os.path.isfile(path))
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        self.assertIn("'?m='", html)
        self.assertIn("navigateToMob", html)
        self.assertIn("resolveMobName", html)
        self.assertIn("filterAcquisitionEvents", html)
        self.assertIn("fetchGzJsonCached", html)
        self.assertIn("mob-select", html)
        self.assertIn("mob-search", html)
        self.assertIn("Loot Table", html)
        self.assertIn("Acquisition Log", html)
        self.assertIn("sortable", html)
        self.assertIn("renderAcquisitionLogTable", html)
        self.assertIn("acqSort", html)
        self.assertIn("dir: 'desc'", html)
        self.assertIn('id="mob-items"', html)
        self.assertIn('id="mob-zones"', html)
        # Embedded JSON scripts must be parseable when present
        for script_id in ("mob-items", "mob-zones"):
            start = html.find(f'id="{script_id}"')
            self.assertGreater(start, 0)
            gt = html.find(">", start)
            end = html.find("</script>", gt)
            payload = html[gt + 1 : end]
            json.loads(payload)


if __name__ == "__main__":
    unittest.main()
