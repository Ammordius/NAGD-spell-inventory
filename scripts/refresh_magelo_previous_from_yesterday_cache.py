#!/usr/bin/env python3
"""After restoring magelo-dump-YYYY-MM-DD into workspace, copy dumps to _previous files.

The Actions cache key is the calendar day of the export; ``.magelo_update_date`` inside
an old cache blob can still carry an earlier stamp (e.g. Feb 7 under key 2026-05-14).
We always align ``.magelo_previous_dump_date.txt`` to EXPECTED_YESTERDAY_DATE when they differ.
"""
import os
import re
import shutil
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


def format_takp_stamp(dt: datetime) -> str:
    """Match TAKP export page: 'Sat Feb 7 16:30:25 UTC 2026'."""
    return dt.strftime("%a %b ") + str(dt.day) + dt.strftime(" 16:30:25 UTC %Y")


def main() -> int:
    expected = (os.environ.get("EXPECTED_YESTERDAY_DATE") or "").strip()
    if not expected:
        print("::error::EXPECTED_YESTERDAY_DATE is not set")
        return 1

    try:
        expected_dt = datetime.strptime(expected, "%Y-%m-%d")
    except ValueError:
        print(f"::error::Invalid EXPECTED_YESTERDAY_DATE: {expected!r}")
        return 1

    char_src = Path("character/TAKP_character.txt")
    inv_src = Path("inventory/TAKP_character_inventory.txt")
    if not char_src.is_file() or not inv_src.is_file():
        print(
            "::error::Yesterday cache restore did not provide character/inventory files "
            f"(expected magelo-dump-{expected})"
        )
        return 1

    char_prev = Path("character/TAKP_character_previous.txt")
    inv_prev = Path("inventory/TAKP_character_inventory_previous.txt")
    shutil.copy2(char_src, char_prev)
    shutil.copy2(inv_src, inv_prev)
    print(f"✓ Copied yesterday cache into _previous (key magelo-dump-{expected})")

    stamp_path = Path(".magelo_update_date")
    stamp_from_cache = stamp_path.read_text(encoding="utf-8").strip() if stamp_path.is_file() else ""
    parsed = parse_stamp(stamp_from_cache)
    if parsed and parsed.date() == expected_dt.date():
        final_stamp = stamp_from_cache
        print(f"✓ Previous stamp matches cache key date: {final_stamp}")
    else:
        final_stamp = format_takp_stamp(expected_dt)
        print(
            f"::warning::Cache .magelo_update_date {stamp_from_cache!r} does not match "
            f"magelo-dump-{expected}; writing {final_stamp!r} to .magelo_previous_dump_date.txt"
        )

    Path(".magelo_previous_dump_date.txt").write_text(final_stamp + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
