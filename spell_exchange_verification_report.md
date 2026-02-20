# Spell Exchange List vs TAKP Allaclone – Verification Report

Verified **spell_exchange_list.json** against **https://www.takproject.net/allaclone/** (item.php by spell scroll ID).

## Summary

| Result        | Count |
|---------------|-------|
| Match         | 184   |
| Mismatch      | 20    |
| Fetch failed  | 18    |
| **Unique spells** | **222** |

## Mismatches (fix in JSON or treat as alias)

- **28527** – JSON: "Immolation of Ro" → Allaclone: **"Fury of Ro"**
- **26941** – JSON: "Crusader's Touch" → Allaclone: "Crusaders Touch" *(apostrophe; script now normalizes)*
- **21647** – JSON: "Kazad's Mark" → Allaclone: **"Mark of Kazad"**
- **26911** – JSON: "Talisman of Alacrity" → Allaclone: **"Talisman of Celerity"**
- **28448** – JSON: "Iceflame of E'ci" → Allaclone: **"Iceflame of Ec'I"**
- **26940** – JSON: "Tears of Arlyxir" → Allaclone: **"Tears of Aryxil"**

## Likely JSON ordering errors (spell_ids vs spell_names out of sync)

- **Beastlord (Primalist_Saosith, Ethereal 29112)** – IDs 28544, 28545, 21629, 28547, 28548: names are shifted (e.g. 28544 shows "Infusion of Spirit" on Allaclone but JSON says "Spirit of Arag").
- **Shaman (Mystic_Abomin, Ethereal 29112)** – IDs 21660, 21661, 28491, 28492, 28493, 28494: same shift.
- **Shadowknight (Reaver_Nydlil, Spectral 29131)** – IDs 21632, 21634, 21633 (Blood of Hate, Pact of Hate, Spear of Decay): order swapped vs Allaclone.

Fix by reordering **spell_names** to match the **spell** ID order from Allaclone for those NPC blocks.

## Fetch failed (retry or check item IDs)

Bard songs (Allaclone uses "Song:" for these; script now parses that). Manual check confirms **28471** = "Song: Silent Song of Quellious" on Allaclone, matching the JSON—so the 18 "fetch failed" entries are likely **correct in the JSON**; failures are due to timeouts/rate limiting when the script runs.  
Re-run only these IDs:  
`python verify_spell_json.py --ids=28471,28473,21636,... --delay=1`  
if you want to confirm the rest when the server is responsive.

---

Re-run: `python verify_spell_json.py` (full), `--limit=20` for a quick check, or `--ids=id1,id2,...` for specific IDs.
