#!/usr/bin/env python3
"""
Cross-reference focus names on ornate and elemental armor items against canonical spell_focii_level65.json
and TAKP focus name maps in generate_class_rankings.py (SPELL_DAMAGE_TYPE_MAP, SPELL_MANA_EFFICIENCY_CATEGORY_MAP,
SPELL_HASTE_CATEGORY_MAP, SPELL_DURATION_CATEGORY_MAP). Reports items whose focus is not in the canonical list
so you can confirm or add them.

Reads: spell_focii_level65.json, data/ornate_armor_ids.json, elemental_armor_ids.txt, data/item_stats.json
Prints: For each ornate/elemental item with a focus, whether the focus name is canonical (and category) or UNKNOWN.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parent.parent
SPELL_FOCII = MAGELO_ROOT / "spell_focii_level65.json"
ORNATE_IDS_JSON = MAGELO_ROOT / "data" / "ornate_armor_ids.json"
ELEMENTAL_IDS_TXT = MAGELO_ROOT / "elemental_armor_ids.txt"
ITEM_STATS_JSON = MAGELO_ROOT / "data" / "item_stats.json"


def normalize_focus_name(s: str) -> str:
    """Lowercase, collapse spaces, normalize apostrophe/backtick for matching."""
    if not s or not isinstance(s, str):
        return ""
    s = s.lower().strip()
    s = re.sub(r"['`\u2019]", "'", s)
    s = re.sub(r"\s+", " ", s)
    return s


def load_canonical_focus_names() -> dict[str, str]:
    """Load focus name -> category from spell_focii_level65.json. Returns dict of normalized_name -> category."""
    if not SPELL_FOCII.exists():
        return {}
    data = json.loads(SPELL_FOCII.read_text(encoding="utf-8"))
    focii = data.get("focii") if isinstance(data, dict) else []
    if not isinstance(focii, list):
        return {}
    out = {}
    for f in focii:
        name = (f.get("name") or "").strip()
        cat = (f.get("category") or "").strip()
        if name:
            out[normalize_focus_name(name)] = cat
    return out


def load_class_rankings_focus_maps() -> dict[str, str]:
    """Known focus names from generate_class_rankings maps (SPELL_DAMAGE_TYPE_MAP, etc.) as canonical."""
    try:
        import sys
        root = MAGELO_ROOT
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        from generate_class_rankings import (
            SPELL_DAMAGE_TYPE_MAP,
            SPELL_DURATION_CATEGORY_MAP,
            SPELL_HASTE_CATEGORY_MAP,
            SPELL_MANA_EFFICIENCY_CATEGORY_MAP,
        )
    except ImportError:
        return {}
    out = {}
    for name, sub in SPELL_DAMAGE_TYPE_MAP.items():
        out[normalize_focus_name(name)] = f"Spell Damage ({sub})"
    for name, sub in SPELL_MANA_EFFICIENCY_CATEGORY_MAP.items():
        out[normalize_focus_name(name)] = f"Spell Mana Efficiency ({sub})"
    for name, sub in SPELL_HASTE_CATEGORY_MAP.items():
        out[normalize_focus_name(name)] = f"Spell Haste ({sub})"
    for name, sub in SPELL_DURATION_CATEGORY_MAP.items():
        out[normalize_focus_name(name)] = f"Spell Duration ({sub})"
    return out


def load_ornate_ids() -> list[int]:
    """Ornate + extra IDs from data/ornate_armor_ids.json."""
    if not ORNATE_IDS_JSON.exists():
        return []
    data = json.loads(ORNATE_IDS_JSON.read_text(encoding="utf-8"))
    ids = list(data.get("ornate_from_wiki") or [])
    ids.extend(data.get("extra_ids") or [])
    return sorted(set(ids))


def load_elemental_ids() -> list[int]:
    """Elemental armor IDs from elemental_armor_ids.txt (numeric lines only)."""
    if not ELEMENTAL_IDS_TXT.exists():
        return []
    ids = []
    for line in ELEMENTAL_IDS_TXT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.isdigit():
            ids.append(int(line))
    return sorted(set(ids))


def main() -> int:
    canonical = load_canonical_focus_names()
    try:
        code_maps = load_class_rankings_focus_maps()
        for k, v in code_maps.items():
            if k and k not in canonical:
                canonical[k] = v
    except Exception:
        pass  # if generate_class_rankings not importable, use only spell_focii

    ornate_ids = set(load_ornate_ids())
    elemental_ids = set(load_elemental_ids())
    supplement_ids = ornate_ids | elemental_ids

    if not ITEM_STATS_JSON.exists():
        print("item_stats.json not found. Run fetch_supplement_items.py first to pull item data from AllaClone.")
        return 1
    item_stats = json.loads(ITEM_STATS_JSON.read_text(encoding="utf-8"))

    print("Focus cross-reference: ornate and elemental armor vs canonical lists (spell_focii_level65 + TAKP maps)")
    print("=" * 80)
    unknown = []
    for iid in sorted(supplement_ids):
        sid = str(iid)
        entry = item_stats.get(sid)
        if not entry:
            continue
        focus_name = (entry.get("focusSpellName") or entry.get("focus") or "").strip()
        if not focus_name:
            continue
        item_name = (entry.get("name") or f"Item {iid}").strip()
        norm = normalize_focus_name(focus_name)
        cat = canonical.get(norm)
        kind = "ornate" if iid in ornate_ids else "elemental"
        if cat:
            print(f"  [{kind}] id={iid}  {item_name[:45]}")
            print(f"         focus: {focus_name}  -> canonical: {cat}")
        else:
            print(f"  [{kind}] id={iid}  {item_name[:45]}")
            print(f"         focus: {focus_name}  -> UNKNOWN (not in spell_focii or CLASS_WEIGHTS maps)")
            unknown.append((iid, item_name, focus_name))
    if unknown:
        print()
        print("Items with focus not in canonical list (please confirm if these are foci and add to spell_focii or maps):")
        for iid, iname, fname in unknown:
            print(f"  id={iid}  {iname}  focus=\"{fname}\"")
    return 0


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(MAGELO_ROOT))
    sys.exit(main())
