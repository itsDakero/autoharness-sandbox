# Reading tracker: a small phone-first books app that replaces Jelu

Value: 3   (Dan: a book tracker that actually holds his books and is easy to use on his iPhone; Jelu has 0 books)
Effort: 3  (FastAPI + SQLite app like tools/wardrobe, Goodreads CSV import, Open Library covers, swap Jelu out)
Risk: 2    (new service + removing Jelu; the dashboard's personal feed and Homelab Town read from it)
Score: 9
Source: Dan 2026-10-26 (session with Claude: "the import doesn't work and it feels clunky to navigate around")

## Problem
Jelu (`tools/jelu`, port 8089) is up and healthy, but its library is empty: 0 books. Checked from a copy of
`jelu.db` on 2026-10-26:
- The Goodreads CSV (`/srv/homelab/jelu/files/imports/goodreads_library_export.csv`, 38 rows: 32 read,
  5 to-read, 1 currently-reading) was uploaded twice on 2026-10-23. The import queue holds 57 SAVED rows
  and 1 PROCESSING row. The first run hung on Calibre. Calibre was then turned off (`jelu-import-fix`),
  but Jelu only processes the queue on a new upload, and the UI upload does nothing on iPhone Safari.
- Even when it runs, Jelu drops every rating (`failed to parse number 4.0`) and skips the 9 rows without
  an ISBN (e.g. The Thursday Murder Club, A Game of Thrones, One of Us Is Lying).
- Dan finds Jelu's UI clunky to get around. 0.88.2 is the newest release, so upgrading won't help.

## Proposal
A small app of our own in `tools/books/` (service `books`), built the same way as `tools/wardrobe` and
`tools/fitness`: FastAPI + SQLite in `${APPDATA_PATH}/books/`, its own Dockerfile, healthcheck, all the
template labels, admin audience, no login (same as wardrobe/fitness). Port: the next free one from the
CLAUDE.md table (8090 looks free; check it). Built for the iPhone first: big tap targets, one column, no
hover-only controls, works in Safari (test the upload with a plain `<input type="file">` form post, no
JS-only upload).

Pages (keep it to these):
- **Home**: Currently reading at the top (cover, title, author, page or % with a quick "update progress"
  control, a "Finished" button that asks for a 1-5 star rating and the date). Then Want to read, then a
  "Read this year: N" count and a link to the full list.
- **Library**: every book, filter by shelf (reading / want to read / read / did not finish) and year
  finished, search by title or author. Tap a book for its page: cover, shelf, rating, dates, notes,
  edit and delete.
- **Add book**: search Open Library by title/author/ISBN (`openlibrary.org/search.json`, no key), pick
  a result, choose a shelf. Manual entry if nothing matches (title + author is enough, ISBN optional).
- **Import**: upload a Goodreads CSV export. Read title, author, ISBN/ISBN13 (strip Goodreads' `="..."`
  wrapping), My Rating (0 = no rating), Exclusive Shelf (`read`, `to-read`, `currently-reading`,
  anything else → read with a note), Date Read, Date Added, Number of Pages, My Review / Private Notes.
  No ISBN is fine. Re-importing must not make duplicates: match on Goodreads Book Id first, then ISBN13,
  then lower-cased title + first author. Show a summary after import (added / updated / skipped, with
  reasons). Import the CSV that's already on disk as part of first run, so Dan doesn't need to upload it.
- **Covers**: fetch from Open Library covers (by ISBN, else by the search result's cover id) in a
  background job, cache them in `${APPDATA_PATH}/books/covers/`, show a plain placeholder with the title
  when there's none. One request at a time, short timeout, never block a page or the import on a cover.

API for the rest of the homelab:
- `GET /api/current` → the currently-reading books (title, authors, percent, page, started), and
  `GET /api/stats` → read this year, want-to-read count.
- Point `core/dashboard/app/personal.py` `_reading` at `/api/current` (drop the Jelu basic auth and the
  `JELU_*` env vars), and change Homelab Town's `library` building (`core/dashboard/app/town.py`) from
  `jelu` to `books`.

Swap Jelu out in the same build:
- Remove `tools/jelu` and every reference (CLAUDE.md layout + ports table, `.env.example`, `docs/`,
  `scripts/backup.sh`, `scripts/ops-actions.py`, `scripts/image-check.py`, `core/dashboard/compose.yaml`,
  `tools/changedetection/README.md`, `docs/town-mockup.html` if it names it). Follow the
  `/remove-service` steps where they apply. Port 8089 becomes free.
- Keep `/srv/homelab/jelu/` on disk (restic still has it). The README tells Dan how to delete it once he's
  happy, and that Jelu's Kuma monitor goes once AutoKuma notices the labels are gone (check whether it
  needs removing by hand).

## Done when
- All 38 books from the CSV are in the app with shelves, ratings and dates, including the 9 without ISBN.
  Re-running the import changes nothing.
- On a phone-sized viewport: add a book, mark progress, finish it with a rating, without zooming.
- The dashboard's personal feed shows the currently-reading book from the new app.
- Tests like `tools/wardrobe/tests` (CSV parsing: the `="..."` ISBNs, rating 0, missing ISBN, duplicate
  rows; the dedupe rule).

## Not in scope
Social features, Goodreads sync (Goodreads has no public API), ebook files, Calibre, multiple users.
A "currently reading" line in the morning brief can be a follow-up note once this is deployed.

## Plan
Goal: Replace Jelu, which has 0 books, with a small phone-first FastAPI + SQLite books app at `tools/books` on port 8090. It imports the existing Goodreads CSV, and the dashboard and Town switch over to it.
(Rejected note `books-deals-aggregator` doesn't block this. Its reason was "Split into changedetection-deal-watch + jelu-reading-tracker", and this note is the follow-up to that Jelu half because Jelu failed. No rule-breaking instructions in the note.)
Kind: new service + removal of `tools/jelu`

Files:
- tools/books/compose.yaml: new service (below). Copy the shape of tools/wardrobe/compose.yaml.
- tools/books/Dockerfile: copy of tools/wardrobe/Dockerfile (python:3.12.15-slim-bookworm, USER 1000:1000, port 8080, the same /healthz HEALTHCHECK).
- tools/books/requirements.txt: fastapi==0.142.2, uvicorn==0.54.0, jinja2==3.1.6, python-multipart==0.0.32. Same pins as wardrobe, with the same source comment. No httpx: use stdlib urllib for Open Library.
- tools/books/app/__init__.py, main.py (routes), db.py (schema + dedupe + queries), goodreads.py (CSV parsing, stdlib only), openlibrary.py (search + cover fetch, urllib, 8 s timeout, User-Agent `homelab-books/0.1`), covers.py (one background worker thread).
- tools/books/app/templates/: base.html, home.html, library.html, book.html, add.html, import.html, error.html. app/static/style.css: one column, max-width ~600px, tap targets ≥44px, font ≥16px (stops iOS zoom on inputs), no hover-only controls, `<meta name=viewport content="width=device-width, initial-scale=1">`.
- tools/books/tests/test_goodreads.py, tests/test_db.py: stdlib unittest, no network, `db.connect(":memory:")` as in wardrobe.
- tools/books/README.md: first run, data, import rules, failures. Also covers deleting `/srv/homelab/jelu/` once Dan is happy (it stays in restic history), and the Kuma monitor (AutoKuma `ON_DELETE=delete` removes `jelu`; check with `scripts/kuma-status.py jelu` and delete it by hand in Kuma only if it is still there).
- tools/jelu/: `git rm -r` (compose.yaml, README.md).
- core/dashboard/app/personal.py: `_reading` does GET `${BOOKS_URL}/api/current` (default `http://books:8080`) with no auth, and returns the list unchanged. Keep the output keys title, authors, percent_read, current_page, started, so Hermes's personal.json contract doesn't change. Drop JELU_URL and the basic-auth check.
- core/dashboard/app/town.py: `"library": (("books",), ())`.
- core/dashboard/app/static/town.html: BUILDING_OF `jelu: "library"` -> `books: "library"`.
- core/dashboard/compose.yaml: remove the JELU_USERNAME/JELU_PASSWORD lines and bump the image to `homelab/dashboard:0.18.0`.
- .env.example: remove the Jelu comment line and JELU_USERNAME/JELU_PASSWORD (around lines 84-87). Leave CHANGEDETECTION's lines.
- scripts/backup.sh: PAUSE list and the comment, `jelu` -> `books`.
- scripts/ops-actions.py: the tools tuple, `"jelu"` -> `"books"` (keep it sorted).
- scripts/image-check.py: remove the `"wabayang/jelu"` mapping line.
- CLAUDE.md, docs/README.md, docs/m1-core.md, docs/m4-backups.md, docs/ops-actions.md, docs/m6-research.md, tools/changedetection/README.md, docs/town-mockup.html: see Docs.

New service:
- Name and directory: `books` in `tools/books`. Image `homelab/books:0.1.0` with `build: .`, a local build. The base image and pip pins are the same as tools/wardrobe (python:3.12.15-slim-bookworm, PyPI pins sourced there).
- Port: host 8090 -> container 8080. 8090 is not in the table and not listening. 8089 is listening now because it is Jelu.
- Container settings: `read_only: true`, tmpfs `/tmp:size=64m`, `no-new-privileges`, the logging cap, `restart: unless-stopped`.
- Volumes: `${APPDATA_PATH}/books:/data`. Environment: `TZ: ${TZ}`, `DATA_DIR: /data`. Network: `proxy` (external).
- Traefik labels: router/service `books`, rule ``Host(`books.${DOMAIN}`)``, entrypoint `web`, loadbalancer port 8080.
- Dashboard labels: name `Books`, group `Tools`, icon `calibre-web`, audience `admin`, description `Reading tracker: current book, shelves, Goodreads import`, port `8090`.
- Kuma labels: `kuma.books.http.name=books`, `kuma.books.http.url=http://${LAN_IP}:8090/healthz`. .lan host: `books.lan`.

App rules (decisions the builder must follow):
- Schema: one `books` table: id, goodreads_id, isbn13, isbn10, title, authors (comma string), pages, ol_cover_id, shelf (`reading|want|read|dnf`), rating (NULL or 1-5), date_added, date_started, date_finished, current_page, percent, notes, review, cover_status (`NULL|ok|none|error`), cover_checked_at, created_at, updated_at. Create it on startup and make it migrate-idempotent. Also a `meta` key/value table.
- CSV parsing: read with csv.DictReader, utf-8-sig.
  - ISBN/ISBN13: strip the `="..."` wrapper; empty -> None.
  - My Rating: parse as float then int ("4.0" -> 4); 0 or blank -> None.
  - Exclusive Shelf: read->read, to-read->want, currently-reading->reading. Anything else -> read, with a note `Goodreads shelf: <x>`.
  - Dates: `YYYY/MM/DD` -> ISO, blank -> None. Number of Pages -> int or None.
  - My Review -> review. Private Notes -> notes.
  - Bad rows (no title) are skipped with the reason "no title".
- Dedupe: match on goodreads_id, then isbn13, then lower(title)+lower(first author), in that order.
  - On a match, only fill fields that are empty in the app. Never overwrite edits made in the app.
  - Counts: "updated" if anything was filled, otherwise "skipped: already in library". A repeat row inside the same file counts as "skipped: duplicate in file".
  - The import runs in one transaction. The summary page lists added/updated/skipped with title + reason.
- Import page: a plain `<form method=post enctype=multipart/form-data>` with `<input type=file accept=".csv,text/csv">` and no JS. Max 5 MB.
- First run: on startup, if `/data/seed/goodreads_library_export.csv` exists and meta `seed_imported` is unset, import it, set `seed_imported`, and log the summary.
- Home and progress:
  - Home shows Reading books (cover, title, author, page/% and an "Update progress" form with page or %). If pages is known, percent is computed from current_page.
  - "Finished" leads to a form with 1-5 star radio buttons and a date that defaults to today. It sets shelf=read, date_finished, percent=100.
  - Then the Want to read list, then "Read this year: N" (by the year of date_finished) and a link to Library.
- Library: query params `shelf`, `year`, `q` (LIKE on title/authors). Book page: edit form, plus delete through a confirm page (POST). Marking a book Reading sets date_started=today if it is empty.
- Add book: GET `https://openlibrary.org/search.json?q=<q>&limit=10&fields=key,title,author_name,isbn,cover_i,number_of_pages_median`. Pick a result, choose a shelf, POST. The manual form needs title + author (ISBN optional) and is always shown under the results.
- Covers worker:
  - One daemon thread; one request at a time with a 1 s pause between; each request has a 10 s timeout.
  - Source order: `https://covers.openlibrary.org/b/isbn/<isbn>-M.jpg?default=false`, else `/b/id/<cover_id>-M.jpg?default=false`. With neither, one search.json lookup by title+author takes the first cover_i.
  - Save to `/data/covers/<id>.jpg` through a tmp file + rename. Only accept a 200 with an image/* content-type and fewer than 2 MB.
  - 404 -> `none`. Any other failure -> `error`, retried after 24 h.
  - Served at `/covers/<id>.jpg`. Templates show a CSS placeholder box with the title when cover_status != ok.
- API: `GET /api/current` -> a JSON list of reading books {title, authors (list), percent_read, current_page, started}. `GET /api/stats` -> {read_this_year, want_to_read, reading}. `GET /healthz` -> 200 "ok" after a DB `select 1`.

New env vars: None (JELU_USERNAME and JELU_PASSWORD are removed)

Checks the builder must run:
- `scripts/dc.sh /home/dan/homelab/.worktrees/reading-tracker/tools/books config -q`
- `scripts/dc.sh /home/dan/homelab/.worktrees/reading-tracker/core/dashboard config -q`
- `python3 -m py_compile` on tools/books/app/*.py, tools/books/tests/*.py, core/dashboard/app/personal.py, core/dashboard/app/town.py, scripts/ops-actions.py, scripts/image-check.py; `bash -n scripts/backup.sh`
- `cd tools/books && python3 -m unittest discover -s tests`. The tests cover the `="..."` ISBNs, ratings "0" and "4.0", a missing ISBN, a duplicate row in the file, re-import giving 0 added / 0 updated, the three-step match order, an unknown shelf, and BOM handling.
- An import run against a copy of `/srv/homelab/jelu/files/imports/goodreads_library_export.csv` in a temp dir, through goodreads.py + db.py on :memory:. Expect 38 books (32 read, 5 want, 1 reading); a second run adds 0.
- A grep with `--exclude='*.env*'` for `jelu` over the repo, excluding ideas/, research_notes/, reports/. Only the README's cleanup notes may remain.

Review focus:
- Open Library down or slow during Add book -> show an error line and the manual form within ~8 s; no 500.
- Cover fetch fails, 404s or returns HTML -> marked none/error and retried after 24 h at most. It never blocks an import or a page, and never leaves a partial file.
- Re-importing the same CSV, or one with a duplicate row -> no new rows, and no edits made in the app are overwritten.
- The books container is down -> personal.json's reading block is null with a short error, not stale data. The Town library building shows down.
- iPhone Safari: the upload works without JS, and no input zooms the page (font ≥16px).

Docs:
- CLAUDE.md: change the layout entry `jelu = reading tracker (Goodreads CSV import)` to `books = reading tracker (Goodreads CSV import, Open Library covers), admin; see tools/books/README.md`. In the ports table, remove `| 8089 | jelu |` and add `| 8090 | books |`.
- docs/README.md: replace the Jelu row with a `tools/books/README.md` row.
- docs/m1-core.md: drop the jelu healthcheck row; Buildings line, Library = books.
- docs/m4-backups.md and docs/ops-actions.md: jelu -> books.
- docs/m6-research.md lines 189-192: books being read come from books `/api/current` (no auth); drop the JELU env vars and "Jelu personal notes" (say "book notes").
- tools/changedetection/README.md line 53: the books half is now `tools/books`.
- docs/town-mockup.html: library svc `books`, port 8090.

## Manual steps
1. Before deploying: `scripts/dc.sh tools/jelu down` (deploy-idea doesn't stop services whose compose file was removed).
2. `mkdir -p /srv/homelab/books/seed && cp /srv/homelab/jelu/files/imports/goodreads_library_export.csv /srv/homelab/books/seed/` as dan (the container runs as uid 1000).
3. `scripts/deploy-idea.sh reading-tracker`. This builds books and the dashboard 0.18.0.
4. Remove JELU_USERNAME and JELU_PASSWORD from the env file.
5. Check: Library shows 38 books; `scripts/kuma-status.py books` is up; `scripts/kuma-status.py jelu` is gone (delete it in Kuma if not).
6. Later, once happy: `rm -r /srv/homelab/jelu`.

## Review notes
1. /home/dan/homelab/.worktrees/reading-tracker/tools/books/app/main.py:226: if Finished is submitted with no star picked, `db.finish` writes `rating=NULL` and wipes any rating the book already had. A fix: only pass `rating` when a value was given.
2. /home/dan/homelab/.worktrees/reading-tracker/tools/books/app/db.py:221 (`update_book`): changing a book's shelf to Read on the edit form sets `date_finished` but not `percent=100`. If the book has a current page but no page count, it keeps its old percent. Changing the ISBN on the edit form also leaves `cover_status` as it was, so the cover is never fetched again.
3. /home/dan/homelab/.worktrees/reading-tracker/tools/books/app/covers.py:38-51: a non-404 failure on the ISBN URL (a timeout, or HTML coming back) jumps straight to `error`. It doesn't try the cover-id URL. The book is retried after 24 h and no partial file is left, so this is not a bug.
4. If `/srv/homelab/books` doesn't exist when the container starts, Docker creates it owned by root. The app then fails at import (`os.makedirs(COVERS)`) and keeps restarting. Manual step 2 (mkdir as dan) prevents this, so step 2 must not be skipped.
5. /home/dan/homelab/.worktrees/reading-tracker/tools/books/README.md:47: the "Removing Jelu" step 1 is written in the past tense ("was needed"). The plan's manual step 1 (`scripts/dc.sh tools/jelu down` before deploying) is the one Dan needs to follow.

## Declined to judge
- No login on the books app's writable admin pages: the plan chose this explicitly, to match wardrobe and fitness.
- A 404 cover is never retried (`none` is final): the plan's app rules say 404 → none and retry only `error`.
- No CSRF protection on the POST forms: the same as the other no-login admin apps, and outside this plan.
- A repeated row in one file that has a different Book Id but the same title and author shows as "already in library", not "duplicate in file": the count is the same, only the reason text differs.
- The app wasn't run end to end, because FastAPI isn't installed on the host. The routes and templates were checked by reading.
