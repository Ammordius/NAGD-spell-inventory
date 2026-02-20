import json
import time
import re
import sys
import os
import requests
from bs4 import BeautifulSoup

# TAKP Allaclone base URL for item (spell scroll) lookups
ALLACLONE_ITEM_URL = "https://www.takproject.net/allaclone/item.php?id={id}"

def normalize_name(name):
    """
    Normalizes the name to make comparison easier.
    Removes 'Spell: ', 'Scroll: ', ignores case/trailing whitespaces,
    and treats apostrophe variants as equal (e.g. "Crusader's" vs "Crusaders").
    """
    if not name:
        return ""
    name = name.lower().strip()
    name = re.sub(r"^(spell|scroll|song|tome):\s*", "", name)
    # Allaclone sometimes omits apostrophes (e.g. "Crusaders Touch")
    name = re.sub(r"'", "", name)
    return name

def extract_expected_spells(data):
    """
    Extracts a dictionary mapping spell_id to expected spell_name 
    from the nested JSON structure.
    """
    spell_map = {}
    items = data.get("items", {})
    
    for item_id, item_data in items.items():
        for npc in item_data.get("npcs", []):
            spells = npc.get("spells", [])
            spell_names = npc.get("spell_names", [])
            
            for s_id, s_name in zip(spells, spell_names):
                # Using a dictionary automatically handles duplicates
                spell_map[s_id] = s_name
                
    return spell_map

def fetch_canonical_name(spell_id):
    """
    Fetches the item page from TAKP Allaclone and parses out the spell/item name.
    """
    url = ALLACLONE_ITEM_URL.format(id=spell_id)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        title_text = (soup.title.string or "").strip()
        
        # TAKP Allaclone title format: "Name \" TAKP AllaClone :: Spell: Name" or "Song: Name" for bard songs
        if title_text:
            # Prefer "Spell: <name>" or "Song: <name>" when present (canonical form)
            for prefix in ("Spell:", "Song:"):
                idx = title_text.find(prefix)
                if idx >= 0:
                    name = title_text[idx + len(prefix):].strip()
                    if name.startswith(":"):
                        name = name[1:].strip()
                    for sep in (" - ", " :: ", " \""):
                        if sep in name:
                            name = name.split(sep)[0].strip()
                    if name:
                        return name
            # Else take the first segment before " - " or " :: "
            for sep in (" - ", " :: "):
                if sep in title_text:
                    canonical_name = title_text.split(sep)[0].strip().rstrip(' "')
                    if canonical_name and "AllaClone" not in canonical_name:
                        return canonical_name
            if title_text and "AllaClone" not in title_text:
                return title_text.rstrip(' "')
        
        # Fallback: look for "Spell: <name>" in page body (e.g. first heading)
        spell_heading = soup.find(string=re.compile(r"Spell:\s*\S", re.I))
        if spell_heading:
            m = re.search(r"Spell:\s*(.+)", spell_heading.strip(), re.I)
            if m:
                return m.group(1).strip()
            
    except requests.exceptions.RequestException as e:
        print(f"Error fetching ID {spell_id}: {e}")
        
    return None

def main():
    # Load spell exchange list: spell_exchange_list.json next to this script or from cwd
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_paths = [
        os.path.join(script_dir, "spell_exchange_list.json"),
        "spell_exchange_list.json",
    ]
    json_path = None
    for p in json_paths:
        if os.path.isfile(p):
            json_path = p
            break
    if not json_path:
        print("spell_exchange_list.json not found. Run from magelo/ or pass path.")
        sys.exit(1)

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {json_path}: {e}")
        sys.exit(1)

    expected_spells = extract_expected_spells(data)
    total_spells = len(expected_spells)

    # Optional: --limit N for a quick test run
    limit = None
    for arg in sys.argv[1:]:
        if arg.startswith("--limit="):
            limit = int(arg.split("=", 1)[1])
            break
        if arg == "--limit" and len(sys.argv) > sys.argv.index(arg) + 1:
            limit = int(sys.argv[sys.argv.index(arg) + 1])
            break
    if limit is not None:
        expected_spells = dict(list(expected_spells.items())[:limit])
        total_spells = len(expected_spells)
        print(f"(Limited to first {total_spells} spells)\n")

    # Optional: --ids=id1,id2,... to verify only those spell IDs
    ids_only = None
    for arg in sys.argv[1:]:
        if arg.startswith("--ids="):
            ids_only = [int(x.strip()) for x in arg.split("=", 1)[1].split(",") if x.strip()]
            break
    if ids_only is not None:
        expected_spells = {k: v for k, v in expected_spells.items() if k in ids_only}
        total_spells = len(expected_spells)
        print(f"(Verifying only {total_spells} requested IDs)\n")

    delay = 1.0
    if "--delay=" in " ".join(sys.argv):
        for a in sys.argv[1:]:
            if a.startswith("--delay="):
                delay = float(a.split("=", 1)[1])
                break
    
    print(f"Verifying {total_spells} unique spells against TAKP Allaclone ({json_path}).\n")
    
    mismatches = []
    failed = []
    
    for i, (spell_id, expected_name) in enumerate(expected_spells.items(), 1):
        print(f"[{i}/{total_spells}] ID {spell_id} ({expected_name})...", end=" ", flush=True)
        
        canonical_name = fetch_canonical_name(spell_id)
        
        if canonical_name is None:
            print("FAILED (Could not fetch)")
            failed.append({"id": spell_id, "expected": expected_name})
            if delay > 0:
                time.sleep(delay)
            continue
            
        norm_expected = normalize_name(expected_name)
        norm_canonical = normalize_name(canonical_name)
        
        if norm_expected == norm_canonical:
            print(f"OK")
        else:
            print(f"MISMATCH (Allaclone: '{canonical_name}')")
            mismatches.append({
                "id": spell_id, 
                "expected": expected_name, 
                "canonical": canonical_name
            })
            
        if delay > 0:
            time.sleep(delay)

    print("\n--- Verification Complete ---")
    if failed:
        print(f"Fetch failed: {len(failed)}")
        for m in failed[:20]:
            print(f"  ID {m['id']}: {m['expected']}")
        if len(failed) > 20:
            print(f"  ... and {len(failed) - 20} more")
    if mismatches:
        print(f"Mismatches: {len(mismatches)}")
        for m in mismatches:
            print(f"  ID {m['id']}: JSON '{m['expected']}' vs Allaclone '{m['canonical']}'")
    if not failed and not mismatches:
        print("All spell names match TAKP Allaclone.")

if __name__ == "__main__":
    main()
