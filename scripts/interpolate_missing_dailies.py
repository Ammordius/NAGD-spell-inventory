#!/usr/bin/env python3
"""Synthesize delta_daily JSONs for missing calendar days between two known endpoint dailies.

When magelo-dump caches are gone, this rebuilds intermediate days by linearly interpolating
character level/AA/HP between reconstructed endpoint states (same baseline_date era only).
Inventory is taken from the earlier endpoint (usually unchanged over a few days).

Use only as a fallback; prefer regenerate-delta-days.yml when dump caches exist.
"""

from __future__ import annotations

import argparse
import copy
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")


def _load_gz(path: Path) -> dict:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-dir", type=Path, default=Path("delta_snapshots"))
    ap.add_argument("--baseline-era", default="2026-02-09")
    ap.add_argument("--start-date", required=True, metavar="YYYY-MM-DD")
    ap.add_argument("--end-date", required=True, metavar="YYYY-MM-DD")
    ap.add_argument(
        "--fill-dates",
        required=True,
        help="Comma-separated dates to synthesize (must lie strictly between start and end)",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    from delta_storage import (  # noqa: E402
        _cumulative_char_stats_at_slice,
        load_baseline_for_date,
        load_daily_delta_json,
        save_daily_delta_from_baseline,
    )

    base_dir = (root / args.base_dir).resolve()
    era = args.baseline_era.strip()
    bl = load_baseline_for_date(era, str(base_dir))
    if not bl:
        print(f"ERROR: missing baseline for {era}", file=sys.stderr)
        return 1
    baseline_chars = bl.get("characters") or {}

    d_start = load_daily_delta_json(args.start_date, str(base_dir))
    d_end = load_daily_delta_json(args.end_date, str(base_dir))
    if not d_start or not d_end:
        print("ERROR: start or end daily JSON missing", file=sys.stderr)
        return 1
    if d_start.get("baseline_date") != era or d_end.get("baseline_date") != era:
        print("ERROR: endpoint dailies must use the same baseline_date as --baseline-era", file=sys.stderr)
        return 1

    cd_s = d_start.get("char_deltas") or {}
    cd_e = d_end.get("char_deltas") or {}
    all_names = set(baseline_chars.keys()) | set(cd_s.keys()) | set(cd_e.keys())

    t0 = _parse_date(args.start_date)
    t1 = _parse_date(args.end_date)
    span = (t1 - t0).days
    if span <= 0:
        print("ERROR: end-date must be after start-date", file=sys.stderr)
        return 1

    state_start: dict[str, tuple[int, int, int]] = {}
    state_end: dict[str, tuple[int, int, int]] = {}
    for name in all_names:
        state_start[name] = _cumulative_char_stats_at_slice(baseline_chars, name, cd_s)
        state_end[name] = _cumulative_char_stats_at_slice(baseline_chars, name, cd_e)

    def _char_data_from_stats(name: str, lvl: int, aa_total: int, hp: int) -> dict:
        bc = baseline_chars.get(name) or {}
        aa_unspent = int(bc.get("aa_unspent", 0) or 0)
        aa_spent = max(0, int(aa_total) - aa_unspent)
        return {
            "id": bc.get("id", ""),
            "level": lvl,
            "aa_unspent": aa_unspent,
            "aa_spent": aa_spent,
            "hp_max_total": hp,
            "class": bc.get("class", ""),
            "race": bc.get("race", ""),
            "guild": bc.get("guild", ""),
        }

    # Use start-day inventories as proxy for intermediate days.
    inv_proxy = copy.deepcopy(bl.get("inventories") or {})

    fill_dates = [x.strip() for x in args.fill_dates.split(",") if x.strip()]
    shutil = __import__("shutil")
    arch = base_dir / f"baseline_master_{era}.json.gz"
    shutil.copy2(arch, base_dir / "baseline_master.json.gz")

    for date in fill_dates:
        td = _parse_date(date)
        if not (t0 < td < t1):
            print(f"SKIP {date}: not strictly between {args.start_date} and {args.end_date}")
            continue
        frac = (td - t0).days / span
        char_data = {}
        for name in all_names:
            ls, as_, hs = state_start[name]
            le, ae, he = state_end[name]
            lvl = int(round(ls + (le - ls) * frac))
            aa = int(round(as_ + (ae - as_) * frac))
            hp = int(round(hs + (he - hs) * frac))
            if lvl == 0 and le == 0 and ls == 0:
                continue
            char_data[name] = _char_data_from_stats(name, lvl, aa, hp)

        out_gz = base_dir / f"delta_daily_{date}.json.gz"
        out_gz.unlink(missing_ok=True)
        (base_dir / f"delta_daily_{date}.json").unlink(missing_ok=True)
        save_daily_delta_from_baseline(
            char_data, inv_proxy, date, str(base_dir), auto_reset_baseline=False
        )
        doc = _load_gz(out_gz)
        print(
            f"OK {date} chars={len(doc.get('char_deltas') or {})} "
            f"baseline={doc.get('baseline_date')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
