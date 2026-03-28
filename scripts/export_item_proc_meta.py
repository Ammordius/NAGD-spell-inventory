"""
Export items.procrate / proclevel / proceffect into data/item_proc_meta.json.

Used by build_weapon_threat_server.py for TryWeaponProc WPC = GetProcChance * (100 + procrate) / 100.

Usage:
  python scripts/export_item_proc_meta.py --from-mysql --mysql-database peq

  # Or from a tab-separated file (mysql -N -B output: id, procrate, proclevel, proceffect):
  mysql -u root -N -B peq < scripts/threat/sql/export_item_proc_meta.sql > /tmp/proc.tsv
  python scripts/export_item_proc_meta.py --from-tsv /tmp/proc.tsv

Environment (optional): MYSQL_USER, MYSQL_PASSWORD, MYSQL_HOST, MYSQL_DATABASE
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

_MAG = Path(__file__).resolve().parents[1]


def rows_to_meta(rows: list[tuple[int, int, int, int]]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for iid, pr, pl, pe in rows:
        out[str(int(iid))] = {
            "procrate": int(pr),
            "proclevel": int(pl),
            "proceffect": int(pe),
        }
    return out


def parse_tsv(text: str) -> list[tuple[int, int, int, int]]:
    rows: list[tuple[int, int, int, int]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 4:
            continue
        rows.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3])))
    return rows


def fetch_mysql(
    *,
    user: str,
    password: str,
    host: str,
    database: str,
    mysql_bin: str,
) -> list[tuple[int, int, int, int]]:
    sql = (
        "SELECT id, procrate, proclevel, proceffect FROM items "
        "WHERE proceffect > 0 OR procrate != 0 ORDER BY id"
    )
    cmd = [mysql_bin, "-N", "-B", "-h", host, "-u", user, database, "-e", sql]
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
    except FileNotFoundError:
        print("mysql client not found; use --mysql-bin or install MySQL client.", file=sys.stderr)
        raise SystemExit(1)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        raise SystemExit(proc.returncode)
    return parse_tsv(proc.stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, default=_MAG / "data" / "item_proc_meta.json")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--from-mysql",
        action="store_true",
        help="Query MySQL (see --mysql-* / MYSQL_* env).",
    )
    src.add_argument("--from-tsv", type=Path, help="Tab-separated id, procrate, proclevel, proceffect.")
    ap.add_argument("--mysql-bin", default=os.environ.get("MYSQL_BIN", "mysql"))
    ap.add_argument("--mysql-user", default=os.environ.get("MYSQL_USER", "root"))
    ap.add_argument("--mysql-password", default=os.environ.get("MYSQL_PASSWORD", ""))
    ap.add_argument("--mysql-host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    ap.add_argument("--mysql-database", default=os.environ.get("MYSQL_DATABASE", "peq"))
    args = ap.parse_args()

    if args.from_tsv:
        text = args.from_tsv.read_text(encoding="utf-8")
        rows = parse_tsv(text)
    else:
        rows = fetch_mysql(
            user=args.mysql_user,
            password=args.mysql_password,
            host=args.mysql_host,
            database=args.mysql_database,
            mysql_bin=args.mysql_bin,
        )

    meta = rows_to_meta(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Wrote {args.out} ({len(meta)} items)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
