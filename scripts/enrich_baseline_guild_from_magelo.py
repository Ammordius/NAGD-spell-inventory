#!/usr/bin/env python3
"""Merge guild from current Magelo character export into baseline archives.

The Feb 2026 baseline era predates the ``guild`` field in baseline JSON. This script
adds ``guild`` to every character row without changing ``baseline_date`` or other stats.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_spell_page import find_latest_magelo_file, parse_character_data  # noqa: E402


def enrich_baseline_guild(
    baseline_path: Path,
    char_file: Path,
    *,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Return (chars_updated, chars_with_guild) after merging guild into baseline."""
    with gzip.open(baseline_path, "rt", encoding="utf-8") as f:
        baseline = json.load(f)

    guild_by_name = {
        name: (row.get("guild") or "").strip()
        for name, row in parse_character_data(str(char_file), None).items()
    }

    characters = baseline.get("characters") or {}
    updated = 0
    with_guild = 0
    for name, row in characters.items():
        guild = guild_by_name.get(name, "")
        if row.get("guild") != guild:
            row["guild"] = guild
            updated += 1
        if guild:
            with_guild += 1

    if dry_run:
        return updated, with_guild

    tmp = baseline_path.with_suffix(baseline_path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)
    shutil.move(str(tmp), str(baseline_path))
    return updated, with_guild


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-dir",
        type=Path,
        default=Path("delta_snapshots"),
        help="Directory containing baseline_master*.json.gz",
    )
    ap.add_argument(
        "--baseline-date",
        default="2026-02-09",
        help="baseline_date to enrich (baseline_master_<date>.json.gz)",
    )
    ap.add_argument(
        "--character",
        type=Path,
        default=None,
        help="Magelo character TSV (default: character/TAKP_character.txt)",
    )
    ap.add_argument(
        "--also-master",
        action="store_true",
        help="Also copy enriched archive to baseline_master.json.gz",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base_dir = args.base_dir.resolve()
    archive = base_dir / f"baseline_master_{args.baseline_date}.json.gz"
    if not archive.is_file():
        print(f"ERROR: missing {archive}", file=sys.stderr)
        return 1

    char_file = args.character
    if char_file is None:
        char_dir = Path("character")
        char_file = char_dir / "TAKP_character.txt"
        if not char_file.is_file():
            found = find_latest_magelo_file(str(char_dir), "TAKP_character")
            if not found:
                print("ERROR: no character export found", file=sys.stderr)
                return 1
            char_file = Path(found)
    char_file = char_file.resolve()
    if not char_file.is_file():
        print(f"ERROR: missing {char_file}", file=sys.stderr)
        return 1

    updated, with_guild = enrich_baseline_guild(archive, char_file, dry_run=args.dry_run)
    print(
        f"{'[dry-run] ' if args.dry_run else ''}{archive.name}: "
        f"updated {updated} rows, {with_guild} chars with guild"
    )

    if args.also_master and not args.dry_run:
        master = base_dir / "baseline_master.json.gz"
        shutil.copy2(archive, master)
        print(f"OK: copied -> {master.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
