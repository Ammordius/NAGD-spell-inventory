/**
 * TAKP incoming-damage tank simulator.
 *
 * Survival is the result of a timestamped fight. Average DPS and HPS are
 * diagnostics. Experimental Mod2s are off unless a scenario turns them on.
 * This file does not change ranking scores or the outgoing DPS calculator.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.TankSim = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    var DEATH_HP = -10;
    var MIN_HASTED_DELAY = 400;
    var SHIELDING_CAP = 35;
    var DEFAULT_SEED = 14650;
    var DEFAULT_TRIALS = 10000;
    var DEFAULT_HORIZON_MS = 180000;
    var DEFAULT_JITTER_MS = 500;

    var CLASS_ID = {
        Warrior: 1, Cleric: 2, Paladin: 3, Ranger: 4, 'Shadow Knight': 5,
        Druid: 6, Monk: 7, Bard: 8, Rogue: 9, Shaman: 10, Necromancer: 11,
        Wizard: 12, Magician: 13, Enchanter: 14, Beastlord: 15
    };
    var PURE_CASTER = { Wizard: 1, Necromancer: 1, Enchanter: 1, Magician: 1 };
    var MOD2_STATS = ['accuracy', 'avoidance', 'combat_effects', 'damage_shield', 'dot_shielding', 'shielding', 'spell_shielding', 'strikethrough', 'stun_resist'];
    var EXPERIMENTAL_APPLIED = ['shielding', 'avoidance'];

    // Level-65 caps from utils/sql/git/required/2022_08_03_skill_caps.sql.
    // A missing skill means the class cannot use that check.
    var SKILL_CAPS = {
        Warrior: { defense: 252, dodge: 190, parry: 230, riposte: 225 },
        Cleric: { defense: 200, dodge: 75 },
        Paladin: { defense: 252, dodge: 170, parry: 205, riposte: 200 },
        Ranger: { defense: 240, dodge: 170, parry: 220, riposte: 185 },
        'Shadow Knight': { defense: 252, dodge: 170, parry: 205, riposte: 200 },
        Druid: { defense: 200, dodge: 75 },
        Monk: { defense: 252, dodge: 230, riposte: 225, block: 225 },
        Bard: { defense: 252, dodge: 170, parry: 185, riposte: 75 },
        Rogue: { defense: 252, dodge: 210, parry: 230, riposte: 225 },
        Shaman: { defense: 200, dodge: 75 },
        Necromancer: { defense: 145, dodge: 75 },
        Wizard: { defense: 145, dodge: 75 },
        Magician: { defense: 145, dodge: 75 },
        Enchanter: { defense: 145, dodge: 75 },
        Beastlord: { defense: 240, dodge: 170, riposte: 185, block: 200 }
    };

    var COMPLETE_HEAL_PRESET = {
        name: 'Illustrative four-healer chain',
        verified: false,
        status: 'illustrative',
        amount: 7500,
        healers: 4,
        castMs: 10000,
        spacingMs: 3000,
        note: 'Cast time and healed amount were not confirmed from a spell row in this tree. Four healers at 3 seconds between landings have a 12 second personal cycle, which covers a 10 second cast.'
    };

    function truncDiv(n, d) {
        return Math.trunc(n / d);
    }

    function hasDied(hp) {
        return hp < DEATH_HP;
    }

    function mulberry32(seed) {
        var a = seed >>> 0;
        return function () {
            a = (a + 0x6D2B79F5) | 0;
            var t = Math.imul(a ^ (a >>> 15), 1 | a);
            t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
            return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
        };
    }

    function rngFrom(seed) {
        var next = mulberry32(seed);
        return {
            real: function () { return next(); },
            int: function (low, high) {
                var span = high - low + 1;
                return low + Math.floor(next() * span);
            }
        };
    }

    function scriptedRng(draws) {
        var i = 0;
        function take() {
            if (i >= draws.length) {
                throw new Error('scripted rng exhausted at ' + i);
            }
            return draws[i++];
        }
        return {
            real: take,
            int: function () { return take(); },
            remaining: function () { return draws.length - i; }
        };
    }

    function makeStreams(seed) {
        var s = seed >>> 0;
        return {
            phase: rngFrom(s + 1),
            avoid: rngFrom(s + 2),
            hit: rngFrom(s + 3),
            di: rngFrom(s + 4),
            special: rngFrom(s + 5),
            chainPhase: rngFrom(s + 6),
            jitter: rngFrom(s + 7)
        };
    }

    function skillCaps(className) {
        return SKILL_CAPS[className] || {};
    }

    function defenseCap(className) {
        var caps = skillCaps(className);
        return caps.defense || 0;
    }

    function playerAvoidance(defense, agi, level, combatAgilityPercent) {
        defense = defense || 0;
        agi = agi || 0;
        level = level || 65;
        combatAgilityPercent = combatAgilityPercent || 0;
        var defenseAvoidance = defense > 0 ? truncDiv(defense * 400, 225) : 0;
        var agiAvoidance = 0;
        if (agi < 40) {
            agiAvoidance = truncDiv(25 * (agi - 40), 40);
        } else if (agi >= 60 && agi <= 74) {
            agiAvoidance = truncDiv(2 * (28 - truncDiv(200 - agi, 5)), 3);
        } else if (agi >= 75) {
            var bonusAdj = 80;
            if (level < 7) bonusAdj = 35;
            else if (level < 20) bonusAdj = 55;
            else if (level < 40) bonusAdj = 70;
            if (agi < 200) {
                agiAvoidance = truncDiv(2 * (bonusAdj - truncDiv(200 - agi, 5)), 3);
            } else {
                agiAvoidance = truncDiv(2 * bonusAdj, 3);
            }
        }
        var computed = defenseAvoidance + agiAvoidance;
        computed += truncDiv(computed * combatAgilityPercent, 100);
        if (computed < 1) computed = 1;
        return computed;
    }

    function softcapFor(className, level) {
        if (level <= 50) return 350;
        if (className === 'Warrior') return 430;
        if (className === 'Paladin' || className === 'Shadow Knight' || className === 'Cleric' || className === 'Bard') return 403;
        if (className === 'Ranger' || className === 'Shaman') return 375;
        if (className === 'Monk') return 315;
        return 350;
    }

    function overcapReturns(className, level) {
        if (className === 'Warrior') {
            if (level <= 61) return 5;
            if (level <= 63) return 4;
            return 3;
        }
        if (className === 'Paladin' || className === 'Shadow Knight') {
            if (level <= 61) return 6;
            if (level <= 63) return 5;
            return 4;
        }
        if (className === 'Bard') {
            if (level <= 61) return 8;
            if (level <= 63) return 7;
            return 6;
        }
        if (className === 'Monk' || className === 'Rogue') {
            if (level <= 61) return 20;
            if (level === 62) return 18;
            if (level === 63) return 16;
            if (level === 64) return 14;
            return 12;
        }
        if (className === 'Ranger' || className === 'Beastlord') {
            if (level <= 61) return 10;
            if (level === 62) return 9;
            if (level === 63) return 8;
            return 7;
        }
        return 20;
    }

    function getMitigation(opts) {
        opts = opts || {};
        var className = opts.className || 'Warrior';
        var level = opts.level == null ? 65 : opts.level;
        var acSum = opts.itemAc || 0;
        if (!PURE_CASTER[className]) acSum = truncDiv(4 * acSum, 3);

        if (!opts.ignoreCap && level < 50 && acSum > (level * 6 + 25)) {
            acSum = level * 6 + 25;
        }

        if (className === 'Monk') {
            var hardcap = 53;
            var weightSoft = 24;
            if (level <= 61) { hardcap = 45; weightSoft = 24; }
            if (level <= 59) { hardcap = 40; weightSoft = 20; }
            if (level > 64) { hardcap = 53; weightSoft = 24; }
            var weight = opts.weight || 0;
            var acBonus = level + 5;
            if (weight <= weightSoft) {
                acSum += Math.trunc(acBonus * 4 / 3);
            } else if (weight > hardcap + 1) {
                var penalty = level + 5;
                var multiplier = (weight - (hardcap - 10)) / 100;
                if (multiplier > 1) multiplier = 1;
                penalty = 4 * penalty / 3;
                penalty = multiplier * penalty;
                acSum -= Math.trunc(penalty);
            } else if (weight > weightSoft) {
                var reduction = (weight - weightSoft) * 6.66667;
                if (reduction > 100) reduction = 100;
                reduction = (100 - reduction) / 100;
                acBonus *= reduction;
                if (acBonus < 0) acBonus = 0;
                acBonus = 4 * acBonus / 3;
                acSum += Math.trunc(acBonus);
            }
        } else if (className === 'Rogue' && level >= 30 && (opts.agi || 0) > 75) {
            var levelScaler = level - 26;
            var agi = opts.agi || 0;
            var bonus = 0;
            if (agi < 80) bonus = truncDiv(levelScaler, 4);
            else if (agi < 85) bonus = truncDiv(levelScaler * 2, 4);
            else if (agi < 90) bonus = truncDiv(levelScaler * 3, 4);
            else if (agi < 100) bonus = truncDiv(levelScaler * 4, 4);
            else bonus = truncDiv(levelScaler * 5, 4);
            if (bonus > 12) bonus = 12;
            acSum += bonus;
        } else if (className === 'Beastlord' && level > 10) {
            var scaler = level - 6;
            var bagi = opts.agi || 0;
            var bbonus = 0;
            if (bagi < 80) bbonus = truncDiv(scaler, 5);
            else if (bagi < 85) bbonus = truncDiv(scaler * 2, 5);
            else if (bagi < 90) bbonus = truncDiv(scaler * 3, 5);
            else if (bagi < 100) bbonus = truncDiv(scaler * 4, 5);
            else bbonus = truncDiv(scaler * 5, 5);
            if (bbonus > 16) bbonus = 16;
            acSum += bbonus;
        }

        if (opts.race === 'Iksar') {
            if (level < 10) acSum += 10;
            else if (level > 35) acSum += 35;
            else acSum += level;
        }
        if (acSum < 0) acSum = 0;

        var defense = opts.defense == null ? defenseCap(className) : opts.defense;
        if (defense > 0) {
            acSum += PURE_CASTER[className] ? truncDiv(defense, 2) : truncDiv(defense, 3);
        }
        var spellDiv = PURE_CASTER[className] ? 3 : 4;
        acSum += truncDiv(opts.spellAc || 0, spellDiv);
        if ((opts.agi || 0) > 70) acSum += truncDiv(opts.agi, 20);
        if (opts.preSoftcapBonus) acSum += opts.preSoftcapBonus;
        if (acSum < 0) acSum = 0;

        var soft = softcapFor(className, level);
        var stability = opts.stabilityPercent || 0;
        soft += truncDiv(stability * soft, 100);
        soft += opts.shieldAc || 0;
        var beforeCap = acSum;
        if (!opts.ignoreCap && acSum > soft) {
            if (level <= 50) return { mitigation: soft, softcap: soft, beforeCap: beforeCap, returns: null };
            var over = acSum - soft;
            var returns = overcapReturns(className, level);
            acSum = soft + truncDiv(over, returns);
            return { mitigation: acSum, softcap: soft, beforeCap: beforeCap, returns: returns };
        }
        return { mitigation: acSum, softcap: soft, beforeCap: beforeCap, returns: null };
    }

    function displayedAc(avoidance, uncappedMitigation) {
        return truncDiv((avoidance + uncappedMitigation) * 1000, 847);
    }

    function npcWeaponSkill(level) {
        if (level > 50) return 250 + level;
        return Math.min(level * 6, 275);
    }

    function npcDoubleAttackSkill(level) {
        if (level <= 7) return 0;
        if (level > 50) return 250;
        return Math.min(level * 5, 210);
    }

    function npcOffense(level, atk) {
        var mob = level;
        if (mob > 45 && mob < 51) mob = 45;
        var base = truncDiv(mob * 55, 10) - 4;
        if (base > 320) base = 320;
        var str = 0;
        if (mob < 6) {
            base = mob * 4;
            str = mob;
        } else if (mob < 30) {
            str = truncDiv(mob, 2) + 1;
        } else {
            str = mob * 2 - 40 + 20;
        }
        var offense = base + str + (atk || 0);
        if (offense < 1) offense = 1;
        return offense;
    }

    function npcToHit(level, accuracy) {
        var skill = npcWeaponSkill(level);
        return 7 + skill + skill + (accuracy || 0);
    }

    function hitChance(toHit, avoidance) {
        toHit += 10;
        avoidance += 10;
        if (toHit * 1.21 > avoidance) {
            return 1 - avoidance / (toHit * 1.21 * 2);
        }
        return (toHit * 1.21) / (avoidance * 2);
    }

    function dbAndBase(minHit, maxHit) {
        if (minHit == null || maxHit == null) return null;
        if (minHit > maxHit) return { db: minHit, baseDamage: 1 };
        if (maxHit === minHit) return { db: minHit, baseDamage: 1 };
        var di1k = truncDiv((maxHit - minHit) * 1000, 19);
        di1k = truncDiv(di1k + 50, 100) * 100;
        return {
            db: truncDiv(maxHit * 1000 - di1k * 20, 1000),
            baseDamage: truncDiv(di1k, 100),
            di1k: di1k
        };
    }

    function rollD20(rng, offense, mitigation) {
        var atkRoll = rng.int(0, offense + 4);
        var defRoll = rng.int(0, mitigation + 4);
        var avg = truncDiv(offense + mitigation + 10, 2);
        if (avg <= 0) return 1;
        var index = (atkRoll - defRoll) + truncDiv(avg, 2);
        if (index < 0) index = 0;
        index = truncDiv(index * 20, avg);
        if (index < 0) index = 0;
        if (index > 19) index = 19;
        return index + 1;
    }

    function intervalDamage(baseDamage, roll, spellMitigationEffect) {
        var base = baseDamage;
        var effect = spellMitigationEffect || 0;
        base += truncDiv(base * effect, 100);
        var damage = truncDiv(roll * base + 5, 10);
        if (damage < 1) damage = 1;
        return damage;
    }

    function shieldingDb(db, percent, enabled) {
        if (!enabled) return { db: db, applied: false, percent: 0 };
        var pct = Math.max(0, Math.min(SHIELDING_CAP, percent || 0));
        return {
            db: truncDiv(db * (100 - pct), 100),
            applied: true,
            percent: pct,
            hypothesis: 'DB * (100 - percent) / 100, cap 35, DI unchanged. Not current TAKP melee.'
        };
    }

    function skillCheckChance(skill, bonus, divisor) {
        if (!skill) return 0;
        var chance = skill + 100;
        chance += truncDiv(chance * (bonus || 0), 100);
        chance = truncDiv(chance, divisor);
        return chance;
    }

    function rollPercent(rng, chance) {
        if (chance >= 100) return true;
        if (chance <= 0) return false;
        return rng.int(0, 99) < chance;
    }

    function avoidChances(defender) {
        var inFront = defender.inFront !== false;
        var ranged = !!defender.ranged;
        var caps = defender.skills || skillCaps(defender.className);
        var block = skillCheckChance(caps.block, defender.blockBonus, 25);
        var parry = (!ranged && inFront) ? skillCheckChance(caps.parry, defender.parryBonus, 50) : 0;
        var riposte = (!ranged && inFront) ? skillCheckChance(caps.riposte, defender.riposteBonus, 55) : 0;
        var dodge = inFront ? skillCheckChance(caps.dodge, defender.dodgeBonus, 45) : 0;
        function pRoll(chance) {
            if (chance >= 100) return 1;
            if (chance <= 0) return 0;
            return Math.min(chance, 100) / 100;
        }
        var remain = 1;
        var out = { block: 0, parry: 0, riposte: 0, dodge: 0 };
        out.block = remain * pRoll(block);
        remain -= out.block;
        out.parry = remain * pRoll(parry);
        remain -= out.parry;
        out.riposte = remain * pRoll(riposte);
        remain -= out.riposte;
        out.dodge = remain * pRoll(dodge);
        remain -= out.dodge;
        out.reachedCheck = remain;
        out.chances = { block: block, parry: parry, riposte: riposte, dodge: dodge };
        out.inFront = inFront;
        return out;
    }

    function resolveAvoid(rng, defender) {
        var chances = avoidChances(defender);
        if (rollPercent(rng, chances.chances.block)) return 'block';
        if (rollPercent(rng, chances.chances.parry)) return 'parry';
        if (rollPercent(rng, chances.chances.riposte)) return 'riposte';
        if (rollPercent(rng, chances.chances.dodge)) return 'dodge';
        return null;
    }

    function combatAgilityPercent(scenario) {
        var pct = 0;
        if (scenario.combatAgility) pct += 10;
        if (scenario.lightningReflexes) pct += 15;
        return pct;
    }

    function stabilityPercent(scenario) {
        var pct = 0;
        if (scenario.combatStability) pct += 10;
        if (scenario.innateDefense) pct += 15;
        return pct;
    }

    function defenderProfile(scenario) {
        var className = scenario.className || 'Warrior';
        var caps = skillCaps(className);
        var agi = scenario.agi == null ? 200 : scenario.agi;
        var defense = scenario.defense == null ? (caps.defense || 0) : scenario.defense;
        var agility = combatAgilityPercent(scenario);
        var avoidance = playerAvoidance(defense, agi, scenario.level || 65, agility);
        var mit = getMitigation({
            className: className,
            level: scenario.level || 65,
            itemAc: scenario.itemAc || 0,
            shieldAc: scenario.shieldAc || 0,
            spellAc: scenario.spellAc || 0,
            race: scenario.race,
            weight: scenario.weight || 0,
            agi: agi,
            defense: defense,
            stabilityPercent: stabilityPercent(scenario),
            ignoreCap: false,
            preSoftcapBonus: scenario.preSoftcapBonus || 0
        });
        var sheet = getMitigation({
            className: className,
            level: scenario.level || 65,
            itemAc: scenario.itemAc || 0,
            shieldAc: scenario.shieldAc || 0,
            spellAc: scenario.spellAc || 0,
            race: scenario.race,
            weight: scenario.weight || 0,
            agi: agi,
            defense: defense,
            stabilityPercent: 0,
            ignoreCap: true
        });
        var sheetAvoid = playerAvoidance(defense, agi, scenario.level || 65, 0);
        return {
            className: className,
            skills: caps,
            inFront: scenario.inFront !== false,
            avoidance: avoidance,
            mitigation: mit.mitigation,
            softcap: mit.softcap,
            returns: mit.returns,
            beforeCap: mit.beforeCap,
            sheetMitigation: sheet.mitigation,
            sheetAvoidance: sheetAvoid,
            displayed: displayedAc(sheetAvoid, sheet.mitigation),
            defense: defense,
            defenseAssumed: scenario.defense == null
        };
    }

    function avoidancePercent(scenario) {
        var spell = scenario.avoidancePct || 0;
        var worn = 0;
        if (scenario.experimentalMod2 && scenario.mod2) worn = scenario.mod2.avoidance || 0;
        if (scenario.additiveAvoidance) return spell + worn;
        return Math.max(spell, worn);
    }

    function mobDamageParts(mob) {
        if (mob.fixedDamage != null) {
            return { db: 0, baseDamage: 0, fixedDamage: mob.fixedDamage, source: 'fixed' };
        }
        if (mob.minHit != null && mob.maxHit != null) {
            var parts = dbAndBase(mob.minHit, mob.maxHit);
            parts.source = 'min-max';
            return parts;
        }
        if (mob.db != null && mob.di != null) {
            return { db: mob.db, baseDamage: Math.round(mob.di * 10), source: 'db-di' };
        }
        return null;
    }

    function hasteFromSlow(slowed, slowPercent, slowMitigation) {
        if (!slowed || !slowPercent) {
            return { haste: 100, effectiveSlow: 0, undefinedTimer: false };
        }
        var effect = 100 - slowPercent;
        var real = (100 - effect) * -1;
        var mit = slowMitigation || 0;
        real -= truncDiv(real * mit, 100);
        var haste = 100 + real;
        return {
            haste: haste,
            effectiveSlow: -real,
            undefinedTimer: haste === 0,
            effectValue: effect,
            slowMitigation: mit
        };
    }

    function attackIntervalMs(delayRaw, haste) {
        if (delayRaw == null || delayRaw === '') {
            return { ms: null, reason: 'attack delay unavailable' };
        }
        if (haste == null) return { ms: null, reason: 'haste unavailable' };
        if (haste === 0) return { ms: null, reason: 'haste is 0; the attack timer divides by zero' };
        var delay = Number(delayRaw);
        var ms = delay < 401 ? delay * 100 : delay;
        var speed = Math.trunc(ms / (haste * 0.01));
        return { ms: Math.max(MIN_HASTED_DELAY, speed), unhastedMs: ms, haste: haste };
    }

    function doubleAttackEffective(level) {
        var skill = npcDoubleAttackSkill(level);
        if (skill > 0 && level > 35) skill += level;
        return skill;
    }

    function checkDoubleAttack(rng, level) {
        var chance = doubleAttackEffective(level);
        if (chance <= 0) return false;
        return chance > rng.int(0, 499);
    }

    function missingCombatFields(mob) {
        var missing = [];
        if (!mob) return ['encounter'];
        if (mob.fixedDamage == null) {
            var parts = mobDamageParts(mob);
            if (!parts) missing.push('min/max hit or DB/DI');
            if (mob.level == null) missing.push('level');
        }
        if (mob.attackCount == null) missing.push('attack count');
        if (mob.attackDelay == null) missing.push('attack delay');
        return missing;
    }

    function landedSwingDamage(scenario, mob, defender, rngs) {
        if (mob.fixedDamage != null) return mob.fixedDamage;
        var parts = mobDamageParts(mob);
        var shield = shieldingDb(parts.db, scenario.mod2 && scenario.mod2.shielding, !!scenario.experimentalMod2);
        var roll = scenario.sitting ? 20 : rollD20(rngs.di, npcOffense(mob.level, mob.atk || 0), defender.mitigation);
        var interval = intervalDamage(parts.baseDamage, roll, scenario.spellMitigationEffect || 0);
        return shield.db + interval;
    }

    function scalePct(damage, damagePct) {
        var pct = damagePct == null || damagePct <= 0 ? 100 : damagePct;
        return truncDiv(damage * pct, 100);
    }

    function resolveSwing(scenario, mob, defender, rngs, hand, damagePct) {
        if (scenario.alwaysHit) {
            return { outcome: 'hit', damage: scalePct(landedSwingDamage(scenario, mob, defender, rngs), damagePct), hand: hand };
        }
        var avoided = resolveAvoid(rngs.avoid, {
            className: defender.className,
            skills: defender.skills,
            inFront: defender.inFront
        });
        if (avoided) return { outcome: avoided, damage: 0, hand: hand };
        var toHit = npcToHit(mob.level || 1, mob.accuracy || 0);
        var avoidance = defender.avoidance;
        var pct = avoidancePercent(scenario);
        avoidance = truncDiv(avoidance * (100 + pct), 100);
        var chance = hitChance(toHit, avoidance);
        if (scenario.sitting || rngs.hit.real() < chance) {
            return { outcome: 'hit', damage: scalePct(landedSwingDamage(scenario, mob, defender, rngs), damagePct), hand: hand, hitChance: chance };
        }
        return { outcome: 'miss', damage: 0, hand: hand, hitChance: chance };
    }

    function mainHandSwings(scenario, mob, defender, rngs, events, state, damagePct) {
        var count = mob.attackCount || 1;
        var i;
        for (i = 0; i < count; i++) {
            if (state.dead) return;
            applySwing(resolveSwing(scenario, mob, defender, rngs, 'primary', damagePct), events, state);
        }
        if (state.dead || mob.noSpecials) return;
        if (checkDoubleAttack(rngs.special, mob.level || 1)) {
            applySwing(resolveSwing(scenario, mob, defender, rngs, 'primary', damagePct), events, state);
            var klass = mob.className;
            if (!state.dead && (klass === 'Warrior' || klass === 'Monk') && (mob.level || 0) >= 60) {
                if (rngs.special.int(0, 999) < 135) {
                    applySwing(resolveSwing(scenario, mob, defender, rngs, 'primary', damagePct), events, state);
                }
            }
        }
    }

    function offhandSwings(scenario, mob, defender, rngs, events, state, damagePct) {
        applySwing(resolveSwing(scenario, mob, defender, rngs, 'offhand', damagePct), events, state);
        if (!state.dead && !mob.noSpecials && npcDoubleAttackSkill(mob.level || 1) >= 150 && checkDoubleAttack(rngs.special, mob.level || 1)) {
            applySwing(resolveSwing(scenario, mob, defender, rngs, 'offhand', damagePct), events, state);
        }
    }

    function applySwing(swing, events, state) {
        events.push({ t: state.t, kind: 'swing', outcome: swing.outcome, damage: swing.damage, hand: swing.hand, hpBefore: state.hp });
        state.swings += 1;
        if (swing.outcome === 'hit') {
            state.hp -= swing.damage;
            state.damage += swing.damage;
            state.landed += 1;
            state.landedDamage += swing.damage;
            state.hitsSinceHeal += 1;
            if (state.hitsSinceHeal > state.maxHitsBetween) state.maxHitsBetween = state.hitsSinceHeal;
            state.damageEvents.push({ t: state.t, amount: swing.damage });
            if (state.hp < state.minHp) state.minHp = state.hp;
            if (hasDied(state.hp)) state.dead = true;
        }
        events[events.length - 1].hpAfter = state.hp;
        events[events.length - 1].dead = state.dead;
    }

    function chainFeasibility(chain) {
        chain = chain || {};
        var healers = chain.healers || 1;
        var spacing = chain.spacingMs || 0;
        var castMs = chain.castMs || 0;
        var personal = healers * spacing;
        var ok = healers > 0 && spacing > 0 && personal >= castMs;
        return {
            feasible: ok,
            healers: healers,
            spacingMs: spacing,
            castMs: castMs,
            personalCycleMs: personal,
            reason: ok ? '' : 'Each healer needs a personal cycle of at least the cast time. ' + healers + ' healer(s) at ' + spacing + ' ms spacing have a ' + personal + ' ms cycle, and the cast is ' + castMs + ' ms.'
        };
    }

    function plannedHeals(chain, durationMs, rngs) {
        var check = chainFeasibility(chain);
        if (!check.feasible) return { feasible: false, reason: check.reason, landings: [] };
        var healers = chain.healers;
        var spacing = chain.spacingMs;
        var castMs = chain.castMs || 0;
        var jitterMs = chain.jitterMs == null ? DEFAULT_JITTER_MS : chain.jitterMs;
        var start = chain.start === 'cold' ? 'cold' : 'steady';
        var phase = chain.phaseMs || 0;
        if (chain.randomizePhase && rngs) {
            phase = Math.floor(rngs.chainPhase.real() * healers * spacing);
        }
        var landings = [];
        var h;
        for (h = 0; h < healers; h++) {
            var planned = (start === 'cold' ? castMs : 0) + phase + h * spacing;
            var earliest = start === 'cold' ? castMs : 0;
            while (planned - jitterMs <= durationMs) {
                var jitter = 0;
                if (jitterMs && rngs) {
                    jitter = Math.floor(rngs.jitter.real() * (jitterMs * 2 + 1)) - jitterMs;
                } else if (chain.jitterOverride != null) {
                    jitter = chain.jitterOverride;
                }
                var actual = planned + jitter;
                if (actual < earliest) actual = earliest;
                if (actual < 0) actual = 0;
                if (actual <= durationMs) {
                    landings.push({ t: actual, planned: planned, healer: h, amount: chain.amount || 0, jitter: jitter });
                }
                earliest = actual + castMs;
                planned += healers * spacing;
            }
        }
        landings.sort(function (a, b) { return a.t - b.t || a.healer - b.healer; });
        return { feasible: true, landings: landings, phaseMs: phase, feasibility: check };
    }

    function applyHeal(state, amount, maxHp) {
        var room = Math.max(0, maxHp - state.hp);
        var healed = Math.min(amount, room);
        var over = amount - healed;
        state.hp += healed;
        state.healed += healed;
        state.overheal += over;
        state.healCount += 1;
        state.hitsSinceHeal = 0;
        return { healed: healed, overheal: over };
    }

    function slidingPeak(events, width) {
        if (!events.length) return 0;
        var best = 0;
        var sum = 0;
        var j = 0;
        var i;
        for (i = 0; i < events.length; i++) {
            sum += events[i].amount;
            while (events[i].t - events[j].t > width) {
                sum -= events[j].amount;
                j += 1;
            }
            if (sum > best) best = sum;
        }
        return best;
    }

    function simulateTrial(scenario, seedOrStreams) {
        var mob = scenario.mob || {};
        var missing = missingCombatFields(mob);
        if (missing.length && mob.fixedDamage == null) {
            return { runnable: false, missing: missing };
        }
        if (mob.fixedDamage != null && (mob.attackCount == null || mob.attackDelay == null)) {
            return { runnable: false, missing: missingCombatFields(mob) };
        }
        var slowed = hasteFromSlow(!!scenario.slowed, scenario.slowPercent || 0, mob.slowMitigation);
        var interval = attackIntervalMs(mob.attackDelay, slowed.haste);
        if (interval.ms == null) return { runnable: false, missing: [interval.reason] };

        var healing = scenario.healing || { mode: 'none' };
        var mode = healing.mode || 'none';
        var healPlan = { feasible: true, landings: [] };
        if (mode === 'fixed') {
            healPlan = plannedHeals(healing, scenario.horizonMs || DEFAULT_HORIZON_MS, null);
            if (!healPlan.feasible) return { runnable: false, infeasibleChain: true, reason: healPlan.reason };
        }

        var rngs = seedOrStreams && seedOrStreams.avoid ? seedOrStreams : makeStreams(seedOrStreams == null ? DEFAULT_SEED : seedOrStreams);
        if (mode === 'fixed') {
            healPlan = plannedHeals(healing, scenario.horizonMs || DEFAULT_HORIZON_MS, rngs);
        }
        var defender = defenderProfile(scenario);
        var duration = scenario.horizonMs == null ? DEFAULT_HORIZON_MS : scenario.horizonMs;
        var phase = scenario.phaseMs || 0;
        if (scenario.randomizePhase) phase = Math.floor(rngs.phase.real() * interval.ms);

        var state = {
            t: 0,
            hp: scenario.maxHp || 1,
            minHp: scenario.maxHp || 1,
            dead: false,
            damage: 0,
            swings: 0,
            landed: 0,
            landedDamage: 0,
            healed: 0,
            overheal: 0,
            healCount: 0,
            hitsSinceHeal: 0,
            maxHitsBetween: 0,
            damageEvents: []
        };
        var trace = [];
        var queue = [];
        var seq = 0;
        function push(ev) {
            ev.seq = seq++;
            queue.push(ev);
        }
        var kindOrder = { primary: 1, offhand: 2, heal: 5, end: 9 };
        push({ t: phase, kind: 'primary' });
        if (mob.dualWield) push({ t: phase, kind: 'offhand' });
        var hi;
        for (hi = 0; hi < healPlan.landings.length; hi++) {
            push({ t: healPlan.landings[hi].t, kind: 'heal', amount: healPlan.landings[hi].amount, healer: healPlan.landings[hi].healer });
        }
        push({ t: duration, kind: 'end' });

        function pop() {
            var best = 0;
            var i;
            for (i = 1; i < queue.length; i++) {
                var a = queue[i];
                var b = queue[best];
                if (a.t < b.t || (a.t === b.t && kindOrder[a.kind] < kindOrder[b.kind])) best = i;
            }
            return queue.splice(best, 1)[0];
        }

        while (queue.length && !state.dead) {
            var ev = pop();
            state.t = ev.t;
            if (ev.kind === 'end') break;
            if (ev.kind === 'heal') {
                if (state.dead) break;
                var healed = applyHeal(state, ev.amount, scenario.maxHp);
                trace.push({ t: ev.t, kind: 'heal', healed: healed.healed, overheal: healed.overheal, hpAfter: state.hp, healer: ev.healer });
                continue;
            }
            if (ev.kind === 'primary') {
                mainHandSwings(scenario, mob, defender, rngs, trace, state, 100);
                if (!state.dead && mob.flurryChance != null && rollPercent(rngs.special, mob.flurryChance)) {
                    trace.push({ t: state.t, kind: 'flurry' });
                    mainHandSwings(scenario, mob, defender, rngs, trace, state, 100);
                    if (!state.dead && mob.dualWield) offhandSwings(scenario, mob, defender, rngs, trace, state, 100);
                }
                if (!state.dead && mob.areaRampageChance != null && rollPercent(rngs.special, mob.areaRampageChance)) {
                    trace.push({ t: state.t, kind: 'area-rampage', damagePct: mob.areaRampageDamagePct || 100 });
                    mainHandSwings(scenario, mob, defender, rngs, trace, state, mob.areaRampageDamagePct || 100);
                    if (!state.dead && mob.dualWield) offhandSwings(scenario, mob, defender, rngs, trace, state, mob.areaRampageDamagePct || 100);
                }
                if (!state.dead) push({ t: ev.t + interval.ms, kind: 'primary' });
            } else if (ev.kind === 'offhand') {
                offhandSwings(scenario, mob, defender, rngs, trace, state, 100);
                if (!state.dead) push({ t: ev.t + interval.ms, kind: 'offhand' });
            }
        }

        return {
            runnable: true,
            survived: !state.dead,
            dead: state.dead,
            hp: state.hp,
            minHp: state.minHp,
            deathTime: state.dead ? state.t : null,
            endTime: state.dead ? state.t : duration,
            damage: state.damage,
            swings: state.swings,
            landed: state.landed,
            landedDamage: state.landedDamage,
            healed: state.healed,
            overheal: state.overheal,
            healCount: state.healCount,
            maxHitsBetween: state.maxHitsBetween,
            windowPeak: {
                8000: slidingPeak(state.damageEvents, 8000),
                13000: slidingPeak(state.damageEvents, 13000),
                20000: slidingPeak(state.damageEvents, 20000)
            },
            intervalMs: interval.ms,
            haste: slowed,
            trace: scenario.trace ? trace : null,
            defender: defender
        };
    }

    function percentile(sorted, p) {
        if (!sorted.length) return null;
        var idx = Math.min(sorted.length - 1, Math.max(0, Math.ceil(p * sorted.length) - 1));
        return sorted[idx];
    }

    function wilson(deaths, n, z) {
        z = z || 1.96;
        if (!n) return null;
        var p = deaths / n;
        var z2 = z * z;
        var denom = 1 + z2 / n;
        var center = (p + z2 / (2 * n)) / denom;
        var margin = (z * Math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom;
        return {
            low: Math.max(0, center - margin),
            high: Math.min(1, center + margin)
        };
    }

    function summarize(scenario, rows, extras) {
        var deaths = 0;
        var minHps = [];
        var deathTimes = [];
        var damage = 0;
        var time = 0;
        var swings = 0;
        var landed = 0;
        var landedDamage = 0;
        var healed = 0;
        var overheal = 0;
        var maxHits = 0;
        var peaks = { 8000: [], 13000: [], 20000: [] };
        var i;
        for (i = 0; i < rows.length; i++) {
            var row = rows[i];
            if (row.dead) {
                deaths += 1;
                deathTimes.push(row.deathTime);
            }
            minHps.push(row.minHp);
            damage += row.damage;
            time += row.endTime;
            swings += row.swings;
            landed += row.landed;
            landedDamage += row.landedDamage;
            healed += row.healed;
            overheal += row.overheal;
            if (row.maxHitsBetween > maxHits) maxHits = row.maxHitsBetween;
            peaks[8000].push(row.windowPeak[8000]);
            peaks[13000].push(row.windowPeak[13000]);
            peaks[20000].push(row.windowPeak[20000]);
        }
        minHps.sort(function (a, b) { return a - b; });
        deathTimes.sort(function (a, b) { return a - b; });
        peaks[8000].sort(function (a, b) { return a - b; });
        peaks[13000].sort(function (a, b) { return a - b; });
        peaks[20000].sort(function (a, b) { return a - b; });
        var n = rows.length;
        var deathP = n ? deaths / n : 0;
        var interval = wilson(deaths, n);
        var horizon = scenario.horizonMs == null ? DEFAULT_HORIZON_MS : scenario.horizonMs;
        var healing = scenario.healing || { mode: 'none' };
        var scheduledHps = null;
        if (healing.mode === 'fixed' && healing.spacingMs) {
            scheduledHps = (healing.amount || 0) / (healing.spacingMs / 1000);
        }
        var seconds = time / 1000;
        return {
            runnable: true,
            estimated: true,
            horizonMs: horizon,
            trials: n,
            seed: scenario.seed == null ? DEFAULT_SEED : scenario.seed,
            survived: n - deaths,
            deaths: deaths,
            survivalProbability: n ? (n - deaths) / n : 0,
            deathProbability: deathP,
            deathInterval: interval,
            timeToDeathMs: {
                count: deathTimes.length,
                median: percentile(deathTimes, 0.5),
                p25: percentile(deathTimes, 0.25),
                p75: percentile(deathTimes, 0.75)
            },
            minHp: {
                median: percentile(minHps, 0.5),
                p5: percentile(minHps, 0.05),
                p1: percentile(minHps, 0.01)
            },
            secondary: {
                averageIncomingDps: seconds ? damage / seconds : 0,
                meanLandedHit: landed ? landedDamage / landed : 0,
                landRate: swings ? landed / swings : 0,
                avoidanceRate: swings ? 1 - landed / swings : 0,
                swings: swings,
                swingsPerSecond: seconds ? swings / seconds : 0,
                intervalMs: extras.intervalMs,
                haste: extras.haste,
                attacksPerSecond: extras.intervalMs ? 1000 / extras.intervalMs : null,
                windowP95: {
                    8: percentile(peaks[8000], 0.95),
                    13: percentile(peaks[13000], 0.95),
                    20: percentile(peaks[20000], 0.95)
                },
                windowP99: {
                    8: percentile(peaks[8000], 0.99),
                    13: percentile(peaks[13000], 0.99),
                    20: percentile(peaks[20000], 0.99)
                },
                scheduledHps: scheduledHps,
                effectiveHps: seconds ? healed / seconds : 0,
                overheal: overheal,
                maxDamagingHitsBetweenHeals: maxHits
            },
            experimentalMod2: !!scenario.experimentalMod2,
            label: scenario.experimentalMod2 ? 'Experimental Mod2 scenario' : 'Current TAKP combat',
            defender: extras.defender
        };
    }

    function simulate(scenario) {
        scenario = scenario || {};
        var mob = scenario.mob || {};
        var missing = missingCombatFields(mob);
        if (missing.length) {
            return { runnable: false, missing: missing, estimated: true, perHit: perHit(scenario) };
        }
        var probe = simulateTrial(scenario, scenario.seed == null ? DEFAULT_SEED : scenario.seed);
        if (!probe.runnable) return probe;
        var n = scenario.trials == null ? DEFAULT_TRIALS : scenario.trials;
        var seed = scenario.seed == null ? DEFAULT_SEED : scenario.seed;
        var offset = scenario.trialOffset || 0;
        var rows = [];
        var i;
        for (i = 0; i < n; i++) {
            rows.push(simulateTrial(scenario, seed + offset + i));
        }
        var summary = summarize(scenario, rows, { intervalMs: probe.intervalMs, haste: probe.haste, defender: probe.defender });
        summary.perHit = perHit(scenario);
        if (scenario.trace) summary.trace = probe.trace;
        var deathIndex = -1;
        var survivalIndex = -1;
        var survivalMin = null;
        for (i = 0; i < rows.length; i++) {
            if (rows[i].dead && deathIndex < 0) deathIndex = i;
            if (!rows[i].dead) {
                if (survivalIndex < 0 || Math.abs(rows[i].minHp - summary.minHp.median) < Math.abs(survivalMin - summary.minHp.median)) {
                    survivalIndex = i;
                    survivalMin = rows[i].minHp;
                }
            }
        }
        summary.representative = { survivalIndex: survivalIndex, deathIndex: deathIndex };
        if (scenario.includeTraces) {
            var traced = Object.assign({}, scenario, { trace: true });
            summary.traces = {
                survival: survivalIndex >= 0 ? simulateTrial(traced, seed + offset + survivalIndex).trace : null,
                death: deathIndex >= 0 ? simulateTrial(traced, seed + offset + deathIndex).trace : null
            };
        }
        summary.rows = scenario.keepRows ? rows : null;
        return summary;
    }

    function perHit(scenario) {
        var mob = scenario.mob || {};
        var parts = mobDamageParts(mob);
        if (!parts || mob.level == null) {
            return { available: false, missing: missingCombatFields(mob).filter(function (item) {
                return item !== 'attack count' && item !== 'attack delay';
            }) };
        }
        var defender = defenderProfile(scenario);
        var shield = shieldingDb(parts.db, scenario.mod2 && scenario.mod2.shielding, !!scenario.experimentalMod2);
        var offense = npcOffense(mob.level, mob.atk || 0);
        var toHit = npcToHit(mob.level, mob.accuracy || 0);
        var avoidance = defender.avoidance;
        var pct = avoidancePercent(scenario);
        avoidance = truncDiv(avoidance * (100 + pct), 100);
        var chance = hitChance(toHit, avoidance);
        var avoids = avoidChances({ className: defender.className, skills: defender.skills, inFront: defender.inFront });
        var meanRoll = expectedRoll(offense, defender.mitigation);
        var interval = intervalDamage(parts.baseDamage, meanRoll, scenario.spellMitigationEffect || 0);
        return {
            available: true,
            db: parts.db,
            shieldedDb: shield.db,
            shieldingApplied: shield.applied,
            baseDamage: parts.baseDamage,
            offense: offense,
            mitigation: defender.mitigation,
            toHit: toHit,
            avoidance: avoidance,
            hitChance: chance,
            avoid: avoids,
            expectedRoll: meanRoll,
            expectedLanded: shield.db + interval,
            displayedAc: defender.displayed,
            sheetMitigation: defender.sheetMitigation,
            combatMitigation: defender.mitigation
        };
    }

    function expectedRoll(offense, mitigation) {
        var spanA = offense + 5;
        var spanB = mitigation + 5;
        if (spanA * spanB > 250000) {
            var rng = rngFrom(14650 + offense + mitigation);
            var total = 0;
            var n = 4000;
            var i;
            for (i = 0; i < n; i++) total += rollD20(rng, offense, mitigation);
            return total / n;
        }
        var avg = truncDiv(offense + mitigation + 10, 2);
        var sum = 0;
        var a;
        var b;
        for (a = 0; a < spanA; a++) {
            for (b = 0; b < spanB; b++) {
                var index = (a - b) + truncDiv(avg, 2);
                if (index < 0) index = 0;
                index = truncDiv(index * 20, avg);
                if (index < 0) index = 0;
                if (index > 19) index = 19;
                sum += index + 1;
            }
        }
        return sum / (spanA * spanB);
    }

    function searchSpacing(scenario, options) {
        options = options || {};
        var target = options.target == null ? 0.99 : options.target;
        var seeds = options.seeds || [scenario.seed == null ? DEFAULT_SEED : scenario.seed, (scenario.seed || DEFAULT_SEED) + 10007, (scenario.seed || DEFAULT_SEED) + 20011];
        var trials = options.trials == null ? Math.min(scenario.trials || 2000, 2000) : options.trials;
        var healing = Object.assign({ mode: 'fixed', jitterMs: DEFAULT_JITTER_MS }, scenario.healing || {});
        var horizon = scenario.horizonMs || DEFAULT_HORIZON_MS;
        var minSpacing = Math.ceil((healing.castMs || 0) / (healing.healers || 1));
        if (minSpacing < 1) minSpacing = 1;
        function pooled(spacing) {
            var deaths = 0;
            var n = 0;
            var effective = 0;
            var over = 0;
            var time = 0;
            var s;
            for (s = 0; s < seeds.length; s++) {
                var run = simulate(Object.assign({}, scenario, {
                    seed: seeds[s],
                    trials: trials,
                    healing: Object.assign({}, healing, { mode: 'fixed', spacingMs: spacing })
                }));
                if (!run.runnable) return run;
                deaths += run.deaths;
                n += run.trials;
                effective += run.secondary.effectiveHps * (run.trials);
                over += run.secondary.overheal;
                time += 1;
            }
            var interval = wilson(deaths, n);
            var survival = n ? (n - deaths) / n : 0;
            return {
                runnable: true,
                spacingMs: spacing,
                survivalProbability: survival,
                deathProbability: n ? deaths / n : 0,
                deathInterval: interval,
                deaths: deaths,
                trials: n,
                seeds: seeds.slice(),
                scheduledHps: (healing.amount || 0) / (spacing / 1000),
                meetsPoint: survival >= target,
                meetsLower: interval && (1 - interval.high) >= target,
                uncertain: interval && (1 - interval.high) < target && survival >= target
            };
        }
        var tight = chainFeasibility(Object.assign({}, healing, { spacingMs: minSpacing }));
        if (!tight.feasible) {
            return { runnable: false, infeasibleChain: true, reason: tight.reason };
        }
        var low = minSpacing;
        var high = horizon;
        var best = null;
        var guard = 0;
        while (low <= high && guard < 24) {
            guard += 1;
            var mid = Math.floor((low + high) / 2);
            var sample = pooled(mid);
            if (!sample.runnable) return sample;
            if (sample.meetsPoint) {
                best = sample;
                low = mid + 1;
            } else {
                high = mid - 1;
            }
        }
        if (!best) {
            var floorSample = pooled(minSpacing);
            return {
                runnable: true,
                found: false,
                target: target,
                horizonMs: horizon,
                tightest: floorSample,
                note: 'No feasible spacing in the search reached the survival target on the point estimate. This is not a required-HPS figure derived from average incoming DPS.'
            };
        }
        return {
            runnable: true,
            found: true,
            target: target,
            horizonMs: horizon,
            spacingMs: best.spacingMs,
            survivalProbability: best.survivalProbability,
            deathProbability: best.deathProbability,
            deathInterval: best.deathInterval,
            scheduledHps: best.scheduledHps,
            uncertain: best.uncertain,
            seeds: best.seeds,
            trialsPerSeed: trials,
            note: best.uncertain
                ? 'The point estimate meets the target and the confidence interval still crosses it. This is not an exact minimum spacing.'
                : 'Longest searched spacing whose pooled point estimate meets the target. Nearby samples can move a noisy threshold.'
        };
    }

    function compare(left, right) {
        var a = simulate(left);
        var b = simulate(right);
        if (!a.runnable || !b.runnable) return { runnable: false, left: a, right: b };
        return {
            runnable: true,
            left: a,
            right: b,
            survivalDelta: a.survivalProbability - b.survivalProbability,
            deathDelta: a.deathProbability - b.deathProbability
        };
    }

    function auditSheet(input) {
        var className = input.className || 'Warrior';
        var agi = input.agi == null ? 0 : input.agi;
        var defense = input.defense == null ? defenseCap(className) : input.defense;
        var sheet = getMitigation({
            className: className,
            level: input.level || 65,
            itemAc: input.itemAc || 0,
            shieldAc: input.shieldAc || 0,
            spellAc: input.spellAc || 0,
            race: input.race,
            weight: input.weight || 0,
            agi: agi,
            defense: defense,
            ignoreCap: true
        });
        var avoid = playerAvoidance(defense, agi, input.level || 65, 0);
        var displayed = displayedAc(avoid, sheet.mitigation);
        function delta(rebuilt, exported) {
            if (exported == null) return null;
            return rebuilt - exported;
        }
        return {
            reconstructed: {
                ac_mitigation: sheet.mitigation,
                ac_avoidance: avoid,
                ac_total: displayed,
                ac_item: input.itemAc,
                ac_shield: input.shieldAc
            },
            exported: input.exported || {},
            deltas: {
                ac_mitigation: delta(sheet.mitigation, input.exported && input.exported.ac_mitigation),
                ac_avoidance: delta(avoid, input.exported && input.exported.ac_avoidance),
                ac_total: delta(displayed, input.exported && input.exported.ac_total),
                ac_item: delta(input.summedItemAc, input.exported && input.exported.ac_item)
            },
            defenseAssumed: input.defense == null,
            notes: [
                'ac_mitigation is uncapped sheet mitigation. Combat mitigation applies the class softcap.',
                'Defense is the level-65 class cap unless a skill value is supplied. The character export has no defense column.',
                'Worn spell AC and missing item rows are not invented.'
            ]
        };
    }

    function sumMod2(table, itemIds) {
        var totals = {};
        MOD2_STATS.forEach(function (stat) { totals[stat] = 0; });
        var items = (table && table.items) || {};
        (itemIds || []).forEach(function (id) {
            var entry = items[String(id)];
            if (!entry || !entry.mods) return;
            MOD2_STATS.forEach(function (stat) {
                totals[stat] += Number(entry.mods[stat]) || 0;
            });
        });
        return {
            totals: totals,
            appliedWhenEnabled: EXPERIMENTAL_APPLIED.slice(),
            unused: MOD2_STATS.filter(function (stat) { return EXPERIMENTAL_APPLIED.indexOf(stat) < 0; })
        };
    }

    function wornSlots(inventory) {
        return (inventory || []).filter(function (row) {
            var slot = Number(row.slot_id);
            return slot >= 1 && slot <= 21;
        });
    }

    return {
        DEATH_HP: DEATH_HP,
        DEFAULT_SEED: DEFAULT_SEED,
        DEFAULT_TRIALS: DEFAULT_TRIALS,
        DEFAULT_HORIZON_MS: DEFAULT_HORIZON_MS,
        SKILL_CAPS: SKILL_CAPS,
        COMPLETE_HEAL_PRESET: COMPLETE_HEAL_PRESET,
        hasDied: hasDied,
        scriptedRng: scriptedRng,
        makeStreams: makeStreams,
        skillCaps: skillCaps,
        playerAvoidance: playerAvoidance,
        getMitigation: getMitigation,
        displayedAc: displayedAc,
        npcOffense: npcOffense,
        npcToHit: npcToHit,
        hitChance: hitChance,
        dbAndBase: dbAndBase,
        rollD20: rollD20,
        intervalDamage: intervalDamage,
        shieldingDb: shieldingDb,
        hasteFromSlow: hasteFromSlow,
        attackIntervalMs: attackIntervalMs,
        avoidChances: avoidChances,
        resolveAvoid: resolveAvoid,
        chainFeasibility: chainFeasibility,
        plannedHeals: plannedHeals,
        applyHeal: applyHeal,
        defenderProfile: defenderProfile,
        simulateTrial: simulateTrial,
        simulate: simulate,
        searchSpacing: searchSpacing,
        compare: compare,
        wilson: wilson,
        auditSheet: auditSheet,
        sumMod2: sumMod2,
        wornSlots: wornSlots,
        perHit: perHit,
        expectedRoll: expectedRoll,
        doubleAttackEffective: doubleAttackEffective
    };
}));
