"""
Emit data/weapon_threat_server.json — server-model melee + proc hate/sec per weapon_procs key.

Assumptions match DPS_CALCULATOR_THREAT.md and dps_calculator baseline (Warrior 65, haste 70, DW from dps_config).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Run as script from magelo/scripts
_MAG = Path(__file__).resolve().parents[1]


def normalize_name(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    return " ".join(s.strip().lower().split())


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def pick_weapon_item(cands: list[dict]) -> dict | None:
    if not cands:
        return None
    for it in cands:
        if (it.get("slot") or "").upper() == "PRIMARY":
            return it
    return cands[0]


def items_matching_name(item_stats: dict, key: str) -> list[dict]:
    out = []
    for _iid, it in item_stats.items():
        if normalize_name(it.get("name") or "") == key:
            out.append(it)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weapon-procs", type=Path, default=_MAG / "data" / "weapon_procs.json")
    ap.add_argument("--item-stats", type=Path, default=_MAG / "data" / "item_stats.json")
    ap.add_argument("--spells-threat", type=Path, default=_MAG / "data" / "spells_threat.json")
    ap.add_argument("--item-proc-meta", type=Path, default=_MAG / "data" / "item_proc_meta.json")
    ap.add_argument("--dps-config", type=Path, default=_MAG / "data" / "dps_config.json")
    ap.add_argument("--out", type=Path, default=_MAG / "data" / "weapon_threat_server.json")
    ap.add_argument(
        "--patch-weapon-procs",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rewrite weapon_procs.json procDps/procDpsOH from server proc rate × spell DD when spell data exists.",
    )
    args = ap.parse_args()

    sys.path.insert(0, str(_MAG / "scripts"))
    from threat.check_aggro_amount import check_aggro_amount, spell_direct_damage_total
    from threat.melee_proc import (
        double_attack_chance_pct,
        dual_wield_chance_pct,
        get_proc_chance_fraction,
        is_two_hander_skill,
        mainhand_proc_rolls_per_second,
        melee_hate_per_swing_offhand,
        melee_hate_per_swing_primary,
        offhand_proc_rolls_per_second,
        swings_per_second_mh,
        swings_per_second_oh,
        warrior_aa_map,
        wpc_from_proc_rate,
    )

    weapon_procs = load_json(args.weapon_procs)
    item_stats = load_json(args.item_stats)
    st_wrap = load_json(args.spells_threat)
    spells = st_wrap.get("spells", st_wrap)
    proc_meta = load_json(args.item_proc_meta) if args.item_proc_meta.is_file() else {}
    aas = warrior_aa_map(args.dps_config)
    cfg_w = load_json(args.dps_config).get("classes", {}).get("Warrior", {})
    skills = cfg_w.get("skills", {})
    dw_skill = int(skills.get("dualWield", 245))
    da_skill = int(skills.get("doubleAttack", 252))
    level = int(load_json(args.dps_config).get("levelCap", 65))
    haste_pct = 70
    overhaste_pct = 0
    dex = 255

    dw_pct = dual_wield_chance_pct(dw_skill, level, int(aas.get("Ambidexterity", 0)))
    da_pct = double_attack_chance_pct(da_skill, level, aas)
    flurry = float(aas.get("FlurryChance", 0) or 0)

    out: dict[str, object] = {}
    meta = {
        "class": "Warrior",
        "level": level,
        "hastePct": haste_pct,
        "overhastePct": overhaste_pct,
        "dex": dex,
        "targetMaxHp": 1_000_000,
        "dualWieldChancePct": round(dw_pct, 3),
        "doubleAttackChancePct": round(da_pct, 3),
        "note": "Proc hate/DPS: one TryProcs per attack timer tick (not per DA/triple/flurry swing). GetProcChance uses attack_timer duration_ms/100 (Client::SetAttackTimer), not item_delay/100 as seconds. hatePerSec*ServerBard: CheckAggroAmount with is_bard=True. Melee rows are still Warrior primary DB; dps_calculator scales Bard MH melee hate in JS.",
    }
    out["_meta"] = meta

    for wkey, wp in weapon_procs.items():
        if wkey.startswith("_"):
            continue
        cands = items_matching_name(item_stats, wkey)
        it = pick_weapon_item(cands)
        delay = int(it.get("atkDelay") or 40) if it else 40
        dmg = int(it.get("dmg") or 0) if it else 0
        skill = (it.get("skill") or "") if it else ""
        use_2h = is_two_hander_skill(skill)
        item_id = None
        for nid, ob in item_stats.items():
            if ob is it:
                item_id = nid
                break

        spell_id = it.get("effectSpellId") if it else None
        proc_rate = 0
        if item_id is not None and str(item_id) in proc_meta:
            proc_rate = int(proc_meta[str(item_id)].get("procrate", 0) or 0)
        elif item_id is not None and item_id in proc_meta:
            proc_rate = int(proc_meta[item_id].get("procrate", 0) or 0)
        if proc_rate == 0 and it is not None and it.get("procrate") is not None:
            proc_rate = int(it.get("procrate") or 0)

        swings_mh = swings_per_second_mh(
            delay, haste_pct, overhaste_pct, da_chance_pct=da_pct, level=level, flurry_chance=flurry
        )
        hate_mh_sw = melee_hate_per_swing_primary(dmg, level, delay, skill, is_warrior_class_for_bonus=True)
        melee_hps_mh = swings_mh * hate_mh_sw

        swings_oh = 0.0
        hate_oh_sw = 0
        melee_hps_oh = 0.0
        if not use_2h and dmg > 0:
            swings_oh = swings_per_second_oh(
                delay,
                haste_pct,
                overhaste_pct,
                dw_chance_pct=dw_pct,
                da_skill=da_skill,
                aas=aas,
                level=level,
            )
            hate_oh_sw = melee_hate_per_swing_offhand(dmg)
            melee_hps_oh = swings_oh * hate_oh_sw

        proc_hate_per_cast = 0
        spell_dd = 0
        spell_obj = None
        proc_hate_per_cast_bard = 0
        if spell_id is not None and str(spell_id) in spells:
            spell_obj = spells[str(spell_id)]
            proc_hate_per_cast = check_aggro_amount(
                spell_obj,
                caster_level=level,
                target_max_hp=1_000_000,
                class_id=1,
                is_weapon_proc=True,
            )
            proc_hate_per_cast_bard = check_aggro_amount(
                spell_obj,
                caster_level=level,
                target_max_hp=1_000_000,
                class_id=1,
                is_weapon_proc=True,
                is_bard=True,
            )
            spell_dd = spell_direct_damage_total(spell_obj, caster_level=level)

        base_pc_mh = get_proc_chance_fraction(
            dex,
            delay,
            haste_pct=haste_pct,
            overhaste_pct=overhaste_pct,
            hand_is_secondary=False,
            dual_wield_chance_pct=dw_pct,
        )
        wpc_mh = min(1.0, wpc_from_proc_rate(base_pc_mh, proc_rate))
        mh_proc_rolls = mainhand_proc_rolls_per_second(delay, haste_pct, overhaste_pct)
        proc_hps_mh = mh_proc_rolls * wpc_mh * proc_hate_per_cast
        proc_hps_mh_bard = mh_proc_rolls * wpc_mh * proc_hate_per_cast_bard

        proc_hps_oh = 0.0
        proc_hps_oh_bard = 0.0
        wpc_oh = 0.0
        oh_proc_rolls = 0.0
        oh_proc = float(wp.get("hatePerSecOH") or 0) > 0 or float(wp.get("procDpsOH") or 0) > 0
        if oh_proc and not use_2h and proc_hate_per_cast > 0:
            base_pc_oh = get_proc_chance_fraction(
                dex,
                delay,
                haste_pct=haste_pct,
                overhaste_pct=overhaste_pct,
                hand_is_secondary=True,
                dual_wield_chance_pct=dw_pct,
            )
            wpc_oh = min(1.0, wpc_from_proc_rate(base_pc_oh, proc_rate))
            oh_proc_rolls = offhand_proc_rolls_per_second(
                delay, haste_pct, overhaste_pct, dw_chance_pct=dw_pct
            )
            proc_hps_oh = oh_proc_rolls * wpc_oh * proc_hate_per_cast
            proc_hps_oh_bard = oh_proc_rolls * wpc_oh * proc_hate_per_cast_bard

        proc_dps_mh = 0.0
        proc_dps_oh = 0.0
        if spell_dd > 0:
            proc_dps_mh = mh_proc_rolls * wpc_mh * spell_dd
            if oh_proc and not use_2h:
                proc_dps_oh = oh_proc_rolls * wpc_oh * spell_dd

        row: dict[str, object] = {
            "meleeHatePerSecServer": round(melee_hps_mh, 2),
            "hatePerSecServer": round(proc_hps_mh, 2),
            "hatePerSecServerBard": round(proc_hps_mh_bard, 2),
            "meleeHatePerSecOHServer": round(melee_hps_oh, 2) if not use_2h else 0,
            "hatePerSecOHServer": round(proc_hps_oh, 2) if not use_2h else 0,
            "hatePerSecOHServerBard": round(proc_hps_oh_bard, 2) if not use_2h else 0,
            "itemId": item_id,
            "effectSpellId": spell_id,
            "procRateDb": proc_rate,
        }
        if spell_dd > 0:
            row["procDpsServer"] = round(proc_dps_mh, 2)
            if oh_proc and not use_2h:
                row["procDpsOHServer"] = round(proc_dps_oh, 2)
        out[wkey] = row

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2), encoding="utf-8")
    n = len([k for k in out if not str(k).startswith("_")])
    print(f"Wrote {args.out} ({n} weapons)")

    if args.patch_weapon_procs:
        wpn = load_json(args.weapon_procs)
        patched = 0
        for wkey, row in out.items():
            if str(wkey).startswith("_"):
                continue
            ent = wpn.get(wkey)
            if not isinstance(ent, dict):
                continue
            srv = row.get("procDpsServer")
            if srv is not None:
                ent["procDps"] = srv
                patched += 1
            srv_oh = row.get("procDpsOHServer")
            if srv_oh is not None:
                ent["procDpsOH"] = srv_oh
        args.weapon_procs.write_text(json.dumps(wpn, indent=2), encoding="utf-8")
        print(f"Patched procDps in {args.weapon_procs} ({patched} entries with spell DD)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
