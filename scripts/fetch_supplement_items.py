#!/usr/bin/env python3
"""
Fetch supplement item IDs (ornate armor + extra) from TAKP AllaClone and merge into magelo data/item_stats.json.
Use so class_rankings item cards and name→id resolution work for ornate armor and other tracked items.

Reads: data/ornate_armor_ids.json (ornate_from_wiki + extra_ids)
Reads: data/item_stats.json (existing)
Writes: data/item_stats.json (merged)

Usage:
  python scripts/fetch_supplement_items.py [--delay 1.5] [--dry-run]
  python scripts/fetch_supplement_items.py --from-cache path/to/html/cache  # no network

Requires: requests, beautifulsoup4 (pip install requests beautifulsoup4).
Alternatively run from DKP repo: add these IDs to raid_item_sources or a supplement, run build_item_stats, then copy_dkp_item_stats_to_magelo.
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

MAGELO_ROOT = Path(__file__).resolve().parent.parent
SUPPLEMENT_IDS_JSON = MAGELO_ROOT / "data" / "ornate_armor_ids.json"
ITEM_STATS_JSON = MAGELO_ROOT / "data" / "item_stats.json"
TAKP_ITEM_URL = "https://www.takproject.net/allaclone/item.php?id={id}"
USER_AGENT = "TAKP-Magelo-Supplement/1.0 (class_rankings item DB)"


def _parse_item_page(html: str, item_id: int, name: str) -> dict | None:
    """Parse AllaClone item page HTML into item-stats schema. Same logic as dkp/scripts/takp_jsons/build_item_stats.py."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Requires beautifulsoup4: pip install beautifulsoup4", file=sys.stderr)
        return None
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ", strip=True)

    spell_links = []
    for a in soup.find_all("a", href=True):
        m = re.search(r"spell\.php\?id=(\d+)", a.get("href", ""))
        if m:
            spell_links.append((int(m.group(1)), (a.get_text() or "").strip()))

    out: dict = {}

    flags = []
    for token in ["MAGIC ITEM", "LORE ITEM", "NO DROP", "NO TRADE"]:
        if token in text:
            flags.append(token)
    if flags:
        out["flags"] = flags

    m = re.search(
        r"Slot:\s*([A-Za-z0-9\s]+?)(?=\s+Skill:|\s+AC:|\s+STR:|\s+STA:|\s+AGI:|\s+DEX:|\s+WIS:|\s+INT:|\s+CHA:|\s+Required|\s+Recommended|\s+Effect:|\s+Focus|\s+WT:|\s+Class:|\s+Singing|\s+Wind|\s+Brass|\s+Percussion|$)",
        text,
        re.IGNORECASE,
    )
    if m:
        out["slot"] = m.group(1).strip()

    m = re.search(r"Skill:\s*([^A]+?)\s+Atk Delay:\s*(\d+)", text)
    if m:
        out["skill"] = m.group(1).strip()
        out["atkDelay"] = int(m.group(2))
    m = re.search(r"DMG:\s*(\d+)", text)
    if m:
        out["dmg"] = int(m.group(1))
    m = re.search(r"Dmg Bonus:\s*(\d+)", text)
    if m:
        out["dmgBonus"] = int(m.group(1))
        out["dmgBonusNote"] = "(lvl 65)"
    m = re.search(r"AC:\s*(\d+)", text)
    if m:
        out["ac"] = int(m.group(1))

    mod_map = {}
    for stat in ["STR", "STA", "AGI", "DEX", "WIS", "INT", "CHA"]:
        m = re.search(rf"\b{stat}:\s*([+]?\d+)\b", text)
        if m:
            v = m.group(1)
            mod_map[stat] = int(v.replace("+", "")) if v.lstrip("+").isdigit() else v
    for stat in ["HP", "MANA"]:
        m = re.search(rf"\b{stat}:\s*([+]?\d+)\b", text)
        if m:
            v = m.group(1)
            mod_map[stat] = int(v.replace("+", "")) if v.lstrip("+").isdigit() else v
    if mod_map:
        out["mods"] = [{"label": k, "value": v} for k, v in mod_map.items()]

    resists = []
    for r in ["FIRE", "COLD", "MAGIC", "POISON", "DISEASE"]:
        m = re.search(rf"(?:SV\s+)?{r}:\s*([+]?\d+)", text, re.IGNORECASE)
        if m:
            resists.append(
                {"label": r.capitalize() if r != "DISEASE" else "Disease", "value": int(m.group(1).replace("+", ""))}
            )
    if resists:
        out["resists"] = resists

    m = re.search(r"Required level of (\d+)", text, re.IGNORECASE)
    if m:
        out["requiredLevel"] = int(m.group(1))
        out["levelType"] = "required"
    else:
        m = re.search(r"Recommended level of (\d+)", text, re.IGNORECASE)
        if m:
            out["requiredLevel"] = int(m.group(1))
            out["levelType"] = "recommended"

    if spell_links:
        if "Effect:" in text and len(spell_links) >= 1:
            sid, sname = spell_links[0]
            out["effectSpellId"] = sid
            out["effectSpellName"] = sname
            out["effectNote"] = ""
        if "Focus Effect:" in text or "Focus:" in text:
            if len(spell_links) >= 2:
                sid, sname = spell_links[1]
                out["focusSpellId"] = sid
                out["focusSpellName"] = sname
            elif len(spell_links) >= 1:
                sid, sname = spell_links[0]
                out["focusSpellId"] = sid
                out["focusSpellName"] = sname

    m = re.search(r"WT:\s*([\d.]+)", text)
    if m:
        try:
            out["weight"] = float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"Size:\s*(TINY|SMALL|MEDIUM|LARGE)", text, re.IGNORECASE)
    if m:
        out["size"] = m.group(1).upper()

    m = re.search(r"Class:\s*([A-Za-z\s]+?)(?=\s*Race:)", text)
    if m:
        out["classes"] = m.group(1).strip()
    m = re.search(r"Race:\s*([A-Za-z\s]+?)(?=\s+Light:|\s+Tint:|\s*$)", text)
    if m:
        out["races"] = m.group(1).strip()

    m = re.search(r"Light:\s*(\d+)", text, re.IGNORECASE)
    if m:
        out["light"] = int(m.group(1))
    m = re.search(r"Tint:\s*\(([^)]+)\)", text)
    if m:
        out["tint"] = "(" + m.group(1).strip() + ")"

    total_saves = sum((r.get("value") or 0) for r in out.get("resists") or [])
    ac = out.get("ac") or 0
    hp = 0
    for mod in out.get("mods") or []:
        if (mod.get("label") or "").strip().upper() == "HP":
            hp = int(mod.get("value") or 0)
            break
    out["gearScore"] = total_saves + ac + (hp // 3)

    return out if out else None


def load_supplement_ids() -> list[int]:
    """Load ornate + extra IDs from data/ornate_armor_ids.json."""
    if not SUPPLEMENT_IDS_JSON.exists():
        print(f"Missing {SUPPLEMENT_IDS_JSON}", file=sys.stderr)
        return []
    data = json.loads(SUPPLEMENT_IDS_JSON.read_text(encoding="utf-8"))
    ids = list(data.get("ornate_from_wiki") or [])
    ids.extend(data.get("extra_ids") or [])
    return sorted(set(ids))


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Fetch supplement items from TAKP AllaClone and merge into item_stats.json")
    p.add_argument("--delay", type=float, default=1.5, help="Seconds between requests")
    p.add_argument("--dry-run", action="store_true", help="Do not write item_stats.json")
    p.add_argument("--from-cache", type=str, default="", help="Build from local HTML cache dir (e.g. dkp data/item_pages); no network")
    args = p.parse_args()

    supplement_ids = load_supplement_ids()
    if not supplement_ids:
        return 1
    print(f"Supplement IDs: {len(supplement_ids)} (ornate + extra)")

    existing: dict = {}
    if ITEM_STATS_JSON.exists():
        try:
            existing = json.loads(ITEM_STATS_JSON.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"Could not load {ITEM_STATS_JSON}: {e}", file=sys.stderr)
        print(f"Existing item_stats: {len(existing)} entries")
    else:
        ITEM_STATS_JSON.parent.mkdir(parents=True, exist_ok=True)

    missing = [iid for iid in supplement_ids if str(iid) not in existing]
    if not missing:
        print("All supplement IDs already in item_stats. Nothing to fetch.")
        return 0
    print(f"Missing in item_stats: {len(missing)} IDs")

    from_cache = (args.from_cache or "").strip()
    if from_cache:
        cache_dir = Path(from_cache)
        if not cache_dir.is_absolute():
            cache_dir = MAGELO_ROOT / cache_dir
        if not cache_dir.exists():
            print(f"Cache dir not found: {cache_dir}", file=sys.stderr)
            return 1
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            print("Requires beautifulsoup4 for --from-cache", file=sys.stderr)
            return 1
        for iid in missing:
            path = cache_dir / f"{iid}.html"
            if not path.exists():
                existing[str(iid)] = {"name": f"Item {iid}"}
                continue
            html = path.read_text(encoding="utf-8")
            parsed = _parse_item_page(html, iid, f"Item {iid}")
            entry = dict(parsed) if parsed else {}
            if "name" not in entry or entry.get("name") == f"Item {iid}":
                title = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
                if title:
                    entry["name"] = title.group(1).strip().replace(" - EQ Item - The Al`Kabor Project", "").strip()
                else:
                    entry["name"] = f"Item {iid}"
            existing[str(iid)] = entry
        print(f"Loaded {len(missing)} from cache")
    else:
        try:
            import requests
        except ImportError:
            print("Requires requests: pip install requests", file=sys.stderr)
            return 1
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        for i, iid in enumerate(missing, 1):
            try:
                r = session.get(TAKP_ITEM_URL.format(id=iid), timeout=15)
                r.raise_for_status()
                parsed = _parse_item_page(r.text, iid, f"Item {iid}")
                entry = dict(parsed) if parsed else {}
                if "name" not in entry or entry.get("name") == f"Item {iid}":
                    title = re.search(r"<title>([^<]+)</title>", r.text, re.IGNORECASE)
                    if title:
                        entry["name"] = title.group(1).strip().replace(" - EQ Item - The Al`Kabor Project", "").strip()
                    else:
                        entry["name"] = f"Item {iid}"
                existing[str(iid)] = entry
                print(f"  [{i}/{len(missing)}] id={iid} {entry.get('name', '')[:50]}")
            except Exception as e:
                existing[str(iid)] = {"name": f"Item {iid}"}
                print(f"  [{i}/{len(missing)}] id={iid} ERROR: {e}")
            if i < len(missing):
                time.sleep(args.delay)

    if not args.dry_run:
        ITEM_STATS_JSON.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        print(f"Wrote {ITEM_STATS_JSON} ({len(existing)} entries)")
    else:
        print("Dry run: did not write item_stats.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
