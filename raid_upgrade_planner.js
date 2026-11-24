/**
 * Raid Upgrade Planner — pure evaluation helpers for class_rankings.html?dkp_val=true.
 * No DOM. Scoring is supplied by the host via evaluateItemUpgradeForCharacter.
 * Catalog-driven; does not invent armor conversions or treat missing prices as zero.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.RaidUpgradePlanner = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    var ACQUISITION = Object.freeze({
        DIRECT: 'direct_wearable',
        PATTERN: 'armor_pattern',
        UNRESOLVED: 'unresolved'
    });

    var SORT = Object.freeze({
        SCORE: 'score',
        SCORE_DKP: 'score_dkp',
        HP_DKP: 'hp_dkp'
    });

    /**
     * Resolve the Magelo wearable id to score for a catalog item + character class abbrev.
     * @returns {{ status: string, wearableItemId: string|null, purchaseItemId: string|null,
     *            lootItemId: string, lootName: string, acquisitionType: string,
     *            acquisitionNote: string|null, reason: string|null }}
     */
    function resolveWearableForCharacter(catalogItem, classAbbrev) {
        if (!catalogItem || catalogItem.item_id == null) {
            return {
                status: 'skip',
                wearableItemId: null,
                purchaseItemId: null,
                lootItemId: null,
                lootName: '',
                acquisitionType: null,
                acquisitionNote: null,
                reason: 'bad_item'
            };
        }
        var lootItemId = String(catalogItem.item_id);
        var lootName = catalogItem.name || ('Item ' + lootItemId);
        var purchaseItemId = catalogItem.purchase_item_id != null
            ? String(catalogItem.purchase_item_id)
            : lootItemId;
        var acq = catalogItem.acquisition_type || ACQUISITION.UNRESOLVED;

        if (catalogItem.stats_present === false || acq === ACQUISITION.UNRESOLVED) {
            return {
                status: 'skip',
                wearableItemId: null,
                purchaseItemId: purchaseItemId,
                lootItemId: lootItemId,
                lootName: lootName,
                acquisitionType: acq,
                acquisitionNote: null,
                reason: catalogItem.unresolved_reason || 'unresolved'
            };
        }

        if (acq === ACQUISITION.PATTERN) {
            var map = catalogItem.class_wearables || {};
            var abbr = classAbbrev ? String(classAbbrev) : '';
            var wear = abbr && map[abbr] != null && String(map[abbr]).trim() !== ''
                ? String(map[abbr]).trim()
                : null;
            if (!wear) {
                return {
                    status: 'skip',
                    wearableItemId: null,
                    purchaseItemId: purchaseItemId,
                    lootItemId: lootItemId,
                    lootName: lootName,
                    acquisitionType: acq,
                    acquisitionNote: 'Requires class armor turn-in / craft',
                    reason: 'no_class_wearable'
                };
            }
            return {
                status: 'ok',
                wearableItemId: wear,
                purchaseItemId: purchaseItemId,
                lootItemId: lootItemId,
                lootName: lootName,
                acquisitionType: acq,
                acquisitionNote: 'Requires turn-in / craft to finished class armor',
                reason: null
            };
        }

        // direct_wearable (and any future equivalent)
        var wearable = catalogItem.wearable_item_id != null
            ? String(catalogItem.wearable_item_id)
            : lootItemId;
        return {
            status: 'ok',
            wearableItemId: wearable,
            purchaseItemId: purchaseItemId,
            lootItemId: lootItemId,
            lootName: lootName,
            acquisitionType: acq,
            acquisitionNote: null,
            reason: null
        };
    }

    /**
     * Last three DKP purchases + average. Unknown stays null (never coerced to 0).
     * Zero costs are preserved when present. Does not double-count: one id → one series.
     */
    function getLastThreeDkp(dkpPricesCache, itemId) {
        if (itemId == null || itemId === '') {
            return { prices: null, costs: null, average: null, unknown: true };
        }
        var entry = dkpPricesCache && dkpPricesCache[String(itemId)];
        if (!entry || !Array.isArray(entry.dkp_prices) || entry.dkp_prices.length === 0) {
            return { prices: null, costs: null, average: null, unknown: true };
        }
        var slice = entry.dkp_prices.slice(0, 3);
        var costs = slice.map(function (p) { return p && p.cost != null ? Number(p.cost) : null; });
        if (costs.some(function (c) { return c == null || isNaN(c); })) {
            // Keep only numeric costs for average; if none numeric → unknown
            var numeric = costs.filter(function (c) { return c != null && !isNaN(c); });
            if (!numeric.length) {
                return { prices: slice, costs: costs, average: null, unknown: true };
            }
            var avgPartial = numeric.reduce(function (a, b) { return a + b; }, 0) / numeric.length;
            return { prices: slice, costs: costs, average: avgPartial, unknown: false };
        }
        var avg = costs.reduce(function (a, b) { return a + b; }, 0) / costs.length;
        return { prices: slice, costs: costs, average: avg, unknown: false };
    }

    /** Score / DKP; null when average unknown or <= 0 (no divide-by-zero). */
    function scorePerDkp(scoreDelta, dkpInfo) {
        if (scoreDelta == null || isNaN(scoreDelta)) return null;
        if (!dkpInfo || dkpInfo.unknown || dkpInfo.average == null) return null;
        if (dkpInfo.average <= 0) return null;
        return scoreDelta / dkpInfo.average;
    }

    /** HP / DKP; null when missing/non-positive hp or avg DKP. */
    function hpPerDkp(hpDelta, dkpInfo) {
        if (hpDelta == null || !(hpDelta > 0)) return null;
        if (!dkpInfo || dkpInfo.unknown || dkpInfo.average == null || dkpInfo.average <= 0) return null;
        return hpDelta / dkpInfo.average;
    }

    /**
     * After evaluateItemUpgradeForCharacter: detect missing equipped-item stats on the
     * chosen slot (and offhand when 2H primary). Do not treat those as score-0 upgrades.
     */
    function checkMissingEquippedStats(evalResult, char, itemStatsCache, isTwoHandedFn) {
        if (!evalResult || !evalResult.eligible) {
            return { unresolved: false, reason: null };
        }
        var equipped = (char && char.inventory) || [];
        function statsMissing(itemId) {
            if (itemId == null || itemId === '' || isNaN(Number(itemId))) return false;
            var st = itemStatsCache[Number(itemId)] || itemStatsCache[String(itemId)];
            return !st;
        }
        var slotId = evalResult.slotId;
        var curId = evalResult.currentItemId;
        if (curId != null && statsMissing(curId)) {
            return { unresolved: true, reason: 'unresolved_missing_equipped_stats' };
        }
        // 2H replacing primary: baseline includes offhand
        var candId = evalResult.itemId;
        var candStats = itemStatsCache[Number(candId)] || itemStatsCache[String(candId)];
        var is2h = typeof isTwoHandedFn === 'function'
            ? isTwoHandedFn(candStats)
            : !!(candStats && (candStats.slot === 'PRIMARY' || /2H|TWO.?HAND/i.test(String(candStats.itemtype || candStats.itemType || ''))));
        if (slotId === 13 && is2h) {
            var oh = equipped.find(function (i) { return i.slot_id === 14; });
            var ohId = oh && oh.item_id != null && oh.item_id !== '' ? Number(oh.item_id) : null;
            if (ohId != null && !isNaN(ohId) && statsMissing(ohId)) {
                return { unresolved: true, reason: 'unresolved_missing_equipped_stats' };
            }
        }
        return { unresolved: false, reason: null };
    }

    /**
     * Build a positive-upgrade row, or null / unresolved marker.
     * evaluateFn(char, wearableItemId) → evaluateItemUpgradeForCharacter result.
     */
    function evaluateCatalogItemForCharacter(opts) {
        var catalogItem = opts.catalogItem;
        var char = opts.char;
        var classAbbrev = opts.classAbbrev;
        var evaluateFn = opts.evaluateFn;
        var itemStatsCache = opts.itemStatsCache || {};
        var dkpPricesCache = opts.dkpPricesCache || {};
        var isTwoHandedFn = opts.isTwoHandedFn;

        var resolved = resolveWearableForCharacter(catalogItem, classAbbrev);
        if (resolved.status !== 'ok') {
            return { status: 'skip', reason: resolved.reason, resolved: resolved };
        }

        var evalResult = evaluateFn(char, resolved.wearableItemId);
        if (!evalResult || !evalResult.eligible) {
            return {
                status: 'skip',
                reason: (evalResult && evalResult.reason) || 'ineligible',
                resolved: resolved,
                evalResult: evalResult || null
            };
        }

        var missing = checkMissingEquippedStats(evalResult, char, itemStatsCache, isTwoHandedFn);
        if (missing.unresolved) {
            return {
                status: 'unresolved',
                reason: missing.reason,
                resolved: resolved,
                evalResult: evalResult
            };
        }

        var delta = evalResult.scoreDelta != null ? evalResult.scoreDelta : evalResult.delta;
        if (!(evalResult.isUpgrade && delta > 0)) {
            return {
                status: 'skip',
                reason: 'not_positive',
                resolved: resolved,
                evalResult: evalResult
            };
        }

        var dkp = getLastThreeDkp(dkpPricesCache, resolved.wearableItemId);
        var hpDelta = evalResult.deltas && evalResult.deltas.hpDelta != null
            ? evalResult.deltas.hpDelta
            : 0;

        return {
            status: 'positive',
            reason: null,
            resolved: resolved,
            evalResult: evalResult,
            row: {
                charId: char.id != null ? String(char.id) : '',
                charName: char.name || '',
                charClass: char.class || '',
                classAbbrev: classAbbrev || '',
                lootItemId: resolved.lootItemId,
                lootName: resolved.lootName,
                purchaseItemId: resolved.purchaseItemId,
                wearableItemId: resolved.wearableItemId,
                acquisitionType: resolved.acquisitionType,
                acquisitionNote: resolved.acquisitionNote,
                slotId: evalResult.slotId,
                slotName: evalResult.slotName,
                currentItemId: evalResult.currentItemId,
                currentItemName: evalResult.currentItemName,
                scoreDelta: delta,
                deltas: evalResult.deltas || {},
                focusSpellName: evalResult.focusSpellName || '',
                wearableName: evalResult.itemName || evalResult.candidateName || '',
                dkpCosts: dkp.costs,
                dkpAverage: dkp.average,
                dkpUnknown: dkp.unknown,
                scorePerDkp: scorePerDkp(delta, dkp),
                hpPerDkp: hpPerDkp(hpDelta, dkp),
                sources: Array.isArray(catalogItem.sources) ? catalogItem.sources.slice() : []
            }
        };
    }

    /** Stable cache fingerprint for roster + scoring inputs. */
    function buildCacheKey(parts) {
        var rosterIds = (parts.rosterIds || []).map(String).slice().sort();
        return JSON.stringify({
            roster: rosterIds,
            catalogVersion: parts.catalogVersion != null ? parts.catalogVersion : null,
            catalogItemCount: parts.catalogItemCount != null ? parts.catalogItemCount : null,
            mod2: !!parts.mod2Enabled,
            weights: parts.weightsFingerprint || '',
            statsStamp: parts.statsStamp || '',
            pricesStamp: parts.pricesStamp || ''
        });
    }

    /**
     * Evaluate all catalog items for all roster characters.
     * Returns { rows, unresolved, skipped, cacheKey }.
     */
    function computeAllUpgrades(opts) {
        var catalog = opts.catalog;
        var roster = opts.roster || [];
        var classToAbbrev = opts.classToAbbrev || {};
        var evaluateFn = opts.evaluateFn;
        var itemStatsCache = opts.itemStatsCache || {};
        var dkpPricesCache = opts.dkpPricesCache || {};
        var isTwoHandedFn = opts.isTwoHandedFn;
        var onProgress = opts.onProgress;

        var items = (catalog && catalog.items) || [];
        var rows = [];
        var unresolved = [];
        var cacheKey = buildCacheKey({
            rosterIds: roster.map(function (c) { return c.id; }),
            catalogVersion: catalog && catalog.version,
            catalogItemCount: items.length,
            mod2Enabled: opts.mod2Enabled,
            weightsFingerprint: opts.weightsFingerprint,
            statsStamp: opts.statsStamp,
            pricesStamp: opts.pricesStamp
        });

        for (var ri = 0; ri < roster.length; ri++) {
            var char = roster[ri];
            var abbrev = classToAbbrev[char.class] || '';
            if (typeof onProgress === 'function') {
                onProgress({ charIndex: ri, charCount: roster.length, charName: char.name || '' });
            }
            for (var ii = 0; ii < items.length; ii++) {
                var result = evaluateCatalogItemForCharacter({
                    catalogItem: items[ii],
                    char: char,
                    classAbbrev: abbrev,
                    evaluateFn: evaluateFn,
                    itemStatsCache: itemStatsCache,
                    dkpPricesCache: dkpPricesCache,
                    isTwoHandedFn: isTwoHandedFn
                });
                if (result.status === 'positive' && result.row) {
                    rows.push(result.row);
                } else if (result.status === 'unresolved') {
                    unresolved.push({
                        charId: char.id != null ? String(char.id) : '',
                        charName: char.name || '',
                        lootItemId: result.resolved && result.resolved.lootItemId,
                        lootName: result.resolved && result.resolved.lootName,
                        reason: result.reason
                    });
                }
            }
        }

        return { rows: rows, unresolved: unresolved, cacheKey: cacheKey };
    }

    function sortRows(rows, mode) {
        var list = (rows || []).slice();
        var m = mode || SORT.SCORE;
        list.sort(function (a, b) {
            if (m === SORT.SCORE_DKP) {
                var sa = a.scorePerDkp != null ? a.scorePerDkp : -Infinity;
                var sb = b.scorePerDkp != null ? b.scorePerDkp : -Infinity;
                if (sb !== sa) return sb - sa;
            } else if (m === SORT.HP_DKP) {
                var ha = a.hpPerDkp != null ? a.hpPerDkp : -Infinity;
                var hb = b.hpPerDkp != null ? b.hpPerDkp : -Infinity;
                if (hb !== ha) return hb - ha;
            }
            var da = a.scoreDelta != null ? a.scoreDelta : 0;
            var db = b.scoreDelta != null ? b.scoreDelta : 0;
            if (db !== da) return db - da;
            return String(a.lootName || '').localeCompare(String(b.lootName || ''));
        });
        return list;
    }

    /**
     * Group positive rows for zone view: zone → targets → loot items (deduped) → beneficiaries.
     */
    function groupByZoneTarget(rows, catalog, zoneId) {
        var targetMeta = {};
        ((catalog && catalog.targets) || []).forEach(function (t) {
            targetMeta[t.target_id] = t;
        });
        var byTarget = {};
        (rows || []).forEach(function (row) {
            var sources = row.sources || [];
            var hit = false;
            sources.forEach(function (s) {
                if (zoneId && s.zone_id !== zoneId) return;
                hit = true;
                var tid = s.target_id || ('_unknown|' + (s.zone_id || ''));
                if (!byTarget[tid]) {
                    var meta = targetMeta[tid] || {};
                    byTarget[tid] = {
                        targetId: tid,
                        zoneId: s.zone_id || zoneId || meta.zone_id || '',
                        displayName: meta.display_name || s.mob || tid,
                        mob: meta.mob || s.mob || '',
                        items: {}
                    };
                }
                var bucket = byTarget[tid].items;
                var lid = row.lootItemId;
                if (!bucket[lid]) {
                    bucket[lid] = {
                        lootItemId: lid,
                        lootName: row.lootName,
                        purchaseItemId: row.purchaseItemId,
                        wearableItemId: row.wearableItemId,
                        acquisitionType: row.acquisitionType,
                        acquisitionNote: row.acquisitionNote,
                        beneficiaries: []
                    };
                }
                bucket[lid].beneficiaries.push(row);
            });
            if (!hit && !zoneId) {
                // no sources — skip
            }
        });

        var targets = Object.keys(byTarget).map(function (tid) {
            var t = byTarget[tid];
            var items = Object.keys(t.items).map(function (lid) {
                var it = t.items[lid];
                it.beneficiaries = sortRows(it.beneficiaries, SORT.SCORE);
                it.bestScoreDelta = it.beneficiaries.length
                    ? Math.max.apply(null, it.beneficiaries.map(function (b) { return b.scoreDelta || 0; }))
                    : 0;
                return it;
            });
            items.sort(function (a, b) { return (b.bestScoreDelta || 0) - (a.bestScoreDelta || 0); });
            return {
                targetId: t.targetId,
                zoneId: t.zoneId,
                displayName: t.displayName,
                mob: t.mob,
                items: items
            };
        });
        targets.sort(function (a, b) {
            return String(a.displayName || '').localeCompare(String(b.displayName || ''));
        });
        return targets;
    }

    /**
     * Group positive rows for character view: optionally filter by charId, then zone → target → rows.
     */
    function groupByCharacter(rows, catalog, charId, sortMode) {
        var filtered = (rows || []).filter(function (r) {
            if (!charId || charId === 'all') return true;
            return String(r.charId) === String(charId);
        });
        filtered = sortRows(filtered, sortMode || SORT.SCORE);

        var zoneMeta = {};
        ((catalog && catalog.zones) || []).forEach(function (z) {
            zoneMeta[z.zone_id] = z;
        });
        var targetMeta = {};
        ((catalog && catalog.targets) || []).forEach(function (t) {
            targetMeta[t.target_id] = t;
        });

        var byZone = {};
        filtered.forEach(function (row) {
            var sources = row.sources || [];
            if (!sources.length) {
                var zid0 = '_none';
                if (!byZone[zid0]) {
                    byZone[zid0] = { zoneId: zid0, displayName: 'Unknown', targets: {} };
                }
                var tid0 = '_none';
                if (!byZone[zid0].targets[tid0]) {
                    byZone[zid0].targets[tid0] = {
                        targetId: tid0,
                        displayName: 'Unassigned',
                        rows: []
                    };
                }
                byZone[zid0].targets[tid0].rows.push(row);
                return;
            }
            // Attach row once per distinct zone (avoid duplicating same row under every source in same zone)
            var seenZones = {};
            sources.forEach(function (s) {
                var zid = s.zone_id || '_none';
                var tid = s.target_id || ('_unknown|' + zid);
                var key = zid + '::' + tid;
                if (seenZones[key]) return;
                seenZones[key] = true;
                if (!byZone[zid]) {
                    byZone[zid] = {
                        zoneId: zid,
                        displayName: (zoneMeta[zid] && zoneMeta[zid].display_name) || zid,
                        targets: {}
                    };
                }
                if (!byZone[zid].targets[tid]) {
                    var meta = targetMeta[tid] || {};
                    byZone[zid].targets[tid] = {
                        targetId: tid,
                        displayName: meta.display_name || s.mob || tid,
                        rows: []
                    };
                }
                byZone[zid].targets[tid].rows.push(row);
            });
        });

        var zones = Object.keys(byZone).map(function (zid) {
            var z = byZone[zid];
            var targets = Object.keys(z.targets).map(function (tid) {
                var t = z.targets[tid];
                t.rows = sortRows(t.rows, sortMode || SORT.SCORE);
                return t;
            });
            targets.sort(function (a, b) {
                return String(a.displayName || '').localeCompare(String(b.displayName || ''));
            });
            return { zoneId: z.zoneId, displayName: z.displayName, targets: targets };
        });
        // Prefer catalog zone order
        var order = ((catalog && catalog.zones) || []).map(function (z) { return z.zone_id; });
        zones.sort(function (a, b) {
            var ia = order.indexOf(a.zoneId);
            var ib = order.indexOf(b.zoneId);
            if (ia < 0) ia = 999;
            if (ib < 0) ib = 999;
            if (ia !== ib) return ia - ib;
            return String(a.displayName || '').localeCompare(String(b.displayName || ''));
        });
        return { rows: filtered, zones: zones };
    }

    /**
     * Group positive rows for a single zone by character → target → rows.
     * Omits characters with no upgrades in the zone.
     * @returns {Array<{charId, charName, charClass, targets: Array<{targetId, displayName, rows}>}>}
     */
    function groupZoneByCharacter(rows, catalog, zoneId, sortMode) {
        var zoneRows = filterRowsForZone(rows, zoneId);
        zoneRows = sortRows(zoneRows, sortMode || SORT.SCORE);

        var targetMeta = {};
        ((catalog && catalog.targets) || []).forEach(function (t) {
            targetMeta[t.target_id] = t;
        });

        var byChar = {};
        var charOrder = [];
        zoneRows.forEach(function (row) {
            var cid = row.charId != null ? String(row.charId) : '';
            if (!byChar[cid]) {
                byChar[cid] = {
                    charId: cid,
                    charName: row.charName || '',
                    charClass: row.charClass || '',
                    targets: {}
                };
                charOrder.push(cid);
            }
            var sources = row.sources || [];
            var seenTargets = {};
            sources.forEach(function (s) {
                if (zoneId && s.zone_id !== zoneId) return;
                var tid = s.target_id || ('_unknown|' + (s.zone_id || zoneId || ''));
                if (seenTargets[tid]) return;
                seenTargets[tid] = true;
                if (!byChar[cid].targets[tid]) {
                    var meta = targetMeta[tid] || {};
                    byChar[cid].targets[tid] = {
                        targetId: tid,
                        displayName: meta.display_name || s.mob || tid,
                        rows: []
                    };
                }
                byChar[cid].targets[tid].rows.push(row);
            });
            if (!Object.keys(seenTargets).length && !zoneId) {
                var tid0 = '_none';
                if (!byChar[cid].targets[tid0]) {
                    byChar[cid].targets[tid0] = {
                        targetId: tid0,
                        displayName: 'Unassigned',
                        rows: []
                    };
                }
                byChar[cid].targets[tid0].rows.push(row);
            }
        });

        return charOrder.map(function (cid) {
            var c = byChar[cid];
            var targets = Object.keys(c.targets).map(function (tid) {
                var t = c.targets[tid];
                t.rows = sortRows(t.rows, sortMode || SORT.SCORE);
                return t;
            });
            targets.sort(function (a, b) {
                return String(a.displayName || '').localeCompare(String(b.displayName || ''));
            });
            return {
                charId: c.charId,
                charName: c.charName,
                charClass: c.charClass,
                targets: targets
            };
        }).filter(function (c) {
            return c.targets.some(function (t) { return t.rows && t.rows.length; });
        });
    }

    /** Format last-3 DKP for display; unknown → explicit unknown string. */
    function formatDkpLastThree(dkpCosts, dkpAverage, dkpUnknown) {
        if (dkpUnknown || !dkpCosts || !dkpCosts.length) return null;
        var parts = dkpCosts.filter(function (c) { return c != null && !isNaN(c); });
        if (!parts.length) return null;
        var avgStr = dkpAverage != null && !isNaN(dkpAverage) ? dkpAverage.toFixed(1) : '?';
        return {
            text: 'Last 3 DKP: ' + parts.join(', ') + ' (avg ' + avgStr + ')',
            costs: parts,
            average: dkpAverage
        };
    }

    /** In-memory result cache helpers. */
    function createResultCache() {
        var store = { key: null, rows: null, unresolved: null, catalog: null };
        return {
            get: function (key) {
                if (key && store.key === key && store.rows) {
                    return { rows: store.rows, unresolved: store.unresolved || [], catalog: store.catalog };
                }
                return null;
            },
            set: function (key, payload) {
                store.key = key;
                store.rows = payload.rows || [];
                store.unresolved = payload.unresolved || [];
                store.catalog = payload.catalog || null;
            },
            clear: function () {
                store.key = null;
                store.rows = null;
                store.unresolved = null;
                store.catalog = null;
            },
            currentKey: function () { return store.key; }
        };
    }

    function filterRowsForZone(rows, zoneId) {
        if (!zoneId) return rows || [];
        return (rows || []).filter(function (row) {
            return (row.sources || []).some(function (s) { return s.zone_id === zoneId; });
        });
    }

    return {
        ACQUISITION: ACQUISITION,
        SORT: SORT,
        resolveWearableForCharacter: resolveWearableForCharacter,
        getLastThreeDkp: getLastThreeDkp,
        scorePerDkp: scorePerDkp,
        hpPerDkp: hpPerDkp,
        checkMissingEquippedStats: checkMissingEquippedStats,
        evaluateCatalogItemForCharacter: evaluateCatalogItemForCharacter,
        buildCacheKey: buildCacheKey,
        computeAllUpgrades: computeAllUpgrades,
        sortRows: sortRows,
        groupByZoneTarget: groupByZoneTarget,
        groupByCharacter: groupByCharacter,
        groupZoneByCharacter: groupZoneByCharacter,
        formatDkpLastThree: formatDkpLastThree,
        createResultCache: createResultCache,
        filterRowsForZone: filterRowsForZone
    };
}));
