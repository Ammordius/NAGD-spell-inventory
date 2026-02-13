#!/usr/bin/env python3
"""
Cross-reference raid_item_sources.json with the TAKP/PEQ SQL database to correct
mob (and zone) names and add respawn data. Queries loottable -> spawn2.respawntime
for DB respawn; applies known overrides for triggered/script-based repops.

Usage:
    python update_raid_item_sources_from_db.py [database_connection_string]
    python update_raid_item_sources_from_db.py --from-file droppers.json   # use exported data (no respawn)

Environment: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT (defaults: localhost, root, no password, peq, 3306)

Output: Updates raid_item_sources.json in place. Adds respawn_seconds (from DB) and respawn_note (override).
Use --dry-run to print changes without writing.

Export format for --from-file: JSON array of {"item_id": N, "npc_name": "...", "zone_long_name": "..."}.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

SCRIPT_DIR = Path(__file__).resolve().parent
JSON_PATH = SCRIPT_DIR / "raid_item_sources.json"

# Zone name normalization for matching JSON zone to DB long_name
def normalize_zone(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"^the\s+", "", s)
    # Common variants
    s = s.replace("vex thall", "vex thal").replace("ssraeshza", "ssra")
    return s


def query_item_droppers(conn, item_ids: list[int]) -> dict[int, list[tuple[str, str]]]:
    """Return { item_id: [(npc_name, zone_long_name), ...], ... }."""
    if not item_ids:
        return {}
    placeholders = ",".join(["%s"] * len(item_ids))
    sql = f"""
    SELECT DISTINCT
        lde.item_id,
        nt.name AS npc_name,
        COALESCE(NULLIF(TRIM(z.long_name), ''), s2.zone, '') AS zone_long_name
    FROM lootdrop_entries lde
    JOIN loottable_entries lte ON lte.lootdrop_id = lde.lootdrop_id
    JOIN loottable lt ON lt.id = lte.loottable_id
    JOIN npc_types nt ON nt.loottable_id = lt.id
    LEFT JOIN spawnentry se ON se.npcID = nt.id
    LEFT JOIN spawngroup sg ON sg.id = se.spawngroupID
    LEFT JOIN spawn2 s2 ON s2.spawngroupID = sg.id
    LEFT JOIN zone z ON z.short_name = s2.zone
    WHERE lde.item_id IN ({placeholders})
    ORDER BY lde.item_id, zone_long_name, nt.name
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(item_ids))
        rows = cur.fetchall()
    result: dict[int, list[tuple[str, str]]] = {}
    for row in rows:
        item_id = row["item_id"]
        npc = (row["npc_name"] or "").strip()
        zone = (row["zone_long_name"] or "").strip()
        if item_id not in result:
            result[item_id] = []
        entry = (npc, zone)
        if entry not in result[item_id]:
            result[item_id].append(entry)
    return result


def pick_best_dropper(
    candidates: list[tuple[str, str]],
    current_mob: str,
    current_zone: str,
) -> tuple[str, str] | None:
    """Choose best (npc_name, zone) from DB candidates. Prefer zone match, then current mob match."""
    if not candidates:
        return None
    curr_zone_n = normalize_zone(current_zone)
    curr_mob = (current_mob or "").strip()

    # Prefer exact (mob, zone) match
    for npc, zone in candidates:
        if normalize_zone(zone) == curr_zone_n and (npc == curr_mob or not curr_mob):
            return (npc, zone)

    # Prefer zone match (any mob in same zone)
    for npc, zone in candidates:
        if normalize_zone(zone) == curr_zone_n:
            return (npc, zone)

    # Prefer named over generic "trash" when multiple in same zone
    trash_like = ("trash", "eom trash", "trash mob")
    def is_trash(name: str) -> bool:
        return name.lower() in trash_like or "trash" in name.lower()

    named = [(n, z) for n, z in candidates if not is_trash(n)]
    if named:
        # Same zone preferred
        for npc, zone in named:
            if normalize_zone(zone) == curr_zone_n:
                return (npc, zone)
        return named[0]

    # Any candidate
    return candidates[0]


def query_respawn_by_dropper(conn, item_ids: List[int]) -> Dict[Tuple[str, str], int]:
    """Return (npc_name, zone_long_name) -> max respawntime in seconds for NPCs that drop these items."""
    if not item_ids:
        return {}
    placeholders = ",".join(["%s"] * len(item_ids))
    zone_expr = "COALESCE(NULLIF(TRIM(z.long_name), ''), s2.zone, '')"
    sql = f"""
    SELECT
        nt.name AS npc_name,
        {zone_expr} AS zone_long_name,
        MAX(COALESCE(s2.respawntime, 0)) AS respawn_seconds
    FROM lootdrop_entries lde
    JOIN loottable_entries lte ON lte.lootdrop_id = lde.lootdrop_id
    JOIN loottable lt ON lt.id = lte.loottable_id
    JOIN npc_types nt ON nt.loottable_id = lt.id
    LEFT JOIN spawnentry se ON se.npcID = nt.id
    LEFT JOIN spawngroup sg ON sg.id = se.spawngroupID
    LEFT JOIN spawn2 s2 ON s2.spawngroupID = sg.id
    LEFT JOIN zone z ON z.short_name = s2.zone
    WHERE lde.item_id IN ({placeholders})
      AND s2.respawntime IS NOT NULL AND s2.respawntime > 0
    GROUP BY nt.name, {zone_expr}
    """
    with conn.cursor() as cur:
        cur.execute(sql, tuple(item_ids))
        rows = cur.fetchall()
    result: Dict[Tuple[str, str], int] = {}
    for row in rows:
        npc = (row["npc_name"] or "").strip()
        zone = (row["zone_long_name"] or "").strip()
        sec = int(row["respawn_seconds"] or 0)
        if sec > 0:
            key = (npc, zone)
            result[key] = max(result.get(key, 0), sec)
    return result


# Respawn overrides for triggered/script mobs (applied after DB respawn).
# zone_norm: normalize_zone(zone) must match. mob_contains: mob name must contain this (or any if "").
# mob_excludes: if set, do not apply override when mob contains this (e.g. exclude Xegony in Po Air).
# If respawn_seconds is set, use that value; otherwise set respawn_note and clear respawn_seconds.
RESPAWN_OVERRIDES: List[dict] = [
    {"zone_norm": "temple of ssra", "mob_contains": "Emperor", "respawn_note": "7 day (blood)"},
    {"zone_norm": "temple of ssra", "mob_contains": "Cursed", "respawn_note": "Script: 6.5±0.5 days"},
    {"zone_norm": "plane of earth", "mob_contains": "", "respawn_note": "Minis triggered by rings: 3.5±0.5 days"},
    {"zone_norm": "plane of air", "mob_contains": "", "mob_excludes": "Xegony", "respawn_note": "3.5±0.5 days (triggered)"},
    {"zone_norm": "kael drakkel", "mob_contains": "Statue", "respawn_note": "Triggers Avatar of War"},
    {"zone_norm": "plane of time", "mob_contains": "", "respawn_note": "Triggered/script (not tracked)"},
    {"zone_norm": "vex thal", "mob_contains": "Thall_Va_Xakra", "respawn_seconds": 259200},
]


def apply_respawn_overrides(entry: dict) -> None:
    """If (zone, mob) matches an override, set respawn_note/respawn_seconds as specified."""
    zone = entry.get("zone") or ""
    mob = entry.get("mob") or ""
    zone_n = normalize_zone(zone)
    for ov in RESPAWN_OVERRIDES:
        if zone_n != ov["zone_norm"]:
            continue
        if ov.get("mob_excludes") and ov["mob_excludes"] in mob:
            continue
        if ov["mob_contains"] and ov["mob_contains"] not in mob:
            continue
        if "respawn_seconds" in ov:
            entry["respawn_seconds"] = ov["respawn_seconds"]
        else:
            entry["respawn_note"] = ov["respawn_note"]
            entry["respawn_seconds"] = None
        return


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Update raid item sources from DB or --from-file.")
    parser.add_argument("--input", "-i", type=Path, default=None, help="Input JSON path (default: raid_item_sources.json)")
    parser.add_argument("--output", "-o", type=Path, default=None, help="Output JSON path (default: same as input)")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    parser.add_argument("--no-respawn-update", action="store_true", help="Only update mob/zone; do not touch respawn_seconds/respawn_note (use after reset to preserve repop data)")
    parser.add_argument("conn_or_file", nargs="*", help="DB connection string or --from-file <path>")
    args, rest = parser.parse_known_args()
    # Re-inject for legacy --from-file handling
    sys.argv = [sys.argv[0]] + (["--from-file", rest[1]] if "--from-file" in rest and len(rest) > 1 else rest)

    dry_run = args.dry_run
    no_respawn_update = getattr(args, "no_respawn_update", False)
    json_path = args.input if args.input is not None else JSON_PATH
    if not json_path.is_absolute():
        json_path = SCRIPT_DIR / json_path
    out_path = args.output if args.output is not None else json_path
    if not out_path.is_absolute():
        out_path = SCRIPT_DIR / out_path

    if not json_path.exists():
        print(f"Error: {json_path} not found.")
        sys.exit(1)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    item_ids = [int(k) for k in data.keys()]
    print(f"Loaded {len(item_ids)} items from {json_path.name}")

    from_file = None
    if "--from-file" in sys.argv:
        idx = sys.argv.index("--from-file")
        if idx + 1 < len(sys.argv):
            from_file = Path(sys.argv[idx + 1])
        sys.argv = [a for i, a in enumerate(sys.argv) if i != idx and i != idx + 1]

    if from_file:
        if not from_file.is_absolute():
            from_file = SCRIPT_DIR / from_file
        if not from_file.exists():
            print(f"Error: file not found: {from_file}")
            sys.exit(1)
        print(f"Loading droppers from {from_file}...")
        try:
            raw = json.loads(from_file.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Error loading file: {e}")
            sys.exit(1)
        if isinstance(raw, list):
            droppers = {}
            for row in raw:
                iid = row.get("item_id")
                if iid is None:
                    continue
                iid = int(iid)
                npc = (row.get("npc_name") or "").strip()
                zone = (row.get("zone_long_name") or "").strip()
                if iid not in droppers:
                    droppers[iid] = []
                entry = (npc, zone)
                if entry not in droppers[iid]:
                    droppers[iid].append(entry)
        else:
            print("Expected JSON array of {item_id, npc_name, zone_long_name}")
            sys.exit(1)
        found_count = len(droppers)
        no_drop = [iid for iid in item_ids if iid not in droppers]
        if no_drop:
            print(f"  {len(no_drop)} item(s) have no dropper in file.")
        respawn_map = {}
    else:
        if not HAS_PYMYSQL:
            print("Warning: pymysql not installed. Install with: pip install pymysql")
            print("No database query performed. Exiting.")
            sys.exit(1)

        db_host = os.environ.get("DB_HOST", "localhost")
        db_user = os.environ.get("DB_USER", "root")
        db_password = os.environ.get("DB_PASSWORD", "")  # no password by default
        db_name = os.environ.get("DB_NAME", "peq")
        db_port = int(os.environ.get("DB_PORT", "3306"))

        if len(sys.argv) > 1:
            arg = sys.argv[1]
            if "=" in arg or ":" in arg:
                # Parse connection string (e.g. user=eq:password=eq:host=localhost:database=peq)
                for part in re.split(r"[,;]|\s+", arg):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k in ("host", "user", "password", "database", "db", "name"):
                            if k == "name" or k == "db":
                                db_name = v
                            elif k == "host":
                                db_host = v
                            elif k == "user":
                                db_user = v
                            elif k == "password":
                                db_password = v
                        if "port" in k:
                            db_port = int(v)

        try:
            conn = pymysql.connect(
                host=db_host,
                user=db_user,
                password=db_password,
                database=db_name,
                port=db_port,
                cursorclass=pymysql.cursors.DictCursor,
            )
        except Exception as e:
            print(f"Database connection failed: {e}")
            print("Tip: install cryptography for MySQL 8 auth: pip install cryptography")
            print("Or export droppers to JSON and run: python update_raid_item_sources_from_db.py --from-file droppers.json")
            sys.exit(1)

        print(f"Querying {db_name}@{db_host} for droppers of {len(item_ids)} items...")
        droppers = query_item_droppers(conn, item_ids)
        print(f"Querying respawn (spawn2.respawntime) for same items...")
        respawn_map = query_respawn_by_dropper(conn, item_ids)
        conn.close()
        print(f"  Respawn data for {len(respawn_map)} (npc, zone) pairs.")

        found_count = len(droppers)
        no_drop = [iid for iid in item_ids if iid not in droppers]
        if no_drop:
            print(f"  {len(no_drop)} item(s) have no dropper in DB (loot/spawn): {no_drop[:20]}{'...' if len(no_drop) > 20 else ''}")

    updates: list[tuple[str, str, str, str, str]] = []  # id, old_mob, new_mob, old_zone, new_zone
    for item_id_str, entry in data.items():
        item_id = int(item_id_str)
        current_mob = entry.get("mob", "")
        current_zone = entry.get("zone", "")
        candidates = droppers.get(item_id, [])
        best = pick_best_dropper(candidates, current_mob, current_zone)
        if best is None:
            continue
        new_mob, new_zone = best
        # DB may return Eom_Thall (placeholder); actual mob is Thall Va Xakra (npcid 158136), 3 day
        if new_mob == "Eom_Thall" and normalize_zone(new_zone or "") == "vex thal":
            new_mob = "Thall_Va_Xakra"
        if new_mob != current_mob or (new_zone and new_zone != current_zone):
            updates.append((item_id_str, current_mob, new_mob, current_zone, new_zone))
            entry["mob"] = new_mob
            if new_zone:
                entry["zone"] = new_zone

    # Populate respawn_seconds from DB and apply overrides (unless --no-respawn-update to preserve post-reset data)
    respawn_filled = 0
    override_applied = 0
    if not no_respawn_update:
        for entry in data.values():
            mob = entry.get("mob") or ""
            zone = entry.get("zone") or ""
            if not zone and not mob:
                continue
            key = (mob, zone)
            if key in respawn_map:
                entry["respawn_seconds"] = respawn_map[key]
                respawn_filled += 1
            had_note = "respawn_note" in entry
            apply_respawn_overrides(entry)
            if "respawn_note" in entry and not had_note:
                override_applied += 1

    print(f"Updates: {len(updates)} entries corrected from database.")
    for item_id_str, old_mob, new_mob, old_zone, new_zone in updates[:30]:
        mob_ch = f"mob: {old_mob!r} -> {new_mob!r}" if old_mob != new_mob else ""
        zone_ch = f"zone: {old_zone!r} -> {new_zone!r}" if new_zone and old_zone != new_zone else ""
        print(f"  {item_id_str}: {mob_ch} {zone_ch}")
    if len(updates) > 30:
        print(f"  ... and {len(updates) - 30} more")
    if respawn_map and not no_respawn_update:
        print(f"Respawn: {respawn_filled} entries with DB respawn_seconds; {override_applied} with respawn_note/value override.")
    if no_respawn_update:
        print("Respawn: skipped (--no-respawn-update); existing respawn data preserved.")

    if dry_run:
        print("Dry run: no file written.")
        return

    if updates or respawn_filled or override_applied:
        out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"Wrote {out_path}")
    else:
        print("No changes to write.")


if __name__ == "__main__":
    main()
