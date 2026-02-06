# TAKP Mule Spell Inventory Generator

Automatically generates an HTML page showing which PoK spells are available on your mule characters.

## Setup

1. **Clone this repository** or create a new one on GitHub

2. **Add the spell exchange JSON file**:
   - Make sure `spell_exchange_list.json` is in the repository root
   - This file contains the mapping of PoK turn-in items to spells

3. **Enable GitHub Pages**:
   - Go to Settings → Pages
   - Source: Deploy from a branch
   - Branch: `gh-pages` / `root`

That's it! The workflow automatically downloads magelo data from [TAKP's export page](https://www.takproject.net/magelo/export/) daily.

## Manual Run

The workflow runs automatically daily at 2 AM UTC. You can also trigger it manually:
- Go to Actions tab → "Daily Spell Inventory Update" → "Run workflow"

It will also run automatically when you push changes to `generate_spell_page.py` or `spell_exchange_list.json`.

## Output

The generated HTML will be available at:
`https://YOUR_USERNAME.github.io/YOUR_REPO/spell_inventory.html`

## Local Development

To run locally:
```bash
python generate_spell_page.py
```

Make sure you have:
- `character/2_6_26.txt` - Character data
- `inventory/2_6_26.txt` - Inventory data  
- `../quests/poknowledge/spell_exchange_list.json` - Spell exchange data
