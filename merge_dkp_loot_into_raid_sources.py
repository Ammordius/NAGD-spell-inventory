#!/usr/bin/env python3
"""
Merge item_id -> { mob, zone, name } from dkp_mob_loot.json into raid_item_sources.json.

DKP repo builds dkp_mob_loot.json from DB + raid_item_sources + elemental_armor; it has
almost all loot (including elemental patterns/molds). Magelo's raid_item_sources.json is
built from raid_items.txt and only contains items from that paste — so elemental and
other DKP-only loot are missing. That causes item cards and mob tracker to not show
those items as linked or dropped.

This script:
1) Adds every item_id from dkp_mob_loot that is not already in raid_item_sources.
2) Backfills real item names for entries that currently have placeholder "(item N)" or empty name.
3) Optionally writes data/item_name_to_id.json (normalized name -> item_id) so the frontend
   can resolve magelo item names to IDs reliably.

Usage:
    python merge_dkp_loot_into_raid_sources.py [--dkp-loot PATH] [--raid-sources PATH] [--dry-run]
    python merge_dkp_loot_into_raid_sources.py --write-name-to-id   # also emit data/item_name_to_id.json

Defaults:
    --dkp-loot: ../dkp/data/dkp_mob_loot.json (relative to script dir) or MAGELO_ROOT
    --raid-sources: raid_item_sources.json in script dir
"""

import argparse
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_RAID_SOURCES = SCRIPT_DIR / "raid_item_sources.json"
DEFAULT_DKP_LOOT = SCRIPT_DIR.parent / "dkp" / "data" / "dkp_mob_loot.json"
OUT_NAME_TO_ID = SCRIPT_DIR / "data" / "item_name_to_id.json"

PLACEHOLDER_PAT = re.compile(r"^\(item\s+\d+\)$", re.I)


def normalize_name(s: str) -> str:
    """Lowercase, collapse spaces, remove apostrophe/backtick (match frontend normalizeItemNameForLookup)."""
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"['`\u2019]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def is_placeholder_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return True
    return bool(PLACEHOLDER_PAT.match(name.strip()))


def main() -> int:
    p = argparse.ArgumentParser(
        description="Merge dkp_mob_loot into raid_item_sources; backfill names; optionally emit item_name_to_id.json."
    )
    p.add_argument(
        "--dkp-loot",
        type=Path,
        default=DEFAULT_DKP_LOOT,
        help="Path to dkp_mob_loot.json",
    )
    p.add_argument(
        "--raid-sources",
        type=Path,
        default=DEFAULT_RAID_SOURCES,
        help="Path to raid_item_sources.json (read and write)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be changed without writing",
    )
    p.add_argument(
        "--write-name-to-id",
        action="store_true",
        help="Write data/item_name_to_id.json (normalized name -> item_id) for frontend resolution",
    )
    args = p.parse_args()

    raid_path = args.raid_sources if args.raid_sources.is_absolute() else SCRIPT_DIR / args.raid_sources
    dkp_path = args.dkp_loot if args.dkp_loot.is_absolute() else SCRIPT_DIR / args.dkp_loot

    if not raid_path.exists():
        print(f"Error: {raid_path} not found.")
        return 1
    if not dkp_path.exists():
        print(f"Error: {dkp_path} not found. Run build_dkp_mob_loot.py or point --dkp-loot to dkp repo.")
        return 1

    raid_sources: dict = json.loads(raid_path.read_text(encoding="utf-8"))
    dkp_loot: dict = json.loads(dkp_path.read_text(encoding="utf-8"))

    # Build item_id -> real name from dkp_mob_loot (first occurrence wins)
    dkp_id_to_name: dict[str, str] = {}
    for entry in dkp_loot.values() if isinstance(dkp_loot, dict) else []:
        if not isinstance(entry, dict):
            continue
        for item in entry.get("loot") or []:
            iid = item.get("item_id")
            name = (item.get("name") or "").strip()
            if iid is None or not name or is_placeholder_name(name):
                continue
            sid = str(int(iid))
            if sid not in dkp_id_to_name:
                dkp_id_to_name[sid] = name

    added: list[tuple[str, dict]] = []
    backfilled: list[tuple[str, str, str]] = []  # (sid, old_name, new_name)

    for _key, entry in dkp_loot.items():
        if not isinstance(entry, dict):
            continue
        mob = (entry.get("mob") or "").strip()
        zone = (entry.get("zone") or "").strip()
        loot = entry.get("loot") or []
        for item in loot:
            iid = item.get("item_id")
            name = (item.get("name") or "").strip()
            if iid is None:
                continue
            sid = str(int(iid))
            name = name or f"Item {iid}"
            if sid not in raid_sources:
                new_entry = {"mob": mob, "zone": zone, "name": name}
                raid_sources[sid] = new_entry
                added.append((sid, new_entry))
            else:
                # Backfill name if current is placeholder or empty
                current = raid_sources[sid]
                current_name = (current.get("name") or "").strip()
                if is_placeholder_name(current_name) and not is_placeholder_name(name):
                    backfilled.append((sid, current_name or "(empty)", name))
                    current["name"] = name

    total_items = len(raid_sources)
    if added:
        print(f"Added {len(added)} item(s) from dkp_mob_loot to raid_item_sources.")
        for sid, ent in added[:10]:
            print(f"  {sid}: {ent.get('name', '')} <- {ent.get('mob', '')} in {ent.get('zone', '')}")
        if len(added) > 10:
            print(f"  ... and {len(added) - 10} more")
    if backfilled:
        print(f"Backfilled {len(backfilled)} real names (replaced placeholder/empty).")
        for sid, old, new in backfilled[:10]:
            print(f"  {sid}: {old!r} -> {new!r}")
        if len(backfilled) > 10:
            print(f"  ... and {len(backfilled) - 10} more")

    if not added and not backfilled:
        print("No new items and no names to backfill; raid_item_sources unchanged.")

    print(f"raid_item_sources.json has {total_items} items.")

    if args.dry_run:
        print("Dry run: not writing files.")
        if args.write_name_to_id:
            _write_name_to_id(raid_sources, OUT_NAME_TO_ID, dry_run=True)
        return 0

    if added or backfilled:
        out = {k: v for k, v in raid_sources.items()}
        raid_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Wrote {raid_path}")

    if args.write_name_to_id:
        _write_name_to_id(raid_sources, OUT_NAME_TO_ID, dry_run=False)

    return 0


def _write_name_to_id(raid_sources: dict, out_path: Path, *, dry_run: bool) -> None:
    """Build normalized name -> item_id from raid_sources and write JSON (or print if dry_run)."""
    name_to_id: dict[str, int] = {}
    for sid, ent in raid_sources.items():
        try:
            iid = int(sid)
        except (ValueError, TypeError):
            continue
        name = (ent.get("name") or "").strip()
        if not name or is_placeholder_name(name):
            continue
        norm = normalize_name(name)
        if norm and norm not in name_to_id:
            name_to_id[norm] = iid
    # JSON keys must be strings
    out_obj = {k: v for k, v in name_to_id.items()}
    if dry_run:
        print(f"Would write {len(out_obj)} name->id entries to {out_path}")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_obj, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out_path} ({len(out_obj)} name->id entries)")


if __name__ == "__main__":
    raise SystemExit(main())
