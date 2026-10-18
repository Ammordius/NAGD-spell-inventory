# Mod2 calibration report

## Architecture

- `data/item_mod2.json` is the only Mod2 dataset: the launch Plane of Time list, keyed by item id. 63 items resolved. Galladan's Stormwrath Tunic has no `items.name` match and is not scored.
- `scripts/mod2_scoring.py` calibrates full-cap weights and scores equipped totals. `data/mod2_config.json` is the frozen result.
- `mod2_rankings.js` applies that config in `class_rankings.html` only when `mod2=true`.
- `generate_class_rankings.py` attaches a `mod2` object and does not change `overall_score`.
- `dkp/web/src/lib/mageloUpgradeEngine.js` adds a Mod2 upgrade delta only when `ctx.mod2 === true`. DKP price math is untouched. `dkp_val` and `mod2` are independent.
- With the flag off, displayed score stays the core percentage. With the flag on, `displayed = 100 * (core + mod2) / (100 + reference_mod2_points)`.

## What 100% means

The ranking sheet is unbuffed. The server snapshot sets `hp_max_total` with `CalcMaxHP(true)` (no spell HP or STA buffs) and displayed AC from avoidance plus mitigation without combat agility. The page then shows each character as a percentage of the best core total in that class, so the leader is 100%.

The current rank-1 warrior, Voracious, is 8992 HP and 2206 displayed AC. That is the calibration anchor. It is not a buffed raid total, and it is not an internal mitigation cap. Warrior combat mitigation for that displayed AC, with defense 252 and agility 200, is 742 before shield AC and Combat Stability. The softcap before those additions is 430, and level-65 warrior overcap returns are 3.

## Quarm

npc_types id 223008 is min 1140, max 3800, ATK 500, Accuracy 750. DB = 1000, DI = 140. One percent shielding prevents 10 damage per landed hit. Four percent prevents 40, and 100 such hits prevent 4000. Points above 35% do not add benefit.

This server's melee path does not multiply worn shielding into the damage bonus. Spell shield and DoT shield are applied in `AffectMagicalDamage`. Strikethrough on a riposte in `attack.cpp` is AA-only. Combat Effects are not the weapon `ProcRate` field. The weights below are a scoring model on top of those verified formulas, not a claim that every Mod2 is implemented on the item struct.

Shielding's full-cap share of a landed hit, blended 50% Quarm / 30% illustrative PoP boss / 20% illustrative PoTime trash, is 10.5%. Full avoidance (100) removes 5.5% of hits against the unbuffed warrior avoidance rating of 501. Full accuracy (150) raises a 252/252 melee hit rate by 13.3% relative to an NPC avoidance cap of 460.

Avoidance is added to the avoidance rating and run through `AvoidanceCheck`. It is not treated as 10 hit points per 100 avoidance. Quarm's accuracy of 750 flattens avoidance; the blend keeps some value from the lower-accuracy profiles. Those two profiles are illustrative, not parsed boss rows.

## Weight matrix

A full cap is worth the points below on the 100-point core scale. U is linear in the stat up to the cap. Stun Resist and Combat Effects split a threat portion from a non-threat portion. The default scenario uses each class's threat factor (0.35 for warriors) and a 0.20 stun exposure. Threat value is zero when threat is not limiting, and stun threat is zero when stun exposure is zero. Reaching 35% is not an extra bonus.

| Class | Reference | Core JSON | Ref Mod2 pts | Shield | Avoid | SpellSh | DoTSh | Acc | Strike | CE | Stun | DS |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Warrior | Voracious | 91.79 | 3.27 | 3.90 | 2.04 | 1.17 | 0.78 | 0.70 | 0.22 | 0.21 | 0.68 | 0.02 |
| Cleric | Drudger | 94.90 | 2.26 | 0.31 | 0.16 | 3.41 | 0.71 | 0.09 | 0.03 | 0.03 | 0.20 | 0.00 |
| Paladin | Pigpen | 89.34 | 3.08 | 2.64 | 1.38 | 1.88 | 0.68 | 1.30 | 0.41 | 0.39 | 0.69 | 0.03 |
| Ranger | Linkamus | 98.47 | 2.87 | 1.28 | 0.67 | 1.19 | 0.51 | 2.88 | 0.91 | 0.87 | 0.15 | 0.07 |
| Shadow Knight | Slouch | 91.66 | 2.95 | 2.64 | 1.38 | 1.54 | 1.02 | 1.40 | 0.44 | 0.42 | 0.74 | 0.03 |
| Druid | Baily | 93.60 | 1.85 | 0.31 | 0.16 | 2.70 | 1.42 | 0.23 | 0.07 | 0.07 | 0.17 | 0.01 |
| Monk | Zentile | 97.35 | 2.84 | 1.04 | 0.54 | 0.83 | 0.52 | 3.49 | 1.10 | 1.05 | 0.02 | 0.08 |
| Bard | Taelor | 93.60 | 1.24 | 0.52 | 0.27 | 1.44 | 0.52 | 0.30 | 0.10 | 0.09 | 0.16 | 0.01 |
| Rogue | Tarkon | 97.97 | 2.44 | 0.82 | 0.43 | 0.62 | 0.41 | 3.72 | 0.20 | 1.12 | 0.02 | 0.09 |
| Shaman | Ziva | 94.27 | 1.62 | 0.38 | 0.20 | 2.27 | 1.56 | 0.37 | 0.12 | 0.11 | 0.17 | 0.01 |
| Necromancer | Nark | 90.99 | 1.28 | 0.20 | 0.11 | 1.99 | 2.56 | 0.09 | 0.03 | 0.03 | 0.13 | 0.00 |
| Wizard | Beldis | 89.76 | 2.39 | 0.20 | 0.11 | 3.91 | 0.57 | 0.09 | 0.03 | 0.03 | 0.14 | 0.00 |
| Magician | Starsha | 91.57 | 1.97 | 0.20 | 0.11 | 3.20 | 0.85 | 0.09 | 0.03 | 0.03 | 0.13 | 0.00 |
| Enchanter | Diox | 92.39 | 2.04 | 0.26 | 0.13 | 3.27 | 0.85 | 0.09 | 0.03 | 0.03 | 0.16 | 0.00 |
| Beastlord | Akbar | 94.45 | 1.66 | 1.45 | 0.76 | 1.19 | 0.68 | 0.40 | 0.13 | 0.12 | 0.15 | 0.01 |

Warrior shielding is the largest tank Mod2. Avoidance is next. Neither is close to the whole HP category (about 28 points). Monk and front-line accuracy is the large offensive Mod2. Rogue strikethrough is much smaller because the model assumes attacks from behind. Caster spell shielding is meaningful and still smaller than the focus block, which is 35 points of the core.

## Warrior comparisons

On Voracious, +100 HP is 0.275 display points. +10 displayed AC is 0.092 and +30 displayed AC is 0.275. The AC slope is the existing ranking's linear displayed-AC term, not extra mitigation past the softcap.
4% shielding is 0.45 points (4/35 of 3.90). 2% shielding is 0.22. 10 avoidance is 0.20. 25 avoidance is 0.51.
So 2% shielding is in the same range as +100 HP, and 4% shielding is ahead of +100 HP and ahead of +30 displayed AC. That is the intended tank result on this blend, not a forced ranking.

Default warrior stun threat at 35% is 0.64 points. With threat limitation 0 it is 0. With threat limitation 1 and stun exposure 0.8 it is 7.35.

## Reference loadouts

- **Warrior** (3.27 Mod2 points): Shroud of Eternity, Greaves of Furious Might, Shield of Strife, Raex's Chestplate of Destruction, Earthen Bracer of Fortitude, Collar of Catastrophe, Globe of Mystical Protection, Prismatic Ring of Resistance, Belt of Temporal Bindings, Armguards of the Brute, Bracer of Precision, Boots of Despair, Mantle of Deadly Precision, Padded Tigerskin Gloves, Mask of Strategic Insight, Timestone Adorned Ring, Darkblade of the Warlord, Silver Hoop of Speed, Earring of Xaoth Kor
- **Shadow Knight** (2.95 Mod2 points): Shroud of Eternity, Greaves of Furious Might, Prismatic Ring of Resistance, Earthen Bracer of Fortitude, Shield of Strife, Belt of Temporal Bindings, Armguards of the Brute, Collar of Catastrophe, Grimror's Guard of the Plagues, Mantle of Deadly Precision, Globe of Mystical Protection, Padded Tigerskin Gloves, Bracer of Precision, Boots of Despair, Mask of Strategic Insight, Cudgel of Venomous Hatred, Timestone Adorned Ring, Silver Hoop of Speed, Earring of Xaoth Kor
- **Monk** (2.84 Mod2 points): Wristband of Icy Vengeance, Mantle of Deadly Precision, Padded Tigerskin Gloves, Cord of Temporal Weavings, Mask of Strategic Insight, Timestone Adorned Ring, Silver Hoop of Speed, Prismatic Ring of Resistance, Pants of Furious Might, Shroud of Eternity, Tactician's Shield, Shoes of Fleeting Fury, Ton Po's Chestwraps of Composure, Collar of Catastrophe, Globe of Mystical Protection, Earring of Xaoth Kor, Protective Sleeves, Bracer of Precision
- **Rogue** (2.44 Mod2 points): Bracer of the Inferno, Mantle of Deadly Precision, Bidilis' Hauberk of the Elusive, Mask of Strategic Insight, Silver Hoop of Speed, Jagged Timeforged Blade, Band of Prismatic Focus, Shroud of Eternity, Prismatic Ring of Resistance, Leggings of Furious Might, Belt of Temporal Bindings, Winged Storm Boots, Earring of Xaoth Kor, Padded Tigerskin Gloves, Collar of Catastrophe, Globe of Mystical Protection, Bracer of Precision
- **Wizard** (2.39 Mod2 points): Maelin's Robe of Lore, Tactician's Shield, Belt of Temporal Bindings, Gloves of the Unseen, Ethereal Silk Leggings, Shroud of Eternity, Protective Sleeves, Symbol of the Planemasters, Sandals of Empowerment, Earring of Unseen Horrors, Shawl of Eternal Forces, Band of Prismatic Focus, Earring of Xaoth Kor
- **Cleric** (2.26 Mod2 points): Prismatic Ring of Resistance, Tactician's Shield, Belt of Temporal Bindings, Armguards of the Brute, Earthen Bracer of Fortitude, Ultor's Chestguard of Faith, Shroud of Eternity, Greaves of Furious Might, Symbol of the Planemasters, Bracer of Precision, Boots of Despair, Earring of Unseen Horrors, Necklace of Eternal Visions, Ring of Evasion, Padded Tigerskin Gloves, Shawl of Eternal Forces, Earring of Xaoth Kor

Ultor's Chestguard of Faith is class bit CLR in this database, and Trydan's Chestplate of Nobility is PAL. Mods stay on the named items. The loadout follows the class bitmask.

## Ranking movement

Before is the stored `overall_score` divided by the class maximum, which is 100 for the current leader. After adds equipped launch Mod2s and renormalizes with that class's reference loadout. Characters with no launch Mod2s keep their order and sit slightly below their old percentage.

### Warrior

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Frosst | 99.68 | 2.37 | 98.83 |
| Xorik | 99.79 | 2.12 | 98.68 |
| Kalistrate | 99.79 | 1.99 | 98.56 |
| Voracious | 100.00 | 1.70 | 98.48 |
| Slay | 99.81 | 1.23 | 97.85 |
| Rangerwoodelf | 99.49 | 1.32 | 97.61 |
| Warboss | 98.64 | 2.15 | 97.60 |
| Thucydides | 99.31 | 1.15 | 97.29 |

### Shadow Knight

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Slouch | 100.00 | 1.88 | 98.96 |
| Devour | 99.29 | 2.04 | 98.43 |
| Exos | 96.15 | 1.57 | 94.92 |
| Gkssizz | 96.29 | 1.22 | 94.72 |
| Gadzooks | 95.56 | 1.65 | 94.42 |
| Roach | 95.12 | 1.46 | 93.81 |
| Tapornap | 91.85 | 1.54 | 90.71 |
| Lamia | 91.86 | 1.45 | 90.64 |

### Monk

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Zentile | 100.00 | 1.68 | 98.88 |
| Gorrok | 98.59 | 2.17 | 97.99 |
| Tyrin | 96.73 | 2.12 | 96.12 |
| Raud | 96.01 | 1.79 | 95.10 |
| Jyslia | 95.70 | 1.19 | 94.21 |
| Masmacho | 94.92 | 1.22 | 93.48 |
| Pretzella | 94.13 | 1.40 | 92.90 |
| Hollowlung | 93.79 | 1.42 | 92.58 |

### Rogue

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Tarkon | 100.00 | 1.93 | 99.50 |
| Senbus | 95.94 | 1.65 | 95.26 |
| Braveheartt | 94.65 | 1.53 | 93.89 |
| Littlernemce | 94.57 | 1.37 | 93.66 |
| Kaerilai | 92.61 | 1.00 | 91.38 |
| Baditude | 91.26 | 1.83 | 90.88 |
| Swytetea | 91.95 | 0.69 | 90.43 |
| Arttemis | 91.70 | 0.60 | 90.10 |

### Wizard

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Beldis | 100.00 | 1.18 | 98.82 |
| Benoeb | 98.96 | 0.73 | 97.38 |
| Vindication | 99.28 | 0.04 | 97.00 |
| Charybdis | 97.81 | 1.30 | 96.79 |
| Zigzag | 97.30 | 1.73 | 96.72 |
| Hopkins | 97.79 | 0.77 | 96.27 |
| Sarafelle | 96.90 | 1.28 | 95.90 |
| Breadward | 96.52 | 0.70 | 94.96 |

### Cleric

| Name | Before % | Mod2 pts | After % |
|---|---:|---:|---:|
| Drudger | 100.00 | 0.61 | 98.39 |
| Shorttin | 98.37 | 0.57 | 96.76 |
| Maye | 98.00 | 0.54 | 96.37 |
| Neea | 95.87 | 1.18 | 94.91 |
| Winstonn | 96.22 | 0.49 | 94.58 |
| Medikus | 94.91 | 0.54 | 93.35 |
| Navalny | 94.54 | 0.47 | 92.92 |
| Drat | 94.82 | 0.12 | 92.84 |

## Largest moves inside the tracked classes

| Class | Name | Before rank | After rank | Score change |
|---|---|---:|---:|---:|
| Warrior | Frosst | 5 | 1 | -0.86 |
| Warrior | Voracious | 1 | 4 | -1.52 |
| Warrior | Slay | 2 | 5 | -1.97 |
| Rogue | Baditude | 9 | 6 | -0.39 |
| Monk | Hollowlung | 10 | 8 | -1.20 |
| Warrior | Xorik | 3 | 2 | -1.11 |
| Warrior | Kalistrate | 4 | 3 | -1.23 |
| Warrior | Warboss | 8 | 7 | -1.04 |
| Warrior | Thucydides | 7 | 8 | -2.03 |
| Shadow Knight | Exos | 4 | 3 | -1.23 |
| Shadow Knight | Gkssizz | 3 | 4 | -1.57 |
| Shadow Knight | Tapornap | 8 | 7 | -1.14 |

## Item examples

| Item | Id | Warrior pts | Monk pts | Wizard pts |
|---|---:|---:|---:|---:|
| Greaves of Furious Might | 28650 | 0.45 | 0.12 | 0.02 |
| Pants of Furious Might | 28652 | 0.51 | 0.14 | 0.03 |
| Leggings of Furious Might | 28651 | 0.43 | 0.11 | 0.02 |
| Shield of Strife | 27298 | 0.33 | 0.09 | 0.02 |
| Shroud of Eternity | 15805 | 0.45 | 0.14 | 0.02 |
| Padded Tigerskin Gloves | 27000 | 0.06 | 0.32 | 0.01 |
| Wristband of Icy Vengeance | 32110 | 0.38 | 0.43 | 0.03 |
| Prismatic Ring of Resistance | 26989 | 0.20 | 0.14 | 0.67 |
| Raex's Chestplate of Destruction | 32129 | 0.33 | 0.09 | 0.02 |
| Ultor's Chestguard of Faith | 32603 | 0.14 | 0.00 | 0.03 |
| Trydan's Chestplate of Nobility | 32132 | 0.22 | 0.06 | 0.01 |

Highest-HP warrior legs currently in `item_stats.json`, for scale against Greaves of Furious Might (4% shielding, 0.45 warrior points):

- Greaves of Furious Might (28650): 210 HP, 69 AC, about 0.58 HP display points and 0.63 AC display points
- Raex's Greaves of Destruction (16693): 165 HP, 70 AC, about 0.45 HP display points and 0.64 AC display points
- Leggings of Fiery Might (28965): 125 HP, 35 AC, about 0.34 HP display points and 0.32 AC display points
- Farwater Plate Greaves (31296): 100 HP, 43 AC, about 0.28 HP display points and 0.39 AC display points
- Leggings of Serenity (30532): 100 HP, 20 AC, about 0.28 HP display points and 0.18 AC display points

## Weight sensitivity

Warrior top 10 were re-ranked with every Mod2 weight at 75% and 125% of the frozen values.

- 75%: 0 of the top 10 change position. Order: Frosst, Xorik, Kalistrate, Voracious, Slay, Rangerwoodelf, Warboss, Thucydides, Zender, Barnpig
- 125%: 2 of the top 10 change position. Order: Frosst, Xorik, Kalistrate, Voracious, Slay, Warboss, Rangerwoodelf, Thucydides, Zender, Barnpig

## Unresolved

- Galladan's Stormwrath Tunic is not in `peq.items`. It is listed under `unresolved` and contributes nothing.
- Later expansions have no Mod2s in this dataset. They score zero until an item is added to `item_mod2.json`.
- Displayed AC is still linear in the core score. The Mod2 model does not revalue the existing AC category.
- Combat Stability and shield AC were left at zero in the mitigation example, so the 742 mitigation figure is a lower-gear overcap case for the displayed total, not a logged parse.

