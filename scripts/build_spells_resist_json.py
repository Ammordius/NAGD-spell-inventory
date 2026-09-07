"""
Build data/spells_resist.json from Server SQL dumps (spells_en).

Compact catalog for the Spell Land Rate calculator: resisttype, ResistDiff,
partial-capable flag, class levels, and effect slots needed for IsPartialCapableSpell
and harmony/mez/charm detection.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


SE_CURRENT_HP = 0
SE_CHA = 10
SE_LULL = 18
SE_CHARM = 22
SE_CHANGE_FRENZY_RAD = 30
SE_MEZ = 31
SE_CURRENT_HP_ONCE = 79
SE_HARMONY = 86
SE_BLANK = 254
SE_STACKING_BLOCK = 148
SE_STACKING_OVERWRITE = 149

# EQ class order for spells_en classes1..classes15 (1-indexed War..Beastlord)
CLASS_INDEX = {
    "Warrior": 0,
    "Cleric": 1,
    "Paladin": 2,
    "Ranger": 3,
    "Shadow Knight": 4,
    "Druid": 5,
    "Monk": 6,
    "Bard": 7,
    "Rogue": 8,
    "Shaman": 9,
    "Necromancer": 10,
    "Wizard": 11,
    "Magician": 12,
    "Enchanter": 13,
    "Beastlord": 14,
}


def _magelo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Server"


def _int_field(raw: dict[str, Any], key: str, default: int = 0) -> int:
    v = raw.get(key)
    if v is None:
        return default
    return int(float(v))


def is_blank_effect(effect_id: int, base: int, formula: int) -> bool:
    if effect_id == SE_BLANK:
        return True
    if effect_id == SE_CHA and base == 0 and formula == 100:
        return True
    if effect_id in (SE_STACKING_BLOCK, SE_STACKING_OVERWRITE):
        return True
    return False


def is_partial_capable(effectids: list[int], bases: list[int], formulas: list[int], no_partial: int) -> bool:
    if no_partial:
        return False
    for eid, base, formula in zip(effectids, bases, formulas, strict=True):
        if is_blank_effect(eid, base, formula):
            continue
        if eid in (SE_CURRENT_HP, SE_CURRENT_HP_ONCE) and base < 0:
            return True
        return False
    return False


def has_effect(effectids: list[int], effect: int) -> bool:
    return effect in effectids


def spell_resist_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    sid = int(raw["id"])
    name = raw.get("name") or ""
    if not name or name.startswith("NPC"):
        return None

    bases = [_int_field(raw, f"effect_base_value{i}") for i in range(1, 13)]
    formulas = [_int_field(raw, f"formula{i}") for i in range(1, 13)]
    effectids = [_int_field(raw, f"effectid{i}", SE_BLANK) for i in range(1, 13)]
    classes = [int(raw[f"classes{i}"] or 255) for i in range(1, 16)]

    if all(c >= 255 for c in classes):
        return None

    resisttype = _int_field(raw, "resisttype")
    no_partial = _int_field(raw, "no_partial_resist")
    resist_diff = _int_field(raw, "ResistDiff")
    buffduration = _int_field(raw, "buffduration")
    good_effect = _int_field(raw, "goodEffect")

    partial = is_partial_capable(effectids, bases, formulas, no_partial)
    is_dd = buffduration == 0 and any(
        eid in (SE_CURRENT_HP, SE_CURRENT_HP_ONCE) and base < 0
        for eid, base in zip(effectids, bases, strict=True)
    )
    is_harmony = (
        has_effect(effectids, SE_HARMONY)
        or has_effect(effectids, SE_CHANGE_FRENZY_RAD)
        or has_effect(effectids, SE_LULL)
    )
    is_mez = has_effect(effectids, SE_MEZ)
    is_charm = has_effect(effectids, SE_CHARM)

    # Land-rate catalog: detrimental spells, lulls/harmony, and beneficial spells that check resists
    # (e.g. Nullify Magic). Skip pure beneficial buffs with no resist check.
    if good_effect == 1 and resisttype == 0 and not is_harmony:
        return None
    if good_effect == 1 and resisttype != 0 and not is_harmony:
        # Keep beneficial resistable (dispels etc.)
        pass

    return {
        "id": sid,
        "name": name,
        "resisttype": resisttype,
        "resistDiff": resist_diff,
        "noPartialResist": bool(no_partial),
        "partialCapable": partial,
        "directDamage": is_dd,
        "harmony": is_harmony,
        "mez": is_mez,
        "charm": is_charm,
        "buffduration": buffduration,
        "classes": classes,
        "effectid": effectids,
        "base": bases,
    }


def load_raw_spells(sql_files: list[Path], columns: list[str]) -> dict[int, dict[str, Any]]:
    sys.path.insert(0, str(_magelo_root() / "scripts"))
    from threat.parse_spells_en import iter_spells_en_inserts, row_dict

    by_id: dict[int, dict[str, Any]] = {}
    for p in sql_files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for inner in iter_spells_en_inserts(text):
            raw = row_dict(columns, inner)
            rid = raw.get("id")
            if rid is None:
                continue
            by_id[int(rid)] = raw
    return by_id


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-sql", nargs="*", type=Path, help="spells_en SQL files")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = _magelo_root()
    out = args.out or (root / "data" / "spells_resist.json")

    if args.server_sql:
        sql_files = list(args.server_sql)
    else:
        sroot = _server_root()
        sql_files = [
            sroot / "utils" / "sql" / "git" / "required" / "2016_11_12_spells_part1.sql",
            sroot / "utils" / "sql" / "git" / "required" / "2016_11_12_spells_part2.sql",
        ]
        if not sql_files[0].is_file():
            print("Default Server SQL not found; pass --server-sql paths.", file=sys.stderr)
            return 1

    sys.path.insert(0, str(root / "scripts"))
    from threat.parse_spells_en import load_columns_from_part1

    columns = load_columns_from_part1(sql_files[0])
    raw_spells = load_raw_spells(sql_files, columns)

    subset: dict[str, dict[str, Any]] = {}
    for sid, raw in sorted(raw_spells.items()):
        rec = spell_resist_record(raw)
        if rec is None:
            continue
        # Prefer resistable + lulls; also include resisttype 0 detrimental? filtered above
        if rec["resisttype"] == 0 and not rec["harmony"]:
            # Still include if detrimental with resisttype none (unresistable nukes etc.)
            # already filtered beneficial; keep unresistable for 100% land note
            pass
        subset[str(sid)] = rec

    payload = {
        "_meta": {
            "source": [str(p) for p in sql_files],
            "spellCount": len(subset),
            "classIndex": CLASS_INDEX,
            "resistTypes": {
                "0": "Unresistable",
                "1": "Magic",
                "2": "Fire",
                "3": "Cold",
                "4": "Poison",
                "5": "Disease",
            },
            "notes": "Compact catalog for resist_calculator.html; formulas from Server CheckResistSpell / IsPartialCapableSpell.",
        },
        "spells": subset,
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    size_kb = out.stat().st_size / 1024
    print(f"Wrote {len(subset)} spells to {out} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
