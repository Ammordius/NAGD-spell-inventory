#!/usr/bin/env python3
"""
1) Classify every item in items_seen.json to the mob(s) that drop it (from DB + raid_item_sources).
2) Build a compact per-mob loot list: for each mob that drops at least one DKP item, list all their
   drops that are in items_seen (DKP) OR in raid_item_sources for that mob. Use this when you kill
   a mob for DKP to quickly select from their possible loot.

Usage:
    python build_dkp_mob_loot.py [database_connection_string]

Environment: DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT
  (defaults: localhost, root, no password, peq, 3306)

Outputs:
    items_seen_to_mobs.json  - each items_seen item name -> list of { mob, zone } that drop it
    dkp_mob_loot.json       - each DKP mob -> { mob, zone, loot: [...], respawn_seconds? }
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

SCRIPT_DIR = Path(__file__).resolve().parent


def normalize_zone(s: str) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    s = re.sub(r"^the\s+", "", s)
    s = s.replace("vex thall", "vex thal").replace("ssraeshza", "ssra")
    return s


def strip_mob(mob: str) -> str:
    if not mob:
        return ""
    return mob.lstrip("#").strip()


def normalize_mob_for_db(mob: str) -> str:
    """Normalize mob name for DB matching so Vulak`Aerr and Vulak'Aerr match (backtick vs apostrophe)."""
    if not mob:
        return ""
    return mob.replace("`", "'").strip()


def query_item_ids_by_names(conn, names: List[str]) -> Set[int]:
    if not names:
        return set()
    seen: Set[int] = set()
    batch_size = 500
    for i in range(0, len(names), batch_size):
        batch = names[i : i + batch_size]
        normalized = [n.strip().lower() for n in batch]
        placeholders = ",".join(["%s"] * len(normalized))
        sql = f"SELECT id FROM items WHERE LOWER(TRIM(name)) IN ({placeholders})"
        with conn.cursor() as cur:
            cur.execute(sql, normalized)
            for row in cur.fetchall():
                seen.add(int(row["id"]))
    return seen


def query_item_id_to_name(conn, item_ids: Set[int]) -> Dict[int, str]:
    """Return item_id -> item name for given ids."""
    if not item_ids:
        return {}
    ids_list = list(item_ids)
    placeholders = ",".join(["%s"] * len(ids_list))
    sql = f"SELECT id, name FROM items WHERE id IN ({placeholders})"
    with conn.cursor() as cur:
        cur.execute(sql, ids_list)
        rows = cur.fetchall()
    return {int(row["id"]): (row["name"] or "").strip() for row in rows}


def query_item_droppers(conn, item_ids: List[int]) -> Dict[int, List[Tuple[str, str]]]:
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
    result: Dict[int, List[Tuple[str, str]]] = {}
    for row in rows:
        item_id = int(row["item_id"])
        npc = (row["npc_name"] or "").strip()
        zone = (row["zone_long_name"] or "").strip()
        if item_id not in result:
            result[item_id] = []
        entry = (npc, zone)
        if entry not in result[item_id]:
            result[item_id].append(entry)
    return result


def query_npc_ids_for_mobs(conn, norm_keys: Set[Tuple[str, str]]) -> Set[int]:
    if not norm_keys:
        return set()
    sql = """
    SELECT DISTINCT
        nt.id,
        nt.name AS npc_name,
        COALESCE(NULLIF(TRIM(z.long_name), ''), s2.zone, '') AS zone_long_name
    FROM npc_types nt
    LEFT JOIN spawnentry se ON se.npcID = nt.id
    LEFT JOIN spawngroup sg ON sg.id = se.spawngroupID
    LEFT JOIN spawn2 s2 ON s2.spawngroupID = sg.id
    LEFT JOIN zone z ON z.short_name = s2.zone
    WHERE nt.loottable_id > 0
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    our_norm = set((normalize_mob_for_db(npc), normalize_zone(z) if z else "") for npc, z in norm_keys)
    ids: Set[int] = set()
    for row in rows:
        npc = (row["npc_name"] or "").strip()
        zone_raw = (row["zone_long_name"] or "").strip()
        zone_n = normalize_zone(zone_raw) if zone_raw else ""
        if (normalize_mob_for_db(npc), zone_n) in our_norm:
            ids.add(int(row["id"]))
    return ids


def query_drops_by_npc_ids(
    conn, npc_ids: Set[int]
) -> Dict[Tuple[str, str], List[Tuple[int, str]]]:
    if not npc_ids:
        return {}
    ids_list = list(npc_ids)
    placeholders = ",".join(["%s"] * len(ids_list))
    sql = f"""
    SELECT DISTINCT
        nt.id AS npc_id,
        nt.name AS npc_name,
        COALESCE(NULLIF(TRIM(z.long_name), ''), s2.zone, '') AS zone_long_name,
        lde.item_id,
        i.name AS item_name
    FROM npc_types nt
    JOIN loottable_entries lte ON lte.loottable_id = nt.loottable_id
    JOIN lootdrop_entries lde ON lde.lootdrop_id = lte.lootdrop_id
    JOIN items i ON i.id = lde.item_id
    LEFT JOIN spawnentry se ON se.npcID = nt.id
    LEFT JOIN spawngroup sg ON sg.id = se.spawngroupID
    LEFT JOIN spawn2 s2 ON s2.spawngroupID = sg.id
    LEFT JOIN zone z ON z.short_name = s2.zone
    WHERE nt.id IN ({placeholders})
    ORDER BY nt.name, zone_long_name, lde.item_id
    """
    with conn.cursor() as cur:
        cur.execute(sql, ids_list)
        rows = cur.fetchall()
    result: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
    for row in rows:
        npc = (row["npc_name"] or "").strip()
        zone = (row["zone_long_name"] or "").strip()
        key = (normalize_mob_for_db(npc), normalize_zone(zone))
        item_id = int(row["item_id"])
        item_name = (row["item_name"] or "").strip()
        if key not in result:
            result[key] = []
        if not any(x[0] == item_id for x in result[key]):
            result[key].append((item_id, item_name))
    return result


def query_respawn_for_mobs(conn, mob_zone_pairs: List[Tuple[str, str]]) -> Dict[Tuple[str, str], int]:
    if not mob_zone_pairs:
        return {}
    keys = set((normalize_mob_for_db(strip_mob(m)), normalize_zone(z)) for m, z in mob_zone_pairs)
    zone_expr = "COALESCE(NULLIF(TRIM(z.long_name), ''), s2.zone, '')"
    sql = f"""
    SELECT
        nt.name AS npc_name,
        {zone_expr} AS zone_long_name,
        MAX(COALESCE(s2.respawntime, 0)) AS respawn_seconds
    FROM npc_types nt
    LEFT JOIN spawnentry se ON se.npcID = nt.id
    LEFT JOIN spawngroup sg ON sg.id = se.spawngroupID
    LEFT JOIN spawn2 s2 ON s2.spawngroupID = sg.id
    LEFT JOIN zone z ON z.short_name = s2.zone
    WHERE s2.respawntime IS NOT NULL AND s2.respawntime > 0
    GROUP BY nt.name, {zone_expr}
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()
    out: Dict[Tuple[str, str], int] = {}
    for row in rows:
        npc = (row["npc_name"] or "").strip()
        zone = (row["zone_long_name"] or "").strip()
        key = (normalize_mob_for_db(npc), normalize_zone(zone))
        if key in keys:
            sec = int(row["respawn_seconds"] or 0)
            if sec > 0:
                out[key] = max(out.get(key, 0), sec)
    return out


def main() -> None:
    raid_sources_path = SCRIPT_DIR / "raid_item_sources.json"
    items_seen_path = SCRIPT_DIR / "items_seen.json"
    elemental_path = SCRIPT_DIR / "elemental_armor.json"
    classification_path = SCRIPT_DIR / "raid_loot_classification.json"
    out_class_path = SCRIPT_DIR / "items_seen_to_mobs.json"
    out_loot_path = SCRIPT_DIR / "dkp_mob_loot.json"

    for p in (raid_sources_path, items_seen_path):
        if not p.exists():
            print(f"Error: {p.name} not found.")
            sys.exit(1)

    raid_sources: Dict[str, Any] = json.loads(raid_sources_path.read_text(encoding="utf-8"))
    items_seen: List[str] = json.loads(items_seen_path.read_text(encoding="utf-8"))
    elemental_armor: Dict[str, Any] = {}
    if elemental_path.exists():
        elemental_armor = json.loads(elemental_path.read_text(encoding="utf-8"))

    dkp_item_ids: Set[int] = set()
    if not HAS_PYMYSQL:
        print("Error: pymysql required. pip install pymysql")
        sys.exit(1)

    db_host = os.environ.get("DB_HOST", "localhost")
    db_user = os.environ.get("DB_USER", "root")
    db_password = os.environ.get("DB_PASSWORD", "")
    db_name = os.environ.get("DB_NAME", "peq")
    db_port = int(os.environ.get("DB_PORT", "3306"))
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if "=" in arg or ":" in arg:
            for part in re.split(r"[,;]|\s+", arg):
                if "=" in part:
                    k, v = part.split("=", 1)
                    k, v = k.strip().lower(), v.strip()
                    if k in ("host", "user", "password", "database", "db", "name"):
                        if k in ("name", "db"):
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
        sys.exit(1)

    # DKP item IDs and id -> name
    print("Resolving items_seen to item IDs...")
    dkp_item_ids = query_item_ids_by_names(conn, items_seen)
    print(f"  {len(dkp_item_ids)} item IDs matched.")
    id_to_name = query_item_id_to_name(conn, dkp_item_ids)

    # item_id -> list of (mob, zone): from DB and from raid_item_sources
    print("Getting droppers for DKP items from DB...")
    db_droppers = query_item_droppers(conn, list(dkp_item_ids))
    item_id_to_mobs: Dict[int, List[Tuple[str, str]]] = {}
    for iid in dkp_item_ids:
        mobs = list(db_droppers.get(iid, []))
        if str(iid) in raid_sources:
            ent = raid_sources[str(iid)]
            m, z = (ent.get("mob") or "").strip(), (ent.get("zone") or "").strip()
            if (m, z) not in mobs:
                mobs.append((m, z))
        item_id_to_mobs[iid] = mobs

    # name -> list of { mob, zone } (use first display form per normalized name from items_seen)
    seen_normalized: Set[str] = set()
    name_to_display: Dict[str, str] = {}
    for name in items_seen:
        n = name.strip().lower()
        if n not in seen_normalized:
            seen_normalized.add(n)
            name_to_display[n] = name.strip()
    # Build name -> mobs: for each id in dkp_item_ids, its name (from id_to_name) maps to its mobs
    name_to_mobs: Dict[str, List[Dict[str, str]]] = {}
    for iid, mob_list in item_id_to_mobs.items():
        display_name = id_to_name.get(iid, "").strip()
        if not display_name:
            continue
        n = display_name.lower()
        key = name_to_display.get(n, display_name)
        if key not in name_to_mobs:
            name_to_mobs[key] = []
        added = set()
        for mob, zone in mob_list:
            if (mob, zone) not in added:
                added.add((mob, zone))
                name_to_mobs[key].append({"mob": mob, "zone": zone})
    # Ensure every items_seen display name has an entry (even if no mobs)
    for name in items_seen:
        n = name.strip().lower()
        key = name_to_display.get(n, name.strip())
        if key not in name_to_mobs:
            name_to_mobs[key] = []

    # Elemental armor: only items that are actually dropped (patterns/molds); add their droppers to classification and mob list
    elemental_dropped_ids: Set[int] = set()
    elem_droppers: Dict[int, List[Tuple[str, str]]] = {}
    if elemental_armor:
        elemental_ids = [int(k) for k in elemental_armor.keys()]
        print("Querying which elemental armor items are dropped by mobs (patterns/molds)...")
        elem_droppers = query_item_droppers(conn, elemental_ids)
        elemental_dropped_ids = {iid for iid in elemental_ids if elem_droppers.get(iid)}
        print(f"  {len(elemental_dropped_ids)} elemental items are dropped (patterns/molds); rest are crafted only.")
        if elemental_dropped_ids:
            elem_id_to_name = query_item_id_to_name(conn, elemental_dropped_ids)
            for iid in elemental_dropped_ids:
                mob_list = elem_droppers.get(iid, [])
                name = (elem_id_to_name.get(iid) or "").strip()
                if not name:
                    continue
                if name not in name_to_mobs:
                    name_to_mobs[name] = []
                existing = {(x["mob"], x["zone"]) for x in name_to_mobs[name]}
                for m, z in mob_list:
                    if (m, z) not in existing:
                        existing.add((m, z))
                        name_to_mobs[name].append({"mob": m, "zone": z})

    # Raid classification overrides (e.g. Plane of Time P1/P3): one entry per phase instead of per boss; aliases for typo matching
    if classification_path.exists():
        classification_data = json.loads(classification_path.read_text(encoding="utf-8"))
        classifications = classification_data.get("classifications") or {}
        aliases = classification_data.get("aliases") or {}
        for canonical, entry in classifications.items():
            if isinstance(entry, dict) and "mob" in entry:
                name_to_mobs[canonical] = [{"mob": entry["mob"], "zone": entry.get("zone", "")}]
        for alias_name, canonical in aliases.items():
            if canonical in classifications and isinstance(classifications[canonical], dict):
                name_to_mobs[alias_name] = [{"mob": classifications[canonical]["mob"], "zone": classifications[canonical].get("zone", "")}]

    # Every items_seen name (first occurrence per normalized name) -> list of mobs; include empty list if no droppers
    out_class: Dict[str, List[Dict[str, str]]] = {}
    for display_name in name_to_display.values():
        out_class[display_name] = name_to_mobs.get(display_name, [])
    # Add elemental dropped item names that aren't in items_seen
    for name, mobs in name_to_mobs.items():
        if name not in out_class:
            out_class[name] = mobs
    out_class_path.write_text(
        json.dumps(out_class, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(out_class)} items to {out_class_path.name}.")

    # DKP mobs = (mob, zone) that drop at least one DKP item OR at least one dropped elemental (pattern)
    dkp_mobs_set: Set[Tuple[str, str]] = set()
    for mob_list in item_id_to_mobs.values():
        for m, z in mob_list:
            dkp_mobs_set.add((m, z))
    if elemental_armor and elemental_dropped_ids:
        for iid in elemental_dropped_ids:
            for m, z in elem_droppers.get(iid, []):
                dkp_mobs_set.add((m, z))
    dkp_mobs_list = sorted(dkp_mobs_set, key=lambda x: (x[1], x[0]))
    print(f"Found {len(dkp_mobs_list)} mobs that drop at least one DKP item or elemental pattern.")

    # For each DKP mob: raid_item_sources item_ids for this (mob, zone)
    mob_to_raid_item_ids: Dict[Tuple[str, str], Set[int]] = {}
    all_raid_item_ids: Set[int] = set()
    for item_id_str, ent in raid_sources.items():
        m = (ent.get("mob") or "").strip()
        z = (ent.get("zone") or "").strip()
        key = (m, z)
        if key not in mob_to_raid_item_ids:
            mob_to_raid_item_ids[key] = set()
        iid = int(item_id_str)
        mob_to_raid_item_ids[key].add(iid)
        all_raid_item_ids.add(iid)

    # Item names for raid_item_sources (so we can show loot when DB has no drops for this mob, e.g. Vulak`Aerr name mismatch)
    raid_id_to_name = query_item_id_to_name(conn, all_raid_item_ids) if all_raid_item_ids else {}

    # Normalized (strip_mob, normalize_zone) -> original (mob, zone) for output
    norm_to_orig: Dict[Tuple[str, str], Tuple[str, str]] = {}
    for mob, zone in dkp_mobs_list:
        nk = (strip_mob(mob), normalize_zone(zone))
        if nk not in norm_to_orig:
            norm_to_orig[nk] = (mob, zone)

    norm_keys = set(norm_to_orig.keys())
    print("Finding NPC IDs for DKP mobs...")
    npc_ids = query_npc_ids_for_mobs(conn, norm_keys)
    print("Querying drops for those NPCs...")
    drops_by_npc_zone = query_drops_by_npc_ids(conn, npc_ids)
    respawn_map = query_respawn_for_mobs(conn, dkp_mobs_list)
    conn.close()

    # Build dkp_mob_loot: for each DKP mob, loot = drops in dkp_item_ids OR raid_item_sources for this mob OR dropped elemental (patterns)
    result: Dict[str, Any] = {}
    for mob, zone in dkp_mobs_list:
        norm_key = (normalize_mob_for_db(strip_mob(mob)), normalize_zone(zone))
        raid_ids = mob_to_raid_item_ids.get((mob, zone), set())
        db_drops = drops_by_npc_zone.get(norm_key, [])
        loot: List[Dict[str, Any]] = []
        for item_id, item_name in db_drops:
            if item_id not in dkp_item_ids and item_id not in raid_ids and item_id not in elemental_dropped_ids:
                continue
            sources = []
            if item_id in dkp_item_ids:
                sources.append("dkp")
            if item_id in raid_ids:
                sources.append("raid_item_sources")
            if item_id in elemental_dropped_ids:
                sources.append("elemental_armor")
            loot.append({"item_id": item_id, "name": item_name, "sources": sources})
        # Include raid_item_sources items even when DB returned no drops (e.g. NPC name mismatch like Vulak`Aerr)
        for item_id in raid_ids:
            if any(x["item_id"] == item_id for x in loot):
                continue
            name = id_to_name.get(item_id) or raid_id_to_name.get(item_id) or f"Item {item_id}"
            loot.append({"item_id": item_id, "name": name, "sources": ["raid_item_sources"]})
        loot.sort(key=lambda x: (x["name"], x["item_id"] or 0))
        out_key = f"{mob}|{zone}"
        entry = {"mob": mob, "zone": zone, "loot": loot}
        if norm_key in respawn_map:
            entry["respawn_seconds"] = respawn_map[norm_key]
        result[out_key] = entry

    # Add synthetic Plane of Time phase entries (P1, P3, P3 Guardian) from raid_loot_classification
    if classification_path.exists():
        classification_data = json.loads(classification_path.read_text(encoding="utf-8"))
        classifications = classification_data.get("classifications") or {}
        phase_to_items: Dict[Tuple[str, str], List[str]] = {}
        for item_name, entry in classifications.items():
            if isinstance(entry, dict) and "mob" in entry:
                key = (entry["mob"], entry.get("zone", ""))
                phase_to_items.setdefault(key, []).append(item_name)
        for (mob, zone), item_names in phase_to_items.items():
            out_key = f"{mob}|{zone}"
            if out_key not in result:
                result[out_key] = {"mob": mob, "zone": zone, "loot": []}
            existing_names = {x["name"] for x in result[out_key]["loot"]}
            for name in sorted(item_names):
                if name not in existing_names:
                    result[out_key]["loot"].append({"item_id": None, "name": name, "sources": ["raid_classification"]})
                    existing_names.add(name)
            result[out_key]["loot"].sort(key=lambda x: (x["name"] or "", x["item_id"] or 0))

    # Only include mobs that have at least one loot item (compact list for selecting at kill time)
    result = {k: v for k, v in result.items() if v["loot"]}
    out_loot_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Wrote {len(result)} DKP mobs with loot to {out_loot_path.name}.")


if __name__ == "__main__":
    main()
