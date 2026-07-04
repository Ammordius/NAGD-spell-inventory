#!/usr/bin/env python3
"""Return 0 when gear_events manifest lists the given calendar date."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument(
        "--base-dir",
        default="delta_snapshots",
        help="Root containing gear_events/manifest.json",
    )
    args = p.parse_args()
    manifest = Path(args.base_dir) / "gear_events" / "manifest.json"
    if not manifest.is_file():
        return 1
    try:
        with manifest.open(encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return 1
    days = (data or {}).get("days") or {}
    return 0 if args.date in days else 1


if __name__ == "__main__":
    sys.exit(main())
