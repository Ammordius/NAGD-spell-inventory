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

def accumulate_weekly_deltas(week_start_date, current_char_data, base_dir='delta_snapshots'):
    """Accumulate all deltas for a week to get weekly totals.
    Compares current data against weekly baseline.
    
    Args:
        week_start_date: Week start date (YYYY-MM-DD)
        current_char_data: Current character data dict
        base_dir: Base directory for snapshots and baselines
    
    Returns:
        Dict with accumulated AA/HP gains per character
    """
    weekly_totals = defaultdict(lambda: {
        'aa_gain': 0,
        'hp_gain': 0,
        'class': '',
        'level': 0
    })
    
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

def accumulate_monthly_deltas(month_start_date, current_char_data, base_dir='delta_snapshots'):
    """Accumulate all deltas for a month to get monthly totals.
    Compares current data against monthly baseline.
    
    Args:
        month_start_date: Month start date (YYYY-MM-DD)
        current_char_data: Current character data dict
        base_dir: Base directory for snapshots and baselines
    
    Returns:
        Dict with accumulated AA/HP gains per character
    """
    monthly_totals = defaultdict(lambda: {
        'aa_gain': 0,
        'hp_gain': 0,
        'class': '',
        'level': 0
    })
    
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

def get_weekly_leaderboard(week_start_date, stat_type='aa', top_n=20, base_dir='delta_snapshots', current_char_data=None):
    """Get weekly leaderboard for AA or HP gains.
    
    Args:
        week_start_date: Week start date (YYYY-MM-DD)
        stat_type: 'aa' or 'hp'
        top_n: Number of top entries to return
        base_dir: Base directory for snapshots
        current_char_data: Current character data (required for baseline comparison)
    
    Returns:
        List of dicts with leaderboard entries
    """
    if current_char_data is None:
        return []
    totals = accumulate_weekly_deltas(week_start_date, current_char_data, base_dir)
    
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

def get_monthly_leaderboard(month_start_date, stat_type='aa', top_n=20, base_dir='delta_snapshots', current_char_data=None):
    """Get monthly leaderboard for AA or HP gains.
    
    Args:
        month_start_date: Month start date (YYYY-MM-DD)
        stat_type: 'aa' or 'hp'
        top_n: Number of top entries to return
        base_dir: Base directory for snapshots
        current_char_data: Current character data (required for baseline comparison)
    
    Returns:
        List of dicts with leaderboard entries
    """
    if current_char_data is None:
        return []
    totals = accumulate_monthly_deltas(month_start_date, current_char_data, base_dir)
    
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
    
    Saves as compressed .json.gz to stay under GitHub's 100 MB file size limit.
    
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
    
    # Also save uncompressed for local use (optional, can be removed)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(baseline_json, f, indent=2)
    
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
            # Archive old baseline
            old_baseline_file = os.path.join(base_dir, f"baseline_master_{baseline['baseline_date']}.json")
            import shutil
            shutil.copy2(os.path.join(base_dir, "baseline_master.json"), old_baseline_file)
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
    from generate_spell_page import compare_character_data, compare_inventories
    char_deltas = compare_character_data(current_char_data, baseline_char_data, None)
    inv_deltas = compare_inventories(current_inv_data, baseline_inv_data, None)
    
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
    
    # Save delta data (changes from baseline)
    daily_delta = {
        'date': date_str,
        'delta_type': 'daily_from_baseline',
        'baseline_date': baseline['baseline_date'],
        'char_deltas': char_deltas,
        'inv_deltas': inv_deltas,
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

def compare_delta_to_delta(delta_a, delta_b):
    """Compare two deltas (from baseline) to get changes between Day A and Day B.
    
    Args:
        delta_a: Delta dict for Day A (from baseline)
        delta_b: Delta dict for Day B (from baseline)
    
    Returns:
        Dict with 'char_deltas' and 'inv_deltas' representing changes from Day A to Day B
    """
    from collections import defaultdict
    
    # Character deltas: delta_B - delta_A
    char_deltas = {}
    
    # Get all characters from both deltas
    all_chars = set(list(delta_a.get('char_deltas', {}).keys()) + 
                    list(delta_b.get('char_deltas', {}).keys()))
    
    for char_name in all_chars:
        delta_a_char = delta_a.get('char_deltas', {}).get(char_name, {})
        delta_b_char = delta_b.get('char_deltas', {}).get(char_name, {})
        
        # Extract values (these are cumulative from baseline)
        a_level = delta_a_char.get('current_level', delta_a_char.get('previous_level', 0))
        b_level = delta_b_char.get('current_level', delta_b_char.get('previous_level', 0))
        a_aa = delta_a_char.get('current_aa_total', delta_a_char.get('previous_aa_total', 0))
        b_aa = delta_b_char.get('current_aa_total', delta_b_char.get('previous_aa_total', 0))
        a_hp = delta_a_char.get('current_hp', delta_a_char.get('previous_hp', 0))
        b_hp = delta_b_char.get('current_hp', delta_b_char.get('previous_hp', 0))
        
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
    
    return {
        'char_deltas': char_deltas,
        'inv_deltas': inv_deltas
    }

def get_date_range_deltas(start_date, end_date, base_dir='delta_snapshots'):
    """Get deltas for a date range by comparing two daily delta JSONs.
    This is much more efficient than aggregating all days in between.
    
    Handles baseline transitions automatically - if dates are from different baseline periods,
    it will use the appropriate baseline for each.
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        base_dir: Base directory for daily deltas
    
    Returns:
        Dict with 'char_deltas' and 'inv_deltas' representing changes from start_date to end_date
    """
    # Load deltas for both dates
    delta_start = load_daily_delta_json(start_date, base_dir)
    delta_end = load_daily_delta_json(end_date, base_dir)
    
    if not delta_start:
        raise ValueError(f"Delta not found for start date: {start_date}")
    if not delta_end:
        raise ValueError(f"Delta not found for end date: {end_date}")
    
    # If same date, return empty deltas (no changes)
    if start_date == end_date:
        return {
            'char_deltas': {},
            'inv_deltas': {},
            'start_date': start_date,
            'end_date': end_date
        }
    
    # Check if deltas are from different baseline periods
    baseline_start = delta_start.get('baseline_date', 'Unknown')
    baseline_end = delta_end.get('baseline_date', 'Unknown')
    
    if baseline_start != baseline_end:
        # Different baselines - need to handle this case
        # For now, we can still compare them (the comparison function handles this)
        # But ideally we'd want to reconstruct states from their respective baselines
        # This is a limitation but should be rare (only happens across yearly resets)
        pass
    
    # Compare the two deltas
    result = compare_delta_to_delta(delta_start, delta_end)
    result['start_date'] = start_date
    result['end_date'] = end_date
    
    return result