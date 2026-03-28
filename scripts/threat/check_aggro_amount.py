"""Port of Mob::CheckAggroAmount (aggro.cpp) for offensive spell hate."""

from __future__ import annotations

from typing import Any, Mapping

from .spell_effects import (
    SE_AllStats,
    SE_Amnesia,
    SE_ArmorClass,
    SE_AttackSpeed,
    SE_AttackSpeed2,
    SE_AttackSpeed3,
    SE_AvoidMeleeChance,
    SE_Accuracy,
    SE_AGI,
    SE_ATK,
    SE_Blind,
    SE_CancelMagic,
    SE_CastingLevel,
    SE_CHA,
    SE_Charm,
    SE_CriticalHitChance,
    SE_CurrentEndurance,
    SE_CurrentHP,
    SE_CurrentHPOnce,
    SE_CurrentMana,
    SE_DamageModifier,
    SE_DamageShield,
    SE_Destroy,
    SE_DEX,
    SE_DispelDetrimental,
    SE_DodgeChance,
    SE_DoubleAttackChance,
    SE_DualWieldChance,
    SE_Fear,
    SE_Harmony,
    SE_HitChance,
    SE_IncreaseArchery,
    SE_IncreaseBlockChance,
    SE_InstantHate,
    SE_INT,
    SE_Silence,
    SE_ManaPool,
    SE_MeleeMitigation,
    SE_MeleeSkillCheck,
    SE_Mez,
    SE_MinDamageModifier,
    SE_MovementSpeed,
    SE_ParryChance,
    SE_PoisonCounter,
    SE_ResistAll,
    SE_ResistCold,
    SE_ResistDisease,
    SE_ResistFire,
    SE_ResistMagic,
    SE_ResistPoison,
    SE_ReverseDS,
    SE_RiposteChance,
    SE_Root,
    SE_SpellDamageShield,
    SE_SpinTarget,
    SE_STA,
    SE_STR,
    SE_Stun,
    SE_WIS,
    SE_DiseaseCounter,
    SPELL_MANABURN,
    UNUSED_EFFECT,
)
from .spell_formula import calc_spell_effect_value_formula


def _effect_val(spell: Mapping[str, Any], slot: int, spell_id: int, caster_level: int) -> int:
    return calc_spell_effect_value_formula(
        int(spell["formula"][slot]),
        int(spell["base"][slot]),
        int(spell["max"][slot]),
        caster_level,
        spell_id,
    )


def is_slow_spell(spell: Mapping[str, Any]) -> bool:
    """common/spdat.cpp IsSlowSpell."""
    for i in range(12):
        eid = int(spell["effectid"][i])
        if eid == SE_AttackSpeed and int(spell["base"][i]) < 100:
            return True
    return False


def can_class_cast_spell(spell: Mapping[str, Any], class_id_1based: int) -> bool:
    """zone/mob.h CanClassCastSpell (1=Warrior)."""
    if int(spell.get("not_player_spell") or 0):
        return False
    classes = spell["classes"]
    idx = class_id_1based - 1
    if idx < 0 or idx >= len(classes):
        return False
    return int(classes[idx]) < 255


def check_aggro_amount(
    spell: Mapping[str, Any],
    *,
    caster_level: int = 65,
    target_max_hp: int = 1_000_000,
    class_id: int = 1,
    is_pet: bool = False,
    is_bard: bool = False,
    is_weapon_proc: bool = True,
    shadows_of_luclin_disease_rule: bool = False,
    scars_of_velious_epic_hate: bool = False,
    spell_aggro_mod: int = 100,
    hate_mod_bonus: int = 0,
    focus_spell_hate_mod: int = 0,
    skip_belly_caster_rule: bool = True,
    target_level: int = 65,
) -> int:
    """
    Return spell hate added to hatelist (before melee CommonDamage extras).

    When modeling weapon procs, pass is_weapon_proc=True so the 400 non-damage cap is not applied
    (mirrors equipped proc matching GetWeaponEffectID on TAKP).
    """
    spell_id = int(spell["id"])
    non_damage_hate = 0
    instant_hate = 0
    damage = 0

    thp = max(375, target_max_hp)
    standard_spell_hate = min(1200, thp // 15)

    for o in range(12):
        eid = int(spell["effectid"][o])
        if eid == UNUSED_EFFECT or eid < 0:
            continue

        if eid in (SE_CurrentHPOnce, SE_CurrentHP):
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                damage -= val
                if spell_id == SPELL_MANABURN:
                    damage = -1
            continue

        if eid == SE_MovementSpeed:
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += standard_spell_hate
            continue

        if eid in (SE_AttackSpeed, SE_AttackSpeed2, SE_AttackSpeed3):
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 100:
                non_damage_hate += standard_spell_hate
            continue

        if eid in (SE_Stun, SE_Blind, SE_Mez, SE_Charm, SE_Fear):
            non_damage_hate += standard_spell_hate
            continue

        if eid == SE_ArmorClass:
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += standard_spell_hate
            continue

        if eid == SE_DiseaseCounter:
            if not shadows_of_luclin_disease_rule:
                if is_slow_spell(spell):
                    pass
                else:
                    non_damage_hate += standard_spell_hate
            continue

        if eid == SE_PoisonCounter:
            non_damage_hate += standard_spell_hate
            continue

        if eid == SE_Root:
            non_damage_hate += 10
            continue

        if eid in (
            SE_ResistMagic,
            SE_ResistFire,
            SE_ResistCold,
            SE_ResistPoison,
            SE_ResistDisease,
            SE_STR,
            SE_STA,
            SE_DEX,
            SE_AGI,
            SE_INT,
            SE_WIS,
            SE_CHA,
            SE_ATK,
        ):
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += 10
            continue

        if eid == SE_ResistAll:
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += 50
            continue

        if eid == SE_AllStats:
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += 70
            continue

        if eid in (SE_SpinTarget, SE_Amnesia, SE_Silence, SE_Destroy):
            non_damage_hate += standard_spell_hate
            continue

        if eid in (
            SE_Harmony,
            SE_CastingLevel,
            SE_MeleeMitigation,
            SE_CriticalHitChance,
            SE_AvoidMeleeChance,
            SE_RiposteChance,
            SE_DodgeChance,
            SE_ParryChance,
            SE_DualWieldChance,
            SE_DoubleAttackChance,
            SE_MeleeSkillCheck,
            SE_HitChance,
            SE_IncreaseArchery,
            SE_DamageModifier,
            SE_MinDamageModifier,
            SE_IncreaseBlockChance,
            SE_Accuracy,
            SE_DamageShield,
            SE_SpellDamageShield,
            SE_ReverseDS,
        ):
            non_damage_hate += caster_level * 2
            continue

        if eid in (SE_CurrentMana, SE_ManaPool, SE_CurrentEndurance):
            val = _effect_val(spell, o, spell_id, caster_level)
            if val < 0:
                non_damage_hate += 10
            continue

        if eid in (SE_CancelMagic, SE_DispelDetrimental):
            non_damage_hate += 1
            continue

        if eid == SE_InstantHate:
            instant_hate += _effect_val(spell, o, spell_id, caster_level)
            # Pre-SoV warrior epic procs: instant hate replaced by standardSpellHate
            if spell_id in (1935, 1933) and not scars_of_velious_epic_hate:
                instant_hate = standard_spell_hate
            continue

    hate_added = int(spell.get("hate_added") or 0)
    if hate_added > 0:
        non_damage_hate = hate_added

    if is_pet and non_damage_hate > 100:
        non_damage_hate = 100

    if not can_class_cast_spell(spell, class_id) and non_damage_hate > 400:
        if not is_weapon_proc:
            non_damage_hate = 400

    if is_bard:
        if damage + non_damage_hate > 40:
            non_damage_hate = 0
        elif non_damage_hate > 40:
            if target_level >= 20 or caster_level >= 20:
                non_damage_hate = 40

    non_damage_hate += instant_hate
    combined = non_damage_hate + damage

    if combined > 0:
        hate_mult = spell_aggro_mod + focus_spell_hate_mod + hate_mod_bonus
        combined = (combined * hate_mult) // 100

    if not skip_belly_caster_rule:
        resist = int(spell.get("resisttype") or 0)
        if resist != 0:
            return 0

    return int(combined)
