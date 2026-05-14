#!/usr/bin/env python3
"""Verify delta_snapshots: baseline archives for cross-era math, and daily JSON sanity.

Exit 1 if any referenced baseline_date cannot be resolved (see delta_storage.load_baseline_for_date)
for delta_daily files from 2026-01-01 onward (required for delta-history / cross-era ranges).

Dump dates strictly before ``baseline_date`` are reported as warnings only (backfill / mixed-era
snapshots are allowed in CI).

Older pinned dailies (e.g. 2024) are skipped; they predate the current baseline archive layout.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Only enforce archive resolution / forward-order for modern snapshot layout.
EARLIEST_VERIFY_DATE = "2026-01-01"
# Baselines before this predate archived ``baseline_master_<date>.json.gz`` in repo.
BASELINE_ARCHIVE_CUTOFF = "2026-02-01"


def _parse_iso(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def _days_between(a: str, b: str) -> int:
    """Calendar days from date a to date b (a, b are YYYY-MM-DD)."""
    return (_parse_iso(b) - _parse_iso(a)).days


def _embedded_master_baseline_date(gz_path: Path) -> str | None:
    if not gz_path.is_file():
        return None
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    bd = data.get("baseline_date")
    return str(bd) if bd not in (None, "", "Unknown") else None


def baseline_resolvable(baseline_date: str, base_dir: Path) -> bool:
    """Mirror delta_storage.load_baseline_for_date without importing generate_spell_page side effects."""
    if not baseline_date or baseline_date == "Unknown":
        return True
    archive = base_dir / f"baseline_master_{baseline_date}.json.gz"
    if archive.is_file():
        return True
    master = base_dir / "baseline_master.json.gz"
    emb = _embedded_master_baseline_date(master)
    return emb is not None and str(emb) == str(baseline_date)


def iter_daily_gz(base_dir: Path) -> list[Path]:
    out = sorted(base_dir.glob("delta_daily_*.json.gz"))
    return out


def daily_file_date(path: Path) -> str | None:
    m = re.match(r"delta_daily_(\d{4}-\d{2}-\d{2})\.json\.gz$", path.name)
    return m.group(1) if m else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-dir",
        type=Path,
        default=Path("delta_snapshots"),
        help="Directory containing delta_daily_*.json.gz and baseline_master*.json.gz",
    )
    args = ap.parse_args()
    base_dir = args.base_dir.resolve()
    if not base_dir.is_dir():
        print(f"ERROR: not a directory: {base_dir}", file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    baseline_dates_need_resolution: set[str] = set()

    for path in iter_daily_gz(base_dir):
        file_date = daily_file_date(path)
        if not file_date:
            warnings.append(f"{path.name}: could not parse date from filename")
            continue
        if file_date < EARLIEST_VERIFY_DATE:
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                doc = json.load(f)
        except OSError as e:
            errors.append(f"{path.name}: cannot read gzip ({e})")
            continue
        bd = doc.get("baseline_date") or "Unknown"
        if bd != "Unknown":
            bd_s = str(bd)
            # Same-day-or-later dumps in this era require a resolvable baseline snapshot.
            if _days_between(bd_s, file_date) >= 0:
                baseline_dates_need_resolution.add(bd_s)
            gap_days = _days_between(file_date, bd_s)
            if gap_days >= 1:
                msg = (
                    f"{path.name}: dump date {file_date} is before baseline_date {bd_s} "
                    f"({gap_days} day(s)) - likely wrong baseline snapshot when generating this file; "
                    f"regenerate with the correct era (see .github/workflows/regenerate-delta-days.yml "
                    f"baseline_era_date)."
                )
                warnings.append(msg)
        if bd == "Unknown":
            warnings.append(f"{path.name}: missing baseline_date in JSON")

    for bd in sorted(baseline_dates_need_resolution):
        if bd < BASELINE_ARCHIVE_CUTOFF:
            continue
        if not baseline_resolvable(bd, base_dir):
            errors.append(
                f"baseline_date={bd!r} is not resolvable under {base_dir}: need "
                f"baseline_master_{bd}.json.gz OR baseline_master.json.gz whose embedded "
                f"baseline_date matches (required for delta-history / cross-era ranges)."
            )

    for msg in warnings:
        print(f"WARNING: {msg}")
    for msg in errors:
        print(f"ERROR: {msg}", file=sys.stderr)

    if errors:
        return 1
    print(f"OK: verified {len(list(iter_daily_gz(base_dir)))} delta_daily_*.json.gz in {base_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
