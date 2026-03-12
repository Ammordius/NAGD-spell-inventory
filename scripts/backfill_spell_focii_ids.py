#!/usr/bin/env python3
"""
Backfill missing item IDs in spell_focii_level65.json by looking up item names
in item_stats.json, item_name_to_id.json, raid_item_sources, and dkp_mob_loot.
"""

import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
MAGELO_ROOT = SCRIPT_DIR.parent
SPELL_FOCII = MAGELO_ROOT / "spell_focii_level65.json"


def normalize_name(s: str) -> str:
    """Match merge_dkp_loot normalize."""
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"['`\u2019]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def name_variants(norm: str) -> list[str]:
    """Return normalization variants for fuzzy matching (e.g. hyphen, apostrophe)."""
    out = [norm]
    # Try without hyphens: "bear-hide boots" -> "bearhide boots"
    no_hyphen = norm.replace("-", "")
    if no_hyphen != norm:
        out.append(no_hyphen)
    # Try with/without "the": "x of the y" vs "x of y"
    if " of the " in norm:
        out.append(norm.replace(" of the ", " of "))
    if " of " in norm and " of the " not in norm:
        out.append(norm.replace(" of ", " of the "))
    return out


def _add_from_source(name_to_id: dict[str, int], path: Path, source_name: str) -> int:
    """Add name->id from a JSON file. Returns count added."""
    if not path.is_file():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return 0
    if not isinstance(data, dict):
        return 0
    added = 0
    # item_name_to_id format: {"normalized_name": id, ...} - keys are non-numeric
    sample_keys = list(data.keys())[:5]
    is_name_to_id_format = sample_keys and not any(str(k).replace(".", "").isdigit() for k in sample_keys)
    if is_name_to_id_format:
        for norm, iid in data.items():
            if norm and iid is not None and norm not in name_to_id:
                try:
                    name_to_id[norm] = int(iid)
                    added += 1
                except (ValueError, TypeError):
                    pass
    else:
        # item_stats / raid_sources format: {"id": {name: ...}, ...}
        for sid, ent in data.items():
            if not isinstance(ent, dict):
                continue
            try:
                nid = int(sid)
            except (ValueError, TypeError):
                continue
            name = (ent.get("name") or "").strip()
            if name and not name.startswith("(item "):
                norm = normalize_name(name)
                if norm and norm not in name_to_id:
                    name_to_id[norm] = nid
                    added += 1
    return added


def build_name_to_id() -> dict[str, int]:
    """Build normalized name -> item_id from all available sources (merge all)."""
    name_to_id: dict[str, int] = {}

    # 1. item_stats.json (largest - full item DB)
    for path in [MAGELO_ROOT / "data" / "item_stats.json", MAGELO_ROOT.parent / "dkp" / "data" / "item_stats.json"]:
        n = _add_from_source(name_to_id, path, "item_stats")
        if n > 0:
            break
    # 2. item_name_to_id.json
    _add_from_source(name_to_id, MAGELO_ROOT / "data" / "item_name_to_id.json", "item_name_to_id")

    # 3. raid_item_sources.json
    for path in [MAGELO_ROOT / "raid_item_sources.json", MAGELO_ROOT.parent / "dkp" / "raid_item_sources.json"]:
        _add_from_source(name_to_id, path, "raid_item_sources")
        if (MAGELO_ROOT / "raid_item_sources.json").exists():
            break

    # 4. dkp_mob_loot.json
    for path in [MAGELO_ROOT.parent / "dkp" / "data" / "dkp_mob_loot.json", MAGELO_ROOT.parent / "dkp" / "web" / "public" / "dkp_mob_loot.json"]:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for _key, entry in (data or {}).items():
                    if not isinstance(entry, dict):
                        continue
                    for item in entry.get("loot") or []:
                        iid = item.get("item_id")
                        name = (item.get("name") or "").strip()
                        if iid is not None and name and not name.startswith("(item "):
                            try:
                                nid = int(iid)
                                norm = normalize_name(name)
                                if norm and norm not in name_to_id:
                                    name_to_id[norm] = nid
                            except (ValueError, TypeError):
                                pass
            except (json.JSONDecodeError, OSError):
                pass
            break

    # 5. known_spell_focus_item_ids.json (manual mappings for items not in DB)
    known_path = MAGELO_ROOT / "data" / "known_spell_focus_item_ids.json"
    if known_path.is_file():
        try:
            data = json.loads(known_path.read_text(encoding="utf-8"))
            for name, iid in (data or {}).items():
                if name.startswith("_") or iid is None:
                    continue
                try:
                    norm = normalize_name(name)
                    if norm and norm not in name_to_id:
                        name_to_id[norm] = int(iid)
                except (ValueError, TypeError):
                    pass
        except (json.JSONDecodeError, OSError):
            pass

    return name_to_id


def main() -> int:
    if not SPELL_FOCII.is_file():
        print(f"Error: {SPELL_FOCII} not found")
        return 1

    name_to_id = build_name_to_id()
    print(f"Name->id lookup: {len(name_to_id)} entries")

    data = json.loads(SPELL_FOCII.read_text(encoding="utf-8"))
    focii = data.get("focii", [])
    added = 0
    still_missing = []

    for focus in focii:
        if not isinstance(focus, dict):
            continue
        for item in focus.get("items", []):
            if not isinstance(item, dict):
                continue
            if item.get("id") is not None:
                continue
            name = (item.get("name") or "").strip()
            if not name:
                continue
            norm = normalize_name(name)
            iid = name_to_id.get(norm)
            if iid is None:
                for v in name_variants(norm):
                    iid = name_to_id.get(v)
                    if iid is not None:
                        break
            if iid is not None:
                item["id"] = iid
                added += 1
                print(f"  + {name} -> {iid}")
            else:
                still_missing.append((focus.get("name", "?"), name))

    if added:
        SPELL_FOCII.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nAdded {added} item IDs to spell_focii_level65.json")
    else:
        print("No new IDs added.")

    if still_missing:
        print(f"\nStill missing ID ({len(still_missing)} items):")
        for foc, name in still_missing[:30]:
            print(f"  {foc}: {name}")
        if len(still_missing) > 30:
            print(f"  ... and {len(still_missing) - 30} more")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
