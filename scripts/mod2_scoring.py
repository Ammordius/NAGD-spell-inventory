#!/usr/bin/env python3
"""TAKP-era Mod2 scoring for class rankings.

Character scores stay on the existing 100-point class scale. A full-cap Mod2
is worth W * 100 points, where W is calibrated from combat math and that
class's existing HP/AC/focus weights. Only data/item_mod2.json contributes
Mod2 totals. Legacy overall_score is not modified here.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
ITEM_PATH = ROOT / "data" / "item_mod2.json"
CONFIG_PATH = ROOT / "data" / "mod2_config.json"

STATS = (
    "accuracy",
    "avoidance",
    "combat_effects",
    "damage_shield",
    "dot_shielding",
    "shielding",
    "spell_shielding",
    "strikethrough",
    "stun_resist",
)

CAPS = {
    "accuracy": 150.0,
    "avoidance": 100.0,
    "combat_effects": 100.0,
    "damage_shield": 25.0,
    "dot_shielding": 35.0,
    "shielding": 35.0,
    "spell_shielding": 35.0,
    "strikethrough": 35.0,
    "stun_resist": 35.0,
}

ALIASES = {
    "accuracy": "accuracy",
    "acc": "accuracy",
    "avoidance": "avoidance",
    "avoid": "avoidance",
    "combat_effects": "combat_effects",
    "combateffects": "combat_effects",
    "combat effects": "combat_effects",
    "damage_shield": "damage_shield",
    "damageshield": "damage_shield",
    "ds": "damage_shield",
    "dot_shielding": "dot_shielding",
    "dotshielding": "dot_shielding",
    "dot shielding": "dot_shielding",
    "shielding": "shielding",
    "spell_shielding": "spell_shielding",
    "spellshield": "spell_shielding",
    "spell shield": "spell_shielding",
    "spell shielding": "spell_shielding",
    "strikethrough": "strikethrough",
    "strike_through": "strikethrough",
    "stun_resist": "stun_resist",
    "stunresist": "stun_resist",
    "stun resist": "stun_resist",
}

CLASS_BITS = {
    "Warrior": 1,
    "Cleric": 2,
    "Paladin": 4,
    "Ranger": 8,
    "Shadow Knight": 16,
    "Druid": 32,
    "Monk": 64,
    "Bard": 128,
    "Rogue": 256,
    "Shaman": 512,
    "Necromancer": 1024,
    "Wizard": 2048,
    "Magician": 4096,
    "Enchanter": 8192,
    "Beastlord": 16384,
}

# (group, bit, how many can be worn)
SLOT_GROUPS = (
    ("ear", 2 | 16, 2),
    ("head", 4, 1),
    ("face", 8, 1),
    ("neck", 32, 1),
    ("shoulder", 64, 1),
    ("arms", 128, 1),
    ("back", 256, 1),
    ("wrist", 512 | 1024, 2),
    ("range", 2048, 1),
    ("hands", 4096, 1),
    ("primary", 8192, 1),
    ("secondary", 16384, 1),
    ("ring", 32768 | 65536, 2),
    ("chest", 131072, 1),
    ("legs", 262144, 1),
    ("feet", 524288, 1),
    ("waist", 1048576, 1),
)

# Unbuffed rank-1 sheets from class_rankings.json. core_json is the pre-UI score;
# the page displays that character as 100% of the class.
REFERENCES = {
    "Warrior": {"name": "Voracious", "hp": 8992, "ac": 2206, "mana": 0, "core_json": 91.79},
    "Cleric": {"name": "Drudger", "hp": 6335, "ac": 1917, "mana": 7312, "core_json": 94.9},
    "Paladin": {"name": "Pigpen", "hp": 7878, "ac": 2128, "mana": 6540, "core_json": 89.34},
    "Ranger": {"name": "Linkamus", "hp": 7457, "ac": 1815, "mana": 6990, "core_json": 98.47},
    "Shadow Knight": {"name": "Slouch", "hp": 8428, "ac": 2109, "mana": 6975, "core_json": 91.66},
    "Druid": {"name": "Baily", "hp": 6357, "ac": 1515, "mana": 7502, "core_json": 93.6},
    "Monk": {"name": "Zentile", "hp": 6969, "ac": 1809, "mana": 0, "core_json": 97.35},
    "Bard": {"name": "Taelor", "hp": 6722, "ac": 1997, "mana": 6555, "core_json": 93.6},
    "Rogue": {"name": "Tarkon", "hp": 7338, "ac": 1883, "mana": 0, "core_json": 97.97},
    "Shaman": {"name": "Ziva", "hp": 6280, "ac": 1765, "mana": 7367, "core_json": 94.27},
    "Necromancer": {"name": "Nark", "hp": 5502, "ac": 1144, "mana": 7247, "core_json": 90.99},
    "Wizard": {"name": "Beldis", "hp": 5299, "ac": 1049, "mana": 7097, "core_json": 89.76},
    "Magician": {"name": "Starsha", "hp": 5524, "ac": 1015, "mana": 7332, "core_json": 91.57},
    "Enchanter": {"name": "Diox", "hp": 5755, "ac": 1105, "mana": 7437, "core_json": 92.39},
    "Beastlord": {"name": "Akbar", "hp": 6913, "ac": 1580, "mana": 6715, "core_json": 94.45},
}

# melee_in / spell_in / dot_in are shares of dangerous incoming damage.
# threat is the default threat-limitation factor (0 means threat mods score 0).
# offense scales accuracy, strikethrough, and non-threat proc value.
ROLES = {
    "Warrior": {"melee_in": 0.80, "spell_in": 0.12, "dot_in": 0.08, "threat": 0.35, "offense": 0.20, "behind": False, "action": 0.05},
    "Paladin": {"melee_in": 0.62, "spell_in": 0.22, "dot_in": 0.08, "threat": 0.25, "offense": 0.28, "behind": False, "action": 0.12},
    "Shadow Knight": {"melee_in": 0.62, "spell_in": 0.18, "dot_in": 0.12, "threat": 0.28, "offense": 0.30, "behind": False, "action": 0.08},
    "Ranger": {"melee_in": 0.30, "spell_in": 0.14, "dot_in": 0.06, "threat": 0.05, "offense": 0.62, "behind": False, "action": 0.04},
    "Monk": {"melee_in": 0.28, "spell_in": 0.08, "dot_in": 0.05, "threat": 0.0, "offense": 0.75, "behind": False, "action": 0.02},
    "Rogue": {"melee_in": 0.22, "spell_in": 0.06, "dot_in": 0.04, "threat": 0.0, "offense": 0.80, "behind": True, "action": 0.02},
    "Beastlord": {"melee_in": 0.34, "spell_in": 0.14, "dot_in": 0.08, "threat": 0.08, "offense": 0.52, "behind": False, "action": 0.06},
    "Bard": {"melee_in": 0.22, "spell_in": 0.22, "dot_in": 0.08, "threat": 0.10, "offense": 0.40, "behind": False, "action": 0.15},
    "Cleric": {"melee_in": 0.12, "spell_in": 0.48, "dot_in": 0.10, "threat": 0.0, "offense": 0.02, "behind": False, "action": 0.35},
    "Druid": {"melee_in": 0.12, "spell_in": 0.38, "dot_in": 0.20, "threat": 0.0, "offense": 0.05, "behind": False, "action": 0.30},
    "Shaman": {"melee_in": 0.15, "spell_in": 0.32, "dot_in": 0.22, "threat": 0.0, "offense": 0.08, "behind": False, "action": 0.30},
    "Necromancer": {"melee_in": 0.08, "spell_in": 0.28, "dot_in": 0.36, "threat": 0.0, "offense": 0.02, "behind": False, "action": 0.22},
    "Wizard": {"melee_in": 0.08, "spell_in": 0.55, "dot_in": 0.08, "threat": 0.0, "offense": 0.02, "behind": False, "action": 0.25},
    "Magician": {"melee_in": 0.08, "spell_in": 0.45, "dot_in": 0.12, "threat": 0.0, "offense": 0.02, "behind": False, "action": 0.22},
    "Enchanter": {"melee_in": 0.10, "spell_in": 0.46, "dot_in": 0.12, "threat": 0.0, "offense": 0.02, "behind": False, "action": 0.28},
}

# Default ranking scenario: PoP raid, threat sometimes relevant, stuns not constant.
DEFAULT_STUN_EXPOSURE = 0.20
DEFAULT_ACTION_EXPOSURE = 0.08
# Assumed share of melee swings that are a successful parry/riposte/dodge/block.
FRONT_DEFENSE_RATE = 0.12
BEHIND_DEFENSE_RATE = 0.02
# Full combat effects assumed at about 4% of melee offense. Not the server ProcRate field.
COMBAT_EFFECTS_OFFENSE = 0.04
# Player white-hit stand-in for damage-shield comparison.
PLAYER_HIT = 400.0

TANK_CLASSES = ("Warrior", "Paladin", "Shadow Knight")

# Quarm row is verified in npc_types id 223008. The other rows are illustrative.
ENCOUNTERS = (
    {"name": "Quarm", "status": "verified", "weight": 0.50, "db": 1000, "di": 140, "min_hit": 1140, "max_hit": 3800, "level": 80, "atk": 500, "accuracy": 750},
    {"name": "PoP boss (illustrative)", "status": "illustrative", "weight": 0.30, "db": 600, "di": 220, "level": 70, "atk": 250, "accuracy": 150},
    {"name": "PoTime raid trash (illustrative)", "status": "illustrative", "weight": 0.20, "db": 180, "di": 60, "level": 65, "atk": 150, "accuracy": 50},
)

HEALING_WINDOWS = (8, 13, 20)


def canonical_stat(name: str) -> Optional[str]:
    if not name:
        return None
    key = ALIASES.get(str(name).strip().lower())
    return key


def empty_mods() -> Dict[str, float]:
    return {stat: 0.0 for stat in STATS}


def normalize_mods(raw: Optional[Mapping]) -> Dict[str, float]:
    out = empty_mods()
    if not raw:
        return out
    if isinstance(raw, list):
        pairs = []
        for entry in raw:
            if isinstance(entry, Mapping):
                pairs.append((entry.get("label") or entry.get("stat"), entry.get("value")))
        raw = dict(pairs)
    for key, value in raw.items():
        stat = canonical_stat(str(key))
        if stat is None or value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        out[stat] += number
    return out


def cap_mods(raw: Mapping[str, float]) -> Dict[str, float]:
    capped = empty_mods()
    for stat in STATS:
        try:
            value = float(raw.get(stat, 0) or 0)
        except (TypeError, ValueError):
            value = 0.0
        if value < 0:
            value = 0.0
        capped[stat] = min(CAPS[stat], value)
    return capped


def utility(stat: str, value: float) -> float:
    """Linear fraction of cap. U(0)=0, U(cap)=1, no value above cap."""
    cap = CAPS[stat]
    if cap <= 0 or value <= 0:
        return 0.0
    return min(float(value), cap) / cap


def quarm_db_di(min_hit: float = 1140, max_hit: float = 3800) -> tuple:
    di = (max_hit - min_hit) / 19.0
    db = min_hit - di
    return db, di


def shielding_prevented_per_hit(db: float, shielding_percent: float) -> float:
    percent = max(0.0, min(CAPS["shielding"], shielding_percent))
    return db * percent / 100.0


def player_avoidance(defense: int = 252, agi: int = 200, level: int = 65) -> int:
    """Client::GetAvoidance with combat agility 0, matching the unbuffed AC snapshot."""
    defense_avoidance = defense * 400 // 225 if defense > 0 else 0
    if agi < 40:
        agi_avoidance = (25 * (agi - 40)) // 40
    elif 60 <= agi <= 74:
        agi_avoidance = (2 * (28 - ((200 - agi) // 5))) // 3
    elif agi >= 75:
        bonus_adj = 80 if level >= 40 else 70 if level >= 20 else 55 if level >= 7 else 35
        if agi < 200:
            agi_avoidance = (2 * (bonus_adj - ((200 - agi) // 5))) // 3
        else:
            agi_avoidance = 2 * bonus_adj // 3
    else:
        agi_avoidance = 0
    return max(1, defense_avoidance + agi_avoidance)


def displayed_ac_parts(displayed_ac: int, avoidance: int) -> tuple:
    raw_sum = displayed_ac * 847 // 1000
    raw_mit = raw_sum - avoidance
    return raw_sum, raw_mit


def combat_mitigation(raw_mit: int, level: int = 65, softcap: int = 430, shield_ac: int = 0, stability_percent: int = 0) -> int:
    """PoP warrior-style softcap. Returns are the level-65 warrior values unless noted."""
    soft = softcap + (softcap * stability_percent) // 100 + shield_ac
    if raw_mit <= soft:
        return raw_mit
    if level <= 61:
        returns = 5
    elif level <= 63:
        returns = 4
    else:
        returns = 3
    return soft + (raw_mit - soft) // returns


def npc_offense(level: int, atk: int) -> int:
    mob = 45 if 45 < level < 51 else level
    base = mob * 55 // 10 - 4
    if base > 320:
        base = 320
    if level >= 30:
        str_off = level * 2 - 40 + 20
    elif level >= 6:
        str_off = level // 2 + 1
    else:
        str_off = level
    return max(1, base + str_off + atk)


def npc_weapon_skill(level: int) -> int:
    if level > 50:
        return 250 + level
    return min(level * 6, 275)


def npc_to_hit(level: int, accuracy: int) -> int:
    skill = npc_weapon_skill(level)
    return 7 + skill + skill + accuracy


def hit_chance(to_hit: float, avoidance: float) -> float:
    to_hit = to_hit + 10
    avoidance = avoidance + 10
    if to_hit * 1.21 > avoidance:
        return 1.0 - avoidance / (to_hit * 1.21 * 2.0)
    return (to_hit * 1.21) / (avoidance * 2.0)


def expected_interval(offense: int, mitigation: int, samples: int = 3000, seed: int = 14650) -> float:
    """Mean RollD20 index (1..20) using integer math like Mob::RollD20."""
    rng = random.Random(seed + offense * 17 + mitigation)
    total = 0
    off_span = int(offense) + 5
    mit_span = int(mitigation) + 5
    avg = (int(offense) + int(mitigation) + 10) // 2
    if avg <= 0:
        return 1.0
    for _ in range(samples):
        atk_roll = rng.randrange(off_span)
        def_roll = rng.randrange(mit_span)
        index = (atk_roll - def_roll) + (avg // 2)
        if index < 0:
            index = 0
        index = (index * 20) // avg
        if index < 0:
            index = 0
        if index > 19:
            index = 19
        total += index + 1
    return total / samples


def mean_hit(db: float, di: float, interval: float, shielding: float = 0.0) -> float:
    shielded_db = db * (1.0 - min(CAPS["shielding"], max(0.0, shielding)) / 100.0)
    return shielded_db + di * interval


def load_item_table(path: Optional[Path] = None) -> dict:
    path = path or ITEM_PATH
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items") or {}
    clean = {}
    for item_id, entry in items.items():
        mods = normalize_mods((entry or {}).get("mods"))
        clean[str(item_id)] = {
            "name": (entry or {}).get("name") or "",
            "db_name": (entry or {}).get("db_name") or "",
            "slots": int((entry or {}).get("slots") or 0),
            "classes": int((entry or {}).get("classes") or 0),
            "mods": {stat: mods[stat] for stat in STATS if mods[stat]},
        }
    return {"source": data.get("source", ""), "items": clean, "unresolved": data.get("unresolved") or []}


def merge_mods(existing: Mapping[str, float], incoming: Mapping[str, float]) -> Dict[str, float]:
    """Fill only missing or zero stats. A second apply does not stack."""
    out = normalize_mods(existing)
    extra = normalize_mods(incoming)
    for stat, value in extra.items():
        if out.get(stat, 0) == 0 and value:
            out[stat] = value
    return out


def lookup_mods(item_id, table: Mapping) -> Dict[str, float]:
    if item_id is None or item_id == "":
        return empty_mods()
    entry = (table.get("items") or table).get(str(item_id))
    if not entry:
        return empty_mods()
    return normalize_mods(entry.get("mods"))


def sum_mods(item_ids: Iterable, table: Mapping) -> Dict[str, float]:
    total = empty_mods()
    for item_id in item_ids:
        if item_id is None or item_id == "":
            continue
        mods = lookup_mods(item_id, table)
        for stat in STATS:
            total[stat] += mods[stat]
    return total


def _lazy_normalize(class_name: str) -> dict:
    import sys
    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    from generate_class_rankings import CLASS_WEIGHTS, normalize_class_weights
    return normalize_class_weights(CLASS_WEIGHTS[class_name])


def power_share(norm: Mapping) -> float:
    focus = norm.get("focus") or {}
    weapon = focus.get("WeaponMetric") or 0
    if isinstance(weapon, (int, float)) and weapon > 0:
        return float(weapon)
    total = 0.0
    for value in focus.values():
        if isinstance(value, dict):
            total += sum(float(v) for v in value.values() if isinstance(v, (int, float)) and v > 0)
        elif isinstance(value, (int, float)) and value > 0:
            total += float(value)
    return total


def json_points_per_hp(class_name: str, ref: Mapping, norm: Mapping) -> float:
    hp_w = float(norm.get("hp_pct") or 0)
    if hp_w <= 0:
        return 0.0
    if class_name in TANK_CLASSES:
        max_combined = max(float(ref["ac"] or 1), float(ref["hp"]) / 5.0)
        return (0.2 / max_combined) * 100.0 * hp_w
    max_combined = max(float(ref["hp"]), float(ref.get("mana") or 0), 1.0)
    return (1.0 / max_combined) * 100.0 * hp_w


def upgrade_scale_for(class_name: str, ref: Mapping, norm: Mapping) -> float:
    """Item-score points equal to one Mod2 display point, matched to that class's HP slope."""
    per_hp_json = json_points_per_hp(class_name, ref, norm)
    core = float(ref["core_json"]) or 1.0
    per_hp_display = per_hp_json / (core / 100.0)
    hp_w = float(norm.get("hp_pct") or 0)
    per_hp_item = hp_w / 5000.0 if hp_w else float(norm.get("ac_pct") or 0) / 1200.0
    if per_hp_display <= 0:
        return 0.0
    return per_hp_item / per_hp_display


def _warrior_mitigation() -> int:
    avoidance = player_avoidance()
    _raw_sum, raw_mit = displayed_ac_parts(REFERENCES["Warrior"]["ac"], avoidance)
    return combat_mitigation(raw_mit)


def encounter_mean_hit(encounter: Mapping, shielding: float = 0.0, mitigation: Optional[int] = None) -> float:
    mit = _warrior_mitigation() if mitigation is None else mitigation
    offense = npc_offense(int(encounter["level"]), int(encounter["atk"]))
    interval = expected_interval(offense, mit)
    return mean_hit(float(encounter["db"]), float(encounter["di"]), interval, shielding)


def blended_shielding_fraction() -> float:
    """Share of a landed hit removed by 35% shielding, averaged across encounters."""
    total_w = 0.0
    acc = 0.0
    for enc in ENCOUNTERS:
        bare = encounter_mean_hit(enc, 0.0)
        if bare <= 0:
            continue
        weight = float(enc["weight"])
        acc += weight * (shielding_prevented_per_hit(float(enc["db"]), 35.0) / bare)
        total_w += weight
    return acc / total_w if total_w else 0.0


def blended_avoidance_fraction(extra: float = 100.0) -> float:
    """Relative hit-rate drop from worn avoidance added to the sheet avoidance rating."""
    base_av = player_avoidance()
    total_w = 0.0
    acc = 0.0
    for enc in ENCOUNTERS:
        to_hit = npc_to_hit(int(enc["level"]), int(enc["accuracy"]))
        h0 = hit_chance(to_hit, base_av)
        h1 = hit_chance(to_hit, base_av + extra)
        if h0 <= 0:
            continue
        weight = float(enc["weight"])
        acc += weight * max(0.0, (h0 - h1) / h0)
        total_w += weight
    return acc / total_w if total_w else 0.0


def accuracy_relative_gain(amount: float = 150.0) -> float:
    """Relative melee hit gain versus a level-80 avoidance cap of 460."""
    npc_av = 460.0
    base = hit_chance(7 + 252 + 252, npc_av)
    boosted = hit_chance(7 + 252 + 252 + amount, npc_av)
    if base <= 0:
        return 0.0
    return max(0.0, (boosted - base) / base)


def derive_weights() -> Dict[str, Dict[str, Dict[str, float]]]:
    shield_frac = blended_shielding_fraction()
    avoid_frac = blended_avoidance_fraction(CAPS["avoidance"])
    acc_gain = accuracy_relative_gain(CAPS["accuracy"])
    weights = {}
    for class_name, role in ROLES.items():
        norm = _lazy_normalize(class_name)
        hp_w = float(norm.get("hp_pct") or 0)
        ac_w = float(norm.get("ac_pct") or 0)
        defensive = hp_w + ac_w
        power = power_share(norm)
        defense_rate = BEHIND_DEFENSE_RATE if role["behind"] else FRONT_DEFENSE_RATE
        ce_offense = COMBAT_EFFECTS_OFFENSE * role["offense"] * power
        if role["threat"] <= 0:
            ce_other, ce_threat = ce_offense, 0.0
        elif role["offense"] >= 0.45:
            ce_other, ce_threat = ce_offense * 0.70, ce_offense * 0.30
        else:
            ce_other, ce_threat = 0.0, ce_offense
        stun_threat = CAPS["stun_resist"] / 100.0 * DEFAULT_STUN_EXPOSURE * role["threat"] * max(power, defensive * 0.5)
        stun_action = CAPS["stun_resist"] / 100.0 * DEFAULT_ACTION_EXPOSURE * role["action"] * max(hp_w, 0.05)
        row = {
            "shielding": {"other": shield_frac * role["melee_in"] * defensive, "threat": 0.0},
            "avoidance": {"other": avoid_frac * role["melee_in"] * defensive, "threat": 0.0},
            "spell_shielding": {"other": (CAPS["spell_shielding"] / 100.0) * role["spell_in"] * hp_w, "threat": 0.0},
            "dot_shielding": {"other": (CAPS["dot_shielding"] / 100.0) * role["dot_in"] * hp_w, "threat": 0.0},
            "accuracy": {"other": acc_gain * role["offense"] * power, "threat": 0.0},
            "strikethrough": {"other": defense_rate * (CAPS["strikethrough"] / 100.0) * role["offense"] * power, "threat": 0.0},
            "combat_effects": {"other": ce_other, "threat": ce_threat},
            "stun_resist": {"other": stun_action, "threat": stun_threat},
            "damage_shield": {"other": (CAPS["damage_shield"] / PLAYER_HIT) * 0.05 * role["offense"] * power, "threat": 0.0},
        }
        weights[class_name] = row
    return weights


def scenario_weights(class_name: str, weights: Mapping, scenario: Optional[Mapping] = None) -> Dict[str, float]:
    role = ROLES[class_name]
    scenario = scenario or {}
    threat_factor = role["threat"] if "threat_limitation" not in scenario else float(scenario["threat_limitation"])
    stun_exposure = DEFAULT_STUN_EXPOSURE if "stun_exposure" not in scenario else float(scenario["stun_exposure"])
    out = {}
    for stat, parts in weights[class_name].items():
        other = float(parts.get("other") or 0)
        threat = float(parts.get("threat") or 0)
        if role["threat"] <= 0 or threat_factor <= 0:
            scaled_threat = 0.0
        else:
            scaled_threat = threat * (threat_factor / role["threat"])
        if stat == "stun_resist":
            if stun_exposure <= 0:
                scaled_threat = 0.0
            else:
                scaled_threat *= stun_exposure / DEFAULT_STUN_EXPOSURE
        out[stat] = other + scaled_threat
    return out


def mod2_fraction(class_name: str, capped: Mapping[str, float], weights: Mapping, scenario: Optional[Mapping] = None) -> float:
    active = scenario_weights(class_name, weights, scenario)
    total = 0.0
    for stat in STATS:
        total += active[stat] * utility(stat, float(capped.get(stat, 0) or 0))
    return total


def mod2_points(class_name: str, capped: Mapping[str, float], weights: Mapping, scenario: Optional[Mapping] = None) -> float:
    """Points on the same 100-point scale as a class's displayed core score."""
    return 100.0 * mod2_fraction(class_name, capped, weights, scenario)


def combined_display(core_pct: float, mod2_pts: float, reference_pts: float) -> float:
    denom = 100.0 + max(0.0, reference_pts)
    return 100.0 * (core_pct + mod2_pts) / denom


def displayed_score(core_pct: float, mod2_pts: float, reference_pts: float, mod2_enabled: bool) -> float:
    """dkp_val does not enter this function. mod2 off returns the core score unchanged."""
    if not mod2_enabled:
        return core_pct
    return combined_display(core_pct, mod2_pts, reference_pts)


def groups_for_slots(slots: int) -> List[str]:
    found = []
    for name, bits, _count in SLOT_GROUPS:
        if slots & bits:
            found.append(name)
    return found


def fits(open_counts: Mapping[str, int], needed: Sequence[str]) -> bool:
    needed_counts: Dict[str, int] = {}
    for name in needed:
        needed_counts[name] = needed_counts.get(name, 0) + 1
    return all(open_counts.get(name, 0) >= count for name, count in needed_counts.items())


def reference_loadout(class_name: str, table: Mapping, weights: Mapping) -> dict:
    """Greedy equip of launch items this class can wear, by marginal Mod2 points."""
    bit = CLASS_BITS[class_name]
    pool = []
    for item_id, entry in (table.get("items") or {}).items():
        if int(entry.get("classes") or 0) & bit:
            pool.append((str(item_id), entry))
    open_counts = {name: count for name, _bits, count in SLOT_GROUPS}
    raw = empty_mods()
    chosen = []
    while pool:
        best = None
        best_gain = 0.0
        current_pts = mod2_points(class_name, cap_mods(raw), weights)
        for item_id, entry in pool:
            needed = groups_for_slots(int(entry.get("slots") or 0))
            if not needed or not fits(open_counts, needed):
                continue
            trial = dict(raw)
            mods = normalize_mods(entry.get("mods"))
            for stat in STATS:
                trial[stat] += mods[stat]
            gain = mod2_points(class_name, cap_mods(trial), weights) - current_pts
            if gain > best_gain + 1e-9:
                best_gain = gain
                best = (item_id, entry, needed, trial)
        if best is None:
            break
        item_id, entry, needed, trial = best
        for name in needed:
            open_counts[name] -= 1
        raw = trial
        chosen.append({"id": item_id, "name": entry.get("name")})
        pool = [row for row in pool if row[0] != item_id]
    capped = cap_mods(raw)
    return {
        "items": chosen,
        "raw": {k: raw[k] for k in STATS if raw[k]},
        "capped": {k: capped[k] for k in STATS if capped[k]},
        "points": round(mod2_points(class_name, capped, weights), 4),
    }


def build_config() -> dict:
    weights = derive_weights()
    table = load_item_table()
    classes = {}
    for class_name, ref in REFERENCES.items():
        norm = _lazy_normalize(class_name)
        loadout = reference_loadout(class_name, table, weights)
        scale = upgrade_scale_for(class_name, ref, norm)
        classes[class_name] = {
            "reference": ref,
            "role": ROLES[class_name],
            "weights": weights[class_name],
            "reference_loadout": loadout,
            "reference_mod2_points": loadout["points"],
            "upgrade_scale": scale,
            "core_weights": {
                "hp_pct": norm.get("hp_pct"),
                "mana_pct": norm.get("mana_pct"),
                "ac_pct": norm.get("ac_pct"),
                "resists_pct": norm.get("resists_pct"),
            },
        }
    return {
        "caps": CAPS,
        "stats": list(STATS),
        "default_scenario": {
            "name": "pop_raid_partial_threat",
            "stun_exposure": DEFAULT_STUN_EXPOSURE,
            "action_exposure": DEFAULT_ACTION_EXPOSURE,
            "note": "Threat-limitation uses each class role default. Pass threat_limitation 0 to zero threat value.",
        },
        "encounters": list(ENCOUNTERS),
        "classes": classes,
        "calibration": {
            "shielding_fraction_of_hit": blended_shielding_fraction(),
            "avoidance_fraction_of_hits": blended_avoidance_fraction(),
            "accuracy_relative_gain": accuracy_relative_gain(),
            "warrior_avoidance": player_avoidance(),
            "warrior_combat_mitigation": _warrior_mitigation(),
            "quarm_db_di": quarm_db_di(),
        },
    }


def write_config(path: Optional[Path] = None) -> dict:
    config = build_config()
    path = path or CONFIG_PATH
    path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    return config


def load_config(path: Optional[Path] = None) -> dict:
    path = path or CONFIG_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def score_ids(class_name: str, item_ids: Iterable, config: Mapping, table: Mapping, scenario: Optional[Mapping] = None) -> dict:
    raw = sum_mods(item_ids, table)
    capped = cap_mods(raw)
    weights = {class_name: config["classes"][class_name]["weights"]}
    points = mod2_points(class_name, capped, weights, scenario)
    active = scenario_weights(class_name, weights, scenario)
    by_stat = {}
    for stat in STATS:
        if raw[stat] or capped[stat]:
            by_stat[stat] = {
                "raw": raw[stat],
                "capped": capped[stat],
                "utility": utility(stat, capped[stat]),
                "weight": active[stat],
                "points": 100.0 * active[stat] * utility(stat, capped[stat]),
            }
    return {"raw": raw, "capped": capped, "points": points, "by_stat": by_stat}


def upgrade_delta(class_name: str, before_ids: Sequence, after_ids: Sequence, config: Mapping, table: Mapping, scenario: Optional[Mapping] = None) -> dict:
    before = score_ids(class_name, before_ids, config, table, scenario)
    after = score_ids(class_name, after_ids, config, table, scenario)
    display_delta = after["points"] - before["points"]
    scale = float(config["classes"][class_name]["upgrade_scale"])
    return {
        "display_delta": display_delta,
        "item_delta": display_delta * scale,
        "before": before,
        "after": after,
    }


def worn_ids(inventory: Optional[Sequence]) -> List:
    ids = []
    for row in inventory or []:
        slot = row.get("slot_id")
        try:
            slot_n = int(slot)
        except (TypeError, ValueError):
            continue
        if slot_n < 1 or slot_n > 22:
            continue
        ids.append(row.get("item_id"))
    return ids


def annotate_character(char: MutableMapping, config: Optional[Mapping] = None, table: Optional[Mapping] = None) -> None:
    """Attach char['mod2'] without changing overall_score."""
    config = config or load_config()
    table = table or load_item_table()
    class_name = char.get("class")
    if class_name not in config["classes"]:
        return
    scored = score_ids(class_name, worn_ids(char.get("inventory")), config, table)
    ref_pts = float(config["classes"][class_name]["reference_mod2_points"])
    char["mod2"] = {
        "points": round(scored["points"], 4),
        "reference_points": ref_pts,
        "by_stat": scored["by_stat"],
    }


def public_config() -> dict:
    config = load_config()
    return {
        "caps": config["caps"],
        "default_scenario": config["default_scenario"],
        "classes": {
            name: {
                "reference_mod2_points": row["reference_mod2_points"],
                "upgrade_scale": row["upgrade_scale"],
                "weights": row["weights"],
            }
            for name, row in config["classes"].items()
        },
    }


def threat_component(class_name: str, capped: Mapping[str, float], config: Mapping, scenario: Mapping) -> float:
    weights = {class_name: config["classes"][class_name]["weights"]}
    role = ROLES[class_name]
    # Rebuild only the threat portion.
    threat_factor = role["threat"] if "threat_limitation" not in scenario else float(scenario["threat_limitation"])
    stun_exposure = DEFAULT_STUN_EXPOSURE if "stun_exposure" not in scenario else float(scenario["stun_exposure"])
    total = 0.0
    for stat in ("stun_resist", "combat_effects"):
        stored = float(weights[class_name][stat].get("threat") or 0)
        if role["threat"] <= 0 or threat_factor <= 0 or stored <= 0:
            continue
        scaled = stored * (threat_factor / role["threat"])
        if stat == "stun_resist":
            if stun_exposure <= 0:
                continue
            scaled *= stun_exposure / DEFAULT_STUN_EXPOSURE
        total += 100.0 * scaled * utility(stat, float(capped.get(stat, 0) or 0))
    return total


if __name__ == "__main__":
    written = write_config()
    cal = written["calibration"]
    print("quarm", cal["quarm_db_di"])
    print("shield fraction", round(cal["shielding_fraction_of_hit"], 4))
    print("avoid fraction", round(cal["avoidance_fraction_of_hits"], 4))
    print("accuracy gain", round(cal["accuracy_relative_gain"], 4))
    print("warrior mit", cal["warrior_combat_mitigation"], "av", cal["warrior_avoidance"])
    for name in ("Warrior", "Monk", "Rogue", "Wizard", "Cleric", "Shadow Knight"):
        row = written["classes"][name]
        full = {stat: round((parts["other"] + parts["threat"]) * 100, 2) for stat, parts in row["weights"].items()}
        print(name, "ref_pts", row["reference_mod2_points"], "full_cap_points", full)
