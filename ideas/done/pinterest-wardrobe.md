# Pinterest Wardrobe Outfit Builder

Value: 4   (Pinterest scans → outfit suggestions)
Effort: 4  (multi-stage: track, aggregate, generate combinations)
Risk: 2    (web scraping Pinterest/brands; low data sensitivity)
Source: hermes 2026-10-15

## Problem
Want to build a wardrobe based on items I tag on Pinterest. Currently no automated system to collect tagged clothes, find similar pieces via web search, or generate outfit combinations for my binder/shelf display.

## Proposal
1. Create tool that:
   - Periodically scans Pinterest (or your board exports) to identify "tagged" clothing items you like
   - Scans web (Amazon, ASOS, Depop, etc.) for similar/alternative pieces
   - Generates outfit bundles combining tops/bottoms/shoes that match your style

2. Add binding logic (e.g., max 3 outfits/day rotation) + seasonal filters.

3. Eventually link with your binder/shelf photos (you can upload photos via Tailscale or API, and the tool suggests which cards/items fill gaps).


## Rough plan
1. Define your "liked items" data source (Pinterest board URL? export? manual list?)
2. Build scraper/search wrapper for clothing (reverse image search + text description)
3. Create outfit-combining layer (top+bottom+shoes with style matching)
4. Add web interface (Dashboard link or ntfy alert) to view suggested outfits
5. Optional: integrate card binder photos via upload → gap analysis

_Approved on the dashboard, 2026-10-18._

## Parked 2026-10-18

## Questions
1. Where do the liked items come from: (a) upload photos/links by hand in the app, (b) import the Pinterest data export now and then, or (c) the Pinterest API, with a developer app and token you create?
2. Should I start with just a + b (catalogue + outfit generator), and leave c and d as separate later ideas, or drop c and d?
3. Whose wardrobe is it, and who uses it: just you (admin), or family audience on the dashboard?
4. Outfit matching: simple rules (category + season + colour tags you set), or ask the Mac mini model to pick?
5. Do the "cards" in step 3 mean clothes on a shelf/binder, or Pokemon cards (if so, it belongs with pokemon-card-collector)?

## Answers 2026-10-19

1.	Adding my current clothes. Needs a fast batch photo upload where the model auto-tags items and I only fix mistakes.
	2.	Tagging needs a vision model. Check the Mac mini model handles images, or use a cloud one.
	3.	Size and budget profile, so recommendations fit me and my price range.
	4.	Finding real products. Prefer official or affiliate APIs over scraping ASOS or Depop.
	5.	Marking items as bought. Could read order confirmation emails instead of a manual step.
	6.	Removing items that are sold, worn out or given away.
	7.	Gap analysis. Find what's missing to make more outfits and recommend that next. This is how the wardrobe builds slowly.
	8.	Thumbs up or down on outfits so the rules improve.
	9.	Check the weather forecast for daily outfits.
	10.	Wear tracking to avoid repeats and spot items I never wear.
	11.	Reuse the deal-watch price engine to alert on price drops for recommended clothes.

## Parked 2026-10-19

## Proposed split
1. wardrobe-catalogue (stage 1, can be planned straight away once the split is confirmed). A new tools/wardrobe web app, admin audience, next free port ≥8082 (8086 is fitness and 8087 is taken by the changedetection proposal, so likely 8089). Covers:
   - batch photo upload
   - auto-tagging (category, colour, season, style) by the Mac mini's Ollama
   - a fix-tags review screen
   - size and budget profile
   - retiring items as sold, worn out or given away (soft delete, so the history stays)
   - photos in /srv/homelab/wardrobe
   Covers answers 1, 2, 3 and 6.
2. wardrobe-outfits. A rule-based generator (top+bottom+shoes, season and colour rules) with:
   - thumbs up/down that adjusts rule weights
   - a wear log (no repeats, "never worn" list)
   - a daily outfit using the Open-Meteo forecast (free, no key)
   - an optional daily Discord line
   Covers answers 8, 9 and 10.
3. wardrobe-gaps. Gap analysis (which missing item would unlock the most new outfits, within his size and budget) plus real product suggestions. Needs a product API Dan signs up for. ASOS and Depop have no public product API. Amazon PA-API needs an Associates account. Feeds like Awin need a publisher account. Covers answers 4 and 7.
4. wardrobe-purchases. Reads order confirmation emails to mark items as bought. Needs an IMAP mailbox or app password from Dan, and it touches private email, so it should be its own reviewed idea. Covers answer 5.
5. Price-drop alerts on recommended items, through changedetection-deal-watch (ideas/changedetection-deal-watch.md, not built yet). Wait for it to land, then add watches from stage 3's picks. Covers answer 11.

## Research
Vision check (answer 2): the Mac mini already has gemma4:12b-it-qat (docs/mac-mini.md, top of the bench table). Ollama's gemma4 listing marks the family as vision-capable (text + image input) ([Ollama gemma4](https://registry.ollama.ai/library/gemma4), [Gemma vision docs](https://ai.google.dev/gemma/docs/capabilities/vision)). Before stage 1, Dan should confirm on the Mac with `ollama show gemma4:12b-it-qat` that the capabilities list includes "vision". If it does, no cloud model is needed: photos stay local, and there's no paid API. qwen3.5:9b is the fallback to check the same way.

## Questions
1. Do you agree with the split above, with wardrobe-catalogue built first and the others filed as separate ideas later? (yes / change it)
2. Is the local Mac mini model (gemma4:12b-it-qat, if `ollama show` lists vision) fine for tagging, or do you want a cloud vision model? If cloud, which one: it needs an API key you create, and it can't be Anthropic's (the homelab rules ban an Anthropic API key).
3. Is Pinterest out completely now that the catalogue is your own clothes? Or should the catalogue also accept Pinterest pin links/images as "wishlist" items (by upload, no API)?
4. For stage 3, which product source will you sign up for: Amazon Associates/PA-API, an affiliate network such as Awin, or none for now (gap analysis names the missing item without product links)?
5. For stage 4, which mailbox would it read (provider), and are you OK creating an app password for it? Or should stage 4 be dropped in favour of a "mark bought" button?

## Answers 2026-10-19

1.	Yes, agree with the split and building wardrobe-catalogue first. Add one more stage: wardrobe-pinterest, a scheduled sync of a "Wardrobe" board via the Pinterest API. Pinterest is the main way I want to add wishlist items.
	2.	Use the local Mac mini model if ollama show lists vision. Try qwen3.5:9b next if it doesn't. Only consider a cloud model if both fail.
	3.	Pinterest is not out. It's core. For now, let the catalogue accept pin links and images as wishlist items. Later, wardrobe-pinterest syncs my board so I don't have to upload. Outfits only use items marked as bought.
	4.	None for now. Gap analysis names the missing item without product links. Revisit Awin or Amazon later.
	5.	Drop stage 4 for now. Use a "mark bought" button instead. Email reading can be its own idea later.

## Plan
Goal: Stage 1 of the agreed split, wardrobe-catalogue. It is a batch photo upload where the Mac mini's vision model tags each item and Dan fixes mistakes, plus a size/budget profile, Pinterest pin links/images as wishlist items, a "mark bought" button and soft retire.
Changed since the park: Dan answered every question (split yes, local model, Pinterest stays as wishlist, no product API, no email). Vision is confirmed: `GET http://100.74.81.122:11434/api/tags` lists `vision` for gemma4:12b-it-qat, qwen3.5:9b and qwen3.5:9b-q4_K_M.
Kind: new service
Files:
- tools/wardrobe/compose.yaml: the service (below)
- tools/wardrobe/Dockerfile: copy tools/fitness/Dockerfile (python:3.12.15-slim-bookworm, USER 1000:1000, EXPOSE 8080, /healthz HEALTHCHECK, uvicorn app.main:app)
- tools/wardrobe/requirements.txt: fastapi==0.142.2, uvicorn==0.54.0, jinja2==3.1.6, python-multipart==0.0.32 (same as fitness), plus pillow and pillow-heif pinned to the current stable from https://pypi.org/pypi/<name>/json, with a source comment like the fitness file
- tools/wardrobe/app/main.py: FastAPI routes, server-rendered, no CDN
- tools/wardrobe/app/db.py: SQLite at /data/wardrobe.db, stdlib only
- tools/wardrobe/app/tagger.py: Ollama client plus a background worker thread (stdlib urllib)
- tools/wardrobe/app/tags.py: the allowed tag values and validation of the model's JSON (stdlib only)
- tools/wardrobe/app/images.py: Pillow resize, EXIF strip, thumbnail, HEIC to JPEG
- tools/wardrobe/app/pins.py: pin link to image fetch
- tools/wardrobe/app/templates/*.html, tools/wardrobe/app/static/style.css
- tools/wardrobe/tests/test_tags.py, tests/test_db.py, tests/test_pins.py: stdlib unittest only, no network
- tools/wardrobe/README.md: first run, data, how tagging works, failures
- .env.example: the two vars below, with their defaults
- CLAUDE.md: Layout `tools/` line (add `wardrobe` = clothes catalogue, Mac mini vision tagging, admin; see `tools/wardrobe/README.md`), port row `| 8089 | wardrobe |`
- docs/README.md: one line for `tools/wardrobe/README.md`

New service: name `wardrobe`, dir `tools/wardrobe`, `build: .` plus `image: homelab/wardrobe:0.1.0`.
- Ports: host 8089, container 8080, `"8089:8080"`. 8087 is held by the queued changedetection-deal-watch, 8088 is omada, and 8089 is not in the table and not listening (ss checked).
- Hardening like fitness: `read_only: true`, `tmpfs: - /tmp:size=512m`, `no-new-privileges`, the logging cap.
- Volume: `${APPDATA_PATH}/wardrobe:/data` (photos/ and thumbs/ underneath). Network: `proxy`.
- Env: `TZ`, `DATA_DIR: /data`, `OLLAMA_URL: ${WARDROBE_OLLAMA_URL:-http://100.74.81.122:11434}`, `WARDROBE_MODEL: ${WARDROBE_MODEL:-gemma4:12b-it-qat}`.
- Traefik: router/service `wardrobe`, Host(`wardrobe.${DOMAIN}`), entrypoint web, server port 8080.
- Dashboard: name "Wardrobe", group "Tools", audience admin, description "Clothes catalogue, auto-tagged photos and wishlist", port 8089. Icon: a slug that exists in homarr-labs/dashboard-icons (`svg/<slug>.svg`); try `wardrobe`, then fall back to `homebox`.
- Kuma: `kuma.wardrobe.http.name=wardrobe`, url `http://${LAN_IP}:8089/healthz`.
- .lan host: `wardrobe.lan`.

App behaviour (decisions, not code):
- Items table: id, kind (owned|wishlist), status (active|retired), retired_reason (sold|worn_out|given_away), retired_at, bought_at, category (top|bottom|shoes|outerwear|dress|accessory), colours (1-3 from a fixed list of about 14 basic colours), seasons (any of spring/summer/autumn/winter), style (casual|smart|sport|formal), brand, size, price, notes, source_url, photo, thumb, tag_status (pending|tagged|failed|reviewed), tag_error, tagged_by_model, created_at, updated_at.
- Profile table (key/value): top/bottom/shoe/dress sizes, currency (default GBP), max price per category. Stage 3 reads it later.
- Pages:
  - `/`: grid with filters for kind, category and status. Retired items are hidden unless the filter asks for them.
  - `/upload`: a multi-file `<input accept="image/*" multiple>` plus an owned/wishlist choice.
  - `/review`: every item that is `tagged` or `failed`, each with editable fields. Save sets `reviewed`; "Retry tagging" sets it back to `pending`.
  - `/item/{id}`: edit, "Mark bought" (wishlist becomes owned and bought_at is set), "Retire" with a reason, "Restore".
  - `/wishlist/link`: a pin URL form.
  - `/profile`.
  - `/healthz`: 200 when the DB opens.
- Images: open with Pillow (register pillow-heif). Apply exif_transpose, then save the photo as JPEG at max 1600 px and a 400 px thumbnail, with no EXIF (this drops phone GPS). File names are uuid, never the upload name.
- Tagger:
  - One worker thread works through `pending` items oldest first, one at a time, and picks pending items up again after a restart.
  - Each item is a POST to `{OLLAMA_URL}/api/chat` with the 1024 px JPEG in base64, `stream:false`, `think:false`, and `format` set to a JSON schema whose enums come from tags.py. Timeout 180 s.
  - tags.py validates the reply. Values not in the list are dropped; if the category is missing or invalid the item is `failed` with the reason.
  - Delete removes the row and its files after a confirm. It only touches /data.

Pin links:
- Accept only https URLs whose host is pinterest.<tld>, www.pinterest.<tld> or pin.it.
- Fetch with a 10 s timeout and a 2 MB cap. Follow redirects only to those hosts.
- Read `og:image`, and download it only from `i.pinimg.com` (cap 15 MB).
- Any failure saves the wishlist item with source_url and no photo, `failed`, error "Couldn't get the image; upload it on the item page". The item page has a single-photo replace upload.

New env vars:
- WARDROBE_OLLAMA_URL: the Mac mini's Ollama base URL (default http://100.74.81.122:11434)
- WARDROBE_MODEL: the vision model for tagging (default gemma4:12b-it-qat; fallback qwen3.5:9b)

Checks the builder must run:
- `scripts/dc.sh .worktrees/pinterest-wardrobe/tools/wardrobe config -q`
- `python3 -m py_compile` on every file in tools/wardrobe/app/*.py and tests/*.py
- `cd .worktrees/pinterest-wardrobe/tools/wardrobe && python3 -m unittest discover -s tests` (tests import only the stdlib modules tags.py, db.py and pins.py' URL/host checks; no network)
- `ss -ltnH "sport = :8089"` is empty
- `grep -n 8089 CLAUDE.md` shows exactly one row

Review focus:
- Mac mini off, asleep or Ollama down -> items stay `pending`, the worker retries every 5 min with no crash loop, the UI shows "Tagger offline, N waiting", /healthz stays 200 (the Mac has its own Kuma monitor, so no extra alert).
- Model returns non-JSON, a value outside the enums or an empty reply -> stray values are dropped; no valid category means `failed` with the reason shown on /review. Nothing is ever stored half-written.
- Big batch (for example 30 phone photos at 8-15 MB, or HEIC) -> limits are 15 MB per file and 25 files / 400 MB per batch, so a bigger upload gets a clear 413 message and tmpfs never fills. An unreadable or non-image file is skipped with its name listed, and the rest of the batch still saves.
- Photo privacy -> stored photos and thumbs have no EXIF/GPS; the original upload is never kept.
- Pin link to a non-Pinterest host, a redirect elsewhere, or a page with no og:image -> no fetch outside the allowed hosts (no SSRF to LAN IPs); the item is saved as failed with "upload the image".

Docs: CLAUDE.md layout `tools/` line and the port row 8089; docs/README.md line for tools/wardrobe/README.md. The README covers the first run, the data dir (backed up by restic/B2), the model switch through WARDROBE_MODEL, and the fact that there is no login: anyone on the LAN or tailnet can open it, the same as fitness.

## Manual steps
- `mkdir -p /srv/homelab/wardrobe` as dan (the container runs as uid 1000).
- Optional: set WARDROBE_MODEL / WARDROBE_OLLAMA_URL in the env file; the defaults work.
- Deploy with `scripts/deploy-idea.sh pinterest-wardrobe` (or `scripts/dc.sh tools/wardrobe up -d --build`).
- Note: gemma4 and Hermes's qwen3.5:9b can't both stay loaded in 16 GB, so the first tag after Hermes was used (and the reverse) waits for a model swap. Setting WARDROBE_MODEL=qwen3.5:9b shares Hermes's model and avoids it.
- After deploy, queue the later stages as separate ideas: wardrobe-outfits (only items marked bought), wardrobe-gaps (no product links), wardrobe-pinterest (Pinterest API board sync; needs a developer app and token from Dan), and price alerts once changedetection-deal-watch has landed. Stage 4 (email) is dropped.

## Review notes
1. Live pin.it chain, traced with curl and with `pins.fetch_image` itself on Python 3.12: pin.it (308) → api.pinterest.com/url_shortener/.../redirect/ (302) → www.pinterest.com. Every hop passes `allowed_page_url`, and urllib follows the 308. My test short code was not a real pin, so it landed on the Pinterest homepage. There it failed cleanly with "image host not allowed" and would be saved as a failed wishlist item, which is the planned behaviour. A real pin page (`https://www.pinterest.com/pin/762304674415523145/`) fetched a JPEG from i.pinimg.com through the real code. I could not get a real pin.it code to test end to end, but each host in the chain is allowed.
2. The hostile-host probes still fail: `pinterest.com@127.0.0.1`, `127.0.0.1\@pinterest.com`, `pinterest.com%2f@127.0.0.1`, `pinterest.com:443@127.0.0.1`, `[::ffff:127.0.0.1]`, `pinterest.com.`, `evil.api.pinterest.com`, `api.pinterest.de`, a non-443 port and http. The image check rejects userinfo and backslash forms of i.pinimg.com.
3. `https://pinterest.com\n/` passes the check, because urlsplit strips the newline. It is harmless: it can only resolve to pinterest.com, and if http.client rejects it the InvalidURL is now caught.
4. `[a-z]{2}\.pinterest.<tld>` lets any two-letter subdomain through. Those are all Pinterest's own DNS, so there is no SSRF exposure.

## Declined to judge
None
