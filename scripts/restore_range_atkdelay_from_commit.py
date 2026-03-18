#!/usr/bin/env python3
"""
One-off helper: restore bow / ranged atkDelay values into data/item_stats.json
from the known-good commit that re-parsed these from AllaClone.

This is safe to re-run; it only fills in missing atkDelay fields where the
reference commit had a value and the current file does not.
"""

import json
import subprocess
import sys
from pathlib import Path


MAGELO_ROOT = Path(__file__).resolve().parent.parent
ITEM_STATS_JSON = MAGELO_ROOT / "data" / "item_stats.json"

# Commit that contains the correct bow / ranged atkDelay values
SOURCE_COMMIT = "688ac3ab33afc78a629b05d79d182508cc47a1fc"


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error loading {path}: {e}", file=sys.stderr)
        return {}


def load_reference_from_git() -> dict:
    try:
        result = subprocess.run(
            ["git", "show", f"{SOURCE_COMMIT}:data/item_stats.json"],
            cwd=str(MAGELO_ROOT),
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"git show failed: {e}", file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        return {}
    try:
        return json.loads(result.stdout)
    except Exception as e:
        print(f"Error parsing reference JSON from git show: {e}", file=sys.stderr)
        return {}


def main() -> int:
    if not ITEM_STATS_JSON.exists():
        print(f"Missing {ITEM_STATS_JSON}", file=sys.stderr)
        return 1

    current = load_json(ITEM_STATS_JSON)
    if not isinstance(current, dict):
        print("Current item_stats.json is not an object", file=sys.stderr)
        return 1

    reference = load_reference_from_git()
    if not isinstance(reference, dict):
        print("Reference item_stats.json is not an object", file=sys.stderr)
        return 1

    updated = 0
    for sid, ref_entry in reference.items():
        if not isinstance(ref_entry, dict):
            continue
        if "atkDelay" not in ref_entry:
            continue
        cur_entry = current.get(sid)
        if not isinstance(cur_entry, dict):
            continue
        if "atkDelay" in cur_entry:
            continue
        cur_entry["atkDelay"] = ref_entry["atkDelay"]
        updated += 1

    if not updated:
        print("No atkDelay fields needed updating.")
        return 0

    ITEM_STATS_JSON.write_text(json.dumps(current, indent=2), encoding="utf-8")
    print(f"Updated atkDelay for {updated} items in {ITEM_STATS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

