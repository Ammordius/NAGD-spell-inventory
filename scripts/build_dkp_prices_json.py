#!/usr/bin/env python3
"""
Build a JSON file of the most recent 3 DKP prices per item, for items that exist
in both magelo item_stats and Supabase raid_loot. Intended to be merged into
magelo (e.g. data/dkp_prices.json) so item_stats can be augmented with DKP data.

Elemental loot: raid_loot uses DKP purchase names (e.g. "Timeless Leather Tunic Pattern");
the actual worn pieces are per-class (e.g. Ton Po's Chestguard). We load
dkp_elemental_to_magelo.json (from DKP repo) and map each DKP name to all Magelo
item_ids; DKP history is then attached to each of those IDs so the class_rankings
upgrade finder shows DKP for elemental armor.

Workflow:
  1) Cross-reference: item_stats name -> item_id; plus elemental DKP name -> [magelo_item_ids].
  2) Pull from Supabase: raid_loot, raids (dates).
  3) For each loot row: match by name (or elemental map); attach (date, cost) to resolved id(s).
  4) Write JSON: { "item_id": { "dkp_prices": [ {"cost": N, "date": "YYYY-MM-DD"}, ... ] }, ... }

Requires: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY if RLS allows read).

Usage:
  python scripts/build_dkp_prices_json.py [--item-stats data/item_stats.json] [--out data/dkp_prices.json]
  python scripts/build_dkp_prices_json.py [--elemental-json ../dkp/dkp_elemental_to_magelo.json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
import re

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_ITEM_STATS = REPO_ROOT / "data" / "item_stats.json"
DEFAULT_OUT = REPO_ROOT / "data" / "dkp_prices.json"
# DKP repo (sibling of magelo) has the canonical elemental mapping
DEFAULT_ELEMENTAL_JSON = REPO_ROOT.parent / "dkp" / "dkp_elemental_to_magelo.json"
PAGE_SIZE = 1000
LAST_N_PRICES = 3


def normalize_item_name_for_lookup(name: str) -> str:
    """Match DKP assign_loot / frontend: lowercase, strip, collapse spaces, remove apostrophes, hyphen->space."""
    if not name or not isinstance(name, str):
        return ""
    s = name.strip()
    for c in ("'", "'", "`", "\u2019", "\u2018"):
        s = s.replace(c, "")
    s = s.replace("-", " ")
    s = " ".join(re.split(r"\s+", s.lower()))
    return s


def load_elemental_dkp_name_to_magelo_ids(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]], set[str]]:
    """
    Load dkp_elemental_to_magelo.json and return:
    - normalized DKP purchase name -> list of Magelo item_ids
    - dkp_purchase_id (e.g. "16373") -> list of Magelo item_ids (for when raid_loot stores id not name)
    - set of all Magelo elemental piece ids (for when raid_loot stores magelo id as item_name)
    """
    name_to_ids: dict[str, list[str]] = {}
    dkp_id_to_magelo_ids: dict[str, list[str]] = {}
    all_magelo_ids: set[str] = set()
    if not path.is_file():
        return (name_to_ids, dkp_id_to_magelo_ids, all_magelo_ids)
    data = json.loads(path.read_text(encoding="utf-8"))
    purchases = data.get("dkp_purchases") or {}
    for dkp_id, entry in purchases.items():
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        by_class = entry.get("magelo_item_ids_by_class") or {}
        ids = list({str(v).strip() for v in by_class.values() if v})
        if not ids:
            continue
        dkp_id_to_magelo_ids[str(dkp_id).strip()] = ids
        all_magelo_ids.update(ids)
        if name:
            norm = normalize_item_name_for_lookup(name)
            name_to_ids[norm] = ids
    return (name_to_ids, dkp_id_to_magelo_ids, all_magelo_ids)


def load_item_stats(path: Path) -> dict:
    """Load item_stats.json and return dict id -> entry."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_name_to_item_id(item_stats: dict) -> dict[str, str]:
    """
    Build normalized item name -> item_id from item_stats.
    Uses same normalization as raid_loot lookup (apostrophe/hyphen) so names match.
    """
    out: dict[str, str] = {}
    for item_id, entry in item_stats.items():
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not name or not isinstance(name, str):
            continue
        key = normalize_item_name_for_lookup(name)
        if key and key not in out:
            out[key] = str(item_id)
    return out


def parse_cost(cost) -> int | None:
    """Parse cost to int; return None if invalid."""
    if cost is None:
        return None
    if isinstance(cost, int):
        return cost
    if isinstance(cost, str):
        try:
            return int(cost.strip())
        except ValueError:
            return None
    return None


def date_iso_slice(date_iso) -> str | None:
    """Get YYYY-MM-DD from date_iso string or None."""
    if not date_iso:
        return None
    s = str(date_iso).strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build DKP prices JSON from Supabase for items in item_stats."
    )
    ap.add_argument(
        "--item-stats",
        type=Path,
        default=DEFAULT_ITEM_STATS,
        help="Path to item_stats.json",
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help="Output JSON path",
    )
    ap.add_argument(
        "--elemental-json",
        type=Path,
        default=DEFAULT_ELEMENTAL_JSON,
        help="Path to dkp_elemental_to_magelo.json (DKP repo) for elemental loot name -> magelo item_ids",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print counts and item_ids that would get DKP data; do not write file.",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print which env and key type are used (no secrets).",
    )
    args = ap.parse_args()

    # Load env from dkp/web/.env.local or .env if present (so we can use VITE_* vars)
    try:
        from dotenv import load_dotenv
        dkp_web = REPO_ROOT.parent / "dkp" / "web"
        for name in (".env", ".env.local"):
            path = dkp_web / name
            if path.is_file():
                load_dotenv(path)
                if getattr(args, "verbose", False):
                    print(f"Loaded env from {path}", file=sys.stderr)
                break
    except ImportError:
        pass

    if not args.item_stats.is_file():
        print(f"item_stats not found: {args.item_stats}", file=sys.stderr)
        return 1

    url = (
        os.environ.get("SUPABASE_URL", "").strip()
        or os.environ.get("VITE_SUPABASE_URL", "").strip()
    )
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("SUPABASE_ANON_KEY", "").strip()
        or os.environ.get("VITE_SUPABASE_SERVICE_ROLE_KEY", "").strip()
        or os.environ.get("VITE_SUPABASE_ANON_KEY", "").strip()
    )
    if not url or not key:
        print(
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY). "
        "From dkp/web use VITE_SUPABASE_URL and VITE_SUPABASE_SERVICE_ROLE_KEY or VITE_SUPABASE_ANON_KEY.",
            file=sys.stderr,
        )
        return 1

    if args.verbose:
        key_type = "service_role" if (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("VITE_SUPABASE_SERVICE_ROLE_KEY")) else "anon"
        print(f"Using URL: {url[:50]}... key type: {key_type}", file=sys.stderr)

    try:
        from supabase import create_client
    except ImportError:
        print("Install supabase: pip install supabase", file=sys.stderr)
        return 1

    # 1) Cross-reference: build name -> item_id from item_stats; load elemental DKP name -> [magelo_ids] and id-based maps
    item_stats = load_item_stats(args.item_stats)
    name_to_id = build_name_to_item_id(item_stats)
    elemental_dkp_to_magelo, elemental_dkp_id_to_magelo_ids, elemental_all_magelo_ids = load_elemental_dkp_name_to_magelo_ids(args.elemental_json)
    if elemental_dkp_to_magelo:
        print(f"Elemental DKP names -> magelo ids: {len(elemental_dkp_to_magelo)} entries", file=sys.stderr)
    print(f"item_stats: {len(item_stats)} items, {len(name_to_id)} with names", file=sys.stderr)

    client = create_client(url, key)

    # 2) Fetch raid_loot (item_name, cost, raid_id) — single table, no join to minimize query shape
    loot_rows: list[dict] = []
    offset = 0
    while True:
        resp = (
            client.table("raid_loot")
            .select("item_name, cost, raid_id")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
        )
        rows = resp.data or []
        if not rows:
            break
        loot_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    print(f"Fetched {len(loot_rows)} raid_loot rows", file=sys.stderr)

    # Collect unique raid_ids and fetch raid dates
    raid_ids = list({r["raid_id"] for r in loot_rows if r.get("raid_id")})
    raids_by_id: dict[str, dict] = {}
    if raid_ids:
        # Fetch raids in chunks to avoid URL length limits
        chunk = 200
        for i in range(0, len(raid_ids), chunk):
            batch = raid_ids[i : i + chunk]
            resp = (
                client.table("raids")
                .select("raid_id, date_iso")
                .in_("raid_id", batch)
                .execute()
            )
            for row in resp.data or []:
                raids_by_id[row["raid_id"]] = row
    print(f"Fetched {len(raids_by_id)} raid dates", file=sys.stderr)

    # 3) Filter to items in item_stats or elemental map; attach date and item_id(s)
    by_item_id: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for row in loot_rows:
        item_name = row.get("item_name")
        if not item_name:
            continue
        norm = normalize_item_name_for_lookup(str(item_name).strip())
        raid_id = row.get("raid_id")
        date_str = None
        if raid_id:
            r = raids_by_id.get(raid_id)
            if r:
                date_str = date_iso_slice(r.get("date_iso"))
        if not date_str:
            date_str = ""
        cost = parse_cost(row.get("cost"))
        if cost is None:
            cost = 0

        # Try item_stats name first; then exact elemental DKP name -> all magelo piece ids; then numeric id (DKP purchase id -> bridge to Magelo ids, or Magelo id directly)
        item_id = name_to_id.get(norm)
        if item_id:
            by_item_id[item_id].append((date_str, cost))
        elif norm in elemental_dkp_to_magelo:
            for mid in elemental_dkp_to_magelo[norm]:
                by_item_id[mid].append((date_str, cost))
        elif norm.isdigit():
            # raid_loot may store item_name as number: DKP purchase id (e.g. "16373") -> bridge to all Magelo ids; or Magelo piece id (e.g. "16693") -> that id. Stats come from Raex/Magelo; DKP uses its own ids, hence the bridge.
            num_id = norm
            if num_id in elemental_dkp_id_to_magelo_ids:
                for mid in elemental_dkp_id_to_magelo_ids[num_id]:
                    by_item_id[mid].append((date_str, cost))
            elif num_id in elemental_all_magelo_ids:
                by_item_id[num_id].append((date_str, cost))

    # 4) For each item_id: sort by date desc, take last 3
    result: dict[str, dict] = {}
    for item_id, pairs in by_item_id.items():
        # Most recent first: sort by date desc, then take 3
        pairs.sort(key=lambda p: (p[0] or "", -(p[1] or 0)), reverse=True)
        last3 = pairs[:LAST_N_PRICES]
        result[item_id] = {
            "dkp_prices": [
                {"date": d, "cost": c}
                for d, c in last3
            ]
        }

    if args.dry_run:
        print(f"Would write {len(result)} items with DKP prices", file=sys.stderr)
        for item_id in sorted(result.keys(), key=lambda x: int(x) if str(x).isdigit() else 0):
            print(f"  {item_id}: {result[item_id]['dkp_prices']}", file=sys.stderr)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote {len(result)} items to {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
