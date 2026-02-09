#!/usr/bin/env python3
"""Generate historical deltas from cached magelo dump files.

This script processes cached magelo dump files to generate delta JSONs
for dates that have cached data but no delta JSON yet.
"""

import os
import sys
from datetime import datetime, timedelta
from delta_storage import (
    parse_character_data, parse_inventory_file,
    save_master_baseline, load_master_baseline,
    save_daily_delta_from_baseline
)

def find_cached_files_for_date(date_str, base_dir='.'):
    """Find cached character/inventory files for a specific date.
    
    Looks for files named with the date pattern or in dated subdirectories.
    """
    char_file = None
    inv_file = None
    
    # Try various naming patterns
    patterns = [
        (f"character/TAKP_character_{date_str}.txt", f"inventory/TAKP_character_inventory_{date_str}.txt"),
        (f"character/{date_str}/TAKP_character.txt", f"inventory/{date_str}/TAKP_character_inventory.txt"),
        (f"character/TAKP_character.txt", f"inventory/TAKP_character_inventory.txt"),  # Current files
    ]
    
    for char_pattern, inv_pattern in patterns:
        if os.path.exists(char_pattern) and os.path.exists(inv_pattern):
            char_file = char_pattern
            inv_file = inv_pattern
            break
    
    return char_file, inv_file

def generate_delta_for_date(date_str, char_file, inv_file, delta_snapshots_dir='delta_snapshots'):
    """Generate a delta JSON for a specific date from character/inventory files."""
    print(f"\n=== Generating delta for {date_str} ===")
    
    if not os.path.exists(char_file):
        print(f"  ERROR: Character file not found: {char_file}")
        return False
    if not os.path.exists(inv_file):
        print(f"  ERROR: Inventory file not found: {inv_file}")
        return False
    
    print(f"  Using character file: {char_file}")
    print(f"  Using inventory file: {inv_file}")
    
    # Parse the files
    print("  Parsing character file...")
    char_data = parse_character_data(char_file)
    print(f"  Found {len(char_data)} characters")
    
    print("  Parsing inventory file...")
    inv_data = parse_inventory_file(inv_file)
    print(f"  Found inventories for {len(inv_data)} characters")
    
    # Load or create baseline
    baseline = load_master_baseline(delta_snapshots_dir)
    if not baseline:
        print("  No baseline found, creating from current data...")
        save_master_baseline(char_data, inv_data, date_str, delta_snapshots_dir)
        baseline = load_master_baseline(delta_snapshots_dir)
        print(f"  Created baseline from {date_str}")
    
    # Generate and save delta
    print(f"  Generating delta from baseline ({baseline['baseline_date']})...")
    try:
        save_daily_delta_from_baseline(
            char_data, inv_data, date_str,
            baseline['characters'], baseline['inventories'],
            delta_snapshots_dir
        )
        print(f"  ✓ Successfully generated delta for {date_str}")
        return True
    except Exception as e:
        print(f"  ERROR: Failed to generate delta: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Generate deltas for dates that have cached files but no delta JSON."""
    # Dates from GitHub cache that we want to generate deltas for
    target_dates = [
        '2026-02-06',
        '2026-02-07', 
        '2026-02-08',
        '2026-02-09'
    ]
    
    # Check which deltas already exist
    delta_snapshots_dir = 'delta_snapshots'
    existing_deltas = set()
    if os.path.exists(delta_snapshots_dir):
        for filename in os.listdir(delta_snapshots_dir):
            if filename.startswith('delta_daily_') and filename.endswith('.json.gz'):
                # Extract date from filename
                date_part = filename.replace('delta_daily_', '').replace('.json.gz', '')
                existing_deltas.add(date_part)
    
    print(f"Existing deltas: {sorted(existing_deltas)}")
    
    # Generate missing deltas
    success_count = 0
    for date_str in target_dates:
        if date_str in existing_deltas:
            print(f"\n{date_str}: Delta already exists, skipping")
            continue
        
        # Try to find cached files for this date
        # In GitHub Actions, cached files are named TAKP_character.txt with date in cache key
        # We'll need to check if files exist or download from cache
        char_file, inv_file = find_cached_files_for_date(date_str)
        
        if not char_file or not inv_file:
            print(f"\n{date_str}: No cached files found")
            print("  Note: In GitHub Actions, files should be restored from cache first")
            continue
        
        if generate_delta_for_date(date_str, char_file, inv_file, delta_snapshots_dir):
            success_count += 1
    
    print(f"\n=== Summary ===")
    print(f"Successfully generated {success_count} deltas")
    print(f"Total deltas now: {len(existing_deltas) + success_count}")

if __name__ == '__main__':
    main()
