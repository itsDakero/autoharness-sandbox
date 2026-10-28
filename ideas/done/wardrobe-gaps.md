# Wardrobe stage 3: gap analysis

Value: 3   (says which missing item would unlock the most new outfits)
Effort: 2  (builds on the outfit rules)
Risk: 1    (inside tools/wardrobe; no external API)
Source: Dan 2026-10-23 (stage 3 of ideas/done/pinterest-wardrobe.md)
Depends on: wardrobe-outfits (uses its outfit rules). Park if that isn't built yet.

## Proposal
In tools/wardrobe: rank missing items (category, colour, season) by how many new valid outfits each
would unlock, filtered by the size and budget profile from stage 1. **No product links or product API**
(Dan's answer 4: none for now; Awin/Amazon revisited later). Name the item only.
Price-drop alerts (old stage 5) need product links, so they wait until a product source exists.

## Parked 2026-10-23

## Questions
1. Requeue wardrobe-gaps once wardrobe-outfits is built and deployed. This needs no answer unless you want gap analysis to have its own simple top + bottom + shoes rule instead of waiting, and then it could be built now. Wait, or own rule?

## Answers 2026-10-25

Wait-for-outfits is satisfied: wardrobe-outfits is built and deployed (wardrobe 0.2.0). Use its outfit rules.

## Plan
Goal: Add a `/gaps` page to the wardrobe app. It ranks missing items (category + colour + season) by how many new valid outfits each would unlock under the stage 2 outfit rules, filtered by the size and budget profile. It names the item only, with no product links or product API (Dan's answer 4). The dependency is now met: on 2026-10-25 Dan answered that wardrobe-outfits is deployed (0.2.0) and asked to use its rules.
Kind: change to tools/wardrobe
Files:
- tools/wardrobe/app/gaps.py: new, stdlib only, pure functions. `rank(items, season, profile, wishlist=())` returns a list of dicts {category, colour, season, unlocks, size, max_price, on_wishlist}.
  - Candidates: category in (top, bottom, shoes, outerwear, dress) x colour in tags.COLOURS (all 14, including multi) x the season(s) asked for. Each candidate is a virtual item: colours=[colour], seasons=[season], style=None, so it never clashes on style.
  - Pool = outfits.build_pool(items), then outfits.fits_season(it, season).
  - Skip a candidate when an item already in the in-season pool has the same category and that colour. It is not missing.
  - Unlocks = the number of outfits that contain the candidate and pass outfits.colour_rule and outfits.style_rule:
    - top: bottom x shoes
    - bottom: top x shoes
    - dress: shoes
    - shoes: both shapes (top x bottom, plus dress)
    - outerwear: every valid base outfit (top+bottom+shoes or dress+shoes) plus this outer
  - Base outfits never include an outer layer, so the counts don't depend on the weather.
  - Enumerate with outfits._combos(lists, random.Random(0)), so the outfits.MAX_COMBOS cap and the sampling are deterministic.
  - Budget: profile `max_price_<cat>` set to 0 means skip that category. Blank means no limit. Otherwise show it as "up to <currency> N".
  - Size: profile top_size, bottom_size, shoe_size or dress_size for that category (outerwear uses top_size). If blank, show "size not set".
  - on_wishlist = True when an active wishlist item has the same category and colour.
  - Drop candidates with unlocks 0. Sort by unlocks desc, then the CATEGORIES order, then the COLOURS order.
  - Also return `current = count of valid base outfits this season`. When nothing unlocks anything, return outfits._missing_reason(pool, by_cat) or "Nothing to suggest yet".
- tools/wardrobe/app/main.py: `GET /gaps?season=<spring|summer|autumn|winter|all>`.
  - Default season: weather.season_for(today.month) (month only, no forecast fetch).
  - "all" ranks each of the 4 seasons and merges the results.
  - Show the top 20. Any other season value gives a 400 through error().
  - Items: db.list_items(kind="owned", status="active", tag_statuses=OK_STATUS). Wishlist: db.list_items(kind="wishlist", status="active").
  - Profile: db.get_profile.
- tools/wardrobe/app/templates/gaps.html: new page.
  - A season selector (links), then the line "N outfits possible this season now".
  - A table: rank, item name ("navy bottom, winter"), "+N outfits", size, budget, "on wishlist" tag.
  - The empty case shows the reason.
  - Footer note: "Suggestions name the item only; no shop links."
- tools/wardrobe/app/templates/base.html: add a ("/gaps", "Gaps") nav tab after Worn.
- tools/wardrobe/tests/test_gaps.py: new unittest, stdlib, no network. Reuse the item() helper style from test_outfits.py. Cases:
  - pool top+bottom+shoes in black, candidate grey bottom: unlocks 1
  - a colour already owned in that category and season is not suggested
  - max_price_dress=0 removes all dress candidates
  - a style clash and a >2 non-neutral colour combo are not counted
  - an empty pool gives an empty list plus a reason
  - a pool over MAX_COMBOS returns the same result twice (deterministic)
  - wishlist match sets on_wishlist
- tools/wardrobe/compose.yaml: image tag homelab/wardrobe:0.2.0 -> homelab/wardrobe:0.3.0. Nothing else changes (port 8091, volumes, labels as they are).
- tools/wardrobe/README.md: a "Gaps" section (rules above in 5-6 lines, no product links). Update the "Later stages" line to drop gap analysis.
- CLAUDE.md: layout line "wardrobe = clothes catalogue + outfit generator" -> "... + outfit generator + gap analysis".
- docs/README.md: the tools/wardrobe/README.md row adds "outfits, gap analysis".
New service (if any): None
New env vars: None
Checks the builder must run:
- cd <worktree>/tools/wardrobe && python3 -m unittest discover -s tests
- python3 -m py_compile <worktree>/tools/wardrobe/app/gaps.py <worktree>/tools/wardrobe/app/main.py
- scripts/dc.sh <worktree>/tools/wardrobe config -q
Review focus:
- empty or tiny wardrobe (no shoes, nothing owned) -> page renders 200 with the missing reason, no crash or division by zero
- large wardrobe (combos over MAX_COMBOS for 5 cats x 14 colours) -> capped, deterministic counts, and the page answers within a few seconds
- profile blank or holding odd values (non-numeric max_price, missing currency) -> treated as no limit and GBP, no 500
- items with no colours or no seasons (all-season) -> counted the same way as on /outfits (empty seasons fits every season)
- bad ?season= value -> 400 via error(), not a 500
Docs: tools/wardrobe/README.md Gaps section; CLAUDE.md layout line; docs/README.md wardrobe row. No port or table changes.

## Manual steps
Run `scripts/deploy-idea.sh wardrobe-gaps`, which rebuilds the image as 0.3.0. Then open http://homelab:8091/gaps.

## Review notes
1. /home/dan/homelab/.worktrees/wardrobe-gaps/tools/wardrobe/app/gaps.py:18-41: the build doesn't use `outfits._combos(..., random.Random(0))` with the 50,000 cap as the plan said. It has its own `_enum` capped at 5,000 per candidate and scales sampled counts up to the full total. Results are still deterministic and the README explains it. Speed is good: a 245-item wardrobe across all 4 seasons took 0.9 s. I accept the change, but the counts are estimates once a wardrobe passes the cap.
2. Because sampled counts are scaled, an estimate can come out a little off. In a large random wardrobe, a black outerwear candidate showed "+6716 outfits" while the page said 6660 outfits are possible now. A neutral outer layer with no style should equal the current count exactly. It looks odd, but it is harmless.
3. The plan says outerwear unlocks one outfit per valid base outfit. So in any sizeable wardrobe, every neutral outerwear colour ties at the top of the list and can fill most of the top 20. The code follows the plan; Dan may want to weight or cap outerwear later.
4. FastAPI isn't installed on the host, so I couldn't render `/gaps` here. I checked the route and template by reading them. The season is checked before rendering and a bad value goes to `error()` (400). The `seasons + ("all",)` tuple join and `currents[0][1]` are both valid.
5. With `?season=all`, the empty-state reason is the first season's reason only. That's fine because rows are empty only when every season is empty.

## Declined to judge
- Unlock counts for "multi"-colour candidates: the plan includes multi on purpose and the colour rule handles it.
- No product or shop links: Dan asked for that (answer 4).
- How candidates rank across seasons with "all": the plan says merge and take the top 20, and the build does that.
