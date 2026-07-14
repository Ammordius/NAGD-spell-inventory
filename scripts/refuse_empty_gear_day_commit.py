#!/usr/bin/env python3
"""Fail if working-tree gear_events would commit an N→0 wipe for a calendar day.

Used by CI before `git commit` of gear event shards so same-day push re-runs
cannot clear a previously healthy export day.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _day_total(manifest: dict, date_str: str) -> int:
    meta = (manifest.get("days") or {}).get(date_str) or {}
    return int(meta.get("gear") or 0) + int(meta.get("char") or 0)


def head_manifest_total(date_str: str, manifest_rel: str) -> int | None:
    try:
        raw = subprocess.check_output(
            ["git", "show", f"HEAD:{manifest_rel}"],
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    try:
        return _day_total(json.loads(raw.decode("utf-8")), date_str)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def check(date_str: str, manifest_path: Path, *, min_existing: int = 50) -> int:
    if not date_str or date_str == "unknown":
        print("refuse_empty_gear_day_commit: no date; skip")
        return 0
    if not manifest_path.is_file():
        print(f"refuse_empty_gear_day_commit: missing {manifest_path}; skip")
        return 0
    new = json.loads(manifest_path.read_text(encoding="utf-8"))
    new_total = _day_total(new, date_str)
    rel = manifest_path.as_posix()
    # Prefer path relative to repo if under cwd.
    try:
        rel = str(manifest_path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except ValueError:
        pass
    old_total = head_manifest_total(date_str, rel)
    print(
        f"gear_events commit guard for {date_str}: HEAD={old_total} working={new_total}"
    )
    if old_total is not None and old_total >= min_existing and new_total == 0:
        print(
            f"::error::Refusing gear_events commit: {date_str} would drop from "
            f"{old_total} events to 0 (empty rewrite wipe)."
        )
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", required=True, help="Export date YYYY-MM-DD")
    ap.add_argument(
        "--manifest",
        type=Path,
        default=Path("delta_snapshots/gear_events/manifest.json"),
    )
    ap.add_argument("--min-existing", type=int, default=50)
    args = ap.parse_args()
    return check(args.date, args.manifest, min_existing=args.min_existing)


if __name__ == "__main__":
    raise SystemExit(main())
