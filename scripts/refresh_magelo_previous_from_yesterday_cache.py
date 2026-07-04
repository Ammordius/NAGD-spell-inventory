#!/usr/bin/env python3
"""After restoring magelo-dump-YYYY-MM-DD into workspace, copy dumps to _previous files.

Verifies cache content via embedded stamp fingerprint, standalone JSON, or legacy
stamp/index checks before copying. Does not rewrite stamps to hide stale cache content.

When ``YESTERDAY_CHAR`` / ``YESTERDAY_INV`` / ``YESTERDAY_STAMP`` env vars point at
``.delta_yesterday_*`` backups from the early cache restore, avoids a second Actions
cache restore of the same key in one job (which can miss even when the cache exists).
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from magelo_dump_fingerprint import (  # noqa: E402
    DEFAULT_CHAR,
    DEFAULT_INV,
    DEFAULT_STAMP,
    FINGERPRINT_FILENAME,
    load_fingerprint,
    parse_stamp,
    read_stamp_line,
    verify_dump_against_index,
    verify_fingerprint,
    verify_legacy_stamp,
)


def format_takp_stamp(dt: datetime) -> str:
    """Match TAKP export page: 'Sat Feb 7 16:30:25 UTC 2026'."""
    return dt.strftime("%a %b ") + str(dt.day) + dt.strftime(" 16:30:25 UTC %Y")


def _source_paths() -> tuple[Path, Path, Path]:
    char = Path(os.environ.get("YESTERDAY_CHAR") or DEFAULT_CHAR)
    inv = Path(os.environ.get("YESTERDAY_INV") or DEFAULT_INV)
    stamp = Path(os.environ.get("YESTERDAY_STAMP") or DEFAULT_STAMP)
    return char, inv, stamp


def verify_yesterday_cache(
    expected: str,
    char_src: Path,
    inv_src: Path,
    stamp_src: Path,
) -> list[str]:
    fp = load_fingerprint(Path(FINGERPRINT_FILENAME), stamp_path=stamp_src)
    if fp:
        return verify_fingerprint(fp, char_src, inv_src, expected)
    errors = verify_legacy_stamp(stamp_src, expected)
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

    char_src, inv_src, stamp_src = _source_paths()
    if not char_src.is_file() or not inv_src.is_file():
        print(
            "::error::Yesterday dump files missing "
            f"(expected magelo-dump-{expected}; char={char_src}, inv={inv_src})"
        )
        return 1

    errors = verify_yesterday_cache(expected, char_src, inv_src, stamp_src)
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
    print(f"OK Copied yesterday cache into _previous (key magelo-dump-{expected})")

    stamp_from_cache = read_stamp_line(stamp_src)
    parsed = parse_stamp(stamp_from_cache)
    if parsed and parsed.date() == expected_dt.date():
        final_stamp = stamp_from_cache
        print(f"OK Previous stamp matches cache key date: {final_stamp}")
    else:
        final_stamp = format_takp_stamp(expected_dt)
        print(
            f"::warning::Cache stamp {stamp_from_cache!r} missing or mismatched; "
            f"using verified cache key date stamp {final_stamp!r} for .magelo_previous_dump_date.txt"
        )

    Path(".magelo_previous_dump_date.txt").write_text(final_stamp + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
