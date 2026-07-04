#!/usr/bin/env python3
"""CI: verify yesterday Magelo cache backup, copy to _previous, or skip when stale.

When yesterday's Actions cache content is wrong-era but gear_events/manifest.json
already lists today's export date, exit 0 with ``skip_dump_delta`` output so the
job continues without inflated dump diffs.

Set ``GITHUB_OUTPUT`` when that file path is present in the environment.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parents[1]
if str(MAGELO_ROOT) not in sys.path:
    sys.path.insert(0, str(MAGELO_ROOT))


def _write_output(name: str, value: str) -> None:
    out_path = os.environ.get("GITHUB_OUTPUT")
    if out_path:
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")
    print(f"OUTPUT {name}={value}")


def _clear_previous() -> None:
    for rel in (
        "character/TAKP_character_previous.txt",
        "inventory/TAKP_character_inventory_previous.txt",
        ".magelo_previous_dump_date.txt",
    ):
        path = MAGELO_ROOT / rel
        if path.is_file():
            path.unlink()


def main() -> int:
    export_date = (os.environ.get("EXPORT_DATE") or "").strip()
    expected_yesterday = (os.environ.get("EXPECTED_YESTERDAY_DATE") or "").strip()
    if not expected_yesterday:
        print("::error::EXPECTED_YESTERDAY_DATE is not set")
        return 1

    refresh = subprocess.run(
        [sys.executable, str(MAGELO_ROOT / "scripts" / "refresh_magelo_previous_from_yesterday_cache.py")],
        cwd=str(MAGELO_ROOT),
        env=os.environ.copy(),
    )
    if refresh.returncode == 0:
        _write_output("skip_dump_delta", "false")
        print("OK Yesterday cache verified and copied to _previous")
        return 0

    print(
        f"::warning::magelo-dump-{expected_yesterday} failed verify "
        "(wrong-era blob under cache key is expected until cache self-heals)."
    )
    _clear_previous()

    if not export_date or export_date == "unknown":
        print("::error::Yesterday cache stale and EXPORT_DATE unknown — cannot fall back.")
        return 1

    check = subprocess.run(
        [
            sys.executable,
            str(MAGELO_ROOT / "scripts" / "check_gear_manifest_date.py"),
            "--date",
            export_date,
        ],
        cwd=str(MAGELO_ROOT),
    )
    if check.returncode != 0:
        print(
            f"::error::Yesterday cache stale and gear_events manifest lacks {export_date}. "
            "Run scripts/validate_day_over_day_dump_diff.py locally and commit shards."
        )
        return 1

    print(
        f"::warning::Skipping dump diff for {export_date}; gear_events manifest already has this date."
    )
    _write_output("skip_dump_delta", "true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
