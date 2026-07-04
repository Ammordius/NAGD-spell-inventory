# Magelo data exports

- **item_stats.json** – Item stats keyed by `item_id` (source: dkp/data/item_stats.csv). Fields: name, slot, ac, flags, mods, resists, effect, focus, required_level, **classes**, weight, size. Used for class usability and item details.
- **item_name_to_id.json** – Normalized item name → item_id (from raid_item_sources). Used by class rankings so item cards can resolve names to IDs even when item_stats is missing an entry. Generate with `python merge_dkp_loot_into_raid_sources.py --write-name-to-id`.
- **item_id_to_name.json** – Full item_id → display name map (primary source: PEQ `items` table). Used by the char timeline page (`char.html`) so Current Holdings and gear logs show real item names instead of `Item 12345`. Generate with `python scripts/build_item_id_to_name.py` (requires local PEQ MySQL). CI merges Magelo inventory names on top with `--skip-db`.
- **all_items.csv** – Same items as above in CSV form (item_id, name, slot, ac, flags, mods, resists, effect, focus, required_level, classes, weight, size).

## Raid item sources and item cards (parity with DKP loot)

So that item cards and mob tracker show **all** loot (including elemental patterns/molds and other DKP-only items):

1. **raid_item_sources.json** – Should include every item that can drop from raid/DKP mobs. It is built from `raid_items.txt` (extract_raid_item_sources.py) and does not initially include elemental or other DKP-only loot.
2. After you have an up-to-date **dkp_mob_loot.json** (e.g. from `build_dkp_mob_loot.py` or the dkp repo), merge and backfill names:
   ```bash
   python merge_dkp_loot_into_raid_sources.py --write-name-to-id
   ```
   This adds missing items, replaces placeholder names like `(item 28648)` with real names (e.g. "Cap of Flowing Time"), and writes **data/item_name_to_id.json** so the frontend can resolve magelo item names to IDs. Use `--dkp-loot ../dkp/data/dkp_mob_loot.json` if the path differs. Then commit the updated `raid_item_sources.json` and `data/item_name_to_id.json`.
3. Regenerate the full id→name map for char timeline pages:
   ```bash
   python scripts/build_item_id_to_name.py --inventory inventory/TAKP_character_inventory.txt
   ```
   Commit **data/item_id_to_name.json** (large file from PEQ `items` table). CI runs `--skip-db` daily to overlay Magelo inventory display names.
4. Regenerate item_stats so item cards resolve names and IDs for all loot (including merged items):
   ```bash
   python utils/update_focus_items_and_stats.py
   ```
   The script uses `raid_item_sources.json`, `raid_mob_loot.json`, and (by default) `../dkp/data/dkp_mob_loot.json` to build name↔id; it merges raid/DKP-only items into item_stats so class rankings item cards can show them.

## Regenerating data (from magelo repo, with dkp repo alongside)

```bash
python utils/update_focus_items_and_stats.py
```

That script also updates `spell_focii_level65.json` with item IDs and classes from raid loot + item_stats.
