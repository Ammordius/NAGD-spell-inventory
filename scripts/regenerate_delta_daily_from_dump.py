#!/usr/bin/env python3
"""Regenerate one delta_daily_YYYY-MM-DD.json.gz from Magelo dumps.

Local equivalent of the matrix step in .github/workflows/regenerate-delta-days.yml.

Requires character/TAKP_character.txt and inventory/TAKP_character_inventory.txt for that day.

May 2026 rotation: use ``--baseline-era`` matching the dump's coordinate system — **not** always
2026-05-12. For dumps **before** 2026-05-12 use the pre-rotation archive (typically ``2026-02-09``);
for **2026-05-12** onward use ``2026-05-12``. Using the May-12 snapshot for a May-9 dump sets
``date < baseline_date`` (incoherent; see ``data_quality`` in written JSON).

Examples::

    python scripts/regenerate_delta_daily_from_dump.py 2026-05-09 --baseline-era 2026-02-09 --force
    python scripts/regenerate_delta_daily_from_dump.py 2026-05-12 --baseline-era 2026-05-12 --force

With --baseline-era, copies delta_snapshots/baseline_master_<era>.json.gz over
delta_snapshots/baseline_master.json.gz first (same as the workflow).
"""

from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("date", help="YYYY-MM-DD (dump date = delta filename)")
    ap.add_argument(
        "--baseline-era",
        default="",
        help="If set, copy baseline_master_<era>.json.gz over baseline_master.json.gz first",
    )
    ap.add_argument(
        "--char",
        type=Path,
        default=Path("character/TAKP_character.txt"),
        help="Character export path",
    )
    ap.add_argument(
        "--inv",
        type=Path,
        default=Path("inventory/TAKP_character_inventory.txt"),
        help="Inventory export path",
    )
    ap.add_argument(
        "--base-dir",
        type=Path,
        default=Path("delta_snapshots"),
        help="Delta and baseline directory",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Remove existing delta_daily_<date>.json.gz before writing",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(root))

    from generate_spell_page import parse_character_data, parse_inventory_file
    from delta_storage import load_master_baseline, save_daily_delta_from_baseline

    base_dir = (root / args.base_dir).resolve() if not args.base_dir.is_absolute() else args.base_dir
    base_dir.mkdir(parents=True, exist_ok=True)

    era = (args.baseline_era or "").strip()
    if era:
        arch = base_dir / f"baseline_master_{era}.json.gz"
        if not arch.is_file():
            print(f"ERROR: missing archive {arch}", file=sys.stderr)
            return 1
        shutil.copy2(arch, base_dir / "baseline_master.json.gz")
        print(f"OK: copied {arch.name} -> baseline_master.json.gz")

    if not load_master_baseline(str(base_dir)):
        print("ERROR: delta_snapshots/baseline_master.json.gz missing after --baseline-era", file=sys.stderr)
        return 1

    char_path = (root / args.char).resolve() if not args.char.is_absolute() else args.char
    inv_path = (root / args.inv).resolve() if not args.inv.is_absolute() else args.inv
    if not char_path.is_file() or not inv_path.is_file():
        print(f"ERROR: need character and inventory files:\n  {char_path}\n  {inv_path}", file=sys.stderr)
        return 1

    out_gz = base_dir / f"delta_daily_{args.date}.json.gz"
    out_json = base_dir / f"delta_daily_{args.date}.json"
    if args.force:
        out_gz.unlink(missing_ok=True)
        out_json.unlink(missing_ok=True)

    char_data = parse_character_data(str(char_path), None)
    char_ids: dict[str, str] = {}
    with open(char_path, "r", encoding="utf-8") as f:
        next(f)
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) >= 9:
                char_ids[parts[0]] = parts[8]
    inv_data = parse_inventory_file(str(inv_path), char_ids)
    save_daily_delta_from_baseline(
        char_data, inv_data, args.date, str(base_dir), auto_reset_baseline=False
    )
    with gzip.open(out_gz, "rt", encoding="utf-8") as fh:
        doc = json.load(fh)
    print("OK", args.date, "baseline_date", doc.get("baseline_date"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
