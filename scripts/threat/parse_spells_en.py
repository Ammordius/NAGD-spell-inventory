"""Parse EQEmu spells_en INSERT dumps into row dicts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def extract_spells_en_columns(create_sql: str) -> list[str]:
    m = re.search(r"CREATE TABLE `spells_en`\s*\((.*)\)\s*ENGINE", create_sql, re.DOTALL | re.IGNORECASE)
    if not m:
        raise ValueError("Could not find CREATE TABLE spells_en")
    body = m.group(1)
    if "PRIMARY KEY" in body:
        body = body.split("PRIMARY KEY")[0]
    return re.findall(r"`([^`]+)`", body)


def split_top_level_commas(s: str) -> list[str]:
    parts: list[str] = []
    i = 0
    start = 0
    in_q = False
    n = len(s)
    while i < n:
        c = s[i]
        if in_q:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'" and i + 1 < n and s[i + 1] == "'":
                i += 2
                continue
            if c == "'":
                in_q = False
        else:
            if c == "'":
                in_q = True
            elif c == ",":
                parts.append(s[start:i].strip())
                start = i + 1
        i += 1
    parts.append(s[start:].strip())
    return parts


def parse_sql_value(raw: str) -> Any:
    t = raw.strip()
    if t.lower() == "null":
        return None
    if t.startswith("'") and t.endswith("'"):
        inner = t[1:-1].replace("''", "'")
        return inner
    try:
        if "." in t:
            return float(t)
        return int(t)
    except ValueError:
        return t


def row_dict(columns: list[str], values_inner: str) -> dict[str, Any]:
    cells = split_top_level_commas(values_inner)
    if len(cells) < len(columns):
        cells = cells + ["NULL"] * (len(columns) - len(cells))
    if len(cells) > len(columns):
        raise ValueError(f"Column count mismatch: {len(columns)} cols vs {len(cells)} values (truncation unsafe)")
    return dict(zip(columns, [parse_sql_value(c) for c in cells], strict=True))


def _int_field(raw: dict[str, Any], key: str, default: int = 0) -> int:
    v = raw.get(key)
    if v is None:
        return default
    return int(float(v))


def spell_threat_record(raw: dict[str, Any]) -> dict[str, Any]:
    """Subset + normalized arrays for CheckAggroAmount."""
    sid = int(raw["id"])
    bases = [
        _int_field(raw, "effect_base_value1"),
        _int_field(raw, "effect_base_value2"),
        _int_field(raw, "effect_base_value3"),
        _int_field(raw, "effect_base_value4"),
        _int_field(raw, "effect_base_value5"),
        _int_field(raw, "effect_base_value6"),
        _int_field(raw, "effect_base_value7"),
        _int_field(raw, "effect_base_value8"),
        _int_field(raw, "effect_base_value9"),
        _int_field(raw, "effect_base_value10"),
        _int_field(raw, "effect_base_value11"),
        _int_field(raw, "effect_base_value12"),
    ]
    maxes = [_int_field(raw, f"effect_limit_value{i}") for i in range(1, 13)]
    formulas = [_int_field(raw, f"formula{i}") for i in range(1, 13)]
    effectids = [_int_field(raw, f"effectid{i}", 254) for i in range(1, 13)]
    classes = [int(raw[f"classes{i}"] or 255) for i in range(1, 16)]
    return {
        "id": sid,
        "name": raw.get("name") or "",
        "effectid": effectids,
        "formula": formulas,
        "base": bases,
        "max": maxes,
        "resisttype": _int_field(raw, "resisttype"),
        "buffduration": _int_field(raw, "buffduration"),
        "buffdurationformula": _int_field(raw, "buffdurationformula"),
        "classes": classes,
        "not_player_spell": _int_field(raw, "not_player_spell") if "not_player_spell" in raw else 0,
        "hate_added": _int_field(raw, "HateAdded") if "HateAdded" in raw else 0,
        "goodEffect": _int_field(raw, "goodEffect"),
    }


def iter_spells_en_inserts(sql_text: str):
    # Non-greedy: one INSERT row per statement (typical dump: one VALUES tuple per line).
    for m in re.finditer(
        r"INSERT INTO `spells_en` VALUES\s*\((.*?)\)\s*;",
        sql_text,
        re.DOTALL | re.IGNORECASE,
    ):
        yield m.group(1)


def load_spells_en_from_files(paths: list[Path], columns: list[str]) -> dict[int, dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    for p in paths:
        text = p.read_text(encoding="utf-8", errors="replace")
        for inner in iter_spells_en_inserts(text):
            raw = row_dict(columns, inner)
            rid = raw.get("id")
            if rid is None:
                continue
            rec = spell_threat_record(raw)
            by_id[rec["id"]] = rec
    return by_id


def load_columns_from_part1(part1: Path) -> list[str]:
    text = part1.read_text(encoding="utf-8", errors="replace")
    end = text.find("-- ----------------------------\n-- Records")
    if end < 0:
        end = text.find("INSERT INTO `spells_en`")
    chunk = text[:end] if end > 0 else text
    return extract_spells_en_columns(chunk)
