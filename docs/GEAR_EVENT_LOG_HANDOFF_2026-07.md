# Handoff: Gear event log storage (July 2026)

Replaces cumulative `delta_daily_*.json.gz` growth (~76 MB, unbounded per baseline era) with an append-only **gear event log** (~2.5 MB gz for full backfilled history).

---

## What changed

| Before | After |
|--------|-------|
| Each day commits `delta_daily_DATE.json.gz` (cumulative vs baseline) | Each day appends rows to `delta_snapshots/gear_events/gear_YYYY-MM.json.gz` |
| `delta.html` subtracts two cumulative JSONs | `delta.html` diffs previous vs current Magelo dumps (true day-over-day); gear events are persisted separately for history |
| `get_date_range_deltas` diffs two cumulative endpoints | Prefers folding events in `(start, end]` when both dates are in `manifest.json` |
| ~622 KB/day average gz growth | ~tens of KB/day append |

**Baseline** (`baseline_master.json.gz`, ~19 MB) is unchanged — still required for full inventory reconstruction.

---

## On-disk layout

```
delta_snapshots/
  baseline_master.json.gz
  gear_events/
    manifest.json              # per-day event counts + era metadata
    gear_2026-05.json.gz       # inventory +/- events
    char_2026-05.json.gz       # level/AA/HP stat events
    ...
```

**Event row (gear):** `{"d":"2026-05-14","c":"CharName","i":"12345","s":1,"n":1,"v":0}`

- `s`: `+1` gain, `-1` loss  
- `v`: `1` = visibility/anon toggle (filterable; ~46% of raw rows in backfill)  
- Item names omitted — resolved at display from inventory / `data/item_name_to_id.json`

Events are created only from **true day-over-day Magelo dump diffs** (`append_day_events`), never from baseline-vs-current comparison. That avoids false all-lost/all-gained spikes on baseline rotation.

---

## Key files

| Area | Path |
|------|------|
| Storage API | [`gear_event_storage.py`](../gear_event_storage.py) |
| Range deltas (Python) | [`delta_storage.py`](../delta_storage.py) — `get_date_range_deltas` |
| Daily pipeline + HTML | [`generate_spell_page.py`](../generate_spell_page.py) |
| Backfill from legacy dailies | [`scripts/backfill_gear_events_from_dailies.py`](../scripts/backfill_gear_events_from_dailies.py) |
| CI audit | [`scripts/audit_gear_events.py`](../scripts/audit_gear_events.py) |
| Tests | [`tests/test_gear_event_storage.py`](../tests/test_gear_event_storage.py) |
| CI commit/deploy | [`.github/workflows/daily-update.yml`](../.github/workflows/daily-update.yml) |

---

## Operator commands

**Backfill / refresh shards from legacy cumulative dailies (offline archive):**

Point `--base-dir` at a folder containing archived `delta_daily_*.json.gz` (removed from git July 2026; kept locally e.g. `magelo-archive/delta_daily_legacy/`):

```bash
cd magelo
python scripts/backfill_gear_events_from_dailies.py --base-dir /path/to/delta_daily_legacy --clear --parity
```

**Audit:**

```bash
python scripts/audit_gear_events.py --base-dir delta_snapshots --fail-on-issue
```

**Optional dual-write (legacy cumulative daily JSON):**

```bash
export MAGELO_WRITE_CUMULATIVE_DAILY=1
python generate_spell_page.py
```

Default: cumulative dailies are **not** written.

---

## CI behavior

1. `generate_spell_page.py` calls `append_day_events(previous, current, date)`.
2. Job commits `delta_snapshots/gear_events/` (not new `delta_daily_*.json.gz`).
3. Deploy copies `gear_events/` + baselines to GitHub Pages.
4. Smoke check curls `delta_snapshots/gear_events/gear_YYYY-MM.json.gz` for export month.

Legacy `delta_daily_*.json.gz` are **not in the repo** (gitignored). `delta-history.html` falls back to cumulative JSON only when gear shards are missing on Pages.

---

## delta-history.html (client)

When gear shards exist at build time, generated HTML sets `USE_GEAR_EVENTS = true` and embeds `GEAR_EVENT_SHARD_MONTHS`. Range reports load monthly shards and fold events (`start < d <= end`). Legacy cumulative JSON path remains as fallback.

**Note:** Event-based range totals can differ slightly from old endpoint cumulative subtraction when characters drop out of sparse cumulative rows but had intermediate oscillations — the event log is the intended source of truth for “what happened each day.”

---

## Gaps / follow-ups

1. **`ABANDONED_DATES.txt`** (2026-05-09 … 05-13): no events until regen dumps exist; backfill skips those days.
2. **Cross-era ranges:** event log does not yet replace `compare_delta_to_delta_reconstructed` for ranges spanning baseline rotation — legacy cumulative JSON from offline archive + baselines still needed for that edge case in Python until era tags are used end-to-end in JS.
3. **Git history:** old `delta_daily_*.json.gz` remain in history (~76 MB); optional `git filter-repo` cleanup is separate. **Repo tip (Jul 2026):** ~150 daily files removed from tree; archive locally before any regen.
4. **Item timelines in UI:** `item_history()` / `detect_oscillations()` exist in Python; no dedicated UI yet (phase 2).
5. **Local branch:** pull/rebase before push if behind `origin/main` (CI bot commits).
6. **Backfill regen after inflation fix:** if `delta.html` or audit flagged inflated days, re-run:
   ```bash
   python scripts/backfill_gear_events_from_dailies.py --base-dir delta_snapshots --dry-run
   python scripts/backfill_gear_events_from_dailies.py --base-dir delta_snapshots --clear --parity
   python scripts/audit_gear_events.py --base-dir delta_snapshots --fail-on-issue
   ```
   CI `append_day_events()` overwrites each calendar day going forward; historical days need regen or manual clear.

---

## Validation performed

- `python scripts/backfill_gear_events_from_dailies.py --parity` → Parity OK  
- `python -m unittest tests.test_gear_event_storage tests.test_delta_baseline_transition` → all passed  
- `python scripts/audit_gear_events.py` → 11 shards, 519239 events, 123 manifest days  

---

## One-line summary

**Gear history is now dated +/- events under `delta_snapshots/gear_events/` (~3 MB vs ~76 MB dailies); CI appends from dump diffs; `delta.html` and `get_date_range_deltas` read the log first; legacy cumulative JSON is fallback only.**
