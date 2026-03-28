# DPS Calculator – Threat / hate (TAKP Server reference)

This document ties the magelo **server-derived threat** tooling to EQEmu/TAKP server code. Use it when interpreting `spells_threat.json`, `weapon_threat_server.json`, and `compare_threat_meriadoc.py` output.

## Melee hate (player → NPC)

- **Source:** `Server/zone/attack.cpp` — client combat path: `hate = baseDamage + damageBonus` where `damageBonus = GetDamageBonus()` **only for primary hand**; offhand swings add **base damage only** (no character damage bonus to hate on that swing).
- **Per swing:** Hate is generated **for every swing** (hit, miss, dodge, etc.), not scaled by hit rate or crit damage. Rolled melee damage goes through `Damage()` / `CommonDamage()` into the hatelist **damage** bucket, which is **not** added to the `hate` value used for NPC target selection (see below).

## Hate list: `hate` vs `damage`

- **Source:** `Server/zone/hate_list.cpp` — `HateList::Add` stores `in_hate` and `in_dam` separately. `GetEntHate` / `GetTop` use **`hate` + proximity bonuses**, not `damage`.
- **Implication:** Spreadsheet models that equate **melee threat with expected DPS** can disagree with this server: crit magnitude and “damage dealt” do not increase the `hate` field for melee the way spell `CheckAggroAmount` uses spell-file DD values.

## Spell / proc offensive hate

- **Source:** `Server/zone/aggro.cpp` — `Mob::CheckAggroAmount`
- **Summary:** Sums **non-damage** hate from control/debuff effects (scaled by `standardSpellHate = clamp(target_max_hp / 15, min 375/15, max 1200)`), **negative HP** effects as a damage component, **`SE_InstantHate`**, optional **`HateAdded`** override, **pet** and **bard** caps, **400 cap** on non-damage hate for non–class-castable spells unless the spell is the equipped weapon proc (see server condition with `GetWeaponEffectID`).
- **Multiplier:** `combinedHate = (nonDamage + damageFromEffects) * SpellAggroMod / 100` plus focus / `hatemod` bonuses (calculator defaults: 100, no focus).

## Weapon proc chance

- **Source:** `Server/zone/attack.cpp` — `GetProcChance`, `TryWeaponProc`
- **Main hand:** `chance = (0.0004166667 + 1.1437908496732e-5 * min(DEX,255)) * (weapon_delay/100)` (fraction per swing). **OH:** multiply by `50 / DualWieldChance`.
- **DB modifier:** `WPC = chance * (100 + item.ProcRate) / 100`, then `Roll(WPC)` (uniform [0,1], success if `<= WPC`).

## Data files in magelo

| File | Purpose |
|------|---------|
| [data/spells_threat.json](spells_threat.json) | Subset of `spells_new`/`spells_en` columns needed for `CheckAggroAmount` (built by `scripts/build_spells_threat_json.py` from Server SQL dumps). |
| [data/item_proc_meta.json](item_proc_meta.json) | Optional `item_id → { procrate, proclevel, proceffect }` from live DB (`scripts/threat/sql/export_item_proc_meta.sql`). If empty, proc rate modifier defaults to **0**. |
| [data/weapon_threat_server.json](weapon_threat_server.json) | Precomputed per-weapon server-model hate/sec for the DPS calculator toggle (`scripts/build_weapon_threat_server.py`). |

## Assumptions for default numbers

- **Caster level:** 65  
- **Target max HP:** 1,000,000 (raid benchmark; change in scripts for sensitivity).  
- **Class for proc caps / bard rules:** Warrior (1).  
- **DEX for proc chance:** 255 (matches capped server behavior).  
- **Shadows of Luclin disease-counter rule:** disabled (matches pre-SoL branch in `CheckAggroAmount`).  
- **Scars of Velious epic instant-hate override:** disabled unless you enable it in Python options.

## Meriadoc comparison

[Meriadoc’s TAKP Weapon Chart](https://docs.google.com/spreadsheets/d/1YA6WAkCKPdytNOsdeoxicv7_ng2BZviwSdAG7GNn1-Y/) supplies `meleeHatePerSec` / `hatePerSec` in [data/weapon_procs.json](weapon_procs.json). Differences often trace to: (1) melee hate tied to DPS vs fixed per-swing hate, (2) proc hate using spreadsheet DPS coupling, (3) benchmark target HP for `standardSpellHate`, (4) missing `procrate` in `item_proc_meta.json`.

See also: [DPS_CALCULATOR_AAS.md](DPS_CALCULATOR_AAS.md) for melee DPS mechanics.
