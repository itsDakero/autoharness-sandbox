# LeafGreen Field Notes

A single-page web app: an interactive Pokémon LeafGreen walkthrough and Nuzlocke helper.
The owner is playing a "soft" Nuzlocke (nickname everything, fainted = gone, no first-encounter rule) and wants to complete the Pokédex. They are dyslexic: keep UI copy in short sentences and bullets.

## Build and test

Hosted in the homelab as `leafgreen` (port 8085, `http://homelab:8085`, `leafgreen.lan`).
The image runs `assemble.py` itself, so deploying = rebuilding the image.

```bash
python3 scripts/assemble.py           # src/ + data/ -> dist/index.html (one self-contained file, gitignored)
# No Node on the host: run the smoke tests in a pinned container
docker run --rm --network none -v "$PWD":/app:ro -w /app node:22.23.3-alpine node tests/run.js
docker run --rm --network none -v "$PWD":/app:ro -w /app node:22.23.3-alpine node tests/run.js tests/sample-save.json
docker run --rm --network none -v "$PWD":/app:ro -w /app node:22.23.3-alpine node tests/run.js tests/save-diglett.json   # a real save that once crashed Play
scripts/dc.sh games/leafgreen up -d --build   # from the repo root: deploy
```

Always rebuild `dist/index.html` before testing after editing `src/` or `data/`. Never edit `dist/` by hand.

## Files

- `server.py`, `Dockerfile`, `compose.yaml`: the homelab service.
- `src/app.html`: all UI, CSS and logic. Placeholders `/*__DATA__*/`, `/*__TRAINERS__*/`, `/*__ROUTE__*/`, `/*__WALK__*/` are filled by `assemble.py`.
- `src/walk.js`: hand-written content. `WALK` (35 areas: 29 story, then 6 post-game: National Dex/Ruby, Sevii 4–7, Cerulean Cave; to-dos, items with h/g/b/s flags, wild encounter keys, bosses), `GIFTS` (to-do → gift item indexes; ticking the to-do ticks them, `syncGifts` once per save for old ticks), `TRADES` (in-game trades: to-do key, give/get species ids, fixed nickname), `CATCH_SPOTS` (one-off catches), `ITEM_AFTER` (items locked until a story to-do in a later area), `ITEM_VIDEOS` (Techno Trainer's YouTube "EVERY Item Location" videos per area), `BOSSES` (gym leaders, rivals by starter, Elite Four), `TUTORS`, `MAP_LINKS` (Bulbapedia pages).
- `data/game.json`: LeafGreen game data from PokeAPI (Gen 3 types, stats, EXP group `g`, learnsets, TMs, move power/category, LeafGreen-only encounters). Built by `scripts/build_game_data.py <pokeapi csv dir> data/game.json`, then
  `scripts/add_gen3_yields.py <pokefirered>/src/data/pokemon/species_info.h data/game.json` adds Gen 3 EXP yield `x`
  and catch rate `c` (PokeAPI's base EXP is from later games).
- `data/route.json`: walking order per area (`["tr:<id>" | "i:<n>", ...]`), from map positions in pret/pokefirered
  (`data/maps`, `data/scripts`). Built by `scripts/build_route.py <pokefirered repo> data/route.json` (needs node and
  `data/trainers.json`): maps in the order you reach them (map links and warps), inside a map along the route from where
  you walk in (`ENTRY` fixes wrong guesses, `SHARED` = maps two areas split). Rebuild it after adding walk items.
- `data/trainers.json`: every story trainer's party (species, level, IV, moves) from the pret/pokefirered decompilation, keyed by guide area; `_bosses` holds boss/rival parties; `r` = Vs. Seeker rematch parties `[[tier, party]]` from `src/vs_seeker.c`. `POSTGAME` moves post-game battles on early maps (Mt. Ember Rockets) to their post-game area. Built by `scripts/build_trainers.py <pokefirered repo> data/trainers.json`.

## Key rules baked into the logic

- `WALK` items and to-dos are ticked by index (`<area>:i:<n>`, `<area>:t:<n>` in `S.done`): only append, never insert,
  reorder or delete, or saved ticks move to the wrong line.
- Item spots from stage 4 (Routes 5–7, 12–17, all of Sevii, Cerulean Cave) are tile offsets read from the
  pret/pokefirered `data/maps/*/map.json` files, measured from a sign, door, trainer or other item.

- Gen 3: move category is by type (Fire/Water/Grass/Electric/Ice/Psychic/Dragon/Dark are special). `catTag(mid)` = the P/S tag ("Fixed" for `isFixed`: Seismic Toss, Night Shade, Super Fang…)
  shown next to moves (move lists, advice, battle plans, fights, encounters); `attackerLine(sp)` on Team cards.
- Only LeafGreen encounters. Only Fire/Water/Thunder/Leaf/Moon Stones exist. No trade evolutions (owner can't trade: the Switch version trades by local wireless only, and Pokémon HOME is deposit-only).
- One-copy TMs and tutors are shared across the team, never suggested twice. One owner for the Team tab's move advice
  and the Best team card: `carryPlan().tmOwner` (move id -> team index or `'catch'`), owned Pokémon claim first, and a
  catch loses a TM your party's advice teaches now, with a "hold off" note both ways (`tmHold`, `c.hold` on the
  change). `teamAdvice` = `teamAdviceWith(indices, tmOwner)` + those notes. `oneCopy(t)`.
- Game Corner TMs (`s` items, 3,500–4,500 coins ≈ ₽80,000) only when `S.coinTMs` is on (Team → More; off by default:
  the owner can't afford them). Then kind `tmcoin` (`PEN.tmcoin`), one copy, text from `coinText`.
- Kept Pokémon (`m.fav`, "Keep in best team" on the card; for the starter) are always in the carry plan's six and never
  swapped out; the others are picked around them.
- Gone Pokémon are excluded from every plan: fainted (`dead: true`, `died: {a: area, t}`), sent to Pokémon HOME
  (`home: true`; HOME is one-way) or traded away in-game (`traded: <to-do key>`). Use `gone(m)`, not `m.dead`. All still count for the Pokédex.
- In-game trades are possible (link trades are not). The owner's rule: fainted Pokémon may be traded.

## Main features (search these function names in `src/app.html`)

- Play tab (default; one scrolling page per area, `renderPlay`): 1 Story (to-dos), 2 On the way (`walkRows`: trainers and
  items in walking order from `ROUTE`, then any it couldn't place; gifts/shops/coins in a fold; ticked rows shrink to one
  line; the first open row is "Next" (`#next`); the next 3 trainers show who to send, `trainerHint`, and "Fight help"),
  3 Big battle / Level check (boss buttons, `renderCap`, training, `renderRematches`), 4 Before you leave (item video
  = the sweep, done last; locked items to come back for; next area), then the encounter log and party. `itemGate` / `gateOpen` hold back items behind an HM you get in
  that area or later ("needs Cut", "(Surf)" in the spot text) or an `ITEM_AFTER` step; `renderComeBack` lists earlier
  areas whose locked items are open now (Go sets `S.back`, so the area's done card offers "Back to …"),
  `vidBtns` / `renderVideo` (item video in step 4; the player is in `#vid`, outside `#main`, so a re-render
  doesn't restart it, and the page doesn't self-reload while one is open),
  `renderCap` (next boss vs best level, + `renderBench`: `bossBench` = PC Pokémon that safely answer some of the next
  boss's team at real levels, swapped for party ones that can't help (duel < 40; never an HM user or the Exp. Share
  holder); `benchWhy` says what can't hurt it / which move / which to avoid; also on Battles), `renderPartyQuick` + `levelUpPrompts` (+1, move learn/skip, evolve),
  `renderEncounter` (log Caught / Fainted / Ran to `S.log`, rename the catch), `speak` (read aloud, Web Speech).
- Trades (`TRADES`, Play and Team): `tradeInfo` (who to give: fainted first; would the new one join `carryPlan`
  (re-run with it added); new Pokédex entry; cost), `tradeBody` (advice + Traded ✓ / Skip / Later), `renderTradesDue`
  (Play: ticked but not recorded, or doable now in another area), `renderTrades` (Team → More, with Undo). A trade sets
  `S.trades[k]`, `m.traded = k` on the one given and pushes the new one with `tr: k`, `ot: true` (1.5x EXP; may disobey
  above `obeyCap()`), at the given one's level. Optional to-dos (text has "optional") get Skip: `S.done[k] = 'skip'`
  (`'later'` = trade to do once you own the Pokémon). `bestTeamPrompt` after a catch or trade.
- Live battle helper (Play tab, `S.fight`; started by "Fight help" on a trainer or boss row, rematches in `renderRematches`): `renderFight`, `matchups` (party ranked by
  one-hit-KO risk, then expected damage taken before the enemy faints + 8 per try, like `planBattle`; accuracy counts), `dangerLine` warnings.
  `yourHit` picks the move with the fewest expected tries (hits / accuracy), marked down if PP runs out; the live
  fight counts the PP the plan used in `S.fight.pp` (`ix:mid` → uses, a guess). `stratTips`: sleep / paralyse first,
  Growl, a safer move when the best one misses a lot, when to heal (their max hit), low PP.
  Battle plan: `planBattle` assigns each of their Pokémon in order, sharing out PP and damage taken over the battle.
  Set-up sweeps: `BOOST` (stage multipliers; `bst` on a Pokémon is read by `dmgRange` and `faster`), `setupOpt` = boost
  once first when safe and the turn pays off here + on the next ones it stays in for (`stay`); the boost carries while
  the same one stays in (`up`, `boosted`), a switch loses it. The live fight shows a "Sweep" line from the same planner.
  Move advice (`setValue` / `bestSet`): per target the best hit + 30% of the second (`BACKUP`: misses, low PP, resists);
  `ppFactor` marks down 5-PP (×0.8) and 10-PP (×0.93) moves. `statusPart` counts an attack boost only as much as the set's best hits use that attack kind.
  Fight keys: `<area>:tr:<id>`, `boss:<id>`, `rm:<area>:<id>` (Vs. Seeker rematch, doesn't tick anything).
- Vs. Seeker (`vermilion:t:0` ticked): `rematchTier` (1 / Celadon / Fuchsia / Champion / National Dex), `rematchParty`,
  `rematchPlan` (best of this, previous, next area); `trainEstimate` uses rematches instead of wild battles when they
  give more EXP a minute (`REMATCH_MIN` = 3, incl. 100 steps to recharge).
- Tabs: Play | Team | Guide | Pokédex. The battle plan (`S.tab = 'battle'`, `renderBattle`) has no tab: it opens from
  Guide ("Battle plans here" / next boss) and Play's level check (`openboss`), with a back button; Guide stays lit.
  `fold(id, title, sub, body)` = a tap-to-open section (`openFolds` keeps them open across re-renders, not saved).
  Team: Best team (carry plan), Party, PC, Add, then folds Training & Day Care and More (trades, fallen, HOME, rules,
  summary, backup).
- HMs: `HM_INFO` (get / need areas; Rock Smash = Ember Spa, Sevii; Waterfall = Icefall Cave). `hmPlan` (cached `_hp`):
  strong = 70+ power and goes in a best-team Pokémon's best four (`bestSet` gain) → teach it to that one; weak = one HM helper takes
  every weak HM it can learn (best-team ones only if nobody else can), kept in the party until the last area that needs
  it. `hmLine` (Guide `renderHMs`), `renderHMPlan` (Team: HMs you have + the next one).
  HM mule (`muleIdx`, `muleOn` = Vermilion until Victory Road): one Pokémon carries the weak HMs (`MULE_HMS`); auto =
  most HMs (2+ of Cut/Strength/Rock Smash), weakest final form, never a kept one or the starter's family; `S.mule` sets it
  by hand ("Make HM mule" on a card; `removeMon` keeps the index right). The carry plan leaves it out, picks 5 fighters
  (`SIZE`), gives no HM points for HMs the mule learns, and `renderCarry` shows it in the 6th slot. No mule:
  `muleCatch` suggests one to catch. At Indigo Plateau (`league`) the plan is 6 fighters again.
  Before the Elite Four: `e4Cleanup` = best-team Pokémon carrying weak HMs (not Fly) forget them at the Move Deleter
  after Victory Road, then take their Elite Four projection's moves (one-copy TMs to the first that wants them); shown in
  `renderHMPlan`, and `hmLine` flags a weak HM on a best-team helper. The carry plan already scores the Elite Four without HMs.
- Guide tab: `renderGuide`, `renderTrainers`, `renderHMs`, `renderEvoReminders`, `catchPicks`.
- Training, "Train or play on?" (Team; short version in Play): `trainingPlan` gives each carry pick a verdict
  (`VERDICT`, `verdictText`; headline `playOnLine`). `unsafeFoes` = next boss's Pokémon nobody beats safely (each checked
  alone with `planBattle`); `bossFixes` = cheapest training (extra minutes) that fixes them, for the next boss (train /
  free = story trainers cover it / catch) and the one after (later). Otherwise `cp.keep` from the carry plan (key for
  the Elite Four) = keeper, else skip. Back-ups aren't pushed to their
  evolution level. `estLines` says how and how long, `renderTraining` / `renderTrainNext`. Day Care (Route 5, one Pokémon):
  `daycarePicks` (value = new Pokédex entries from the level evolutions it reaches ×60, + a stone evolution to a new
  entry ×20, + levels/evolutions for best-team or training-plan ones (×1.5 if it can't fight); `dcStay` = steps until you
  pass Route 5 again: from the Rock Tunnel trip to Fly at Routes 12–18, `DC_STEPS` per area; after Fly, steps to its next
  evolution. Long stays skip fighters in your team and the Fly user; shown on Play at Route 5 and on the way to Rock Tunnel), `daycareMoves`
  (learns moves, forgets the first), `evoMoves` (collect by evo level - 1, or the evolved form skips moves at that level).
  In the Day Care: `m.dc = {lv, a, t, now}` (`now` = level the lady showed, saved; `dcNow`) and `m.box = true`; warns at the collect-by level. Rare Candy: `candyAdvice` (save them; use now only to evolve
  a "Train now" Pokémon in 1–2 or one that can't win a battle), count = ticked Rare Candy items + `S.candy.adj` − `S.candy.used`.
- EXP (Gen 3): `expGain` (yield × level / 7, split between `fought`, ×1.5 trainers; Exp. Share holder `S.share` gets
  half), `m.xp` = EXP into the current level (absent = start of level; +1 carries the rest over, candy/Day Care reset it).
  Logged wins add EXP: wild "It fainted" (`encAdvice` picks who fought; chips change it) and trainer "We won"
  (`fightDefault` / `foughtChips`). Catches give none. Estimates: `trainEstimate` (story trainers up to the next boss's area
  first, free and shared out in plan order; `mins` = extra time only, then `wildPlan`'s best grass spot; `trainMode` = solo / switch / share / avoid),
  `catchInstead` (a wild Pokémon in the next 3 areas with wild Pokémon that does the job sooner), ~1 min wild, ~2 min trainer.
  `carryPlan` and `trainingPlan` are cached per render (`_cp`, `_tp`).
- Carry plan (`carryPlanCalc`, weights in `CARRY_W` / `CARRY_PTS`): candidates = owned (not gone, not in the Day Care)
  + `catchCands` (next 3 areas with wild Pokémon, method open there, family not owned, final form BST 400+; at most 2
  in the six). Each projected (`projMemo`, kept across renders) to the next 3 bosses' level, the next 6's, and Lv 55
  for the Elite Four + Champion (TMs by then). `duel` = real moves both ways, speed, HP; `sweepDuels` plans each boss with that one alone and scores
  the duels it sweeps after one boost as boosted (boost turn counted), so set-up sweepers score higher (role "Sweeper" at 2+ in a row). Score = weighted depth (1 /
  .6 / .4; the Elite Four only from badge `END_FROM` = 6) + coverage (types hit, shared weakness) + roles (fast attacker, tank, HM users for HMs due soon, STAB) −
  levels to train − catch time + staying in the party. Greedy pick, then single swaps until none helps; 3+ ready.
  Then it sticks with your current party unless the new team scores `STICK` (10%) more, so advice doesn't flip-flop.
  `pick` = owned indexes only, catches in `catches`; `dbg` exposes the score for tests.
- Team: `renderTeam`, `renderCarry` / `carryPlan` (who to carry and train), Day Care box, `replacement` (PC pick for a free slot), `teamAdvice` / `advise` (move advice), `stonePlan`, `renderSummary`, `renderBackup`.
- `weakLine(sp)`: "Weak to" chips (×4 marked) + no-effect types; wild encounter, live fight, Battles. `encAdvice`
  always gives the best pick and move first, the training tip second.
- Catching (Gen 3 formula): `catchChance(sp, lv, hpFrac, status, ballX)`, `BALLS` (Net/Nest/Repeat/Timer only from the
  Sevii Islands and only when better than an Ultra Ball), `catchPlan` (from a pool of team indexes: `bestChip` = most HP
  off without a knockout, False Swipe / Super Fang first; `bestStatus` = sleep 2×, paralysis 1.5×), `renderCatch` (steps,
  danger lines, "could help later" from `catchLearns`, chance table). Easy catches (Poké Ball 30%+ at full HP) skip the
  steps; a spot more than one area past `farIdx()` shows best odds only. `CATCH_SPOTS` (walk.js: Snorlax, the birds,
  the starter's roaming beast, Mewtwo) → Guide "Catch plan", Team → "Catching legendaries" (`renderLegends`), and a
  legendary's battle plan shows the catch plan instead of a knock-out plan. Wild encounters: "Catch chance ›".
- Battles: `renderBattle` (the next boss is planned with real levels; later ones level the team up to the target), damage engine `dmgRange` / `threat` / `yourHit` (Gen 3 formula, crit = 2x).
- Pokédex: `renderDex`, `dexHow`, `dexCaught`.

## Saving

- `server.py` (stdlib, no deps) serves the page and the save: `GET`/`PUT /api/state`, `GET /healthz`.
- The save is one file: `/srv/homelab/leafgreen/state.json` (in restic). Before an accepted `PUT` the old one is
  copied to `backups/` if the newest copy is over an hour old (newest 100 kept). A `PUT` with an older `savedAt` gets `409` + the current save.
- The page saves to `localStorage` (`lgfn-v1`) first, then pushes (debounced). It pulls on load, when it comes
  back into view and every 30s; the newest `savedAt` wins. Offline edits push on the next pull.
- Every server response has `X-App-Version` (hash of the page). If a pull sees a new one, the page reloads
  itself (not while logging an encounter or typing), so a deploy reaches an open phone without a manual refresh.
- Opened from `file://` (or in the tests) it only uses `localStorage`.
- The Backup section exports/imports the whole state as JSON.
- Imported 2026-10-13 from the old claude.ai artifact's database (it was hosted there before).

## Cards (Hall of Fame binder)

- Team → Cards fold (`renderCards`). After `S.beaten.champion`, "Lock Hall of Fame team" (confirm tap) freezes
  `S.hof = {at, nine: [{sp, nick, lv, hof}]}`: the party that isn't `gone()`, then the 3 highest-`lv` others (dead or
  alive, ties to the lower index) (`hofNine`, `lockHof`). Unlock clears `S.hof`; a re-lock keeps a slot's pick only if its `sp` is unchanged.
- Picks: `S.cards = {<slot 0-8>: {sp, id, name, n, set, rarity, image, got}}`. They live in `S` and use the normal save/409 flow;
  the server never writes `state.json` for cards.
- Endpoints: `GET /api/cards?dex=<n>&name=<Species>` (TCGdex `api.tcgdex.net/v2/en`, free, no key; pokemontcg.io was dropped:
  deprecated, flaky, prices frozen). Each card: `{id, name, localId, set:{id,name}, rarity, image, kind: modern|retro, eur:{low,trend,avg,avg7,avg30,updated}}`
  (Cardmarket EUR; a null field falls back to its `-holo` field). Only cards whose `dexId` has the species. The page shows `<image>/low.webp`.
  TCGdex down: stale cache, else `{cards: [], error}` (always 200). `GET /api/cards/prices` serves `prices.json` (`{}` if none).
- Rarity constants `MODERN` / `RETRO` at the top of `server.py` (lowercase; TCGdex spells them "Special illustration rare",
  "Hyper rare", "Holo Rare", "Rare Holo LV.X"...). Other rarities are dropped.
- Cache: `/data/cards/cache/species-<dex>.json` and `card-<id>.json`, 7 days, atomic writes, one lock per species.
- `/data/cards/prices.json` (`{id: {name, set, hist: [[date, low, trend, avg30]], alerted?}}`) is written only by
  `scripts/card-prices.py` (host cron 09:20): daily history of un-owned picks, one Discord message when a low drops to
  <= 0.75 x the 30-day median of the daily lows (low vs low, not trend) (needs 7 days of history). See the script's docstring.
- `PORT` env overrides 8080 (for local tests: `DATA_DIR=<scratch> PORT=18765 python3 server.py`).

## Known gaps

- No browser click tests in the repo: `tests/run.js` only renders the tabs.
- Player damage assumes average IVs (15) and no EVs.
