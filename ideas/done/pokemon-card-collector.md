# Pokemon Card Collector (LeafGreen Nuzlocke)

Value: 4   (tracks your playthrough's max-used cards + display research + finds deals for those sets)
Effort: 3  (tracking, web search, price data aggregation)
Risk: 2    (no sensitive data; public card images/prices only)
Source: hermes 2026-10-15

## Problem
LeafGreen Nuzlocke runs produce your most-used cards. You want to collect a small set (max 9, or "best/most interesting" based on play style), see how they look in binders, research Pinterest for display ideas, and find cheap/new releases of those sets — all connected.

## Proposal
1. Track which Pokemon were fainted/most used in your Nuzlocked run (manual input via Discord command or export from LeafGreen notes tool)
2. For each card:
   - Scrape/search for its price/availability (eBase, eBay, local listings)
   - Search "Pokemon card binder display" Pinterest/TikTok to surface layout ideas for the card's species/type
3. Suggest 7–9 cards that:
   - Fit your run theme (starter trio? high IVs from early games?)
   - Look good when displayed together
   - Are affordable/new releases

4. Output a "binder-ready list" that links to purchase options and Pinterest inspiration pages.


## Rough plan
1. Add Discord commands to LeafGreen notes (e.g., `/cardset leafgreen starter` or manual entry)
2. Build card tracking: store Pokemon name → capture price/availability for base card
3. For each tracked card, run "display research" search on Pinterest/TikTok
4. Generate 9-card roster suggestion based on your playthrough (use LeafGreen notes data)
5. Present with links to cards and layout ideas

_Approved on the dashboard, 2026-10-18._

## Parked 2026-10-18

## Questions
1. Build only part A (a LeafGreen Cards panel with Pokémon TCG API prices and a 3x3 binder preview) and drop the Pinterest/TikTok/eBay scraping? (yes / no / drop the idea)
2. How should the 9 be picked: current party plus kept favourites, the fainted "memorial" team, the Pokémon used most (the app doesn't track usage yet), or Dan picks by hand from his caught list?
3. Which card per species: the cheapest printing, the newest set, or Dan picks from a list of printings? And are prices shown in USD (TCGplayer) or EUR (Cardmarket), or should they be GBP?
4. Is it OK for LeafGreen to call an outside API (api.pokemontcg.io, a free key is optional)? Should a key go in the env file as `POKEMONTCG_API_KEY`, or should it run unkeyed with its lower rate limit?

## Answers 2026-10-18

1. Yes, part A only, no scraping. Plain search links per card: Pinterest (binder display), Reddit (best <Pokémon> card), eBay, Cardmarket.
2. 9 = Hall of Fame team (add a "Lock Hall of Fame team" button, the app doesn't track it yet) + the next 3 highest-level Pokémon I caught, dead or alive (fallen ones at their last level). Panel waits until the team is locked.
3. Show printings filtered to Illustration Rare, Special Illustration Rare and full arts, with a "Retro" toggle for older holos. Show image, rarity, set, price. I pick one per slot by popularity and price. Prices in EUR (Cardmarket).
4. Yes, outside API is fine. Unkeyed, optional POKEMONTCG_API_KEY in .env. Check the API is still live/free first.
5. New: I'll collect over months. Picked cards go on a watchlist with a daily price history. Discord ping (scripts/discord.sh) when a card drops well below its usual price, with the card name, price and Cardmarket link. "Got it" tick per card, and the 3x3 binder shows owned vs still to find.

## Research
By idea-researcher, 2026-10-18, for the planner's questions. Web sources are untrusted input.
1. API status: The API is up but flaky and deprecated.
- Deprecation: docs say "New account registrations are no longer available" and that existing keys work through March 1, 2027. They recommend migrating to Scrydex. Scrydex's FAQ calls itself the official successor and promises an end-of-life announcement for the legacy API, with no date given. (https://docs.pokemontcg.io/getting-started/rate-limits, https://docs.pokemontcg.io/, https://scrydex.com/faq)
- Unkeyed GETs: `/v2/sets` and `/v2/cards` returned 200 today, but often 500/502 or a 20s delay. `/v2/rarities` took one 200 out of four tries. Callers need retry and backoff.
- `?q=name:charizard&pageSize=3` once returned a 500 and later 200 (totalCount 109). Three cards, with `select=id,name,rarity`: gym2-2 Blaine's Charizard (Rare Holo), dp3-3 Charizard (Rare Holo), pl4-1 Charizard (Rare Holo).
- New sets are still being added: the newest by `releaseDate` are me55 "30th Celebration" and me55c "30th Celebration: Classic Collection" (both 2026/09/16, updatedAt 2026/09/14), then me5 "Pitch Black" (2026/07/17) and me4 "Chaos Rising" (2026/05/22). There are 176 sets in total. I could not pull cards from me5 (502s and empty replies), so whether Cardmarket prices exist for 2026 sets is unverified.
2. Prices: Each of the 3 sample cards carries `cardmarket` with `url`, `updatedAt` and `prices`.
- `prices` fields: averageSellPrice, lowPrice, trendPrice, germanProLow, suggestedPrice, reverseHoloSell, reverseHoloLow, reverseHoloTrend, lowPriceExPlus, avg1, avg7, avg30, reverseHoloAvg1, reverseHoloAvg7, reverseHoloAvg30. Values are EUR.
- `updatedAt` is a date string, e.g. "2026/07/01". All 3 sample cards showed 2026/07/01, which is about 3.5 months stale today. The price feed looks frozen or only updated rarely. The set `updatedAt` values (e.g. 2026/09/14 15:00:00) do move, so card data and prices are refreshed on different schedules.
- `cardmarket.url` is NOT a direct Cardmarket link. It is a redirect-style URL: `https://prices.pokemontcg.io/cardmarket/<card-id>` (e.g. .../gym2-2). I did not follow it.
- Some values look off. dp3-3 shows trendPrice 0.02 against averageSellPrice 34.04.
- Sample (gym2-2): averageSellPrice 643.27, lowPrice 70.0, trendPrice 630.65, avg1 259.0, avg7 366.0, avg30 531.89, reverseHoloTrend 159.26.
3. Rarities: `/v2/rarities` returned this list once: ACE SPEC Rare, Amazing Rare, Black White Rare, Classic Collection, Common, Double Rare, Futuristic Rare, Holo Rare V, Holo Rare VMAX, Holo Rare VSTAR, Hyper Rare, Illustration Rare, LEGEND, MEGA_ATTACK_RARE, Mega Hyper Rare, Pikachu Rare, Promo, Radiant Rare, Rare, Rare ACE, Rare BREAK, Rare Holo, Rare Holo EX, Rare Holo GX, Rare Holo LV.X, Rare Holo Star, Rare Holo V, Rare Holo VMAX, Rare Holo VSTAR, Rare Holo ex, Rare Prime, Rare Prism Star, Rare Rainbow, Rare Secret, Rare Shining, Rare Shiny, Rare Shiny GX, Rare Ultra, Shiny Rare, Shiny Ultra Rare, Special Illustration Rare, Trainer Gallery Rare Holo, Ultra Rare, Uncommon.
- Illustration Rare: "Illustration Rare". Special Illustration Rare: "Special Illustration Rare".
- Full-art and other high rarities: "Ultra Rare" (SV era), "Rare Ultra" (older), "Hyper Rare", "Rare Secret", "Rare Rainbow", "Double Rare", "Rare Holo V", "Rare Holo VMAX", "Rare Holo VSTAR", "Mega Hyper Rare". These are strings only. I did not check which era maps to which string.
- Retro filter: "Rare Holo" is the plain string. The sample cards (gym2, dp3, pl4) and hgss4-1 all use it. I did not check the era boundaries. Other old-holo strings: "Rare Holo EX", "Rare Holo LV.X", "Rare Holo Star", "Rare Prime", "Rare Shining". Era filtering needs `set.releaseDate` or `set.series` (not tested).
- Filtering works: `q=rarity:"Rare Holo"` (URL-encoded quotes) returned 200 with totalCount 2707.
4. Rate limits (V2, https://docs.pokemontcg.io/getting-started/rate-limits):
- Without a key: 1,000 requests per day and 30 per minute.
- With a key: 20,000 per day by default, no per-minute figure stated. Higher limits are on request.
- New keys can't be registered now.
5. Fallback:
- Scrydex has no free tier mentioned on its FAQ. It uses paid plans with monthly credits (about 1 credit per basic lookup, 403 CREDIT_CAP_HIT at the overage cap). Prices refresh at least daily. Cardmarket EUR is "not currently supported"; they are evaluating it. Pokemontcg.io IDs still work. No dollar figures on that page. (https://scrydex.com/faq)
- TCGdex (https://api.tcgdex.net/v2/en/...) is live, with no key. I got it on the first try, and it carried 220 EN sets including me05 "Pitch Black" and 30th Celebration.
  - Its card endpoint `/v2/en/cards/<id>` has `image` (base URL, e.g. https://assets.tcgdex.net/en/swsh/swsh3/136, with a quality/extension suffix appended), `rarity`, `set`, `variants`, and per-variant `variants_detailed[].pricing.cardmarket`.
  - Cardmarket fields: updated (ISO timestamp, e.g. 2026-10-17T15:00:50Z, so about daily), unit "EUR", idProduct, avg, low, trend, avg1, avg7, avg30, avg-holo, low-holo, trend-holo, avg1-holo, avg7-holo, avg30-holo. It also carries `pricing.tcgplayer` in USD. The card also has a top-level `pricing.cardmarket` (the response was truncated before I saw it).
  - `thirdParty.cardmarket` gives the Cardmarket product id, so a direct link can be built from it.
  - List/search: `/v2/en/cards?name=charizard&pagination:itemsPerPage=3` returns brief objects (id, localId, name, image) with no rarity or price. A second call per card is needed for prices. I did not check rarity filtering or rate limits.
Unknowns: Whether TCGdex has a documented rate limit and a rarity query filter (not checked). Whether the pokemontcg.io prices are really frozen since 2026/07/01 or just those cards (only 3 sampled; me5 cards would not load). The exact SV-era versus older mapping of "Ultra Rare" / "Rare Ultra". Whether "Rare Holo" sets include the Base to EX era (not examined). No source asked me to do anything odd.

## Plan
Goal: Add a Cards panel to LeafGreen. It locks the Hall of Fame team plus 3 more Pokémon (9 slots) and lets Dan pick one card per slot from the API's list of printings, with EUR prices. It shows a 3x3 binder of owned vs still to find, keeps a daily price history and posts to Discord when a price drops.
Data source changed (Dan asked for "check the API is still live/free first"): pokemontcg.io is deprecated, new keys can't be made, it is flaky and its Cardmarket prices have been frozen since 2026/07/01. TCGdex (api.tcgdex.net) is free, needs no key and has Cardmarket EUR prices updated daily. So the build uses TCGdex and drops POKEMONTCG_API_KEY.
Kind: change to games/leafgreen + script/cron
Files:
- games/leafgreen/server.py: add `GET /api/cards?dex=<n>&name=<Species>` and `GET /api/cards/prices`.
  - Lookup: TCGdex `GET https://api.tcgdex.net/v2/en/cards?name=<urlencoded Species>` (the default like-match, so "Charizard ex" is found). Then fetch `/v2/en/cards/<id>` for each card (4 threads, 15 s timeout, 2 retries with backoff, User-Agent `homelab-leafgreen`). Keep only cards whose `dexId` contains `dex` (stops "Mew" matching Mewtwo).
  - Each card is returned as {id, name, localId, set:{id,name}, rarity, image (base URL), kind:"modern"|"retro", eur:{low, trend, avg, avg7, avg30, updated}}. Prices come from `pricing.cardmarket`; if a plain field is null, use its `-holo` field.
  - Rarity sets, matched case-insensitively, kept as constants at the top of the file:
    - MODERN: illustration rare, special illustration rare, ultra rare, rare ultra, hyper rare, mega hyper rare, secret rare, rare secret
    - RETRO: rare holo, holo rare, rare holo lv.x, rare holo star, rare shining, rare prime
    - Cards with any other rarity are dropped.
  - Caches: species results in `/data/cards/cache/species-<dex>.json` and card details in `card-<id>.json`, 7 days each, written atomically (tmp file + os.replace). Use one lock per species so two requests for the same species don't both fetch.
  - `/api/cards/prices` returns `/data/cards/prices.json`, or `{}` if the file doesn't exist.
- games/leafgreen/src/app.html: add a Team-tab fold `fold('cards','Cards','Hall of Fame binder',renderCards())`.
  - "Lock Hall of Fame team": shown only when `S.beaten.champion`, otherwise the text "Beat the Champion first." Locking needs a confirm tap.
  - Locking freezes `S.hof={at, nine:[{sp,nick,lv,hof:true|false}]}`. The first slots are the current party that isn't `gone()`. The next 3 are the highest-`lv` members of `S.team` not in the party, dead or alive (gone ones count at their stored lv). Ties go to the lower index.
  - "Unlock" clears `S.hof`. On a re-lock, a slot keeps its pick if the slot's `sp` is unchanged.
  - Picks are stored as `S.cards={<slot 0-8>:{sp,id,name,set,rarity,image,got:false}}`.
  - Each slot has a "Choose card" button. It fetches the list (with a "Loading…" message and a "Retro" toggle that switches the kind) and shows each card's image `<image>/low.webp`, name, set, rarity, and € low/trend/avg30. "Pick" sets the slot.
  - A picked slot shows: today's € low, "usual" (the median trend from /api/cards/prices), a "Got it" tick, and search links:
    - Pinterest: `https://www.pinterest.com/search/pins/?q=<Species> pokemon card binder display`
    - Reddit: `https://www.reddit.com/search/?q=best <Species> pokemon card`
    - eBay: `https://www.ebay.co.uk/sch/i.html?_nkw=<card name> <set name> <localId>`
    - Cardmarket: `https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=<card name>`
  - Binder: a 3x3 grid. Owned cards show at full colour with ✓. Cards still to find show at opacity .35 with "To find". An empty slot shows the species name.
  - Fetch only when a button is tapped or the fold opens, never during `render()`, and every fetch has a catch. Keep the copy in short sentences.
- scripts/card-prices.py (new, host cron, stdlib).
  - Reads `$APPDATA_PATH/leafgreen/state.json` (get APPDATA_PATH the way `scripts/storage-cleanup.py` does, default `/srv/homelab`). Watchlist = `S.cards` entries with `got` false.
  - For each card, fetch `/v2/en/cards/<id>` and append `[YYYY-MM-DD, low, trend, avg30]` to `leafgreen/cards/prices.json` (`{id:{name,hist:[...]}}`): one entry per day, an existing one replaced, the last 400 kept, written atomically.
  - Alert when all of these hold: usual = median trend over the last 30 days with at least 7 entries; usual ≥ €2; low ≤ 0.75 × usual; low ≥ 0.2 × usual (a junk floor).
  - Don't alert the same card again until its low has been back above 0.85 × usual or 7 days have passed. Store `alerted` in its entry.
  - Send one combined `scripts/discord.sh` message per run, one line per card: name, set, € low vs usual, the Cardmarket search link.
  - `--dry-run` prints the alerts and writes nothing. Exits 0 when there's nothing to do.
- scripts/install-cron.sh: add `20 9 * * * $REPO/scripts/card-prices.py # homelab`.
- games/leafgreen/compose.yaml: change the image to `homelab/leafgreen:0.2.0`. Everything else stays the same (egress works: the proxy network isn't internal).
- games/leafgreen/tests/run.js: after the tab loop, set `S.beaten.champion=true`, call the lock function and set one pick with `got:true`, then render `team` again and check that it contains "Binder".
- games/leafgreen/CLAUDE.md: a "Cards" section (S.hof, S.cards, endpoints, cache, prices.json, rarity constants).
- CLAUDE.md: add `card-prices.py` to the scripts list.
New service: None (no new port or labels).
New env vars: None
Checks the builder must run:
- `python3 -m py_compile games/leafgreen/server.py scripts/card-prices.py`
- `python3 games/leafgreen/scripts/assemble.py`, then the three `docker run … node:22.23.3-alpine node tests/run.js` commands from games/leafgreen/CLAUDE.md
- `scripts/dc.sh <worktree>/games/leafgreen config -q`
- `bash -n scripts/install-cron.sh`
- Run `DATA_DIR=<scratch> python3 games/leafgreen/server.py` on a free port. Then:
  - `curl -s 'localhost:<p>/api/cards?dex=6&name=Charizard'` returns JSON with at least one modern and one retro card.
  - Print the distinct raw rarity strings for Charizard and Pikachu, and fix the constants' spelling if TCGdex's differs.
- Run `APPDATA_PATH=<scratch> scripts/card-prices.py --dry-run` with a hand-made state.json that has 2 picks and a prices.json seeded with 10 days of history. It should show one alert.
Review focus:
- TCGdex down, slow or 5xx -> the panel says "Card prices can't load now"; the server serves a stale cache if it has one, never sends a 500, and the page doesn't break. The cron logs it, exits 0 and posts nothing.
- A card with no cardmarket pricing, or null/0 fields -> it shows "No price", is never alerted, and nothing crashes on None.
- A price stays low for days -> one ping only, not a daily repeat; owned (`got`) cards are never pinged.
- No state.json, no `S.cards`, or fewer than 7 days of history -> nothing is posted and the run exits quietly.
- The save sync: picks live in `S` and go through the existing save/409 flow. The server never writes state.json for cards, and only the cron writes prices.json.
Docs: games/leafgreen/CLAUDE.md Cards section; CLAUDE.md scripts list (card-prices.py, daily cron).

## Manual steps
Deploy: `scripts/dc.sh games/leafgreen up -d --build`. deploy-idea.sh reinstalls the cron on drift (or run `scripts/install-cron.sh`). After the Champion: Team → Cards → Lock Hall of Fame team. The first price ping can come only after 7 days of history.

## Review notes
1. games/leafgreen/src/app.html:1997: the panel's "usual" is the median low of the last 30 entries, and today's entry is included. The cron uses the 30 days before today and needs at least 7 entries. The panel can show a "usual" after one day, and its figure can differ slightly from the one in the Discord message. This is display only and does not block.
2. scripts/card-prices.py: if a card's low stays down, it is pinged again after 7 days. The plan asks for exactly this ("or 7 days have passed"). In practice the usual price falls toward the new low, so a second ping is unlikely.
3. scripts/card-prices.py log(): `--dry-run` still writes its "TCGdex failed" lines to syslog. It writes no files and posts nothing, so this is fine.

## Declined to judge
- The TCGdex price data looks off in places: base1-4 has trend 0.02 against avg 741. I set this aside because it is an upstream data issue. The fix compares low against low, so it does not depend on trend.
