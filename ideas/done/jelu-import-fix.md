# Jelu: unstick the Goodreads import (Calibre hang, stale import queue)

Value: 3   (Dan's 29 Goodreads books never arrive; the reading tracker is empty)
Effort: 2  (one config change plus a one-off queue clear and re-import)
Risk: 1    (tools/jelu only; Jelu has one user and no books yet)
Research: yes
Source: Dan 2026-10-23 (first import attempt, done with Claude from the server)

## What happened (2026-10-23)
- The import button in Jelu's UI (and "create API token") did nothing on iPhone Safari: no request
  reached the server. The API works: `POST /api/v1/imports` (multipart `file` + `importConfig` JSON
  `{"shouldFetchMetadata":..,"shouldFetchCovers":..,"importSource":"GOODREADS"}`) with HTTP basic auth
  returned 201. Dan's credentials are in `~/.jelu-netrc` (mode 600) for `curl --netrc-file`.
- Jelu parsed 29 of 38 rows; 9 were skipped for "Missing isbn" (Dan adds those by hand).
- Processing then hung on the first entry: `/opt/calibre/bin/fetch-ebook-metadata -o -d 30 -i <isbn>
  -p Google -p Amazon.com -c ...` plus a calibre-parallel webengine worker, running for 9+ min (the
  Amazon scraper). The processes run as root, so Claude can't kill them; `dc.sh tools/jelu restart`
  clears them, but the next run picks the same entry and hangs again.
- `import_entity` now holds ~58 rows (1 PROCESSING, the rest SAVED), most with
  `should_fetch_metadata` = true, from two imports. Each entry keeps its own flag, so a new import with
  metadata off still processes the old rows first and hangs. 0 rows in `book`/`user_book`.
- The database files under `/srv/homelab/jelu/database/` are not writable by dan (Jelu runs as root).
- Reading `jelu.db` with sqlite3 while Jelu was importing caused one `SQLITE_BUSY` in Jelu's log. Check
  progress through the API or `dc.sh logs`, not the db file.

## Proposal
1. Research Jelu 0.88.2 config (application.yml / env vars): how to drop the Amazon.com provider, set a
   Calibre timeout, or disable Calibre lookups, so a metadata fetch can't hang an import. Pick the
   smallest change in `tools/jelu/compose.yaml` (`environment:`), and note it in `tools/jelu/README.md`.
2. Clear the stale `import_entity` queue: a documented one-off for Dan (Jelu stopped), or an API
   endpoint if Jelu has one. Don't touch the other tables.
3. Manual steps for Dan after deploy: re-run the import (curl command with `--netrc-file ~/.jelu-netrc`,
   metadata on if the fix makes it safe, otherwise off), check 29 books appear, then
   `rm ~/.jelu-netrc ~/.jelu-token`.
4. README: say the UI upload fails on iPhone Safari and give the curl import as the fallback.

## Parked 2026-10-23

## Research
Doable: yes
Size: Effort 1-2 (1 = one env line in compose.yaml plus README; 2 if a small wrapper script for Calibre is added)
Root cause (Jelu v0.88.2 source, CalibreMetadataProvider.kt): Jelu runs fetch-ebook-metadata and calls
`waitFor(timeout=30s)`. When that times out, it never kills the process. It then reads the process's
stdout with `readText()`, and that blocks until Calibre exits. So `jelu.metadata.calibre.timeout` (default 30,
which is also the `-d 30`) can't stop the hang, and raising or lowering it changes nothing. The import
always passes `onlyUseCorePlugins=true`, so it always runs `-p Google -p Amazon.com`. No setting
removes Amazon.com from that list.
How the queue behaves (CsvImportService.kt): imports only fetch metadata when `jelu.metadata.calibre.path` is
not blank, whatever an entry's `should_fetch_metadata` flag says. Each import resets PROCESSING to SAVED,
then works through every SAVED row for the user. Rows whose ISBN already matches a book are merged into
that book, and a read event with the same date is skipped. So the ~58 stale rows (two copies of the
same 29) would import as 29 books, and nobody needs to edit the database. Jelu has no API to delete
queue entries.
Options:
1. Turn Calibre off: add `JELU_METADATA_CALIBRE_PATH: ""` to `environment:` in tools/jelu/compose.yaml.
   The Dockerfile sets it to /usr/bin/fetch-ebook-metadata, and an empty value makes Jelu skip Calibre.
   Then re-upload the CSV with curl, and the old and new rows import from the CSV data alone. Effort 1.
   Downside: no covers, summaries or tags from metadata, and the UI's "auto-fill" lookup has no provider
   left unless Dan later adds the Google Books provider, which needs an API key he would have to create.
   (https://github.com/bayang/jelu/blob/v0.88.2/src/main/kotlin/io/github/bayang/jelu/service/metadata/PluginInfoHolder.kt)
2. Keep Calibre behind a wrapper: commit `tools/jelu/fetch-metadata.sh`, mount it read-only, and point
   JELU_METADATA_CALIBRE_PATH at it. The wrapper drops the `-p Amazon.com` pair and runs
   `timeout -k 10 60 /usr/bin/fetch-ebook-metadata "$@"` (coreutils is in the Ubuntu noble base). Imports
   then get Google-only metadata and covers. Effort 2. Downsides: it depends on the argument shape Jelu
   passes (it may change on upgrade), and a timeout may not kill the calibre-parallel webengine worker.
   (https://github.com/bayang/jelu/blob/v0.88.2/src/main/kotlin/io/github/bayang/jelu/service/metadata/providers/CalibreMetadataProvider.kt)
3. Option 1 now, with Calibre back on (unset) after the import, so per-book UI lookups work again.
   Those could still hang a single UI request on Amazon, but never a queue. Effort 1.
Recommended: Option 1. It is one line, it can't hang, the Goodreads CSV already carries title, author,
pages, dates and shelves, and the 29 books are what matters. Covers can be added per book later.
Unknowns: why the Amazon scraper hangs in the container (webengine and sandbox are untested). With option 2,
whether `timeout` also kills the worker. Why the upload button does nothing on iPhone Safari (not
researched; the curl fallback goes in the README either way).
Note: the "Research: yes" header was the only instruction in the note. It contained nothing that breaks the rules.
Other: this is worth an upstream issue for bayang/jelu (destroy the process after the waitFor timeout).

## Questions
1. Which option: 1 (Calibre off for good), 2 (Google-only wrapper with a hard timeout), or 3 (off for the
   import, back on afterwards)?
2. Is it OK to let the stale queue import as-is? Jelu merges duplicates by ISBN, so you get 29 books, no
   database edits, and the re-upload adds a third copy that merges too. Or do you still want a manual
   clean-up with Jelu stopped?
3. With option 2: should the re-run import fetch covers (shouldFetchCovers true), or metadata only?

## Answers 2026-10-25

1. Option 1: turn Calibre off for good (JELU_METADATA_CALIBRE_PATH empty). No covers is fine.
2. Yes, let the stale queue import as-is (merged by ISBN), no database clean-up.
3. n/a (not option 2).

## Plan
Goal: Stop Jelu imports hanging by turning Calibre metadata lookups off for good (option 1 in Dan's
answers of 2026-10-25), and document the curl re-import that brings in the 29 Goodreads books.
Kind: change to tools/jelu
Files:
- tools/jelu/compose.yaml: under `environment:`, after `JELU_DATABASE_JOURNALMODE: wal`, add
  `JELU_METADATA_CALIBRE_PATH: ""` with a comment above it: `# Calibre off: v0.88.2 never kills a
  timed-out fetch-ebook-metadata, so the Amazon scraper hangs the import queue (ideas/jelu-import-fix)`.
  Write the empty value as the quoted string `""`. A bare key with no value would pass the var
  through from the host instead of setting it empty. Change nothing else.
- tools/jelu/README.md: replace the "Goodreads import" section with:
  * Metadata: Calibre is off (one line on why, as in the compose comment). No covers, summaries or
    "auto-fill" lookups. Covers can be added per book by hand. To turn it back on, remove the env
    line (it could still hang a single UI lookup on Amazon).
  * Upload: the UI's Imports upload (and "create API token") does nothing on iPhone Safari. Use a
    desktop browser or the curl fallback:
    `curl --netrc-file ~/.jelu-netrc -F 'file=@goodreads_library_export.csv;type=text/csv'
     -F 'importConfig={"shouldFetchMetadata":false,"shouldFetchCovers":false,"importSource":"GOODREADS"};type=application/json'
     http://192.168.0.210:8089/api/v1/imports`
    It should return 201. `~/.jelu-netrc` is a mode 600 file containing
    `machine 192.168.0.210 login <user> password <pw>`. Delete it afterwards.
  * Rows without an ISBN are skipped ("Missing isbn" in the logs). Add those books by hand.
  * Queue behaviour: each import resets PROCESSING rows to SAVED and processes every SAVED row for
    the user. Rows whose ISBN matches a book already in the library are merged into it, so a repeat
    upload doesn't create duplicates. Jelu has no API to delete queue rows. Don't edit `jelu.db`.
  * Watch progress with `scripts/dc.sh tools/jelu logs` or the UI, not with sqlite3 on the db while
    Jelu runs (that caused SQLITE_BUSY).
  * Keep the existing line "Imports are a one-off: re-export and re-import to refresh."
New env vars: None (the literal is set in compose; nothing goes in `.env.example`)
Checks the builder must run:
- `scripts/dc.sh <worktree>/tools/jelu config -q`
- `git diff --stat`: only the two files above change
Review focus:
- Empty value dropped or turned into a passthrough by compose (bare key, `~`, or no quotes) -> Jelu
  falls back to the Dockerfile default /usr/bin/fetch-ebook-metadata, and the hang returns. The value
  must be the quoted `""`.
- Stale queue (~58 SAVED/PROCESSING rows, two copies of the same 29) -> no DB edits in the plan or the
  README. The re-upload is documented as safe because rows merge by ISBN.
- The README says to check the logs and the library count, not the db file.
- The README must not hold any real credentials, only the netrc format with placeholders.
Docs: tools/jelu/README.md only. docs/README.md's jelu line ("first login, Goodreads CSV import,
data paths") still fits. No changes to the CLAUDE.md port table or layout.

## Manual steps
1. Deploy (deploy-idea / auto-deploy, Risk 1). This recreates the container and kills the hung
   Calibre processes.
2. Re-upload the CSV with the curl command in the README (metadata and covers false). The stale
   SAVED rows also get processed, now without Calibre.
3. Check the logs and the UI: 29 books in the library, no fetch-ebook-metadata in the logs. Add the
   9 ISBN-less books by hand.
4. `rm ~/.jelu-netrc ~/.jelu-token`.
Optional: open an upstream issue on bayang/jelu (CalibreMetadataProvider never destroys the process
after the waitFor timeout).

## Review notes
1. Jelu's own UI lookup will now find no metadata provider, and the README says so ("no auto-fill lookups"). Dan chose this in his answers.
2. The compose comment runs past 140 columns. It follows the planned wording, so this is only a style point.

## Declined to judge
- Why the UI upload does nothing on iPhone Safari: the plan only asks for a README fallback, not a fix.
- Opening an upstream issue on bayang/jelu: the plan lists it as optional and manual.
