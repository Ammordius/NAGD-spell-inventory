# DKP prices JSON for Magelo

## Overview

`build_dkp_prices_json.py` pulls the **most recent 3 DKP prices** from Supabase for every item that exists in both:

- **item_stats** (magelo `data/item_stats.json`) — keyed by item id, has `name`
- **Supabase** `raid_loot` — has `item_name`, `cost`, `raid_id`; dates come from `raids.date_iso`

Only items that appear in both are included. Queries are minimized: one paginated read of `raid_loot`, then one batched read of `raids` for the raid dates (no per-item queries).

## Output format

The script writes `data/dkp_prices.json` (or `--out` path) in this shape:

```json
{
  "1097": {
    "dkp_prices": [
      { "date": "2026-02-15", "cost": 50 },
      { "date": "2026-01-10", "cost": 45 },
      { "date": "2025-12-01", "cost": 55 }
    ]
  }
}
```

You can merge this into item_stats (e.g. add `dkp_prices` to each item that has an entry) when building Magelo pages.

## Setup

1. **Python deps** (from repo root or `scripts/`):
   ```bash
   pip install supabase
   ```

2. **Supabase env** (same as DKP repo):
   ```bash
   export SUPABASE_URL=https://your-project.supabase.co
   export SUPABASE_SERVICE_ROLE_KEY=eyJ...
   ```
   Or use `SUPABASE_ANON_KEY` if your RLS allows reading `raid_loot` and `raids`.

## Usage

From the **magelo** repo root:

```bash
# Generate data/dkp_prices.json
python scripts/build_dkp_prices_json.py

# Custom paths
python scripts/build_dkp_prices_json.py --item-stats data/item_stats.json --out data/dkp_prices.json

# See what would be written without writing
python scripts/build_dkp_prices_json.py --dry-run
```

## Cross-reference logic

1. Build a map: **normalized item name** (lowercase, trimmed) → **item_id** from `item_stats.json`.
2. Fetch all `raid_loot` rows (`item_name`, `cost`, `raid_id`).
3. Fetch `raids` for those `raid_id`s to get `date_iso`.
4. Keep only loot rows whose `item_name` (normalized) is in the item_stats name set.
5. For each item_id, sort (date desc) and keep the latest 3 `(date, cost)`.
6. Write JSON keyed by item_id with `dkp_prices` array.
