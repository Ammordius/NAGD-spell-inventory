# Gear planner (focuses, FT, ATK, haste) — agent handoff

Use this doc to resume implementation without re-reading the full thread. **Do not edit** `.cursor/plans/gear_planner_focus_ft_atk_haste_eb272af3.plan.md` unless the user asks.

## Goal

Extend the **Stat simulator** (gear planner) on **`magelo/class_rankings.html`**: when the user picks a virtual loadout per slot, show:

1. **Spell focuses** — unique `focusSpellName` values across selected items (from `item_stats` / `itemStatsCache`).
2. **FT (Flowing Thought)** — totals like Magelo `mana_regen_item` (`X / 15`).
3. **Worn ATK** — totals like Magelo `atk_item` (`X / 250`).
4. **Item haste %** — melee item haste, cap **30** (same mental model as `generate_class_rankings.py`).

Baseline values come from **`char.stats`** on each character row (Magelo export). Virtual totals = baseline − sum(spell bonuses from **equipped** items) + sum(spell bonuses from **picked** items), mirroring how HP/Mana/AC deltas work in `recomputeVirtualStats()`.

## What’s not done yet

- **`magelo/scripts/build_item_spell_bonuses.py`** — not created.
- **`magelo/data/item_spell_bonuses.json`** — not created.
- **`magelo/class_rankings.html`** — not wired (no fetch, no UI block).

Todos (Cursor): `script-spell-bonuses`, `html-load-merge`, `html-ui` — complete and mark done when finished.

## Where the UI lives

| Area | Location in `class_rankings.html` (approx.) |
|------|-----------------------------------------------|
| Virtual loadout state | `itemPickerState.virtualLoadout` (~3539) |
| HP/Mana/AC delta math | `recomputeVirtualStats()` (~3543–3610) |
| Table update | `updateItemPickerStatTable()` (~3613–3634) |
| Item picker build | `buildItemPickerPanel()` (~3667+) |

Reuse the **same 2H + offhand branches** as HP (slots 13/14): when main is 2H, merge primary+offhand “current” for deltas; OH empty when 2H equipped.

## Data pipeline (planned)

1. **Build script** reads:
   - `magelo/data/item_stats.json` — collect every `effectSpellId` and `focusSpellId` (numeric).
   - `Server/utils/sql/git/required/2016_11_12_spells_part1.sql` + `part2.sql` — full `spells_en` via existing **`magelo/scripts/threat/parse_spells_en.py`** (`load_columns_from_part1`, `load_spells_en_from_files`, `spell_threat_record` shape).

2. **Output** `magelo/data/item_spell_bonuses.json`:
   - Keys: **spell id strings** `"1298"`.
   - Values: `{ "atk": int, "haste": int, "ft": int }` (per spell, not per item).
   - `_meta.missingIds`: spell ids from items not found in DB.

3. **Runtime (HTML)** loads JSON once (pattern similar to `loadItemStats()` / `itemStatsCache`). For each item id, read `item_stats` → get effect + focus spell ids → look up bonuses → sum for that item (both spells).

## Spell effect IDs (from `magelo/scripts/threat/spell_effects.py` + `Server/common/spdat.h`)

- **`SE_ATK` = 2** — sum `base[i]` where `effectid[i] == 2`.
- **`SE_AttackSpeed` = 11**, **`SE_AttackSpeed2` = 98**, **`SE_AttackSpeed3` = 119** — sum haste contributions; cap **30** when aggregating loadout (additive stacking per plan / `generate_class_rankings` display).
- **Flowing Thought**: spell names `Flowing Thought I` … in DB. Inspected rows:
  - Spell **1298** Flowing Thought I: `effectid` starts `[10, 15, ...]`, `base` `[0, 1, 0, ...]`
  - **1299** II: `base[1] == 2`
  - **1300** III: `base[1] == 3`
  - Slot index **1** uses **`effectid == 15` (`SE_CurrentMana`)** — the **base value is the FT tier (1, 2, 3…)** for that line, **not** “+1 toward 15” directly. For **total worn FT toward cap 15**, product logic may need to match server/Magelo (sum of tier values vs count of FT items). **Fallback in plan**: parse name `Flowing Thought\s+([IVXLC]+)` → Roman → tier **1–15** if effect parsing is ambiguous.

- Spell **998** “Haste”: `effectid[0]==11`, `base[0]==101` — haste value is in **tenths** or raw %; **verify** against one known item in-game (41% haste often displays as 101 in spell data on some emus).

**Path note:** In scripts, resolve Server SQL with **`Path(__file__).resolve().parents[1]`** for `magelo/scripts` → `magelo`, then `parents[2]` = `TAKP` → `TAKP/Server/...` — same as `build_spells_threat_json.py` (`_server_root()`).

## Validation commands

```powershell
Set-Location c:\TAKP\magelo
python -c "
import sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from threat.parse_spells_en import load_columns_from_part1, load_spells_en_from_files
sroot = Path(r'c:\TAKP\Server\utils\sql\git\required')
sql = [sroot/'2016_11_12_spells_part1.sql', sroot/'2016_11_12_spells_part2.sql']
cols = load_columns_from_part1(sql[0])
sp = load_spells_en_from_files(sql, cols)
for sid in [1298, 1299, 1300, 998]:
    if sid in sp:
        print(sid, sp[sid]['name'], sp[sid]['effectid'], sp[sid]['base'])
"
```

## Reference: caps and parsing (Python)

See **`magelo/generate_class_rankings.py`** ~1081–1120:

- `mana_regen_item` → `ft_current`, `ft_cap` (often **15**).
- `atk_item` → `current_atk` vs **250**.
- `haste` numeric → item haste; **≥30** treated as capped for binary score in some paths.

## Files to add/change (checklist)

- [ ] `magelo/scripts/build_item_spell_bonuses.py`
- [ ] `magelo/data/item_spell_bonuses.json` (generated; commit like other `data/*.json`)
- [ ] `magelo/class_rankings.html` — load JSON, extend `recomputeVirtualStats`, update table + focuses list + FT/ATK/Haste rows

## Optional

One-line rebuild note in script docstring or `magelo/scripts/README` if one exists — user asked for “similar to `build_spells_threat_json.py`”.
