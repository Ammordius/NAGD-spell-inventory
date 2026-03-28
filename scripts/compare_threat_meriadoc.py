"""
Compare Meriadoc weapon_procs.json hate columns to server-model JSON / recomputation.

Outputs:
  data/threat_compare_report.csv
  data/threat_compare_summary.md
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_MAG = Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weapon-procs", type=Path, default=_MAG / "data" / "weapon_procs.json")
    ap.add_argument("--server-json", type=Path, default=_MAG / "data" / "weapon_threat_server.json")
    ap.add_argument("--csv-out", type=Path, default=_MAG / "data" / "threat_compare_report.csv")
    ap.add_argument("--md-out", type=Path, default=_MAG / "data" / "threat_compare_summary.md")
    args = ap.parse_args()

    procs = json.loads(args.weapon_procs.read_text(encoding="utf-8"))
    server = json.loads(args.server_json.read_text(encoding="utf-8"))

    rows = []
    for key, w in procs.items():
        if key.startswith("_"):
            continue
        s = server.get(key) or {}
        m_mh = float(w.get("meleeHatePerSec") or 0)
        m_oh = float(w.get("meleeHatePerSecOH") or 0)
        p_mh = float(w.get("hatePerSec") or 0)
        p_oh = float(w.get("hatePerSecOH") or 0)
        meri_total = m_mh + m_oh + p_mh + p_oh

        sm_mh = float(s.get("meleeHatePerSecServer") or 0)
        sm_oh = float(s.get("meleeHatePerSecOHServer") or 0)
        sp_mh = float(s.get("hatePerSecServer") or 0)
        sp_oh = float(s.get("hatePerSecOHServer") or 0)
        srv_total = sm_mh + sm_oh + sp_mh + sp_oh

        delta = srv_total - meri_total
        delta_proc_mh = sp_mh - p_mh
        delta_proc_oh = sp_oh - p_oh
        delta_melee_mh = sm_mh - m_mh
        delta_melee_oh = sm_oh - m_oh
        rows.append(
            {
                "weapon": key,
                "meri_melee_mh": round(m_mh, 2),
                "srv_melee_mh": round(sm_mh, 2),
                "meri_melee_oh": round(m_oh, 2),
                "srv_melee_oh": round(sm_oh, 2),
                "meri_proc_mh": round(p_mh, 2),
                "srv_proc_mh": round(sp_mh, 2),
                "meri_proc_oh": round(p_oh, 2),
                "srv_proc_oh": round(sp_oh, 2),
                "delta_melee_mh": round(delta_melee_mh, 2),
                "delta_melee_oh": round(delta_melee_oh, 2),
                "delta_proc_mh": round(delta_proc_mh, 2),
                "delta_proc_oh": round(delta_proc_oh, 2),
                "meri_total": round(meri_total, 2),
                "srv_total": round(srv_total, 2),
                "delta": round(delta, 2),
                "procRateDb": s.get("procRateDb", ""),
                "notes": "",
            }
        )

    rows.sort(key=lambda r: abs(r["delta"]), reverse=True)

    args.csv_out.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else [
        "weapon",
        "meri_melee_mh",
        "srv_melee_mh",
        "meri_melee_oh",
        "srv_melee_oh",
        "meri_proc_mh",
        "srv_proc_mh",
        "meri_proc_oh",
        "srv_proc_oh",
        "delta_melee_mh",
        "delta_melee_oh",
        "delta_proc_mh",
        "delta_proc_oh",
        "meri_total",
        "srv_total",
        "delta",
        "procRateDb",
        "notes",
    ]
    with args.csv_out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    top = rows[:15]
    # Largest proc-only disagreements (Meriadoc proc MH − server proc MH, by absolute delta)
    proc_rows = sorted(rows, key=lambda r: abs(r["delta_proc_mh"]), reverse=True)[:10]
    lines = [
        "# Meriadoc vs server-model threat (largest absolute **total** deltas first)",
        "",
        "Server model: fixed Warrior 65, haste 70, DEX 255, target max HP 1M — see `weapon_threat_server.json` `_meta`.",
        "Proc frequency uses `items.procrate` from `item_proc_meta.json` when present (re-export from your DB if values differ from TAKP).",
        "",
        "Typical reasons for gaps:",
        "",
        "- **Melee**: Meriadoc ties hate to expected DPS; server uses fixed hate per swing (no crit scaling).",
        "- **Procs (total)**: Meriadoc `hatePerSec` is a separate model from `CheckAggroAmount` + `GetProcChance` × `(100+procrate)/100`.",
        "- **Anger / stun procs**: Magelo uses **400** non-damage cap + **SE_InstantHate** + DD hate per proc (see `check_aggro_amount.py`); Meriadoc sheet numbers use a different model.",
        "- **procRateDb**: If `item_proc_meta.json` is stale or from another fork, proc HPS will not match live TAKP.",
        "",
        "| weapon | Meriadoc total | Server total | Δ |",
        "|--------|----------------|--------------|---|",
    ]
    for r in top:
        lines.append(f"| {r['weapon'][:40]} | {r['meri_total']} | {r['srv_total']} | {r['delta']} |")
    lines.extend(
        [
            "",
            "## Largest proc (MH) disagreements: Meriadoc `hatePerSec` vs server `hatePerSecServer`",
            "",
            "| weapon | Meriadoc proc MH | Server proc MH | Δ proc MH | procRateDb |",
            "|--------|------------------|----------------|-----------|------------|",
        ]
    )
    for r in proc_rows:
        lines.append(
            f"| {r['weapon'][:36]} | {r['meri_proc_mh']} | {r['srv_proc_mh']} | "
            f"{r['delta_proc_mh']} | {r['procRateDb']} |"
        )
    lines.append("")
    args.md_out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.csv_out} and {args.md_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
