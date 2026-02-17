#!/usr/bin/env python3
"""Parse instruments.html and output (section, id, name, mod) for each item."""
import re
import json

with open('instruments.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Row pattern: ...id=NUM">NAME</a>\n</td>\n<td>+MOD%</td>
pat = re.compile(
    r'item\.php\?id=(\d+)\">([^<]+)</a>\s*</td>\s*<td>\+(\d+)%',
    re.DOTALL
)

# Split by section (All, Brass, Percussion, Singing, Strings, Wind)
section_heads = list(re.finditer(r'<h1[^>]*><span[^>]*class="mw-headline"[^>]*id="(All|Brass|Percussion|Singing|Strings|Wind)"', content))
results = []
for i, head in enumerate(section_heads):
    section = head.group(1)
    start = head.start()
    end = section_heads[i + 1].start() if i + 1 < len(section_heads) else len(content)
    block = content[start:end]
    for m in pat.finditer(block):
        results.append({
            'instrument_type': section,
            'item_id': m.group(1),
            'name': m.group(2).strip(),
            'mod': int(m.group(3)),
        })

print(json.dumps(results, indent=2))
print(f'\nTotal items: {len(results)}', file=__import__('sys').stderr)
