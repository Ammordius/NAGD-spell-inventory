#!/usr/bin/env python3
"""CI helper: ensure previous vs current Magelo export stamps are within max_span_days."""
import os
import re
import sys
from datetime import datetime
from pathlib import Path


def parse_stamp(s: str):
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s or s.lower() == "unknown":
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S UTC %Y")
    except ValueError:
        return None


def main() -> int:
    prev_path = Path(".magelo_previous_dump_date.txt")
    cur_path = Path(".magelo_update_date")
    if not prev_path.is_file() or not cur_path.is_file():
        print("No previous/current stamp files; skipping span check.")
        return 0

    prev_raw = prev_path.read_text(encoding="utf-8")
    cur_raw = cur_path.read_text(encoding="utf-8")
    pt = parse_stamp(prev_raw)
    ct = parse_stamp(cur_raw)
    if not pt or not ct:
        print(
            "::warning::Could not parse .magelo_previous_dump_date.txt or "
            ".magelo_update_date; skipping span check."
        )
        return 0

    expected_prev = (os.environ.get("EXPECTED_PREVIOUS_DATE") or "").strip()
    if expected_prev:
        try:
            exp_date = datetime.strptime(expected_prev, "%Y-%m-%d").date()
        except ValueError:
            print(f"::warning::Invalid EXPECTED_PREVIOUS_DATE: {expected_prev!r}")
            exp_date = None
        if exp_date is not None and pt.date() != exp_date:
            print(
                "::error::Previous stamp calendar date %s does not match expected "
                "magelo-dump-%s (previous stamp: %r). Re-run refresh_magelo_previous step."
                % (pt.date(), expected_prev, prev_raw.strip())
            )
            return 1

    days = abs((ct.date() - pt.date()).days)
    if days > 2:
        print(
            "::error::Previous Magelo export stamp vs current spans %d calendar days (max 2). "
            "Refusing to generate inflated delta.html. Previous stamp: %r. Current: %r. "
            "Restore magelo-dump-* Actions cache for the prior calendar day or re-run after "
            "yesterday's job populated cache."
            % (days, prev_raw, cur_raw)
        )
        return 1

    print("✓ Magelo export date span OK: %d calendar day(s) between previous and current." % days)
    return 0


if __name__ == "__main__":
    sys.exit(main())
