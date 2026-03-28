"""Run from magelo/scripts:  python -m unittest threat.test_check_aggro"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from threat.check_aggro_amount import check_aggro_amount

_SPELLS = Path(__file__).resolve().parents[2] / "data" / "spells_threat.json"


class TestCheckAggroAmount(unittest.TestCase):
    def test_enraging_blow_proc_instant_hate(self):
        spell = {
            "id": 2675,
            "effectid": [92] + [254] * 11,
            "formula": [100] + [100] * 11,
            "base": [700] + [0] * 11,
            "max": [0] * 12,
            "resisttype": 0,
            "buffduration": 0,
            "buffdurationformula": 0,
            "classes": [1] + [255] * 14,
            "not_player_spell": 0,
            "hate_added": 0,
            "goodEffect": 0,
        }
        h = check_aggro_amount(spell, caster_level=65, target_max_hp=1_000_000, is_weapon_proc=True)
        self.assertEqual(h, 700)

    def test_proc_cap_non_weapon_when_high_non_damage(self):
        spell = {
            "id": 999001,
            "effectid": [21] + [254] * 11,
            "formula": [100] * 12,
            "base": [0] * 12,
            "max": [0] * 12,
            "resisttype": 0,
            "buffduration": 0,
            "buffdurationformula": 0,
            "classes": [255] * 15,
            "not_player_spell": 0,
            "hate_added": 0,
            "goodEffect": 0,
        }
        h = check_aggro_amount(spell, is_weapon_proc=False, class_id=1)
        self.assertEqual(h, 400)

    def test_weapon_proc_uses_400_cap_on_non_damage(self):
        spell = {
            "id": 999001,
            "effectid": [21] + [254] * 11,
            "formula": [100] * 12,
            "base": [0] * 12,
            "max": [0] * 12,
            "resisttype": 0,
            "buffduration": 0,
            "buffdurationformula": 0,
            "classes": [255] * 15,
            "not_player_spell": 0,
            "hate_added": 0,
            "goodEffect": 0,
        }
        h = check_aggro_amount(spell, is_weapon_proc=True, class_id=1)
        self.assertEqual(h, 400)

    def test_anger_proc_capped_path(self):
        data = json.loads(_SPELLS.read_text(encoding="utf-8"))
        spell = data["spells"]["3624"]
        h = check_aggro_amount(spell, caster_level=65, target_max_hp=1_000_000, class_id=1)
        self.assertEqual(h, 1150)


if __name__ == "__main__":
    unittest.main()
