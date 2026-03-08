#!/usr/bin/env python3
"""
Build data/elemental_slot_options.json from dkp_elemental_to_magelo.json for use in
class_rankings.html "Gear upgrades across toons". Output: by_slot_id -> list of
{ pattern_name, pattern_id, by_class: { ROG: magelo_id, ... } } so the UI can,
for each slot and character class, show the elemental option (with stats from
item_stats) and compare to current gear.
"""
from pathlib import Path
import json
import os

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ELEMENTAL = REPO_ROOT.parent / "dkp" / "dkp_elemental_to_magelo.json"
OUT_PATH = REPO_ROOT / "data" / "elemental_slot_options.json"

# Elemental slot name (from DKP JSON) -> EQ slot_id(s) used in class_rankings (SLOT_ID_TO_EQ_SLOTS)
ELEMENTAL_SLOT_TO_IDS = {
    "head": [2],
    "chest": [17],
    "arms": [7],
    "legs": [18],
    "wrists": [9, 10],
    "feet": [19],
    "hands": [12],
}


def main():
    paths = [
        DEFAULT_ELEMENTAL,
        REPO_ROOT / "dkp_elemental_to_magelo.json",
        Path(os.environ.get("ELEMENTAL_JSON", "")),
    ]
    data = None
    for p in paths:
        if not p or not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            break
        except (OSError, json.JSONDecodeError):
            continue
    if not data:
        print("elemental_slot_options: dkp_elemental_to_magelo.json not found, skipping")
        return

    purchases = data.get("dkp_purchases") or {}
    by_slot_id = {}
    for dkp_id, entry in purchases.items():
        if not isinstance(entry, dict):
            continue
        slot_name = (entry.get("slot") or "").strip().lower()
        name = (entry.get("name") or "").strip()
        by_class_raw = entry.get("magelo_item_ids_by_class") or {}
        if not slot_name or slot_name not in ELEMENTAL_SLOT_TO_IDS:
            continue
        # Uppercase keys for UI (CLASS_TO_ABBREV is ROG, SHM, etc.)
        by_class = { k.upper(): str(v).strip() for k, v in by_class_raw.items() if v }
        if not by_class:
            continue
        opt = {"pattern_name": name, "pattern_id": str(dkp_id), "by_class": by_class}
        for eq_slot_id in ELEMENTAL_SLOT_TO_IDS[slot_name]:
            sid = str(eq_slot_id)
            if sid not in by_slot_id:
                by_slot_id[sid] = []
            by_slot_id[sid].append(opt)

    out = {"by_slot_id": by_slot_id}
    REPO_ROOT.mkdir(parents=True, exist_ok=True)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH} ({len(by_slot_id)} slot ids, {sum(len(v) for v in by_slot_id.values())} options)")


if __name__ == "__main__":
    main()
