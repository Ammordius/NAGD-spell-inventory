/**
 * Node tests for raid_upgrade_planner.js
 * Run: node --test tests/js/raid_upgrade_planner.test.js
 */
'use strict';

const { test } = require('node:test');
const assert = require('node:assert/strict');
const path = require('path');

const RP = require(path.join(__dirname, '..', '..', 'raid_upgrade_planner.js'));

const PATTERN_ITEM = {
    item_id: '16363',
    name: 'Timeless Chain Tunic Pattern',
    acquisition_type: 'armor_pattern',
    purchase_item_id: '16363',
    wearable_item_id: null,
    class_wearables: { RNG: '32604', ROG: '32130', SHM: '32138' },
    sources: [
        { zone_id: 'plane_of_time', target_id: 'quarm|plane_of_time', mob: 'Quarm' }
    ],
    stats_present: true
};

const DIRECT_ITEM = {
    item_id: '9488',
    name: 'Abalone Engraved Tribal Mask',
    acquisition_type: 'direct_wearable',
    purchase_item_id: '9488',
    wearable_item_id: '9488',
    class_wearables: null,
    sources: [
        { zone_id: 'plane_of_water', target_id: 'hydrotha|plane_of_water', mob: 'Hydrotha' }
    ],
    stats_present: true
};

test('resolveWearableForCharacter maps armor_pattern by class', () => {
    const ok = RP.resolveWearableForCharacter(PATTERN_ITEM, 'ROG');
    assert.equal(ok.status, 'ok');
    assert.equal(ok.wearableItemId, '32130');
    assert.equal(ok.lootItemId, '16363');
    assert.ok(ok.acquisitionNote);

    const skip = RP.resolveWearableForCharacter(PATTERN_ITEM, 'WAR');
    assert.equal(skip.status, 'skip');
    assert.equal(skip.reason, 'no_class_wearable');
});

test('resolveWearableForCharacter direct_wearable uses wearable id', () => {
    const ok = RP.resolveWearableForCharacter(DIRECT_ITEM, 'CLR');
    assert.equal(ok.status, 'ok');
    assert.equal(ok.wearableItemId, '9488');
    assert.equal(ok.acquisitionNote, null);
});

test('resolveWearableForCharacter skips unresolved / missing stats', () => {
    const u = RP.resolveWearableForCharacter({
        item_id: '1',
        name: 'X',
        acquisition_type: 'unresolved',
        purchase_item_id: '1',
        wearable_item_id: null,
        stats_present: false
    }, 'WAR');
    assert.equal(u.status, 'skip');
});

test('getLastThreeDkp unknown stays unknown; zero costs preserved; no /0 ratios', () => {
    const unknown = RP.getLastThreeDkp({}, '999');
    assert.equal(unknown.unknown, true);
    assert.equal(unknown.average, null);

    const cache = {
        '100': { dkp_prices: [{ date: '2026-01-03', cost: 0 }, { date: '2026-01-02', cost: 0 }, { date: '2026-01-01', cost: 10 }] }
    };
    const info = RP.getLastThreeDkp(cache, 100);
    assert.equal(info.unknown, false);
    assert.equal(info.costs[0], 0);
    assert.ok(Math.abs(info.average - (10 / 3)) < 1e-9);

    assert.equal(RP.scorePerDkp(5, { average: 0, unknown: false }), null);
    assert.equal(RP.hpPerDkp(50, { average: 0, unknown: false }), null);
    assert.equal(RP.scorePerDkp(5, unknown), null);
    assert.ok(RP.scorePerDkp(5, { average: 2.5, unknown: false }) === 2);
});

test('checkMissingEquippedStats flags equipped item without stats', () => {
    const evalResult = {
        eligible: true,
        isUpgrade: true,
        slotId: 2,
        currentItemId: 555,
        itemId: 9488,
        scoreDelta: 10
    };
    const char = { inventory: [{ slot_id: 2, item_id: 555 }] };
    const missing = RP.checkMissingEquippedStats(evalResult, char, {}, () => false);
    assert.equal(missing.unresolved, true);
    assert.equal(missing.reason, 'unresolved_missing_equipped_stats');

    const ok = RP.checkMissingEquippedStats(evalResult, char, { 555: { name: 'Old' } }, () => false);
    assert.equal(ok.unresolved, false);
});

test('evaluateCatalogItemForCharacter only returns positive upgrades', () => {
    const itemStats = { 9488: { name: 'Mask' }, 100: { name: 'Old' } };
    const char = { id: '1', name: 'Alice', class: 'Cleric', inventory: [{ slot_id: 1, item_id: 100 }] };

    const positive = RP.evaluateCatalogItemForCharacter({
        catalogItem: DIRECT_ITEM,
        char,
        classAbbrev: 'CLR',
        itemStatsCache: itemStats,
        dkpPricesCache: { '9488': { dkp_prices: [{ cost: 100 }, { cost: 90 }, { cost: 80 }] } },
        evaluateFn: () => ({
            eligible: true,
            isUpgrade: true,
            scoreDelta: 12.5,
            delta: 12.5,
            slotId: 1,
            slotName: 'Face',
            currentItemId: 100,
            currentItemName: 'Old',
            itemId: 9488,
            itemName: 'Mask',
            deltas: { hpDelta: 25 },
            focusSpellName: ''
        }),
        isTwoHandedFn: () => false
    });
    assert.equal(positive.status, 'positive');
    assert.equal(positive.row.lootName, 'Abalone Engraved Tribal Mask');
    assert.equal(positive.row.wearableItemId, '9488');
    assert.ok(positive.row.dkpAverage > 0);

    const notUp = RP.evaluateCatalogItemForCharacter({
        catalogItem: DIRECT_ITEM,
        char,
        classAbbrev: 'CLR',
        itemStatsCache: itemStats,
        evaluateFn: () => ({
            eligible: true,
            isUpgrade: false,
            scoreDelta: -1,
            delta: -1,
            slotId: 1,
            currentItemId: 100,
            itemId: 9488
        }),
        isTwoHandedFn: () => false
    });
    assert.equal(notUp.status, 'skip');
    assert.equal(notUp.reason, 'not_positive');

    const unresolved = RP.evaluateCatalogItemForCharacter({
        catalogItem: DIRECT_ITEM,
        char,
        classAbbrev: 'CLR',
        itemStatsCache: { 9488: { name: 'Mask' } }, // current 100 missing
        evaluateFn: () => ({
            eligible: true,
            isUpgrade: true,
            scoreDelta: 5,
            delta: 5,
            slotId: 1,
            currentItemId: 100,
            itemId: 9488
        }),
        isTwoHandedFn: () => false
    });
    assert.equal(unresolved.status, 'unresolved');
});

test('zone and character grouping agree on positive row membership', () => {
    const catalog = {
        version: 1,
        zones: [
            { zone_id: 'plane_of_water', display_name: 'Plane of Water' },
            { zone_id: 'plane_of_time', display_name: 'Plane of Time' }
        ],
        targets: [
            { target_id: 'hydrotha|plane_of_water', zone_id: 'plane_of_water', display_name: 'Hydrotha', mob: 'Hydrotha' },
            { target_id: 'quarm|plane_of_time', zone_id: 'plane_of_time', display_name: 'Quarm', mob: 'Quarm' }
        ],
        items: [DIRECT_ITEM, PATTERN_ITEM]
    };

    const rows = [
        {
            charId: '1',
            charName: 'Alice',
            lootItemId: '9488',
            lootName: 'Mask',
            scoreDelta: 10,
            sources: DIRECT_ITEM.sources,
            wearableItemId: '9488',
            acquisitionType: 'direct_wearable'
        },
        {
            charId: '2',
            charName: 'Bob',
            lootItemId: '16363',
            lootName: 'Pattern',
            scoreDelta: 20,
            sources: PATTERN_ITEM.sources,
            wearableItemId: '32130',
            acquisitionType: 'armor_pattern'
        },
        {
            charId: '1',
            charName: 'Alice',
            lootItemId: '16363',
            lootName: 'Pattern',
            scoreDelta: 8,
            sources: PATTERN_ITEM.sources,
            wearableItemId: '32130',
            acquisitionType: 'armor_pattern'
        }
    ];

    const waterTargets = RP.groupByZoneTarget(rows, catalog, 'plane_of_water');
    const waterLootIds = new Set();
    waterTargets.forEach(t => t.items.forEach(it => waterLootIds.add(it.lootItemId)));
    assert.deepEqual([...waterLootIds], ['9488']);

    const byCharAll = RP.groupByCharacter(rows, catalog, 'all', 'score');
    const allLoot = new Set(byCharAll.rows.map(r => r.lootItemId + ':' + r.charId));
    assert.equal(allLoot.size, 3);

    const alice = RP.groupByCharacter(rows, catalog, '1', 'score');
    assert.equal(alice.rows.length, 2);
    assert.ok(alice.rows.every(r => r.charId === '1'));

    // Same positive pairs appear in zone projection of all rows
    const timeTargets = RP.groupByZoneTarget(rows, catalog, 'plane_of_time');
    const beneficiaries = [];
    timeTargets.forEach(t => t.items.forEach(it => it.beneficiaries.forEach(b => beneficiaries.push(b.charId + ':' + b.lootItemId))));
    assert.ok(beneficiaries.includes('2:16363'));
    assert.ok(beneficiaries.includes('1:16363'));
});

test('groupZoneByCharacter scopes to zone and groups by character', () => {
    const catalog = {
        zones: [
            { zone_id: 'plane_of_time', display_name: 'Plane of Time' },
            { zone_id: 'plane_of_water', display_name: 'Plane of Water' }
        ],
        targets: [
            { target_id: 'quarm|plane_of_time', zone_id: 'plane_of_time', display_name: 'Quarm', mob: 'Quarm' },
            { target_id: 'hydrotha|plane_of_water', zone_id: 'plane_of_water', display_name: 'Hydrotha', mob: 'Hydrotha' }
        ]
    };
    const rows = [
        {
            charId: '1',
            charName: 'Alice',
            charClass: 'Rogue',
            lootItemId: '9488',
            lootName: 'Mask',
            scoreDelta: 10,
            sources: DIRECT_ITEM.sources
        },
        {
            charId: '2',
            charName: 'Bob',
            charClass: 'Ranger',
            lootItemId: '16363',
            lootName: 'Pattern',
            scoreDelta: 20,
            sources: PATTERN_ITEM.sources
        },
        {
            charId: '1',
            charName: 'Alice',
            charClass: 'Rogue',
            lootItemId: '16363',
            lootName: 'Pattern',
            scoreDelta: 8,
            sources: PATTERN_ITEM.sources
        },
        {
            charId: '3',
            charName: 'Carol',
            charClass: 'Warrior',
            lootItemId: '9999',
            lootName: 'Other Zone Only',
            scoreDelta: 50,
            sources: [{ zone_id: 'plane_of_water', target_id: 'hydrotha|plane_of_water', mob: 'Hydrotha' }]
        }
    ];

    const timeByChar = RP.groupZoneByCharacter(rows, catalog, 'plane_of_time', 'score');
    assert.equal(timeByChar.length, 2);
    assert.deepEqual(timeByChar.map(c => c.charId), ['2', '1']); // score sort: Bob 20 before Alice 8
    assert.ok(timeByChar.every(c => c.charId !== '3'));

    const alice = timeByChar.find(c => c.charId === '1');
    assert.ok(alice);
    assert.equal(alice.charName, 'Alice');
    assert.equal(alice.targets.length, 1);
    assert.equal(alice.targets[0].targetId, 'quarm|plane_of_time');
    assert.equal(alice.targets[0].rows.length, 1);
    assert.equal(alice.targets[0].rows[0].lootItemId, '16363');

    const waterByChar = RP.groupZoneByCharacter(rows, catalog, 'plane_of_water', 'score');
    const waterCharIds = waterByChar.map(c => c.charId).sort();
    assert.deepEqual(waterCharIds, ['1', '3']);

    // Membership agrees with filterRowsForZone
    const waterRows = RP.filterRowsForZone(rows, 'plane_of_water');
    const waterPairs = new Set(waterRows.map(r => r.charId + ':' + r.lootItemId));
    const groupedPairs = new Set();
    waterByChar.forEach(c => c.targets.forEach(t => t.rows.forEach(r => groupedPairs.add(r.charId + ':' + r.lootItemId))));
    assert.deepEqual([...groupedPairs].sort(), [...waterPairs].sort());

    // Char with no upgrades in zone is omitted
    const onlyCarolWater = RP.groupZoneByCharacter(
        rows.filter(r => r.charId === '2'),
        catalog,
        'plane_of_water',
        'score'
    );
    assert.equal(onlyCarolWater.length, 0);
});

test('sortRows defaults to score improvement; score/DKP optional', () => {
    const rows = [
        { lootName: 'A', scoreDelta: 5, scorePerDkp: 0.1, hpPerDkp: 2 },
        { lootName: 'B', scoreDelta: 12, scorePerDkp: null, hpPerDkp: 9 },
        { lootName: 'C', scoreDelta: 8, scorePerDkp: 2, hpPerDkp: 1 }
    ];
    assert.equal(RP.sortRows(rows, 'score')[0].lootName, 'B');
    assert.equal(RP.sortRows(rows, 'score_dkp')[0].lootName, 'C');
    assert.equal(RP.sortRows(rows, 'hp_dkp')[0].lootName, 'B');
});

test('result cache hit/miss by key', () => {
    const cache = RP.createResultCache();
    const key = RP.buildCacheKey({ rosterIds: ['1', '2'], catalogVersion: 1, catalogItemCount: 2, mod2Enabled: false });
    assert.equal(cache.get(key), null);
    cache.set(key, { rows: [{ a: 1 }], unresolved: [], catalog: { version: 1 } });
    assert.equal(cache.get(key).rows.length, 1);
    cache.clear();
    assert.equal(cache.get(key), null);
});

test('checkMissingEquippedStats flags 2H offhand without stats', () => {
    const evalResult = {
        eligible: true,
        isUpgrade: true,
        slotId: 13,
        currentItemId: 100,
        itemId: 200,
        scoreDelta: 15
    };
    const char = {
        inventory: [
            { slot_id: 13, item_id: 100 },
            { slot_id: 14, item_id: 101 }
        ]
    };
    const itemStats = {
        100: { name: '1H' },
        200: { name: '2H', slot: 'PRIMARY', itemtype: '2H Slashing' }
        // 101 offhand missing
    };
    const missing = RP.checkMissingEquippedStats(
        evalResult,
        char,
        itemStats,
        (st) => !!(st && /2H/i.test(String(st.itemtype || '')))
    );
    assert.equal(missing.unresolved, true);
    assert.equal(missing.reason, 'unresolved_missing_equipped_stats');
});

test('zero or negative Magelo delta never becomes a positive planner row', () => {
    const char = { id: '1', name: 'Empty', class: 'Rogue', inventory: [] };
    const itemStats = { 32130: { name: 'Timeless Chain Tunic' } };

    for (const delta of [0, -3.5]) {
        const out = RP.evaluateCatalogItemForCharacter({
            catalogItem: PATTERN_ITEM,
            char,
            classAbbrev: 'ROG',
            itemStatsCache: itemStats,
            evaluateFn: () => ({
                eligible: true,
                isUpgrade: delta > 0,
                scoreDelta: delta,
                delta,
                slotId: 2,
                currentItemId: null,
                itemId: 32130,
                itemName: 'Timeless Chain Tunic',
                deltas: {}
            }),
            isTwoHandedFn: () => false
        });
        assert.equal(out.status, 'skip');
        assert.equal(out.reason, 'not_positive');
    }
});

test('planner scoreDelta matches evaluateFn for same wearable (parity)', () => {
    const char = {
        id: '9',
        name: 'Parity',
        class: 'Cleric',
        inventory: [{ slot_id: 1, item_id: 100 }]
    };
    const itemStats = { 9488: { name: 'Mask' }, 100: { name: 'Old' } };
    const mageloResult = {
        eligible: true,
        isUpgrade: true,
        scoreDelta: 4.25,
        delta: 4.25,
        slotId: 1,
        slotName: 'Face',
        currentItemId: 100,
        currentItemName: 'Old',
        itemId: 9488,
        itemName: 'Mask',
        deltas: { hpDelta: 10 }
    };
    let seenWearable = null;
    const out = RP.evaluateCatalogItemForCharacter({
        catalogItem: DIRECT_ITEM,
        char,
        classAbbrev: 'CLR',
        itemStatsCache: itemStats,
        dkpPricesCache: {},
        evaluateFn: (c, wearableId) => {
            seenWearable = String(wearableId);
            assert.equal(c.name, 'Parity');
            return mageloResult;
        },
        isTwoHandedFn: () => false
    });
    assert.equal(seenWearable, '9488');
    assert.equal(out.status, 'positive');
    assert.equal(out.row.scoreDelta, mageloResult.scoreDelta);
    assert.equal(out.row.slotId, mageloResult.slotId);
    assert.equal(out.row.currentItemId, mageloResult.currentItemId);
    assert.equal(out.row.wearableItemId, '9488');
});

test('armor_pattern class applicability alone does not create upgrades', () => {
    const char = { id: '2', name: 'War', class: 'Warrior', inventory: [] };
    const skipClass = RP.evaluateCatalogItemForCharacter({
        catalogItem: PATTERN_ITEM,
        char,
        classAbbrev: 'WAR',
        itemStatsCache: { 32130: { name: 'Tunic' } },
        evaluateFn: () => {
            throw new Error('evaluateFn must not run when class has no wearable');
        },
        isTwoHandedFn: () => false
    });
    assert.equal(skipClass.status, 'skip');
    assert.equal(skipClass.reason, 'no_class_wearable');
});

test('sortRows with all-unknown DKP does not invent zero ratios', () => {
    const rows = [
        { lootName: 'A', scoreDelta: 5, scorePerDkp: null, hpPerDkp: null, dkpUnknown: true },
        { lootName: 'B', scoreDelta: 12, scorePerDkp: null, hpPerDkp: null, dkpUnknown: true }
    ];
    const byScore = RP.sortRows(rows, 'score');
    assert.equal(byScore[0].lootName, 'B');
    const byDkp = RP.sortRows(rows, 'score_dkp');
    assert.equal(byDkp.length, 2);
    assert.equal(byDkp.every(r => r.scorePerDkp == null), true);
});

test('buildCacheKey differs when mod2Enabled flips', () => {
    const base = {
        rosterIds: ['1'],
        catalogVersion: 1,
        catalogItemCount: 10,
        weightsFingerprint: 'w1',
        statsStamp: 's',
        pricesStamp: 'p'
    };
    const a = RP.buildCacheKey(Object.assign({}, base, { mod2Enabled: false }));
    const b = RP.buildCacheKey(Object.assign({}, base, { mod2Enabled: true }));
    assert.notEqual(a, b);
});

test('computeAllUpgrades integrates evaluate + filters', () => {
    const catalog = {
        version: 1,
        zones: [{ zone_id: 'plane_of_water', display_name: 'Plane of Water' }],
        targets: [{ target_id: 'hydrotha|plane_of_water', zone_id: 'plane_of_water', display_name: 'Hydrotha', mob: 'Hydrotha' }],
        items: [DIRECT_ITEM, PATTERN_ITEM]
    };
    const roster = [
        { id: '1', name: 'Alice', class: 'Cleric', inventory: [] },
        { id: '2', name: 'Bob', class: 'Rogue', inventory: [] }
    ];
    const out = RP.computeAllUpgrades({
        catalog,
        roster,
        classToAbbrev: { Cleric: 'CLR', Rogue: 'ROG' },
        itemStatsCache: { 9488: { name: 'Mask' }, 32130: { name: 'Tunic' } },
        dkpPricesCache: {},
        evaluateFn: (char, wearableId) => {
            // Only Mask upgrades Cleric; Pattern wearable upgrades Rogue
            if (char.class === 'Cleric' && String(wearableId) === '9488') {
                return {
                    eligible: true, isUpgrade: true, scoreDelta: 3, delta: 3,
                    slotId: 1, slotName: 'Face', currentItemId: null, itemId: 9488, itemName: 'Mask', deltas: {}
                };
            }
            if (char.class === 'Rogue' && String(wearableId) === '32130') {
                return {
                    eligible: true, isUpgrade: true, scoreDelta: 7, delta: 7,
                    slotId: 2, slotName: 'Chest', currentItemId: null, itemId: 32130, itemName: 'Tunic', deltas: {}
                };
            }
            return { eligible: true, isUpgrade: false, scoreDelta: 0, delta: 0, slotId: 1, currentItemId: null, itemId: Number(wearableId) };
        },
        isTwoHandedFn: () => false
    });
    assert.equal(out.rows.length, 2);
    const names = out.rows.map(r => r.charName + ':' + r.lootItemId).sort();
    assert.deepEqual(names, ['Alice:9488', 'Bob:16363']);
});
