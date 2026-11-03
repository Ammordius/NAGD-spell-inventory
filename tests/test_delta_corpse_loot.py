"""Tests for worn-slot counting used in corpse-loot exclusion (delta report)."""
import os
import sys
import unittest

# Repo root: magelo/
_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from generate_spell_page import (  # noqa: E402
    EXTRA_GUILD_WATCH,
    GUILD_STATUS_WATCHLIST,
    MULE_CHARACTERS,
    WALEX_CHARACTERS,
    chars_became_naked,
    chars_corpse_loot_excluded,
    count_equipped,
    equipped_worn_by_char_from_inventories,
    format_discord_naked_alert,
    generate_guild_status_html,
    notify_discord_if_guild_naked,
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


class TestCharsBecameNaked(unittest.TestCase):
    def test_equipped_to_naked(self):
        prev_inv = {'X': [{'slot_id': '1', 'item_id': '50'}]}
        curr_inv = {'X': [{'slot_id': '1', 'item_id': ''}]}
        self.assertEqual(chars_became_naked(curr_inv, prev_inv), {'X'})

    def test_stay_naked(self):
        prev_inv = {'X': []}
        curr_inv = {'X': []}
        self.assertEqual(chars_became_naked(curr_inv, prev_inv), set())

    def test_stay_equipped(self):
        prev_inv = {'X': [{'slot_id': '1', 'item_id': '50'}]}
        curr_inv = {'X': [{'slot_id': '1', 'item_id': '99'}]}
        self.assertEqual(chars_became_naked(curr_inv, prev_inv), set())

    def test_naked_to_equipped(self):
        prev_inv = {'X': []}
        curr_inv = {'X': [{'slot_id': '1', 'item_id': '100'}]}
        self.assertEqual(chars_became_naked(curr_inv, prev_inv), set())

    def test_names_filter(self):
        prev_inv = {
            'Watch': [{'slot_id': '1', 'item_id': '1'}],
            'Other': [{'slot_id': '1', 'item_id': '1'}],
        }
        curr_inv = {'Watch': [], 'Other': []}
        self.assertEqual(
            chars_became_naked(curr_inv, prev_inv, names=['Watch']),
            {'Watch'},
        )


class TestGuildStatusWatchlist(unittest.TestCase):
    def test_includes_mules_and_named_alts(self):
        for name in MULE_CHARACTERS:
            self.assertIn(name, GUILD_STATUS_WATCHLIST)
        for name in WALEX_CHARACTERS:
            self.assertIn(name, GUILD_STATUS_WATCHLIST)
        for name in EXTRA_GUILD_WATCH:
            self.assertIn(name, GUILD_STATUS_WATCHLIST)
        self.assertEqual(
            len(GUILD_STATUS_WATCHLIST),
            len(set(GUILD_STATUS_WATCHLIST)),
        )

    def test_html_marks_naked_and_missing(self):
        watchlist = ['Geared', 'NakedNow', 'Gone']
        current_char = {
            'Geared': {'level': 65, 'class': 'Wizard', 'guild': 'Azure Guard'},
            'NakedNow': {'level': 60, 'class': 'Cleric', 'guild': 'Azure Guard'},
        }
        previous_char = dict(current_char)
        current_inv = {
            'Geared': [{'slot_id': '1', 'item_id': '10'}],
            'NakedNow': [],
        }
        previous_inv = {
            'Geared': [{'slot_id': '1', 'item_id': '10'}],
            'NakedNow': [{'slot_id': '1', 'item_id': '20'}],
        }
        html, status = generate_guild_status_html(
            watchlist,
            current_char,
            previous_char,
            current_inv,
            previous_inv,
            magelo_update_date='test',
            has_previous=True,
        )
        self.assertIn('status-equipped', html)
        self.assertIn('status-naked', html)
        self.assertIn('status-missing', html)
        self.assertIn('Became naked today', html)
        self.assertIn('Alert:', html)
        self.assertIn('NakedNow', html)
        self.assertNotIn('delta.html', html)
        self.assertEqual(status['currently_naked'], ['NakedNow'])
        self.assertIn('NakedNow', status['became_naked'])

    def test_discord_alert_message_and_skip(self):
        msg = format_discord_naked_alert(
            ['NakedNow'],
            became_naked={'NakedNow'},
            page_url='https://example.test/guild_characters.html',
            magelo_update_date='Sun Nov 1 16:30:26 UTC 2026',
        )
        self.assertIn('Guild naked alert', msg)
        self.assertIn('NakedNow', msg)
        self.assertIn('Became naked since previous dump', msg)
        self.assertIn('https://example.test/guild_characters.html', msg)
        self.assertEqual(format_discord_naked_alert([]), '')
        self.assertFalse(
            notify_discord_if_guild_naked(['NakedNow'], webhook_url='')
        )
        self.assertFalse(
            notify_discord_if_guild_naked([], webhook_url='https://example.invalid/hook')
        )


if __name__ == '__main__':
    unittest.main()
