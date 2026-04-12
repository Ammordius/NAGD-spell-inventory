"""Tests for worn-slot counting used in corpse-loot exclusion (delta report)."""
import os
import sys
import unittest

# Repo root: magelo/
_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from generate_spell_page import (  # noqa: E402
    chars_corpse_loot_excluded,
    count_equipped,
    equipped_worn_by_char_from_inventories,
)


class TestCountEquipped(unittest.TestCase):
    def test_empty_inventory(self):
        self.assertEqual(count_equipped([]), 0)
        self.assertEqual(count_equipped(None), 0)

    def test_ignores_worn_row_with_empty_item_id(self):
        items = [
            {'slot_id': '17', 'item_id': ''},
            {'slot_id': '1', 'item_id': '  '},
            {'slot_id': '2', 'item_id': 'NULL'},
        ]
        self.assertEqual(count_equipped(items), 0)

    def test_counts_valid_worn_int_or_str_slot(self):
        items = [
            {'slot_id': '17', 'item_id': '32129'},
            {'slot_id': 14, 'item_id': '27298'},
        ]
        self.assertEqual(count_equipped(items), 2)

    def test_ignores_item_id_zero(self):
        items = [{'slot_id': '13', 'item_id': '0'}]
        self.assertEqual(count_equipped(items), 0)

    def test_ignores_bag_slots(self):
        items = [{'slot_id': '30', 'item_id': '12345'}]
        self.assertEqual(count_equipped(items), 0)


class TestCharsCorpseLootExcluded(unittest.TestCase):
    def test_prev_effectively_naked_then_geared(self):
        prev_inv = {'X': [{'slot_id': '1', 'item_id': ''}]}
        curr_inv = {'X': [{'slot_id': '1', 'item_id': '100'}]}
        self.assertEqual(chars_corpse_loot_excluded(curr_inv, prev_inv), {'X'})

    def test_no_exclude_when_prev_had_real_gear(self):
        prev_inv = {'X': [{'slot_id': '1', 'item_id': '50'}]}
        curr_inv = {'X': [{'slot_id': '1', 'item_id': '100'}]}
        self.assertEqual(chars_corpse_loot_excluded(curr_inv, prev_inv), set())


class TestEquippedWornByChar(unittest.TestCase):
    def test_builds_counts(self):
        char_data = {'A': {}, 'B': {}}
        inv_data = {
            'A': [{'slot_id': '1', 'item_id': '1'}],
            'B': [],
        }
        m = equipped_worn_by_char_from_inventories(char_data, inv_data)
        self.assertEqual(m['A']['count'], 1)
        self.assertEqual(m['B']['count'], 0)


if __name__ == '__main__':
    unittest.main()
