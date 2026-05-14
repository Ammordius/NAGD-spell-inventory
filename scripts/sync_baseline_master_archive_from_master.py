#!/usr/bin/env python3
"""Ensure dated ``baseline_master_<date>.json.gz`` files exist for CI / verify.

1. If ``baseline_master.json.gz`` exists and ``baseline_master_<embedded>.json.gz`` is missing,
   copy master → dated path (never overwrites an existing dated archive).

2. Scan ``delta_daily_*.json.gz`` (same rules as ``verify_delta_baseline_archives``) for
   ``baseline_date`` values that must be resolvable. For each still-missing archive, try
   (in order) downloading from **raw.githubusercontent.com** (current ``GITHUB_SHA``, then
   ``main`` / ``master``), then **GitHub Pages**, when ``GITHUB_REPOSITORY`` is set.

``generate_spell_page`` may leave master on a newer rotation while repo dailies still reference
an older baseline; fetches recover the dated snapshot from git or the last deploy when possible.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Keep in sync with scripts/verify_delta_baseline_archives.py
EARLIEST_VERIFY_DATE = "2026-01-01"
BASELINE_ARCHIVE_CUTOFF = "2026-02-01"


def _parse_iso(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")


def _days_between(a: str, b: str) -> int:
    return (_parse_iso(b) - _parse_iso(a)).days


def _embedded_baseline_date(gz_path: Path) -> str | None:
    if not gz_path.is_file():
        return None
    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
    bd = data.get("baseline_date")
    if bd in (None, "", "Unknown"):
        return None
    return str(bd)


def baseline_resolvable(baseline_date: str, base_dir: Path) -> bool:
    if not baseline_date or baseline_date == "Unknown":
        return True
    archive = base_dir / f"baseline_master_{baseline_date}.json.gz"
    if archive.is_file():
        return True
    master = base_dir / "baseline_master.json.gz"
    emb = _embedded_baseline_date(master)
    return emb is not None and str(emb) == str(baseline_date)


def daily_file_date(path: Path) -> str | None:
    m = re.match(r"delta_daily_(\d{4}-\d{2}-\d{2})\.json\.gz$", path.name)
    return m.group(1) if m else None


def collect_needed_baseline_dates(base_dir: Path) -> set[str]:
    """baseline_date strings that verify_delta_baseline_archives requires to be resolvable."""
    needed: set[str] = set()
    for path in sorted(base_dir.glob("delta_daily_*.json.gz")):
        file_date = daily_file_date(path)
        if not file_date or file_date < EARLIEST_VERIFY_DATE:
            continue
        try:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                doc = json.load(f)
        except OSError:
            continue
        bd = doc.get("baseline_date") or "Unknown"
        if bd == "Unknown":
            continue
        bd_s = str(bd)
        if bd_s < BASELINE_ARCHIVE_CUTOFF:
            continue
        if _days_between(bd_s, file_date) >= 0:
            needed.add(bd_s)
    return needed


def sync_master_to_dated_archive(base_dir: Path) -> None:
    master = base_dir / "baseline_master.json.gz"
    bd = _embedded_baseline_date(master)
    if not bd:
        print(f"No embedded baseline_date in {master.name}; skip master→archive copy.")
        return

    archive = base_dir / f"baseline_master_{bd}.json.gz"
    if archive.is_file():
        print(f"OK: archive already exists: {archive.name}")
        return

    shutil.copy2(master, archive)
    print(f"OK: created {archive.name} from {master.name} (baseline_date={bd})")


def _validate_and_write_gz_bytes(raw: bytes, baseline_date: str, dest: Path) -> bool:
    if not raw:
        return False
    try:
        data = json.loads(gzip.decompress(raw).decode("utf-8"))
    except (OSError, json.JSONDecodeError, EOFError) as e:
        print(f"WARN: invalid gzip/json for {baseline_date}: {e}")
        return False
    emb = data.get("baseline_date")
    if str(emb) != str(baseline_date):
        print(f"WARN: fetched baseline_date={emb!r} expected {baseline_date!r}; not saving.")
        return False

    fd, tmp_path = tempfile.mkstemp(prefix=".baseline_dl_", suffix=".json.gz", dir=str(dest.parent))
    os.close(fd)
    tmp = Path(tmp_path)
    try:
        tmp.write_bytes(raw)
        os.replace(tmp, dest)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise

    print(f"OK: saved {dest.name} ({len(raw) // 1024} KiB)")
    return True


def _http_get_bytes(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "magelo-ci-baseline-sync"})
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        print(f"WARN: HTTP {e.code} for {url}")
        return None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"WARN: GET failed {url}: {e}")
        return None


def try_fetch_missing_archive_from_raw_github(base_dir: Path, baseline_date: str) -> bool:
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not gh_repo or "/" not in gh_repo:
        return False

    owner, _, repo = gh_repo.partition("/")
    dest = base_dir / f"baseline_master_{baseline_date}.json.gz"
    if dest.is_file():
        return True

    refs: list[str] = []
    sha = os.environ.get("GITHUB_SHA", "").strip()
    if sha:
        refs.append(sha)
    refs.extend(["main", "master"])

    for ref in refs:
        url = (
            f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/"
            f"delta_snapshots/baseline_master_{baseline_date}.json.gz"
        )
        print(f"Trying raw GitHub fetch: {url}")
        raw = _http_get_bytes(url)
        if raw and _validate_and_write_gz_bytes(raw, baseline_date, dest):
            return True

    return False


def try_fetch_missing_archive_from_pages(base_dir: Path, baseline_date: str) -> bool:
    gh_repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not gh_repo or "/" not in gh_repo:
        print(
            f"SKIP Pages fetch baseline_master_{baseline_date}.json.gz: "
            "GITHUB_REPOSITORY not set (not running in GitHub Actions?).",
        )
        return False

    owner, _, repo = gh_repo.partition("/")
    repo_lc = repo.lower()
    url = (
        f"https://{owner}.github.io/{repo_lc}/delta_snapshots/"
        f"baseline_master_{baseline_date}.json.gz"
    )
    dest = base_dir / f"baseline_master_{baseline_date}.json.gz"
    if dest.is_file():
        return True

    print(f"Trying Pages fetch: {url}")
    raw = _http_get_bytes(url)
    if raw and _validate_and_write_gz_bytes(raw, baseline_date, dest):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--base-dir",
        type=Path,
        default=Path("delta_snapshots"),
        help="Directory containing baseline_master*.json.gz and delta_daily_*.json.gz",
    )
    args = ap.parse_args()
    base_dir = args.base_dir.resolve()
    if not base_dir.is_dir():
        print(f"ERROR: not a directory: {base_dir}", file=sys.stderr)
        return 1

    sync_master_to_dated_archive(base_dir)

    needed = collect_needed_baseline_dates(base_dir)
    for bd in sorted(needed):
        if baseline_resolvable(bd, base_dir):
            continue
        print(f"Missing resolvable baseline for {bd!r}; attempting recovery…")
        if try_fetch_missing_archive_from_raw_github(base_dir, bd):
            continue
        if try_fetch_missing_archive_from_pages(base_dir, bd):
            continue
        print(
            f"WARN: still missing baseline_master_{bd}.json.gz "
            f"(master embedded mismatch; raw GitHub + Pages fetch failed or unavailable).",
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
