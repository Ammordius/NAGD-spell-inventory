# Item cards – local run and test

## Quick test (build + serve)

From **magelo** repo root:

```bash
python scripts/run_and_test_item_cards.py
```

Then open **http://localhost:8765/class_rankings.html** and hover over item links (e.g. Cap of Flowing Time, Mask of Strategic Insight). Item cards should show.

- `--no-serve` – only build `deploy_local/`, do not start the server.
- `--port 8000` – use a different port.

## Verify data only

```bash
python scripts/verify_item_cards.py
```

Checks that Cap of Flowing Time, Mask of Strategic Insight, Amulet of Crystal Dreams, and Bracer of Precision exist in `data/item_name_to_id.json` and `data/item_stats.json`.

## Why CI might not show full item cards

1. **`data/item_name_to_id.json`** – Generated in CI by `merge_dkp_loot_into_raid_sources.py --write-name-to-id` (before class rankings and again before deploy). So it **is** in deploy.

2. **`data/item_stats.json`** – The workflow only **copies** it if it exists. For full stats (e.g. Cap of Flowing Time), run `python scripts/copy_dkp_item_stats_to_magelo.py` to copy from `../dkp/web/public/item_stats.json`; otherwise it can be built from `utils/update_focus_items_and_stats.py` (reads `../dkp/data/item_stats.csv`, smaller set). If `data/item_stats.json` is not committed, CI won’t have it and deploy won’t get it → item cards on the live site show **name + link only** (no stats).

**Options for CI:**

- **Commit `data/item_stats.json`** in the magelo repo (if it’s not gitignored and size is acceptable), so CI copies it to deploy and full cards work.
- Or **add a CI step** that generates `data/item_stats.json` when the dkp repo (or `dkp_mob_loot` / `item_stats.csv`) is available (e.g. checkout dkp, run `utils/update_focus_items_and_stats.py`), then copy it into deploy.

Running `scripts/run_and_test_item_cards.py` locally uses your existing `data/item_stats.json`, so you can confirm full cards work before fixing CI.
