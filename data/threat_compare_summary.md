# Meriadoc vs server-model threat (largest absolute deltas first)

Server model: fixed Warrior 65, haste 70, DEX 255, target max HP 1M — see `weapon_threat_server.json` `_meta`.

Typical reasons for gaps:

- **Melee**: Meriadoc ties hate to expected DPS; server uses fixed hate per swing (no crit scaling).
- **Procs**: `item_proc_meta.json` may be empty — proc rate modifier defaults to 0 (underestimates vs DB procrate).
- **standardSpellHate** scales with benchmark target HP for non-DD proc components.

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
