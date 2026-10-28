"""Walking order for each guide area: trainers and items sorted along the path, from the pret/pokefirered maps.

Usage: python3 scripts/build_route.py <pokefirered repo> data/route.json
Needs data/maps and data/scripts from the repo. Writes {area: ["tr:<id>" | "i:<n>", ...]}: trainer ids as in
data/trainers.json, item indexes into WALK[area].items. Entries it can't place (gifts, shop items, unmatched) are
left out; the app adds them after the ordered ones.

Order: the area's maps in the order you reach them (breadth-first over map connections and warps, starting from the
map joined to an earlier area), and inside each map a nearest-neighbour walk from where you come in.
"""
import glob, json, os, re, sys, subprocess

R, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))

# Script labels -> body, from every map and shared script file.
bodies = {}
for path in glob.glob(os.path.join(R, 'data/maps/*/scripts.inc')) + glob.glob(os.path.join(R, 'data/scripts/*.inc')):
    label = None
    for line in open(path):
        m = re.match(r'^(\w+)::', line)
        if m: label = m.group(1); bodies[label] = ''; continue
        if label: bodies[label] += line

def follow(label, depth=0):
    """A script body plus the bodies it jumps to (one level), for item balls that call a shared script."""
    b = bodies.get(label, '')
    if depth < 1:
        for t in re.findall(r'(?:goto|call)\s+(\w+)', b): b += follow(t, depth + 1)
    return b

maps = {}
for mj in glob.glob(os.path.join(R, 'data/maps/*/map.json')):
    d = json.load(open(mj)); name = os.path.basename(os.path.dirname(mj))
    pts = []
    for o in d.get('object_events', []):
        if o.get('type') != 'object': continue
        b = follow(o.get('script', ''))
        t = re.search(r'trainerbattle_\w+\s+(TRAINER_\w+)', b)
        if t and o.get('trainer_type', 'TRAINER_TYPE_NONE') != 'TRAINER_TYPE_NONE':
            pts.append(dict(kind='tr', ref=t.group(1).replace('TRAINER_', '').lower(), x=o['x'], y=o['y'])); continue
        it = re.search(r'finditem\s+(ITEM_\w+)', b)
        if it and 'ITEM_BALL' in o.get('graphics_id', ''):
            pts.append(dict(kind='item', ref=it.group(1), hidden=False, x=o['x'], y=o['y']))
    for e in d.get('bg_events', []):
        if e.get('type') == 'hidden_item':
            ref = 'ITEM_COINS' if e['item'] == 'ITEM_NONE' and 'COINS' in e.get('flag', '') else e['item']
            pts.append(dict(kind='item', ref=ref, hidden=True, x=e['x'], y=e['y']))
    links = [(c['map'], c['direction']) for c in d.get('connections') or []]
    warps = [(w['dest_map'], w['x'], w['y']) for w in d.get('warp_events', [])]
    maps['MAP_' + re.sub(r'(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])', '_', name).upper()] = dict(name=name, pts=pts, links=links, warps=warps, id=d.get('id'))
# Use the map's own id (MAP_ROUTE4 etc.) as the key: the regex above is only a fallback.
maps = {v['id'] or k: v for k, v in maps.items()}

# Map -> guide area. First match wins, so put the specific ones first.
RULES = [
    ('PalletTown', 'pallet'), ('Route1', 'viridian'), ('ViridianCity_Gym', 'viridiangym'), ('ViridianCity', 'viridian'),
    ('Route22', 'route23'), ('Route23', 'route23'), ('Route2', 'forest'), ('ViridianForest', 'forest'),
    ('PewterCity', 'pewter'), ('Route3', 'route3'), ('Route4', 'mtmoon'), ('MtMoon', 'mtmoon'),
    ('CeruleanCity', 'cerulean'), ('Route24', 'nugget'), ('Route25', 'nugget'), ('Route5', 'route56'),
    ('Route6', 'route56'), ('UndergroundPath_EastWest', 'lavender'), ('UndergroundPath_East', 'lavender'),
    ('UndergroundPath_West', 'lavender'), ('UndergroundPath', 'route56'), ('VermilionCity_Gym', 'surge'), ('SSAnne', 'vermilion'),
    ('VermilionCity', 'vermilion'), ('Route11', 'diglett'), ('DiglettsCave', 'diglett'), ('Route9', 'rocktunnel'),
    ('Route10', 'rocktunnel'), ('RockTunnel', 'rocktunnel'), ('LavenderTown', 'lavender'), ('Route8', 'lavender'),
    ('Route7', 'lavender'), ('PokemonTower', 'tower'), ('CeladonCity_GameCorner', 'celadon'), ('RocketHideout', 'hideout'),
    ('CeladonCity', 'celadon'), ('Route12', 'route12'), ('Route13', 'route12'), ('Route14', 'route12'),
    ('Route15', 'route12'), ('Route16', 'route12'), ('Route17', 'route12'), ('Route18', 'route12'),
    ('FuchsiaCity', 'fuchsia'), ('SafariZone', 'fuchsia'), ('SaffronCity', 'saffron'), ('SilphCo', 'saffron'),
    ('Route19', 'seafoam'), ('Route20', 'seafoam'), ('SeafoamIslands', 'seafoam'), ('PokemonMansion', 'cinnabar'),
    ('CinnabarIsland', 'cinnabar'), ('OneIsland', 'sevii'), ('TwoIsland', 'sevii'), ('ThreeIsland', 'sevii'),
    ('MtEmber', 'sevii'), ('Route21', 'powerplant'), ('PowerPlant', 'powerplant'), ('VictoryRoad', 'victoryroad'),
    ('PokemonLeague', 'league'), ('FourIsland', 'four'), ('FiveIsland', 'five'), ('SixIsland', 'six'),
    ('SevenIsland', 'seven'), ('CeruleanCave', 'ceruleancave'),
]
def area_of(name):
    for pre, a in RULES:
        # "Route1" must not match Route11: the next character can't be a digit.
        if name.startswith(pre) and not name[len(pre):len(pre) + 1].isdigit(): return a
    return None

# Guide data (WALK, ITEM_AFTER...) via node, so the item list is exactly the app's.
walk = json.loads(subprocess.check_output(['node', '-e', '''
const fs=require('fs'); const s=fs.readFileSync(process.argv[1],'utf8');
eval(s.replace(/^const /gm,'var ')); console.log(JSON.stringify(WALK.map(a=>({id:a.id,items:a.items}))));
''', os.path.join(HERE, '..', 'src', 'walk.js')]))
trainers = json.load(open(os.path.join(HERE, '..', 'data', 'trainers.json')))

def norm_walk(name):
    m = re.match(r'(TM|HM)(\d\d)', name)
    if m: return m.group(1) + m.group(2)
    name = re.sub(r'\s*\(.*?\)|\s*×\s*\d+.*$', '', name)   # "Coins ×10 (more)" -> "Coins"
    return re.sub(r'[^A-Z0-9]', '', name.upper().replace('É', 'E'))
def norm_item(item):
    return re.sub(r'[^A-Z0-9]', '', item.replace('ITEM_', '').upper())
ALIAS = {'COIN': 'COINS', 'POKEBALL': 'POKEBALL'}

def nn_order(pts, start):
    """Nearest-neighbour walk from `start` (x, y); Manhattan distance."""
    left, out, cur = pts[:], [], start
    while left:
        p = min(left, key=lambda q: abs(q['x'] - cur[0]) + abs(q['y'] - cur[1]))
        left.remove(p); out.append(p); cur = (p['x'], p['y'])
    return out

EDGE = {'up': lambda w, h: (w // 2, 0), 'down': lambda w, h: (w // 2, h), 'left': lambda w, h: (0, h // 2), 'right': lambda w, h: (w, h // 2)}
OPP = {'up': 'down', 'down': 'up', 'left': 'right', 'right': 'left'}

# Where you walk in, when the map graph guesses wrong (both gates of a forest look the same to it).
ENTRY = {'ViridianForest': 'down', 'Route2': 'down', 'RockTunnel_1F': 'up', 'Route10': 'up', 'Route9': 'left'}
SHARED = {'cerulean': ['Route4'], 'diglett': ['Route2'], 'powerplant': ['Route10']}
out = {}
area_maps = {}
for mid, m in maps.items():
    a = area_of(m['name'])
    if a: area_maps.setdefault(a, []).append(mid)
    for sa, names in SHARED.items():
        if m['name'] in names: area_maps.setdefault(sa, []).append(mid)
seen_before = set()
for ai, A in enumerate(walk):
    a = A['id']; mids = set(area_maps.get(a, []))
    if not mids: seen_before |= set(); continue
    # Start: a map of this area joined to a map of an earlier area (else the first by name).
    def joined_to(mid, pool):
        m = maps[mid]
        for dest, d in m['links']:
            if dest in pool: return (dest, d)
        for dest, x, y in m['warps']:
            if dest in pool: return (dest, (x, y))
        return None
    starts = [mid for mid in sorted(mids) if joined_to(mid, seen_before)]
    queue = [starts[0] if starts else sorted(mids)[0]]; order = []; entry = {}
    j = joined_to(queue[0], seen_before)
    if j: entry[queue[0]] = j[1]
    while queue:
        mid = queue.pop(0)
        if mid in order: continue
        order.append(mid); m = maps[mid]
        for dest, d in m['links']:
            if dest in mids and dest not in order and dest not in queue: queue.append(dest); entry.setdefault(dest, OPP[d])
        for dest, x, y in m['warps']:
            if dest in mids and dest not in order and dest not in queue:
                queue.append(dest)
                back = [(xx, yy) for dd, xx, yy in maps[dest]['warps'] if dd == mid]
                entry.setdefault(dest, back[0] if back else None)
        if not queue:
            rest = sorted(mids - set(order))
            if rest: queue.append(rest[0])
    path = []
    for mid in order:
        m = maps[mid]; pts = m['pts']
        if not pts: continue
        w = max([p['x'] for p in pts] + [1]); h = max([p['y'] for p in pts] + [1])
        e = ENTRY.get(m['name'], entry.get(mid))
        if isinstance(e, str):
            # Walked in from an edge (a route): go along it, away from that edge. Steadier than nearest-neighbour,
            # which leaves side paths near the entrance until last.
            key = {'down': lambda p: -p['y'], 'up': lambda p: p['y'], 'left': lambda p: p['x'], 'right': lambda p: -p['x']}[e]
            for p in sorted(pts, key=key): path.append((mid, p))
        else:
            for p in nn_order(pts, e if e else (0, h)): path.append((mid, p))
    # Match walk items to map items: same item and same hidden flag, first unused in path order.
    keys, used, tr_ids = [], set(), {t['id'] for t in trainers.get(a, [])}
    wantI = {}
    for i, it in enumerate(A['items']):
        flag = it[2] if len(it) > 2 else ''
        if flag in ('g', 'b', 's'): continue
        wantI.setdefault((norm_walk(it[0]), flag == 'h'), []).append(i)
    for mid, p in path:
        if p['kind'] == 'tr':
            if p['ref'] in tr_ids and 'tr:' + p['ref'] not in keys: keys.append('tr:' + p['ref'])
            continue
        k = (ALIAS.get(norm_item(p['ref']), norm_item(p['ref'])), p['hidden'])
        lst = wantI.get(k)
        if lst:
            # Prefer the walk item whose text names this map ("Route 13: ..."), else the first one left.
            rn = re.match(r'Route(\d+)', maps[mid]['name'])
            pick = next((i for i in lst if rn and re.search(r'Route %s\b' % rn.group(1), A['items'][i][1])), lst[0])
            lst.remove(pick); keys.append('i:%d' % pick)
    out[a] = keys
    seen_before |= mids - {mid for mid in mids if maps[mid]['name'] in SHARED.get(a, [])}

json.dump(out, open(OUT, 'w'), separators=(',', ':'))
for A in walk:
    k = out.get(A['id'], []); n_i = sum(1 for x in k if x.startswith('i:')); n_t = sum(1 for x in k if x.startswith('tr:'))
    placeable = sum(1 for it in A['items'] if (it[2] if len(it) > 2 else '') not in ('g', 'b', 's'))
    print(f"{A['id']:13} items {n_i}/{placeable} trainers {n_t}/{len(trainers.get(A['id'], []))}")
