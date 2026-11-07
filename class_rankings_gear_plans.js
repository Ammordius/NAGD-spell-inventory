/**
 * Class Rankings — browser-local gear plans, recently viewed, and claim preferences.
 * No network I/O. Claims are local preferences only, not authenticated ownership.
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
        return { version: 1, characters: {} };
    }

    function emptyRecent() {
        return { version: 1, characters: {} };
    }

    function emptyClaims() {
        return { version: 1, characters: {} };
    }

    function loadPlans() {
        const data = readJson(KEYS.plans, emptyPlans());
        if (!data.characters || typeof data.characters !== 'object') data.characters = {};
        data.version = 1;
        return data;
    }

    function savePlans(plans) {
        const payload = plans && typeof plans === 'object' ? plans : emptyPlans();
        payload.version = 1;
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
                ? planPatch.selectedSlots
                : (prev.selectedSlots || {}),
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

    /**
     * Compare virtual loadout to Magelo equipped. Returns sparse selectedSlots.
     * null = explicit empty; omit = same as equipped / unspecified.
     */
    function diffSelectedSlots(equippedBySlot, virtualLoadout) {
        const out = {};
        const equipped = equippedBySlot || {};
        const virtual = virtualLoadout || {};
        for (let slotId = 1; slotId <= 22; slotId++) {
            const key = String(slotId);
            const hasVirtual = Object.prototype.hasOwnProperty.call(virtual, slotId)
                || Object.prototype.hasOwnProperty.call(virtual, key);
            if (!hasVirtual) continue;
            const raw = virtual[slotId] !== undefined ? virtual[slotId] : virtual[key];
            const picked = (raw != null && raw !== '') ? Number(raw) : null;
            const eqRaw = equipped[slotId] !== undefined ? equipped[slotId] : equipped[key];
            const equippedId = (eqRaw != null && eqRaw !== '') ? Number(eqRaw) : null;
            if (picked == null && equippedId == null) continue;
            if (picked != null && equippedId != null && picked === equippedId) continue;
            out[key] = picked;
        }
        return out;
    }

    /**
     * Apply sparse selectedSlots onto Magelo equipped baseline → full loadout map (numeric keys).
     */
    function applyPlanToLoadout(equippedBySlot, selectedSlots) {
        const loadout = {};
        const equipped = equippedBySlot || {};
        const selected = selectedSlots || {};
        for (let slotId = 1; slotId <= 22; slotId++) {
            const key = String(slotId);
            const eqRaw = equipped[slotId] !== undefined ? equipped[slotId] : equipped[key];
            const equippedId = (eqRaw != null && eqRaw !== '') ? Number(eqRaw) : null;
            if (Object.prototype.hasOwnProperty.call(selected, key)
                || Object.prototype.hasOwnProperty.call(selected, slotId)) {
                const raw = selected[key] !== undefined ? selected[key] : selected[slotId];
                loadout[slotId] = (raw != null && raw !== '') ? Number(raw) : null;
            } else {
                loadout[slotId] = equippedId;
            }
        }
        return loadout;
    }

    /**
     * For saved ids not already in option lists, build slotExtras entries from itemStatsCache.
     * optionIdsBySlot: { [slotId]: Set|Array of numeric ids }
     */
    function buildSlotExtras(selectedSlots, optionIdsBySlot, itemStatsCache) {
        const extras = {};
        const selected = selectedSlots || {};
        const options = optionIdsBySlot || {};
        const cache = itemStatsCache || {};
        Object.keys(selected).forEach(function (key) {
            const slotId = Number(key);
            if (isNaN(slotId)) return;
            const raw = selected[key];
            if (raw == null || raw === '') return;
            const itemId = Number(raw);
            if (isNaN(itemId)) return;
            const existing = options[slotId] || options[key] || [];
            const idSet = existing instanceof Set
                ? existing
                : new Set([].concat(existing).map(Number));
            if (idSet.has(itemId)) return;
            const stats = cache[itemId] || cache[String(itemId)];
            if (!extras[slotId]) extras[slotId] = [];
            extras[slotId].push({
                id: itemId,
                name: (stats && stats.name) ? stats.name : ('Item ' + itemId)
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
            // Explicit empty while Magelo still has something (or vice versa handled by Seeking)
            if (equippedId != null) return 'Seeking';
            return 'Acquired';
        }
        const cache = itemStatsCache || {};
        const stats = cache[targetId] || cache[String(targetId)];
        if (!stats) return 'Needs Review';
        return 'Seeking';
    }

    /**
     * Derive gear-target rows.
     * options.scope: 'claimed' (default) | 'all' | { characterIds: [] }
     * options.claims / options.plans optional (loaded if omitted)
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
                const targetRaw = plan.selectedSlots[slotKey];
                const targetId = (targetRaw != null && targetRaw !== '') ? Number(targetRaw) : null;
                const equippedId = equipped[slotId] != null ? Number(equipped[slotId]) : null;
                const status = targetStatus(equippedId, targetId, itemStatsCache);
                const cache = itemStatsCache || {};
                const targetStats = targetId != null ? (cache[targetId] || cache[String(targetId)]) : null;
                const equippedStats = equippedId != null ? (cache[equippedId] || cache[String(equippedId)]) : null;
                rows.push({
                    characterId: id,
                    characterName: name,
                    characterClass: cls,
                    slotId: slotId,
                    equippedItemId: equippedId,
                    equippedItemName: equippedStats && equippedStats.name
                        ? equippedStats.name
                        : (equippedId != null ? ('Item ' + equippedId) : '— None —'),
                    targetItemId: targetId,
                    targetItemName: targetStats && targetStats.name
                        ? targetStats.name
                        : (targetId != null ? ('Item ' + targetId) : '— None —'),
                    status: status
                });
            });
        });
        return rows;
    }

    function removeTarget(charId, slotId) {
        const id = charKey(charId);
        if (!id) return false;
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
            if (Object.prototype.hasOwnProperty.call(plan.selectedSlots, key)) {
                delete plan.selectedSlots[key];
                plan.updatedAt = nowIso();
                changed = true;
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
        // auto or missing
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
     * Persist a meaningful user gear edit: sparse slots + editedAt; ensure auto claim if unset.
     * Does not override explicit claimed/unclaimed.
     */
    function persistUserGearEdit(char, equippedBySlot, virtualLoadout) {
        const id = charKey(char && char.id);
        if (!id) {
            console.warn('ClassRankingsGearPlans: skip gear edit — missing character id');
            return null;
        }
        const selectedSlots = diffSelectedSlots(equippedBySlot, virtualLoadout);
        const ts = nowIso();
        if (Object.keys(selectedSlots).length === 0) {
            // User reverted all slots to Magelo baseline — clear plan but keep editedAt? Keep a tombstone
            // with empty slots removed entirely; effective claim under auto then false unless explicit claimed.
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
        CLAIM_PREFS: CLAIM_PREFS,
        charKey: charKey,
        loadPlans: loadPlans,
        savePlans: savePlans,
        getCharacterPlan: getCharacterPlan,
        setCharacterPlan: setCharacterPlan,
        clearCharacterPlan: clearCharacterPlan,
        hasSavedPlan: hasSavedPlan,
        diffSelectedSlots: diffSelectedSlots,
        applyPlanToLoadout: applyPlanToLoadout,
        buildSlotExtras: buildSlotExtras,
        equippedMapFromChar: equippedMapFromChar,
        deriveTargets: deriveTargets,
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
