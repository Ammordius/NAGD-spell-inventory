# Handoff: Jul 4 gear events via local Jul 3 state (no cache repair)

**Status:** Jul 4 **validated and regenerated** locally — do **not** repair GitHub `magelo-dump-2026-07-03`.  
**Decision:** Keep Jul 4 gear events (1909 total); do **not** abandon Jul 4.

**Supersedes cache-reseed plan:** GitHub Actions dump caches may stay stale; daily truth is **verified local/export file pairs**, not event reconstruction.

**See also:** [GEAR_EVENT_CI_STATE_2026-07-04.md](GEAR_EVENT_CI_STATE_2026-07-04.md), [GEAR_EVENT_INFLATION_HANDOFF_2026-07-04.md](GEAR_EVENT_INFLATION_HANDOFF_2026-07-04.md)

---

## Strategy (operator)

1. **Jul 3 ground truth** = local `TAKP_character_previous.txt` / `TAKP_character_inventory_previous.txt` (verified vs audit index: 38746 / 1724310 lines).
2. **Jul 4 current** = fetch from TAKP export URLs (matches local workspace MD5 as of 2026-07-04).
3. **Diff** prev vs curr → if reasonable (~2k inv rows, ~90 char, guard PASS), run `generate_spell_page.py` and commit gear shards + `delta.html`.
4. **If diff fails** (inflated / guard refuse): add date to `ABANDONED_DATES.txt`, skip that day's gear write, let next run absorb a 2-day span.

**Do not** use `baseline + gear_events` as Jul 3 substitute — reconstruction drift ~73k inv rows vs real Jul 3 dump.

---

## Validation results (2026-07-04 session)

### Reconstruction parity (NOT viable for Jul 3)

```text
python scripts/verify_reconstruction_parity.py --date 2026-07-03 --prev-date 2026-07-03 --curr-date 2026-07-04
```

| Check | Result |
|-------|--------|
| Events loaded through Jul 3 | 145,138 |
| recon vs Jul 3 dump inv rows | **73,249** |
| recon vs Jul 3 dump char keys | **716** |
| Ground truth Jul3→Jul4 inv rows | **2,028** |
| Ground truth estimated events | **2,165** |

### Local Jul 3 + fetched Jul 4 (PASS)

```text
python scripts/validate_day_over_day_dump_diff.py --prev-date 2026-07-03 --curr-date 2026-07-04 --fetch-current
```

| Metric | Value |
|--------|-------|
| inv rows | 2,028 |
| char meaningful | 91 |
| estimated events | 2,165 |
| manifest median | 871 |
| guard_gear_event | **PASS** |

Web fetch vs local Jul 4: char/inv MD5 match (38755 / 1724812 lines).

### Regeneration

```powershell
$env:MAGELO_UPDATE_DATE = "Sat Jul  4 16:30:25 UTC 2026"
python generate_spell_page.py
python scripts/audit_gear_events.py --base-dir delta_snapshots --min-events-after 2026-06-27 --fail-on-issue
```

Output: `Saved gear_events: 1794 inventory rows, 115 stat rows` (1909 total) — matches committed manifest.

Committed estimate (2165) vs shard rows (1909): difference from no-rent filtering and visibility/event folding — expected and within guard.

---

## Why GitHub cache still shows Feb 7 under Jul 3 key

Pre-`fb19313` workflow could save **wrong-era file content** under a calendar cache key when:

- `restore-keys: magelo-dump-` restored an old blob,
- stamp line 1 was rewritten to match scrape date without re-download,
- `refresh_magelo_previous` copied stale content and aligned stamps.

Fingerprint verification (`fb19313`+) now **rejects** that blob in CI. **No cache repair required** for this fix — local Jul 3 files are authoritative.

---

## Operator scripts

| Script | Purpose |
|--------|---------|
| [`scripts/validate_day_over_day_dump_diff.py`](../scripts/validate_day_over_day_dump_diff.py) | Fetch current export, diff vs `_previous`, guard check, optional `--run-generate` |
| [`scripts/verify_reconstruction_parity.py`](../scripts/verify_reconstruction_parity.py) | Prove event reconstruction ≠ dump snapshot |
| [`scripts/prepare_magelo_dump_cache_seed.py`](../scripts/prepare_magelo_dump_cache_seed.py) | Optional; only if re-seeding Actions cache later (not required) |

### Validate another day

```powershell
cd c:\TAKP\magelo
python scripts/validate_day_over_day_dump_diff.py `
  --prev-date 2026-07-03 --curr-date 2026-07-04 --fetch-current `
  --run-generate
```

### Abandon path (if validation FAILs)

```powershell
python scripts/validate_day_over_day_dump_diff.py `
  --prev-date 2026-07-03 --curr-date 2026-07-04 --fetch-current `
  --print-abandon-instructions
```

Then:

1. Add `2026-07-04` to [`delta_snapshots/ABANDONED_DATES.txt`](../delta_snapshots/ABANDONED_DATES.txt)
2. Remove Jul 4 from `gear_events/manifest.json` and trim shards
3. On Jul 5 export: keep Jul 3 `_previous`, fetch Jul 5 current → 2-day delta attributed to Jul 5

---

## Jul 5+ CI expectations (no cache fix)

| Scenario | Expected CI behavior |
|----------|---------------------|
| Jul 4 job saves good `magelo-dump-2026-07-04` with fingerprint | Jul 5 run verifies yesterday normally (~800–1100 events) |
| Jul 4 cache still stale | Stale fallback may skip dump diff; gear for Jul 5 may need **same local validate + generate** pattern |
| Jul 4 abandoned | Jul 5 diff spans 2 days; event count may be ~2× median — watch guard logs |

Monitor checklist:

- [ ] No `Refusing gear-event write` on export day
- [ ] `audit_gear_events.py --min-events-after` passes after bot commit
- [ ] `delta.html` shows Jul 3 → Jul 4 span in header when `_previous` is verified locally

---

## Files touched by local fix

- `delta_snapshots/gear_events/` — Jul 4 shards (already in git; regenerated locally confirms 1909 events)
- `delta.html` — regenerated from true Jul 3 `_previous` vs Jul 4 current
- `character/.magelo_dump_index.json` — Jul 3/4 line counts (audit)

Do **not** commit `character/*.txt`, `inventory/*.txt`, or `.magelo_update_date` (gitignored).

---

## Summary for next agent

**Jul 4 is fixable without cache repair.** Use local verified Jul 3 `_previous` + TAKP Jul 4 export; validation PASS at ~2165 estimated events; regeneration yields 1909 committed gear events. Reconstruction from cumulative gear events is **not** a substitute for Jul 3 dumps. If a future day fails validation, abandon that calendar date and catch up on the next export with a 2-day diff.
