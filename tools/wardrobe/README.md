# Wardrobe (catalogue + outfit generator)

Clothes catalogue at `http://<host>:8091/` (`wardrobe.lan`). Admin audience. **No login**: anyone on the
LAN or tailnet can open it, the same as fitness.

## First run
1. `mkdir -p /srv/homelab/wardrobe` as dan (the container runs as uid 1000).
2. `scripts/dc.sh tools/wardrobe up -d --build` (or `scripts/deploy-idea.sh pinterest-wardrobe`).
3. Open `/profile` for sizes and budget, then `/upload` for photos.

## Data
`/srv/homelab/wardrobe/`: `wardrobe.db` (SQLite), `photos/` (max 1600 px JPEG), `thumbs/` (400 px).
Backed up by restic/B2 with the rest of `/srv/homelab`. Uploads are re-encoded: EXIF/GPS is dropped and
the original is never kept. File names are random uuids.

## How tagging works
Uploads become `pending` items. One worker thread sends them, oldest first, to the Mac mini's Ollama
(`WARDROBE_OLLAMA_URL`, model `WARDROBE_MODEL`, default `gemma4:12b-it-qat`) with a JSON schema limited to
the allowed category/colour/season/style values. Values outside the lists are dropped. Tagged items wait
on `/review`; saving there marks them `reviewed`. Switch model with `WARDROBE_MODEL=qwen3.5:9b` (shares
Hermes's model, so no swap in the Mac's 16 GB) and redeploy.

## Wishlist and pin links
`/wishlist/link` takes a pinterest.<tld> or pin.it https link, reads `og:image` and downloads it only from
`i.pinimg.com`. Nothing else is ever fetched. If it fails the item is saved as `failed`; upload the
picture on its page. "Mark bought" turns a wishlist item into an owned one. Retire (sold, worn out,
given away) is a soft delete; Restore undoes it.

## Failures
- Mac mini off or Ollama down: items stay `pending`, the banner says "Tagger offline, N waiting", the
  worker retries every 5 min. `/healthz` stays 200.
- Model returns junk or no valid category: the item is `failed` with the reason on `/review`; use
  "Retry tagging" after fixing the cause, or fix the tags by hand.
- Limits: 15 MB per file, 25 files and 400 MB per upload (413 message beyond that). Unreadable files are
  skipped and listed; the rest still saves.
- Tests: `cd tools/wardrobe && python3 -m unittest discover -s tests` (stdlib only, no network).

## Outfits
`/outfits` shows today's outfit: top + bottom + shoes (or dress + shoes), plus an optional outer layer.
- **Pool**: only items marked bought (`owned`), active, and tagged or reviewed. Never wishlist, retired,
  pending or failed items. Accessories are ignored.
- **Season**: an item fits if its seasons include today's or its list is empty (all-season). With a
  forecast: max >= 20C summer, <= 11C winter, else spring (Mar-Jun) or autumn. Without: DJF winter, MAM
  spring, JJA summer, SON autumn.
- **Outer layer**: required when max < 14C or rain >= 50% (if none fits: note "No suitable outer layer
  owned"); left out when max >= 20C and rain < 50%; otherwise optional.
- **Colour**: neutrals are black, white, grey, navy, beige, brown. At most 2 distinct non-neutral colours
  (shoes count) and at most one `multi` item. **Style**: sport+smart, sport+formal, casual+formal clash.
- **Thumbs**: each colour pair and style pair in an outfit has a weight = clamp(1 + 0.2 ups - 0.3 downs,
  0.2, 3), recomputed from the votes every time. A thumbs-down outfit is never shown again; changing your
  vote replaces it. Score = mean weight x a random 0.85-1.15.
- **Wear log**: "Wore this" logs the outfit for today (one row per outfit per date). A top, bottom or
  dress worn within the no-repeat days (profile, default 7, 0-60) is skipped; if nothing else is left the
  note says so and a repeat is shown. `/worn` lists never-worn items and the last 60 entries (delete a
  mistaken entry there).
- **Another** shows a fresh pick without changing today's outfit.
- **Weather**: Open-Meteo (no key), fetched once per date when `/outfits` is first opened, 10 s timeout.
  Set latitude and longitude in `/profile`; without them, or if the fetch fails, the month decides and the
  page says "No forecast; using the month". A failed fetch is not retried that day.
- **Daily Discord line**: tick "Daily Discord line" in `/profile` (off by default).
  `scripts/morning-brief.py` runs at 07:00 from cron and puts `/api/daily.txt` as the outfit line
  in the Discord morning brief.

Failures: toggle off gives 204 and no outfit line; app down gives a syslog line only (`journalctl -t
morning-brief`) and the rest of the brief still posts; an empty or tiny wardrobe gives a reason such as "Add at least one shoes item marked
bought". If a stored item is retired or deleted, today's outfit is regenerated.

## Gaps
`/gaps?season=spring|summer|autumn|winter|all` (default: this month's season) ranks missing items.
- Candidates are category (top, bottom, shoes, outerwear, dress) x colour x season. A colour already owned
  in that category and season is not missing.
- Unlocks = new outfits that pass the Outfits colour and style rules (outer layers counted on top of every
  valid base outfit). Combinations over a cap are sampled with a fixed seed and scaled, so counts are stable.
- Profile: `max_price_<category>` 0 skips the category, blank or invalid means no limit; sizes show
  "size not set" when blank. Items already on the wishlist (same category and colour) are tagged.
- Top 20 only. It names the item only: no product links or shop API.

Later stages (separate ideas): Pinterest API board sync, price alerts.
