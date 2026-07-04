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
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

GEAR_EVENTS_DIR = "gear_events"
GEAR_SHARD_RE = re.compile(r"^gear_(\d{4}-\d{2})\.json\.gz$")
CHAR_SHARD_RE = re.compile(r"^char_(\d{4}-\d{2})\.json\.gz$")
MANIFEST_FILE = "manifest.json"

# Match scripts/audit_gear_events.py default anomaly threshold.
DEFAULT_EVENT_INFLATION_MEDIAN_FACTOR = 5.0


class GearEventInflationError(RuntimeError):
    """Raised when a day-over-day delta would write far more events than recent history."""


def manifest_median_day_total(
    base_dir: str,
    date_str: str,
    *,
    window: int = 14,
    min_samples: int = 7,
) -> float | None:
    """Median gear+char event count for manifest days strictly before ``date_str``."""
    path = _manifest_path(base_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    days_meta = manifest.get("days") or {}
    totals: list[int] = []
    for d in sorted(days_meta.keys()):
        if d >= date_str:
            continue
        meta = days_meta[d] or {}
        totals.append(int(meta.get("gear") or 0) + int(meta.get("char") or 0))
    recent = totals[-window:]
    if len(recent) < min_samples:
        return None
    return float(statistics.median(recent))


def _manifest_day_total(base_dir: str, date_str: str) -> int | None:
    path = _manifest_path(base_dir)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    meta = (manifest.get("days") or {}).get(date_str) or {}
    if not meta:
        return None
    return int(meta.get("gear") or 0) + int(meta.get("char") or 0)


def guard_gear_event_write(
    char_deltas: dict,
    inv_deltas: dict,
    date_str: str,
    base_dir: str,
    baseline_date: str | None = None,
    *,
    median_factor: float = DEFAULT_EVENT_INFLATION_MEDIAN_FACTOR,
    min_excess: int = 2000,
) -> None:
    """Refuse writes that look like stale-cache / wrong-era dump inflation."""
    gear_events, char_events = delta_shape_to_events(
        char_deltas, inv_deltas, date_str, baseline_date
    )
    total = len(gear_events) + len(char_events)
    existing = _manifest_day_total(base_dir, date_str)
    if existing and existing > 0:
        if total > existing * median_factor and total > existing + min_excess:
            raise GearEventInflationError(
                f"Refusing gear-event rewrite for {date_str}: estimated {total} events "
                f"vs existing manifest {existing} ({total / existing:.1f}x). "
                "Keeping prior shard; check Magelo _previous cache alignment."
            )
    med = manifest_median_day_total(base_dir, date_str)
    if med is None or med <= 0:
        return
    if total > med * median_factor and total > med + min_excess:
        raise GearEventInflationError(
            f"Refusing gear-event write for {date_str}: estimated {total} events "
            f"vs recent manifest median {med:.0f} ({total / med:.1f}x). "
            "Check Magelo _previous cache alignment or dump date span."
        )


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
    unique_tracked_ids: set[str] | None = None,
) -> tuple[int, int]:
    """Append gear/stat events for one calendar day from precomputed day-over-day deltas."""
    try:
        guard_gear_event_write(
            char_deltas, inv_deltas, date_str, base_dir, baseline_date
        )
    except GearEventInflationError as e:
        print(f"::warning::{e}")
        return 0, 0
    gear_events, char_events = delta_shape_to_events(
        char_deltas, inv_deltas, date_str, baseline_date
    )
    gear_count = _append_shard_events(
        base_dir, date_str, gear_events, char_events, unique_tracked_ids=unique_tracked_ids
    )
    _update_manifest(base_dir, date_str, baseline_date, gear_count, len(char_events))
    return gear_count, len(char_events)


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
    unique_tracked_ids: set[str] | None = None,
) -> int:
    month = _month_key(date_str)
    gear_path = _gear_shard_path(base_dir, month)
    char_path = _char_shard_path(base_dir, month)

    existing_gear = _load_shard_gz(gear_path)
    existing_char = _load_shard_gz(char_path)
    existing_gear = [e for e in existing_gear if e.get("d") != date_str]
    existing_char = [e for e in existing_char if e.get("d") != date_str]
    if unique_tracked_ids:
        existing_gear, gear_events = cancel_paired_unique_events(
            existing_gear,
            gear_events,
            unique_tracked_ids,
            window_days=14,
            current_date=date_str,
        )
    existing_gear.extend(gear_events)
    existing_char.extend(char_events)
    existing_gear.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("i", "")))
    existing_char.sort(key=lambda e: (e.get("d", ""), e.get("c", ""), e.get("f", "")))

    _save_shard_gz(gear_path, existing_gear)
    _save_shard_gz(char_path, existing_char)
    return sum(1 for e in existing_gear if e.get("d") == date_str)


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
    unique_tracked_ids: set[str] | None = None,
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
    char = load_char_events(
        base_dir, start_date=start_date, end_date=end_date, exclusive_start=True
    )
    char_deltas = char_events_to_char_deltas(char)

    baseline_date = _manifest_baseline_for_date(base_dir, end_date)
    baseline_inv: dict = {}
    if baseline_date:
        try:
            from delta_storage import load_baseline_for_date

            bl = load_baseline_for_date(baseline_date, base_dir)
            if bl:
                baseline_inv = bl.get("inventories") or {}
        except ImportError:
            pass

    try:
        from generate_spell_page import load_no_rent_items

        no_rent = load_no_rent_items()
    except ImportError:
        no_rent = set()

    all_gear = load_gear_events(base_dir, end_date=end_date)
    abs_start = build_possession_map(baseline_inv, all_gear, start_date, no_rent=no_rent)
    abs_end = build_possession_map(baseline_inv, all_gear, end_date, no_rent=no_rent)
    inv_deltas = diff_absolute_possession_maps(abs_start, abs_end)
    if unique_tracked_ids:
        filter_inv_deltas_for_display(inv_deltas, abs_start, abs_end, unique_tracked_ids)
    if item_names:
        for row in inv_deltas.values():
            inames = row.setdefault("item_names", {})
            for iid in list((row.get("added") or {}).keys()) + list((row.get("removed") or {}).keys()):
                if iid in item_names:
                    inames[iid] = item_names[iid]

    return {
        "char_deltas": char_deltas,
        "inv_deltas": inv_deltas,
        "start_date": start_date,
        "end_date": end_date,
    }


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


def filter_events_for_char(events: list[dict], char_name: str) -> list[dict]:
    """Return events whose character field matches ``char_name``."""
    return [e for e in (events or []) if e.get("c") == char_name]


def filter_char_events_for_baseline(
    events: list[dict],
    baseline_date: str,
) -> list[dict]:
    """Drop stat events from a prior baseline era (``ev.b`` != ``baseline_date``)."""
    if not baseline_date:
        return list(events or [])
    out: list[dict] = []
    for ev in events or []:
        b = ev.get("b")
        if b is not None and b != baseline_date:
            continue
        if (
            b is None
            and ev.get("f") in ("aa", "lvl", "hp")
            and (ev.get("d") or "") < baseline_date
        ):
            continue
        out.append(ev)
    return out


def manifest_latest_date(manifest: dict | None) -> str:
    """Latest calendar date key from gear_events manifest, or empty string."""
    days = (manifest or {}).get("days") or {}
    return max(days.keys()) if days else ""


def load_item_id_to_name_map(base_dir: str | None = None) -> dict[str, str]:
    """Load full item_id -> name map from data/item_id_to_name.json."""
    root = base_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(root, "data", "item_id_to_name.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {str(k): str(v).strip() for k, v in data.items() if v}
    except (json.JSONDecodeError, OSError):
        return {}


def build_item_name_map_for_char(
    baseline: dict,
    char_name: str,
    extra: dict | None = None,
) -> dict[str, str]:
    """Resolve item id -> name for one character from global map, baseline inventory, extras."""
    name_map = load_item_id_to_name_map()
    for item in ((baseline or {}).get("inventories") or {}).get(char_name, []):
        iid = str(item.get("item_id", ""))
        iname = (item.get("item_name") or "").strip()
        if iid and iname:
            name_map[iid] = iname
    if extra:
        name_map.update(extra)
    return name_map


def reconstruct_holdings_for_char(
    baseline: dict,
    gear_events: list[dict],
    char_name: str,
    no_rent: set[str] | None = None,
) -> dict[str, int]:
    """Absolute item_id -> count for one character: baseline inventory + gear events."""
    no_rent = no_rent or set()
    inv_base = (baseline or {}).get("inventories") or {}
    baseline_items = inv_base.get(char_name) or []
    char_gear = filter_events_for_char(gear_events, char_name)
    if not baseline_items and not char_gear:
        return {}
    counts: dict[str, int] = {}
    for item in baseline_items:
        iid = str(item.get("item_id", ""))
        if not iid or iid.upper() == "NULL" or iid == "0":
            continue
        if iid in no_rent:
            continue
        counts[iid] = counts.get(iid, 0) + 1
    for ev in sorted(char_gear, key=lambda e: e.get("d") or ""):
        iid = str(ev.get("i", ""))
        sign = int(ev.get("s") or 0)
        n = int(ev.get("n") or 0)
        if not iid or n <= 0 or sign not in (1, -1):
            continue
        if iid in no_rent:
            continue
        if sign > 0:
            counts[iid] = counts.get(iid, 0) + n
        else:
            counts[iid] = counts.get(iid, 0) - n
            if counts[iid] <= 0:
                del counts[iid]
    return {k: v for k, v in counts.items() if v > 0}


def build_aa_timeline(
    baseline: dict,
    char_events: list[dict],
    char_name: str,
) -> list[dict]:
    """Chronological AA rows: baseline snapshot then dated ``f:aa`` events."""
    baseline_chars = (baseline or {}).get("characters") or {}
    bl = baseline_chars.get(char_name) or {}
    running = int(bl.get("aa_unspent") or 0) + int(bl.get("aa_spent") or 0)
    baseline_date = (baseline or {}).get("baseline_date") or ""
    rows: list[dict] = []
    if char_name in baseline_chars or running > 0:
        rows.append(
            {
                "date": baseline_date,
                "delta": 0,
                "total": running,
                "is_baseline": True,
            }
        )
    era_events = filter_char_events_for_baseline(char_events, baseline_date)
    aa_events = sorted(
        [e for e in era_events if e.get("c") == char_name and e.get("f") == "aa"],
        key=lambda e: e.get("d") or "",
    )
    for ev in aa_events:
        n = int(ev.get("n") or 0)
        running += n
        if ev.get("aa") is not None:
            running = int(ev["aa"])
        rows.append(
            {
                "date": ev.get("d") or "",
                "delta": n,
                "total": running,
                "is_baseline": False,
            }
        )
    return rows


def build_gear_event_log_rows(
    gear_events: list[dict],
    char_name: str,
    name_map: dict | None = None,
) -> list[dict]:
    """Dated gear +/- rows for one character (client timeline log)."""
    name_map = name_map or {}
    rows: list[dict] = []
    for ev in sorted(
        filter_events_for_char(gear_events, char_name),
        key=lambda e: (e.get("d") or "", str(e.get("i") or "")),
    ):
        sign = int(ev.get("s") or 0)
        n = int(ev.get("n") or 0)
        iid = str(ev.get("i", ""))
        if not iid or n <= 0 or sign not in (1, -1):
            continue
        rows.append(
            {
                "date": ev.get("d") or "",
                "sign": sign,
                "count": n,
                "item_id": iid,
                "item_name": name_map.get(iid) or f"Item {iid}",
                "visibility": bool(ev.get("v")),
            }
        )
    return rows


def baseline_only_item_ids(
    holdings: dict[str, int],
    gear_events: list[dict],
    char_name: str,
) -> dict[str, int]:
    """Items in holdings that never appear in gear events for this character."""
    touched = {str(e.get("i")) for e in filter_events_for_char(gear_events, char_name)}
    return {iid: cnt for iid, cnt in holdings.items() if iid not in touched}


def build_tracked_gear_event_log_rows(
    gear_events: list[dict],
    char_name: str,
    tracked_ids: set[str] | frozenset,
    name_map: dict | None = None,
    *,
    unique_tracked_ids: set[str] | None = None,
    baseline: dict | None = None,
    initial_holdings: dict[str, int] | None = None,
    no_rent: set[str] | None = None,
    source_label: dict | None = None,
) -> list[dict]:
    """Dated tracked-item +/- rows for one character (lore reacquire guard applied)."""
    tracked_ids = {str(i) for i in (tracked_ids or set())}
    if not tracked_ids:
        return []
    unique_tracked_ids = {str(i) for i in (unique_tracked_ids or set())}
    no_rent = {str(i) for i in (no_rent or set())}
    name_map = name_map or {}
    source_label = source_label or {}

    holdings: dict[str, int] = {}
    if initial_holdings is not None:
        for iid, cnt in initial_holdings.items():
            n = int(cnt or 0)
            if n > 0:
                holdings[str(iid)] = n
    else:
        baseline_items = ((baseline or {}).get("inventories") or {}).get(char_name) or []
        for item in baseline_items:
            iid = str(item.get("item_id", ""))
            if not iid or iid.upper() == "NULL" or iid == "0" or iid in no_rent:
                continue
            holdings[iid] = holdings.get(iid, 0) + 1

    rows: list[dict] = []
    char_events = sorted(
        filter_events_for_char(gear_events, char_name),
        key=lambda e: (e.get("d") or "", str(e.get("i") or "")),
    )

    for ev in char_events:
        if ev.get("v"):
            continue
        sign = int(ev.get("s") or 0)
        n = int(ev.get("n") or 0)
        iid = str(ev.get("i", ""))
        if not iid or n <= 0 or sign not in (1, -1) or iid in no_rent:
            continue

        is_tracked = iid in tracked_ids
        if is_tracked and sign > 0 and iid in unique_tracked_ids and holdings.get(iid, 0) > 0:
            continue

        if is_tracked:
            rows.append(
                {
                    "date": ev.get("d") or "",
                    "sign": sign,
                    "count": n,
                    "item_id": iid,
                    "item_name": name_map.get(iid) or f"Item {iid}",
                    "source": source_label.get(iid, ""),
                }
            )

        if sign > 0:
            holdings[iid] = holdings.get(iid, 0) + n
        else:
            holdings[iid] = holdings.get(iid, 0) - n
            if holdings.get(iid, 0) <= 0:
                holdings.pop(iid, None)

    return rows


def group_tracked_rows_by_date(rows: list[dict]) -> dict[str, dict[str, list[dict]]]:
    """Group tracked log rows by date into acquired and lost lists."""
    grouped: dict[str, dict[str, list[dict]]] = {}
    for row in rows or []:
        date_key = row.get("date") or ""
        if date_key not in grouped:
            grouped[date_key] = {"acquired": [], "lost": []}
        bucket = "acquired" if int(row.get("sign") or 0) > 0 else "lost"
        grouped[date_key][bucket].append(row)
    return grouped


def group_tracked_rows_by_zone(
    rows: list[dict],
    item_zone: dict | None = None,
    item_mob: dict | None = None,
) -> dict[str, dict[str, list[dict]]]:
    """Group tracked log rows by zone then mob (delta Items-by-Zone shape)."""
    item_zone = item_zone or {}
    item_mob = item_mob or {}
    out: dict[str, dict[str, list[dict]]] = {}
    for row in rows or []:
        iid = str(row.get("item_id") or "")
        zone = item_zone.get(iid) or "Other"
        mob = item_mob.get(iid) or ""
        out.setdefault(zone, {}).setdefault(mob, []).append(row)
    return out


def baseline_only_tracked_item_ids(
    holdings: dict[str, int],
    gear_events: list[dict],
    char_name: str,
    tracked_ids: set[str] | frozenset,
) -> dict[str, int]:
    """Tracked items held since baseline with no gear events for this character."""
    tracked_ids = {str(i) for i in (tracked_ids or set())}
    only = baseline_only_item_ids(holdings, gear_events, char_name)
    return {iid: cnt for iid, cnt in only.items() if iid in tracked_ids}


def _days_between(date_a: str | None, date_b: str | None) -> int:
    """Absolute calendar-day gap between two YYYY-MM-DD strings."""
    if not date_a or not date_b:
        return 9999
    try:
        a = datetime.strptime(date_a, "%Y-%m-%d")
        b = datetime.strptime(date_b, "%Y-%m-%d")
        return abs((b - a).days)
    except ValueError:
        return 9999


def possession_from_inv_snapshot(inv_data: dict | None) -> dict[str, dict[str, int]]:
    """Build {char_name: {item_id: count}} from Magelo inventory rows."""
    out: dict[str, dict[str, int]] = {}
    for char_name, items in (inv_data or {}).items():
        counts: dict[str, int] = defaultdict(int)
        for item in items:
            iid = str(item.get("item_id", "")).strip()
            if not iid or iid.upper() == "NULL":
                continue
            try:
                if int(iid) == 0:
                    continue
            except (ValueError, TypeError):
                pass
            counts[iid] += 1
        if counts:
            out[char_name] = dict(counts)
    return out


def _gear_events_by_char_up_to(
    gear_events: list[dict],
    up_to_date: str,
) -> dict[str, list[dict]]:
    """Index gear events by character, keeping only rows with ``d <= up_to_date``."""
    by_char: dict[str, list[dict]] = defaultdict(list)
    for ev in gear_events or []:
        d = ev.get("d", "")
        char_name = ev.get("c")
        if not char_name or not d or d > up_to_date:
            continue
        by_char[char_name].append(ev)
    for events in by_char.values():
        events.sort(key=lambda e: (e.get("d", ""), str(e.get("i", "")), int(e.get("s") or 0)))
    return by_char


def build_possession_map(
    baseline_inv: dict,
    gear_events: list[dict],
    up_to_date: str,
    *,
    no_rent: set | None = None,
) -> dict[str, dict[str, int]]:
    """Absolute item counts per character at end of ``up_to_date`` (baseline + events)."""
    no_rent = no_rent or set()
    counts_by_char: dict[str, dict[str, int]] = {}
    events_by_char = _gear_events_by_char_up_to(gear_events, up_to_date)
    all_chars = set((baseline_inv or {}).keys()) | set(events_by_char.keys())

    for char_name in all_chars:
        baseline_items = (baseline_inv or {}).get(char_name, [])
        char_events = events_by_char.get(char_name, [])
        if not baseline_items and not char_events:
            continue
        counts: dict[str, int] = defaultdict(int)
        for item in baseline_items:
            iid = str(item.get("item_id", "")).strip()
            if not iid or iid.upper() == "NULL":
                continue
            try:
                if int(iid) in no_rent:
                    continue
            except (ValueError, TypeError):
                pass
            try:
                if int(iid) == 0:
                    continue
            except (ValueError, TypeError):
                pass
            counts[iid] += 1

        for ev in char_events:
            item_id = str(ev.get("i", ""))
            if not item_id:
                continue
            try:
                if int(item_id) in no_rent:
                    continue
            except (ValueError, TypeError):
                pass
            sign = int(ev.get("s") or 0)
            n = int(ev.get("n") or 0)
            if n <= 0 or sign not in (1, -1):
                continue
            if sign > 0:
                counts[item_id] += n
            else:
                counts[item_id] -= n
                if counts[item_id] <= 0:
                    counts.pop(item_id, None)

        cleaned = {k: v for k, v in counts.items() if v > 0}
        if cleaned:
            counts_by_char[char_name] = cleaned
    return counts_by_char


def diff_absolute_possession_maps(
    abs_start: dict[str, dict[str, int]],
    abs_end: dict[str, dict[str, int]],
) -> dict:
    """Net inventory change between two per-character item-count maps."""
    inv_deltas: dict[str, dict] = {}
    all_chars = set(abs_start.keys()) | set(abs_end.keys())
    for char_name in all_chars:
        a = abs_start.get(char_name, {})
        b = abs_end.get(char_name, {})
        all_ids = set(a.keys()) | set(b.keys())
        added_items: dict[str, int] = {}
        removed_items: dict[str, int] = {}
        for item_id in all_ids:
            sid = str(item_id)
            ca = int(a.get(sid, 0) or 0)
            cb = int(b.get(sid, 0) or 0)
            net = cb - ca
            if net > 0:
                added_items[sid] = net
            elif net < 0:
                removed_items[sid] = -net
        if added_items or removed_items:
            inv_deltas[char_name] = {
                "added": added_items,
                "removed": removed_items,
                "item_names": {},
            }
    return inv_deltas


def filter_unique_reacquires_in_inv_deltas(
    inv_deltas: dict,
    possession_before: dict[str, dict[str, int]],
    unique_ids: set[str],
) -> None:
    """Drop spurious ``added`` rows for lore tracked items the character already possessed."""
    if not unique_ids:
        return
    unique_ids = {str(i) for i in unique_ids}
    empty_chars: list[str] = []
    for char_name, row in (inv_deltas or {}).items():
        added = row.get("added") or {}
        prev = possession_before.get(char_name, {})
        for item_id in list(added.keys()):
            if str(item_id) not in unique_ids:
                continue
            if int(prev.get(str(item_id), 0) or 0) > 0:
                del added[item_id]
        if not added and not (row.get("removed") or {}):
            empty_chars.append(char_name)
    for char_name in empty_chars:
        inv_deltas.pop(char_name, None)


def filter_inv_deltas_for_display(
    inv_deltas: dict,
    abs_start: dict[str, dict[str, int]],
    abs_end: dict[str, dict[str, int]],
    unique_ids: set[str],
) -> None:
    """Remove unique-item ``added`` rows when possession did not net-increase across the range."""
    if not unique_ids:
        return
    unique_ids = {str(i) for i in unique_ids}
    empty_chars: list[str] = []
    for char_name, row in (inv_deltas or {}).items():
        added = row.get("added") or {}
        for item_id in list(added.keys()):
            if str(item_id) not in unique_ids:
                continue
            start_c = int((abs_start.get(char_name) or {}).get(str(item_id), 0) or 0)
            end_c = int((abs_end.get(char_name) or {}).get(str(item_id), 0) or 0)
            if end_c <= start_c:
                del added[item_id]
        if not added and not (row.get("removed") or {}):
            empty_chars.append(char_name)
    for char_name in empty_chars:
        inv_deltas.pop(char_name, None)


def cancel_paired_unique_events(
    existing_gear: list[dict],
    new_events: list[dict],
    unique_ids: set[str],
    *,
    window_days: int = 14,
    current_date: str,
) -> tuple[list[dict], list[dict]]:
    """Cancel reacquire (+1) by dropping today's gain and the prior loss within window_days."""
    if not unique_ids:
        return existing_gear, new_events
    unique_ids = {str(i) for i in unique_ids}
    losses_to_remove: set[tuple] = set()
    filtered_new: list[dict] = []

    for nev in new_events:
        item_id = str(nev.get("i", ""))
        char_name = nev.get("c", "")
        sign = int(nev.get("s") or 0)
        if item_id not in unique_ids or sign != 1 or not char_name:
            filtered_new.append(nev)
            continue

        candidates = [
            e
            for e in existing_gear
            if e.get("c") == char_name
            and str(e.get("i")) == item_id
            and int(e.get("s") or 0) == -1
            and e.get("d", "") < current_date
            and _days_between(e.get("d"), current_date) <= window_days
        ]
        if not candidates:
            filtered_new.append(nev)
            continue

        loss_ev = max(candidates, key=lambda e: e.get("d", ""))
        losses_to_remove.add(
            (
                loss_ev.get("d"),
                loss_ev.get("c"),
                str(loss_ev.get("i")),
                int(loss_ev.get("s") or 0),
                int(loss_ev.get("n") or 0),
            )
        )

    def _event_key(e: dict) -> tuple:
        return (
            e.get("d"),
            e.get("c"),
            str(e.get("i")),
            int(e.get("s") or 0),
            int(e.get("n") or 0),
        )

    pruned_existing = [e for e in existing_gear if _event_key(e) not in losses_to_remove]
    return pruned_existing, filtered_new


def _manifest_baseline_for_date(base_dir: str, date_str: str) -> str | None:
    path = _manifest_path(base_dir)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    days = manifest.get("days") or {}
    if date_str in days and days[date_str].get("baseline_date"):
        return days[date_str]["baseline_date"]
    for era in reversed(manifest.get("eras") or []):
        first = era.get("first_event")
        if first and first <= date_str and era.get("baseline_date"):
            return era["baseline_date"]
    return None


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
        for iid in all_ids:
            if iid not in name_map:
                global_name = load_item_id_to_name_map(base_dir).get(iid)
                if global_name:
                    name_map[iid] = global_name
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
