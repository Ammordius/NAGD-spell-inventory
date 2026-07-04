#!/usr/bin/env python3
"""Compare gear-event reconstruction vs real Magelo dumps (diagnostic only).

Shows why baseline+gear_events cannot substitute for yesterday's export in daily CI.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from gear_event_storage import (  # noqa: E402
    build_possession_map,
    load_gear_events,
    possession_from_inv_snapshot,
    diff_absolute_possession_maps,
    reconstruct_char_data_at_date,
)
from generate_spell_page import (  # noqa: E402
    _count_inv_event_rows,
    _count_meaningful_char_deltas,
    _estimate_delta_event_total,
    compare_character_data,
    compare_inventories,
    parse_character_data,
    parse_inventory_file,
)


def _load_pair(char_path: Path, inv_path: Path) -> tuple[dict, dict]:
    cd = parse_character_data(str(char_path), None)
    ids = {n: d["id"] for n, d in cd.items() if d.get("id")}
    inv = parse_inventory_file(str(inv_path), ids)
    return cd, inv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", required=True, help="Snapshot date YYYY-MM-DD")
    parser.add_argument(
        "--dump-char",
        type=Path,
        default=MAGELO_ROOT / "character" / "TAKP_character_previous.txt",
    )
    parser.add_argument(
        "--dump-inv",
        type=Path,
        default=MAGELO_ROOT / "inventory" / "TAKP_character_inventory_previous.txt",
    )
    parser.add_argument(
        "--prev-date",
        help="Optional prior dump date for day-over-day ground truth (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--prev-char",
        type=Path,
        default=MAGELO_ROOT / "character" / "TAKP_character_previous.txt",
    )
    parser.add_argument(
        "--prev-inv",
        type=Path,
        default=MAGELO_ROOT / "inventory" / "TAKP_character_inventory_previous.txt",
    )
    parser.add_argument(
        "--curr-char",
        type=Path,
        default=MAGELO_ROOT / "character" / "TAKP_character.txt",
    )
    parser.add_argument(
        "--curr-inv",
        type=Path,
        default=MAGELO_ROOT / "inventory" / "TAKP_character_inventory.txt",
    )
    parser.add_argument("--curr-date", help="Current export date for ground-truth diff")
    args = parser.parse_args()

    base_dir = MAGELO_ROOT / "delta_snapshots"
    with gzip.open(base_dir / "baseline_master.json.gz", "rt", encoding="utf-8") as f:
        baseline = json.load(f)
    baseline_date = baseline.get("baseline_date") or ""

    if not args.dump_char.is_file() or not args.dump_inv.is_file():
        print("::error::Dump snapshot files missing")
        return 1

    dump_char, dump_inv = _load_pair(args.dump_char, args.dump_inv)
    events = load_gear_events(str(base_dir), start_date=baseline_date, end_date=args.date)
    recon_map = build_possession_map(baseline.get("inventories") or {}, events, args.date)
    dump_map = possession_from_inv_snapshot(dump_inv)
    inv_diff = diff_absolute_possession_maps(recon_map, dump_map)
    recon_char = reconstruct_char_data_at_date(baseline, str(base_dir), args.date)
    char_diff = compare_character_data(dump_char, recon_char, None)

    print(f"Reconstruction parity @ {args.date} (events loaded: {len(events)})")
    print(f"  recon vs dump inv rows:  {_count_inv_event_rows(inv_diff)}")
    print(f"  recon vs dump char keys: {len(char_diff)}")
    print("  => NOT suitable as Magelo export substitute for daily CI")

    if args.curr_date and args.prev_char.is_file() and args.curr_inv.is_file():
        pc, pi = _load_pair(args.prev_char, args.prev_inv)
        cc, ci = _load_pair(args.curr_char, args.curr_inv)
        inv_d = compare_inventories(ci, pi, None)
        char_d = compare_character_data(cc, pc, None)
        print(f"\nGround truth dump diff {args.prev_date or 'prev'} -> {args.curr_date}")
        print(f"  inv rows:         {_count_inv_event_rows(inv_d)}")
        print(f"  char meaningful:  {_count_meaningful_char_deltas(char_d)}")
        print(f"  estimated events: {_estimate_delta_event_total(char_d, inv_d, args.curr_date)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
