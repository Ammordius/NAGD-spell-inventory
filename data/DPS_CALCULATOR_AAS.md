# DPS Calculator – AAs and Class Mechanics

## Innate / skill (not AAs)

- **Triple Attack** – Warrior and Monk at level 60+: 13.5% chance for one extra primary-hand swing per round. Implemented in the calculator for both classes; no AA toggle.
- **Flurry** – In server code, Flurry is an **AA** that grants `FlurryChance`; when Triple Attack fires, Flurry can add 1–2 more primary-hand swings. Only **Warrior** has the Flurry AA line in TAKP; Monk gets Triple Attack but not Flurry.

## AAs currently in `dps_config.json` (per class)

Only DPS-relevant AAs are included. Combat Stability (mitigation) is omitted. Return Kick is Monk-only (DB classes=128).

| Class        | AAs in config |
|-------------|----------------|
| **Warrior** | Ferocity, Flurry, Raging Flurry, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Tactical Mastery (Strikethrough) |
| **Rogue**   | Ambidexterity, Combat Agility, Double Riposte, Sinister Strikes, Chaotic Stab |
| **Monk**    | Ambidexterity, Combat Agility, Return Kick, Double Riposte, Punishing Blade |
| **Ranger**  | Archery Mastery, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Precision of the Pathfinder |
| **Paladin** | Knight's Advantage, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Speed of the Knight |
| **Shadow Knight** | Knight's Advantage, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Speed of the Knight |
| **Bard**    | Ambidexterity, Combat Agility |
| **Beastlord** | Bestial Frenzy, Harmonious Attack, Ambidexterity, Combat Agility |

## Riposte / tank DPS (planned)

When **tanking**, DPS includes ripostes: the mob swings at you, you have a chance to riposte (and double riposte). To model that we need a **riposte calculator** with its own toggle (e.g. “Include riposte DPS when tanking”), driven by:

- **Mob attack delay** – how often the mob swings (and thus how many riposte opportunities per second)
- **Player riposte chance** – from defense skill, level, and **Return Kick** AA (Monk) if applicable
- **Dual wield** – more riposte chances when the mob dual-wields (two attacks per round)
- **Mob triple attack / flurry** – more attacks from the mob → more riposte rolls
- **Double Riposte** (and Flash of Steel) – chance to get two ripostes off one defensive round

So total tank DPS = **melee DPS** (current calculator) + **riposte DPS** (mob swings × riposte chance × damage per riposte × (1 + double riposte chance)). This will be a separate toggle and inputs (mob delay, mob dual wield, etc.) to be added.

## Still to verify / investigate

- Sinister Strikes (Rogue) – confirm skill_id / effect in canonical export if present.
- Flash of Steel (same classes as Double Riposte) – effect 223 base1=30; server takes max of GiveDoubleRiposte[0], so 50 from Double Riposte already covers; no separate config entry needed.

## Source of truth

- **Server**: `zone/client_process.cpp` (Triple Attack 13.5%, Flurry after triple), `zone/aa.h` (AA IDs), `zone/common.h` (bonus names, e.g. `FlurryChance`).
- **TAKP DB**: `altadv_vars` + `aa_effects` via `Server/utils/sql/aa_list_canonical.sql` (run `run_aa_canonical.ps1`). Values in `dps_config.json` are from this canonical export.

**Canonical values (max rank, from DB):** FlurryChance 30 (+ Raging Flurry 7), DoubleAttackChance (Ferocity/Knight's Advantage) 9, Ambidexterity 32, Combat Agility 10, RiposteChance (Return Kick, Monk only) 60, GiveDoubleRiposte0 50, StrikeThrough (Tactical Mastery) 45, **ExtraAttackChance (Punishing Blade / Speed of the Knight) 8 each**, ArcheryDamageModifier 100, AccuracyAll (Precision Pathfinder) 30, GiveDoubleAttack (Bestial/Harmonious) 15. Combat Stability omitted (not DPS).
