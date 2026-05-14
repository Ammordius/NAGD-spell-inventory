#!/usr/bin/env python3
"""
Module for storing and retrieving delta snapshots for weekly/monthly tracking.
Stores minimal differences instead of full files to save space.
"""

import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

def get_week_start(date_str):
    """Get the Monday of the week for a given date (YYYY-MM-DD)."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    # Get Monday of the week (weekday 0 = Monday)
    days_since_monday = dt.weekday()
    monday = dt - timedelta(days=days_since_monday)
    return monday.strftime('%Y-%m-%d')

def get_month_start(date_str):
    """Get the first day of the month for a given date (YYYY-MM-DD)."""
    dt = datetime.strptime(date_str, '%Y-%m-%d')
    return dt.replace(day=1).strftime('%Y-%m-%d')

def save_baseline_json(char_data, baseline_type, date_str, base_dir='delta_snapshots'):
    """Save a minimal JSON baseline containing only essential character data.
    
    Args:
        char_data: Dict of character data from parse_character_data
        baseline_type: 'weekly' or 'monthly'
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for baselines
    
    Returns:
        Path to saved baseline file
    """
    os.makedirs(base_dir, exist_ok=True)
    
    # Calculate week/month start
    if baseline_type == 'weekly':
        period_start = get_week_start(date_str)
        filename = f"baseline_week_{period_start}.json"
    elif baseline_type == 'monthly':
        period_start = get_month_start(date_str)
        filename = f"baseline_month_{period_start}.json"
    else:
        raise ValueError(f"Invalid baseline_type: {baseline_type}")
    
    filepath = os.path.join(base_dir, filename)
    
    # Extract only essential data for comparisons (much smaller than full text file)
    baseline_data = {}
    for char_name, data in char_data.items():
        baseline_data[char_name] = {
            'level': data.get('level', 0),
            'aa_unspent': data.get('aa_unspent', 0),
            'aa_spent': data.get('aa_spent', 0),
            'hp_max_total': data.get('hp_max_total', 0),
            'class': data.get('class', '')
        }
    
    baseline_json = {
        'period_start': period_start,
        'baseline_type': baseline_type,
        'date_saved': date_str,
        'timestamp': datetime.now().isoformat(),
        'characters': baseline_data
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(baseline_json, f, indent=2)
    
    return filepath

def load_baseline_json(baseline_type, date_str, base_dir='delta_snapshots'):
    """Load a JSON baseline.
    
    Args:
        baseline_type: 'weekly' or 'monthly'
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for baselines
    
    Returns:
        Dict with baseline character data or None if not found
    """
    if baseline_type == 'weekly':
        period_start = get_week_start(date_str)
        filename = f"baseline_week_{period_start}.json"
    elif baseline_type == 'monthly':
        period_start = get_month_start(date_str)
        filename = f"baseline_month_{period_start}.json"
    else:
        raise ValueError(f"Invalid baseline_type: {baseline_type}")
    
    filepath = os.path.join(base_dir, filename)
    
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        baseline_json = json.load(f)
    
    return baseline_json.get('characters', {})

def save_delta_snapshot(delta_data, snapshot_type, date_str, base_dir='delta_snapshots'):
    """Save a minimal delta snapshot (only changes).
    
    Args:
        delta_data: Dict with 'char_deltas' and 'inv_deltas'
        snapshot_type: 'weekly' or 'monthly'
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for snapshots
    """
    os.makedirs(base_dir, exist_ok=True)
    
    # Create filename based on type and date
    if snapshot_type == 'weekly':
        week_start = get_week_start(date_str)
        filename = f"delta_week_{week_start}.json"
    elif snapshot_type == 'monthly':
        month_start = get_month_start(date_str)
        filename = f"delta_month_{month_start}.json"
    else:
        raise ValueError(f"Invalid snapshot_type: {snapshot_type}")
    
    filepath = os.path.join(base_dir, filename)
    
    # Save minimal delta data (only characters with changes)
    snapshot = {
        'date': date_str,
        'snapshot_type': snapshot_type,
        'char_deltas': delta_data.get('char_deltas', {}),
        'inv_deltas': delta_data.get('inv_deltas', {}),
        'timestamp': datetime.now().isoformat()
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(snapshot, f, indent=2)
    
    return filepath

def load_delta_snapshot(snapshot_type, date_str, base_dir='delta_snapshots'):
    """Load a delta snapshot.
    
    Args:
        snapshot_type: 'weekly' or 'monthly'
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for snapshots
    
    Returns:
        Dict with snapshot data or None if not found
    """
    if snapshot_type == 'weekly':
        week_start = get_week_start(date_str)
        filename = f"delta_week_{week_start}.json"
    elif snapshot_type == 'monthly':
        month_start = get_month_start(date_str)
        filename = f"delta_month_{month_start}.json"
    else:
        raise ValueError(f"Invalid snapshot_type: {snapshot_type}")
    
    filepath = os.path.join(base_dir, filename)
    
    if not os.path.exists(filepath):
        return None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def accumulate_weekly_deltas(week_start_date, current_char_data, base_dir='delta_snapshots', end_date=None):
    """Accumulate all deltas for a week to get weekly totals.
    When end_date is provided and both daily deltas exist, uses historical delta JSONs (same as delta-history).
    Otherwise compares current data against weekly baseline.
    
    Args:
        week_start_date: Week start date (YYYY-MM-DD, Monday)
        current_char_data: Current character data dict
        base_dir: Base directory for snapshots and baselines
        end_date: Optional end date (YYYY-MM-DD); if set and deltas exist, use date-range from daily JSONs
    
    Returns:
        Dict with accumulated AA/HP gains per character
    """
    weekly_totals = defaultdict(lambda: {
        'aa_gain': 0,
        'hp_gain': 0,
        'class': '',
        'level': 0
    })
    
    # Prefer historical daily deltas when end_date given (same data as delta-history)
    if end_date and end_date >= week_start_date:
        range_totals = get_leaderboard_totals_from_date_range(week_start_date, end_date, base_dir)
        if range_totals is not None:
            return dict(range_totals)
    
    # Try to load weekly baseline JSON (much smaller than text file)
    baseline_data = load_baseline_json('weekly', week_start_date, base_dir)
    
    if not baseline_data:
        # Fall back to old text file format if JSON doesn't exist (backward compatibility)
        baseline_file = os.path.join(base_dir, '..', 'character', f'baseline_week_{week_start_date}.txt')
        if os.path.exists(baseline_file):
            from generate_spell_page import parse_character_data
            baseline_data = parse_character_data(baseline_file, None)
        else:
            # Fall back to snapshot if baseline doesn't exist
            snapshot = load_delta_snapshot('weekly', week_start_date, base_dir)
            if snapshot:
                char_deltas = snapshot.get('char_deltas', {})
                for char_name, delta in char_deltas.items():
                    if delta.get('is_deleted', False) or delta.get('is_new', False):
                        continue
                    weekly_totals[char_name]['aa_gain'] += delta.get('aa_total_change', 0)
                    weekly_totals[char_name]['hp_gain'] += delta.get('hp_change', 0)
                    weekly_totals[char_name]['class'] = delta.get('class', '')
                    weekly_totals[char_name]['level'] = delta.get('current_level', 0)
            return weekly_totals
    
    for char_name, current in current_char_data.items():
        baseline = baseline_data.get(char_name, {})
        if not baseline:
            continue
        
        current_aa = current.get('aa_unspent', 0) + current.get('aa_spent', 0)
        baseline_aa = baseline.get('aa_unspent', 0) + baseline.get('aa_spent', 0)
        current_hp = current.get('hp_max_total', 0)
        baseline_hp = baseline.get('hp_max_total', 0)
        
        aa_gain = current_aa - baseline_aa
        hp_gain = current_hp - baseline_hp
        
        if aa_gain > 0 or hp_gain > 0:
            weekly_totals[char_name] = {
                'aa_gain': aa_gain,
                'hp_gain': hp_gain,
                'class': current.get('class', ''),
                'level': current.get('level', 0)
            }
    
    return weekly_totals

def accumulate_monthly_deltas(month_start_date, current_char_data, base_dir='delta_snapshots', end_date=None):
    """Accumulate all deltas for a month to get monthly totals.
    When end_date is provided and both daily deltas exist, uses historical delta JSONs (same as delta-history).
    Otherwise compares current data against monthly baseline.
    
    Args:
        month_start_date: Month start date (YYYY-MM-DD)
        current_char_data: Current character data dict
        base_dir: Base directory for snapshots and baselines
        end_date: Optional end date (YYYY-MM-DD); if set and deltas exist, use date-range from daily JSONs
    
    Returns:
        Dict with accumulated AA/HP gains per character
    """
    monthly_totals = defaultdict(lambda: {
        'aa_gain': 0,
        'hp_gain': 0,
        'class': '',
        'level': 0
    })
    
    # Prefer historical daily deltas when end_date given (same data as delta-history)
    if end_date and end_date >= month_start_date:
        range_totals = get_leaderboard_totals_from_date_range(month_start_date, end_date, base_dir)
        if range_totals is not None:
            return dict(range_totals)
    
    # Try to load monthly baseline JSON (much smaller than text file)
    baseline_data = load_baseline_json('monthly', month_start_date, base_dir)
    
    if not baseline_data:
        # Fall back to old text file format if JSON doesn't exist (backward compatibility)
        baseline_file = os.path.join(base_dir, '..', 'character', f'baseline_month_{month_start_date}.txt')
        if not os.path.exists(baseline_file):
            baseline_file = os.path.join('character', f'baseline_month_{month_start_date}.txt')
        if os.path.exists(baseline_file):
            from generate_spell_page import parse_character_data
            baseline_data = parse_character_data(baseline_file, None)
        else:
            # Fall back to snapshot if baseline doesn't exist
            snapshot = load_delta_snapshot('monthly', month_start_date, base_dir)
            if snapshot:
                char_deltas = snapshot.get('char_deltas', {})
                for char_name, delta in char_deltas.items():
                    if delta.get('is_deleted', False) or delta.get('is_new', False):
                        continue
                    monthly_totals[char_name]['aa_gain'] += delta.get('aa_total_change', 0)
                    monthly_totals[char_name]['hp_gain'] += delta.get('hp_change', 0)
                    monthly_totals[char_name]['class'] = delta.get('class', '')
                    monthly_totals[char_name]['level'] = delta.get('current_level', 0)
            return monthly_totals
    
    for char_name, current in current_char_data.items():
        baseline = baseline_data.get(char_name, {})
        if not baseline:
            continue
        
        current_aa = current.get('aa_unspent', 0) + current.get('aa_spent', 0)
        baseline_aa = baseline.get('aa_unspent', 0) + baseline.get('aa_spent', 0)
        current_hp = current.get('hp_max_total', 0)
        baseline_hp = baseline.get('hp_max_total', 0)
        
        aa_gain = current_aa - baseline_aa
        hp_gain = current_hp - baseline_hp
        
        if aa_gain > 0 or hp_gain > 0:
            monthly_totals[char_name] = {
                'aa_gain': aa_gain,
                'hp_gain': hp_gain,
                'class': current.get('class', ''),
                'level': current.get('level', 0)
            }
    
    return monthly_totals

def get_weekly_leaderboard(week_start_date, stat_type='aa', top_n=20, base_dir='delta_snapshots', current_char_data=None, end_date=None):
    """Get weekly leaderboard for AA or HP gains.
    Uses historical daily delta JSONs when end_date is provided and both deltas exist (same as delta-history).
    
    Args:
        week_start_date: Week start date (YYYY-MM-DD)
        stat_type: 'aa' or 'hp'
        top_n: Number of top entries to return
        base_dir: Base directory for snapshots
        current_char_data: Current character data (required for baseline fallback)
        end_date: End date for period (e.g. today); when set, uses daily delta JSONs if available
    
    Returns:
        List of dicts with leaderboard entries
    """
    if current_char_data is None and not end_date:
        return []
    totals = accumulate_weekly_deltas(week_start_date, current_char_data or {}, base_dir, end_date=end_date)
    
    leaderboard = []
    for char_name, data in totals.items():
        if stat_type == 'aa':
            gain = data['aa_gain']
            # Only include if level 50+ and gained AA
            if data['level'] >= 50 and gain > 0:
                leaderboard.append({
                    'name': char_name,
                    'class': data['class'],
                    'level': data['level'],
                    'gain': gain
                })
        elif stat_type == 'hp':
            gain = data['hp_gain']
            # Include if gained HP
            if gain > 0:
                leaderboard.append({
                    'name': char_name,
                    'class': data['class'],
                    'level': data['level'],
                    'gain': gain
                })
    
    # Sort by gain (descending) and return top N
    leaderboard.sort(key=lambda x: x['gain'], reverse=True)
    return leaderboard[:top_n]

def get_monthly_leaderboard(month_start_date, stat_type='aa', top_n=20, base_dir='delta_snapshots', current_char_data=None, end_date=None):
    """Get monthly leaderboard for AA or HP gains.
    Uses historical daily delta JSONs when end_date is provided and both deltas exist (same as delta-history).
    
    Args:
        month_start_date: Month start date (YYYY-MM-DD)
        stat_type: 'aa' or 'hp'
        top_n: Number of top entries to return
        base_dir: Base directory for snapshots
        current_char_data: Current character data (required for baseline fallback)
        end_date: End date for period (e.g. today); when set, uses daily delta JSONs if available
    
    Returns:
        List of dicts with leaderboard entries
    """
    if current_char_data is None and not end_date:
        return []
    totals = accumulate_monthly_deltas(month_start_date, current_char_data or {}, base_dir, end_date=end_date)
    
    leaderboard = []
    for char_name, data in totals.items():
        if stat_type == 'aa':
            gain = data['aa_gain']
            # Only include if level 50+ and gained AA
            if data['level'] >= 50 and gain > 0:
                leaderboard.append({
                    'name': char_name,
                    'class': data['class'],
                    'level': data['level'],
                    'gain': gain
                })
        elif stat_type == 'hp':
            gain = data['hp_gain']
            # Include if gained HP
            if gain > 0:
                leaderboard.append({
                    'name': char_name,
                    'class': data['class'],
                    'level': data['level'],
                    'gain': gain
                })
    
    # Sort by gain (descending) and return top N
    leaderboard.sort(key=lambda x: x['gain'], reverse=True)
    return leaderboard[:top_n]

def save_master_baseline(char_data, inv_data, date_str, base_dir='delta_snapshots'):
    """Save a master baseline containing full character and inventory data.

    This is the reference point that all daily deltas are compared against.
    Writes ``baseline_master.json.gz`` (compressed, required for GitHub size limits).
    Uncompressed ``baseline_master.json`` is only written when env
    ``MAGELO_WRITE_BASELINE_UNCOMPRESSED`` is 1/true/yes (local debugging); otherwise an
    existing uncompressed file is removed to avoid huge Pages artifacts.

    Args:
        char_data: Dict of character data from parse_character_data
        inv_data: Dict of inventory data from parse_inventory_file
        date_str: Date string (YYYY-MM-DD) when baseline was created
        base_dir: Base directory for baselines

    Returns:
        Path to saved baseline file (compressed)
    """
    os.makedirs(base_dir, exist_ok=True)
    
    filename = "baseline_master.json"
    filepath = os.path.join(base_dir, filename)
    compressed_filepath = filepath + '.gz'
    
    # Save full baseline data
    baseline_json = {
        'baseline_date': date_str,
        'timestamp': datetime.now().isoformat(),
        'characters': char_data,
        'inventories': inv_data
    }
    
    # Save as compressed JSON (required for GitHub's 100 MB limit)
    # Note: Baseline is generated on-the-fly and cached, not committed to repo
    import gzip
    with gzip.open(compressed_filepath, 'wt', encoding='utf-8') as f:
        json.dump(baseline_json, f, indent=2)

    # Uncompressed master is ~200MB+ and bloats Pages artifacts; opt-in for local debugging only.
    write_uncompressed = os.environ.get(
        "MAGELO_WRITE_BASELINE_UNCOMPRESSED", ""
    ).strip().lower() in ("1", "true", "yes")
    if write_uncompressed:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(baseline_json, f, indent=2)
    elif os.path.isfile(filepath):
        try:
            os.remove(filepath)
        except OSError:
            pass

    print(f"  Baseline saved (compressed: {os.path.getsize(compressed_filepath) / 1024 / 1024:.2f} MB)")
    return compressed_filepath

def load_master_baseline(base_dir='delta_snapshots'):
    """Load the master baseline (supports both compressed .gz and uncompressed).
    
    Args:
        base_dir: Base directory for baselines
    
    Returns:
        Dict with baseline data (characters and inventories) or None if not found
    """
    import gzip
    
    # Try compressed first (preferred, required for GitHub)
    compressed_filepath = os.path.join(base_dir, "baseline_master.json.gz")
    if os.path.exists(compressed_filepath):
        with gzip.open(compressed_filepath, 'rt', encoding='utf-8') as f:
            baseline = json.load(f)
        return {
            'characters': baseline.get('characters', {}),
            'inventories': baseline.get('inventories', {}),
            'baseline_date': baseline.get('baseline_date', 'Unknown')
        }
    
    # Fall back to uncompressed (for backward compatibility)
    filepath = os.path.join(base_dir, "baseline_master.json")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            baseline = json.load(f)
        return {
            'characters': baseline.get('characters', {}),
            'inventories': baseline.get('inventories', {}),
            'baseline_date': baseline.get('baseline_date', 'Unknown')
        }
    
    return None


def load_baseline_for_date(baseline_date, base_dir='delta_snapshots'):
    """Load the master baseline snapshot for a given ``baseline_date`` string.

    Prefer ``baseline_master_<baseline_date>.json.gz`` (written on rotation). If missing,
    use ``baseline_master.json.gz`` only when its embedded ``baseline_date`` matches
    (avoids using a post-rotation master for old daily JSONs).
    """
    import gzip

    if not baseline_date or baseline_date == 'Unknown':
        return load_master_baseline(base_dir)

    archive = os.path.join(base_dir, f'baseline_master_{baseline_date}.json.gz')
    if os.path.isfile(archive):
        with gzip.open(archive, 'rt', encoding='utf-8') as f:
            baseline = json.load(f)
        return {
            'characters': baseline.get('characters', {}),
            'inventories': baseline.get('inventories', {}),
            'baseline_date': baseline.get('baseline_date', baseline_date),
        }

    master = load_master_baseline(base_dir)
    if master and str(master.get('baseline_date')) == str(baseline_date):
        return master
    return None


def build_daily_delta_data_quality(date_str, baseline_date):
    """Sanity flags embedded in each daily delta JSON for CI and manual review.

    ``dump_before_baseline`` is True when the dump ``date`` is strictly before ``baseline_date``.
    That usually means the wrong ``baseline_master_<era>.json.gz`` was copied when regenerating
    (see ``verify_delta_baseline_archives`` and docs/DELTA_BASELINE_HANDOFF_2026-05.md).

    Note: per-character ``aa_total_change`` in ``char_deltas`` is **cumulative vs baseline**, not
    a one-day gain, so large values are not flagged here.
    """
    dq = {'dump_before_baseline': False}
    bd = str(baseline_date or '')
    if bd and date_str and date_str < bd:
        dq['dump_before_baseline'] = True
    return dq


def should_reset_baseline(baseline_date, current_date, reset_interval_days=90):
    """Check if baseline should be reset (e.g., quarterly).
    
    Args:
        baseline_date: Baseline date string (YYYY-MM-DD)
        current_date: Current date string (YYYY-MM-DD)
        reset_interval_days: Days before resetting baseline (default 90 = quarterly/3 months)
    
    Returns:
        True if baseline should be reset
    """
    baseline_dt = datetime.strptime(baseline_date, '%Y-%m-%d')
    current_dt = datetime.strptime(current_date, '%Y-%m-%d')
    days_since_baseline = (current_dt - baseline_dt).days
    return days_since_baseline >= reset_interval_days

def save_daily_delta_from_baseline(current_char_data, current_inv_data, date_str, base_dir='delta_snapshots', auto_reset_baseline=True):
    """Save a daily delta JSON file containing changes from baseline to current day.
    This is much smaller than keeping full character/inventory files.
    
    Optionally resets baseline periodically to keep delta file sizes reasonable.
    
    Args:
        current_char_data: Current character data dict
        current_inv_data: Current inventory data dict
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for daily deltas
        auto_reset_baseline: If True, reset baseline if it's been >365 days (yearly reset)
    
    Returns:
        Path to saved daily delta file
    """
    os.makedirs(base_dir, exist_ok=True)
    
    # Load baseline
    baseline = load_master_baseline(base_dir)
    
    # Check if we should reset baseline (quarterly reset to keep file sizes reasonable)
    if baseline and auto_reset_baseline:
        if should_reset_baseline(baseline['baseline_date'], date_str, reset_interval_days=90):
            print(f"[INFO] Baseline is >3 months old ({baseline['baseline_date']}), resetting to current date...")
            # Archive old baseline (save as compressed .json.gz)
            import shutil
            import gzip
            old_baseline_file = os.path.join(base_dir, f"baseline_master_{baseline['baseline_date']}.json.gz")
            current_baseline_file = os.path.join(base_dir, "baseline_master.json.gz")
            # Copy compressed baseline if it exists, otherwise compress the uncompressed one
            if os.path.exists(current_baseline_file):
                shutil.copy2(current_baseline_file, old_baseline_file)
            else:
                # Load uncompressed baseline and save as compressed
                uncompressed_file = os.path.join(base_dir, "baseline_master.json")
                if os.path.exists(uncompressed_file):
                    with open(uncompressed_file, 'r', encoding='utf-8') as f_in:
                        baseline_data = json.load(f_in)
                    with gzip.open(old_baseline_file, 'wt', encoding='utf-8') as f_out:
                        json.dump(baseline_data, f_out, indent=2)
            print(f"  Archived old baseline to: {os.path.basename(old_baseline_file)}")
            
            # Create new baseline from current data
            save_master_baseline(current_char_data, current_inv_data, date_str, base_dir)
            baseline = load_master_baseline(base_dir)
            print(f"  Created new baseline: {date_str}")
    
    if not baseline:
        raise ValueError("Master baseline not found. Cannot create daily delta without baseline.")
    
    baseline_char_data = baseline['characters']
    baseline_inv_data = baseline['inventories']
    
    # Calculate deltas from baseline
    from generate_spell_page import (
        compare_character_data,
        compare_inventories,
        chars_corpse_loot_excluded,
        equipped_worn_by_char_from_inventories,
    )
    char_deltas = compare_character_data(current_char_data, baseline_char_data, None)
    inv_deltas = compare_inventories(current_inv_data, baseline_inv_data, None)
    # Exclude corpse-loot chars (0 equipped -> any equipped) so delta-history and other consumers don't see them
    corpse_loot_chars = chars_corpse_loot_excluded(current_inv_data, baseline_inv_data)
    for char_name in corpse_loot_chars:
        char_deltas.pop(char_name, None)
        inv_deltas.pop(char_name, None)
    
    # Get item names for inventory deltas
    all_item_ids = set()
    for char_delta in inv_deltas.values():
        all_item_ids.update(char_delta['added'].keys())
        all_item_ids.update(char_delta['removed'].keys())
    
    item_names = {}
    for char_name, items in current_inv_data.items():
        for item in items:
            if item['item_id'] in all_item_ids:
                item_names[item['item_id']] = item['item_name']
    
    # Populate item names in deltas
    for char_delta in inv_deltas.values():
        for item_id in char_delta['added']:
            if item_id in item_names:
                char_delta['item_names'][item_id] = item_names[item_id]
        for item_id in char_delta['removed']:
            if item_id in item_names:
                char_delta['item_names'][item_id] = item_names[item_id]
    
    filename = f"delta_daily_{date_str}.json"
    filepath = os.path.join(base_dir, filename)
    
    # Per-character worn slot counts (real item_id in slots 1-22) for historical corpse-loot parity
    equipped_worn_by_char = equipped_worn_by_char_from_inventories(current_char_data, current_inv_data)

    data_quality = build_daily_delta_data_quality(date_str, baseline.get('baseline_date'))
    if data_quality.get('dump_before_baseline'):
        print(
            f"[WARN] data_quality.dump_before_baseline: date {date_str} < baseline_date "
            f"{baseline.get('baseline_date')} — wrong-era baseline_master when generating this file; "
            f"see docs/DELTA_BASELINE_HANDOFF_2026-05.md and regenerate-delta-days baseline_era_date."
        )

    # Save delta data (changes from baseline)
    daily_delta = {
        'date': date_str,
        'delta_type': 'daily_from_baseline',
        'baseline_date': baseline['baseline_date'],
        'char_deltas': char_deltas,
        'inv_deltas': inv_deltas,
        'equipped_worn_by_char': equipped_worn_by_char,
        'data_quality': data_quality,
        'timestamp': datetime.now().isoformat()
    }
    
    # Save as compressed JSON (gzip) to reduce storage by ~80%
    import gzip
    compressed_filepath = filepath + '.gz'
    with gzip.open(compressed_filepath, 'wt', encoding='utf-8') as f:
        json.dump(daily_delta, f, indent=2)
    
    # Also save uncompressed for easier debugging (optional - can remove later)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(daily_delta, f, indent=2)
    
    return compressed_filepath

def save_daily_delta_json(delta_data, date_str, base_dir='delta_snapshots'):
    """Save a daily delta JSON file containing only the changes.
    DEPRECATED: Use save_daily_delta_from_baseline instead.
    Kept for backward compatibility.
    """
    os.makedirs(base_dir, exist_ok=True)
    
    filename = f"delta_daily_{date_str}.json"
    filepath = os.path.join(base_dir, filename)
    
    # Save minimal delta data (only characters with changes)
    daily_delta = {
        'date': date_str,
        'delta_type': 'daily',
        'char_deltas': delta_data.get('char_deltas', {}),
        'inv_deltas': delta_data.get('inv_deltas', {}),
        'timestamp': datetime.now().isoformat()
    }
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(daily_delta, f, indent=2)
    
    return filepath

def load_daily_delta_json(date_str, base_dir='delta_snapshots'):
    """Load a daily delta JSON file (supports both compressed .gz and uncompressed).
    
    Args:
        date_str: Date string (YYYY-MM-DD)
        base_dir: Base directory for daily deltas
    
    Returns:
        Dict with daily delta data or None if not found
    """
    import gzip
    
    # Try compressed first (preferred)
    compressed_filepath = os.path.join(base_dir, f"delta_daily_{date_str}.json.gz")
    if os.path.exists(compressed_filepath):
        with gzip.open(compressed_filepath, 'rt', encoding='utf-8') as f:
            return json.load(f)
    
    # Fall back to uncompressed (for backward compatibility)
    filepath = os.path.join(base_dir, f"delta_daily_{date_str}.json")
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    return None


def _corpse_loot_chars_from_equipped_meta(delta_prev, delta_curr):
    """Names with 0 real worn items at prev snapshot and >=1 at curr; only if both have numeric counts."""
    meta_p = delta_prev.get('equipped_worn_by_char') or {}
    meta_c = delta_curr.get('equipped_worn_by_char') or {}
    if not meta_p or not meta_c:
        return set()
    out = set()
    for name in set(meta_p.keys()) & set(meta_c.keys()):
        cp = meta_p.get(name) or {}
        cc = meta_c.get(name) or {}
        a_count, b_count = cp.get('count'), cc.get('count')
        if isinstance(a_count, int) and isinstance(b_count, int) and a_count == 0 and b_count >= 1:
            out.add(name)
    return out


def list_available_delta_dates(base_dir='delta_snapshots'):
    """Return sorted list of date strings (YYYY-MM-DD) for which we have a daily delta JSON."""
    import glob
    import re
    dates = set()
    for pattern in ('delta_daily_*.json.gz', 'delta_daily_*.json'):
        for path in glob.glob(os.path.join(base_dir, pattern)):
            name = os.path.basename(path)
            if name.endswith('.gz'):
                name = name[:-3]
            m = re.match(r'delta_daily_(\d{4}-\d{2}-\d{2})\.json', name)
            if m:
                dates.add(m.group(1))
    return sorted(dates)


def get_leaderboard_totals_from_date_range(start_date, end_date, base_dir='delta_snapshots'):
    """Compute AA/HP gains from start_date to end_date using daily delta JSONs (same data as delta-history).
    Only includes characters present in BOTH start and end deltas (excludes anon flip / visibility change).
    When both daily JSONs include equipped_worn_by_char, excludes characters with 0 real worn at start
    and >=1 at end (corpse-loot across range), matching delta.html leaderboards.
    Returns dict char_name -> {aa_gain, hp_gain, class, level} or None if either delta is missing."""
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    delta_start = load_daily_delta_json(start_date, base_dir)
    delta_end = load_daily_delta_json(end_date, base_dir)
    if not delta_start or not delta_end:
        return None
    bd_s = delta_start.get('baseline_date', 'Unknown')
    bd_e = delta_end.get('baseline_date', 'Unknown')
    if bd_s != 'Unknown' and bd_e != 'Unknown' and bd_s != bd_e:
        try:
            result = compare_delta_to_delta_reconstructed(delta_start, delta_end, base_dir)
        except ValueError:
            # Missing archived baseline for one era; cannot reconstruct cross-baseline range.
            return None
    else:
        baseline_chars = None
        if bd_s == bd_e and bd_s != 'Unknown':
            bl = load_baseline_for_date(bd_s, base_dir)
            if bl:
                baseline_chars = bl.get('characters')
        result = compare_delta_to_delta(delta_start, delta_end, baseline_chars)
    # Only consider characters present in both snapshots (same rule as delta-history / general visibility)
    start_chars = set(delta_start.get('char_deltas', {}).keys())
    end_chars = set(delta_end.get('char_deltas', {}).keys())
    chars_in_both = start_chars & end_chars
    # Exclude anyone deleted in end delta
    end_deltas = delta_end.get('char_deltas', {})
    for char_name in list(chars_in_both):
        if end_deltas.get(char_name, {}).get('is_deleted'):
            chars_in_both.discard(char_name)
    corpse_loot_chars = _corpse_loot_chars_from_equipped_meta(delta_start, delta_end)
    totals = {}
    for char_name, delta in result.get('char_deltas', {}).items():
        if char_name not in chars_in_both:
            continue
        if char_name in corpse_loot_chars:
            continue
        if delta.get('is_deleted') or delta.get('is_new'):
            continue
        aa = delta.get('aa_total_change', 0)
        hp = delta.get('hp_change', 0)
        if aa > 0 or hp > 0:
            totals[char_name] = {
                'aa_gain': aa,
                'hp_gain': hp,
                'class': delta.get('class', ''),
                'level': delta.get('current_level', 0)
            }
    return totals


def reconstruct_character_names(baseline_characters, delta):
    """Character names present in a snapshot = baseline keys + char_deltas, mirroring
    delta-history.js reconstructCharacterState (keys only)."""
    names = set((baseline_characters or {}).keys())
    for char_name, d in (delta.get('char_deltas') or {}).items():
        if d.get('is_deleted'):
            names.discard(char_name)
            continue
        if d.get('is_new') or char_name not in names:
            names.add(char_name)
    return names


def _apply_cross_day_inventory_visibility(inv_deltas, delta_a, delta_b, baseline_characters):
    """Tag inv_deltas with is_visibility_change and add empty rows (delta-history parity)."""
    if not baseline_characters:
        return
    start_names = reconstruct_character_names(baseline_characters, delta_a)
    end_names = reconstruct_character_names(baseline_characters, delta_b)
    inv_a = delta_a.get('inv_deltas') or {}
    inv_b = delta_b.get('inv_deltas') or {}
    inv_a_keys = set(inv_a.keys())
    inv_b_keys = set(inv_b.keys())

    for char_name in list(inv_deltas.keys()):
        row = inv_deltas[char_name]
        in_start_state = char_name in start_names
        in_end_state = char_name in end_names
        is_vis = (in_start_state and not in_end_state) or (not in_start_state and in_end_state)
        if not is_vis:
            is_vis = (char_name in inv_a_keys and char_name not in inv_b_keys) or (
                char_name not in inv_a_keys and char_name in inv_b_keys
            )
        row['is_visibility_change'] = is_vis

    empty_vis = {'added': {}, 'removed': {}, 'item_names': {}, 'is_visibility_change': True}
    for char_name in start_names:
        if char_name in end_names or char_name in inv_deltas:
            continue
        inv_deltas[char_name] = dict(empty_vis)
    for char_name in end_names:
        if char_name in start_names or char_name in inv_deltas:
            continue
        inv_deltas[char_name] = dict(empty_vis)


def _cumulative_char_stats_at_slice(baseline_characters, char_name, char_deltas_dict):
    """Level/AA/HP at end of day for one daily delta JSON.

    Daily files omit characters identical to baseline; missing key means baseline stats.
    """
    row = (char_deltas_dict or {}).get(char_name)
    if row:
        lvl = row.get('current_level', row.get('previous_level', 0))
        aa = row.get('current_aa_total', row.get('previous_aa_total', 0))
        hp = row.get('current_hp', row.get('previous_hp', 0))
        return (int(lvl or 0), int(aa or 0), int(hp or 0))
    bc = (baseline_characters or {}).get(char_name)
    if bc:
        lvl = int(bc.get('level', 0) or 0)
        aa = int(bc.get('aa_unspent', 0) or 0) + int(bc.get('aa_spent', 0) or 0)
        hp = int(bc.get('hp_max_total', 0) or 0)
        return (lvl, aa, hp)
    return (0, 0, 0)


def _apply_cross_day_inventory_visibility_dual(
    inv_deltas, delta_a, delta_b, baseline_a, baseline_b
):
    """Tag inv_deltas with is_visibility_change when the two days use different baselines."""
    bc_a = (baseline_a or {}).get('characters') or {}
    bc_b = (baseline_b or {}).get('characters') or {}
    start_names = reconstruct_character_names(bc_a, delta_a)
    end_names = reconstruct_character_names(bc_b, delta_b)
    inv_a = delta_a.get('inv_deltas') or {}
    inv_b = delta_b.get('inv_deltas') or {}
    inv_a_keys = set(inv_a.keys())
    inv_b_keys = set(inv_b.keys())

    for char_name in list(inv_deltas.keys()):
        row = inv_deltas[char_name]
        in_start_state = char_name in start_names
        in_end_state = char_name in end_names
        is_vis = (in_start_state and not in_end_state) or (not in_start_state and in_end_state)
        if not is_vis:
            is_vis = (char_name in inv_a_keys and char_name not in inv_b_keys) or (
                char_name not in inv_a_keys and char_name in inv_b_keys
            )
        row['is_visibility_change'] = is_vis

    empty_vis = {'added': {}, 'removed': {}, 'item_names': {}, 'is_visibility_change': True}
    for char_name in start_names:
        if char_name in end_names or char_name in inv_deltas:
            continue
        inv_deltas[char_name] = dict(empty_vis)
    for char_name in end_names:
        if char_name in start_names or char_name in inv_deltas:
            continue
        inv_deltas[char_name] = dict(empty_vis)


def _reconstruct_inventory_counts_for_char(baseline_inv, inv_deltas, char_name, no_rent):
    """Absolute item_id -> count for one character: baseline inventories + cumulative inv delta."""
    counts = defaultdict(int)
    no_rent = no_rent or set()
    for item in (baseline_inv or {}).get(char_name, []):
        item_id = item.get('item_id')
        try:
            iid = int(item_id)
            if iid in no_rent:
                continue
        except (TypeError, ValueError):
            pass
        kid = str(item_id)
        counts[kid] += 1
    row = (inv_deltas or {}).get(char_name)
    if not row:
        return {k: v for k, v in counts.items() if v > 0}
    for item_id, n in (row.get('added') or {}).items():
        kid = str(item_id)
        try:
            if int(kid) in no_rent:
                continue
        except (TypeError, ValueError):
            pass
        counts[kid] += int(n or 0)
    for item_id, n in (row.get('removed') or {}).items():
        kid = str(item_id)
        try:
            if int(kid) in no_rent:
                continue
        except (TypeError, ValueError):
            pass
        counts[kid] -= int(n or 0)
    return {k: v for k, v in counts.items() if v > 0}


def _reconstruct_all_inventory_counts(baseline_inv, inv_deltas, no_rent):
    inv_deltas = inv_deltas or {}
    chars = set((baseline_inv or {}).keys()) | set(inv_deltas.keys())
    out = {}
    for char_name in chars:
        c = _reconstruct_inventory_counts_for_char(baseline_inv, inv_deltas, char_name, no_rent)
        if c:
            out[char_name] = c
    return out


def _diff_inv_absolute_maps(abs_start, abs_end, inv_delta_start, inv_delta_end):
    """Net inventory change between two absolute per-character item count maps."""
    inv_deltas = {}
    meta_s = inv_delta_start or {}
    meta_e = inv_delta_end or {}
    all_chars = set(abs_start.keys()) | set(abs_end.keys())
    for char_name in all_chars:
        a = abs_start.get(char_name, {})
        b = abs_end.get(char_name, {})
        row_s = meta_s.get(char_name) or {}
        row_e = meta_e.get(char_name) or {}
        names_s = row_s.get('item_names') or {}
        names_e = row_e.get('item_names') or {}
        all_ids = set(a.keys()) | set(b.keys())
        added_items = {}
        removed_items = {}
        item_names = {}
        for item_id in all_ids:
            ca = int(a.get(item_id, 0) or 0)
            cb = int(b.get(item_id, 0) or 0)
            net = cb - ca
            if net > 0:
                added_items[item_id] = net
                if names_e.get(item_id):
                    item_names[item_id] = names_e[item_id]
                elif names_s.get(item_id):
                    item_names[item_id] = names_s[item_id]
            elif net < 0:
                removed_items[item_id] = -net
                if names_s.get(item_id):
                    item_names[item_id] = names_s[item_id]
                elif names_e.get(item_id):
                    item_names[item_id] = names_e[item_id]
        if added_items or removed_items:
            inv_deltas[char_name] = {
                'added': added_items,
                'removed': removed_items,
                'item_names': item_names,
            }
    return inv_deltas


def compare_delta_to_delta_reconstructed(delta_start, delta_end, base_dir='delta_snapshots'):
    """Range delta when daily JSONs use different ``baseline_date`` values.

    Reconstructs per-endpoint character stats and inventory using each day's baseline
    snapshot (archived ``baseline_master_<date>.json.gz`` when present), then diffs.
    """
    from generate_spell_page import load_no_rent_items

    bd_s = delta_start.get('baseline_date')
    bd_e = delta_end.get('baseline_date')
    bl_s = load_baseline_for_date(bd_s, base_dir) if bd_s else None
    bl_e = load_baseline_for_date(bd_e, base_dir) if bd_e else None
    if bd_s and bl_s is None:
        raise ValueError(
            f"Missing baseline snapshot for baseline_date={bd_s!r}: need "
            f"{os.path.join(base_dir, f'baseline_master_{bd_s}.json.gz')} or "
            f"baseline_master.json.gz whose baseline_date matches."
        )
    if bd_e and bl_e is None:
        raise ValueError(
            f"Missing baseline snapshot for baseline_date={bd_e!r}: need "
            f"{os.path.join(base_dir, f'baseline_master_{bd_e}.json.gz')} or "
            f"baseline_master.json.gz whose baseline_date matches."
        )
    bc_s = (bl_s or {}).get('characters') or {}
    bc_e = (bl_e or {}).get('characters') or {}
    bi_s = (bl_s or {}).get('inventories') or {}
    bi_e = (bl_e or {}).get('inventories') or {}
    no_rent = load_no_rent_items() or set()

    char_deltas = {}
    cd_s = delta_start.get('char_deltas') or {}
    cd_e = delta_end.get('char_deltas') or {}
    all_chars = set(list(cd_s.keys()) + list(cd_e.keys()))
    for char_name in all_chars:
        delta_a_char = cd_s.get(char_name, {})
        delta_b_char = cd_e.get(char_name, {})
        a_level, a_aa, a_hp = _cumulative_char_stats_at_slice(bc_s, char_name, cd_s)
        b_level, b_aa, b_hp = _cumulative_char_stats_at_slice(bc_e, char_name, cd_e)
        level_change = b_level - a_level
        aa_change = b_aa - a_aa
        hp_change = b_hp - a_hp
        if level_change != 0 or aa_change != 0 or hp_change != 0 or \
           delta_b_char.get('is_new', False) or delta_b_char.get('is_deleted', False):
            char_deltas[char_name] = {
                'name': char_name,
                'level_change': level_change,
                'aa_total_change': aa_change,
                'hp_change': hp_change,
                'current_level': b_level,
                'previous_level': a_level,
                'current_aa_total': b_aa,
                'previous_aa_total': a_aa,
                'current_hp': b_hp,
                'previous_hp': a_hp,
                'class': delta_b_char.get('class', '') or delta_a_char.get('class', ''),
                'is_new': delta_b_char.get('is_new', False) and not delta_a_char.get('is_new', False),
                'is_deleted': delta_b_char.get('is_deleted', False) and not delta_a_char.get('is_deleted', False)
            }

    abs_inv_s = _reconstruct_all_inventory_counts(bi_s, delta_start.get('inv_deltas'), no_rent)
    abs_inv_e = _reconstruct_all_inventory_counts(bi_e, delta_end.get('inv_deltas'), no_rent)
    inv_deltas = _diff_inv_absolute_maps(
        abs_inv_s, abs_inv_e, delta_start.get('inv_deltas'), delta_end.get('inv_deltas')
    )
    _apply_cross_day_inventory_visibility_dual(inv_deltas, delta_start, delta_end, bl_s, bl_e)

    return {
        'char_deltas': char_deltas,
        'inv_deltas': inv_deltas,
    }


def compare_delta_to_delta(delta_a, delta_b, baseline_characters=None):
    """Compare two deltas (from baseline) to get changes between Day A and Day B.
    
    Args:
        delta_a: Delta dict for Day A (from baseline)
        delta_b: Delta dict for Day B (from baseline)
        baseline_characters: Optional baseline ``characters`` dict; when set, merged
            ``inv_deltas`` get ``is_visibility_change`` (same rules as delta-history.html).
            **Strongly recommended:** daily JSONs omit unchanged characters; without baseline,
            missing keys are misread as 0 (inflating day-over-day to full cumulative-from-baseline).
    
    Returns:
        Dict with 'char_deltas' and 'inv_deltas' representing changes from Day A to Day B
    """
    from collections import defaultdict
    
    # Character deltas: delta_B - delta_A
    char_deltas = {}
    
    # Get all characters from both deltas
    all_chars = set(list(delta_a.get('char_deltas', {}).keys()) + 
                    list(delta_b.get('char_deltas', {}).keys()))
    cd_a = delta_a.get('char_deltas') or {}
    cd_b = delta_b.get('char_deltas') or {}
    
    for char_name in all_chars:
        delta_a_char = cd_a.get(char_name, {})
        delta_b_char = cd_b.get(char_name, {})
        
        # Extract values (cumulative-from-baseline snapshot at each day; missing row = baseline)
        a_level, a_aa, a_hp = _cumulative_char_stats_at_slice(
            baseline_characters, char_name, cd_a
        )
        b_level, b_aa, b_hp = _cumulative_char_stats_at_slice(
            baseline_characters, char_name, cd_b
        )
        
        # Calculate changes from Day A to Day B
        level_change = b_level - a_level
        aa_change = b_aa - a_aa
        hp_change = b_hp - a_hp
        
        # Only include if there are changes
        if level_change != 0 or aa_change != 0 or hp_change != 0 or \
           delta_b_char.get('is_new', False) or delta_b_char.get('is_deleted', False):
            char_deltas[char_name] = {
                'name': char_name,
                'level_change': level_change,
                'aa_total_change': aa_change,
                'hp_change': hp_change,
                'current_level': b_level,
                'previous_level': a_level,
                'current_aa_total': b_aa,
                'previous_aa_total': a_aa,
                'current_hp': b_hp,
                'previous_hp': a_hp,
                'class': delta_b_char.get('class', '') or delta_a_char.get('class', ''),
                'is_new': delta_b_char.get('is_new', False) and not delta_a_char.get('is_new', False),
                'is_deleted': delta_b_char.get('is_deleted', False) and not delta_a_char.get('is_deleted', False)
            }
    
    # Inventory deltas: merge added/removed items
    inv_deltas = {}
    all_inv_chars = set(list(delta_a.get('inv_deltas', {}).keys()) + 
                        list(delta_b.get('inv_deltas', {}).keys()))
    
    for char_name in all_inv_chars:
        delta_a_inv = delta_a.get('inv_deltas', {}).get(char_name, {'added': {}, 'removed': {}, 'item_names': {}})
        delta_b_inv = delta_b.get('inv_deltas', {}).get(char_name, {'added': {}, 'removed': {}, 'item_names': {}})
        
        # Calculate net changes: (B_added - B_removed) - (A_added - A_removed)
        # Simplified: B_added - B_removed - A_added + A_removed
        added_items = defaultdict(int)
        removed_items = defaultdict(int)
        item_names = {}
        
        # Items added in B but not in A (or more in B than A)
        for item_id, count in delta_b_inv.get('added', {}).items():
            a_added = delta_a_inv.get('added', {}).get(item_id, 0)
            if count > a_added:
                added_items[item_id] = count - a_added
                if item_id in delta_b_inv.get('item_names', {}):
                    item_names[item_id] = delta_b_inv['item_names'][item_id]
        
        # Items removed in B but not in A (or more in B than A)
        for item_id, count in delta_b_inv.get('removed', {}).items():
            a_removed = delta_a_inv.get('removed', {}).get(item_id, 0)
            if count > a_removed:
                removed_items[item_id] = count - a_removed
                if item_id in delta_b_inv.get('item_names', {}):
                    item_names[item_id] = delta_b_inv['item_names'][item_id]
        
        # Items that were added in A but removed in B (net removal)
        for item_id, count in delta_a_inv.get('added', {}).items():
            b_removed = delta_b_inv.get('removed', {}).get(item_id, 0)
            if b_removed > 0:
                net_change = b_removed - count
                if net_change > 0:
                    removed_items[item_id] = net_change
                elif net_change < 0:
                    added_items[item_id] = -net_change
                if item_id in delta_a_inv.get('item_names', {}):
                    item_names[item_id] = delta_a_inv['item_names'][item_id]
        
        if added_items or removed_items:
            inv_deltas[char_name] = {
                'added': dict(added_items),
                'removed': dict(removed_items),
                'item_names': item_names
            }

    if baseline_characters:
        _apply_cross_day_inventory_visibility(inv_deltas, delta_a, delta_b, baseline_characters)
    
    return {
        'char_deltas': char_deltas,
        'inv_deltas': inv_deltas
    }

def get_date_range_deltas(start_date, end_date, base_dir='delta_snapshots'):
    """Get deltas for a date range by comparing two daily delta JSONs.

    Compares the two endpoint daily files (not every calendar day in between).
    ``start_date`` and ``end_date`` may be passed in either order; they are normalized
    so the earlier calendar day is always the range start.

    When both dailies share the same ``baseline_date``, inventory math subtracts two
    cumulative-from-baseline snapshots (requires baseline character metadata for sparse
    rows). When ``baseline_date`` differs (baseline rotation), character and inventory
    changes are computed by reconstructing each endpoint from its era baseline + delta,
    then diffing (needs ``baseline_master_<baseline_date>.json.gz`` archives on disk).

    Raises:
        ValueError: If a daily file is missing, or cross-baseline reconstruction cannot
        load a required baseline (missing archive and mismatched ``baseline_master.json.gz``).
    """
    if start_date == end_date:
        return {
            'char_deltas': {},
            'inv_deltas': {},
            'start_date': start_date,
            'end_date': end_date,
        }

    if start_date > end_date:
        start_date, end_date = end_date, start_date

    delta_start = load_daily_delta_json(start_date, base_dir)
    delta_end = load_daily_delta_json(end_date, base_dir)

    if not delta_start:
        raise ValueError(f"Delta not found for start date: {start_date}")
    if not delta_end:
        raise ValueError(f"Delta not found for end date: {end_date}")

    baseline_start = delta_start.get('baseline_date', 'Unknown')
    baseline_end = delta_end.get('baseline_date', 'Unknown')

    if (
        baseline_start != 'Unknown'
        and baseline_end != 'Unknown'
        and baseline_start != baseline_end
    ):
        result = compare_delta_to_delta_reconstructed(delta_start, delta_end, base_dir)
    else:
        baseline_chars = None
        if baseline_start == baseline_end and baseline_start != 'Unknown':
            bl = load_baseline_for_date(baseline_start, base_dir)
            if bl:
                baseline_chars = bl.get('characters')
        result = compare_delta_to_delta(delta_start, delta_end, baseline_chars)

    result['start_date'] = start_date
    result['end_date'] = end_date
    return result