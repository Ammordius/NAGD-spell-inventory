#!/usr/bin/env python3
"""
Generate class-specific character rankings with focus analysis
"""

import csv
import json
import os
import sys
from collections import defaultdict

# Class definitions
CLASSES_WITH_MANA = {'Cleric', 'Druid', 'Shaman', 'Necromancer', 'Wizard', 'Magician', 'Enchanter', 'Bard'}
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

# Create focus lookup by item name (normalized)
def create_focus_lookup(focii_data):
    """Create a lookup: item_name (normalized) -> focus effects"""
    focus_by_item_name = defaultdict(list)
    
    for focus in focii_data:
        for item in focus.get('items', []):
            item_name = normalize_item_name(item.get('name', ''))
            if item_name:
                focus_by_item_name[item_name].append({
                    'name': focus['name'],
                    'category': focus['category'],
                    'percentage': focus['percentage']
                })
    
    print(f"Created focus lookup with {len(focus_by_item_name)} unique item names")
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
        if item_name in focus_lookup:
            for focus_effect in focus_lookup[item_name]:
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
    'Fury of Solusek': 'Fire',
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
    
    # Disease/Poison (DoT) focii (Bertoxxulous, Saryrn are disease/poison)
    'Fury of Bertoxxulous': 'Disease',
    'Saryrn\'s Torment': 'Disease',
    'Saryrn\'s Venom': 'Disease',
    
    # Vengeance of Eternity - works for all damage types (including DoT)
    'Vengeance of Eternity': 'All',
    
    # All damage types (generic damage focii)
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
}

# Map Spell Haste focii to categories (detrimental, beneficial)
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

# Class-specific damage type priorities
CLASS_DAMAGE_TYPES = {
    'Necromancer': ['All', 'Disease'],  # All damage + DoT focus
    'Shaman': ['Cold', 'Disease'],  # Cold + DoT
    'Wizard': ['Fire', 'Cold', 'Magic'],
    'Magician': ['Fire', 'Magic'],
    'Druid': ['Fire', 'Cold'],
    'Enchanter': ['Magic'],
    'Cleric': ['Magic'],
}

# Class-specific focus priorities (updated with damage types)
CLASS_FOCUS_PRIORITIES = {
    'Necromancer': ['Spell Damage (All)', 'Spell Damage (Disease)', 'Spell Mana Efficiency', 'Spell Haste', 'Detrimental Spell Duration'],
    'Shaman': ['Spell Damage (Cold)', 'Spell Damage (Disease)', 'Healing Enhancement', 'Spell Mana Efficiency', 'Buff Spell Duration'],
    'Druid': ['Healing Enhancement', 'Spell Damage (Fire)', 'Spell Damage (Cold)', 'Spell Mana Efficiency', 'Buff Spell Duration'],
    'Cleric': ['Healing Enhancement', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Buff Spell Duration'],
    'Wizard': ['Spell Damage (Fire)', 'Spell Damage (Cold)', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste'],
    'Magician': ['Spell Damage (Fire)', 'Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste'],
    'Enchanter': ['Spell Damage (Magic)', 'Spell Mana Efficiency', 'Spell Haste', 'Buff Spell Duration'],
    'Bard': ['Spell Haste', 'Spell Mana Efficiency'],
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

def check_warrior_focus_items(char_inventory, char_haste):
    """Check if Warrior has the required focus items in correct slots and max haste"""
    has_mh = False
    has_chest = False
    
    for item in char_inventory:
        slot_id = item.get('slot_id', 0)
        item_id = item.get('item_id', '')
        
        # Check Main Hand (slot 13) for item 22999
        if slot_id == 13 and item_id == WARRIOR_FOCUS_ITEMS['mh']:
            has_mh = True
        # Check Chest (slot 17) for item 32129
        if slot_id == 17 and item_id == WARRIOR_FOCUS_ITEMS['chest']:
            has_chest = True
    
    # Check haste - binary: 30% item haste (70% buff + 30% item = 100% total) = on, otherwise off
    # char_haste is the item haste value, so >= 30 means max total haste
    has_max_haste = (char_haste >= 30)
    
    # Calculate focus score: 100% if all three (both items + max haste), otherwise prorated
    items_score = 0
    if has_mh and has_chest:
        items_score = 100.0
    elif has_mh or has_chest:
        items_score = 50.0
    
    haste_score = 100.0 if has_max_haste else 0.0
    
    # Average of items (2/3 weight) and haste (1/3 weight)
    if items_score > 0 or haste_score > 0:
        return (items_score * 2 + haste_score) / 3, {'has_mh': has_mh, 'has_chest': has_chest, 'has_haste': has_max_haste}
    else:
        return 0.0, {'has_mh': has_mh, 'has_chest': has_chest, 'has_haste': has_max_haste}

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
        slot_id = item.get('slot_id', 0)
        item_id = item.get('item_id', '')
        
        # Check Range (slot 11) for item 22959
        if slot_id == 11 and item_id == ENCHANTER_FOCUS_ITEMS['range']:
            has_serpent = True
    
    # Focus score: 100% if has serpent, 0% otherwise
    return 100.0 if has_serpent else 0.0, {'has_serpent': has_serpent}

# Calculate class-specific scores
def calculate_class_scores(char_data, char_focii, char_damage_focii, best_focii, all_chars_by_class, char_inventory=None, char_spell_haste_cats=None):
    """Calculate percentage scores for a character based on their class"""
    char_class = char_data['class']
    scores = {}
    
    # HP - store raw value for conversion-based scoring
    scores['hp'] = char_data['stats']['hp']
    
    # Mana - only for classes with mana, store raw value
    if char_class in CLASSES_WITH_MANA:
        scores['mana'] = char_data.get('stats', {}).get('mana', 0)
    else:
        scores['mana'] = None  # Not applicable
    
    # AC - only for tank/hybrid classes, store raw value
    if char_class in CLASSES_NEED_AC:
        scores['ac'] = char_data['stats']['ac']
    else:
        scores['ac'] = None  # Not applicable
    
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
        # FT capped (15/15) is worth 2.0 weight
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
        warrior_focus_score, warrior_items = check_warrior_focus_items(char_inventory or [], char_haste)
        # For Warriors, focus_overall_pct is just the warrior focus score
        focus_scores = {'Warrior Focus Items': warrior_focus_score}
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
            # Spell Haste (Beneficial) will be handled via spell_haste_cats in the scoring function
    elif char_class == 'Shadow Knight':
        pal_sk_focus_score, pal_sk_items = check_paladin_sk_focus_items(char_inventory or [])
        focus_scores = {'Shield of Strife': pal_sk_focus_score}
        scores['focus_items'] = pal_sk_items
    elif char_class == 'Enchanter':
        enchanter_focus_score, enchanter_items = check_enchanter_focus_items(char_inventory or [])
        focus_scores = {'Serpent of Vindication': enchanter_focus_score}
        scores['focus_items'] = enchanter_items
        # Add other focus scores for Enchanters (spell focuses)
        for category, best_pct in best_focii.items():
            if category == 'Spell Damage':
                # Handle spell damage separately
                char_pct = char_damage_focii.get('Magic', 0)
                if best_pct > 0:
                    focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                else:
                    focus_scores[category] = 0
            elif category in ['Spell Mana Efficiency', 'Spell Haste', 'Spell Range Extension']:
                # Track these for Enchanters
                char_pct = char_focii.get(category, 0)
                if best_pct > 0:
                    focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                else:
                    focus_scores[category] = 0
    else:
        focus_scores = {}
        for category, best_pct in best_focii.items():
            if category == 'Spell Damage':
                # For spell damage, calculate class-specific damage type scores
                if char_class in CLASS_DAMAGE_TYPES:
                    damage_types = CLASS_DAMAGE_TYPES[char_class]
                    best_damage_score = 0
                    for damage_type in damage_types:
                        char_pct = char_damage_focii.get(damage_type, 0)
                        if best_pct > 0:
                            damage_score = (char_pct / best_pct * 100) if char_pct > 0 else 0
                            best_damage_score = max(best_damage_score, damage_score)
                    # Also check "All" damage type
                    all_pct = char_damage_focii.get('All', 0)
                    if best_pct > 0:
                        all_score = (all_pct / best_pct * 100) if all_pct > 0 else 0
                        best_damage_score = max(best_damage_score, all_score)
                    focus_scores[category] = best_damage_score
                else:
                    # Non-caster classes don't need spell damage
                    focus_scores[category] = 0
            else:
                # Other categories work normally
                char_pct = char_focii.get(category, 0)
                if best_pct > 0:
                    focus_scores[category] = (char_pct / best_pct * 100) if char_pct > 0 else 0
                else:
                    focus_scores[category] = 0
        
        # Add haste binary check for all ATK classes (mnk, rog, war, pal, shd, bst, brd, rng)
        # Binary: 30% item haste (70% buff + 30% item = 100% total) = 100%, otherwise 0%
        if char_class in CLASSES_NEED_ATK:
            char_haste = char_data.get('stats', {}).get('haste', 0)
            if isinstance(char_haste, (int, float)):
                has_max_haste = (char_haste >= 30)
                focus_scores['Haste'] = 100.0 if has_max_haste else 0.0
            else:
                focus_scores['Haste'] = 0.0
    
    scores['focus_scores'] = focus_scores
    
    # Store damage-specific focii for display
    scores['damage_focii'] = char_damage_focii
    
    # Calculate overall focus score based on class priorities
    if char_class == 'Warrior':
        # For Warriors, focus score is just the warrior focus items score
        scores['focus_overall_pct'] = focus_scores.get('Warrior Focus Items', 0)
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
        # For SK, focus score is just the Shield of Strife score
        scores['focus_overall_pct'] = focus_scores.get('Shield of Strife', 0)
    elif char_class in CLASS_FOCUS_PRIORITIES:
        priority_cats = CLASS_FOCUS_PRIORITIES[char_class]
        # Weighted average of priority focus categories
        total_score = 0
        total_weight = 0
        for i, cat in enumerate(priority_cats):
            weight = len(priority_cats) - i  # Higher weight for higher priority
            # Handle spell damage with damage type
            if cat.startswith('Spell Damage ('):
                score = focus_scores.get('Spell Damage', 0)
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
    # Warrior/Monk - Tank melees
    'Warrior': {
        'hp_pct': 1.0,
        'mana_pct': 0.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            # No focus weights for pure melees
        }
    },
    'Monk': {
        'hp_pct': 1.0,
        'mana_pct': 0.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {}
    },
    
    # Rogue - DPS melee
    'Rogue': {
        'hp_pct': 1.0,
        'mana_pct': 0.0,
        'ac_pct': 0.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {}
    },
    
    # Shadow Knight/Paladin - Tank hybrids
    'Shadow Knight': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {}
    },
    'Paladin': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            'Beneficial Spell Haste': 0.75,
            'Healing Enhancement': 0.5,
            'Shield of Strife': 2.0,
        }
    },
    
    # Wizard - Pure caster
    'Wizard': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Fire': 1.0, 'Cold': 1.0, 'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Spell Haste': 1.0,
        }
    },
    
    # Cleric - Healer
    'Cleric': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Magic': 0.5},
            'Healing Enhancement': 2.0,
            'Spell Mana Efficiency': 1.0,
            'Spell Range Extension': 1.0,
            'Buff Spell Duration': 1.0,
            'Beneficial Spell Haste': 1.0,
        }
    },
    
    # Magician - Pet caster
    'Magician': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Fire': 1.0, 'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Detrimental Spell Haste': 1.0,
            'Detrimental Spell Duration': 0.75,
        }
    },
    
    # Necromancer - DoT caster
    'Necromancer': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'All': 0.75, 'Disease': 1.0},
            'Spell Mana Efficiency': 1.0,  # det mana
            'Detrimental Spell Duration': 1.0,  # det or all e
            'Detrimental Spell Haste': 1.0,  # det spell h
        }
    },
    
    # Shaman - Hybrid healer/DoT
    'Shaman': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Cold': 1.0, 'All': 0.75, 'Disease': 1.0},
            'Healing Enhancement': 1.0,
            'Spell Mana Efficiency': 1.0,
            'Detrimental Spell Haste': 0.75,
            'Buff Spell Duration': 1.0,  # Bene exter
            'Detrimental Spell Duration': 1.0,  # DoT duration focus
            'All Spell Duration': 1.0,  # All duration focus (works for both)
        }
    },
    
    # Enchanter - Support caster
    'Enchanter': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Magic': 0.5},
            'Spell Mana Efficiency': 1.0,
            'Buff Spell Duration': 1.0,  # Bene exter
            'Detrimental Spell Duration': 1.0,  # Det duration (required)
            'Detrimental Spell Haste': 1.0,
            'Spell Range Extension': 0.75,
            'Serpent of Vindication': 2.0,
        }
    },
    
    # Beastlord - Hybrid melee/caster
    'Beastlord': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Cold': 0.5},
            'Healing Enhancement': 0.75,
            'Spell Mana Efficiency': 1.0,
            'Beneficial Spell Haste': 0.75,
            'Detrimental Spell Haste': 0.75,
        }
    },
    
    # Druid - Hybrid healer/caster
    'Druid': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 0.0,
        'haste_pct': 0.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Damage': {'Fire': 1.0, 'Cold': 1.0},
            'Healing Enhancement': 1.0,
            'Spell Mana Efficiency': 1.0,
            'Beneficial Spell Haste': 1.0,
            'Detrimental Spell Haste': 0.75,
            'Detrimental Spell Duration': 0.5,  # det or all e
            'Buff Spell Duration': 1.0,  # Bene exter
        }
    },
    
    # Ranger - Hybrid melee/caster
    'Ranger': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 1.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {}
    },
    
    # Bard - Support hybrid
    'Bard': {
        'hp_pct': 1.0,
        'mana_pct': 1.0,
        'ac_pct': 0.0,
        'atk_pct': 1.0,
        'haste_pct': 1.0,
        'resists_pct': 1.0,
        'focus': {
            'Spell Haste': 1.0,
            'Spell Mana Efficiency': 1.0,
        }
    },
}

def normalize_class_weights(weights_config):
    """Normalize class weights: focus weights total = 2.4x HP weight (40% of score for casters), then normalize all to sum to 1.0"""
    hp_weight = weights_config.get('hp_pct', 1.0)
    
    # Calculate total focus weight from config (relative weights)
    focus_weights = weights_config.get('focus', {})
    total_focus_weight_config = 0.0
    if focus_weights:
        for focus_cat, focus_value in focus_weights.items():
            if isinstance(focus_value, dict):
                # Spell Damage with damage types
                total_focus_weight_config += sum(focus_value.values())
            else:
                # Single focus weight
                total_focus_weight_config += focus_value
    
    # Scale focus weights so they total 2.4x HP weight (40% of score for casters)
    focus_scale = (2.4 * hp_weight) / total_focus_weight_config if total_focus_weight_config > 0 else 0.0
    
    # Calculate total weight including scaled focuses
    total_weight = 0.0
    # Sum stat weights (including resists)
    for stat_key in ['hp_pct', 'mana_pct', 'ac_pct', 'atk_pct', 'haste_pct', 'resists_pct']:
        total_weight += weights_config.get(stat_key, 0.0)
    
    # Add scaled focus weights
    if focus_weights and focus_scale > 0:
        for focus_cat, focus_value in focus_weights.items():
            if isinstance(focus_value, dict):
                total_weight += sum(focus_value.values()) * focus_scale
            else:
                total_weight += focus_value * focus_scale
    
    # Normalize if total > 0
    if total_weight > 0:
        normalized = {}
        # Normalize stat weights
        for stat_key in ['hp_pct', 'mana_pct', 'ac_pct', 'atk_pct', 'haste_pct', 'resists_pct']:
            normalized[stat_key] = weights_config.get(stat_key, 0.0) / total_weight
        
        # Normalize focus weights (with scaling applied)
        if focus_weights and focus_scale > 0:
            normalized['focus'] = {}
            for focus_cat, focus_value in focus_weights.items():
                if isinstance(focus_value, dict):
                    # Spell Damage with damage types - scale then normalize
                    normalized['focus'][focus_cat] = {
                        k: (v * focus_scale) / total_weight for k, v in focus_value.items()
                    }
                else:
                    # Single focus weight - scale then normalize
                    normalized['focus'][focus_cat] = (focus_value * focus_scale) / total_weight
        else:
            normalized['focus'] = {}
        
        return normalized
    else:
        return weights_config

def calculate_resist_score(resist_value):
    """
    Calculate resist score with weight curve:
    - Full weight (1.0) up to 220
    - Linearly decreasing weight from 220 to 320 (1.0 to 0.35)
    - 0.35 weight from 320 to 500
    - 0 weight above 500
    
    The score percentage is normalized to show actual value (higher resists = higher score %),
    but the weight decreases above 220 to reflect diminishing returns.
    
    Returns: (score_percentage, effective_weight)
    """
    if resist_value <= 0:
        return (0.0, 0.0)
    
    # Normalize score based on max value of 500 (so 500 = 100%)
    # This shows the actual value proportionally
    max_resist = 500.0
    score = (resist_value / max_resist) * 100.0
    
    # Calculate weight based on the curve
    if resist_value <= 220:
        # Full weight up to 220
        weight = 1.0
    elif resist_value <= 320:
        # Linear decrease from 220 to 320 (1.0 to 0.35)
        weight = 1.0 - ((resist_value - 220) / 100.0) * 0.65  # Decreases from 1.0 to 0.35
    elif resist_value <= 500:
        # 0.35 weight from 320 to 500
        weight = 0.35
    else:
        # 0 weight above 500
        weight = 0.0
        score = 0.0  # No score above 500
    
    return (score, weight)

def calculate_overall_score_with_weights(char_class, scores, char_damage_focii, focus_scores, best_focii, class_max_values=None, char_spell_haste_cats=None, char_duration_cats=None, char_mana_efficiency_cats=None, char=None):
    """Calculate overall score using class-specific weights with conversion rates"""
    weights_config = CLASS_WEIGHTS.get(char_class, {})
    class_max_values = class_max_values or {}
    
    if not weights_config:
        # Fallback to default weights if class not found
        return calculate_overall_score_fallback(scores, char_class)
    
    # Normalize weights so they sum to 1.0
    weights_config = normalize_class_weights(weights_config)
    
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
        
        # Convert HP to AC-equivalent and normalize
        hp_weight = weights_config.get('hp_pct', 0.0)
        if hp_weight > 0 and max_combined > 0:
            hp_ac_equivalent = hp_value / 5.0
            hp_score = (hp_ac_equivalent / max_combined * 100) if hp_ac_equivalent > 0 else 0
            scores['hp_pct'] = hp_score  # Store percentage for display
            total_score += hp_score * hp_weight
            total_weight += hp_weight
        
        # AC normalized to same scale
        ac_weight = weights_config.get('ac_pct', 0.0)
        if ac_weight > 0 and max_combined > 0 and ac_value > 0:
            ac_score = (ac_value / max_combined * 100) if ac_value > 0 else 0
            scores['ac_pct'] = ac_score  # Store percentage for display
            total_score += ac_score * ac_weight
            total_weight += ac_weight
        
        # ATK and Haste (percentages)
        if scores.get('atk_pct') is not None:
            weight = weights_config.get('atk_pct', 0.0)
            if weight > 0:
                total_score += scores['atk_pct'] * weight
                total_weight += weight
        if scores.get('haste_pct') is not None:
            weight = weights_config.get('haste_pct', 0.0)
            if weight > 0:
                total_score += scores['haste_pct'] * weight
                total_weight += weight
        
        # Resists - calculate individual resist scores with weight curve
        resists_weight = weights_config.get('resists_pct', 0.0)
        if resists_weight > 0:
            individual_resists = char.get('individual_resists', {})
            if individual_resists:
                # Calculate individual resist scores
                # The curve weight multiplies the base resists_weight
                resist_scores = {}
                total_resist_score = 0.0
                total_resist_weight = 0.0
                
                for resist_type, resist_value in individual_resists.items():
                    score, curve_weight = calculate_resist_score(resist_value)
                    # The effective weight is base resists_weight multiplied by the curve weight
                    effective_weight = resists_weight * curve_weight
                    resist_scores[resist_type] = {
                        'value': resist_value,
                        'score': score,
                        'weight': curve_weight  # Store curve weight for display, but use effective_weight in calculation
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
                total_score += avg_resist_score * total_resist_weight
                total_weight += total_resist_weight
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
                focus_score = scores.get('focus_overall_pct', 0)
                # Sum all focus weights to get total focus weight
                total_focus_weight = 0.0
                for focus_cat, weight_config in focus_weights.items():
                    if isinstance(weight_config, dict):
                        total_focus_weight += sum(weight_config.values())
                    else:
                        total_focus_weight += weight_config
                if total_focus_weight > 0:
                    total_score += focus_score * total_focus_weight
                    total_weight += total_focus_weight
            elif char_class == 'Paladin':
                # Handle Paladin focuses individually with their specific weights
                # Shield of Strife (2.0), Beneficial Spell Haste (0.75), Healing Enhancement (0.5)
                for focus_cat, weight_config in focus_weights.items():
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
                    # Beneficial Spell Haste is handled in the main focus loop below
            elif char_class == 'Enchanter':
                # Handle Enchanter focuses individually (Serpent of Vindication + spell focuses)
                for focus_cat, weight_config in focus_weights.items():
                    if focus_cat == 'Serpent of Vindication':
                        if isinstance(weight_config, (int, float)) and weight_config > 0:
                            serpent_score = focus_scores.get('Serpent of Vindication', 0)
                            total_score += serpent_score * weight_config
                            total_weight += weight_config
                    # Other focuses (Spell Damage, Spell Mana Efficiency, etc.) handled in main loop below
            else:
                # For other classes, use focus_overall_pct
                focus_score = scores.get('focus_overall_pct', 0)
                # Sum all focus weights to get total focus weight
                total_focus_weight = 0.0
                for focus_cat, weight_config in focus_weights.items():
                    if isinstance(weight_config, dict):
                        total_focus_weight += sum(weight_config.values())
                    else:
                        total_focus_weight += weight_config
                if total_focus_weight > 0:
                    total_score += focus_score * total_focus_weight
                    total_weight += total_focus_weight
        
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
        hp_score = (hp_value / max_combined * 100) if hp_value > 0 else 0
        scores['hp_pct'] = hp_score  # Store percentage for display
        total_score += hp_score * hp_weight
        total_weight += hp_weight
    
    mana_weight = weights_config.get('mana_pct', 0.0)
    if mana_weight > 0 and max_combined > 0 and mana_value > 0:
        mana_score = (mana_value / max_combined * 100) if mana_value > 0 else 0
        scores['mana_pct'] = mana_score  # Store percentage for display
        total_score += mana_score * mana_weight
        total_weight += mana_weight
    
    # FT (Flowing Thought) - capped (15/15) is worth 2.0 weight
    if scores.get('ft_capped') is True:
        ft_weight = 2.0
        total_score += 100.0 * ft_weight  # 100% for capped
        total_weight += ft_weight
    
    # AC, ATK, Haste (if applicable)
    if scores.get('ac') is not None:
        weight = weights_config.get('ac_pct', 0.0)
        if weight > 0:
            max_ac = class_max_values.get('max_ac', 1)
            ac_value = scores.get('ac', 0)
            ac_score = (ac_value / max_ac * 100) if max_ac > 0 and ac_value > 0 else 0
            scores['ac_pct'] = ac_score  # Store percentage for display
            total_score += ac_score * weight
            total_weight += weight
    
    if scores.get('atk_pct') is not None:
        weight = weights_config.get('atk_pct', 0.0)
        if weight > 0:
            total_score += scores['atk_pct'] * weight
            total_weight += weight
    
    if scores.get('haste_pct') is not None:
        weight = weights_config.get('haste_pct', 0.0)
        if weight > 0:
            total_score += scores['haste_pct'] * weight
            total_weight += weight
    
        # Resists - calculate individual resist scores with weight curve
        resists_weight = weights_config.get('resists_pct', 0.0)
        if resists_weight > 0:
            individual_resists = char.get('individual_resists', {})
            if individual_resists:
                # Calculate individual resist scores
                # The curve weight multiplies the base resists_weight
                resist_scores = {}
                total_resist_score = 0.0
                total_resist_weight = 0.0
                
                for resist_type, resist_value in individual_resists.items():
                    score, curve_weight = calculate_resist_score(resist_value)
                    # The effective weight is base resists_weight multiplied by the curve weight
                    effective_weight = resists_weight * curve_weight
                    resist_scores[resist_type] = {
                        'value': resist_value,
                        'score': score,
                        'weight': curve_weight  # Store curve weight for display, but use effective_weight in calculation
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
                total_score += avg_resist_score * total_resist_weight
                total_weight += total_resist_weight
            else:
                # Fallback to total resists if individual not available
                max_resists = class_max_values.get('max_resists', 1)
                resists_value = scores.get('resists', 0)
                if max_resists > 0:
                    resists_score = (resists_value / max_resists * 100) if resists_value > 0 else 0
                    scores['resists_pct'] = resists_score
                    total_score += resists_score * resists_weight
                    total_weight += resists_weight
    
    # Focus weights - each focus gets the proportional weight specified
    focus_weights = weights_config.get('focus', {})
    if focus_weights:
        best_spell_damage = best_focii.get('Spell Damage', 35.0)
        
        for focus_cat, weight_config in focus_weights.items():
            if focus_cat == 'Spell Damage':
                # Handle damage type specific weights
                # "All" damage counts for all damage types
                if isinstance(weight_config, dict):
                    for damage_type, weight in weight_config.items():
                        if weight > 0:
                            # Get the character's focus percentage for this damage type
                            # "All" counts for all damage types, so use max of specific type and "All"
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
            elif focus_cat in ['Beneficial Spell Duration', 'Detrimental Spell Duration', 'All Spell Duration']:
                # Handle duration categories - look up from char_duration_cats
                # "All" categories count for both Bene and Det
                if isinstance(weight_config, (int, float)) and weight_config > 0:
                    if char_duration_cats:
                        if focus_cat == 'All Spell Duration':
                            char_pct = char_duration_cats.get('All', 0)
                            best_duration = best_focii.get('All Spell Duration', 15.0)
                        elif focus_cat == 'Beneficial Spell Duration':
                            # Use max of Bene and All (All counts for both)
                            char_pct = max(
                                char_duration_cats.get('Bene', 0),
                                char_duration_cats.get('All', 0)
                            )
                            best_duration = max(
                                best_focii.get('Buff Spell Duration', 25.0),
                                best_focii.get('All Spell Duration', 15.0)
                            )
                        else:  # Detrimental Spell Duration
                            # Use max of Det and All (All counts for both)
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
            elif focus_cat == 'Spell Mana Efficiency':
                # Handle Spell Mana Efficiency - class-specific category selection
                if isinstance(weight_config, (int, float)) and weight_config > 0:
                    if char_mana_efficiency_cats:
                        # For Clerics, use Beneficial (Bene) instead of Nuke
                        if char_class == 'Cleric':
                            char_pct = char_mana_efficiency_cats.get('Bene', 0)
                            # If no Bene, try to get the best available (prefer Bene > Det > Nuke)
                            if char_pct == 0:
                                char_pct = max(
                                    char_mana_efficiency_cats.get('Bene', 0),
                                    char_mana_efficiency_cats.get('Det', 0),
                                    char_mana_efficiency_cats.get('Nuke', 0)
                                )
                        else:
                            # For other classes, use the best available category
                            char_pct = max(
                                char_mana_efficiency_cats.get('Nuke', 0),
                                char_mana_efficiency_cats.get('Det', 0),
                                char_mana_efficiency_cats.get('Bene', 0)
                            )
                        
                        best_mana_eff = best_focii.get('Spell Mana Efficiency', 40.0)
                        if best_mana_eff > 0:
                            focus_score = (char_pct / best_mana_eff * 100) if char_pct > 0 else 0
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
    
    # Load characters
    characters = {}
    with open(char_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            if row['level'] == '65':
                char_id = row['id']
                try:
                    def safe_int(value, default=0):
                        if not value or value == 'NULL' or value == '':
                            return default
                        try:
                            return int(value)
                        except (ValueError, TypeError):
                            return default
                    
                    # Parse FT (Flowing Thought) - mana_regen_item / mana_regen_item_cap
                    ft_current = safe_int(row.get('mana_regen_item', 0))
                    ft_cap = safe_int(row.get('mana_regen_item_cap', 15))
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
    
    # Load inventory
    print("Loading inventory data...")
    inventory = {}
    with open(inv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            char_id = row['id']
            slot_id = int(row['slot_id'])
            
            if char_id in characters and 1 <= slot_id <= 22:  # Worn slots
                if char_id not in inventory:
                    inventory[char_id] = []
                inventory[char_id].append({
                    'item_id': row['item_id'],
                    'item_name': row['item_name'],
                    'slot_id': slot_id
                })
    
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
                'max_ac': max(c['stats']['ac'] for c in class_chars) if char_class in CLASSES_NEED_AC else 0,
                'max_resists': max(c.get('stats', {}).get('resists', 0) for c in class_chars),
            }
    
    for char_id, char_data in characters.items():
        char_class = char_data['class']
        char_inventory = inventory.get(char_id, [])
        char_focii, char_damage_focii, char_mana_efficiency_cats, char_spell_haste_cats, char_duration_cats = analyze_character_focii(char_inventory, focus_lookup)
        scores = calculate_class_scores(char_data, char_focii, char_damage_focii, best_focii, chars_by_class, char_inventory, char_spell_haste_cats)
        
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
            None,  # char_mana_efficiency_cats (not used in this function)
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
            'scores': scores,  # Percentage scores
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
    output_file = 'class_rankings.json'
    output = {
        'characters': output_data,
        'class_weights': CLASS_WEIGHTS
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
