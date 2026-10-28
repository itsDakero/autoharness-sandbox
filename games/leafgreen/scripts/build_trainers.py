"""Extract every LeafGreen trainer battle and map it to the guide's areas.
Vs. Seeker rematches (src/vs_seeker.c sRematches) go in r = [[tier, party], ...]: tier 1 once you have the Vs. Seeker,
2 after visiting Celadon, 3 Fuchsia, 4 after the Champion, 5 after the National Dex. The newest tier you've reached wins."""
import re, os, json, sys, glob
R = sys.argv[1]; OUT = sys.argv[2]

src = open(os.path.join(R, 'src/data/trainer_parties.h')).read()
parties = {}
def blocks(body):
    out, depth, start = [], 0, None
    for i, ch in enumerate(body):
        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0: out.append(body[start+1:i])
    return out
for m in re.finditer(r'sParty_(\w+)\[\]\s*=\s*\{(.*?)\n\};', src, re.S):
    mons = []
    for blk in blocks(m.group(2)):
        sp = re.search(r'\.species\s*=\s*SPECIES_(\w+)', blk); lv = re.search(r'\.lvl\s*=\s*(\d+)', blk)
        if not sp or not lv: continue
        iv = re.search(r'\.iv\s*=\s*(\d+)', blk)
        mv = re.search(r'\.moves\s*=\s*\{([^}]*)\}', blk)
        moves = [x.replace('MOVE_', '').replace('_', '').lower() for x in re.findall(r'MOVE_\w+', mv.group(1))] if mv else []
        moves = [x for x in moves if x != 'none']
        mons.append([sp.group(1), int(lv.group(1)), int(iv.group(1)) if iv else 0, moves])
    parties[m.group(1)] = mons

tr = open(os.path.join(R, 'src/data/trainers.h')).read()
trainers = {}
for m in re.finditer(r'\[(TRAINER_\w+)\]\s*=\s*\{(.*?)\n    \},', tr, re.S):
    b = m.group(2)
    cls = re.search(r'\.trainerClass\s*=\s*(TRAINER_CLASS_\w+)', b)
    name = re.search(r'\.trainerName\s*=\s*_\("([^"]*)"\)', b)
    party = re.search(r'sParty_(\w+)', b)
    dbl = 'doubleBattle = TRUE' in b
    if cls and party:
        trainers[m.group(1)] = dict(cls=cls.group(1), name=name.group(1) if name else '', party=party.group(1), dbl=dbl)

cn = open(os.path.join(R, 'src/data/text/trainer_class_names.h')).read()
classnames = {m.group(1): m.group(2) for m in re.finditer(r'\[(TRAINER_CLASS_\w+)\]\s*=\s*_\("([^"]*)"\)', cn)}

# battles: (map, trainer const) in file order
battles = []
def scan(path, default_map=None):
    label = None
    for line in open(path):
        lm = re.match(r'^(\w+)::', line)
        if lm: label = lm.group(1)
        bm = re.search(r'trainerbattle_(single|double|no_intro|earlyrival)\s+(TRAINER_\w+)', line)
        if bm and label:
            mp = label.split('_EventScript')[0] if '_EventScript' in label else default_map
            battles.append((mp, bm.group(2), bm.group(1)))
scan(os.path.join(R, 'data/scripts/trainers.inc'))
for d in sorted(glob.glob(os.path.join(R, 'data/maps/*/scripts.inc'))):
    scan(d, os.path.basename(os.path.dirname(d)))

def area_of(mp):
    rules = [
        ('PalletTown', 'pallet'), ('Route22', 'route22'), ('ViridianForest', 'forest'), ('PewterCity', 'pewter'),
        ('Route3', 'route3'), ('Route4', 'mtmoon'), ('MtMoon', 'mtmoon'), ('CeruleanCity', 'cerulean'),
        ('Route24', 'nugget'), ('Route25', 'nugget'), ('Route6', 'route56'), ('Route5', 'route56'),
        ('SSAnne', 'vermilion'), ('VermilionCity_Gym', 'surge'), ('Route11', 'diglett'), ('Route9', 'rocktunnel'),
        ('Route10', 'rocktunnel'), ('RockTunnel', 'rocktunnel'), ('Route8', 'lavender'), ('Route7', 'lavender'),
        ('PokemonTower', 'tower'), ('CeladonCity_GameCorner', 'hideout'), ('RocketHideout', 'hideout'),
        ('CeladonCity', 'celadon'), ('Route12', 'route12'), ('Route13', 'route12'), ('Route14', 'route12'),
        ('Route15', 'route12'), ('Route16', 'route12'), ('Route17', 'route12'), ('Route18', 'route12'),
        ('FuchsiaCity', 'fuchsia'), ('SaffronCity', 'saffron'), ('SilphCo', 'saffron'), ('Route19', 'seafoam'),
        ('Route20', 'seafoam'), ('SeafoamIslands', 'seafoam'), ('PokemonMansion', 'cinnabar'), ('CinnabarIsland', 'cinnabar'),
        ('OneIsland', 'sevii'), ('TwoIsland', 'sevii'), ('ThreeIsland', 'sevii'), ('MtEmber', 'sevii'),
        ('Route21', 'powerplant'), ('PowerPlant', 'powerplant'), ('ViridianCity_Gym', 'viridiangym'),
        ('Route23', 'route23'), ('VictoryRoad', 'victoryroad'), ('PokemonLeague', 'league'),
        ('FourIsland', 'four'), ('FiveIsland', 'five'), ('SixIsland', 'six'), ('SevenIsland', 'seven'),
    ]
    for pre, a in rules:
        if mp.startswith(pre): return a
    return None

# Post-game battles on maps the story visits earlier: the Mt. Ember Rockets guarding the Ruby Path.
POSTGAME = {'TRAINER_TEAM_ROCKET_GRUNT_43': 'ruby', 'TRAINER_TEAM_ROCKET_GRUNT_44': 'ruby'}
BOSS_CLASSES = {'TRAINER_CLASS_LEADER', 'TRAINER_CLASS_ELITE_FOUR', 'TRAINER_CLASS_CHAMPION', 'TRAINER_CLASS_RIVAL_EARLY', 'TRAINER_CLASS_RIVAL_LATE', 'TRAINER_CLASS_BOSS'}
out = {}; seen = set(); skipped = {}; bosses = []
for mp, t, kind in battles:
    a = area_of(mp)
    if t in POSTGAME: a = POSTGAME[t]
    if not a: skipped[mp] = skipped.get(mp, 0) + 1; continue
    if t in seen or t not in trainers: continue
    seen.add(t)
    T = trainers[t]
    if T['cls'] in BOSS_CLASSES or kind == 'earlyrival':
        bosses.append(dict(c=t, p=[[s.replace('_', ' ').title(), l, iv, mv] for s, l, iv, mv in parties.get(T['party'], [])])); continue
    party = parties.get(T['party'], [])
    if not party: continue
    cname = classnames.get(T['cls'], T['cls']).title().replace('{Pkmn}', 'Pokémon').replace('Pkmn', 'Pokémon').replace('Team Rocket', 'Rocket')
    name = (cname + ' ' + T['name'].title()).strip()
    out.setdefault(a, []).append(dict(id=t.replace('TRAINER_', '').lower(), n=name, p=[[s.replace('_', ' ').title(), l, iv, mv] for s, l, iv, mv in party], d=T['dbl']))
vs = open(os.path.join(R, 'src/vs_seeker.c')).read()
rematch = {}
for m in re.finditer(r'\{\s*\{([^}]*)\},\s*MAP\(', vs):
    ids = [x.strip() for x in m.group(1).split(',') if x.strip()]
    rematch[ids[0]] = [[k, ids[k]] for k in range(1, len(ids)) if ids[k] != 'SKIP']
for a, lst in out.items():
    for T in lst:
        r = rematch.get('TRAINER_' + T['id'].upper())
        if r: T['r'] = [[k, [[s.replace('_', ' ').title(), l, iv, mv] for s, l, iv, mv in parties[trainers[t]['party']]]] for k, t in r]
out['_bosses'] = bosses
json.dump(out, open(OUT, 'w'), separators=(',', ':'))
print({k: len(v) for k, v in out.items()})
print('skipped maps', skipped)
