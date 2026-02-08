# Character Ranking Score Explanation

This document explains how character rankings are calculated for the TAKP level 65 character rankings page.

## Overview

Each character receives an overall score (0-100%) based on their stats, resists, and spell focuses. The scoring system is **class-specific**, meaning different classes are evaluated based on what matters most for their role.

## Stat Scoring

### HP (Hit Points)
- **All classes**: HP is always weighted
- **Tanks (Warrior, Paladin, Shadow Knight)**: HP is converted to AC-equivalent (5 HP = 1 AC) for comparison
- **Casters**: HP is on the same scale as Mana (1 HP = 1 Mana)

### Mana
- **Only for classes with mana**: Cleric, Druid, Shaman, Necromancer, Wizard, Enchanter, Magician, Beastlord, Ranger, Paladin, Shadow Knight
- **Casters**: Mana is on the same scale as HP (1 HP = 1 Mana)

### AC (Armor Class)
- **Only for tank/hybrid classes**: Warrior, Paladin, Shadow Knight, Beastlord, Ranger
- **Tanks**: AC is converted from HP (5 HP = 1 AC) for comparison

### ATK (Attack)
- **Only for melee/hybrid classes**: Warrior, Paladin, Shadow Knight, Monk, Rogue, Ranger, Beastlord, Bard
- **Scoring**: Percentage of 250 ATK cap (e.g., 250/250 = 100%)

### Resists
- **All classes**: Total of all 5 resists (MR, FR, CR, DR, PR)
- **Scoring**: Percentage relative to the best in class

### FT (Flowing Thought)
- **Only for casters and bards**: Cleric, Druid, Shaman, Necromancer, Wizard, Enchanter, Magician, Beastlord, Ranger, Bard
- **Scoring**: If capped (15/15), worth 2.0 weight in stat priority

## Focus Scoring

Focus scoring is **class-specific** and varies significantly by class. Each class has different focus priorities based on their role.

### Focus Weight System

1. **Total focus weight = 3x HP weight**: The combined weight of all focuses equals 3 times the HP weight
2. **Individual focus weights**: Each focus category has a specific weight within that total
3. **Normalization**: All weights are normalized so each class's total priorities sum to 1.0

### Class-Specific Focus Priorities

#### Warriors
- **Focus Items**: Darkblade of the Warlord (Main Hand) + Raex's Chestplate of Destruction (Chest)
- **Haste**: Binary check (100% if >= 30% item haste, 0% otherwise)
- **Weight**: Combined focus weight = 3x HP weight

#### Paladins
- **Shield of Strife**: 2.0 weight
- **Beneficial Spell Haste**: 0.75 weight
- **Healing Enhancement**: 0.5 weight

#### Shadow Knights
- **Shield of Strife**: Binary check (100% if present, 0% otherwise)

#### Casters (Cleric, Druid, Shaman, Necromancer, Wizard, Enchanter, Magician)
Each caster class has specific focus priorities:

- **Spell Damage**: Class-specific damage types (e.g., Necro wants Disease/DoT, Wizard wants Fire/Cold/Magic)
- **Spell Mana Efficiency**: Categorized as Nuke, Detrimental, Beneficial, or Sanguine (self-only, not displayed)
- **Spell Haste**: Categorized as Beneficial or Detrimental
- **Spell Duration**: Categorized as Beneficial, Detrimental, or All
- **Healing Enhancement**: For healing classes
- **Spell Range Extension**: For classes that benefit from extended range

#### Hybrid Classes (Ranger, Beastlord, Bard)
- **Ranger**: Mix of melee stats (ATK, AC) and spell focuses
- **Beastlord**: Mix of melee stats and spell focuses, with specific detrimental spell haste cap (27.5% effective, due to innate abilities)
- **Bard**: Mix of melee stats and spell focuses

### Focus Categories

#### Mana Efficiency Categories
- **Nuke**: Direct damage spells
- **Detrimental**: Harmful spells (DoTs, debuffs)
- **Beneficial**: Helpful spells (buffs, heals)
- **Sanguine**: Self-only (not displayed in rankings)

#### Spell Haste Categories
- **Beneficial**: Buffs, heals
- **Detrimental**: DoTs, debuffs, nukes

#### Duration Categories
- **Beneficial**: Buff duration
- **Detrimental**: DoT/debuff duration
- **All**: Applies to both beneficial and detrimental

## Overall Score Calculation

1. **Stat scores** are calculated as percentages relative to the best in class
2. **Focus scores** are calculated as percentages relative to the best focus in each category
3. **Weighted average**: Each stat and focus is multiplied by its weight
4. **Normalization**: All weights are normalized so they sum to 1.0 for fair cross-class comparison
5. **Final score**: Weighted sum of all applicable stats and focuses

## Example: Cleric Scoring

A Cleric's score is calculated from:
- HP (weight: normalized)
- Mana (weight: normalized)
- Resists (weight: 1.0)
- Healing Enhancement (weight: 2.0, within focus total)
- Beneficial Spell Haste (weight: 1.0, within focus total)
- Spell Range Extension (weight: 1.0, within focus total)
- Spell Mana Efficiency (weight: varies by category, within focus total)

The focus weights total 3x the HP weight, then all weights are normalized to sum to 1.0.

## Notes

- **Pure melees** (Warrior, Monk, Rogue) don't have spell focuses displayed
- **Focus percentages** shown are relative to the best-in-slot focus for that category
- **Class-specific damage types** are weighted differently (e.g., Necro's Disease focus is more important than Fire)
- **Beastlord detrimental spell haste** is capped at 27.5% effective (50% total cap - 22.5% innate)

## Viewing Your Score Breakdown

Click on any character in the rankings table to see a detailed breakdown of:
- Individual stat scores and weights
- Individual focus scores and weights
- Equipped items with links to TAKP item pages
