"""
Optional: run MySQL query and write item_proc_meta.json.

Requires: mysql client on PATH, or set MYSQL_* env and use pymysql (not bundled).

Example (manual):
  mysql -N -B -e \"SELECT id,procrate,proclevel,proceffect FROM items WHERE proceffect>0\" db > tsv
Then convert to JSON with a one-off script.

This file documents the workflow; extend with subprocess + your credentials if desired.
"""

from __future__ import annotations

print(__doc__)
