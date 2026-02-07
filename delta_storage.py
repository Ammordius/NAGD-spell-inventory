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
    
    # Try to load weekly baseline
    baseline_file = os.path.join(base_dir, '..', 'character', f'baseline_week_{week_start_date}.txt')
    if not os.path.exists(baseline_file):
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
    
    # Parse baseline and compare with current
    from generate_spell_page import parse_character_data
    baseline_data = parse_character_data(baseline_file, None)
    
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
    
    # Try to load monthly baseline
    baseline_file = os.path.join(base_dir, '..', 'character', f'baseline_month_{month_start_date}.txt')
    if not os.path.exists(baseline_file):
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
    
    # Parse baseline and compare with current
    from generate_spell_page import parse_character_data
    baseline_data = parse_character_data(baseline_file, None)
    
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
