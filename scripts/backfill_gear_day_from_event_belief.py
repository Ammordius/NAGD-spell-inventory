#!/usr/bin/env python3
"""Backfill a calendar day's gear events from baseline + shard belief vs live export.

When verified Magelo ``*_previous`` dump files are unavailable, believed end-of-day
state for ``prev_date`` is:

  baseline_master + all committed gear/char events with ``d <= prev_date``

Day ``curr_date`` deltas come from ``day_deltas_from_event_reconstruction()`` (same
primitive as commit ``7f5dc00``). This is **not** used in daily CI (see
``docs/GEAR_EVENT_INFLATION_HANDOFF_2026-07-04.md``); operator backfill only.

Example::

  python scripts/backfill_gear_day_from_event_belief.py \\
    --prev-date 2026-07-05 --curr-date 2026-07-06 --fetch-current --run-generate
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from delta_storage import load_master_baseline  # noqa: E402
from gear_event_storage import (  # noqa: E402
    GearEventInflationError,
    append_day_events_from_deltas,
    day_deltas_from_event_reconstruction,
    filter_unique_reacquires_in_inv_deltas,
    guard_gear_event_write,
    manifest_median_day_total,
    possession_from_inv_snapshot,
    reconstruct_char_data_at_date,
)
from generate_spell_page import (  # noqa: E402
    _count_inv_event_rows,
    _count_meaningful_char_deltas,
    _estimate_delta_event_total,
    chars_corpse_loot_excluded,
    generate_delta_html,
    load_tracked_item_ids,
    load_unique_tracked_item_ids,
    parse_character_data,
    parse_inventory_file,
)

TAKP_CHAR_URL = "https://www.takproject.net/magelo/export/TAKP_character.txt"
TAKP_INV_URL = "https://www.takproject.net/magelo/export/TAKP_character_inventory.txt"

REASONABLE_INV_ROWS_MAX = 5000
REASONABLE_CHAR_MAX = 500
REASONABLE_EVENTS_MAX = 6000


def _fetch_export(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _load_current_pair(char_path: Path, inv_path: Path) -> tuple[dict, dict]:
    char_data = parse_character_data(str(char_path), None)
    char_ids = {name: row["id"] for name, row in char_data.items() if row.get("id")}
    inv_data = parse_inventory_file(str(inv_path), char_ids)
    return char_data, inv_data


def _manifest_day_counts(base_dir: Path, date_str: str) -> tuple[int, int]:
    manifest_path = base_dir / "gear_events" / "manifest.json"
    if not manifest_path.is_file():
        return 0, 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    meta = (manifest.get("days") or {}).get(date_str) or {}
    return int(meta.get("gear") or 0), int(meta.get("char") or 0)


def _shard_day_counts(base_dir: Path, date_str: str) -> tuple[int, int]:
    month = date_str[:7]
    gear_path = base_dir / "gear_events" / f"gear_{month}.json.gz"
    char_path = base_dir / "gear_events" / f"char_{month}.json.gz"
    gear_n = char_n = 0
    if gear_path.is_file():
        with gzip.open(gear_path, "rt", encoding="utf-8") as f:
            gear_n = sum(1 for ev in json.load(f) if ev.get("d") == date_str)
    if char_path.is_file():
        with gzip.open(char_path, "rt", encoding="utf-8") as f:
            char_n = sum(1 for ev in json.load(f) if ev.get("d") == date_str)
    return gear_n, char_n


def _cross_check_prev_date_shards(base_dir: Path, prev_date: str) -> list[str]:
    issues: list[str] = []
    gear_m, char_m = _manifest_day_counts(base_dir, prev_date)
    if gear_m == 0 and char_m == 0:
        issues.append(f"manifest has no entry for prev_date {prev_date}")
        return issues
    gear_s, char_s = _shard_day_counts(base_dir, prev_date)
    if gear_s != gear_m:
        issues.append(f"{prev_date} gear shard rows {gear_s} != manifest {gear_m}")
    if char_s != char_m:
        issues.append(f"{prev_date} char shard rows {char_s} != manifest {char_m}")
    return issues


def evaluate_belief_diff(
    prev_date: str,
    curr_date: str,
    curr_char: Path,
    curr_inv: Path,
    base_dir: Path,
) -> dict:
    baseline = load_master_baseline(str(base_dir))
    if not baseline:
        raise RuntimeError("baseline_master.json.gz not found")

    current_char, current_inv = _load_current_pair(curr_char, curr_inv)
    char_d, inv_d = day_deltas_from_event_reconstruction(
        current_char,
        current_inv,
        prev_date,
        curr_date,
        str(base_dir),
        baseline,
    )
    inv_rows = _count_inv_event_rows(inv_d)
    char_n = _count_meaningful_char_deltas(char_d)
    est_events = _estimate_delta_event_total(char_d, inv_d, curr_date)
    baseline_date = baseline.get("baseline_date") or ""
    guard_ok = True
    guard_err = ""
    try:
        guard_gear_event_write(char_d, inv_d, curr_date, str(base_dir), baseline_date)
    except GearEventInflationError as exc:
        guard_ok = False
        guard_err = str(exc)
    med = manifest_median_day_total(str(base_dir), curr_date)
    reasonable = (
        guard_ok
        and inv_rows <= REASONABLE_INV_ROWS_MAX
        and char_n <= REASONABLE_CHAR_MAX
        and est_events <= REASONABLE_EVENTS_MAX
    )
    return {
        "baseline": baseline,
        "baseline_date": baseline_date,
        "current_char": current_char,
        "current_inv": current_inv,
        "char_deltas": char_d,
        "inv_deltas": inv_d,
        "inv_rows": inv_rows,
        "char_meaningful": char_n,
        "estimated_events": est_events,
        "manifest_median": med,
        "guard_ok": guard_ok,
        "guard_error": guard_err,
        "reasonable": reasonable,
    }


def _format_takp_stamp(dt: datetime) -> str:
    return dt.strftime("%a %b ") + str(dt.day) + dt.strftime(" 16:30:27 UTC %Y")


def _write_delta_html(
    result: dict,
    prev_date: str,
    base_dir: Path,
    magelo_stamp: str,
    output_path: Path,
) -> None:
    baseline = result["baseline"]
    prev_char = reconstruct_char_data_at_date(baseline, str(base_dir), prev_date)
    char_d = result["char_deltas"]
    inv_d = result["inv_deltas"]
    current_inv = result["current_inv"]

    tracked_ids, _, _, _ = load_tracked_item_ids()
    unique_tracked = load_unique_tracked_item_ids(tracked_ids)
    prev_possession = possession_from_inv_snapshot({})
    filter_unique_reacquires_in_inv_deltas(inv_d, prev_possession, unique_tracked)
    corpse_loot = chars_corpse_loot_excluded(current_inv, {})

    prev_dt = datetime.strptime(prev_date, "%Y-%m-%d")
    prev_stamp = _format_takp_stamp(prev_dt)

    html = generate_delta_html(
        result["current_char"],
        prev_char,
        current_inv,
        {},
        magelo_stamp,
        serverwide=True,
        char_deltas=char_d,
        inv_deltas=inv_d,
        corpse_loot_chars=corpse_loot,
        previous_export_date=prev_stamp,
    )
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prev-date", required=True, help="Belief end date YYYY-MM-DD")
    parser.add_argument("--curr-date", required=True, help="Current export YYYY-MM-DD")
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
    parser.add_argument("--fetch-current", action="store_true", help="Download curr char/inv from TAKP")
    parser.add_argument("--base-dir", type=Path, default=MAGELO_ROOT / "delta_snapshots")
    parser.add_argument("--run-generate", action="store_true", help="Append shards, delta.html, audit")
    parser.add_argument(
        "--dump-pair-fallback",
        action="store_true",
        help="If belief diff fails guard, try validate_day_over_day_dump_diff dump-pair path",
    )
    parser.add_argument(
        "--magelo-update-date",
        help="TAKP stamp for curr-date (default: derived from curr-date)",
    )
    args = parser.parse_args()

    shard_issues = _cross_check_prev_date_shards(args.base_dir, args.prev_date)
    if shard_issues:
        for issue in shard_issues:
            print(f"::error::{issue}")
        return 1
    gear_m, char_m = _manifest_day_counts(args.base_dir, args.prev_date)
    print(f"OK {args.prev_date} shard/manifest cross-check: gear={gear_m} char={char_m}")

    if args.fetch_current:
        print(f"Fetching current export for {args.curr_date}...")
        _fetch_export(TAKP_CHAR_URL, args.curr_char)
        _fetch_export(TAKP_INV_URL, args.curr_inv)

    for label, path in (("curr-char", args.curr_char), ("curr-inv", args.curr_inv)):
        if not path.is_file():
            print(f"::error::{label} missing: {path}")
            return 1

    result = evaluate_belief_diff(
        args.prev_date,
        args.curr_date,
        args.curr_char,
        args.curr_inv,
        args.base_dir,
    )

    print(f"Event-belief diff {args.prev_date} -> {args.curr_date}")
    print(f"  inv rows:           {result['inv_rows']}")
    print(f"  char meaningful:    {result['char_meaningful']}")
    print(f"  estimated events:   {result['estimated_events']}")
    print(f"  manifest median:    {result['manifest_median']}")
    print(f"  guard_gear_event:   {'PASS' if result['guard_ok'] else 'FAIL'}")
    if result["guard_error"]:
        print(f"  guard detail:       {result['guard_error']}")

    if not result["reasonable"]:
        print(f"::warning::Belief diff for {args.curr_date} is NOT reasonable")
        if args.dump_pair_fallback and args.run_generate:
            print("Trying dump-pair fallback via validate_day_over_day_dump_diff.py...")
            cmd = [
                sys.executable,
                str(MAGELO_ROOT / "scripts" / "validate_day_over_day_dump_diff.py"),
                "--prev-date",
                args.prev_date,
                "--curr-date",
                args.curr_date,
                "--prev-char",
                str(args.curr_char.parent / "TAKP_character_previous.txt"),
                "--prev-inv",
                str(args.curr_inv.parent / "TAKP_character_inventory_previous.txt"),
                "--curr-char",
                str(args.curr_char),
                "--curr-inv",
                str(args.curr_inv),
                "--run-generate",
            ]
            if args.fetch_current:
                cmd.append("--fetch-current")
            return subprocess.call(cmd, cwd=str(MAGELO_ROOT))
        print(f"::error::Belief diff for {args.curr_date} is NOT reasonable — do not append")
        return 1

    print(f"OK Belief diff looks reasonable for gear-event append on {args.curr_date}")

    if not args.run_generate:
        return 0

    tracked_ids, _, _, _ = load_tracked_item_ids()
    unique_tracked = load_unique_tracked_item_ids(tracked_ids)
    gear_n, char_n = append_day_events_from_deltas(
        result["char_deltas"],
        result["inv_deltas"],
        args.curr_date,
        str(args.base_dir),
        baseline_date=result["baseline_date"],
        unique_tracked_ids=unique_tracked,
    )
    print(f"Saved gear_events: {gear_n} inventory rows, {char_n} stat rows")

    if gear_n == 0 and char_n == 0:
        print(f"::warning::No events written for {args.curr_date}")

    stamp = args.magelo_update_date
    if not stamp:
        curr_dt = datetime.strptime(args.curr_date, "%Y-%m-%d")
        stamp = _format_takp_stamp(curr_dt)

    delta_path = MAGELO_ROOT / "delta.html"
    _write_delta_html(result, args.prev_date, args.base_dir, stamp, delta_path)
    print(f"Wrote {delta_path}")

    audit = subprocess.call(
        [
            sys.executable,
            str(MAGELO_ROOT / "scripts" / "audit_gear_events.py"),
            "--base-dir",
            str(args.base_dir),
            "--min-events-after",
            "2026-06-27",
            "--fail-on-issue",
        ],
        cwd=str(MAGELO_ROOT),
    )
    return audit


if __name__ == "__main__":
    raise SystemExit(main())
