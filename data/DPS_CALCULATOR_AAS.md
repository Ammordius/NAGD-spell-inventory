# DPS Calculator – AAs and Class Mechanics

## Innate / skill (not AAs)

- **Triple Attack** – Warrior and Monk at level 60+: 13.5% chance for one extra primary-hand swing per round. Implemented in the calculator for both classes; no AA toggle.
- **Flurry** – In server code, Flurry is an **AA** that grants `FlurryChance`; when Triple Attack fires, Flurry can add 1–2 more primary-hand swings. Only **Warrior** has the Flurry AA line in TAKP; Monk gets Triple Attack but not Flurry.

## AAs currently in `dps_config.json` (per class)

Only DPS-relevant AAs are included. Combat Stability (mitigation) is omitted. Return Kick is Monk-only (DB classes=128).

| Class        | AAs in config |
|-------------|----------------|
| **Warrior** | Ferocity, Flurry, Raging Flurry, Ambidexterity, Combat Agility, Double Riposte, Tactical Mastery (Strikethrough) |
| **Rogue**   | Ambidexterity, Combat Agility, Double Riposte, Sinister Strikes, Chaotic Stab |
| **Monk**    | Ambidexterity, Combat Agility, Return Kick, Double Riposte |
| **Ranger**  | Archery Mastery, Ambidexterity, Combat Agility, Double Riposte, Precision of the Pathfinder |
| **Paladin** | Knight's Advantage, Ambidexterity, Combat Agility, Double Riposte |
| **Shadow Knight** | Knight's Advantage, Ambidexterity, Combat Agility, Double Riposte |
| **Bard**    | Ambidexterity, Combat Agility |
| **Beastlord** | Bestial Frenzy, Harmonious Attack, Ambidexterity, Combat Agility |

## Still to verify / investigate

- Per-class AA list vs DB `classes` bitmask for all melee DPS AAs (e.g. Sinister Strikes, Flash of Steel, other class-specific).
- Whether any other AAs (e.g. Punishing Blade, Speed of the Knight) should be included for knights.

## Source of truth

- **Server**: `zone/client_process.cpp` (Triple Attack 13.5%, Flurry after triple), `zone/aa.h` (AA IDs), `zone/common.h` (bonus names, e.g. `FlurryChance`).
- **TAKP DB**: `altadv_vars` + `aa_effects` via `Server/utils/sql/aa_list_canonical.sql` (run `run_aa_canonical.ps1`). Values in `dps_config.json` are from this canonical export.

**Canonical values (max rank, from DB):** FlurryChance 30 (+ Raging Flurry 7), DoubleAttackChance (Ferocity/Knight's Advantage) 9, Ambidexterity 32, Combat Agility 10, RiposteChance (Return Kick, Monk only) 60, GiveDoubleRiposte0 50, StrikeThrough (Tactical Mastery) 45, ArcheryDamageModifier 100, AccuracyAll (Precision Pathfinder) 30, GiveDoubleAttack (Bestial/Harmonious) 15. Combat Stability omitted (not DPS).
