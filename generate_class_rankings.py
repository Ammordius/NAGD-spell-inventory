#!/usr/bin/env python3
"""
Generate class-specific character rankings with focus analysis
"""

import csv
import json
import os
import sys
from collections import defaultdict

# Class definitions (hybrids Paladin, Shadow Knight, Beastlord, Ranger have mana and FT)
CLASSES_WITH_MANA = {'Cleric', 'Druid', 'Shaman', 'Necromancer', 'Wizard', 'Magician', 'Enchanter', 'Bard', 'Paladin', 'Shadow Knight', 'Beastlord', 'Ranger'}
CLASSES_NEED_AC = {'Warrior', 'Shadow Knight', 'Paladin', 'Beastlord', 'Ranger'}
CLASSES_NEED_ATK = {'Rogue', 'Ranger', 'Monk', 'Warrior', 'Shadow Knight', 'Paladin', 'Beastlord', 'Bard'}
PURE_MELEE = {'Warrior', 'Rogue', 'Monk'}

# Load spell focus data
def load_focii():
    possible_paths = [
        '../Server/spell_focii_level65.json',
        'spell_focii_level65.json',
        '../spell_focii_level65.json',
        '../../Server/spell_focii_level65.json',  # For GitHub Actions workflow
        'Server/spell_focii_level65.json'  # Alternative path
    ]
    
    for path in possible_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"Loaded focii from: {path}")
                return data.get('focii', [])
        except FileNotFoundError:
            continue
    
    print("Warning: spell_focii_level65.json not found. Focus analysis will be skipped.")
    return []

def load_bard_instruments():
    """Load bard instrument focus data (item mods, cap 390%, 60% AA, 230% from items)."""
    possible_paths = [
        'bard_instrument_focii.json',
        '../magelo/bard_instrument_focii.json',
        '../bard_instrument_focii.json',
    ]
    for path in possible_paths:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"Loaded bard instruments from: {path}")
                return data
        except FileNotFoundError:
            continue
    print("Warning: bard_instrument_focii.json not found. Bard instrument focus will be skipped.")
    return None

# Get CSV row value by key, trying exact match then case-insensitive match.
# Handles export format variations (e.g. Mana_Regen_Item) so FT (Flowing Thought) is read correctly.
def _row_get(row, preferred_key, default=''):
    value = row.get(preferred_key, default)
    if value != '' and value is not None:
        return value
    key_lower = preferred_key.lower().replace(' ', '')
    for k, v in row.items():
        if k and v not in ('', None) and k.lower().replace(' ', '') == key_lower:
            return v
    return default


# Normalize item name for matching (handle apostrophes, case, etc.)
def normalize_item_name(name):
    """Normalize item name for matching"""
    if not name:
        return ''
    # Convert to lowercase and remove apostrophes
    normalized = name.lower().strip()
    normalized = normalized.replace("'", "").replace("'", "").replace("`", "")
    # Remove extra spaces
    normalized = ' '.join(normalized.split())
    return normalized

# Create focus lookup by item name (normalized) and optionally by item id
def create_focus_lookup(focii_data):
    """Create a lookup: item_name (normalized) or item_id (str) -> focus effects"""
    focus_by_item_name = defaultdict(list)
    
    for focus in focii_data:
        for item in focus.get('items', []):
            effect = {
                'name': focus['name'],
                'category': focus['category'],
                'percentage': focus['percentage']
            }
            item_name = normalize_item_name(item.get('name', ''))
            if item_name:
                focus_by_item_name[item_name].append(effect)
            if item.get('id') is not None:
                focus_by_item_name[str(item['id'])].append(effect)
    
    print(f"Created focus lookup with {len(focus_by_item_name)} unique item names/ids")
    return focus_by_item_name

# Get best focus percentage for each category
def get_best_focii_by_category(focii_data):
    """Get the highest percentage focus in each category"""
    best_by_category = {}
    
    for focus in focii_data:
        cat = focus['category']
        pct = focus['percentage']
        if cat not in best_by_category or pct > best_by_category[cat]:
            best_by_category[cat] = pct
    
    return best_by_category


def get_best_focii_by_subcategory(focii_data):
    """Get the best focus percentage per subcategory for Mana Efficiency, Spell Haste, and Duration.
    Used so we can show and score each category separately (e.g. Det vs Bene vs Self-only mana eff)."""
    best_mana = defaultdict(float)
    best_haste = defaultdict(float)
    best_duration = defaultdict(float)
    for focus in focii_data:
        name = focus.get('name', '')
        cat = focus.get('category', '')
        pct = focus.get('percentage', 0)
        if cat == 'Spell Mana Efficiency':
            sub = SPELL_MANA_EFFICIENCY_CATEGORY_MAP.get(name, 'Nuke')
            if pct > best_mana[sub]:
                best_mana[sub] = pct
        elif cat == 'Spell Haste':
            sub = SPELL_HASTE_CATEGORY_MAP.get(name, 'Bene')
            if pct > best_haste[sub]:
                best_haste[sub] = pct
        elif cat == 'Buff Spell Duration':
            if pct > best_duration['Bene']:
                best_duration['Bene'] = pct
        elif cat == 'Detrimental Spell Duration':
            if pct > best_duration['Det']:
                best_duration['Det'] = pct
        elif cat == 'All Spell Duration':
            if pct > best_duration['All']:
                best_duration['All'] = pct
    return dict(best_mana), dict(best_haste), dict(best_duration)

# Analyze character gear for focii
def analyze_character_focii(char_inventory, focus_lookup):
    """Analyze a character's gear and return best focus in each category and damage type"""
    char_focii = defaultdict(float)  # category -> best percentage
    char_damage_focii = defaultdict(float)  # damage_type -> best percentage
    # Track categories for Mana Efficiency, Spell Haste, and Duration
    char_mana_efficiency_cats = defaultdict(float)  # category -> best percentage
    char_spell_haste_cats = defaultdict(float)  # category -> best percentage
    char_duration_cats = defaultdict(float)  # category -> best percentage
    
    for item in char_inventory:
        item_name = normalize_item_name(item.get('item_name', ''))
        item_id = str(item.get('item_id', '')) if item.get('item_id') is not None else ''
        lookup_key = item_name if item_name in focus_lookup else (item_id if item_id in focus_lookup else None)
        if lookup_key is not None:
            for focus_effect in focus_lookup[lookup_key]:
                focus_name = focus_effect['name']
                cat = focus_effect['category']
                pct = focus_effect['percentage']
                
                # Keep the best (highest) focus in each category
                if pct > char_focii[cat]:
                    char_focii[cat] = pct
                
                # For spell damage, also track by damage type
                if cat == 'Spell Damage':
                    damage_type = SPELL_DAMAGE_TYPE_MAP.get(focus_name, 'All')
                    if pct > char_damage_focii[damage_type]:
                        char_damage_focii[damage_type] = pct
                
                # Track Mana Efficiency categories
                if cat == 'Spell Mana Efficiency':
                    efficiency_cat = SPELL_MANA_EFFICIENCY_CATEGORY_MAP.get(focus_name, 'Nuke')
                    if pct > char_mana_efficiency_cats[efficiency_cat]:
                        char_mana_efficiency_cats[efficiency_cat] = pct
                
                # Track Spell Haste categories
                if cat == 'Spell Haste':
                    haste_cat = SPELL_HASTE_CATEGORY_MAP.get(focus_name, 'Bene')
                    if pct > char_spell_haste_cats[haste_cat]:
                        char_spell_haste_cats[haste_cat] = pct
                
                # Track Duration categories
                if cat in ['Buff Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration']:
                    if cat == 'All Spell Duration':
                        # All Spell Duration applies to both, track as "All"
                        if pct > char_duration_cats['All']:
                            char_duration_cats['All'] = pct
                    else:
                        duration_cat = SPELL_DURATION_CATEGORY_MAP.get(focus_name, 
                            'Bene' if cat == 'Buff Spell Duration' else 'Det')
                        if pct > char_duration_cats[duration_cat]:
                            char_duration_cats[duration_cat] = pct
    
    return (dict(char_focii), dict(char_damage_focii), 
            dict(char_mana_efficiency_cats), dict(char_spell_haste_cats), dict(char_duration_cats))


def get_focus_sources(char_inventory, focus_lookup):
    """Return per-focus item sources for equipped gear (slots 1-22 only).
    Pet Power is checked from full inventory (including bags) so swap-in is shown.
    Keys match focus_scores keys where possible. Skip attack haste (Haste/ATK) item listing.
    Value is list of {item_name, slot_id, value, item_id} for the best item(s) providing that focus."""
    EQUIPPED_SLOTS = set(range(1, 23))  # 1-22
    best = {}  # focus_key -> (pct, item_name, slot_id, item_id)

    def set_best(key, pct, item_name, slot_id, item_id=None):
        if key not in best or pct > best[key][0]:
            best[key] = (pct, item_name, slot_id, item_id)

    # Pet Power: check full inventory (including bags) so swap-in items are shown
    for item in char_inventory or []:
        item_id = str(item.get('item_id', '')) if item.get('item_id') is not None else ''
        if item_id in PET_POWER_ITEMS:
            pct = PET_POWER_ITEMS[item_id]
            item_name = item.get('item_name', '') or item.get('name', '') or f'Item {item_id}'
            slot_id = item.get('slot_id', 0)
            set_best('Pet Power', pct, item_name, slot_id, item_id)

    for item in char_inventory or []:
        slot_id = item.get('slot_id', 0)
        if slot_id not in EQUIPPED_SLOTS:
            continue
        item_id = str(item.get('item_id', '')) if item.get('item_id') is not None else ''
        item_name = item.get('item_name', '') or item.get('name', '') or f'Item {item_id}'

        # Binary focus items (we don't list ATK/Haste sources per user request)
        if item_id == PALADIN_SK_FOCUS_ITEMS['shield']:
            set_best('Shield of Strife', 100, item_name, slot_id, item_id)
            continue
        if item_id == ENCHANTER_FOCUS_ITEMS['range']:
            set_best('Serpent of Vindication', 100, item_name, slot_id, item_id)
            continue
        if item_id == SHAMAN_FOCUS_ITEMS['range']:
            set_best("Time's Antithesis", 100, item_name, slot_id, item_id)
            continue
        if item_id == WARRIOR_FOCUS_ITEMS['mh']:
            set_best('Darkblade', 100, item_name, slot_id, item_id)
            continue
        if item_id == WARRIOR_FOCUS_ITEMS['chest']:
            set_best('Raex Chest', 100, item_name, slot_id, item_id)
            continue

        item_name_norm = normalize_item_name(item_name)
        lookup_key = item_name_norm if item_name_norm in focus_lookup else (item_id if item_id in focus_lookup else None)
        if lookup_key is None:
            continue

        for focus_effect in focus_lookup[lookup_key]:
            focus_name = focus_effect['name']
            cat = focus_effect['category']
            pct = focus_effect['percentage']

            if cat == 'Spell Damage':
                damage_type = SPELL_DAMAGE_TYPE_MAP.get(focus_name, 'All')
                set_best(f'Spell Damage ({damage_type})', pct, item_name, slot_id, item_id)
            elif cat == 'Spell Mana Efficiency':
                sub = SPELL_MANA_EFFICIENCY_CATEGORY_MAP.get(focus_name, 'Nuke')
                set_best(f'Spell Mana Efficiency ({sub})', pct, item_name, slot_id, item_id)
            elif cat == 'Spell Haste':
                sub = SPELL_HASTE_CATEGORY_MAP.get(focus_name, 'Bene')
                if sub == 'Det':
                    set_best('Detrimental Spell Haste', pct, item_name, slot_id, item_id)
                else:
                    set_best('Beneficial Spell Haste', pct, item_name, slot_id, item_id)
            elif cat in ('Buff Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration'):
                if cat == 'All Spell Duration':
                    set_best('Buff Spell Duration', pct, item_name, slot_id, item_id)
                    set_best('Detrimental Spell Duration', pct, item_name, slot_id, item_id)
                else:
                    dur_cat = SPELL_DURATION_CATEGORY_MAP.get(focus_name, 'Bene' if cat == 'Buff Spell Duration' else 'Det')
                    key = 'Buff Spell Duration' if dur_cat == 'Bene' else 'Detrimental Spell Duration'
                    set_best(key, pct, item_name, slot_id, item_id)
            else:
                # Healing Enhancement, Spell Range Extension, etc.
                set_best(cat, pct, item_name, slot_id, item_id)

    # Convert to list of dicts for JSON (include item_id for item links in UI)
    result = {}
    for key, (pct, name, sid, iid) in best.items():
        result[key] = [{'item_name': name, 'slot_id': sid, 'value': pct, 'item_id': iid}]
    return result


def load_item_stats():
    """Load item_id -> classes from data/item_stats.json if present. Used to filter focus candidates by class."""
    base_dir = os.path.dirname(__file__) if '__file__' in globals() else '.'
    for path in [os.path.join(base_dir, 'data', 'item_stats.json'), 'data/item_stats.json']:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return {str(iid): (info.get('classes') or '').strip() for iid, info in data.items() if info.get('classes')}
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def load_item_stats_name_to_id():
    """Load data/item_stats.json and return normalized item name -> item_id (str). Used to backfill missing item_id in inventory."""
    base_dir = os.path.dirname(__file__) if '__file__' in globals() else '.'
    for path in [os.path.join(base_dir, 'data', 'item_stats.json'), 'data/item_stats.json']:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            name_to_id = {}
            for iid, info in (data or {}).items():
                name = (info.get('name') or '').strip()
                if name:
                    norm = normalize_item_name(name)
                    if norm and norm not in name_to_id:
                        name_to_id[norm] = str(iid)
            return name_to_id
        except (FileNotFoundError, json.JSONDecodeError):
            continue
    return {}


def get_all_focus_candidates(focii_data, item_stats_lookup=None):
    """Build a map of focus_key -> list of {item_name, item_id, value, classes?} for all items that provide that focus.
    Used in the UI to show 'items that could give this focus' when the character doesn't have it but weight > 0.
    If item_stats_lookup (item_id -> classes string) is provided, each candidate gets a 'classes' field for class filtering."""
    if item_stats_lookup is None:
        item_stats_lookup = {}
    candidates = defaultdict(list)
    for focus in focii_data:
        name = focus.get('name', '')
        cat = focus.get('category', '')
        pct = focus.get('percentage', 0)
        for item in focus.get('items', []):
            item_name = item.get('name', '') or ('Item ' + str(item.get('id', '')) if item.get('id') is not None else '')
            item_id = str(item['id']) if item.get('id') is not None else ''
            if not item_name and not item_id:
                continue
            entry = {'item_name': item_name or f'Item {item_id}', 'item_id': item_id, 'value': pct}
            if item_id and item_stats_lookup:
                cls_str = item_stats_lookup.get(item_id, '')
                if cls_str:
                    entry['classes'] = cls_str
            if cat == 'Spell Damage':
                damage_type = SPELL_DAMAGE_TYPE_MAP.get(name, 'All')
                key = f'Spell Damage ({damage_type})'
                candidates[key].append(entry)
            elif cat == 'Spell Mana Efficiency':
                sub = SPELL_MANA_EFFICIENCY_CATEGORY_MAP.get(name, 'Nuke')
                key = f'Spell Mana Efficiency ({sub})'
                candidates[key].append(entry)
            elif cat == 'Spell Haste':
                sub = SPELL_HASTE_CATEGORY_MAP.get(name, 'Bene')
                key = 'Detrimental Spell Haste' if sub == 'Det' else 'Beneficial Spell Haste'
                candidates[key].append(entry)
            elif cat in ('Buff Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration'):
                if cat == 'All Spell Duration':
                    candidates['Buff Spell Duration'].append(entry)
                    candidates['Detrimental Spell Duration'].append(entry)
                else:
                    dur_cat = SPELL_DURATION_CATEGORY_MAP.get(name, 'Bene' if cat == 'Buff Spell Duration' else 'Det')
                    key = 'Buff Spell Duration' if dur_cat == 'Bene' else 'Detrimental Spell Duration'
                    candidates[key].append(entry)
            else:
                # Healing Enhancement, Spell Range Extension, etc.
                candidates[cat].append(entry)
    # Dedupe by item_id per key (keep highest value)
    result = {}
    for key, items in candidates.items():
        by_id = {}
        for it in items:
            iid = it.get('item_id', '')
            if iid not in by_id or (it.get('value', 0) or 0) > (by_id[iid].get('value', 0) or 0):
                by_id[iid] = it
        result[key] = sorted(by_id.values(), key=lambda x: (0 - (x.get('value') or 0), x.get('item_name', '')))
    # Pet Power: item-based, not in spell focii data
    pet_entries = []
    for iid, pct in PET_POWER_ITEMS.items():
        e = {'item_id': str(iid), 'item_name': PET_POWER_ITEM_NAMES.get(str(iid), f'Item {iid}'), 'value': pct}
        if item_stats_lookup and str(iid) in item_stats_lookup:
            e['classes'] = item_stats_lookup[str(iid)]
        pet_entries.append(e)
    result['Pet Power'] = sorted(pet_entries, key=lambda x: (0 - (x.get('value') or 0), x.get('item_name', '')))
    return result


# Map spell damage focii to damage types
SPELL_DAMAGE_TYPE_MAP = {
    # Magic damage focii (Druzzil is the god of magic)
    'Anger of Druzzil': 'Magic',
    'Fury of Druzzil': 'Magic',
    'Wrath of Druzzil': 'Magic',
    
    # Fire damage focii (Ro, Solusek are fire gods)
    'Anger of Ro': 'Fire',
    'Anger of Solusek': 'Fire',
    'Fury of Ro': 'Fire',
    'Fury of Solusek': 'All',  # All damage 30% on item 20496 (not fire)
    'Wrath of Ro': 'Fire',
    'Burning Affliction': 'Fire',
    'Focus of Flame': 'Fire',
    'Fires of Sol': 'Fire',
    'Inferno of Sol': 'Fire',
    "Summer's Anger": 'Fire',
    "Summer's Vengeance": 'Fire',
    
    # Cold damage focii (E`ci is cold god)
    'Anger of E`ci': 'Cold',
    'Fury of E`ci': 'Cold',
    'Wrath of E`ci': 'Cold',
    'Chill of the Umbra': 'Cold',
    
    # Magic damage focii
    'Enchantment of Destruction': 'Magic',
    'Insidious Dreams': 'Magic',
    
    # Saryrn's Torment / Saryrn's Venom are mana preservation on nuke, not spell damage. Fury of Bertoxxulous is SK-only.
    
    # DoT-only spell damage (not instant); tracked for Necro/Shaman. "All" is instant-only and does not apply.
    'Vengeance of Eternity': 'DoT',   # 30% DoT, items 32142, 20898
    'Vengeance of Time': 'DoT',       # 25% DoT, item 26748
    'Cursed Extension': 'DoT',        # 20% DoT, item 28980
    
    # All damage types (instant/nuke only; does not apply to DoT)
    'Improved Damage': 'All',
    "Gallenite's ____": 'All',
}

# Map Spell Mana Efficiency focii to categories (nuke, detrimental, beneficial, Sanguine)
SPELL_MANA_EFFICIENCY_CATEGORY_MAP = {
    # Detrimental mana efficiency
    'Affliction Efficiency': 'Det',
    'Affliction Preservation': 'Det',
    
    # Beneficial mana efficiency
    'Enhancement Efficiency': 'Bene',
    'Enhancement Preservation': 'Bene',
    'Preservation of Mithaniel': 'Bene',
    'Reanimation Efficiency': 'Bene',
    'Reanimation Preservation': 'Bene',
    'Summoning Efficiency': 'Bene',
    'Summoning Preservation': 'Bene',
    'Alluring Preservation': 'Bene',
    
    # Nuke mana efficiency (direct damage spells)
    'Mana Preservation': 'Nuke',  # Generic nuke focus
    'Preservation of Xegony': 'Nuke',
    'Preservation of Solusek': 'Nuke',
    'Preservation of Ro': 'Nuke',
    'Preservation of Druzzil': 'Nuke',
    
    # Sanguine Preservation (self only)
    'Sanguine Preservation': 'Sanguine',
    'Sanguine Enchantment': 'Sanguine',

    # All spells (applies to Bene, Det, Nuke - count for all when scoring)
    # Add any focus that applies to all spell types here
    # 'Mana Preservation': 'All',  # if generic preservation applies to all
}

# Map Spell Haste focii to categories (detrimental, beneficial, or All).
# Scoring uses max(Bene, All) and max(Det, All), so 'All' counts for BOTH Beneficial and Detrimental.
# Add e.g. 'All Spell Haste': 'All' here if a focus applies to both; then track best_haste['All'] in get_best_focii_by_subcategory.
SPELL_HASTE_CATEGORY_MAP = {
    # Detrimental haste
    'Affliction Haste': 'Det',
    'Haste of Solusek': 'Det',
    'Quickening of Solusek': 'Det',  # Detrimental spell haste
    
    # Beneficial haste
    'Enhancement Haste': 'Bene',
    'Reanimation Haste': 'Bene',
    'Summoning Haste': 'Bene',
    'Haste of Mithaniel': 'Bene',  # Paladin beneficial
    'Haste of Druzzil': 'Bene',  # Usually beneficial
    'Spell Haste': 'Bene',  # Generic beneficial
    
    # 'All Spell Haste': 'All',  # Uncomment if a focus applies to both Bene and Det
}

# Map Duration focii to categories (detrimental, beneficial)
# Note: "All Spell Duration" applies to both, so we'll track it separately
SPELL_DURATION_CATEGORY_MAP = {
    # Detrimental duration
    'Extended Affliction': 'Det',
    'Affliction Extension': 'Det',
    
    # Beneficial duration
    'Extended Enhancement': 'Bene',
    'Enhancement Extension': 'Bene',
    'Chrononostrum': 'Bene',
    'Eterninostrum': 'Bene',
    'Extended Reanimation': 'Bene',
    'Extended Summoning': 'Bene',
}

# Per-class weights for Spell Mana Efficiency categories (Bene, Det, Nuke).
# Consider each category separately; "All" (if present) counts for all of Bene/Det/Nuke.
# Score = weighted sum of (effective_cat_pct/best*100) / sum(weights), where effective_cat = max(cat_pct, all_pct).
SPELL_MANA_EFFICIENCY_WEIGHTS = {
    'Enchanter': {'Det': 1.0, 'Bene': 0.25},           # primarily det (mez/charm), small bene (buffs)
    'Shadow Knight': {'Det': 1.0},
    'Paladin': {'Bene': 1.0},
    'Wizard': {'Det': 1.0, 'Bene': 0.25},              # large det (nukes), small bene
    'Cleric': {'Bene': 1.0, 'Det': 0.25},              # large bene (heals), small det
    'Necromancer': {'Det': 1.0},
    'Shaman': {'Bene': 0.5, 'Det': 0.5},
    'Druid': {'Bene': 0.5, 'Det': 0.5},
    'Magician': {'Nuke': 1.0, 'Bene': 0.25},           # nuke + summoning (bene)
    'Beastlord': {'Bene': 0.5, 'Det': 0.5},
    'Ranger': {'Bene': 0.5, 'Det': 0.5},
}


def calculate_spell_mana_efficiency_score(char_mana_efficiency_cats, char_class, best_mana_eff, best_mana_by_cat=None):
    """Weighted Spell Mana Efficiency score (0-100). Each category (Bene/Det/Nuke/Sanguine) considered separately.
    All counts for all possible: effective_cat = max(cat_pct, all_pct).
    When best_mana_by_cat is provided, each category is compared to its own best; otherwise use best_mana_eff for all."""
    if not char_mana_efficiency_cats or best_mana_eff <= 0:
        return 0.0
    weights = SPELL_MANA_EFFICIENCY_WEIGHTS.get(char_class)
    if not weights:
        return 0.0
    all_pct = char_mana_efficiency_cats.get('All', 0)
    weighted_sum = 0.0
    total_weight = 0.0
    for cat, w in weights.items():
        if w <= 0:
            continue
        effective_pct = max(char_mana_efficiency_cats.get(cat, 0), all_pct)
        best_for_cat = (best_mana_by_cat.get(cat, best_mana_eff)) if best_mana_by_cat else best_mana_eff
        if best_for_cat <= 0:
            continue
        cat_score = (effective_pct / best_for_cat * 100) if effective_pct > 0 else 0
        weighted_sum += cat_score * w
        total_weight += w
    if total_weight <= 0:
        return 0.0
    return weighted_sum / total_weight


# Class-specific damage type priorities (DoT is special; "All" applies to other subcategories only, not a separate line)
CLASS_DAMAGE_TYPES = {
    'Necromancer': ['DoT'],   # DoT-only; instant covered by All but not a separate weighted category
    'Shaman': ['Cold', 'DoT'],  # Cold + DoT-only focus
    'Wizard': ['Fire', 'Cold', 'Magic'],
    'Magician': ['Fire', 'Magic'],
    'Druid': ['Fire', 'Cold'],
    'Enchanter': ['Magic'],
    'Cleric': ['Magic'],
    'Beastlord': ['Cold'],
}

# Class-specific focus priorities (updated with damage types)
CLASS_FOCUS_PRIORITIES = {
    'Necromancer': ['Spell Damage (DoT)', 'Spell Mana Efficiency', 'Spell Haste', 'Detrimental Spell Duration', 'Pet Power'],
    'Shaman': ['Spell Damage (Cold)', 'Spell Damage (DoT)', 'Healing Enhancement', 'Spell Mana Efficiency', 'Beneficial Spell Haste', 'Buff Spell Duration'],
    'Druid': ['Healing Enhancement', 'Spell Damage (Fire)', 'Spell Damage (Cold)', 'Spell Mana Efficiency', 'Buff Spell Duration'],
    'Cleric': ['Healing Enhancement', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Beneficial Spell Haste', 'Buff Spell Duration'],
    'Wizard': ['Spell Damage (Fire)', 'Spell Damage (Cold)', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste'],
    'Magician': ['Spell Damage (Fire)', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste', 'Detrimental Spell Haste'],
    'Enchanter': ['Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste', 'Buff Spell Duration'],
    'Beastlord': ['ATK', 'FT', 'Spell Damage (Cold)', 'Healing Enhancement', 'Spell Mana Efficiency', 'Buff Spell Duration', 'Beneficial Spell Haste', 'Detrimental Spell Haste'],
    'Bard': ['Brass', 'Percussion', 'Singing', 'Strings', 'Wind'],
}

# Class-specific focus items
WARRIOR_FOCUS_ITEMS = {
    'mh': '22999',  # Darkblade of the Warlord in Main Hand (slot 13)
    'chest': '32129'  # Raex's Chestplate of Destruction in Chest (slot 17)
}

PALADIN_SK_FOCUS_ITEMS = {
    'shield': '27298'  # Shield of Strife in Secondary (slot 14)
}

ENCHANTER_FOCUS_ITEMS = {
    'range': '22959'  # Serpent of Vindication in Range (slot 11)
}

# Time's Antithesis (item 24699) - same weight as Serpent of Vindication for Enchanters
SHAMAN_FOCUS_ITEMS = {
    'range': '24699'  # Time's Antithesis in Range (slot 11)
}

# Pet Power focus: item_id -> percentage. Checked from full inventory (including bags) so they can swap in.
PET_POWER_ITEMS = {
    '28144': 20,
    '20508': 25,
}
# Display names for Pet Power items (so we show names instead of "Item 20508")
PET_POWER_ITEM_NAMES = {
    '20508': 'Symbol of Ancient Summoning',
    '28144': 'Gloves of Dark Summoning',
}

def get_char_pet_power(char_inventory):
    """Return best Pet Power % from full inventory (including bags). Items 28144=20%, 20508=25%."""
    best = 0
    for item in char_inventory or []:
        iid = str(item.get('item_id', '')) if item.get('item_id') is not None else ''
        if iid in PET_POWER_ITEMS and PET_POWER_ITEMS[iid] > best:
            best = PET_POWER_ITEMS[iid]
    return best

def check_bard_instrument_focus(char_inventory, bard_data):
    """Bard instrument focus: take the BEST single mod in each category (not sum).
    All-type items (e.g. epic +80%) count for every instrument type.
    Singing: best regular singing item + best of the two harmonize items (Voice of the Serpent 60%, Shadowsong 90%).
    Cap 230% from items per type (390 total - 100 base - 60 AA)."""
    if not bard_data or not bard_data.get('items'):
        return {}, {}
    item_cap = bard_data.get('item_cap_from_items', 230)
    resonance = bard_data.get('singing_resonance_mods', {})  # item_id -> singing mod (VoS 60, Shadowsong 90)
    resonance_ids = set(resonance.keys())
    inst_types = ['Brass', 'Percussion', 'Singing', 'Strings', 'Wind']
    # Build lookup: item_id -> list of (instrument_type, mod). All -> contributes to all 5 types.
    item_to_contrib = {}
    for rec in bard_data['items']:
        iid = str(rec['item_id'])
        mod = rec['mod']
        typ = rec.get('instrument_type', '')
        if typ == 'All':
            contrib = [(t, mod) for t in inst_types]
        else:
            contrib = [(typ, mod)] if typ in inst_types else []
        if iid not in item_to_contrib:
            item_to_contrib[iid] = []
        item_to_contrib[iid].extend(contrib)
    # For resonance items, use their override mod for Singing only (for the "best harmonize" bucket)
    for iid in resonance_ids:
        if iid in item_to_contrib:
            item_to_contrib[iid] = [(t, resonance[iid] if t == 'Singing' else m) for t, m in item_to_contrib[iid]]
    equipped_ids = {str(item.get('item_id', '')) for item in char_inventory}
    # Per type: take BEST single mod from any equipped item that applies (including All)
    best_per_type = {t: 0 for t in inst_types}
    for iid in equipped_ids:
        for typ, mod in item_to_contrib.get(iid, []):
            if mod > best_per_type[typ]:
                best_per_type[typ] = mod
    # Singing: best regular (non-resonance) + best of the two harmonize items only
    best_regular_singing = 0
    best_resonance_singing = 0
    for iid in equipped_ids:
        for typ, mod in item_to_contrib.get(iid, []):
            if typ != 'Singing':
                continue
            if iid in resonance_ids:
                if mod > best_resonance_singing:
                    best_resonance_singing = mod
            else:
                if mod > best_regular_singing:
                    best_regular_singing = mod
    best_per_type['Singing'] = best_regular_singing + best_resonance_singing
    # Cap at item_cap per type, score 0-100 as % of cap
    focus_scores = {}
    for t in inst_types:
        capped = min(best_per_type[t], item_cap)
        focus_scores[t] = (capped / item_cap * 100.0) if item_cap > 0 else 0.0
    items_detail = {t: min(best_per_type[t], item_cap) for t in inst_types}
    return focus_scores, items_detail

def check_warrior_focus_items(char_inventory, char_haste):
    """Check if Warrior has the required focus items anywhere in inventory and max haste
    Returns individual scores for each item (Darkblade, Raex Chest, Haste)"""
    has_darkblade = False
    has_raex_chest = False
    
    for item in char_inventory:
        item_id = item.get('item_id', '')
        
        # Check for Darkblade (item 22999) anywhere in inventory
        if item_id == WARRIOR_FOCUS_ITEMS['mh']:
            has_darkblade = True
        # Check for Raex Chest (item 32129) anywhere in inventory
        if item_id == WARRIOR_FOCUS_ITEMS['chest']:
            has_raex_chest = True
    
    # Check haste - binary: 30% item haste (70% buff + 30% item = 100% total) = on, otherwise off
    # char_haste is the item haste value, so >= 30 means max total haste
    has_max_haste = (char_haste >= 30)
    
    # Return individual scores for each item (each has weight 1.0)
    darkblade_score = 100.0 if has_darkblade else 0.0
    raex_chest_score = 100.0 if has_raex_chest else 0.0
    haste_score = 100.0 if has_max_haste else 0.0
    
    return {
        'Darkblade': darkblade_score,
        'Raex Chest': raex_chest_score,
        'Haste': haste_score
    }, {'has_darkblade': has_darkblade, 'has_raex_chest': has_raex_chest, 'has_haste': has_max_haste}

def check_paladin_sk_focus_items(char_inventory):
    """Check if Paladin/Shadow Knight has Shield of Strife"""
    has_shield = False
    
    for item in char_inventory:
        slot_id = item.get('slot_id', 0)
        item_id = item.get('item_id', '')
        
        # Check Secondary (slot 14) for item 27298
        if slot_id == 14 and item_id == PALADIN_SK_FOCUS_ITEMS['shield']:
            has_shield = True
    
    # Focus score: 100% if has shield, 0% otherwise
    return 100.0 if has_shield else 0.0, {'has_shield': has_shield}

def check_enchanter_focus_items(char_inventory):
    """Check if Enchanter has Serpent of Vindication"""
    has_serpent = False
    
    for item in char_inventory:
        item_id = item.get('item_id', '')
        
        # Check if item 22959 (Serpent of Vindication) is in inventory (any slot)
        if item_id == ENCHANTER_FOCUS_ITEMS['range']:
            has_serpent = True
            break
    
    # Focus score: 100% if has serpent, 0% otherwise
    return 100.0 if has_serpent else 0.0, {'has_serpent': has_serpent}

def check_shaman_focus_items(char_inventory):
    """Check if Shaman has Time's Antithesis (same weight as Serpent of Vindication for Enchanters)"""
    has_times_antithesis = False
    for item in char_inventory:
        item_id = item.get('item_id', '')
        if item_id == SHAMAN_FOCUS_ITEMS['range']:
            has_times_antithesis = True
            break
    return 100.0 if has_times_antithesis else 0.0, {'has_times_antithesis': has_times_antithesis}

# Calculate class-specific scores
def calculate_class_scores(char_data, char_focii, char_damage_focii, best_focii, all_chars_by_class, char_inventory=None, char_spell_haste_cats=None, char_duration_cats=None, char_mana_efficiency_cats=None, bard_instrument_data=None, best_mana_by_cat=None, best_haste_by_cat=None, best_duration_by_cat=None, best_pet_power_by_class=None):
    """Calculate percentage scores for a character based on their class.
    best_*_by_cat: best focus % per subcategory (Det/Bene/Nuke/Sanguine for mana; Det/Bene for haste; Bene/Det/All for duration)."""
    char_class = char_data['class']
    scores = {}
    
    # HP - store raw value for conversion-based scoring
    scores['hp'] = char_data['stats']['hp']
    
    # Mana - only for classes with mana, store raw value
    if char_class in CLASSES_WITH_MANA:
        scores['mana'] = char_data.get('stats', {}).get('mana', 0)
    else:
        scores['mana'] = None  # Not applicable
    
    # AC - store for all classes (all classes get a small weight by default; tanks get full weight)
    scores['ac'] = char_data.get('stats', {}).get('ac', 0)
    
    # Resists - store raw total value (MR + FR + CR + DR + PR)
    scores['resists'] = char_data.get('stats', {}).get('resists', 0)
    
    # FT (Flowing Thought) - mana regen for casters/bards
    # Format: "current / 15" where 15 is the cap
    if char_class in CLASSES_WITH_MANA:
        mana_regen = char_data.get('stats', {}).get('mana_regen_item', '0 / 15')
        if isinstance(mana_regen, str) and ' / ' in mana_regen:
            ft_current = int(mana_regen.split(' / ')[0])
            ft_cap = int(mana_regen.split(' / ')[1]) if ' / ' in mana_regen else 15
        else:
            ft_current = 0
            ft_cap = 15
        scores['ft_current'] = ft_current
        scores['ft_cap'] = ft_cap
        scores['ft_pct'] = (ft_current / ft_cap * 100) if ft_cap > 0 else 0  # For display
        # FT capped (15/15) gets meaningful focus weight (4.0 raw, then scaled)
        scores['ft_capped'] = (ft_current >= ft_cap) if ft_cap > 0 else False
    else:
        scores['ft_current'] = None
        scores['ft_cap'] = None
        scores['ft_pct'] = None
        scores['ft_capped'] = None
    
    # ATK - only for melee/hybrid classes (% of 250 cap)
    if char_class in CLASSES_NEED_ATK:
        atk_item = char_data.get('stats', {}).get('atk_item', '0 / 250')
        if isinstance(atk_item, str) and ' / ' in atk_item:
            current_atk = int(atk_item.split(' / ')[0])
        else:
            current_atk = 0
        # ATK is capped at 250, so max is 100%
        scores['atk_pct'] = min((current_atk / 250 * 100), 100) if current_atk > 0 else 0
        
        # Haste - binary: 30% item haste (70% buff + 30% item = 100% total) = on, otherwise off
        haste = char_data.get('stats', {}).get('haste', 0)
        if isinstance(haste, (int, float)):
            # Binary: 30% item haste means 100% total (70% buff + 30% item) = on, otherwise off
            scores['haste_pct'] = 100.0 if haste >= 30 else 0.0
            scores['haste_value'] = haste  # Store actual item haste value for display
        else:
            scores['haste_pct'] = 0.0
            scores['haste_value'] = 0
    else:
        scores['atk_pct'] = None
        scores['haste_pct'] = None
    
    # Focus scores - calculate % of best focus in each category
    # Special handling for Warriors - focus score is based on having specific items + haste
    if char_class == 'Warrior':
        char_haste = char_data.get('stats', {}).get('haste', 0)
        warrior_focus_scores, warrior_items = check_warrior_focus_items(char_inventory or [], char_haste)
        # For Warriors, each focus item has its own score (ATK, Haste, Darkblade, Raex Chest)
        focus_scores = warrior_focus_scores
        # Add ATK to focus_scores (ATK is calculated in scores['atk_pct'])
        if scores.get('atk_pct') is not None:
            focus_scores['ATK'] = scores['atk_pct']
        # Store item status for display
        scores['focus_items'] = warrior_items
    elif char_class == 'Paladin':
        # Paladins have Shield of Strife + spell focuses
        pal_sk_focus_score, pal_sk_items = check_paladin_sk_focus_items(char_inventory or [])
        focus_scores = {'Shield of Strife': pal_sk_focus_score}
        scores['focus_items'] = pal_sk_items
        # Add other focus scores for Paladins (spell focuses)
        for category, best_pct in best_focii.items():
            if category == 'Spell Damage':
                # Paladins don't need spell damage
                focus_scores[category] = 0
            elif category == 'Healing Enhancement':
                # Track Healing Enhancement for Paladins
                char_pct = char_focii.get(category, 0)
                if best_pct > 0:
                    focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                else:
                    focus_scores[category] = 0
        # Beneficial Spell Haste for display (e.g. Haste of Mithaniel from item 26983)
        if char_spell_haste_cats is not None:
            bene_pct = max(char_spell_haste_cats.get('Bene', 0), char_spell_haste_cats.get('All', 0))
            best_haste = best_focii.get('Spell Haste', 33.0)
            if best_haste > 0:
                focus_scores['Beneficial Spell Haste'] = (bene_pct / best_haste * 100) if bene_pct > 0 else 0
            else:
                focus_scores['Beneficial Spell Haste'] = 0
        else:
            focus_scores['Beneficial Spell Haste'] = 0
        # Spell Mana Efficiency - Paladin: beneficial
        best_mana_eff = max((best_mana_by_cat or {}).values()) if best_mana_by_cat else best_focii.get('Spell Mana Efficiency', 40.0)
        focus_scores['Spell Mana Efficiency'] = calculate_spell_mana_efficiency_score(
            char_mana_efficiency_cats or {}, 'Paladin', best_mana_eff, best_mana_by_cat
        )
    elif char_class == 'Shadow Knight':
        pal_sk_focus_score, pal_sk_items = check_paladin_sk_focus_items(char_inventory or [])
        focus_scores = {'Shield of Strife': pal_sk_focus_score}
        if scores.get('atk_pct') is not None:
            focus_scores['ATK'] = scores['atk_pct']
        char_haste = char_data.get('stats', {}).get('haste', 0)
        focus_scores['Haste'] = 100.0 if (isinstance(char_haste, (int, float)) and char_haste >= 30) else 0.0
        # Spell Mana Efficiency - weighted by class (SHD: Det only)
        best_mana_eff = max((best_mana_by_cat or {}).values()) if best_mana_by_cat else best_focii.get('Spell Mana Efficiency', 40.0)
        focus_scores['Spell Mana Efficiency'] = calculate_spell_mana_efficiency_score(
            char_mana_efficiency_cats or {}, 'Shadow Knight', best_mana_eff, best_mana_by_cat
        )
        scores['focus_items'] = pal_sk_items
    elif char_class == 'Enchanter':
        enchanter_focus_score, enchanter_items = check_enchanter_focus_items(char_inventory or [])
        focus_scores = {'Serpent of Vindication': enchanter_focus_score}
        scores['focus_items'] = enchanter_items
        # Spell Damage (Magic)
        best_dmg = best_focii.get('Spell Damage', 35.0)
        char_pct = char_damage_focii.get('Magic', 0)
        focus_scores['Spell Damage'] = (char_pct / best_dmg * 100) if best_dmg > 0 and char_pct > 0 else 0
        # Spell Mana Efficiency: weighted by category (Det, Bene; Sanguine/self-only not weighted)
        best_mana_eff = max((best_mana_by_cat or {}).values()) if best_mana_by_cat else best_focii.get('Spell Mana Efficiency', 40.0)
        focus_scores['Spell Mana Efficiency'] = calculate_spell_mana_efficiency_score(
            char_mana_efficiency_cats or {}, 'Enchanter', best_mana_eff, best_mana_by_cat
        ) if char_mana_efficiency_cats else 0
        # Spell Haste: consider Beneficial and Detrimental separately (Enchanter uses both).
        # All counts for both: effective best = max(cat_best, All_best).
        if char_spell_haste_cats and best_haste_by_cat:
            best_all_haste = best_haste_by_cat.get('All', 0)
            best_bene = max(best_haste_by_cat.get('Bene', 0), best_all_haste) or best_focii.get('Spell Haste', 33.0)
            bene_pct = max(char_spell_haste_cats.get('Bene', 0), char_spell_haste_cats.get('All', 0))
            focus_scores['Beneficial Spell Haste'] = (bene_pct / best_bene * 100) if best_bene > 0 and bene_pct > 0 else 0
            best_det = max(best_haste_by_cat.get('Det', 0), best_all_haste) or best_focii.get('Spell Haste', 33.0)
            det_pct = max(char_spell_haste_cats.get('Det', 0), char_spell_haste_cats.get('All', 0))
            focus_scores['Detrimental Spell Haste'] = (det_pct / best_det * 100) if best_det > 0 and det_pct > 0 else 0
            # Composite for focus_overall_pct (CLASS_FOCUS_PRIORITIES has 'Spell Haste')
            focus_scores['Spell Haste'] = 0.5 * focus_scores.get('Beneficial Spell Haste', 0) + 0.5 * focus_scores.get('Detrimental Spell Haste', 0)
        else:
            char_pct = char_focii.get('Spell Haste', 0)
            best_pct = best_focii.get('Spell Haste', 33.0)
            focus_scores['Spell Haste'] = (char_pct / best_pct * 100) if best_pct > 0 and char_pct > 0 else 0
        # Spell Range Extension
        best_range = best_focii.get('Spell Range Extension', 20.0)
        focus_scores['Spell Range Extension'] = (char_focii.get('Spell Range Extension', 0) / best_range * 100) if best_range > 0 and char_focii.get('Spell Range Extension', 0) > 0 else 0
        # Buff Spell Duration and Detrimental Spell Duration (by category)
        if char_duration_cats and best_duration_by_cat:
            best_buff = max(best_duration_by_cat.get('Bene', 0), best_duration_by_cat.get('All', 0))
            eff_buff = max(char_duration_cats.get('Bene', 0), char_duration_cats.get('All', 0))
            focus_scores['Buff Spell Duration'] = (eff_buff / best_buff * 100) if best_buff > 0 and eff_buff > 0 else 0
            best_det_dur = max(best_duration_by_cat.get('Det', 0), best_duration_by_cat.get('All', 0))
            eff_det_dur = max(char_duration_cats.get('Det', 0), char_duration_cats.get('All', 0))
            focus_scores['Detrimental Spell Duration'] = (eff_det_dur / best_det_dur * 100) if best_det_dur > 0 and eff_det_dur > 0 else 0
        else:
            focus_scores['Buff Spell Duration'] = 0
            focus_scores['Detrimental Spell Duration'] = 0
    elif char_class == 'Bard' and bard_instrument_data:
        bard_focus_scores, bard_items_detail = check_bard_instrument_focus(char_inventory or [], bard_instrument_data)
        focus_scores = dict(bard_focus_scores)
        scores['focus_items'] = bard_items_detail
        if scores.get('atk_pct') is not None:
            focus_scores['ATK'] = scores['atk_pct']
        if char_data.get('stats', {}).get('haste', 0) is not None:
            char_haste = char_data.get('stats', {}).get('haste', 0)
            focus_scores['Haste'] = 100.0 if (isinstance(char_haste, (int, float)) and char_haste >= 30) else 0.0
        else:
            focus_scores['Haste'] = 0.0
    elif char_class == 'Bard':
        focus_scores = {'Brass': 0, 'Percussion': 0, 'Singing': 0, 'Strings': 0, 'Wind': 0, 'Haste': 0.0}
        if scores.get('atk_pct') is not None:
            focus_scores['ATK'] = scores['atk_pct']
        if char_data.get('stats', {}).get('haste', 0) is not None:
            char_haste = char_data.get('stats', {}).get('haste', 0)
            focus_scores['Haste'] = 100.0 if (isinstance(char_haste, (int, float)) and char_haste >= 30) else 0.0
        scores['focus_items'] = {}
    else:
        focus_scores = {}
        for category, best_pct in best_focii.items():
            if category == 'Spell Damage':
                # For spell damage, calculate class-specific damage type scores
                if char_class in CLASS_DAMAGE_TYPES:
                    damage_types = CLASS_DAMAGE_TYPES[char_class]
                    best_damage_score = 0
                    # Shaman: store best-in-each per type (DoT 1.0, Cold 0.2 weight ratio)
                    if char_class == 'Shaman':
                        for damage_type in damage_types:
                            char_pct = char_damage_focii.get(damage_type, 0)
                            if best_pct > 0:
                                damage_score = (char_pct / best_pct * 100) if char_pct > 0 else 0
                            else:
                                damage_score = 0
                            focus_scores[f'Spell Damage ({damage_type})'] = damage_score
                            best_damage_score = max(best_damage_score, damage_score)
                        # Composite: DoT 1.0, Cold 0.2 => 5/6 DoT, 1/6 Cold
                        focus_scores[category] = (
                            (5/6) * focus_scores.get('Spell Damage (DoT)', 0) +
                            (1/6) * focus_scores.get('Spell Damage (Cold)', 0)
                        )
                    else:
                        for damage_type in damage_types:
                            if damage_type == 'DoT':
                                char_pct = char_damage_focii.get('DoT', 0)
                            else:
                                # "All" (instant) applies to non-DoT subcategories
                                char_pct = max(char_damage_focii.get(damage_type, 0), char_damage_focii.get('All', 0))
                            if best_pct > 0:
                                damage_score = (char_pct / best_pct * 100) if char_pct > 0 else 0
                            else:
                                damage_score = 0
                            focus_scores[f'Spell Damage ({damage_type})'] = damage_score
                            best_damage_score = max(best_damage_score, damage_score)
                        # "All" only applies to non-DoT types; don't add for DoT-only classes (e.g. Necro)
                        if any(dt != 'DoT' for dt in damage_types):
                            all_pct = char_damage_focii.get('All', 0)
                            if best_pct > 0:
                                all_score = (all_pct / best_pct * 100) if all_pct > 0 else 0
                                best_damage_score = max(best_damage_score, all_score)
                        focus_scores[category] = best_damage_score
                else:
                    # Non-caster classes don't need spell damage
                    focus_scores[category] = 0
            elif category in ['Buff Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration']:
                # Duration: All counts for both Buff (Bene) and Detrimental (Det)
                if char_duration_cats is not None:
                    if category == 'Buff Spell Duration':
                        effective_pct = max(char_duration_cats.get('Bene', 0), char_duration_cats.get('All', 0))
                        best_dur = max(best_focii.get('Buff Spell Duration', 25.0), best_focii.get('All Spell Duration', 15.0))
                    elif category == 'Detrimental Spell Duration':
                        effective_pct = max(char_duration_cats.get('Det', 0), char_duration_cats.get('All', 0))
                        best_dur = max(best_focii.get('Detrimental Spell Duration', 25.0), best_focii.get('All Spell Duration', 15.0))
                    else:  # All Spell Duration
                        effective_pct = char_duration_cats.get('All', 0)
                        best_dur = best_focii.get('All Spell Duration', 15.0)
                    if best_dur > 0:
                        focus_scores[category] = (effective_pct / best_dur * 100) if effective_pct > 0 else 0
                    else:
                        focus_scores[category] = 0
                else:
                    char_pct = char_focii.get(category, 0)
                    if best_pct > 0:
                        focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                    else:
                        focus_scores[category] = 0
            elif category == 'Spell Mana Efficiency':
                # Weighted by class (Bene/Det/Nuke separately; All counts for all)
                best_mana_eff = max((best_mana_by_cat or {}).values()) if best_mana_by_cat else best_focii.get('Spell Mana Efficiency', 40.0)
                focus_scores[category] = calculate_spell_mana_efficiency_score(
                    char_mana_efficiency_cats or {}, char_class, best_mana_eff, best_mana_by_cat
                ) if char_mana_efficiency_cats else (
                    (char_focii.get(category, 0) / best_pct * 100) if best_pct > 0 and char_focii.get(category, 0) > 0 else 0
                )
            elif category == 'Spell Haste' and char_class == 'Magician' and char_spell_haste_cats and best_haste_by_cat:
                # Magician: score Beneficial and Detrimental Spell Haste separately (like Enchanter)
                best_all_haste = best_haste_by_cat.get('All', 0)
                best_bene = max(best_haste_by_cat.get('Bene', 0), best_all_haste) or best_focii.get('Spell Haste', 33.0)
                bene_pct = max(char_spell_haste_cats.get('Bene', 0), char_spell_haste_cats.get('All', 0))
                focus_scores['Beneficial Spell Haste'] = (bene_pct / best_bene * 100) if best_bene > 0 and bene_pct > 0 else 0
                best_det = max(best_haste_by_cat.get('Det', 0), best_all_haste) or best_focii.get('Spell Haste', 33.0)
                det_pct = max(char_spell_haste_cats.get('Det', 0), char_spell_haste_cats.get('All', 0))
                focus_scores['Detrimental Spell Haste'] = (det_pct / best_det * 100) if best_det > 0 and det_pct > 0 else 0
                focus_scores['Spell Haste'] = 0.5 * focus_scores.get('Beneficial Spell Haste', 0) + 0.5 * focus_scores.get('Detrimental Spell Haste', 0)
            else:
                # Other categories work normally
                char_pct = char_focii.get(category, 0)
                if best_pct > 0:
                    focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                else:
                    focus_scores[category] = 0
        
        # Beneficial / Detrimental Spell Haste: for classes in the generic path (Cleric, Shaman, Druid, Beastlord, etc.)
        # best_focii only has 'Spell Haste', not these subcategories. Populate from char_spell_haste_cats so the
        # UI shows the correct % when the character has e.g. 30% Beneficial Spell Haste from an item.
        if char_spell_haste_cats and best_haste_by_cat:
            if 'Beneficial Spell Haste' not in focus_scores:
                best_bene = max(best_haste_by_cat.get('Bene', 0), best_haste_by_cat.get('All', 0)) or best_focii.get('Spell Haste', 33.0)
                bene_pct = max(char_spell_haste_cats.get('Bene', 0), char_spell_haste_cats.get('All', 0))
                focus_scores['Beneficial Spell Haste'] = (bene_pct / best_bene * 100) if best_bene > 0 and bene_pct > 0 else 0
            if 'Detrimental Spell Haste' not in focus_scores:
                best_det = max(best_haste_by_cat.get('Det', 0), best_haste_by_cat.get('All', 0)) or best_focii.get('Spell Haste', 33.0)
                det_pct = max(char_spell_haste_cats.get('Det', 0), char_spell_haste_cats.get('All', 0))
                focus_scores['Detrimental Spell Haste'] = (det_pct / best_det * 100) if best_det > 0 and det_pct > 0 else 0
        
        # Add haste binary check for all ATK classes (mnk, rog, war, pal, shd, bst, brd, rng)
        # Binary: 30% item haste (70% buff + 30% item = 100% total) = 100%, otherwise 0%
        if char_class in CLASSES_NEED_ATK:
            char_haste = char_data.get('stats', {}).get('haste', 0)
            if isinstance(char_haste, (int, float)):
                has_max_haste = (char_haste >= 30)
                focus_scores['Haste'] = 100.0 if has_max_haste else 0.0
            else:
                focus_scores['Haste'] = 0.0
        # Shaman: Time's Antithesis (item 24699), same weight as Serpent of Vindication for Enchanter
        if char_class == 'Shaman':
            shaman_focus_score, shaman_items = check_shaman_focus_items(char_inventory or [])
            focus_scores["Time's Antithesis"] = shaman_focus_score
            scores['focus_items'] = shaman_items
        # Pet Power: Magician, Beastlord, Necromancer; checked from full inventory (including bags)
        if char_class in ('Magician', 'Beastlord', 'Necromancer'):
            best_pp = (best_pet_power_by_class or {}).get(char_class, 25)
            char_pp = get_char_pet_power(char_inventory or [])
            focus_scores['Pet Power'] = (char_pp / best_pp * 100) if best_pp > 0 and char_pp > 0 else 0
    
    # FT (Flowing Thought) - tracked focus for all classes with mana, cap 15
    if char_class in CLASSES_WITH_MANA and scores.get('ft_capped') is not None:
        focus_scores['FT'] = 100.0 if scores.get('ft_capped') else (scores.get('ft_pct') or 0)
    
    scores['focus_scores'] = focus_scores
    
    # Build focus_details for display: per-category rows for Mana Efficiency (and optionally Haste/Duration)
    # so the UI can show Detrimental / Beneficial / Self-only separately with correct raw and score %
    focus_details = {}
    if char_mana_efficiency_cats and best_mana_by_cat:
        weights = SPELL_MANA_EFFICIENCY_WEIGHTS.get(char_class, {})
        all_pct = char_mana_efficiency_cats.get('All', 0)
        cat_labels = {'Det': 'Detrimental', 'Bene': 'Beneficial', 'Nuke': 'Nuke', 'Sanguine': 'Self only'}
        rows = []
        for cat in ('Det', 'Bene', 'Nuke', 'Sanguine'):
            raw = max(char_mana_efficiency_cats.get(cat, 0), all_pct)
            best = best_mana_by_cat.get(cat, 0)
            score_pct = (raw / best * 100) if best > 0 and raw > 0 else 0
            weight_share = weights.get(cat, 0)
            rows.append({
                'label': cat_labels.get(cat, cat),
                'cat': cat,
                'raw': round(raw, 1),
                'best': round(best, 1),
                'score_pct': round(score_pct, 1),
                'weight_share': weight_share
            })
        focus_details['Spell Mana Efficiency'] = rows
    scores['focus_details'] = focus_details if focus_details else None
    
    # Store damage-specific focii for display
    scores['damage_focii'] = char_damage_focii
    
    # Calculate overall focus score based on class priorities
    if char_class == 'Warrior':
        # For Warriors, calculate weighted average of Darkblade, Raex Chest, and Haste (each weight 1.0)
        total_score = 0.0
        total_weight = 0.0
        for focus_name in ['Darkblade', 'Raex Chest', 'Haste']:
            if focus_name in focus_scores:
                total_score += focus_scores[focus_name] * 1.0
                total_weight += 1.0
        scores['focus_overall_pct'] = (total_score / total_weight) if total_weight > 0 else 0.0
    elif char_class == 'Paladin':
        # For Paladins, calculate weighted average for display: Shield of Strife (2.0), Beneficial Spell Haste (0.75), Healing Enhancement (0.5)
        # Note: The actual weighted calculation happens in calculate_overall_score_with_weights
        total_score = 0
        total_weight = 0
        if 'Shield of Strife' in focus_scores:
            total_score += focus_scores['Shield of Strife'] * 2.0
            total_weight += 2.0
        if 'Healing Enhancement' in focus_scores:
            total_score += focus_scores['Healing Enhancement'] * 0.5
            total_weight += 0.5
        # Beneficial Spell Haste (0.75 weight) - add if available
        if char_spell_haste_cats and 'Bene' in char_spell_haste_cats:
            bene_haste_pct = char_spell_haste_cats.get('Bene', 0)
            best_haste = best_focii.get('Spell Haste', 33.0)
            if best_haste > 0:
                bene_haste_score = (bene_haste_pct / best_haste * 100) if bene_haste_pct > 0 else 0
                total_score += bene_haste_score * 0.75
                total_weight += 0.75
        scores['focus_overall_pct'] = (total_score / total_weight) if total_weight > 0 else 0
    elif char_class == 'Shadow Knight':
        # Weighted average: Shield of Strife 2.0, Haste 0.75, ATK 0.75, Spell Mana Efficiency 0.5, FT 1.0
        total_score = 0.0
        total_weight = 0.0
        for name, w in [('Shield of Strife', 2.0), ('Haste', 0.75), ('ATK', 0.75), ('Spell Mana Efficiency', 0.5), ('FT', 1.0)]:
            s = focus_scores.get(name, 0)
            total_score += s * w
            total_weight += w
        scores['focus_overall_pct'] = (total_score / total_weight) if total_weight > 0 else 0
    elif char_class in CLASS_FOCUS_PRIORITIES:
        priority_cats = CLASS_FOCUS_PRIORITIES[char_class]
        # Weighted average of priority focus categories
        total_score = 0
        total_weight = 0
        added_shaman_detrimental = False
        for i, cat in enumerate(priority_cats):
            # Shaman detrimental = DoT 1.0, Cold 0.2 => 5/6 DoT, 1/6 Cold (one composite, weight 5)
            if char_class == 'Shaman' and cat.startswith('Spell Damage ('):
                if not added_shaman_detrimental:
                    det_composite = (
                        (5/6) * focus_scores.get('Spell Damage (DoT)', 0) +
                        (1/6) * focus_scores.get('Spell Damage (Cold)', 0)
                    )
                    total_score += det_composite * 5
                    total_weight += 5
                    added_shaman_detrimental = True
                continue
            weight = len(priority_cats) - i  # Higher weight for higher priority
            # Handle spell damage with damage type (use per-type score when available)
            if cat.startswith('Spell Damage ('):
                score = focus_scores.get(cat, focus_scores.get('Spell Damage', 0))
            else:
                score = focus_scores.get(cat, 0)
            total_score += score * weight
            total_weight += weight
        
        # For ATK classes, also include Haste in the focus score
        if char_class in CLASSES_NEED_ATK and 'Haste' in focus_scores:
            haste_score = focus_scores.get('Haste', 0)
            # Add Haste with same weight as lowest priority (weight = 1)
            total_score += haste_score * 1
            total_weight += 1
        # Shaman: include Time's Antithesis (weight 2.0, same as Serpent for Enchanter)
        if char_class == 'Shaman' and "Time's Antithesis" in focus_scores:
            total_score += focus_scores["Time's Antithesis"] * 2.0
            total_weight += 2.0
        
        scores['focus_overall_pct'] = (total_score / total_weight) if total_weight > 0 else 0
    else:
        # For classes without specific priorities, average all focus scores (includes Haste for ATK classes)
        if focus_scores:
            scores['focus_overall_pct'] = sum(focus_scores.values()) / len(focus_scores)
        else:
            scores['focus_overall_pct'] = 0
    
    return scores

# Class-specific weight configuration
# This defines how much each stat/focus contributes to the overall score per class
CLASS_WEIGHTS = {
    # Warrior/Monk - Tank melees (Warrior: HP 3x, AC 2x, Resists 2x; no mana)
    'Warrior': {
        'hp_pct': 3.0,
        'mana_pct': 0.0,
        'ac_pct': 2.0,
        'atk_pct': 0.0,  # Moved to focus
        'haste_pct': 0.0,  # Moved to focus
        'resists_pct': 2.0,
        'focus': {
            'ATK': 1.0,  # ATK moved to focus
            'Haste': 1.0,  # Item haste (30% item = 100% total) moved to focus
            'Darkblade': 1.0,  # Darkblade of the Warlord
            'Raex Chest': 1.0,  # Raex's Chestplate of Destruction
        }
    },
    'Monk': {
        'hp_pct': 1.0,
        'mana_pct': 0.0,
        'ac_pct': 0.2,  # Small contribution from AC (all classes get small AC weight)
        'atk_pct': 0.0,  # Moved to focus
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            'ATK': 1.0,  # ATK moved to focus
            'Haste': 1.0,  # Item haste
        }
    },
    
    # Rogue - DPS melee
    'Rogue': {
        'hp_pct': 1.0,
        'mana_pct': 0.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,  # Moved to focus
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            'ATK': 1.0,  # ATK moved to focus
            'Haste': 1.0,  # Item haste
        }
    },
    
    # Shadow Knight - Tank hybrid: HP 3x, Mana 1x, AC 2x, Resists 2x
    'Shadow Knight': {
        'hp_pct': 3.0,
        'mana_pct': 1.0,
        'ac_pct': 2.0,
        'atk_pct': 0.0,   # Moved to focus
        'haste_pct': 0.0, # Moved to focus
        'resists_pct': 2.0,
        'focus': {
            'Haste': 0.75,
            'ATK': 0.75,
            'Spell Mana Efficiency': 0.5,  # detrimental mana preservation
            'Shield of Strife': 2.0,
            'FT': 1.0,
        }
    },
    'Paladin': {
        'hp_pct': 3.0,
        'mana_pct': 1.0,
        'ac_pct': 2.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,  # Moved to focus (weight 0.5)
        'resists_pct': 2.0,
        'focus': {
            'ATK': 0.5,
            'FT': 1.0,
            'Haste': 0.5,
            'Beneficial Spell Haste': 0.75,
            'Healing Enhancement': 0.5,
            'Shield of Strife': 2.0,
            'Spell Mana Efficiency': 0.5,  # beneficial (Bene)
        }
    },
    
    # Wizard - Pure caster
    'Wizard': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'Fire': 1.0, 'Cold': 1.0, 'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Detrimental Spell Haste': 1.0,  # Required
            'Detrimental Spell Duration': 0.75,
            'Spell Range Extension': 0.5,  # Lower weight for all casters
        }
    },
    
    # Cleric - Healer
    'Cleric': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'Magic': 0.5},
            'Healing Enhancement': 2.0,
            'Spell Mana Efficiency': 1.0,
            'Spell Range Extension': 0.5,  # Lower weight for all casters
            'Buff Spell Duration': 1.0,
            'Beneficial Spell Haste': 2.0,  # Class-defining for priests (spot heals)
        }
    },
    
    # Magician - Pet caster
    'Magician': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'Fire': 1.0, 'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Detrimental Spell Haste': 1.0,
            'Detrimental Spell Duration': 0.75,
            'Spell Range Extension': 0.5,  # Lower weight for all casters
            'Pet Power': 3.0,
        }
    },
    
    # Necromancer - DoT caster
    'Necromancer': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'DoT': 1.0},
            'Spell Mana Efficiency': 1.0,  # det mana
            'Detrimental Spell Duration': 1.0,  # det or all e
            'Detrimental Spell Haste': 1.0,  # det spell h
            'Spell Range Extension': 0.5,  # Lower weight for all casters
            'Pet Power': 2.0,
        }
    },
    
    # Shaman - Hybrid healer/DoT
    'Shaman': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            # Detrimental focus: DoT 1.0, Cold 0.2 (best in each)
            'Spell Damage': {'DoT': 1.0, 'Cold': 0.2},
            'Healing Enhancement': 1.0,
            'Spell Mana Efficiency': 1.0,
            'Beneficial Spell Haste': 2.0,  # Class-defining for priests (spot heals)
            'Detrimental Spell Haste': 0.75,
            'Buff Spell Duration': 1.0,  # Bene exter
            'Detrimental Spell Duration': 1.0,  # DoT duration focus (All duration applies to both, no separate weight)
            'Spell Range Extension': 0.5,  # Lower weight for all casters
            "Time's Antithesis": 2.0,  # Item 24699, same weight as Serpent of Vindication for Enchanter
        }
    },
    
    # Enchanter - Support caster
    'Enchanter': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Buff Spell Duration': 1.0,  # Bene exter
            'Detrimental Spell Duration': 1.0,  # Det duration (required)
            'Detrimental Spell Haste': 1.0,
            'Spell Range Extension': 0.75,
            'Serpent of Vindication': 2.0,
        }
    },
    
    # Beastlord - Hybrid melee/caster (HP 3x, Mana 1x, AC 2x, Resists 2x)
    'Beastlord': {
        'hp_pct': 3.0,
        'mana_pct': 1.0,
        'ac_pct': 2.0,
        'atk_pct': 0.0,
        'haste_pct': 1.0,
        'resists_pct': 2.0,
        'focus': {
            'ATK': 1.0,
            'FT': 1.0,
            'Spell Damage': {'Cold': 0.5},
            'Healing Enhancement': 0.75,
            'Spell Mana Efficiency': 1.0,
            'Buff Spell Duration': 1.0,
            'Beneficial Spell Haste': 0.75,
            'Detrimental Spell Haste': 0.75,
            'Pet Power': 3.0,
        }
    },

    # Druid - Hybrid healer/caster
    'Druid': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,  # Small contribution from AC for all classes
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'FT': 4.0,
            'Spell Damage': {'Fire': 1.0, 'Cold': 1.0},
            'Healing Enhancement': 1.0,
            'Spell Mana Efficiency': 1.0,
            'Beneficial Spell Haste': 2.0,  # Class-defining for priests (spot heals)
            'Detrimental Spell Haste': 0.75,
            'Detrimental Spell Duration': 0.5,  # det or all e
            'Buff Spell Duration': 1.0,  # Bene exter
            'Spell Range Extension': 0.5,  # Lower weight for all casters
        }
    },
    
    # Ranger - Hybrid melee/caster (HP 3x, Mana 1x, AC 2x, Resists 2x)
    'Ranger': {
        'hp_pct': 3.0,
        'mana_pct': 1.0,
        'ac_pct': 2.0,
        'atk_pct': 0.0,
        'haste_pct': 1.0,
        'resists_pct': 2.0,
        'focus': {
            'ATK': 1.0,
            'FT': 1.0,
        }
    },
    
    # Bard - Support hybrid (instrument mods cap 390%: 100 base + 60 AA + 230 items)
    # target_focus 0.40 so instruments+ATK+Haste+FT share ~35% focus
    'Bard': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.2,
        'atk_pct': 0.0,  # Moved to focus
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'target_focus': 0.40,
        'focus': {
            'ATK': 4.0,
            'FT': 4.0,
            'Haste': 4.0,
            'Brass': 4.0,
            'Percussion': 4.0,
            'Singing': 4.0,
            'Strings': 4.0,
            'Wind': 4.0,
        }
    },
}

# Ensure all classes have all simple focus keys (with 0 where not used) so UI can adjust from zero
_all_simple_focus_keys = set()
for _w in CLASS_WEIGHTS.values():
    if 'focus' in _w:
        for _k, _v in _w['focus'].items():
            if not isinstance(_v, dict):
                _all_simple_focus_keys.add(_k)
for _w in CLASS_WEIGHTS.values():
    if 'focus' in _w:
        for _k in _all_simple_focus_keys:
            if _k not in _w['focus']:
                _w['focus'][_k] = 0

def normalize_class_weights(weights_config):
    """
    Normalize class weights so that:
    - Stats (HP, AC, Mana where applied, Resists) sum to 65% (0.65)
    - Focus (ATK, FT, Haste, spell focuses) sum to 35% (0.35)
    Total = 100%. This yields Stat Total out of 65 points and Focus Total out of 35 points.
    ATK, FT, and Haste are part of focus weight. Resists weight is TOTAL across all 5 resists.
    """
    # Stat weights from config are relative (e.g. HP 3, Mana 1, AC 2, Resists 2); scaled so stat total = 65%
    TARGET_FOCUS = 0.35  # Focus gets 35% (35 points out of 100)

    # Per-class override (e.g. Bard 0.40)
    focus_target = weights_config.get('target_focus')
    if focus_target is None:
        focus_target = TARGET_FOCUS
    focus_target = max(0.0, min(1.0, focus_target))
    stat_total_target = 1.0 - focus_target

    # Check which stats are applicable
    has_mana = weights_config.get('mana_pct', 0) > 0
    has_ac = weights_config.get('ac_pct', 0) > 0

    # Use config as relative weights; scale so they sum to stat_total_target
    hp_w = weights_config.get('hp_pct', 0.0)
    mana_w = weights_config.get('mana_pct', 0.0)
    ac_w = weights_config.get('ac_pct', 0.0)
    resists_w = weights_config.get('resists_pct', 0.0)
    stat_sum = hp_w + (mana_w if has_mana else 0.0) + (ac_w if has_ac else 0.0) + resists_w
    scale_stat = (stat_total_target / stat_sum) if stat_sum > 0 else 0.0
    hp_target = hp_w * scale_stat
    resists_target = resists_w * scale_stat
    mana_target = (mana_w * scale_stat) if has_mana else 0.0
    ac_target = (ac_w * scale_stat) if has_ac else 0.0
    
    # Calculate focus weight components from config
    # ATK, FT, Haste and spell focuses all in focus dict; one scale for ~35% total
    focus_weights = weights_config.get('focus', {})
    atk_weight_raw = 0.0
    haste_weight_raw = 0.0
    total_focus_components = 0.0
    if focus_weights:
        for focus_cat, focus_value in focus_weights.items():
            if focus_cat == 'ATK':
                atk_weight_raw = focus_value if isinstance(focus_value, (int, float)) else 0.0
            elif focus_cat == 'Haste':
                haste_weight_raw = focus_value if isinstance(focus_value, (int, float)) else 0.0
            elif isinstance(focus_value, dict):
                total_focus_components += sum(focus_value.values())
            elif isinstance(focus_value, (int, float)):
                total_focus_components += focus_value  # FT and other scalar foci
    if haste_weight_raw == 0.0:
        haste_weight_raw = weights_config.get('haste_pct', 0.0)
    total_focus_components += atk_weight_raw + haste_weight_raw
    
    focus_scale = (focus_target / total_focus_components) if total_focus_components > 0 else 0.0
    
    # Build normalized weights
    normalized = {}
    normalized['hp_pct'] = hp_target
    normalized['resists_pct'] = resists_target
    normalized['mana_pct'] = mana_target
    normalized['ac_pct'] = ac_target
    
    normalized['atk_pct'] = 0.0
    normalized['haste_pct'] = 0.0
    
    # Normalize focus weights (ATK, FT, Haste, spell foci - same scale)
    normalized['focus'] = {}
    if focus_weights and focus_scale > 0:
        for focus_cat, focus_value in focus_weights.items():
            if isinstance(focus_value, dict):
                # For dict values (like Spell Damage with damage types), include all entries
                normalized['focus'][focus_cat] = {
                    k: v * focus_scale for k, v in focus_value.items()
                }
            else:
                # Include all weights (including 0) so UI can adjust from zero up
                if isinstance(focus_value, (int, float)) and focus_value >= 0:
                    normalized['focus'][focus_cat] = focus_value * focus_scale
    
    # Store ATK and Haste as focus components (if not already in normalized focus dict)
    # Include them if they're > 0 (they will be included when changed from 0 to non-zero)
    if 'ATK' not in normalized['focus']:
        if atk_weight_raw > 0:
            normalized['focus']['ATK'] = atk_weight_raw * focus_scale
        elif 'ATK' in focus_weights:
            # Check if ATK weight is now > 0 (for dynamic reweighting)
            atk_config_value = focus_weights.get('ATK', 0.0)
            if isinstance(atk_config_value, (int, float)) and atk_config_value > 0:
                normalized['focus']['ATK'] = atk_config_value * focus_scale
    
    if 'Haste' not in normalized['focus']:
        if haste_weight_raw > 0:
            normalized['focus']['Haste'] = haste_weight_raw * focus_scale
        elif 'Haste' in focus_weights:
            # Check if Haste weight is now > 0 (for dynamic reweighting)
            haste_config_value = focus_weights.get('Haste', 0.0)
            if isinstance(haste_config_value, (int, float)) and haste_config_value > 0:
                normalized['focus']['Haste'] = haste_config_value * focus_scale
    
    return normalized

def calculate_resist_score(resist_value):
    """
    Calculate resist score with progressive taper curve:
    - L = 220 (start taper)
    - H = 500 (hard-cap point)
    - r = 0.35 (post-cap marginal credit)
    - p = 1.2 (controls how "progressive" the taper is)
    - t = (x - L) / (H - L) = (x - 220) / 280
    
    S(x) = {
        x,                                    if x <= 220
        220 + (x - 220)(r + (1 - r)(1 - t)^p), if 220 < x < 500
        318 + r(x - 500),                      if x >= 500
    }
    
    Score percentage = (S(x) / S(500)) * 100, where S(500) = 318
    
    Returns: (score_percentage_with_curve, weight_always_1.0)
    """
    if resist_value <= 0:
        return (0.0, 1.0)
    
    L = 220.0  # Start taper
    H = 500.0  # Hard-cap point
    r = 0.35   # Post-cap marginal credit
    p = 1.2    # Progressive taper control
    
    x = float(resist_value)
    
    if x <= L:
        # No taper: S(x) = x
        S_x = x
    elif x < H:
        # Progressive taper: S(x) = 220 + (x - 220)(r + (1 - r)(1 - t)^p)
        t = (x - L) / (H - L)  # t = (x - 220) / 280
        S_x = L + (x - L) * (r + (1 - r) * ((1 - t) ** p))
    else:
        # Post-cap: S(x) = 318 + r(x - 500)
        S_500 = L + r * (H - L)  # = 220 + 0.35 * 280 = 318
        S_x = S_500 + r * (x - H)
    
    # Normalize: S(500) = 318, so score percentage = (S(x) / 318) * 100
    # But cap at 100% to match HP/AC normalization
    S_500 = L + r * (H - L)  # = 318
    score = min((S_x / S_500) * 100.0, 100.0) if S_500 > 0 else 0.0
    
    # Weight is always 1.0
    weight = 1.0
    
    return (score, weight)

def calculate_overall_score_with_weights(char_class, scores, char_damage_focii, focus_scores, best_focii, class_max_values=None, char_spell_haste_cats=None, char_duration_cats=None, char_mana_efficiency_cats=None, char=None):
    """Calculate overall score using class-specific weights with conversion rates"""
    raw_weights = CLASS_WEIGHTS.get(char_class, {})
    # Normalize weights to target percentages
    weights_config = normalize_class_weights(raw_weights)
    class_max_values = class_max_values or {}
    
    if not weights_config:
        # Fallback to default weights if class not found
        return calculate_overall_score_fallback(scores, char_class)
    
    # Don't normalize again - weights_config is already normalized
    
    total_score = 0.0
    total_weight = 0.0
    
    # For Warriors, Paladins, Shadow Knights: 5 HP = 1 AC
    # Convert both to a common unit for comparison
    if char_class in ['Warrior', 'Paladin', 'Shadow Knight']:
        max_hp = class_max_values.get('max_hp', 1)
        max_ac = class_max_values.get('max_ac', 1)
        
        hp_value = scores.get('hp', 0)
        ac_value = scores.get('ac', 0) if scores.get('ac') is not None else 0
        
        # Convert HP to AC-equivalent: HP/5 = AC equivalent
        # Find max AC-equivalent from HP: max_hp/5
        max_hp_ac_equivalent = max_hp / 5.0 if max_hp > 0 else 1
        # Use the larger of max_ac or max_hp_ac_equivalent as the normalization base
        max_combined = max(max_ac, max_hp_ac_equivalent) if max_ac > 0 else max_hp_ac_equivalent
        
        # Convert HP to AC-equivalent for scoring, but display HP as % of max_hp
        hp_weight = weights_config.get('hp_pct', 0.0)
        if hp_weight > 0 and max_combined > 0:
            hp_ac_equivalent = hp_value / 5.0
            # For scoring: use AC-equivalent normalized to max_combined
            hp_score_for_calc = (hp_ac_equivalent / max_combined * 100) if hp_ac_equivalent > 0 else 0
            # For display: use HP as % of max_hp (so max HP shows 100%)
            hp_score_for_display = (hp_value / max_hp * 100) if max_hp > 0 and hp_value > 0 else 0
            scores['hp_pct'] = hp_score_for_display  # Store percentage for display
            total_score += hp_score_for_calc * hp_weight
            total_weight += hp_weight
        
        # AC normalized to same scale
        ac_weight = weights_config.get('ac_pct', 0.0)
        if ac_weight > 0 and max_combined > 0 and ac_value > 0:
            ac_score = (ac_value / max_combined * 100) if ac_value > 0 else 0
            scores['ac_pct'] = ac_score  # Store percentage for display
            total_score += ac_score * ac_weight
            total_weight += ac_weight
        
        # Mana for Paladin/Shadow Knight (hybrids with mana) - so frontend custom "mana only" works
        if char_class in ['Paladin', 'Shadow Knight']:
            mana_weight = weights_config.get('mana_pct', 0.0)
            mana_value = scores.get('mana', 0) if scores.get('mana') is not None else 0
            max_mana = class_max_values.get('max_mana', 1)
            if mana_weight > 0 and max_mana > 0 and mana_value > 0:
                mana_score = (mana_value / max_mana * 100) if mana_value > 0 else 0
                scores['mana_pct'] = mana_score  # Store percentage for display (and frontend reweighting)
                total_score += mana_score * mana_weight
                total_weight += mana_weight

        # ATK and Haste are now part of focus weight (handled below)
        
        # Resists - calculate individual resist scores with weight curve
        resists_weight = weights_config.get('resists_pct', 0.0)
        if resists_weight > 0:
            individual_resists = char.get('individual_resists', {})
            if individual_resists:
                # Calculate individual resist scores
                # Resists weight is TOTAL across all 5 resists, so divide by number of resists
                num_resists = len(individual_resists)
                resist_weight_per_resist = resists_weight / num_resists if num_resists > 0 else 0.0
                
                resist_scores = {}
                total_resist_score = 0.0
                total_resist_weight = 0.0
                
                for resist_type, resist_value in individual_resists.items():
                    score, weight = calculate_resist_score(resist_value)
                    # Weight is always 1.0, curve is applied to score
                    # The effective weight per resist is resists_weight / num_resists
                    effective_weight = resist_weight_per_resist * weight  # weight is always 1.0
                    resist_scores[resist_type] = {
                        'value': resist_value,
                        'score': score,  # Score already has curve applied
                        'weight': 1.0  # Weight is always 1.0 (for display)
                    }
                    # Add to total (each resist contributes its weighted score)
                    total_resist_score += score * effective_weight
                    total_resist_weight += effective_weight
                
                # Average the weighted scores
                if total_resist_weight > 0:
                    avg_resist_score = total_resist_score / total_resist_weight
                else:
                    avg_resist_score = 0.0
                
                scores['resists_pct'] = avg_resist_score
                scores['individual_resist_scores'] = resist_scores
                # Total resists weight should equal resists_weight (17.5% total)
                total_score += avg_resist_score * resists_weight
                total_weight += resists_weight
            else:
                # Fallback to total resists if individual not available
                max_resists = class_max_values.get('max_resists', 1)
                resists_value = scores.get('resists', 0)
                if max_resists > 0:
                    resists_score = (resists_value / max_resists * 100) if resists_value > 0 else 0
                    scores['resists_pct'] = resists_score
                    total_score += resists_score * resists_weight
                    total_weight += resists_weight
        
        # Focus score - use normalized weight from config
        focus_weights = weights_config.get('focus', {})
        if focus_weights:
            # For Warriors, focus is already calculated in focus_overall_pct
            # For Paladins, handle focuses individually (Shield of Strife, Beneficial Spell Haste, Healing Enhancement)
            if char_class == 'Warrior':
                # Handle Warrior focuses individually: ATK, Haste, Darkblade, Raex Chest (each normalized to equal weight)
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat in ['ATK', 'Haste', 'Darkblade', 'Raex Chest']:
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            focus_score = focus_scores.get(focus_cat, 0)
                            total_score += focus_score * weight_config
                            total_weight += weight_config
            elif char_class == 'Paladin':
                # Handle Paladin focuses individually with their specific weights
                # Shield of Strife (2.0), Beneficial Spell Haste (0.75), Healing Enhancement (0.5)
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat in ['ATK', 'Haste']:
                        continue  # Already handled above
                    if focus_cat == 'Shield of Strife':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            shield_score = focus_scores.get('Shield of Strife', 0)
                            total_score += shield_score * weight_config
                            total_weight += weight_config
                    elif focus_cat == 'Healing Enhancement':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            heal_score = focus_scores.get('Healing Enhancement', 0)
                            total_score += heal_score * weight_config
                            total_weight += weight_config
                    elif focus_cat == 'Beneficial Spell Haste':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            total_score += focus_scores.get('Beneficial Spell Haste', 0) * weight_config
                            total_weight += weight_config
                    elif focus_cat == 'Spell Mana Efficiency':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            total_score += focus_scores.get('Spell Mana Efficiency', 0) * weight_config
                            total_weight += weight_config
            elif char_class == 'Enchanter':
                # Handle Enchanter focuses individually (Serpent of Vindication + spell focuses)
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat in ['ATK', 'Haste']:
                        continue  # Already handled above
                    if focus_cat == 'Serpent of Vindication':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            serpent_score = focus_scores.get('Serpent of Vindication', 0)
                            total_score += serpent_score * weight_config
                            total_weight += weight_config
                    # Other focuses (Spell Damage, Spell Mana Efficiency, etc.) handled in main loop below
            elif char_class == 'Shadow Knight':
                # Handle Shadow Knight focuses individually: Shield of Strife 2.0, Haste 0.75, ATK 0.75, Spell Mana Efficiency 0.5, FT 1.0 (ATK/Haste/FT added below)
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat in ['ATK', 'Haste', 'FT']:
                        continue  # Handled below
                    if focus_cat == 'Shield of Strife':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            total_score += focus_scores.get('Shield of Strife', 0) * weight_config
                            total_weight += weight_config
                    elif focus_cat == 'Spell Mana Efficiency':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            total_score += focus_scores.get('Spell Mana Efficiency', 0) * weight_config
                            total_weight += weight_config
            else:
                # For other classes, use focus_overall_pct
                focus_score = scores.get('focus_overall_pct', 0)
                # Sum spell focus weights (excluding ATK, Haste, FT - handled above)
                total_focus_weight = 0.0
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat in ['ATK', 'Haste', 'FT']:
                        continue
                    if isinstance(weight_config, dict):
                        total_focus_weight += sum(weight_config.values())
                    else:
                        total_focus_weight += weight_config
                if total_focus_weight > 0:
                    total_score += focus_score * total_focus_weight
                    total_weight += total_focus_weight
        
        # Add ATK and Haste for Paladin/Shadow Knight (not Warrior - already in focus loop)
        if char_class in ['Paladin', 'Shadow Knight']:
            atk_weight = focus_weights.get('ATK', 0.0)
            if atk_weight > 0 and scores.get('atk_pct') is not None:
                total_score += scores['atk_pct'] * atk_weight
                total_weight += atk_weight
            haste_weight = focus_weights.get('Haste', 0.0)
            if haste_weight > 0 and scores.get('haste_pct') is not None:
                total_score += scores['haste_pct'] * haste_weight
                total_weight += haste_weight
        # Add FT (Flowing Thought, cap 15) - from focus dict like ATK/Haste; score 0-100
        ft_weight = focus_weights.get('FT', 0.0)
        if ft_weight > 0 and scores.get('ft_capped') is not None:
            ft_pct = 100.0 if scores.get('ft_capped') else (scores.get('ft_pct') or 0)
            total_score += ft_pct * ft_weight
            total_weight += ft_weight
        
        # After normalization, total_weight should be 1.0, but we divide anyway for safety
        return (total_score / total_weight) if total_weight > 0 else 0
    
    # For casters: 1 HP = 1 Mana (same scale)
    # Convert both to a common unit for comparison
    max_hp = class_max_values.get('max_hp', 1)
    max_mana = class_max_values.get('max_mana', 1)
    
    hp_value = scores.get('hp', 0)
    mana_value = scores.get('mana', 0) if scores.get('mana') is not None else 0
    
    # HP and Mana are on same scale (1:1), so use the larger max for normalization
    max_combined = max(max_hp, max_mana) if max_mana > 0 else max_hp
    
    hp_weight = weights_config.get('hp_pct', 0.0)
    if hp_weight > 0 and max_combined > 0:
        # For scoring: use normalized to max_combined
        hp_score_for_calc = (hp_value / max_combined * 100) if hp_value > 0 else 0
        # For display: use HP as % of max_hp (so max HP shows 100%)
        max_hp = class_max_values.get('max_hp', 1)
        hp_score_for_display = (hp_value / max_hp * 100) if max_hp > 0 and hp_value > 0 else 0
        scores['hp_pct'] = hp_score_for_display  # Store percentage for display
        total_score += hp_score_for_calc * hp_weight
        total_weight += hp_weight
    
    mana_weight = weights_config.get('mana_pct', 0.0)
    if mana_weight > 0 and max_combined > 0 and mana_value > 0:
        mana_score = (mana_value / max_combined * 100) if mana_value > 0 else 0
        scores['mana_pct'] = mana_score  # Store percentage for display
        total_score += mana_score * mana_weight
        total_weight += mana_weight
    
    # AC (if applicable)
    if scores.get('ac') is not None:
        weight = weights_config.get('ac_pct', 0.0)
        if weight > 0:
            max_ac = class_max_values.get('max_ac', 1)
            ac_value = scores.get('ac', 0)
            ac_score = (ac_value / max_ac * 100) if max_ac > 0 and ac_value > 0 else 0
            scores['ac_pct'] = ac_score  # Store percentage for display
            total_score += ac_score * weight
            total_weight += weight
    
    # ATK, FT, and Haste are now part of focus weight (handled below)
    
    # Resists - calculate individual resist scores with weight curve
    resists_weight = weights_config.get('resists_pct', 0.0)
    if resists_weight > 0:
        individual_resists = char.get('individual_resists', {})
        if individual_resists:
            # Calculate individual resist scores
            # Resists weight is TOTAL across all 5 resists, so divide by number of resists
            num_resists = len(individual_resists)
            resist_weight_per_resist = resists_weight / num_resists if num_resists > 0 else 0.0
            
            resist_scores = {}
            total_resist_score = 0.0
            total_resist_weight = 0.0
            
            for resist_type, resist_value in individual_resists.items():
                score, weight = calculate_resist_score(resist_value)
                # Weight is always 1.0, curve is applied to score
                # The effective weight per resist is resists_weight / num_resists
                effective_weight = resist_weight_per_resist * weight  # weight is always 1.0
                resist_scores[resist_type] = {
                    'value': resist_value,
                    'score': score,  # Score already has curve applied
                    'weight': 1.0  # Weight is always 1.0 (for display)
                }
                # Add to total (each resist contributes its weighted score)
                total_resist_score += score * effective_weight
                total_resist_weight += effective_weight
            
            # Average the weighted scores
            if total_resist_weight > 0:
                avg_resist_score = total_resist_score / total_resist_weight
            else:
                avg_resist_score = 0.0
            
            scores['resists_pct'] = avg_resist_score
            scores['individual_resist_scores'] = resist_scores
            # Total resists weight should equal resists_weight (17.5% total)
            total_score += avg_resist_score * resists_weight
            total_weight += resists_weight
        else:
            # Fallback to total resists if individual not available
            max_resists = class_max_values.get('max_resists', 1)
            resists_value = scores.get('resists', 0)
            if max_resists > 0:
                resists_score = (resists_value / max_resists * 100) if resists_value > 0 else 0
                scores['resists_pct'] = resists_score
                total_score += resists_score * resists_weight
                total_weight += resists_weight
    
    # Focus weights - includes ATK, FT, Haste, and spell focuses
    focus_weights = weights_config.get('focus', {})
    
    # Add ATK to focus if applicable (skip for Warriors - handled in Warrior-specific section)
    # ATK is now in focus dict, not a separate stat
    if char_class != 'Warrior' and scores.get('atk_pct') is not None:
        atk_weight = focus_weights.get('ATK', 0.0)
        if atk_weight > 0:
            total_score += scores['atk_pct'] * atk_weight
            total_weight += atk_weight
    
    # Add Haste to focus if applicable (skip for Warriors - handled in Warrior-specific section)
    if char_class != 'Warrior' and scores.get('haste_pct') is not None:
        haste_weight = focus_weights.get('Haste', 0.0)
        if haste_weight > 0:
            total_score += scores['haste_pct'] * haste_weight
            total_weight += haste_weight
    
    # Add FT (from focus dict; score 0-100, same scale as ATK/Haste)
    ft_weight = focus_weights.get('FT', 0.0)
    if ft_weight > 0 and scores.get('ft_capped') is not None:
        ft_pct = 100.0 if scores.get('ft_capped') else (scores.get('ft_pct') or 0)
        total_score += ft_pct * ft_weight
        total_weight += ft_weight
    
    # Spell focuses
    if focus_weights:
        best_spell_damage = best_focii.get('Spell Damage', 35.0)
        
        for focus_cat, weight_config in focus_weights.items():
            if focus_cat in ['ATK', 'Haste', 'FT']:
                continue
            if focus_cat == 'Spell Damage':
                # Handle damage type specific weights
                # "All" damage counts for all damage types
                if isinstance(weight_config, dict):
                    for damage_type, weight in weight_config.items():
                        if weight > 0:
                            # Get the character's focus percentage for this damage type
                            # "All" is instant-only; "DoT" is DoT-only (they don't apply to each other)
                            if damage_type == 'DoT':
                                char_pct = char_damage_focii.get('DoT', 0)
                            else:
                                # For non-DoT types, "All" (instant) counts
                                char_pct = max(
                                    char_damage_focii.get(damage_type, 0),
                                    char_damage_focii.get('All', 0)
                                )
                            # Calculate score as % of best spell damage focus
                            # Use max of specific type best and "All" best
                            best_damage = max(
                                best_spell_damage,
                                char_damage_focii.get('All', 0)  # "All" damage best
                            )
                            if best_damage > 0:
                                focus_score = (char_pct / best_damage * 100) if char_pct > 0 else 0
                                total_score += focus_score * weight
                                total_weight += weight
            elif focus_cat in ['Beneficial Spell Haste', 'Detrimental Spell Haste']:
                # Handle spell haste categories - look up from char_spell_haste_cats
                # "All" categories count for both Bene and Det
                if isinstance(weight_config, (int, float)) and weight_config > 0:
                    if char_spell_haste_cats is not None:
                        if focus_cat == 'Beneficial Spell Haste':
                            # Use max of Bene and All (All counts for both)
                            char_pct = max(
                                char_spell_haste_cats.get('Bene', 0),
                                char_spell_haste_cats.get('All', 0)
                            )
                            best_haste = max(
                                best_focii.get('Spell Haste', 33.0),
                                best_focii.get('All Spell Haste', 0)  # If "All Spell Haste" exists
                            )
                        else:  # Detrimental Spell Haste
                            # Use max of Det and All (All counts for both)
                            char_pct = max(
                                char_spell_haste_cats.get('Det', 0),
                                char_spell_haste_cats.get('All', 0)
                            )
                            best_haste = max(
                                best_focii.get('Spell Haste', 33.0),
                                best_focii.get('All Spell Haste', 0)  # If "All Spell Haste" exists
                            )
                        
                        # For Beastlord detrimental spell haste: they get 1.5% per level (15 levels = 22.5% innate)
                        # Focus caps at 50% total, so focus item can only contribute 50% - 22.5% = 27.5%
                        # But the focus item itself shows the full percentage, so we cap the effective at 27.5%
                        if char_class == 'Beastlord' and focus_cat == 'Detrimental Spell Haste':
                            # Cap the effective focus at 27.5% (50% total - 22.5% innate)
                            effective_pct = min(char_pct, 27.5)
                            best_haste = 27.5  # Best possible for Beastlord det haste
                        else:
                            effective_pct = char_pct
                            if best_haste == 0:
                                best_haste = best_focii.get('Spell Haste', 33.0)  # Default to 33% if not found
                        
                        if best_haste > 0:
                            focus_score = (effective_pct / best_haste * 100) if effective_pct > 0 else 0
                            total_score += focus_score * weight_config
                            total_weight += weight_config
            elif focus_cat in ['Buff Spell Duration', 'Beneficial Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration']:
                # Handle duration categories - look up from char_duration_cats
                # All Spell Duration counts for both Buff (Bene) and Detrimental (Det) at its percentage
                if isinstance(weight_config, (int, float)) and weight_config > 0:
                    if char_duration_cats:
                        if focus_cat == 'All Spell Duration':
                            char_pct = char_duration_cats.get('All', 0)
                            best_duration = best_focii.get('All Spell Duration', 15.0)
                        elif focus_cat in ('Buff Spell Duration', 'Beneficial Spell Duration'):
                            # Buff/Beneficial: use max(Bene, All) so All counts as that % for beneficial
                            char_pct = max(
                                char_duration_cats.get('Bene', 0),
                                char_duration_cats.get('All', 0)
                            )
                            best_duration = max(
                                best_focii.get('Buff Spell Duration', 25.0),
                                best_focii.get('All Spell Duration', 15.0)
                            )
                        else:  # Detrimental Spell Duration
                            # Detrimental: use max(Det, All) so All counts as that % for detrimental
                            char_pct = max(
                                char_duration_cats.get('Det', 0),
                                char_duration_cats.get('All', 0)
                            )
                            best_duration = max(
                                best_focii.get('Detrimental Spell Duration', 25.0),
                                best_focii.get('All Spell Duration', 15.0)
                            )
                        if best_duration > 0:
                            focus_score = (char_pct / best_duration * 100) if char_pct > 0 else 0
                            total_score += focus_score * weight_config
                            total_weight += weight_config
            else:
                # Other focus categories - use the already calculated focus_scores with specified weight
                if isinstance(weight_config, (int, float)) and weight_config > 0:
                    focus_score = focus_scores.get(focus_cat, 0)
                    total_score += focus_score * weight_config
                    total_weight += weight_config
    
    return (total_score / total_weight) if total_weight > 0 else 0

def calculate_overall_score_fallback(scores, char_class):
    """Fallback calculation for classes without specific weights"""
    relevant_scores = []
    weights = []
    
    # HP is always important
    relevant_scores.append(scores['hp_pct'])
    weights.append(1.0)
    
    # Class-specific weighting
    if char_class in CLASSES_WITH_MANA:
        if scores.get('mana_pct') is not None:
            relevant_scores.append(scores['mana_pct'])
            weights.append(1.0)
        if scores.get('focus_overall_pct', 0) > 0:
            relevant_scores.append(scores['focus_overall_pct'])
            weights.append(1.5)
    else:
        if scores.get('ac_pct') is not None:
            relevant_scores.append(scores['ac_pct'])
            weights.append(1.0)
        if scores.get('atk_pct') is not None:
            relevant_scores.append(scores['atk_pct'])
            weights.append(1.0)
        if scores.get('haste_pct') is not None:
            relevant_scores.append(scores['haste_pct'])
            weights.append(0.5)
    
    if relevant_scores and weights:
        return sum(s * w for s, w in zip(relevant_scores, weights)) / sum(weights)
    return 0

def main():
    print("Loading spell focus data...")
    focii_data = load_focii()
    focus_lookup = create_focus_lookup(focii_data)
    best_focii = get_best_focii_by_category(focii_data)
    best_mana_by_cat, best_haste_by_cat, best_duration_by_cat = get_best_focii_by_subcategory(focii_data)
    item_stats_lookup = load_item_stats()
    focus_candidates = get_all_focus_candidates(focii_data, item_stats_lookup)
    bard_instrument_data = load_bard_instruments()
    
    print(f"Loaded {len(focii_data)} focus effects")
    print(f"Best focii by category: {best_focii}")
    
    print("\nLoading character data...")
    
    # Find the latest character and inventory files (similar to generate_spell_page.py)
    base_dir = os.path.dirname(__file__) if '__file__' in globals() else '.'
    char_dir = os.path.join(base_dir, "character")
    inv_dir = os.path.join(base_dir, "inventory")
    
    # Look for TAKP_character.txt first (used by GitHub Actions), then fall back to dated files
    char_file = None
    inv_file = None
    
    if os.path.exists(os.path.join(char_dir, "TAKP_character.txt")):
        char_file = os.path.join(char_dir, "TAKP_character.txt")
    else:
        # Find latest dated file
        all_char_files = []
        if os.path.exists(char_dir):
            for filename in os.listdir(char_dir):
                if filename.endswith('.txt') and '_previous' not in filename:
                    filepath = os.path.join(char_dir, filename)
                    if os.path.isfile(filepath):
                        all_char_files.append((filepath, os.path.getmtime(filepath)))
        if all_char_files:
            all_char_files.sort(key=lambda x: x[1], reverse=True)
            char_file = all_char_files[0][0]
        else:
            char_file = os.path.join(char_dir, "2_6_26.txt")  # Fallback
    
    if os.path.exists(os.path.join(inv_dir, "TAKP_character_inventory.txt")):
        inv_file = os.path.join(inv_dir, "TAKP_character_inventory.txt")
    else:
        # Find latest dated file
        all_inv_files = []
        if os.path.exists(inv_dir):
            for filename in os.listdir(inv_dir):
                if filename.endswith('.txt') and '_previous' not in filename:
                    filepath = os.path.join(inv_dir, filename)
                    if os.path.isfile(filepath):
                        all_inv_files.append((filepath, os.path.getmtime(filepath)))
        if all_inv_files:
            all_inv_files.sort(key=lambda x: x[1], reverse=True)
            inv_file = all_inv_files[0][0]
        else:
            inv_file = os.path.join(inv_dir, "2_6_26.txt")  # Fallback
    
    if not os.path.exists(char_file):
        print(f"Error: Character file not found: {char_file}")
        return 1
    if not os.path.exists(inv_file):
        print(f"Error: Inventory file not found: {inv_file}")
        return 1
    
    print(f"Using character file: {os.path.basename(char_file)}")
    print(f"Using inventory file: {os.path.basename(inv_file)}")
    
    # Load characters (utf-8-sig strips BOM so header keys like 'name' are correct)
    characters = {}
    with open(char_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            # Normalize row keys: strip BOM from first key if present (e.g. Excel export)
            if row and reader.fieldnames:
                first_key = reader.fieldnames[0]
                if first_key.startswith('\ufeff'):
                    row[first_key.lstrip('\ufeff')] = row.pop(first_key)
            level = _row_get(row, 'level', '')
            if level == '65':
                char_id = _row_get(row, 'id', '')
                if not char_id:
                    continue
                try:
                    def safe_int(value, default=0):
                        if not value or value == 'NULL' or value == '':
                            return default
                        try:
                            return int(value)
                        except (ValueError, TypeError):
                            return default
                    
                    # Parse FT (Flowing Thought) - mana_regen_item / mana_regen_item_cap.
                    # Source: same TAKP export as Magelo. Use _row_get so we read FT even if export
                    # uses different casing (e.g. Mana_Regen_Item) or BOM affected header keys.
                    ft_current = safe_int(_row_get(row, 'mana_regen_item', 0))
                    ft_cap = safe_int(_row_get(row, 'mana_regen_item_cap', 15))
                    ft_str = f"{ft_current} / {ft_cap}" if ft_cap > 0 else "0 / 15"
                    
                    # Extract resists
                    mr = safe_int(row.get('MR_total', 0))
                    fr = safe_int(row.get('FR_total', 0))
                    cr = safe_int(row.get('CR_total', 0))
                    dr = safe_int(row.get('DR_total', 0))
                    pr = safe_int(row.get('PR_total', 0))
                    resists_total = mr + fr + cr + dr + pr
                    
                    characters[char_id] = {
                        'id': char_id,
                        'name': row['name'],
                        'guild': row.get('guild_name', ''),
                        'class': row.get('class', ''),
                        'race': row.get('race', ''),
                        'hp': safe_int(row.get('hp_max_total')),
                        'mana': safe_int(row.get('mana_max_total')),
                        'ac': safe_int(row.get('ac_total')),
                        'atk_item': f"{safe_int(row.get('atk_item'))} / {safe_int(row.get('atk_item_cap'))}",
                        'haste': safe_int(row.get('haste_item')),
                        'mana_regen_item': ft_str,
                        'resists': resists_total,
                        'individual_resists': {
                            'MR': mr,
                            'FR': fr,
                            'CR': cr,
                            'DR': dr,
                            'PR': pr
                        },
                        'stats': {
                            'hp': safe_int(row.get('hp_max_total')),
                            'mana': safe_int(row.get('mana_max_total')),
                            'ac': safe_int(row.get('ac_total')),
                            'atk_item': f"{safe_int(row.get('atk_item'))} / {safe_int(row.get('atk_item_cap'))}",
                            'haste': safe_int(row.get('haste_item')),
                            'mana_regen_item': ft_str,
                            'resists': resists_total
                        }
                    }
                except Exception as e:
                    print(f"Error processing character {char_id}: {e}")
                    continue
    
    print(f"Found {len(characters)} level 65 characters")
    
    # Load inventory (utf-8-sig for consistency with character file)
    # Include all slots (worn + bags) so focus items like harmonize clickies count when in inventory
    # Backfill missing item_id from item name using data/item_stats.json so item cards work for all slots
    print("Loading inventory data...")
    item_name_to_id = load_item_stats_name_to_id()
    if item_name_to_id:
        print(f"  Name->id lookup: {len(item_name_to_id)} items (for backfilling missing item_id)")
    inventory = {}
    backfilled = 0
    with open(inv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            char_id = row.get('id', '')
            try:
                slot_id = int(row.get('slot_id', 0))
            except (ValueError, TypeError):
                continue
            if char_id not in characters:
                continue
            if char_id not in inventory:
                inventory[char_id] = []
            item_id = (row.get('item_id') or '').strip()
            item_name = (row.get('item_name') or '').strip()
            if not item_id and item_name and item_name_to_id:
                resolved = item_name_to_id.get(normalize_item_name(item_name), '')
                if resolved:
                    item_id = resolved
                    backfilled += 1
            inventory[char_id].append({
                'item_id': item_id,
                'item_name': item_name or row.get('item_name', ''),
                'slot_id': slot_id
            })
    if backfilled:
        print(f"  Backfilled item_id for {backfilled} inventory rows from name lookup")
    print(f"Loaded inventory for {len(inventory)} characters")
    
    # Group characters by class
    chars_by_class = defaultdict(list)
    for char_id, char_data in characters.items():
        char_class = char_data['class']
        chars_by_class[char_class].append(char_data)
    
    # Analyze focii and calculate scores
    print("\nAnalyzing character focii and calculating scores...")
    output_data = []
    
    # Calculate max values per class for normalization after conversion
    class_max_values = {}
    for char_class, class_chars in chars_by_class.items():
        if class_chars:
            class_max_values[char_class] = {
                'max_hp': max(c['stats']['hp'] for c in class_chars),
                'max_mana': max(c.get('stats', {}).get('mana', 0) for c in class_chars) if char_class in CLASSES_WITH_MANA else 0,
                'max_ac': max(c.get('stats', {}).get('ac', 0) for c in class_chars),  # All classes have AC for scoring
                'max_resists': max(c.get('stats', {}).get('resists', 0) for c in class_chars),
            }
    
    # Best Pet Power % per class (for normalizing Pet Power score); uses full inventory
    best_pet_power_by_class = {}
    for char_class in ('Magician', 'Beastlord', 'Necromancer'):
        best_pp = 0
        for cid, c in characters.items():
            if c.get('class') != char_class:
                continue
            inv = inventory.get(cid, [])
            p = get_char_pet_power(inv)
            if p > best_pp:
                best_pp = p
        best_pet_power_by_class[char_class] = best_pp

    for char_id, char_data in characters.items():
        char_class = char_data['class']
        char_inventory = inventory.get(char_id, [])
        char_focii, char_damage_focii, char_mana_efficiency_cats, char_spell_haste_cats, char_duration_cats = analyze_character_focii(char_inventory, focus_lookup)
        scores = calculate_class_scores(char_data, char_focii, char_damage_focii, best_focii, chars_by_class, char_inventory, char_spell_haste_cats, char_duration_cats, char_mana_efficiency_cats, bard_instrument_data, best_mana_by_cat, best_haste_by_cat, best_duration_by_cat, best_pet_power_by_class)
        scores['focus_sources'] = get_focus_sources(char_inventory, focus_lookup)
        
        # Calculate overall score using class-specific weights with conversion rates
        overall_score = calculate_overall_score_with_weights(
            char_class, 
            scores, 
            char_damage_focii, 
            scores.get('focus_scores', {}),
            best_focii,
            class_max_values.get(char_class, {}),
            char_spell_haste_cats,
            char_duration_cats,
            char_mana_efficiency_cats,
            char_data  # Pass char_data for individual_resists
        )
        
        output_data.append({
            'id': char_id,
            'name': char_data['name'],
            'guild': char_data['guild'],
            'class': char_data['class'],
            'race': char_data['race'],
            'stats': char_data['stats'],
            'individual_resists': char_data.get('individual_resists', {}),  # Individual resist values
            'focii': char_focii,  # Best focus in each category (percentage values)
            'damage_focii': char_damage_focii,  # Best focus by damage type
            'mana_efficiency_cats': char_mana_efficiency_cats,  # Mana Efficiency by category
            'spell_haste_cats': char_spell_haste_cats,  # Spell Haste by category
            'duration_cats': char_duration_cats,  # Duration by category
            'scores': scores,  # Percentage scores (includes focus_scores and focus_items)
            'overall_score': round(overall_score, 2),  # Overall ranking score
            'inventory': char_inventory  # Inventory items for item links
        })
    
    # Sort by overall score (descending)
    output_data.sort(key=lambda x: x['overall_score'], reverse=True)
    
    # Add rankings by class
    class_rankings = defaultdict(int)
    for char in output_data:
        char_class = char['class']
        class_rankings[char_class] += 1
        char['class_rank'] = class_rankings[char_class]
        char['overall_rank'] = len([c for c in output_data if c['overall_score'] > char['overall_score']]) + 1
    
    # Write output with class weights for filtering in UI
    # normalized_class_weights: per-class weights used for scoring (focus ~35%); use for card Stat/Focus Total and Weight column
    output_file = 'class_rankings.json'
    normalized_by_class = {
        cls: normalize_class_weights(CLASS_WEIGHTS[cls]) for cls in CLASS_WEIGHTS
    }
    output = {
        'characters': output_data,
        'class_weights': CLASS_WEIGHTS,
        'normalized_class_weights': normalized_by_class,
        'focus_candidates': focus_candidates,
    }
    # Helper function to round floats in nested structures
    def round_floats(obj):
        if isinstance(obj, float):
            # Round to 2 decimal places, but keep as float (not string)
            return round(obj, 2) if obj != int(obj) else int(obj)
        elif isinstance(obj, dict):
            return {k: round_floats(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [round_floats(item) for item in obj]
        return obj
    
    # Round all float values to avoid precision issues
    output = round_floats(output)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\nGenerated {output_file}")
    print(f"Total characters: {len(output_data)}")
    
    # Print top 5 by class
    print("\nTop 5 characters by overall score:")
    for char in output_data[:5]:
        print(f"  #{char['overall_rank']} {char['name']} ({char['class']}) - Score: {char['overall_score']:.2f}%")
    
    # Print sample with details
    if output_data:
        sample = output_data[0]
        print(f"\nSample character: {sample['name']} ({sample['class']})")
        print(f"  Overall Rank: #{sample['overall_rank']}, Class Rank: #{sample['class_rank']}")
        print(f"  Overall Score: {sample['overall_score']:.2f}%")
        print(f"  Scores: HP: {sample['scores'].get('hp_pct', 0):.1f}%, AC: {sample['scores'].get('ac_pct', 'N/A')}, ATK: {sample['scores'].get('atk_pct', 'N/A')}")
        print(f"  Focii: {sample['focii']}")

if __name__ == '__main__':
    main()
