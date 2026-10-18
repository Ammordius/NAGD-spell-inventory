#!/usr/bin/env python3
"""Write docs/MOD2_CALIBRATION_REPORT.md from the frozen config and current rankings."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mod2_scoring as m  # noqa: E402

OUT = ROOT / "docs" / "MOD2_CALIBRATION_REPORT.md"
RANKINGS = ROOT / "class_rankings.json"
STATS_PATH = ROOT / "data" / "item_stats.json"
FOCUS_CLASSES = ("Warrior", "Shadow Knight", "Monk", "Rogue", "Wizard", "Cleric")


def core_percent(score: float, class_max: float) -> float:
    if class_max <= 0:
        return 0.0
    return 100.0 * score / class_max


def full_cap_points(weights: dict) -> dict:
    return {
        stat: round(100.0 * (float(parts["other"]) + float(parts["threat"])), 2)
        for stat, parts in weights.items()
    }


def slot_hp(stats: dict, slot_token: str, class_token: str) -> list:
    rows = []
    for item_id, entry in stats.items():
        slot = str(entry.get("slot") or "")
        classes = str(entry.get("classes") or "")
        if slot_token not in slot.split() or class_token not in classes.split():
            continue
        hp = 0
        ac = int(entry.get("ac") or 0)
        for mod in entry.get("mods") or []:
            if str(mod.get("label") or "").upper() == "HP":
                hp += int(mod.get("value") or 0)
        if hp or ac:
            rows.append((hp, ac, entry.get("name"), item_id))
    rows.sort(reverse=True)
    return rows[:5]


def main() -> None:
    config = m.load_config()
    table = m.load_item_table()
    cal = config["calibration"]
    db, di = cal["quarm_db_di"]
    rankings = json.loads(RANKINGS.read_text(encoding="utf-8"))
    by_class = defaultdict(list)
    for char in rankings["characters"]:
        by_class[char["class"]].append(char)
    class_max = {cls: max(c["overall_score"] for c in rows) for cls, rows in by_class.items()}

    lines = []
    w = lines.append
    w("# Mod2 calibration report")
    w("")
    w("## Architecture")
    w("")
    w("- `data/item_mod2.json` is the only Mod2 dataset: the launch Plane of Time list, keyed by item id. 63 items resolved. Galladan's Stormwrath Tunic has no `items.name` match and is not scored.")
    w("- `scripts/mod2_scoring.py` calibrates full-cap weights and scores equipped totals. `data/mod2_config.json` is the frozen result.")
    w("- `mod2_rankings.js` applies that config in `class_rankings.html` only when `mod2=true`.")
    w("- `generate_class_rankings.py` attaches a `mod2` object and does not change `overall_score`.")
    w("- `dkp/web/src/lib/mageloUpgradeEngine.js` adds a Mod2 upgrade delta only when `ctx.mod2 === true`. DKP price math is untouched. `dkp_val` and `mod2` are independent.")
    w("- With the flag off, displayed score stays the core percentage. With the flag on, `displayed = 100 * (core + mod2) / (100 + reference_mod2_points)`.")
    w("")
    w("## What 100% means")
    w("")
    w("The ranking sheet is unbuffed. The server snapshot sets `hp_max_total` with `CalcMaxHP(true)` (no spell HP or STA buffs) and displayed AC from avoidance plus mitigation without combat agility. The page then shows each character as a percentage of the best core total in that class, so the leader is 100%.")
    w("")
    w("The current rank-1 warrior, Voracious, is 8992 HP and 2206 displayed AC. That is the calibration anchor. It is not a buffed raid total, and it is not an internal mitigation cap. Warrior combat mitigation for that displayed AC, with defense 252 and agility 200, is %s before shield AC and Combat Stability. The softcap before those additions is 430, and level-65 warrior overcap returns are 3." % cal["warrior_combat_mitigation"])
    w("")
    w("## Quarm")
    w("")
    w("npc_types id 223008 is min 1140, max 3800, ATK 500, Accuracy 750. DB = 1000, DI = 140. One percent shielding prevents 10 damage per landed hit. Four percent prevents 40, and 100 such hits prevent 4000. Points above 35% do not add benefit.")
    w("")
    w("This server's melee path does not multiply worn shielding into the damage bonus. Spell shield and DoT shield are applied in `AffectMagicalDamage`. Strikethrough on a riposte in `attack.cpp` is AA-only. Combat Effects are not the weapon `ProcRate` field. The weights below are a scoring model on top of those verified formulas, not a claim that every Mod2 is implemented on the item struct.")
    w("")
    w("Shielding's full-cap share of a landed hit, blended 50%% Quarm / 30%% illustrative PoP boss / 20%% illustrative PoTime trash, is %.1f%%. Full avoidance (100) removes %.1f%% of hits against the unbuffed warrior avoidance rating of %s. Full accuracy (150) raises a 252/252 melee hit rate by %.1f%% relative to an NPC avoidance cap of 460." % (
        100 * cal["shielding_fraction_of_hit"],
        100 * cal["avoidance_fraction_of_hits"],
        cal["warrior_avoidance"],
        100 * cal["accuracy_relative_gain"],
    ))
    w("")
    w("Avoidance is added to the avoidance rating and run through `AvoidanceCheck`. It is not treated as 10 hit points per 100 avoidance. Quarm's accuracy of 750 flattens avoidance; the blend keeps some value from the lower-accuracy profiles. Those two profiles are illustrative, not parsed boss rows.")
    w("")
    w("## Weight matrix")
    w("")
    w("A full cap is worth the points below on the 100-point core scale. U is linear in the stat up to the cap. Stun Resist and Combat Effects split a threat portion from a non-threat portion. The default scenario uses each class's threat factor (0.35 for warriors) and a 0.20 stun exposure. Threat value is zero when threat is not limiting, and stun threat is zero when stun exposure is zero. Reaching 35% is not an extra bonus.")
    w("")
    w("| Class | Reference | Core JSON | Ref Mod2 pts | Shield | Avoid | SpellSh | DoTSh | Acc | Strike | CE | Stun | DS |")
    w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for class_name, row in config["classes"].items():
        ref = row["reference"]
        pts = full_cap_points(row["weights"])
        w("| %s | %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f |" % (
            class_name, ref["name"], ref["core_json"], row["reference_mod2_points"],
            pts["shielding"], pts["avoidance"], pts["spell_shielding"], pts["dot_shielding"],
            pts["accuracy"], pts["strikethrough"], pts["combat_effects"], pts["stun_resist"], pts["damage_shield"],
        ))
    w("")
    w("Warrior shielding is the largest tank Mod2. Avoidance is next. Neither is close to the whole HP category (about 28 points). Monk and front-line accuracy is the large offensive Mod2. Rogue strikethrough is much smaller because the model assumes attacks from behind. Caster spell shielding is meaningful and still smaller than the focus block, which is 35 points of the core.")
    w("")
    war = config["classes"]["Warrior"]
    hp_display = m.json_points_per_hp("Warrior", war["reference"], {"hp_pct": war["core_weights"]["hp_pct"]}) / (war["reference"]["core_json"] / 100.0)
    norm_ac = war["core_weights"]["ac_pct"]
    max_combined = max(war["reference"]["ac"], war["reference"]["hp"] / 5.0)
    ac_display = ((1.0 / max_combined) * 100.0 * norm_ac) / (war["reference"]["core_json"] / 100.0)
    w("## Warrior comparisons")
    w("")
    w("On Voracious, +100 HP is %.3f display points. +10 displayed AC is %.3f and +30 displayed AC is %.3f. The AC slope is the existing ranking's linear displayed-AC term, not extra mitigation past the softcap." % (100 * hp_display, 10 * ac_display, 30 * ac_display))
    shield_w = war["weights"]["shielding"]["other"]
    avoid_w = war["weights"]["avoidance"]["other"]
    w("4%% shielding is %.2f points (4/35 of %.2f). 2%% shielding is %.2f. 10 avoidance is %.2f. 25 avoidance is %.2f." % (
        shield_w * 100 * 4 / 35, shield_w * 100, shield_w * 100 * 2 / 35, avoid_w * 100 * 10 / 100, avoid_w * 100 * 25 / 100,
    ))
    w("So 2% shielding is in the same range as +100 HP, and 4% shielding is ahead of +100 HP and ahead of +30 displayed AC. That is the intended tank result on this blend, not a forced ranking.")
    w("")
    w("Default warrior stun threat at 35%% is %.2f points. With threat limitation 0 it is 0. With threat limitation 1 and stun exposure 0.8 it is %.2f." % (
        m.threat_component("Warrior", {"stun_resist": 35}, config, {}),
        m.threat_component("Warrior", {"stun_resist": 35}, config, {"threat_limitation": 1, "stun_exposure": 0.8}),
    ))
    w("")
    w("## Reference loadouts")
    w("")
    for class_name in FOCUS_CLASSES:
        loadout = config["classes"][class_name]["reference_loadout"]
        names = ", ".join(item["name"] for item in loadout["items"]) or "(none this class can wear)"
        w("- **%s** (%.2f Mod2 points): %s" % (class_name, loadout["points"], names))
    w("")
    w("Ultor's Chestguard of Faith is class bit CLR in this database, and Trydan's Chestplate of Nobility is PAL. Mods stay on the named items. The loadout follows the class bitmask.")
    w("")
    w("## Ranking movement")
    w("")
    w("Before is the stored `overall_score` divided by the class maximum, which is 100 for the current leader. After adds equipped launch Mod2s and renormalizes with that class's reference loadout. Characters with no launch Mod2s keep their order and sit slightly below their old percentage.")
    w("")

    movements = []
    for class_name in FOCUS_CLASSES:
        rows = []
        for char in by_class[class_name]:
            core = core_percent(char["overall_score"], class_max[class_name])
            scored = m.score_ids(class_name, m.worn_ids(char.get("inventory")), config, table)
            ref_pts = config["classes"][class_name]["reference_mod2_points"]
            after = m.combined_display(core, scored["points"], ref_pts)
            rows.append((char["name"], core, after, scored["points"], char.get("class_rank")))
        before_order = [name for name, *_rest in sorted(rows, key=lambda r: -r[1])]
        after_order = [name for name, *_rest in sorted(rows, key=lambda r: -r[2])]
        w("### %s" % class_name)
        w("")
        w("| Name | Before % | Mod2 pts | After % |")
        w("|---|---:|---:|---:|")
        for name, core, after, pts, _rank in sorted(rows, key=lambda r: -r[2])[:8]:
            w("| %s | %.2f | %.2f | %.2f |" % (name, core, pts, after))
            if name in before_order[:15]:
                movements.append((class_name, name, before_order.index(name), after_order.index(name), after - core))
        w("")

    w("## Largest moves inside the tracked classes")
    w("")
    movements.sort(key=lambda row: abs(row[3] - row[2]), reverse=True)
    w("| Class | Name | Before rank | After rank | Score change |")
    w("|---|---|---:|---:|---:|")
    for class_name, name, before_i, after_i, delta in movements[:12]:
        w("| %s | %s | %d | %d | %+.2f |" % (class_name, name, before_i + 1, after_i + 1, delta))
    w("")

    w("## Item examples")
    w("")
    by_name = {row["name"]: item_id for item_id, row in table["items"].items()}
    examples = [
        "Greaves of Furious Might",
        "Pants of Furious Might",
        "Leggings of Furious Might",
        "Shield of Strife",
        "Shroud of Eternity",
        "Padded Tigerskin Gloves",
        "Wristband of Icy Vengeance",
        "Prismatic Ring of Resistance",
        "Raex's Chestplate of Destruction",
        "Ultor's Chestguard of Faith",
        "Trydan's Chestplate of Nobility",
    ]
    w("| Item | Id | Warrior pts | Monk pts | Wizard pts |")
    w("|---|---:|---:|---:|---:|")
    for name in examples:
        item_id = by_name[name]
        def pts(cls, iid=item_id):
            return m.score_ids(cls, [iid], config, table)["points"]
        w("| %s | %s | %.2f | %.2f | %.2f |" % (name, item_id, pts("Warrior"), pts("Monk"), pts("Wizard")))
    w("")
    if STATS_PATH.exists():
        stats = json.loads(STATS_PATH.read_text(encoding="utf-8"))
        w("Highest-HP warrior legs currently in `item_stats.json`, for scale against Greaves of Furious Might (4%% shielding, %.2f warrior points):" % m.score_ids("Warrior", [by_name["Greaves of Furious Might"]], config, table)["points"])
        w("")
        for hp, ac, name, item_id in slot_hp(stats, "LEGS", "WAR")[:5]:
            w("- %s (%s): %s HP, %s AC, about %.2f HP display points and %.2f AC display points" % (
                name, item_id, hp, ac, hp * hp_display, ac * ac_display,
            ))
        w("")
    w("## Weight sensitivity")
    w("")
    w("Warrior top 10 were re-ranked with every Mod2 weight at 75% and 125% of the frozen values.")
    w("")
    base_weights = config["classes"]["Warrior"]["weights"]
    war_rows = []
    for char in by_class["Warrior"]:
        core = core_percent(char["overall_score"], class_max["Warrior"])
        scored = m.score_ids("Warrior", m.worn_ids(char.get("inventory")), config, table)
        war_rows.append((char["name"], core, scored["capped"]))
    def order_for(scale: float):
        scaled = {stat: {"other": parts["other"] * scale, "threat": parts["threat"] * scale} for stat, parts in base_weights.items()}
        ref = config["classes"]["Warrior"]["reference_mod2_points"] * scale
        ranked = []
        for name, core, capped in war_rows:
            pts = m.mod2_points("Warrior", capped, {"Warrior": scaled})
            ranked.append((m.combined_display(core, pts, ref), name))
        ranked.sort(reverse=True)
        return [name for _score, name in ranked[:10]]
    base_top = order_for(1.0)
    for label, scale in (("75%", 0.75), ("125%", 1.25)):
        top = order_for(scale)
        changed = [name for name in base_top if name not in top or top.index(name) != base_top.index(name)]
        w("- %s: %d of the top 10 change position. Order: %s" % (label, len(changed), ", ".join(top)))
    w("")
    w("## Unresolved")
    w("")
    w("- Galladan's Stormwrath Tunic is not in `peq.items`. It is listed under `unresolved` and contributes nothing.")
    w("- Later expansions have no Mod2s in this dataset. They score zero until an item is added to `item_mod2.json`.")
    w("- Displayed AC is still linear in the core score. The Mod2 model does not revalue the existing AC category.")
    w("- Combat Stability and shield AC were left at zero in the mitigation example, so the 742 mitigation figure is a lower-gear overcap case for the displayed total, not a logged parse.")
    w("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
