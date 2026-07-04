#!/usr/bin/env python3
"""Validate a day-over-day Magelo dump diff using local previous files vs current export.

Use this to decide whether a calendar day's gear-event write is trustworthy without
relying on GitHub Actions dump caches. Typical flow for a missed/stale CI day:

  1. Ensure ``*_previous`` files are the verified prior-day export (not cache-derived).
  2. Fetch or refresh current-day ``TAKP_character*.txt`` from TAKP.
  3. Run this script; if PASS, run ``generate_spell_page.py`` with matching stamps.

Exit 0 = diff looks reasonable for gear-event append; exit 1 = abandon day (see
``--print-abandon-instructions``).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))

from gear_event_storage import (  # noqa: E402
    DEFAULT_EVENT_INFLATION_MEDIAN_FACTOR,
    GearEventInflationError,
    guard_gear_event_write,
    manifest_median_day_total,
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

TAKP_CHAR_URL = "https://www.takproject.net/magelo/export/TAKP_character.txt"
TAKP_INV_URL = "https://www.takproject.net/magelo/export/TAKP_character_inventory.txt"

# Rough band for a single healthy day (guard uses median * factor + excess).
REASONABLE_INV_ROWS_MAX = 5000
REASONABLE_CHAR_MAX = 500
REASONABLE_EVENTS_MAX = 6000


def _load_dump_pair(char_path: Path, inv_path: Path) -> tuple[dict, dict]:
    char_data = parse_character_data(str(char_path), None)
    char_ids = {name: row["id"] for name, row in char_data.items() if row.get("id")}
    inv_data = parse_inventory_file(str(inv_path), char_ids)
    return char_data, inv_data


def _fetch_export(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())


def _baseline_date(base_dir: Path) -> str:
    path = base_dir / "baseline_master.json.gz"
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f).get("baseline_date") or ""


def evaluate_diff(
    prev_char: Path,
    prev_inv: Path,
    curr_char: Path,
    curr_inv: Path,
    curr_date: str,
    base_dir: Path,
) -> dict:
    pc, pi = _load_dump_pair(prev_char, prev_inv)
    cc, ci = _load_dump_pair(curr_char, curr_inv)
    char_d = compare_character_data(cc, pc, None)
    inv_d = compare_inventories(ci, pi, None)
    inv_rows = _count_inv_event_rows(inv_d)
    char_n = _count_meaningful_char_deltas(char_d)
    est_events = _estimate_delta_event_total(char_d, inv_d, curr_date)
    baseline_date = _baseline_date(base_dir)
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
        "inv_rows": inv_rows,
        "char_meaningful": char_n,
        "estimated_events": est_events,
        "guard_ok": guard_ok,
        "guard_error": guard_err,
        "manifest_median": med,
        "reasonable": reasonable,
        "baseline_date": baseline_date,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prev-date", required=True, help="Previous export YYYY-MM-DD")
    parser.add_argument("--curr-date", required=True, help="Current export YYYY-MM-DD")
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
    parser.add_argument(
        "--fetch-current",
        action="store_true",
        help="Download current char/inv from TAKP before diff",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=MAGELO_ROOT / "delta_snapshots",
    )
    parser.add_argument(
        "--run-generate",
        action="store_true",
        help="Run generate_spell_page.py after PASS (requires MAGELO_UPDATE_DATE env or stamp file)",
    )
    parser.add_argument(
        "--print-abandon-instructions",
        action="store_true",
        help="On FAIL, print steps to abandon curr-date and use 2-day delta on next run",
    )
    args = parser.parse_args()

    for label, path in (
        ("prev-char", args.prev_char),
        ("prev-inv", args.prev_inv),
    ):
        if not path.is_file():
            print(f"::error::{label} missing: {path}")
            return 1

    if args.fetch_current:
        print(f"Fetching current export for {args.curr_date}...")
        _fetch_export(TAKP_CHAR_URL, args.curr_char)
        _fetch_export(TAKP_INV_URL, args.curr_inv)

    for label, path in (
        ("curr-char", args.curr_char),
        ("curr-inv", args.curr_inv),
    ):
        if not path.is_file():
            print(f"::error::{label} missing: {path}")
            return 1

    result = evaluate_diff(
        args.prev_char,
        args.prev_inv,
        args.curr_char,
        args.curr_inv,
        args.curr_date,
        args.base_dir,
    )

    print(f"Day-over-day diff {args.prev_date} -> {args.curr_date}")
    print(f"  inv rows:           {result['inv_rows']}")
    print(f"  char meaningful:    {result['char_meaningful']}")
    print(f"  estimated events:   {result['estimated_events']}")
    print(f"  manifest median:    {result['manifest_median']}")
    print(f"  guard_gear_event:   {'PASS' if result['guard_ok'] else 'FAIL'}")
    if result["guard_error"]:
        print(f"  guard detail:       {result['guard_error']}")

    if result["reasonable"]:
        print(f"OK Diff looks reasonable for gear-event append on {args.curr_date}")
        if args.run_generate:
            env = os.environ.copy()
            stamp_path = MAGELO_ROOT / ".magelo_update_date"
            if not env.get("MAGELO_UPDATE_DATE") and stamp_path.is_file():
                env["MAGELO_UPDATE_DATE"] = stamp_path.read_text(encoding="utf-8").splitlines()[0]
            rc = subprocess.call(
                [sys.executable, str(MAGELO_ROOT / "generate_spell_page.py")],
                cwd=str(MAGELO_ROOT),
                env=env,
            )
            if rc != 0:
                return rc
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
        return 0

    print(f"::error::Diff for {args.curr_date} is NOT reasonable — do not append gear events")
    if args.print_abandon_instructions:
        print(
            f"\nAbandon {args.curr_date}:\n"
            f"  1. Add {args.curr_date} to delta_snapshots/ABANDONED_DATES.txt\n"
            f"  2. Remove {args.curr_date} from gear_events/manifest.json and trim shards if present\n"
            f"  3. On the next export day, ensure _previous is {args.prev_date} verified files;\n"
            f"     the following day's diff will span 2 calendar days (acceptable one-time catch-up).\n"
            f"  4. Do not commit inflated gear_events for {args.curr_date}.\n"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
