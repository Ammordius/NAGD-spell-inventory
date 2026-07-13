#!/usr/bin/env python3
"""Prune unique tracked corpse/over-reset pairs from gear_events shards.

Uses baseline inventories + LORE/NO DROP unique tracked set so:
- death then recovery within 14 days cancels both events
- duplicate + after already ever-held (dump gap) drops the reacquire +
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from delta_storage import load_master_baseline  # noqa: E402
from gear_event_storage import (  # noqa: E402
    _gear_shard_path,
    _list_all_shard_months,
    _load_shard_gz,
    _manifest_path,
    _save_shard_gz,
    load_gear_events,
    prune_unique_reacquire_events,
    GEAR_SHARD_RE,
)
from generate_spell_page import (  # noqa: E402
    load_no_rent_items,
    load_tracked_item_ids,
    load_unique_tracked_item_ids,
)


def _recount_manifest_gear(base_dir: Path, events: list[dict]) -> None:
    path = _manifest_path(str(base_dir))
    if not Path(path).is_file():
        print(f"Warning: no manifest at {path}; skipping manifest recount")
        return
    with open(path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    days = manifest.setdefault("days", {})
    by_day = Counter(e.get("d") for e in events if e.get("d"))
    for date_str, meta in list(days.items()):
        if not isinstance(meta, dict):
            continue
        meta["gear"] = int(by_day.get(date_str, 0))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def prune(
    base_dir: Path,
    *,
    dry_run: bool = False,
    window_days: int = 14,
) -> tuple[int, int]:
    tracked, _, _, _ = load_tracked_item_ids()
    unique = load_unique_tracked_item_ids(tracked)
    no_rent = {str(i) for i in load_no_rent_items()}
    baseline = load_master_baseline(str(base_dir)) or {}
    baseline_inv = baseline.get("inventories") or {}

    before = load_gear_events(str(base_dir))
    after = prune_unique_reacquire_events(
        before,
        unique,
        baseline_inv,
        window_days=window_days,
        no_rent=no_rent,
    )
    removed = len(before) - len(after)
    print(
        f"Unique tracked: {len(unique)}; events before={len(before)} after={len(after)} "
        f"removed={removed} (window={window_days}d)"
    )
    if dry_run:
        return len(before), len(after)

    by_month: dict[str, list[dict]] = defaultdict(list)
    for ev in after:
        d = ev.get("d") or ""
        if len(d) >= 7:
            by_month[d[:7]].append(ev)

    months = _list_all_shard_months(str(base_dir), GEAR_SHARD_RE)
    for month in months:
        path = _gear_shard_path(str(base_dir), month)
        events = by_month.get(month, [])
        events.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("i", "")))
        _save_shard_gz(path, events)
        print(f"  wrote {month}: {len(events)} events")
        # Drop month from by_month so leftovers are handled
        by_month.pop(month, None)

    for month, events in sorted(by_month.items()):
        path = _gear_shard_path(str(base_dir), month)
        events.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("i", "")))
        _save_shard_gz(path, events)
        print(f"  wrote new month {month}: {len(events)} events")

    _recount_manifest_gear(base_dir, after)
    print(f"Updated {_manifest_path(str(base_dir))} gear day counts")
    return len(before), len(after)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-dir",
        default=str(MAGELO_ROOT / "delta_snapshots"),
        help="delta_snapshots directory (default: repo delta_snapshots)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report counts only; do not rewrite shards",
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=14,
        help="Max days between loss and reacquire to cancel (default 14)",
    )
    args = parser.parse_args()
    base = Path(args.base_dir)
    if not base.is_dir():
        print(f"Missing base dir: {base}", file=sys.stderr)
        return 1
    prune(base, dry_run=args.dry_run, window_days=args.window_days)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
