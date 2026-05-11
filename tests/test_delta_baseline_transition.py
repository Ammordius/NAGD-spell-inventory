"""Quarterly baseline reset: cumulative daily JSONs become incompatible.

After reset, ``delta_daily_*.json`` omits characters with zero diff vs the new
baseline. ``compare_delta_to_delta`` without a baseline still cannot reconstruct
cross-baseline slices (missing side defaults to zeros).

``generate_spell_page.py`` Step 3 compares ``baseline_date`` on both JSONs; when
they differ, it uses previous vs current Magelo files instead (see that branch).

When both JSONs share the same baseline, ``compare_delta_to_delta`` should receive
``baseline_characters`` so omitted keys mean \"unchanged from baseline\" at that day,
not numeric zero (which inflated day-over-day to a full quarter of gains).
"""

import os
import sys
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from delta_storage import compare_delta_to_delta  # noqa: E402


class TestCompareDeltaToDeltaBaselinePitfall(unittest.TestCase):
    def test_cross_baseline_without_master_still_degenerate(self):
        """Different baseline_date + no master baseline: missing side cannot be inferred."""
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


class TestCompareDeltaToDeltaBaselineFill(unittest.TestCase):
    def test_omitted_yesterday_row_resolves_from_baseline(self):
        """Daily JSON omits chars unchanged from baseline; diff vs today must be one day."""
        baseline_chars = {
            'Alice': {
                'level': 60,
                'aa_unspent': 0,
                'aa_spent': 100,
                'hp_max_total': 500,
                'class': 'Wizard',
            }
        }
        yesterday = {'char_deltas': {}, 'inv_deltas': {}, 'baseline_date': '2026-02-09'}
        today = {
            'baseline_date': '2026-02-09',
            'char_deltas': {
                'Alice': {
                    'current_level': 61,
                    'previous_level': 60,
                    'current_aa_total': 102,
                    'previous_aa_total': 100,
                    'current_hp': 510,
                    'previous_hp': 500,
                    'class': 'Wizard',
                }
            },
            'inv_deltas': {},
        }
        out = compare_delta_to_delta(yesterday, today, baseline_chars)
        alice = out['char_deltas']['Alice']
        self.assertEqual(alice['level_change'], 1)
        self.assertEqual(alice['aa_total_change'], 2)
        self.assertEqual(alice['hp_change'], 10)


if __name__ == '__main__':
    unittest.main()
