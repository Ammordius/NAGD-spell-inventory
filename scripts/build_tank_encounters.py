#!/usr/bin/env python3
"""Build data/tank_encounters.json from raid loot mobs and the Zeal NPC export.

Only mobs named in raid_item_sources.json are included. Names that are not a
single NPC, and names with no Zeal row, are listed and not invented.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZEAL_NPC = Path(r"C:\TAKP\Zeal\Zeal\uifiles\zeal\npc_info")
SOURCES = ROOT / "raid_item_sources.json"
OUT = ROOT / "data" / "tank_encounters.json"

SKIP_FILES = {
    "items.json",
    "factions.json",
    "item_sources.json",
    "spells.json",
    "level_exp_mods.json",
}

CLASS_NAMES = {
    1: "Warrior",
    2: "Cleric",
    3: "Paladin",
    4: "Ranger",
    5: "Shadow Knight",
    6: "Druid",
    7: "Monk",
    8: "Bard",
    9: "Rogue",
    10: "Shaman",
    11: "Necromancer",
    12: "Wizard",
    13: "Magician",
    14: "Enchanter",
    15: "Beastlord",
}

SA_RAMPAGE = 3
SA_AREA_RAMPAGE = 4
SA_FLURRY = 5
SA_DUAL_WIELD = 7

ZONE_SHORT = {
    "temple of veeshan": ("templeveeshan",),
    "plane of time": ("potimeb", "potimea"),
    "vex thal": ("vexthal",),
    "temple of ssraeshza": ("ssratemple",),
    "ssraeshza temple": ("ssratemple",),
    "sleepers tomb": ("sleeper",),
    "plane of fire": ("pofire",),
    "akheva ruins": ("akheva",),
    "kael drakkel": ("kael",),
    "plane of air": ("poair",),
    "the umbral plains": ("umbral",),
    "umbral plains": ("umbral",),
    "veeshans peak": ("veeshan",),
    "veeshans peak 1.0": ("veeshan",),
    "skyshrine": ("skyshrine",),
    "torment, the plane of pain": ("potorment",),
    "plane of growth": ("growthplane",),
    "the deep": ("thedeep",),
    "tower of solusek ro": ("solrotower",),
    "plane of water": ("powater",),
    "plane of earth": ("poearthb", "poeartha"),
    "bastion of thunder": ("bothunder",),
    "torden, bastion of thunder": ("bothunder",),
    "cazic-thule 2.0": ("cazicthule",),
    "crypt of decay": ("codecay",),
    "plane of tactics": ("potactics",),
    "ruins of sebilis": ("sebilis",),
    "griegs end": ("griegsend",),
    "sanctus seru": ("sseru",),
    "dragon necropolis": ("necropolis",),
    "halls of honor": ("hohonora", "hohonorb"),
    "western wastes": ("westwastes",),
    "icewell keep": ("thurgadinb",),
    "velketors labyrinth": ("velketor",),
    "drunder, the fortress of zek": ("potactics",),
    "the lair of terris thule": ("ponightmare",),
    "plane of fear": ("fearplane",),
    "plane of innovation": ("poinnovation",),
    "katta castellum": ("katta",),
    "permafrost caverns": ("permafrost",),
    "plane of storms": ("postorms",),
    "the plane of tranquility": ("potranquility",),
    "the hole": ("hole",),
    "the great divide": ("greatdivide",),
    "chardok": ("chardok",),
    "plane of sky": ("airplane",),
    "skyfire mountains": ("skyfire",),
    "the grey": ("thegrey",),
}


def norm_name(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    text = text.replace(" ", "_")
    while text.endswith("_"):
        text = text[:-1]
    return text.lower()


def norm_zone(value: str) -> str:
    text = (value or "").lower().replace("'", "").replace("`", "")
    return " ".join(text.split())


def display_name(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    while text.endswith("_"):
        text = text[:-1]
    return text.replace("_", " ")


def skip_label(value: str) -> bool:
    text = (value or "").strip()
    low = text.lower()
    if not text:
        return True
    if low.startswith("quest:"):
        return True
    if "/" in text:
        return True
    return low in {"wave 1", "eom trash"}


def parse_specials(raw: str) -> dict[int, list[int]]:
    found: dict[int, list[int]] = {}
    for piece in (raw or "").split("^"):
        if not piece:
            continue
        parts: list[int] = []
        bad = False
        for bit in piece.split(","):
            bit = bit.strip()
            if bit == "":
                parts.append(0)
                continue
            try:
                parts.append(int(bit))
            except ValueError:
                bad = True
                break
        if bad or len(parts) < 2 or parts[1] == 0:
            continue
        found[parts[0]] = parts[2:]
    return found


def ability_param(params: list[int] | None, index: int, default: int) -> int | None:
    if params is None:
        return None
    if index < len(params) and params[index] > 0:
        return params[index]
    return default


def load_zeal() -> dict[str, list[dict]]:
    index: dict[str, list[dict]] = defaultdict(list)
    for path in ZEAL_NPC.glob("*.json"):
        if path.name in SKIP_FILES or path.name.endswith((".quest.json", ".spawngroups.json")):
            continue
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, list) or not data or not isinstance(data[0], dict):
            continue
        if "mindmg" not in data[0]:
            continue
        zone = path.stem
        for rec in data:
            name = rec.get("name") or ""
            if not isinstance(name, str) or not name:
                continue
            index[norm_name(name)].append({
                "zone": zone,
                "id": int(rec.get("id") or 0),
                "name": name,
                "level": int(rec.get("level") or 0),
                "class_id": int(rec.get("class") or 0),
                "min_hit": int(rec.get("mindmg") or 0),
                "max_hit": int(rec.get("maxdmg") or 0),
                "atk": int(rec.get("atk") or 0),
                "accuracy": int(rec.get("accuracy") or 0),
                "attack_delay": int(rec.get("attack_delay") or 0),
                "attack_count": int(rec.get("attack_count") or 0),
                "slow_mitigation": int(rec.get("slow_mitigation") or 0),
                "specials": rec.get("special_abilities") or "",
            })
    return index


def signature(row: dict) -> tuple:
    return (
        row["level"],
        row["class_id"],
        row["min_hit"],
        row["max_hit"],
        row["atk"],
        row["accuracy"],
        row["attack_delay"],
        row["attack_count"],
        row["slow_mitigation"],
        row["specials"],
    )


def rank(row: dict) -> tuple:
    return (row["max_hit"], row["level"], row["id"])


def shorts_for(labels: set[str]) -> set[str]:
    found: set[str] = set()
    for label in labels:
        if not label:
            continue
        found.update(ZONE_SHORT.get(norm_zone(label), ()))
    return found


def zone_label(zone: str, labels: set[str]) -> str:
    matched = []
    for label in sorted(labels):
        if not label:
            continue
        if zone in ZONE_SHORT.get(norm_zone(label), ()):
            matched.append(label)
    return matched[0] if matched else zone


def encounter_from(row: dict, name: str, zone_text: str) -> dict:
    specials = parse_specials(row["specials"])
    count = row["attack_count"]
    attack_count = count if count >= 2 else 1
    klass = CLASS_NAMES.get(row["class_id"], "Class %s" % row["class_id"])
    return {
        "id": "%s-%s" % (row["zone"], row["id"]),
        "name": name,
        "zone": row["zone"],
        "zoneLabel": zone_text,
        "npcId": row["id"],
        "minHit": row["min_hit"],
        "maxHit": row["max_hit"],
        "atk": row["atk"],
        "accuracy": row["accuracy"],
        "level": row["level"],
        "className": klass,
        "attackDelay": row["attack_delay"],
        "slowMitigation": row["slow_mitigation"],
        "attackCount": attack_count,
        "dualWield": SA_DUAL_WIELD in specials,
        "flurryChance": ability_param(specials.get(SA_FLURRY), 0, 20),
        "rampageChance": ability_param(specials.get(SA_RAMPAGE), 0, 20),
        "rampageDamagePct": ability_param(specials.get(SA_RAMPAGE), 2, 100),
        "areaRampageChance": ability_param(specials.get(SA_AREA_RAMPAGE), 0, 20),
        "areaRampageDamagePct": ability_param(specials.get(SA_AREA_RAMPAGE), 2, 100),
    }


def build() -> dict:
    index = load_zeal()
    sources = json.loads(SOURCES.read_text(encoding="utf-8"))
    by_name: dict[str, set[str]] = defaultdict(set)
    raw_names: dict[str, str] = {}
    skipped: list[str] = []
    for entry in sources.values():
        mob = (entry.get("mob") or "").strip()
        if skip_label(mob):
            if mob and mob not in skipped:
                skipped.append(mob)
            continue
        key = norm_name(mob)
        raw_names.setdefault(key, mob)
        by_name[key].add((entry.get("zone") or "").strip())

    encounters: list[dict] = []
    unmatched: list[str] = []
    for key, labels in by_name.items():
        hits = index.get(key) or []
        if not hits:
            loot_zones = sorted(zone for zone in labels if zone)
            encounters.append({
                "id": "upcoming-%s" % key,
                "name": display_name(raw_names[key]) + " (upcoming)",
                "zone": "",
                "zoneLabel": "Upcoming",
                "lootZone": loot_zones[0] if loot_zones else "",
                "npcId": None,
                "future": True,
            })
            continue
        shorts = shorts_for(labels)
        pool = [row for row in hits if row["zone"] in shorts] if shorts else hits
        if not pool:
            pool = hits
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for row in pool:
            groups[signature(row)].append(row)
        chosen = [max(rows, key=rank) for rows in groups.values()]
        base = display_name(raw_names[key])
        for row in chosen:
            label = zone_label(row["zone"], labels)
            name = base if len(chosen) == 1 else "%s (%s)" % (base, label)
            encounters.append(encounter_from(row, name, label))

    seen: dict[str, int] = {}
    for enc in encounters:
        seen[enc["name"]] = seen.get(enc["name"], 0) + 1
    if any(count > 1 for count in seen.values()):
        for enc in encounters:
            if seen[enc["name"]] > 1:
                enc["name"] = "%s [%s]" % (enc["name"], enc["npcId"])
                enc["id"] = "%s-%s" % (enc["id"], enc["npcId"])

    encounters.sort(key=lambda enc: (enc["zoneLabel"].lower(), enc["name"].lower(), enc["npcId"]))
    return {
        "version": 2,
        "source": "raid_item_sources.json matched to Zeal npc_info zone JSON",
        "completeHealPreset": {
            "name": "Four-healer chain",
            "amount": 7500,
            "healers": 4,
            "castMs": 10000,
            "spacingMs": 3000,
            "note": "Complete Heal cast time and amount were not loaded from a spell row. Four healers at 3 seconds between landings have a 12 second personal cycle, which covers a 10 second cast.",
        },
        "unmatched": sorted(unmatched),
        "skipped": sorted(set(skipped)),
        "encounters": encounters,
    }


def main() -> None:
    payload = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("encounters %s unmatched %s skipped %s" % (
        len(payload["encounters"]), len(payload["unmatched"]), len(payload["skipped"])
    ))


if __name__ == "__main__":
    main()
