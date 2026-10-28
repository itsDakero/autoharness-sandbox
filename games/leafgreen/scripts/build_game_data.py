"""Build compact LeafGreen (Gen 3, FRLG) data JSON from PokeAPI CSVs."""
import csv, json, sys, os
from collections import defaultdict

D = sys.argv[1]
OUT = sys.argv[2]
VG = 7          # firered-leafgreen
LG = 11         # leafgreen version id
GEN = 3

def rows(name):
    with open(os.path.join(D, name + '.csv'), newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))

def i(x):
    return int(x) if x not in (None, '') else None

# ---- types ----
types = {int(r['id']): r['identifier'] for r in rows('types') if int(r['id']) <= 17}
TYPE_NAMES = {k: v.capitalize() for k, v in types.items()}

# type chart for gen 3
eff = {}
for r in rows('type_efficacy'):
    a, b = int(r['damage_type_id']), int(r['target_type_id'])
    if a in types and b in types:
        eff[(a, b)] = int(r['damage_factor'])
past = defaultdict(list)
for r in rows('type_efficacy_past'):
    g = int(r['generation_id'])
    if g >= GEN:
        past[(int(r['damage_type_id']), int(r['target_type_id']))].append((g, int(r['damage_factor'])))
for k, v in past.items():
    if k[0] in types and k[1] in types:
        eff[k] = sorted(v)[0][1]
chart = {}
for (a, b), f in eff.items():
    if f != 100:
        chart.setdefault(TYPE_NAMES[a], {})[TYPE_NAMES[b]] = f / 100

# ---- moves ----
dmg_class = {1: 'status', 2: 'physical', 3: 'special'}
SPECIAL_TYPES = {'Fire', 'Water', 'Grass', 'Electric', 'Ice', 'Psychic', 'Dragon', 'Dark'}
names = {}
for r in rows('move_names'):
    if r['local_language_id'] == '9':
        names[int(r['move_id'])] = r['name']
moves = {}
for r in rows('moves'):
    mid = int(r['id'])
    if i(r['generation_id']) > GEN:
        continue
    moves[mid] = dict(t=i(r['type_id']), p=i(r['power']), pp=i(r['pp']), a=i(r['accuracy']),
                      c=dmg_class[int(r['damage_class_id'])], pr=i(r['priority']), e=i(r['effect_id']))
chg = defaultdict(list)
for r in rows('move_changelog'):
    vg = int(r['changed_in_version_group_id'])
    if vg > VG:
        chg[int(r['move_id'])].append((vg, r))
for mid, lst in chg.items():
    if mid not in moves:
        continue
    # apply from latest to earliest so the earliest change after FRLG wins
    for vg, r in sorted(lst, reverse=True):
        for key, col in (('t', 'type_id'), ('p', 'power'), ('pp', 'pp'), ('a', 'accuracy'), ('pr', 'priority'), ('e', 'effect_id')):
            if r[col] != '':
                moves[mid][key] = int(r[col])
move_out = {}
for mid, m in moves.items():
    tname = TYPE_NAMES.get(m['t'], '???')
    cat = m['c']
    if cat != 'status':
        cat = 'special' if tname in SPECIAL_TYPES else 'physical'
    move_out[mid] = dict(n=names.get(mid, str(mid)), t=tname, p=m['p'] or 0, a=m['a'], pp=m['pp'], c=cat, pr=m['pr'] or 0, e=m['e'])

# ---- TMs / HMs in FRLG ----
item_names = {int(r['item_id']): r['name'] for r in rows('item_names') if r['local_language_id'] == '9'}
machines = {}
for r in rows('machines'):
    if int(r['version_group_id']) == VG:
        num = int(r['machine_number'])
        label = ('HM%02d' % (num - 100)) if num > 100 else ('TM%02d' % num)
        machines[int(r['move_id'])] = label

# ---- species ----
sp_names = {int(r['pokemon_species_id']): r['name'] for r in rows('pokemon_species_names') if r['local_language_id'] == '9'}
species = {int(r['id']): r for r in rows('pokemon_species') if int(r['id']) <= 386}
ptypes = defaultdict(list)
for r in rows('pokemon_types'):
    pid = int(r['pokemon_id'])
    if pid <= 386:
        ptypes[pid].append((int(r['slot']), int(r['type_id'])))
past_t = defaultdict(list)
for r in rows('pokemon_types_past'):
    g = int(r['generation_id'])
    pid = int(r['pokemon_id'])
    if g >= GEN and pid <= 386:
        past_t[pid].append((g, int(r['slot']), int(r['type_id'])))
for pid, lst in past_t.items():
    g0 = min(x[0] for x in lst)
    ptypes[pid] = [(s, t) for g, s, t in lst if g == g0]
stats = defaultdict(dict)
STAT = {1: 'hp', 2: 'atk', 3: 'def', 4: 'spa', 5: 'spd', 6: 'spe'}
for r in rows('pokemon_stats'):
    pid = int(r['pokemon_id'])
    if pid <= 386:
        stats[pid][STAT[int(r['stat_id'])]] = int(r['base_stat'])

learn = defaultdict(lambda: {'lv': [], 'tm': [], 'tu': []})
for r in rows('pokemon_moves'):
    if r['version_group_id'] != str(VG):
        continue
    pid = int(r['pokemon_id'])
    if pid > 386:
        continue
    mid = int(r['move_id'])
    meth = int(r['pokemon_move_method_id'])
    if meth == 1:
        learn[pid]['lv'].append([int(r['level'] or 1), mid])
    elif meth == 4:
        learn[pid]['tm'].append(mid)
    elif meth == 3:
        learn[pid]['tu'].append(mid)

evo = defaultdict(list)   # from species -> list of (to, how)
trig = {int(r['id']): r['identifier'] for r in rows('evolution_triggers')}
for r in rows('pokemon_evolution'):
    to = int(r['evolved_species_id'])
    if to > 386:
        continue
    frm = i(species[to]['evolves_from_species_id'])
    if frm is None:
        continue
    t = trig.get(int(r['evolution_trigger_id']))
    how = ''
    if t == 'level-up':
        if r['minimum_level']:
            how = 'Lv %s' % r['minimum_level']
        elif r['minimum_happiness']:
            how = 'High friendship'
        else:
            how = 'Level up'
    elif t == 'use-item':
        how = item_names.get(int(r['trigger_item_id']), 'Item')
    elif t == 'trade':
        how = 'Trade'
    else:
        how = t or ''
    e = [to, how]
    if e not in evo[frm]:
        evo[frm].append(e)

pk_out = {}
for pid in sorted(species):
    if pid not in learn:
        continue
    lv = sorted(learn[pid]['lv'])
    pk_out[pid] = dict(
        n=sp_names.get(pid, species[pid]['identifier']),
        t=[TYPE_NAMES[t] for s, t in sorted(ptypes[pid])],
        s=stats[pid],
        lv=lv,
        tm=sorted(learn[pid]['tm']),
        tu=sorted(learn[pid]['tu']),
        ev=evo.get(pid, []),
        pre=i(species[pid]['evolves_from_species_id']),
        g=i(species[pid]['growth_rate_id']),   # EXP group: 1 slow, 2 medium, 3 fast, 4 medium-slow, 5 erratic, 6 fluctuating
    )

# ---- LeafGreen encounters ----
la = {int(r['id']): (int(r['location_id']), r['identifier']) for r in rows('location_areas')}
loc_ident = {int(r['id']): r['identifier'] for r in rows('locations')}
loc_name = {int(r['location_id']): r['name'] for r in rows('location_names') if r['local_language_id'] == '9'}
slots = {int(r['id']): (int(r['encounter_method_id']), int(r['rarity'] or 0)) for r in rows('encounter_slots')}
meth = {int(r['id']): r['identifier'] for r in rows('encounter_methods')}
enc = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: [999, 0, 0])))
for r in rows('encounters'):
    if int(r['version_id']) != LG:
        continue
    aid = int(r['location_area_id'])
    lid, aident = la[aid]
    key = loc_ident.get(lid, str(lid)) + ((' / ' + aident) if aident else '')
    m, rar = slots[int(r['encounter_slot_id'])]
    pid = int(r['pokemon_id'])
    rec = enc[key][meth[m]][pid]
    rec[0] = min(rec[0], int(r['min_level']))
    rec[1] = max(rec[1], int(r['max_level']))
    rec[2] += rar
enc_out = {}
for key, ms in enc.items():
    enc_out[key] = {mm: sorted([[pid, *v] for pid, v in d.items()], key=lambda x: -x[3]) for mm, d in ms.items()}

json.dump(dict(types=list(TYPE_NAMES.values()), chart=chart, moves=move_out, machines=machines,
               pokemon=pk_out, encounters=enc_out), open(OUT, 'w'), separators=(',', ':'))
print('pokemon', len(pk_out), 'moves', len(move_out), 'machines', len(machines), 'enc areas', len(enc_out))
