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

import gzip
import json
import os
import sys
import tempfile
import unittest

_MAGELO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _MAGELO_ROOT not in sys.path:
    sys.path.insert(0, _MAGELO_ROOT)

from delta_storage import (  # noqa: E402
    compare_delta_to_delta,
    daily_json_pair_usable_for_delta_html_json_compare,
    get_date_range_deltas,
    load_baseline_for_date,
)


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


class TestDeltaHtmlJsonComparePredicate(unittest.TestCase):
    """``delta.html`` Step 3 must not JSON-subtract when the prior day file is degenerate."""

    def test_rejects_empty_yesterday_nonempty_today_even_with_baseline(self):
        """Bad prior run: empty char_deltas; compare_delta_to_delta would use baseline as 'yesterday'."""
        baseline = {'Alice': {'level': 60, 'aa_unspent': 0, 'aa_spent': 100, 'hp_max_total': 500}}
        yesterday = {'char_deltas': {}, 'baseline_date': '2026-02-09'}
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
        }
        self.assertFalse(
            daily_json_pair_usable_for_delta_html_json_compare(
                yesterday, today, baseline
            )
        )

    def test_rejects_when_baseline_characters_missing(self):
        yesterday = {
            'char_deltas': {
                'Bob': {
                    'current_level': 65,
                    'previous_level': 65,
                    'current_aa_total': 100,
                    'previous_aa_total': 100,
                    'current_hp': 5000,
                    'previous_hp': 5000,
                    'class': 'Warrior',
                }
            },
        }
        today = dict(yesterday)
        self.assertFalse(
            daily_json_pair_usable_for_delta_html_json_compare(yesterday, today, None)
        )

    def test_accepts_nonempty_yesterday_with_baseline(self):
        row = {
            'current_level': 65,
            'previous_level': 65,
            'current_aa_total': 400,
            'previous_aa_total': 400,
            'current_hp': 8000,
            'previous_hp': 8000,
            'class': 'Wizard',
        }
        baseline = {'Alice': {'level': 60, 'aa_unspent': 0, 'aa_spent': 100, 'hp_max_total': 500}}
        yesterday = {'char_deltas': {'Alice': dict(row)}, 'baseline_date': '2026-02-09'}
        today = {
            'baseline_date': '2026-02-09',
            'char_deltas': {
                'Alice': {
                    **row,
                    'current_aa_total': 404,
                    'previous_aa_total': 400,
                }
            },
        }
        self.assertTrue(
            daily_json_pair_usable_for_delta_html_json_compare(
                yesterday, today, baseline
            )
        )


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

    def test_deleted_on_end_day_aa_change_not_full_wipe(self):
        """End-day is_deleted: diff is slice(end)-slice(start), not -start_aa (Sturm 5/14->5/15)."""
        baseline_chars = {
            'Sturm': {
                'level': 65,
                'aa_unspent': 0,
                'aa_spent': 512,
                'hp_max_total': 5676,
                'class': 'Ranger',
            }
        }
        day_a = {
            'baseline_date': '2026-02-09',
            'char_deltas': {
                'Sturm': {
                    'current_level': 65,
                    'current_aa_total': 600,
                    'current_hp': 5766,
                    'class': 'Ranger',
                    'is_deleted': False,
                }
            },
            'inv_deltas': {},
        }
        day_b = {
            'baseline_date': '2026-02-09',
            'char_deltas': {
                'Sturm': {
                    'current_level': 65,
                    'current_aa_total': 512,
                    'current_hp': 5676,
                    'class': 'Ranger',
                    'is_deleted': True,
                }
            },
            'inv_deltas': {},
        }
        out = compare_delta_to_delta(day_a, day_b, baseline_chars)
        sturm = out['char_deltas']['Sturm']
        self.assertEqual(sturm['aa_total_change'], -88)
        self.assertTrue(sturm['is_deleted'])


def _write_json_gz(path, obj):
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        json.dump(obj, f)


class TestGetDateRangeDeltas(unittest.TestCase):
    """``get_date_range_deltas`` date order and cross-baseline inventory."""

    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.snap = os.path.join(self._td.name, 'delta_snapshots')
        os.makedirs(self.snap, exist_ok=True)

    def tearDown(self):
        self._td.cleanup()

    def test_reversed_calendar_dates_normalized(self):
        bd = '2026-02-09'
        alice_bl = {
            'level': 60,
            'aa_unspent': 0,
            'aa_spent': 100,
            'hp_max_total': 500,
            'class': 'Wizard',
        }
        _write_json_gz(
            os.path.join(self.snap, f'baseline_master_{bd}.json.gz'),
            {'baseline_date': bd, 'characters': {'Alice': alice_bl}, 'inventories': {}},
        )
        d1 = {
            'date': '2026-05-01',
            'baseline_date': bd,
            'char_deltas': {
                'Alice': {
                    'current_level': 60,
                    'previous_level': 60,
                    'current_aa_total': 100,
                    'previous_aa_total': 100,
                    'current_hp': 500,
                    'previous_hp': 500,
                    'class': 'Wizard',
                }
            },
            'inv_deltas': {},
        }
        d2 = {
            'date': '2026-05-02',
            'baseline_date': bd,
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
        _write_json_gz(os.path.join(self.snap, 'delta_daily_2026-05-01.json.gz'), d1)
        _write_json_gz(os.path.join(self.snap, 'delta_daily_2026-05-02.json.gz'), d2)

        forward = get_date_range_deltas('2026-05-01', '2026-05-02', self.snap)
        backward = get_date_range_deltas('2026-05-02', '2026-05-01', self.snap)
        self.assertEqual(forward['start_date'], backward['start_date'])
        self.assertEqual(forward['end_date'], backward['end_date'])
        self.assertEqual(
            forward['char_deltas']['Alice']['level_change'],
            backward['char_deltas']['Alice']['level_change'],
        )
        self.assertEqual(forward['char_deltas']['Alice']['level_change'], 1)

    def test_cross_baseline_inventory_uses_reconstruction(self):
        b1 = '2026-01-01'
        b2 = '2026-06-01'
        _write_json_gz(
            os.path.join(self.snap, f'baseline_master_{b1}.json.gz'),
            {
                'baseline_date': b1,
                'characters': {},
                'inventories': {'X': [{'item_id': '1', 'item_name': 'Gem'}]},
            },
        )
        _write_json_gz(
            os.path.join(self.snap, f'baseline_master_{b2}.json.gz'),
            {
                'baseline_date': b2,
                'characters': {},
                'inventories': {
                    'X': [
                        {'item_id': '1', 'item_name': 'Gem'},
                        {'item_id': '1', 'item_name': 'Gem'},
                        {'item_id': '1', 'item_name': 'Gem'},
                    ]
                },
            },
        )
        day_a = {
            'date': '2026-05-01',
            'baseline_date': b1,
            'char_deltas': {},
            'inv_deltas': {
                'X': {'added': {'1': 2}, 'removed': {}, 'item_names': {'1': 'Gem'}},
            },
        }
        day_b = {
            'date': '2026-06-01',
            'baseline_date': b2,
            'char_deltas': {},
            'inv_deltas': {},
        }
        _write_json_gz(os.path.join(self.snap, 'delta_daily_2026-05-01.json.gz'), day_a)
        _write_json_gz(os.path.join(self.snap, 'delta_daily_2026-06-01.json.gz'), day_b)

        out = get_date_range_deltas('2026-05-01', '2026-06-01', self.snap)
        self.assertEqual(out['start_date'], '2026-05-01')
        self.assertEqual(out['end_date'], '2026-06-01')
        self.assertNotIn('X', out.get('inv_deltas') or {})

    def test_load_baseline_for_date_prefers_archive_over_mismatched_master(self):
        b_old = '2026-01-01'
        _write_json_gz(
            os.path.join(self.snap, f'baseline_master_{b_old}.json.gz'),
            {'baseline_date': b_old, 'characters': {'Z': {'level': 1}}, 'inventories': {}},
        )
        _write_json_gz(
            os.path.join(self.snap, 'baseline_master.json.gz'),
            {'baseline_date': '2026-06-01', 'characters': {'Z': {'level': 99}}, 'inventories': {}},
        )
        bl = load_baseline_for_date(b_old, self.snap)
        self.assertEqual(bl['baseline_date'], b_old)
        self.assertEqual(bl['characters']['Z']['level'], 1)


    def test_load_baseline_for_date_returns_none_when_no_archive_and_master_mismatched(self):
        b_old = '2026-02-09'
        _write_json_gz(
            os.path.join(self.snap, 'baseline_master.json.gz'),
            {'baseline_date': '2026-05-12', 'characters': {}, 'inventories': {}},
        )
        self.assertIsNone(load_baseline_for_date(b_old, self.snap))

    def test_get_date_range_deltas_raises_when_cross_baseline_missing_archive(self):
        b1 = '2026-01-01'
        b2 = '2026-06-01'
        _write_json_gz(
            os.path.join(self.snap, 'baseline_master.json.gz'),
            {'baseline_date': b2, 'characters': {}, 'inventories': {}},
        )
        _write_json_gz(
            os.path.join(self.snap, 'delta_daily_2026-05-01.json.gz'),
            {'date': '2026-05-01', 'baseline_date': b1, 'char_deltas': {}, 'inv_deltas': {}},
        )
        _write_json_gz(
            os.path.join(self.snap, 'delta_daily_2026-06-01.json.gz'),
            {'date': '2026-06-01', 'baseline_date': b2, 'char_deltas': {}, 'inv_deltas': {}},
        )
        with self.assertRaises(ValueError) as ctx:
            get_date_range_deltas('2026-05-01', '2026-06-01', self.snap)
        self.assertIn('Missing baseline snapshot', str(ctx.exception))
        self.assertIn(b1, str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
