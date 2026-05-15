#!/usr/bin/env python3
"""POST workflow_dispatch for ``Regenerate delta daily JSONs`` (``regenerate-delta-days.yml``).

Requires ``GITHUB_TOKEN`` or ``GH_TOKEN`` with ``workflow`` (or ``repo``) scope.

Example::

    set GITHUB_TOKEN=ghp_...
    python scripts/dispatch_regenerate_delta_days.py --repo Ammordius/NAGD-spell-inventory ^
      --dates 2026-05-09,2026-05-10,2026-05-11,2026-05-12,2026-05-13

If ``--repo`` is omitted, the script tries ``git remote get-url origin``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORKFLOW_FILE = "regenerate-delta-days.yml"


def _repo_from_git(remote_root: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=remote_root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    url = (r.stdout or "").strip()
    if not url:
        return None
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo",
        default="",
        metavar="OWNER/NAME",
        help="GitHub repository (default: parse from git remote origin)",
    )
    ap.add_argument(
        "--dates",
        default="2026-05-09,2026-05-10,2026-05-11,2026-05-12,2026-05-13,2026-05-14,2026-05-15",
        help="Comma-separated YYYY-MM-DD passed to the workflow dates input",
    )
    ap.add_argument("--baseline-era-date", default="2026-02-09")
    ap.add_argument("--baseline-cache-date", default="")
    ap.add_argument("--ref", default="main", help="Git ref to run workflow on")
    ap.add_argument("--force", choices=("true", "false"), default="true")
    ap.add_argument("--commit-changes", choices=("true", "false"), default="true")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print(
            "ERROR: set GITHUB_TOKEN or GH_TOKEN to dispatch the workflow.",
            file=sys.stderr,
        )
        return 1

    repo = (args.repo or "").strip() or _repo_from_git(root) or ""
    if not repo:
        print("ERROR: could not determine repo; pass --repo OWNER/NAME", file=sys.stderr)
        return 1

    url = f"https://api.github.com/repos/{repo}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    body = {
        "ref": args.ref,
        "inputs": {
            "dates": args.dates.replace(" ", ""),
            "baseline_era_date": args.baseline_era_date,
            "baseline_cache_date": args.baseline_cache_date,
            "force": args.force,
            "commit_changes": args.commit_changes,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            if resp.status not in (200, 201, 204):
                print(f"ERROR: HTTP {resp.status}", file=sys.stderr)
                return 1
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: HTTP {e.code}: {err}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"OK: dispatched {WORKFLOW_FILE} on {repo} ref={args.ref}")
    print("    inputs:", json.dumps(body["inputs"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
