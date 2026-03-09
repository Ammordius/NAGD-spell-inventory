# DPS Calculator – AAs and Class Mechanics

## Innate / skill (not AAs)

- **Triple Attack** – Warrior and Monk at level 60+: 13.5% chance for one extra primary-hand swing per round. Implemented in the calculator for both classes; no AA toggle.
- **Flurry** – In server code, Flurry is an **AA** that grants `FlurryChance`; when Triple Attack fires, Flurry can add 1–2 more primary-hand swings. Only **Warrior** has the Flurry AA line in TAKP; Monk gets Triple Attack but not Flurry.

## AAs currently in `dps_config.json` (per class)

| Class        | AAs in config |
|-------------|----------------|
| **Warrior** | Ferocity, Flurry, Ambidexterity, Combat Agility, Combat Stability, Return Kick, Double Riposte, Strikethrough |
| **Rogue**   | Ambidexterity, Combat Agility, Return Kick, Double Riposte, Sinister Strikes, Chaotic Stab |
| **Monk**    | Ambidexterity, Combat Agility, Return Kick, Double Riposte |
| **Ranger**  | Archery Mastery, Ambidexterity, Combat Agility, Precision of the Pathfinder |
| **Paladin** | Knight's Advantage, Ambidexterity, Combat Agility, Return Kick, Double Riposte |
| **Shadow Knight** | Knight's Advantage, Ambidexterity, Combat Agility, Return Kick, Double Riposte |
| **Bard**    | Ambidexterity, Combat Agility |
| **Beastlord** | Bestial Frenzy, Harmonious Attack, Ambidexterity, Combat Agility |

## Source of truth

- **Server**: `zone/client_process.cpp` (Triple Attack 13.5%, Flurry after triple), `zone/aa.h` (AA IDs), `zone/common.h` (bonus names, e.g. `FlurryChance`).
- **TAKP DB**: `altadv_vars` and spell effects for exact per-AA, per-rank values.

If you have a canonical list of AAs per class (e.g. from TAKP DB or a wiki), we can align the config and add any missing AAs or correct bonus values.
