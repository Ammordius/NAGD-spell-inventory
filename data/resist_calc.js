/**
 * TAKP Spell Land Rate — port of Mob::CheckResistSpell (NPC target, client caster, PoP-on).
 * Exact probabilities over rolls 0..200 (201 outcomes).
 */
(function (global) {
  'use strict';

  const RESIST_FALL_OFF = 67;
  const ROLL_MAX = 200;
  const ROLL_COUNT = ROLL_MAX + 1; // 0..200

  const RESIST_TYPE = {
    0: 'Unresistable',
    1: 'MR',
    2: 'FR',
    3: 'CR',
    4: 'PR',
    5: 'DR',
  };

  const RESIST_KEY = { 1: 'MR', 2: 'FR', 3: 'CR', 4: 'PR', 5: 'DR' };

  /** C++ toward-zero integer division. */
  function cTruncDiv(a, b) {
    return Math.trunc(a / b);
  }

  /**
   * Apply instrument mod: effect * mod / 10 where mod is e.g. 31 for 3.1x.
   * @param {number} base
   * @param {number} drumMod e.g. 3.1
   */
  function applyInstrumentMod(base, drumMod) {
    const mod = Math.round(drumMod * 10); // 3.1 -> 31
    return cTruncDiv(base * mod, 10);
  }

  /**
   * Sum debuff deltas for one resist key, applying instrument mod when flagged.
   * @param {Array} activeDebuffs list of {deltas, instrumentModdable}
   * @param {string} resistKey MR|FR|CR|DR|PR
   * @param {number} drumMod
   */
  function sumDebuffDelta(activeDebuffs, resistKey, drumMod) {
    let total = 0;
    for (const d of activeDebuffs) {
      const raw = (d.deltas && d.deltas[resistKey]) || 0;
      if (!raw) continue;
      total += d.instrumentModdable ? applyInstrumentMod(raw, drumMod) : raw;
    }
    return total;
  }

  /**
   * Level modifier for NPC target vs client caster (PoP-on, non-classic).
   */
  function computeLevelMod(casterLevel, targetLevel, isDirectDamage) {
    let leveldiff = targetLevel - casterLevel;
    let temp_level_diff = leveldiff;

    if (targetLevel >= RESIST_FALL_OFF) {
      const a = RESIST_FALL_OFF - 1 - casterLevel;
      temp_level_diff = a > 0 ? a : 0;
    }

    // NPC: floor at -9
    if (temp_level_diff < -9) temp_level_diff = -9;

    let level_mod = cTruncDiv(temp_level_diff * temp_level_diff, 2);
    if (temp_level_diff < 0) level_mod = -level_mod;

    // High-level NPC bump
    if (casterLevel < 50) {
      const bump_level = casterLevel + 4 + cTruncDiv(casterLevel, 6);
      if (targetLevel >= bump_level) {
        level_mod += 70 + casterLevel * 6;
      }
    } else {
      if (casterLevel < 64) {
        if (leveldiff >= 13) level_mod = casterLevel * 5;
      } else {
        if (leveldiff >= 16) level_mod = casterLevel * 5;
      }
    }

    // Direct damage extra
    if (isDirectDamage) {
      let dd_temp;
      if (targetLevel >= RESIST_FALL_OFF) {
        dd_temp = RESIST_FALL_OFF - 1 - casterLevel;
        if (dd_temp < 0) dd_temp = 0;
      } else {
        dd_temp = targetLevel - casterLevel;
      }
      if (dd_temp > 0 && targetLevel >= 17) {
        level_mod += 2 * dd_temp;
      }
    }

    return level_mod;
  }

  /**
   * Build resist_chance (pre-roll) for NPC target.
   */
  function computeResistChance(opts) {
    const {
      casterLevel,
      targetLevel,
      targetResists, // {MR,FR,CR,DR,PR}
      spell, // {resisttype, resistDiff, harmony, mez, charm, directDamage, partialCapable}
      debuffDelta, // number already summed for this resist type
      tickSave,
      cha,
      casterClass, // 'Enchanter' etc.
      manualAdjust,
    } = opts;

    if (spell.resisttype === 0 && !spell.harmony) {
      return {
        resistChance: null,
        unresistable: true,
        targetResist: 0,
        levelMod: 0,
        resistDiff: spell.resistDiff || 0,
        debuffDelta: 0,
        effectiveCasterLevel: casterLevel,
      };
    }

    let effectiveCasterLevel = casterLevel;
    if (tickSave) effectiveCasterLevel += 4;

    let resistKey = RESIST_KEY[spell.resisttype] || 'MR';
    let target_resist = (targetResists[resistKey] || 0) + (debuffDelta || 0);

    // Lull/harmony/pacify: force resist to 15 (PoP+)
    if (spell.harmony) {
      target_resist = 15;
    }

    let resist_modifier = spell.resistDiff || 0;
    if (manualAdjust) resist_modifier += manualAdjust;

    // Enchanter CHA for mez/charm (initial cast only, not tick_save)
    if (!tickSave && casterClass === 'Enchanter' && (spell.mez || spell.charm)) {
      const c = cha || 0;
      if (c > 75) {
        resist_modifier -= cTruncDiv(c - 75, 8);
      }
    }

    const level_mod = computeLevelMod(
      effectiveCasterLevel,
      targetLevel,
      !!spell.directDamage
    );

    let resist_chance = target_resist + level_mod + resist_modifier;

    // Tick save floor
    if (tickSave) {
      if (spell.charm) {
        if (resist_chance < 5) resist_chance = 5;
      } else if (spell.root) {
        if (resist_chance < 5) resist_chance = 5;
      } else if (resist_chance < 5) {
        resist_chance = 5;
      }
    }

    return {
      resistChance: resist_chance,
      unresistable: false,
      targetResist: target_resist,
      levelMod: level_mod,
      resistDiff: resist_modifier,
      debuffDelta: debuffDelta || 0,
      resistKey,
      effectiveCasterLevel,
    };
  }

  /**
   * Partial effectiveness for one failed roll (NPC target).
   * Returns 0..100 (100 = full land from partial path edge cases).
   */
  function partialEffectiveness(resistChance, roll, casterLevel, targetLevel) {
    let chance = resistChance;
    if (chance === 0) return 0;

    let partial_modifier = cTruncDiv(150 * (chance - roll), chance);

    if (targetLevel > casterLevel && targetLevel >= 17 && casterLevel <= 50) {
      partial_modifier += 5;
    }
    if (targetLevel >= 30 && casterLevel <= 50) {
      partial_modifier += casterLevel - 25;
    }
    if (targetLevel < 15) {
      partial_modifier -= 5;
    }

    if (partial_modifier <= 0) return 100;
    if (partial_modifier >= 100) return 0;
    return 100 - partial_modifier;
  }

  /**
   * Exact outcomes over rolls 0..200.
   */
  function computeLandRates(resistChance, spell, casterLevel, targetLevel) {
    if (resistChance === null || spell.resisttype === 0 && !spell.harmony) {
      return {
        fullLandPct: 100,
        fullResistPct: 0,
        partialPct: 0,
        expectedEffectiveness: 100,
        scale: 'unresistable',
      };
    }

    const partialCapable = !!spell.partialCapable;
    let fullLand = 0;
    let fullResist = 0;
    let partial = 0;
    let effectivenessSum = 0;

    for (let roll = 0; roll <= ROLL_MAX; roll++) {
      if (roll > resistChance) {
        fullLand += 1;
        effectivenessSum += 100;
      } else if (!partialCapable || resistChance === 0) {
        fullResist += 1;
        // effectiveness 0
      } else {
        const eff = partialEffectiveness(resistChance, roll, casterLevel, targetLevel);
        if (eff <= 0) {
          fullResist += 1;
        } else if (eff >= 100) {
          fullLand += 1;
          effectivenessSum += 100;
        } else {
          partial += 1;
          effectivenessSum += eff;
        }
      }
    }

    return {
      fullLandPct: (100 * fullLand) / ROLL_COUNT,
      fullResistPct: (100 * fullResist) / ROLL_COUNT,
      partialPct: (100 * partial) / ROLL_COUNT,
      expectedEffectiveness: effectivenessSum / ROLL_COUNT,
      scale: partialCapable ? '600' : '200',
      fullLandCount: fullLand,
      fullResistCount: fullResist,
      partialCount: partial,
    };
  }

  function evaluate(opts) {
    const chanceInfo = computeResistChance(opts);
    const spell = opts.spell;
    if (chanceInfo.unresistable) {
      return {
        ...chanceInfo,
        rates: {
          fullLandPct: 100,
          fullResistPct: 0,
          partialPct: 0,
          expectedEffectiveness: 100,
          scale: 'unresistable',
        },
      };
    }
    const rates = computeLandRates(
      chanceInfo.resistChance,
      spell,
      chanceInfo.effectiveCasterLevel,
      opts.targetLevel
    );
    return { ...chanceInfo, rates };
  }

  global.ResistCalc = {
    RESIST_TYPE,
    RESIST_KEY,
    RESIST_FALL_OFF,
    ROLL_COUNT,
    applyInstrumentMod,
    sumDebuffDelta,
    computeLevelMod,
    computeResistChance,
    computeLandRates,
    partialEffectiveness,
    evaluate,
    cTruncDiv,
  };
})(typeof window !== 'undefined' ? window : globalThis);
