#!/usr/bin/env python3
"""Audit gear_events monthly shards under delta_snapshots/gear_events/."""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from gear_event_storage import list_available_event_dates  # noqa: E402


def audit(base_dir: Path, min_events_after: str | None, *, anomaly_median_factor: float = 5.0) -> list[str]:
    issues: list[str] = []
    gear_root = base_dir / "gear_events"
    if not gear_root.is_dir():
        issues.append("gear_events/ directory missing")
        return issues

    manifest_path = gear_root / "manifest.json"
    manifest: dict = {}
    if not manifest_path.is_file():
        issues.append("manifest.json missing")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not manifest.get("days"):
                issues.append("manifest days empty")
        except json.JSONDecodeError:
            issues.append("manifest.json invalid JSON")

    shards = sorted(gear_root.glob("gear_*.json.gz"))
    if not shards:
        issues.append("no gear_*.json.gz shards")
        return issues

    total_events = 0
    for shard in shards:
        try:
            with gzip.open(shard, "rt", encoding="utf-8") as f:
                events = json.load(f)
            if not isinstance(events, list):
                issues.append(f"{shard.name}: not a JSON list")
                continue
            total_events += len(events)
            if len(events) == 0:
                issues.append(f"{shard.name}: empty shard")
        except OSError as e:
            issues.append(f"{shard.name}: read error {e}")

    dates = list_available_event_dates(str(base_dir))
    days_meta = manifest.get("days") or {}
    if min_events_after and dates:
        for d in dates:
            if d >= min_events_after:
                day_events = 0
                month = d[:7]
                shard = gear_root / f"gear_{month}.json.gz"
                if shard.is_file():
                    with gzip.open(shard, "rt", encoding="utf-8") as f:
                        for ev in json.load(f):
                            if ev.get("d") == d:
                                day_events += 1
                if day_events == 0:
                    meta = days_meta.get(d) or {}
                    manifest_total = int(meta.get("gear") or 0) + int(meta.get("char") or 0)
                    if manifest_total == 0:
                        # Blind-skip only for known empty days that are not the newest
                        # day surrounded by healthy neighbors (N→0 wipe detection).
                        continue
                    issues.append(f"no gear events for {d}")

    day_counts: list[tuple[str, int]] = []
    for d in sorted(days_meta.keys()):
        meta = days_meta[d] or {}
        total = int(meta.get("gear") or 0) + int(meta.get("char") or 0)
        day_counts.append((d, total))

    # Flag newest-day wipe: manifest 0 while recent neighbors are healthy.
    if day_counts:
        newest_d, newest_total = day_counts[-1]
        if min_events_after is None or newest_d >= min_events_after:
            neighbors = [
                total
                for d, total in day_counts[-8:-1]
                if (min_events_after is None or d >= min_events_after)
            ]
            healthy_neighbors = [t for t in neighbors if t >= 50]
            if newest_total == 0 and len(healthy_neighbors) >= 2:
                issues.append(
                    f"{newest_d}: 0 events but {len(healthy_neighbors)} recent neighbor "
                    f"days average {sum(healthy_neighbors) / len(healthy_neighbors):.0f} "
                    "(possible empty rewrite wipe)"
                )

    if len(day_counts) >= 7:
        import statistics

        vals = [c for _, c in day_counts]
        med = statistics.median(vals)
        if med > 0:
            for d, total in day_counts:
                if min_events_after and d < min_events_after:
                    continue
                if total > med * anomaly_median_factor:
                    issues.append(
                        f"{d}: {total} events vs manifest median {med:.0f} "
                        f"({total / med:.1f}x; possible backfill inflation)"
                    )

    print(f"gear_events: {len(shards)} shards, {total_events} total events, {len(dates)} days in manifest")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-dir", type=Path, default=Path("delta_snapshots"))
    ap.add_argument("--min-events-after", type=str, default=None)
    ap.add_argument("--fail-on-issue", action="store_true")
    args = ap.parse_args()
    issues = audit(args.base_dir, args.min_events_after)
    for issue in issues:
        print(f"ISSUE: {issue}")
    if issues and args.fail_on_issue:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
