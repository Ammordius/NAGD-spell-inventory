#!/usr/bin/env python3
"""
Script to generate a static HTML page showing which mule characters have
spells from PoK turn-ins (items 29112, 29131, 29132).
"""

import json
import math
import os
import re
from html import escape
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import quote
from delta_storage import (
    save_delta_snapshot, load_delta_snapshot,
    get_week_start, get_month_start,
    get_weekly_leaderboard, get_monthly_leaderboard,
    save_baseline_json, save_daily_delta_json, get_date_range_deltas,
    save_master_baseline, load_master_baseline,
    save_daily_delta_from_baseline,
    load_daily_delta_json,
    load_baseline_for_date,
    compare_delta_to_delta,
    daily_json_pair_usable_for_delta_html_json_compare,
    _corpse_loot_chars_from_equipped_meta,
)
from gear_event_storage import (
    append_day_events_from_deltas,
    build_possession_map,
    filter_unique_reacquires_in_inv_deltas,
    gear_events_available,
    get_day_delta_from_events,
    list_available_event_dates,
    populate_item_names_for_inv_deltas,
    possession_from_inv_snapshot,
)

# Character names to look for
MULE_CHARACTERS = [
    "Freelootone", "Freeloottwo", "Freelootthree",
    "Miscthree", "Miscfour", "Miscfive", "Miscsix", "Miscseven",
    "Armourgirl", "Beastlordgirl", "Enchantergirl", "Magiciangirl",
    "Necromancergirl", "Rangergirl", "Shadoknightgirl", "Wizardgirl",
    "Bardboy", "Clericboy", "Druidboy", "Enchanterboy",
    "Magicianboy", "Necromancerboy", "Paladinboy", "Shamanboy"
]

# GoatCounter analytics snippet (included in all generated HTML pages)
GOATCOUNTER_SCRIPT = '''    <script data-goatcounter="https://ammordius.goatcounter.com/count"
            async src="//gc.zgo.at/count.js"></script>
'''

# Officer mule characters
OFFICER_MULE_CHARACTERS = [
    "Nagalchpoistink", "Nagbaker", "Nagbows", "Nagbrew",
    "Nagclothes", "Nagpottery", "Nagshinystuff", "Nagsmith",
    "Gemsdaddy", "Incharge", "Overflow", "Overflowfive",
    "Overflowfour", "Overflowthree", "Overflowtwo", "Slushfund"
]

def load_spell_exchange_data():
    """Load the spell exchange JSON data and extract all spell IDs."""
    # Try multiple possible locations
    base_dir = os.path.dirname(__file__)
    possible_paths = [
        os.path.join(base_dir, "spell_exchange_list.json"),  # Same directory
        os.path.join(base_dir, "..", "quests", "poknowledge", "spell_exchange_list.json"),  # Relative path
        os.path.join(base_dir, "..", "..", "quests", "poknowledge", "spell_exchange_list.json"),  # Alternative relative
    ]
    
    json_path = None
    for path in possible_paths:
        if os.path.exists(path):
            json_path = path
            break
    
    if json_path is None:
        raise FileNotFoundError(f"Could not find spell_exchange_list.json. Tried: {possible_paths}")
    
    with open(json_path, 'r') as f:
        data = json.load(f)
    
    # Extract all spell IDs and create a mapping
    spell_info = {}  # spell_id -> {name, npc, class, item_type}
    
    for item_id, item_data in data['items'].items():
        item_name = item_data['name']
        for npc_data in item_data['npcs']:
            npc_name = npc_data['npc']
            npc_class = npc_data['class']
            for spell_id, spell_name in zip(npc_data['spells'], npc_data['spell_names']):
                spell_id_str = str(spell_id)
                if spell_id_str not in spell_info:
                    spell_info[spell_id_str] = {
                        'name': spell_name,
                        'npcs': [],
                        'item_types': []
                    }
                spell_info[spell_id_str]['npcs'].append({
                    'npc': npc_name,
                    'class': npc_class,
                    'item_id': item_id,
                    'item_name': item_name
                })
                if item_name not in spell_info[spell_id_str]['item_types']:
                    spell_info[spell_id_str]['item_types'].append(item_name)
    
    return spell_info, data

def parse_character_file(char_file, character_list):
    """Parse character file to get character IDs for specified characters."""
    char_ids = {}
    with open(char_file, 'r', encoding='utf-8') as f:
        # Skip header
        next(f)
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 9:
                continue
            name = parts[0]
            if name in character_list:
                char_id = parts[8]  # 9th column (0-indexed = 8)
                char_ids[name] = char_id
    return char_ids

def parse_character_data(char_file, character_list):
    """Parse character file to get full character data (level, AA, etc.) for specified characters.
    If character_list is None, parses all characters (serverwide)."""
    char_data = {}
    with open(char_file, 'r', encoding='utf-8') as f:
        # Skip header
        header = next(f).strip().split('\t')
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 12:
                continue
            name = parts[0]
            if character_list is None or name in character_list:
                try:
                    char_data[name] = {
                        'id': parts[8] if len(parts) > 8 else '',
                        'level': int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
                        'aa_unspent': int(parts[10]) if len(parts) > 10 and parts[10].isdigit() else 0,
                        'aa_spent': int(parts[11]) if len(parts) > 11 and parts[11].isdigit() else 0,
                        'hp_max_total': int(parts[28]) if len(parts) > 28 and parts[28].isdigit() else 0,  # Column 28 is hp_max_total
                        'class': parts[5] if len(parts) > 5 else '',  # Column 5 is class (0-indexed)
                        'race': parts[4] if len(parts) > 4 else '',
                        'guild': parts[2].strip() if len(parts) > 2 else '',  # Column 2 is guild (TAKP export)
                    }
                except (ValueError, IndexError):
                    continue
    return char_data

def parse_inventory_file(inv_file, char_ids):
    """Parse inventory file to get items for each character."""
    inventories = defaultdict(list)
    char_id_to_name = {v: k for k, v in char_ids.items()}
    
    with open(inv_file, 'r', encoding='utf-8') as f:
        # Skip header
        next(f)
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 4:
                continue
            char_id = parts[0]
            if char_id in char_id_to_name:
                slot_id = parts[1]
                item_id = parts[2]
                item_name = parts[3] if len(parts) > 3 else ""
                char_name = char_id_to_name[char_id]
                inventories[char_name].append({
                    'slot_id': slot_id,
                    'item_id': item_id,
                    'item_name': item_name
                })
    
    return inventories

def get_spell_sort_key(spell_id, spell_info):
    """Get sort key for a spell: (class_order, item_type_order, spell_name)"""
    spell_data = spell_info[spell_id]
    
    # Class order (alphabetical)
    class_order = 999
    item_type_order = 999
    
    # Get the first NPC's class and item type (primary source)
    if spell_data['npcs']:
        npc_info = spell_data['npcs'][0]
        class_name = npc_info['class']
        
        # Class order - alphabetical
        class_order = class_name
        
        # Item type order: Ethereal Parchment (1), Spectral Parchment (2), Glyphed Rune Word (3)
        item_name = npc_info['item_name']
        if item_name == "Ethereal Parchment":
            item_type_order = 1
        elif item_name == "Spectral Parchment":
            item_type_order = 2
        elif item_name == "Glyphed Rune Word":
            item_type_order = 3
    
    spell_name = spell_data['name']
    return (class_order, item_type_order, spell_name)

def generate_html(char_ids, inventories, spell_info, officer_char_ids=None, officer_inventories=None):
    """Generate the HTML page."""
    
    # Find PoK spells in inventories
    pok_spells = defaultdict(lambda: defaultdict(int))  # char -> spell_id -> count
    all_items = defaultdict(list)
    pok_spell_ids = set(spell_info.keys())
    
    for char_name, items in inventories.items():
        for item in items:
            item_id = item['item_id']
            all_items[char_name].append(item)
            if item_id in pok_spell_ids:
                pok_spells[char_name][item_id] += 1
    
    # Process officer mules if provided
    officer_pok_spells = defaultdict(lambda: defaultdict(int))
    officer_all_items = defaultdict(list)
    if officer_inventories:
        for char_name, items in officer_inventories.items():
            for item in items:
                item_id = item['item_id']
                officer_all_items[char_name].append(item)
                if item_id in pok_spell_ids:
                    officer_pok_spells[char_name][item_id] += 1
    
    # Build item search index: item_id -> {name, chars: [(char_name, count), ...]}
    # Includes all items on regular mules and officer mules (for search/autocomplete)
    item_search_index = {}
    for char_name, items in all_items.items():
        for item in items:
            item_id = item['item_id']
            item_name = (item.get('item_name') or '').strip()
            if not item_id:
                continue
            if item_id not in item_search_index:
                item_search_index[item_id] = {'name': item_name, 'chars': defaultdict(int)}
            item_search_index[item_id]['chars'][char_name] += 1
    if officer_all_items:
        for char_name, items in officer_all_items.items():
            for item in items:
                item_id = item['item_id']
                item_name = (item.get('item_name') or '').strip()
                if not item_id:
                    continue
                if item_id not in item_search_index:
                    item_search_index[item_id] = {'name': item_name, 'chars': defaultdict(int)}
                item_search_index[item_id]['chars'][char_name] += 1
    # Convert chars to sorted list of (char_name, count) for JSON
    item_search_list = []
    all_item_names_for_autocomplete = []
    for item_id, data in item_search_index.items():
        chars_list = sorted(data['chars'].items(), key=lambda x: (-x[1], x[0]))
        item_search_list.append({
            'id': item_id,
            'name': data['name'],
            'chars': chars_list
        })
        if data['name']:
            all_item_names_for_autocomplete.append(data['name'])
    # Safe for embedding in <script>: avoid closing tag
    def script_safe(s):
        return s.replace("</", "<\\/")
    item_search_json = script_safe(json.dumps(item_search_list, ensure_ascii=False))
    autocomplete_names_json = script_safe(json.dumps(sorted(set(all_item_names_for_autocomplete)), ensure_ascii=False))
    
    # Create reverse mapping: spell_id -> list of characters who have it
    spell_to_chars = defaultdict(list)
    for char_name, spells in pok_spells.items():
        for spell_id, count in spells.items():
            spell_to_chars[spell_id].append((char_name, count))
    
    # Get magelo update date from environment variable or use default
    magelo_update_date = os.environ.get('MAGELO_UPDATE_DATE', 'Unknown')
    
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Mule PoK Spell Inventory</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }
        h3 {
            color: #777;
            margin-top: 20px;
        }
        .summary {
            background-color: #fff3cd;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .summary-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }
        .stat-box {
            background-color: white;
            padding: 10px;
            border-radius: 3px;
            text-align: center;
        }
        .stat-number {
            font-size: 24px;
            font-weight: bold;
            color: #4CAF50;
        }
        .spell-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(400px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }
        .spell-card {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            background-color: #fafafa;
            border-left: 5px solid #4CAF50;
        }
        .spell-card.has-spell {
            background-color: #e8f5e9;
            border-left-color: #4CAF50;
        }
        .spell-card.no-spell {
            background-color: #ffebee;
            border-left-color: #f44336;
            opacity: 0.9;
        }
        .spell-card.no-spell .spell-name,
        .spell-card.no-spell .spell-name a {
            color: #c62828;
        }
        .spell-card.no-spell .spell-id {
            color: #d32f2f;
        }
        .spell-card.no-spell .spell-sources {
            color: #b71c1c;
        }
        .spell-name {
            font-weight: bold;
            font-size: 1.1em;
            color: #1976D2;
            margin-bottom: 10px;
        }
        .spell-name a {
            color: #1976D2;
            text-decoration: none;
        }
        .spell-name a:hover {
            text-decoration: underline;
        }
        .spell-id {
            color: #666;
            font-size: 0.9em;
            margin-bottom: 10px;
        }
        .spell-sources {
            font-size: 0.9em;
            color: #555;
            margin: 10px 0;
        }
        .spell-sources strong {
            color: #333;
        }
        .char-list {
            margin-top: 10px;
            padding: 10px;
            background-color: white;
            border-radius: 3px;
        }
        .char-item {
            display: inline-block;
            background-color: #4CAF50;
            color: white;
            padding: 5px 10px;
            margin: 3px;
            border-radius: 3px;
            font-size: 0.9em;
        }
        .char-item .count {
            font-weight: bold;
            margin-left: 5px;
        }
        .character-section {
            margin: 20px 0;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background-color: #fafafa;
        }
        .character-section.has-spells {
            border-left: 5px solid #4CAF50;
        }
        .character-section.no-spells {
            border-left: 5px solid #ccc;
        }
        .spell-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 10px;
            margin-top: 10px;
        }
        .spell-item {
            padding: 8px;
            background-color: white;
            border-radius: 3px;
            border: 1px solid #ddd;
        }
        .spell-item a {
            color: #2196F3;
            text-decoration: none;
            font-weight: bold;
        }
        .spell-item a:hover {
            text-decoration: underline;
        }
        .spell-count {
            color: #4CAF50;
            font-weight: bold;
            margin-left: 5px;
        }
        .other-items {
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        }
        .other-items-list {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 5px;
            margin-top: 10px;
        }
        .other-item {
            padding: 5px;
            background-color: #f0f0f0;
            border-radius: 3px;
            font-size: 0.9em;
        }
        .group-header {
            background-color: #e3f2fd;
            padding: 10px;
            margin: 15px 0 10px 0;
            border-radius: 5px;
            font-weight: bold;
            color: #1976D2;
        }
        .search-inventory {
            margin: 20px 0;
            padding: 15px;
            background: #e8f5e9;
            border-radius: 8px;
            border: 1px solid #c8e6c9;
        }
        .search-inventory h2 {
            margin-top: 0;
            color: #2e7d32;
            border-bottom: none;
        }
        .search-inventory-wrap {
            position: relative;
            max-width: 500px;
        }
        .search-inventory input {
            width: 100%;
            padding: 10px 12px;
            font-size: 1em;
            border: 2px solid #4CAF50;
            border-radius: 5px;
            box-sizing: border-box;
        }
        .search-inventory input:focus {
            outline: none;
            border-color: #2e7d32;
        }
        .autocomplete-list {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            max-height: 280px;
            overflow-y: auto;
            background: white;
            border: 2px solid #4CAF50;
            border-top: none;
            border-radius: 0 0 5px 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            z-index: 100;
            list-style: none;
            margin: 0;
            padding: 0;
        }
        .autocomplete-list li {
            padding: 8px 12px;
            cursor: pointer;
            border-bottom: 1px solid #eee;
        }
        .autocomplete-list li:hover,
        .autocomplete-list li.selected {
            background: #e8f5e9;
        }
        .autocomplete-list li:last-child {
            border-bottom: none;
        }
        .search-results {
            margin-top: 15px;
        }
        .item-result-card {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 10px;
            background-color: #e8f5e9;
            border-left: 5px solid #4CAF50;
        }
        .item-result-card .item-name {
            font-weight: bold;
            font-size: 1.1em;
            margin-bottom: 10px;
        }
        .item-result-card .item-name a {
            color: #1976D2;
            text-decoration: none;
        }
        .item-result-card .item-name a:hover {
            text-decoration: underline;
        }
        .search-results-empty {
            color: #666;
            font-style: italic;
            margin-top: 10px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>TAKP Mule PoK Spell Inventory</h1>
        <p>Generated from magelo dump (last updated: """ + magelo_update_date + """)</p>
        <p>This page shows spells that can be obtained from PoK turn-ins (Ethereal Parchment, Spectral Parchment, Glyphed Rune Word)</p>
        
        <div class="search-inventory">
            <h2>Search mule inventory</h2>
            <p style="margin: 0 0 10px 0; color: #555; font-size: 0.95em;">Type to search items on mules. Autocomplete suggests item names; partial text matches multiple items (e.g. "ring" shows all items containing "ring").</p>
            <div class="search-inventory-wrap">
                <input type="text" id="item-search-input" placeholder="Item name (e.g. ring, parchment)..." autocomplete="off" />
                <ul class="autocomplete-list" id="autocomplete-list" style="display: none;"></ul>
            </div>
            <div class="search-results" id="search-results"></div>
        </div>
        
        <div class="summary">
            <h2>Summary</h2>
            <div class="summary-stats">
"""
    
    # Calculate summary stats
    total_chars = len(MULE_CHARACTERS)
    chars_with_spells = sum(1 for char in MULE_CHARACTERS if pok_spells[char])
    total_unique_spells = len([s for s in pok_spell_ids if any(pok_spells[char].get(s) for char in MULE_CHARACTERS)])
    total_spell_items = sum(sum(pok_spells[char].values()) for char in MULE_CHARACTERS)
    
    html += f"""
                <div class="stat-box">
                    <div class="stat-number">{total_chars}</div>
                    <div>Total Characters</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{chars_with_spells}</div>
                    <div>Characters with PoK Spells</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{total_unique_spells}</div>
                    <div>Unique PoK Spells Found</div>
                </div>
                <div class="stat-box">
                    <div class="stat-number">{total_spell_items}</div>
                    <div>Total PoK Spell Items</div>
                </div>
            </div>
        </div>
        
        <h2>All PoK Spells</h2>
        <p>Spells are grouped by class and item type. Found spells are shown in green, missing spells in red. Click spell names to view on TAKProject.</p>
"""
    
    # Get all unique classes for navigation
    all_classes = set()
    for spell_id in pok_spell_ids:
        if spell_info[spell_id]['npcs']:
            all_classes.add(spell_info[spell_id]['npcs'][0]['class'])
    
    # Calculate status counts per class and item type
    class_status = defaultdict(lambda: {
        'Ethereal Parchment': {'total': 0, 'found': 0},
        'Spectral Parchment': {'total': 0, 'found': 0},
        'Glyphed Rune Word': {'total': 0, 'found': 0}
    })
    
    for spell_id in pok_spell_ids:
        spell_data = spell_info[spell_id]
        if spell_data['npcs']:
            npc_info = spell_data['npcs'][0]
            class_name = npc_info['class']
            item_name = npc_info['item_name']
            is_found = bool(spell_to_chars.get(spell_id, []))
            
            class_status[class_name][item_name]['total'] += 1
            if is_found:
                class_status[class_name][item_name]['found'] += 1
    
    # Add status indicator section
    html += """
        <div style="background-color: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; border: 2px solid #ffc107;">
            <h2 style="margin-top: 0; color: #f57c00;">Collection Status by Class</h2>
            <p style="margin-bottom: 15px;">Use this to see which spells are missing and help complete the collection!</p>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
"""
    
    for class_name in sorted(all_classes):
        status = class_status[class_name]
        ep_total = status['Ethereal Parchment']['total']
        ep_found = status['Ethereal Parchment']['found']
        ep_missing = ep_total - ep_found
        ep_pct = int((ep_found / ep_total * 100)) if ep_total > 0 else 0
        
        sp_total = status['Spectral Parchment']['total']
        sp_found = status['Spectral Parchment']['found']
        sp_missing = sp_total - sp_found
        sp_pct = int((sp_found / sp_total * 100)) if sp_total > 0 else 0
        
        rune_total = status['Glyphed Rune Word']['total']
        rune_found = status['Glyphed Rune Word']['found']
        rune_missing = rune_total - rune_found
        rune_pct = int((rune_found / rune_total * 100)) if rune_total > 0 else 0
        
        class_anchor = class_name.lower().replace(' ', '-')
        html += f"""
                <div style="background-color: white; padding: 15px; border-radius: 5px; border: 1px solid #ddd;">
                    <h3 style="margin-top: 0; color: #1976D2;"><a href="#class-{class_anchor}" style="color: #1976D2; text-decoration: none;">{class_name}</a></h3>
                    <div style="margin: 10px 0;">
                        <div style="font-weight: bold; margin-bottom: 5px;">Ethereal Parchment (EP):</div>
                        <div style="background-color: #f0f0f0; border-radius: 3px; padding: 5px; margin-bottom: 5px;">
                            <div style="background-color: {'#4CAF50' if ep_found == ep_total else '#ff9800' if ep_found > 0 else '#f44336'}; height: 20px; width: {ep_pct}%; border-radius: 3px; transition: width 0.3s;"></div>
                        </div>
                        <div style="font-size: 0.9em; color: #666;">{ep_found}/{ep_total} found ({ep_pct}%) - <strong style="color: {'#4CAF50' if ep_missing == 0 else '#f44336'}">{ep_missing} missing</strong></div>
                    </div>
                    <div style="margin: 10px 0;">
                        <div style="font-weight: bold; margin-bottom: 5px;">Spectral Parchment (SP):</div>
                        <div style="background-color: #f0f0f0; border-radius: 3px; padding: 5px; margin-bottom: 5px;">
                            <div style="background-color: {'#4CAF50' if sp_found == sp_total else '#ff9800' if sp_found > 0 else '#f44336'}; height: 20px; width: {sp_pct}%; border-radius: 3px; transition: width 0.3s;"></div>
                        </div>
                        <div style="font-size: 0.9em; color: #666;">{sp_found}/{sp_total} found ({sp_pct}%) - <strong style="color: {'#4CAF50' if sp_missing == 0 else '#f44336'}">{sp_missing} missing</strong></div>
                    </div>
                    <div style="margin: 10px 0;">
                        <div style="font-weight: bold; margin-bottom: 5px;">Glyphed Rune Word (Rune):</div>
                        <div style="background-color: #f0f0f0; border-radius: 3px; padding: 5px; margin-bottom: 5px;">
                            <div style="background-color: {'#4CAF50' if rune_found == rune_total else '#ff9800' if rune_found > 0 else '#f44336'}; height: 20px; width: {rune_pct}%; border-radius: 3px; transition: width 0.3s;"></div>
                        </div>
                        <div style="font-size: 0.9em; color: #666;">{rune_found}/{rune_total} found ({rune_pct}%) - <strong style="color: {'#4CAF50' if rune_missing == 0 else '#f44336'}">{rune_missing} missing</strong></div>
                    </div>
                    <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #ddd; font-weight: bold; color: #333;">
                        Total: {ep_found + sp_found + rune_found}/{ep_total + sp_total + rune_total} spells found
                    </div>
                </div>
"""
    
    html += """
            </div>
        </div>
"""
    
    # Add class navigation
    html += '<div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;"><strong>Jump to Class:</strong> '
    class_links = []
    for class_name in sorted(all_classes):
        class_anchor = class_name.lower().replace(' ', '-')
        class_links.append(f'<a href="#class-{class_anchor}" style="color: #1976D2; text-decoration: none; margin: 0 10px; padding: 5px 10px; background-color: white; border-radius: 3px;">{class_name}</a>')
    html += ' '.join(class_links)
    html += '</div>'
    
    # Combine all spells into one list
    all_spells = []
    
    for spell_id in pok_spell_ids:
        spell_data = spell_info[spell_id]
        chars_with_this_spell = spell_to_chars.get(spell_id, [])
        
        spell_entry = {
            'id': spell_id,
            'name': spell_data['name'],
            'npcs': spell_data['npcs'],
            'chars': chars_with_this_spell,
            'found': bool(chars_with_this_spell)
        }
        
        all_spells.append(spell_entry)
    
    # Sort by class, then item type, then name
    all_spells.sort(key=lambda x: get_spell_sort_key(x['id'], spell_info))
    
    # Display all spells together
    found_count = sum(1 for s in all_spells if s['found'])
    not_found_count = sum(1 for s in all_spells if not s['found'])
    html += '<div class="group-header">All PoK Spells (Found: ' + str(found_count) + ', Not Found: ' + str(not_found_count) + ')</div>'
    html += '<div class="spell-grid">'
    current_class = None
    current_item_type = None
    
    for spell in all_spells:
        # Get primary class and item type for this spell
        if spell['npcs']:
            npc_info = spell['npcs'][0]
            spell_class = npc_info['class']
            item_type = npc_info['item_name']
            
            if spell_class != current_class:
                if current_class is not None:
                    html += '</div>'  # Close previous class group
                class_anchor = spell_class.lower().replace(' ', '-')
                html += f'<div id="class-{class_anchor}" style="grid-column: 1 / -1; margin-top: 20px;"><h3 style="color: #1976D2; border-bottom: 2px solid #1976D2; padding-bottom: 5px;">{spell_class}</h3></div>'
                html += '<div class="spell-grid" style="grid-column: 1 / -1;">'
                current_class = spell_class
                current_item_type = None  # Reset item type when class changes
            
            if item_type != current_item_type:
                html += f'<div style="grid-column: 1 / -1; margin-top: 10px; margin-bottom: 5px;"><strong style="color: #555; font-size: 1.05em;">{item_type}</strong></div>'
                current_item_type = item_type
        
        # Choose card style based on whether spell is found
        card_class = "has-spell" if spell['found'] else "no-spell"
        
        html += f"""
            <div class="spell-card {card_class}">
                <div class="spell-name">
                    <a href="https://www.takproject.net/allaclone/item.php?id={spell['id']}" target="_blank">{spell['name']}</a>
"""
        if not spell['found']:
            html += '<span style="color: #c62828; font-size: 0.9em; margin-left: 10px;">(Not Found)</span>'
        html += """
                </div>
"""
        # Only show "Available from" for not found spells
        if not spell['found']:
            html += """
                <div class="spell-sources">
                    <strong>Available from:</strong><br>
"""
            # Group NPCs by class
            npcs_by_class = defaultdict(list)
            for npc_info in spell['npcs']:
                npcs_by_class[npc_info['class']].append(npc_info)
            
            for npc_class in sorted(npcs_by_class.keys()):
                html += f"<strong>{npc_class}:</strong> "
                npc_names = []
                for npc_info in npcs_by_class[npc_class]:
                    npc_names.append(f"{npc_info['npc']} ({npc_info['item_name']})")
                html += ", ".join(npc_names) + "<br>"
            
            html += """
                </div>
"""
        if spell['found']:
            html += """
                <div class="char-list">
                    <strong>Found on:</strong><br>
"""
            for char_name, count in sorted(spell['chars']):
                html += f'<span class="char-item">{char_name}<span class="count">x{count}</span></span>'
            
            html += """
                </div>
"""
        html += """
            </div>
"""
    
    if current_class is not None:
        html += '</div>'  # Close last class group
    html += '</div>'
    
    # Character-by-character breakdown
    html += """
        <h2>Spells by Character</h2>
"""
    
    for char_name in sorted([c for c in MULE_CHARACTERS if c in char_ids]):
        char_spells = pok_spells[char_name]
        has_spells = bool(char_spells)
        section_class = "has-spells" if has_spells else "no-spells"
        
        html += f"""
        <div class="character-section {section_class}">
            <h3>{char_name}</h3>
"""
        
        if has_spells:
            html += f"<p><strong>PoK Spells Found: {sum(char_spells.values())} total</strong></p>"
            html += '<div class="spell-list">'
            # Sort by class, item type, then name
            sorted_spells = sorted(char_spells.items(), key=lambda x: get_spell_sort_key(x[0], spell_info))
            for spell_id, count in sorted_spells:
                spell_data = spell_info[spell_id]
                html += f"""
                <div class="spell-item">
                    <a href="https://www.takproject.net/allaclone/item.php?id={spell_id}" target="_blank">{spell_data['name']}</a>
                    <span class="spell-count">x{count}</span>
                </div>
"""
            html += '</div>'
        else:
            html += "<p><em>No PoK spells found.</em></p>"
        
        # Show other items (non-PoK spells) - grouped by item_id
        if char_name in all_items:
            other_items = [item for item in all_items[char_name] if item['item_id'] not in pok_spell_ids]
            if other_items:
                # Group items by item_id and count
                item_counts = defaultdict(lambda: {'name': '', 'count': 0})
                for item in other_items:
                    item_id = item['item_id']
                    item_counts[item_id]['name'] = item['item_name']
                    item_counts[item_id]['count'] += 1
                
                html += f"""
                <div class="other-items">
                    <h4>Other Items ({len(other_items)} total, {len(item_counts)} unique)</h4>
                    <div class="other-items-list">
"""
                # Sort by name, then by count
                sorted_items = sorted(item_counts.items(), key=lambda x: (x[1]['name'], -x[1]['count']))
                for item_id, item_data in sorted_items[:200]:  # Limit to 200 unique items
                    count_text = f" x{item_data['count']}" if item_data['count'] > 1 else ""
                    html += f'<div class="other-item"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #2196F3; text-decoration: none;">{item_data["name"]}</a>{count_text}</div>'
                if len(sorted_items) > 200:
                    html += f'<div class="other-item"><em>... and {len(sorted_items) - 200} more unique items</em></div>'
                html += "</div></div>"
        
        html += "</div>"
    
    # Officer Mules section
    if officer_inventories and officer_char_ids:
        html += """
        <h2>Officer Mules</h2>
"""
        for char_name in sorted([c for c in OFFICER_MULE_CHARACTERS if c in officer_char_ids]):
            char_spells = officer_pok_spells[char_name]
            has_spells = bool(char_spells)
            section_class = "has-spells" if has_spells else "no-spells"
            
            html += f"""
        <div class="character-section {section_class}">
            <h3>{char_name}</h3>
"""
            if has_spells:
                html += f"<p><strong>PoK Spells Found: {sum(char_spells.values())} total</strong></p>"
                html += '<div class="spell-list">'
                # Sort by class, item type, then name
                sorted_spells = sorted(char_spells.items(), key=lambda x: get_spell_sort_key(x[0], spell_info))
                for spell_id, count in sorted_spells:
                    spell_data = spell_info[spell_id]
                    html += f"""
                <div class="spell-item">
                    <a href="https://www.takproject.net/allaclone/item.php?id={spell_id}" target="_blank">{spell_data['name']}</a>
                    <span class="spell-count">x{count}</span>
                </div>
"""
                html += '</div>'
            else:
                html += "<p><em>No PoK spells found.</em></p>"
            
            # Show other items (non-PoK spells) - grouped by item_id
            if char_name in officer_all_items:
                other_items = [item for item in officer_all_items[char_name] if item['item_id'] not in pok_spell_ids]
                if other_items:
                    # Group items by item_id and count
                    item_counts = defaultdict(lambda: {'name': '', 'count': 0})
                    for item in other_items:
                        item_id = item['item_id']
                        item_counts[item_id]['name'] = item['item_name']
                        item_counts[item_id]['count'] += 1
                    
                    html += f"""
                <div class="other-items">
                    <h4>Other Items ({len(other_items)} total, {len(item_counts)} unique)</h4>
                    <div class="other-items-list">
"""
                    # Sort by name, then by count
                    sorted_items = sorted(item_counts.items(), key=lambda x: (x[1]['name'], -x[1]['count']))
                    for item_id, item_data in sorted_items[:200]:  # Limit to 200 unique items
                        count_text = f" x{item_data['count']}" if item_data['count'] > 1 else ""
                        html += f'<div class="other-item"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #2196F3; text-decoration: none;">{item_data["name"]}</a>{count_text}</div>'
                    if len(sorted_items) > 200:
                        html += f'<div class="other-item"><em>... and {len(sorted_items) - 200} more unique items</em></div>'
                    html += "</div></div>"
            
            html += "</div>"
    
    html += """
    <script>
    (function() {
        var itemSearchData = """ + item_search_json + """;
        var autocompleteNames = """ + autocomplete_names_json + """;
        var input = document.getElementById('item-search-input');
        var listEl = document.getElementById('autocomplete-list');
        var resultsEl = document.getElementById('search-results');
        var selectedIdx = -1;

        function showAutocomplete(query) {
            query = (query || '').trim().toLowerCase();
            if (!query) {
                listEl.style.display = 'none';
                listEl.innerHTML = '';
                return;
            }
            var matches = autocompleteNames.filter(function(name) {
                return name.toLowerCase().indexOf(query) !== -1;
            }).slice(0, 80);
            if (matches.length === 0) {
                listEl.style.display = 'none';
                listEl.innerHTML = '';
                return;
            }
            listEl.innerHTML = matches.map(function(name, i) {
                return '<li data-name="' + name.replace(/"/g, '&quot;') + '" data-idx="' + i + '">' + escapeHtml(name) + '</li>';
            }).join('');
            listEl.style.display = 'block';
            selectedIdx = 0;
            setSelected(0);
        }

        function escapeHtml(s) {
            var div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        function setSelected(idx) {
            var items = listEl.querySelectorAll('li');
            for (var i = 0; i < items.length; i++) {
                items[i].classList.toggle('selected', i === idx);
            }
            selectedIdx = idx;
            if (items[idx]) items[idx].scrollIntoView({ block: 'nearest' });
        }

        function runSearch(query) {
            query = (query || '').trim().toLowerCase();
            listEl.style.display = 'none';
            listEl.innerHTML = '';
            if (!query) {
                resultsEl.innerHTML = '';
                return;
            }
            var matches = itemSearchData.filter(function(item) {
                return (item.name || '').toLowerCase().indexOf(query) !== -1;
            });
            if (matches.length === 0) {
                resultsEl.innerHTML = '<p class="search-results-empty">No items on mules matching "' + escapeHtml(query) + '".</p>';
                return;
            }
            var html = '';
            for (var i = 0; i < matches.length; i++) {
                var item = matches[i];
                var name = escapeHtml(item.name || 'Unknown');
                var url = 'https://www.takproject.net/allaclone/item.php?id=' + encodeURIComponent(item.id);
                html += '<div class="item-result-card"><div class="item-name"><a href="' + url + '" target="_blank">' + name + '</a></div>';
                html += '<div class="char-list"><strong>Found on:</strong><br>';
                for (var j = 0; j < item.chars.length; j++) {
                    var c = item.chars[j];
                    var countStr = c[1] > 1 ? ' x' + c[1] : '';
                    html += '<span class="char-item">' + escapeHtml(c[0]) + '<span class="count">' + countStr + '</span></span>';
                }
                html += '</div></div>';
            }
            resultsEl.innerHTML = html;
        }

        input.addEventListener('input', function() {
            showAutocomplete(input.value);
        });
        input.addEventListener('keydown', function(e) {
            if (listEl.style.display !== 'block') {
                if (e.key === 'Enter') runSearch(input.value);
                return;
            }
            var items = listEl.querySelectorAll('li');
            if (e.key === 'ArrowDown') {
                e.preventDefault();
                setSelected(Math.min(selectedIdx + 1, items.length - 1));
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                setSelected(Math.max(selectedIdx - 1, 0));
            } else if (e.key === 'Enter' && items[selectedIdx]) {
                e.preventDefault();
                input.value = items[selectedIdx].getAttribute('data-name');
                runSearch(input.value);
            } else if (e.key === 'Escape') {
                listEl.style.display = 'none';
            }
        });
        listEl.addEventListener('click', function(e) {
            var li = e.target.closest('li');
            if (li) {
                input.value = li.getAttribute('data-name');
                runSearch(input.value);
            }
        });
        document.addEventListener('click', function(e) {
            if (!input.contains(e.target) && !listEl.contains(e.target)) {
                listEl.style.display = 'none';
            }
        });
    })();
    </script>
""" + GOATCOUNTER_SCRIPT + """    </div>
</body>
</html>
"""
    
    return html

def compare_character_data(current_data, previous_data, character_list=None):
    """Compare current and previous character data to find deltas.
    If character_list is None, compares all characters (serverwide)."""
    deltas = {}
    all_chars = set(list(current_data.keys()) + list(previous_data.keys()))
    
    for char_name in all_chars:
        if character_list is not None and char_name not in character_list:
            continue
            
        current = current_data.get(char_name, {})
        previous = previous_data.get(char_name, {})
        
        current_level = current.get('level', 0)
        previous_level = previous.get('level', 0)
        current_aa_total = current.get('aa_unspent', 0) + current.get('aa_spent', 0)
        previous_aa_total = previous.get('aa_unspent', 0) + previous.get('aa_spent', 0)
        current_hp = current.get('hp_max_total', 0)
        previous_hp = previous.get('hp_max_total', 0)
        
        # Detect deleted characters (not in current data, or level 0 in current but was > 0 in previous)
        is_deleted = (char_name not in current_data) or (current_level == 0 and previous_level > 0)
        # Export can include anon with 0 stats: in both snapshots one side 0 the other large = visibility change
        is_visibility_change = False
        if char_name in current_data and char_name in previous_data and not is_deleted:
            if (previous_aa_total == 0 and current_aa_total >= VISIBILITY_CHANGE_AA_THRESHOLD) or (
                current_aa_total == 0 and previous_aa_total >= VISIBILITY_CHANGE_AA_THRESHOLD
            ):
                is_visibility_change = True
            if (previous_hp == 0 and current_hp >= VISIBILITY_CHANGE_HP_THRESHOLD) or (
                current_hp == 0 and previous_hp >= VISIBILITY_CHANGE_HP_THRESHOLD
            ):
                is_visibility_change = True
        
        delta = {
            'name': char_name,
            'level_change': current_level - previous_level if current_level < 65 and not is_deleted else 0,  # Don't track level changes for 65 or deleted
            'aa_total_change': current_aa_total - previous_aa_total,
            'hp_change': current_hp - previous_hp,
            'current_level': current_level if not is_deleted else previous_level,  # Show previous level for deleted
            'previous_level': previous_level,
            'current_aa_total': current_aa_total if not is_deleted else previous_aa_total,  # Show previous AA for deleted
            'previous_aa_total': previous_aa_total,
            'current_hp': current_hp if not is_deleted else previous_hp,  # Show previous HP for deleted
            'previous_hp': previous_hp,
            'class': current.get('class', '') or previous.get('class', ''),
            'guild': current.get('guild', '') or previous.get('guild', ''),
            'is_new': char_name not in previous_data,
            'is_deleted': is_deleted,
            'is_visibility_change': is_visibility_change,
        }
        
        # Only include if there are changes or it's new/deleted
        # For level 65, only show if AA changed (and level 50+)
        # For < 65, show if level or AA changed (and level 50+ for AA)
        has_level_change = delta['level_change'] != 0 and current_level < 65 and not is_deleted
        has_aa_change = delta['aa_total_change'] != 0 and ((current_level >= 50 or previous_level >= 50) if not is_deleted else previous_level >= 50)
        
        # Include if HP shows 0 vs large (anon flip) so we mark is_visibility_change and exclude from HP leaderboard
        has_hp_visibility = (previous_hp == 0 and current_hp >= VISIBILITY_CHANGE_HP_THRESHOLD) or (
            current_hp == 0 and previous_hp >= VISIBILITY_CHANGE_HP_THRESHOLD
        )
        if has_level_change or has_aa_change or has_hp_visibility or delta['is_new'] or delta['is_deleted']:
            deltas[char_name] = delta
    
    return deltas

# Equipment slots (1-22 = worn slots; used to detect "no items -> any items" = corpse loot across day boundary)


def _parse_worn_slot_id(slot_id):
    """Return int 1-22 if worn slot, else None. Accepts int or str from TSV."""
    if slot_id is None:
        return None
    try:
        s = int(str(slot_id).strip())
        if 1 <= s <= 22:
            return s
    except (ValueError, TypeError):
        pass
    return None


def _item_id_counts_as_worn_equipped(item_id):
    """True if item_id is a real item (not empty/NULL/0). Used for corpse-loot heuristic."""
    if item_id is None:
        return False
    s = str(item_id).strip()
    if not s or s.upper() == 'NULL':
        return False
    try:
        return int(s) != 0
    except (ValueError, TypeError):
        return False


def count_equipped(items):
    """Return number of real items in worn slots (1-22). Rows with empty/NULL/0 item_id are ignored."""
    if not items:
        return 0
    return sum(
        1
        for it in items
        if _parse_worn_slot_id(it.get('slot_id')) is not None
        and _item_id_counts_as_worn_equipped(it.get('item_id'))
    )


def equipped_worn_by_char_from_inventories(char_data, inv_data):
    """Build { char_name: {'count': N} } for daily delta JSON (historical corpse-loot parity)."""
    names = set(char_data.keys()) | set(inv_data.keys())
    return {name: {'count': count_equipped(inv_data.get(name, []))} for name in names}


def chars_corpse_loot_excluded(current_inv, previous_inv):
    """Characters who went from 0 equipped to any equipped (likely looting a corpse across day boundary).
    Exclude them from delta, raid gear, and mob tracker."""
    excluded = set()
    all_chars = set(current_inv.keys()) | set(previous_inv.keys())
    for char_name in all_chars:
        prev_items = previous_inv.get(char_name, [])
        curr_items = current_inv.get(char_name, [])
        prev_equipped = count_equipped(prev_items)
        curr_equipped = count_equipped(curr_items)
        if prev_equipped == 0 and curr_equipped >= 1:
            excluded.add(char_name)
    return excluded


def load_no_rent_items():
    """Load list of no-rent item IDs from JSON file."""
    base_dir = os.path.dirname(__file__)
    no_rent_file = os.path.join(base_dir, "no_rent_items.json")
    
    if os.path.exists(no_rent_file):
        try:
            with open(no_rent_file, 'r') as f:
                item_ids = json.load(f)
                return set(item_ids)  # Convert to set for fast lookup
        except Exception as e:
            print(f"Warning: Could not load no_rent_items.json: {e}")
            return set()
    else:
        # File doesn't exist, return empty set (no filtering)
        return set()


def _load_item_ids_with_flag(flag_name: str) -> set:
    """Load item IDs from item_stats.json whose flags contain flag_name (e.g. NO DROP, LORE)."""
    base_dir = os.path.dirname(__file__)
    matched = set()
    for path in [os.path.join(base_dir, 'data', 'item_stats.json'), 'data/item_stats.json']:
        if not os.path.exists(path):
            continue
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for item_id_str, entry in data.items():
                flags = entry.get('flags') or []
                if isinstance(flags, str):
                    flags = [f.strip() for f in flags.split('|')]
                if flag_name in flags:
                    matched.add(str(item_id_str))
            return matched
        except Exception as e:
            print(f"Warning: Could not load item_stats for {flag_name!r}: {e}")
            return set()
    return set()


def load_no_drop_tracked_item_ids():
    """Load set of tracked item IDs that are NO DROP (from data/item_stats.json flags).
    Used to only count mob kills from non-no-drop loot when serverwide net change is positive."""
    return _load_item_ids_with_flag('NO DROP')


def load_lore_item_ids():
    """Load item IDs flagged LORE in item_stats.json (max one per character)."""
    return _load_item_ids_with_flag('LORE')


def load_unique_tracked_item_ids(tracked_ids=None):
    """Tracked raid/elemental/praesterium items that are LORE (unique per character)."""
    if tracked_ids is None:
        tracked_ids, _, _, _ = load_tracked_item_ids()
    return set(tracked_ids) & load_lore_item_ids() if tracked_ids else set()


def load_tracked_item_ids():
    """Load raid, elemental armor, and praesterium item IDs from the 3 JSON files.
    Returns (set of item_id strings, dict item_id -> source_label for display, dict item_id -> zone for raid items, dict item_id -> mob name).
    Raid items use mob name from JSON (e.g. 'Mob Name (Zone)'); others use category label."""
    base_dir = os.path.dirname(__file__)
    tracked = set()
    source_label = {}
    item_zone = {}  # raid item_id -> zone name (for "Items by zone" grouping)
    item_mob = {}   # raid item_id -> mob name (for "Items by zone" subheading by mob)
    # Raid: use mob (and zone) from JSON instead of "raid"
    raid_path = os.path.join(base_dir, "raid_item_sources.json")
    if os.path.exists(raid_path):
        try:
            with open(raid_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item_id, entry in data.items():
                sid = str(item_id)
                tracked.add(sid)
                mob = entry.get("mob", "").strip()
                zone = entry.get("zone", "").strip()
                if zone:
                    item_zone[sid] = zone
                if mob:
                    item_mob[sid] = mob
                if mob and zone:
                    source_label[sid] = f"{mob} ({zone})"
                elif mob:
                    source_label[sid] = mob
                else:
                    source_label[sid] = "Raid"
        except Exception as e:
            print(f"Warning: Could not load {raid_path}: {e}")
    for path, label, zone_name in [
        (os.path.join(base_dir, "elemental_armor.json"), "elemental armor", "Elemental"),
        (os.path.join(base_dir, "praesterium_loot.json"), "praesterium", "Praesterium"),
    ]:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item_id in data:
                sid = str(item_id)
                tracked.add(sid)
                source_label[sid] = label
                if zone_name:
                    item_zone[sid] = zone_name
                # no mob for elemental/praesterium; item_mob stays empty for these
        except Exception as e:
            print(f"Warning: Could not load {path}: {e}")
    return tracked, source_label, item_zone, item_mob


# Character stats: if in both snapshots but one has 0 AA and the other has >= this, treat as anon flip (export includes anon with zeros)
VISIBILITY_CHANGE_AA_THRESHOLD = 50
# HP: if one side 0 and the other >= this, treat as anon flip (anon export often has 0 HP)
VISIBILITY_CHANGE_HP_THRESHOLD = 500


def apply_visibility_change_to_char_deltas(char_deltas):
    """Set is_visibility_change on char_deltas that show 0 vs large level/AA/HP (anon flip).
    Use when char_deltas come from compare_delta_to_delta or from JSON, which don't set this."""
    for char_name, delta in char_deltas.items():
        if delta.get('is_visibility_change'):
            continue
        prev_aa = delta.get('previous_aa_total', 0)
        curr_aa = delta.get('current_aa_total', 0)
        prev_lvl = delta.get('previous_level', 0)
        curr_lvl = delta.get('current_level', 0)
        prev_hp = delta.get('previous_hp', 0)
        curr_hp = delta.get('current_hp', 0)
        if (prev_aa == 0 and curr_aa >= VISIBILITY_CHANGE_AA_THRESHOLD) or (
            curr_aa == 0 and prev_aa >= VISIBILITY_CHANGE_AA_THRESHOLD
        ) or (prev_lvl == 0 and curr_lvl >= 50) or (curr_lvl == 0 and prev_lvl >= 50) or (
            prev_hp == 0 and curr_hp >= VISIBILITY_CHANGE_HP_THRESHOLD
        ) or (curr_hp == 0 and prev_hp >= VISIBILITY_CHANGE_HP_THRESHOLD):
            delta['is_visibility_change'] = True


def compare_inventories(current_inv, previous_inv, character_list=None):
    """Compare current and previous inventories to find item deltas.
    If character_list is None, compares all characters (serverwide).
    No-rent items are automatically filtered out.
    Detects anon/not-anon visibility changes (many items only added or only removed) and marks them for graceful display."""
    item_deltas = {}
    
    # Load no-rent items to filter out
    no_rent_items = load_no_rent_items()
    if no_rent_items:
        print(f"Filtering out {len(no_rent_items)} no-rent items from delta comparison")
    
    # Get all characters from both inventories
    all_chars = set(list(current_inv.keys()) + list(previous_inv.keys()))
    if character_list is not None:
        all_chars = all_chars.intersection(set(character_list))
    
    for char_name in all_chars:
        if char_name not in current_inv and char_name not in previous_inv:
            continue
            
        current_items = defaultdict(int)
        previous_items = defaultdict(int)
        
        # Count items in current inventory (excluding no-rent)
        if char_name in current_inv:
            for item in current_inv[char_name]:
                item_id = item['item_id']
                # Convert to int for comparison with no-rent items set
                try:
                    item_id_int = int(item_id)
                    if item_id_int not in no_rent_items:  # Filter out no-rent items
                        current_items[item_id] += 1
                except (ValueError, TypeError):
                    # If item_id can't be converted, include it (shouldn't happen)
                    current_items[item_id] += 1
        
        # Count items in previous inventory (excluding no-rent)
        if char_name in previous_inv:
            for item in previous_inv[char_name]:
                item_id = item['item_id']
                # Convert to int for comparison with no-rent items set
                try:
                    item_id_int = int(item_id)
                    if item_id_int not in no_rent_items:  # Filter out no-rent items
                        previous_items[item_id] += 1
                except (ValueError, TypeError):
                    # If item_id can't be converted, include it (shouldn't happen)
                    previous_items[item_id] += 1
        
        # Find added and removed items
        added_items = {}
        removed_items = {}
        
        for item_id, count in current_items.items():
            prev_count = previous_items.get(item_id, 0)
            if count > prev_count:
                added_items[item_id] = count - prev_count
        
        for item_id, count in previous_items.items():
            curr_count = current_items.get(item_id, 0)
            if count > curr_count:
                removed_items[item_id] = count - curr_count
        
        if added_items or removed_items:
            in_current = char_name in current_inv
            in_previous = char_name in previous_inv
            # Primary: character in one snapshot but not the other = anon toggle (went anon or came not-anon).
            # We do not use arbitrary item-count thresholds; we have better mechanisms for anon detection.
            is_visibility_change = (not in_current and in_previous) or (in_current and not in_previous)
            item_deltas[char_name] = {
                'added': added_items,
                'removed': removed_items,
                'item_names': {},  # Will be populated with item names
                'is_visibility_change': is_visibility_change,
            }
    
    return item_deltas


def generate_mob_tracker_html(base_dir: str) -> str:
    """Generate static mob_tracker.html that loads mob_tracker_deaths.json and raid_item_sources.json
    and shows deaths in last 24h with repop window and % elapsed."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Raid Mob Repop Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px; }
        .sub { color: #666; margin-bottom: 16px; }
        a { color: #2196F3; }
        table { border-collapse: collapse; width: 100%; margin-top: 12px; }
        th, td { border: 1px solid #ddd; padding: 8px 10px; text-align: left; }
        th { background: #2196F3; color: white; }
        tr:nth-child(even) { background: #f9f9f9; }
        .in-window { background: #e8f5e9 !important; font-weight: bold; }
        .passed { color: #999; }
        .bar { height: 12px; background: #e0e0e0; border-radius: 4px; overflow: hidden; }
        .bar-fill { height: 100%; background: #4CAF50; }
        .no-data { color: #999; padding: 20px; }
    </style>
</head>
<body>
<div class="container">
    <h1>Raid Mob Repop Tracker</h1>
    <p class="sub">All mobs with observed loot (from delta); sorted by <strong>time to repop</strong> (soonest first).</p>
    <p class="sub"><a href="delta.html">Delta report</a></p>
    <details class="sub" style="margin-bottom: 12px; padding: 8px; background: #fff8e1; border-radius: 4px;" id="respawn-help">
        <summary style="cursor: pointer;">Respawn timers showing "—"?</summary>
        <p style="margin: 8px 0 0 0; font-size: 0.9em;">Repop data comes from <code>raid_item_sources.json</code>. Run <code>python update_raid_item_sources_from_db.py</code> (with DB connection or <code>--from-file</code>) to fill <code>respawn_seconds</code> from spawn2 and <code>respawn_note</code> for overrides (Emperor, Cursed, PoEarth, PoAir, Statue). Then commit and push the updated JSON so the deployed site has it.</p>
    </details>
    <div id="content">
        <p class="no-data">Loading…</p>
    </div>
    <p class="sub" id="updated" style="margin-top: 20px; font-size: 0.9em; color: #666;"></p>
</div>
<script>
(function() {
    function parseRespawnNote(note) {
        if (!note) return { baseSec: null, varianceSec: 0 };
        const pm = note.match(/([0-9.]+)\\s*±\\s*([0-9.]+)\\s*day/i);
        if (pm) return { baseSec: parseFloat(pm[1]) * 86400, varianceSec: parseFloat(pm[2]) * 86400 };
        const single = note.match(/([0-9.]+)\\s*day/i);
        if (single) return { baseSec: parseFloat(single[1]) * 86400, varianceSec: 0 };
        return { baseSec: null, varianceSec: 0 };
    }
    const OBSERVATION_WINDOW_MS = 24 * 3600 * 1000;  // Death could have been anytime in last 24h before we saw loot
    const DEFAULT_RESPAWN_VARIANCE_PCT = 0.10;      // ±10% when DB gives only base time (no note variance)
    const NEXT_HOURS_MS = 6 * 3600 * 1000;          // Chance to spawn in next 6 hours
    function buildRespawnMap(raidItemSources) {
        const map = {};
        for (const [itemId, entry] of Object.entries(raidItemSources)) {
            const zone = (entry.zone || "").trim();
            const mob = (entry.mob || "").trim();
            if (!zone && !mob) continue;
            const key = zone + "|" + mob;
            if (map[key]) continue;
            const baseSec = entry.respawn_seconds != null ? entry.respawn_seconds : null;
            const fromNote = parseRespawnNote(entry.respawn_note || "");
            const base = baseSec != null ? baseSec : fromNote.baseSec;
            let varianceSec = fromNote.varianceSec;
            if (base != null && varianceSec === 0) varianceSec = base * DEFAULT_RESPAWN_VARIANCE_PCT;
            map[key] = {
                respawn_seconds: baseSec,
                respawn_note: entry.respawn_note || "",
                baseSec: base,
                varianceSec: varianceSec
            };
        }
        return map;
    }
    function formatTime(ms) {
        const d = new Date(ms);
        return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
    }
    function formatDuration(sec) {
        if (sec == null) return "—";
        if (sec < 3600) return (sec / 60).toFixed(0) + "m";
        if (sec < 86400) return (sec / 3600).toFixed(1) + "h";
        return (sec / 86400).toFixed(1) + "d";
    }
    Promise.all([
        fetch("mob_tracker_deaths.json").then(r => r.ok ? r.json() : { updated: "", deaths: [] }),
        fetch("raid_item_sources.json").then(r => r.ok ? r.json() : {})
    ]).then(([deathsData, raidItemSources]) => {
        const respawnMap = buildRespawnMap(raidItemSources);
        const now = Date.now();
        const deaths = deathsData.deaths || [];
        document.getElementById("updated").textContent = "Deaths data updated: " + (deathsData.updated || "—") + " (up to 14 days; sorted by time to repop). Status and % use your browser time (now: " + new Date().toISOString().slice(0, 19) + "Z).";
        if (deaths.length === 0) {
            document.getElementById("content").innerHTML = "<p class=\\"no-data\\">No mob deaths recorded yet. Run the delta to populate.</p>";
            return;
        }
        const rows = deaths.map(d => {
            const key = (d.zone || "") + "|" + (d.mob || "");
            const resp = respawnMap[key] || {};
            const observedMs = new Date(d.observed_at || 0).getTime();
            const baseSec = resp.baseSec;
            const varianceSec = resp.varianceSec || 0;
            let status = "—";
            let pct = null;
            let windowStart = null;
            let windowEnd = null;
            let chanceNext6h = null;
            if (baseSec != null) {
                // Death happened sometime in the 24h before we observed loot; respawn has natural variance
                const earliestDeathMs = observedMs - OBSERVATION_WINDOW_MS;
                const latestDeathMs = observedMs;
                windowStart = earliestDeathMs + (baseSec - varianceSec) * 1000;
                windowEnd = latestDeathMs + (baseSec + varianceSec) * 1000;
                if (now < windowStart) status = "Not yet";
                else if (now > windowEnd) status = "Passed";
                else {
                    status = "In window";
                    pct = ((now - windowStart) / (windowEnd - windowStart)) * 100;
                }
                // Chance repop falls in [now, now+6h]: uniform over [windowStart, windowEnd], so overlap/windowLength
                if (windowStart != null && windowEnd != null && windowEnd > windowStart) {
                    const overlapStart = Math.max(now, windowStart);
                    const overlapEnd = Math.min(now + NEXT_HOURS_MS, windowEnd);
                    const overlap = Math.max(0, overlapEnd - overlapStart);
                    chanceNext6h = (overlap / (windowEnd - windowStart)) * 100;
                } else {
                    chanceNext6h = 0;
                }
            } else if (resp.respawn_note) {
                status = resp.respawn_note;
            }
            return {
                zone: d.zone || "—",
                mob: d.mob || "—",
                observed_at: d.observed_at,
                respawn_note: resp.respawn_note || (resp.respawn_seconds != null ? formatDuration(resp.respawn_seconds) + " (DB)" : "—"),
                window_start: windowStart,
                window_end: windowEnd,
                status,
                pct,
                chanceNext6h
            };
        });
        const rank = (r) => r.status === "Not yet" ? 0 : r.status === "In window" ? 1 : 2;
        const sortTime = (r) => r.status === "Not yet" ? (r.window_start || 0) : (r.window_end || r.window_start || 0);
        const sorted = [...rows].sort((a, b) => {
            const ra = rank(a), rb = rank(b);
            if (ra !== rb) return ra - rb;
            return sortTime(a) - sortTime(b);
        });
        let html = "<table><thead><tr><th>Zone</th><th>Mob</th><th>Died (observed)</th><th>Respawn</th><th>Window start</th><th>Window end</th><th>Status</th><th>% elapsed</th><th>Chance next 6h</th></tr></thead><tbody>";
        sorted.forEach(r => {
            const trClass = r.status === "In window" ? " class=\\"in-window\\"" : (r.status === "Passed" ? " class=\\"passed\\"" : "");
            html += "<tr" + trClass + ">";
            html += "<td>" + escapeHtml(r.zone) + "</td><td>" + escapeHtml(r.mob) + "</td>";
            html += "<td>" + escapeHtml(r.observed_at ? r.observed_at.slice(0, 19) + "Z" : "—") + "</td>";
            html += "<td>" + escapeHtml(r.respawn_note) + "</td>";
            html += "<td>" + (r.window_start ? formatTime(r.window_start) : "—") + "</td>";
            html += "<td>" + (r.window_end ? formatTime(r.window_end) : "—") + "</td>";
            html += "<td>" + escapeHtml(r.status) + "</td>";
            if (r.pct != null) {
                html += "<td><div class=\\"bar\\"><div class=\\"bar-fill\\" style=\\"width:" + Math.round(r.pct) + "%\\"></div></div> " + Math.round(r.pct) + "%</td>";
            } else {
                html += "<td>—</td>";
            }
            if (r.chanceNext6h != null) {
                html += "<td>" + (r.chanceNext6h < 0.5 ? "&lt;1" : Math.round(r.chanceNext6h)) + "%</td>";
            } else {
                html += "<td>—</td>";
            }
            html += "</tr>";
        });
        html += "</tbody></table>";
        document.getElementById("content").innerHTML = html;
    });
    function escapeHtml(s) {
        if (s == null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;");
    }
})();
</script>
''' + GOATCOUNTER_SCRIPT + '''
</body>
</html>
'''


# Server repop reset: every two Wednesdays (e.g. 2026-02-11, 2026-02-25). Deaths before the last reset are dropped.
REPOP_RESET_REFERENCE_WEDNESDAY = datetime(2026, 2, 11)  # First reset Wednesday


def is_repop_reset_day(when=None):
    """True if the given date (default today UTC) is an every-two-Wednesdays repop reset day."""
    if when is None:
        when = datetime.utcnow()
    d = when.date() if isinstance(when, datetime) else when
    ref = REPOP_RESET_REFERENCE_WEDNESDAY.date() if isinstance(REPOP_RESET_REFERENCE_WEDNESDAY, datetime) else REPOP_RESET_REFERENCE_WEDNESDAY
    if d.weekday() != 2:  # not Wednesday
        return False
    return (d - ref).days % 14 == 0


def get_last_repop_reset_utc(when=None):
    """Return the datetime (UTC, start of day) of the most recent repop reset on or before when."""
    if when is None:
        when = datetime.utcnow()
    d = when.date() if isinstance(when, datetime) else when
    ref = REPOP_RESET_REFERENCE_WEDNESDAY.date() if isinstance(REPOP_RESET_REFERENCE_WEDNESDAY, datetime) else REPOP_RESET_REFERENCE_WEDNESDAY
    days_since_ref = (d - ref).days
    if days_since_ref < 0:
        # Before ref: last reset on or before d is ref - 14*k for k = ceil((ref-d).days/14)
        reset_date = ref - timedelta(days=14 * math.ceil((ref - d).days / 14.0))
    else:
        back = days_since_ref % 14  # 0 = today is reset day, else days since last reset
        reset_date = d - timedelta(days=back)
    return datetime.combine(reset_date, datetime.min.time())


def _parse_respawn_note_py(note):
    """Return (base_sec, variance_sec) from respawn_note; (None, 0) if unparseable."""
    if not note or not note.strip():
        return (None, 0)
    note = note.strip()
    pm = re.match(r"([0-9.]+)\s*±\s*([0-9.]+)\s*day", note, re.I)
    if pm:
        return (float(pm.group(1)) * 86400, float(pm.group(2)) * 86400)
    single = re.match(r"([0-9.]+)\s*day", note, re.I)
    if single:
        return (float(single.group(1)) * 86400, 0)
    return (None, 0)


def _build_respawn_map_py(raid_item_sources):
    """Return dict (zone, mob) -> (base_sec, variance_sec). Default variance 10% when no note."""
    result = {}
    for _item_id, entry in raid_item_sources.items():
        zone = (entry.get("zone") or "").strip()
        mob = (entry.get("mob") or "").strip()
        if not zone and not mob:
            continue
        key = (zone, mob)
        if key in result:
            continue
        base = entry.get("respawn_seconds")
        if base is not None:
            base = int(base)
        note = entry.get("respawn_note") or ""
        from_note_base, from_note_var = _parse_respawn_note_py(note)
        if base is None:
            base = from_note_base
        variance = from_note_var
        if base is not None and variance == 0:
            variance = base * 0.10
        result[key] = (base, variance)
    return result


def save_mob_deaths_from_delta(zone_entries, output_path, observed_at=None, max_age_days=14,
                               raid_item_sources_path=None):
    """Append (zone, mob) from zone_entries to mob tracker deaths JSON. Do not overwrite existing deaths.
    - Load existing deaths from file.
    - If we have gone over a reset: remove entries with observed_at before the last reset.
    - Also drop entries older than max_age_days.
    - If raid_item_sources_path: drop deaths whose repop window ended more than 1 day ago.
    - Append/update one death per (zone, mob) seen this run; write back.
    zone_entries: dict zone -> mob -> list of (char_name, item_id, item_name).
    observed_at: ISO timestamp string (default: utcnow()). Use magelo pull time when available.
    """
    if observed_at is None:
        observed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(observed_at, datetime):
        observed_at = observed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    now_dt = datetime.utcnow()
    last_reset = get_last_repop_reset_utc(now_dt)
    age_cutoff = now_dt - timedelta(days=max_age_days)
    cutoff_dt = max(last_reset, age_cutoff)
    cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    respawn_map = {}
    if raid_item_sources_path and os.path.exists(raid_item_sources_path):
        try:
            with open(raid_item_sources_path, "r", encoding="utf-8") as f:
                respawn_map = _build_respawn_map_py(json.load(f))
        except Exception:
            pass

    data = {"updated": observed_at, "deaths": []}
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    deaths = [d for d in data.get("deaths", []) if (d.get("observed_at") or "") >= cutoff_iso]

    # Remove deaths whose repop window ended more than 1 day ago
    if respawn_map:
        one_day = timedelta(days=1)
        kept = []
        for d in deaths:
            key = (d.get("zone") or "").strip(), (d.get("mob") or "").strip()
            base, variance = respawn_map.get(key, (None, 0))
            if base is None:
                kept.append(d)
                continue
            try:
                obs_str = d.get("observed_at") or ""
                obs_dt = datetime.strptime(obs_str.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                window_end = obs_dt + timedelta(seconds=base + variance)
                if now_dt <= window_end + one_day:
                    kept.append(d)
            except Exception:
                kept.append(d)
        deaths = kept

    seen_this_run = set()
    for zone, mobs in zone_entries.items():
        for mob in mobs:
            key = (zone, mob)
            if key in seen_this_run:
                continue
            seen_this_run.add(key)
            found = False
            for d in deaths:
                if (d.get("zone"), d.get("mob")) == key:
                    d["observed_at"] = observed_at
                    found = True
                    break
            if not found:
                deaths.append({"zone": zone, "mob": mob, "observed_at": observed_at})
    data["deaths"] = deaths
    data["updated"] = observed_at
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def generate_delta_html(current_char_data, previous_char_data, current_inv, previous_inv, 
                        magelo_update_date, serverwide=True, char_deltas=None, inv_deltas=None,
                        mob_tracker_deaths_path=None, observed_at=None, raid_item_sources_path=None,
                        corpse_loot_chars=None, previous_export_date=None):
    """Generate HTML page showing deltas between current and previous magelo dump.
    If serverwide is True, compares all characters, otherwise only mules.
    If char_deltas and inv_deltas are provided, uses those instead of recalculating.
    If mob_tracker_deaths_path and observed_at are set, appends (zone, mob) from this delta to the mob tracker JSON.
    If raid_item_sources_path is set, used to drop deaths 1 day after repop window ends.
    If corpse_loot_chars is set, use it instead of inferring from current_inv vs previous_inv.
    If previous_export_date is set (e.g. from CI .magelo_previous_dump_date.txt), the page header
    shows both export timestamps for transparency."""
    
    # Compare character data (serverwide) if not provided
    if char_deltas is None:
        char_deltas = compare_character_data(current_char_data, previous_char_data, None if serverwide else None)
    
    # Compare inventories (serverwide) if not provided
    if inv_deltas is None:
        inv_deltas = compare_inventories(current_inv, previous_inv, None if serverwide else None)
    
    # Get item names for inventory deltas
    all_item_ids = set()
    for char_delta in inv_deltas.values():
        all_item_ids.update(char_delta['added'].keys())
        all_item_ids.update(char_delta['removed'].keys())
    
    # Try to get item names from current inventory
    item_names = {}
    for char_name, items in current_inv.items():
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
    
    # Load tracked item IDs (raid / elemental armor / praesterium) and filter deltas for that set
    tracked_ids, tracked_source_label, item_zone, item_mob = load_tracked_item_ids()
    unique_tracked = load_unique_tracked_item_ids(tracked_ids) if tracked_ids else set()
    prev_possession = possession_from_inv_snapshot(previous_inv)
    filter_unique_reacquires_in_inv_deltas(inv_deltas, prev_possession, unique_tracked)
    tracked_deltas = {}
    if tracked_ids:
        for char_name, delta in inv_deltas.items():
            added = {k: v for k, v in delta['added'].items() if str(k) in tracked_ids}
            removed = {k: v for k, v in delta['removed'].items() if str(k) in tracked_ids}
            if added or removed:
                tracked_deltas[char_name] = {
                    'added': added,
                    'removed': removed,
                    'item_names': {k: v for k, v in delta['item_names'].items() if str(k) in tracked_ids},
                    'is_visibility_change': delta.get('is_visibility_change', False),
                }
    
    # Characters who went 0 equipped -> any equipped (corpse loot across day boundary): exclude from delta/raid/mob tracker
    if corpse_loot_chars is None:
        corpse_loot_chars = chars_corpse_loot_excluded(current_inv, previous_inv)
    # Tracked item IDs that are NO DROP (from item_stats); non-no-drop tracked loot needs net-change verification for mob kill
    no_drop_tracked = load_no_drop_tracked_item_ids() & tracked_ids if tracked_ids else set()
    # Serverwide net change per tracked item (excluding corpse-loot chars) for non-no-drop kill verification
    net_change_tracked = defaultdict(int)
    for char_name, delta in tracked_deltas.items():
        if char_name in corpse_loot_chars:
            continue
        for item_id, c in (delta.get('added') or {}).items():
            net_change_tracked[item_id] += c
        for item_id, c in (delta.get('removed') or {}).items():
            net_change_tracked[item_id] -= c
    
    # Items by zone: only chars in BOTH snapshots (exclude visibility-change and corpse-loot); only raid zones
    # For non-no-drop tracked loot, only add (zone, mob) when serverwide net change for that item is positive
    # Structure: zone_entries[zone][mob] = [(char_name, item_id, item_name), ...]
    chars_in_both = set(current_inv.keys()) & set(previous_inv.keys())
    zone_entries = {}
    for char_name in tracked_deltas:
        if char_name not in chars_in_both or tracked_deltas[char_name].get('is_visibility_change') or char_name in corpse_loot_chars:
            continue
        delta = tracked_deltas[char_name]
        for item_id, count in (delta.get('added') or {}).items():
            # Lore tracked loot: only count as new if character did not possess it yesterday
            if str(item_id) in unique_tracked:
                if int(prev_possession.get(char_name, {}).get(str(item_id), 0) or 0) > 0:
                    continue
            # Non-no-drop tracked loot: only count toward mob kill if serverwide net change is positive
            if str(item_id) not in no_drop_tracked and net_change_tracked.get(item_id, 0) <= 0:
                continue
            zone = item_zone.get(str(item_id))
            if not zone:
                continue
            mob = item_mob.get(str(item_id), "")
            item_name = (delta.get('item_names') or {}).get(item_id, f"Item {item_id}")
            if zone not in zone_entries:
                zone_entries[zone] = {}
            if mob not in zone_entries[zone]:
                zone_entries[zone][mob] = []
            for _ in range(count):
                zone_entries[zone][mob].append((char_name, item_id, item_name))
    
    if zone_entries and mob_tracker_deaths_path and observed_at is not None:
        save_mob_deaths_from_delta(zone_entries, mob_tracker_deaths_path, observed_at=observed_at,
                                   raid_item_sources_path=raid_item_sources_path)
    
    # Leaderboards: only consider characters present in BOTH snapshots (explicit presence), minus corpse-loot
    chars_in_both = set(current_char_data.keys()) & set(previous_char_data.keys())
    chars_eligible_leaderboard = chars_in_both - corpse_loot_chars
    
    # For display: still compute visibility-change set (anon ↔ not-anon) for character table and visibility note
    visibility_change_chars = {name for name, inv_d in inv_deltas.items() if inv_d.get('is_visibility_change')}
    for name, char_d in char_deltas.items():
        if char_d.get('is_visibility_change'):
            visibility_change_chars.add(name)
    visibility_change_chars |= corpse_loot_chars
    
    # Calculate AA leaderboard (top gainers); only chars present in both snapshots, exclude new/deleted, visibility-change, and corpse-loot
    aa_leaderboard = []
    for char_name, delta in char_deltas.items():
        if char_name not in chars_eligible_leaderboard:
            continue
        if delta.get('is_deleted', False) or delta.get('is_new', False):
            continue
        if delta.get('is_visibility_change', False):
            continue
        current_level = delta['current_level']
        previous_level = delta['previous_level']
        aa_gain = delta['aa_total_change']
        
        # Only include if level 50+ and gained AA
        if (current_level >= 50 or previous_level >= 50) and aa_gain > 0:
            aa_leaderboard.append({
                'name': char_name,
                'class': delta['class'],
                'level': current_level,
                'aa_gain': aa_gain,
                'aa_total': delta['current_aa_total']
            })
    
    # Sort by AA gain (descending) and take top 20
    aa_leaderboard.sort(key=lambda x: x['aa_gain'], reverse=True)
    aa_leaderboard = aa_leaderboard[:20]
    
    # Calculate HP leaderboard (top gainers); only chars present in both snapshots, exclude new/deleted, visibility-change
    hp_leaderboard = []
    for char_name, delta in char_deltas.items():
        if char_name not in chars_eligible_leaderboard:
            continue
        if delta.get('is_deleted', False) or delta.get('is_new', False):
            continue
        if delta.get('is_visibility_change', False):
            continue
        current_level = delta['current_level']
        hp_gain = delta['hp_change']
        
        # Only include if gained HP (any level)
        if hp_gain > 0:
            hp_leaderboard.append({
                'name': char_name,
                'class': delta['class'],
                'level': current_level,
                'hp_gain': hp_gain,
                'hp_total': delta['current_hp']
            })
    
    # Sort by HP gain (descending) and take top 20
    hp_leaderboard.sort(key=lambda x: x['hp_gain'], reverse=True)
    hp_leaderboard = hp_leaderboard[:20]
    
    if previous_export_date and str(previous_export_date).strip():
        pe = str(previous_export_date).strip()
        intro_p = (
            '<p>Day-over-day comparison: previous Magelo export <code>%s</code> '
            '&rarr; current <code>%s</code>.</p>' % (escape(pe), escape(magelo_update_date))
        )
    else:
        intro_p = (
            '<p>Changes detected since previous magelo dump (last updated: %s)</p>'
            % escape(magelo_update_date)
        )
    
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Mule Delta Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #2196F3;
            padding-bottom: 10px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }
        .delta-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .delta-table th, .delta-table td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .delta-table th {
            background-color: #f0f0f0;
            font-weight: bold;
        }
        .positive {
            color: #4CAF50;
            font-weight: bold;
        }
        .negative {
            color: #f44336;
            font-weight: bold;
        }
        .neutral {
            color: #666;
        }
        .item-list {
            display: flex;
            flex-wrap: wrap;
            gap: 5px;
        }
        .item-badge {
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.9em;
        }
        .item-added {
            background-color: #e8f5e9;
            color: #2e7d32;
        }
        .item-removed {
            background-color: #ffebee;
            color: #c62828;
        }
        .no-changes {
            color: #999;
            font-style: italic;
        }
        .leaderboard {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }
        .leaderboard h2 {
            color: white;
            border-bottom: 2px solid rgba(255,255,255,0.3);
            padding-bottom: 10px;
            margin-top: 0;
        }
        .leaderboard-table {
            width: 100%;
            border-collapse: collapse;
            background-color: rgba(255,255,255,0.1);
            border-radius: 5px;
            overflow: hidden;
        }
        .leaderboard-table th {
            background-color: rgba(255,255,255,0.2);
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }
        .leaderboard-table td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .leaderboard-table tr:hover {
            background-color: rgba(255,255,255,0.15);
        }
        .rank-badge {
            display: inline-block;
            width: 30px;
            height: 30px;
            line-height: 30px;
            text-align: center;
            border-radius: 50%;
            font-weight: bold;
            margin-right: 10px;
        }
        .rank-1 { background-color: #FFD700; color: #000; }
        .rank-2 { background-color: #C0C0C0; color: #000; }
        .rank-3 { background-color: #CD7F32; color: #fff; }
        .rank-other { background-color: rgba(255,255,255,0.3); color: #fff; }
        .nav-menu {
            background-color: #f0f0f0;
            padding: 15px;
            border-radius: 5px;
            margin: 20px 0;
            border: 1px solid #ddd;
        }
        .nav-menu h3 {
            margin-top: 0;
            margin-bottom: 10px;
            color: #333;
            font-size: 1.1em;
        }
        .nav-links {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .nav-links a {
            padding: 8px 15px;
            background-color: #4CAF50;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            font-weight: bold;
            transition: background-color 0.3s;
        }
        .nav-links a:hover {
            background-color: #45a049;
        }
        .nav-links a.hp-link {
            background-color: #f5576c;
        }
        .nav-links a.hp-link:hover {
            background-color: #e0485a;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>TAKP Mule Delta Report</h1>
        """ + intro_p + """
        
        <div class="nav-menu">
            <h3>Jump to Section:</h3>
            <div class="nav-links">
"""
    
    # Split inventory deltas by level 1 (mules/traders) vs others; exclude corpse-loot chars from display
    inv_deltas_level1 = {}
    inv_deltas_others = {}
    for char_name, delta in inv_deltas.items():
        if char_name in corpse_loot_chars:
            continue
        # Check if character is level 1 in current data
        char_level = current_char_data.get(char_name, {}).get('level', 0)
        if char_level == 1:
            inv_deltas_level1[char_name] = delta
        else:
            inv_deltas_others[char_name] = delta
    
    # Calculate week and month for leaderboard links
    week_start = None
    month_start = None
    try:
        if magelo_update_date != 'Unknown':
            from datetime import datetime
            try:
                dt = datetime.strptime(magelo_update_date, '%a %b %d %H:%M:%S UTC %Y')
                date_str = dt.strftime('%Y-%m-%d')
            except:
                date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            from datetime import datetime
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        week_start = get_week_start(date_str)
        month_start = get_month_start(date_str)
    except Exception as e:
        print(f"Warning: Could not calculate week/month for leaderboard links: {e}")
    
    # Build navigation links based on what sections will be shown (Items by Zone first)
    nav_links = []
    if zone_entries:
        nav_links.append('<a href="#items-by-zone">📍 Items by Zone</a>')
    if aa_leaderboard:
        nav_links.append('<a href="#aa-leaderboard">🏆 AA Leaderboard</a>')
    if hp_leaderboard:
        nav_links.append('<a href="#hp-leaderboard" class="hp-link">❤️ HP Leaderboard</a>')
    if char_deltas:
        nav_links.append('<a href="#character-changes">Character Changes</a>')
    if inv_deltas_level1:
        nav_links.append('<a href="#inventory-changes-level1">Level 1 (Mules/Traders)</a>')
    if inv_deltas_others:
        nav_links.append('<a href="#inventory-changes">Inventory Changes</a>')
    if tracked_deltas:
        nav_links.append('<a href="#tracked-items" style="background-color: #FF9800;">📌 Tracked Items</a>')
    
    # Add weekly/monthly leaderboard links
    if week_start:
        nav_links.append(f'<a href="leaderboard_week_{week_start}.html" style="background-color: #2196F3;">📅 Weekly Leaderboard</a>')
    if month_start:
        nav_links.append(f'<a href="leaderboard_month_{month_start}.html" style="background-color: #9C27B0;">📆 Monthly Leaderboard</a>')
    # Add delta history link (for date range queries)
    nav_links.append('<a href="delta-history.html" style="background-color: #607D8B;">📜 Delta History</a>')
    # Raid mob repop tracker (deaths + repop windows)
    nav_links.append('<a href="mob_tracker.html" style="background-color: #795548;">⏱ Raid Mob Repop Tracker</a>')
    
    html += "".join(nav_links)
    html += """
            </div>
        </div>
"""
    
    # Items by zone (at top; raid + elemental + praesterium)
    if zone_entries:
        html += """
        <h2 id="items-by-zone">📍 Items by Zone</h2>
        <p><em>Tracked loot (raid, elemental, praesterium) acquired this period, grouped by zone. Only characters present in both snapshots.</em></p>
"""
        for zone in sorted(zone_entries.keys()):
            mobs = zone_entries[zone]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f5f5f5;">
            <h3 style="margin-top: 0;">{zone}</h3>
"""
            # Sort mobs: named mobs first (alphabetically), then "" (no mob) last
            for mob in sorted(mobs.keys(), key=lambda m: (m == "", m)):
                entries = mobs[mob]
                if mob:
                    html += f'            <h4 style="margin: 12px 0 6px 0; font-size: 1em; color: #555;">{mob}</h4>\n'
                html += """
            <ul style="margin: 0; padding-left: 20px;">
"""
                for char_name, item_id, item_name in entries:
                    guild = (current_char_data.get(char_name, {}) or {}).get('guild', '')
                    char_display = f"{char_name} &lt;{guild}&gt;" if guild else char_name
                    char_slug = char_name.lower().replace(' ', '_')
                    item_url = f"https://www.takproject.net/allaclone/item.php?id={item_id}"
                    magelo_url = f"https://www.takproject.net/magelo/character.php?char={char_slug}"
                    html += f'                <li><a href="{magelo_url}" target="_blank" style="text-decoration: none; font-weight: bold;">{char_display}</a>{char_timeline_link(char_name)} — <a href="{item_url}" target="_blank" style="color: #2e7d32;">{item_name}</a></li>\n'
                html += """
            </ul>
"""
            html += """
        </div>
"""
    
    # AA Leaderboard
    if aa_leaderboard:
        html += """
        <div class="leaderboard" id="aa-leaderboard">
            <h2>🏆 Top AA Gainers</h2>
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Character</th>
                        <th>Class</th>
                        <th>Level</th>
                        <th>AA Gained</th>
                        <th>Total AA</th>
                    </tr>
                </thead>
                <tbody>
"""
        for idx, entry in enumerate(aa_leaderboard, 1):
            rank_class = "rank-1" if idx == 1 else "rank-2" if idx == 2 else "rank-3" if idx == 3 else "rank-other"
            html += f"""
                    <tr>
                        <td><span class="rank-badge {rank_class}">{idx}</span></td>
                        <td><strong>{entry['name']}</strong>{char_timeline_link(entry['name'])}</td>
                        <td>{entry['class']}</td>
                        <td>{entry['level']}</td>
                        <td style="color: #4CAF50; font-weight: bold;">+{entry['aa_gain']}</td>
                        <td>{entry['aa_total']}</td>
                    </tr>
"""
        html += """
                </tbody>
            </table>
        </div>
"""
    
    # HP Leaderboard
    if hp_leaderboard:
        html += """
        <div class="leaderboard" id="hp-leaderboard" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <h2>❤️ Top HP Gainers</h2>
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Character</th>
                        <th>Class</th>
                        <th>Level</th>
                        <th>HP Gained</th>
                        <th>Total HP</th>
                    </tr>
                </thead>
                <tbody>
"""
        for idx, entry in enumerate(hp_leaderboard, 1):
            rank_class = "rank-1" if idx == 1 else "rank-2" if idx == 2 else "rank-3" if idx == 3 else "rank-other"
            html += f"""
                    <tr>
                        <td><span class="rank-badge {rank_class}">{idx}</span></td>
                        <td><strong>{entry['name']}</strong>{char_timeline_link(entry['name'])}</td>
                        <td>{entry['class']}</td>
                        <td>{entry['level']}</td>
                        <td style="color: #fff; font-weight: bold;">+{entry['hp_gain']}</td>
                        <td>{entry['hp_total']}</td>
                    </tr>
"""
        html += """
                </tbody>
            </table>
        </div>
"""
    
    html += """
"""
    
    # Character level and AA changes
    if char_deltas:
        html += """
        <h2 id="character-changes">Character Level & AA Changes</h2>
        <table class="delta-table">
            <thead>
                <tr>
                    <th>Character</th>
                    <th>Class</th>
                    <th>Level</th>
                    <th>Level Change</th>
                    <th>Total AA</th>
                    <th>AA Total Change</th>
                </tr>
            </thead>
            <tbody>
"""
        # Sort all deltas (skip inv-flagged visibility-change chars; they appear in the visibility note only)
        for char_name in sorted(char_deltas.keys()):
            delta = char_deltas[char_name]
            if char_name in visibility_change_chars:
                continue
            current_level = delta['current_level']
            is_deleted = delta.get('is_deleted', False)
            
            # Character name display - mark deleted characters
            if is_deleted:
                char_display = f'<strong style="color: #999; text-decoration: line-through;">{char_name}</strong>{char_timeline_link(char_name)} <span style="color: #f44336; font-size: 0.9em;">(Deleted)</span>'
            else:
                char_display = f'<strong>{char_name}</strong>{char_timeline_link(char_name)}'
            
            # Level change display (only hide if they were already 65 in previous dump)
            # Characters leveling 50-65 should show level changes
            if is_deleted:
                level_display = f'<span class="negative">Deleted (was {delta["previous_level"]})</span>'
            elif delta['previous_level'] == 65:
                # Was already 65, can't level anymore
                level_display = '<span class="neutral">—</span>'  # No level tracking for already-65
            else:
                # Show level changes for characters leveling (including those who just reached 65)
                level_class = "positive" if delta['level_change'] > 0 else "negative" if delta['level_change'] < 0 else "neutral"
                level_text = f"+{delta['level_change']}" if delta['level_change'] > 0 else str(delta['level_change'])
                level_display = f'<span class="{level_class}">{level_text} ({delta["previous_level"]} → {delta["current_level"]})</span>'
            
            # Total AA display
            if is_deleted:
                total_aa_display = f'<span style="color: #999;">{delta["previous_aa_total"]}</span>'
            elif current_level >= 50 or delta['previous_level'] >= 50:
                total_aa_display = str(delta['current_aa_total'])
            else:
                total_aa_display = '<span class="neutral">—</span>'  # No AA tracking for < 50
            
            # AA change display (only for level 50+)
            if is_deleted:
                # For deleted, show AA loss
                aa_total_change = delta['aa_total_change']
                aa_class = "negative"
                aa_text = f"{aa_total_change}" if aa_total_change < 0 else f"-{delta['previous_aa_total']}"
                aa_display = f'<span class="{aa_class}">{aa_text} (was {delta["previous_aa_total"]})</span>'
            elif current_level >= 50 or delta['previous_level'] >= 50:
                aa_total_change = delta['aa_total_change']
                aa_class = "positive" if aa_total_change > 0 else "negative" if aa_total_change < 0 else "neutral"
                aa_text = f"+{aa_total_change}" if aa_total_change > 0 else str(aa_total_change)
                aa_display = f'<span class="{aa_class}">{aa_text}</span>'
            else:
                aa_display = '<span class="neutral">—</span>'  # No AA tracking for < 50
            
            html += f"""
                <tr>
                    <td>{char_display}</td>
                    <td>{delta['class']}</td>
                    <td>{delta['previous_level'] if is_deleted else delta['current_level']}</td>
                    <td>{level_display}</td>
                    <td>{total_aa_display}</td>
                    <td>{aa_display}</td>
                </tr>
"""
        html += """
            </tbody>
        </table>
"""
    else:
        html += """
        <h2>Character Level & AA Changes</h2>
        <p class="no-changes">No level or AA changes detected.</p>
"""
    
    # Single visibility note (show once; sections below show only actual changes)
    all_vis = set(visibility_change_chars)
    if inv_deltas_level1:
        for c, d in inv_deltas_level1.items():
            if d.get('is_visibility_change'):
                all_vis.add(c)
    if inv_deltas_others:
        for c, d in inv_deltas_others.items():
            if d.get('is_visibility_change'):
                all_vis.add(c)
    if tracked_deltas:
        for c, d in tracked_deltas.items():
            if d.get('is_visibility_change'):
                all_vis.add(c)
    if all_vis:
        all_vis_sorted = sorted(all_vis)
        html += f"""
        <details id="visibility-note" style="color: #757575; margin: 15px 0; padding: 10px; background: #fafafa; border-radius: 5px; border-left: 4px solid #9e9e9e;">
            <summary style="cursor: pointer; font-style: italic;"><strong>Visibility change (anon ↔ not anon)</strong> — {len(all_vis_sorted)} character(s); their inventory and tracked item deltas are not listed below. Click to expand names.</summary>
            <p style="margin: 8px 0 0 0; font-size: 0.9em;">{', '.join(all_vis_sorted)}</p>
        </details>
"""
    
    # Level 1 inventory changes (mules/traders) — only actual changes
    if inv_deltas_level1:
        html += """
        <h2 id="inventory-changes-level1">Level 1 Inventory Changes (Mules/Traders)</h2>
        <p><em>Showing level 1 characters with inventory changes (limited to first 500 characters for performance)</em></p>
"""
        sorted_chars = sorted(inv_deltas_level1.keys())[:500]
        non_vis_level1 = [c for c in sorted_chars if not inv_deltas_level1[c].get('is_visibility_change')]
        for char_name in non_vis_level1:
            delta = inv_deltas_level1[char_name]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff9e6;">
            <h3><strong>{char_name}</strong>{char_timeline_link(char_name)} <span style="color: #666; font-size: 0.9em;">(Level 1 - Mule/Trader)</span></h3>
"""
            if delta['added']:
                html += """
            <div style="margin: 10px 0;">
                <strong style="color: #4CAF50;">Items Added:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                for item_id, count in sorted(delta['added'].items()):
                    item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                    count_text = f" x{count}" if count > 1 else ""
                    html += f'<span class="item-badge item-added"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #2e7d32; text-decoration: none;">{item_name}</a>{count_text}</span>'
                html += """
                </div>
            </div>
"""
            if delta['removed']:
                html += """
            <div style="margin: 10px 0;">
                <strong style="color: #f44336;">Items Removed:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                for item_id, count in sorted(delta['removed'].items()):
                    item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                    count_text = f" x{count}" if count > 1 else ""
                    html += f'<span class="item-badge item-removed"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #c62828; text-decoration: none;">{item_name}</a>{count_text}</span>'
                html += """
                </div>
            </div>
"""
            html += """
        </div>
"""
    
    # Regular inventory changes (non-level 1) — only actual changes
    if inv_deltas_others:
        html += """
        <h2 id="inventory-changes">Inventory Changes</h2>
        <p><em>Showing characters with inventory changes (limited to first 500 characters for performance)</em></p>
"""
        sorted_chars = sorted(inv_deltas_others.keys())[:500]
        non_vis_others = [c for c in sorted_chars if not inv_deltas_others[c].get('is_visibility_change')]
        for char_name in non_vis_others:
            delta = inv_deltas_others[char_name]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h3><strong>{char_name}</strong>{char_timeline_link(char_name)}</h3>
"""
            if delta['added']:
                    html += """
            <div style="margin: 10px 0;">
                <strong style="color: #4CAF50;">Items Added:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                    for item_id, count in sorted(delta['added'].items()):
                        item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                        count_text = f" x{count}" if count > 1 else ""
                        html += f'<span class="item-badge item-added"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #2e7d32; text-decoration: none;">{item_name}</a>{count_text}</span>'
                    html += """
                </div>
            </div>
"""
            if delta['removed']:
                html += """
            <div style="margin: 10px 0;">
                <strong style="color: #f44336;">Items Removed:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                for item_id, count in sorted(delta['removed'].items()):
                    item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                    count_text = f" x{count}" if count > 1 else ""
                    html += f'<span class="item-badge item-removed"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #c62828; text-decoration: none;">{item_name}</a>{count_text}</span>'
                html += """
                </div>
            </div>
"""
            html += """
        </div>
"""
    else:
        html += """
        <h2>Inventory Changes</h2>
        <p class="no-changes">No inventory changes detected.</p>
"""
    
    # Tracked Items section (raid / elemental armor / praesterium) — only actual changes
    if tracked_deltas:
        html += """
        <h2 id="tracked-items">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>
        <p><em>Changes in raid loot, elemental armor, and praesterium items — see who acquired or lost these.</em></p>
"""
        sorted_tracked = sorted(tracked_deltas.keys())
        non_vis_tracked = [c for c in sorted_tracked if not tracked_deltas[c].get('is_visibility_change') and c not in corpse_loot_chars]
        for char_name in non_vis_tracked:
            delta = tracked_deltas[char_name]
            char_level = current_char_data.get(char_name, {}).get('level', '?')
            guild = (current_char_data.get(char_name, {}) or {}).get('guild', '')
            char_display = f"{char_name} &lt;{guild}&gt;" if guild else char_name
            char_slug = char_name.lower().replace(' ', '_')
            magelo_url = f"https://www.takproject.net/magelo/character.php?char={char_slug}"
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff8e1;">
            <h3><a href="{magelo_url}" target="_blank" style="text-decoration: none; font-weight: bold;">{char_display}</a>{char_timeline_link(char_name)} <span style="color: #666; font-size: 0.9em;">(Level {char_level})</span></h3>
"""
            if delta['added']:
                html += """
            <div style="margin: 10px 0;">
                <strong style="color: #4CAF50;">Acquired:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                for item_id, count in sorted(delta['added'].items()):
                    item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                    source = tracked_source_label.get(str(item_id), "")
                    count_text = f" x{count}" if count > 1 else ""
                    label = f" ({source})" if source else ""
                    html += f'<span class="item-badge item-added"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #2e7d32; text-decoration: none;">{item_name}</a>{count_text}<span style="color: #888; font-size: 0.85em;">{label}</span></span>'
                html += """
                </div>
            </div>
"""
            if delta['removed']:
                html += """
            <div style="margin: 10px 0;">
                <strong style="color: #f44336;">Lost:</strong>
                <div class="item-list" style="margin-top: 5px;">
"""
                for item_id, count in sorted(delta['removed'].items()):
                    item_name = delta['item_names'].get(item_id, f"Item {item_id}")
                    source = tracked_source_label.get(str(item_id), "")
                    count_text = f" x{count}" if count > 1 else ""
                    label = f" ({source})" if source else ""
                    html += f'<span class="item-badge item-removed"><a href="https://www.takproject.net/allaclone/item.php?id={item_id}" target="_blank" style="color: #c62828; text-decoration: none;">{item_name}</a>{count_text}<span style="color: #888; font-size: 0.85em;">{label}</span></span>'
                html += """
                </div>
            </div>
"""
            html += """
        </div>
"""
    
    html += """
    </div>
""" + GOATCOUNTER_SCRIPT + """
</body>
</html>
"""
    
    return html

def generate_leaderboard_html(period_name, aa_leaderboard, hp_leaderboard, period_type):
    """Generate HTML for weekly or monthly leaderboard page."""
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP {period_name.title()} Leaderboard</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .leaderboard {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}
        .leaderboard h2 {{
            color: white;
            border-bottom: 2px solid rgba(255,255,255,0.3);
            padding-bottom: 10px;
            margin-top: 0;
        }}
        .leaderboard-table {{
            width: 100%;
            border-collapse: collapse;
            background-color: rgba(255,255,255,0.1);
            border-radius: 5px;
            overflow: hidden;
        }}
        .leaderboard-table th {{
            background-color: rgba(255,255,255,0.2);
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }}
        .leaderboard-table td {{
            padding: 10px 12px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        .rank-badge {{
            display: inline-block;
            width: 30px;
            height: 30px;
            line-height: 30px;
            text-align: center;
            border-radius: 50%;
            font-weight: bold;
            margin-right: 10px;
        }}
        .rank-1 {{ background-color: #FFD700; color: #000; }}
        .rank-2 {{ background-color: #C0C0C0; color: #000; }}
        .rank-3 {{ background-color: #CD7F32; color: #fff; }}
        .rank-other {{ background-color: rgba(255,255,255,0.3); color: #fff; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>TAKP {period_name} Leaderboard</h1>
"""
    
    # AA Leaderboard
    if aa_leaderboard:
        html += """
        <div class="leaderboard">
            <h2>🏆 Top AA Gainers</h2>
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Character</th>
                        <th>Class</th>
                        <th>Level</th>
                        <th>AA Gained</th>
                    </tr>
                </thead>
                <tbody>
"""
        for idx, entry in enumerate(aa_leaderboard, 1):
            rank_class = "rank-1" if idx == 1 else "rank-2" if idx == 2 else "rank-3" if idx == 3 else "rank-other"
            html += f"""
                    <tr>
                        <td><span class="rank-badge {rank_class}">{idx}</span></td>
                        <td><strong>{entry['name']}</strong>{char_timeline_link(entry['name'])}</td>
                        <td>{entry['class']}</td>
                        <td>{entry['level']}</td>
                        <td style="color: #fff; font-weight: bold;">+{entry['gain']}</td>
                    </tr>
"""
        html += """
                </tbody>
            </table>
        </div>
"""
    
    # HP Leaderboard
    if hp_leaderboard:
        html += """
        <div class="leaderboard" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <h2>❤️ Top HP Gainers</h2>
            <table class="leaderboard-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Character</th>
                        <th>Class</th>
                        <th>Level</th>
                        <th>HP Gained</th>
                    </tr>
                </thead>
                <tbody>
"""
        for idx, entry in enumerate(hp_leaderboard, 1):
            rank_class = "rank-1" if idx == 1 else "rank-2" if idx == 2 else "rank-3" if idx == 3 else "rank-other"
            html += f"""
                    <tr>
                        <td><span class="rank-badge {rank_class}">{idx}</span></td>
                        <td><strong>{entry['name']}</strong>{char_timeline_link(entry['name'])}</td>
                        <td>{entry['class']}</td>
                        <td>{entry['level']}</td>
                        <td style="color: #fff; font-weight: bold;">+{entry['gain']}</td>
                    </tr>
"""
        html += """
                </tbody>
            </table>
        </div>
"""
    
    html += """
    </div>
""" + GOATCOUNTER_SCRIPT + """
</body>
</html>
"""
    return html

def generate_date_range_delta_html(start_date, end_date, base_dir='delta_snapshots', magelo_update_date='Unknown'):
    """Generate HTML for a date range delta by loading and aggregating daily delta JSONs.
    
    Args:
        start_date: Start date string (YYYY-MM-DD)
        end_date: End date string (YYYY-MM-DD)
        base_dir: Base directory for daily delta JSONs
        magelo_update_date: Magelo update date string for display
    
    Returns:
        HTML string for the date range delta page
    """
    # Load and aggregate deltas for the date range
    range_deltas = get_date_range_deltas(start_date, end_date, base_dir)
    
    if not range_deltas or (not range_deltas.get('char_deltas') and not range_deltas.get('inv_deltas')):
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Date Range Delta Report</title>
</head>
<body>
    <h1>TAKP Date Range Delta Report</h1>
    <p>No delta data found for date range: {start_date} to {end_date}</p>
    <p>This may be because daily delta JSON files are not available for this date range.</p>
{GOATCOUNTER_SCRIPT}</body>
</html>"""
    
    # Use the existing generate_delta_html function but we need to reconstruct
    # the "current" and "previous" data structures from the aggregated deltas
    # For now, we'll create a simplified version that shows the aggregated changes
    
    # Reconstruct character data from deltas (approximate)
    current_char_data = {}
    previous_char_data = {}
    for char_name, delta in range_deltas['char_deltas'].items():
        current_char_data[char_name] = {
            'level': delta.get('current_level', 0),
            'aa_unspent': 0,  # We don't track unspent/spent separately in deltas
            'aa_spent': 0,
            'aa_total': delta.get('current_aa_total', 0),
            'hp_max_total': delta.get('current_hp', 0),
            'class': delta.get('class', '')
        }
        previous_char_data[char_name] = {
            'level': delta.get('previous_level', 0),
            'aa_unspent': 0,
            'aa_spent': 0,
            'aa_total': delta.get('previous_aa_total', 0),
            'hp_max_total': delta.get('previous_hp', 0),
            'class': delta.get('class', '')
        }
    
    # Generate HTML using the existing function
    # Note: We pass empty inventories since we're focusing on character changes
    # Inventory changes are shown separately in the aggregated deltas
    html = generate_delta_html(
        current_char_data, previous_char_data,
        {}, {},  # Empty inventories - inventory deltas handled separately
        magelo_update_date,
        serverwide=True,
        char_deltas=range_deltas['char_deltas'],
        inv_deltas=range_deltas['inv_deltas']
    )
    
    # Add a header note about the date range
    header_note = f"""
    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 5px solid #2196F3;">
        <h2 style="margin-top: 0; color: #1976D2;">Date Range: {start_date} to {end_date}</h2>
        <p>This report shows aggregated changes across {start_date} to {end_date}, reconstructed from the gear event log when available.</p>
        <p><strong>Note:</strong> This is a reconstructed view. For the most recent daily changes, see the <a href="delta.html">current delta report</a>.</p>
    </div>
"""
    
    # Insert the header note after the opening container div
    html = html.replace('<div class="container">', '<div class="container">' + header_note)
    
    return html


def _count_meaningful_char_deltas(char_deltas):
    """Count char rows with real stat changes (exclude visibility-only)."""
    n = 0
    for _name, d in (char_deltas or {}).items():
        if d.get('is_visibility_change'):
            continue
        if (
            d.get('level_change')
            or d.get('aa_total_change')
            or d.get('hp_change')
            or d.get('is_new')
            or d.get('is_deleted')
        ):
            n += 1
    return n


def _count_inv_event_rows(inv_deltas):
    return sum(
        len((row.get("added") or {})) + len((row.get("removed") or {}))
        for row in (inv_deltas or {}).values()
    )


def _previous_export_date_str(base_dir, date_str):
    path = os.path.join(base_dir, ".magelo_previous_dump_date.txt")
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                pt = parse_takp_magelo_export_datetime(f.read())
            if pt:
                return pt.strftime("%Y-%m-%d")
        except OSError:
            pass
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return (dt - timedelta(days=1)).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _resolve_day_over_day_deltas(
    previous_char_data,
    previous_inventories,
    current_char_data,
    current_inventories,
    date_str,
    base_dir,
    baseline,
):
    """Prefer delta_daily pair when dump diff looks like stale-cache cumulative inflation."""
    char_deltas = compare_character_data(current_char_data, previous_char_data, None)
    inv_deltas = compare_inventories(current_inventories, previous_inventories, None)

    delta_snapshots_dir = os.path.join(base_dir, "delta_snapshots")
    prev_date = _previous_export_date_str(base_dir, date_str)
    if not prev_date or prev_date >= date_str:
        return char_deltas, inv_deltas

    da = load_daily_delta_json(prev_date, delta_snapshots_dir)
    db = load_daily_delta_json(date_str, delta_snapshots_dir)
    baseline_chars = (baseline or {}).get("characters")
    if not da or not db:
        return char_deltas, inv_deltas
    if da.get("baseline_date") != db.get("baseline_date"):
        return char_deltas, inv_deltas
    if not daily_json_pair_usable_for_delta_html_json_compare(da, db, baseline_chars):
        return char_deltas, inv_deltas

    daily_diff = compare_delta_to_delta(da, db, baseline_chars)
    daily_char = daily_diff.get("char_deltas") or {}
    daily_inv = daily_diff.get("inv_deltas") or {}
    dump_char_n = _count_meaningful_char_deltas(char_deltas)
    daily_char_n = _count_meaningful_char_deltas(daily_char)
    dump_inv_n = _count_inv_event_rows(inv_deltas)
    daily_inv_n = _count_inv_event_rows(daily_inv)
    if (dump_inv_n > daily_inv_n * 3 and dump_inv_n > daily_inv_n + 500) or (
        dump_char_n > daily_char_n * 3 and dump_char_n > daily_char_n + 500
    ):
        print(
            f"Warning: dump diff for {date_str} looks inflated "
            f"({dump_inv_n} inv rows vs {daily_inv_n} from delta_daily pair); "
            f"using delta_daily pair for gear events and delta.html"
        )
        char_deltas = daily_char
        inv_deltas = daily_inv
    return char_deltas, inv_deltas


def _warn_if_event_dump_divergence(event_day, dump_char, dump_inv, date_str):
    """Log when gear-event fold for a day diverges sharply from Magelo dump diff."""
    event_char = event_day.get('char_deltas') or {}
    event_inv = event_day.get('inv_deltas') or {}
    dump_char_n = _count_meaningful_char_deltas(dump_char)
    event_char_n = _count_meaningful_char_deltas(event_char)
    dump_inv_n = len(dump_inv or {})
    event_inv_n = len(event_inv or {})
    char_ratio = event_char_n / max(dump_char_n, 1)
    inv_ratio = event_inv_n / max(dump_inv_n, 1)
    if char_ratio > 3 and event_char_n > dump_char_n + 500:
        print(
            f"Warning: gear events for {date_str} show {event_char_n} char changes "
            f"vs {dump_char_n} from dump diff ({char_ratio:.1f}x); delta.html uses dump diff"
        )
    if inv_ratio > 3 and event_inv_n > dump_inv_n + 500:
        print(
            f"Warning: gear events for {date_str} show {event_inv_n} inventory char rows "
            f"vs {dump_inv_n} from dump diff ({inv_ratio:.1f}x); delta.html uses dump diff"
        )


def load_item_id_to_name(base_dir):
    """Load full item_id -> name map from data/item_id_to_name.json."""
    path = os.path.join(base_dir, 'data', 'item_id_to_name.json')
    if not os.path.exists(path):
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {str(k): str(v).strip() for k, v in data.items() if v}
    except (json.JSONDecodeError, OSError):
        return {}


def build_tracked_item_id_to_name(base_dir, tracked_ids=None):
    """Build id -> display name map for tracked items (delta-history client embed)."""
    if tracked_ids is None:
        tracked_ids, _, _, _ = load_tracked_item_ids()
    tracked_ids = {str(i) for i in (tracked_ids or set())}
    name_map = {}
    data_dir = os.path.join(base_dir, 'data')
    name_to_id_path = os.path.join(data_dir, 'item_name_to_id.json')
    if os.path.exists(name_to_id_path):
        try:
            with open(name_to_id_path, 'r', encoding='utf-8') as f:
                for name, iid in json.load(f).items():
                    sid = str(iid)
                    if sid in tracked_ids:
                        name_map[sid] = name
        except (json.JSONDecodeError, OSError):
            pass
    stats_path = os.path.join(data_dir, 'item_stats.json')
    if os.path.exists(stats_path):
        try:
            with open(stats_path, 'r', encoding='utf-8') as f:
                stats = json.load(f)
            for sid, entry in stats.items():
                sid = str(sid)
                if sid not in tracked_ids or sid in name_map:
                    continue
                if isinstance(entry, dict) and entry.get('name'):
                    name_map[sid] = entry['name']
        except (json.JSONDecodeError, OSError):
            pass
    praesterium_path = os.path.join(base_dir, 'praesterium_loot.json')
    if os.path.exists(praesterium_path):
        try:
            with open(praesterium_path, 'r', encoding='utf-8') as f:
                for sid, entry in json.load(f).items():
                    sid = str(sid)
                    if sid not in tracked_ids or sid in name_map:
                        continue
                    if isinstance(entry, dict) and entry.get('name'):
                        name_map[sid] = entry['name']
        except (json.JSONDecodeError, OSError):
            pass
    return name_map


def build_char_guild_map(char_file):
    """Build name -> guild map for delta-history display (non-empty guilds only)."""
    if not char_file or not os.path.isfile(char_file):
        return {}
    char_data = parse_character_data(char_file, None)
    return {
        name: (row.get('guild') or '').strip()
        for name, row in char_data.items()
        if (row.get('guild') or '').strip()
    }


def char_timeline_link(char_name: str) -> str:
    """HTML fragment: Δ link to on-demand character timeline page."""
    url = "char.html?c=" + quote(char_name, safe="")
    return (
        f' <a href="{escape(url, quote=True)}" title="Character timeline" '
        f'style="text-decoration:none;font-size:0.85em;">Δ</a>'
    )


def _gear_event_page_embed_config(base_dir: str) -> dict:
    """Shared embed config for delta-history and char timeline pages."""
    import glob

    delta_snapshots_dir = os.path.join(base_dir, "delta_snapshots")
    tracked_ids, tracked_source_label, item_zone, item_mob = load_tracked_item_ids()
    unique_tracked = load_unique_tracked_item_ids(tracked_ids)
    gear_shard_months: list[str] = []
    use_gear_events = gear_events_available(delta_snapshots_dir)
    gear_event_manifest: dict = {}
    event_dates: list[str] = []
    if use_gear_events:
        event_dates = list_available_event_dates(delta_snapshots_dir)
        gear_events_root = os.path.join(delta_snapshots_dir, "gear_events")
        if os.path.isdir(gear_events_root):
            for name in os.listdir(gear_events_root):
                m = re.match(r"^gear_(\d{4}-\d{2})\.json\.gz$", name)
                if m:
                    gear_shard_months.append(m.group(1))
            gear_shard_months.sort()
        manifest_path = os.path.join(gear_events_root, "manifest.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    gear_event_manifest = json.load(mf)
            except (json.JSONDecodeError, OSError):
                pass
    dates_seen: set[str] = set(event_dates)
    for filepath in glob.glob(os.path.join(delta_snapshots_dir, "delta_daily_*.json.gz")):
        match = re.match(r"delta_daily_(\d{4}-\d{2}-\d{2})\.json(\.gz)?", os.path.basename(filepath))
        if match:
            dates_seen.add(match.group(1))
    sorted_dates_asc = sorted(dates_seen)
    char_dir = os.path.join(base_dir, "character")
    char_file_for_guild = os.path.join(char_dir, "TAKP_character.txt")
    if not os.path.isfile(char_file_for_guild):
        char_file_for_guild = find_latest_magelo_file(char_dir, "TAKP_character")
    no_rent_for_js = sorted(int(x) for x in (load_no_rent_items() or set()))
    return {
        "tracked_ids_json": json.dumps(list(tracked_ids)),
        "tracked_source_label_json": json.dumps(tracked_source_label),
        "tracked_item_zone_json": json.dumps(item_zone),
        "tracked_item_mob_json": json.dumps(item_mob),
        "unique_tracked_ids_json": json.dumps(list(unique_tracked)),
        "gear_shard_months_json": json.dumps(gear_shard_months),
        "use_gear_events_json": "true" if use_gear_events else "false",
        "gear_event_manifest_json": json.dumps(gear_event_manifest),
        "item_id_to_name_json": json.dumps(load_item_id_to_name(base_dir)),
        "char_guild_map_json": json.dumps(build_char_guild_map(char_file_for_guild)),
        "no_rent_json": json.dumps(no_rent_for_js),
        "sorted_dates_asc": sorted_dates_asc,
        "latest_date": sorted_dates_asc[-1] if sorted_dates_asc else "",
    }


def _gear_event_fetch_client_js() -> str:
    """Shared browser Cache API helpers for gzip JSON under delta_snapshots/."""
    return """
        const GEAR_EVENT_CACHE_NAME = 'takp-gear-events-v1';
        const GEAR_EVENT_CACHE_TTL_MS = 86400000;

        function inflateGzArrayBuffer(arrayBuffer) {
            return JSON.parse(pako.inflate(new Uint8Array(arrayBuffer), { to: 'string' }));
        }

        async function readCachedGzJson(cache, url) {
            const cached = await cache.match(url);
            if (!cached) return null;
            const ts = parseInt(cached.headers.get('x-cached-at') || '0', 10);
            if (!ts || (Date.now() - ts) >= GEAR_EVENT_CACHE_TTL_MS) {
                await cache.delete(url);
                return null;
            }
            return inflateGzArrayBuffer(await cached.arrayBuffer());
        }

        async function storeCachedGz(cache, url, arrayBuffer) {
            const headers = new Headers();
            headers.set('Content-Type', 'application/gzip');
            headers.set('x-cached-at', String(Date.now()));
            await cache.put(url, new Response(arrayBuffer, { headers }));
        }

        async function fetchGzJsonCached(url, { optional = false } = {}) {
            let cache = null;
            try {
                cache = await caches.open(GEAR_EVENT_CACHE_NAME);
                const fromCache = await readCachedGzJson(cache, url);
                if (fromCache !== null) return fromCache;
            } catch (e) {
                cache = null;
            }
            const response = await fetch(url);
            if (!response.ok) {
                if (optional) return null;
                throw new Error('Failed to load: ' + url + ' (HTTP ' + response.status + ')');
            }
            const arrayBuffer = await response.arrayBuffer();
            if (cache) {
                try {
                    await storeCachedGz(cache, url, arrayBuffer);
                } catch (e) { /* ignore cache write errors */ }
            }
            return inflateGzArrayBuffer(arrayBuffer);
        }
"""


def normalize_loot_filters(filters, item_id_to_name=None):
    """Normalize loot filter dict from delta-history UI (zone / mob / item)."""
    item_id_to_name = item_id_to_name or {}
    zone = (filters.get("zone") or "").strip()
    mob = (filters.get("mob") or "").strip()
    item_id = str(filters.get("itemId") or filters.get("item_id") or "").strip()
    item_name = (filters.get("itemName") or filters.get("item_name") or "").strip()
    if not item_id and item_name:
        needle = item_name.lower()
        for iid, name in item_id_to_name.items():
            if (name or "").lower() == needle:
                item_id = str(iid)
                break
    return {"zone": zone, "mob": mob, "itemId": item_id, "itemName": item_name}


def item_matches_loot_filters(
    item_id,
    loot_filters,
    tracked_item_zone,
    tracked_item_mob,
    item_id_to_name=None,
):
    """Return True if item passes active loot filters (AND logic)."""
    item_id_to_name = item_id_to_name or {}
    tracked_item_zone = tracked_item_zone or {}
    tracked_item_mob = tracked_item_mob or {}
    zone_f = loot_filters.get("zone") or ""
    mob_f = loot_filters.get("mob") or ""
    item_id_f = loot_filters.get("itemId") or ""
    item_name_f = loot_filters.get("itemName") or ""
    if not zone_f and not mob_f and not item_id_f and not item_name_f:
        return True
    sid = str(item_id)
    if zone_f:
        item_zone = tracked_item_zone.get(sid, "")
        if zone_f.lower() not in item_zone.lower():
            return False
    if mob_f:
        item_mob = tracked_item_mob.get(sid, "")
        if mob_f.lower() not in item_mob.lower():
            return False
    if item_id_f:
        if sid != str(item_id_f):
            return False
    elif item_name_f:
        name = item_id_to_name.get(sid) or f"Item {sid}"
        if item_name_f.lower() not in name.lower():
            return False
    return True


def build_range_filter_index(
    zone_entries,
    tracked_deltas,
    item_id_to_name=None,
    tracked_item_zone=None,
    tracked_item_mob=None,
):
    """Build autocomplete index from range report loot (zones, mobs, items present)."""
    item_id_to_name = item_id_to_name or {}
    tracked_item_zone = tracked_item_zone or {}
    tracked_item_mob = tracked_item_mob or {}
    zones = sorted(zone_entries.keys())
    mobs_by_zone = {}
    all_mobs = set()
    items_seen = set()
    items = []

    for zone, mobs in zone_entries.items():
        mob_list = []
        for mob, entries in mobs.items():
            mob_key = mob or ""
            if mob_key not in mob_list:
                mob_list.append(mob_key)
            if mob_key:
                all_mobs.add(mob_key)
            for entry in entries:
                iid = str(entry.get("itemId") or entry.get("item_id") or "")
                if not iid or iid in items_seen:
                    continue
                items_seen.add(iid)
                items.append(
                    {
                        "id": iid,
                        "name": entry.get("name") or item_id_to_name.get(iid) or f"Item {iid}",
                        "zone": zone,
                        "mob": mob_key,
                    }
                )
        mobs_by_zone[zone] = sorted(mob_list, key=lambda x: (x == "", x))

    for _char_name, delta in (tracked_deltas or {}).items():
        item_names = delta.get("item_names") or {}
        for item_id in (delta.get("added") or {}):
            sid = str(item_id)
            if sid in items_seen:
                continue
            items_seen.add(sid)
            items.append(
                {
                    "id": sid,
                    "name": item_names.get(item_id)
                    or item_names.get(sid)
                    or item_id_to_name.get(sid)
                    or f"Item {sid}",
                    "zone": tracked_item_zone.get(sid, ""),
                    "mob": tracked_item_mob.get(sid, ""),
                }
            )

    items.sort(key=lambda x: x["name"].lower())
    return {
        "zones": zones,
        "mobsByZone": mobs_by_zone,
        "allMobs": sorted(all_mobs),
        "items": items,
    }


def filter_zone_entries(
    zone_entries,
    loot_filters,
    tracked_item_zone,
    tracked_item_mob,
    item_id_to_name=None,
):
    """Filter Items-by-Zone tree by loot filters."""
    loot_filters = normalize_loot_filters(loot_filters, item_id_to_name)
    if not any(loot_filters.get(k) for k in ("zone", "mob", "itemId", "itemName")):
        return zone_entries
    out = {}
    zone_f = loot_filters.get("zone") or ""
    mob_f = loot_filters.get("mob") or ""
    for zone, mobs in zone_entries.items():
        if zone_f and zone_f.lower() not in zone.lower():
            continue
        filtered_mobs = {}
        for mob, entries in mobs.items():
            mob_str = mob or ""
            if mob_f and mob_f.lower() not in mob_str.lower():
                continue
            filtered_entries = [
                e
                for e in entries
                if item_matches_loot_filters(
                    e.get("itemId"),
                    loot_filters,
                    tracked_item_zone,
                    tracked_item_mob,
                    item_id_to_name,
                )
            ]
            if filtered_entries:
                filtered_mobs[mob] = filtered_entries
        if filtered_mobs:
            out[zone] = filtered_mobs
    return out


def filter_tracked_deltas(
    tracked_deltas,
    loot_filters,
    tracked_item_zone,
    tracked_item_mob,
    item_id_to_name=None,
):
    """Filter tracked item deltas by loot filters; drops visibility-only rows."""
    loot_filters = normalize_loot_filters(loot_filters, item_id_to_name)
    if not any(loot_filters.get(k) for k in ("zone", "mob", "itemId", "itemName")):
        return tracked_deltas
    out = {}
    for char_name, delta in (tracked_deltas or {}).items():
        if delta.get("is_visibility_change"):
            continue
        added = {}
        removed = {}
        item_names = dict(delta.get("item_names") or {})
        for item_id, count in (delta.get("added") or {}).items():
            if item_matches_loot_filters(
                item_id,
                loot_filters,
                tracked_item_zone,
                tracked_item_mob,
                item_id_to_name,
            ):
                added[item_id] = count
        for item_id, count in (delta.get("removed") or {}).items():
            if item_matches_loot_filters(
                item_id,
                loot_filters,
                tracked_item_zone,
                tracked_item_mob,
                item_id_to_name,
            ):
                removed[item_id] = count
        if added or removed:
            out[char_name] = {
                "added": added,
                "removed": removed,
                "item_names": item_names,
                "is_visibility_change": False,
            }
    return out


def default_delta_history_range_endpoints(dates_asc, max_gap_days=14):
    """Pick default start/end dates for delta-history.html (see generate_delta_history).

    Avoid defaulting to ``dates_asc[-2:]`` when the two newest files are far apart on
    the calendar (sparse repo), which makes the UI look like a multi-month gain.
    """
    if not dates_asc:
        return '', ''
    end = dates_asc[-1]
    if len(dates_asc) < 2:
        return end, end
    d_end = datetime.strptime(end, '%Y-%m-%d')
    for i in range(len(dates_asc) - 2, -1, -1):
        cand = dates_asc[i]
        gap = (d_end - datetime.strptime(cand, '%Y-%m-%d')).days
        if 0 < gap <= max_gap_days:
            return cand, end
    return end, end


def generate_delta_history(base_dir):
    """Generate a history page listing all available daily delta JSON files.
    Allows generating date-to-date delta comparisons on demand."""
    import glob
    import re
    
    # Load tracked item IDs so we can embed them for the client-side report (Tracked Items + Items by zone)
    tracked_ids, tracked_source_label, item_zone, item_mob = load_tracked_item_ids()
    tracked_ids_json = json.dumps(list(tracked_ids))
    tracked_source_json = json.dumps(tracked_source_label)
    tracked_item_zone_json = json.dumps(item_zone)
    tracked_item_mob_json = json.dumps(item_mob)
    # Tracked item IDs that are NO DROP (for mob kill verification: non-no-drop only counts when net change > 0)
    no_drop_tracked = load_no_drop_tracked_item_ids() & tracked_ids if tracked_ids else set()
    no_drop_tracked_json = json.dumps(list(no_drop_tracked))
    unique_tracked = load_unique_tracked_item_ids(tracked_ids) if tracked_ids else set()
    unique_tracked_json = json.dumps(list(unique_tracked))
    no_rent_for_js = sorted(int(x) for x in (load_no_rent_items() or set()))
    no_rent_json = json.dumps(no_rent_for_js)
    
    # Find all daily delta JSON files and gear event dates
    delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
    delta_files = []
    event_dates: list[str] = []
    gear_shard_months: list[str] = []
    use_gear_events = gear_events_available(delta_snapshots_dir)
    if use_gear_events:
        event_dates = list_available_event_dates(delta_snapshots_dir)
        gear_events_root = os.path.join(delta_snapshots_dir, 'gear_events')
        if os.path.isdir(gear_events_root):
            for name in os.listdir(gear_events_root):
                m = re.match(r'^gear_(\d{4}-\d{2})\.json\.gz$', name)
                if m:
                    gear_shard_months.append(m.group(1))
            gear_shard_months.sort()
    
    if os.path.exists(delta_snapshots_dir):
        # Find all delta_daily_YYYY-MM-DD.json.gz files (compressed, legacy)
        delta_files.extend(glob.glob(os.path.join(delta_snapshots_dir, "delta_daily_*.json.gz")))
    
    # Extract dates from filenames and sort
    dates_seen: set[str] = set()
    delta_entries = []
    for filepath in delta_files:
        filename = os.path.basename(filepath)
        # Match both .json and .json.gz files
        match = re.match(r'delta_daily_(\d{4}-\d{2}-\d{2})\.json(\.gz)?', filename)
        if match:
            date_str = match.group(1)
            dates_seen.add(date_str)
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                delta_entries.append({
                    'date': date_str,
                    'date_formatted': dt.strftime('%B %d, %Y'),
                    'filename': filename,
                    'filepath': filepath,
                    'timestamp': os.path.getmtime(filepath)
                })
            except Exception:
                pass
    for date_str in event_dates:
        if date_str in dates_seen:
            continue
        dates_seen.add(date_str)
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
            delta_entries.append({
                'date': date_str,
                'date_formatted': dt.strftime('%B %d, %Y'),
                'filename': '',
                'filepath': '',
                'timestamp': 0,
            })
        except Exception:
            pass
    
    # Sort by date (newest first)
    delta_entries.sort(key=lambda x: x['date'], reverse=True)
    sorted_dates_asc = sorted(e['date'] for e in delta_entries)
    default_range_start, default_range_end = default_delta_history_range_endpoints(
        sorted_dates_asc, max_gap_days=14
    )
    sorted_dates_json = json.dumps(sorted_dates_asc)
    gear_shard_months_json = json.dumps(gear_shard_months)
    use_gear_events_json = 'true' if use_gear_events else 'false'
    gear_event_manifest_json = '{}'
    if use_gear_events:
        manifest_path = os.path.join(delta_snapshots_dir, 'gear_events', 'manifest.json')
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, 'r', encoding='utf-8') as mf:
                    gear_event_manifest_json = json.dumps(json.load(mf))
            except (json.JSONDecodeError, OSError):
                pass
    item_id_to_name_json = json.dumps(build_tracked_item_id_to_name(base_dir, tracked_ids))
    char_dir = os.path.join(base_dir, 'character')
    char_file_for_guild = os.path.join(char_dir, 'TAKP_character.txt')
    if not os.path.isfile(char_file_for_guild):
        char_file_for_guild = find_latest_magelo_file(char_dir, 'TAKP_character')
    char_guild_map_json = json.dumps(build_char_guild_map(char_file_for_guild))
    
    # Generate HTML with date-to-date comparison interface
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Delta History & Date Range Generator</title>
    <script src="https://cdn.jsdelivr.net/npm/pako@2.1.0/dist/pako.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }
        h1 {
            color: #333;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }
        h2 {
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }
        .nav-links {
            margin: 20px 0;
            padding: 15px;
            background: #f5f5f5;
            border-radius: 5px;
        }
        .nav-links a {
            color: #667eea;
            text-decoration: none;
            margin-right: 20px;
            font-weight: bold;
        }
        .nav-links a:hover {
            text-decoration: underline;
        }
        .date-range-form {
            background: #e8f4f8;
            padding: 20px;
            border-radius: 5px;
            margin: 20px 0;
        }
        .date-range-form h3 {
            margin-top: 0;
            color: #1976D2;
        }
        .form-group {
            margin: 15px 0;
        }
        .form-group label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
            color: #333;
        }
        .form-group input {
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-size: 1em;
            width: 200px;
        }
        .form-group button {
            padding: 10px 20px;
            background: #4CAF50;
            color: white;
            border: none;
            border-radius: 4px;
            font-size: 1em;
            cursor: pointer;
            font-weight: bold;
        }
        .form-group button:hover {
            background: #45a049;
        }
        .stats {
            margin: 20px 0;
            padding: 15px;
            background: #e8f4f8;
            border-radius: 5px;
        }
        .stats strong {
            color: #667eea;
        }
        .delta-list {
            margin-top: 30px;
        }
        .delta-entry {
            padding: 15px;
            margin: 10px 0;
            background: #f9f9f9;
            border-left: 4px solid #667eea;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .delta-date {
            color: #666;
            font-size: 0.9em;
        }
        .delta-date strong {
            color: #333;
        }
        .info-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
            border-radius: 5px;
        }
        .info-box strong {
            color: #856404;
        }
        .report-filters {
            background: #f3e5f5;
            padding: 16px 20px;
            border-radius: 5px;
            margin: 16px 0 0 0;
            border-left: 4px solid #9c27b0;
        }
        .report-filters h4 {
            margin: 0 0 8px 0;
            color: #6a1b9a;
        }
        .report-filters .filter-hint {
            margin: 0 0 12px 0;
            font-size: 0.9em;
            color: #555;
        }
        .loot-filter-row {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            margin-bottom: 12px;
        }
        .loot-filter-field {
            flex: 1 1 220px;
            min-width: 200px;
        }
        .loot-filter-field label {
            display: block;
            margin-bottom: 4px;
            font-weight: bold;
            font-size: 0.9em;
            color: #333;
        }
        .loot-filter-wrap {
            position: relative;
        }
        .loot-filter-wrap input {
            width: 100%;
            padding: 8px 10px;
            border: 2px solid #9c27b0;
            border-radius: 4px;
            font-size: 0.95em;
            box-sizing: border-box;
        }
        .loot-filter-wrap input:focus {
            outline: none;
            border-color: #7b1fa2;
        }
        .autocomplete-list {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            max-height: 220px;
            overflow-y: auto;
            background: white;
            border: 2px solid #9c27b0;
            border-top: none;
            border-radius: 0 0 4px 4px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.15);
            z-index: 100;
            list-style: none;
            margin: 0;
            padding: 0;
        }
        .autocomplete-list li {
            padding: 8px 10px;
            cursor: pointer;
            border-bottom: 1px solid #eee;
            font-size: 0.9em;
        }
        .autocomplete-list li:hover,
        .autocomplete-list li.selected {
            background: #f3e5f5;
        }
        .autocomplete-list li:last-child {
            border-bottom: none;
        }
        #clear-loot-filters {
            padding: 8px 16px;
            background: #757575;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
        }
        #clear-loot-filters:hover {
            background: #616161;
        }
        #loot-filter-active-banner {
            margin: 10px 0 0 0;
            padding: 8px 12px;
            background: #ede7f6;
            border-radius: 4px;
            font-size: 0.9em;
            color: #4527a0;
        }
        .tracked-items-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 8px;
            font-size: 0.95em;
        }
        .tracked-items-table th,
        .tracked-items-table td {
            padding: 6px 10px;
            border-bottom: 1px solid #eee;
            text-align: left;
        }
        .tracked-items-table th {
            background: #fafafa;
            color: #555;
            font-weight: bold;
        }
        .tracked-items-table .pos { color: #2e7d32; font-weight: bold; }
        .tracked-items-table .neg { color: #c62828; font-weight: bold; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📜 TAKP Delta History & Date Range Generator</h1>
        <div class="nav-links">
            <a href="delta.html">← Current Delta Report</a>
            <a href="spell_inventory.html">← Spell Inventory</a>
        </div>
        
        <div class="info-box">
            <strong>ℹ️ How it works:</strong> History is stored as dated gear +/- events under <code>delta_snapshots/gear_events/</code> (true day-over-day changes). Pick two dates below to aggregate events in that range. Legacy cumulative <code>delta_daily_*.json.gz</code> files are still loaded as a fallback when event shards are missing.
            <br><small>Default start/end prefers the latest snapshot and the newest prior file within 14 calendar days (so sparse archives do not open on a long gap by mistake).</small>
        </div>
        
        <div class="date-range-form">
            <h3>Generate Date-to-Date Delta Report</h3>
            <p>Select start and end dates, then use the generated command to create a date range report:</p>
            <div class="form-group">
                <label for="start_date">Start Date:</label>
                <input type="date" id="start_date" name="start" required>
            </div>
            <div class="form-group">
                <label for="end_date">End Date:</label>
                <input type="date" id="end_date" name="end" required>
            </div>
            <div class="form-group">
                <button type="button" onclick="generateDateRangeReport()" style="background: #4CAF50; color: white; padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer;">Generate Report</button>
            </div>
            <div id="report-filters" class="report-filters" style="display:none;">
                <h4>Filter loot in this report</h4>
                <p class="filter-hint">Narrow <strong>Items by Zone</strong> and <strong>Tracked Items</strong> only (AA/HP leaderboards, character changes, and inventory lists stay unchanged).</p>
                <div class="loot-filter-row">
                    <div class="loot-filter-field">
                        <label for="loot-filter-zone">Zone / raid</label>
                        <div class="loot-filter-wrap">
                            <input type="text" id="loot-filter-zone" autocomplete="off" placeholder="e.g. Plane of Time">
                            <ul class="autocomplete-list" id="loot-filter-zone-list" style="display:none;"></ul>
                        </div>
                    </div>
                    <div class="loot-filter-field">
                        <label for="loot-filter-mob">Mob</label>
                        <div class="loot-filter-wrap">
                            <input type="text" id="loot-filter-mob" autocomplete="off" placeholder="e.g. Emperor Salaris">
                            <ul class="autocomplete-list" id="loot-filter-mob-list" style="display:none;"></ul>
                        </div>
                    </div>
                    <div class="loot-filter-field">
                        <label for="loot-filter-item">Item</label>
                        <div class="loot-filter-wrap">
                            <input type="text" id="loot-filter-item" autocomplete="off" placeholder="e.g. Crown of Deceit">
                            <ul class="autocomplete-list" id="loot-filter-item-list" style="display:none;"></ul>
                        </div>
                    </div>
                </div>
                <button type="button" id="clear-loot-filters">Clear filters</button>
                <p id="loot-filter-active-banner" style="display:none;"></p>
            </div>
            <div id="date_range_output" style="margin-top: 20px; padding: 15px; background: #f9f9f9; border-radius: 5px; min-height: 50px;"></div>
        </div>
        
        <div class="stats">
            <strong>Available history dates:</strong> """ + str(len(delta_entries)) + """
            <br><small>Range reports sum gear events with start &lt; event date ≤ end (same as <code>get_date_range_deltas</code> when events are present).</small>
        </div>
        
        <div class="delta-list">
            <h2>Available Dates</h2>
"""
    
    if delta_entries:
        html += "            <p>Click a date to set the range end to that day and the start to the previous available day:</p>\n"
        html += "            <div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-top: 15px;'>\n"
        for entry in delta_entries:
            html += f"""
                <div class="delta-entry" style="flex-direction: column; align-items: flex-start; cursor: pointer;" 
                     onclick="setDateRangeFromTile('{entry['date']}');">
                    <strong>{entry['date_formatted']}</strong>
                    <div class="delta-date">{entry['date']}</div>
                </div>
"""
        html += "            </div>\n"
    else:
        html += """
            <p>No daily delta JSON files found yet. Daily deltas will appear here once they are generated.</p>
            <p><em>Note: Daily delta JSONs are automatically saved when the delta report is generated.</em></p>
"""
    
    html += """
        </div>
    </div>
    <script type="application/json" id="tracked-item-ids">""" + tracked_ids_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-source-label">""" + tracked_source_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-item-zone">""" + tracked_item_zone_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-item-mob">""" + tracked_item_mob_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="no-drop-tracked-ids">""" + no_drop_tracked_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="unique-tracked-ids">""" + unique_tracked_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="no-rent-item-ids">""" + no_rent_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="sorted-available-dates">""" + sorted_dates_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="gear-event-shard-months">""" + gear_shard_months_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="gear-event-manifest">""" + gear_event_manifest_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="item-id-to-name">""" + item_id_to_name_json.replace("</", "<\\/") + """</script>
    <script type="application/json" id="char-guild-map">""" + char_guild_map_json.replace("</", "<\\/") + """</script>
    <script>
        const TRACKED_ITEM_IDS = new Set(JSON.parse((document.getElementById('tracked-item-ids') || { textContent: '[]' }).textContent));
        const TRACKED_SOURCE_LABEL = JSON.parse((document.getElementById('tracked-source-label') || { textContent: '{}' }).textContent);
        const TRACKED_ITEM_ZONE = JSON.parse((document.getElementById('tracked-item-zone') || { textContent: '{}' }).textContent);
        const TRACKED_ITEM_MOB = JSON.parse((document.getElementById('tracked-item-mob') || { textContent: '{}' }).textContent);
        const NO_DROP_TRACKED_IDS = new Set(JSON.parse((document.getElementById('no-drop-tracked-ids') || { textContent: '[]' }).textContent));
        const UNIQUE_TRACKED_IDS = new Set(JSON.parse((document.getElementById('unique-tracked-ids') || { textContent: '[]' }).textContent));
        const NO_RENT_ITEMS = new Set(JSON.parse((document.getElementById('no-rent-item-ids') || { textContent: '[]' }).textContent).map(String));
        const SORTED_AVAILABLE_DATES = JSON.parse((document.getElementById('sorted-available-dates') || { textContent: '[]' }).textContent);
        const GEAR_EVENT_SHARD_MONTHS = JSON.parse((document.getElementById('gear-event-shard-months') || { textContent: '[]' }).textContent);
        const GEAR_EVENT_MANIFEST = JSON.parse((document.getElementById('gear-event-manifest') || { textContent: '{}' }).textContent);
        const ITEM_ID_TO_NAME = JSON.parse((document.getElementById('item-id-to-name') || { textContent: '{}' }).textContent);
        const CHAR_GUILD_MAP = JSON.parse((document.getElementById('char-guild-map') || { textContent: '{}' }).textContent);
        const USE_GEAR_EVENTS = """ + use_gear_events_json + """;
        const DEFAULT_RANGE_START = """ + json.dumps(default_range_start) + """;
        const DEFAULT_RANGE_END = """ + json.dumps(default_range_end) + """;
        const MAX_RANGE_GAP_DAYS = 14;

        function guildForChar(name, state) {
            const fromState = state && state.guild;
            if (fromState) return fromState;
            return (CHAR_GUILD_MAP && CHAR_GUILD_MAP[name]) || '';
        }

        function formatCharDisplay(name, state) {
            const g = guildForChar(name, state);
            return g ? (name + ' &lt;' + g + '&gt;') : name;
        }

        function charTimelineLink(name) {
            return ' <a href="char.html?c=' + encodeURIComponent(name) + '" title="Character timeline" style="text-decoration:none;font-size:0.85em;">Δ</a>';
        }

        function charStateForName(name, startState, endState) {
            return (endState && endState[name]) || (startState && startState[name]) || {};
        }
        
        function setDateRangeFromTile(endDate) {
            const idx = SORTED_AVAILABLE_DATES.indexOf(endDate);
            let startDate = endDate;
            if (idx > 0) {
                const endMs = new Date(endDate + 'T00:00:00').getTime();
                for (let i = idx - 1; i >= 0; i--) {
                    const cand = SORTED_AVAILABLE_DATES[i];
                    const gap = (endMs - new Date(cand + 'T00:00:00').getTime()) / 86400000;
                    if (gap > 0 && gap <= MAX_RANGE_GAP_DAYS) {
                        startDate = cand;
                        break;
                    }
                }
            }
            document.getElementById('start_date').value = startDate;
            document.getElementById('end_date').value = endDate;
        }
        
        if (DEFAULT_RANGE_END) {
            document.getElementById('end_date').value = DEFAULT_RANGE_END;
            document.getElementById('start_date').value = DEFAULT_RANGE_START || DEFAULT_RANGE_END;
        }
        
        // Load JSONs on-demand (only when date range is selected)
        let loadedDeltas = new Map(); // Cache loaded deltas
        let loadedBaselines = new Map(); // Cache loaded baselines
        let availableDates = new Set(); // Track which dates have JSON files
        
        // Extract available dates from the page (from the date list)
        SORTED_AVAILABLE_DATES.forEach(d => availableDates.add(d));
        document.querySelectorAll('.delta-date').forEach(el => {
            const date = el.textContent.trim();
            if (date.match(/^\\d{4}-\\d{2}-\\d{2}$/)) {
                availableDates.add(date);
            }
        });
        
        async function loadDeltaJSON(date) {
            // Check if date is available
            if (!availableDates.has(date)) {
                throw new Error(`No delta JSON file available for ${date}. Please select a date from the available dates list.`);
            }
            
            if (loadedDeltas.has(date)) {
                return loadedDeltas.get(date);
            }
            try {
                const response = await fetch(`delta_snapshots/delta_daily_${date}.json.gz`);
                if (!response.ok) {
                    if (response.status === 404) {
                        throw new Error(`Delta JSON file not found for ${date}. This date may not have been processed yet.`);
                    }
                    throw new Error(`Failed to load delta for ${date}: HTTP ${response.status}`);
                }
                const arrayBuffer = await response.arrayBuffer();
                // Decompress using pako
                const decompressed = pako.inflate(new Uint8Array(arrayBuffer), { to: 'string' });
                const delta = JSON.parse(decompressed);
                loadedDeltas.set(date, delta);
                return delta;
            } catch (error) {
                console.error(`Error loading delta for ${date}:`, error);
                throw error; // Re-throw so caller can handle it
            }
        }

""" + _gear_event_fetch_client_js() + """
        let loadedGearShards = new Map();
        let loadedCharShards = new Map();

        function monthsBetween(start, end) {
            const out = [];
            const sy = parseInt(start.slice(0, 4), 10);
            const sm = parseInt(start.slice(5, 7), 10);
            const ey = parseInt(end.slice(0, 4), 10);
            const em = parseInt(end.slice(5, 7), 10);
            let y = sy, m = sm;
            while (y < ey || (y === ey && m <= em)) {
                out.push(`${y}-${String(m).padStart(2, '0')}`);
                m += 1;
                if (m > 12) { m = 1; y += 1; }
            }
            return out;
        }

        async function loadGearShard(month) {
            if (loadedGearShards.has(month)) return loadedGearShards.get(month);
            const url = `delta_snapshots/gear_events/gear_${month}.json.gz`;
            const events = await fetchGzJsonCached(url);
            loadedGearShards.set(month, events);
            return events;
        }

        async function loadCharShard(month) {
            if (loadedCharShards.has(month)) return loadedCharShards.get(month);
            const url = `delta_snapshots/gear_events/char_${month}.json.gz`;
            const events = await fetchGzJsonCached(url, { optional: true });
            const result = events || [];
            loadedCharShards.set(month, result);
            return result;
        }

        async function loadEventsInRange(start, end) {
            const months = monthsBetween(start.slice(0, 7), end.slice(0, 7))
                .filter(m => !GEAR_EVENT_SHARD_MONTHS.length || GEAR_EVENT_SHARD_MONTHS.includes(m));
            const gearShards = await Promise.all(
                months.map(month => loadGearShard(month).catch(() => []))
            );
            const charShards = await Promise.all(months.map(month => loadCharShard(month)));
            const gear = gearShards.flat();
            const chars = charShards.flat();
            const gearFiltered = gear.filter(ev => ev.d > start && ev.d <= end);
            const charFiltered = chars.filter(ev => ev.d > start && ev.d <= end);
            return { gear: gearFiltered, char: charFiltered };
        }

        function gearManifestFirstEventMonthForDate(dateStr) {
            const eras = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.eras) || [];
            for (let i = eras.length - 1; i >= 0; i--) {
                const era = eras[i];
                if (era.first_event && era.first_event <= dateStr) {
                    return era.first_event.slice(0, 7);
                }
            }
            return (GEAR_EVENT_SHARD_MONTHS.length ? GEAR_EVENT_SHARD_MONTHS[0] : dateStr.slice(0, 7));
        }

        async function loadCharEventsUpTo(endDate, onProgress) {
            if (!GEAR_EVENT_SHARD_MONTHS.length) return [];
            const firstMonth = gearManifestFirstEventMonthForDate(endDate);
            const months = monthsBetween(firstMonth, endDate.slice(0, 7))
                .filter(m => GEAR_EVENT_SHARD_MONTHS.includes(m));
            let done = 0;
            const shardResults = await Promise.all(months.map(async (month) => {
                const events = await loadCharShard(month);
                done += 1;
                if (onProgress) onProgress(done, months.length);
                return events;
            }));
            const chars = shardResults.flat();
            return chars.filter(ev => ev.d && ev.d <= endDate);
        }

        async function loadGearEventsUpTo(endDate, onProgress) {
            if (!GEAR_EVENT_SHARD_MONTHS.length) return [];
            const firstMonth = gearManifestFirstEventMonthForDate(endDate);
            const months = monthsBetween(firstMonth, endDate.slice(0, 7))
                .filter(m => GEAR_EVENT_SHARD_MONTHS.includes(m));
            let done = 0;
            const shardResults = await Promise.all(months.map(async (month) => {
                const events = await loadGearShard(month);
                done += 1;
                if (onProgress) onProgress(done, months.length);
                return events;
            }));
            const gear = shardResults.flat();
            return gear.filter(ev => ev.d && ev.d <= endDate);
        }

        function indexGearEventsByChar(gearEventsUpTo) {
            const eventsByChar = new Map();
            for (const ev of gearEventsUpTo || []) {
                const c = ev.c;
                if (!c) continue;
                if (!eventsByChar.has(c)) eventsByChar.set(c, []);
                eventsByChar.get(c).push(ev);
            }
            return eventsByChar;
        }

        function buildInventoryAbsMapFromEvents(baseline, gearEventsUpTo) {
            const invBase = (baseline && baseline.inventories) || {};
            const eventsByChar = indexGearEventsByChar(gearEventsUpTo);
            const allChars = new Set(Object.keys(invBase));
            for (const c of eventsByChar.keys()) allChars.add(c);
            const out = {};
            for (const charName of allChars) {
                const baselineItems = invBase[charName] || [];
                const charEvents = eventsByChar.get(charName) || [];
                if (!baselineItems.length && !charEvents.length) continue;
                const counts = {};
                for (const item of baselineItems) {
                    let id = String(item.item_id);
                    if (NO_RENT_ITEMS.has(id)) continue;
                    if (!id || id.toUpperCase() === 'NULL' || id === '0') continue;
                    counts[id] = (counts[id] || 0) + 1;
                }
                for (const ev of charEvents) {
                    const itemId = String(ev.i);
                    const sign = Number(ev.s);
                    const n = Number(ev.n) || 0;
                    if (!itemId || n <= 0 || (sign !== 1 && sign !== -1)) continue;
                    if (NO_RENT_ITEMS.has(itemId)) continue;
                    if (sign > 0) {
                        counts[itemId] = (counts[itemId] || 0) + n;
                    } else {
                        counts[itemId] = (counts[itemId] || 0) - n;
                        if (counts[itemId] <= 0) delete counts[itemId];
                    }
                }
                const cleaned = {};
                for (const [k, v] of Object.entries(counts)) {
                    if (v > 0) cleaned[k] = v;
                }
                if (Object.keys(cleaned).length) out[charName] = cleaned;
            }
            return out;
        }

        function resolveItemNames(invDeltas, nameMap) {
            for (const delta of Object.values(invDeltas || {})) {
                const inames = delta.item_names || (delta.item_names = {});
                for (const bucket of ['added', 'removed']) {
                    for (const itemId of Object.keys(delta[bucket] || {})) {
                        if (!inames[itemId] && nameMap[itemId]) {
                            inames[itemId] = nameMap[itemId];
                        }
                    }
                }
            }
        }

        function filterCharEventsForBaseline(events, baselineDate) {
            if (!baselineDate) return events || [];
            return (events || []).filter(ev => {
                if (ev.b != null && ev.b !== baselineDate) return false;
                if (ev.b == null && (ev.f === 'aa' || ev.f === 'lvl' || ev.f === 'hp')
                    && (ev.d || '') < baselineDate) return false;
                return true;
            });
        }

        function buildCharacterStateFromEvents(baseline, charEvents) {
            const folded = foldCharEventsToCharDeltas(charEvents);
            const baselineChars = (baseline && baseline.characters) || {};
            const fullState = {};
            for (const [charName, charData] of Object.entries(baselineChars)) {
                fullState[charName] = {
                    level: charData.level || 0,
                    aa_total: (charData.aa_unspent || 0) + (charData.aa_spent || 0),
                    hp: charData.hp_max_total || 0,
                    class: charData.class || '',
                    guild: charData.guild || ''
                };
            }
            for (const [charName, deltaData] of Object.entries(folded)) {
                if (deltaData.is_deleted) {
                    delete fullState[charName];
                    continue;
                }
                if (fullState[charName]) {
                    fullState[charName].level += deltaData.level_change || 0;
                    fullState[charName].aa_total += deltaData.aa_total_change || 0;
                    fullState[charName].hp += deltaData.hp_change || 0;
                    if (deltaData.class) fullState[charName].class = deltaData.class;
                } else if (!deltaData.is_deleted) {
                    fullState[charName] = {
                        level: Math.max(0, deltaData.level_change || 0),
                        aa_total: Math.max(0, deltaData.aa_total_change || 0),
                        hp: Math.max(0, deltaData.hp_change || 0),
                        class: deltaData.class || '',
                        guild: ''
                    };
                }
            }
            return fullState;
        }

        function gearManifestBaselineForDate(dateStr) {
            const days = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.days) || {};
            if (days[dateStr] && days[dateStr].baseline_date) {
                return days[dateStr].baseline_date;
            }
            const eras = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.eras) || [];
            for (let i = eras.length - 1; i >= 0; i--) {
                const era = eras[i];
                if (era.first_event && era.first_event <= dateStr && era.baseline_date) {
                    return era.baseline_date;
                }
            }
            return null;
        }

        function foldGearEventsToInvDeltas(gearEvents) {
            const invDeltas = {};
            for (const ev of gearEvents) {
                const charName = ev.c;
                const itemId = String(ev.i);
                const sign = Number(ev.s);
                const n = Number(ev.n) || 0;
                if (!charName || !itemId || n <= 0 || (sign !== 1 && sign !== -1)) continue;
                if (!invDeltas[charName]) {
                    invDeltas[charName] = { added: {}, removed: {}, item_names: {}, is_visibility_change: false };
                }
                const row = invDeltas[charName];
                if (ev.v) row.is_visibility_change = true;
                const bucket = sign > 0 ? row.added : row.removed;
                bucket[itemId] = (bucket[itemId] || 0) + n;
            }
            for (const charName of Object.keys(invDeltas)) {
                const row = invDeltas[charName];
                const added = row.added;
                const removed = row.removed;
                for (const itemId of Object.keys(added)) {
                    if (!removed[itemId]) continue;
                    const a = added[itemId];
                    const r = removed[itemId];
                    if (a > r) { added[itemId] = a - r; delete removed[itemId]; }
                    else if (r > a) { removed[itemId] = r - a; delete added[itemId]; }
                    else { delete added[itemId]; delete removed[itemId]; }
                }
            }
            return invDeltas;
        }

        function applyCharSnapshotFromEvent(row, ev) {
            if (ev.lv != null) row.current_level = Number(ev.lv);
            if (ev.aa != null) row.current_aa_total = Number(ev.aa);
            if (ev.hp != null) row.current_hp = Number(ev.hp);
            if (!row._hasPrevSnap) {
                if (ev.plv != null) row.previous_level = Number(ev.plv);
                if (ev.paa != null) row.previous_aa_total = Number(ev.paa);
                if (ev.php != null) row.previous_hp = Number(ev.php);
                if (ev.plv != null || ev.paa != null || ev.php != null) row._hasPrevSnap = true;
            }
        }

        function foldCharEventsToCharDeltas(charEvents) {
            const sorted = [...charEvents].sort((a, b) => (a.d || '').localeCompare(b.d || ''));
            const charDeltas = {};
            for (const ev of sorted) {
                const charName = ev.c;
                if (!charName) continue;
                if (!charDeltas[charName]) {
                    charDeltas[charName] = {
                        name: charName, level_change: 0, aa_total_change: 0, hp_change: 0,
                        current_level: 0, previous_level: 0, current_aa_total: 0, previous_aa_total: 0,
                        current_hp: 0, previous_hp: 0, class: ev.cl || '', is_new: false, is_deleted: false,
                        is_visibility_change: false
                    };
                }
                const row = charDeltas[charName];
                if (ev.cl) row.class = ev.cl;
                if (ev.v) row.is_visibility_change = true;
                const f = ev.f;
                const n = Number(ev.n) || 0;
                if (f === 'lvl') row.level_change += n;
                else if (f === 'aa') row.aa_total_change += n;
                else if (f === 'hp') row.hp_change += n;
                else if (f === 'new') row.is_new = true;
                else if (f === 'del') row.is_deleted = true;
                applyCharSnapshotFromEvent(row, ev);
            }
            for (const row of Object.values(charDeltas)) {
                delete row._hasPrevSnap;
            }
            return charDeltas;
        }

        function enrichCharChangesFromStates(charChanges, startState, endState, rangeCharDeltas) {
            const names = new Set([
                ...Object.keys(charChanges || {}),
                ...Object.keys(startState || {}),
                ...Object.keys(endState || {})
            ]);
            for (const charName of names) {
                const s = startState[charName];
                const e = endState[charName];
                if (!s || !e) continue;
                const rd = (rangeCharDeltas && rangeCharDeltas[charName]) || {};
                const existing = (charChanges && charChanges[charName]) || {};
                charChanges[charName] = {
                    level: e.level - s.level,
                    aa: e.aa_total - s.aa_total,
                    hp: e.hp - s.hp,
                    current_level: e.level,
                    previous_level: s.level,
                    current_aa_total: e.aa_total,
                    class: e.class || rd.class || existing.class || '',
                    is_new: !!(rd.is_new || existing.is_new),
                    is_deleted: !!(rd.is_deleted || existing.is_deleted),
                    is_visibility_change: !!(rd.is_visibility_change || existing.is_visibility_change)
                };
            }
        }

        function enrichCharChangesFromFoldedDeltas(charChanges, rangeCharDeltas) {
            for (const [charName, d] of Object.entries(rangeCharDeltas || {})) {
                if (d.current_level == null && d.current_aa_total == null && d.current_hp == null) continue;
                const c = charChanges[charName] || (charChanges[charName] = charDeltasToChanges({ [charName]: d })[charName]);
                if (d.current_level != null) c.current_level = d.current_level;
                if (d.previous_level != null) c.previous_level = d.previous_level;
                if (d.current_aa_total != null) c.current_aa_total = d.current_aa_total;
                if (d.aa_total_change != null && c.aa == null) c.aa = d.aa_total_change;
                if (d.hp_change != null && c.hp == null) c.hp = d.hp_change;
                if (d.level_change != null && c.level == null) c.level = d.level_change;
                if (d.is_visibility_change) c.is_visibility_change = true;
                if (d.class) c.class = d.class;
            }
        }
        
        async function loadBaseline(baselineDate) {
            const want = String(baselineDate);
            const baselineKey = `baseline_${baselineDate}`;
            const cacheKey = baselineKey + '_result';
            if (loadedBaselines && loadedBaselines.has(cacheKey)) {
                return loadedBaselines.get(cacheKey);
            }

            const currentUrl = `delta_snapshots/baseline_master.json.gz`;
            const archivedUrl = `delta_snapshots/baseline_master_${baselineDate}.json.gz`;

            function finish(baseline, usedFallback) {
                if (!loadedBaselines) {
                    loadedBaselines = new Map();
                }
                const result = { baseline, usedFallback };
                loadedBaselines.set(cacheKey, result);
                return result;
            }

            /** strictMatch: when using shared master file, embedded baseline_date must equal want. */
            function checkEmbeddedOrThrow(baseline, source, strictMatch) {
                const embedded = baseline.baseline_date != null ? String(baseline.baseline_date) : '';
                if (strictMatch) {
                    if (embedded !== want) {
                        throw new Error(
                            `Archived baseline not found (${archivedUrl}), and ${source} has ` +
                            `baseline_date=${embedded || '(missing)'} (expected ${want}). ` +
                            `Deploy baseline_master_${want}.json.gz under delta_snapshots/.`
                        );
                    }
                } else if (embedded && embedded !== want) {
                    throw new Error(
                        `Baseline file ${source} has baseline_date=${embedded}, expected ${want}.`
                    );
                }
            }

            try {
                let baseline = await fetchGzJsonCached(archivedUrl, { optional: true });
                if (baseline) {
                    checkEmbeddedOrThrow(baseline, archivedUrl, false);
                    return finish(baseline, false);
                }

                // Archive missing: only accept baseline_master.json.gz if embedded baseline_date matches
                baseline = await fetchGzJsonCached(currentUrl, { optional: true });
                if (baseline) {
                    checkEmbeddedOrThrow(baseline, currentUrl, true);
                    return finish(baseline, true);
                }

                // Last resort: uncompressed (backward compatibility)
                let uResp = await fetch(`delta_snapshots/baseline_master_${baselineDate}.json`);
                if (uResp && uResp.ok) {
                    const baseline = JSON.parse(await uResp.text());
                    checkEmbeddedOrThrow(baseline, `delta_snapshots/baseline_master_${baselineDate}.json`, false);
                    return finish(baseline, false);
                }
                uResp = await fetch('delta_snapshots/baseline_master.json');
                if (uResp && uResp.ok) {
                    const baseline = JSON.parse(await uResp.text());
                    checkEmbeddedOrThrow(baseline, 'delta_snapshots/baseline_master.json', true);
                    return finish(baseline, true);
                }
                throw new Error(`Baseline not found for ${baselineDate}. Tried: ${archivedUrl}, ${currentUrl}, and uncompressed variants.`);
            } catch (error) {
                console.error(`Error loading baseline for ${baselineDate}:`, error);
                throw error;
            }
        }
        
        function pickAbsStat(deltaData, field, fallback) {
            // Do not use || for AA/HP/level: legitimate 0 must not fall back to baseline.
            if (!deltaData || !Object.prototype.hasOwnProperty.call(deltaData, field)) return fallback;
            const v = deltaData[field];
            if (v === null || v === undefined || v === '') return fallback;
            const n = Number(v);
            return Number.isFinite(n) ? n : fallback;
        }

        /** Mirror delta_storage._cumulative_char_stats_at_slice (missing row = baseline). */
        function cumulativeCharStatsAtSlice(baselineCharacters, charName, charDeltasDict) {
            const row = (charDeltasDict || {})[charName];
            if (row) {
                const lvl = row.current_level != null ? row.current_level : (row.previous_level || 0);
                const aa = row.current_aa_total != null ? row.current_aa_total : (row.previous_aa_total || 0);
                const hp = row.current_hp != null ? row.current_hp : (row.previous_hp || 0);
                return [Number(lvl) || 0, Number(aa) || 0, Number(hp) || 0];
            }
            const bc = (baselineCharacters || {})[charName];
            if (bc) {
                return [
                    Number(bc.level) || 0,
                    (Number(bc.aa_unspent) || 0) + (Number(bc.aa_spent) || 0),
                    Number(bc.hp_max_total) || 0
                ];
            }
            return [0, 0, 0];
        }

        /** Same logic as delta_storage.compare_delta_to_delta (characters only). */
        function compareDeltaToDeltaChars(deltaA, deltaB, baselineCharacters) {
            const charDeltas = {};
            const cdA = deltaA.char_deltas || {};
            const cdB = deltaB.char_deltas || {};
            const allChars = new Set([...Object.keys(cdA), ...Object.keys(cdB)]);
            for (const charName of allChars) {
                const deltaAChar = cdA[charName] || {};
                const deltaBChar = cdB[charName] || {};
                const [aLevel, aAa, aHp] = cumulativeCharStatsAtSlice(baselineCharacters, charName, cdA);
                const [bLevel, bAa, bHp] = cumulativeCharStatsAtSlice(baselineCharacters, charName, cdB);
                const levelChange = bLevel - aLevel;
                const aaChange = bAa - aAa;
                const hpChange = bHp - aHp;
                if (levelChange !== 0 || aaChange !== 0 || hpChange !== 0 ||
                    deltaBChar.is_new || deltaBChar.is_deleted) {
                    charDeltas[charName] = {
                        name: charName,
                        level_change: levelChange,
                        aa_total_change: aaChange,
                        hp_change: hpChange,
                        current_level: bLevel,
                        previous_level: aLevel,
                        current_aa_total: bAa,
                        previous_aa_total: aAa,
                        current_hp: bHp,
                        previous_hp: aHp,
                        class: deltaBChar.class || deltaAChar.class || '',
                        is_new: !!deltaBChar.is_new && !deltaAChar.is_new,
                        is_deleted: !!deltaBChar.is_deleted && !deltaAChar.is_deleted
                    };
                }
            }
            return charDeltas;
        }

        /** Cross-baseline: mirror compare_delta_to_delta_reconstructed character loop. */
        function compareDeltaToDeltaCharsCrossBaseline(deltaStart, deltaEnd, startBaseline, endBaseline) {
            const bcS = (startBaseline.characters || {});
            const bcE = (endBaseline.characters || {});
            const charDeltas = {};
            const cdS = deltaStart.char_deltas || {};
            const cdE = deltaEnd.char_deltas || {};
            const allChars = new Set([...Object.keys(cdS), ...Object.keys(cdE)]);
            for (const charName of allChars) {
                const deltaAChar = cdS[charName] || {};
                const deltaBChar = cdE[charName] || {};
                const [aLevel, aAa, aHp] = cumulativeCharStatsAtSlice(bcS, charName, cdS);
                const [bLevel, bAa, bHp] = cumulativeCharStatsAtSlice(bcE, charName, cdE);
                const levelChange = bLevel - aLevel;
                const aaChange = bAa - aAa;
                const hpChange = bHp - aHp;
                if (levelChange !== 0 || aaChange !== 0 || hpChange !== 0 ||
                    deltaBChar.is_new || deltaBChar.is_deleted) {
                    charDeltas[charName] = {
                        name: charName,
                        level_change: levelChange,
                        aa_total_change: aaChange,
                        hp_change: hpChange,
                        current_level: bLevel,
                        previous_level: aLevel,
                        current_aa_total: bAa,
                        previous_aa_total: aAa,
                        current_hp: bHp,
                        previous_hp: aHp,
                        class: deltaBChar.class || deltaAChar.class || '',
                        is_new: !!deltaBChar.is_new && !deltaAChar.is_new,
                        is_deleted: !!deltaBChar.is_deleted && !deltaAChar.is_deleted
                    };
                }
            }
            return charDeltas;
        }

        function charDeltasToChanges(charDeltas) {
            const charChanges = {};
            for (const [charName, d] of Object.entries(charDeltas || {})) {
                charChanges[charName] = {
                    level: d.level_change,
                    aa: d.aa_total_change,
                    hp: d.hp_change,
                    current_level: d.current_level,
                    previous_level: d.previous_level,
                    current_aa_total: d.current_aa_total,
                    class: d.class || '',
                    is_new: !!d.is_new,
                    is_deleted: !!d.is_deleted,
                    is_visibility_change: !!d.is_visibility_change
                };
            }
            return charChanges;
        }

        function reconstructCharacterState(baseline, delta) {
            // Reconstruct full character state by combining baseline + delta
            const fullState = {};
            
            // Start with baseline characters
            const baselineChars = baseline.characters || {};
            for (const [charName, charData] of Object.entries(baselineChars)) {
                fullState[charName] = {
                    level: charData.level || 0,
                    aa_total: (charData.aa_unspent || 0) + (charData.aa_spent || 0),
                    hp: charData.hp_max_total || 0,
                    class: charData.class || '',
                    guild: charData.guild || ''
                };
            }
            
            // Apply delta changes
            const deltaChars = delta.char_deltas || {};
            for (const [charName, deltaData] of Object.entries(deltaChars)) {
                if (deltaData.is_deleted) {
                    delete fullState[charName];
                    continue;
                }
                
                if (deltaData.is_new || !fullState[charName]) {
                    // New character - use current values from delta
                    fullState[charName] = {
                        level: pickAbsStat(deltaData, 'current_level', 0),
                        aa_total: pickAbsStat(deltaData, 'current_aa_total', 0),
                        hp: pickAbsStat(deltaData, 'current_hp', 0),
                        class: deltaData.class || '',
                        guild: deltaData.guild || ''
                    };
                } else {
                    // Update existing character - delta has current values (baseline + changes)
                    const prev = fullState[charName];
                    fullState[charName].level = pickAbsStat(deltaData, 'current_level', prev.level);
                    fullState[charName].aa_total = pickAbsStat(deltaData, 'current_aa_total', prev.aa_total);
                    fullState[charName].hp = pickAbsStat(deltaData, 'current_hp', prev.hp);
                    if (deltaData.class) {
                        fullState[charName].class = deltaData.class;
                    }
                    if (deltaData.hasOwnProperty('guild')) {
                        fullState[charName].guild = deltaData.guild || '';
                    }
                }
            }
            
            return fullState;
        }
        
        function reconstructInventoryAbsMap(baseline, delta) {
            const invDeltas = delta.inv_deltas || {};
            const invBase = baseline.inventories || {};
            const charNames = new Set([...Object.keys(invBase), ...Object.keys(invDeltas)]);
            const out = {};
            for (const charName of charNames) {
                const counts = {};
                const items = invBase[charName] || [];
                for (const item of items) {
                    let id = item.item_id;
                    if (NO_RENT_ITEMS.has(String(id))) continue;
                    id = String(id);
                    counts[id] = (counts[id] || 0) + 1;
                }
                const row = invDeltas[charName];
                if (row) {
                    const added = row.added || {};
                    const removed = row.removed || {};
                    for (const itemId of Object.keys(added)) {
                        const sid = String(itemId);
                        if (NO_RENT_ITEMS.has(sid)) continue;
                        counts[sid] = (counts[sid] || 0) + Number(added[itemId]);
                    }
                    for (const itemId of Object.keys(removed)) {
                        const sid = String(itemId);
                        if (NO_RENT_ITEMS.has(sid)) continue;
                        counts[sid] = (counts[sid] || 0) - Number(removed[itemId]);
                        if (counts[sid] <= 0) delete counts[sid];
                    }
                }
                const cleaned = {};
                for (const [k, v] of Object.entries(counts)) {
                    if (v > 0) cleaned[k] = v;
                }
                if (Object.keys(cleaned).length) out[charName] = cleaned;
            }
            return out;
        }
        
        function diffInventoryAbsMaps(absStart, absEnd, invMetaStart, invMetaEnd) {
            const invDeltas = {};
            invMetaStart = invMetaStart || {};
            invMetaEnd = invMetaEnd || {};
            const allChars = new Set([...Object.keys(absStart), ...Object.keys(absEnd)]);
            for (const charName of allChars) {
                const a = absStart[charName] || {};
                const b = absEnd[charName] || {};
                const rowS = invMetaStart[charName] || {};
                const rowE = invMetaEnd[charName] || {};
                const namesS = rowS.item_names || {};
                const namesE = rowE.item_names || {};
                const allIds = new Set([...Object.keys(a), ...Object.keys(b)]);
                const addedItems = {};
                const removedItems = {};
                const itemNames = {};
                for (const itemId of allIds) {
                    const sid = String(itemId);
                    const ca = Number(a[sid]) || 0;
                    const cb = Number(b[sid]) || 0;
                    const net = cb - ca;
                    if (net > 0) {
                        addedItems[sid] = net;
                        if (namesE[sid] !== undefined) itemNames[sid] = namesE[sid];
                        else if (namesE[itemId] !== undefined) itemNames[sid] = namesE[itemId];
                        else if (namesS[sid] !== undefined) itemNames[sid] = namesS[sid];
                        else if (namesS[itemId] !== undefined) itemNames[sid] = namesS[itemId];
                    } else if (net < 0) {
                        removedItems[sid] = -net;
                        if (namesS[sid] !== undefined) itemNames[sid] = namesS[sid];
                        else if (namesS[itemId] !== undefined) itemNames[sid] = namesS[itemId];
                        else if (namesE[sid] !== undefined) itemNames[sid] = namesE[sid];
                        else if (namesE[itemId] !== undefined) itemNames[sid] = namesE[itemId];
                    }
                }
                if (Object.keys(addedItems).length > 0 || Object.keys(removedItems).length > 0) {
                    invDeltas[charName] = { added: addedItems, removed: removedItems, item_names: itemNames };
                }
            }
            return invDeltas;
        }

        let lastReportContext = null;
        let lastFilterIndex = null;
        let lootFilterAutocompleteBound = false;

        function escapeHtmlText(s) {
            const div = document.createElement('div');
            div.textContent = s;
            return div.innerHTML;
        }

        function normalizeLootFilters(filters) {
            const zone = (filters.zone || '').trim();
            const mob = (filters.mob || '').trim();
            let itemId = String(filters.itemId || '').trim();
            const itemName = (filters.itemName || '').trim();
            if (!itemId && itemName) {
                const needle = itemName.toLowerCase();
                for (const [iid, name] of Object.entries(ITEM_ID_TO_NAME || {})) {
                    if ((name || '').toLowerCase() === needle) {
                        itemId = String(iid);
                        break;
                    }
                }
            }
            return { zone, mob, itemId, itemName };
        }

        function itemMatchesLootFilters(itemId, lootFilters) {
            const zoneF = lootFilters.zone || '';
            const mobF = lootFilters.mob || '';
            const itemIdF = lootFilters.itemId || '';
            const itemNameF = lootFilters.itemName || '';
            if (!zoneF && !mobF && !itemIdF && !itemNameF) return true;
            const sid = String(itemId);
            if (zoneF) {
                const itemZone = (TRACKED_ITEM_ZONE && TRACKED_ITEM_ZONE[sid]) || '';
                if (itemZone.toLowerCase().indexOf(zoneF.toLowerCase()) === -1) return false;
            }
            if (mobF) {
                const itemMob = (TRACKED_ITEM_MOB && TRACKED_ITEM_MOB[sid]) || '';
                if (itemMob.toLowerCase().indexOf(mobF.toLowerCase()) === -1) return false;
            }
            if (itemIdF) {
                if (sid !== String(itemIdF)) return false;
            } else if (itemNameF) {
                const name = (ITEM_ID_TO_NAME && ITEM_ID_TO_NAME[sid]) || ('Item ' + sid);
                if (name.toLowerCase().indexOf(itemNameF.toLowerCase()) === -1) return false;
            }
            return true;
        }

        function buildRangeFilterIndex(zoneEntries, trackedDeltas) {
            const zones = Object.keys(zoneEntries || {}).sort();
            const mobsByZone = {};
            const allMobs = new Set();
            const itemsSeen = new Set();
            const items = [];
            for (const zone of zones) {
                const mobs = zoneEntries[zone] || {};
                const mobList = [];
                for (const mob of Object.keys(mobs)) {
                    const mobKey = mob || '';
                    if (!mobList.includes(mobKey)) mobList.push(mobKey);
                    if (mobKey) allMobs.add(mobKey);
                    for (const entry of (mobs[mob] || [])) {
                        const iid = String(entry.itemId || '');
                        if (!iid || itemsSeen.has(iid)) continue;
                        itemsSeen.add(iid);
                        items.push({
                            id: iid,
                            name: entry.name || (ITEM_ID_TO_NAME && ITEM_ID_TO_NAME[iid]) || ('Item ' + iid),
                            zone,
                            mob: mobKey
                        });
                    }
                }
                mobsByZone[zone] = mobList.sort((a, b) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)));
            }
            for (const delta of Object.values(trackedDeltas || {})) {
                const inames = delta.item_names || {};
                for (const itemId of Object.keys(delta.added || {})) {
                    const sid = String(itemId);
                    if (itemsSeen.has(sid)) continue;
                    itemsSeen.add(sid);
                    items.push({
                        id: sid,
                        name: inames[itemId] || inames[sid] || (ITEM_ID_TO_NAME && ITEM_ID_TO_NAME[sid]) || ('Item ' + sid),
                        zone: (TRACKED_ITEM_ZONE && TRACKED_ITEM_ZONE[sid]) || '',
                        mob: (TRACKED_ITEM_MOB && TRACKED_ITEM_MOB[sid]) || ''
                    });
                }
            }
            items.sort((a, b) => a.name.localeCompare(b.name));
            return { zones, mobsByZone, allMobs: [...allMobs].sort(), items };
        }

        function filterZoneEntries(zoneEntries, lootFilters) {
            const lf = normalizeLootFilters(lootFilters);
            if (!lf.zone && !lf.mob && !lf.itemId && !lf.itemName) return zoneEntries;
            const out = {};
            for (const zone of Object.keys(zoneEntries || {})) {
                if (lf.zone && zone.toLowerCase().indexOf(lf.zone.toLowerCase()) === -1) continue;
                const filteredMobs = {};
                for (const mob of Object.keys(zoneEntries[zone])) {
                    const mobStr = mob || '';
                    if (lf.mob && mobStr.toLowerCase().indexOf(lf.mob.toLowerCase()) === -1) continue;
                    const filteredEntries = (zoneEntries[zone][mob] || []).filter(e =>
                        itemMatchesLootFilters(e.itemId, lf)
                    );
                    if (filteredEntries.length) filteredMobs[mob] = filteredEntries;
                }
                if (Object.keys(filteredMobs).length) out[zone] = filteredMobs;
            }
            return out;
        }

        function filterTrackedDeltas(trackedDeltas, lootFilters) {
            const lf = normalizeLootFilters(lootFilters);
            if (!lf.zone && !lf.mob && !lf.itemId && !lf.itemName) return trackedDeltas;
            const out = {};
            for (const [charName, delta] of Object.entries(trackedDeltas || {})) {
                if (delta.is_visibility_change) continue;
                const added = {};
                const removed = {};
                const itemNames = { ...(delta.item_names || {}) };
                for (const itemId of Object.keys(delta.added || {})) {
                    if (itemMatchesLootFilters(itemId, lf)) added[itemId] = delta.added[itemId];
                }
                for (const itemId of Object.keys(delta.removed || {})) {
                    if (itemMatchesLootFilters(itemId, lf)) removed[itemId] = delta.removed[itemId];
                }
                if (Object.keys(added).length || Object.keys(removed).length) {
                    out[charName] = { added, removed, item_names: itemNames, is_visibility_change: false };
                }
            }
            return out;
        }

        function filterEventsForChar(events, charName) {
            return (events || []).filter(ev => ev.c === charName);
        }

        function buildRangeTrackedRows(gearEvents, charName, startHoldings) {
            if (!TRACKED_ITEM_IDS || !TRACKED_ITEM_IDS.size) return [];
            const holdings = {};
            for (const [itemId, cnt] of Object.entries(startHoldings || {})) {
                const n = Number(cnt) || 0;
                if (n > 0) holdings[String(itemId)] = n;
            }
            const rows = [];
            const sorted = filterEventsForChar(gearEvents, charName)
                .sort((a, b) => (a.d || '').localeCompare(b.d || '') || String(a.i).localeCompare(String(b.i)));
            for (const ev of sorted) {
                if (ev.v) continue;
                const sign = Number(ev.s);
                const n = Number(ev.n) || 0;
                const iid = String(ev.i);
                if (!iid || n <= 0 || (sign !== 1 && sign !== -1) || NO_RENT_ITEMS.has(iid)) continue;
                const isTracked = TRACKED_ITEM_IDS.has(iid);
                if (isTracked && sign > 0 && UNIQUE_TRACKED_IDS.has(iid) && (holdings[iid] || 0) > 0) continue;
                if (isTracked) {
                    rows.push({
                        date: ev.d || '',
                        sign: sign,
                        count: n,
                        itemId: iid,
                        itemName: (ITEM_ID_TO_NAME && ITEM_ID_TO_NAME[iid]) || ('Item ' + iid),
                        source: (TRACKED_SOURCE_LABEL && TRACKED_SOURCE_LABEL[iid]) || ''
                    });
                }
                if (sign > 0) holdings[iid] = (holdings[iid] || 0) + n;
                else {
                    holdings[iid] = (holdings[iid] || 0) - n;
                    if (holdings[iid] <= 0) delete holdings[iid];
                }
            }
            return rows;
        }

        function filterTrackedRows(rows, lootFilters) {
            const lf = normalizeLootFilters(lootFilters);
            if (!lf.zone && !lf.mob && !lf.itemId && !lf.itemName) return rows || [];
            return (rows || []).filter(row => itemMatchesLootFilters(row.itemId, lf));
        }

        function buildZoneEntriesFromTrackedRows(trackedRowsByChar, startState, endState, netChangeTracked) {
            const zoneEntries = {};
            for (const [charName, rows] of Object.entries(trackedRowsByChar || {})) {
                if (!startState[charName] || !endState[charName]) continue;
                for (const row of rows) {
                    if (row.sign <= 0) continue;
                    const itemId = row.itemId;
                    if (!NO_DROP_TRACKED_IDS.has(String(itemId)) && (netChangeTracked[itemId] || 0) <= 0) continue;
                    const zone = TRACKED_ITEM_ZONE[String(itemId)];
                    if (!zone) continue;
                    const mob = (TRACKED_ITEM_MOB && TRACKED_ITEM_MOB[String(itemId)]) || '';
                    if (!zoneEntries[zone]) zoneEntries[zone] = {};
                    if (!zoneEntries[zone][mob]) zoneEntries[zone][mob] = [];
                    zoneEntries[zone][mob].push({
                        charName,
                        itemId,
                        name: row.itemName,
                        date: row.date || ''
                    });
                }
            }
            for (const zone of Object.keys(zoneEntries)) {
                for (const mob of Object.keys(zoneEntries[zone])) {
                    zoneEntries[zone][mob].sort((a, b) =>
                        (a.date || '').localeCompare(b.date || '') ||
                        (a.charName || '').localeCompare(b.charName || '') ||
                        String(a.itemId).localeCompare(String(b.itemId))
                    );
                }
            }
            return zoneEntries;
        }

        function getLootFiltersFromUI() {
            const itemEl = document.getElementById('loot-filter-item');
            return {
                zone: (document.getElementById('loot-filter-zone') || {}).value.trim(),
                mob: (document.getElementById('loot-filter-mob') || {}).value.trim(),
                itemId: itemEl ? (itemEl.getAttribute('data-item-id') || '') : '',
                itemName: itemEl ? itemEl.value.trim() : ''
            };
        }

        function updateLootFilterBanner(filters) {
            const banner = document.getElementById('loot-filter-active-banner');
            if (!banner) return;
            const lf = normalizeLootFilters(filters);
            const parts = [];
            if (lf.zone) parts.push('zone: ' + lf.zone);
            if (lf.mob) parts.push('mob: ' + lf.mob);
            if (lf.itemId || lf.itemName) parts.push('item: ' + (lf.itemName || lf.itemId));
            if (!parts.length) {
                banner.style.display = 'none';
                banner.textContent = '';
                return;
            }
            banner.style.display = 'block';
            banner.innerHTML = '<strong>Showing loot for:</strong> ' + escapeHtmlText(parts.join(' / '));
        }

        function rerenderReport() {
            if (!lastReportContext) return;
            const filters = getLootFiltersFromUI();
            document.getElementById('date_range_output').innerHTML = buildReportHTML(lastReportContext, filters);
            updateLootFilterBanner(filters);
        }

        function clearLootFilters(rerender) {
            ['loot-filter-zone', 'loot-filter-mob', 'loot-filter-item'].forEach(id => {
                const el = document.getElementById(id);
                if (!el) return;
                el.value = '';
                el.removeAttribute('data-item-id');
            });
            ['loot-filter-zone-list', 'loot-filter-mob-list', 'loot-filter-item-list'].forEach(id => {
                const list = document.getElementById(id);
                if (list) { list.style.display = 'none'; list.innerHTML = ''; }
            });
            if (rerender !== false) rerenderReport();
            else updateLootFilterBanner({});
        }

        function showReportFilterBar(filterIndex) {
            lastFilterIndex = filterIndex;
            const bar = document.getElementById('report-filters');
            if (bar) bar.style.display = 'block';
            clearLootFilters(false);
            bindLootFilterAutocomplete();
        }

        function bindLootFilterAutocomplete() {
            if (lootFilterAutocompleteBound) return;
            lootFilterAutocompleteBound = true;
            const clearBtn = document.getElementById('clear-loot-filters');
            if (clearBtn) clearBtn.addEventListener('click', () => clearLootFilters(true));

            function setupAutocomplete(inputId, listId, getSuggestions, onSelect) {
                const input = document.getElementById(inputId);
                const listEl = document.getElementById(listId);
                if (!input || !listEl) return;
                let selectedIdx = -1;

                function hideList() {
                    listEl.style.display = 'none';
                    listEl.innerHTML = '';
                    selectedIdx = -1;
                }

                function showList(matches) {
                    if (!matches.length) { hideList(); return; }
                    listEl.innerHTML = matches.slice(0, 80).map((m, i) => {
                        const label = typeof m === 'string' ? m : m.label;
                        const value = typeof m === 'string' ? m : m.value;
                        const extra = typeof m === 'string' ? '' : (m.extra || '');
                        return '<li data-value="' + escapeHtmlText(value).replace(/"/g, '&quot;') +
                            '" data-extra="' + escapeHtmlText(extra || '').replace(/"/g, '&quot;') +
                            '" data-idx="' + i + '">' + escapeHtmlText(label) + '</li>';
                    }).join('');
                    listEl.style.display = 'block';
                    selectedIdx = 0;
                    const items = listEl.querySelectorAll('li');
                    if (items[0]) items[0].classList.add('selected');
                }

                input.addEventListener('input', () => {
                    if (inputId === 'loot-filter-item') input.removeAttribute('data-item-id');
                    showList(getSuggestions(input.value.trim()));
                });
                input.addEventListener('keydown', (ev) => {
                    const items = listEl.querySelectorAll('li');
                    if (ev.key === 'ArrowDown' && items.length) {
                        ev.preventDefault();
                        selectedIdx = Math.min(selectedIdx + 1, items.length - 1);
                        items.forEach((li, i) => li.classList.toggle('selected', i === selectedIdx));
                        items[selectedIdx].scrollIntoView({ block: 'nearest' });
                    } else if (ev.key === 'ArrowUp' && items.length) {
                        ev.preventDefault();
                        selectedIdx = Math.max(selectedIdx - 1, 0);
                        items.forEach((li, i) => li.classList.toggle('selected', i === selectedIdx));
                        items[selectedIdx].scrollIntoView({ block: 'nearest' });
                    } else if (ev.key === 'Enter') {
                        if (items.length && selectedIdx >= 0) {
                            ev.preventDefault();
                            items[selectedIdx].click();
                        } else {
                            rerenderReport();
                        }
                    } else if (ev.key === 'Escape') {
                        hideList();
                    }
                });
                input.addEventListener('blur', () => {
                    setTimeout(hideList, 150);
                    rerenderReport();
                });
                listEl.addEventListener('mousedown', (ev) => ev.preventDefault());
                listEl.addEventListener('click', (ev) => {
                    const li = ev.target.closest('li');
                    if (!li) return;
                    onSelect(li.getAttribute('data-value') || '', li.getAttribute('data-extra') || '');
                    hideList();
                    rerenderReport();
                });
            }

            setupAutocomplete('loot-filter-zone', 'loot-filter-zone-list', (query) => {
                const zones = (lastFilterIndex && lastFilterIndex.zones) || [];
                if (!query) return zones.map(z => ({ label: z, value: z }));
                const q = query.toLowerCase();
                return zones.filter(z => z.toLowerCase().indexOf(q) !== -1).map(z => ({ label: z, value: z }));
            }, (value) => {
                document.getElementById('loot-filter-zone').value = value;
            });

            setupAutocomplete('loot-filter-mob', 'loot-filter-mob-list', (query) => {
                const zoneVal = (document.getElementById('loot-filter-zone') || {}).value.trim();
                let mobs = [];
                if (zoneVal && lastFilterIndex && lastFilterIndex.mobsByZone) {
                    for (const [z, mobList] of Object.entries(lastFilterIndex.mobsByZone)) {
                        if (z.toLowerCase().indexOf(zoneVal.toLowerCase()) !== -1) {
                            mobs = mobs.concat(mobList.filter(m => m));
                        }
                    }
                } else {
                    mobs = (lastFilterIndex && lastFilterIndex.allMobs) || [];
                }
                mobs = [...new Set(mobs)].sort();
                if (!query) return mobs.map(m => ({ label: m, value: m }));
                const q = query.toLowerCase();
                return mobs.filter(m => m.toLowerCase().indexOf(q) !== -1).map(m => ({ label: m, value: m }));
            }, (value) => {
                document.getElementById('loot-filter-mob').value = value;
            });

            setupAutocomplete('loot-filter-item', 'loot-filter-item-list', (query) => {
                const items = (lastFilterIndex && lastFilterIndex.items) || [];
                if (!query) return items.slice(0, 80).map(it => ({
                    label: it.name + (it.zone ? ' (' + it.zone + ')' : ''),
                    value: it.name,
                    extra: it.id
                }));
                const q = query.toLowerCase();
                return items.filter(it => it.name.toLowerCase().indexOf(q) !== -1).slice(0, 80).map(it => ({
                    label: it.name + (it.zone ? ' (' + it.zone + ')' : ''),
                    value: it.name,
                    extra: it.id
                }));
            }, (value, extra) => {
                const el = document.getElementById('loot-filter-item');
                el.value = value;
                if (extra) el.setAttribute('data-item-id', extra);
            });
        }

        function buildReportHTML(ctx, filters) {
            const lootFilters = normalizeLootFilters(filters || {});
            const hasLootFilters = !!(lootFilters.zone || lootFilters.mob || lootFilters.itemId || lootFilters.itemName);
            const displayZoneEntries = hasLootFilters ? filterZoneEntries(ctx.zoneEntries, lootFilters) : ctx.zoneEntries;
            const displayTrackedDeltas = hasLootFilters ? filterTrackedDeltas(ctx.trackedDeltas, lootFilters) : ctx.trackedDeltas;
            const displayNonVisTracked = Object.keys(displayTrackedDeltas).filter(
                c => !displayTrackedDeltas[c].is_visibility_change
            ).sort();

            const start = ctx.start;
            const end = ctx.end;
            const startState = ctx.startState;
            const endState = ctx.endState;
            const eventSourceNote = ctx.eventSourceNote;
            const baselineMismatch = ctx.baselineMismatch;
            const omitRangeLeaderboards = ctx.omitRangeLeaderboards;
            const dumpBeforeBaselineAny = ctx.dumpBeforeBaselineAny;
            const startDelta = ctx.startDelta;
            const endDelta = ctx.endDelta;
            const invDeltas = ctx.invDeltas;
            const invDeltasLevel1 = ctx.invDeltasLevel1;
            const invDeltasOthers = ctx.invDeltasOthers;
            const trackedDeltas = ctx.trackedDeltas;
            const charChanges = ctx.charChanges;
            const charsInBoth = ctx.charsInBoth;
            const corpseLootChars = ctx.corpseLootChars;
            const allVisNames = ctx.allVisNames;
            const nonVisLevel1 = ctx.nonVisLevel1;
            const nonVisOthers = ctx.nonVisOthers;
            const nonVisTracked = ctx.nonVisTracked;
            const aaLeaderboard = ctx.aaLeaderboard;
            const hpLeaderboard = ctx.hpLeaderboard;

            let reportHTML = `<h2 style="color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px;">Date Range Report: ${start} to ${end}</h2>`;
            if (eventSourceNote) {
                reportHTML += `<p style="color: #555; margin-bottom: 12px;"><em>Source: ${eventSourceNote}</em></p>`;
            }
            if (eventSourceNote && baselineMismatch) {
                const newerBaseline = ctx.startBaselineDateGear < ctx.endBaselineDateGear
                    ? ctx.endBaselineDateGear : ctx.startBaselineDateGear;
                reportHTML += `<p style="background:#e3f2fd;padding:10px;border-radius:5px;margin:10px 0;border-left:4px solid #2196F3;">
                    <strong>Different baselines:</strong> This range crosses <code>baseline_date</code> values (${ctx.startBaselineDateGear} vs ${ctx.endBaselineDateGear}).
                    <strong>AA/HP top lists are omitted</strong> — pick both dates on or after the later baseline (<code>${newerBaseline}</code>) for comparable gainers.
                </p>`;
            }
            if (!eventSourceNote) {
                if (dumpBeforeBaselineAny) {
                    const bits = [];
                    if (ctx.dumpBeforeBaselineStart || ctx.dqBadStart) bits.push(`start ${startDelta.date} (baseline ${startDelta.baseline_date})`);
                    if (ctx.dumpBeforeBaselineEnd || ctx.dqBadEnd) bits.push(`end ${endDelta.date} (baseline ${endDelta.baseline_date})`);
                    reportHTML += `<p style="background: #ffebee; padding: 12px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #f44336;">
                        <strong>Unreliable range:</strong> At least one endpoint daily JSON was built with <code>date</code> before <code>baseline_date</code> (${bits.join('; ')}).
                        Character AA/HP in those files can be inconsistent with the archived baseline, so <strong>character deltas and any old top lists could look like months of gains over a day or two</strong>.
                        <strong>AA and HP leaderboards are omitted</strong> for this report until the bad file is fixed.
                        Regenerate the affected <code>delta_daily_*.json.gz</code> with the correct Magelo dump for that calendar day and <code>baseline_era_date</code> (see <code>regenerate-delta-days.yml</code>).
                    </p>`;
                }
                if (ctx.usedFallbackBaseline) {
                    reportHTML += `<p style="background: #fff3e0; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ff9800;">
                        <strong>⚠️ Historical baseline not found.</strong> The archived baseline for one or both dates (for example baseline_master_${startDelta.baseline_date}.json.gz) was not available (404), so the <em>current</em> baseline file was used as a fallback. Character levels/AAs, visibility, and <em>reconstructed inventory</em> for affected dates may be wrong. Ensure dated <code>baseline_master_*.json.gz</code> files are deployed under <code>delta_snapshots/</code>.
                    </p>`;
                }
                if (baselineMismatch) {
                    reportHTML += `<p style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #2196F3;">
                        <strong>Different baselines:</strong> These dates use different <code>baseline_date</code> values (${startDelta.baseline_date} vs ${endDelta.baseline_date}). Character changes compare reconstructed snapshot states (each date's baseline + daily delta). Inventory and tracked items compare absolute item counts rebuilt the same way, then net-changed across the range (same model as server-side range deltas).
                        <strong>AA/HP top lists are omitted</strong> for this range (see note below): sparse rows plus rotation can inflate apparent AA/HP gains.
                    </p>`;
                }
                if (ctx.endBaselineResetDay) {
                    reportHTML += `<p style="background: #fff8e1; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ffc107;">
                        <strong>Baseline reset (end date):</strong> The end date matches the new master baseline; that day's <code>inv_deltas</code> are often empty because inventories match the fresh baseline. Range inventory below is still computed from reconstructed absolute inventories, so changes since the start date can still appear.
                    </p>`;
                }
            }

            const hasZoneSection = Object.keys(displayZoneEntries).length > 0 || Object.keys(ctx.zoneEntries).length > 0;
            reportHTML += `<p style="margin: 10px 0;">${hasZoneSection ? '<a href="#items-by-zone" style="margin-right: 10px;">📍 Items by Zone</a>' : ''}
                <a href="#aa-leaderboard" style="margin-right: 10px;">🏆 AA Leaderboard</a>
                <a href="#hp-leaderboard" style="margin-right: 10px;">❤️ HP Leaderboard</a>
                <a href="#character-changes" style="margin-right: 10px;">Character Changes</a>
                ${allVisNames.length > 0 ? '<a href="#visibility-note" style="margin-right: 10px; color: #757575;">Visibility (anon)</a>' : ''}
                ${nonVisLevel1.length > 0 ? '<a href="#inventory-changes-level1" style="margin-right: 10px;">Level 1 (Mules)</a>' : ''}
                <a href="#inventory-changes" style="margin-right: 10px;">Inventory Changes</a>
                ${(displayNonVisTracked.length > 0 || nonVisTracked.length > 0) ? '<a href="#tracked-items" style="margin-right: 10px; background-color: #FF9800;">📌 Tracked Items</a>' : ''}</p>`;

            if (allVisNames.length > 0) {
                reportHTML += `<details id="visibility-note" style="color: #757575; margin: 15px 0; padding: 10px; background: #fafafa; border-radius: 5px; border-left: 4px solid #9e9e9e;"><summary style="cursor: pointer; font-style: italic;"><strong>Visibility change (anon ↔ not anon)</strong> — ${allVisNames.length} character(s); their inventory and tracked item deltas are not listed below. Click to expand names.</summary><p style="margin: 8px 0 0 0; font-size: 0.9em;">${allVisNames.join(', ')}</p></details>`;
            }

            if (hasLootFilters && !Object.keys(displayZoneEntries).length && !displayNonVisTracked.length) {
                reportHTML += `<p style="color: #757575; font-style: italic; margin: 10px 0; padding: 10px; background: #fafafa; border-radius: 5px;">No matching loot for the current filters in this date range.</p>`;
            }

            if (Object.keys(displayZoneEntries).length > 0) {
                reportHTML += `
                <h2 id="items-by-zone" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">📍 Items by Zone</h2>
                <p><em>Tracked loot (raid, elemental, praesterium) acquired this period, grouped by zone and mob. Only characters present in both snapshots.${ctx.hasTrackedEventDates ? ' Each line shows the date the loot occurred.' : ''}</em></p>`;
                for (const zone of Object.keys(displayZoneEntries).sort()) {
                    const mobs = displayZoneEntries[zone];
                    reportHTML += `
                <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #f5f5f5;">
                    <h3 style="margin-top: 0;">${zone}</h3>`;
                    const mobKeys = Object.keys(mobs).sort((a, b) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)));
                    for (const mob of mobKeys) {
                        const entries = mobs[mob];
                        if (mob) reportHTML += `
                    <h4 style="margin: 12px 0 6px 0; font-size: 1em; color: #555;">${mob}</h4>`;
                        reportHTML += `
                    <ul style="margin: 0; padding-left: 20px;">`;
                        for (const e of entries) {
                            const charDisplay = formatCharDisplay(e.charName, charStateForName(e.charName, startState, endState));
                            const charSlug = e.charName.toLowerCase().replace(/ /g, '_');
                            const mageloUrl = 'https://www.takproject.net/magelo/character.php?char=' + encodeURIComponent(charSlug);
                            const itemUrl = 'https://www.takproject.net/allaclone/item.php?id=' + e.itemId;
                            const datePrefix = e.date
                                ? `<span style="color:#666;">${escapeHtmlText(e.date)}</span> — `
                                : '';
                            reportHTML += `<li>${datePrefix}<a href="${mageloUrl}" target="_blank" style="text-decoration: none; font-weight: bold;">${charDisplay}</a>${charTimelineLink(e.charName)} — <a href="${itemUrl}" target="_blank" style="color: #2e7d32;">${e.name}</a></li>`;
                        }
                        reportHTML += `
                    </ul>`;
                    }
                    reportHTML += `
                </div>`;
                }
            } else if (hasLootFilters && Object.keys(ctx.zoneEntries).length > 0) {
                reportHTML += `
                <h2 id="items-by-zone" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">📍 Items by Zone</h2>
                <p style="color: #999; font-style: italic;">No items match the current loot filters.</p>`;
            }

            const noInventoryOrTrackedBlocks = nonVisLevel1.length === 0 && nonVisOthers.length === 0 && nonVisTracked.length === 0;
            if (noInventoryOrTrackedBlocks && (Object.keys(invDeltasLevel1).length > 0 || Object.keys(invDeltasOthers).length > 0 || Object.keys(trackedDeltas).length > 0)) {
                reportHTML += `<p style="color: #757575; font-style: italic; margin: 10px 0;">No inventory or tracked item changes to list for this range. For date ranges outside the current baseline period, delta files from that time may not include inventory data, or all changes in this range are visibility-only (see above).</p>`;
            }

            if (aaLeaderboard.length > 0) {
                reportHTML += `
                <div class="leaderboard" id="aa-leaderboard" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h2 style="color: white; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; margin-top: 0;">🏆 Top AA Gainers</h2>
                    <table class="leaderboard-table" style="width: 100%; border-collapse: collapse; background-color: rgba(255,255,255,0.1); border-radius: 5px; overflow: hidden;">
                        <thead>
                            <tr>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Rank</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Character</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Class</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Level</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">AA Gained</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Total AA</th>
                            </tr>
                        </thead>
                        <tbody>`;
                for (let idx = 0; idx < Math.min(20, aaLeaderboard.length); idx++) {
                    const entry = aaLeaderboard[idx];
                    const rankStyle = idx === 0 ? 'background-color: #FFD700; color: #000;' :
                                     idx === 1 ? 'background-color: #C0C0C0; color: #000;' :
                                     idx === 2 ? 'background-color: #CD7F32; color: #fff;' :
                                     'background-color: rgba(255,255,255,0.3); color: #fff;';
                    reportHTML += `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                                <td style="padding: 10px 12px;"><span style="display: inline-block; width: 30px; height: 30px; line-height: 30px; text-align: center; border-radius: 50%; font-weight: bold; ${rankStyle}">${idx + 1}</span></td>
                                <td style="padding: 10px 12px;"><strong>${formatCharDisplay(entry.name, charStateForName(entry.name, startState, endState))}</strong>${charTimelineLink(entry.name)}</td>
                                <td style="padding: 10px 12px;">${entry.class}</td>
                                <td style="padding: 10px 12px;">${entry.level}</td>
                                <td style="padding: 10px 12px; color: #4CAF50; font-weight: bold;">+${entry.aa_gain}</td>
                                <td style="padding: 10px 12px;">${entry.aa_total || '—'}</td>
                            </tr>`;
                }
                reportHTML += `
                        </tbody>
                    </table>
                </div>`;
            }

            if (hpLeaderboard.length > 0) {
                reportHTML += `
                <div class="leaderboard" id="hp-leaderboard" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h2 style="color: white; border-bottom: 2px solid rgba(255,255,255,0.3); padding-bottom: 10px; margin-top: 0;">❤️ Top HP Gainers</h2>
                    <table class="leaderboard-table" style="width: 100%; border-collapse: collapse; background-color: rgba(255,255,255,0.1); border-radius: 5px; overflow: hidden;">
                        <thead>
                            <tr>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Rank</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Character</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Class</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Level</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">HP Gained</th>
                                <th style="background-color: rgba(255,255,255,0.2); padding: 12px; text-align: left; font-weight: bold;">Total HP</th>
                            </tr>
                        </thead>
                        <tbody>`;
                for (let idx = 0; idx < Math.min(20, hpLeaderboard.length); idx++) {
                    const entry = hpLeaderboard[idx];
                    const rankStyle = idx === 0 ? 'background-color: #FFD700; color: #000;' :
                                     idx === 1 ? 'background-color: #C0C0C0; color: #000;' :
                                     idx === 2 ? 'background-color: #CD7F32; color: #fff;' :
                                     'background-color: rgba(255,255,255,0.3); color: #fff;';
                    reportHTML += `
                            <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                                <td style="padding: 10px 12px;"><span style="display: inline-block; width: 30px; height: 30px; line-height: 30px; text-align: center; border-radius: 50%; font-weight: bold; ${rankStyle}">${idx + 1}</span></td>
                                <td style="padding: 10px 12px;"><strong>${formatCharDisplay(entry.name, charStateForName(entry.name, startState, endState))}</strong>${charTimelineLink(entry.name)}</td>
                                <td style="padding: 10px 12px;">${entry.class}</td>
                                <td style="padding: 10px 12px;">${entry.level}</td>
                                <td style="padding: 10px 12px; color: #fff; font-weight: bold;">+${entry.hp_gain}</td>
                                <td style="padding: 10px 12px;">${entry.hp_total || '—'}</td>
                            </tr>`;
                }
                reportHTML += `
                        </tbody>
                    </table>
                </div>`;
            }

            if (dumpBeforeBaselineAny) {
                reportHTML += `<p style="background:#fce4ec;padding:12px;border-radius:5px;margin:12px 0;border-left:4px solid #c2185b;"><strong>AA/HP leaderboards omitted</strong> — at least one endpoint <code>delta_daily_*.json.gz</code> was built with the wrong <code>baseline_era_date</code> (dump date before <code>baseline_date</code>). Regenerate that day with the <strong>Regenerate delta daily JSONs</strong> workflow using a <code>baseline_era_date</code> that matches the archive for that dump (for a single Feb-era anchor use <code>2026-02-09</code>), then redeploy.</p>`;
            } else if (baselineMismatch && !eventSourceNote) {
                const newerBaseline = startDelta.baseline_date < endDelta.baseline_date ? endDelta.baseline_date : startDelta.baseline_date;
                reportHTML += `<p style="background:#fce4ec;padding:12px;border-radius:5px;margin:12px 0;border-left:4px solid #c2185b;"><strong>AA/HP leaderboards omitted</strong> — this range crosses different <code>baseline_date</code> values (${startDelta.baseline_date} vs ${endDelta.baseline_date}). Reconstructed AA/HP at the start uses the older era baseline plus sparse <code>char_deltas</code>; at the end it uses the newer era. Characters unchanged vs the old baseline often have <strong>no</strong> row on the start day, so their AA stays at the old baseline snapshot (e.g. 173) even if the calendar day is just before rotation, while the first post-rotation daily row can show a large cumulative jump vs the <em>new</em> baseline — top lists looked like huge short-window gains. For comparable top gainers, pick <strong>both dates on or after the later <code>baseline_date</code></strong> (here <code>${newerBaseline}</code>), or use <code>delta.html</code> day-over-day.</p>`;
            }

            if (Object.keys(charChanges).length > 0) {
                reportHTML += `
                <h2 id="character-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Character Level & AA Changes</h2>
                <table class="delta-table" style="width: 100%; border-collapse: collapse; margin: 20px 0;">
                    <thead>
                        <tr>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">Character</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">Class</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">Level</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">Level Change</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">Total AA</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd; background-color: #f0f0f0; font-weight: bold;">AA Total Change</th>
                        </tr>
                    </thead>
                    <tbody>`;
                for (const charName of Object.keys(charChanges).sort()) {
                    const changes = charChanges[charName];
                    if (!charsInBoth.has(charName)) continue;
                    const isDeleted = changes.is_deleted;
                    const isNew = changes.is_new;
                    const currentLevel = changes.current_level;
                    const previousLevel = changes.previous_level;
                    const charState = charStateForName(charName, startState, endState);
                    let charDisplay;
                    if (isDeleted) {
                        charDisplay = `<strong style="color: #999; text-decoration: line-through;">${formatCharDisplay(charName, charState)}</strong>${charTimelineLink(charName)} <span style="color: #f44336; font-size: 0.9em;">(Deleted)</span>`;
                    } else if (isNew) {
                        charDisplay = `<strong>${formatCharDisplay(charName, charState)}</strong>${charTimelineLink(charName)} <span style="color: #4CAF50; font-size: 0.9em;">(New)</span>`;
                    } else {
                        charDisplay = `<strong>${formatCharDisplay(charName, charState)}</strong>${charTimelineLink(charName)}`;
                    }
                    let levelDisplay;
                    if (isDeleted) {
                        levelDisplay = `<span style="color: #f44336; font-weight: bold;">Deleted (was ${previousLevel})</span>`;
                    } else if (previousLevel === 65) {
                        levelDisplay = `<span style="color: #666;">—</span>`;
                    } else {
                        const levelClass = changes.level > 0 ? 'color: #4CAF50; font-weight: bold;' : changes.level < 0 ? 'color: #f44336; font-weight: bold;' : 'color: #666;';
                        const levelText = changes.level > 0 ? `+${changes.level}` : String(changes.level);
                        levelDisplay = `<span style="${levelClass}">${levelText} (${previousLevel} → ${currentLevel})</span>`;
                    }
                    let totalAADisplay;
                    if (isDeleted) {
                        totalAADisplay = `<span style="color: #999;">—</span>`;
                    } else if (currentLevel >= 50 || previousLevel >= 50) {
                        const endChar = endState[charName];
                        totalAADisplay = String(endChar ? endChar.aa_total : '—');
                    } else {
                        totalAADisplay = `<span style="color: #666;">—</span>`;
                    }
                    let aaDisplay;
                    if (isDeleted) {
                        aaDisplay = `<span style="color: #f44336; font-weight: bold;">—</span>`;
                    } else if (currentLevel >= 50 || previousLevel >= 50) {
                        const aaClass = changes.aa > 0 ? 'color: #4CAF50; font-weight: bold;' : changes.aa < 0 ? 'color: #f44336; font-weight: bold;' : 'color: #666;';
                        const aaText = changes.aa > 0 ? `+${changes.aa}` : String(changes.aa);
                        aaDisplay = `<span style="${aaClass}">${aaText}</span>`;
                    } else {
                        aaDisplay = `<span style="color: #666;">—</span>`;
                    }
                    reportHTML += `
                        <tr>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${charDisplay}</td>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${changes.class || 'Unknown'}</td>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${isDeleted ? previousLevel : currentLevel}</td>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${levelDisplay}</td>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${totalAADisplay}</td>
                            <td style="padding: 10px; text-align: left; border-bottom: 1px solid #ddd;">${aaDisplay}</td>
                        </tr>`;
                }
                reportHTML += `
                    </tbody>
                </table>`;
            } else {
                reportHTML += `
                <h2 id="character-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Character Level & AA Changes</h2>
                <p style="color: #999; font-style: italic;">No level or AA changes detected.</p>`;
            }

            if (nonVisLevel1.length > 0) {
                reportHTML += `
                <h2 id="inventory-changes-level1" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Level 1 Inventory Changes (Mules/Traders)</h2>
                <p><em>Showing level 1 characters with inventory changes (limited to 500)</em></p>`;
                for (const charName of nonVisLevel1) {
                    const delta = invDeltasLevel1[charName];
                    reportHTML += `
                <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff9e6;">
                    <h3 style="margin-top: 0;"><strong>${formatCharDisplay(charName, charStateForName(charName, startState, endState))}</strong>${charTimelineLink(charName)} <span style="color: #666; font-size: 0.9em;">(Level 1)</span></h3>`;
                    if (Object.keys(delta.added || {}).length > 0) {
                        reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #4CAF50;">Items Added:</strong><div style="margin-top: 5px;">`;
                        for (const itemId of Object.keys(delta.added).sort()) {
                            const count = delta.added[itemId];
                            const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                            const countText = count > 1 ? ' x' + count : '';
                            reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #e8f5e9; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #2e7d32;">${name}</a>${countText}</span>`;
                        }
                        reportHTML += `</div></div>`;
                    }
                    if (Object.keys(delta.removed || {}).length > 0) {
                        reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #f44336;">Items Removed:</strong><div style="margin-top: 5px;">`;
                        for (const itemId of Object.keys(delta.removed).sort()) {
                            const count = delta.removed[itemId];
                            const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                            const countText = count > 1 ? ' x' + count : '';
                            reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #ffebee; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #c62828;">${name}</a>${countText}</span>`;
                        }
                        reportHTML += `</div></div>`;
                    }
                    reportHTML += `</div>`;
                }
            }

            if (nonVisOthers.length > 0) {
                reportHTML += `
                <h2 id="inventory-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Inventory Changes</h2>
                <p><em>Showing characters with inventory changes (limited to 500)</em></p>`;
                for (const charName of nonVisOthers) {
                    const delta = invDeltasOthers[charName];
                    reportHTML += `
                <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
                    <h3 style="margin-top: 0;"><strong>${formatCharDisplay(charName, charStateForName(charName, startState, endState))}</strong>${charTimelineLink(charName)}</h3>`;
                    if (Object.keys(delta.added || {}).length > 0) {
                        reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #4CAF50;">Items Added:</strong><div style="margin-top: 5px;">`;
                        for (const itemId of Object.keys(delta.added).sort()) {
                            const count = delta.added[itemId];
                            const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                            const countText = count > 1 ? ' x' + count : '';
                            reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #e8f5e9; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #2e7d32;">${name}</a>${countText}</span>`;
                        }
                        reportHTML += `</div></div>`;
                    }
                    if (Object.keys(delta.removed || {}).length > 0) {
                        reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #f44336;">Items Removed:</strong><div style="margin-top: 5px;">`;
                        for (const itemId of Object.keys(delta.removed).sort()) {
                            const count = delta.removed[itemId];
                            const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                            const countText = count > 1 ? ' x' + count : '';
                            reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #ffebee; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #c62828;">${name}</a>${countText}</span>`;
                        }
                        reportHTML += `</div></div>`;
                    }
                    reportHTML += `</div>`;
                }
            } else {
                reportHTML += `
                <h2 id="inventory-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Inventory Changes</h2>
                <p style="color: #999; font-style: italic;">${Object.keys(invDeltas).length === 0 ? 'No inventory changes detected.' : 'No inventory changes to list (only visibility changes in this range).'}</p>`;
            }

            if (displayNonVisTracked.length > 0) {
                reportHTML += `
                <h2 id="tracked-items" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>
                <p><em>Changes in raid loot, elemental armor, and praesterium items — see who acquired or lost these${ctx.hasTrackedEventDates ? ', with the date each change occurred' : ''}.</em></p>`;
                let trackedSectionRendered = false;
                for (const charName of displayNonVisTracked) {
                    const delta = displayTrackedDeltas[charName];
                    const charRows = (ctx.trackedRowsByChar && ctx.trackedRowsByChar[charName]) || null;
                    const datedRows = charRows
                        ? filterTrackedRows(charRows, lootFilters).sort((a, b) =>
                            (a.date || '').localeCompare(b.date || '') || String(a.itemId).localeCompare(String(b.itemId)))
                        : null;
                    if (datedRows && !datedRows.length) continue;
                    trackedSectionRendered = true;
                    const state = charStateForName(charName, startState, endState);
                    const level = state.level || '?';
                    const charDisplay = formatCharDisplay(charName, state);
                    const charSlug = charName.toLowerCase().replace(/ /g, '_');
                    const mageloUrl = 'https://www.takproject.net/magelo/character.php?char=' + encodeURIComponent(charSlug);
                    reportHTML += `
                <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff8e1;">
                    <h3 style="margin-top: 0;"><a href="${mageloUrl}" target="_blank" style="text-decoration: none; font-weight: bold;">${charDisplay}</a>${charTimelineLink(charName)} <span style="color: #666; font-size: 0.9em;">(Level ${level})</span></h3>`;
                    if (datedRows && datedRows.length) {
                        reportHTML += `
                    <table class="tracked-items-table">
                        <thead><tr><th>Date</th><th>Change</th><th>Item</th><th>Source</th></tr></thead>
                        <tbody>`;
                        for (const row of datedRows) {
                            const signClass = row.sign > 0 ? 'pos' : 'neg';
                            const signLabel = row.sign > 0 ? '+' + row.count : '-' + row.count;
                            const qty = row.count > 1 ? ' x' + row.count : '';
                            const badgeBg = row.sign > 0 ? '#e8f5e9' : '#ffebee';
                            const linkColor = row.sign > 0 ? '#2e7d32' : '#c62828';
                            reportHTML += `
                            <tr>
                                <td>${escapeHtmlText(row.date || '—')}</td>
                                <td><span class="${signClass}">${signLabel}</span></td>
                                <td><span style="display: inline-block; padding: 2px 8px; background: ${badgeBg}; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${row.itemId}" target="_blank" style="color: ${linkColor}; text-decoration: none;">${escapeHtmlText(row.itemName)}</a>${qty}</span></td>
                                <td style="color: #666;">${escapeHtmlText(row.source || '—')}</td>
                            </tr>`;
                        }
                        reportHTML += `
                        </tbody>
                    </table>`;
                    } else {
                        if (Object.keys(delta.added || {}).length > 0) {
                            reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #4CAF50;">Acquired:</strong><div style="margin-top: 5px;">`;
                            for (const itemId of Object.keys(delta.added).sort()) {
                                const count = delta.added[itemId];
                                const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                                const countText = count > 1 ? ' x' + count : '';
                                const source = (TRACKED_SOURCE_LABEL && TRACKED_SOURCE_LABEL[String(itemId)]) ? ' (' + TRACKED_SOURCE_LABEL[String(itemId)] + ')' : '';
                                reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #e8f5e9; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #2e7d32;">${name}</a>${countText}<span style="color: #888; font-size: 0.85em;">${source}</span></span>`;
                            }
                            reportHTML += `</div></div>`;
                        }
                        if (Object.keys(delta.removed || {}).length > 0) {
                            reportHTML += `
                    <div style="margin: 10px 0;"><strong style="color: #f44336;">Lost:</strong><div style="margin-top: 5px;">`;
                            for (const itemId of Object.keys(delta.removed).sort()) {
                                const count = delta.removed[itemId];
                                const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                                const countText = count > 1 ? ' x' + count : '';
                                const source = (TRACKED_SOURCE_LABEL && TRACKED_SOURCE_LABEL[String(itemId)]) ? ' (' + TRACKED_SOURCE_LABEL[String(itemId)] + ')' : '';
                                reportHTML += `<span style="display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #ffebee; border-radius: 4px;"><a href="https://www.takproject.net/allaclone/item.php?id=${itemId}" target="_blank" style="color: #c62828;">${name}</a>${countText}<span style="color: #888; font-size: 0.85em;">${source}</span></span>`;
                            }
                            reportHTML += `</div></div>`;
                        }
                    }
                    reportHTML += `</div>`;
                }
                if (!trackedSectionRendered && hasLootFilters && nonVisTracked.length > 0) {
                    reportHTML += `<p style="color: #999; font-style: italic;">No tracked items match the current loot filters.</p>`;
                }
            } else if (hasLootFilters && nonVisTracked.length > 0) {
                reportHTML += `
                <h2 id="tracked-items" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>
                <p style="color: #999; font-style: italic;">No tracked items match the current loot filters.</p>`;
            }

            return reportHTML;
        }
        
        async function generateDateRangeReport() {
            let start = document.getElementById('start_date').value;
            let end = document.getElementById('end_date').value;
            if (!start || !end) {
                alert('Please select both start and end dates');
                return;
            }
            // Ensure start is the earlier date and end is the later (forward in time = gains)
            if (start > end) {
                [start, end] = [end, start];
            }
            
            // Validate dates are available
            const missingDates = [];
            if (!availableDates.has(start)) {
                missingDates.push(start);
            }
            if (!availableDates.has(end)) {
                missingDates.push(end);
            }
            if (missingDates.length > 0) {
                const outputDiv = document.getElementById('date_range_output');
                outputDiv.innerHTML = `<p style="color: red; padding: 15px; background: #ffebee; border-radius: 5px;">
                    <strong>Error:</strong> No delta JSON files available for: ${missingDates.join(', ')}<br>
                    Please select dates from the available dates list below.
                </p>`;
                return;
            }
            
            const outputDiv = document.getElementById('date_range_output');
            const filterBar = document.getElementById('report-filters');
            if (filterBar) filterBar.style.display = 'none';
            outputDiv.innerHTML = '<p>Loading deltas and baselines for ' + start + ' and ' + end + '...</p>';
            
            try {
                let invDeltas;
                let charChanges;
                let startState = {};
                let endState = {};
                let startDelta = null;
                let endDelta = null;
                let omitRangeLeaderboards = false;
                let usedFallbackBaseline = false;
                let eventSourceNote = '';
                let dumpBeforeBaselineAny = false;
                let baselineMismatch = false;
                let dumpBeforeBaselineStart = false;
                let dumpBeforeBaselineEnd = false;
                let dqBadStart = false;
                let dqBadEnd = false;
                let corpseLootChars = new Set();

                let rangeCharDeltas = null;
                let startBaselineDateGear = null;
                let endBaselineDateGear = null;
                let absStartInv = {};
                let absEndInv = {};
                let rangeGearEvents = [];

                if (USE_GEAR_EVENTS && GEAR_EVENT_SHARD_MONTHS.length > 0) {
                    outputDiv.innerHTML = '<p>Loading gear events for ' + start + ' to ' + end + '...</p>';
                    const { gear, char } = await loadEventsInRange(start, end);
                    rangeGearEvents = gear;
                    rangeCharDeltas = foldCharEventsToCharDeltas(char);
                    charChanges = charDeltasToChanges(rangeCharDeltas);
                    enrichCharChangesFromFoldedDeltas(charChanges, rangeCharDeltas);
                    eventSourceNote = `gear event log (endpoint inventory diff; ${gear.length} range events, ${char.length} stat events)`;

                    startBaselineDateGear = gearManifestBaselineForDate(start);
                    endBaselineDateGear = gearManifestBaselineForDate(end);
                    baselineMismatch = !!(startBaselineDateGear && endBaselineDateGear
                        && startBaselineDateGear !== endBaselineDateGear);
                    omitRangeLeaderboards = baselineMismatch;

                    const baselineDate = endBaselineDateGear;
                    if (baselineDate) {
                        outputDiv.innerHTML = '<p>Loading baseline for character and inventory state...</p>';
                        const baselineResult = await loadBaseline(baselineDate);
                        if (baselineResult && baselineResult.baseline) {
                            usedFallbackBaseline = baselineResult.usedFallback;
                            const [charUpToEnd, gearUpToEnd] = await Promise.all([
                                loadCharEventsUpTo(end, (done, total) => {
                                    outputDiv.innerHTML = '<p>Loading char shards (' + done + '/' + total + ')...</p>';
                                }),
                                loadGearEventsUpTo(end, (done, total) => {
                                    outputDiv.innerHTML = '<p>Loading gear shards (' + done + '/' + total + ')...</p>';
                                }),
                            ]);
                            const eraBaselineDate = baselineResult.baseline.baseline_date || baselineDate;
                            const charUpToStart = filterCharEventsForBaseline(
                                charUpToEnd.filter(ev => ev.d && ev.d <= start),
                                eraBaselineDate
                            );
                            const charUpToEndEra = filterCharEventsForBaseline(charUpToEnd, eraBaselineDate);
                            const gearUpToStart = gearUpToEnd.filter(ev => ev.d && ev.d <= start);
                            outputDiv.innerHTML = '<p>Computing inventory snapshots...</p>';
                            await new Promise(r => setTimeout(r, 0));
                            startState = buildCharacterStateFromEvents(baselineResult.baseline, charUpToStart);
                            endState = buildCharacterStateFromEvents(baselineResult.baseline, charUpToEndEra);
                            absStartInv = buildInventoryAbsMapFromEvents(baselineResult.baseline, gearUpToStart);
                            absEndInv = buildInventoryAbsMapFromEvents(baselineResult.baseline, gearUpToEnd);
                            invDeltas = diffInventoryAbsMaps(absStartInv, absEndInv, {}, {});
                            resolveItemNames(invDeltas, ITEM_ID_TO_NAME);
                            enrichCharChangesFromStates(charChanges, startState, endState, rangeCharDeltas);
                            for (const charName of Object.keys(startState)) {
                                if (charName in endState || charName in invDeltas) continue;
                                invDeltas[charName] = { added: {}, removed: {}, item_names: {}, is_visibility_change: true };
                            }
                            for (const charName of Object.keys(endState)) {
                                if (charName in startState || charName in invDeltas) continue;
                                invDeltas[charName] = { added: {}, removed: {}, item_names: {}, is_visibility_change: true };
                            }
                            for (const charName of Object.keys(invDeltas)) {
                                const delta = invDeltas[charName];
                                const inStart = charName in startState;
                                const inEnd = charName in endState;
                                if (!delta.is_visibility_change) {
                                    delta.is_visibility_change = (inStart && !inEnd) || (!inStart && inEnd);
                                }
                            }
                        } else {
                            invDeltas = foldGearEventsToInvDeltas(gear);
                            resolveItemNames(invDeltas, ITEM_ID_TO_NAME);
                        }
                    } else {
                        invDeltas = foldGearEventsToInvDeltas(gear);
                        resolveItemNames(invDeltas, ITEM_ID_TO_NAME);
                    }
                } else {
                // Legacy: cumulative daily JSON endpoints
                // Load deltas and baselines for both dates
                const [startDelta, endDelta] = await Promise.all([
                    loadDeltaJSON(start),
                    loadDeltaJSON(end)
                ]);
                
                if (!startDelta || !endDelta) {
                    outputDiv.innerHTML = '<p style="color: red;">Error: Could not load delta JSONs for the selected dates.</p>';
                    return;
                }
                
                // Check if baselines match
                baselineMismatch = startDelta.baseline_date !== endDelta.baseline_date;
                dumpBeforeBaselineStart = startDelta.date && startDelta.baseline_date && startDelta.baseline_date !== 'Unknown' && String(startDelta.date) < String(startDelta.baseline_date);
                dumpBeforeBaselineEnd = endDelta.date && endDelta.baseline_date && endDelta.baseline_date !== 'Unknown' && String(endDelta.date) < String(endDelta.baseline_date);
                dqBadStart = !!(startDelta.data_quality && startDelta.data_quality.dump_before_baseline);
                dqBadEnd = !!(endDelta.data_quality && endDelta.data_quality.dump_before_baseline);
                dumpBeforeBaselineAny = dumpBeforeBaselineStart || dumpBeforeBaselineEnd || dqBadStart || dqBadEnd;
                // Leaderboard AA/HP is endState - startState. Across different baseline_date (rotation),
                // sparse char_deltas can leave start AA equal to an old baseline snapshot while end shows
                // full cumulative vs the new baseline — looks like multi-day "gains" that are mostly rotation math.
                omitRangeLeaderboards = dumpBeforeBaselineAny || baselineMismatch;
                
                // Load baselines (needed to reconstruct full character states)
                outputDiv.innerHTML = '<p>Loading baselines... (this may take a moment)</p>';
                const [startResult, endResult] = await Promise.all([
                    loadBaseline(startDelta.baseline_date),
                    loadBaseline(endDelta.baseline_date)
                ]);
                
                if (!startResult || !endResult) {
                    outputDiv.innerHTML = '<p style="color: red;">Error: Could not load baseline JSONs. Baselines may not be available on GitHub Pages.</p>';
                    return;
                }
                const startBaseline = startResult.baseline;
                const endBaseline = endResult.baseline;
                usedFallbackBaseline = startResult.usedFallback || endResult.usedFallback;
                
                // Character changes: compare_delta_to_delta on endpoints (Python get_date_range_deltas); delta.html uses dump-vs-dump
                outputDiv.innerHTML = '<p>Computing character changes...</p>';
                startState = reconstructCharacterState(startBaseline, startDelta);
                endState = reconstructCharacterState(endBaseline, endDelta);
                let rangeCharDeltas;
                if (baselineMismatch) {
                    rangeCharDeltas = compareDeltaToDeltaCharsCrossBaseline(
                        startDelta, endDelta, startBaseline, endBaseline
                    );
                } else {
                    rangeCharDeltas = compareDeltaToDeltaChars(
                        startDelta, endDelta, startBaseline.characters || {}
                    );
                }
                charChanges = charDeltasToChanges(rangeCharDeltas);
                
                // Inventory: rebuild absolute bags (baseline + cumulative inv delta), then diff.
                // Matches Python get_date_range_deltas across baseline_date boundaries.
                absStartInv = reconstructInventoryAbsMap(startBaseline, startDelta);
                absEndInv = reconstructInventoryAbsMap(endBaseline, endDelta);
                invDeltas = diffInventoryAbsMaps(absStartInv, absEndInv, startDelta.inv_deltas, endDelta.inv_deltas);
                const startInv = startDelta.inv_deltas || {};
                const endInv = endDelta.inv_deltas || {};
                for (const charName of Object.keys(invDeltas)) {
                    const delta = invDeltas[charName];
                    const inStart = charName in startInv;
                    const inEnd = charName in endInv;
                    const inStartState = charName in startState;
                    const inEndState = charName in endState;
                    let isVisibilityChange = (inStartState && !inEndState) || (!inStartState && inEndState);
                    if (!isVisibilityChange) {
                        isVisibilityChange = (inStart && !inEnd) || (!inStart && inEnd);
                    }
                    delta.is_visibility_change = isVisibilityChange;
                }
                // Include characters that exist in one snapshot but not the other (e.g. went anon) so we show "Visibility change" not a fake Lost list
                for (const charName of Object.keys(startState)) {
                    if (charName in endState || charName in invDeltas) continue;
                    invDeltas[charName] = { added: {}, removed: {}, item_names: {}, is_visibility_change: true };
                }
                for (const charName of Object.keys(endState)) {
                    if (charName in startState || charName in invDeltas) continue;
                    invDeltas[charName] = { added: {}, removed: {}, item_names: {}, is_visibility_change: true };
                }
                // Corpse-loot exclusion: 0 real worn at range start -> any worn at end (match delta.html); requires equipped_worn_by_char on both daily JSONs
                corpseLootChars = new Set();
                const emStart = startDelta.equipped_worn_by_char;
                const emEnd = endDelta.equipped_worn_by_char;
                if (emStart && emEnd && typeof emStart === 'object' && typeof emEnd === 'object') {
                    const names = new Set([...Object.keys(emStart), ...Object.keys(emEnd)]);
                    for (const charName of names) {
                        const sc = emStart[charName] && emStart[charName].count;
                        const ec = emEnd[charName] && emEnd[charName].count;
                        if (typeof sc === 'number' && typeof ec === 'number' && sc === 0 && ec >= 1) {
                            corpseLootChars.add(charName);
                        }
                    }
                }
                for (const charName of corpseLootChars) {
                    delete invDeltas[charName];
                }
                }

                const invDeltasLevel1 = {};
                const invDeltasOthers = {};
                for (const [charName, delta] of Object.entries(invDeltas)) {
                    const level = (endState[charName] || startState[charName] || {}).level;
                    if (level === 1) {
                        invDeltasLevel1[charName] = delta;
                    } else {
                        invDeltasOthers[charName] = delta;
                    }
                }
                
                // Filter to tracked items only (raid / elemental armor / praesterium) for Tracked Items section
                const trackedDeltas = {};
                if (TRACKED_ITEM_IDS && TRACKED_ITEM_IDS.size > 0) {
                    for (const [charName, delta] of Object.entries(invDeltas)) {
                        const added = {};
                        const removed = {};
                        const itemNames = {};
                        for (const itemId of Object.keys(delta.added || {})) {
                            if (TRACKED_ITEM_IDS.has(String(itemId))) {
                                added[itemId] = delta.added[itemId];
                                if (delta.item_names && delta.item_names[itemId]) itemNames[itemId] = delta.item_names[itemId];
                            }
                        }
                        for (const itemId of Object.keys(delta.removed || {})) {
                            if (TRACKED_ITEM_IDS.has(String(itemId))) {
                                removed[itemId] = delta.removed[itemId];
                                if (delta.item_names && delta.item_names[itemId]) itemNames[itemId] = delta.item_names[itemId];
                            }
                        }
                        if (Object.keys(added).length > 0 || Object.keys(removed).length > 0 || delta.is_visibility_change) {
                            trackedDeltas[charName] = { added, removed, item_names: itemNames, is_visibility_change: delta.is_visibility_change || false };
                        }
                    }
                }

                const trackedRowsByChar = {};
                if (rangeGearEvents.length > 0) {
                    for (const charName of Object.keys(trackedDeltas)) {
                        const delta = trackedDeltas[charName];
                        if (delta.is_visibility_change || corpseLootChars.has(charName)) continue;
                        const rows = buildRangeTrackedRows(rangeGearEvents, charName, absStartInv[charName] || {});
                        if (rows.length) trackedRowsByChar[charName] = rows;
                    }
                }
                
                // Items by zone: only chars in BOTH snapshots (exclude visibility-change); only raid zones
                // For non-no-drop tracked loot, only add (zone, mob) when serverwide net change for that item is positive
                const netChangeTracked = {};
                for (const [charName, delta] of Object.entries(trackedDeltas)) {
                    for (const itemId of Object.keys(delta.added || {})) {
                        netChangeTracked[itemId] = (netChangeTracked[itemId] || 0) + delta.added[itemId];
                    }
                    for (const itemId of Object.keys(delta.removed || {})) {
                        netChangeTracked[itemId] = (netChangeTracked[itemId] || 0) - delta.removed[itemId];
                    }
                }
                const zoneEntries = {};
                if (TRACKED_ITEM_ZONE && typeof TRACKED_ITEM_ZONE === 'object') {
                    if (rangeGearEvents.length > 0 && Object.keys(trackedRowsByChar).length > 0) {
                        Object.assign(
                            zoneEntries,
                            buildZoneEntriesFromTrackedRows(
                                trackedRowsByChar, startState, endState, netChangeTracked
                            )
                        );
                    } else {
                        for (const [charName, delta] of Object.entries(trackedDeltas)) {
                            if (!startState[charName] || !endState[charName] || delta.is_visibility_change) continue;
                            for (const itemId of Object.keys(delta.added || {})) {
                                if (UNIQUE_TRACKED_IDS.has(String(itemId))) {
                                    const sid = String(itemId);
                                    const startCount = (absStartInv[charName] && absStartInv[charName][sid]) || 0;
                                    const endCount = (absEndInv[charName] && absEndInv[charName][sid]) || 0;
                                    if (endCount <= startCount) continue;
                                }
                                if (!NO_DROP_TRACKED_IDS.has(String(itemId)) && (netChangeTracked[itemId] || 0) <= 0) continue;
                                const zone = TRACKED_ITEM_ZONE[String(itemId)];
                                if (!zone) continue;
                                const mob = (TRACKED_ITEM_MOB && TRACKED_ITEM_MOB[String(itemId)]) || '';
                                const count = delta.added[itemId];
                                const name = (delta.item_names && delta.item_names[itemId]) || ('Item ' + itemId);
                                if (!zoneEntries[zone]) zoneEntries[zone] = {};
                                if (!zoneEntries[zone][mob]) zoneEntries[zone][mob] = [];
                                for (let i = 0; i < count; i++) zoneEntries[zone][mob].push({ charName, itemId, name });
                            }
                        }
                    }
                }
                
                let endBaselineResetDay = false;
                if (!eventSourceNote && endDelta) {
                    endBaselineResetDay = (endDelta.baseline_date === end) &&
                        Object.keys(endDelta.inv_deltas || {}).length === 0;
                }

                const sortedLevel1 = Object.keys(invDeltasLevel1).sort().slice(0, 500);
                const visLevel1 = sortedLevel1.filter(c => invDeltasLevel1[c] && invDeltasLevel1[c].is_visibility_change === true);
                const nonVisLevel1 = sortedLevel1.filter(c => !invDeltasLevel1[c] || invDeltasLevel1[c].is_visibility_change !== true);
                const sortedOthers = Object.keys(invDeltasOthers).sort().slice(0, 500);
                const visOthers = sortedOthers.filter(c => invDeltasOthers[c] && invDeltasOthers[c].is_visibility_change === true);
                const nonVisOthers = sortedOthers.filter(c => !invDeltasOthers[c] || invDeltasOthers[c].is_visibility_change !== true);
                const sortedTracked = Object.keys(trackedDeltas).sort();
                const visTracked = sortedTracked.filter(c => trackedDeltas[c] && trackedDeltas[c].is_visibility_change === true);
                const nonVisTracked = sortedTracked.filter(c => !trackedDeltas[c] || trackedDeltas[c].is_visibility_change !== true);
                const allVisNames = [...new Set([...visLevel1, ...visOthers, ...visTracked])].sort();

                const charsInBoth = new Set();
                if (eventSourceNote) {
                    for (const c of Object.keys(startState)) {
                        if (c in endState) charsInBoth.add(c);
                    }
                } else if (!baselineMismatch && startDelta && endDelta) {
                    const sk = Object.keys(startDelta.char_deltas || {});
                    const ek = new Set(Object.keys(endDelta.char_deltas || {}));
                    for (const c of sk) {
                        if (ek.has(c) && !(endDelta.char_deltas[c] || {}).is_deleted) {
                            charsInBoth.add(c);
                        }
                    }
                } else {
                    for (const c of Object.keys(startState)) {
                        if (c in endState) charsInBoth.add(c);
                    }
                }

                const aaLeaderboard = [];
                const hpLeaderboard = [];
                if (!omitRangeLeaderboards) {
                    for (const [charName, changes] of Object.entries(charChanges)) {
                        if (changes.is_deleted || changes.is_new) continue;
                        if (changes.is_visibility_change) continue;
                        if (!charsInBoth.has(charName)) continue;
                        if (corpseLootChars.has(charName)) continue;
                        const currentLevel = changes.current_level;
                        const previousLevel = changes.previous_level;
                        const aaGain = changes.aa;
                        const hpGain = changes.hp;
                        if ((currentLevel >= 50 || previousLevel >= 50) && aaGain > 0) {
                            aaLeaderboard.push({
                                name: charName,
                                class: changes.class || 'Unknown',
                                level: currentLevel,
                                aa_gain: aaGain,
                                aa_total: changes.current_aa_total != null ? changes.current_aa_total : 0
                            });
                        }
                        if (hpGain > 0) {
                            hpLeaderboard.push({
                                name: charName,
                                class: changes.class || 'Unknown',
                                level: currentLevel,
                                hp_gain: hpGain,
                                hp_total: endState[charName]?.hp || 0
                            });
                        }
                    }
                }
                aaLeaderboard.sort((a, b) => b.aa_gain - a.aa_gain);
                hpLeaderboard.sort((a, b) => b.hp_gain - a.hp_gain);

                const filterIndex = buildRangeFilterIndex(zoneEntries, trackedDeltas);
                lastReportContext = {
                    start, end,
                    eventSourceNote, baselineMismatch, omitRangeLeaderboards,
                    usedFallbackBaseline, dumpBeforeBaselineAny,
                    dumpBeforeBaselineStart, dumpBeforeBaselineEnd, dqBadStart, dqBadEnd,
                    startBaselineDateGear, endBaselineDateGear,
                    endBaselineResetDay,
                    startState, endState,
                    startDelta: startDelta || null,
                    endDelta: endDelta || null,
                    invDeltas, invDeltasLevel1, invDeltasOthers,
                    trackedDeltas, zoneEntries,
                    trackedRowsByChar,
                    hasTrackedEventDates: rangeGearEvents.length > 0,
                    charChanges, charsInBoth, corpseLootChars,
                    allVisNames, nonVisLevel1, nonVisOthers, nonVisTracked,
                    aaLeaderboard, hpLeaderboard,
                    filterIndex
                };
                showReportFilterBar(filterIndex);
                outputDiv.innerHTML = buildReportHTML(lastReportContext, getLootFiltersFromUI());
                updateLootFilterBanner(getLootFiltersFromUI());
            } catch (error) {
                if (filterBar) filterBar.style.display = 'none';
                lastReportContext = null;
                outputDiv.innerHTML = `<p style="color: red; padding: 15px; background: #ffebee; border-radius: 5px;">
                    <strong>Error:</strong> ${error.message}<br>
                    <small>Available dates are listed below. Please select dates from the list.</small>
                </p>`;
            }
        }
        
    </script>
""" + GOATCOUNTER_SCRIPT + """
</body>
</html>
"""
    
    history_file = os.path.join(base_dir, "delta-history.html")
    with open(history_file, 'w', encoding='utf-8') as f:
        f.write(html)
    return history_file


def generate_char_timeline(base_dir):
    """Generate on-demand per-character AA/gear timeline page (char.html)."""
    cfg = _gear_event_page_embed_config(base_dir)
    latest_date = json.dumps(cfg["latest_date"])
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TAKP Character Timeline</title>
    <script src="https://cdn.jsdelivr.net/npm/pako@2.1.0/dist/pako.min.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .container { max-width: 1100px; margin: 0 auto; background: #fff; padding: 24px; border-radius: 10px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); }
        h1 { margin-top: 0; color: #333; }
        .meta { color: #666; margin-bottom: 20px; }
        .loading { padding: 20px; background: #f5f5f5; border-radius: 6px; }
        table { width: 100%; border-collapse: collapse; margin: 12px 0 24px; }
        th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f0f0f0; }
        .pos { color: #2e7d32; font-weight: bold; }
        .neg { color: #c62828; font-weight: bold; }
        .vis { color: #9e9e9e; font-style: italic; }
        .note { font-size: 0.9em; color: #757575; background: #fafafa; padding: 10px; border-radius: 5px; border-left: 4px solid #9e9e9e; margin: 12px 0; }
        a.back { color: #667eea; }
        .item-badge { display: inline-block; margin: 2px 4px 2px 0; padding: 2px 8px; background: #e3f2fd; border-radius: 4px; }
        .tracked-section { margin: 20px 0 28px; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff8e1; }
        .tracked-tabs { margin: 12px 0; }
        .tracked-tab { display: inline-block; padding: 8px 16px; margin-right: 8px; border: 1px solid #FF9800; border-radius: 4px; background: #fff; cursor: pointer; font-weight: bold; color: #555; }
        .tracked-tab.active { background: #FF9800; color: #fff; border-color: #FF9800; }
        .tracked-zone-card { margin: 16px 0; padding: 12px; border: 1px solid #ddd; border-radius: 5px; background: #f5f5f5; }
        .item-added { background: #e8f5e9; }
        .item-removed { background: #ffebee; }
    </style>
</head>
<body>
    <div class="container">
        <p><a class="back" href="delta.html">← Daily delta</a> · <a class="back" href="delta-history.html">Delta history</a></p>
        <h1 id="page-title">Character Timeline</h1>
        <div id="char-meta" class="meta"></div>
        <div id="status" class="loading">Loading…</div>
        <div id="content" style="display:none;"></div>
        <div class="note">
            <strong>Notes:</strong> AA and gear history are reconstructed from the gear event log plus the master baseline.
            Items held since the baseline era without inventory events are labeled accordingly.
            Gear events track item counts, not equipment slots. First load may download several MB of compressed shard data; your browser caches it for 24 hours after the first load.
        </div>
    </div>
    <script type="application/json" id="gear-event-shard-months">""" + cfg["gear_shard_months_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="gear-event-manifest">""" + cfg["gear_event_manifest_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="item-id-to-name">""" + cfg["item_id_to_name_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="char-guild-map">""" + cfg["char_guild_map_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="no-rent-item-ids">""" + cfg["no_rent_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-item-ids">""" + cfg["tracked_ids_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-source-label">""" + cfg["tracked_source_label_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-item-zone">""" + cfg["tracked_item_zone_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="tracked-item-mob">""" + cfg["tracked_item_mob_json"].replace("</", "<\\/") + """</script>
    <script type="application/json" id="unique-tracked-ids">""" + cfg["unique_tracked_ids_json"].replace("</", "<\\/") + """</script>
    <script>
        const GEAR_EVENT_SHARD_MONTHS = JSON.parse(document.getElementById('gear-event-shard-months').textContent);
        const GEAR_EVENT_MANIFEST = JSON.parse(document.getElementById('gear-event-manifest').textContent);
        const ITEM_ID_TO_NAME = JSON.parse(document.getElementById('item-id-to-name').textContent);
        const CHAR_GUILD_MAP = JSON.parse(document.getElementById('char-guild-map').textContent);
        const NO_RENT_ITEMS = new Set(JSON.parse(document.getElementById('no-rent-item-ids').textContent).map(String));
        const TRACKED_ITEM_IDS = new Set(JSON.parse(document.getElementById('tracked-item-ids').textContent).map(String));
        const TRACKED_SOURCE_LABEL = JSON.parse(document.getElementById('tracked-source-label').textContent);
        const TRACKED_ITEM_ZONE = JSON.parse(document.getElementById('tracked-item-zone').textContent);
        const TRACKED_ITEM_MOB = JSON.parse(document.getElementById('tracked-item-mob').textContent);
        const UNIQUE_TRACKED_IDS = new Set(JSON.parse(document.getElementById('unique-tracked-ids').textContent).map(String));
        const LATEST_DATE = """ + latest_date + """;
        const USE_GEAR_EVENTS = """ + cfg["use_gear_events_json"] + """;

        const params = new URLSearchParams(window.location.search);
        const CHAR_NAME = params.get('c') || '';

""" + _gear_event_fetch_client_js() + """
        let loadedGearShards = new Map();
        let loadedCharShards = new Map();
        let loadedBaselines = new Map();

        function monthsBetween(start, end) {
            const out = [];
            let y = parseInt(start.slice(0, 4), 10), m = parseInt(start.slice(5, 7), 10);
            const ey = parseInt(end.slice(0, 4), 10), em = parseInt(end.slice(5, 7), 10);
            while (y < ey || (y === ey && m <= em)) {
                out.push(`${y}-${String(m).padStart(2, '0')}`);
                m += 1;
                if (m > 12) { m = 1; y += 1; }
            }
            return out;
        }

        async function loadGearShard(month) {
            if (loadedGearShards.has(month)) return loadedGearShards.get(month);
            const url = `delta_snapshots/gear_events/gear_${month}.json.gz`;
            const events = await fetchGzJsonCached(url);
            loadedGearShards.set(month, events);
            return events;
        }

        async function loadCharShard(month) {
            if (loadedCharShards.has(month)) return loadedCharShards.get(month);
            const url = `delta_snapshots/gear_events/char_${month}.json.gz`;
            const events = await fetchGzJsonCached(url, { optional: true });
            const result = events || [];
            loadedCharShards.set(month, result);
            return result;
        }

        function gearManifestFirstEventMonthForDate(dateStr) {
            const eras = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.eras) || [];
            for (let i = eras.length - 1; i >= 0; i--) {
                const era = eras[i];
                if (era.first_event && era.first_event <= dateStr) return era.first_event.slice(0, 7);
            }
            return GEAR_EVENT_SHARD_MONTHS.length ? GEAR_EVENT_SHARD_MONTHS[0] : dateStr.slice(0, 7);
        }

        function gearManifestBaselineForDate(dateStr) {
            const days = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.days) || {};
            if (days[dateStr] && days[dateStr].baseline_date) return days[dateStr].baseline_date;
            const eras = (GEAR_EVENT_MANIFEST && GEAR_EVENT_MANIFEST.eras) || [];
            for (let i = eras.length - 1; i >= 0; i--) {
                const era = eras[i];
                if (era.first_event && era.first_event <= dateStr && era.baseline_date) return era.baseline_date;
            }
            return null;
        }

        async function loadEventsUpTo(endDate, onProgress) {
            const firstMonth = gearManifestFirstEventMonthForDate(endDate);
            const months = monthsBetween(firstMonth, endDate.slice(0, 7))
                .filter(m => GEAR_EVENT_SHARD_MONTHS.includes(m));
            let done = 0;
            const results = await Promise.all(months.map(async (month) => {
                const [gear, chars] = await Promise.all([loadGearShard(month), loadCharShard(month)]);
                done += 1;
                if (onProgress) onProgress(done, months.length);
                return { gear, chars };
            }));
            const gear = results.flatMap(r => r.gear).filter(ev => ev.d && ev.d <= endDate);
            const chars = results.flatMap(r => r.chars).filter(ev => ev.d && ev.d <= endDate);
            return { gear, chars };
        }

        async function loadBaseline(baselineDate) {
            const want = String(baselineDate);
            const cacheKey = 'baseline_' + want;
            if (loadedBaselines.has(cacheKey)) return loadedBaselines.get(cacheKey);
            const archivedUrl = `delta_snapshots/baseline_master_${baselineDate}.json.gz`;
            const currentUrl = 'delta_snapshots/baseline_master.json.gz';
            let baseline = await fetchGzJsonCached(archivedUrl, { optional: true });
            let usedFallback = false;
            if (!baseline) {
                baseline = await fetchGzJsonCached(currentUrl);
                usedFallback = true;
            }
            const result = { baseline, usedFallback };
            loadedBaselines.set(cacheKey, result);
            return result;
        }

        function foldCharEventsToCharDeltas(charEvents) {
            const charDeltas = {};
            const sorted = [...(charEvents || [])].sort((a, b) => (a.d || '').localeCompare(b.d || '') || (a.c || '').localeCompare(b.c || ''));
            for (const ev of sorted) {
                const charName = ev.c;
                if (!charName) continue;
                if (!charDeltas[charName]) {
                    charDeltas[charName] = { level_change: 0, aa_total_change: 0, hp_change: 0, class: '', is_deleted: false };
                }
                const row = charDeltas[charName];
                if (ev.cl) row.class = ev.cl;
                if (ev.f === 'lvl') row.level_change += Number(ev.n) || 0;
                else if (ev.f === 'aa') row.aa_total_change += Number(ev.n) || 0;
                else if (ev.f === 'hp') row.hp_change += Number(ev.n) || 0;
                else if (ev.f === 'del') row.is_deleted = true;
            }
            return charDeltas;
        }

        function buildCharacterStateFromEvents(baseline, charEvents) {
            const folded = foldCharEventsToCharDeltas(charEvents);
            const baselineChars = (baseline && baseline.characters) || {};
            const fullState = {};
            for (const [charName, charData] of Object.entries(baselineChars)) {
                fullState[charName] = {
                    level: charData.level || 0,
                    aa_total: (charData.aa_unspent || 0) + (charData.aa_spent || 0),
                    hp: charData.hp_max_total || 0,
                    class: charData.class || '',
                    guild: charData.guild || ''
                };
            }
            for (const [charName, deltaData] of Object.entries(folded)) {
                if (deltaData.is_deleted) { delete fullState[charName]; continue; }
                if (fullState[charName]) {
                    fullState[charName].level += deltaData.level_change || 0;
                    fullState[charName].aa_total += deltaData.aa_total_change || 0;
                    fullState[charName].hp += deltaData.hp_change || 0;
                    if (deltaData.class) fullState[charName].class = deltaData.class;
                } else {
                    fullState[charName] = {
                        level: Math.max(0, deltaData.level_change || 0),
                        aa_total: Math.max(0, deltaData.aa_total_change || 0),
                        hp: Math.max(0, deltaData.hp_change || 0),
                        class: deltaData.class || '',
                        guild: ''
                    };
                }
            }
            return fullState;
        }

        function filterEventsForChar(events, charName) {
            return (events || []).filter(ev => ev.c === charName);
        }

        function filterCharEventsForBaseline(events, baselineDate) {
            if (!baselineDate) return events || [];
            return (events || []).filter(ev => {
                if (ev.b != null && ev.b !== baselineDate) return false;
                if (ev.b == null && (ev.f === 'aa' || ev.f === 'lvl' || ev.f === 'hp')
                    && (ev.d || '') < baselineDate) return false;
                return true;
            });
        }

        function buildItemNameMap(baseline, charName) {
            const map = Object.assign({}, ITEM_ID_TO_NAME);
            for (const item of ((baseline.inventories || {})[charName] || [])) {
                const id = String(item.item_id);
                if (item.item_name && !map[id]) map[id] = item.item_name;
            }
            return map;
        }

        function buildAaTimeline(baseline, charEvents, charName) {
            const bl = ((baseline.characters || {})[charName]) || {};
            let running = (bl.aa_unspent || 0) + (bl.aa_spent || 0);
            const baselineDate = baseline.baseline_date || '';
            const rows = [];
            if ((baseline.characters || {})[charName] || running > 0) {
                rows.push({ date: baselineDate, delta: 0, total: running, isBaseline: true });
            }
            const eraEvents = filterCharEventsForBaseline(charEvents, baselineDate);
            const aaEvents = filterEventsForChar(eraEvents, charName)
                .filter(ev => ev.f === 'aa')
                .sort((a, b) => (a.d || '').localeCompare(b.d || ''));
            for (const ev of aaEvents) {
                const n = Number(ev.n) || 0;
                running += n;
                if (ev.aa != null) running = Number(ev.aa);
                rows.push({ date: ev.d, delta: n, total: running, isBaseline: false });
            }
            return rows;
        }

        function buildCurrentHoldings(baseline, gearEvents, charName) {
            const baselineItems = ((baseline.inventories || {})[charName] || []);
            const charGear = filterEventsForChar(gearEvents, charName);
            if (!baselineItems.length && !charGear.length) return {};
            const counts = {};
            for (const item of baselineItems) {
                const id = String(item.item_id);
                if (!id || id.toUpperCase() === 'NULL' || id === '0' || NO_RENT_ITEMS.has(id)) continue;
                counts[id] = (counts[id] || 0) + 1;
            }
            for (const ev of charGear.sort((a, b) => (a.d || '').localeCompare(b.d || ''))) {
                const id = String(ev.i);
                const sign = Number(ev.s);
                const n = Number(ev.n) || 0;
                if (!id || n <= 0 || (sign !== 1 && sign !== -1) || NO_RENT_ITEMS.has(id)) continue;
                if (sign > 0) counts[id] = (counts[id] || 0) + n;
                else {
                    counts[id] = (counts[id] || 0) - n;
                    if (counts[id] <= 0) delete counts[id];
                }
            }
            return counts;
        }

        function buildGearEventLog(gearEvents, charName, nameMap) {
            return filterEventsForChar(gearEvents, charName)
                .filter(ev => {
                    const n = Number(ev.n) || 0;
                    const sign = Number(ev.s);
                    return n > 0 && (sign === 1 || sign === -1);
                })
                .sort((a, b) => (a.d || '').localeCompare(b.d || '') || String(a.i).localeCompare(String(b.i)))
                .map(ev => ({
                    date: ev.d,
                    sign: Number(ev.s),
                    count: Number(ev.n),
                    itemId: String(ev.i),
                    itemName: nameMap[String(ev.i)] || ('Item ' + ev.i),
                    visibility: !!ev.v
                }));
        }

        function baselineOnlyItems(holdings, gearEvents, charName) {
            const touched = new Set(filterEventsForChar(gearEvents, charName).map(ev => String(ev.i)));
            const out = {};
            for (const [id, cnt] of Object.entries(holdings)) {
                if (!touched.has(id)) out[id] = cnt;
            }
            return out;
        }

        function buildTrackedGearEventLog(gearEvents, charName, nameMap, baseline) {
            if (!TRACKED_ITEM_IDS.size) return [];
            const holdings = {};
            for (const item of ((baseline.inventories || {})[charName] || [])) {
                const id = String(item.item_id);
                if (!id || id.toUpperCase() === 'NULL' || id === '0' || NO_RENT_ITEMS.has(id)) continue;
                holdings[id] = (holdings[id] || 0) + 1;
            }
            const rows = [];
            const sorted = filterEventsForChar(gearEvents, charName)
                .sort((a, b) => (a.d || '').localeCompare(b.d || '') || String(a.i).localeCompare(String(b.i)));
            for (const ev of sorted) {
                if (ev.v) continue;
                const sign = Number(ev.s);
                const n = Number(ev.n) || 0;
                const iid = String(ev.i);
                if (!iid || n <= 0 || (sign !== 1 && sign !== -1) || NO_RENT_ITEMS.has(iid)) continue;
                const isTracked = TRACKED_ITEM_IDS.has(iid);
                if (isTracked && sign > 0 && UNIQUE_TRACKED_IDS.has(iid) && (holdings[iid] || 0) > 0) continue;
                if (isTracked) {
                    rows.push({
                        date: ev.d,
                        sign: sign,
                        count: n,
                        itemId: iid,
                        itemName: nameMap[iid] || ('Item ' + iid),
                        source: TRACKED_SOURCE_LABEL[iid] || ''
                    });
                }
                if (sign > 0) holdings[iid] = (holdings[iid] || 0) + n;
                else {
                    holdings[iid] = (holdings[iid] || 0) - n;
                    if (holdings[iid] <= 0) delete holdings[iid];
                }
            }
            return rows;
        }

        function baselineOnlyTracked(holdings, gearEvents, charName) {
            const only = baselineOnlyItems(holdings, gearEvents, charName);
            const out = {};
            for (const [id, cnt] of Object.entries(only)) {
                if (TRACKED_ITEM_IDS.has(id)) out[id] = cnt;
            }
            return out;
        }

        function renderTrackedItemsSection(trackedRows, sinceBaselineTracked, baselineDateStr, nameMap) {
            if (!TRACKED_ITEM_IDS.size) return '';
            let html = '<div class="tracked-section" id="tracked-items">';
            html += '<h2 style="margin-top:0;">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>';
            html += '<p><em>Raid loot, elemental armor, and praesterium items for this character.</em></p>';
            html += '<div class="tracked-tabs">';
            html += '<button type="button" class="tracked-tab active" data-tab="timeline">Timeline</button>';
            html += '<button type="button" class="tracked-tab" data-tab="zone">By Zone</button>';
            html += '</div>';

            html += '<div id="tracked-timeline-view">';
            if (trackedRows.length) {
                html += '<table><thead><tr><th>Date</th><th>Change</th><th>Item</th><th>Source</th></tr></thead><tbody>';
                for (const row of trackedRows) {
                    const sign = row.sign > 0
                        ? '<span class="pos">+' + row.count + '</span>'
                        : '<span class="neg">-' + row.count + '</span>';
                    const badgeClass = row.sign > 0 ? 'item-added' : 'item-removed';
                    const qty = row.count > 1 ? ' x' + row.count : '';
                    html += '<tr><td>' + esc(row.date) + '</td><td>' + sign + '</td><td>'
                        + '<span class="item-badge ' + badgeClass + '"><a href="https://www.takproject.net/allaclone/item.php?id=' + row.itemId + '" target="_blank">'
                        + esc(row.itemName) + '</a>' + qty + '</span></td><td>'
                        + esc(row.source || '—') + '</td></tr>';
                }
                html += '</tbody></table>';
            } else {
                html += '<p class="vis">No tracked item changes recorded for this character.</p>';
            }
            html += '</div>';

            html += '<div id="tracked-zone-view" style="display:none;">';
            if (trackedRows.length) {
                const byZone = {};
                for (const row of trackedRows) {
                    const zone = TRACKED_ITEM_ZONE[row.itemId] || 'Other';
                    const mob = TRACKED_ITEM_MOB[row.itemId] || '';
                    if (!byZone[zone]) byZone[zone] = {};
                    if (!byZone[zone][mob]) byZone[zone][mob] = [];
                    byZone[zone][mob].push(row);
                }
                for (const zone of Object.keys(byZone).sort()) {
                    html += '<div class="tracked-zone-card"><h3 style="margin-top:0;">' + esc(zone) + '</h3>';
                    const mobKeys = Object.keys(byZone[zone]).sort((a, b) => (a === '' ? 1 : b === '' ? -1 : a.localeCompare(b)));
                    for (const mob of mobKeys) {
                        if (mob) html += '<h4 style="margin:12px 0 6px;font-size:1em;color:#555;">' + esc(mob) + '</h4>';
                        html += '<ul style="margin:0;padding-left:20px;">';
                        for (const row of byZone[zone][mob]) {
                            const signLabel = row.sign > 0 ? '+' : '-';
                            const qty = row.count > 1 ? ' x' + row.count : '';
                            html += '<li><span style="color:#666;">' + esc(row.date) + '</span> — '
                                + '<span class="' + (row.sign > 0 ? 'pos' : 'neg') + '">' + signLabel + row.count + '</span> '
                                + '<a href="https://www.takproject.net/allaclone/item.php?id=' + row.itemId + '" target="_blank" style="color:#2e7d32;">'
                                + esc(row.itemName) + '</a>' + qty + '</li>';
                        }
                        html += '</ul>';
                    }
                    html += '</div>';
                }
            } else {
                html += '<p class="vis">No tracked item changes recorded for this character.</p>';
            }
            html += '</div>';

            if (Object.keys(sinceBaselineTracked).length) {
                html += '<p class="note" style="margin-bottom:0;"><strong>Held since baseline (' + esc(baselineDateStr) + '):</strong> ';
                const parts = Object.keys(sinceBaselineTracked).sort((a, b) =>
                    (nameMap[a] || a).localeCompare(nameMap[b] || b)
                ).map(id => esc(nameMap[id] || ('Item ' + id)) + (sinceBaselineTracked[id] > 1 ? ' x' + sinceBaselineTracked[id] : ''));
                html += parts.join(', ') + '</p>';
            }
            html += '</div>';
            return html;
        }

        function bindTrackedTabs() {
            const tabs = document.querySelectorAll('.tracked-tab');
            const timelineView = document.getElementById('tracked-timeline-view');
            const zoneView = document.getElementById('tracked-zone-view');
            tabs.forEach(btn => {
                btn.addEventListener('click', () => {
                    tabs.forEach(t => t.classList.remove('active'));
                    btn.classList.add('active');
                    const tab = btn.getAttribute('data-tab');
                    if (tab === 'zone') {
                        timelineView.style.display = 'none';
                        zoneView.style.display = 'block';
                    } else {
                        timelineView.style.display = 'block';
                        zoneView.style.display = 'none';
                    }
                });
            });
        }

        function esc(s) {
            return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
        }

        async function render() {
            const status = document.getElementById('status');
            const content = document.getElementById('content');
            const meta = document.getElementById('char-meta');
            if (!CHAR_NAME) {
                status.innerHTML = '<strong style="color:#c62828;">No character specified.</strong> Use <code>char.html?c=CharacterName</code>';
                return;
            }
            if (!USE_GEAR_EVENTS || !GEAR_EVENT_SHARD_MONTHS.length) {
                status.innerHTML = '<strong style="color:#c62828;">Gear event shards not available.</strong>';
                return;
            }
            const endDate = LATEST_DATE || new Date().toISOString().slice(0, 10);
            document.getElementById('page-title').textContent = CHAR_NAME + ' — Timeline';
            try {
                status.textContent = 'Loading baseline…';
                const baselineDate = gearManifestBaselineForDate(endDate) || '2026-02-09';
                const { baseline } = await loadBaseline(baselineDate);
                status.textContent = 'Loading event shards…';
                const { gear, chars } = await loadEventsUpTo(endDate, (done, total) => {
                    status.textContent = 'Loading event shards (' + done + '/' + total + ')…';
                });
                const eraBaselineDate = baseline.baseline_date || baselineDate;
                const eraChars = filterCharEventsForBaseline(chars, eraBaselineDate);
                const charEvents = filterEventsForChar(eraChars, CHAR_NAME);
                const charGear = filterEventsForChar(gear, CHAR_NAME);
                const stateMap = buildCharacterStateFromEvents(baseline, eraChars);
                const state = stateMap[CHAR_NAME] || {};
                const guild = state.guild || CHAR_GUILD_MAP[CHAR_NAME] || '';
                const guildPart = guild ? ' &lt;' + esc(guild) + '&gt;' : '';
                const mageloSlug = CHAR_NAME.toLowerCase().replace(/ /g, '_');
                meta.innerHTML = '<strong>' + esc(CHAR_NAME) + guildPart + '</strong> · '
                    + (state.class || '?') + ' · Level ' + (state.level || '?')
                    + ' · ' + (state.aa_total != null ? state.aa_total + ' AA' : '? AA')
                    + ' · through ' + esc(endDate)
                    + ' · <a href="https://www.takproject.net/magelo/character.php?char=' + encodeURIComponent(mageloSlug) + '" target="_blank">Magelo</a>';

                const nameMap = buildItemNameMap(baseline, CHAR_NAME);
                const aaRows = buildAaTimeline(baseline, charEvents, CHAR_NAME);
                const holdings = buildCurrentHoldings(baseline, charGear, CHAR_NAME);
                const sinceBaseline = baselineOnlyItems(holdings, charGear, CHAR_NAME);
                const gearLog = buildGearEventLog(charGear, CHAR_NAME, nameMap);
                const trackedRows = buildTrackedGearEventLog(charGear, CHAR_NAME, nameMap, baseline);
                const sinceBaselineTracked = baselineOnlyTracked(holdings, charGear, CHAR_NAME);

                let html = '';
                html += renderTrackedItemsSection(
                    trackedRows,
                    sinceBaselineTracked,
                    baseline.baseline_date || baselineDate,
                    nameMap
                );

                html += '<h2>AA History</h2>';
                if (aaRows.length) {
                    html += '<table><thead><tr><th>Date</th><th>Change</th><th>Total AA</th></tr></thead><tbody>';
                    for (const row of aaRows) {
                        const delta = row.isBaseline ? '<span class="vis">baseline</span>' : (row.delta > 0 ? '<span class="pos">+' + row.delta + '</span>' : (row.delta < 0 ? '<span class="neg">' + row.delta + '</span>' : '0'));
                        html += '<tr><td>' + esc(row.date || '—') + '</td><td>' + delta + '</td><td>' + row.total + '</td></tr>';
                    }
                    html += '</tbody></table>';
                } else {
                    html += '<p class="vis">No AA history for this character.</p>';
                }

                html += '<h2>Current Holdings</h2>';
                if (Object.keys(holdings).length) {
                    html += '<p>';
                    for (const itemId of Object.keys(holdings).sort((a, b) => (nameMap[a] || a).localeCompare(nameMap[b] || b))) {
                        const cnt = holdings[itemId];
                        const nm = esc(nameMap[itemId] || ('Item ' + itemId));
                        const qty = cnt > 1 ? ' x' + cnt : '';
                        html += '<span class="item-badge"><a href="https://www.takproject.net/allaclone/item.php?id=' + itemId + '" target="_blank">' + nm + '</a>' + qty + '</span>';
                    }
                    html += '</p>';
                } else {
                    html += '<p class="vis">No items in reconstructed inventory.</p>';
                }
                if (Object.keys(sinceBaseline).length) {
                    html += '<p class="note"><strong>Held since baseline (' + esc(baseline.baseline_date || baselineDate) + '):</strong> ';
                    const parts = Object.keys(sinceBaseline).sort().map(id => esc(nameMap[id] || ('Item ' + id)) + (sinceBaseline[id] > 1 ? ' x' + sinceBaseline[id] : ''));
                    html += parts.join(', ') + '</p>';
                }

                html += '<h2>Gear Acquisition / Loss Log</h2>';
                if (gearLog.length) {
                    html += '<table><thead><tr><th>Date</th><th>Change</th><th>Item</th></tr></thead><tbody>';
                    for (const row of gearLog) {
                        const sign = row.sign > 0 ? '<span class="pos">+' + row.count + '</span>' : '<span class="neg">-' + row.count + '</span>';
                        const vis = row.visibility ? ' <span class="vis">(visibility)</span>' : '';
                        html += '<tr' + (row.visibility ? ' class="vis"' : '') + '><td>' + esc(row.date) + '</td><td>' + sign + '</td><td>'
                            + '<a href="https://www.takproject.net/allaclone/item.php?id=' + row.itemId + '" target="_blank">' + esc(row.itemName) + '</a>'
                            + ' <span style="color:#999;font-size:0.85em;">(' + row.itemId + ')</span>' + vis + '</td></tr>';
                    }
                    html += '</tbody></table>';
                } else {
                    html += '<p class="vis">No gear events recorded for this character.</p>';
                }

                content.innerHTML = html;
                content.style.display = 'block';
                bindTrackedTabs();
                status.style.display = 'none';
            } catch (err) {
                status.innerHTML = '<strong style="color:#c62828;">Error:</strong> ' + esc(err.message || err);
            }
        }

        render();
    </script>
""" + GOATCOUNTER_SCRIPT + """
</body>
</html>
"""
    out_path = os.path.join(base_dir, "char.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    return out_path


def find_latest_magelo_file(directory, pattern=None):
    """Find the latest magelo dump file in a directory."""
    if not os.path.exists(directory):
        return None
    
    files = []
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath) and filename.endswith('.txt'):
            # Check if it matches pattern or is a TAKP export file
            if pattern is None or pattern in filename or filename.startswith('TAKP_'):
                files.append((filepath, os.path.getmtime(filepath)))
    
    if not files:
        return None
    
    # Return the most recently modified file
    files.sort(key=lambda x: x[1], reverse=True)
    return files[0][0]


def parse_takp_magelo_export_datetime(stamp):
    """Parse TAKP export page / .magelo_update_date stamp (single-line)."""
    s = re.sub(r'\s+', ' ', (stamp or '').strip())
    if not s or s.lower() == 'unknown':
        return None
    try:
        return datetime.strptime(s, '%a %b %d %H:%M:%S UTC %Y')
    except ValueError:
        return None


def delta_magelo_export_dates_plausible(base_dir, current_stamp, max_span_days=2):
    """True if previous stamp file missing, unparseable, or span within max calendar days."""
    path = os.path.join(base_dir, '.magelo_previous_dump_date.txt')
    if not os.path.isfile(path):
        return True
    try:
        with open(path, 'r', encoding='utf-8') as f:
            prev_raw = f.read()
        pt = parse_takp_magelo_export_datetime(prev_raw)
        ct = parse_takp_magelo_export_datetime(current_stamp)
        if not pt or not ct:
            return True
        days = abs((ct.date() - pt.date()).days)
        return days <= max_span_days
    except OSError:
        return True


def parse_date_from_filename(filename):
    """Parse date from filename like '2_6_26.txt' -> (month, day, year).
    Returns (month, day, year) tuple or None if not parseable."""
    import re
    basename = os.path.basename(filename)
    # Match pattern M_D_YY.txt or M_D_YYYY.txt
    match = re.match(r'(\d+)_(\d+)_(\d+)\.txt', basename)
    if match:
        month = int(match.group(1))
        day = int(match.group(2))
        year = int(match.group(3))
        # Handle 2-digit years (assume 2000-2099)
        if year < 100:
            year += 2000
        return (month, day, year)
    return None

def get_yesterday_filename(current_filename):
    """Given a current filename like '2_6_26.txt', return yesterday's filename.
    Returns None if date cannot be parsed."""
    date_tuple = parse_date_from_filename(current_filename)
    if date_tuple is None:
        return None
    
    month, day, year = date_tuple
    try:
        from datetime import datetime, timedelta
        current_date = datetime(year, month, day)
        yesterday = current_date - timedelta(days=1)
        # Format as M_D_YY (2-digit year)
        yesterday_filename = f"{yesterday.month}_{yesterday.day}_{yesterday.year % 100}.txt"
        return yesterday_filename
    except (ValueError, OverflowError):
        return None

def find_yesterday_file(current_file, directory):
    """Find yesterday's file based on current file's date.
    Returns filepath if found, None otherwise."""
    if current_file is None:
        return None
    
    yesterday_filename = get_yesterday_filename(current_file)
    if yesterday_filename is None:
        return None
    
    yesterday_filepath = os.path.join(directory, yesterday_filename)
    if os.path.exists(yesterday_filepath):
        return yesterday_filepath
    return None

def main():
    # File paths
    base_dir = os.path.dirname(__file__)
    char_dir = os.path.join(base_dir, "character")
    inv_dir = os.path.join(base_dir, "inventory")
    output_file = os.path.join(base_dir, "spell_inventory.html")
    
    # Try to find the latest files, prioritizing current files over previous files
    # First, look for current files (not _previous)
    all_char_files = []
    all_inv_files = []
    
    if os.path.exists(char_dir):
        for filename in os.listdir(char_dir):
            if filename.endswith('.txt') and '_previous' not in filename:
                filepath = os.path.join(char_dir, filename)
                if os.path.isfile(filepath):
                    all_char_files.append((filepath, os.path.getmtime(filepath)))
    
    if os.path.exists(inv_dir):
        for filename in os.listdir(inv_dir):
            if filename.endswith('.txt') and '_previous' not in filename:
                filepath = os.path.join(inv_dir, filename)
                if os.path.isfile(filepath):
                    all_inv_files.append((filepath, os.path.getmtime(filepath)))
    
    # Sort by modification time and get the most recent
    if all_char_files:
        all_char_files.sort(key=lambda x: x[1], reverse=True)
        char_file = all_char_files[0][0]
    else:
        char_file = find_latest_magelo_file(char_dir, "TAKP_character") or find_latest_magelo_file(char_dir)
    
    if all_inv_files:
        all_inv_files.sort(key=lambda x: x[1], reverse=True)
        inv_file = all_inv_files[0][0]
    else:
        inv_file = find_latest_magelo_file(inv_dir, "TAKP_character_inventory") or find_latest_magelo_file(inv_dir)
    
    # Fallback to specific filename if nothing found
    if char_file is None:
        char_file = os.path.join(char_dir, "2_6_26.txt")
    if inv_file is None:
        inv_file = os.path.join(inv_dir, "2_6_26.txt")
    
    if not os.path.exists(char_file):
        print(f"Error: Character file not found: {char_file}")
        print(f"Available files in character/: {os.listdir(char_dir) if os.path.exists(char_dir) else 'directory does not exist'}")
        return
    
    if not os.path.exists(inv_file):
        print(f"Error: Inventory file not found: {inv_file}")
        print(f"Available files in inventory/: {os.listdir(inv_dir) if os.path.exists(inv_dir) else 'directory does not exist'}")
        return
    
    print(f"Using character file: {os.path.basename(char_file)}")
    print(f"Using inventory file: {os.path.basename(inv_file)}")
    
    print("Loading spell exchange data...")
    spell_info, spell_data = load_spell_exchange_data()
    print(f"Loaded {len(spell_info)} unique PoK spells")
    
    print(f"Parsing character file: {os.path.basename(char_file)}...")
    char_ids = parse_character_file(char_file, MULE_CHARACTERS)
    print(f"Found {len(char_ids)} mule characters: {', '.join(sorted(char_ids.keys()))}")
    
    # Parse officer mule characters
    officer_char_ids = parse_character_file(char_file, OFFICER_MULE_CHARACTERS)
    print(f"Found {len(officer_char_ids)} officer mule characters: {', '.join(sorted(officer_char_ids.keys()))}")
    
    print(f"Parsing inventory file: {os.path.basename(inv_file)}...")
    inventories = parse_inventory_file(inv_file, char_ids)
    print(f"Found inventories for {len(inventories)} mule characters")
    
    # Parse officer mule inventories
    officer_inventories = parse_inventory_file(inv_file, officer_char_ids) if officer_char_ids else None
    if officer_inventories:
        print(f"Found inventories for {len(officer_inventories)} officer mule characters")
    
    print("Generating HTML...")
    html = generate_html(char_ids, inventories, spell_info, officer_char_ids, officer_inventories)
    
    print(f"Writing HTML to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    # Try to generate delta page if previous day's files exist
    # Priority: 1) _previous from CI — yesterday's dump copied before today's file overwrites it.
    #            2) Yesterday's dated file (M_D_YY.txt) when using dated archives only.
    #            3) Prototype files for local testing.
    # Dated names used to win over _previous; a stale M_D_YY snapshot next to fresh TAKP_character.txt
    # produced a "whole quarter" diff. Prefer _previous whenever present (GitHub Actions always sets it).
    previous_char_file = None
    previous_inv_file = None
    current_char_file = char_file
    current_inv_file = inv_file

    prev_ci_char = os.path.join(char_dir, "TAKP_character_previous.txt")
    prev_ci_inv = os.path.join(inv_dir, "TAKP_character_inventory_previous.txt")

    yesterday_char_file = find_yesterday_file(char_file, char_dir)
    yesterday_inv_file = find_yesterday_file(inv_file, inv_dir)

    if os.path.exists(prev_ci_char) and os.path.exists(prev_ci_inv):
        previous_char_file = prev_ci_char
        previous_inv_file = prev_ci_inv
        print("[OK] Using workflow _previous files (yesterday Magelo vs current):")
        print(f"  Previous: {os.path.basename(previous_char_file)}")
        print(f"  Current: {os.path.basename(current_char_file)}")
    elif yesterday_char_file and yesterday_inv_file:
        print(f"[OK] Found yesterday's files based on current file date (daily delta):")
        print(f"  Yesterday: {os.path.basename(yesterday_char_file)}")
        print(f"  Current: {os.path.basename(current_char_file)}")
        previous_char_file = yesterday_char_file
        previous_inv_file = yesterday_inv_file
    else:
        proto_prev_char = os.path.join(char_dir, "1_14_24.txt")
        proto_prev_inv = os.path.join(inv_dir, "1_14_24.txt")
        proto_curr_char = os.path.join(char_dir, "1_17_24.txt")
        proto_curr_inv = os.path.join(inv_dir, "1_17_24.txt")

        if os.path.exists(proto_prev_char) and os.path.exists(proto_prev_inv) and \
           os.path.exists(proto_curr_char) and os.path.exists(proto_curr_inv):
            print("⚠ Prototype files found (1_14_24 and 1_17_24), generating serverwide delta page...")
            previous_char_file = proto_prev_char
            previous_inv_file = proto_prev_inv
            current_char_file = proto_curr_char
            current_inv_file = proto_curr_inv
        else:
            previous_char_file = None
            previous_inv_file = None
    
    if previous_char_file and previous_inv_file:
        magelo_stamp = (os.environ.get('MAGELO_UPDATE_DATE') or '').strip()
        if not magelo_stamp or magelo_stamp == 'Unknown':
            ud_path = os.path.join(base_dir, '.magelo_update_date')
            if os.path.isfile(ud_path):
                with open(ud_path, 'r', encoding='utf-8') as uf:
                    magelo_stamp = uf.read().strip()
        if not delta_magelo_export_dates_plausible(base_dir, magelo_stamp, max_span_days=2):
            print(
                '[SKIP] delta.html: .magelo_previous_dump_date.txt vs current export span '
                'more than 2 calendar days; skipping to avoid inflated AA/item diffs.'
            )
            previous_char_file = None
            previous_inv_file = None
    
    if previous_char_file and previous_inv_file and \
       os.path.exists(previous_char_file) and os.path.exists(previous_inv_file):
        print(f"Previous: {os.path.basename(previous_char_file)}, Current: {os.path.basename(current_char_file)}")
        print(f"Previous file exists: {os.path.exists(previous_char_file)}, size: {os.path.getsize(previous_char_file) if os.path.exists(previous_char_file) else 0} bytes")
        print(f"Current file exists: {os.path.exists(current_char_file)}, size: {os.path.getsize(current_char_file) if os.path.exists(current_char_file) else 0} bytes")
        
        # Parse ALL character data (serverwide, not just mules)
        # Pass None to get all characters
        print("Parsing all characters (serverwide) for delta comparison...")
        previous_char_data = parse_character_data(previous_char_file, None)
        current_char_data = parse_character_data(current_char_file, None)
        print(f"Found {len(previous_char_data)} characters in previous, {len(current_char_data)} in current")
        
        # Check if files are identical
        if os.path.exists(previous_char_file) and os.path.exists(current_char_file):
            import hashlib
            prev_hash = hashlib.md5(open(previous_char_file, 'rb').read()).hexdigest()
            curr_hash = hashlib.md5(open(current_char_file, 'rb').read()).hexdigest()
            if prev_hash == curr_hash:
                print("[WARNING] Previous and current files are identical (same hash) - no changes to show")
            else:
                print(f"Files are different (prev hash: {prev_hash[:8]}..., curr hash: {curr_hash[:8]}...)")
        
        # Parse ALL inventories (serverwide)
        previous_char_ids = {}
        current_char_ids = {}
        with open(previous_char_file, 'r', encoding='utf-8') as f:
            next(f)  # Skip header
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 9:
                    name = parts[0]
                    char_id = parts[8]
                    previous_char_ids[name] = char_id
        
        with open(current_char_file, 'r', encoding='utf-8') as f:
            next(f)  # Skip header
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 9:
                    name = parts[0]
                    char_id = parts[8]
                    current_char_ids[name] = char_id
        
        # Parse all inventories
        previous_inventories = parse_inventory_file(previous_inv_file, previous_char_ids) if previous_char_ids else {}
        current_inventories = parse_inventory_file(current_inv_file, current_char_ids) if current_char_ids else {}
        print(f"Found {len(previous_inventories)} characters with inventory in previous, {len(current_inventories)} in current")
        
        # Get magelo update date
        magelo_update_date = os.environ.get('MAGELO_UPDATE_DATE', 'Unknown')
        
        # Extract date from magelo_update_date or use today
        if magelo_update_date != 'Unknown':
            # Try to parse date from format like "Sat Feb 7 16:30:25 UTC 2026"
            try:
                dt = datetime.strptime(magelo_update_date, '%a %b %d %H:%M:%S UTC %Y')
                date_str = dt.strftime('%Y-%m-%d')
            except:
                date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
        
        # Step 1: Check/create master baseline
        # Baseline is generated on-the-fly and cached (not committed to repo due to size)
        baseline = load_master_baseline(delta_snapshots_dir)
        if not baseline:
            print("Master baseline not found. Creating baseline from current data...")
            # Use current data as baseline (first run or after cache clear)
            save_master_baseline(current_char_data, current_inventories, date_str, delta_snapshots_dir)
            print(f"  Created master baseline from current data (date: {date_str})")
            baseline = load_master_baseline(delta_snapshots_dir)
        
        # Step 2: Append gear/stat events from day-over-day deltas (dump diff, with daily JSON fallback)
        print(f"Appending gear events for {date_str} (previous vs current Magelo dumps)...")
        char_deltas, inv_deltas = _resolve_day_over_day_deltas(
            previous_char_data,
            previous_inventories,
            current_char_data,
            current_inventories,
            date_str,
            base_dir,
            baseline,
        )
        corpse_loot_override = chars_corpse_loot_excluded(
            current_inventories, previous_inventories
        )
        for _cn in corpse_loot_override:
            char_deltas.pop(_cn, None)
            inv_deltas.pop(_cn, None)
        tracked_ids, _, _, _ = load_tracked_item_ids()
        unique_tracked = load_unique_tracked_item_ids(tracked_ids)
        possession_yesterday = possession_from_inv_snapshot(previous_inventories)
        filter_unique_reacquires_in_inv_deltas(inv_deltas, possession_yesterday, unique_tracked)
        try:
            gear_n, char_n = append_day_events_from_deltas(
                char_deltas,
                inv_deltas,
                date_str,
                delta_snapshots_dir,
                baseline_date=baseline.get("baseline_date") if baseline else None,
                unique_tracked_ids=unique_tracked,
            )
            print(f"  Saved gear_events: {gear_n} inventory rows, {char_n} stat rows")
        except Exception as e:
            print(f"Warning: Could not append gear events: {e}")
            import traceback
            traceback.print_exc()

        # Step 3: Generate delta HTML from the same day-over-day deltas as gear events.
        print(f"Generating delta.html from previous vs current Magelo dumps ({date_str})...")
        if gear_events_available(delta_snapshots_dir) and date_str in list_available_event_dates(
            delta_snapshots_dir
        ):
            try:
                event_day = get_day_delta_from_events(date_str, delta_snapshots_dir)
                _warn_if_event_dump_divergence(
                    event_day, char_deltas, inv_deltas, date_str
                )
            except Exception as e:
                print(f"Warning: Could not cross-check gear events vs dump diff: {e}")
        
        # Legacy cumulative daily JSON (optional; disabled by default — use gear_events/)
        if os.environ.get('MAGELO_WRITE_CUMULATIVE_DAILY', '').strip() in ('1', 'true', 'yes'):
            print(f"MAGELO_WRITE_CUMULATIVE_DAILY set — also writing cumulative delta_daily JSON...")
            try:
                daily_delta_path = save_daily_delta_from_baseline(
                    current_char_data,
                    current_inventories,
                    date_str,
                    delta_snapshots_dir,
                    auto_reset_baseline=False,
                )
                print(f"Saved daily delta JSON: {daily_delta_path}")
            except Exception as e:
                print(f"Warning: Could not save daily delta JSON: {e}")
        
        # Ensure visibility change (anon 0 vs large AA/level) is set when char_deltas came from events/diff
        apply_visibility_change_to_char_deltas(char_deltas)
        
        # Get item names for inventory deltas
        populate_item_names_for_inv_deltas(inv_deltas, current_inventories)
        
        # Generate delta HTML (and append mob deaths for tracker when we have zone loot)
        mob_tracker_path = os.path.join(base_dir, "mob_tracker_deaths.json")
        raid_sources_path = os.path.join(base_dir, "raid_item_sources.json")
        # Use magelo pull timestamp for "died (observed)", not script run time
        if magelo_update_date != 'Unknown':
            try:
                magelo_dt = datetime.strptime(magelo_update_date, '%a %b %d %H:%M:%S UTC %Y')
                observed_at = magelo_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            except ValueError:
                observed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            observed_at = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        prev_export_date = None
        prev_stamp_path = os.path.join(base_dir, '.magelo_previous_dump_date.txt')
        if os.path.isfile(prev_stamp_path):
            with open(prev_stamp_path, 'r', encoding='utf-8') as _pf:
                prev_export_date = _pf.read().strip()
        delta_html = generate_delta_html(
            current_char_data, previous_char_data,
            current_inventories, previous_inventories,
            magelo_update_date,
            serverwide=True,
            char_deltas=char_deltas,
            inv_deltas=inv_deltas,
            mob_tracker_deaths_path=mob_tracker_path,
            observed_at=observed_at,
            raid_item_sources_path=raid_sources_path,
            corpse_loot_chars=corpse_loot_override,
            previous_export_date=prev_export_date,
        )
        
        delta_file = os.path.join(base_dir, "delta.html")
        print(f"Writing delta HTML to {delta_file}...")
        with open(delta_file, 'w', encoding='utf-8') as f:
            f.write(delta_html)
        print("Delta page generated successfully!")
        
        mob_tracker_file = os.path.join(base_dir, "mob_tracker.html")
        try:
            with open(mob_tracker_file, 'w', encoding='utf-8') as f:
                f.write(generate_mob_tracker_html(base_dir))
            print(f"Wrote {mob_tracker_file}")
        except Exception as e:
            print(f"Warning: Could not write mob_tracker.html: {e}")
        
        # Note: We no longer save historical HTML files - all historical data is in JSON format
        # Historical deltas can be reconstructed on-demand from daily delta JSONs using get_date_range_deltas()
        
        # Generate/update delta history page (shows available JSON dates and allows date-to-date generation)
        try:
            generate_delta_history(base_dir)
            print("Generated delta history page")
        except Exception as e:
            print(f"Warning: Could not generate delta history: {e}")
            import traceback
            traceback.print_exc()

        try:
            generate_char_timeline(base_dir)
            print("Generated char timeline page")
        except Exception as e:
            print(f"Warning: Could not generate char timeline: {e}")
            import traceback
            traceback.print_exc()
        
        # Save delta snapshots for weekly/monthly tracking
        try:
            # Use deltas already calculated above (no need to recalculate)
            delta_data = {
                'char_deltas': char_deltas,
                'inv_deltas': inv_deltas
            }
            
            week_start = get_week_start(date_str)
            month_start = get_month_start(date_str)
            
            # Save weekly baseline JSON if this is a new week (check if baseline exists)
            from delta_storage import load_baseline_json
            delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
            if not load_baseline_json('weekly', date_str, delta_snapshots_dir):
                save_baseline_json(current_char_data, 'weekly', date_str, delta_snapshots_dir)
                print(f"Saved weekly baseline JSON for week starting {week_start}")
            
            # Save monthly baseline JSON if this is a new month (check if baseline exists)
            if not load_baseline_json('monthly', date_str, delta_snapshots_dir):
                save_baseline_json(current_char_data, 'monthly', date_str, delta_snapshots_dir)
                print(f"Saved monthly baseline JSON for month starting {month_start}")
            
            # Save weekly snapshot (overwrites if same week)
            save_delta_snapshot(delta_data, 'weekly', date_str, delta_snapshots_dir)
            print(f"Saved weekly delta snapshot for week starting {week_start}")
            
            # Save monthly snapshot (overwrites if same month)
            save_delta_snapshot(delta_data, 'monthly', date_str, delta_snapshots_dir)
            print(f"Saved monthly delta snapshot for month starting {month_start}")
            
            # Generate weekly/monthly leaderboard pages
            
            # Generate weekly leaderboard page (compare current vs weekly baseline, or use daily delta JSONs when available)
            weekly_aa = get_weekly_leaderboard(week_start, 'aa', 20, delta_snapshots_dir, current_char_data, end_date=date_str)
            weekly_hp = get_weekly_leaderboard(week_start, 'hp', 20, delta_snapshots_dir, current_char_data, end_date=date_str)
            weekly_html = generate_leaderboard_html(
                f"Week of {week_start}", weekly_aa, weekly_hp, 'weekly'
            )
            weekly_file = os.path.join(base_dir, f"leaderboard_week_{week_start}.html")
            with open(weekly_file, 'w', encoding='utf-8') as f:
                f.write(weekly_html)
            print(f"Generated weekly leaderboard: {weekly_file}")
            
            # Generate monthly leaderboard page (compare current vs monthly baseline, or use daily delta JSONs when available)
            monthly_aa = get_monthly_leaderboard(month_start, 'aa', 20, delta_snapshots_dir, current_char_data, end_date=date_str)
            monthly_hp = get_monthly_leaderboard(month_start, 'hp', 20, delta_snapshots_dir, current_char_data, end_date=date_str)
            monthly_html = generate_leaderboard_html(
                f"Month of {month_start}", monthly_aa, monthly_hp, 'monthly'
            )
            monthly_file = os.path.join(base_dir, f"leaderboard_month_{month_start}.html")
            with open(monthly_file, 'w', encoding='utf-8') as f:
                f.write(monthly_html)
            print(f"Generated monthly leaderboard: {monthly_file}")
            
        except Exception as e:
            print(f"Warning: Could not save delta snapshots: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Previous day's files not found, skipping delta page generation.")
        print(f"Current file: {os.path.basename(char_file)}")
        if yesterday_char_file:
            print(f"  Expected yesterday's file: {os.path.basename(yesterday_char_file)} (not found)")
        if previous_char_file:
            print(f"  Also checked: {os.path.basename(previous_char_file)} and {os.path.basename(previous_inv_file) if previous_inv_file else 'N/A'}")
    
    # Generate weekly/monthly leaderboards even if no previous day's files
    # (compare current vs baseline if available)
    try:
        # Get magelo update date
        magelo_update_date = os.environ.get('MAGELO_UPDATE_DATE', 'Unknown')
        
        # Extract date
        if magelo_update_date != 'Unknown':
            try:
                dt = datetime.strptime(magelo_update_date, '%a %b %d %H:%M:%S UTC %Y')
                date_str = dt.strftime('%Y-%m-%d')
            except:
                date_str = datetime.now().strftime('%Y-%m-%d')
        else:
            date_str = datetime.now().strftime('%Y-%m-%d')
        
        week_start = get_week_start(date_str)
        month_start = get_month_start(date_str)
        delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
        
        # Parse current character data for leaderboard comparison
        current_char_data_for_lb = parse_character_data(char_file, None)
        
        # Ensure weekly/monthly baselines exist (create from current data if first run of period)
        from delta_storage import load_baseline_json
        os.makedirs(delta_snapshots_dir, exist_ok=True)
        if not load_baseline_json('weekly', date_str, delta_snapshots_dir):
            save_baseline_json(current_char_data_for_lb, 'weekly', date_str, delta_snapshots_dir)
            print(f"Saved weekly baseline for week starting {week_start}")
        if not load_baseline_json('monthly', date_str, delta_snapshots_dir):
            save_baseline_json(current_char_data_for_lb, 'monthly', date_str, delta_snapshots_dir)
            print(f"Saved monthly baseline for month starting {month_start}")
        
        # Generate weekly leaderboard (use daily delta JSONs when available, else current vs baseline)
        weekly_aa = get_weekly_leaderboard(week_start, 'aa', 20, delta_snapshots_dir, current_char_data_for_lb, end_date=date_str)
        weekly_hp = get_weekly_leaderboard(week_start, 'hp', 20, delta_snapshots_dir, current_char_data_for_lb, end_date=date_str)
        weekly_html = generate_leaderboard_html(
            f"Week of {week_start}", weekly_aa, weekly_hp, 'weekly'
        )
        weekly_file = os.path.join(base_dir, f"leaderboard_week_{week_start}.html")
        with open(weekly_file, 'w', encoding='utf-8') as f:
            f.write(weekly_html)
        print(f"Generated weekly leaderboard: {weekly_file}")
        
        # Generate monthly leaderboard (use daily delta JSONs when available, else current vs baseline)
        monthly_aa = get_monthly_leaderboard(month_start, 'aa', 20, delta_snapshots_dir, current_char_data_for_lb, end_date=date_str)
        monthly_hp = get_monthly_leaderboard(month_start, 'hp', 20, delta_snapshots_dir, current_char_data_for_lb, end_date=date_str)
        monthly_html = generate_leaderboard_html(
            f"Month of {month_start}", monthly_aa, monthly_hp, 'monthly'
        )
        monthly_file = os.path.join(base_dir, f"leaderboard_month_{month_start}.html")
        with open(monthly_file, 'w', encoding='utf-8') as f:
            f.write(monthly_html)
        print(f"Generated monthly leaderboard: {monthly_file}")
        
    except Exception as e:
        print(f"Warning: Could not generate leaderboards: {e}")
        import traceback
        traceback.print_exc()
    
    print("Done!")

if __name__ == "__main__":
    import sys
    
    # Check if we're generating a date range delta
    if len(sys.argv) >= 3 and sys.argv[1] == "--date-range":
        start_date = sys.argv[2]
        end_date = sys.argv[3] if len(sys.argv) > 3 else start_date
        
        base_dir = os.path.dirname(__file__)
        delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
        magelo_update_date = os.environ.get('MAGELO_UPDATE_DATE', 'Unknown')
        
        print(f"Generating date range delta: {start_date} to {end_date}")
        html = generate_date_range_delta_html(start_date, end_date, delta_snapshots_dir, magelo_update_date)
        
        output_file = os.path.join(base_dir, "delta_range.html")
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Generated date range delta: {output_file}")
    else:
        main()
