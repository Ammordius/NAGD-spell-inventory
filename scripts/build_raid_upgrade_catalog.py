#!/usr/bin/env python3
"""
Build a deterministic offline raid upgrade catalog for six allowlisted zones.

Inputs (all local/static; no DB or Supabase):
  - raid_item_sources.json
  - dkp_mob_loot.json (sibling NAGD-DKP preferred)
  - dkp_elemental_to_magelo.json (or data/elemental_slot_options.json fallback)
  - data/item_stats.json

Outputs:
  - data/raid_upgrade_catalog.json
  - data/raid_upgrade_catalog_coverage.json

Usage:
  python scripts/build_raid_upgrade_catalog.py
  python scripts/build_raid_upgrade_catalog.py --dkp-loot ../dkp/data/dkp_mob_loot.json
  python scripts/build_raid_upgrade_catalog.py --validate
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

DEFAULT_RAID_SOURCES = REPO_ROOT / "raid_item_sources.json"
DEFAULT_ITEM_STATS = REPO_ROOT / "data" / "item_stats.json"
DEFAULT_OUT = REPO_ROOT / "data" / "raid_upgrade_catalog.json"
DEFAULT_COVERAGE_OUT = REPO_ROOT / "data" / "raid_upgrade_catalog_coverage.json"
DEFAULT_ELEMENTAL_SLOT_OPTIONS = REPO_ROOT / "data" / "elemental_slot_options.json"

# Prefer sibling NAGD-DKP; fall back to Magelo copies when present.
DEFAULT_DKP_LOOT_CANDIDATES = [
    REPO_ROOT.parent / "dkp" / "data" / "dkp_mob_loot.json",
    REPO_ROOT / "dkp_mob_loot.json",
]
DEFAULT_ELEMENTAL_CANDIDATES = [
    REPO_ROOT.parent / "dkp" / "dkp_elemental_to_magelo.json",
    REPO_ROOT / "dkp_elemental_to_magelo.json",
]

CATALOG_VERSION = 1

# Explicit six-zone allowlist. Aliases are matching only; display_name is canonical.
ZONE_DEFS: list[dict[str, Any]] = [
    {
        "zone_id": "plane_of_time",
        "display_name": "Plane of Time",
        "aliases": ["plane of time", "time", "pot"],
    },
    {
        "zone_id": "plane_of_water",
        "display_name": "Plane of Water",
        "aliases": ["plane of water", "water"],
    },
    {
        "zone_id": "plane_of_fire",
        "display_name": "Plane of Fire",
        "aliases": ["plane of fire", "fire"],
    },
    {
        "zone_id": "vex_thal",
        "display_name": "Vex Thal",
        "aliases": ["vex thal", "vex thall"],
    },
    {
        "zone_id": "temple_of_ssraeshza",
        "display_name": "Temple of Ssraeshza",
        "aliases": [
            "temple of ssraeshza",
            "ssraeshza temple",
            "ssra",
            "ssraeshza",
        ],
    },
    {
        "zone_id": "sanctus_seru",
        "display_name": "Sanctus Seru",
        "aliases": ["sanctus seru", "seru"],
    },
]


def normalize_zone_key(s: str) -> str:
    """Match build_dkp_mob_loot / extract_raid_item_sources conventions."""
    if not s or not isinstance(s, str):
        return ""
    out = s.strip().lower()
    out = re.sub(r"^the\s+", "", out)
    out = out.replace("vex thall", "vex thal")
    # Collapse Ssra long-names for matching (display stays Temple of Ssraeshza).
    out = out.replace("ssraeshza", "ssra")
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _build_zone_alias_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for z in ZONE_DEFS:
        zone_id = z["zone_id"]
        for alias in z["aliases"]:
            mapping[normalize_zone_key(alias)] = zone_id
        mapping[normalize_zone_key(z["display_name"])] = zone_id
    # After ssraeshza→ssra collapse, long names become "temple of ssra" / "ssra temple".
    mapping[normalize_zone_key("temple of ssra")] = "temple_of_ssraeshza"
    mapping[normalize_zone_key("ssra temple")] = "temple_of_ssraeshza"
    return mapping


ZONE_ALIAS_TO_ID = _build_zone_alias_map()
ZONE_ID_TO_DEF = {z["zone_id"]: z for z in ZONE_DEFS}


def resolve_zone_id(zone: str) -> str | None:
    """Return allowlisted zone_id or None. Never infer from mob names."""
    key = normalize_zone_key(zone)
    if not key:
        return None
    return ZONE_ALIAS_TO_ID.get(key)


def normalize_mob(mob: str) -> str:
    if not mob or not isinstance(mob, str):
        return ""
    s = mob.strip()
    if s.startswith("#"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    s = s.replace("`", "'").strip()
    return s


def mob_key(mob: str) -> str:
    return normalize_mob(mob).lower().replace(" ", "_")


def target_id_for(mob: str, zone_id: str) -> str:
    return f"{mob_key(mob)}|{zone_id}"


def display_mob_name(mob: str) -> str:
    n = normalize_mob(mob)
    return n.replace("_", " ") if n else ""


def _first_existing(paths: list[Path]) -> Path | None:
    for p in paths:
        if p and p.is_file():
            return p
    return None


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_elemental_purchases(elemental_path: Path | None, slot_options_path: Path | None) -> dict[str, dict[str, Any]]:
    """
    Return purchase_id -> {name, slot, armor_type, class_wearables: {CLS: id}, provenance}.
    Prefer dkp_elemental_to_magelo.json; fall back to elemental_slot_options.json.
    """
    purchases: dict[str, dict[str, Any]] = {}
    if elemental_path and elemental_path.is_file():
        data = load_json(elemental_path)
        for pid, entry in (data.get("dkp_purchases") or {}).items():
            if not isinstance(entry, dict):
                continue
            by_class_raw = entry.get("magelo_item_ids_by_class") or {}
            by_class = {
                str(k).upper(): str(v).strip()
                for k, v in by_class_raw.items()
                if v is not None and str(v).strip()
            }
            purchases[str(pid)] = {
                "name": (entry.get("name") or "").strip(),
                "slot": (entry.get("slot") or "").strip(),
                "armor_type": (entry.get("armor_type") or "").strip(),
                "class_wearables": dict(sorted(by_class.items())),
                "provenance": "dkp_elemental_to_magelo",
            }
        return purchases

    if slot_options_path and slot_options_path.is_file():
        data = load_json(slot_options_path)
        for _slot_id, opts in (data.get("by_slot_id") or {}).items():
            if not isinstance(opts, list):
                continue
            for opt in opts:
                if not isinstance(opt, dict):
                    continue
                pid = str(opt.get("pattern_id") or "").strip()
                if not pid:
                    continue
                by_class_raw = opt.get("by_class") or {}
                by_class = {
                    str(k).upper(): str(v).strip()
                    for k, v in by_class_raw.items()
                    if v is not None and str(v).strip()
                }
                if pid not in purchases:
                    purchases[pid] = {
                        "name": (opt.get("pattern_name") or "").strip(),
                        "slot": "",
                        "armor_type": "",
                        "class_wearables": dict(sorted(by_class.items())),
                        "provenance": "elemental_slot_options",
                    }
                else:
                    # Merge class maps if the same pattern appears under multiple slot ids (wrists).
                    merged = dict(purchases[pid]["class_wearables"])
                    merged.update(by_class)
                    purchases[pid]["class_wearables"] = dict(sorted(merged.items()))
        return purchases

    return purchases


def _source_key(zone_id: str, mob: str) -> tuple[str, str]:
    return (zone_id, mob_key(mob))


def _merge_provenance(existing: list[str], extra: list[str] | str) -> list[str]:
    out = list(existing)
    extras = [extra] if isinstance(extra, str) else list(extra or [])
    for s in extras:
        if s and s not in out:
            out.append(s)
    out.sort()
    return out


def collect_sources(
    raid_sources: dict[str, Any],
    dkp_loot: dict[str, Any],
) -> tuple[
    dict[str, dict[str, Any]],
    list[dict[str, Any]],
    dict[str, set[str]],
]:
    """
    Build item_id -> item draft with sources.

    Returns (items_by_id, ambiguous_assignments, names_by_id).
    Only allowlisted zone sources are attached to items. Ambiguous/non-allowlisted
    assignments are reported, never used to invent a zone from an NPC name.
    """
    items: dict[str, dict[str, Any]] = {}
    ambiguous: list[dict[str, Any]] = []
    names_by_id: dict[str, set[str]] = defaultdict(set)

    def ensure_item(iid: str, name: str) -> dict[str, Any]:
        if iid not in items:
            items[iid] = {
                "item_id": iid,
                "name": name or "",
                "sources": {},  # source_key -> source dict
            }
        elif name and (not items[iid]["name"] or items[iid]["name"].startswith("(item ")):
            items[iid]["name"] = name
        if name:
            names_by_id[iid].add(name)
        return items[iid]

    def add_source(
        iid: str,
        name: str,
        mob: str,
        zone_raw: str,
        zone_id: str,
        provenance: list[str],
    ) -> None:
        item = ensure_item(iid, name)
        mob_n = normalize_mob(mob) or "(unknown)"
        sk = _source_key(zone_id, mob_n)
        existing = item["sources"].get(sk)
        if existing is None:
            item["sources"][sk] = {
                "zone_id": zone_id,
                "target_id": target_id_for(mob_n, zone_id),
                "mob": mob_n,
                "zone_raw": zone_raw,
                "provenance": sorted(set(provenance)),
            }
        else:
            existing["provenance"] = _merge_provenance(existing["provenance"], provenance)
            # Prefer a non-empty raw zone string that matches the allowlist display.
            if zone_raw and not existing.get("zone_raw"):
                existing["zone_raw"] = zone_raw

    # DKP loot: multi-source truth (already zone-split in NAGD-DKP).
    for _key, entry in (dkp_loot or {}).items():
        if not isinstance(entry, dict):
            continue
        zone_raw = (entry.get("zone") or "").strip()
        zone_id = resolve_zone_id(zone_raw)
        mob = (entry.get("mob") or "").strip()
        mobs = entry.get("mobs") or ([mob] if mob else [])
        primary_mob = mob or (mobs[0] if mobs else "")
        loot = entry.get("loot") or []
        for loot_item in loot:
            if not isinstance(loot_item, dict):
                continue
            raw_id = loot_item.get("item_id")
            name = (loot_item.get("name") or "").strip()
            src_tags = [str(s) for s in (loot_item.get("sources") or []) if s]
            if "dkp_mob_loot" not in src_tags:
                src_tags = _merge_provenance(src_tags, "dkp_mob_loot")

            if raw_id is None:
                ambiguous.append(
                    {
                        "reason": "null_item_id",
                        "name": name,
                        "mob": primary_mob,
                        "zone": zone_raw,
                        "provenance": src_tags,
                    }
                )
                continue
            try:
                iid = str(int(raw_id))
            except (TypeError, ValueError):
                ambiguous.append(
                    {
                        "reason": "invalid_item_id",
                        "item_id": raw_id,
                        "name": name,
                        "mob": primary_mob,
                        "zone": zone_raw,
                        "provenance": src_tags,
                    }
                )
                continue

            if zone_id is None:
                # Non-allowlist zones are out of scope (not ambiguous). Empty/unknown
                # zone strings cannot be assigned without guessing from the NPC name.
                if not zone_raw or normalize_zone_key(zone_raw) in {
                    "other / unknown",
                    "other",
                    "unknown",
                }:
                    ambiguous.append(
                        {
                            "reason": "empty_zone" if not zone_raw else "ambiguous_zone",
                            "item_id": iid,
                            "name": name,
                            "mob": primary_mob,
                            "zone": zone_raw,
                            "provenance": src_tags,
                        }
                    )
                continue

            # One source record per primary mob for this loot row (mobs[] are aliases
            # of the same encounter row, not distinct drop sources).
            add_source(iid, name, primary_mob, zone_raw, zone_id, src_tags)

            # Record alias mobs on the target later via targets builder.
            item = items[iid]
            src = item["sources"][_source_key(zone_id, primary_mob)]
            aliases = src.setdefault("mob_aliases", [])
            for m in mobs:
                mn = normalize_mob(m)
                if mn and mn not in aliases and mn != normalize_mob(primary_mob):
                    aliases.append(mn)
            aliases.sort(key=lambda s: (s.lower(), s))

    # Magelo raid_item_sources: single source per item; only attach if allowlisted.
    for item_id_str, entry in (raid_sources or {}).items():
        if not isinstance(entry, dict):
            continue
        try:
            iid = str(int(item_id_str))
        except (TypeError, ValueError):
            ambiguous.append(
                {
                    "reason": "invalid_item_id",
                    "item_id": item_id_str,
                    "name": (entry.get("name") or "").strip(),
                    "mob": (entry.get("mob") or "").strip(),
                    "zone": (entry.get("zone") or "").strip(),
                    "provenance": ["raid_item_sources"],
                }
            )
            continue
        name = (entry.get("name") or "").strip()
        mob = (entry.get("mob") or "").strip()
        zone_raw = (entry.get("zone") or "").strip()
        zone_id = resolve_zone_id(zone_raw)
        if zone_id is None:
            # Clear non-allowlist zones are out of scope. Only report when the zone
            # string is missing or explicitly unknown (never infer from mob name).
            if not zone_raw or normalize_zone_key(zone_raw) in {
                "other / unknown",
                "other",
                "unknown",
            }:
                ambiguous.append(
                    {
                        "reason": "empty_zone" if not zone_raw else "ambiguous_zone",
                        "item_id": iid,
                        "name": name,
                        "mob": mob,
                        "zone": zone_raw,
                        "provenance": ["raid_item_sources"],
                    }
                )
            continue
        if not mob:
            ambiguous.append(
                {
                    "reason": "empty_mob",
                    "item_id": iid,
                    "name": name,
                    "mob": mob,
                    "zone": zone_raw,
                    "provenance": ["raid_item_sources"],
                }
            )
            continue
        add_source(iid, name, mob, zone_raw, zone_id, ["raid_item_sources"])

    return items, ambiguous, names_by_id


def classify_item(
    iid: str,
    name: str,
    purchases: dict[str, dict[str, Any]],
    item_stats: dict[str, Any],
) -> dict[str, Any]:
    """Assign acquisition type and wearable/purchase ids without guessing armor from names."""
    stats_entry = item_stats.get(iid) if isinstance(item_stats, dict) else None
    stats_present = isinstance(stats_entry, dict)
    stats_name = (stats_entry.get("name") or "").strip() if stats_present else ""
    display_name = name or stats_name or f"Item {iid}"

    if iid in purchases:
        purchase = purchases[iid]
        class_wearables = purchase.get("class_wearables") or {}
        missing_class_stats = [
            cls for cls, wid in class_wearables.items() if wid not in item_stats
        ]
        if not class_wearables:
            return {
                "acquisition_type": "unresolved",
                "purchase_item_id": iid,
                "wearable_item_id": None,
                "class_wearables": {},
                "stats_present": stats_present,
                "name": display_name or purchase.get("name") or f"Item {iid}",
                "conversion_provenance": purchase.get("provenance"),
                "unresolved_reason": "armor_pattern_missing_class_mappings",
                "missing_class_stats": missing_class_stats,
            }
        return {
            "acquisition_type": "armor_pattern",
            "purchase_item_id": iid,
            "wearable_item_id": None,
            "class_wearables": class_wearables,
            "stats_present": stats_present,
            "name": display_name or purchase.get("name") or f"Item {iid}",
            "conversion_provenance": purchase.get("provenance"),
            "missing_class_stats": missing_class_stats,
        }

    # Known class wearable reverse-map (piece drops are rare; still mark if seen).
    # Only from verified purchase tables — do not invent.
    reverse: dict[str, tuple[str, str]] = {}
    for pid, purchase in purchases.items():
        for cls, wid in (purchase.get("class_wearables") or {}).items():
            reverse[str(wid)] = (pid, cls)

    if iid in reverse:
        pid, cls = reverse[iid]
        return {
            "acquisition_type": "direct_wearable",
            "purchase_item_id": pid,
            "wearable_item_id": iid,
            "class_wearables": {cls: iid},
            "stats_present": stats_present,
            "name": display_name,
            "conversion_provenance": purchases[pid].get("provenance"),
            "mapped_from_purchase_id": pid,
        }

    if stats_present:
        return {
            "acquisition_type": "direct_wearable",
            "purchase_item_id": iid,
            "wearable_item_id": iid,
            "class_wearables": None,
            "stats_present": True,
            "name": display_name,
            "conversion_provenance": None,
        }

    return {
        "acquisition_type": "unresolved",
        "purchase_item_id": iid,
        "wearable_item_id": None,
        "class_wearables": None,
        "stats_present": False,
        "name": display_name,
        "conversion_provenance": None,
        "unresolved_reason": "missing_item_stats",
    }


def build_targets(items: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    targets: dict[str, dict[str, Any]] = {}
    for item in items.values():
        for src in item["sources"].values():
            tid = src["target_id"]
            if tid not in targets:
                targets[tid] = {
                    "target_id": tid,
                    "zone_id": src["zone_id"],
                    "display_name": display_mob_name(src["mob"]),
                    "mob": src["mob"],
                    "mob_aliases": [],
                }
            alias_set = set(targets[tid]["mob_aliases"])
            for a in src.get("mob_aliases") or []:
                if a and a != targets[tid]["mob"]:
                    alias_set.add(a)
            targets[tid]["mob_aliases"] = sorted(alias_set, key=lambda s: (s.lower(), s))
    return sorted(targets.values(), key=lambda t: (t["zone_id"], t["mob"].lower(), t["target_id"]))


def build_catalog(
    raid_sources: dict[str, Any],
    dkp_loot: dict[str, Any],
    purchases: dict[str, dict[str, Any]],
    item_stats: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw_items, ambiguous, _names = collect_sources(raid_sources, dkp_loot)

    catalog_items: list[dict[str, Any]] = []
    unresolved_ids: list[str] = []
    missing_stats: list[dict[str, Any]] = []
    missing_armor_mappings: list[dict[str, Any]] = []
    counts_by_zone: dict[str, dict[str, int]] = {
        z["zone_id"]: {"targets": 0, "items": 0, "source_links": 0} for z in ZONE_DEFS
    }
    counts_by_target: dict[str, int] = defaultdict(int)
    acquisition_counts: dict[str, int] = defaultdict(int)

    for iid in sorted(raw_items.keys(), key=lambda x: int(x)):
        draft = raw_items[iid]
        if not draft["sources"]:
            continue
        classified = classify_item(iid, draft["name"], purchases, item_stats)
        sources_out = []
        for sk in sorted(draft["sources"].keys(), key=lambda k: (k[0], k[1])):
            src = draft["sources"][sk]
            sources_out.append(
                {
                    "zone_id": src["zone_id"],
                    "target_id": src["target_id"],
                    "mob": src["mob"],
                    "provenance": list(src["provenance"]),
                }
            )
            counts_by_zone[src["zone_id"]]["source_links"] += 1
            counts_by_target[src["target_id"]] += 1

        zone_ids = sorted({s["zone_id"] for s in sources_out})
        for zid in zone_ids:
            counts_by_zone[zid]["items"] += 1

        entry = {
            "item_id": iid,
            "name": classified["name"],
            "acquisition_type": classified["acquisition_type"],
            "purchase_item_id": classified["purchase_item_id"],
            "wearable_item_id": classified["wearable_item_id"],
            "class_wearables": classified["class_wearables"],
            "sources": sources_out,
            "stats_present": classified["stats_present"],
        }
        if classified.get("conversion_provenance"):
            entry["conversion_provenance"] = classified["conversion_provenance"]
        if classified.get("unresolved_reason"):
            entry["unresolved_reason"] = classified["unresolved_reason"]
        if classified.get("mapped_from_purchase_id"):
            entry["mapped_from_purchase_id"] = classified["mapped_from_purchase_id"]

        catalog_items.append(entry)
        acquisition_counts[classified["acquisition_type"]] += 1

        if classified["acquisition_type"] == "unresolved":
            unresolved_ids.append(iid)
        if not classified["stats_present"] and classified["acquisition_type"] != "armor_pattern":
            missing_stats.append({"item_id": iid, "name": classified["name"]})
        if classified["acquisition_type"] == "armor_pattern":
            missing_cls = classified.get("missing_class_stats") or []
            if missing_cls:
                missing_stats.append(
                    {
                        "item_id": iid,
                        "name": classified["name"],
                        "missing_class_wearable_stats": missing_cls,
                    }
                )
        if classified.get("unresolved_reason") == "armor_pattern_missing_class_mappings":
            missing_armor_mappings.append({"item_id": iid, "name": classified["name"]})

    # Patterns present in purchases but never seen as loot in allowlisted zones.
    seen_purchase_ids = {
        e["item_id"]
        for e in catalog_items
        if e["acquisition_type"] == "armor_pattern"
    }
    for pid, purchase in sorted(purchases.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
        if pid not in seen_purchase_ids:
            # Not an error — may drop outside the six zones — note only if referenced nowhere.
            pass

    targets = build_targets(raw_items)
    for t in targets:
        counts_by_zone[t["zone_id"]]["targets"] += 1

    # Compact: drop empty class_wearables null distinction already set.
    catalog = {
        "version": CATALOG_VERSION,
        "zones": [
            {
                "zone_id": z["zone_id"],
                "display_name": z["display_name"],
                "aliases": list(z["aliases"]),
            }
            for z in ZONE_DEFS
        ],
        "targets": targets,
        "items": catalog_items,
    }

    armor_patterns = [e for e in catalog_items if e["acquisition_type"] == "armor_pattern"]
    armor_with_full_maps = [
        e
        for e in armor_patterns
        if e.get("class_wearables")
        and not any(
            (m.get("item_id") == e["item_id"] and m.get("missing_class_wearable_stats"))
            for m in missing_stats
        )
    ]

    coverage = {
        "version": CATALOG_VERSION,
        "counts_by_zone": {
            zid: dict(sorted(vals.items())) for zid, vals in sorted(counts_by_zone.items())
        },
        "counts_by_target": {
            tid: counts_by_target[tid]
            for tid in sorted(counts_by_target.keys())
        },
        "acquisition_counts": dict(sorted(acquisition_counts.items())),
        "item_count": len(catalog_items),
        "target_count": len(targets),
        "unresolved_ids": unresolved_ids,
        "missing_stats": sorted(missing_stats, key=lambda x: int(x["item_id"])),
        "missing_armor_mappings": missing_armor_mappings,
        "ambiguous_source_assignments": sorted(
            ambiguous,
            key=lambda a: (
                a.get("reason") or "",
                str(a.get("item_id") or ""),
                a.get("zone") or "",
                a.get("mob") or "",
                a.get("name") or "",
            ),
        ),
        "armor_mapping_coverage": {
            "purchase_ids_in_elemental_table": len(purchases),
            "armor_pattern_items_in_catalog": len(armor_patterns),
            "armor_patterns_with_class_maps": sum(
                1 for e in armor_patterns if e.get("class_wearables")
            ),
            "armor_patterns_with_complete_wearable_stats": len(armor_with_full_maps),
        },
        "input_notes": [],
    }
    return catalog, coverage


def dump_stable_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False)
    # Trailing newline for stable diffs / POSIX friendliness.
    path.write_text(text + "\n", encoding="utf-8")


def validate_catalog_schema(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if catalog.get("version") != CATALOG_VERSION:
        errors.append(f"version != {CATALOG_VERSION}")
    zone_ids = [z.get("zone_id") for z in catalog.get("zones") or []]
    expected = [z["zone_id"] for z in ZONE_DEFS]
    if zone_ids != expected:
        errors.append(f"zones mismatch: got {zone_ids}")
    for item in catalog.get("items") or []:
        if not item.get("item_id"):
            errors.append("item missing item_id")
            continue
        if item.get("acquisition_type") not in {
            "direct_wearable",
            "armor_pattern",
            "unresolved",
        }:
            errors.append(f"item {item.get('item_id')}: bad acquisition_type")
        if not item.get("sources"):
            errors.append(f"item {item.get('item_id')}: no sources")
        for src in item.get("sources") or []:
            if src.get("zone_id") not in expected:
                errors.append(
                    f"item {item.get('item_id')}: source zone_id {src.get('zone_id')} not allowlisted"
                )
    return errors


def resolve_input_paths(args: argparse.Namespace) -> dict[str, Path | None]:
    dkp_loot = args.dkp_loot
    if dkp_loot is None:
        dkp_loot = _first_existing(DEFAULT_DKP_LOOT_CANDIDATES)
    elif not dkp_loot.is_absolute():
        dkp_loot = (REPO_ROOT / dkp_loot).resolve()

    elemental = args.elemental
    if elemental is None:
        elemental = _first_existing(DEFAULT_ELEMENTAL_CANDIDATES)
    elif not elemental.is_absolute():
        elemental = (REPO_ROOT / elemental).resolve()

    raid = args.raid_sources
    if not raid.is_absolute():
        raid = (REPO_ROOT / raid).resolve()
    item_stats = args.item_stats
    if not item_stats.is_absolute():
        item_stats = (REPO_ROOT / item_stats).resolve()
    slot_options = args.elemental_slot_options
    if not slot_options.is_absolute():
        slot_options = (REPO_ROOT / slot_options).resolve()

    return {
        "raid_sources": raid,
        "dkp_loot": dkp_loot,
        "elemental": elemental,
        "item_stats": item_stats,
        "elemental_slot_options": slot_options,
    }


def run_build(paths: dict[str, Path | None]) -> tuple[dict[str, Any], dict[str, Any]]:
    raid_path = paths["raid_sources"]
    stats_path = paths["item_stats"]
    if not raid_path or not raid_path.is_file():
        raise FileNotFoundError(f"raid_item_sources not found: {raid_path}")
    if not stats_path or not stats_path.is_file():
        raise FileNotFoundError(f"item_stats not found: {stats_path}")

    raid_sources = load_json(raid_path)
    item_stats = load_json(stats_path)
    dkp_loot: dict[str, Any] = {}
    if paths["dkp_loot"] and paths["dkp_loot"].is_file():
        dkp_loot = load_json(paths["dkp_loot"])
    else:
        dkp_loot = {}

    purchases = load_elemental_purchases(paths["elemental"], paths["elemental_slot_options"])
    catalog, coverage = build_catalog(raid_sources, dkp_loot, purchases, item_stats)

    notes: list[str] = []
    notes.append(f"raid_sources={raid_path}")
    notes.append(f"item_stats={stats_path}")
    if paths["dkp_loot"] and paths["dkp_loot"].is_file():
        notes.append(f"dkp_loot={paths['dkp_loot']}")
    else:
        notes.append("dkp_loot=MISSING (catalog built from raid_item_sources only)")
    if paths["elemental"] and paths["elemental"].is_file():
        notes.append(f"elemental={paths['elemental']}")
    elif paths["elemental_slot_options"] and paths["elemental_slot_options"].is_file():
        notes.append(f"elemental=fallback:{paths['elemental_slot_options']}")
    else:
        notes.append("elemental=MISSING (no armor_pattern class maps)")
    coverage["input_notes"] = notes
    return catalog, coverage


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build raid upgrade catalog (six zones).")
    parser.add_argument("--raid-sources", type=Path, default=DEFAULT_RAID_SOURCES)
    parser.add_argument(
        "--dkp-loot",
        type=Path,
        default=None,
        help="Path to dkp_mob_loot.json (default: sibling dkp/data, then magelo root)",
    )
    parser.add_argument(
        "--elemental",
        type=Path,
        default=None,
        help="Path to dkp_elemental_to_magelo.json",
    )
    parser.add_argument(
        "--elemental-slot-options",
        type=Path,
        default=DEFAULT_ELEMENTAL_SLOT_OPTIONS,
        help="Fallback class maps when --elemental is missing",
    )
    parser.add_argument("--item-stats", type=Path, default=DEFAULT_ITEM_STATS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--coverage-output", type=Path, default=DEFAULT_COVERAGE_OUT)
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Rebuild and verify existing --output matches (and schema is valid)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build in memory and print summary without writing",
    )
    args = parser.parse_args(argv)

    paths = resolve_input_paths(args)
    try:
        catalog, coverage = run_build(paths)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    schema_errors = validate_catalog_schema(catalog)
    if schema_errors:
        print("Schema errors:", file=sys.stderr)
        for e in schema_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    out_path = args.output if args.output.is_absolute() else (REPO_ROOT / args.output)
    cov_path = (
        args.coverage_output
        if args.coverage_output.is_absolute()
        else (REPO_ROOT / args.coverage_output)
    )

    if args.validate:
        if not out_path.is_file():
            print(f"Error: catalog missing for validate: {out_path}", file=sys.stderr)
            return 1
        existing = load_json(out_path)
        existing_errors = validate_catalog_schema(existing)
        if existing_errors:
            print("Existing catalog schema errors:", file=sys.stderr)
            for e in existing_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1
        # Compare without relying on coverage file.
        if existing != catalog:
            print(
                "Validation failed: rebuilt catalog differs from committed file.",
                file=sys.stderr,
            )
            print(
                f"  items existing={len(existing.get('items') or [])} "
                f"rebuilt={len(catalog.get('items') or [])}",
                file=sys.stderr,
            )
            print(
                f"  targets existing={len(existing.get('targets') or [])} "
                f"rebuilt={len(catalog.get('targets') or [])}",
                file=sys.stderr,
            )
            return 1
        print(f"✓ Validated {out_path} (idempotent rebuild matches)")
        print(
            f"  items={coverage['item_count']} targets={coverage['target_count']} "
            f"unresolved={len(coverage['unresolved_ids'])}"
        )
        return 0

    if not args.dry_run:
        dump_stable_json(out_path, catalog)
        dump_stable_json(cov_path, coverage)
        print(f"Wrote {out_path}")
        print(f"Wrote {cov_path}")

    print(
        f"Catalog: {coverage['item_count']} items, {coverage['target_count']} targets"
    )
    for z in ZONE_DEFS:
        zid = z["zone_id"]
        c = coverage["counts_by_zone"][zid]
        print(
            f"  {z['display_name']}: {c['targets']} targets, "
            f"{c['items']} items, {c['source_links']} source links"
        )
    print(f"Acquisition: {coverage['acquisition_counts']}")
    print(
        f"Unresolved: {len(coverage['unresolved_ids'])}; "
        f"missing_stats: {len(coverage['missing_stats'])}; "
        f"ambiguous: {len(coverage['ambiguous_source_assignments'])}"
    )
    print(f"Armor mapping: {coverage['armor_mapping_coverage']}")
    for note in coverage["input_notes"]:
        print(f"  input: {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
