#!/usr/bin/env python3
"""Write ``baseline_master_<baseline_date>.json.gz`` from Magelo character/inventory exports.

Used in CI after restoring a historical ``magelo-dump-<date>`` cache into ``character/`` /
``inventory/``. Writes only the dated archive (never overwrites an existing archive).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Repo root imports
sys.path.insert(0, os.getcwd())

from delta_storage import save_master_baseline  # noqa: E402
from generate_spell_page import parse_character_data, parse_inventory_file  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-date", required=True, help="YYYY-MM-DD stored in JSON baseline_date")
    ap.add_argument("--character", type=Path, default=Path("character/TAKP_character.txt"))
    ap.add_argument("--inventory", type=Path, default=Path("inventory/TAKP_character_inventory.txt"))
    ap.add_argument("--out-dir", type=Path, default=Path("delta_snapshots"))
    args = ap.parse_args()

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"baseline_master_{args.baseline_date}.json.gz"
    if dest.is_file():
        print(f"OK: already exists: {dest.name}")
        return 0

    char_path = args.character.resolve()
    inv_path = args.inventory.resolve()
    if not char_path.is_file() or not inv_path.is_file():
        print(f"ERROR: missing character or inventory file: {char_path} / {inv_path}", file=sys.stderr)
        return 1

    char_data = parse_character_data(str(char_path), None)
    char_ids: dict[str, str] = {}
    with char_path.open("r", encoding="utf-8") as f:
        next(f, None)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 9:
                char_ids[parts[0]] = parts[8]

    inv_data = parse_inventory_file(str(inv_path), char_ids)

    tmp = Path(tempfile.mkdtemp(prefix="baseline_mat_"))
    try:
        save_master_baseline(char_data, inv_data, args.baseline_date, str(tmp))
        produced = tmp / "baseline_master.json.gz"
        if not produced.is_file():
            print("ERROR: save_master_baseline did not produce baseline_master.json.gz", file=sys.stderr)
            return 1
        shutil.move(str(produced), str(dest))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"OK: wrote {dest.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
