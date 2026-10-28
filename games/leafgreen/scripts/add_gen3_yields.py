"""Add Gen 3 EXP yield (x) and catch rate (c) to data/game.json from the pret/pokefirered decompilation.
PokeAPI's base_experience is from later games, so it's wrong for some Gen 3 Pokemon.
Usage: python3 scripts/add_gen3_yields.py <pokefirered>/src/data/pokemon/species_info.h data/game.json"""
import json, re, sys

src, out = sys.argv[1], sys.argv[2]
text = open(src, encoding='utf-8').read()
blocks = {m.group(1): m.group(2) for m in re.finditer(r'\[SPECIES_(\w+)\]\s*=(.*?)(?=\[SPECIES_|\Z)', text, re.S)}
key = lambda s: re.sub(r'[^a-z0-9]', '', s.lower().replace('♀', 'f').replace('♂', 'm'))
by_key = {key(k): v for k, v in blocks.items()}
d = json.load(open(out, encoding='utf-8'))
missing = []
for pid, p in d['pokemon'].items():
    b = by_key.get(key(p['n']))
    if not b:
        missing.append(p['n']); continue
    p['x'] = int(re.search(r'\.expYield\s*=\s*(\d+)', b).group(1))
    p['c'] = int(re.search(r'\.catchRate\s*=\s*(\d+)', b).group(1))
if missing:
    sys.exit('No species_info entry for: ' + ', '.join(missing))
json.dump(d, open(out, 'w', encoding='utf-8'), separators=(',', ':'))
print('added x/c to', len(d['pokemon']), 'species')
