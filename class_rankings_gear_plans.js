/**
 * Class Rankings — browser-local gear plans, recently viewed, and claim preferences.
 * No network I/O. Claims are local preferences only, not authenticated ownership.
 *
 * Slot interest schema (plans.version >= 2):
 *   selectedSlots[slotId] = {
 *     preferredItemId: number|null,   // drives Stat Simulator virtual loadout
 *     candidates: [{ itemId: number|null, bid?: number|null }]
 *   }
 * Legacy v1 values (number|null) migrate on load. Bid is optional; UI gates editing
 * behind ?dkp_val=true (0 = rot roll intent).
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.ClassRankingsGearPlans = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const KEYS = {
        plans: 'classRankings:gearPlans:v1',
        recent: 'classRankings:recentChars:v1',
        claims: 'classRankings:charClaims:v1',
        toonList: 'classRankings:toonList:v1'
    };

    const RECENT_CAP = 100;
    const PLAN_VERSION = 2;
    const CLAIM_PREFS = Object.freeze(['auto', 'claimed', 'unclaimed']);

    function nowIso() {
        return new Date().toISOString();
    }

    function charKey(id) {
        if (id == null || id === '') return null;
        return String(id);
    }

    function safeStorage() {
        try {
            if (typeof localStorage === 'undefined') return null;
            return localStorage;
        } catch (e) {
            return null;
        }
    }

    function readJson(key, fallback) {
        const store = safeStorage();
        if (!store) return fallback;
        try {
            const raw = store.getItem(key);
            if (raw == null || raw === '') return fallback;
            const parsed = JSON.parse(raw);
            if (!parsed || typeof parsed !== 'object') return fallback;
            return parsed;
        } catch (e) {
            console.warn('ClassRankingsGearPlans: malformed JSON for', key, e);
            return fallback;
        }
    }

    function writeJson(key, value) {
        const store = safeStorage();
        if (!store) return false;
        try {
            store.setItem(key, JSON.stringify(value));
            return true;
        } catch (e) {
            console.warn('ClassRankingsGearPlans: unable to write', key, e);
            return false;
        }
    }

    function emptyPlans() {
        return { version: PLAN_VERSION, characters: {} };
    }

    function emptyRecent() {
        return { version: 1, characters: {} };
    }

    function emptyClaims() {
        return { version: 1, characters: {} };
    }

    function normalizeItemId(raw) {
        if (raw == null || raw === '') return null;
        const n = Number(raw);
        return isNaN(n) ? null : n;
    }

    function sameItemId(a, b) {
        const na = normalizeItemId(a);
        const nb = normalizeItemId(b);
        if (na == null && nb == null) return true;
        if (na == null || nb == null) return false;
        return na === nb;
    }

    function normalizeBid(raw) {
        if (raw == null || raw === '') return null;
        const n = Number(raw);
        if (isNaN(n) || n < 0) return null;
        return n;
    }

    /**
     * Normalize a single slot entry to { preferredItemId, candidates[] }.
     * Accepts legacy number|null or already-normalized objects.
     */
    function normalizeSlotInterest(raw) {
        if (raw != null && typeof raw === 'object' && !Array.isArray(raw)) {
            const preferredItemId = Object.prototype.hasOwnProperty.call(raw, 'preferredItemId')
                ? normalizeItemId(raw.preferredItemId)
                : (Object.prototype.hasOwnProperty.call(raw, 'itemId')
                    ? normalizeItemId(raw.itemId)
                    : null);
            let candidates = Array.isArray(raw.candidates) ? raw.candidates.slice() : [];
            candidates = candidates.map(function (c) {
                if (c != null && typeof c === 'object') {
                    const itemId = Object.prototype.hasOwnProperty.call(c, 'itemId')
                        ? normalizeItemId(c.itemId)
                        : null;
                    const out = { itemId: itemId };
                    const bid = normalizeBid(c.bid);
                    if (bid != null) out.bid = bid;
                    return out;
                }
                return { itemId: normalizeItemId(c) };
            });
            // Ensure preferred is among candidates (and last = preferred order)
            const prefIdx = candidates.findIndex(function (c) {
                return sameItemId(c.itemId, preferredItemId);
            });
            if (prefIdx < 0) {
                candidates.push({ itemId: preferredItemId });
            } else if (prefIdx !== candidates.length - 1) {
                const [moved] = candidates.splice(prefIdx, 1);
                candidates.push(moved);
            }
            // Dedupe by itemId keeping last occurrence
            const seen = {};
            const deduped = [];
            for (let i = candidates.length - 1; i >= 0; i--) {
                const key = candidates[i].itemId == null ? '__null__' : String(candidates[i].itemId);
                if (seen[key]) continue;
                seen[key] = true;
                deduped.unshift(candidates[i]);
            }
            return {
                preferredItemId: preferredItemId,
                candidates: deduped
            };
        }
        // Legacy scalar
        const itemId = normalizeItemId(raw);
        return {
            preferredItemId: itemId,
            candidates: [{ itemId: itemId }]
        };
    }

    function normalizeSelectedSlots(selectedSlots) {
        const out = {};
        const src = selectedSlots || {};
        Object.keys(src).forEach(function (key) {
            out[String(key)] = normalizeSlotInterest(src[key]);
        });
        return out;
    }

    function preferredIdFromSlot(slotInterest) {
        if (slotInterest == null) return undefined;
        if (typeof slotInterest === 'object' && !Array.isArray(slotInterest)) {
            return normalizeItemId(slotInterest.preferredItemId);
        }
        return normalizeItemId(slotInterest);
    }

    function migratePlansInPlace(data) {
        let changed = false;
        if (!data.characters || typeof data.characters !== 'object') {
            data.characters = {};
            changed = true;
        }
        Object.keys(data.characters).forEach(function (id) {
            const plan = data.characters[id];
            if (!plan || typeof plan !== 'object') return;
            if (!plan.selectedSlots || typeof plan.selectedSlots !== 'object') {
                plan.selectedSlots = {};
                changed = true;
                return;
            }
            const next = {};
            Object.keys(plan.selectedSlots).forEach(function (slotKey) {
                const raw = plan.selectedSlots[slotKey];
                const needsNorm = !(raw != null && typeof raw === 'object' && !Array.isArray(raw)
                    && Object.prototype.hasOwnProperty.call(raw, 'preferredItemId')
                    && Array.isArray(raw.candidates));
                const norm = normalizeSlotInterest(raw);
                next[String(slotKey)] = norm;
                if (needsNorm) changed = true;
            });
            plan.selectedSlots = next;
        });
        if (data.version !== PLAN_VERSION) {
            data.version = PLAN_VERSION;
            changed = true;
        }
        return changed;
    }

    function loadPlans() {
        const data = readJson(KEYS.plans, emptyPlans());
        const changed = migratePlansInPlace(data);
        if (changed) writeJson(KEYS.plans, data);
        return data;
    }

    function savePlans(plans) {
        const payload = plans && typeof plans === 'object' ? plans : emptyPlans();
        migratePlansInPlace(payload);
        payload.version = PLAN_VERSION;
        if (!payload.characters || typeof payload.characters !== 'object') payload.characters = {};
        return writeJson(KEYS.plans, payload);
    }

    function getCharacterPlan(charId, plans) {
        const id = charKey(charId);
        if (!id) return null;
        const store = plans || loadPlans();
        const plan = store.characters[id];
        return plan && typeof plan === 'object' ? plan : null;
    }

    function setCharacterPlan(charId, planPatch, options) {
        const id = charKey(charId);
        if (!id) {
            console.warn('ClassRankingsGearPlans: skip plan save — missing character id');
            return null;
        }
        const opts = options || {};
        const store = loadPlans();
        const prev = store.characters[id] || {};
        const next = {
            name: planPatch.name != null ? planPatch.name : (prev.name || ''),
            class: planPatch.class != null ? planPatch.class : (prev.class || ''),
            selectedSlots: planPatch.selectedSlots != null
                ? normalizeSelectedSlots(planPatch.selectedSlots)
                : normalizeSelectedSlots(prev.selectedSlots || {}),
            updatedAt: planPatch.updatedAt || nowIso()
        };
        if (planPatch.editedAt != null) {
            next.editedAt = planPatch.editedAt;
        } else if (prev.editedAt && !opts.clearEdited) {
            next.editedAt = prev.editedAt;
        }
        store.characters[id] = next;
        savePlans(store);
        return next;
    }

    function clearCharacterPlan(charId) {
        const id = charKey(charId);
        if (!id) return false;
        const store = loadPlans();
        if (!store.characters[id]) return false;
        delete store.characters[id];
        return savePlans(store);
    }

    function hasSavedPlan(charId, plans) {
        const plan = getCharacterPlan(charId, plans);
        if (!plan || !plan.selectedSlots || typeof plan.selectedSlots !== 'object') return false;
        return Object.keys(plan.selectedSlots).length > 0;
    }

    function getSlotInterest(plan, slotId) {
        if (!plan || !plan.selectedSlots) return null;
        const key = String(slotId);
        const raw = plan.selectedSlots[key];
        if (raw === undefined) return null;
        return normalizeSlotInterest(raw);
    }

    function listSlotCandidates(plan, slotId) {
        const interest = getSlotInterest(plan, slotId);
        return interest ? interest.candidates.slice() : [];
    }

    function isSeekingItem(plan, slotId, itemId) {
        const interest = getSlotInterest(plan, slotId);
        if (!interest) return false;
        return interest.candidates.some(function (c) {
            return sameItemId(c.itemId, itemId);
        });
    }

    function getBid(plan, slotId, itemId) {
        const interest = getSlotInterest(plan, slotId);
        if (!interest) return null;
        const hit = interest.candidates.find(function (c) {
            return sameItemId(c.itemId, itemId);
        });
        return hit && hit.bid != null ? hit.bid : null;
    }

    /**
     * Compare virtual loadout to Magelo equipped. Returns sparse preferred map
     * as normalized slot interests (preserves existing candidates when merging
     * via persistUserGearEdit). For a standalone diff (no prior plan), each
     * changed slot gets a single preferred candidate.
     */
    function diffSelectedSlots(equippedBySlot, virtualLoadout, existingSelectedSlots) {
        const out = {};
        const equipped = equippedBySlot || {};
        const virtual = virtualLoadout || {};
        const existing = existingSelectedSlots || {};
        for (let slotId = 1; slotId <= 22; slotId++) {
            const key = String(slotId);
            const hasVirtual = Object.prototype.hasOwnProperty.call(virtual, slotId)
                || Object.prototype.hasOwnProperty.call(virtual, key);
            if (!hasVirtual) continue;
            const raw = virtual[slotId] !== undefined ? virtual[slotId] : virtual[key];
            const picked = normalizeItemId(raw);
            const eqRaw = equipped[slotId] !== undefined ? equipped[slotId] : equipped[key];
            const equippedId = normalizeItemId(eqRaw);
            const prior = existing[key] !== undefined
                ? normalizeSlotInterest(existing[key])
                : (existing[slotId] !== undefined ? normalizeSlotInterest(existing[slotId]) : null);

            const preferredMatchesEquipped = sameItemId(picked, equippedId);
            if (preferredMatchesEquipped && !prior) continue;

            if (preferredMatchesEquipped && prior) {
                // Keep other seeking candidates; drop preferred back to equipped baseline
                const remaining = prior.candidates.filter(function (c) {
                    return !sameItemId(c.itemId, equippedId) && !sameItemId(c.itemId, picked);
                });
                // Also drop candidates that equal equipped (acquired)
                const filtered = remaining.filter(function (c) {
                    return !sameItemId(c.itemId, equippedId);
                });
                if (filtered.length === 0) continue;
                // Prefer last remaining candidate
                const last = filtered[filtered.length - 1];
                out[key] = {
                    preferredItemId: last.itemId,
                    candidates: filtered
                };
                continue;
            }

            // Preferred differs from equipped — ensure candidate + prefer it
            let candidates = prior ? prior.candidates.slice() : [];
            const idx = candidates.findIndex(function (c) {
                return sameItemId(c.itemId, picked);
            });
            if (idx >= 0) {
                const [moved] = candidates.splice(idx, 1);
                candidates.push(moved);
            } else {
                candidates.push({ itemId: picked });
            }
            out[key] = {
                preferredItemId: picked,
                candidates: candidates
            };
        }
        // Preserve slots that only have non-preferred seeking candidates and were
        // not present in virtualLoadout keys... virtualLoadout usually has all slots.
        // When persist merges, existing slots not touched above but still seeking
        // are handled by persistUserGearEdit merge below.
        return out;
    }

    /**
     * Apply sparse selectedSlots onto Magelo equipped baseline → full loadout map (numeric keys).
     * Uses preferredItemId from each slot interest.
     */
    function applyPlanToLoadout(equippedBySlot, selectedSlots) {
        const loadout = {};
        const equipped = equippedBySlot || {};
        const selected = selectedSlots || {};
        for (let slotId = 1; slotId <= 22; slotId++) {
            const key = String(slotId);
            const eqRaw = equipped[slotId] !== undefined ? equipped[slotId] : equipped[key];
            const equippedId = normalizeItemId(eqRaw);
            if (Object.prototype.hasOwnProperty.call(selected, key)
                || Object.prototype.hasOwnProperty.call(selected, slotId)) {
                const raw = selected[key] !== undefined ? selected[key] : selected[slotId];
                loadout[slotId] = preferredIdFromSlot(normalizeSlotInterest(raw));
            } else {
                loadout[slotId] = equippedId;
            }
        }
        return loadout;
    }

    /**
     * For saved ids not already in option lists, build slotExtras entries from itemStatsCache.
     */
    function buildSlotExtras(selectedSlots, optionIdsBySlot, itemStatsCache) {
        const extras = {};
        const selected = selectedSlots || {};
        const options = optionIdsBySlot || {};
        const cache = itemStatsCache || {};
        Object.keys(selected).forEach(function (key) {
            const slotId = Number(key);
            if (isNaN(slotId)) return;
            const interest = normalizeSlotInterest(selected[key]);
            const existing = options[slotId] || options[key] || [];
            const idSet = existing instanceof Set
                ? existing
                : new Set([].concat(existing).map(Number));
            interest.candidates.forEach(function (c) {
                if (c.itemId == null) return;
                if (idSet.has(c.itemId)) return;
                const stats = cache[c.itemId] || cache[String(c.itemId)];
                if (!extras[slotId]) extras[slotId] = [];
                extras[slotId].push({
                    id: c.itemId,
                    name: (stats && stats.name) ? stats.name : ('Item ' + c.itemId)
                });
                idSet.add(c.itemId);
            });
        });
        return extras;
    }

    function equippedMapFromChar(char) {
        const map = {};
        const inv = (char && char.inventory) || [];
        inv.forEach(function (row) {
            const slotId = Number(row.slot_id);
            if (slotId < 1 || slotId > 22) return;
            map[slotId] = (row.item_id != null && row.item_id !== '') ? Number(row.item_id) : null;
        });
        return map;
    }

    function targetStatus(equippedId, targetId, itemStatsCache) {
        if (targetId != null && equippedId != null && Number(targetId) === Number(equippedId)) {
            return 'Acquired';
        }
        if (targetId == null) {
            if (equippedId != null) return 'Seeking';
            return 'Acquired';
        }
        const cache = itemStatsCache || {};
        const stats = cache[targetId] || cache[String(targetId)];
        if (!stats) return 'Needs Review';
        return 'Seeking';
    }

    function itemNameFromCache(itemId, itemStatsCache, emptyLabel) {
        if (itemId == null) return emptyLabel || '— None —';
        const cache = itemStatsCache || {};
        const stats = cache[itemId] || cache[String(itemId)];
        return (stats && stats.name) ? stats.name : ('Item ' + itemId);
    }

    /**
     * Derive gear-target rows (one per seeking candidate).
     * options.scope: 'claimed' (default) | 'all' | { characterIds: [] }
     */
    function deriveTargets(characters, plans, itemStatsCache, options) {
        const opts = options || {};
        const planStore = plans || loadPlans();
        const claimStore = opts.claims || loadClaims();
        const chars = Array.isArray(characters) ? characters : [];
        const byId = {};
        chars.forEach(function (c) {
            const id = charKey(c && c.id);
            if (id) byId[id] = c;
        });

        let idList;
        if (opts.scope === 'all') {
            idList = Object.keys(planStore.characters || {});
        } else if (opts.scope && Array.isArray(opts.scope.characterIds)) {
            idList = opts.scope.characterIds.map(charKey).filter(Boolean);
        } else {
            idList = listClaimedIds(planStore, claimStore);
        }

        const rows = [];
        idList.forEach(function (id) {
            const plan = planStore.characters[id];
            if (!plan || !plan.selectedSlots) return;
            const live = byId[id];
            const equipped = live ? equippedMapFromChar(live) : {};
            const name = (live && live.name) || plan.name || id;
            const cls = (live && live.class) || plan.class || '';
            Object.keys(plan.selectedSlots).forEach(function (slotKey) {
                const slotId = Number(slotKey);
                const interest = normalizeSlotInterest(plan.selectedSlots[slotKey]);
                const equippedId = equipped[slotId] != null ? Number(equipped[slotId]) : null;
                interest.candidates.forEach(function (cand) {
                    const targetId = cand.itemId;
                    const status = targetStatus(equippedId, targetId, itemStatsCache);
                    rows.push({
                        characterId: id,
                        characterName: name,
                        characterClass: cls,
                        slotId: slotId,
                        equippedItemId: equippedId,
                        equippedItemName: itemNameFromCache(equippedId, itemStatsCache),
                        targetItemId: targetId,
                        targetItemName: itemNameFromCache(targetId, itemStatsCache),
                        status: status,
                        isPreferred: sameItemId(interest.preferredItemId, targetId),
                        bid: cand.bid != null ? cand.bid : null
                    });
                });
            });
        });
        return rows;
    }

    /**
     * Index of seeking interests for fast raid-upgrade lookups.
     * Map key: characterId + ':' + wearableItemId (string)
     */
    function buildSeekingIndex(characters, plans, itemStatsCache, options) {
        const rows = deriveTargets(characters, plans, itemStatsCache, options || { scope: 'claimed' });
        const byCharItem = {};
        const byCharSlot = {};
        rows.forEach(function (row) {
            if (row.status === 'Acquired') return;
            const cid = String(row.characterId);
            const iid = row.targetItemId == null ? '__null__' : String(row.targetItemId);
            const key = cid + ':' + iid;
            byCharItem[key] = row;
            if (!byCharSlot[cid]) byCharSlot[cid] = {};
            if (!byCharSlot[cid][row.slotId]) byCharSlot[cid][row.slotId] = [];
            byCharSlot[cid][row.slotId].push(row);
        });
        return {
            rows: rows.filter(function (r) { return r.status !== 'Acquired'; }),
            byCharItem: byCharItem,
            byCharSlot: byCharSlot,
            lookup: function (charId, itemId) {
                return byCharItem[String(charId) + ':' + (itemId == null ? '__null__' : String(itemId))] || null;
            }
        };
    }

    function _mutateSlot(charId, slotId, mutator, meta) {
        const id = charKey(charId);
        if (!id) return null;
        const store = loadPlans();
        const plan = store.characters[id] || {
            name: (meta && meta.name) || '',
            class: (meta && meta.class) || '',
            selectedSlots: {}
        };
        if (!plan.selectedSlots) plan.selectedSlots = {};
        const key = String(slotId);
        const current = plan.selectedSlots[key]
            ? normalizeSlotInterest(plan.selectedSlots[key])
            : null;
        const next = mutator(current);
        const ts = nowIso();
        if (!next || !next.candidates || next.candidates.length === 0) {
            delete plan.selectedSlots[key];
        } else {
            plan.selectedSlots[key] = normalizeSlotInterest(next);
        }
        plan.updatedAt = ts;
        plan.editedAt = ts;
        if (meta) {
            if (meta.name != null) plan.name = meta.name;
            if (meta.class != null) plan.class = meta.class;
        }
        if (Object.keys(plan.selectedSlots).length === 0) {
            delete store.characters[id];
        } else {
            store.characters[id] = plan;
        }
        savePlans(store);
        ensureAutoClaimPreference(id);
        return getCharacterPlan(id);
    }

    /**
     * Set preferred item for a slot (adds to seeking candidates; last selected = preferred).
     * itemId null = explicit empty preferred.
     */
    function setPreferred(charId, slotId, itemId, meta) {
        const preferred = normalizeItemId(itemId);
        return _mutateSlot(charId, slotId, function (current) {
            let candidates = current ? current.candidates.slice() : [];
            const idx = candidates.findIndex(function (c) {
                return sameItemId(c.itemId, preferred);
            });
            if (idx >= 0) {
                const [moved] = candidates.splice(idx, 1);
                candidates.push(moved);
            } else {
                candidates.push({ itemId: preferred });
            }
            return { preferredItemId: preferred, candidates: candidates };
        }, meta);
    }

    /**
     * Add or remove a seeking candidate. When adding, does not change preferred
     * unless the slot had no interest yet (then preferred becomes the item).
     * When removing the preferred item, the last remaining candidate becomes preferred.
     */
    function toggleSeeking(charId, slotId, itemId, meta) {
        const target = normalizeItemId(itemId);
        return _mutateSlot(charId, slotId, function (current) {
            if (!current) {
                return {
                    preferredItemId: target,
                    candidates: [{ itemId: target }]
                };
            }
            const idx = current.candidates.findIndex(function (c) {
                return sameItemId(c.itemId, target);
            });
            let candidates = current.candidates.slice();
            let preferred = current.preferredItemId;
            if (idx >= 0) {
                candidates.splice(idx, 1);
                if (sameItemId(preferred, target)) {
                    preferred = candidates.length
                        ? candidates[candidates.length - 1].itemId
                        : null;
                }
                if (!candidates.length) return null;
                return { preferredItemId: preferred, candidates: candidates };
            }
            candidates.push({ itemId: target });
            return { preferredItemId: preferred, candidates: candidates };
        }, meta);
    }

    /**
     * Ensure item is seeking and set intended bid (0 = rot). Pass null to clear bid.
     */
    function setBid(charId, slotId, itemId, bid, meta) {
        const target = normalizeItemId(itemId);
        const bidVal = bid == null || bid === '' ? null : normalizeBid(bid);
        return _mutateSlot(charId, slotId, function (current) {
            let candidates = current ? current.candidates.slice() : [];
            let preferred = current ? current.preferredItemId : target;
            const idx = candidates.findIndex(function (c) {
                return sameItemId(c.itemId, target);
            });
            if (idx >= 0) {
                const nextCand = { itemId: candidates[idx].itemId };
                if (bidVal != null) nextCand.bid = bidVal;
                candidates[idx] = nextCand;
            } else {
                const nextCand = { itemId: target };
                if (bidVal != null) nextCand.bid = bidVal;
                candidates.push(nextCand);
                if (!current) preferred = target;
            }
            return { preferredItemId: preferred, candidates: candidates };
        }, meta);
    }

    /**
     * Mark seeking and optionally set preferred + bid in one shot (raid upgrade UX).
     * opts: { preferred?: boolean, bid?: number|null }
     */
    function markSeeking(charId, slotId, itemId, opts, meta) {
        const options = opts || {};
        const target = normalizeItemId(itemId);
        const makePreferred = options.preferred !== false;
        const hasBid = Object.prototype.hasOwnProperty.call(options, 'bid');
        const bidVal = hasBid
            ? (options.bid == null || options.bid === '' ? null : normalizeBid(options.bid))
            : undefined;
        return _mutateSlot(charId, slotId, function (current) {
            let candidates = current ? current.candidates.slice() : [];
            let preferred = current ? current.preferredItemId : target;
            const idx = candidates.findIndex(function (c) {
                return sameItemId(c.itemId, target);
            });
            let cand;
            if (idx >= 0) {
                cand = Object.assign({}, candidates[idx]);
                candidates.splice(idx, 1);
            } else {
                cand = { itemId: target };
            }
            if (hasBid) {
                if (bidVal != null) cand.bid = bidVal;
                else delete cand.bid;
            }
            if (makePreferred) {
                candidates.push(cand);
                preferred = target;
            } else {
                candidates.push(cand);
            }
            return { preferredItemId: preferred, candidates: candidates };
        }, meta);
    }

    function removeTarget(charId, slotId, itemId) {
        const id = charKey(charId);
        if (!id) return false;
        if (itemId !== undefined && itemId !== null && itemId !== '') {
            const before = getCharacterPlan(id);
            const interest = getSlotInterest(before, slotId);
            if (!interest) return false;
            toggleSeeking(id, slotId, itemId);
            return true;
        }
        const store = loadPlans();
        const plan = store.characters[id];
        if (!plan || !plan.selectedSlots) return false;
        const key = String(slotId);
        if (!Object.prototype.hasOwnProperty.call(plan.selectedSlots, key)) return false;
        delete plan.selectedSlots[key];
        plan.updatedAt = nowIso();
        if (Object.keys(plan.selectedSlots).length === 0) {
            delete store.characters[id];
        } else {
            store.characters[id] = plan;
        }
        return savePlans(store);
    }

    function clearAcquired(characters, itemStatsCache, options) {
        const opts = options || {};
        const planStore = loadPlans();
        const rows = deriveTargets(characters, planStore, itemStatsCache, {
            scope: opts.scope || 'all',
            claims: opts.claims
        });
        let changed = false;
        rows.forEach(function (row) {
            if (row.status !== 'Acquired') return;
            const plan = planStore.characters[row.characterId];
            if (!plan || !plan.selectedSlots) return;
            const key = String(row.slotId);
            const interest = plan.selectedSlots[key]
                ? normalizeSlotInterest(plan.selectedSlots[key])
                : null;
            if (!interest) return;
            const filtered = interest.candidates.filter(function (c) {
                return !sameItemId(c.itemId, row.targetItemId);
            });
            if (filtered.length === interest.candidates.length) return;
            changed = true;
            plan.updatedAt = nowIso();
            if (!filtered.length) {
                delete plan.selectedSlots[key];
            } else {
                let preferred = interest.preferredItemId;
                if (sameItemId(preferred, row.targetItemId)) {
                    preferred = filtered[filtered.length - 1].itemId;
                }
                plan.selectedSlots[key] = {
                    preferredItemId: preferred,
                    candidates: filtered
                };
            }
        });
        Object.keys(planStore.characters).forEach(function (id) {
            const plan = planStore.characters[id];
            if (!plan.selectedSlots || Object.keys(plan.selectedSlots).length === 0) {
                delete planStore.characters[id];
                changed = true;
            }
        });
        if (changed) savePlans(planStore);
        return changed;
    }

    function loadRecent() {
        const data = readJson(KEYS.recent, emptyRecent());
        if (!data.characters || typeof data.characters !== 'object') data.characters = {};
        data.version = 1;
        return data;
    }

    function saveRecent(recent) {
        const payload = recent && typeof recent === 'object' ? recent : emptyRecent();
        payload.version = 1;
        if (!payload.characters || typeof payload.characters !== 'object') payload.characters = {};
        return writeJson(KEYS.recent, payload);
    }

    function trimRecent(store) {
        const entries = Object.keys(store.characters).map(function (id) {
            return { id: id, lastViewedAt: store.characters[id].lastViewedAt || '' };
        });
        if (entries.length <= RECENT_CAP) return;
        entries.sort(function (a, b) {
            return (a.lastViewedAt < b.lastViewedAt) ? -1 : (a.lastViewedAt > b.lastViewedAt ? 1 : 0);
        });
        const drop = entries.length - RECENT_CAP;
        for (let i = 0; i < drop; i++) {
            delete store.characters[entries[i].id];
        }
    }

    function recordView(char) {
        const id = charKey(char && char.id);
        if (!id) {
            console.warn('ClassRankingsGearPlans: skip view — missing character id');
            return null;
        }
        const store = loadRecent();
        store.characters[id] = {
            name: (char && char.name) || (store.characters[id] && store.characters[id].name) || '',
            class: (char && char.class) || (store.characters[id] && store.characters[id].class) || '',
            lastViewedAt: nowIso()
        };
        trimRecent(store);
        saveRecent(store);
        return store.characters[id];
    }

    function listRecent() {
        const store = loadRecent();
        return Object.keys(store.characters).map(function (id) {
            const row = store.characters[id];
            return {
                id: id,
                name: row.name || '',
                class: row.class || '',
                lastViewedAt: row.lastViewedAt || ''
            };
        }).sort(function (a, b) {
            return (a.lastViewedAt < b.lastViewedAt) ? 1 : (a.lastViewedAt > b.lastViewedAt ? -1 : 0);
        });
    }

    function loadClaims() {
        const data = readJson(KEYS.claims, emptyClaims());
        if (!data.characters || typeof data.characters !== 'object') data.characters = {};
        data.version = 1;
        return data;
    }

    function saveClaims(claims) {
        const payload = claims && typeof claims === 'object' ? claims : emptyClaims();
        payload.version = 1;
        if (!payload.characters || typeof payload.characters !== 'object') payload.characters = {};
        return writeJson(KEYS.claims, payload);
    }

    function getClaimPreference(charId, claims) {
        const id = charKey(charId);
        if (!id) return null;
        const store = claims || loadClaims();
        const row = store.characters[id];
        if (!row || !row.preference) return null;
        return CLAIM_PREFS.indexOf(row.preference) >= 0 ? row.preference : null;
    }

    function setClaimPreference(charId, preference) {
        const id = charKey(charId);
        if (!id) {
            console.warn('ClassRankingsGearPlans: skip claim — missing character id');
            return null;
        }
        if (CLAIM_PREFS.indexOf(preference) < 0) {
            console.warn('ClassRankingsGearPlans: invalid claim preference', preference);
            return null;
        }
        const store = loadClaims();
        store.characters[id] = {
            preference: preference,
            updatedAt: nowIso()
        };
        saveClaims(store);
        return store.characters[id];
    }

    function ensureAutoClaimPreference(charId) {
        const pref = getClaimPreference(charId);
        if (pref == null) {
            return setClaimPreference(charId, 'auto');
        }
        return null;
    }

    function isEffectivelyClaimed(charId, plans, claims) {
        const id = charKey(charId);
        if (!id) return false;
        const pref = getClaimPreference(id, claims);
        if (pref === 'claimed') return true;
        if (pref === 'unclaimed') return false;
        const plan = getCharacterPlan(id, plans);
        if (!plan) return false;
        if (plan.editedAt) return true;
        return hasSavedPlan(id, plans);
    }

    function listClaimedIds(plans, claims) {
        const planStore = plans || loadPlans();
        const claimStore = claims || loadClaims();
        const ids = new Set();
        Object.keys(claimStore.characters || {}).forEach(function (id) {
            if (isEffectivelyClaimed(id, planStore, claimStore)) ids.add(id);
        });
        Object.keys(planStore.characters || {}).forEach(function (id) {
            if (isEffectivelyClaimed(id, planStore, claimStore)) ids.add(id);
        });
        return Array.from(ids);
    }

    function countOutstandingTargets(charId, characters, plans, itemStatsCache) {
        const rows = deriveTargets(characters, plans || loadPlans(), itemStatsCache, {
            scope: { characterIds: [charId] }
        });
        return rows.filter(function (r) { return r.status === 'Seeking' || r.status === 'Needs Review'; }).length;
    }

    function loadToonList() {
        const store = safeStorage();
        if (!store) return '';
        try {
            const raw = store.getItem(KEYS.toonList);
            return raw == null ? '' : String(raw);
        } catch (e) {
            return '';
        }
    }

    function saveToonList(value) {
        const store = safeStorage();
        if (!store) return false;
        try {
            store.setItem(KEYS.toonList, value == null ? '' : String(value));
            return true;
        } catch (e) {
            console.warn('ClassRankingsGearPlans: unable to write toon list', e);
            return false;
        }
    }

    /**
     * Persist preferred loadout changes while preserving multi-seeking candidates.
     */
    function persistUserGearEdit(char, equippedBySlot, virtualLoadout) {
        const id = charKey(char && char.id);
        if (!id) {
            console.warn('ClassRankingsGearPlans: skip gear edit — missing character id');
            return null;
        }
        const prev = getCharacterPlan(id);
        const existing = (prev && prev.selectedSlots) || {};
        const selectedSlots = diffSelectedSlots(equippedBySlot, virtualLoadout, existing);

        // Preserve seeking-only slots whose preferred was not in virtualLoadout changes
        // (virtualLoadout usually covers all slots via applyPlanToLoadout + edits)
        Object.keys(existing).forEach(function (key) {
            if (Object.prototype.hasOwnProperty.call(selectedSlots, key)) return;
            // Slot absent from diff means preferred matches equipped — keep other candidates
            const interest = normalizeSlotInterest(existing[key]);
            const eqRaw = equippedBySlot && (equippedBySlot[key] !== undefined
                ? equippedBySlot[key]
                : equippedBySlot[Number(key)]);
            const equippedId = normalizeItemId(eqRaw);
            const others = interest.candidates.filter(function (c) {
                return !sameItemId(c.itemId, equippedId)
                    && !sameItemId(c.itemId, interest.preferredItemId);
            });
            // If preferred was equipped-matching and we had only that candidate, drop.
            // If there are other candidates, keep them with last as preferred.
            if (sameItemId(interest.preferredItemId, equippedId) || interest.preferredItemId == null) {
                if (others.length) {
                    selectedSlots[key] = {
                        preferredItemId: others[others.length - 1].itemId,
                        candidates: others
                    };
                }
            } else if (!Object.prototype.hasOwnProperty.call(virtualLoadout, Number(key))
                && !Object.prototype.hasOwnProperty.call(virtualLoadout, key)) {
                selectedSlots[key] = interest;
            }
        });

        const ts = nowIso();
        if (Object.keys(selectedSlots).length === 0) {
            clearCharacterPlan(id);
        } else {
            setCharacterPlan(id, {
                name: char.name || '',
                class: char.class || '',
                selectedSlots: selectedSlots,
                updatedAt: ts,
                editedAt: ts
            });
        }
        ensureAutoClaimPreference(id);
        return getCharacterPlan(id);
    }

    return {
        KEYS: KEYS,
        RECENT_CAP: RECENT_CAP,
        PLAN_VERSION: PLAN_VERSION,
        CLAIM_PREFS: CLAIM_PREFS,
        charKey: charKey,
        normalizeSlotInterest: normalizeSlotInterest,
        normalizeSelectedSlots: normalizeSelectedSlots,
        preferredIdFromSlot: preferredIdFromSlot,
        sameItemId: sameItemId,
        loadPlans: loadPlans,
        savePlans: savePlans,
        getCharacterPlan: getCharacterPlan,
        setCharacterPlan: setCharacterPlan,
        clearCharacterPlan: clearCharacterPlan,
        hasSavedPlan: hasSavedPlan,
        getSlotInterest: getSlotInterest,
        listSlotCandidates: listSlotCandidates,
        isSeekingItem: isSeekingItem,
        getBid: getBid,
        setPreferred: setPreferred,
        toggleSeeking: toggleSeeking,
        setBid: setBid,
        markSeeking: markSeeking,
        diffSelectedSlots: diffSelectedSlots,
        applyPlanToLoadout: applyPlanToLoadout,
        buildSlotExtras: buildSlotExtras,
        equippedMapFromChar: equippedMapFromChar,
        deriveTargets: deriveTargets,
        buildSeekingIndex: buildSeekingIndex,
        removeTarget: removeTarget,
        clearAcquired: clearAcquired,
        recordView: recordView,
        listRecent: listRecent,
        loadRecent: loadRecent,
        loadClaims: loadClaims,
        getClaimPreference: getClaimPreference,
        setClaimPreference: setClaimPreference,
        ensureAutoClaimPreference: ensureAutoClaimPreference,
        isEffectivelyClaimed: isEffectivelyClaimed,
        listClaimedIds: listClaimedIds,
        countOutstandingTargets: countOutstandingTargets,
        loadToonList: loadToonList,
        saveToonList: saveToonList,
        persistUserGearEdit: persistUserGearEdit
    };
}));
