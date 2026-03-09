# DPS Calculator – AAs and Class Mechanics

## Innate / skill (not AAs)

- **Triple Attack** – Warrior and Monk at level 60+: 13.5% chance for one extra primary-hand swing per round. Implemented in the calculator for both classes; no AA toggle.
- **Flurry** – In server code, Flurry is an **AA** that grants `FlurryChance`; when Triple Attack fires, Flurry can add 1–2 more primary-hand swings. Only **Warrior** has the Flurry AA line in TAKP; Monk gets Triple Attack but not Flurry.

## AAs currently in `dps_config.json` (per class)

Only DPS-relevant AAs are included. Combat Stability (mitigation) is omitted. Return Kick is Monk-only (DB classes=128).

| Class        | AAs in config |
|-------------|----------------|
| **Warrior** | Ferocity, Combat Fury, **Fury of the Ages**, Planar Power, Flurry, Raging Flurry, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Tactical Mastery (Strikethrough) |
| **Rogue**   | Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility, Double Riposte, Chaotic Stab |
| **Monk**    | Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility, Return Kick, Double Riposte, Punishing Blade, **Technique of Master Wu** |
| **Ranger**  | Archery Mastery, Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade |
| **Paladin** | Knight's Advantage, Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Speed of the Knight |
| **Shadow Knight** | Knight's Advantage, Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility, Double Riposte, Punishing Blade, Speed of the Knight |
| **Bard**    | Combat Fury, **Fury of the Ages**, Planar Power, Ambidexterity, Combat Agility |
| **Beastlord** | Bestial Frenzy, Ambidexterity, Combat Fury, **Fury of the Ages**, Planar Power |

## Riposte / tank DPS (planned)

When **tanking**, DPS includes ripostes: the mob swings at you, you have a chance to riposte (and double riposte). To model that we need a **riposte calculator** with its own toggle (e.g. “Include riposte DPS when tanking”), driven by:

- **Mob attack delay** – how often the mob swings (and thus how many riposte opportunities per second)
- **Player riposte chance** – from defense skill, level, and **Return Kick** AA (Monk) if applicable
- **Dual wield** – more riposte chances when the mob dual-wields (two attacks per round)
- **Mob triple attack / flurry** – more attacks from the mob → more riposte rolls
- **Double Riposte** (and Flash of Steel) – chance to get two ripostes off one defensive round

So total tank DPS = **melee DPS** (current calculator) + **riposte DPS** (mob swings × riposte chance × damage per riposte × (1 + double riposte chance)). This will be a separate toggle and inputs (mob delay, mob dual wield, etc.) to be added.

## Combat Fury vs Fury of the Ages

**Warriors** get both Combat Fury and **Fury of the Ages** (same as non‑warrior melee). Both grant **SE_CriticalHitChance** (effect 169): Combat Fury base1=75 (max rank), Fury of the Ages base1=150 (max rank). Fury of the Ages requires Combat Fury (prereq_skill 113). Server merges with **max** (`zone/bonuses.cpp`). So when both are taken, effective = 150. The calculator uses **max** when merging AA bonuses for `CriticalHitChance`.

## How crit is calculated (server logic)

Source: `zone/attack.cpp` melee crit block. Rule `Combat:ClientBaseCritChance` = 0 (TAKP default).

1. **Base:** `critChance += ClientBaseCritChance` (0).
2. **Class path (one of):**
   - **Warrior level ≥ 12:** `critChance += 0.5 + min(DEX,255)/90 + overCap` (overCap = (DEX−255)/400 if DEX>255, else 0). Warriors can crit **without** any AA.
   - **Ranger archery level > 16:** `critChance += 1.35 + min(DEX,255)/34 + overCap*2`. Rangers with bow can crit without the crit AAs.
   - **All other (non‑Warrior, or Ranger melee):** `critChance += 0.275 + min(DEX,255)/150 + overCap` **only if** `aabonuses.CriticalHitChance` is set. **Without Combat Fury / Fury of the Ages, these classes cannot crit** (path not applied).
3. **Multiplier:** If `CriticalHitChance` bonus present: `critChance *= (1 + CriticalHitChance/100)`.
4. Final roll: `critChance /= 100`; roll for crit.

So: **non‑warriors (and Ranger melee) have 0% crit unless they have at least Combat Fury.** Warrior and Ranger archery have an innate base that is then scaled by the AA.

### Approximate crit % by class and AA (level 65, DEX 255)

| Class / mode      | No crit AA | Combat Fury (75) | Fury of the Ages (150) |
|-------------------|------------|-------------------|-------------------------|
| **Warrior**       | ~3.3%      | ~5.8%             | ~8.3%                   |
| **Ranger (bow)**  | ~8.9%      | ~15.5%            | ~22.2%                  |
| **Ranger (melee)**| 0%         | ~3.5%             | ~4.9%                   |
| **All other melee** (Monk, Rogue, Paladin, SK, Bard, Beastlord) | 0% | ~3.5% | ~4.9% |

Formula at cap: Warrior base ≈ 0.5 + 255/90 ≈ 3.33%; non‑warrior base (with AA) ≈ 0.275 + 255/150 ≈ 1.98%; Ranger archery base ≈ 1.35 + 255/34 ≈ 8.85%. Then ×(1 + 75/100) or ×(1 + 150/100) for the AA multiplier.

## Ferocity (Warrior-only)

**Ferocity** (skill_id 564) grants DoubleAttackChance (effect 177) base1=9. In TAKP canonical it has **classes = 658**; that mask does not include Monk (32). So Ferocity is **Warrior-only** in config; Monk gets double attack from skill + Triple Attack, not Ferocity.

## Ambidexterity

Monks (and Rogue, Ranger, Paladin, SK, Bard, Beastlord) have **Ambidexterity** in the canonical list (classes 33682); config already includes it for all. No change.

## Still to verify / investigate

- Flash of Steel (same classes as Double Riposte) – effect 223 base1=30; server takes max of GiveDoubleRiposte[0], so 50 from Double Riposte already covers; no separate config entry needed.

## Audit (vs TAKP canonical AA list)

Audited `dps_config.json` against `Server/utils/sql/aa_list_canonical_results.txt` (from `altadv_vars` + `aa_effects`). Removed AAs that do **not** exist on TAKP:

- **Precision of the Pathfinder** (Ranger) – no Accuracy AA for Rangers in TAKP DB; removed.
- **Sinister Strikes** (Rogue) – not in TAKP canonical list; removed.
- **Harmonious Attack** (Beastlord) – in TAKP it is **Bard-only** (classes=256); Beastlord has Bestial Frenzy (effect 225, 15) only; removed from Beastlord.

## Source of truth

- **Server**: `zone/client_process.cpp` (Triple Attack 13.5%, Flurry after triple), `zone/attack.cpp` (melee crit paths: Warrior 12+, Ranger archery 17+, non‑Warrior with CriticalHitChance), `zone/aa.h` (AA IDs), `zone/common.h` (bonus names), `zone/special_attacks.cpp` (Technique of Master Wu).
- **TAKP DB**: `altadv_vars` + `aa_effects` via `Server/utils/sql/aa_list_canonical.sql` (run `run_aa_canonical.ps1`). Values in `dps_config.json` are from this canonical export.

**Canonical values (max rank, from DB):** FlurryChance 30 (+ Raging Flurry 7), DoubleAttackChance (Ferocity/Knight's Advantage) 9, Ambidexterity 32, Combat Agility 10, RiposteChance (Return Kick, Monk only) 60, GiveDoubleRiposte0 50, StrikeThrough (Tactical Mastery) 45, **ExtraAttackChance (Punishing Blade / Speed of the Knight) 8 each**, ArcheryDamageModifier 100, GiveDoubleAttack (Bestial Frenzy) 15, **DoubleSpecialAttack (Technique of Master Wu, Monk) 100**, **CriticalHitChance (Combat Fury 75, Fury of the Ages 150; server takes max)**. Combat Stability omitted (not DPS). Accuracy / Precision of the Pathfinder and Sinister Strikes not present on TAKP.
