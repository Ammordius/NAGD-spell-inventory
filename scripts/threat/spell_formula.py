"""Port of Mob::CalcSpellEffectValue_formula (spell_effects.cpp), ticsremaining=0 path."""

from __future__ import annotations

from .spell_effects import SPELL_HARM_TOUCH, SPELL_HARM_TOUCH2, SPELL_IMP_HARM_TOUCH


def calc_spell_effect_value_formula(
    formula: int,
    base: int,
    maxv: int,
    caster_level: int,
    spell_id: int,
    *,
    ticsremaining: int = 0,
) -> int:
    result = 0
    updownsign = 1
    ubase = base if base >= 0 else -base

    if maxv < base and maxv != 0:
        updownsign = -1
    else:
        updownsign = 1

    f = formula
    if f in (0, 100):
        result = ubase
    elif f == 101:
        result = updownsign * (ubase + (caster_level // 2))
    elif f == 102:
        result = updownsign * (ubase + caster_level)
    elif f == 103:
        result = updownsign * (ubase + (caster_level * 2))
    elif f == 104:
        result = updownsign * (ubase + (caster_level * 3))
    elif f == 105:
        result = updownsign * (ubase + (caster_level * 4))
    elif f == 107:
        result = updownsign * ubase if ticsremaining <= 0 else updownsign * ubase  # simplified
    elif f == 108:
        result = updownsign * ubase if ticsremaining <= 0 else updownsign * ubase
    elif f == 109:
        result = updownsign * (ubase + (caster_level // 4))
    elif f == 110:
        result = updownsign * (ubase + (caster_level // 6))
    elif f == 111:
        result = updownsign * (ubase + 6 * (caster_level - 16))
    elif f == 112:
        result = updownsign * (ubase + 8 * (caster_level - 24))
    elif f == 113:
        result = updownsign * (ubase + 10 * (caster_level - 34))
    elif f == 114:
        result = updownsign * (ubase + 15 * (caster_level - 44))
    elif f == 115:
        result = ubase
        if caster_level > 15:
            result += 7 * (caster_level - 15)
    elif f == 116:
        result = ubase
        if caster_level > 24:
            result += 10 * (caster_level - 24)
    elif f == 117:
        result = ubase
        if caster_level > 34:
            result += 13 * (caster_level - 34)
    elif f == 118:
        result = ubase
        if caster_level > 44:
            result += 20 * (caster_level - 44)
    elif f == 119:
        result = ubase + (caster_level // 8)
    elif f == 120:
        result = updownsign * ubase
    elif f == 121:
        result = ubase + (caster_level // 3)
    elif f == 122:
        result = updownsign * ubase
    elif f == 123:
        # Random between ubase and abs(max); use midpoint for deterministic threat estimates
        lo, hi = ubase, abs(maxv)
        if lo > hi:
            lo, hi = hi, lo
        result = (lo + hi) // 2
    elif f == 124:
        result = ubase
        if caster_level > 50:
            result += updownsign * (caster_level - 50)
    elif f == 125:
        result = ubase
        if caster_level > 50:
            result += updownsign * 2 * (caster_level - 50)
    elif f == 126:
        result = ubase
        if caster_level > 50:
            result += updownsign * 3 * (caster_level - 50)
    elif f == 127:
        result = ubase
        if caster_level > 50:
            result += updownsign * 4 * (caster_level - 50)
    elif f == 128:
        result = ubase
        if caster_level > 50:
            result += updownsign * 5 * (caster_level - 50)
    elif f == 129:
        result = ubase
        if caster_level > 50:
            result += updownsign * 10 * (caster_level - 50)
    elif f == 130:
        result = ubase
        if caster_level > 50:
            result += updownsign * 15 * (caster_level - 50)
    elif f == 131:
        result = ubase
        if caster_level > 50:
            result += updownsign * 20 * (caster_level - 50)
    elif f == 150:
        if caster_level > 50:
            result = 10
        elif caster_level > 45:
            result = 5 + caster_level - 45
        elif caster_level > 40:
            result = 5
        elif caster_level > 34:
            result = 4
        else:
            result = 3
    elif f in (201, 202, 203, 204, 205):
        result = maxv
    else:
        if f < 100:
            adj_formula = f
            if spell_id == SPELL_HARM_TOUCH2:
                adj_formula = 10
            result = ubase + (caster_level * adj_formula)
            if spell_id in (SPELL_HARM_TOUCH, SPELL_HARM_TOUCH2, SPELL_IMP_HARM_TOUCH):
                if caster_level > 40:
                    ht_bonus = 20 * caster_level - 40
                    if ht_bonus > 400:
                        ht_bonus = 400
                    result += ht_bonus
        else:
            result = ubase

    oresult = result
    if maxv != 0:
        if updownsign == 1:
            if result > maxv:
                result = maxv
        else:
            if result < maxv:
                result = maxv

    if base < 0 and result > 0:
        result *= -1
    return int(result)
