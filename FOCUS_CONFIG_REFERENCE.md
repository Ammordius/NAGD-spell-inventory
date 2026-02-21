# Focus configuration – all classes (single reference)

**Edit in code:** `generate_class_rankings.py`  
- **Priorities (order for focus_overall_pct):** `CLASS_FOCUS_PRIORITIES` ~line 364  
- **Weights (scoring):** `CLASS_WEIGHTS` → each class’s `focus` dict ~line 918  

---

## Spell Haste “All” → both Bene and Det

Yes. Where Beneficial or Detrimental spell haste is scored we use:

- **Beneficial:** `max(char_spell_haste_cats['Bene'], char_spell_haste_cats['All'])`
- **Detrimental:** `max(char_spell_haste_cats['Det'], char_spell_haste_cats['All'])`

So any focus tracked as **All** (in `SPELL_HASTE_CATEGORY_MAP`) counts for **both** Beneficial and Detrimental. Right now no focus name is mapped to `'All'`; only Det/Bene are used. To support an “all spell haste” focus, add it in `SPELL_HASTE_CATEGORY_MAP` with value `'All'` and ensure `get_best_focii_by_subcategory` and `analyze_character_focii` handle the `'All'` haste category.

---

## CLASS_FOCUS_PRIORITIES (order for focus_overall_pct)

| Class       | Priorities (first = highest weight in average) |
|------------|--------------------------------------------------|
| Necromancer | Spell Damage (All), (DoT), (Disease), Spell Mana Efficiency, Spell Haste, Detrimental Spell Duration |
| Shaman      | Spell Damage (Cold), (DoT), (Disease), Healing Enhancement, Spell Mana Efficiency, Buff Spell Duration |
| Druid       | Healing Enhancement, Spell Damage (Fire), (Cold), Spell Mana Efficiency, Buff Spell Duration |
| Cleric      | Healing Enhancement, Spell Damage (Magic), Spell Mana Efficiency, Buff Spell Duration |
| Wizard      | Spell Damage (Fire), (Cold), (Magic), Spell Mana Efficiency, Spell Haste |
| Magician    | Spell Damage (Fire), (Magic), Spell Mana Efficiency, Spell Haste |
| Enchanter   | Spell Damage (Magic), Spell Mana Efficiency, Spell Haste, Buff Spell Duration |
| Bard        | Brass, Percussion, Singing, Strings, Wind |

---

## CLASS_WEIGHTS.focus (scoring weights per class)

| Class        | Focus weights (name: weight) |
|-------------|------------------------------|
| **Warrior** | ATK 1.0, Haste 1.0, Darkblade 1.0, Raex Chest 1.0 |
| **Monk**    | ATK 1.0 |
| **Rogue**   | ATK 1.0 |
| **Shadow Knight** | Haste 0.75, ATK 0.75, Spell Mana Efficiency 0.5, Shield of Strife 2.0, FT 1.0 |
| **Paladin** | ATK 0.5, FT 1.0, Haste 0.5, Beneficial Spell Haste 0.75, Healing Enhancement 0.5, Shield of Strife 2.0, Spell Mana Efficiency 0.5 |
| **Wizard**  | FT 4.0, Spell Damage {Fire 1.0, Cold 1.0, Magic 0.5}, Spell Mana Efficiency 1.0, Detrimental Spell Haste 1.0, Detrimental Spell Duration 0.75, Spell Range Extension 0.5 |
| **Cleric**  | FT 4.0, Spell Damage {Magic 0.5}, Healing Enhancement 2.0, Spell Mana Efficiency 1.0, Spell Range Extension 0.5, Buff Spell Duration 1.0, Beneficial Spell Haste 1.0 |
| **Magician**| FT 4.0, Spell Damage {Fire 1.0, Magic 0.5}, Spell Mana Efficiency 1.0, Detrimental Spell Haste 1.0, Detrimental Spell Duration 0.75, Spell Range Extension 0.5 |
| **Necromancer** | FT 4.0, Spell Damage {All 0.75, DoT 1.0, Disease 1.0}, Spell Mana Efficiency 1.0, Detrimental Spell Duration 1.0, Detrimental Spell Haste 1.0, Spell Range Extension 0.5 |
| **Shaman**  | FT 4.0, Spell Damage {DoT 4.0, Cold 1.0}, Healing Enhancement 1.0, Spell Mana Efficiency 1.0, Detrimental Spell Haste 0.75, Buff Spell Duration 1.0, Detrimental Spell Duration 1.0, All Spell Duration 1.0, Spell Range Extension 0.5, Time's Antithesis 2.0 |
| **Enchanter** | FT 4.0, Spell Damage {Magic 0.5}, Spell Mana Efficiency 1.0, Buff Spell Duration 1.0, Detrimental Spell Duration 1.0, Detrimental Spell Haste 1.0, Spell Range Extension 0.75, Serpent of Vindication 2.0 |
| **Beastlord** | ATK 1.0, FT 1.0, Spell Damage {Cold 0.5}, Healing Enhancement 0.75, Spell Mana Efficiency 1.0, Beneficial Spell Haste 0.75, Detrimental Spell Haste 0.75 |
| **Druid**   | FT 4.0, Spell Damage {Fire 1.0, Cold 1.0}, Healing Enhancement 1.0, Spell Mana Efficiency 1.0, Beneficial Spell Haste 1.0, Detrimental Spell Haste 0.75, Detrimental Spell Duration 0.5, Buff Spell Duration 1.0, Spell Range Extension 0.5 |
| **Ranger**  | ATK 1.0, FT 1.0 |
| **Bard**    | ATK 4.0, FT 4.0, Haste 4.0, Brass 4.0, Percussion 4.0, Singing 4.0, Strings 4.0, Wind 4.0 |

---

## Category maps (which focus names → Bene/Det/All/etc.)

- **Spell Mana Efficiency:** `SPELL_MANA_EFFICIENCY_CATEGORY_MAP` ~line 248 (Det, Bene, Nuke, Sanguine). Sanguine = self-only; weight 0 for most classes.
- **Spell Haste:** `SPELL_HASTE_CATEGORY_MAP` ~line 276 (Det, Bene). Add `'Focus Name': 'All'` to have a focus count for both.
- **Spell Duration:** Buff/Detrimental/All Spell Duration; “All Spell Duration” is tracked as `All` and counts for both Buff (Bene) and Detrimental (Det) in scoring.
- **Spell Mana Efficiency weights per class:** `SPELL_MANA_EFFICIENCY_WEIGHTS` ~line 311 (e.g. Enchanter Det 1.0, Bene 0.25).
