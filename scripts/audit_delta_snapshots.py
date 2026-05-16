#!/usr/bin/env python3
"""Audit delta_daily_*.json.gz under delta_snapshots/ for baseline-era mistakes.

Flags ``date < baseline_date`` in file metadata (incoherent wrong-era regen; same idea as
``verify_delta_baseline_archives`` warnings). Optionally print one character's ``char_deltas`` row
across a date range (e.g. **Tuned**) to spot bad ``current_aa_total`` after rotation week.

Examples::

    python scripts/audit_delta_snapshots.py --prefix delta_daily_2026-05 --fail-on-issue
    python scripts/audit_delta_snapshots.py --from-date 2026-05-12 --to-date 2026-05-14 --character Tuned

"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import sys
from pathlib import Path

# Empty/wrong-era regen cluster (~250 KB); healthy Feb-era dailies are typically ~800 KB+.
MIN_HEALTHY_BYTES = 400_000
ABANDONED_DATES_FILENAME = "ABANDONED_DATES.txt"


def _parse_daily_path(p: Path) -> str | None:
    m = re.match(r"delta_daily_(\d{4}-\d{2}-\d{2})\.json\.gz$", p.name)
    return m.group(1) if m else None


def audit_dump_before_baseline(path: Path) -> list[str]:
    issues: list[str] = []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        return [f"{path.name}: cannot read ({e})"]
    file_date = doc.get("date") or _parse_daily_path(path)
    bd = doc.get("baseline_date")
    if file_date and bd and str(bd) != "Unknown" and str(file_date) < str(bd):
        issues.append(
            f"{path.name}: dump date {file_date} < baseline_date {bd} (wrong-era regen; "
            f"use baseline_era_date matching the dump era; see handoff doc)"
        )
    dq = doc.get("data_quality") or {}
    if dq.get("dump_before_baseline") and not any("dump date" in x for x in issues):
        issues.append(f"{path.name}: data_quality.dump_before_baseline is true")
    return issues


def audit_degenerate_payload(path: Path, min_bytes: int) -> list[str]:
    """Flag tiny gzip files with empty cumulative deltas (bad regen)."""
    if path.stat().st_size >= min_bytes:
        return []
    try:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            doc = json.load(f)
    except OSError as e:
        return [f"{path.name}: cannot read ({e})"]
    inv = doc.get("inv_deltas") or {}
    char = doc.get("char_deltas") or {}
    if not inv and not char:
        return [
            f"{path.name}: {path.stat().st_size} bytes with empty inv_deltas and char_deltas "
            f"(expected >={min_bytes} bytes for a healthy daily; regen or delete)"
        ]
    return []


def load_exclude_dates(base_dir: Path, explicit: str) -> set[str]:
    out: set[str] = set()
    if explicit.strip():
        out.update(d.strip() for d in explicit.split(",") if d.strip())
    abandoned = base_dir / ABANDONED_DATES_FILENAME
    if abandoned.is_file():
        for line in abandoned.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(line)
    return out


def print_character_rows(paths: list[Path], character: str) -> None:
    for p in paths:
        try:
            with gzip.open(p, "rt", encoding="utf-8") as f:
                doc = json.load(f)
        except OSError as e:
            print(f"{p.name}: read error {e}")
            continue
        row = (doc.get("char_deltas") or {}).get(character)
        print(
            p.name,
            "date",
            doc.get("date"),
            "baseline",
            doc.get("baseline_date"),
            "row",
            row,
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-dir", type=Path, default=Path("delta_snapshots"))
    ap.add_argument(
        "--prefix",
        default="",
        help="Only files whose basename starts with this (e.g. delta_daily_2026-05)",
    )
    ap.add_argument("--from-date", default="", metavar="YYYY-MM-DD")
    ap.add_argument("--to-date", default="", metavar="YYYY-MM-DD")
    ap.add_argument(
        "--character",
        default="",
        metavar="NAME",
        help="Print this character's char_deltas row for each matched file (spot-check AA)",
    )
    ap.add_argument(
        "--fail-on-issue",
        action="store_true",
        help="Exit 1 if any dump date < baseline_date or degenerate payload",
    )
    ap.add_argument(
        "--exclude-dates",
        default="",
        help="Comma-separated YYYY-MM-DD to skip (also reads ABANDONED_DATES.txt in base-dir)",
    )
    ap.add_argument(
        "--min-bytes",
        type=int,
        default=MIN_HEALTHY_BYTES,
        help="Fail when gzip is smaller and inv_deltas/char_deltas are both empty",
    )
    args = ap.parse_args()
    base = args.base_dir.resolve()
    if not base.is_dir():
        print(f"ERROR: not a directory: {base}", file=sys.stderr)
        return 1

    paths = sorted(base.glob("delta_daily_*.json.gz"))
    if args.prefix:
        paths = [p for p in paths if p.name.startswith(args.prefix)]
    if args.from_date or args.to_date:
        lo = args.from_date or "0000-00-00"
        hi = args.to_date or "9999-99-99"
        filtered = []
        for p in paths:
            d = _parse_daily_path(p)
            if d and lo <= d <= hi:
                filtered.append(p)
        paths = filtered

    exclude = load_exclude_dates(base, args.exclude_dates)
    if exclude:
        paths = [p for p in paths if (_parse_daily_path(p) or "") not in exclude]

    all_issues: list[str] = []
    for p in paths:
        all_issues.extend(audit_dump_before_baseline(p))
        all_issues.extend(audit_degenerate_payload(p, args.min_bytes))

    for msg in all_issues:
        print(msg)

    if args.character:
        print(f"--- char_deltas[{args.character!r}] ---")
        print_character_rows(paths, args.character.strip())

    if not paths:
        print("(no delta_daily_*.json.gz matched)")
    elif not all_issues and not args.character:
        print(f"OK: audited {len(paths)} file(s), no dump-before-baseline issues")

    return 1 if (args.fail_on_issue and all_issues) else 0


if __name__ == "__main__":
    sys.exit(main())
