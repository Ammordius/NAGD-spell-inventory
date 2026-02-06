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

def parse_character_file(char_file):
    """Parse character file to get character IDs."""
    char_ids = {}
    with open(char_file, 'r', encoding='utf-8') as f:
        # Skip header
        next(f)
        for line in f:
            parts = line.strip().split('\t')
            if len(parts) < 9:
                continue
            name = parts[0]
            if name in MULE_CHARACTERS:
                char_id = parts[8]  # 9th column (0-indexed = 8)
                char_ids[name] = char_id
    return char_ids

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

def generate_html(char_ids, inventories, spell_info):
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
    
    # Create reverse mapping: spell_id -> list of characters who have it
    spell_to_chars = defaultdict(list)
    for char_name, spells in pok_spells.items():
        for spell_id, count in spells.items():
            spell_to_chars[spell_id].append((char_name, count))
    
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
        <p>Generated from magelo dump: 2_6_26.txt</p>
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
    
    for char_name in sorted(MULE_CHARACTERS):
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
    char_ids = parse_character_file(char_file)
    print(f"Found {len(char_ids)} characters: {', '.join(sorted(char_ids.keys()))}")
    
    print(f"Parsing inventory file: {os.path.basename(inv_file)}...")
    inventories = parse_inventory_file(inv_file, char_ids)
    print(f"Found inventories for {len(inventories)} characters")
    
    print("Generating HTML...")
    html = generate_html(char_ids, inventories, spell_info)
    
    print(f"Writing HTML to {output_file}...")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print("Done!")

if __name__ == "__main__":
    main()
