#!/usr/bin/env python3
"""
Script to generate a static HTML page showing which mule characters have
spells from PoK turn-ins (items 29112, 29131, 29132).
"""

import json
import os
from collections import defaultdict
from datetime import datetime
from delta_storage import (
    save_delta_snapshot, load_delta_snapshot,
    get_week_start, get_month_start,
    get_weekly_leaderboard, get_monthly_leaderboard,
    save_baseline_json, save_daily_delta_json, get_date_range_deltas,
    save_master_baseline, load_master_baseline,
    save_daily_delta_from_baseline, compare_delta_to_delta,
    load_daily_delta_json
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
                        'race': parts[4] if len(parts) > 4 else ''
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
    </style>
</head>
<body>
    <div class="container">
        <h1>TAKP Mule PoK Spell Inventory</h1>
        <p>Generated from magelo dump (last updated: """ + magelo_update_date + """)</p>
        <p>This page shows spells that can be obtained from PoK turn-ins (Ethereal Parchment, Spectral Parchment, Glyphed Rune Word)</p>
        
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
    </div>
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
            'is_new': char_name not in previous_data,
            'is_deleted': is_deleted
        }
        
        # Only include if there are changes or it's new/deleted
        # For level 65, only show if AA changed (and level 50+)
        # For < 65, show if level or AA changed (and level 50+ for AA)
        has_level_change = delta['level_change'] != 0 and current_level < 65 and not is_deleted
        has_aa_change = delta['aa_total_change'] != 0 and ((current_level >= 50 or previous_level >= 50) if not is_deleted else previous_level >= 50)
        
        if has_level_change or has_aa_change or delta['is_new'] or delta['is_deleted']:
            deltas[char_name] = delta
    
    return deltas

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


def load_tracked_item_ids():
    """Load raid, elemental armor, and praesterium item IDs from the 3 JSON files.
    Returns (set of item_id strings, dict item_id -> source_label for display)."""
    base_dir = os.path.dirname(__file__)
    tracked = set()
    source_label = {}
    files = [
        (os.path.join(base_dir, "raid_item_sources.json"), "raid"),
        (os.path.join(base_dir, "elemental_armor.json"), "elemental armor"),
        (os.path.join(base_dir, "praesterium_loot.json"), "praesterium"),
    ]
    for path, label in files:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item_id in data:
                sid = str(item_id)
                tracked.add(sid)
                source_label[sid] = label
        except Exception as e:
            print(f"Warning: Could not load {path}: {e}")
    return tracked, source_label


def compare_inventories(current_inv, previous_inv, character_list=None):
    """Compare current and previous inventories to find item deltas.
    If character_list is None, compares all characters (serverwide).
    No-rent items are automatically filtered out."""
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
            item_deltas[char_name] = {
                'added': added_items,
                'removed': removed_items,
                'item_names': {}  # Will be populated with item names
            }
    
    return item_deltas

def generate_delta_html(current_char_data, previous_char_data, current_inv, previous_inv, 
                        magelo_update_date, serverwide=True, char_deltas=None, inv_deltas=None):
    """Generate HTML page showing deltas between current and previous magelo dump.
    If serverwide is True, compares all characters, otherwise only mules.
    If char_deltas and inv_deltas are provided, uses those instead of recalculating."""
    
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
    tracked_ids, tracked_source_label = load_tracked_item_ids()
    tracked_deltas = {}
    if tracked_ids:
        for char_name, delta in inv_deltas.items():
            added = {k: v for k, v in delta['added'].items() if str(k) in tracked_ids}
            removed = {k: v for k, v in delta['removed'].items() if str(k) in tracked_ids}
            if added or removed:
                tracked_deltas[char_name] = {
                    'added': added,
                    'removed': removed,
                    'item_names': {k: v for k, v in delta['item_names'].items() if str(k) in tracked_ids}
                }
    
    # Calculate AA leaderboard (top gainers)
    aa_leaderboard = []
    for char_name, delta in char_deltas.items():
        if delta.get('is_deleted', False) or delta.get('is_new', False):
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
    
    # Calculate HP leaderboard (top gainers)
    hp_leaderboard = []
    for char_name, delta in char_deltas.items():
        if delta.get('is_deleted', False) or delta.get('is_new', False):
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
        <p>Changes detected since previous magelo dump (last updated: """ + magelo_update_date + """)</p>
        
        <div class="nav-menu">
            <h3>Jump to Section:</h3>
            <div class="nav-links">
"""
    
    # Split inventory deltas by level 1 (mules/traders) vs others
    inv_deltas_level1 = {}
    inv_deltas_others = {}
    for char_name, delta in inv_deltas.items():
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
    
    # Build navigation links based on what sections will be shown
    nav_links = []
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
    
    html += "".join(nav_links)
    html += """
            </div>
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
                        <td><strong>{entry['name']}</strong></td>
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
                        <td><strong>{entry['name']}</strong></td>
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
        # Sort all deltas
        for char_name in sorted(char_deltas.keys()):
            delta = char_deltas[char_name]
            current_level = delta['current_level']
            is_deleted = delta.get('is_deleted', False)
            
            # Character name display - mark deleted characters
            if is_deleted:
                char_display = f'<strong style="color: #999; text-decoration: line-through;">{char_name}</strong> <span style="color: #f44336; font-size: 0.9em;">(Deleted)</span>'
            else:
                char_display = f'<strong>{char_name}</strong>'
            
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
    
    # Level 1 inventory changes (mules/traders)
    if inv_deltas_level1:
        html += """
        <h2 id="inventory-changes-level1">Level 1 Inventory Changes (Mules/Traders)</h2>
        <p><em>Showing level 1 characters with inventory changes (limited to first 500 characters for performance)</em></p>
"""
        sorted_chars = sorted(inv_deltas_level1.keys())[:500]
        for char_name in sorted_chars:
            delta = inv_deltas_level1[char_name]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff9e6;">
            <h3><strong>{char_name}</strong> <span style="color: #666; font-size: 0.9em;">(Level 1 - Mule/Trader)</span></h3>
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
    
    # Regular inventory changes (non-level 1)
    if inv_deltas_others:
        html += """
        <h2 id="inventory-changes">Inventory Changes</h2>
        <p><em>Showing characters with inventory changes (limited to first 500 characters for performance)</em></p>
"""
        sorted_chars = sorted(inv_deltas_others.keys())[:500]
        for char_name in sorted_chars:
            delta = inv_deltas_others[char_name]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h3><strong>{char_name}</strong></h3>
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
    
    # Tracked Items section (raid / elemental armor / praesterium)
    if tracked_deltas:
        html += """
        <h2 id="tracked-items">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>
        <p><em>Changes in raid loot, elemental armor, and praesterium items — see who acquired or lost these.</em></p>
"""
        for char_name in sorted(tracked_deltas.keys()):
            delta = tracked_deltas[char_name]
            char_level = current_char_data.get(char_name, {}).get('level', '?')
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff8e1;">
            <h3><strong>{char_name}</strong> <span style="color: #666; font-size: 0.9em;">(Level {char_level})</span></h3>
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
                        <td><strong>{entry['name']}</strong></td>
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
                        <td><strong>{entry['name']}</strong></td>
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
</body>
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
        <p>This report shows aggregated changes across {start_date} to {end_date}, reconstructed from daily delta JSON files.</p>
        <p><strong>Note:</strong> This is a reconstructed view. For the most recent daily changes, see the <a href="delta.html">current delta report</a>.</p>
    </div>
"""
    
    # Insert the header note after the opening container div
    html = html.replace('<div class="container">', '<div class="container">' + header_note)
    
    return html

def generate_delta_history(base_dir):
    """Generate a history page listing all available daily delta JSON files.
    Allows generating date-to-date delta comparisons on demand."""
    import glob
    import re
    
    # Load tracked item IDs so we can embed them for the client-side report (Tracked Items section)
    tracked_ids, tracked_source_label = load_tracked_item_ids()
    tracked_ids_json = json.dumps(list(tracked_ids))
    tracked_source_json = json.dumps(tracked_source_label)
    
    # Find all daily delta JSON files
    delta_snapshots_dir = os.path.join(base_dir, 'delta_snapshots')
    delta_files = []
    
    if os.path.exists(delta_snapshots_dir):
        # Find all delta_daily_YYYY-MM-DD.json.gz files (compressed)
        delta_files.extend(glob.glob(os.path.join(delta_snapshots_dir, "delta_daily_*.json.gz")))
    
    # Extract dates from filenames and sort
    delta_entries = []
    for filepath in delta_files:
        filename = os.path.basename(filepath)
        # Match both .json and .json.gz files
        match = re.match(r'delta_daily_(\d{4}-\d{2}-\d{2})\.json(\.gz)?', filename)
        if match:
            date_str = match.group(1)
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                delta_entries.append({
                    'date': date_str,
                    'date_formatted': dt.strftime('%B %d, %Y'),
                    'filename': filename,
                    'filepath': filepath,
                    'timestamp': os.path.getmtime(filepath)
                })
            except:
                pass
    
    # Sort by date (newest first)
    delta_entries.sort(key=lambda x: x['date'], reverse=True)
    
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
            <strong>ℹ️ How it works:</strong> Historical deltas are stored as JSON files (much smaller than HTML). 
            Use the form below to generate a date-to-date comparison report for any date range. 
            The report will be reconstructed from daily delta JSONs on demand.
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
            <div id="date_range_output" style="margin-top: 20px; padding: 15px; background: #f9f9f9; border-radius: 5px; min-height: 50px;"></div>
        </div>
        
        <div class="stats">
            <strong>Available Daily Delta JSON Files:</strong> """ + str(len(delta_entries)) + """
            <br><small>These JSON files contain daily changes and can be used to reconstruct any date range.</small>
        </div>
        
        <div class="delta-list">
            <h2>Available Dates</h2>
"""
    
    if delta_entries:
        html += "            <p>Click on a date to use it in the date range form above:</p>\n"
        html += "            <div style='display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-top: 15px;'>\n"
        for entry in delta_entries:
            html += f"""
                <div class="delta-entry" style="flex-direction: column; align-items: flex-start; cursor: pointer;" 
                     onclick="document.getElementById('start_date').value='{entry['date']}'; document.getElementById('end_date').value='{entry['date']}';">
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
    <script>
        const TRACKED_ITEM_IDS = new Set(JSON.parse((document.getElementById('tracked-item-ids') || { textContent: '[]' }).textContent));
        const TRACKED_SOURCE_LABEL = JSON.parse((document.getElementById('tracked-source-label') || { textContent: '{}' }).textContent);
        // Set default dates (today and 7 days ago)
        const today = new Date().toISOString().split('T')[0];
        const weekAgo = new Date();
        weekAgo.setDate(weekAgo.getDate() - 7);
        const weekAgoStr = weekAgo.toISOString().split('T')[0];
        
        document.getElementById('end_date').value = today;
        document.getElementById('start_date').value = weekAgoStr;
        
        // Load JSONs on-demand (only when date range is selected)
        let loadedDeltas = new Map(); // Cache loaded deltas
        let loadedBaselines = new Map(); // Cache loaded baselines
        let availableDates = new Set(); // Track which dates have JSON files
        
        // Extract available dates from the page (from the date list)
        document.querySelectorAll('.delta-date').forEach(el => {
            const date = el.textContent.trim();
            if (date.match(/^\d{4}-\d{2}-\d{2}$/)) {
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
        
        async function loadBaseline(baselineDate) {
            // Try to load baseline file (compressed .json.gz)
            // First try archived baseline_master_YYYY-MM-DD.json.gz, then current baseline_master.json.gz
            const baselineKey = `baseline_${baselineDate}`;
            if (loadedBaselines && loadedBaselines.has(baselineKey)) {
                return loadedBaselines.get(baselineKey);
            }
            
            const currentUrl = `delta_snapshots/baseline_master.json.gz`;
            const archivedUrl = `delta_snapshots/baseline_master_${baselineDate}.json.gz`;
            try {
                let response = null;
                // Try archived baseline first (baseline_master_YYYY-MM-DD.json.gz exists only after a reset)
                try {
                    response = await fetch(archivedUrl);
                } catch (e) {
                    // Network or other error on archived URL; will try current below
                }
                // If archived missing (404) or failed, use current baseline (baseline_master.json.gz)
                if (!response || !response.ok) {
                    response = await fetch(currentUrl);
                }
                if (!response || !response.ok) {
                    // Last resort: try uncompressed (for backward compatibility)
                    const uncompressedUrl = `delta_snapshots/baseline_master_${baselineDate}.json`;
                    response = await fetch(uncompressedUrl);
                    if (!response || !response.ok) {
                        response = await fetch('delta_snapshots/baseline_master.json');
                    }
                    if (!response || !response.ok) {
                        throw new Error(`Baseline not found for ${baselineDate}. Tried: ${archivedUrl}, ${currentUrl}, and uncompressed variants.`);
                    }
                    const text = await response.text();
                    const baseline = JSON.parse(text);
                    if (!loadedBaselines) {
                        loadedBaselines = new Map();
                    }
                    loadedBaselines.set(baselineKey, baseline);
                    return baseline;
                }
                // Parse compressed JSON (from archived or current .json.gz)
                const arrayBuffer = await response.arrayBuffer();
                const decompressed = pako.inflate(new Uint8Array(arrayBuffer), { to: 'string' });
                const baseline = JSON.parse(decompressed);
                if (!loadedBaselines) {
                    loadedBaselines = new Map();
                }
                loadedBaselines.set(baselineKey, baseline);
                return baseline;
            } catch (error) {
                console.error(`Error loading baseline for ${baselineDate}:`, error);
                throw error;
            }
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
                    class: charData.class || ''
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
                        level: deltaData.current_level || 0,
                        aa_total: deltaData.current_aa_total || 0,
                        hp: deltaData.current_hp || 0,
                        class: deltaData.class || ''
                    };
                } else {
                    // Update existing character - delta has current values (baseline + changes)
                    fullState[charName].level = deltaData.current_level || fullState[charName].level;
                    fullState[charName].aa_total = deltaData.current_aa_total || fullState[charName].aa_total;
                    fullState[charName].hp = deltaData.current_hp || fullState[charName].hp;
                    if (deltaData.class) {
                        fullState[charName].class = deltaData.class;
                    }
                }
            }
            
            return fullState;
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
            outputDiv.innerHTML = '<p>Loading deltas and baselines for ' + start + ' and ' + end + '...</p>';
            
            try {
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
                const baselineMismatch = startDelta.baseline_date !== endDelta.baseline_date;
                
                // Load baselines (needed to reconstruct full character states)
                outputDiv.innerHTML = '<p>Loading baselines... (this may take a moment)</p>';
                const [startBaseline, endBaseline] = await Promise.all([
                    loadBaseline(startDelta.baseline_date),
                    loadBaseline(endDelta.baseline_date)
                ]);
                
                if (!startBaseline || !endBaseline) {
                    outputDiv.innerHTML = '<p style="color: red;">Error: Could not load baseline JSONs. Baselines may not be available on GitHub Pages.</p>';
                    return;
                }
                
                // Reconstruct full character states for both dates
                outputDiv.innerHTML = '<p>Reconstructing character states...</p>';
                const startState = reconstructCharacterState(startBaseline, startDelta);
                const endState = reconstructCharacterState(endBaseline, endDelta);
                
                // Compare the two reconstructed states
                const charChanges = {};
                const allCharNames = new Set([...Object.keys(startState), ...Object.keys(endState)]);
                
                for (const charName of allCharNames) {
                    const startChar = startState[charName];
                    const endChar = endState[charName];
                    
                    // Character was deleted
                    if (startChar && !endChar) {
                        charChanges[charName] = {
                            level: -startChar.level,
                            aa: -startChar.aa_total,
                            hp: -startChar.hp,
                            current_level: 0,
                            previous_level: startChar.level,
                            class: startChar.class,
                            is_deleted: true
                        };
                        continue;
                    }
                    
                    // Character is new
                    if (!startChar && endChar) {
                        charChanges[charName] = {
                            level: endChar.level,
                            aa: endChar.aa_total,
                            hp: endChar.hp,
                            current_level: endChar.level,
                            previous_level: 0,
                            class: endChar.class,
                            is_new: true
                        };
                        continue;
                    }
                    
                    // Character exists in both - compare values
                    if (startChar && endChar) {
                        const levelChange = endChar.level - startChar.level;
                        const aaChange = endChar.aa_total - startChar.aa_total;
                        const hpChange = endChar.hp - startChar.hp;
                        
                        // Only include if there are changes
                        if (levelChange !== 0 || aaChange !== 0 || hpChange !== 0) {
                            charChanges[charName] = {
                                level: levelChange,
                                aa: aaChange,
                                hp: hpChange,
                                current_level: endChar.level,
                                previous_level: startChar.level,
                                class: endChar.class || startChar.class || ''
                            };
                        }
                    }
                }
                
                // Compute inventory deltas from start to end (same logic as Python compare_delta_to_delta)
                const invDeltas = {};
                const startInv = startDelta.inv_deltas || {};
                const endInv = endDelta.inv_deltas || {};
                const allInvChars = new Set([...Object.keys(startInv), ...Object.keys(endInv)]);
                for (const charName of allInvChars) {
                    const a = startInv[charName] || { added: {}, removed: {}, item_names: {} };
                    const b = endInv[charName] || { added: {}, removed: {}, item_names: {} };
                    const aAdded = a.added || {};
                    const aRemoved = a.removed || {};
                    const bAdded = b.added || {};
                    const bRemoved = b.removed || {};
                    const addedItems = {};
                    const removedItems = {};
                    const itemNames = {};
                    const get = (obj, k) => (typeof obj[k] !== 'undefined' ? Number(obj[k]) : 0);
                    for (const itemId of Object.keys(bAdded)) {
                        const count = get(bAdded, itemId);
                        const aAdd = get(aAdded, itemId);
                        if (count > aAdd) {
                            addedItems[itemId] = count - aAdd;
                            if (b.item_names && b.item_names[itemId]) itemNames[itemId] = b.item_names[itemId];
                        }
                    }
                    for (const itemId of Object.keys(bRemoved)) {
                        const count = get(bRemoved, itemId);
                        const aRem = get(aRemoved, itemId);
                        if (count > aRem) {
                            removedItems[itemId] = count - aRem;
                            if (b.item_names && b.item_names[itemId]) itemNames[itemId] = b.item_names[itemId];
                        }
                    }
                    for (const itemId of Object.keys(aAdded)) {
                        const count = get(aAdded, itemId);
                        const bRem = get(bRemoved, itemId);
                        if (bRem > 0) {
                            const net = bRem - count;
                            if (net > 0) {
                                removedItems[itemId] = (removedItems[itemId] || 0) + net;
                            } else if (net < 0) {
                                addedItems[itemId] = (addedItems[itemId] || 0) + (-net);
                            }
                            if (a.item_names && a.item_names[itemId]) itemNames[itemId] = a.item_names[itemId];
                        }
                    }
                    if (Object.keys(addedItems).length > 0 || Object.keys(removedItems).length > 0) {
                        invDeltas[charName] = { added: addedItems, removed: removedItems, item_names: itemNames };
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
                        if (Object.keys(added).length > 0 || Object.keys(removed).length > 0) {
                            trackedDeltas[charName] = { added, removed, item_names: itemNames };
                        }
                    }
                }
                
                // Generate HTML report matching delta.html formatting
                let reportHTML = `<h2 style="color: #333; border-bottom: 3px solid #2196F3; padding-bottom: 10px;">Date Range Report: ${start} to ${end}</h2>`;
                
                if (baselineMismatch) {
                    reportHTML += `<p style="background: #e3f2fd; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #2196F3;">
                        <strong>ℹ️ Different Baselines:</strong> These dates use different baselines (${startDelta.baseline_date} vs ${endDelta.baseline_date}).
                        <br>Full character states have been reconstructed by combining baseline + delta for accurate comparison.
                    </p>`;
                }
                reportHTML += `<p style="margin: 10px 0;"><a href="#aa-leaderboard" style="margin-right: 10px;">🏆 AA Leaderboard</a>
                    <a href="#hp-leaderboard" style="margin-right: 10px;">❤️ HP Leaderboard</a>
                    <a href="#character-changes" style="margin-right: 10px;">Character Changes</a>
                    ${Object.keys(invDeltasLevel1).length > 0 ? '<a href="#inventory-changes-level1" style="margin-right: 10px;">Level 1 (Mules)</a>' : ''}
                    <a href="#inventory-changes" style="margin-right: 10px;">Inventory Changes</a>
                    ${Object.keys(trackedDeltas).length > 0 ? '<a href="#tracked-items" style="margin-right: 10px; background-color: #FF9800;">📌 Tracked Items</a>' : ''}</p>`;
                
                // Calculate leaderboards (matching delta.html format)
                const aaLeaderboard = [];
                const hpLeaderboard = [];
                
                for (const [charName, changes] of Object.entries(charChanges)) {
                    if (changes.is_deleted || changes.is_new) continue;
                    
                    const currentLevel = changes.current_level;
                    const previousLevel = changes.previous_level;
                    const aaGain = changes.aa;
                    const hpGain = changes.hp;
                    
                    // AA leaderboard (level 50+)
                    if ((currentLevel >= 50 || previousLevel >= 50) && aaGain > 0) {
                        const endChar = endState[charName];
                        aaLeaderboard.push({
                            name: charName,
                            class: changes.class || 'Unknown',
                            level: currentLevel,
                            aa_gain: aaGain,
                            aa_total: endChar ? endChar.aa_total : 0
                        });
                    }
                    
                    // HP leaderboard (any level)
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
                
                // Sort leaderboards
                aaLeaderboard.sort((a, b) => b.aa_gain - a.aa_gain);
                hpLeaderboard.sort((a, b) => b.hp_gain - a.hp_gain);
                
                // AA Leaderboard
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
                        const rankClass = idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : 'rank-other';
                        const rankStyle = idx === 0 ? 'background-color: #FFD700; color: #000;' : 
                                         idx === 1 ? 'background-color: #C0C0C0; color: #000;' : 
                                         idx === 2 ? 'background-color: #CD7F32; color: #fff;' : 
                                         'background-color: rgba(255,255,255,0.3); color: #fff;';
                        reportHTML += `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                                    <td style="padding: 10px 12px;"><span style="display: inline-block; width: 30px; height: 30px; line-height: 30px; text-align: center; border-radius: 50%; font-weight: bold; ${rankStyle}">${idx + 1}</span></td>
                                    <td style="padding: 10px 12px;"><strong>${entry.name}</strong></td>
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
                
                // HP Leaderboard
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
                        const rankClass = idx === 0 ? 'rank-1' : idx === 1 ? 'rank-2' : idx === 2 ? 'rank-3' : 'rank-other';
                        const rankStyle = idx === 0 ? 'background-color: #FFD700; color: #000;' : 
                                         idx === 1 ? 'background-color: #C0C0C0; color: #000;' : 
                                         idx === 2 ? 'background-color: #CD7F32; color: #fff;' : 
                                         'background-color: rgba(255,255,255,0.3); color: #fff;';
                        reportHTML += `
                                <tr style="border-bottom: 1px solid rgba(255,255,255,0.1);">
                                    <td style="padding: 10px 12px;"><span style="display: inline-block; width: 30px; height: 30px; line-height: 30px; text-align: center; border-radius: 50%; font-weight: bold; ${rankStyle}">${idx + 1}</span></td>
                                    <td style="padding: 10px 12px;"><strong>${entry.name}</strong></td>
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
                
                // Character Changes Table (matching delta.html format)
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
                    
                    // Sort characters alphabetically
                    const sortedCharNames = Object.keys(charChanges).sort();
                    for (const charName of sortedCharNames) {
                        const changes = charChanges[charName];
                        const isDeleted = changes.is_deleted;
                        const isNew = changes.is_new;
                        const currentLevel = changes.current_level;
                        const previousLevel = changes.previous_level;
                        
                        // Character name display
                        let charDisplay;
                        if (isDeleted) {
                            charDisplay = `<strong style="color: #999; text-decoration: line-through;">${charName}</strong> <span style="color: #f44336; font-size: 0.9em;">(Deleted)</span>`;
                        } else if (isNew) {
                            charDisplay = `<strong>${charName}</strong> <span style="color: #4CAF50; font-size: 0.9em;">(New)</span>`;
                        } else {
                            charDisplay = `<strong>${charName}</strong>`;
                        }
                        
                        // Level change display
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
                        
                        // Total AA display
                        let totalAADisplay;
                        if (isDeleted) {
                            totalAADisplay = `<span style="color: #999;">—</span>`;
                        } else if (currentLevel >= 50 || previousLevel >= 50) {
                            // Need to calculate total AA from end state
                            const endChar = endState[charName];
                            totalAADisplay = String(endChar ? endChar.aa_total : '—');
                        } else {
                            totalAADisplay = `<span style="color: #666;">—</span>`;
                        }
                        
                        // AA change display
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
                
                // Level 1 inventory changes (mules/traders)
                if (Object.keys(invDeltasLevel1).length > 0) {
                    reportHTML += `
                    <h2 id="inventory-changes-level1" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Level 1 Inventory Changes (Mules/Traders)</h2>
                    <p><em>Showing level 1 characters with inventory changes (limited to 500)</em></p>`;
                    const sortedLevel1 = Object.keys(invDeltasLevel1).sort().slice(0, 500);
                    for (const charName of sortedLevel1) {
                        const delta = invDeltasLevel1[charName];
                        reportHTML += `
                    <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff9e6;">
                        <h3 style="margin-top: 0;"><strong>${charName}</strong> <span style="color: #666; font-size: 0.9em;">(Level 1)</span></h3>`;
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
                
                // Regular inventory changes (non-level 1)
                if (Object.keys(invDeltasOthers).length > 0) {
                    reportHTML += `
                    <h2 id="inventory-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Inventory Changes</h2>
                    <p><em>Showing characters with inventory changes (limited to 500)</em></p>`;
                    const sortedOthers = Object.keys(invDeltasOthers).sort().slice(0, 500);
                    for (const charName of sortedOthers) {
                        const delta = invDeltasOthers[charName];
                        reportHTML += `
                    <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
                        <h3 style="margin-top: 0;"><strong>${charName}</strong></h3>`;
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
                } else if (Object.keys(invDeltas).length === 0) {
                    reportHTML += `
                    <h2 id="inventory-changes" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">Inventory Changes</h2>
                    <p style="color: #999; font-style: italic;">No inventory changes detected.</p>`;
                }
                
                // Tracked Items section (raid / elemental armor / praesterium)
                if (Object.keys(trackedDeltas).length > 0) {
                    reportHTML += `
                    <h2 id="tracked-items" style="color: #555; margin-top: 30px; border-bottom: 2px solid #ddd; padding-bottom: 5px;">📌 Tracked Items (Raid / Elemental Armor / Praesterium)</h2>
                    <p><em>Changes in raid loot, elemental armor, and praesterium items — see who acquired or lost these.</em></p>`;
                    for (const charName of Object.keys(trackedDeltas).sort()) {
                        const delta = trackedDeltas[charName];
                        const level = (endState[charName] || startState[charName] || {}).level || '?';
                        reportHTML += `
                    <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px; background-color: #fff8e1;">
                        <h3 style="margin-top: 0;"><strong>${charName}</strong> <span style="color: #666; font-size: 0.9em;">(Level ${level})</span></h3>`;
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
                        reportHTML += `</div>`;
                    }
                }
                
                outputDiv.innerHTML = reportHTML;
            } catch (error) {
                outputDiv.innerHTML = `<p style="color: red; padding: 15px; background: #ffebee; border-radius: 5px;">
                    <strong>Error:</strong> ${error.message}<br>
                    <small>Available dates are listed below. Please select dates that have delta JSON files.</small>
                </p>`;
            }
        }
        
    </script>
</body>
</html>
"""
    
    history_file = os.path.join(base_dir, "delta-history.html")
    with open(history_file, 'w', encoding='utf-8') as f:
        f.write(html)
    return history_file

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
    # Priority: 1) Yesterday's dated file, 2) _previous files, 3) prototype files
    previous_char_file = None
    previous_inv_file = None
    current_char_file = char_file
    current_inv_file = inv_file
    
    # First, try to find yesterday's file based on current file's date
    # This ensures we compare today vs yesterday for daily deltas
    yesterday_char_file = find_yesterday_file(char_file, char_dir)
    yesterday_inv_file = find_yesterday_file(inv_file, inv_dir)
    
    if yesterday_char_file and yesterday_inv_file:
        print(f"[OK] Found yesterday's files based on current file date (daily delta):")
        print(f"  Yesterday: {os.path.basename(yesterday_char_file)}")
        print(f"  Current: {os.path.basename(current_char_file)}")
        previous_char_file = yesterday_char_file
        previous_inv_file = yesterday_inv_file
    else:
        # Fall back to _previous files from workflow (may be older than yesterday)
        previous_char_file = os.path.join(char_dir, "TAKP_character_previous.txt")
        previous_inv_file = os.path.join(inv_dir, "TAKP_character_inventory_previous.txt")
        if os.path.exists(previous_char_file) and os.path.exists(previous_inv_file):
            print(f"[WARNING] Using _previous files (yesterday's dated files not found - may not be daily delta):")
            print(f"  Previous: {os.path.basename(previous_char_file)}")
            print(f"  Current: {os.path.basename(current_char_file)}")
        else:
            # Last resort: check for prototype files (for testing)
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
        
        # Step 2: Compare today vs baseline and save daily delta
        print(f"Comparing today ({date_str}) vs baseline ({baseline['baseline_date']})...")
        try:
            daily_delta_path = save_daily_delta_from_baseline(
                current_char_data, current_inventories, date_str, delta_snapshots_dir
            )
            print(f"Saved daily delta JSON: {daily_delta_path}")
        except Exception as e:
            print(f"Warning: Could not save daily delta JSON: {e}")
            import traceback
            traceback.print_exc()
            # Fall back to old method if baseline comparison fails
            char_deltas = compare_character_data(current_char_data, previous_char_data, None)
            inv_deltas = compare_inventories(current_inventories, previous_inventories, None)
            delta_data = {'char_deltas': char_deltas, 'inv_deltas': inv_deltas}
            daily_delta_path = save_daily_delta_json(delta_data, date_str, delta_snapshots_dir)
        
        # Step 3: Generate delta HTML by comparing today's delta vs yesterday's delta (default to 1 day)
        # Load today's and yesterday's deltas
        today_delta = load_daily_delta_json(date_str, delta_snapshots_dir)
        
        # Calculate yesterday's date
        from datetime import timedelta
        today_dt = datetime.strptime(date_str, '%Y-%m-%d')
        yesterday_dt = today_dt - timedelta(days=1)
        yesterday_date_str = yesterday_dt.strftime('%Y-%m-%d')
        
        yesterday_delta = load_daily_delta_json(yesterday_date_str, delta_snapshots_dir)
        
        if today_delta and yesterday_delta:
            # Compare deltas: today's delta vs yesterday's delta
            delta_comparison = compare_delta_to_delta(yesterday_delta, today_delta)
            char_deltas = delta_comparison['char_deltas']
            inv_deltas = delta_comparison['inv_deltas']
            print(f"Generated delta comparison from JSON: {yesterday_date_str} to {date_str}")
        elif today_delta:
            # Only today's delta available, show changes from baseline
            char_deltas = today_delta.get('char_deltas', {})
            inv_deltas = today_delta.get('inv_deltas', {})
            print(f"Showing changes from baseline to {date_str} (yesterday's delta not available)")
        else:
            # Fall back to comparing current vs previous files (backward compatibility)
            print("Warning: Daily deltas not available, falling back to file comparison")
            char_deltas = compare_character_data(current_char_data, previous_char_data, None)
            inv_deltas = compare_inventories(current_inventories, previous_inventories, None)
        
        # Get item names for inventory deltas
        all_item_ids = set()
        for char_delta in inv_deltas.values():
            all_item_ids.update(char_delta.get('added', {}).keys())
            all_item_ids.update(char_delta.get('removed', {}).keys())
        
        item_names = {}
        for char_name, items in current_inventories.items():
            for item in items:
                if item['item_id'] in all_item_ids:
                    item_names[item['item_id']] = item['item_name']
        
        # Populate item names in deltas
        for char_delta in inv_deltas.values():
            for item_id in char_delta.get('added', {}):
                if item_id in item_names:
                    char_delta.setdefault('item_names', {})[item_id] = item_names[item_id]
            for item_id in char_delta.get('removed', {}):
                if item_id in item_names:
                    char_delta.setdefault('item_names', {})[item_id] = item_names[item_id]
        
        # Generate delta HTML
        delta_html = generate_delta_html(
            current_char_data, previous_char_data,
            current_inventories, previous_inventories,
            magelo_update_date,
            serverwide=True,
            char_deltas=char_deltas,
            inv_deltas=inv_deltas
        )
        
        delta_file = os.path.join(base_dir, "delta.html")
        print(f"Writing delta HTML to {delta_file}...")
        with open(delta_file, 'w', encoding='utf-8') as f:
            f.write(delta_html)
        print("Delta page generated successfully!")
        
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
            
            # Generate weekly leaderboard page (compare current vs weekly baseline)
            weekly_aa = get_weekly_leaderboard(week_start, 'aa', 20, delta_snapshots_dir, current_char_data)
            weekly_hp = get_weekly_leaderboard(week_start, 'hp', 20, delta_snapshots_dir, current_char_data)
            weekly_html = generate_leaderboard_html(
                f"Week of {week_start}", weekly_aa, weekly_hp, 'weekly'
            )
            weekly_file = os.path.join(base_dir, f"leaderboard_week_{week_start}.html")
            with open(weekly_file, 'w', encoding='utf-8') as f:
                f.write(weekly_html)
            print(f"Generated weekly leaderboard: {weekly_file}")
            
            # Generate monthly leaderboard page (compare current vs monthly baseline)
            monthly_aa = get_monthly_leaderboard(month_start, 'aa', 20, delta_snapshots_dir, current_char_data)
            monthly_hp = get_monthly_leaderboard(month_start, 'hp', 20, delta_snapshots_dir, current_char_data)
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
        
        # Generate weekly leaderboard (compare current vs weekly baseline in delta_snapshots)
        weekly_aa = get_weekly_leaderboard(week_start, 'aa', 20, delta_snapshots_dir, current_char_data_for_lb)
        weekly_hp = get_weekly_leaderboard(week_start, 'hp', 20, delta_snapshots_dir, current_char_data_for_lb)
        weekly_html = generate_leaderboard_html(
            f"Week of {week_start}", weekly_aa, weekly_hp, 'weekly'
        )
        weekly_file = os.path.join(base_dir, f"leaderboard_week_{week_start}.html")
        with open(weekly_file, 'w', encoding='utf-8') as f:
            f.write(weekly_html)
        print(f"Generated weekly leaderboard: {weekly_file}")
        
        # Generate monthly leaderboard (compare current vs monthly baseline in delta_snapshots)
        monthly_aa = get_monthly_leaderboard(month_start, 'aa', 20, delta_snapshots_dir, current_char_data_for_lb)
        monthly_hp = get_monthly_leaderboard(month_start, 'hp', 20, delta_snapshots_dir, current_char_data_for_lb)
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
