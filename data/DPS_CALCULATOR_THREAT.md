# DPS Calculator – Threat / hate (TAKP Server reference)

This document ties the magelo **server-derived threat** tooling to EQEmu/TAKP server code. Use it when interpreting `spells_threat.json`, `weapon_threat_server.json`, and (for QA) `compare_threat_meriadoc.py` output.

## Melee hate (player → NPC)

- **Source:** `Server/zone/attack.cpp` — client combat path: `hate = baseDamage + damageBonus` where `damageBonus = GetDamageBonus()` **only for primary hand**; offhand swings add **base damage only** (no character damage bonus to hate on that swing).
- **Per swing:** Hate is generated **for every swing** (hit, miss, dodge, etc.), not scaled by hit rate or crit damage. Rolled melee damage goes through `Damage()` / `CommonDamage()` into the hatelist **damage** bucket, which is **not** added to the `hate` value used for NPC target selection (see below).

## Bard: melee and proc hate in the calculator

- **Primary-hand melee hate:** `weapon_threat_server.json` is built with **Warrior** per-swing primary hate (`baseDamage + GetDamageBonus()`). Bards do **not** get that innate damage bonus on primary swings (same as DPS: no warrior `damageBonus` on damage). For **Bard**, the calculator scales main-hand melee hate from the table by `weaponDmg / (weaponDmg + warriorPrimaryDB)` (1H vs 2H DB matches `attack.cpp` / `melee_proc.py`). Off-hand melee hate is unchanged (offhand hate is base damage only for everyone).
- **Proc hate:** The JSON includes `hatePerSecServerBard` / `hatePerSecOHServerBard`, from `CheckAggroAmount` with the bard branch in `aggro.cpp` (non-damage hate interacts with the **40** cap before instant hate is added). Pure direct-damage procs often match the warrior-line numbers; procs with stun/slow/debuff hate diverge. If bard columns are absent (old file), the calculator falls back to `hatePerSecServer` / `hatePerSecOHServer`.

## Hate list: `hate` vs `damage`

- **Source:** `Server/zone/hate_list.cpp` — `HateList::Add` stores `in_hate` and `in_dam` separately. `GetEntHate` / `GetTop` use **`hate` + proximity bonuses**, not `damage`.
- **Implication:** Spreadsheet models that equate **melee threat with expected DPS** can disagree with this server: crit magnitude and “damage dealt” do not increase the `hate` field for melee the way spell `CheckAggroAmount` uses spell-file DD values.

## Spell / proc offensive hate

- **Source:** `Server/zone/aggro.cpp` — `Mob::CheckAggroAmount`
- **Summary:** Sums **non-damage** hate from control/debuff effects (scaled by `standardSpellHate = clamp(target_max_hp / 15, min 375/15, max 1200)`), **negative HP** effects as a damage component, **`SE_InstantHate`**, optional **`HateAdded`** override, **pet** and **bard** caps, **400 cap** on non-damage hate for non–class-castable spells before adding instant hate and DD hate. On the live server this cap can be skipped when the proc matches the equipped weapon (`GetWeaponEffectID`); **magelo always applies the cap** for weapon proc hate in `weapon_threat_server.json` (conservative path: 400 + instant + DD).
- **Multiplier:** `combinedHate = (nonDamage + damageFromEffects) * SpellAggroMod / 100` plus focus / `hatemod` bonuses (calculator defaults: 100, no focus).

## Weapon proc chance

- **Source:** `Server/zone/attack.cpp` — `GetProcChance`, `TryWeaponProc`
- **Main hand:** `chance = (0.0004166667 + 1.1437908496732e-5 * min(DEX,255)) * (weapon_delay/100)` (fraction per swing). **OH:** multiply by `50 / DualWieldChance`.
- **DB modifier:** `WPC = chance * (100 + item.ProcRate) / 100`, then `Roll(WPC)` (uniform [0,1], success if `<= WPC`).

## Data files in magelo

| File | Purpose |
|------|---------|
| [data/spells_threat.json](spells_threat.json) | Subset of `spells_new`/`spells_en` columns needed for `CheckAggroAmount` (built by `scripts/build_spells_threat_json.py` from Server SQL dumps). |
| [data/item_proc_meta.json](item_proc_meta.json) | `item_id → { procrate, proclevel, proceffect }` from your **`items`** table. Generate with `python scripts/export_item_proc_meta.py --from-mysql --mysql-database YOUR_DB` (or `--from-tsv` after running `scripts/threat/sql/export_item_proc_meta.sql`). If an item is missing, `procrate` defaults to **0** (underestimates proc frequency). Re-run `scripts/build_weapon_threat_server.py` after updating this file. |
| [data/weapon_threat_server.json](weapon_threat_server.json) | Precomputed per-weapon server-model melee + proc **hate/sec** for the DPS calculator (`scripts/build_weapon_threat_server.py`). Includes Warrior-line fields (`meleeHatePerSecServer`, `hatePerSecServer`, OH variants) and Bard proc lines (`hatePerSecServerBard`, `hatePerSecOHServerBard`). |
| [data/weapon_procs.json](weapon_procs.json) | Per-weapon **proc DPS** (and optional legacy hate columns). The calculator always uses `weapon_threat_server.json` for displayed hate when the weapon key exists; proc DPS is read from `procDps` / `procDpsOH` here. |

## Assumptions for default numbers

- **Caster level:** 65  
- **Target max HP:** 1,000,000 (raid benchmark; change in scripts for sensitivity).  
- **Class for proc caps in the build script:** Warrior (`class_id=1`) for the generic proc line; bard-specific proc hate uses `is_bard=True` in `check_aggro_amount` for the `*Bard` JSON fields.  
- **DEX for proc chance:** 255 (matches capped server behavior).  
- **Shadows of Luclin disease-counter rule:** disabled (matches pre-SoL branch in `CheckAggroAmount`).  
- **Scars of Velious epic instant-hate override:** disabled unless you enable it in Python options.

## Legacy spreadsheet comparison

Older third-party weapon charts coupled melee threat to expected DPS and used different proc assumptions. The calculator’s **authoritative** hate numbers are `weapon_threat_server.json` (fixed per-swing melee hate, `CheckAggroAmount` for procs). For regression checks against legacy columns still present in `weapon_procs.json`, see `scripts/compare_threat_meriadoc.py` and [threat_compare_summary.md](threat_compare_summary.md).

**Proc hate:** Meriadoc-style `hatePerSec` often diverges from magelo’s **capped** proc model (400 non-damage + instant + DD for non-castable procs like Anger). Use the comparison report for **proc** vs **melee** deltas (`delta_proc_mh`, `delta_proc_oh`).

## Refresh pipeline (repo maintainers)

1. Export proc modifiers: `python scripts/export_item_proc_meta.py --from-mysql --mysql-database peq` (use your TAKP DB name if it differs from stock PEQ).
2. Rebuild threat JSON: `python scripts/build_weapon_threat_server.py`
3. Refresh Meriadoc diff: `python scripts/compare_threat_meriadoc.py`

## DPS vs log parses (Bard and others)

Reported **Total DPS** in many parsers is `total damage ÷ entire encounter time`. The calculator models **steady melee + proc** at **100% melee uptime** (no song twisting, movement gaps, or out-of-combat clock time). Session-wide DPS can sit far below that ceiling even when hit rate, swings/sec, and average hit match—use the same time basis when comparing.

See also: [DPS_CALCULATOR_AAS.md](DPS_CALCULATOR_AAS.md) for melee DPS mechanics.
