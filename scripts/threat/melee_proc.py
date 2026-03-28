"""Melee hate per swing (attack.cpp) and weapon proc chance (GetProcChance / TryWeaponProc)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def is_two_hander_skill(skill: str | None) -> bool:
    if not skill:
        return False
    s = skill.upper()
    return "2H" in s


def client_damage_bonus_primary(level: int, delay: int, *, is_two_hander: bool) -> int:
    """Client::GetDamageBonus (attack.cpp) — Warrior-class melee; used for primary-hand hate only."""
    if level < 28:
        return 0
    bonus = 1 + (level - 28) // 3
    if not is_two_hander:
        return bonus
    if delay <= 27:
        return bonus + 1
    if level > 29:
        level_bonus = (level - 30) // 5 + 1
        if level > 50:
            level_bonus += 1
            level_bonus2 = level - 50
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


# RuleI(Combat, MinHastedDelay) — zone/common/ruletypes.h
MIN_HASTED_DELAY_MS = 400


def attack_timer_duration_ms(
    delay_tenths: int,
    haste_pct: int,
    overhaste_pct: int = 0,
    *,
    hundred_hands: int = 0,
) -> int:
    """Client::SetAttackTimer melee timer duration (ms), then Mob::GetWeaponSpeedbyHand min clamp."""
    combined = min(100, int(haste_pct)) + int(overhaste_pct)
    haste_mod = (100 + combined) / 100.0
    delay_f = float(delay_tenths)
    inner = delay_f / haste_mod + (float(hundred_hands) / 100.0) * delay_f
    speed_ms = int(inner * 100.0)
    return max(MIN_HASTED_DELAY_MS, speed_ms)


def proc_weapon_speed_units(duration_ms: int) -> float:
    """GetProcChance: weapon_speed = GetWeaponSpeedbyHand(hand) / 100.0 (after min-delay clamp)."""
    return duration_ms / 100.0


def get_proc_chance_fraction(
    dex: int,
    delay_tenths: int,
    *,
    haste_pct: int,
    overhaste_pct: int = 0,
    hand_is_secondary: bool,
    dual_wield_chance_pct: float,
    hundred_hands: int = 0,
) -> float:
    """Mob::GetProcChance — success probability per TryProcs roll (0–1+ before Roll cap)."""
    dur = attack_timer_duration_ms(
        delay_tenths, haste_pct, overhaste_pct, hundred_hands=hundred_hands
    )
    weapon_speed = proc_weapon_speed_units(dur)
    d = float(min(dex, 255))
    chance = (0.0004166667 + 1.1437908496732e-5 * d) * weapon_speed
    if hand_is_secondary:
        if dual_wield_chance_pct <= 0:
            return 0.0
        chance *= 50.0 / dual_wield_chance_pct
    return float(chance)


def mainhand_proc_rolls_per_second(
    delay_tenths: int,
    haste_pct: int,
    overhaste_pct: int = 0,
    *,
    hundred_hands: int = 0,
) -> float:
    """One weapon proc roll per primary attack timer tick (client_process TryProcs before Attack)."""
    dur = attack_timer_duration_ms(
        delay_tenths, haste_pct, overhaste_pct, hundred_hands=hundred_hands
    )
    return 1000.0 / float(dur)


def offhand_proc_rolls_per_second(
    delay_tenths: int,
    haste_pct: int,
    overhaste_pct: int = 0,
    *,
    dw_chance_pct: float,
    hundred_hands: int = 0,
) -> float:
    """Offhand: one roll per offhand timer tick when dual wield succeeds."""
    return mainhand_proc_rolls_per_second(
        delay_tenths, haste_pct, overhaste_pct, hundred_hands=hundred_hands
    ) * (float(dw_chance_pct) / 100.0)


def dual_wield_chance_pct(dual_wield_skill: int, level: int, ambidexterity: int) -> float:
    """Matches dps_calculator.html getDualWieldChance."""
    return (dual_wield_skill + level + ambidexterity) * 100.0 / 375.0


def wpc_from_proc_rate(base_chance: float, proc_rate_from_db: int) -> float:
    """TryWeaponProc: WPC = GetProcChance * (100 + ProcRate) / 100"""
    return base_chance * (100 + int(proc_rate_from_db)) / 100.0


def warrior_aa_map(dps_config_path: Path) -> dict[str, int]:
    """Sum Warrior AA numeric bonuses from data/dps_config.json."""
    data = json.loads(dps_config_path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for aa in data.get("classes", {}).get("Warrior", {}).get("aas", []):
        for k, v in (aa.get("bonuses") or {}).items():
            if isinstance(v, (int, float)):
                out[k] = out.get(k, 0) + int(v)
    return out


def double_attack_chance_pct(double_attack_skill: int, level: int, aas: Mapping[str, Any]) -> float:
    """dps_calculator getDoubleAttackChance."""
    chance = float(double_attack_skill)
    if chance > 0:
        chance += level
    chance += float(aas.get("GiveDoubleAttack", 0) or 0) * 5
    chance += chance * float(aas.get("DoubleAttackChance", 0) or 0) / 100.0
    return min(100.0, chance / 5.0)


def effective_delay_tenths(delay: int, haste_pct: int, overhaste_pct: int) -> int:
    combined = min(100, int(haste_pct)) + int(overhaste_pct)
    reduced = int(delay * 100 / (100 + combined))
    return max(4, reduced)


def swings_per_second_mh(
    delay: int,
    haste_pct: int,
    overhaste_pct: int,
    *,
    da_chance_pct: float,
    level: int,
    flurry_chance: float,
) -> float:
    eff = effective_delay_tenths(delay, haste_pct, overhaste_pct)
    base = 10.0 / eff
    triple_extra = 0.135 if level >= 60 else 0.0
    flurry_extra = 0.135 * (flurry_chance / 100.0) * 1.1 if level >= 60 else 0.0
    return base * (1.0 + da_chance_pct / 100.0 + triple_extra + flurry_extra)


def swings_per_second_oh(
    delay: int,
    haste_pct: int,
    overhaste_pct: int,
    *,
    dw_chance_pct: float,
    da_skill: int,
    aas: Mapping[str, Any],
    level: int = 65,
) -> float:
    eff = effective_delay_tenths(delay, haste_pct, overhaste_pct)
    da = double_attack_chance_pct(da_skill, level, aas) if da_skill >= 150 or (aas.get("GiveDoubleAttack", 0) or 0) > 0 else 0.0
    offhand_da_mult = 1.0 + da / 100.0
    return (10.0 / eff) * (dw_chance_pct / 100.0) * offhand_da_mult


def melee_hate_per_swing_primary(
    weapon_dmg: int,
    level: int,
    atk_delay: int,
    skill: str | None,
    *,
    is_warrior_class_for_bonus: bool = True,
) -> int:
    """Hate added per primary swing (hit or miss): baseDamage + GetDamageBonus."""
    base = int(weapon_dmg)
    if not is_warrior_class_for_bonus:
        return base
    db = client_damage_bonus_primary(level, atk_delay, is_two_hander=is_two_hander_skill(skill))
    return base + db


def melee_hate_per_swing_offhand(weapon_dmg: int) -> int:
    """Offhand: no character damage bonus to hate (attack.cpp)."""
    return int(weapon_dmg)
