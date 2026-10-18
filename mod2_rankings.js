/**
 * Browser runtime for Mod2 class rankings.
 * Weights and items come from data/mod2_config.json and data/item_mod2.json.
 * Scoring matches scripts/mod2_scoring.py. Legacy rankings do not call this.
 */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.Mod2Scoring = factory();
    }
}(typeof self !== 'undefined' ? self : this, function () {
    const STATS = ['accuracy', 'avoidance', 'combat_effects', 'damage_shield', 'dot_shielding', 'shielding', 'spell_shielding', 'strikethrough', 'stun_resist'];
    const LABELS = {
        accuracy: 'Accuracy',
        avoidance: 'Avoidance',
        combat_effects: 'Combat Effects',
        damage_shield: 'Damage Shield',
        dot_shielding: 'DoT Shielding',
        shielding: 'Shielding',
        spell_shielding: 'Spell Shielding',
        strikethrough: 'Strikethrough',
        stun_resist: 'Stun Resist'
    };
    const PERCENT = {
        dot_shielding: true,
        shielding: true,
        spell_shielding: true,
        strikethrough: true,
        stun_resist: true
    };

    let config = null;
    let table = null;

    function isReady() {
        return !!(config && table);
    }

    function load(configUrl, itemUrl) {
        const configPaths = configUrl ? [configUrl] : ['data/mod2_config.json', './data/mod2_config.json'];
        const itemPaths = itemUrl ? [itemUrl] : ['data/item_mod2.json', './data/item_mod2.json'];
        return Promise.all([fetchFirst(configPaths), fetchFirst(itemPaths)]).then(function (pair) {
            config = pair[0];
            table = pair[1];
            return true;
        });
    }

    function fetchFirst(paths) {
        let chain = Promise.reject(new Error('no path'));
        paths.forEach(function (path) {
            chain = chain.catch(function () {
                return fetch(path).then(function (res) {
                    if (!res.ok) throw new Error(path);
                    return res.json();
                });
            });
        });
        return chain;
    }

    function emptyMods() {
        const out = {};
        STATS.forEach(function (stat) { out[stat] = 0; });
        return out;
    }

    function itemMods(itemId) {
        const items = (table && table.items) || {};
        const entry = items[String(itemId)];
        const mods = emptyMods();
        if (!entry || !entry.mods) return mods;
        STATS.forEach(function (stat) {
            mods[stat] = Number(entry.mods[stat]) || 0;
        });
        return mods;
    }

    function sumIds(itemIds) {
        const total = emptyMods();
        (itemIds || []).forEach(function (itemId) {
            if (itemId == null || itemId === '') return;
            const mods = itemMods(itemId);
            STATS.forEach(function (stat) { total[stat] += mods[stat]; });
        });
        return total;
    }

    function capMods(raw) {
        const caps = config.caps;
        const capped = emptyMods();
        STATS.forEach(function (stat) {
            let value = Number(raw[stat]) || 0;
            if (value < 0) value = 0;
            capped[stat] = Math.min(caps[stat], value);
        });
        return capped;
    }

    function utility(stat, value) {
        const cap = config.caps[stat];
        if (!cap || value <= 0) return 0;
        return Math.min(value, cap) / cap;
    }

    function activeWeights(className, scenario) {
        const row = config.classes[className];
        if (!row) return null;
        const roleThreat = Number(row.role && row.role.threat) || 0;
        const threatFactor = scenario && Object.prototype.hasOwnProperty.call(scenario, 'threat_limitation')
            ? Number(scenario.threat_limitation)
            : roleThreat;
        const defaultStun = Number(config.default_scenario.stun_exposure) || 0.2;
        const stunExposure = scenario && Object.prototype.hasOwnProperty.call(scenario, 'stun_exposure')
            ? Number(scenario.stun_exposure)
            : defaultStun;
        const out = {};
        STATS.forEach(function (stat) {
            const parts = row.weights[stat] || { other: 0, threat: 0 };
            let threat = Number(parts.threat) || 0;
            if (roleThreat <= 0 || threatFactor <= 0) threat = 0;
            else threat = threat * (threatFactor / roleThreat);
            if (stat === 'stun_resist') {
                if (stunExposure <= 0) threat = 0;
                else threat *= stunExposure / defaultStun;
            }
            out[stat] = (Number(parts.other) || 0) + threat;
        });
        return out;
    }

    function scoreIds(className, itemIds, scenario) {
        const raw = sumIds(itemIds);
        const capped = capMods(raw);
        const weights = activeWeights(className, scenario);
        const byStat = {};
        let points = 0;
        if (weights) {
            STATS.forEach(function (stat) {
                const u = utility(stat, capped[stat]);
                const pts = 100 * weights[stat] * u;
                points += pts;
                if (raw[stat] || capped[stat]) {
                    byStat[stat] = { raw: raw[stat], capped: capped[stat], utility: u, weight: weights[stat], points: pts };
                }
            });
        }
        return { raw: raw, capped: capped, points: points, by_stat: byStat };
    }

    function wornIds(inventory) {
        const ids = [];
        (inventory || []).forEach(function (row) {
            const slot = Number(row.slot_id);
            if (slot >= 1 && slot <= 22) ids.push(row.item_id);
        });
        return ids;
    }

    function combined(corePct, mod2Pts, referencePts) {
        return 100 * ((Number(corePct) || 0) + (Number(mod2Pts) || 0)) / (100 + Math.max(0, Number(referencePts) || 0));
    }

    function applyToCharacters(characters) {
        if (!isReady()) return;
        const scoreTo2 = function (s) { return Math.round((s || 0) * 100) / 100; };
        characters.forEach(function (char) {
            const row = config.classes[char.class];
            if (!row) return;
            const scored = scoreIds(char.class, wornIds(char.inventory));
            char.core_score = char.overall_score;
            char.mod2_points = scored.points;
            char.mod2 = {
                points: scored.points,
                reference_points: row.reference_mod2_points,
                by_stat: scored.by_stat,
                raw: scored.raw,
                capped: scored.capped
            };
            char.overall_score = combined(char.core_score, scored.points, row.reference_mod2_points);
            char.normalized_score = char.overall_score;
        });
        characters.sort(function (a, b) {
            const d = (b.overall_score || 0) - (a.overall_score || 0);
            if (Math.abs(d) < 0.001) return (a.name || '').localeCompare(b.name || '');
            return d;
        });
        let rank = 1;
        for (let i = 0; i < characters.length; i++) {
            if (i > 0 && scoreTo2(characters[i].overall_score) < scoreTo2(characters[i - 1].overall_score)) rank = i + 1;
            characters[i].overall_rank = rank;
        }
        const byClass = {};
        characters.forEach(function (char) {
            if (!char.class) return;
            if (!byClass[char.class]) byClass[char.class] = [];
            byClass[char.class].push(char);
        });
        Object.keys(byClass).forEach(function (className) {
            const group = byClass[className];
            group.sort(function (a, b) {
                const d = (b.overall_score || 0) - (a.overall_score || 0);
                if (Math.abs(d) < 0.001) return (a.name || '').localeCompare(b.name || '');
                return d;
            });
            let classRank = 1;
            for (let i = 0; i < group.length; i++) {
                if (i > 0 && scoreTo2(group[i].overall_score) < scoreTo2(group[i - 1].overall_score)) classRank = i + 1;
                group[i].class_rank = classRank;
            }
        });
    }

    function upgradeDetail(className, equipped, slotId, currentItemId, candidateId, is2h) {
        if (!isReady() || !config.classes[className]) return { item: 0, display: 0 };
        const before = wornIds(equipped);
        const afterRows = (equipped || []).filter(function (row) {
            if (Number(row.slot_id) === Number(slotId)) return false;
            if (is2h && Number(row.slot_id) === 14) return false;
            return Number(row.slot_id) >= 1 && Number(row.slot_id) <= 22;
        });
        const after = afterRows.map(function (row) { return row.item_id; });
        after.push(candidateId);
        const display = scoreIds(className, after).points - scoreIds(className, before).points;
        return { item: display * (Number(config.classes[className].upgrade_scale) || 0), display: display };
    }

    function upgradeAdjustment(className, equipped, slotId, currentItemId, candidateId, is2h) {
        return upgradeDetail(className, equipped, slotId, currentItemId, candidateId, is2h).item;
    }

    function formatMod(stat, value) {
        const n = Number(value) || 0;
        const shown = Number.isInteger(n) ? String(n) : String(Math.round(n * 10) / 10);
        return PERCENT[stat] ? shown + '%' : shown;
    }

    function itemLine(itemId) {
        if (!isReady()) return '';
        const mods = itemMods(itemId);
        const parts = [];
        STATS.forEach(function (stat) {
            if (mods[stat]) parts.push(LABELS[stat] + ' ' + formatMod(stat, mods[stat]));
        });
        return parts.length ? 'Mod2: ' + parts.join(', ') : '';
    }

    function breakdownText(char) {
        if (!char || !char.mod2) return '';
        const statPts = Number(char.stat_points) || 0;
        const focusPts = Number(char.focus_points) || 0;
        const modPts = Number(char.mod2_points) || 0;
        const lines = ['Core ' + statPts.toFixed(2) + ' | Focus ' + focusPts.toFixed(2) + ' | Mod2 ' + modPts.toFixed(2) + ' | Total ' + (Number(char.overall_score) || 0).toFixed(2) + '%'];
        const bits = [];
        Object.keys(char.mod2.by_stat || {}).forEach(function (stat) {
            const row = char.mod2.by_stat[stat];
            bits.push(LABELS[stat] + ' raw ' + formatMod(stat, row.raw) + ', capped ' + formatMod(stat, row.capped) + ', +' + row.points.toFixed(2));
        });
        if (bits.length) lines.push(bits.join('; '));
        else lines.push('No launch Mod2s equipped.');
        return lines.join(' ');
    }

    return {
        load: load,
        isReady: isReady,
        scoreIds: scoreIds,
        applyToCharacters: applyToCharacters,
        upgradeAdjustment: upgradeAdjustment,
        upgradeDetail: upgradeDetail,
        itemLine: itemLine,
        breakdownText: breakdownText,
        combined: combined,
        utility: utility,
        LABELS: LABELS
    };
}));
