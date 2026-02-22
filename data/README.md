# Magelo data exports

- **item_stats.json** – Item stats keyed by `item_id` (source: dkp/data/item_stats.csv). Fields: name, slot, ac, flags, mods, resists, effect, focus, required_level, **classes**, weight, size. Used for class usability and item details.
- **all_items.csv** – Same items as above in CSV form (item_id, name, slot, ac, flags, mods, resists, effect, focus, required_level, classes, weight, size).

Regenerate with (from magelo repo, with dkp repo alongside):

```bash
python utils/update_focus_items_and_stats.py
```

That script also updates `spell_focii_level65.json` with item IDs and classes from raid loot + item_stats.
