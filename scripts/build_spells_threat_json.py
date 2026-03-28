"""
Build data/spells_threat.json from Server SQL dumps (spells_en).

Default inputs: Server/utils/sql/git/required/2016_11_12_spells_part1.sql + part2.sql
Also includes spell IDs referenced by magelo data/item_stats.json proc weapons.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _magelo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _server_root() -> Path:
    return Path(__file__).resolve().parents[2] / "Server"


def normalize_name(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    return " ".join(s.strip().lower().split())


def collect_spell_ids_from_item_stats(item_stats_path: Path, weapon_proc_keys: set[str]) -> set[int]:
    data = json.loads(item_stats_path.read_text(encoding="utf-8"))
    ids: set[int] = set()
    for _item_id, item in data.items():
        name = normalize_name(item.get("name") or "")
        if name not in weapon_proc_keys:
            continue
        sid = item.get("effectSpellId")
        if sid is not None:
            try:
                ids.add(int(sid))
            except (TypeError, ValueError):
                pass
    return ids


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--server-sql",
        nargs="*",
        type=Path,
        help="spells_en SQL files (default: TAKP/Server utils required part1+part2)",
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--weapon-procs", type=Path, default=None)
    ap.add_argument("--item-stats", type=Path, default=None)
    args = ap.parse_args()

    root = _magelo_root()
    out = args.out or (root / "data" / "spells_threat.json")
    weapon_procs_path = args.weapon_procs or (root / "data" / "weapon_procs.json")
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

    proc_keys = set(json.loads(weapon_procs_path.read_text(encoding="utf-8")).keys())
    want_ids = collect_spell_ids_from_item_stats(item_stats_path, proc_keys)
    # regression / edge cases
    want_ids.update({2675, 22, 88, 1933, 1935})

    subset = {}
    missing = []
    for sid in sorted(want_ids):
        if sid in all_spells:
            subset[str(sid)] = all_spells[sid]
        else:
            missing.append(sid)

    payload = {
        "_meta": {
            "source": [str(p) for p in sql_files],
            "spellCount": len(subset),
            "missingIds": missing,
        },
        "spells": subset,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({len(subset)} spells, {len(missing)} missing)")
    return 0 if not missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
