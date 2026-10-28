# Books (reading tracker)

Phone-first reading tracker, replaces Jelu. FastAPI + SQLite, server-rendered, no login, admin only:
`http://192.168.0.210:8090` (also `http://books.lan`). Local build (`homelab/books:0.1.1`); bump the tag in
`compose.yaml` when the code changes.

Pages: Home (currently reading with progress + Finished, want to read, read this year), Library (filter by
shelf/year, search), Add (Open Library search, or by hand), Import (Goodreads CSV).

## First run
As `dan` (the container runs as uid 1000):
```
mkdir -p /srv/homelab/books/seed
cp /srv/homelab/jelu/files/imports/goodreads_library_export.csv /srv/homelab/books/seed/
```
On first start, if `seed/goodreads_library_export.csv` exists and was not imported before, the app imports it
once (meta `seed_imported`) and logs the summary (`scripts/dc.sh tools/books logs`). Expect 38 books
(32 read, 5 want, 1 reading).

## Data
`/srv/homelab/books/` (restic backs it up; the container is paused for the backup): `books.db`, `covers/`, `seed/`.

## Import rules
- Goodreads: My Books, Import and export, Export Library. Upload on the Import page (a plain form post, works in
  iPhone Safari). Max 5 MB.
- ISBN `="..."` wrappers are stripped; rating 0 = no rating; shelves `read`/`to-read`/`currently-reading` map to
  read/want/reading, anything else becomes read with a note `Goodreads shelf: <x>`. Rows without a title are skipped.
- Re-importing is safe. A row matches an existing book by Goodreads Book Id, then ISBN13, then lower-cased title +
  first author. A match only fills fields that are empty; edits made in the app are never overwritten. A repeated
  row inside one file is skipped as a duplicate. The whole import is one transaction.

## Covers
A background thread fetches covers from Open Library (ISBN, else cover id, else one title search), one request
at a time, cached in `covers/`. No cover = a placeholder with the title. A 404 is final (`none`); any other failure
(`error`) is retried after 24 h. Pages and imports never wait for it.

## API (for the dashboard)
`GET /api/current` (books being read), `GET /api/stats`, `GET /healthz`. The dashboard's personal feed reads
`/api/current`; Homelab Town's Library building is this service.

## Failures
- Add page says Open Library didn't answer: use the manual form (8 s timeout, no error page).
- Books container down: `personal.json` reading block is null with a short error; the Library building shows down.

## Removing Jelu
Done in the same change. Afterwards, as `dan`:
1. `scripts/dc.sh tools/jelu down` was needed before deploying (the compose file is gone from the repo).
2. Remove `JELU_USERNAME` and `JELU_PASSWORD` from the env file.
3. `scripts/kuma-status.py jelu` should show nothing once AutoKuma (`ON_DELETE=delete`) has noticed the labels are
   gone. If the monitor is still there, delete it by hand in Kuma.
4. Once happy with Books: `rm -r /srv/homelab/jelu` (it stays in restic history).
