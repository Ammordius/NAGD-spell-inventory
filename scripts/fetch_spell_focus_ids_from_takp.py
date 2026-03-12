#!/usr/bin/env python3
"""
Fetch spell focus item IDs from TAKP AllaClone search and backfill known_spell_focus_item_ids.json.

Reads: data/spell_focii_missing_ids.txt
Reads: data/known_spell_focus_item_ids.json (existing mappings)
Writes: data/known_spell_focus_item_ids.json (merged with new IDs)

Search URL: https://www.takproject.net/allaclone/items.php?iname=<name>&...
When exactly one result: page may show single item; we parse item.php?id= links from HTML.
When multiple results: we pick the first item.php?id= link (or best match by name).

Usage:
  python scripts/fetch_spell_focus_ids_from_takp.py [--delay 1.5] [--dry-run] [--limit N]

Requires: requests (pip install requests)
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import quote_plus

MAGELO_ROOT = Path(__file__).resolve().parent.parent
MISSING_IDS_TXT = MAGELO_ROOT / "data" / "spell_focii_missing_ids.txt"
KNOWN_JSON = MAGELO_ROOT / "data" / "known_spell_focus_item_ids.json"
SEARCH_BASE = "https://www.takproject.net/allaclone/items.php"
USER_AGENT = "TAKP-Magelo-SpellFocus/1.0"


def extract_item_name(line: str) -> str | None:
    """Extract item name from line like 'Affliction Efficiency: Ceramic Gavel of Justice'."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if ": " in line:
        return line.split(": ", 1)[1].strip()
    return line


def search_takp_for_item(name: str, session) -> int | None:
    """
    Search TAKP AllaClone for item by name. Returns item_id if found, else None.
    Uses items.php?iname=<name>&... and parses item.php?id= links from the response.
    Tries alternate spellings (apostrophe variants) when primary search fails.
    """
    # Build search query - use key words; "Ceramic Gavel of Justice" -> "ceramic gavel of justice"
    iname = name
    url = (
        f"{SEARCH_BASE}?"
        f"iname={quote_plus(iname)}"
        "&iclass=-1&irace=-1&islot=0"
        "&istat1=&istat1comp=%3E%3D&istat1value="
        "&istat2=&istat2comp=%3E%3D&istat2value="
        "&iresists=&iresistscomp=%3E%3D&iresistsvalue="
        "&imod=&imodcomp=%3E%3D&imodvalue="
        "&ieffect=&iminlevel=0&ireqlevel=0"
        "&iavailability=0&iavaillevel=0&ideity=0&isearch=Search"
    )
    try:
        r = session.get(url, timeout=15, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
    except Exception as e:
        print(f"    Error fetching {name!r}: {e}", file=sys.stderr)
        return None

    # Check if we were redirected to item.php?id=X (single result)
    if "item.php?id=" in r.url:
        m = re.search(r"item\.php\?id=(\d+)", r.url)
        if m:
            return int(m.group(1))

    # Parse HTML for item.php?id= links
    ids = re.findall(r"item\.php\?id=(\d+)", r.text)
    if not ids:
        # Try alternate spelling: "Headsmans" -> "Headsman's", "Gallenites" -> "Gallenite's"
        alt_name = re.sub(r"([a-z])s\s+", r"\1's ", name, flags=re.I)
        if alt_name != name:
            return search_takp_for_item(alt_name, session)
        return None

    # Dedupe preserving order; first is usually the best match
    seen = set()
    unique_ids = []
    for iid in ids:
        if iid not in seen:
            seen.add(iid)
            unique_ids.append(int(iid))

    if len(unique_ids) == 1:
        return unique_ids[0]
    # Multiple results: prefer one where item name appears in page near the link
    # For simplicity, return first - caller can verify
    return unique_ids[0]


def main() -> int:
    try:
        import requests
    except ImportError:
        print("Requires requests: pip install requests", file=sys.stderr)
        return 1

    import argparse
    p = argparse.ArgumentParser(description="Fetch spell focus item IDs from TAKP and backfill known_spell_focus_item_ids.json")
    p.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    p.add_argument("--dry-run", action="store_true", help="Do not write JSON")
    p.add_argument("--limit", type=int, default=0, help="Max items to fetch (0 = all)")
    args = p.parse_args()

    if not MISSING_IDS_TXT.is_file():
        print(f"Missing {MISSING_IDS_TXT}", file=sys.stderr)
        return 1

    lines = MISSING_IDS_TXT.read_text(encoding="utf-8").splitlines()
    items = []
    for line in lines:
        name = extract_item_name(line)
        if name:
            items.append(name)

    # Load existing known mappings
    known: dict[str, int] = {}
    if KNOWN_JSON.is_file():
        try:
            data = json.loads(KNOWN_JSON.read_text(encoding="utf-8"))
            for k, v in (data or {}).items():
                if not k.startswith("_") and v is not None:
                    known[k] = int(v)
        except Exception as e:
            print(f"Could not load {KNOWN_JSON}: {e}", file=sys.stderr)
    print(f"Existing known mappings: {len(known)}")

    # Skip items we already have
    to_fetch = [n for n in items if n not in known]
    if not to_fetch:
        print("No new items to fetch.")
        return 0

    if args.limit:
        to_fetch = to_fetch[: args.limit]
    print(f"Fetching {len(to_fetch)} items from TAKP AllaClone...")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    added = 0

    for i, name in enumerate(to_fetch):
        if i > 0:
            time.sleep(args.delay)
        iid = search_takp_for_item(name, session)
        if iid is not None:
            known[name] = iid
            added += 1
            print(f"  + {name} -> {iid}")
        else:
            print(f"  - {name} (not found)")

    if added and not args.dry_run:
        # Preserve _comment if present
        out = {"_comment": (
            "Manual item ID mappings for spell_focii items not in item_stats. "
            "Verify IDs at https://www.takproject.net/allaclone/fullsearch.php?isearchtype=name&iname=<itemname>"
        )}
        for k, v in sorted(known.items()):
            out[k] = v
        KNOWN_JSON.parent.mkdir(parents=True, exist_ok=True)
        KNOWN_JSON.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nWrote {added} new mappings to {KNOWN_JSON}")
    elif added:
        print(f"\n[DRY RUN] Would add {added} mappings")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
