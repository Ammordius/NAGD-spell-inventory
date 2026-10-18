#!/usr/bin/env python3
"""Write data/item_mod2.json from the launch list and peq item ids.

The launch list is the complete Mod2 dataset. Items that do not match an
equippable row are recorded under unresolved and are not scored.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pymysql

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "item_mod2.json"

# name -> canonical mods. Percent stats are stored as their percent points.
LAUNCH = {
    "Gauntlets of Disruption": {"strikethrough": 5},
    "Protective Sleeves": {"stun_resist": 5},
    "Earring of Xaoth Kor": {"combat_effects": 5},
    "Mask of Strategic Insight": {"accuracy": 10},
    "Symbol of the Planemasters": {"stun_resist": 5},
    "Ring of Evasion": {"avoidance": 10},
    "Gloves of the Unseen": {"spell_shielding": 4},
    "Bracer of Precision": {"stun_resist": 5},
    "Cloak of the Falling Skies": {"avoidance": 10},
    "Hopebringer": {"strikethrough": 5},
    "Band of Prismatic Focus": {"combat_effects": 10},
    "Mantle of Deadly Precision": {"accuracy": 15},
    "Winged Storm Boots": {"spell_shielding": 4},
    "Tactician's Shield": {"spell_shielding": 5},
    "Cudgel of Venomous Hatred": {"strikethrough": 5},
    "Armguards of the Brute": {"spell_shielding": 4},
    "Shinai of the Ancients": {"avoidance": 5},
    "Globe of Mystical Protection": {"avoidance": 10},
    "Shoes of Fleeting Fury": {"spell_shielding": 4},
    "Collar of Catastrophe": {"shielding": 2},
    "Leggings of Furious Might": {"shielding": 2, "avoidance": 10},
    "Boots of Despair": {"stun_resist": 5},
    "Timespinner, Blade of the Hunter": {"accuracy": 5},
    "Belt of Temporal Bindings": {"spell_shielding": 5},
    "Earring of Unseen Horrors": {"stun_resist": 4},
    "Greaves of Furious Might": {"shielding": 4},
    "Timestone Adorned Ring": {"strikethrough": 5},
    "Padded Tigerskin Gloves": {"strikethrough": 10},
    "Necklace of Eternal Visions": {"shielding": 2},
    "Girdle of Stability": {"stun_resist": 5},
    "Gloves of Airy Mists": {"strikethrough": 10},
    "Jagged Timeforged Blade": {"accuracy": 5},
    "Shroud of Survival": {"accuracy": 8},
    "Shield of Strife": {"shielding": 3},
    "Sandals of Empowerment": {"stun_resist": 5},
    "Platinum Cloak of War": {"avoidance": 10},
    "Darkblade of the Warlord": {"strikethrough": 5},
    "Pants of Furious Might": {"avoidance": 25},
    "Shroud of Eternity": {"shielding": 4, "damage_shield": 5},
    "Bracer of the Inferno": {"stun_resist": 4, "accuracy": 15},
    "Earthen Bracer of Fortitude": {"shielding": 2, "stun_resist": 4},
    "Ethereal Silk Leggings": {"stun_resist": 5, "avoidance": 20},
    "Whorl of Unnatural Forces": {"stun_resist": 5},
    "Wristband of Icy Vengeance": {"avoidance": 15, "accuracy": 15},
    "Cord of Temporal Weavings": {"strikethrough": 10},
    "Shawl of Eternal Forces": {"combat_effects": 15},
    "Silver Hoop of Speed": {"combat_effects": 15},
    "Prismatic Ring of Resistance": {"spell_shielding": 6},
    "Grimror's Guard of the Plagues": {"shielding": 2},
    "Trydan's Chestplate of Nobility": {"shielding": 2},
    "Raex's Chestplate of Destruction": {"shielding": 3},
    "Rizlona's Fiery Chestplate": {"stun_resist": 7},
    "Ultor's Chestguard of Faith": {"stun_resist": 7},
    "Kerasha's Sylvan Tunic": {"stun_resist": 7},
    "Rosrak's Hauberk of the Primal": {"stun_resist": 7},
    "Ton Po's Chestwraps of Composure": {"avoidance": 15},
    "Dumul's Chestwraps of the Brute": {"avoidance": 15},
    "Galladan's Stormwrath Tunic": {"accuracy": 15},
    "Bidilis' Hauberk of the Elusive": {"accuracy": 15},
    "Askr's Thunderous Chainmail": {"accuracy": 15},
    "Miragul's Shroud of Risen Souls": {"spell_shielding": 6},
    "Maelin's Robe of Lore": {"spell_shielding": 6},
    "Magi'Kot's Robe of Convergence": {"spell_shielding": 6},
    "Romar's Robe of Visions": {"spell_shielding": 6},
}

NAME_ALIASES = {
    "Magi'Kot's Robe of Convergence": "Magi`Kot's Robe of Convergence",
    "Ultor's Chestguard of Faith": "Ultor's Chestguard of Faith",
}


def connect():
    return pymysql.connect(
        host="localhost",
        user="root",
        database="peq",
        port=3306,
        cursorclass=pymysql.cursors.DictCursor,
    )


def main() -> None:
    lookup_names = []
    for name in LAUNCH:
        lookup_names.append(NAME_ALIASES.get(name, name))
    conn = connect()
    cur = conn.cursor()
    q = "SELECT id, name, slots, classes FROM items WHERE name IN (" + ",".join(["%s"] * len(lookup_names)) + ")"
    cur.execute(q, lookup_names)
    by_name = defaultdict(list)
    for row in cur.fetchall():
        by_name[row["name"]].append(row)
    conn.close()

    items = {}
    unresolved = []
    for prompt_name, mods in LAUNCH.items():
        db_name = NAME_ALIASES.get(prompt_name, prompt_name)
        rows = [r for r in by_name.get(db_name, []) if int(r["slots"] or 0) > 0 and int(r["classes"] or 0) > 0]
        if len(rows) != 1:
            unresolved.append({
                "name": prompt_name,
                "db_name": db_name,
                "mods": mods,
                "matches": [int(r["id"]) for r in by_name.get(db_name, [])],
                "reason": "expected one equippable items row",
            })
            continue
        row = rows[0]
        items[str(int(row["id"]))] = {
            "name": prompt_name,
            "db_name": row["name"],
            "slots": int(row["slots"]),
            "classes": int(row["classes"]),
            "mods": mods,
        }

    payload = {
        "source": "Launch-era Plane of Time Mod2 additions. No other items currently have Mod2s.",
        "items": items,
        "unresolved": unresolved,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(items)} items, {len(unresolved)} unresolved -> {OUT}")
    for row in unresolved:
        print(" unresolved", row["name"], row["matches"])


if __name__ == "__main__":
    main()
