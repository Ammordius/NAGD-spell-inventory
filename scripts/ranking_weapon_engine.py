"""
Weapon DPS / hate-per-sec for class rankings — parity with magelo/dps_calculator.html.

Buffed: hastePct buff 70 + item haste (capped), worn ATK + 140 Pred/Tunare spell ATK.
Unbuffed: item haste only, worn ATK only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_MAG = Path(__file__).resolve().parents[1]

WARRIOR_2H_MULT_SCALE = 0.91
TRUESHOT_ARCHERY_DAMAGE_PCT = 100
EAGLE_EYE_ARCHERY_HIT_PCT = 40
MIN_HASTED_DELAY_MS = 400
BOW_TIMER_CORR_MS = 100
FLEETING_QUIVER_BAG_WR = 60
QUIVER_WR_HASTE_DIV = 4


def _mag_path(*parts: str) -> Path:
    return _MAG.joinpath(*parts)


def normalize_proc_name(s: str | None) -> str:
    if not s or not isinstance(s, str):
        return ""
    return " ".join(s.strip().lower().split())


def load_json(path: Path | str) -> dict[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def build_aa_map(dps_config: Mapping[str, Any], class_name: str) -> dict[str, int]:
    out: dict[str, int] = {}
    cfg = (dps_config.get("classes") or {}).get(class_name) or {}
    for aa in cfg.get("aas") or []:
        for k, v in (aa.get("bonuses") or {}).items():
            if isinstance(v, (int, float)):
                if k == "CriticalHitChance":
                    out[k] = max(out.get(k, 0), int(v))
                else:
                    out[k] = out.get(k, 0) + int(v)
    return out


def sum_warrior_flurry_chance(dps_config: Mapping[str, Any]) -> int:
    s = 0
    for aa in (dps_config.get("classes") or {}).get("Warrior", {}).get("aas") or []:
        s += int((aa.get("bonuses") or {}).get("FlurryChance") or 0)
    return s


def npc_mitigation(level: int, ac: int) -> int:
    if level < 15:
        mit = level * 3
        if level < 3:
            mit += 2
    else:
        mit = min(200, int(level * 41 / 10 - 15))
        if mit == 200 and ac > 200:
            mit = ac
    return max(1, mit)


def npc_avoidance(level: int) -> int:
    a = level * 9 + 5
    if level <= 50 and a > 400:
        a = 400
    elif a > 460:
        a = 460
    return max(1, a)


def hit_chance(to_hit: float, avoidance: float, to_hit_pct: float = 0, avoidance_pct: float = 0) -> float:
    to_hit = to_hit * (100 + to_hit_pct) / 100
    avoidance = avoidance * (100 + avoidance_pct) / 100
    to_hit += 10
    avoidance += 10
    if to_hit * 1.21 > avoidance:
        return 1 - avoidance / (to_hit * 1.21 * 2)
    return (to_hit * 1.21) / (avoidance * 2)


def expected_roll_d20(offense: int, mitigation: int) -> float:
    avg = offense + mitigation + 10
    e = 1 + (20 * (offense + 5)) / avg
    return max(1, min(20, e))


def calc_melee_damage(base_damage: int, offense: int, mitigation: int, is_ranged: bool) -> int:
    bd = base_damage
    if is_ranged and bd > 1:
        bd = bd // 2
    roll = expected_roll_d20(offense, mitigation)
    dmg = int((roll * bd + 5) / 10)
    min_hit = base_damage
    if dmg < min_hit:
        dmg = min_hit
    if dmg < 1:
        dmg = 1
    return dmg


def roll_damage_multiplier_expected(offense: int, level: int, is_monk: bool) -> float:
    if is_monk and level >= 65:
        roll_chance, max_extra, minus_factor = 83, 300, 50
    elif level >= 65 or (is_monk and level >= 63):
        roll_chance, max_extra, minus_factor = 81, 295, 55
    elif level >= 63 or (is_monk and level >= 60):
        roll_chance, max_extra, minus_factor = 79, 290, 60
    elif level >= 60 or (is_monk and level >= 56):
        roll_chance, max_extra, minus_factor = 77, 285, 65
    elif level >= 56:
        roll_chance, max_extra, minus_factor = 72, 265, 70
    elif level >= 51 or is_monk:
        roll_chance, max_extra, minus_factor = 65, 245, 80
    else:
        return 1.0
    base_bonus = max(10, (offense - minus_factor) // 2)
    expected_roll_when_proc = 100 + base_bonus / 2
    mult_when_proc = min(max_extra / 100, expected_roll_when_proc / 100)
    return (roll_chance / 100) * mult_when_proc + (1 - roll_chance / 100)


def get_offense(skill: int, str_: int, dex: int, is_archery: bool, is_ranger55: bool) -> int:
    stat = dex if is_archery else str_
    stat_bonus = (2 * stat - 150) // 3 if stat >= 75 else 0
    off = skill + stat_bonus
    if is_ranger55:
        off += 65 * 4 - 216
    return max(1, off)


def get_to_hit(offense_skill: int, weapon_skill: int, accuracy: int) -> int:
    return 7 + offense_skill + weapon_skill + accuracy


def get_double_attack_chance(skill: int, level: int, aas: Mapping[str, Any]) -> float:
    chance = float(skill)
    if chance > 0:
        chance += level
    chance += float(aas.get("GiveDoubleAttack", 0) or 0) * 5
    chance += chance * float(aas.get("DoubleAttackChance", 0) or 0) / 100.0
    return min(100.0, chance / 5.0)


def get_dual_wield_chance(skill: int, level: int, aas: Mapping[str, Any]) -> float:
    chance = skill + level + int(aas.get("Ambidexterity", 0) or 0)
    return chance * 100.0 / 375.0


def get_damage_bonus_1h(level: int) -> int:
    if level < 28:
        return 0
    return 1 + (level - 28) // 3


def get_damage_bonus_2h(level: int, delay: int) -> int:
    if level < 28:
        return 0
    bonus = 1 + (level - 28) // 3
    if delay <= 27:
        return bonus + 1
    if level <= 29:
        return bonus
    level_bonus = (level - 30) // 5 + 1
    if level > 50:
        level_bonus2 = level - 50
        level_bonus += 1
        if level > 67:
            level_bonus2 += 5
        elif level > 59:
            level_bonus2 += 4
        elif level > 58:
            level_bonus2 += 3
        elif level > 56:
            level_bonus2 += 2
        elif level > 54:
            level_bonus2 += 1
        level_bonus += level_bonus2 * delay // 40
    bonus += level_bonus
    if delay >= 40:
        delay_bonus = (delay - 40) // 3 + 1
        if delay >= 45:
            delay_bonus += 2
        elif delay >= 43:
            delay_bonus += 1
        bonus += delay_bonus
    return bonus


def is_two_hander_item(item: Mapping[str, Any] | None) -> bool:
    if not item:
        return False
    sk = str(item.get("skill") or "")
    return "2H" in sk.upper()


def weapon_skill_to_config_key(weapon_skill: str | None, is_ranger: bool) -> str:
    if not weapon_skill:
        return "archery" if is_ranger else "1HSlash"
    raw = str(weapon_skill).replace(" ", "")
    m = {
        "1HSlashing": "1HSlash",
        "2HSlashing": "2HSlash",
        "1HBlunt": "1HBlunt",
        "2HBlunt": "2HBlunt",
        "HandtoHand": "handToHand",
        "Piercing": "1HPiercing",
    }
    return m.get(raw, raw)


def effective_delay(delay: int, combined_haste: int, is_ranged: bool) -> int:
    reduced = int(delay * 100 / (100 + combined_haste))
    min_delay = 10 if is_ranged else 4
    return max(min_delay, reduced)


def swings_per_second(eff_delay: int) -> float:
    return 10.0 / eff_delay


def attack_timer_duration_ms(delay_tenths: int, combined_haste_melee: int) -> int:
    haste_mod = (100 + combined_haste_melee) / 100.0
    speed_ms = int(delay_tenths / haste_mod * 100)
    return max(MIN_HASTED_DELAY_MS, speed_ms)


def bow_ranged_timer_duration_ms(
    delay_tenths: int,
    spell_haste_bonus: int,
    overhaste_pct: int,
    use_quiver: bool,
    hundred_hands: int,
) -> int:
    cap_spell = min(100, int(spell_haste_bonus))
    get_haste = 100 + cap_spell + int(overhaste_pct)
    haste_mod = get_haste / 100.0
    hhe = int(hundred_hands)
    speed_ms = int(delay_tenths / haste_mod * 100 + (hhe / 100.0) * delay_tenths * 100)
    if use_quiver:
        quiver_haste = (FLEETING_QUIVER_BAG_WR / QUIVER_WR_HASTE_DIV) / 100.0
        bow_delay_reduction = int(quiver_haste * speed_ms + 1)
        if speed_ms - bow_delay_reduction > 1000:
            speed_ms -= bow_delay_reduction
    return max(MIN_HASTED_DELAY_MS, speed_ms) - BOW_TIMER_CORR_MS


def bow_swings_per_second(
    delay_tenths: int,
    spell_haste_bonus: int,
    overhaste_pct: int,
    use_quiver: bool,
    hundred_hands: int,
) -> float:
    ms = bow_ranged_timer_duration_ms(
        delay_tenths, spell_haste_bonus, overhaste_pct, use_quiver, hundred_hands
    )
    return 1000.0 / ms


def get_crit_chance(
    cls: str,
    aas: Mapping[str, Any],
    level: int,
    dex: int,
    use_bow: bool,
) -> float:
    dex_cap = min(dex, 255)
    over_cap = (dex - 255) / 400 if dex > 255 else 0
    crit_mult = int(aas.get("CriticalHitChance", 0) or 0)
    base = 0.0
    if cls == "Warrior" and level >= 12:
        base += 0.5 + dex_cap / 90 + over_cap
    elif cls == "Ranger" and use_bow and level > 16:
        base += 1.35 + dex_cap / 34 + over_cap * 2
    elif cls != "Warrior":
        if not crit_mult:
            return 0.0
        base += 0.275 + dex_cap / 150 + over_cap
    if crit_mult:
        base *= 1 + crit_mult / 100.0
    return min(1.0, base / 100.0)


def get_skill_base_damage_kick(skill_level: int) -> int:
    base = 3
    if skill_level >= 25:
        base += 1
    if skill_level >= 75:
        base += 1
    if skill_level >= 125:
        base += 1
    if skill_level >= 175:
        base += 1
    return base


def can_offhand_double_attack(da_skill: int, aas: Mapping[str, Any]) -> bool:
    return da_skill >= 150 or int(aas.get("GiveDoubleAttack", 0) or 0) > 0


def is_warrior_class(cls: str) -> bool:
    return cls in ("Warrior", "Paladin", "Shadow Knight")


@dataclass
class BuffEnv:
    """Haste and ATK inputs matching dps_calculator rows."""

    combined_haste_melee: int  # min(100, spell+haste buff) + overhaste; for melee delay
    spell_haste_for_bow: int  # uncapped spell haste input to bow timer (same as hastePct field)
    overhaste_pct: int
    worn_atk: int
    spell_atk_extra: int  # Pred/Tunare etc.
    atk_ferine: bool
    atk_ferocity: bool
    atk_pred_tunare: bool
    atk_vallon: bool
    use_fleeting_quiver: bool
    use_eagle_eye: bool
    ranger_stationary: bool
    use_trueshot: bool
    attack_from_front: bool


def offense_total(
    env: BuffEnv,
    offense_base: int,
) -> int:
    return (
        offense_base
        + env.worn_atk
        + env.spell_atk_extra
        + (140 if env.atk_ferine else 0)
        + (140 if env.atk_ferocity else 0)
        + (140 if env.atk_pred_tunare else 0)
        + (41 if env.atk_vallon else 0)
    )


def mob_front_avoidance_factor(mob_level: int, strike_through_pct: int) -> float:
    level = max(1, mob_level)
    parry_skill = min(level * 5, 230) if level > 6 else 0
    riposte_skill = min(level * 5, 225) if level > 11 else 0
    dodge_skill = min(level * 5, 190) if level > 10 else 0
    st = min(100, max(0, strike_through_pct)) / 100.0
    p_parry = min(100, (parry_skill + 100) // 50) / 100.0 if parry_skill else 0
    p_riposte = min(100, (riposte_skill + 100) // 55) / 100.0 if riposte_skill else 0
    p_dodge = min(100, (dodge_skill + 100) // 45) / 100.0 if dodge_skill else 0
    bypass = 1 - st
    return (1 - p_parry * bypass) * (1 - p_riposte * bypass) * (1 - p_dodge * bypass)


# Import threat helpers (same package when run from magelo)
def _import_melee_proc():
    from threat import melee_proc as mp

    return mp


def reference_mainhand_swings_for_threat(
    delay_tenths: int,
    threat_meta: Mapping[str, Any],
    dps_config: Mapping[str, Any],
) -> float:
    ref_ch = min(100, int(threat_meta.get("hastePct", 70))) + int(threat_meta.get("overhastePct", 0) or 0)
    eff = effective_delay(delay_tenths, ref_ch, False)
    base = swings_per_second(eff)
    ref_lv = int(threat_meta.get("level", 65))
    ref_da = float(threat_meta.get("doubleAttackChancePct", 0) or 0)
    mult = 1 + ref_da / 100.0
    if ref_lv >= 60:
        mult += 0.135
        fc = sum_warrior_flurry_chance(dps_config)
        mult += 0.135 * (fc / 100.0) * 1.1
    return base * mult


def reference_offhand_swings_for_threat(
    delay_tenths: int,
    threat_meta: Mapping[str, Any],
    dps_config: Mapping[str, Any],
) -> float:
    mp = _import_melee_proc()
    ref_ch = min(100, int(threat_meta.get("hastePct", 70))) + int(threat_meta.get("overhastePct", 0) or 0)
    eff = effective_delay(delay_tenths, ref_ch, False)
    ref_dw = float(threat_meta.get("dualWieldChancePct", 0) or 0)
    ref_da = float(threat_meta.get("doubleAttackChancePct", 0) or 0)
    w_cfg = (dps_config.get("classes") or {}).get("Warrior") or {}
    da_skill = int((w_cfg.get("skills") or {}).get("doubleAttack", 252))
    aas_w = build_aa_map(dps_config, "Warrior")
    offhand_da_mult = (1 + ref_da / 100.0) if can_offhand_double_attack(da_skill, aas_w) else 1.0
    return (10.0 / eff) * (ref_dw / 100.0) * offhand_da_mult


def get_proc_data(
    weapon_procs: Mapping[str, Any],
    item: Mapping[str, Any] | None,
    is_offhand: bool,
) -> dict[str, Any] | None:
    if not item or not item.get("name"):
        return None
    key = normalize_proc_name(str(item["name"]))
    data = weapon_procs.get(key)
    if not isinstance(data, dict):
        return None
    if is_offhand and (
        data.get("hatePerSecOH") is not None
        or data.get("procDpsOH") is not None
        or data.get("meleeHatePerSecOH") is not None
    ):
        return {
            "procName": data.get("procName"),
            "procDps": data.get("procDpsOH", data.get("procDps")),
            "hatePerSec": data.get("hatePerSecOH", data.get("hatePerSec")),
            "meleeHatePerSec": data.get("meleeHatePerSecOH", data.get("meleeHatePerSec")),
        }
    return dict(data)


def get_hate_per_sec_for_weapon(
    weapon_threat: Mapping[str, Any],
    weapon_procs: Mapping[str, Any],
    item: Mapping[str, Any] | None,
    is_offhand: bool,
) -> tuple[float, float]:
    if not item or not item.get("name"):
        return 0.0, 0.0
    key = normalize_proc_name(str(item["name"]))
    if key in weapon_threat and not str(key).startswith("_"):
        s = weapon_threat[key]
        if isinstance(s, dict):
            if is_offhand:
                return (
                    float(s.get("meleeHatePerSecOHServer") or 0),
                    float(s.get("hatePerSecOHServer") or 0),
                )
            return (
                float(s.get("meleeHatePerSecServer") or 0),
                float(s.get("hatePerSecServer") or 0),
            )
    pd = get_proc_data(weapon_procs, item, is_offhand)
    if pd:
        return float(pd.get("meleeHatePerSec") or 0), float(pd.get("hatePerSec") or 0)
    return 0.0, 0.0


def bard_melee_hate_mh_scale_from_warrior_table(
    weapon_dmg: int,
    level: int,
    delay_tenths: int,
    weapon_skill_str: str,
) -> float:
    from threat.melee_proc import client_damage_bonus_primary, is_two_hander_skill

    d = max(0, int(weapon_dmg))
    db = client_damage_bonus_primary(
        level, delay_tenths, is_two_hander=is_two_hander_skill(weapon_skill_str)
    )
    denom = d + db
    return d / denom if denom > 0 else 1.0


def compute_total_hate_per_sec(
    cls: str,
    weapon_mh: Mapping[str, Any] | None,
    weapon_oh: Mapping[str, Any] | None,
    use_2h: bool,
    env: BuffEnv,
    dps_config: Mapping[str, Any],
    weapon_procs: Mapping[str, Any],
    weapon_threat: Mapping[str, Any],
    threat_meta: Mapping[str, Any],
    level: int,
    dex: int,
) -> float:
    """Warrior-focused hate/sec; uses weapon_threat_server scaling like dps_calculator."""
    mp = _import_melee_proc()
    cfg = (dps_config.get("classes") or {}).get(cls) or {}
    aas = build_aa_map(dps_config, cls)
    dw_skill = int((cfg.get("skills") or {}).get("dualWield", 245))
    da_skill = int((cfg.get("skills") or {}).get("doubleAttack", 252))
    dw_pct = mp.dual_wield_chance_pct(dw_skill, level, int(aas.get("Ambidexterity", 0)))
    da_pct = mp.double_attack_chance_pct(da_skill, level, aas)
    flurry = float(aas.get("FlurryChance", 0) or 0)

    if not weapon_mh or int(weapon_mh.get("dmg") or 0) <= 0:
        return 0.0
    delay_mh = int(weapon_mh.get("atkDelay") or 40)
    combined = env.combined_haste_melee
    eff_mh = effective_delay(delay_mh, combined, False)
    base_sps_mh = swings_per_second(eff_mh)
    swings_mh = base_sps_mh * (1 + da_pct / 100.0)
    if cls in ("Warrior", "Monk") and level >= 60:
        triple_extra = 0.135
        flurry_extra = (0.135 * (flurry / 100.0) * 1.1) if cls == "Warrior" else 0.0
        swings_mh = base_sps_mh * (1 + da_pct / 100.0 + triple_extra + flurry_extra)
    if use_2h and weapon_mh and "2H" in str(weapon_mh.get("skill") or "") and aas.get("ExtraAttackChance"):
        swings_mh += base_sps_mh * float(aas.get("ExtraAttackChance", 0)) / 100.0

    key_mh = normalize_proc_name(str(weapon_mh.get("name") or ""))
    row_mh = weapon_threat.get(key_mh) if key_mh else None
    ref_swings_mh = reference_mainhand_swings_for_threat(delay_mh, threat_meta, dps_config)
    melee_hate_mh, proc_hate_mh = get_hate_per_sec_for_weapon(weapon_threat, weapon_procs, weapon_mh, False)
    if isinstance(row_mh, dict) and ref_swings_mh > 0:
        melee_base = float(row_mh.get("meleeHatePerSecServer") or melee_hate_mh)
        melee_hate_mh = melee_base * (swings_mh / ref_swings_mh)
        if cls == "Bard" and weapon_mh:
            melee_hate_mh *= bard_melee_hate_mh_scale_from_warrior_table(
                int(weapon_mh.get("dmg") or 0),
                level,
                delay_mh,
                str(weapon_mh.get("skill") or ""),
            )
        pr = int(row_mh.get("procRateDb") or 0)
        ref_ch = min(100, int(threat_meta.get("hastePct", 70))) + int(threat_meta.get("overhastePct", 0) or 0)
        ref_dex = int(threat_meta.get("dex", 255))
        ref_dw = float(threat_meta.get("dualWieldChancePct", 91.2))
        wpc_ref = min(
            1.0,
            mp.wpc_from_proc_rate(
                mp.get_proc_chance_fraction(
                    ref_dex,
                    delay_mh,
                    haste_pct=min(100, int(threat_meta.get("hastePct", 70))),
                    overhaste_pct=int(threat_meta.get("overhastePct", 0) or 0),
                    hand_is_secondary=False,
                    dual_wield_chance_pct=ref_dw,
                ),
                pr,
            ),
        )
        wpc_user = min(
            1.0,
            mp.wpc_from_proc_rate(
                mp.get_proc_chance_fraction(
                    dex,
                    delay_mh,
                    haste_pct=min(100, combined),
                    overhaste_pct=0,
                    hand_is_secondary=False,
                    dual_wield_chance_pct=dw_pct,
                ),
                pr,
            ),
        )
        wpc_ratio = wpc_user / wpc_ref if wpc_ref > 1e-9 else 1.0
        proc_base = float(
            row_mh.get("hatePerSecServerBard" if cls == "Bard" else "hatePerSecServer") or proc_hate_mh
        )
        if proc_base > 0:
            proc_hate_mh = proc_base * wpc_ratio
    swings_oh = 0.0
    melee_hate_oh = 0.0
    proc_hate_oh = 0.0
    if weapon_oh and not use_2h:
        delay_oh = int(weapon_oh.get("atkDelay") or 40)
        eff_oh = effective_delay(delay_oh, combined, False)
        offhand_da_mult = (1 + da_pct / 100.0) if can_offhand_double_attack(da_skill, aas) else 1.0
        swings_oh = (10.0 / eff_oh) * (dw_pct / 100.0) * offhand_da_mult
        key_oh = normalize_proc_name(str(weapon_oh.get("name") or ""))
        row_oh = weapon_threat.get(key_oh) if key_oh else None
        ref_swings_oh = reference_offhand_swings_for_threat(delay_oh, threat_meta, dps_config)
        mh2, ph2 = get_hate_per_sec_for_weapon(weapon_threat, weapon_procs, weapon_oh, True)
        melee_hate_oh, proc_hate_oh = mh2, ph2
        if isinstance(row_oh, dict) and ref_swings_oh > 0:
            melee_base_oh = float(row_oh.get("meleeHatePerSecOHServer") or melee_hate_oh)
            melee_hate_oh = melee_base_oh * (swings_oh / ref_swings_oh)
            pr = int(row_oh.get("procRateDb") or 0)
            wpc_ref = min(
                1.0,
                mp.wpc_from_proc_rate(
                    mp.get_proc_chance_fraction(
                        ref_dex,
                        delay_oh,
                        haste_pct=min(100, int(threat_meta.get("hastePct", 70))),
                        overhaste_pct=int(threat_meta.get("overhastePct", 0) or 0),
                        hand_is_secondary=True,
                        dual_wield_chance_pct=ref_dw,
                    ),
                    pr,
                ),
            )
            wpc_user = min(
                1.0,
                mp.wpc_from_proc_rate(
                    mp.get_proc_chance_fraction(
                        dex,
                        delay_oh,
                        haste_pct=min(100, combined),
                        overhaste_pct=0,
                        hand_is_secondary=True,
                        dual_wield_chance_pct=dw_pct,
                    ),
                    pr,
                ),
            )
            wpc_ratio = wpc_user / wpc_ref if wpc_ref > 1e-9 else 1.0
            proc_base_oh = float(
                row_oh.get("hatePerSecOHServerBard" if cls == "Bard" else "hatePerSecOHServer") or proc_hate_oh
            )
            if proc_base_oh > 0:
                proc_hate_oh = proc_base_oh * wpc_ratio

    return melee_hate_mh + melee_hate_oh + proc_hate_mh + proc_hate_oh


def compute_total_dps(
    cls: str,
    weapon_mh: Mapping[str, Any] | None,
    weapon_oh: Mapping[str, Any] | None,
    weapon_range: Mapping[str, Any] | None,
    weapon_ammo: Mapping[str, Any] | None,
    use_bow: bool,
    use_2h: bool,
    env: BuffEnv,
    dps_config: Mapping[str, Any],
    weapon_procs: Mapping[str, Any],
    level: int,
    mob_level: int,
    mob_ac: int,
) -> float:
    cfg = (dps_config.get("classes") or {}).get(cls) or {}
    aas = build_aa_map(dps_config, cls)
    str_ = min(305, int(cfg.get("str") or 255) + int(aas.get("StatBonus", 0) or 0))
    dex = min(305, int(cfg.get("dex") or 255) + int(aas.get("StatBonus", 0) or 0))

    mitigation = npc_mitigation(mob_level, mob_ac)
    avoidance = npc_avoidance(mob_level)
    offense_skill = int((cfg.get("skills") or {}).get("offense") or 252)
    da_skill = int((cfg.get("skills") or {}).get("doubleAttack") or 252)
    da_chance = get_double_attack_chance(da_skill, level, aas)

    weapon_for_skill = weapon_range if use_bow else weapon_mh
    skill_key = weapon_skill_to_config_key(
        str(weapon_for_skill.get("skill") if weapon_for_skill else "") or None,
        cls == "Ranger",
    )
    ws = int((cfg.get("skills") or {}).get(skill_key) or 252)
    accuracy = int(aas.get("AccuracyAll", 0) or 0)
    to_hit = get_to_hit(offense_skill, ws, accuracy)
    is_ranged_attack = use_bow and weapon_range is not None
    archery_bonus = EAGLE_EYE_ARCHERY_HIT_PCT if (cls == "Ranger" and use_bow and weapon_range and env.use_eagle_eye) else 0
    hit_pct = min(1.0, max(0.0, hit_chance(to_hit, avoidance, 0, archery_bonus)))
    if env.attack_from_front:
        st = int(aas.get("StrikeThrough", 0) or 0) if cls == "Warrior" else 0
        hit_pct *= mob_front_avoidance_factor(mob_level, st)

    is_ranger55 = cls == "Ranger" and level > 54
    offense_base = get_offense(ws, str_, dex, is_ranged_attack, is_ranger55)
    off = offense_total(env, offense_base)

    if use_bow and weapon_range:
        base_dmg_mh = int(weapon_range.get("dmg") or 0)
        if weapon_ammo and weapon_ammo.get("dmg"):
            base_dmg_mh += int(weapon_ammo.get("dmg") or 0)
        delay_mh = int(weapon_range.get("atkDelay") or 40)
        item_dmg_bonus = int(weapon_range.get("dmgBonus") or 0)
        damage_bonus_mh = 0
        roll_base_mh = base_dmg_mh
        if is_ranged_attack and cls == "Ranger" and aas.get("ArcheryDamageModifier"):
            roll_base_mh = int(roll_base_mh * (1 + int(aas.get("ArcheryDamageModifier", 0)) / 100.0))
        if is_ranged_attack and cls == "Ranger" and env.use_trueshot:
            roll_base_mh = int(roll_base_mh * (1 + TRUESHOT_ARCHERY_DAMAGE_PCT / 100.0))
        roll_part_mh = calc_melee_damage(roll_base_mh, off, mitigation, is_ranged_attack)
        if is_ranged_attack and cls == "Ranger" and env.ranger_stationary:
            roll_part_mh = int(roll_part_mh * 2)
        monk_mult_mh = roll_damage_multiplier_expected(off, level, cls == "Monk")
        dmg_per_swing_mh = int(roll_part_mh * monk_mult_mh) + damage_bonus_mh
        item_dmg_add_mh = 0
        base_swings_mh = bow_swings_per_second(
            delay_mh,
            env.spell_haste_for_bow,
            env.overhaste_pct,
            env.use_fleeting_quiver,
            0,
        )
        swings_mh = base_swings_mh
    else:
        if not weapon_mh:
            return 0.0
        base_dmg_mh = int(weapon_mh.get("dmg") or 0)
        delay_mh = int(weapon_mh.get("atkDelay") or 40)
        item_dmg_bonus = int(weapon_mh.get("dmgBonus") or 0)
        damage_bonus_mh = 0
        if is_warrior_class(cls):
            damage_bonus_mh = (
                get_damage_bonus_2h(level, delay_mh)
                if is_two_hander_item(weapon_mh)
                else get_damage_bonus_1h(level)
            )
        roll_part_mh = calc_melee_damage(base_dmg_mh, off, mitigation, False)
        monk_mult_mh = roll_damage_multiplier_expected(off, level, cls == "Monk")
        if use_2h and cls == "Warrior":
            scaled = 1 + (monk_mult_mh - 1) * WARRIOR_2H_MULT_SCALE
            dmg_per_swing_mh = int(roll_part_mh * scaled) + damage_bonus_mh + item_dmg_bonus
        else:
            dmg_per_swing_mh = int(roll_part_mh * monk_mult_mh) + damage_bonus_mh + item_dmg_bonus

        combined = env.combined_haste_melee
        eff_delay_mh = effective_delay(delay_mh, combined, False)
        base_sps_mh = swings_per_second(eff_delay_mh)
        swings_mh = base_sps_mh * (1 + da_chance / 100.0)
        if cls in ("Warrior", "Monk") and level >= 60:
            triple_extra = 0.135
            flurry_extra = (
                0.135 * (float(aas.get("FlurryChance", 0) or 0) / 100.0) * 1.1 if cls == "Warrior" else 0.0
            )
            swings_mh = base_sps_mh * (1 + da_chance / 100.0 + triple_extra + flurry_extra)
        if use_2h and weapon_mh and "2H" in str(weapon_mh.get("skill") or "") and aas.get("ExtraAttackChance"):
            swings_mh += base_sps_mh * float(aas.get("ExtraAttackChance", 0)) / 100.0
        item_dmg_add_mh = item_dmg_bonus

    dw_chance = (
        get_dual_wield_chance(int((cfg.get("skills") or {}).get("dualWield") or 252), level, aas)
        if (weapon_oh and not use_2h and not use_bow)
        else 0.0
    )
    if cls in ("Paladin", "Shadow Knight"):
        dw_chance = 0.0

    dmg_per_swing_oh = 0.0
    swings_oh = 0.0
    if weapon_oh and not use_2h and not use_bow:
        base_oh = int(weapon_oh.get("dmg") or 0)
        delay_oh = int(weapon_oh.get("atkDelay") or 40)
        eff_oh = effective_delay(delay_oh, env.combined_haste_melee, False)
        offhand_da_mult = (1 + da_chance / 100.0) if can_offhand_double_attack(da_skill, aas) else 1.0
        swings_oh = (10.0 / eff_oh) * (dw_chance / 100.0) * offhand_da_mult
        roll_oh = calc_melee_damage(base_oh, off, mitigation, False)
        mult_oh = roll_damage_multiplier_expected(off, level, cls == "Monk")
        item_oh_bonus = int(weapon_oh.get("dmgBonus") or 0)
        dmg_per_swing_oh = int(roll_oh * mult_oh) + item_oh_bonus

    melee_dps = hit_pct * (dmg_per_swing_mh * swings_mh + dmg_per_swing_oh * swings_oh)

    kick_dps = 0.0
    if cls == "Monk":
        kick_skill = int((cfg.get("skills") or {}).get("kick") or 252)
        kick_base = get_skill_base_damage_kick(kick_skill)
        off_kick = get_offense(kick_skill, str_, dex, False, False) + env.worn_atk + env.spell_atk_extra
        off_kick += (140 if env.atk_ferine else 0) + (140 if env.atk_ferocity else 0) + (140 if env.atk_pred_tunare else 0) + (41 if env.atk_vallon else 0)
        kick_dmg = calc_melee_damage(kick_base, off_kick, mitigation, False)
        kick_dmg = int(kick_dmg * roll_damage_multiplier_expected(off_kick, level, True))
        kick_dps = hit_pct * kick_dmg * (1.0 / 6.0)
        wu = float(aas.get("DoubleSpecialAttack", 0) or 0) / 100.0
        if wu > 0:
            kick_dps *= 1 + wu * (1 + wu / 4)

    backstab_dps = 0.0
    if cls == "Rogue" and weapon_mh and "Piercing" in str(weapon_mh.get("skill") or ""):
        backstab_skill = int((cfg.get("skills") or {}).get("backstab") or 252)
        backstab_base = ((backstab_skill * 0.02) + 2) * (int(weapon_mh.get("dmg") or 1))
        min_hit = level * 2 if level >= 60 else (level * 3 // 2 if level > 50 else level)
        backstab_dmg = max(min_hit, calc_melee_damage(int(backstab_base), off, mitigation, False))
        stabs = 2 if level > 54 else 1
        backstab_dps = hit_pct * backstab_dmg * (1.0 / 3.0) * stabs

    crit_chance = get_crit_chance(cls, aas, level, dex, use_bow)
    proc_dps_mh = 0.0
    proc_dps_oh = 0.0
    pd_mh = get_proc_data(weapon_procs, weapon_mh, False) if weapon_mh and not use_bow else None
    pd_oh = get_proc_data(weapon_procs, weapon_oh, True) if weapon_oh and not use_2h and not use_bow else None
    if pd_mh and pd_mh.get("procDps"):
        proc_dps_mh = float(pd_mh.get("procDps") or 0)
    if pd_oh and pd_oh.get("procDps"):
        proc_dps_oh = float(pd_oh.get("procDps") or 0)
    if use_bow:
        pd_r = get_proc_data(weapon_procs, weapon_range, False)
        if pd_r and pd_r.get("procDps"):
            proc_dps_mh = float(pd_r.get("procDps") or 0)

    total = (melee_dps + kick_dps + backstab_dps) * (1 + crit_chance) + proc_dps_mh + proc_dps_oh
    return float(total)


def make_env_buffed(item_haste: int, worn_atk: int) -> BuffEnv:
    combined = min(100, 70 + int(item_haste)) + 0
    return BuffEnv(
        combined_haste_melee=combined,
        spell_haste_for_bow=min(100, 70 + int(item_haste)),
        overhaste_pct=0,
        worn_atk=worn_atk,
        spell_atk_extra=140,
        atk_ferine=False,
        atk_ferocity=False,
        atk_pred_tunare=True,
        atk_vallon=False,
        use_fleeting_quiver=True,
        use_eagle_eye=True,
        ranger_stationary=True,
        use_trueshot=False,
        attack_from_front=False,
    )


def make_env_unbuffed(item_haste: int, worn_atk: int) -> BuffEnv:
    combined = min(100, int(item_haste)) + 0
    return BuffEnv(
        combined_haste_melee=combined,
        spell_haste_for_bow=min(100, int(item_haste)),
        overhaste_pct=0,
        worn_atk=worn_atk,
        spell_atk_extra=0,
        atk_ferine=False,
        atk_ferocity=False,
        atk_pred_tunare=False,
        atk_vallon=False,
        use_fleeting_quiver=True,
        use_eagle_eye=True,
        ranger_stationary=True,
        use_trueshot=False,
        attack_from_front=False,
    )


def item_by_id(item_stats: Mapping[str, Any], iid: str) -> dict[str, Any] | None:
    if not iid:
        return None
    ob = item_stats.get(str(iid))
    return ob if isinstance(ob, dict) else None


def inventory_id_set(char_inventory: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    for it in char_inventory or []:
        iid = it.get("item_id")
        if iid is not None and str(iid).strip():
            out.add(str(iid).strip())
    return out


def pick_first_owned_row(
    dual_rows: list[dict[str, Any]],
    two_h_rows: list[dict[str, Any]],
    owned: set[str],
) -> tuple[str, dict[str, Any] | None]:
    for row in dual_rows:
        mh = str(row.get("mh") or "")
        oh = str(row.get("oh") or "")
        if mh in owned and oh in owned:
            return ("dual_wield", row)
    for row in two_h_rows:
        mh = str(row.get("mh") or "")
        if mh in owned:
            return ("two_hand", row)
    return ("none", None)


def pick_ranger_rows(
    archery_list: list[dict[str, Any]],
    melee_dual: list[dict[str, Any]],
    melee_2h: list[dict[str, Any]],
    owned: set[str],
) -> tuple[dict[str, Any] | None, tuple[str, dict[str, Any] | None]]:
    arch_sel = None
    for row in archery_list:
        r = str(row.get("range") or "")
        ammo = row.get("ammo")
        need_ammo = ammo is not None and str(ammo).strip() != ""
        ok = r in owned and (not need_ammo or str(ammo) in owned)
        if ok:
            arch_sel = row
            break
    melee_mode, melee_row = pick_first_owned_row(melee_dual, melee_2h, owned)
    return arch_sel, (melee_mode, melee_row)


def compute_weapon_ranking_metrics(
    char_class: str,
    char_inventory: list[dict[str, Any]],
    worn_atk: int,
    item_haste: int,
    *,
    item_stats: Mapping[str, Any],
    presets: Mapping[str, Any],
    dps_config: Mapping[str, Any],
    weapon_procs: Mapping[str, Any],
    weapon_threat: Mapping[str, Any],
    threat_meta: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Returns weapon DPS / hate metrics for class rankings.
    focus_raw_buffed: value used for WeaponMetric normalization (hate for Warrior, blended DPS for Ranger, else DPS).
    """
    level = int(dps_config.get("levelCap") or 65)
    mob_level = level
    mob_ac = 200
    owned = inventory_id_set(char_inventory)
    cfg_dex = int(((dps_config.get("classes") or {}).get(char_class) or {}).get("dex") or 255)

    env_b = make_env_buffed(item_haste, worn_atk)
    env_u = make_env_unbuffed(item_haste, worn_atk)

    empty = {
        "weapon_preset_kind": None,
        "weapon_preset_label": None,
        "dps_buffed": None,
        "dps_unbuffed": None,
        "hate_per_sec_buffed": None,
        "hate_per_sec_unbuffed": None,
        "ranger_archery_dps_buffed": None,
        "ranger_archery_dps_unbuffed": None,
        "ranger_melee_dps_buffed": None,
        "ranger_melee_dps_unbuffed": None,
        "focus_raw_buffed": None,
    }

    if char_class == "Warrior":
        wpre = (presets.get("Warrior") or {})
        mode, row = pick_first_owned_row(
            list(wpre.get("dual_wield") or []),
            list(wpre.get("two_hand") or []),
            owned,
        )
        if mode == "none" or not row:
            return empty
        label = str(row.get("label") or "Warrior loadout")
        mh = item_by_id(item_stats, str(row.get("mh") or ""))
        use_2h = mode == "two_hand"
        oh = None if use_2h else item_by_id(item_stats, str(row.get("oh") or ""))
        if not mh:
            return empty
        hb = compute_total_hate_per_sec(
            "Warrior",
            mh,
            oh,
            use_2h,
            env_b,
            dps_config,
            weapon_procs,
            weapon_threat,
            threat_meta,
            level,
            cfg_dex,
        )
        hu = compute_total_hate_per_sec(
            "Warrior",
            mh,
            oh,
            use_2h,
            env_u,
            dps_config,
            weapon_procs,
            weapon_threat,
            threat_meta,
            level,
            cfg_dex,
        )
        return {
            "weapon_preset_kind": mode,
            "weapon_preset_label": label,
            "dps_buffed": None,
            "dps_unbuffed": None,
            "hate_per_sec_buffed": round(hb, 2),
            "hate_per_sec_unbuffed": round(hu, 2),
            "ranger_archery_dps_buffed": None,
            "ranger_archery_dps_unbuffed": None,
            "ranger_melee_dps_buffed": None,
            "ranger_melee_dps_unbuffed": None,
            "focus_raw_buffed": hb,
        }

    if char_class == "Ranger":
        rp = presets.get("Ranger") or {}
        arch_list = list(rp.get("archery") or [])
        melee_sec = rp.get("melee") or {}
        arch_sel, (melee_mode, melee_row) = pick_ranger_rows(
            arch_list,
            list(melee_sec.get("dual_wield") or []),
            list(melee_sec.get("two_hand") or []),
            owned,
        )
        blend = presets.get("ranger_blend") or {"archery": 0.7, "melee": 0.3}
        wa = float(blend.get("archery", 0.7))
        wm = float(blend.get("melee", 0.3))

        arch_b = arch_u = None
        if arch_sel:
            wr = item_by_id(item_stats, str(arch_sel.get("range") or ""))
            ammo_id = arch_sel.get("ammo")
            wa_it = item_by_id(item_stats, str(ammo_id)) if ammo_id else None
            if wr:
                arch_b = compute_total_dps(
                    "Ranger",
                    None,
                    None,
                    wr,
                    wa_it,
                    True,
                    False,
                    env_b,
                    dps_config,
                    weapon_procs,
                    level,
                    mob_level,
                    mob_ac,
                )
                arch_u = compute_total_dps(
                    "Ranger",
                    None,
                    None,
                    wr,
                    wa_it,
                    True,
                    False,
                    env_u,
                    dps_config,
                    weapon_procs,
                    level,
                    mob_level,
                    mob_ac,
                )

        mel_b = mel_u = None
        if melee_row and melee_mode != "none":
            mh = item_by_id(item_stats, str(melee_row.get("mh") or ""))
            use_2h = melee_mode == "two_hand"
            oh = None if use_2h else item_by_id(item_stats, str(melee_row.get("oh") or ""))
            if mh:
                mel_b = compute_total_dps(
                    "Ranger",
                    mh,
                    oh,
                    None,
                    None,
                    False,
                    use_2h,
                    env_b,
                    dps_config,
                    weapon_procs,
                    level,
                    mob_level,
                    mob_ac,
                )
                mel_u = compute_total_dps(
                    "Ranger",
                    mh,
                    oh,
                    None,
                    None,
                    False,
                    use_2h,
                    env_u,
                    dps_config,
                    weapon_procs,
                    level,
                    mob_level,
                    mob_ac,
                )

        parts_b = []
        parts_u = []
        if arch_b is not None:
            parts_b.append(wa * arch_b)
            parts_u.append(wa * arch_u if arch_u is not None else 0)
        if mel_b is not None:
            parts_b.append(wm * mel_b)
            parts_u.append(wm * mel_u if mel_u is not None else 0)
        focus_raw = sum(parts_b) if parts_b else None
        focus_raw_u = sum(parts_u) if parts_u else None

        label_parts = []
        if arch_sel:
            label_parts.append(str(arch_sel.get("label") or "Archery"))
        if melee_row:
            label_parts.append(str(melee_row.get("label") or "Melee"))
        lbl = " + ".join(label_parts) if label_parts else None

        return {
            "weapon_preset_kind": "ranger_mixed",
            "weapon_preset_label": lbl,
            "dps_buffed": round(focus_raw, 2) if focus_raw is not None else None,
            "dps_unbuffed": round(focus_raw_u, 2) if focus_raw_u is not None else None,
            "hate_per_sec_buffed": None,
            "hate_per_sec_unbuffed": None,
            "ranger_archery_dps_buffed": round(arch_b, 2) if arch_b is not None else None,
            "ranger_archery_dps_unbuffed": round(arch_u, 2) if arch_u is not None else None,
            "ranger_melee_dps_buffed": round(mel_b, 2) if mel_b is not None else None,
            "ranger_melee_dps_unbuffed": round(mel_u, 2) if mel_u is not None else None,
            "focus_raw_buffed": focus_raw,
        }

    if char_class not in ("Rogue", "Monk", "Beastlord", "Bard"):
        return empty

    wpre = (presets.get(char_class) or {})
    mode, row = pick_first_owned_row(
        list(wpre.get("dual_wield") or []),
        list(wpre.get("two_hand") or []),
        owned,
    )
    if mode == "none" or not row:
        return empty
    label = str(row.get("label") or char_class)
    mh = item_by_id(item_stats, str(row.get("mh") or ""))
    use_2h = mode == "two_hand"
    oh = None if use_2h else item_by_id(item_stats, str(row.get("oh") or ""))
    if not mh:
        return empty

    db = compute_total_dps(
        char_class,
        mh,
        oh,
        None,
        None,
        False,
        use_2h,
        env_b,
        dps_config,
        weapon_procs,
        level,
        mob_level,
        mob_ac,
    )
    du = compute_total_dps(
        char_class,
        mh,
        oh,
        None,
        None,
        False,
        use_2h,
        env_u,
        dps_config,
        weapon_procs,
        level,
        mob_level,
        mob_ac,
    )
    return {
        "weapon_preset_kind": mode,
        "weapon_preset_label": label,
        "dps_buffed": round(db, 2),
        "dps_unbuffed": round(du, 2),
        "hate_per_sec_buffed": None,
        "hate_per_sec_unbuffed": None,
        "ranger_archery_dps_buffed": None,
        "ranger_archery_dps_unbuffed": None,
        "ranger_melee_dps_buffed": None,
        "ranger_melee_dps_unbuffed": None,
        "focus_raw_buffed": db,
    }
