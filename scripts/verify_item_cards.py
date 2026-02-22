#!/usr/bin/env python3
"""
Verify that key items (Cap of Flowing Time, etc.) are resolvable for item cards.
Run from repo root: python scripts/verify_item_cards.py
Checks: data/item_name_to_id.json and data/item_stats.json contain the items;
        normalization matches between Python and what the frontend expects.
"""
import json
import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
NAME_TO_ID = DATA_DIR / "item_name_to_id.json"
ITEM_STATS = DATA_DIR / "item_stats.json"

# Same normalization as merge_dkp_loot_into_raid_sources.normalize_name and frontend normalizeItemNameForLookup
def normalize_name(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"['`\u2019]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


KEY_ITEMS = [
    "Cap of Flowing Time",
    "Mask of Strategic Insight",
    "Amulet of Crystal Dreams",
    "Bracer of Precision",
]


def main():
    os.chdir(REPO_ROOT)
    ok = True

    if not NAME_TO_ID.exists():
        print(f"[FAIL] {NAME_TO_ID} not found. Run: python merge_dkp_loot_into_raid_sources.py --write-name-to-id")
        return 1
    with open(NAME_TO_ID, encoding="utf-8") as f:
        name_to_id = json.load(f)

    print("data/item_name_to_id.json:")
    for name in KEY_ITEMS:
        norm = normalize_name(name)
        iid = name_to_id.get(norm)
        if iid is not None:
            print(f"  [OK] {name!r} -> norm={norm!r} -> id={iid}")
        else:
            print(f"  [MISSING] {name!r} (norm={norm!r})")
            ok = False

    if not ITEM_STATS.exists():
        print(f"\n[WARN] {ITEM_STATS} not found (item cards will show name-only, no stats)")
    else:
        with open(ITEM_STATS, encoding="utf-8") as f:
            item_stats = json.load(f)
        print("\ndata/item_stats.json (ids from name_to_id):")
        for name in KEY_ITEMS:
            norm = normalize_name(name)
            iid = name_to_id.get(norm)
            if iid is None:
                continue
            sid = str(iid)
            if sid in item_stats:
                print(f"  [OK] {name} (id={iid}) has stats")
            else:
                print(f"  [MISSING] {name} (id={iid}) has no stats in item_stats.json")
                ok = False

    if ok:
        print("\n[OK] All key items are resolvable for item cards.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
