-- Item proc fields for magelo threat tooling (merge into data/item_proc_meta.json by item id).
SELECT id, procrate, proclevel, proceffect
FROM items
WHERE proceffect > 0 OR procrate != 0
ORDER BY id;
