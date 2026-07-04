#!/usr/bin/env python3
"""After restoring magelo-dump-YYYY-MM-DD into workspace, copy dumps to _previous files.

Verifies cache content via ``magelo_dump_fingerprint.json`` (or legacy stamp/index checks)
before copying. Does not rewrite stamps to hide stale cache content.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

# Allow import when run as scripts/refresh_magelo_previous_from_yesterday_cache.py
sys.path.insert(0, str(Path(__file__).resolve().parent))

from magelo_dump_fingerprint import (  # noqa: E402
    DEFAULT_CHAR,
    DEFAULT_INV,
    DEFAULT_STAMP,
    FINGERPRINT_FILENAME,
    load_fingerprint,
    parse_stamp,
    verify_dump_against_index,
    verify_fingerprint,
    verify_legacy_stamp,
)


def format_takp_stamp(dt: datetime) -> str:
    """Match TAKP export page: 'Sat Feb 7 16:30:25 UTC 2026'."""
    return dt.strftime("%a %b ") + str(dt.day) + dt.strftime(" 16:30:25 UTC %Y")


def verify_yesterday_cache(expected: str, char_src: Path, inv_src: Path) -> list[str]:
    fp = load_fingerprint(Path(FINGERPRINT_FILENAME))
    if fp:
        return verify_fingerprint(fp, char_src, inv_src, expected)
    errors = verify_legacy_stamp(DEFAULT_STAMP, expected)
    errors.extend(verify_dump_against_index(char_src, inv_src, expected))
    return errors


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

    char_src = DEFAULT_CHAR
    inv_src = DEFAULT_INV
    if not char_src.is_file() or not inv_src.is_file():
        print(
            "::error::Yesterday cache restore did not provide character/inventory files "
            f"(expected magelo-dump-{expected})"
        )
        return 1

    errors = verify_yesterday_cache(expected, char_src, inv_src)
    if errors:
        for err in errors:
            print(f"::error::{err}")
        print(
            f"Refusing to copy stale magelo-dump-{expected} into _previous. "
            "Re-seed Actions cache with verified export files."
        )
        return 1

    char_prev = Path("character/TAKP_character_previous.txt")
    inv_prev = Path("inventory/TAKP_character_inventory_previous.txt")
    shutil.copy2(char_src, char_prev)
    shutil.copy2(inv_src, inv_prev)
    print(f"✓ Copied yesterday cache into _previous (key magelo-dump-{expected})")

    stamp_from_cache = (
        DEFAULT_STAMP.read_text(encoding="utf-8").strip() if DEFAULT_STAMP.is_file() else ""
    )
    parsed = parse_stamp(stamp_from_cache)
    if parsed and parsed.date() == expected_dt.date():
        final_stamp = stamp_from_cache
        print(f"✓ Previous stamp matches cache key date: {final_stamp}")
    else:
        final_stamp = format_takp_stamp(expected_dt)
        print(
            f"::warning::Cache .magelo_update_date {stamp_from_cache!r} missing or mismatched; "
            f"using verified cache key date stamp {final_stamp!r} for .magelo_previous_dump_date.txt"
        )

    Path(".magelo_previous_dump_date.txt").write_text(final_stamp + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
