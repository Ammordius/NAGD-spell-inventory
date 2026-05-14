#!/usr/bin/env python3
"""Create baseline_master_<embedded_date>.json.gz from baseline_master.json.gz when missing.

``load_baseline_for_date`` and ``verify_delta_baseline_archives`` need a dated archive for each
``baseline_date`` referenced by modern dailies. ``generate_spell_page.py`` only refreshes
``baseline_master.json.gz``; this script copies it to ``baseline_master_<baseline_date>.json.gz``
when that path does not exist (never overwrites an existing archive).
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from pathlib import Path


def _embedded_baseline_date(master_gz: Path) -> str | None:
    if not master_gz.is_file():
        return None
    with gzip.open(master_gz, "rt", encoding="utf-8") as f:
        data = json.load(f)
    bd = data.get("baseline_date")
    if bd in (None, "", "Unknown"):
        return None
    return str(bd)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-dir",
        type=Path,
        default=Path("delta_snapshots"),
        help="Directory containing baseline_master.json.gz",
    )
    args = ap.parse_args()
    base_dir = args.base_dir.resolve()
    if not base_dir.is_dir():
        print(f"ERROR: not a directory: {base_dir}", file=sys.stderr)
        return 1

    master = base_dir / "baseline_master.json.gz"
    bd = _embedded_baseline_date(master)
    if not bd:
        print(f"No embedded baseline_date in {master.name}; skip sync.")
        return 0

    archive = base_dir / f"baseline_master_{bd}.json.gz"
    if archive.is_file():
        print(f"OK: archive already exists: {archive.name}")
        return 0

    shutil.copy2(master, archive)
    print(f"OK: created {archive.name} from {master.name} (baseline_date={bd})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
