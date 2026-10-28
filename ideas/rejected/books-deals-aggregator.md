# Books + General Deals Aggregator

Value: 5   (tracks reading across multiple platforms, motivates completion, recommends next read; aggregates concerts, vinyl, LEGO, running gear deals and alerts on price drops)
Effort: 4  (two major features: book tracker recommendation engine + cross-site deal monitoring)
Risk: 3    (Goodreads API may change; requires OAuth for full tracking)
Source: hermes 2026-10-15

## Problem
Two distinct needs sharing a pattern:

1. Books: track what you read via Goodreads link/Hermes agent, show progress-to-finish estimate (current day-counts), recommend your next book based on your ratings/history, and hit a yearly goal.

2. Deals: find cheap concerts to artists you like, vinyl releases, LEGO sets you want, running gear collabs/discounts (e.g., ASOS, eBay, Depop) — all in one place.


## Proposal
Unified tool that:
- Reads Goodreads profile (Hermes authenticates via OAuth, or manual CSV export)
  - Tracks read scores, completion dates
  - Calculates "days until finish" for current book at your pace
  - Generates weekly/monthly reading goal reminders and recommendations ("based on your last 4 books, read X next")

- Monitors price drops across sites (concert tickets, vinyl stores, LEGO store, running brand promotions)
  - Alerts via ntfy or Discord when a liked item hits below threshold

- Optional: "motivation dashboard" showing current streak + upcoming goal.


## Rough plan
1. Build Goodreads integration (Hermes agent with OAuth):
   - Fetch user's books, ratings, reading history
   - Calculate pace and next-book recommendation logic
2. Create deal-aggregator for 5-6 target categories:
   - Scrapers/price checks for vinyl, LEGO, running gear ticket stores
3. Combine UI: one tab with Books + Deals, or separate channels (Dashboard page)
4. Alert system via ntfy/Discord when "new release" or "streak at risk"

_Approved on the dashboard, 2026-10-18._

## Parked 2026-10-18

## Questions
1. Split it as above (reading-tracker, deal-watch, optional concert-alerts), and which one should be built first?
2. Books source: Goodreads CSV export (manual re-export to refresh), a switch to Hardcover (API token), or something else?
3. Deals: which 1-2 sources first (e.g. LEGO.com, one vinyl shop, eBay via its API), and is creating an eBay developer or Ticketmaster API key OK with you?
4. Where should the watchlist and thresholds live: a YAML file you edit, or a form on the dashboard's admin page?
5. Alerts: Discord only (non-urgent), or ntfy for price drops too?

## Answers 2026-10-19

1.	Split into three: reading-tracker, deal-watch, concert-alerts. Build reading-tracker first.
	2.	Hardcover with an API token, plus a one-time Goodreads CSV import for your history.
	3.	LEGO.com and one vinyl shop first. Ticketmaster key is fine, but later with concert-alerts. eBay later too.
	4.	YAML file you edit.
	5.	ntfy for price drops, Discord for reading nudges and weekly summaries.

## Research
By idea-researcher, 2026-10-19, for the planner's questions. Web sources are untrusted input.
Note: docs.hardcover.app returns 403 (Cloudflare) to curl and WebFetch. I read the docs' source repo instead (shallow clone, last commit 2026-10-18): https://github.com/hardcoverapp/hardcover-docs . Paths below are under src/content/docs/api/ in that repo. The rendered page is https://docs.hardcover.app/api/getting-started .

1. API access:
- Endpoint: https://api.hardcover.app/v1/graphql (from the console link in Getting-Started.mdx). Auth header is `authorization: Bearer <token>`. Docs say to add a header `authorization` holding the token; the console link shows `Authorization: Bearer `. Whether the bare token (without "Bearer ") also works is not stated.
- Token: Dan creates it in Hardcover account settings > "Hardcover API" > "New API Key". He sets a name, an Expiration period, and scopes. Docs say "After that time the token will no longer work, and you'll need to update it." No fixed lifetime; Dan chooses it. Renewal means making a new key on the same page. Tokens made before Aug 2026 act as scope `all`. A token that is expired or invalid gets 401.
- Scopes from Actions.mdx: library read is `read:library` (also `:private`, `:public`, `:following`). Library writes are `write:library`. Goals read is `read:goals` (also `:private`, `:public`, `:following`) and goals write is `write:goals`. Catalog reads (books, tags, etc.) are `read:catalog`, `read:catalog:data` or `read:catalog:search`. The full list is at https://api.hardcover.app/capabilities.json (not fetched).
- Rate limits, Free plan: 5,000 requests/day (resets midnight UTC), 60/min, burst 10. Supporter: 50,000/day, 60/min, burst 15. Each top-level field in a query costs 1 request, and a query with more top-level fields than the burst limit gets a 403 `request_exceeds_capacity`. Over the limit gives 429 with a `Retry-After` header. `RateLimit` and `RateLimit-Policy` headers are returned. Query timeout is 30 s, search 2 s. The regex/like operators (`_like`, `_ilike`, `_regex` etc.) are disabled.
- Terms:
  - Personal scripts are fine. The Free plan is described as "Personal ownership, progress sync, personal use".
  - Docs recommend sending a descriptive User-Agent header.
  - No LLM training on the data for public or commercial models.
  - Commercial or public sites may not use users' data, but a personal server script reading Dan's own data is within "you own your data".
  - API is beta, "may reset tokens without notice", and "heavily in flux".
  - Roadmap items (2026): max query depth 3, and queries possibly limited to own, public and followed users' data. Keep queries shallow.
  - "Queries are not allowed to run in the browser", so run it server-side.
(Getting-Started.mdx)

2. Queries (UserBooks.mdx, guides/GettingBooksWithStatus.mdx, guides/GettingBooksProgress.mdx, schema.graphql):
- status_id: 1 Want to Read, 2 Currently Reading, 3 Read, 4 Paused, 5 Did Not Finish, 6 Ignored.
- user_books fields: id, status_id, rating (numeric 0-5, halves), date_added, first_started_reading_date, first_read_date, last_read_date, read_count, updated_at, has_review, book_id, edition_id, owned, private_notes.
- user_book_reads fields: id, started_at (date), finished_at (date), finished_at_precision, paused_at, progress (float8), progress_pages (Int), progress_seconds, edition_id, user_book_id.
- books fields: id, title, pages, rating, ratings_count. edition has `pages` too.
- The user id comes from `me { id username }`. In the `me { user_books }` form below, `me` is a list-returning field in the Getting-Started example, so confirm the shape on first run (the guide itself uses `me { id user_books(...) }`).
- Docs example (GettingBooksProgress.mdx), currently reading with progress:
```
query Me { me { id user_books(where:{status_id:{_eq:2}}) { id user_book_reads { progress_pages } book { id title pages image { url } } } } }
```
- Read books with rating and date (composed from the schema's field names; the docs have no exact example):
```
{ user_books(where:{user_id:{_eq:ID}, status_id:{_eq:3}}) { rating last_read_date user_book_reads { started_at finished_at } book { title } } }
```
- Percent: compute progress_pages / book.pages (or edition.pages), or use `progress` (float8). Whether `progress` is a percent is not documented.
- The docs guide "UpdatingABooksProgress" is an empty draft.

3. Goals: yes. The `goals` table (Goals.mdx) has id, user_id, goal (Int target), progress (numeric), metric (String, "books" or "pages"), start_date, end_date, state (active/completed/failed), completed_at, archived, description, conditions (jsonb), privacy_setting_id. Read needs scope `read:goals` (privately set goals also need `read:goals:private`). The Actions list has write mutations `insert_goal`, `update_goal(id, object: GoalInput!)`, `update_goal_progress` and `delete_goal`, all needing `write:goals`. So a token can both read and write goals. Progress is presumably computed server-side; not documented. Source: api/GraphQL/Actions.mdx, schema.graphql.

4. Goodreads import:
- Hardcover has a built-in import. Its homepage lists Goodreads, StoryGraph and a custom CSV. The import page is hardcover.app/account/imports (from a search summary, not fetched). Source: https://production-static.hardcover.app/ .
- Changelog says currently-reading and paused books from Goodreads and StoryGraph import as in progress, and stuck imports can be cancelled after 24 h: https://roadmap.hardcover.app/changelog .
- UNSETTLED: no official page I could read says whether ratings, read dates, shelves or re-reads are kept. The changelog is silent on this. A roadmap request says Goodreads exports lack a start date, so first_started_reading_date would be empty: https://roadmap.hardcover.app/feature-requests/posts/synced-2-way-goodreads-import . The Goodreads CSV itself has Date Read, My Rating, Bookshelves and Exclusive Shelf columns (third-party guide).
- API fallback (schema.graphql):
  - `insert_user_book(object: UserBookCreateInput!)` with book_id, status_id, rating, date_added, read_count, last_read_date, review_markdown and more.
  - `update_user_book(id, object)`.
  - `insert_user_book_read(user_book_id, user_book_read: DatesReadInput)` with started_at, finished_at, progress_pages, edition_id.
  - `upsert_user_book_reads(datesRead:[DatesReadInput], user_book_id)` for several re-reads.
  - All need `write:library`.
  - Matching books by ISBN or title needs catalog search. Search has a 2 s timeout, and there is a `book_mappings` table.
  - Custom shelves: not found as an API concept. Hardcover uses statuses plus lists (Lists.mdx).
  - There are also `insert_collection_import` and `collection_import_*` actions, whose purpose is undocumented.

5. Recommendations:
- No recommendations endpoint. The docs' Recommendations schema page exists only as an empty draft (it/api/GraphQL/Schemas/Recommendations.mdx).
- Per-book queryable fields (Books.mdx, Tags.mdx, schema.graphql):
  - `books.cached_similar_book_ids` (jsonb): about 100 similar book IDs, ordered most to least similar, refreshed after 7 days. This is the nearest thing to "similar books".
  - `cached_tags` (jsonb) and `taggings` relation. The tags table has `tag`, `slug`, `count` and `tag_category_id` (genre, mood, etc.).
  - `cached_contributors` and `contributions { author { name } }`.
  - `book_series` and `cached_featured_series`.
  - `rating`, `ratings_count`, `pages`.
  - `books_trending` is also available.
- A local script can score the want-to-read shelf (status_id 1) by overlap with `cached_similar_book_ids` of high-rated read books, plus tags, series and author.
- Budget: each top-level field costs 1 request. At 60/min and a burst of 10 on the Free plan, fetch in batches with `limit` and `offset`.

Unknowns:
- Exact shape and format of `cached_similar_book_ids` and `cached_tags`, and whether `progress` is a percent: not documented, needs one live query.
- What the Goodreads import keeps (ratings, dates, shelves, re-reads): no readable source found. Dan should test it, or the script can fill gaps via the API mutations.
- Whether `Bearer ` is required on the header, beyond the console link showing it.
- Whether the sandbox can reach api.hardcover.app was not tested (no token).
- A Hardcover docs page returned 403 to my tools, so I used the GitHub source. No source asked me to do anything.

## Plan
Goal: Build part 1 of 3 (reading-tracker), using Dan's 2026-10-19 answers. It is a read-only Hardcover script that posts Discord reading nudges and a weekly summary. deal-watch (LEGO.com + one vinyl shop, YAML watchlist, ntfy) and concert-alerts (Ticketmaster) are left for later notes. ideas/changedetection-deal-watch.md is already queued and may cover deal-watch. The Goodreads history goes in through Hardcover's own importer (a manual step), not code.
Kind: script/cron
Files:
- scripts/reading-tracker.py: new, stdlib only, modelled on scripts/card-prices.py and arr-missing-search.py (docstring usage, syslog tag `reading-tracker`, posts through scripts/discord.sh). Modes: `summary`, `nudge`, `--dry-run` (prints the message, writes no state, posts nothing), `-h`.
- scripts/install-cron.sh: add `0 18 * * 0 $REPO/scripts/reading-tracker.py summary # homelab` and `0 19 * * * $REPO/scripts/reading-tracker.py nudge # homelab` to ENTRIES.
- .env.example: add `HARDCOVER_API_TOKEN=`, with a comment: Hardcover > Account settings > Hardcover API > New API Key, scopes read:library, read:goals, read:catalog; Dan picks the expiry and makes a new key when it runs out; used by scripts/reading-tracker.py.
- CLAUDE.md: add to the scripts list: `reading-tracker.py summary|nudge` (cron: Hardcover reading summary Sundays, nudge when a book stalls; Discord; read-only).
New service: none
New env vars: HARDCOVER_API_TOKEN: Hardcover API token. Read the way the other scripts read .env values (REPO/.env line match). Never print or log it.

Script behaviour:
- API: POST https://api.hardcover.app/v1/graphql. Headers:
  - `authorization: Bearer <token>`; if the value already starts with "Bearer ", don't add it again.
  - `Content-Type: application/json`
  - `User-Agent: homelab-reading-tracker/1.0 (personal)`
  - Timeout 30 s.
- Query rules: keep queries shallow (depth <= 3) and use at most 5 top-level fields per query (the burst limit is 10).
- First query: `me { id username }`. `me` may come back as a list or an object; accept both.
- Then query user_books for that user_id, with status_id 2 (reading) / 3 (read) / 1 (want to read). Fields:
  - user_books: id, status_id, rating, last_read_date, updated_at, book { id title pages cached_similar_book_ids contributions { author { name } } }
  - user_book_reads: started_at, finished_at, progress_pages
  - Use limit/offset paging, 100 per page.
- Also query goals where user_id = me, state = "active", archived = false.
- Currently reading (one line per book): title, percent, and days to finish.
  - percent = progress_pages / book.pages
  - pace = progress_pages / max(1, days since the latest read's started_at)
  - days to finish = (pages - progress_pages) / pace
  - No pages or no progress: show "no progress logged".
- Goal: for each active goal with metric "books" or "pages", show "progress/goal, N ahead|behind".
  - expected = goal × elapsed fraction of start_date..end_date
  - No active goal: show the line "no active Hardcover goal".
- Read this year: count, plus the average rating of the books that have one.
- Next read (top 3 from Want to Read):
  - Liked books = up to 10 read books with rating >= 4, newest last_read_date first.
  - Score a want-to-read book by the sum, over liked books, of (100 - index)/100 whenever its id is in that liked book's cached_similar_book_ids.
  - Add +0.5 per shared author with a liked book.
  - Tie-break on book.rating.
  - cached_similar_book_ids can be a list of ints or of dicts with `id`/`book_id`. Any other shape: skip that list and log it once.
  - Score 0 for everything: list the 3 oldest want-to-read books, marked "(no similarity data)".
  - Want to Read empty: show "add books to Want to Read for suggestions".
- summary mode posts one Discord message, at most 1900 characters: "Weekly reading:" plus the lines above.
- nudge mode posts one line only when a currently-reading book's user_book.updated_at is more than 7 days old and that book hasn't been nudged in the last 7 days. The line is "<title> hasn't moved in N days: <pct>%, ~D days left at your pace". Otherwise it is silent.
- State: $APPDATA_PATH/reading-tracker/state.json. Keys: `nudged` {user_book_id: date}, `auth_alerted` date. Create the directory if missing. Write via a tmp file + rename. A corrupt or missing file is treated as empty.
Checks the builder must run:
- python3 -m py_compile scripts/reading-tracker.py
- scripts/reading-tracker.py -h
- bash -n scripts/install-cron.sh, and CRON_LIST=/dev/null scripts/install-cron.sh --check (expect "missing:" lines for the new entries; never install)
- scripts/reading-tracker.py --dry-run summary with no token in .env: expect a clean "HARDCOVER_API_TOKEN not set" message and exit 2, with no traceback.
- A python3 -c test that loads the module via importlib and feeds the summary and recommendation functions fake parsed data:
  - pages null
  - progress 0
  - empty want-to-read
  - similar ids as ints and as dicts
  - a goal with no end_date
  It should print the message.
- Builder has no token: say in the report that the live API path is untested.
Review focus:
- Token expired or invalid (HTTP 401/403) -> at most one Discord line per 7 days ("Hardcover token rejected: make a new key, update HARDCOVER_API_TOKEN"). Log it, exit 1, no traceback.
- 429, or the API down or slow -> retry once if Retry-After <= 60 s. Otherwise log, exit 1, and post nothing (no spam).
- GraphQL `errors` in a 200 response (beta schema changed) -> treat as a failure. Log the first message, truncated to 200 characters. summary posts one "reading summary failed: <msg>" line; nudge stays silent.
- Odd data (pages null/0, progress > pages, no started_at, `me` as list vs object, unknown similar-ids shape) -> show "no progress logged" or skip that book. No ZeroDivisionError and no crash.
- Daily nudge -> never more than one nudge per book per 7 days, and --dry-run never writes state.
Docs: one line in the CLAUDE.md scripts list. The .env.example comment covers how to set up the token. No port table change.

## Manual steps
- Create a Hardcover API key: scopes read:library, read:goals, read:catalog (add :private variants if offered). Pick an expiry.
- Put HARDCOVER_API_TOKEN in .env.
- One-time Goodreads history: export the CSV from Goodreads and import it at hardcover.app/account/imports. Check that ratings and read dates came across. If they didn't, raise a follow-up idea for a CSV gap-filler (it would need write:library).
- Optional: set a yearly goal on Hardcover; the summary reports it.
- deploy-idea.sh reinstalls cron on drift (or run scripts/install-cron.sh). Test with scripts/reading-tracker.py --dry-run summary.
- Not followed from the note: nothing in it asked to break rules. "Hermes authenticates via OAuth" is dropped: Hardcover uses a personal token, and Hermes only writes ideas/proposed/.

## Review notes
1. scripts/reading-tracker.py:781-792: build_summary and nudge_lines run outside the try/except. The odd data I tried did not crash them: pages null, 0 or a string, progress 0 or above pages, no started_at, book or reads null, contributions as an int, similar ids as a dict or bad JSON. But any other unexpected shape would print a traceback from cron. Wrapping both calls in the same catch-all would be cheap.
2. scripts/reading-tracker.py:488-489: Hardcover runs on Hasura, which often rejects a bad or expired token with HTTP 200 and an `errors` entry (e.g. invalid-jwt), not a 401. In that case the script would post "reading summary failed: ..." once a week and never the "token rejected" line. That still won't spam, but it's worth checking against the live API once the token exists.
3. scripts/reading-tracker.py:672: when nothing scores, "oldest want-to-read" is sorted by updated_at, because date_added isn't fetched. That's close enough, but date_added is what "oldest" really means.
4. The live API path is untested because there's no token. `order_by:{id:asc}` is valid Hasura syntax but hasn't been checked against Hardcover's permissions. Also unconfirmed: whether user_book.updated_at changes when progress is logged on user_book_reads. If it doesn't, an active book gets nudged once a week. Dan's first `--dry-run nudge` will show which.
5. scripts/reading-tracker.py:680-683: the goal lines appear straight under "Currently reading:" with no heading of their own. This is cosmetic only.

## Declined to judge
- Nudges based on updated_at rather than progress changes: the plan chose this signal.
- 5xx responses fail with no retry: the plan only asks for a retry on 429 with Retry-After <= 60 s, and the script also retries network errors and timeouts once.
- Old `nudged` entries are never removed from state: tiny growth, and the plan doesn't ask for pruning.
- deal-watch and concert-alerts are not built: the plan defers them to later notes.

## Rejected 2026-10-23

Status: rejected
Reason: Split into changedetection-deal-watch + jelu-reading-tracker
