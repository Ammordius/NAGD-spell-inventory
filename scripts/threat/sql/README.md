# Item proc metadata export (optional)

`item_proc_meta.json` keys items by `id` with DB proc fields used by `build_weapon_threat_server.py`:

```json
{
  "12345": { "procrate": 0, "proclevel": 0, "proceffect": 2675 }
}
```

## MySQL export

Run `export_item_proc_meta.sql` against your live `items` table and save as JSON (or pipe through a small script). Example:

```bash
mysql -u USER -p DATABASE < export_item_proc_meta.sql > /tmp/proc.tsv
```

Then convert TSV to JSON keyed by item id, or run:

`python scripts/export_item_proc_meta.py --from-tsv /path/to/proc.tsv --out ../../data/item_proc_meta.json`

For a direct MySQL export:

`python scripts/export_item_proc_meta.py --from-mysql --mysql-database peq`

If `item_proc_meta.json` is empty `{}`, proc rate modifier defaults to **0** (proc chance uses base dex/delay only).
