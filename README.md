# TAKP Magelo Tools

Tools for [TAKP](https://www.takproject.net/) magelo/export data: spell inventory, class rankings, and historical snapshots. Data is pulled from the server’s export page; a daily GitHub Action builds and deploys the outputs.

## Why this matters (engineering)

- **No stable API** — Ingestion from upstream exports/dumps; pipeline tolerates format drift and ad‑hoc HTML/text sources.
- **Deterministic pipeline** — Reproducible transforms from fixed inputs to publishable artifacts (HTML, JSON).
- **Storage-efficient history** — Baseline snapshot plus compact incremental change artifacts (~50 MB full snapshot vs ~300 KB daily diff); date-range views diff two deltas without full reconstruction.
- **Automated refresh** — Scheduled CI runs daily and rebuilds/redeploys all outputs.
- **Product surfaces** — Published dashboards (spell inventory, class rankings, etc) linked under Live site below.

## Build & reproducibility

- The **GitHub Actions** workflow is the canonical end-to-end runbook: install → ingest → transform → publish. How the project runs in production is defined there.
- To reproduce locally, mirror the steps in [`.github/workflows/daily-update.yml`](.github/workflows/daily-update.yml) (workflow name: **Daily Spell Inventory Update**).
- Runs: **Actions** tab → **Daily Spell Inventory Update** → Run workflow, or on push to `main`.

## Outputs

- **Spell inventory** — HTML of PoK spell availability per mule (from `spell_exchange_list.json`).
- **Class rankings** — Gear and focus rankings: `class_rankings.html`, `class_rankings.json`, `class_rankings.txt`. Data is JSON-driven (`class_rankings.json`, `data/item_stats.json`, `data/elemental_slot_options.json`); the UI supports user-customizable stat/focus weights with client-side persistence (localStorage). Per-class priorities and focus lists are configurable in code; all relevant spell foci are tracked. See `FOCUS_CONFIG_REFERENCE.md`.
- **Historical snapshots** — Baseline snapshot plus compact incremental change artifacts; stored as one full snapshot (~50 MB) and daily diffs (~300 KB). Change reports support audit and debugging of upstream/data drift. Date-range views load two deltas and diff them (no full reconstruction).

**Live site** (GitHub Pages):

- [Spell inventory (index)](https://ammordius.github.io/NAGD-spell-inventory/)
- [Class rankings](https://ammordius.github.io/NAGD-spell-inventory/class_rankings)

## Setup

1. Clone the repo. Ensure `spell_exchange_list.json` is present (e.g. from the quests repo or root).
2. Enable GitHub Pages: Settings → Pages → deploy from branch `gh-pages` (or root).
3. The workflow runs daily and on push to the generator scripts; trigger manually from Actions → “Daily Spell Inventory Update” → Run workflow.

Generated HTML/JSON are deployed to `gh-pages`. See **Live site** above for links.

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
