#!/usr/bin/env python3
"""Compute, write, and verify Magelo dump cache fingerprints for Actions cache integrity."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

FINGERPRINT_FILENAME = "magelo_dump_fingerprint.json"
DEFAULT_CHAR = Path("character/TAKP_character.txt")
DEFAULT_INV = Path("inventory/TAKP_character_inventory.txt")
DEFAULT_STAMP = Path(".magelo_update_date")
DUMP_INDEX_PATH = Path("character/.magelo_dump_index.json")
DUMP_INDEX_MAX_DAYS = 14


def read_stamp_line(stamp_path: Path = DEFAULT_STAMP) -> str:
    """First line of stamp file (ignores embedded fingerprint JSON on line 2)."""
    if not stamp_path.is_file():
        return ""
    with stamp_path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                return stripped
    return ""


def parse_stamp(s: str) -> datetime | None:
    first = (s or "").splitlines()[0] if s else ""
    s = re.sub(r"\s+", " ", first.strip())
    if not s or s.lower() == "unknown":
        return None
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S UTC %Y")
    except ValueError:
        return None


def embed_fingerprint_in_stamp(stamp_path: Path, fp: dict) -> None:
    """Append fingerprint JSON to stamp file (cached via existing .magelo_update_date path)."""
    stamp_line = read_stamp_line(stamp_path) or (fp.get("export_stamp_raw") or "")
    payload = {k: v for k, v in fp.items() if k != "export_stamp_raw"}
    with stamp_path.open("w", encoding="utf-8") as f:
        f.write(stamp_line.rstrip() + "\n")
        json.dump(payload, f, separators=(",", ":"))
        f.write("\n")


def _file_md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _count_lines(path: Path) -> int:
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def compute_fingerprint(
    char_path: Path,
    inv_path: Path,
    stamp_path: Path,
    *,
    cache_key_date: str | None = None,
) -> dict:
    """Build fingerprint dict from dump files and export stamp."""
    if not char_path.is_file():
        raise FileNotFoundError(f"Character dump missing: {char_path}")
    if not inv_path.is_file():
        raise FileNotFoundError(f"Inventory dump missing: {inv_path}")

    stamp_raw = read_stamp_line(stamp_path)
    parsed = parse_stamp(stamp_raw)
    export_stamp_date = parsed.strftime("%Y-%m-%d") if parsed else None

    fp = {
        "version": 1,
        "cache_key_date": (cache_key_date or os.environ.get("EXPECTED_DATE") or "").strip() or None,
        "export_stamp_date": export_stamp_date,
        "export_stamp_raw": stamp_raw or None,
        "char_lines": _count_lines(char_path),
        "inv_lines": _count_lines(inv_path),
        "char_md5": _file_md5(char_path),
        "inv_md5": _file_md5(inv_path),
    }
    return fp


def write_fingerprint(
    out_path: Path,
    char_path: Path = DEFAULT_CHAR,
    inv_path: Path = DEFAULT_INV,
    stamp_path: Path = DEFAULT_STAMP,
    *,
    cache_key_date: str | None = None,
) -> dict:
    fp = compute_fingerprint(
        char_path, inv_path, stamp_path, cache_key_date=cache_key_date
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(fp, f, indent=2)
        f.write("\n")
    return fp


def verify_fingerprint(
    fp: dict,
    char_path: Path,
    inv_path: Path,
    expected_date: str,
) -> list[str]:
    """Return human-readable errors; empty list means OK."""
    errors: list[str] = []
    if not expected_date:
        errors.append("expected_date is empty")
        return errors

    cache_key = (fp.get("cache_key_date") or "").strip()
    if cache_key and cache_key != expected_date:
        errors.append(
            f"fingerprint cache_key_date {cache_key!r} != expected {expected_date!r}"
        )

    export_date = (fp.get("export_stamp_date") or "").strip()
    if export_date and export_date != expected_date:
        errors.append(
            f"fingerprint export_stamp_date {export_date!r} != expected {expected_date!r}"
        )

    if not char_path.is_file():
        errors.append(f"character dump missing: {char_path}")
    if not inv_path.is_file():
        errors.append(f"inventory dump missing: {inv_path}")
    if errors:
        return errors

    char_md5 = _file_md5(char_path)
    inv_md5 = _file_md5(inv_path)
    char_lines = _count_lines(char_path)
    inv_lines = _count_lines(inv_path)

    if fp.get("char_md5") and fp["char_md5"] != char_md5:
        errors.append("character file MD5 mismatch vs fingerprint")
    if fp.get("inv_md5") and fp["inv_md5"] != inv_md5:
        errors.append("inventory file MD5 mismatch vs fingerprint")
    if fp.get("char_lines") is not None and fp["char_lines"] != char_lines:
        errors.append(
            f"character line count {char_lines} != fingerprint {fp['char_lines']}"
        )
    if fp.get("inv_lines") is not None and fp["inv_lines"] != inv_lines:
        errors.append(
            f"inventory line count {inv_lines} != fingerprint {fp['inv_lines']}"
        )
    return errors


def load_fingerprint(
    path: Path = Path(FINGERPRINT_FILENAME),
    stamp_path: Path = DEFAULT_STAMP,
) -> dict | None:
    if path.is_file():
        try:
            with path.open(encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    if not stamp_path.is_file():
        return None
    try:
        lines = stamp_path.read_text(encoding="utf-8").splitlines()
        if len(lines) < 2:
            return None
        return json.loads(lines[1])
    except (OSError, json.JSONDecodeError):
        return None


def verify_legacy_stamp(stamp_path: Path, expected_date: str) -> list[str]:
    """For caches saved before fingerprints existed."""
    if not stamp_path.is_file():
        return [f"export stamp missing: {stamp_path}"]
    raw = read_stamp_line(stamp_path)
    parsed = parse_stamp(raw)
    if not parsed:
        return [f"could not parse export stamp: {raw!r}"]
    actual = parsed.strftime("%Y-%m-%d")
    if actual != expected_date:
        return [
            f"legacy cache export stamp date {actual!r} != expected {expected_date!r} "
            f"(stamp: {raw!r})"
        ]
    return []


def verify_dump_against_index(
    char_path: Path,
    inv_path: Path,
    expected_date: str,
    index_path: Path = DUMP_INDEX_PATH,
) -> list[str]:
    """Secondary check when fingerprint is absent."""
    if not index_path.is_file():
        return []
    try:
        with index_path.open(encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    entry = (index or {}).get(expected_date)
    if not entry:
        return []
    errors: list[str] = []
    if char_path.is_file() and entry.get("char_lines") is not None:
        actual = _count_lines(char_path)
        expected = int(entry["char_lines"])
        if actual != expected:
            errors.append(
                f"character lines {actual} != audit index {expected} for {expected_date}"
            )
    if inv_path.is_file() and entry.get("inv_lines") is not None:
        actual = _count_lines(inv_path)
        expected = int(entry["inv_lines"])
        if actual != expected:
            errors.append(
                f"inventory lines {actual} != audit index {expected} for {expected_date}"
            )
    return errors


def update_dump_index(
    date_str: str,
    char_lines: int,
    inv_lines: int,
    index_path: Path = DUMP_INDEX_PATH,
    max_days: int = DUMP_INDEX_MAX_DAYS,
) -> None:
    """Append/update committed audit index (last N days)."""
    index: dict = {}
    if index_path.is_file():
        try:
            with index_path.open(encoding="utf-8") as f:
                index = json.load(f) or {}
        except (OSError, json.JSONDecodeError):
            index = {}
    index[date_str] = {"char_lines": char_lines, "inv_lines": inv_lines}
    sorted_dates = sorted(index.keys())
    if len(sorted_dates) > max_days:
        for old in sorted_dates[: len(sorted_dates) - max_days]:
            index.pop(old, None)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("w", encoding="utf-8") as f:
        json.dump(index, f, indent=2)
        f.write("\n")


def cmd_write() -> int:
    expected = (os.environ.get("EXPECTED_DATE") or "").strip()
    out = Path(FINGERPRINT_FILENAME)
    fp = write_fingerprint(out, cache_key_date=expected or None)
    embed_fingerprint_in_stamp(DEFAULT_STAMP, fp)
    print(f"OK Wrote {out} and embedded fingerprint in {DEFAULT_STAMP}")
    print(
        f"  cache_key_date={fp.get('cache_key_date')} "
        f"export_stamp_date={fp.get('export_stamp_date')} "
        f"char_lines={fp.get('char_lines')} inv_lines={fp.get('inv_lines')}"
    )
    if expected and fp.get("export_stamp_date") and fp["export_stamp_date"] != expected:
        print(
            f"::warning::Export stamp date {fp['export_stamp_date']} != "
            f"EXPECTED_DATE {expected}"
        )
    if expected:
        update_dump_index(expected, int(fp["char_lines"]), int(fp["inv_lines"]))
        print(f"OK Updated {DUMP_INDEX_PATH} for {expected}")
    return 0


def cmd_verify() -> int:
    expected = (
        os.environ.get("EXPECTED_YESTERDAY_DATE")
        or os.environ.get("EXPECTED_DATE")
        or os.environ.get("EXPECTED_PREVIOUS_DATE")
        or ""
    ).strip()
    if not expected:
        print("::error::EXPECTED_YESTERDAY_DATE or EXPECTED_DATE is not set")
        return 1

    char_path = DEFAULT_CHAR
    inv_path = DEFAULT_INV
    stamp_path = DEFAULT_STAMP
    fp_path = Path(FINGERPRINT_FILENAME)
    fp = load_fingerprint(fp_path)

    errors: list[str] = []
    if fp:
        errors.extend(verify_fingerprint(fp, char_path, inv_path, expected))
    else:
        errors.extend(verify_legacy_stamp(stamp_path, expected))
        errors.extend(verify_dump_against_index(char_path, inv_path, expected))

    if errors:
        for err in errors:
            print(f"::error::{err}")
        print(
            f"Magelo dump cache verification failed for magelo-dump-{expected}. "
            "Restore or re-seed cache with matching export content."
        )
        return 1

    print(f"OK Magelo dump cache verified for {expected}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} write|verify", file=sys.stderr)
        return 2
    cmd = sys.argv[1].lower()
    if cmd == "write":
        return cmd_write()
    if cmd == "verify":
        return cmd_verify()
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
