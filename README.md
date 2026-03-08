# TAKP Magelo Tools

Tools for [TAKP](https://www.takproject.net/) magelo/export data: spell inventory, class rankings, and historical snapshots. Data is pulled from the server’s export page; a daily GitHub Action builds and deploys the outputs.

## Outputs

- **Spell inventory** — HTML of PoK spell availability per mule (from `spell_exchange_list.json`).
- **Class rankings** — Gear and focus rankings: `class_rankings.html`, `class_rankings.json`, `class_rankings.txt`. Data is JSON-driven (`class_rankings.json`, `data/item_stats.json`, `data/elemental_slot_options.json`); the UI supports user-customizable stat/focus weights with client-side persistence (localStorage). Per-class priorities and focus lists are configurable in code; all relevant spell foci are tracked. See `FOCUS_CONFIG_REFERENCE.md`.
- **Historical snapshots** — Baseline + delta storage: one full snapshot (~50MB) plus daily diffs (~300KB). Date-range views load two deltas and diff them (no full reconstruction).

## Setup

1. Clone the repo. Ensure `spell_exchange_list.json` is present (e.g. from the quests repo or root).
2. Enable GitHub Pages: Settings → Pages → deploy from branch `gh-pages` (or root).
3. The workflow runs daily (~2 AM UTC) and on push to the generator scripts; trigger manually from Actions → “Daily Spell Inventory Update” → Run workflow.

Generated HTML/JSON are deployed to `gh-pages`. Live URLs:  
`https://<username>.github.io/<repo>/` (index), `.../class_rankings.html`.

## Local run

```bash
# Spell inventory
python generate_spell_page.py

# Class rankings
python generate_class_rankings.py
```

Requires: `character/` and `inventory/` data (from TAKP export or workflow cache), and `../quests/poknowledge/spell_exchange_list.json` for spell inventory.

## Docs

- `FOCUS_CONFIG_REFERENCE.md` — Focus priorities and weights per class; which foci are tracked.
- `QUICKSTART.md` — Short deployment steps.
- `CHARACTER_RANKINGS_SETUP.md` — Character rankings HTML/JSON setup.
