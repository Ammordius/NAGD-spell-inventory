"""Quarterly baseline reset: cumulative daily JSONs become incompatible.

After reset, ``delta_daily_*.json`` omits characters with zero diff vs the new
baseline. ``compare_delta_to_delta(yesterday, today)`` then treats missing keys
as zeros — bogus level/AA drops and mass false \"visibility\" flags.

``generate_spell_page.py`` Step 3 compares ``baseline_date`` on both JSONs; when
they differ, it uses previous vs current Magelo files instead (see that branch).
"""

import os
import sys
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from delta_storage import compare_delta_to_delta  # noqa: E402


class TestCompareDeltaToDeltaBaselinePitfall(unittest.TestCase):
    def test_sparse_today_delta_reads_missing_chars_as_zero(self):
        """Mirrors post-reset JSON: yesterday cumulative vs old baseline; today sparse."""
        yesterday = {
            'baseline_date': '2026-02-09',
            'char_deltas': {
                'Alice': {
                    'current_level': 65,
                    'previous_level': 65,
                    'current_aa_total': 4000,
                    'previous_aa_total': 4000,
                    'current_hp': 8000,
                    'previous_hp': 8000,
                    'class': 'Wizard',
                }
            },
            'inv_deltas': {},
        }
        today = {
            'baseline_date': '2026-05-10',
            'char_deltas': {},
            'inv_deltas': {},
        }
        out = compare_delta_to_delta(yesterday, today, None)
        alice = out['char_deltas'].get('Alice')
        self.assertIsNotNone(alice)
        self.assertEqual(alice['current_level'], 0)
        self.assertEqual(alice['previous_level'], 65)


if __name__ == '__main__':
    unittest.main()
