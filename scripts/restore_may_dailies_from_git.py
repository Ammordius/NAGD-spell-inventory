#!/usr/bin/env python3
"""Restore best-known delta_daily files for the May 2026 window from git history.

Picks the newest commit per date where baseline_date is 2026-02-09 and char_deltas is
non-empty (or the newest commit with Feb-9 baseline if all are empty).

Used when magelo-dump Actions caches are unavailable locally.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _load_gz(blob: bytes) -> dict:
    return json.load(gzip.GzipFile(fileobj=io.BytesIO(blob)))


def _score(doc: dict) -> tuple[int, int]:
  """Higher is better: prefer non-empty char_deltas, then inv_deltas."""
  chars = len(doc.get("char_deltas") or {})
  inv = len(doc.get("inv_deltas") or {})
  return (chars, inv)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--dates",
        default="2026-05-09,2026-05-10,2026-05-11,2026-05-12,2026-05-13,2026-05-14,2026-05-15",
    )
    ap.add_argument("--baseline-era", default="2026-02-09")
    ap.add_argument("--base-dir", type=Path, default=Path("delta_snapshots"))
    ap.add_argument("--max-commits", type=int, default=400)
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    base_dir = (root / args.base_dir).resolve()
    base_dir.mkdir(parents=True, exist_ok=True)
    dates = [d.strip() for d in args.dates.split(",") if d.strip()]
    era = args.baseline_era.strip()

    commits = (
        subprocess.check_output(
            ["git", "log", "--oneline", f"-{args.max_commits}", "--", "delta_snapshots/"],
            cwd=root,
        )
        .decode()
        .splitlines()
    )

    restored = 0
    for date in dates:
        rel = f"delta_snapshots/delta_daily_{date}.json.gz"
        dest = base_dir / f"delta_daily_{date}.json.gz"
        best: tuple[tuple[int, int], str, dict] | None = None
        fallback: tuple[str, dict] | None = None

        for line in commits:
            commit = line.split()[0]
            try:
                blob = subprocess.check_output(
                    ["git", "show", f"{commit}:{rel}"],
                    cwd=root,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                continue
            doc = _load_gz(blob)
            if str(doc.get("baseline_date")) != era:
                continue
            if fallback is None:
                fallback = (commit, doc)
            sc = _score(doc)
            if sc > (0, 0) and (best is None or sc > best[0]):
                best = (sc, commit, doc)

        pick = best or (None, fallback[0], fallback[1]) if fallback else None
        if pick is None or (isinstance(pick, tuple) and pick[1] is None):
            print(f"SKIP {date}: no commit with baseline_date={era}", file=sys.stderr)
            continue

        if best:
            _, commit, doc = best
        else:
            commit, doc = fallback  # type: ignore[misc]

        with gzip.open(dest, "wt", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
        shutil.copy2(dest, base_dir / f"delta_daily_{date}.json")
        n_chars = len(doc.get("char_deltas") or {})
        print(f"OK {date} from {commit} chars={n_chars} baseline={doc.get('baseline_date')}")
        restored += 1

    print(f"Restored {restored}/{len(dates)} files into {base_dir}")
    return 0 if restored == len(dates) else 1


if __name__ == "__main__":
    sys.exit(main())
