#!/usr/bin/env python3
"""
Update spell_focii_level65.json with item IDs (from raid loot) and classes (from item_stats.csv).
Also export item_stats to magelo repo as JSON and CSV.

- Reads magelo/raid_mob_loot.json and magelo/raid_item_sources.json for item_id <-> name.
- Reads dkp/data/item_stats.csv for item stats and classes.
- Matches focus item names case-insensitively and with fuzzy special-char handling (` vs ').
- Writes: spell_focii_level65.json (updated), data/item_stats.json, data/all_items.csv.

Run from repo root (magelo) or with paths; expects ../dkp/data/item_stats.csv or --item-stats.
"""
import csv
import json
import re
import sys
from difflib import get_close_matches
from pathlib import Path

# Paths relative to magelo repo root
MAGELO_ROOT = Path(__file__).resolve().parent.parent
RAID_MOB_LOOT = MAGELO_ROOT / "raid_mob_loot.json"
RAID_ITEM_SOURCES = MAGELO_ROOT / "raid_item_sources.json"
SPELL_FOCII = MAGELO_ROOT / "spell_focii_level65.json"
OUT_ITEM_STATS_JSON = MAGELO_ROOT / "data" / "item_stats.json"
OUT_ALL_ITEMS_CSV = MAGELO_ROOT / "data" / "all_items.csv"
DEFAULT_ITEM_STATS_CSV = MAGELO_ROOT.parent / "dkp" / "data" / "item_stats.csv"
DEFAULT_DKP_MOB_LOOT = MAGELO_ROOT.parent / "dkp" / "data" / "dkp_mob_loot.json"


def normalize_name(s: str) -> str:
    """Lowercase, collapse spaces, normalize apostrophe/backtick for matching."""
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    # Treat backtick and apostrophe (including curly) as equivalent
    s = re.sub(r"['`\u2019]", "'", s)
    s = re.sub(r"\s+", " ", s)
    return s


def build_name_to_id_from_raid_loot(
    raid_mob_loot_path: Path,
    raid_sources_path: Path,
    dkp_mob_loot_path: Path | None = None,
) -> tuple[dict[str, int], dict[int, str]]:
    """Build normalized_name -> item_id and item_id -> display name from raid/dkp loot.
    Returns (name_to_id, id_to_name). Prefers real item names over '(item NNN)' placeholders."""
    name_to_id: dict[str, int] = {}
    id_to_name: dict[int, str] = {}

    def prefer_name(existing: str | None, new: str) -> bool:
        """True if we should use new over existing (e.g. real name over '(item 123)')."""
        if not existing:
            return True
        if new.startswith("(item ") and ")" in new:
            return False
        return True

    def add_loot(data: dict) -> None:
        for entry in (data.values() if isinstance(data, dict) else []):
            for item in entry.get("loot") or []:
                iid = item.get("item_id")
                name = (item.get("name") or "").strip()
                if iid is not None and name:
                    iid = int(iid)
                    norm = normalize_name(name)
                    if norm and norm not in name_to_id:
                        name_to_id[norm] = iid
                    if prefer_name(id_to_name.get(iid), name):
                        id_to_name[iid] = name

    if raid_mob_loot_path.exists():
        add_loot(json.loads(raid_mob_loot_path.read_text(encoding="utf-8")))

    if dkp_mob_loot_path and dkp_mob_loot_path.exists():
        add_loot(json.loads(dkp_mob_loot_path.read_text(encoding="utf-8")))

    if raid_sources_path.exists():
        data = json.loads(raid_sources_path.read_text(encoding="utf-8"))
        for sid, entry in (data.items() if isinstance(data, dict) else []):
            try:
                iid = int(sid)
            except (ValueError, TypeError):
                continue
            name = (entry.get("name") or "").strip()
            if name:
                norm = normalize_name(name)
                if norm and norm not in name_to_id:
                    name_to_id[norm] = iid
                if prefer_name(id_to_name.get(iid), name):
                    id_to_name[iid] = name

    return name_to_id, id_to_name


def load_item_stats_csv(csv_path: Path) -> tuple[dict[int, dict], dict[str, int]]:
    """Load item_stats.csv. Returns (id_to_stats, normalized_name_to_id)."""
    id_to_stats: dict[int, dict] = {}
    name_to_id: dict[str, int] = {}
    if not csv_path.exists():
        return id_to_stats, name_to_id

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                iid = int(row.get("item_id", 0))
            except (ValueError, TypeError):
                continue
            name = (row.get("name") or "").strip()
            stats = {
                "name": name,
                "slot": row.get("slot", ""),
                "ac": row.get("ac", ""),
                "flags": row.get("flags", ""),
                "mods": row.get("mods", ""),
                "resists": row.get("resists", ""),
                "effect": row.get("effect", ""),
                "focus": row.get("focus", ""),
                "required_level": row.get("required_level", ""),
                "classes": row.get("classes", ""),
                "weight": row.get("weight", ""),
                "size": row.get("size", ""),
            }
            id_to_stats[iid] = stats
            if name:
                norm = normalize_name(name)
                if norm:
                    name_to_id[norm] = iid

    return id_to_stats, name_to_id


def find_item_id(
    item_name: str,
    existing_id: int | None,
    name_to_id_raid: dict[str, int],
    name_to_id_stats: dict[str, int],
    all_names_raid: list[str],
    cutoff: float = 0.82,
) -> int | None:
    """Return item_id if we can resolve; prefer existing_id, then exact match, then fuzzy."""
    if existing_id is not None:
        return existing_id
    norm = normalize_name(item_name)
    if not norm:
        return None
    # Prefer raid loot/sources, then item_stats
    if norm in name_to_id_raid:
        return name_to_id_raid[norm]
    if norm in name_to_id_stats:
        return name_to_id_stats[norm]
    # Fuzzy: only if we have a close match
    if all_names_raid:
        matches = get_close_matches(norm, all_names_raid, n=1, cutoff=cutoff)
        if matches:
            return name_to_id_raid.get(matches[0]) or name_to_id_stats.get(matches[0])
    return None


def update_focii_with_ids_and_classes(
    focii_path: Path,
    name_to_id_raid: dict[str, int],
    id_to_stats: dict[int, dict],
    name_to_id_stats: dict[str, int],
) -> tuple[dict, list[tuple[str, str]]]:
    """Update focii JSON: add id and classes to each item. Returns (updated data, list of (focus_name, item_name) unmatched)."""
    data = json.loads(focii_path.read_text(encoding="utf-8"))
    focii = data.get("focii") if isinstance(data, dict) and "focii" in data else data
    if not isinstance(focii, list):
        focii = [data] if isinstance(data, dict) else []
    wrap = {"focii": focii}

    all_names_raid = list(name_to_id_raid.keys())
    unmatched: list[tuple[str, str]] = []

    for focus in focii:
        focus_name = focus.get("name", "")
        for item in focus.get("items") or []:
            name = (item.get("name") or "").strip()
            existing_id = item.get("id")
            if isinstance(existing_id, str):
                try:
                    existing_id = int(existing_id)
                except ValueError:
                    existing_id = None
            iid = find_item_id(
                name,
                existing_id,
                name_to_id_raid,
                name_to_id_stats,
                all_names_raid,
            )
            if iid is not None:
                item["id"] = iid
                stats = id_to_stats.get(iid)
                if stats and stats.get("classes"):
                    item["classes"] = stats["classes"].strip()
            else:
                # Try stats-only match for classes (no raid loot link)
                stats_id = name_to_id_stats.get(normalize_name(name))
                if stats_id:
                    item["id"] = stats_id
                    st = id_to_stats.get(stats_id)
                    if st and st.get("classes"):
                        item["classes"] = st["classes"].strip()
                else:
                    unmatched.append((focus_name, name))

    return wrap, unmatched


def normalize_focus_name_for_match(s: str) -> str:
    """Strip Roman numeral suffix ( I through VII) for matching CSV focus to spell_focii focus name."""
    if not s or not isinstance(s, str):
        return ""
    s = s.strip()
    s = re.sub(r"['`\u2019]", "'", s)
    # Strip trailing " III", " IV", " I", " II", " V", " VI", " VII"
    s = re.sub(r"\s+(I{1,3}|IV|V|VI{0,3}|VII)$", "", s, flags=re.IGNORECASE)
    return s.strip()


def add_focus_items_from_csv(
    focii_list: list,
    id_to_stats: dict[int, dict],
    focus_names_set: set[str],
) -> int:
    """Add any item_stats rows that have a focus but are not yet in that focus's items list. Returns count added."""
    # Build focus name -> index in focii_list and existing (id, norm_name) per focus
    focus_name_to_index: dict[str, int] = {}
    existing_per_focus: list[set[tuple[int | None, str]]] = []
    for i, focus in enumerate(focii_list):
        name = focus.get("name", "")
        if name:
            focus_name_to_index[normalize_name(name)] = i
            focus_name_to_index[normalize_focus_name_for_match(name)] = i
        existing = set()
        for item in focus.get("items") or []:
            iname = (item.get("name") or "").strip()
            iid = item.get("id")
            if isinstance(iid, str):
                try:
                    iid = int(iid)
                except ValueError:
                    iid = None
            existing.add((iid, normalize_name(iname)))
        existing_per_focus.append(existing)

    added = 0
    for iid, stats in id_to_stats.items():
        focus_str = (stats.get("focus") or "").strip()
        if not focus_str:
            continue
        name = (stats.get("name") or "").strip()
        if not name:
            continue
        norm_focus = normalize_focus_name_for_match(focus_str)  # e.g. "Anger of Druzzil"
        norm_focus_key = normalize_name(norm_focus)  # e.g. "anger of druzzil"
        idx = focus_name_to_index.get(norm_focus_key)
        if idx is None:
            # Try matching any focus name that normalizes to same
            for fn in focus_names_set:
                if normalize_name(fn) == norm_focus_key:
                    for i, f in enumerate(focii_list):
                        if (f.get("name") or "").strip() == fn:
                            idx = i
                            break
                    break
        if idx is None:
            continue
        norm_name = normalize_name(name)
        existing = existing_per_focus[idx]
        if (iid, norm_name) in existing:
            continue
        # Already in list by id?
        if any((eid == iid and eid is not None) for eid, _ in existing):
            continue
        if any(en == norm_name for _, en in existing):
            continue
        # Add new item
        new_item = {"name": name, "id": iid}
        if stats.get("classes"):
            new_item["classes"] = stats["classes"].strip()
        focii_list[idx].setdefault("items", []).append(new_item)
        existing_per_focus[idx].add((iid, norm_name))
        added += 1
    return added


def write_item_stats_json(id_to_stats: dict[int, dict], out_path: Path) -> None:
    """Write data/item_stats.json keyed by item_id."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    by_id = {str(k): v for k, v in id_to_stats.items()}
    out_path.write_text(json.dumps(by_id, indent=2), encoding="utf-8")


def write_all_items_csv(id_to_stats: dict[int, dict], out_path: Path) -> None:
    """Write data/all_items.csv with all item stats (usable CSV)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["item_id", "name", "slot", "ac", "flags", "mods", "resists", "effect", "focus", "required_level", "classes", "weight", "size"]
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for iid in sorted(id_to_stats.keys()):
            row = {"item_id": iid, **id_to_stats[iid]}
            w.writerow(row)


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Update focus items with raid item IDs and classes; export item_stats to magelo.")
    p.add_argument("--item-stats", type=Path, default=DEFAULT_ITEM_STATS_CSV, help="Path to item_stats.csv")
    p.add_argument("--raid-loot", type=Path, default=RAID_MOB_LOOT, help="Path to raid_mob_loot.json")
    p.add_argument("--raid-sources", type=Path, default=RAID_ITEM_SOURCES, help="Path to raid_item_sources.json")
    p.add_argument("--dkp-mob-loot", type=Path, default=DEFAULT_DKP_MOB_LOOT, help="Path to dkp_mob_loot.json (optional extra item names)")
    p.add_argument("--focii", type=Path, default=SPELL_FOCII, help="Path to spell_focii_level65.json")
    p.add_argument("--no-write-focii", action="store_true", help="Do not overwrite spell_focii_level65.json")
    p.add_argument("--no-write-stats", action="store_true", help="Do not write data/item_stats.json and data/all_items.csv")
    args = p.parse_args()

    print("Building name->id from raid loot...")
    name_to_id_raid, id_to_name_raid = build_name_to_id_from_raid_loot(
        args.raid_loot, args.raid_sources, args.dkp_mob_loot
    )
    print(f"  Raid loot/sources (+ dkp): {len(name_to_id_raid)} unique item names")

    print("Loading item_stats.csv...")
    id_to_stats, name_to_id_stats = load_item_stats_csv(args.item_stats)
    print(f"  Item stats: {len(id_to_stats)} items")

    # Merge in raid/dkp items that are not in CSV so item cards can resolve by id (and name)
    id_to_stats_merged = dict(id_to_stats)
    for iid, name in id_to_name_raid.items():
        if iid not in id_to_stats_merged:
            id_to_stats_merged[iid] = {"name": name}
    if len(id_to_stats_merged) > len(id_to_stats):
        print(f"  Merged {len(id_to_stats_merged) - len(id_to_stats)} raid/dkp-only items into stats")

    if not args.focii.exists():
        print(f"Missing focii file: {args.focii}", file=sys.stderr)
        sys.exit(1)

    print("Updating focus list with item IDs and classes...")
    updated, unmatched = update_focii_with_ids_and_classes(
        args.focii, name_to_id_raid, id_to_stats, name_to_id_stats
    )
    if unmatched:
        print(f"  Unmatched focus items (no id/classes added): {len(unmatched)}")
        for fn, iname in unmatched[:20]:
            print(f"    - {fn}: {iname}")
        if len(unmatched) > 20:
            print(f"    ... and {len(unmatched) - 20} more")

    # Add any items from item_stats that have a focus but are missing from the focus list
    focus_names_set = {f.get("name", "").strip() for f in updated.get("focii") or [] if f.get("name")}
    n_added = add_focus_items_from_csv(
        updated["focii"], id_to_stats, focus_names_set
    )
    if n_added:
        print(f"  Added {n_added} focus items from item_stats.csv (were missing from focus list)")

    if not args.no_write_focii:
        args.focii.write_text(json.dumps(updated, indent=2), encoding="utf-8")
        print(f"Wrote {args.focii}")

    if not args.no_write_stats and id_to_stats_merged:
        write_item_stats_json(id_to_stats_merged, OUT_ITEM_STATS_JSON)
        print(f"Wrote {OUT_ITEM_STATS_JSON}")
        write_all_items_csv(id_to_stats_merged, OUT_ALL_ITEMS_CSV)
        print(f"Wrote {OUT_ALL_ITEMS_CSV}")


if __name__ == "__main__":
    main()
