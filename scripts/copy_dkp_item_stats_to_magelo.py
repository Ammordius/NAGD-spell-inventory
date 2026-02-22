#!/usr/bin/env python3
"""
Copy DKP's complete item_stats.json into magelo and merge names from raid_item_sources.
Use this so item cards have full stats (e.g. Cap of Flowing Time) instead of name-only.

- Reads: ../dkp/web/public/item_stats.json (or --dkp-stats), magelo/raid_item_sources.json
- Writes: magelo/data/item_stats.json, magelo/data/all_items.csv

Run from magelo repo root: python scripts/copy_dkp_item_stats_to_magelo.py
"""
import csv
import json
import sys
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DKP_ITEM_STATS = MAGELO_ROOT.parent / "dkp" / "web" / "public" / "item_stats.json"
RAID_ITEM_SOURCES = MAGELO_ROOT / "raid_item_sources.json"
OUT_ITEM_STATS_JSON = MAGELO_ROOT / "data" / "item_stats.json"
OUT_ALL_ITEMS_CSV = MAGELO_ROOT / "data" / "all_items.csv"


def stats_to_csv_row(item_id: int, name: str, stats: dict) -> dict:
    """Flatten one item's stats for CSV (same columns as magelo all_items.csv)."""
    row = {"item_id": item_id, "name": name or ""}
    if not stats:
        return {**row, "slot": "", "ac": "", "flags": "", "mods": "", "resists": "", "effect": "", "focus": "", "required_level": "", "classes": "", "weight": "", "size": ""}
    row["slot"] = stats.get("slot") or ""
    row["ac"] = stats.get("ac") if stats.get("ac") is not None else ""
    row["flags"] = " | ".join(stats.get("flags") or [])
    mods = stats.get("mods") or []
    row["mods"] = ", ".join(f"{m.get('label', '')}: {m.get('value', '')}" for m in mods)
    resists = stats.get("resists") or []
    row["resists"] = ", ".join(f"{r.get('label', '')}: {r.get('value', '')}" for r in resists)
    row["effect"] = stats.get("effectSpellName") or stats.get("effectSpellId") or ""
    row["focus"] = stats.get("focusSpellName") or stats.get("focusSpellId") or ""
    row["required_level"] = stats.get("requiredLevel") if stats.get("requiredLevel") is not None else ""
    row["classes"] = stats.get("classes") or ""
    row["weight"] = stats.get("weight") if stats.get("weight") is not None else ""
    row["size"] = stats.get("size") or ""
    return row


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Copy DKP item_stats into magelo for full item cards")
    p.add_argument("--dkp-stats", type=Path, default=DEFAULT_DKP_ITEM_STATS, help="Path to DKP item_stats.json")
    p.add_argument("--raid-sources", type=Path, default=RAID_ITEM_SOURCES, help="Path to raid_item_sources.json")
    args = p.parse_args()

    if not args.dkp_stats.exists():
        print(f"Missing DKP item_stats: {args.dkp_stats}", file=sys.stderr)
        return 1
    if not args.raid_sources.exists():
        print(f"Missing raid_item_sources: {args.raid_sources}", file=sys.stderr)
        return 1

    dkp_stats = json.loads(args.dkp_stats.read_text(encoding="utf-8"))
    raid_sources = json.loads(args.raid_sources.read_text(encoding="utf-8"))

    # id -> name from raid_item_sources
    id_to_name_raid = {}
    for sid, entry in (raid_sources.items() if isinstance(raid_sources, dict) else []):
        try:
            iid = int(sid)
        except (ValueError, TypeError):
            continue
        name = (entry.get("name") or "").strip()
        if name:
            id_to_name_raid[iid] = name

    merged = {}
    for sid, stats in (dkp_stats.items() if isinstance(dkp_stats, dict) else []):
        try:
            iid = int(sid)
        except (ValueError, TypeError):
            continue
        entry = dict(stats) if isinstance(stats, dict) else {}
        name = (entry.get("name") or "").strip() or id_to_name_raid.get(iid, "")
        if name:
            entry["name"] = name
        merged[sid] = entry

    # Add raid-only items (name only) so cards can resolve
    for iid, name in id_to_name_raid.items():
        sid = str(iid)
        if sid not in merged:
            merged[sid] = {"name": name}

    OUT_ITEM_STATS_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_ITEM_STATS_JSON.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_ITEM_STATS_JSON} ({len(merged)} items)")

    # Write all_items.csv
    fieldnames = ["item_id", "name", "slot", "ac", "flags", "mods", "resists", "effect", "focus", "required_level", "classes", "weight", "size"]
    with open(OUT_ALL_ITEMS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for sid in sorted(merged.keys(), key=lambda x: int(x) if x.isdigit() else 0):
            try:
                iid = int(sid)
            except ValueError:
                continue
            entry = merged[sid]
            name = (entry.get("name") or "").strip()
            row = stats_to_csv_row(iid, name, entry)
            w.writerow(row)
    print(f"Wrote {OUT_ALL_ITEMS_CSV}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
