# LeafGreen Field Notes

An interactive Pokémon LeafGreen walkthrough and Nuzlocke helper. One page on the phone while playing.
Port 8085 (`http://homelab:8085`, `leafgreen.lan`). The save lives in `/srv/homelab/leafgreen/state.json`.

Developer notes (files, data, logic, rules): see `CLAUDE.md` in this folder. Keep that one up to date.

## Using it

- **Play tab**: one page per area. Scroll down as you walk.
  1. **Story**: the to-dos for this area.
  2. **On the way**: trainers and items in walking order. The next one is marked. Trainers say who to send;
     "Fight help" gives live advice.
  3. **Big battle / level check**: battle plan, training advice, Vs. Seeker rematches.
  4. **Before you leave**: the item video (do it last, it sweeps up anything missed), items to come back for
     later, and the next area.
  Then the wild encounter log and your party (+1 when they level up).
- **Team tab**: best team (5 fighters + an HM mule until Victory Road), move advice, HM moves, training,
  Day Care, trades. "Keep in best team" on a card keeps a Pokémon (your starter, say) in the plan.
  "Make HM mule" picks the mule yourself. Team → More: Nuzlocke rules, Game Corner TMs (off by default).
- **Guide tab**: the full area reference (all to-dos, trainers, items, HMs, maps).
- **Pokédex tab**: what you have and where to get the rest.

## Deploy

```bash
cd ~/homelab && git pull && scripts/dc.sh games/leafgreen up -d --build
```

An open page reloads itself after a deploy.

## Rebuilding the data

Only needed when `src/walk.js` items or the game data change. The pret/pokefirered repo is the source:

```bash
python3 scripts/build_trainers.py <pokefirered repo> data/trainers.json
python3 scripts/build_route.py <pokefirered repo> data/route.json    # walking order; needs node
```
