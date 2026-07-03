#!/usr/bin/env python3
"""Backfill gear_events monthly shards from consecutive delta_daily JSON pairs."""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from delta_storage import compare_delta_to_delta, load_master_baseline  # noqa: E402
from gear_event_storage import (  # noqa: E402
    append_day_events_from_deltas,
    events_to_delta_shape,
    gear_events_available,
    get_range_delta_from_events,
    list_available_event_dates,
    load_gear_events,
)

DELTA_DAILY_RE = re.compile(r"^delta_daily_(\d{4}-\d{2}-\d{2})\.json\.gz$")
ABANDONED_FILE = "ABANDONED_DATES.txt"


def _load_abandoned(base_dir: Path) -> set[str]:
    path = base_dir / ABANDONED_FILE
    if not path.is_file():
        return set()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        out.add(line)
    return out


def _list_delta_dates(base_dir: Path) -> list[str]:
    dates = []
    for f in base_dir.iterdir():
        m = DELTA_DAILY_RE.match(f.name)
        if m:
            dates.append(m.group(1))
    return sorted(dates)


def _load_delta(base_dir: Path, date_str: str) -> dict | None:
    path = base_dir / f"delta_daily_{date_str}.json.gz"
    if not path.is_file():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def _daily_degenerate(daily: dict | None) -> bool:
    """True when a cumulative daily JSON is unsuitable as a backfill pair endpoint."""
    if not daily:
        return True
    dq = daily.get("data_quality") or {}
    if dq.get("dump_before_baseline"):
        return True
    if not (daily.get("char_deltas") or {}):
        return True
    return False


def _derived_event_counts(diff: dict) -> tuple[int, int]:
    char_n = len(diff.get("char_deltas") or {})
    inv_n = sum(
        len((row.get("added") or {})) + len((row.get("removed") or {}))
        for row in (diff.get("inv_deltas") or {}).values()
    )
    return char_n, inv_n


def backfill(
    base_dir: Path | str,
    *,
    clear: bool = False,
    skip_abandoned: bool = True,
    dry_run: bool = False,
    anomaly_median_factor: float = 5.0,
) -> dict:
    base_dir = Path(base_dir)
    if clear:
        gear_root = base_dir / "gear_events"
        if gear_root.is_dir():
            for f in gear_root.iterdir():
                f.unlink()
    abandoned = _load_abandoned(base_dir) if skip_abandoned else set()
    dates = _list_delta_dates(base_dir)
    bl = load_master_baseline(str(base_dir))
    baseline_chars = (bl or {}).get("characters")

    pairs = 0
    days_written = 0
    skipped = 0
    skipped_degenerate = 0
    derived_counts: list[tuple[str, int, int]] = []
    anomalies: list[str] = []
    for i in range(1, len(dates)):
        prev_date, curr_date = dates[i - 1], dates[i]
        if curr_date in abandoned:
            skipped += 1
            continue
        da = _load_delta(base_dir, prev_date)
        db = _load_delta(base_dir, curr_date)
        if not da or not db:
            skipped += 1
            continue
        if da.get("baseline_date") != db.get("baseline_date"):
            skipped += 1
            continue
        if _daily_degenerate(da):
            skipped += 1
            skipped_degenerate += 1
            continue
        pairs += 1
        diff = compare_delta_to_delta(da, db, baseline_chars)
        char_n, inv_n = _derived_event_counts(diff)
        derived_counts.append((curr_date, char_n, inv_n))
        if not dry_run:
            append_day_events_from_deltas(
                diff.get("char_deltas") or {},
                diff.get("inv_deltas") or {},
                curr_date,
                str(base_dir),
                db.get("baseline_date"),
            )
            days_written += 1

    if len(derived_counts) >= 7:
        import statistics

        char_vals = [c for _, c, _ in derived_counts]
        inv_vals = [i for _, _, i in derived_counts]
        char_med = statistics.median(char_vals)
        inv_med = statistics.median(inv_vals)
        for curr_date, char_n, inv_n in derived_counts:
            if char_med > 0 and char_n > char_med * anomaly_median_factor:
                anomalies.append(
                    f"{curr_date}: {char_n} char rows vs median {char_med:.0f}"
                )
            if inv_med > 0 and inv_n > inv_med * anomaly_median_factor:
                anomalies.append(
                    f"{curr_date}: {inv_n} inv event rows vs median {inv_med:.0f}"
                )

    return {
        "pairs": pairs,
        "days_written": days_written,
        "skipped": skipped,
        "skipped_degenerate": skipped_degenerate,
        "dry_run": dry_run,
        "anomalies": anomalies,
        "event_dates": len(list_available_event_dates(str(base_dir))),
    }


def _net_inv_map(inv_deltas: dict | None) -> dict[str, dict[str, int]]:
    """Per-character net item counts (positive = gained, negative = lost)."""
    out: dict[str, dict[str, int]] = {}
    for char, row in (inv_deltas or {}).items():
        nets: dict[str, int] = {}
        for iid, n in (row.get("added") or {}).items():
            nets[str(iid)] = nets.get(str(iid), 0) + int(n)
        for iid, n in (row.get("removed") or {}).items():
            nets[str(iid)] = nets.get(str(iid), 0) - int(n)
        nets = {k: v for k, v in nets.items() if v != 0}
        if nets:
            out[char] = nets
    return out


def parity_check(base_dir: Path | str, sample_count: int = 5) -> list[str]:
    """Compare folded event ranges vs sum of per-day events (internal consistency)."""
    base_dir = Path(base_dir)
    issues: list[str] = []
    dates = list_available_event_dates(str(base_dir))
    if len(dates) < 2:
        return ["not enough event dates for parity check"]
    step = max(1, len(dates) // sample_count)
    for i in range(0, len(dates) - 1, step):
        start, end = dates[i], dates[min(i + step, len(dates) - 1)]
        if start == end:
            continue
        folded = get_range_delta_from_events(start, end, str(base_dir))
        gear = load_gear_events(
            str(base_dir), start_date=start, end_date=end, exclusive_start=True
        )
        manual = events_to_delta_shape(gear, [])
        if _net_inv_map(folded.get("inv_deltas")) != _net_inv_map(manual.get("inv_deltas")):
            issues.append(f"{start}->{end}: fold vs manual mismatch")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-dir", type=Path, default=Path("delta_snapshots"))
    ap.add_argument("--clear", action="store_true", help="Remove existing gear_events before backfill")
    ap.add_argument("--dry-run", action="store_true", help="Compute stats only; do not write shards")
    ap.add_argument("--parity", action="store_true", help="Run parity checks after backfill")
    ap.add_argument("--parity-only", action="store_true", help="Only run parity checks")
    args = ap.parse_args()
    base_dir = args.base_dir
    if not base_dir.is_dir():
        print(f"ERROR: {base_dir} not found", file=sys.stderr)
        return 1

    if args.parity_only:
        if not gear_events_available(str(base_dir)):
            print("ERROR: no gear_events shards found", file=sys.stderr)
            return 1
        issues = parity_check(base_dir)
        if issues:
            for issue in issues:
                print(f"PARITY: {issue}")
            return 1
        print("Parity OK")
        return 0

    stats = backfill(base_dir, clear=args.clear, dry_run=args.dry_run)
    print(json.dumps(stats, indent=2))
    if stats.get("anomalies"):
        print("ANOMALY (possible cumulative inflation in backfill source):")
        for line in stats["anomalies"]:
            print(f"  {line}")

    if args.parity and not args.dry_run:
        issues = parity_check(base_dir)
        if issues:
            for issue in issues:
                print(f"PARITY: {issue}")
            return 1
        print("Parity OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
