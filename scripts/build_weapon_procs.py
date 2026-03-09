"""
Build data/weapon_procs.json from Meriadoc's TAKP Weapon Chart CSVs.
Proc DPS and hate/sec are taken from the weapon sheets (1H Primary, 1H Secondary, 2H)
when present; otherwise from Proc Info.csv. Name normalization matches dps_calculator.html.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path


def normalize_name(s: str) -> str:
    """Same rule as calculator: trim, lower, collapse spaces."""
    if not s or not isinstance(s, str):
        return ""
    return " ".join(s.strip().lower().split())


def load_proc_info(path: Path) -> dict[str, dict]:
    """Proc Info.csv: cols Weapon(0), Proc(1), Hate per second(4), Damage per second(5)."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # header
        for row in reader:
            if len(row) < 6:
                continue
            weapon = row[0].strip()
            if not weapon or weapon.lower() == "none":
                continue
            proc_name = (row[1] or "").strip()
            try:
                hate_ps = float(row[4].strip() or 0)
            except (ValueError, IndexError):
                hate_ps = 0
            try:
                dmg_ps = float(row[5].strip() or 0)
            except (ValueError, IndexError):
                dmg_ps = 0
            key = normalize_name(weapon)
            if key and key not in out:  # first wins
                out[key] = {
                    "procName": proc_name or None,
                    "procDps": round(dmg_ps, 2),
                    "hatePerSec": round(hate_ps, 2),
                }
    return out


def find_col(header_row: list[str], want: str) -> int:
    """Find column index by header (handles multiline like 'Round/\\nSec')."""
    want_flat = want.lower().replace("\n", " ").strip()
    for i, cell in enumerate(header_row):
        if want_flat in cell.lower().replace("\n", " "):
            return i
    return -1


def load_weapon_sheet(
    path: Path,
    proc_dps_header: str = "Proc DPS",
    hate_sec_header: str = "PHate/ Sec",  # proc hate only; Hate/ Sec = total
) -> dict[str, dict]:
    """Parse a weapon CSV; return normalized name -> { procName?, procDps, hatePerSec }."""
    out = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        idx_weapon = find_col(header, "Weapon")
        idx_proc_dps = find_col(header, proc_dps_header)
        idx_hate_sec = find_col(header, hate_sec_header)
        if idx_weapon < 0:
            return out
        for row in reader:
            if len(row) <= idx_weapon:
                continue
            weapon = (row[idx_weapon] or "").strip()
            if not weapon:
                continue
            key = normalize_name(weapon)
            if not key:
                continue
            try:
                proc_dps = float(row[idx_proc_dps].strip() or 0) if idx_proc_dps >= 0 and len(row) > idx_proc_dps else 0
            except (ValueError, IndexError):
                proc_dps = 0
            try:
                hate_sec = float(row[idx_hate_sec].strip() or 0) if idx_hate_sec >= 0 and len(row) > idx_hate_sec else 0
            except (ValueError, IndexError):
                hate_sec = 0
            entry = {
                "procDps": round(proc_dps, 2),
                "hatePerSec": round(hate_sec, 2),
            }
            out[key] = entry
    return out


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    sheets_dir = root / "meriadoc sheets"
    data_dir = root / "data"
    data_dir.mkdir(exist_ok=True)

    # 1) Proc Info as fallback (has proc name + hate/dps)
    proc_info_path = sheets_dir / "Meriadoc's TAKP Weapon Chart - Proc Info.csv"
    combined: dict[str, dict] = {}
    if proc_info_path.exists():
        combined = load_proc_info(proc_info_path)
    else:
        print(f"Warning: {proc_info_path} not found")

    # 2) Weapon sheets override (prefer 1H Primary, then 1H Secondary, then 2H)
    for sheet_name, path_suffix in [
        ("1H Primary", "Meriadoc's TAKP Weapon Chart - 1H Primary.csv"),
        ("1H Secondary", "Meriadoc's TAKP Weapon Chart - 1H Secondary.csv"),
        ("2H Weapons", "Meriadoc's TAKP Weapon Chart - 2H Weapons.csv"),
    ]:
        path = sheets_dir / path_suffix
        if not path.exists():
            print(f"Warning: {path} not found")
            continue
        sheet_data = load_weapon_sheet(path)
        for key, entry in sheet_data.items():
            existing = combined.get(key, {})
            proc_name = existing.get("procName") if isinstance(existing, dict) else None
            combined[key] = {
                "procName": proc_name,
                "procDps": entry.get("procDps", 0),
                "hatePerSec": entry.get("hatePerSec", 0),
            }
        print(f"Loaded {sheet_name}: {len(sheet_data)} weapons")

    # Keep all entries so calculator can show proc/hate for any weapon that appears in sheets
    out = combined
    out_path = data_dir / "weapon_procs.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {out_path} ({len(out)} entries)")


if __name__ == "__main__":
    main()
