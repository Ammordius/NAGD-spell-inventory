#!/usr/bin/env python3
"""CI helper: ensure previous vs current Magelo export stamps are within max_span_days."""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from magelo_dump_fingerprint import (  # noqa: E402
    load_fingerprint,
    verify_fingerprint,
)


def parse_stamp(s: str):
    s = re.sub(r"\s+", " ", (s or "").strip())
    if not s or s.lower() == "unknown":
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S UTC %Y")
    except ValueError:
        return None


def _count_lines(path: Path) -> int:
    try:
        with path.open(encoding="utf-8") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def check_dump_content_plausible(max_line_delta_ratio: float = 0.10) -> int:
    """Fail when character dump line counts diverge sharply (stale cache content)."""
    prev_char = Path("character/TAKP_character_previous.txt")
    cur_char = Path("character/TAKP_character.txt")
    if not prev_char.is_file() or not cur_char.is_file():
        return 0
    prev_lines = _count_lines(prev_char)
    cur_lines = _count_lines(cur_char)
    if prev_lines < 100 or cur_lines < 100:
        return 0
    ratio = abs(cur_lines - prev_lines) / max(prev_lines, cur_lines)
    if ratio > max_line_delta_ratio:
        print(
            "::error::Previous vs current character dump line counts differ by "
            f"{ratio * 100:.1f}% (max {max_line_delta_ratio * 100:.0f}%). "
            f"Previous: {prev_lines} lines, current: {cur_lines} lines. "
            "Likely stale magelo-dump-* cache content despite aligned stamp."
        )
        return 1
    return 0


def check_inventory_line_counts(max_line_delta_ratio: float = 0.10) -> int:
    """Fail when inventory dump line counts diverge sharply."""
    prev_inv = Path("inventory/TAKP_character_inventory_previous.txt")
    cur_inv = Path("inventory/TAKP_character_inventory.txt")
    if not prev_inv.is_file() or not cur_inv.is_file():
        return 0
    prev_lines = _count_lines(prev_inv)
    cur_lines = _count_lines(cur_inv)
    if prev_lines < 100 or cur_lines < 100:
        return 0
    ratio = abs(cur_lines - prev_lines) / max(prev_lines, cur_lines)
    if ratio > max_line_delta_ratio:
        print(
            "::error::Previous vs current inventory dump line counts differ by "
            f"{ratio * 100:.1f}% (max {max_line_delta_ratio * 100:.0f}%). "
            f"Previous: {prev_lines} lines, current: {cur_lines} lines. "
            "Likely stale magelo-dump-* cache content."
        )
        return 1
    return 0


def check_previous_fingerprint() -> int:
    """Verify _previous files still match yesterday's cache fingerprint when present."""
    expected = (os.environ.get("EXPECTED_PREVIOUS_DATE") or "").strip()
    if not expected:
        return 0
    fp = load_fingerprint(Path("magelo_dump_fingerprint.json"))
    if not fp:
        return 0
    prev_char = Path("character/TAKP_character_previous.txt")
    prev_inv = Path("inventory/TAKP_character_inventory_previous.txt")
    if not prev_char.is_file() or not prev_inv.is_file():
        return 0
    errors = verify_fingerprint(fp, prev_char, prev_inv, expected)
    if errors:
        for err in errors:
            print(f"::error::{err}")
        print(
            "_previous files no longer match magelo_dump_fingerprint.json after cache refresh."
        )
        return 1
    return 0


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
    for check in (
        check_dump_content_plausible,
        check_inventory_line_counts,
        check_previous_fingerprint,
    ):
        rc = check()
        if rc != 0:
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main())
