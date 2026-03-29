"""
Build data/item_spell_bonuses.json from Server spells_en + magelo data/item_stats.json.

Per-spell-id bonuses for effectSpellId / focusSpellId (worn ATK, melee haste %, FT tier).

  python scripts/build_item_spell_bonuses.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

SE_ATK = 2
SE_AttackSpeed = 11
SE_CurrentMana = 15
SE_AttackSpeed2 = 98
SE_AttackSpeed3 = 119

_FT_NAME_RE = re.compile(r"Flowing Thought\s+([IVXLCDM]+)\s*$", re.IGNORECASE)

_ROMAN_MAP: dict[str, int] = {
    "I": 1,
    "II": 2,
    "III": 3,
    "IV": 4,
    "V": 5,
    "VI": 6,
    "VII": 7,
    "VIII": 8,
    "IX": 9,
    "X": 10,
    "XI": 11,
    "XII": 12,
    "XIII": 13,
    "XIV": 14,
    "XV": 15,
}


def _magelo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Server"


def roman_tier(s: str) -> int:
    return _ROMAN_MAP.get(s.strip().upper(), 0)


def extract_ft(name: str, effectid: list[int], base: list[int]) -> int:
    n = (name or "").strip()
    low = n.lower()
    if "flowing thought" not in low:
        return 0
    ft = 0
    for i, eid in enumerate(effectid):
        if eid == SE_CurrentMana and i < len(base):
            b = int(base[i])
            if 1 <= b <= 15:
                ft += b
    if ft > 0:
        return ft
    m = _FT_NAME_RE.search(n)
    if m:
        return roman_tier(m.group(1))
    return 0


def extract_haste(effectid: list[int], base: list[int]) -> int:
    total = 0
    for i, eid in enumerate(effectid):
        if i >= len(base):
            break
        b = int(base[i])
        if eid in (SE_AttackSpeed, SE_AttackSpeed2) and b > 100:
            total += b - 100
        elif eid == SE_AttackSpeed3 and b > 0:
            total += b
    return total


def extract_atk(effectid: list[int], base: list[int]) -> int:
    s = 0
    for i, eid in enumerate(effectid):
        if eid == SE_ATK and i < len(base):
            s += int(base[i])
    return s


def spell_bonuses(rec: dict[str, Any]) -> dict[str, int]:
    name = (rec.get("name") or "").replace("\\'", "'")
    eff = rec.get("effectid") or []
    bas = rec.get("base") or []
    return {
        "atk": extract_atk(eff, bas),
        "haste": extract_haste(eff, bas),
        "ft": extract_ft(name, eff, bas),
    }


def collect_spell_ids_from_item_stats(path: Path) -> set[int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    ids: set[int] = set()
    for _k, item in data.items():
        if not isinstance(item, dict):
            continue
        for key in ("effectSpellId", "focusSpellId"):
            v = item.get(key)
            if v is None or v == "":
                continue
            try:
                ids.add(int(v))
            except (TypeError, ValueError):
                pass
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--server-sql", nargs="*", type=Path, default=None)
    ap.add_argument("--item-stats", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = _magelo_root()
    out = args.out or (root / "data" / "item_spell_bonuses.json")
    item_stats_path = args.item_stats or (root / "data" / "item_stats.json")

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
    from threat.parse_spells_en import load_columns_from_part1, load_spells_en_from_files

    columns = load_columns_from_part1(sql_files[0])
    all_spells = load_spells_en_from_files(sql_files, columns)

    want_ids = collect_spell_ids_from_item_stats(item_stats_path)
    by_id: dict[str, dict[str, int]] = {}
    missing: list[int] = []

    for sid in sorted(want_ids):
        if sid in all_spells:
            by_id[str(sid)] = spell_bonuses(all_spells[sid])
        else:
            missing.append(sid)

    payload = {
        "_meta": {
            "sourceSql": [str(p) for p in sql_files],
            "itemStats": str(item_stats_path),
            "spellCount": len(by_id),
            "missingIds": missing,
        },
        "spells": by_id,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(by_id)} spells, {len(missing)} missing)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
