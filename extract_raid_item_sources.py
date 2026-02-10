#!/usr/bin/env python3
"""
Extract item IDs and their drop sources (mob, zone) from raid_items.txt.
Processes every item block (data-id); itemdrop may be missing in truncated/corrupt blocks.
Outputs: raid_item_ids.txt (plain list) and raid_item_sources.json (item -> mob/zone).
"""
import re
import json
from pathlib import Path

INPUT = Path(__file__).parent / "raid_items.txt"
IDS_OUT = Path(__file__).parent / "raid_item_ids.txt"
JSON_OUT = Path(__file__).parent / "raid_item_sources.json"

# Start of next item block (details row with data-id)
DATA_ID_PAT = re.compile(r'data-id="(\d+)"')
# Within a block: item name (first occurrence after data-id)
ITEMNAME_PAT = re.compile(r'<span class="itemname">([^<]*)</span>')
# Within a block: drop source - "Raid: Mob in Zone" or "Appears in X instance" or other
ITEMDROP_PAT = re.compile(r'<span class="itemdrop">([^<]+)</span>')
# Section header: <h2 id="...">Mob Name</h2> — items below this belong to this boss until next h2
H2_PAT = re.compile(r'<h2\s+id="[^"]*">([^<]+)</h2>')
# Zone labels (standalone lines) — map to zone name for items below until next label
ZONE_LABEL_PAT = re.compile(r'(?m)^(water|vex thall|fire|time|ssra|seru)\s*$')
ZONE_LABEL_TO_NAME = {
    "water": "Plane of Water",
    "vex thall": "Vex Thal",
    "fire": "Plane of Fire",
    "time": "Plane of Time",
    "ssra": "Temple of Ssraeshza",
    "seru": "Sanctus Seru",
}


def parse_drop(drop_text: str) -> tuple[str, str]:
    """Parse 'Raid: Mob in Zone' or 'Appears in X instance' into (mob, zone)."""
    drop_text = drop_text.strip()
    if not drop_text:
        return "", ""
    # "Raid: Mob in Zone"
    if drop_text.lower().startswith("raid:"):
        drop_text = drop_text[5:].strip()
        if " in " in drop_text:
            mob, zone = drop_text.rsplit(" in ", 1)
            return mob.strip(), zone.strip()
        return drop_text, ""
    # "Appears in \"Earth B\" instance" -> zone = Earth B, mob = (instance)
    if "appears in " in drop_text.lower():
        # Extract quoted or unquoted zone name before "instance"
        m = re.search(r'appears in\s+["\']?([^"\']+)["\']?\s+instance', drop_text, re.I)
        if m:
            return "(instance)", m.group(1).strip()
    return drop_text, ""


def _section_at(pos: int, sections: list[tuple[int, str]]) -> str:
    """Return the section (mob or zone) that applies at character position pos."""
    out = ""
    for p, name in sections:
        if p <= pos:
            out = name
        else:
            break
    return out


def _zone_start_at(pos: int, zone_sections: list[tuple[int, str]]) -> int:
    """Return the character position of the zone label that applies at pos (for scoping mob to zone)."""
    zone_start = 0
    for p, _ in zone_sections:
        if p <= pos:
            zone_start = p
        else:
            break
    return zone_start


def _mob_in_zone(item_start: int, zone_start: int, h2_sections: list[tuple[int, str]]) -> str:
    """Return the last (most recent) h2 mob that appears between zone_start and item_start.
    This ensures we use the correct mob within the current zone, not the first mob from a previous zone."""
    out = ""
    for p, name in h2_sections:
        if zone_start <= p <= item_start:
            out = name
        elif p > item_start:
            break
    return out


def main():
    text = INPUT.read_text(encoding="utf-8", errors="replace")

    # Build (position, mob name) for each <h2> so we can infer boss for items with no itemdrop
    h2_sections = [(m.start(), m.group(1).strip()) for m in H2_PAT.finditer(text)]
    # Build (position, zone name) for each zone label
    zone_sections = [
        (m.start(), ZONE_LABEL_TO_NAME.get(m.group(1).lower(), m.group(1).title()))
        for m in ZONE_LABEL_PAT.finditer(text)
    ]

    matches = list(DATA_ID_PAT.finditer(text))
    sources = {}
    # Carry forward last explicit itemdrop (mob, zone) within the same zone when blocks are truncated
    last_drop: tuple[str, str, int] | None = None  # (mob, zone, zone_start)

    for i, m in enumerate(matches):
        item_id = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        name = ""
        name_m = ITEMNAME_PAT.search(block)
        if name_m:
            name = name_m.group(1).strip()

        zone = _section_at(start, zone_sections)
        zone_start = _zone_start_at(start, zone_sections)

        mob, zone_from_drop = "", ""
        drop_m = ITEMDROP_PAT.search(block)
        if drop_m:
            mob, zone_from_drop = parse_drop(drop_m.group(1))
            if mob or zone_from_drop:
                zone = zone_from_drop or zone
                last_drop = (mob, zone, zone_start)

        # If block has no itemdrop (truncated), use last seen itemdrop in this zone, else last h2 in zone
        if not (mob or zone_from_drop):
            if last_drop and last_drop[2] == zone_start:
                mob, zone = last_drop[0], last_drop[1]
            else:
                mob = _mob_in_zone(start, zone_start, h2_sections)

        # Prefer keeping existing mob/zone if this block is truncated (no drop text) and we've seen this item before
        existing = sources.get(str(item_id))
        if existing and (existing["mob"] or existing["zone"]) and not (mob or zone):
            mob, zone = existing["mob"], existing["zone"]
        if existing and existing["name"] and not name:
            name = existing["name"]

        sources[str(item_id)] = {
            "mob": mob,
            "zone": zone,
            "name": name or f"(item {item_id})",
        }

    item_ids = sorted(sources.keys(), key=int)

    IDS_OUT.write_text("\n".join(item_ids) + "\n", encoding="utf-8")
    print(f"Wrote {len(item_ids)} item IDs to {IDS_OUT}")

    out = {k: {"mob": v["mob"], "zone": v["zone"], "name": v["name"]} for k, v in sources.items()}
    JSON_OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {len(sources)} item sources to {JSON_OUT}")

    with_source = sum(1 for v in sources.values() if v["mob"] or v["zone"])
    print(f"  ({with_source} with mob/zone, {len(sources) - with_source} without)")


if __name__ == "__main__":
    main()
