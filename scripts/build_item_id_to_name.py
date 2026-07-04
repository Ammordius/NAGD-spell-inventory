#!/usr/bin/env python3
"""
Build data/item_id_to_name.json (item_id string -> display name) for char timeline and gear events.

Primary source: PEQ items table (SELECT id, name).
Overlays (fill gaps): item_stats.json, raid_item_sources.json, item_name_to_id.json,
praesterium_loot.json.
Inventory scan: Magelo TAKP_character_inventory.txt names override when non-empty.

Usage:
    python scripts/build_item_id_to_name.py
    python scripts/build_item_id_to_name.py --inventory inventory/TAKP_character_inventory.txt
    python scripts/build_item_id_to_name.py --skip-db --inventory inventory/TAKP_character_inventory.txt

Environment: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
  (defaults: localhost, eq, eq, peq, 3306)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

MAGELO_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = MAGELO_ROOT / "data" / "item_id_to_name.json"


def _db_connect():
    if not HAS_PYMYSQL:
        return None
    host = os.environ.get("DB_HOST", "localhost")
    database = os.environ.get("DB_NAME", "peq")
    port = int(os.environ.get("DB_PORT", "3306"))
    if "DB_USER" in os.environ:
        attempts = [(os.environ["DB_USER"], os.environ.get("DB_PASSWORD") or None)]
    else:
        attempts = [("eq", "eq"), ("root", None)]
    last_exc = None
    for user, password in attempts:
        try:
            kwargs = dict(
                host=host,
                user=user,
                database=database,
                port=port,
                cursorclass=pymysql.cursors.DictCursor,
            )
            if password is not None:
                kwargs["password"] = password
            return pymysql.connect(**kwargs)
        except Exception as exc:
            last_exc = exc
    if last_exc:
        print(f"Database connection failed: {last_exc}", file=sys.stderr)
    return None


def query_all_item_names(conn) -> Dict[str, str]:
    """Return all item id -> name from PEQ items table."""
    sql = "SELECT id, name FROM items WHERE name IS NOT NULL AND TRIM(name) != ''"
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: Dict[str, str] = {}
    for row in rows:
        iid = str(int(row["id"]))
        name = (row.get("name") or "").strip()
        if name:
            out[iid] = name
    return out


def merge_fill_gaps(name_map: Dict[str, str], overlay: Dict[str, str]) -> int:
    """Add overlay entries only where name_map has no name or empty name. Returns count added."""
    added = 0
    for iid, name in overlay.items():
        name = (name or "").strip()
        if not name:
            continue
        sid = str(iid)
        if not name_map.get(sid):
            name_map[sid] = name
            added += 1
    return added


def merge_override(name_map: Dict[str, str], overlay: Dict[str, str]) -> int:
    """Overlay non-empty names (inventory / Magelo display names). Returns count updated."""
    updated = 0
    for iid, name in overlay.items():
        name = (name or "").strip()
        if not name:
            continue
        sid = str(iid)
        if name_map.get(sid) != name:
            name_map[sid] = name
            updated += 1
    return updated


def load_item_stats_names(magelo_root: Path) -> Dict[str, str]:
    path = magelo_root / "data" / "item_stats.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, str] = {}
    for sid, entry in data.items():
        if isinstance(entry, dict) and entry.get("name"):
            out[str(sid)] = str(entry["name"]).strip()
    return out


def load_raid_source_names(magelo_root: Path) -> Dict[str, str]:
    path = magelo_root / "raid_item_sources.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, str] = {}
    for sid, entry in (data.items() if isinstance(data, dict) else []):
        if isinstance(entry, dict):
            name = (entry.get("name") or "").strip()
            if name:
                out[str(sid)] = name
    return out


def load_name_to_id_inverted(magelo_root: Path) -> Dict[str, str]:
    path = magelo_root / "data" / "item_name_to_id.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {str(v): k for k, v in data.items() if k and v is not None}


def load_praesterium_names(magelo_root: Path) -> Dict[str, str]:
    path = magelo_root / "praesterium_loot.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    out: Dict[str, str] = {}
    for sid, entry in (data.items() if isinstance(data, dict) else []):
        if isinstance(entry, dict) and entry.get("name"):
            out[str(sid)] = str(entry["name"]).strip()
    return out


def scan_inventory_names(inventory_path: Path) -> Dict[str, str]:
    """Scan full Magelo inventory TSV; last seen name wins per item_id."""
    if not inventory_path.is_file():
        return {}
    out: Dict[str, str] = {}
    with inventory_path.open("r", encoding="utf-8-sig") as f:
        next(f, None)  # header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                continue
            item_id = parts[2].strip()
            item_name = parts[3].strip() if len(parts) > 3 else ""
            if item_id and item_name:
                out[item_id] = item_name
    return out


def load_existing_map(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {str(k): str(v).strip() for k, v in data.items() if v}
    except (json.JSONDecodeError, OSError):
        return {}


def build_item_id_to_name(
    magelo_root: Path | None = None,
    *,
    inventory_file: Path | None = None,
    skip_db: bool = False,
    existing_path: Path | None = None,
) -> tuple[Dict[str, str], dict]:
    """Build merged id->name map. Returns (map, stats dict)."""
    root = magelo_root or MAGELO_ROOT
    out_path = existing_path or (root / "data" / "item_id_to_name.json")
    stats = {
        "from_db": 0,
        "from_existing": 0,
        "from_item_stats": 0,
        "from_raid_sources": 0,
        "from_name_to_id": 0,
        "from_praesterium": 0,
        "from_inventory": 0,
    }
    name_map: Dict[str, str] = {}

    if skip_db:
        name_map = load_existing_map(out_path)
        stats["from_existing"] = len(name_map)
    else:
        conn = _db_connect()
        if conn:
            try:
                name_map = query_all_item_names(conn)
                stats["from_db"] = len(name_map)
            finally:
                conn.close()
        elif not out_path.is_file():
            print("Warning: no DB connection and no existing item_id_to_name.json", file=sys.stderr)

    stats["from_item_stats"] = merge_fill_gaps(name_map, load_item_stats_names(root))
    stats["from_raid_sources"] = merge_fill_gaps(name_map, load_raid_source_names(root))
    stats["from_name_to_id"] = merge_fill_gaps(name_map, load_name_to_id_inverted(root))
    stats["from_praesterium"] = merge_fill_gaps(name_map, load_praesterium_names(root))

    if inventory_file:
        stats["from_inventory"] = merge_override(name_map, scan_inventory_names(inventory_file))

    return name_map, stats


def write_item_id_to_name(
    name_map: Dict[str, str],
    out_path: Path | None = None,
) -> Path:
    path = out_path or OUT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_map = {k: name_map[k] for k in sorted(name_map, key=lambda x: int(x) if x.isdigit() else x)}
    path.write_text(json.dumps(sorted_map, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    p = argparse.ArgumentParser(description="Build data/item_id_to_name.json from PEQ DB and Magelo sources")
    p.add_argument("--inventory", type=Path, default=None, help="Path to TAKP_character_inventory.txt")
    p.add_argument("--skip-db", action="store_true", help="Skip PEQ query; merge onto existing JSON (CI)")
    p.add_argument("--out", type=Path, default=OUT_PATH, help="Output JSON path")
    args = p.parse_args()

    name_map, stats = build_item_id_to_name(
        inventory_file=args.inventory,
        skip_db=args.skip_db,
        existing_path=args.out,
    )
    if not name_map:
        print("Error: no item names produced (need DB, existing file, or merge sources)", file=sys.stderr)
        return 1

    out = write_item_id_to_name(name_map, args.out)
    print(f"Wrote {out} ({len(name_map)} entries)")
    for key, val in stats.items():
        if val:
            print(f"  {key}: {val}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
