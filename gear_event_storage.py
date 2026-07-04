#!/usr/bin/env python3
"""
Append-only gear and character stat event log.

Stores dated +/- inventory events and stat deltas derived from true day-over-day
Magelo dump diffs (never baseline-vs-current), enabling smaller storage and
item acquisition timelines without cumulative daily JSON growth.
"""

from __future__ import annotations

import gzip
import json
import os
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

GEAR_EVENTS_DIR = "gear_events"
GEAR_SHARD_RE = re.compile(r"^gear_(\d{4}-\d{2})\.json\.gz$")
CHAR_SHARD_RE = re.compile(r"^char_(\d{4}-\d{2})\.json\.gz$")
MANIFEST_FILE = "manifest.json"


def _month_key(date_str: str) -> str:
    return date_str[:7]


def _events_dir(base_dir: str) -> str:
    return os.path.join(base_dir, GEAR_EVENTS_DIR)


def _gear_shard_path(base_dir: str, month: str) -> str:
    return os.path.join(_events_dir(base_dir), f"gear_{month}.json.gz")


def _char_shard_path(base_dir: str, month: str) -> str:
    return os.path.join(_events_dir(base_dir), f"char_{month}.json.gz")


def _manifest_path(base_dir: str) -> str:
    return os.path.join(_events_dir(base_dir), MANIFEST_FILE)


def inv_deltas_to_gear_events(
    inv_deltas: dict,
    date_str: str,
    baseline_date: str | None = None,
) -> list[dict]:
    """Convert compare_inventories / compare_delta_to_delta inv_deltas to event rows."""
    events: list[dict] = []
    for char_name, row in (inv_deltas or {}).items():
        visibility = 1 if row.get("is_visibility_change") else 0
        for item_id, count in (row.get("added") or {}).items():
            n = int(count or 0)
            if n <= 0:
                continue
            ev: dict[str, Any] = {
                "d": date_str,
                "c": char_name,
                "i": str(item_id),
                "s": 1,
                "n": n,
                "v": visibility,
            }
            if baseline_date:
                ev["b"] = baseline_date
            events.append(ev)
        for item_id, count in (row.get("removed") or {}).items():
            n = int(count or 0)
            if n <= 0:
                continue
            ev = {
                "d": date_str,
                "c": char_name,
                "i": str(item_id),
                "s": -1,
                "n": n,
                "v": visibility,
            }
            if baseline_date:
                ev["b"] = baseline_date
            events.append(ev)
    return events


def _attach_char_snapshot_fields(ev: dict[str, Any], row: dict) -> None:
    """Attach end-of-day absolutes and previous_* for leaderboard folding (optional on events)."""
    if row.get("is_deleted"):
        return
    if row.get("current_level") is not None:
        ev["lv"] = int(row.get("current_level") or 0)
    if row.get("current_aa_total") is not None:
        ev["aa"] = int(row.get("current_aa_total") or 0)
    if row.get("current_hp") is not None:
        ev["hp"] = int(row.get("current_hp") or 0)
    if row.get("previous_level") is not None:
        ev["plv"] = int(row.get("previous_level") or 0)
    if row.get("previous_aa_total") is not None:
        ev["paa"] = int(row.get("previous_aa_total") or 0)
    if row.get("previous_hp") is not None:
        ev["php"] = int(row.get("previous_hp") or 0)


def char_deltas_to_stat_events(
    char_deltas: dict,
    date_str: str,
    baseline_date: str | None = None,
) -> list[dict]:
    """Convert compare_character_data / compare_delta_to_delta char_deltas to event rows."""
    events: list[dict] = []
    for char_name, row in (char_deltas or {}).items():
        for field_key, field_name in (
            ("level_change", "lvl"),
            ("aa_total_change", "aa"),
            ("hp_change", "hp"),
        ):
            n = int(row.get(field_key) or 0)
            if n == 0:
                continue
            ev: dict[str, Any] = {
                "d": date_str,
                "c": char_name,
                "f": field_name,
                "n": n,
            }
            if baseline_date:
                ev["b"] = baseline_date
            if row.get("class"):
                ev["cl"] = row["class"]
            if row.get("is_new"):
                ev["new"] = 1
            if row.get("is_deleted"):
                ev["del"] = 1
            if row.get("is_visibility_change"):
                ev["v"] = 1
            _attach_char_snapshot_fields(ev, row)
            events.append(ev)
        if row.get("is_new") and not any(
            int(row.get(k) or 0) != 0 for k in ("level_change", "aa_total_change", "hp_change")
        ):
            ev = {"d": date_str, "c": char_name, "f": "new", "n": 1}
            if baseline_date:
                ev["b"] = baseline_date
            if row.get("class"):
                ev["cl"] = row["class"]
            if row.get("is_visibility_change"):
                ev["v"] = 1
            _attach_char_snapshot_fields(ev, row)
            events.append(ev)
        if row.get("is_deleted") and not any(
            int(row.get(k) or 0) != 0 for k in ("level_change", "aa_total_change", "hp_change")
        ):
            ev = {"d": date_str, "c": char_name, "f": "del", "n": 1}
            if baseline_date:
                ev["b"] = baseline_date
            if row.get("is_visibility_change"):
                ev["v"] = 1
            events.append(ev)
    return events


def delta_shape_to_events(
    char_deltas: dict,
    inv_deltas: dict,
    date_str: str,
    baseline_date: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Split a day-over-day delta dict into gear and char event lists."""
    return (
        inv_deltas_to_gear_events(inv_deltas, date_str, baseline_date),
        char_deltas_to_stat_events(char_deltas, date_str, baseline_date),
    )


def append_day_events_from_deltas(
    char_deltas: dict,
    inv_deltas: dict,
    date_str: str,
    base_dir: str = "delta_snapshots",
    baseline_date: str | None = None,
) -> tuple[int, int]:
    """Append gear/stat events for one calendar day from precomputed day-over-day deltas."""
    gear_events, char_events = delta_shape_to_events(
        char_deltas, inv_deltas, date_str, baseline_date
    )
    _append_shard_events(base_dir, date_str, gear_events, char_events)
    _update_manifest(base_dir, date_str, baseline_date, len(gear_events), len(char_events))
    return len(gear_events), len(char_events)


def append_day_events(
    previous_char_data: dict,
    previous_inv_data: dict,
    current_char_data: dict,
    current_inv_data: dict,
    date_str: str,
    base_dir: str = "delta_snapshots",
    baseline_date: str | None = None,
    exclude_corpse_loot: bool = True,
) -> tuple[int, int]:
    """Diff consecutive Magelo dumps and append events for ``date_str`` (the current day)."""
    from generate_spell_page import (
        chars_corpse_loot_excluded,
        compare_character_data,
        compare_inventories,
    )

    char_deltas = compare_character_data(current_char_data, previous_char_data, None)
    inv_deltas = compare_inventories(current_inv_data, previous_inv_data, None)
    if exclude_corpse_loot:
        for char_name in chars_corpse_loot_excluded(current_inv_data, previous_inv_data):
            char_deltas.pop(char_name, None)
            inv_deltas.pop(char_name, None)
    return append_day_events_from_deltas(
        char_deltas, inv_deltas, date_str, base_dir, baseline_date
    )


def _load_shard_gz(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    return data.get("events") or []


def _save_shard_gz(path: str, events: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(events, f, separators=(",", ":"))


def _append_shard_events(
    base_dir: str,
    date_str: str,
    gear_events: list[dict],
    char_events: list[dict],
) -> None:
    month = _month_key(date_str)
    gear_path = _gear_shard_path(base_dir, month)
    char_path = _char_shard_path(base_dir, month)

    existing_gear = _load_shard_gz(gear_path)
    existing_char = _load_shard_gz(char_path)
    existing_gear = [e for e in existing_gear if e.get("d") != date_str]
    existing_char = [e for e in existing_char if e.get("d") != date_str]
    existing_gear.extend(gear_events)
    existing_char.extend(char_events)
    existing_gear.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("i", "")))
    existing_char.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("f", "")))

    _save_shard_gz(gear_path, existing_gear)
    _save_shard_gz(char_path, existing_char)


def _update_manifest(
    base_dir: str,
    date_str: str,
    baseline_date: str | None,
    gear_count: int,
    char_count: int,
) -> None:
    path = _manifest_path(base_dir)
    manifest: dict = {"version": 1, "days": {}, "eras": []}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    manifest.setdefault("version", 1)
    manifest.setdefault("days", {})
    manifest.setdefault("eras", [])
    manifest["days"][date_str] = {
        "gear": gear_count,
        "char": char_count,
        "baseline_date": baseline_date,
        "updated": datetime.now().isoformat(),
    }
    if baseline_date:
        eras = manifest["eras"]
        if not eras or eras[-1].get("baseline_date") != baseline_date:
            eras.append(
                {
                    "baseline_date": baseline_date,
                    "first_event": date_str,
                    "last_event": date_str,
                }
            )
        else:
            eras[-1]["last_event"] = date_str
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def _iter_months_between(start_date: str | None, end_date: str | None) -> list[str]:
    if not start_date and not end_date:
        events_root = ""
        return []
    if start_date and end_date:
        start_m = _month_key(start_date)
        end_m = _month_key(end_date)
    elif start_date:
        start_m = end_m = _month_key(start_date)
    else:
        start_m = end_m = _month_key(end_date or "")
    months = []
    y, m = int(start_m[:4]), int(start_m[5:7])
    ey, em = int(end_m[:4]), int(end_m[5:7])
    while (y, m) <= (ey, em):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def _list_all_shard_months(base_dir: str, shard_re: re.Pattern[str]) -> list[str]:
    root = _events_dir(base_dir)
    if not os.path.isdir(root):
        return []
    months = []
    for name in os.listdir(root):
        m = shard_re.match(name)
        if m:
            months.append(m.group(1))
    return sorted(months)


def load_gear_events(
    base_dir: str = "delta_snapshots",
    start_date: str | None = None,
    end_date: str | None = None,
    exclusive_start: bool = False,
    inclusive_end: bool = True,
) -> list[dict]:
    """Load gear events, optionally filtered to a date range."""
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    if start_date or end_date:
        months = _iter_months_between(start_date, end_date)
    else:
        months = _list_all_shard_months(base_dir, GEAR_SHARD_RE)

    out: list[dict] = []
    for month in months:
        for ev in _load_shard_gz(_gear_shard_path(base_dir, month)):
            d = ev.get("d", "")
            if start_date:
                if exclusive_start and d <= start_date:
                    continue
                if not exclusive_start and d < start_date:
                    continue
            if end_date and ((d > end_date) if inclusive_end else (d >= end_date)):
                continue
            out.append(ev)
    return out


def load_char_events(
    base_dir: str = "delta_snapshots",
    start_date: str | None = None,
    end_date: str | None = None,
    exclusive_start: bool = False,
    inclusive_end: bool = True,
) -> list[dict]:
    """Load character stat events, optionally filtered to a date range."""
    if start_date and end_date and start_date > end_date:
        start_date, end_date = end_date, start_date

    if start_date or end_date:
        months = _iter_months_between(start_date, end_date)
    else:
        months = _list_all_shard_months(base_dir, CHAR_SHARD_RE)

    out: list[dict] = []
    for month in months:
        for ev in _load_shard_gz(_char_shard_path(base_dir, month)):
            d = ev.get("d", "")
            if start_date:
                if exclusive_start and d <= start_date:
                    continue
                if not exclusive_start and d < start_date:
                    continue
            if end_date and ((d > end_date) if inclusive_end else (d >= end_date)):
                continue
            out.append(ev)
    return out


def list_available_event_dates(base_dir: str = "delta_snapshots") -> list[str]:
    """Dates with at least one gear event row (from manifest or shards)."""
    manifest_path = _manifest_path(base_dir)
    if os.path.exists(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        days = manifest.get("days") or {}
        if days:
            return sorted(days.keys())
    dates: set[str] = set()
    for month in _list_all_shard_months(base_dir, GEAR_SHARD_RE):
        for ev in _load_shard_gz(_gear_shard_path(base_dir, month)):
            if ev.get("d"):
                dates.add(ev["d"])
    for month in _list_all_shard_months(base_dir, CHAR_SHARD_RE):
        for ev in _load_shard_gz(_char_shard_path(base_dir, month)):
            if ev.get("d"):
                dates.add(ev["d"])
    return sorted(dates)


def gear_events_to_inv_deltas(
    gear_events: list[dict],
    item_names: dict | None = None,
    *,
    net_per_item: bool = True,
) -> dict:
    """Fold gear events into legacy inv_deltas shape."""
    inv_deltas: dict[str, dict] = {}
    names = item_names or {}
    for ev in gear_events:
        char_name = ev.get("c", "")
        item_id = str(ev.get("i", ""))
        if not char_name or not item_id:
            continue
        sign = int(ev.get("s") or 0)
        n = int(ev.get("n") or 0)
        if n <= 0 or sign not in (1, -1):
            continue
        row = inv_deltas.setdefault(
            char_name,
            {"added": {}, "removed": {}, "item_names": {}, "is_visibility_change": False},
        )
        if ev.get("v"):
            row["is_visibility_change"] = True
        bucket = row["added"] if sign > 0 else row["removed"]
        bucket[item_id] = bucket.get(item_id, 0) + n
        if item_id in names:
            row["item_names"][item_id] = names[item_id]

    if net_per_item:
        for row in inv_deltas.values():
            added = row.get("added") or {}
            removed = row.get("removed") or {}
            for item_id in list(added.keys()):
                if item_id not in removed:
                    continue
                a = added[item_id]
                r = removed[item_id]
                if a > r:
                    added[item_id] = a - r
                    del removed[item_id]
                elif r > a:
                    removed[item_id] = r - a
                    del added[item_id]
                else:
                    del added[item_id]
                    del removed[item_id]
    return inv_deltas


def _apply_char_snapshot_from_event(row: dict, ev: dict) -> None:
    """Update current_* from latest event; previous_* from first event with snapshots."""
    if ev.get("lv") is not None:
        row["current_level"] = int(ev["lv"])
    if ev.get("aa") is not None:
        row["current_aa_total"] = int(ev["aa"])
    if ev.get("hp") is not None:
        row["current_hp"] = int(ev["hp"])
    if not row.get("_has_prev_snap"):
        if ev.get("plv") is not None:
            row["previous_level"] = int(ev["plv"])
        if ev.get("paa") is not None:
            row["previous_aa_total"] = int(ev["paa"])
        if ev.get("php") is not None:
            row["previous_hp"] = int(ev["php"])
        if ev.get("plv") is not None or ev.get("paa") is not None or ev.get("php") is not None:
            row["_has_prev_snap"] = True


def char_events_to_char_deltas(char_events: list[dict]) -> dict:
    """Fold char stat events into legacy char_deltas shape."""
    char_deltas: dict[str, dict] = {}
    sorted_events = sorted(char_events, key=lambda e: (e.get("d") or "", e.get("c") or ""))
    for ev in sorted_events:
        char_name = ev.get("c", "")
        if not char_name:
            continue
        field = ev.get("f", "")
        n = int(ev.get("n") or 0)
        row = char_deltas.setdefault(
            char_name,
            {
                "name": char_name,
                "level_change": 0,
                "aa_total_change": 0,
                "hp_change": 0,
                "current_level": 0,
                "previous_level": 0,
                "current_aa_total": 0,
                "previous_aa_total": 0,
                "current_hp": 0,
                "previous_hp": 0,
                "class": "",
                "is_new": False,
                "is_deleted": False,
                "is_visibility_change": False,
            },
        )
        if ev.get("cl"):
            row["class"] = ev["cl"]
        if ev.get("v"):
            row["is_visibility_change"] = True
        if field == "lvl":
            row["level_change"] += n
        elif field == "aa":
            row["aa_total_change"] += n
        elif field == "hp":
            row["hp_change"] += n
        elif field == "new":
            row["is_new"] = True
        elif field == "del":
            row["is_deleted"] = True
        _apply_char_snapshot_from_event(row, ev)
    for row in char_deltas.values():
        row.pop("_has_prev_snap", None)
    char_deltas = {k: v for k, v in char_deltas.items() if _char_row_has_signal(v)}
    return char_deltas


def _char_row_has_signal(row: dict) -> bool:
    return bool(
        row.get("level_change")
        or row.get("aa_total_change")
        or row.get("hp_change")
        or row.get("is_new")
        or row.get("is_deleted")
    )


def events_to_delta_shape(
    gear_events: list[dict] | None = None,
    char_events: list[dict] | None = None,
    item_names: dict | None = None,
) -> dict:
    """Convert event lists to {char_deltas, inv_deltas} for HTML generators."""
    return {
        "char_deltas": char_events_to_char_deltas(char_events or []),
        "inv_deltas": gear_events_to_inv_deltas(gear_events or [], item_names),
    }


def get_day_delta_from_events(
    date_str: str,
    base_dir: str = "delta_snapshots",
    item_names: dict | None = None,
) -> dict:
    """Day-over-day delta for a single calendar date."""
    gear = load_gear_events(base_dir, start_date=date_str, end_date=date_str)
    char = load_char_events(base_dir, start_date=date_str, end_date=date_str)
    result = events_to_delta_shape(gear, char, item_names)
    result["date"] = date_str
    return result


def get_range_delta_from_events(
    start_date: str,
    end_date: str,
    base_dir: str = "delta_snapshots",
    item_names: dict | None = None,
) -> dict:
    """Range delta matching get_date_range_deltas semantics (exclusive start, inclusive end)."""
    if start_date == end_date:
        return {
            "char_deltas": {},
            "inv_deltas": {},
            "start_date": start_date,
            "end_date": end_date,
        }
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    gear = load_gear_events(
        base_dir, start_date=start_date, end_date=end_date, exclusive_start=True
    )
    char = load_char_events(
        base_dir, start_date=start_date, end_date=end_date, exclusive_start=True
    )
    result = events_to_delta_shape(gear, char, item_names)
    result["start_date"] = start_date
    result["end_date"] = end_date
    return result


def item_history(
    item_id: str,
    base_dir: str = "delta_snapshots",
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Timeline of +/- events for one item across all characters."""
    item_id = str(item_id)
    events = load_gear_events(base_dir, start_date, end_date)
    return [ev for ev in events if str(ev.get("i")) == item_id]


def char_item_history(
    char_name: str,
    item_id: str,
    base_dir: str = "delta_snapshots",
) -> list[dict]:
    """Timeline for one character + item pair."""
    item_id = str(item_id)
    return [
        ev
        for ev in load_gear_events(base_dir)
        if ev.get("c") == char_name and str(ev.get("i")) == item_id
    ]


def detect_oscillations(
    history: list[dict],
    window_days: int = 7,
) -> list[dict]:
    """Flag +/-/+ or -/+/- patterns within window_days."""
    if len(history) < 3:
        return []
    sorted_hist = sorted(history, key=lambda e: e.get("d", ""))
    flags = []
    for i in range(2, len(sorted_hist)):
        a, b, c = sorted_hist[i - 2], sorted_hist[i - 1], sorted_hist[i]
        if a.get("c") != b.get("c") or b.get("c") != c.get("c"):
            continue
        if str(a.get("i")) != str(b.get("i")) or str(b.get("i")) != str(c.get("i")):
            continue
        sa, sb, sc = int(a.get("s") or 0), int(b.get("s") or 0), int(c.get("s") or 0)
        if sa == sc and sa != sb:
            try:
                d0 = datetime.strptime(a["d"], "%Y-%m-%d")
                d2 = datetime.strptime(c["d"], "%Y-%m-%d")
                if (d2 - d0).days <= window_days:
                    flags.append(
                        {
                            "char": a.get("c"),
                            "item_id": str(a.get("i")),
                            "pattern": [sa, sb, sc],
                            "dates": [a.get("d"), b.get("d"), c.get("d")],
                        }
                    )
            except (ValueError, KeyError):
                pass
    return flags


def gear_events_available(base_dir: str = "delta_snapshots") -> bool:
    """True if at least one gear event shard exists."""
    root = _events_dir(base_dir)
    if not os.path.isdir(root):
        return False
    for name in os.listdir(root):
        if GEAR_SHARD_RE.match(name):
            return True
    return False


def populate_item_names_for_inv_deltas(
    inv_deltas: dict,
    current_inv_data: dict | None = None,
) -> None:
    """Fill item_names in inv_deltas from inventory rows, item_name_to_id, item_stats, praesterium."""
    all_ids: set[str] = set()
    for row in (inv_deltas or {}).values():
        all_ids.update((row.get("added") or {}).keys())
        all_ids.update((row.get("removed") or {}).keys())
    name_map: dict[str, str] = {}
    if current_inv_data:
        for items in current_inv_data.values():
            for item in items:
                iid = str(item.get("item_id", ""))
                if iid in all_ids:
                    name_map[iid] = item.get("item_name", "")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if len(name_map) < len(all_ids):
        path = os.path.join(base_dir, "data", "item_name_to_id.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    id_to_name = {str(v): k for k, v in json.load(f).items()}
                for iid in all_ids:
                    if iid not in name_map and iid in id_to_name:
                        name_map[iid] = id_to_name[iid]
            except (json.JSONDecodeError, OSError):
                pass
    if len(name_map) < len(all_ids):
        stats_path = os.path.join(base_dir, "data", "item_stats.json")
        if os.path.exists(stats_path):
            try:
                with open(stats_path, "r", encoding="utf-8") as f:
                    stats = json.load(f)
                for iid in all_ids:
                    if iid in name_map:
                        continue
                    entry = stats.get(iid) or stats.get(str(iid))
                    if isinstance(entry, dict) and entry.get("name"):
                        name_map[iid] = entry["name"]
            except (json.JSONDecodeError, OSError):
                pass
    if len(name_map) < len(all_ids):
        pr_path = os.path.join(base_dir, "praesterium_loot.json")
        if os.path.exists(pr_path):
            try:
                with open(pr_path, "r", encoding="utf-8") as f:
                    for sid, entry in json.load(f).items():
                        sid = str(sid)
                        if sid in all_ids and sid not in name_map:
                            if isinstance(entry, dict) and entry.get("name"):
                                name_map[sid] = entry["name"]
            except (json.JSONDecodeError, OSError):
                pass
    for row in inv_deltas.values():
        inames = row.setdefault("item_names", {})
        for iid in all_ids:
            if iid in name_map:
                inames[iid] = name_map[iid]
