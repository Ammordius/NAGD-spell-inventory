/**
 * Node tests for class_rankings_gear_plans.js
 * Run: node --test tests/js/class_rankings_gear_plans.test.js
 *
 * Manual checklist (browser):
 * 1. Select gear for A, reopen → persists
 * 2. Different gear for B → A unchanged
 * 3. Refresh → both restored
 * 4. Change upgrades-per-slot → selections remain
 * 5. Saved item outside top N → still selected
 * 6. Magelo equip changes → plan intact, Acquired updates
 * 7. 2H/OH consistent
 * 8. Clear/reset only intended character
 * 9. Without dkp_val, DKP UI stays gated; planning works
 * 10. No plan data sent to server
 * + Viewing does not claim; edit auto-claims; unclaim keeps plan
 */
'use strict';

const { test, beforeEach, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

// In-memory localStorage shim
function makeMemoryStorage() {
    const map = new Map();
    return {
        getItem(k) { return map.has(k) ? map.get(k) : null; },
        setItem(k, v) { map.set(String(k), String(v)); },
        removeItem(k) { map.delete(k); },
        clear() { map.clear(); },
        _map: map
    };
}

let GP;
let storage;

beforeEach(() => {
    storage = makeMemoryStorage();
    global.localStorage = storage;
    delete require.cache[require.resolve('../../class_rankings_gear_plans.js')];
    GP = require('../../class_rankings_gear_plans.js');
});

afterEach(() => {
    delete global.localStorage;
});

test('viewing records recent but does not claim or create a plan', () => {
    GP.recordView({ id: '101', name: 'Alice', class: 'Paladin' });
    const recent = GP.listRecent();
    assert.equal(recent.length, 1);
    assert.equal(recent[0].id, '101');
    assert.equal(GP.hasSavedPlan('101'), false);
    assert.equal(GP.isEffectivelyClaimed('101'), false);
    assert.equal(GP.getClaimPreference('101'), null);
});

test('meaningful edit saves sparse plan, sets editedAt, effective claim under auto', () => {
    const char = { id: '201', name: 'Bob', class: 'Warrior' };
    const equipped = { 13: 100, 14: 200 };
    const virtual = { 13: 999, 14: 200 }; // only main hand changed
    GP.persistUserGearEdit(char, equipped, virtual);
    const plan = GP.getCharacterPlan('201');
    assert.ok(plan);
    assert.equal(plan.selectedSlots['13'], 999);
    assert.equal(plan.selectedSlots['14'], undefined);
    assert.ok(plan.editedAt);
    assert.equal(GP.getClaimPreference('201'), 'auto');
    assert.equal(GP.isEffectivelyClaimed('201'), true);
});

test('explicit empty slot is stored as null and differs from unspecified', () => {
    const selected = GP.diffSelectedSlots({ 14: 55 }, { 14: null });
    assert.equal(selected['14'], null);
    const loadout = GP.applyPlanToLoadout({ 13: 1, 14: 55 }, { '14': null });
    assert.equal(loadout[14], null);
    assert.equal(loadout[13], 1);
});

test('init/restore path helpers do not imply claim without edit preference', () => {
    // Simulate restore-only: plan written without going through persistUserGearEdit claim ensure
    // (should not happen in UI, but loading existing plan alone doesn't call setClaimPreference)
    GP.setCharacterPlan('301', {
        name: 'Carol',
        class: 'Cleric',
        selectedSlots: { '17': 50 },
        updatedAt: '2026-01-01T00:00:00.000Z'
        // no editedAt
    });
    assert.equal(GP.getClaimPreference('301'), null);
    // hasSavedPlan alone with missing preference → effectively claimed per auto rule
    assert.equal(GP.isEffectivelyClaimed('301'), true);
    // Explicit unclaim overrides
    GP.setClaimPreference('301', 'unclaimed');
    assert.equal(GP.isEffectivelyClaimed('301'), false);
    assert.equal(GP.hasSavedPlan('301'), true);
});

test('explicit unclaim overrides auto and preserves gear + recent', () => {
    GP.recordView({ id: '401', name: 'Dana', class: 'Druid' });
    GP.persistUserGearEdit(
        { id: '401', name: 'Dana', class: 'Druid' },
        { 5: 10 },
        { 5: 99 }
    );
    assert.equal(GP.isEffectivelyClaimed('401'), true);
    GP.setClaimPreference('401', 'unclaimed');
    assert.equal(GP.isEffectivelyClaimed('401'), false);
    assert.equal(GP.hasSavedPlan('401'), true);
    assert.equal(GP.listRecent().some(r => r.id === '401'), true);
    // Further edits while unclaimed do not flip claim
    GP.persistUserGearEdit(
        { id: '401', name: 'Dana', class: 'Druid' },
        { 5: 10 },
        { 5: 100 }
    );
    assert.equal(GP.getClaimPreference('401'), 'unclaimed');
    assert.equal(GP.isEffectivelyClaimed('401'), false);
    assert.equal(GP.getCharacterPlan('401').selectedSlots['5'], 100);
});

test('explicit claimed sticks without requiring edits', () => {
    GP.setClaimPreference('501', 'claimed');
    assert.equal(GP.isEffectivelyClaimed('501'), true);
    assert.equal(GP.hasSavedPlan('501'), false);
});

test('per-character isolation of plans, claims, and views', () => {
    GP.recordView({ id: '1', name: 'A', class: 'Warrior' });
    GP.recordView({ id: '2', name: 'B', class: 'Cleric' });
    GP.persistUserGearEdit({ id: '1', name: 'A', class: 'Warrior' }, { 2: 1 }, { 2: 9 });
    GP.setClaimPreference('2', 'claimed');
    assert.equal(GP.hasSavedPlan('1'), true);
    assert.equal(GP.hasSavedPlan('2'), false);
    assert.equal(GP.isEffectivelyClaimed('1'), true);
    assert.equal(GP.isEffectivelyClaimed('2'), true);
    GP.clearCharacterPlan('1');
    assert.equal(GP.hasSavedPlan('1'), false);
    assert.equal(GP.isEffectivelyClaimed('2'), true);
});

test('buildSlotExtras inserts saved ids missing from option lists', () => {
    const extras = GP.buildSlotExtras(
        { '13': 777 },
        { 13: new Set([100, 200]) },
        { 777: { name: 'Rare Blade' } }
    );
    assert.equal(extras[13].length, 1);
    assert.equal(extras[13][0].id, 777);
    assert.equal(extras[13][0].name, 'Rare Blade');
});

test('deriveTargets statuses and claimed default scope', () => {
    const chars = [{
        id: '601',
        name: 'Eve',
        class: 'Enchanter',
        inventory: [
            { slot_id: 1, item_id: 10, item_name: 'Old Ear' },
            { slot_id: 2, item_id: 20, item_name: 'Old Head' }
        ]
    }, {
        id: '602',
        name: 'Frank',
        class: 'Wizard',
        inventory: [{ slot_id: 1, item_id: 11, item_name: 'Ear' }]
    }];
    GP.persistUserGearEdit(
        { id: '601', name: 'Eve', class: 'Enchanter' },
        { 1: 10, 2: 20 },
        { 1: 10, 2: 888 } // seeking head upgrade
    );
    // Acquired: same as equipped
    GP.setCharacterPlan('601', {
        name: 'Eve',
        class: 'Enchanter',
        selectedSlots: { '1': 10, '2': 888 },
        editedAt: '2026-01-01T00:00:00.000Z'
    });
    // Unclaimed character with a plan
    GP.setCharacterPlan('602', {
        name: 'Frank',
        class: 'Wizard',
        selectedSlots: { '1': 999 },
        editedAt: '2026-01-01T00:00:00.000Z'
    });
    GP.setClaimPreference('602', 'unclaimed');

    const cache = {
        10: { name: 'Old Ear' },
        20: { name: 'Old Head' },
        888: { name: 'New Helm' },
        999: { name: 'Mystery' }
        // 999 present; also test Needs Review with missing id elsewhere
    };
    GP.setCharacterPlan('601', {
        name: 'Eve',
        class: 'Enchanter',
        selectedSlots: { '1': 10, '2': 888, '3': 40404 },
        editedAt: '2026-01-01T00:00:00.000Z'
    });

    const claimedRows = GP.deriveTargets(chars, GP.loadPlans(), cache, { scope: 'claimed' });
    assert.ok(claimedRows.every(r => r.characterId === '601'));
    const bySlot = Object.fromEntries(claimedRows.map(r => [r.slotId, r]));
    assert.equal(bySlot[1].status, 'Acquired');
    assert.equal(bySlot[2].status, 'Seeking');
    assert.equal(bySlot[3].status, 'Needs Review');

    const allRows = GP.deriveTargets(chars, GP.loadPlans(), cache, { scope: 'all' });
    assert.ok(allRows.some(r => r.characterId === '602'));
});

test('removeTarget and clearAcquired', () => {
    const chars = [{
        id: '701',
        name: 'Gus',
        class: 'Rogue',
        inventory: [{ slot_id: 15, item_id: 50, item_name: 'Ring' }]
    }];
    GP.setCharacterPlan('701', {
        name: 'Gus',
        class: 'Rogue',
        selectedSlots: { '15': 50, '16': 60 },
        editedAt: '2026-01-01T00:00:00.000Z'
    });
    GP.setClaimPreference('701', 'claimed');
    const cache = { 50: { name: 'Ring' }, 60: { name: 'Other' } };
    GP.clearAcquired(chars, cache, { scope: 'all' });
    const plan = GP.getCharacterPlan('701');
    assert.equal(plan.selectedSlots['15'], undefined);
    assert.equal(plan.selectedSlots['16'], 60);
    GP.removeTarget('701', 16);
    assert.equal(GP.hasSavedPlan('701'), false);
});

test('malformed JSON and missing storage are tolerated', () => {
    storage.setItem(GP.KEYS.plans, '{not-json');
    const plans = GP.loadPlans();
    assert.deepEqual(plans.characters, {});
    storage.setItem(GP.KEYS.claims, 'null');
    assert.deepEqual(GP.loadClaims().characters, {});

    // Unavailable storage
    delete global.localStorage;
    delete require.cache[require.resolve('../../class_rankings_gear_plans.js')];
    const GP2 = require('../../class_rankings_gear_plans.js');
    assert.doesNotThrow(() => GP2.recordView({ id: '9', name: 'X', class: 'Bard' }));
    assert.equal(GP2.hasSavedPlan('9'), false);
});

test('toon list persistence', () => {
    assert.equal(GP.loadToonList(), '');
    GP.saveToonList('ammo*, tandiyen');
    assert.equal(GP.loadToonList(), 'ammo*, tandiyen');
});

test('module path loads from repo root', () => {
    assert.ok(GP.KEYS.plans.includes('gearPlans'));
    assert.equal(path.basename(require.resolve('../../class_rankings_gear_plans.js')), 'class_rankings_gear_plans.js');
});
