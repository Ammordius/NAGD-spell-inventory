# Handoff: Magelo delta baseline and delta-history (May 2026)

This document captures context for fixing **delta-history** behavior and related **CI baseline cache** issues after the **2026-05-09** region incident through **2026-05-12** baseline rotation. Use it in a fresh thread or PR so implementers do not re-derive root causes.

---

## Symptoms

- **delta-history** (client-side date range): for “the last few days” users see either **no inventory delta**, or **massive** inventory deltas that feel like **months of loot** (often described as “everything since the first snapshot” around **early February 2026**, e.g. **2/8–2/9**).
- **`delta_daily_YYYY-MM-DD.json.gz`** sometimes had **empty** `inv_deltas` / `char_deltas` on days that should show churn, or **`baseline_date` jumps** so ranges no longer subtract cleanly.

---

## What daily JSONs actually mean (non-negotiable for fixes)

- Each **`delta_daily_*.json.gz`** is produced by **`save_daily_delta_from_baseline`** in [`delta_storage.py`](../delta_storage.py).
- **`inv_deltas`** (and character rows) are **cumulative differences vs that file’s `baseline_date`**, not “loot that calendar day only.”
- **Historical range UI** computes “changes from day A to day B” by **subtracting two endpoint snapshots** — same idea as **`compare_delta_to_delta`** in Python and the mirrored block in [`generate_spell_page.py`](../generate_spell_page.py) (search for `compare_delta_to_delta` / `generateDateRangeReport` / inventory merge ~3265+).

**Implication:** subtracting endpoints is only valid when **both days share the same `baseline_date` coordinate system**. Crossing a **real baseline rotation** without reconstruction is **undefined** for inventory.

---

## Root cause A: GitHub Actions baseline cache (addressed in recent commits)

- Baseline artifacts were cached under a key that **did not uniquely identify the run/day** (monthly collision pattern described in commit `9178fcf`).
- GitHub cache is **immutable per exact key**; later runs do not overwrite the same key.
- Effect: baseline restore could be **wrong or stale**, **`save_daily_delta_from_baseline`** could **rotate the master baseline too often**, and **daily JSONs** (notably **2026-05-10 / 05-11**) could be **empty or wrong**.

**Fix landed in `9178fcf` (“Fix baseline persistence: per-day cache key + backfill 5/10 and 5/11”):**

- Baseline cache key is **`magelo-baseline-${{ steps.check-update.outputs.normalized_date }}`** with **`restore-keys: magelo-baseline-`** so the newest prior baseline still restores.
- Restore **`baseline_master_*.json.gz`** in the historical baseline restore path so **archives carry forward**.
- **Deleted bad** `delta_daily_2026-05-10.json.gz` / `delta_daily_2026-05-11.json.gz` and added **explicit backfill steps** (pattern matches **2026-02-07 / 2026-02-08**) that regenerate from **`magelo-dump-2026-05-10`** / **`magelo-dump-2026-05-11`** when cache hits, with **`auto_reset_baseline=False`** so backfill **never** rotates baseline.
- Hardened existing **2/7** and **2/8** backfills with **`auto_reset_baseline=False`**.

**Prior commit `08090e1`:** “Add historical delta JSONs from cached files” — bot commit adding/regenerating historical **`delta_snapshots/delta_daily_*.json.gz`** from CI cache.

**Workflow:** [`.github/workflows/daily-update.yml`](../.github/workflows/daily-update.yml) — search `magelo-baseline-`, `2026-05-10`, `2026-05-11`, `auto_reset_baseline=False`.

---

## Root cause B: Real baseline rotation + historical math (still open)

**Product expectation (confirmed):** **2026-05-12 should rotate** the master baseline. You **need** a baseline; rotation is correct.

After a **legitimate** rotation:

- The **first** daily file for the new era often has **`baseline_date` equal to that calendar day** and **empty** `inv_deltas` / `char_deltas` (everyone matches the **new** baseline snapshot). That is **coherent**, not “missing data.”

**Why users saw “nothing”:**

- Example range **2026-05-09 → 2026-05-12**: **`baseline_date`** differs (**2026-02-09** vs **2026-05-12**), and the **end** file can be **empty** for inventory. **`compare_delta_to_delta`** with **`baseline_characters=None`** across that boundary yields **zero inventory rows** even though the world changed.

**Why users saw “everything since ~2/8 / first snapshot”:**

- Inventory in each daily file is **cumulative since that file’s `baseline_date`** (the “Feb snapshot” era). When the UI or any code path treats that as “changes inside a short window,” or compares endpoints **without** a shared baseline, the user reads it as **all loot since the first baseline in that period** (early Feb), not “last three days.”

**Important:** If **`compare_delta_to_delta`** is ever invoked with **newer snapshot first** (reverse chronological), subtracting an **empty “new”** day from a **full “old”** day can explode to **full cumulative**-shaped output. The **browser** normalizes `start`/`end` so the earlier date is first (`generate_spell_page.js` block ~3150–3152); **other callers** (e.g. **`get_date_range_deltas`** in Python) should be checked for the same guarantee.

---

## GitHub cache vs repo (5/8–5/12)

- **5/10** and **5/11** are explicitly regenerated via **conditional** dump + baseline cache hits in the workflow.
- **5/12** is **not** in that backfill list; it comes from the **main** `generate_spell_page.py` run after today’s dump is restored.
- Having dumps in **Actions cache** for **5/8–5/12** helps backfill/regenerate, but **does not** by itself fix **delta-history** math across a baseline boundary.

---

## Update 2026-05-14 — still broken (handoff for the next owner)

This section summarizes what landed **after** the May 12 rotation, what **still fails**, and what to do next. Treat it as the live continuation of this doc.

### Symptoms still reported

- **`delta.html` “current delta”** looked like **months of character AA** (same failure mode as sparse JSON subtraction without the right baseline character map).
- **CI log (May 13 run)** showed `baseline_master.json.gz` still embedded **`2026-02-09`**, then **`save_daily_delta_from_baseline`** hit the **90-day auto-reset** and created a **new** baseline dated **`2026-05-13`** mid-run. That made **`delta_daily_2026-05-12`** vs **`delta_daily_2026-05-13`** use **different `baseline_date`**, so the generator printed **`Baseline transition (2026-05-12 -> 2026-05-13); using previous vs current Magelo files for delta.html`** and skipped the JSON day-over-day path for that day.
- **`delta-history` date-range AA leaderboard** (e.g. **2026-05-12 → 2026-05-14** or **2026-05-13 → 2026-05-14**) shows **impossible AA gains** (+250 AA in 1–2 days) even after “regenerate JSONs” for some days.

### Fixes already merged (do not revert without re-reading why)

| Change | Where | Purpose |
|--------|--------|---------|
| **`compare_delta_to_delta` uses era baseline chars** | [`generate_spell_page.py`](../generate_spell_page.py) (`load_baseline_for_date` for `today_delta['baseline_date']`) | Stops “quarter-scale” inflation when **yesterday/today share a baseline** and JSON compare runs. |
| **`auto_reset_baseline=False`** in main daily save | [`generate_spell_page.py`](../generate_spell_page.py) (`save_daily_delta_from_baseline(...)`) | Stops **surprise 90-day rotation** during the daily job while `baseline_master.json.gz` still carried an old embedded date. |
| **Align master to May 12 archive before generate** | [`.github/workflows/daily-update.yml`](../.github/workflows/daily-update.yml) step **“Align baseline_master.json.gz to May 12 rotation archive when present”** | Forces **`baseline_master.json.gz`** to match the **May 12** era before `generate_spell_page.py` so dailies are not still computed vs **Feb 9** until something auto-rotates. |
| **Early + late `sync_baseline_master_archive_from_master.py`** | `daily-update.yml` | Fetches / materializes missing **`baseline_master_<date>.json.gz`** where possible. |
| **`pickAbsStat` + red banner when `date < baseline_date`** | [`generate_spell_page.py`](../generate_spell_page.py) embedded **delta-history** JS | Avoids **`||`** dropping legitimate **0** stats; warns when an endpoint daily is the “dump before baseline_date” class (same idea as verify). |
| **Restore `baseline_master.json.gz` embedded date to May 12** | `delta_snapshots/baseline_master.json.gz` in git | Undoes accidental **May 13** master from the bad CI run (binary; resolve rebase conflicts by preferring **May 12** archive). |

**Known limitation:** the red banner only triggers when **`delta_daily.date` < `baseline_date`**. It does **not** catch **same-day** files (e.g. **`2026-05-12`**) whose rows are still **internally inconsistent** because the baseline snapshot used at write time did not match the dump.

### Root cause C (current): bad endpoint `delta_daily` rows + rotation-week data

Example inspected locally in **`delta_daily_2026-05-12.json.gz`** for **Tuned**:

- `baseline_date`: **`2026-05-12`** (metadata looks fine)
- `previous_aa_total`: **429**, `current_aa_total`: **173**, `aa_total_change`: **-256**

**`reconstructCharacterState`** (delta-history) applies **`current_aa_total`** from the row. If that number is wrong relative to the archived baseline + Magelo reality, the **start** of a short range becomes a false floor and the **end** day (e.g. May 14) looks like **hundreds of AA gained in two days**.

So: **regenerating only `2026-05-13` is not enough** if the user still picks **`2026-05-12`** (or **5/9–5/11**) as a range endpoint. **`verify_delta_baseline_archives.py`** already warns for **dump date before `baseline_date`**; **May 12** often does **not** trigger that warning because **`date == baseline_date`** even when the **row content** is still wrong from an earlier inconsistent CI state.

### What to do next (operator + engineer)

1. **Regenerate endpoint dailies for the fragile window** using [`.github/workflows/regenerate-delta-days.yml`](../.github/workflows/regenerate-delta-days.yml) with the **correct `baseline_era_date` per dump date** (each row needs **`date >= baseline_date`** in the written JSON). **Do not** use **`baseline_era_date: 2026-05-12`** for dumps **before** 2026-05-12 — that reproduces **`dump date < baseline_date`** (incoherent deltas; CI verify warns).
   - **Batch A — dumps `2026-05-09`, `2026-05-10`, `2026-05-11`:** `baseline_era_date: 2026-02-09` (pre-rotation era; requires `delta_snapshots/baseline_master_2026-02-09.json.gz` in repo or cache). `magelo-dump-<date>` caches must match each matrix date. `force: true`.
   - **Batch B — dumps `2026-05-12` onward** (e.g. `2026-05-12`, `2026-05-13`, `2026-05-14`): `baseline_era_date: 2026-05-12`. `force: true`.
   - **Typo check:** `baseline_era_date` must match the archive filename exactly (**`2026-05-12`**, not `2025-05-12`). If Actions reports a missing `baseline_master_YYYY-MM-DD.json.gz`, compare the year to the files in [`delta_snapshots/`](../delta_snapshots/) on `main`.
- **Sanity check after batch A:** `python -c "import gzip,json; print(json.load(gzip.open('delta_snapshots/delta_daily_2026-05-11.json.gz'))['baseline_date'])"` must print **`2026-02-09`**. If it still prints **`2026-05-12`**, batch A did not run (wrong input or commit not on the branch Pages built from).
   - If any `delta_daily` ever referenced a mistaken **`2026-05-13`** baseline era, include that date in batch B only after confirming the embedded `baseline_date` in `baseline_master_2026-05-12.json.gz` is correct.
   - After regen: **`python scripts/audit_delta_snapshots.py --from-date 2026-05-09 --to-date 2026-05-14 --fail-on-issue`** (expect **no** lines for 05-09..05-11 once batch A is correct). Spot-check AA rows: **`python scripts/audit_delta_snapshots.py --from-date 2026-05-12 --to-date 2026-05-14 --character Tuned`**. Optionally **`python scripts/verify_delta_baseline_archives.py --strict`** once all known bad files are fixed. Then **commit** the new **`delta_daily_*.json.gz`** files and redeploy.
2. **Re-run Daily Spell Inventory Update** (or wait for schedule) so **`delta-history.html`** is regenerated with the latest embedded JS.
3. **Hard-refresh** the site when testing (`delta-history.html` + JSON gzip are cacheable).
4. **Engineering follow-ups (pick any):**
   - **`data_quality` at write time** — **Done** in [`delta_storage.py`](../delta_storage.py) (`save_daily_delta_from_baseline`): embeds **`dump_before_baseline`** when ``date < baseline_date`` (wrong-era ``baseline_master``). Row-level AA sanity for same-day files still needs manual spot-check (e.g. ``python scripts/audit_delta_snapshots.py --character Tuned ...``) or future delta-history UI.
   - **`verify_delta_baseline_archives.py --strict`** — promotes **dump date `<` baseline_date** to **exit 1** for dailies on/after 2026-01-01 (enable in CI after bad historical files are regenerated or excluded).
   - Replace hardcoded **“copy `baseline_master_2026-05-12` → master”** in `daily-update.yml` with a **config file** or script driven by “current rotation anchor” so the next manual rotation does not require another workflow edit.
   - Decide whether **`baseline_master_2026-05-13.json.gz`** should remain in git if it was only created by the accidental auto-reset; remove only if **no** `delta_daily` still references **`baseline_date` = `2026-05-13`** (run verify + grep).

### Quick repro / inspection commands

```bash
cd /path/to/magelo
python scripts/verify_delta_baseline_archives.py --base-dir delta_snapshots
python scripts/verify_delta_baseline_archives.py --base-dir delta_snapshots --strict

python scripts/audit_delta_snapshots.py --from-date 2026-05-09 --to-date 2026-05-14 --fail-on-issue

python -c "
import gzip, json
from pathlib import Path
name = 'Tuned'
for p in sorted(Path('delta_snapshots').glob('delta_daily_2026-05-1*.json.gz')):
    j = json.load(gzip.open(p, 'rt', encoding='utf-8'))
    row = (j.get('char_deltas') or {}).get(name)
    print(p.name, 'baseline', j.get('baseline_date'), 'date', j.get('date'), 'row', row)
"
```

### File index (additions)

| Area | File |
|------|------|
| Main daily baseline alignment + no auto-reset in CI | [`.github/workflows/daily-update.yml`](../.github/workflows/daily-update.yml) |
| `delta.html` JSON compare baseline chars; daily `auto_reset_baseline=False` | [`generate_spell_page.py`](../generate_spell_page.py) |
| Baseline load rules | [`delta_storage.py`](../delta_storage.py) (`load_baseline_for_date`, `save_daily_delta_from_baseline`, `get_date_range_deltas`) |
| Regenerate matrix (May 2026 two-batch example in workflow header) | [`.github/workflows/regenerate-delta-days.yml`](../.github/workflows/regenerate-delta-days.yml) |
| Local one-day regen helper | [`scripts/regenerate_delta_daily_from_dump.py`](../scripts/regenerate_delta_daily_from_dump.py) |
| Audit dailies / AA sanity | [`scripts/audit_delta_snapshots.py`](../scripts/audit_delta_snapshots.py) |
| Verify baselines; optional ``--strict`` | [`scripts/verify_delta_baseline_archives.py`](../scripts/verify_delta_baseline_archives.py) |

---

## What to implement next (prioritized)

### 1. Deploy and repo: archived baselines

- Ensure **`baseline_master_<old_baseline_date>.json.gz`** exists where **`loadBaseline`** in **`delta-history`** can fetch it (see `generate_spell_page.py`: archived URL vs `baseline_master.json.gz` fallback).
- Workflow **Prepare for deployment** copies `delta_snapshots/baseline_master*.json.gz` into **`deploy/delta_snapshots/`**. Confirm the **post–5/12** artifact actually contains the **archived** file for the **pre–5/12** era so old dates are not silently using the **wrong** baseline for reconstruction.

### 2. delta-history: inventory across `baseline_date` mismatch

Pick one (or combine):

- **Guardrail (small change):** If `startDelta.baseline_date !== endDelta.baseline_date`, **disable or clearly label** inventory (and tracked-loot sections derived from it) with text: baseline rotated on …; pick both dates in the same baseline era, or implement reconstruction.
- **AA/HP leaderboards across rotation (May 2026):** Even with correct regen (`2026-05-11` → `baseline_date` `2026-02-09`), **Tuned** can have **no** `char_deltas` row on 5/11 (unchanged vs Feb at **173** AA — same as in `baseline_master_2026-05-12`). The **2026-05-14** daily then holds the first large cumulative row vs the new baseline (**+269** to **442**). Reconstructed range math **173 → 442** looks like three days of gains but is mostly **rotation + cumulative row placement**. **Mitigation:** for top-AA lists use **both dates on or after** the new baseline (e.g. `2026-05-12`–`2026-05-14`), or `delta.html` day-over-day. **Done in JS:** omit AA/HP leaderboards when `baseline_date` differs between range endpoints (see `generateDateRangeReport` in [`generate_spell_page.py`](../generate_spell_page.py)).
- **Reset-day UX:** If the **end** date’s daily JSON is a **baseline reset day** with empty `inv_deltas`, show an explicit **“inventory N/A for end date (baseline reset)”** or clamp guidance.
- **Correct fix (larger):** Reconstruct **full inventory** at each endpoint from **that endpoint’s baseline + cumulative delta** (parallel to **`reconstructCharacterState`** for stats), then diff **reconstructed** inventories for arbitrary ranges.

### 3. Python parity

- **`get_date_range_deltas`** in [`delta_storage.py`](../delta_storage.py): ensure **start/end chronological order** matches the JS contract if any caller passes reversed dates.

---

## Verification (local)

Inspect recent dailies: `baseline_date` and inventory volume.

```bash
cd /path/to/magelo   # repo root
python scripts/audit_delta_snapshots.py --prefix delta_daily_2026-05

python -c "
import gzip, json
from pathlib import Path
for p in sorted(Path('delta_snapshots').glob('delta_daily_2026-05-*.json.gz')):
    j = json.load(gzip.open(p, 'rt', encoding='utf-8'))
    inv = j.get('inv_deltas') or {}
    slots = sum(len(v.get('added', {})) + len(v.get('removed', {})) for v in inv.values())
    print(j.get('date'), 'baseline', j.get('baseline_date'), 'inv_chars', len(inv), 'slots', slots)
"
```

Cross-baseline range (expect broken inventory with current subtract-only logic):

```bash
python -c "
import sys
sys.path.insert(0, '.')
from delta_storage import load_daily_delta_json, compare_delta_to_delta
base = 'delta_snapshots'
a = load_daily_delta_json('2026-05-09', base)
b = load_daily_delta_json('2026-05-12', base)
r = compare_delta_to_delta(a, b, None)
inv = r['inv_deltas']
slots = sum(len(v.get('added', {})) + len(v.get('removed', {})) for v in inv.values())
print('2026-05-09 vs 2026-05-12 inv slots (baseline mismatch):', slots)
"
```

---

## Tooling: Pages artifact analyzer

[`scripts/analyze_github_pages_artifact.py`](../scripts/analyze_github_pages_artifact.py) — point at a downloaded **`github-pages-*.zip`** or unpacked **`deploy/`** root:

```bash
python scripts/analyze_github_pages_artifact.py --path /path/to/artifact.zip --sample-days 5 --json
```

Use it to confirm **`baseline_names`**, last days’ **`baseline_date`**, and sudden drops in **`inv_chars`** on the **rotation day**.

---

## File index

| Area | File |
|------|------|
| CI baseline cache, 5/10–5/11 backfill | [`.github/workflows/daily-update.yml`](../.github/workflows/daily-update.yml) |
| Daily gzip schema, `compare_delta_to_delta`, `get_date_range_deltas` | [`delta_storage.py`](../delta_storage.py) |
| delta-history JS, `generateDateRangeReport`, `loadBaseline` | [`generate_spell_page.py`](../generate_spell_page.py) |
| Pages artifact inspection | [`scripts/analyze_github_pages_artifact.py`](../scripts/analyze_github_pages_artifact.py) |
| Audit dailies / AA sanity | [`scripts/audit_delta_snapshots.py`](../scripts/audit_delta_snapshots.py) |
| Verify baselines; optional ``--strict`` | [`scripts/verify_delta_baseline_archives.py`](../scripts/verify_delta_baseline_archives.py) |

---

## One-line summary

**CI cache collision caused bad mid-May dailies (mitigated with per-day keys + 5/10–5/11 backfill and `auto_reset_baseline=False` on backfills).** **2026-05-12 baseline rotation is intended.** **As of 2026-05-14 the product is still broken in places:** **surprise master baseline / May 13 era** (mitigated by disabling main-job auto-reset + aligning master to the May 12 archive in CI), **bad or inconsistent `delta_daily` endpoint rows** (especially rotation week — still need regen + optional schema flags), and **delta-history range leaderboards** that trust those JSONs. Original doc pain also remains: **inventory math and UX across `baseline_date` boundaries** plus **archived baselines on Pages** for `loadBaseline`.
