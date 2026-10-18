'use strict';

const assert = require('assert');
const Tank = require('../tank_simulator.js');

function eq(actual, expected, label) {
    assert.strictEqual(actual, expected, label + ' expected ' + expected + ' got ' + actual);
}

function warriorMit(itemAc, extra) {
    return Tank.getMitigation(Object.assign({
        className: 'Warrior',
        level: 65,
        itemAc: itemAc,
        shieldAc: 0,
        agi: 200,
        defense: 252,
        ignoreCap: false
    }, extra || {})).mitigation;
}

eq(Tank.hasDied(-10), false, 'hp -10');
eq(Tank.hasDied(-11), true, 'hp -11');
eq(Tank.hasDied(0), false, 'hp 0');
eq(Tank.playerAvoidance(252, 200, 65, 0), 501, 'avoidance');
eq(Tank.getMitigation({ className: 'Warrior', level: 65, itemAc: 900, agi: 200, defense: 252, ignoreCap: true }).mitigation, 1294, 'sheet mit');
eq(warriorMit(900), 718, 'combat mit');
eq(warriorMit(900, { shieldAc: 85 }), 774, 'shield cap');
eq(warriorMit(900, { stabilityPercent: 10 }), 746, 'stability');
eq(Tank.getMitigation({ className: 'Wizard', level: 65, itemAc: 300, agi: 200, defense: 145, ignoreCap: false }).mitigation, 351, 'wizard returns');
eq(Tank.skillCaps('Wizard').parry, undefined, 'wizard parry');
eq(Tank.dbAndBase(1140, 3800).db, 1000, 'quarm db');
eq(Tank.dbAndBase(1140, 3800).baseDamage, 1400, 'quarm base');
eq(Tank.hasteFromSlow(true, 75, 30).haste, 47, 'slow 75 mit 30');
eq(Tank.hasteFromSlow(true, 75, 100).haste, 100, 'slow fully resisted');
eq(Tank.hasteFromSlow(false, 75, 0).haste, 100, 'no slow');
eq(Tank.attackIntervalMs(30, 100).ms, 3000, 'unslowed delay');
eq(Tank.attackIntervalMs(30, 47).ms, 6382, 'slowed delay');
eq(Tank.attackIntervalMs(30, 0).ms, null, 'zero haste');

const behind = Tank.avoidChances({ className: 'Monk', inFront: false });
eq(behind.chances.parry, 0, 'behind parry');
eq(behind.chances.riposte, 0, 'behind riposte');
eq(behind.chances.dodge, 0, 'behind dodge');
assert.ok(behind.chances.block > 0, 'block skill check remains');
const front = Tank.avoidChances({ className: 'Warrior', inFront: true });
assert.ok(front.chances.parry > 0 && front.chances.block === 0, 'warrior front parry and no block skill');

eq(Tank.shieldingDb(1000, 10, false).db, 1000, 'mod2 off');
eq(Tank.shieldingDb(1000, 10, true).db, 900, 'mod2 shielding hypothesis');
eq(Tank.shieldingDb(1000, 40, true).percent, 35, 'shielding cap');

const chainOk = Tank.chainFeasibility({ healers: 4, spacingMs: 3000, castMs: 10000 });
eq(chainOk.feasible, true, 'illustrative chain');
eq(chainOk.personalCycleMs, 12000, 'personal cycle');
eq(Tank.chainFeasibility({ healers: 1, spacingMs: 3000, castMs: 10000 }).feasible, false, 'impossible chain');

const healState = { hp: 900, healed: 0, overheal: 0, healCount: 0, hitsSinceHeal: 3 };
const healed = Tank.applyHeal(healState, 500, 1000);
eq(healed.healed, 100, 'capped heal');
eq(healed.overheal, 400, 'overheal');
eq(healState.hp, 1000, 'hp cap');

const full = { hp: 1000, healed: 0, overheal: 0, healCount: 0, hitsSinceHeal: 0 };
eq(Tank.applyHeal(full, 500, 1000).healed, 0, 'full heal');

function burstMob(extra) {
    return Object.assign({
        className: 'Warrior',
        level: 65,
        maxHp: 5000,
        itemAc: 0,
        agi: 200,
        inFront: true,
        alwaysHit: true,
        phaseMs: 0,
        seed: 14650,
        trials: 1,
        trace: true,
        horizonMs: 30000,
        healing: { mode: 'fixed', amount: 7500, healers: 1, castMs: 1000, spacingMs: 3000, jitterMs: 0, start: 'cold' },
        mob: {
            level: 5,
            attackCount: 2,
            attackDelay: 300,
            fixedDamage: 2000,
            flurryChance: 100,
            atk: 0,
            accuracy: 0
        }
    }, extra || {});
}

const burst = Tank.simulateTrial(burstMob(), 14650);
eq(burst.dead, true, 'flurry kills');
const swingHits = burst.trace.filter(function (ev) { return ev.kind === 'swing' && ev.outcome === 'hit'; });
assert.ok(swingHits.length >= 3, 'several hits in the round');
eq(burst.trace.some(function (ev) { return ev.kind === 'heal' && ev.t === burst.deathTime; }), false, 'no same-time heal before death resolution');
assert.ok(burst.trace.filter(function (ev) { return ev.kind === 'heal'; }).length === 0 || burst.trace.find(function (ev) { return ev.kind === 'heal'; }).t > 0, 'heal is not inside the opening burst');
const scheduledHps = 7500 / 3;
const spreadDps = (swingHits.length * 2000) / 30;
assert.ok(scheduledHps > spreadDps, 'scheduled HPS exceeds spread DPS');

const early = Tank.simulateTrial({
    className: 'Warrior', level: 65, maxHp: 3000, itemAc: 0, agi: 200, alwaysHit: true,
    phaseMs: 10000, horizonMs: 25000, trace: true,
    healing: { mode: 'fixed', amount: 2500, healers: 1, castMs: 1, spacingMs: 60000, jitterMs: 0, start: 'steady', phaseMs: 19500 },
    mob: { level: 5, attackCount: 1, attackDelay: 100, fixedDamage: 2500, atk: 0, accuracy: 0 }
}, 1);
eq(early.dead, false, 'heal 500ms early');

const late = Tank.simulateTrial({
    className: 'Warrior', level: 65, maxHp: 3000, itemAc: 0, agi: 200, alwaysHit: true,
    phaseMs: 10000, horizonMs: 25000, trace: true,
    healing: { mode: 'fixed', amount: 2500, healers: 1, castMs: 1, spacingMs: 60000, jitterMs: 0, start: 'steady', phaseMs: 20500 },
    mob: { level: 5, attackCount: 1, attackDelay: 100, fixedDamage: 2500, atk: 0, accuracy: 0 }
}, 1);
eq(late.dead, true, 'heal 500ms late');
assert.ok(late.hp < -10, 'late heal does not revive');
eq(late.trace.some(function (ev) { return ev.kind === 'heal' && ev.healed > 0 && ev.t > late.deathTime; }), false, 'no heal after death');

const none = Tank.simulate({
    className: 'Warrior', level: 65, maxHp: 100000, itemAc: 0, agi: 200, alwaysHit: true,
    phaseMs: 0, horizonMs: 5000, trials: 5, seed: 14650,
    healing: { mode: 'none' },
    mob: { level: 5, attackCount: 1, attackDelay: 100, fixedDamage: 100, atk: 0, accuracy: 0 }
});
eq(none.deaths, 0, 'short fight survives');

const longer = Tank.simulate({
    className: 'Warrior', level: 65, maxHp: 3000, itemAc: 0, agi: 200, alwaysHit: true,
    phaseMs: 10000, horizonMs: 15000, trials: 5, seed: 14650,
    healing: { mode: 'none' },
    mob: { level: 5, attackCount: 1, attackDelay: 100, fixedDamage: 4000, atk: 0, accuracy: 0 }
});
eq(longer.deaths, 5, 'longer horizon dies');

const repeatA = Tank.simulate({
    className: 'Warrior', level: 65, maxHp: 8000, itemAc: 400, agi: 200,
    horizonMs: 20000, trials: 30, seed: 14650,
    healing: { mode: 'fixed', amount: 2000, healers: 2, castMs: 2000, spacingMs: 2000, jitterMs: 500, start: 'steady' },
    mob: { level: 70, minHit: 400, maxHit: 900, atk: 200, accuracy: 100, attackCount: 1, attackDelay: 30, className: 'Warrior' }
});
const repeatB = Tank.simulate({
    className: 'Warrior', level: 65, maxHp: 8000, itemAc: 400, agi: 200,
    horizonMs: 20000, trials: 30, seed: 14650,
    healing: { mode: 'fixed', amount: 2000, healers: 2, castMs: 2000, spacingMs: 2000, jitterMs: 500, start: 'steady' },
    mob: { level: 70, minHit: 400, maxHit: 900, atk: 200, accuracy: 100, attackCount: 1, attackDelay: 30, className: 'Warrior' }
});
eq(repeatA.deaths, repeatB.deaths, 'repeatable deaths');
eq(repeatA.survivalProbability, repeatB.survivalProbability, 'repeatable survival');

const pairBase = {
    className: 'Warrior', level: 65, itemAc: 200, agi: 200, alwaysHit: true,
    phaseMs: 0, horizonMs: 60000, trials: 40, seed: 14650,
    healing: { mode: 'fixed', amount: 1800, healers: 1, castMs: 1000, spacingMs: 8000, jitterMs: 400, start: 'steady' },
    mob: { level: 5, attackCount: 1, attackDelay: 30, fixedDamage: 1600, atk: 0, accuracy: 0 }
};
const lowHp = Tank.simulate(Object.assign({}, pairBase, { maxHp: 4000 }));
const highHp = Tank.simulate(Object.assign({}, pairBase, { maxHp: 80000 }));
assert.ok(lowHp.deaths > highHp.deaths, 'lower HP dies more often under the same chain: ' + lowHp.deaths + ' vs ' + highHp.deaths);
eq(Math.round(lowHp.secondary.meanLandedHit), Math.round(highHp.secondary.meanLandedHit), 'same landed hit');
const lowAgain = Tank.simulate(Object.assign({}, pairBase, { maxHp: 4000 }));
eq(lowHp.deaths, lowAgain.deaths, 'paired seed repeats');

const off = Tank.simulateTrial({
    className: 'Warrior', level: 65, maxHp: 20000, itemAc: 0, agi: 200, alwaysHit: true,
    experimentalMod2: false, mod2: { shielding: 35, avoidance: 100, accuracy: 150 },
    phaseMs: 0, horizonMs: 1000, trace: true,
    mob: { level: 5, attackCount: 1, attackDelay: 50, minHit: 1000, maxHit: 1000, atk: 0, accuracy: 0 }
}, 3);
const on = Tank.simulateTrial({
    className: 'Warrior', level: 65, maxHp: 20000, itemAc: 0, agi: 200, alwaysHit: true,
    experimentalMod2: true, mod2: { shielding: 35, avoidance: 100, accuracy: 150 },
    phaseMs: 0, horizonMs: 1000, trace: true,
    mob: { level: 5, attackCount: 1, attackDelay: 50, minHit: 1000, maxHit: 1000, atk: 0, accuracy: 0 }
}, 3);
const offHit = off.trace.find(function (ev) { return ev.outcome === 'hit'; }).damage;
const onHit = on.trace.find(function (ev) { return ev.outcome === 'hit'; }).damage;
assert.ok(onHit < offHit, 'experimental shielding reduces the hit');
eq(offHit - onHit, 350, '35 percent of DB 1000');

const missing = Tank.simulate({ className: 'Warrior', maxHp: 1000, mob: { minHit: 1, maxHit: 2, level: 80 } });
eq(missing.runnable, false, 'missing delay blocks survival');
assert.ok(missing.perHit && missing.perHit.available, 'per-hit still available');

const interval = Tank.wilson(20, 100);
assert.ok(interval.low < 0.2 && interval.high > 0.2, 'wilson covers 0.2');

const sameRound = Tank.simulateTrial({
    className: 'Warrior', level: 65, maxHp: 5000, itemAc: 0, agi: 200, alwaysHit: true,
    phaseMs: 0, horizonMs: 1000, trace: true,
    healing: { mode: 'fixed', amount: 5000, healers: 1, castMs: 1, spacingMs: 60000, jitterMs: 0, start: 'steady', phaseMs: 0 },
    mob: { level: 5, attackCount: 2, attackDelay: 100, fixedDamage: 3000, atk: 0, accuracy: 0 }
}, 9);
eq(sameRound.dead, true, 'two hits before the simultaneous heal');
eq(sameRound.healed, 0, 'heal does not land before the killing round');

console.log(JSON.stringify({ ok: true, deaths: repeatA.deaths }));
