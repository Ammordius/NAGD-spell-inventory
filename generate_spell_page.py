#!/usr/bin/env python3
"""
Script to generate a static HTML page showing which mule characters have
spells from PoK turn-ins (items 29112, 29131, 29132).
"""

import json
import os
from collections import defaultdict

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
        
        # Detect deleted characters (not in current data, or level 0 in current but was > 0 in previous)
        is_deleted = (char_name not in current_data) or (current_level == 0 and previous_level > 0)
        
        delta = {
            'name': char_name,
            'level_change': current_level - previous_level if current_level < 65 and not is_deleted else 0,  # Don't track level changes for 65 or deleted
            'aa_total_change': current_aa_total - previous_aa_total,
            'current_level': current_level if not is_deleted else previous_level,  # Show previous level for deleted
            'previous_level': previous_level,
            'current_aa_total': current_aa_total if not is_deleted else previous_aa_total,  # Show previous AA for deleted
            'previous_aa_total': previous_aa_total,
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

def compare_inventories(current_inv, previous_inv, character_list=None):
    """Compare current and previous inventories to find item deltas.
    If character_list is None, compares all characters (serverwide)."""
    item_deltas = {}
    
    # Get all characters from both inventories
    all_chars = set(list(current_inv.keys()) + list(previous_inv.keys()))
    if character_list is not None:
        all_chars = all_chars.intersection(set(character_list))
    
    for char_name in all_chars:
        if char_name not in current_inv and char_name not in previous_inv:
            continue
            
        current_items = defaultdict(int)
        previous_items = defaultdict(int)
        
        # Count items in current inventory
        if char_name in current_inv:
            for item in current_inv[char_name]:
                item_id = item['item_id']
                current_items[item_id] += 1
        
        # Count items in previous inventory
        if char_name in previous_inv:
            for item in previous_inv[char_name]:
                item_id = item['item_id']
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
                        magelo_update_date, serverwide=True):
    """Generate HTML page showing deltas between current and previous magelo dump.
    If serverwide is True, compares all characters, otherwise only mules."""
    
    # Compare character data (serverwide)
    char_deltas = compare_character_data(current_char_data, previous_char_data, None if serverwide else None)
    
    # Compare inventories (serverwide)
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
    </style>
</head>
<body>
    <div class="container">
        <h1>TAKP Mule Delta Report</h1>
        <p>Changes detected since previous magelo dump (last updated: """ + magelo_update_date + """)</p>
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
    
    html += """
"""
    
    # Character level and AA changes
    if char_deltas:
        html += """
        <h2>Character Level & AA Changes</h2>
        <table class="delta-table">
            <thead>
                <tr>
                    <th>Character</th>
                    <th>Class</th>
                    <th>Level</th>
                    <th>Level Change</th>
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
            
            # Level change display (only for < 65, not for deleted)
            if is_deleted:
                level_display = f'<span class="negative">Deleted (was {delta["previous_level"]})</span>'
            elif current_level < 65:
                level_class = "positive" if delta['level_change'] > 0 else "negative" if delta['level_change'] < 0 else "neutral"
                level_text = f"+{delta['level_change']}" if delta['level_change'] > 0 else str(delta['level_change'])
                level_display = f'<span class="{level_class}">{level_text} ({delta["previous_level"]} → {delta["current_level"]})</span>'
            else:
                level_display = '<span class="neutral">—</span>'  # No level tracking for 65
            
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
    
    # Inventory changes
    if inv_deltas:
        html += """
        <h2>Inventory Changes</h2>
        <p><em>Showing characters with inventory changes (limited to first 500 characters for performance)</em></p>
"""
        # Limit to first 500 characters for performance
        sorted_chars = sorted(inv_deltas.keys())[:500]
        for char_name in sorted_chars:
            delta = inv_deltas[char_name]
            html += f"""
        <div style="margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
            <h3>{char_name}</h3>
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
    
    html += """
    </div>
</body>
</html>
"""
    
    return html

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

def main():
    # File paths
    base_dir = os.path.dirname(__file__)
    char_dir = os.path.join(base_dir, "character")
    inv_dir = os.path.join(base_dir, "inventory")
    output_file = os.path.join(base_dir, "spell_inventory.html")
    
    # Try to find the latest files, or use specific names
    char_file = find_latest_magelo_file(char_dir, "TAKP_character") or find_latest_magelo_file(char_dir)
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
    # For prototyping, check for specific files first
    previous_char_file = None
    previous_inv_file = None
    
    # Check for prototype files first
    proto_prev_char = os.path.join(char_dir, "1_14_24.txt")
    proto_prev_inv = os.path.join(inv_dir, "1_14_24.txt")
    proto_curr_char = os.path.join(char_dir, "1_17_24.txt")
    proto_curr_inv = os.path.join(inv_dir, "1_17_24.txt")
    
    if os.path.exists(proto_prev_char) and os.path.exists(proto_prev_inv) and \
       os.path.exists(proto_curr_char) and os.path.exists(proto_curr_inv):
        print("Prototype files found (1_14_24 and 1_17_24), generating serverwide delta page...")
        previous_char_file = proto_prev_char
        previous_inv_file = proto_prev_inv
        current_char_file = proto_curr_char
        current_inv_file = proto_curr_inv
    else:
        # Check for previous day's files from workflow
        previous_char_file = os.path.join(char_dir, "TAKP_character_previous.txt")
        previous_inv_file = os.path.join(inv_dir, "TAKP_character_inventory_previous.txt")
        current_char_file = char_file
        current_inv_file = inv_file
    
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
                print("⚠ Warning: Previous and current files are identical (same hash) - no changes to show")
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
        
        # Generate delta HTML (serverwide)
        delta_html = generate_delta_html(
            current_char_data, previous_char_data,
            current_inventories, previous_inventories,
            magelo_update_date,
            serverwide=True
        )
        
        delta_file = os.path.join(base_dir, "delta.html")
        print(f"Writing delta HTML to {delta_file}...")
        with open(delta_file, 'w', encoding='utf-8') as f:
            f.write(delta_html)
        print("Delta page generated successfully!")
    else:
        print("Previous day's files not found, skipping delta page generation.")
        if previous_char_file:
            print(f"Looking for: {previous_char_file} and {previous_inv_file}")
    
    print("Done!")

if __name__ == "__main__":
    main()
