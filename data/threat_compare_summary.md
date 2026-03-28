# Meriadoc vs server-model threat (largest absolute **total** deltas first)

Server model: fixed Warrior 65, haste 70, DEX 255, target max HP 1M — see `weapon_threat_server.json` `_meta`.
Proc frequency uses `items.procrate` from `item_proc_meta.json` when present (re-export from your DB if values differ from TAKP).

Typical reasons for gaps:

- **Melee**: Meriadoc ties hate to expected DPS; server uses fixed hate per swing (no crit scaling).
- **Procs (total)**: Meriadoc `hatePerSec` is a separate model from `CheckAggroAmount` + `GetProcChance` × `(100+procrate)/100`.
- **Anger / stun procs**: Magelo uses **400** non-damage cap + **SE_InstantHate** + DD hate per proc (see `check_aggro_amount.py`); Meriadoc sheet numbers use a different model.
- **procRateDb**: If `item_proc_meta.json` is stale or from another fork, proc HPS will not match live TAKP.

| weapon | Meriadoc total | Server total | Δ |
|--------|----------------|--------------|---|
| sceptre of destruction | 76.64 | 10.63 | -66.01 |
| hopebringer | 52.72 | 117.72 | 65.0 |
| gem encrusted axe | 55.54 | 114.52 | 58.98 |
| frostbite, cold blade of dread | 68.68 | 10.63 | -58.05 |
| wand of temporal power | 20.0 | 75.63 | 55.63 |
| ornate broadsword | 47.59 | 103.14 | 55.55 |
| greatstaff of thunder | 65.34 | 10.63 | -54.71 |
| jagged blade of war | 64.68 | 10.63 | -54.05 |
| blade of tactics | 60.74 | 10.63 | -50.11 |
| infestation | 60.7 | 10.63 | -50.07 |
| horror shard blade | 59.23 | 10.63 | -48.6 |
| primal velium warsword | 14.47 | 62.69 | 48.22 |
| basalt greatsword of protector | 57.89 | 10.63 | -47.26 |
| great lance of stone | 57.57 | 10.63 | -46.94 |
| war marshall's bladed staff | 57.53 | 10.63 | -46.9 |

## Largest proc (MH) disagreements: Meriadoc `hatePerSec` vs server `hatePerSecServer`

| weapon | Meriadoc proc MH | Server proc MH | Δ proc MH | procRateDb |
|--------|------------------|----------------|-----------|------------|
| darkblade of the warlord | 40.43 | 1.64 | -38.79 | 30 |
| bloodfrenzy | 29.34 | 1.24 | -28.1 | 55 |
| frostbite, cold blade of dread | 24.74 | 0.0 | -24.74 | 0 |
| blasphemous blade of the exiled | 22.09 | 0.87 | -21.22 | 65 |
| kelp hilted mace | 21.0 | 0.0 | -21.0 | 0 |
| hammer of holy vengeance | 21.3 | 0.79 | -20.51 | 530 |
| furious hammer of zek | 21.3 | 0.8 | -20.5 | 530 |
| hammer of hours | 20.28 | 0.83 | -19.45 | 0 |
| wand of temporal power | 20.0 | 0.83 | -19.17 | 0 |
| sceptre of destruction | 18.61 | 0.0 | -18.61 | 0 |
