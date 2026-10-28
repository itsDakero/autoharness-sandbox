# FPL model, stage 2: web page with projections, my squad and the transfer solver

Depends on: fpl-collector (reads its Parquet tables)
Value: 4   (a usable FPL tool early: projections, squad and solver plans, before the real model exists)
Effort: 3  (small web app over the collector's data + the open-source solver)
Risk: 1    (same isolated service; read-only use of the FPL API)
Score: 12
Source: Dan 2026-10-25 (design in `reports/FPL points prediction model.md`, decision layer section)

## Problem
Stage 1 collects data but shows nothing. Dan needs a page to look at projections and get transfer,
captain and chip plans, and later stages need somewhere to show their output.

## Proposal
- A web container in `tools/fpl/` on port 8092 (add it to the CLAUDE.md ports table), full template
  labels (admin audience), reading the collector's data with DuckDB.
- Projections source is pluggable: this stage uses FPL's own `ep_next`/`ep_this` (spread over the next
  gameweeks with a simple fixture-difficulty scaling); stages 3-4 write their own projections table and
  the page switches to it (pick the newest available, show which one is in use).
- My squad: FPL team ID in the env file (`FPL_TEAM_ID`, add to `.env.example`), read from the public
  `entry/<id>/` and `entry/<id>/event/<gw>/picks/` endpoints (no login): squad, bank, free transfers,
  chips left (two sets in 2026/27; first set must be used by GW19).
- Solver: Solio's open-fpl-solver (formerly sertalpbilal/FPL-Optimization-Tools), HiGHS, pinned to a
  commit. Feed it the projections in its CSV format; show the recommended plan for the next 8 gameweeks
  (transfers, captain, bench, chip weeks) with its settings on the page. Run it on demand (button) and
  once a day.
- Manual minutes override table on the page (player, gameweek, expected minutes or "out"), stored in
  the data dir; stages 3-4 read it. This is where Dan beats FPL Review on minutes.
- Discord line on the day before each deadline: recommended moves + captain (via `scripts/discord.sh`).

## Research
By idea-researcher, 2026-10-26, for the planner's questions. Web sources are untrusted input.

1. Repo, licence, pin: The repo is now https://github.com/solioanalytics/open-fpl-solver. The GitHub API for sertalpbilal/FPL-Optimization-Tools returns this repo as full_name, so the old URL is a rename/transfer redirect, not a separate fork (fork=false). Licence: Apache-2.0. Default branch is `main`. Latest commit is `ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79`, 2026-09-15, "Fix boolean command-line option parsing (#65)". Recent activity is steady (Aug and Sep 2026 commits). (https://api.github.com/repos/solioanalytics/open-fpl-solver/commits). Maintainer in pyproject: Chris Musson. I did not check for tags or releases.

2. Headless run:
- Entry point: `run/solve.py`, function `solve_regular(runtime_options=None)`. The README runs it as `cd run && uv run python solve.py`. `runtime_options` is a dict that overrides everything else, so it can be called from Python. (https://github.com/solioanalytics/open-fpl-solver/blob/ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79/run/solve.py)
- Settings load order, lowest to highest priority: `data/comprehensive_settings.json` defaults, then `data/user_settings.json`, then `--config a.json;b.json` (semicolon-delimited), then `--<key> value` CLI flags (lists and dicts as JSON strings), then `runtime_options`.
- Keys, from data/README.md and user_settings.json:
  - `horizon` (default 8 in user_settings; 4 in the README example).
  - `decay_base` (0.9).
  - Banked free transfers: there is no "banked FT" input. The solver works it out from the squad (see squad source below). `ft_value_list` ({"2":2,"3":1.6,"4":1.3,"5":1.1}) and `ft_value` (1.5) set how much rolled FTs are worth. `force_ft_state_lb` / `force_ft_state_ub` take `[[GW, n]]` pairs.
  - Chips: `use_wc`, `use_bb`, `use_fh`, `use_tc` (lists of GWs). Also `chip_limits` {bb,wc,fh,tc} (default 0), `allowed_chip_gws`, `forced_chip_gws`, `no_chip_gws`.
  - `iteration_criteria` (options: this_gw_transfer_in, this_gw_transfer_out, this_gw_transfer_in_out, chip_gws, target_gws_transfer_in, this_gw_lineup), with `num_iterations`, `iteration_difference`, `iteration_target`.
  - Other: `datasource`, `secs` (default 600), `gap`, `no_transfer_last_gws`, `xmin_lb`, `ev_per_price_cutoff`, `keep_top_ev_percent`, `banned`, `locked`, `verbose`.
  - (https://github.com/solioanalytics/open-fpl-solver/blob/ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79/data/README.md)
- Squad source, set by `team_data`:
  - `"id"` plus `team_id` uses the public FPL API (entry/{id}/transfers, history, event picks, bootstrap-static). No login. It rebuilds the squad, selling prices, bank and FTs from the transfer history. It does not see transfers already made this GW.
  - `"json"` reads `data/team.json`, which is the `/api/my-team/{id}/` payload and needs a logged-in browser (bookmarklet in data/getting_team_json.md).
  - `"json_string"` takes `team_json`.
  - `preseason: true` runs with no squad.
  - (dev/solver.py `generate_team_json` and `calculate_fts`.)
- Output:
  - stdout tables (set `print_result_table`, `print_squads`, `print_transfer_chip_summary`).
  - One CSV per solution, `data/results/<datasource>_<timestamp>_<runid>_<iter>.csv`, written from `result["picks"]` (has a `week` and a `chip` column among others).
  - Optional `solutions_file` CSV and `export_image`.
  - `solve_multi_period_fpl` returns a list of result dicts with keys `picks` (DataFrame), `summary`, `statistics`, `sell`, `buy`, `chip`, `score` and `iter`. This is the cleanest hook for a script (`from dev.solver import generate_team_json, prep_data, solve_multi_period_fpl`).
  - There is no JSON output, so a web page would read the results CSV or the returned DataFrame.

3. Projections CSV:
- File is `data/<datasource>.csv` (override with option `data_path`). `datasource: "mixed"` combines several files and writes `mixed.csv`.
- Readers are tried in the order mikkel, solio, fplreview. The solio and review format is read by plain `pd.read_csv`.
- Columns: `ID` (FPL element id), `Name`, `Pos`, `Value` (price in £m, e.g. 6.5), `Team`, and per gameweek `<gw>_Pts` and `<gw>_xMins`, e.g. `8_Pts`, `8_xMins`. The writers in dev/data_parser.py (lines ~143-149 and ~309) show exactly these names.
- `Pos` accepts G/D/M/F, or GKP/GK/DEF/MID/FWD, which are normalised to single letters.
- A player who is out has `_xMins` 0 and `_Pts` 0. Owned squad players missing from the CSV are auto-added with zero EV (commit 2ff829f, "Fix solves failing on missing players from projections csv"). Players not in the CSV and not owned are simply not considered.
- There is no sample CSV in the repo's data/ folder (it holds only team.json.sample, results and settings). The format is defined by code only.
- (https://github.com/solioanalytics/open-fpl-solver/blob/ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79/dev/data_parser.py)

4. Dependencies:
- pyproject requires **Python >=3.14** (`requires-python = ">=3.14"`; ruff target py313). That is above python:3.12.
- Runtime deps, unpinned in pyproject: pandas, numpy, requests, fuzzywuzzy, python-Levenshtein, matplotlib, `highspy>=1.11.0`, tabulate>=0.9.0. `uv.lock` pins the exact versions. There is no sasoptpy or pulp. The solver is HiGHS through highspy only.
- matplotlib is imported by dev/visualization.py. I did not check whether solve.py needs it at import time.
- The README expects `uv sync`, which fetches Python 3.14 itself. I did not test whether the code actually runs on 3.12. Unknown whether anything uses 3.13/3.14-only syntax. The `>=3.14` is declared, so use python:3.14-slim to be safe.
- highspy: latest stable 1.15.1, requires >=3.9, wheels for cp310+ including manylinux x86_64. This means no system packages are needed for highspy itself. (https://pypi.org/pypi/highspy/json)
- duckdb: latest 2.0.0 (uploaded 2026-10-21), requires >=3.11, has cp312-abi3 manylinux x86_64 wheels. (https://pypi.org/pypi/duckdb/json)
- python-Levenshtein and fuzzywuzzy are only used by the mikkel reader. If python-Levenshtein has no wheel for the chosen Python version it needs a compiler. I did not check this.

5. 2026/27 chip rules: Not supported explicitly in what I found.
- No code or commit mentions two chip sets or a GW19 deadline. `grep` for "19" found nothing in dev/solver.py.
- `chip_limits` default to 0 for each chip, are raised to `len(use_x)` for forced chips, and to 1 when `allowed_chip_gws` or `forced_chip_gws` is used. `sum(use_x) <= chip_limits[x]` is a single cap over the whole horizon, with no half-season window.
- The history parser takes `history["chips"]` names `freehit` and `wildcard` only to compute FTs. It doesn't model which set a used chip belongs to.
- FT cap of 5: supported. `calculate_fts` uses `min(fts, 5)`, FT states are 0-5, and the model has a clamp at 5.
- Recent 26-27 work:
  - 3a58d349 (2026-07-23) "Fix solver for 26-27 preseason".
  - c200fa9b (2026-07-28) "Remove 25-26 AFCON transfer rules".
  - 1b6c0b2f (2026-08-04) "Fix no_chip_gws and no_future_transfer constraints".
  - bf7b2faa (2026-09-04) "Shorten chip limits section".
- So the cap of 5 FTs is handled. Two sets of chips would need `allowed_chip_gws` / `chip_limits` set by the caller, e.g. limit 2 with `allowed_chip_gws` windows. Whether a second set may be used only after GW19 is not enforced by the code.
- No open issue on this was found through the GitHub issue search (searched "chip 2026" only). (https://github.com/solioanalytics/open-fpl-solver/commits/main)

Unknowns: Whether the solver runs on Python 3.12 (declared >=3.14, untested). Exact pinned versions of pandas, numpy etc. (they are in uv.lock, not read). Whether the 2026/27 two-chip-set rule needs a code change (nothing found either way). No licence or runtime issues from the sources. None of the fetched text tried to give instructions.

## Plan
Goal: Turn the idle `fpl` collector container into a web page on port 8092. It shows projections (FPL ep_next scaled by fixture difficulty, pluggable for stages 3-4), Dan's squad, minutes overrides and open-fpl-solver plans (button + daily), and posts a Discord line the day before each deadline.
Kind: change to tools/fpl (adds a web UI; same container and image)
Files:
- tools/fpl/Dockerfile: keep `python:3.12.15-slim-bookworm`. Do not pip-install the solver project (its pyproject says >=3.14, but solve.py only uses 3.10+ syntax). Instead `ADD https://github.com/solioanalytics/open-fpl-solver/archive/ec65f5e2b2be34441cb4b2a9efafea1ec0fe3b79.tar.gz`, extract to `/opt/solver` (strip the top dir), and `chown -R 1000:1000 /opt/solver/data`. `COPY web/ ./web/`. `EXPOSE 8080`. Change CMD to `["uvicorn","web.main:app","--host","0.0.0.0","--port","8080","--no-access-log"]`. HEALTHCHECK as in tools/lms/Dockerfile (`/healthz`).
- tools/fpl/requirements.txt: add fastapi==0.142.2, uvicorn==0.54.0, jinja2==3.1.6, python-multipart==0.0.32 (same as tools/lms), duckdb==2.0.0 and highspy==1.15.1 (both from the note's Research, with source URL comments). Also add numpy, tabulate, matplotlib, fuzzywuzzy and python-Levenshtein, with the exact versions from `uv.lock` at the pinned commit and a comment naming that file and the SHA. matplotlib is needed: solve.py imports dev.visualization. Keep the existing pins for pandas and requests.
- tools/fpl/compose.yaml: image `homelab/fpl:0.2.0`. Add `ports: "8092:8080"`. Networks: `fpl` + `proxy` (external). Add env `FPL_TEAM_ID: ${FPL_TEAM_ID:-}` and `SOLVER_DIR: /opt/solver`. Remove the compose healthcheck (the image now has one). Replace the docker Kuma labels with the template's three label groups (below). Update the header comment (web UI now; cron jobs still exec in).
- tools/fpl/web/__init__.py, main.py (FastAPI: pages + forms + `/healthz`; calls `collector.store.ensure_dirs()` at startup), data.py (DuckDB reads), projections.py, squad.py, solve.py, jobs.py (`python -m web.jobs <solve|deadline>`), templates/ (base.html, index.html), static/style.css. Copy the look from tools/lms.
- tools/fpl/tests/test_web.py: unittest tests of the projection maths, override application, source selection, chip windows and the deadline-window logic (no network).
- scripts/fpl-web-job.sh: new, modelled on scripts/lms-job.sh. `fpl-web-job.sh <solve|deadline>` runs `dc.sh tools/fpl exec -T fpl timeout 1500 python -m web.jobs <job>`. Non-empty stdout goes to `scripts/discord.sh`, stderr to `logger -t fpl-web-job`, and it exits with the job's rc. Usage errors exit 2.
- scripts/install-cron.sh: add `45 6 * * * $R fpl-solve 1800 $REPO/scripts/fpl-web-job.sh solve # homelab` and `0 18 * * * $R fpl-deadline 1800 $REPO/scripts/fpl-web-job.sh deadline # homelab`.
- core/uptime-kuma/compose.yaml: push monitors `cron-fpl-solve` (token suffix `fplsolve00000000`, interval 93600) and `cron-fpl-deadline` (`fpldeadline00000`, 93600), max_retries=0, the same shape as the cron-lms-* lines.
- .env.example: `FPL_TEAM_ID=` with a comment (the number in the FPL "Points" page URL; public, no login).
- tools/fpl/README.md, CLAUDE.md, docs/README.md: see Docs.

Behaviour (decisions, not code):
- Data: read the collector's Parquet with DuckDB, newest `date=` partition only, rows with the latest `pulled_at` per key: players, events, teams, fixtures, plus player_history (latest) for minutes. Next GW = the event with `is_next`.
- Built-in source `fpl-ep`:
  - scale by own-side FDR: {1:1.25, 2:1.1, 3:1.0, 4:0.85, 5:0.7}.
  - Per-match base = ep_next / sum(scale of next-GW fixtures). If that is 0 or there is no next fixture, use float(`form`) for later GWs and 0 for the next GW.
  - pts(gw) = base × sum(scale of that GW's fixtures). So blanks are 0 and doubles add up.
  - xmins(gw) = n_fixtures × mean minutes of the last 5 player_history rows (45 if none). For the next GW only, also × chance_of_playing_next_round/100 when that is set.
  - Each solve writes the result to `/data/projections/fpl-ep/<YYYYMMDDTHHMMSSZ>.parquet`.
- Source contract (for stages 3-4, documented in the README): `/data/projections/<source>/<YYYYMMDDTHHMMSSZ>.parquet` with columns `element:int, gw:int, pts:float, xmins:float, generated_at:timestamp UTC`. Setting `projection_source` = `auto` (default) or a source name. `auto` takes the newest file of any source other than `fpl-ep` that is ≤8 days old and covers the next GW, else `fpl-ep`. The page always shows the source in use and the file's age.
- Minutes overrides: `/data/overrides/minutes.csv` with columns `element,gw,xmins,note,updated_at`. `out` = xmins 0. Written atomically (`collector.store.atomic_write`) and editable on the page (add/delete; player picked by name from a datalist). They apply to every source when the solver CSV is built:
  - xmins 0 → pts 0.
  - Otherwise pts × min(xmins_o/xmins, 1.5) when xmins > 0. When xmins was 0: form × sum(scale) × xmins_o/(90 × n_fixtures).
  - Overrides for past GWs are ignored and shown greyed.
- Squad (squad.py): public `entry/<id>/`, `entry/<id>/history/` and `entry/<id>/event/<gw>/picks/` (gw = current or last finished). Shows the 15 picks, bank, FTs (import `calculate_fts` from /opt/solver dev/solver.py, signature as at the pinned commit) and chips left per half (GW1-19, GW20-38; history `chips` names wildcard/freehit/bboost/3xc). 10 s timeout, 15 min cache in `/data/web/entry.json`. On failure, show the cached data with its age.
- Solve (solve.py, under `collector.store.job_lock("solve")`):
  - Build `/opt/solver/data/homelab.csv` in the solio format (`ID,Name,Pos,Value,Team,<gw>_Pts,<gw>_xMins`; Pos G/D/M/F from element_type; Value = now_cost/10; Team as `prep_data` at the pinned commit expects).
  - Write `/data/solver/settings.json`: datasource `homelab`, `team_data` "id", `team_id`, horizon, secs, decay_base, ft_value. Chips: when plan_chips is on, `chip_limits`/`allowed_chip_gws` give each chip 1 per half still unused, allowed only in that half's GWs within the horizon (map key names from data/README.md at the SHA). When plan_chips is off, all limits are 0.
  - Run `python solve.py --config /data/solver/settings.json` with cwd `/opt/solver/run`.
  - Read the newest `/opt/solver/data/results/homelab_*.csv` (columns week, name, id, type, lineup, bench, captain, vicecaptain, chip, transfer_in, transfer_out) and save `/data/solver/latest.json`: status, started/finished, source, settings, a per-GW plan, the stdout tail on failure. Then delete the results CSVs.
- Page settings (`/data/web/settings.json`, form): horizon 8, secs 300, decay_base 0.9, ft_value 1.5, plan_chips on, projection_source auto. The plan section shows the settings it ran with.
- Run button: starts `python -m web.jobs solve` as a detached subprocess and redirects back. The page shows "running since …" while the lock is held.
- Deadline job: if the next deadline is within (now, now+36h] and `/data/web/state.json` has no `sent_gw` for it:
  - run a fresh solve if latest.json is older than 12 h or failed;
  - print one line: `FPL GW<n> (deadline <Fri 18:30>): <OUT x -> IN y, … | roll, <k> FTs>; captain <C> (vice <V>); chip <none|name>; source <src>; http://192.168.0.210:8092/`;
  - record sent_gw.
New service (if any): none new; `fpl` gains a web UI.
  Image homelab/fpl:0.2.0 (local build). Host 8092 → container 8080 (8092 per the note and the stage-1 comment; 8090 is Traefik's unpublished ping entrypoint).
  Volume `${APPDATA_PATH}/fpl:/data` (unchanged). Networks fpl + proxy. Env TZ, DATA_DIR, SOCCERDATA_DIR, HOME, ODDS_API_KEY, FPL_TEAM_ID, SOLVER_DIR.
  Traefik: router/service `fpl`, Host(`fpl.${DOMAIN}`), entrypoint web, server port 8080.
  Dashboard: name "FPL", group Tools, icon sportarr, audience admin, description "FPL projections, my squad and transfer plans", port 8092.
  Kuma: `kuma.fpl.http.name=fpl`, `kuma.fpl.http.url=http://${LAN_IP}:8092/healthz`. .lan host: fpl.lan
New env vars: FPL_TEAM_ID: Dan's FPL entry id for the squad and the solver (empty = squad/solve/deadline say "no FPL_TEAM_ID" and exit 0)
Checks the builder must run: scripts/dc.sh /home/dan/homelab/.worktrees/fpl-dashboard/tools/fpl config -q; scripts/dc.sh /home/dan/homelab/.worktrees/fpl-dashboard/core/uptime-kuma config -q; python3 -m py_compile on tools/fpl/web/*.py; cd tools/fpl && python3 -m unittest discover -s tests (skip modules needing duckdb/fastapi if not installed on the host, as tools/lms does); bash -n scripts/fpl-web-job.sh; scripts/install-cron.sh --check in the worktree is not needed, but grep that both new lines are present
Review focus:
- Collector tables empty or missing (fresh install) -> page renders "no data yet"; solve/deadline print "no data" and exit 0; no traceback.
- Solver fails (import error on Python 3.12, FPL API down, infeasible, timeout) -> solve exits 1 with one stderr line. latest.json keeps the previous plan, shown with its time plus the failure line. The collector cron jobs are unaffected.
- Two solves at once (button + cron) -> the second says "already running" (cron exit 0; page shows "running since").
- Deadline job across hourly/daily reruns -> at most one Discord line per GW. If the solve failed, the line says so instead of giving moves.
- Override for a player or GW outside the horizon, or a malformed CSV row -> ignored and shown greyed; it never crashes the page or the solve.
Docs:
- CLAUDE.md ports table: `| 8092 | fpl |`.
- CLAUDE.md layout `tools/` line: add "fpl = FPL collector + projections/squad/solver page, admin; see `tools/fpl/README.md`".
- CLAUDE.md scripts list: `fpl-web-job.sh <solve|deadline>` (cron: daily solver run 06:45, deadline Discord line 18:00).
- tools/fpl/README.md: drop "No web UI yet"; add sections Page, Projections contract, Minutes overrides, Solver (pinned SHA, settings, the Python 3.12 note, chip-half handling, that it doesn't see transfers already made this GW), Cron, Failures.
- docs/README.md fpl line: add "page on 8092: projections, squad, overrides, solver".

## Manual steps
- Put `FPL_TEAM_ID=<id>` in the env file.
- `scripts/deploy-idea.sh fpl-dashboard` (rebuilds and recreates `fpl`, installs the cron lines).
- `scripts/dc.sh core/uptime-kuma up -d` so AutoKuma creates `cron-fpl-solve` and `cron-fpl-deadline` (the `fpl` monitor changes from a docker check to http).
- Open http://192.168.0.210:8092/ and press "Run solver now" once. If it fails with an import/syntax error from the solver, the Python 3.12 choice needs revisiting (bump the image to python:3.14 slim).

## Review notes
1. /home/dan/homelab/.worktrees/fpl-dashboard/tools/fpl/web/data.py:17: `player_history` is deduplicated on `element, round`. In a double gameweek both matches have the same round, so one of them is dropped and the "last 5 minutes" mean is slightly off. Keying on `element, fixture` would keep both.
2. /home/dan/homelab/.worktrees/fpl-dashboard/tools/fpl/web/solve.py `running_since()`: this takes the solve lock for a moment every time the page renders and every 10 s while the deadline job waits. A cron or button solve that starts at exactly that moment exits "already running" without a word (the button still says "Solver started"). This is rare. Checking with a non-exclusive probe, or reading running.json first, would avoid it.
3. /home/dan/homelab/.worktrees/fpl-dashboard/tools/fpl/web/data.py `clean_settings`: `float("nan")` gets through the min/max clamp. Typing "nan" for decay or FT value saves NaN, and NaN then goes to the solver. A `v == v` check would stop it.
4. The solver's `calculate_fts` raises a KeyError if the public `entry/<id>/transfers/` list already holds transfers for the coming gameweek. That would make the solve fail, and the deadline line would then say "solver failed". The README covers this with "run it before making them". Check it after the first real gameweek.
5. The Dockerfile's `ADD` of the commit tarball has no `--checksum`. It is pinned to a commit SHA, so the risk is low, but a checksum would make it tamper-evident.

## Declined to judge
- No login on the page: the plan specifies an admin tile with no login, the same as tools/lms. The footer says so.
- Whether the solver runs on Python 3.12: the plan deliberately leaves this to Dan's first "Run solver now" (it's a manual step). I parsed the solver's files at the pinned SHA with the 3.12 grammar and they are fine, but I could not run them.
- Whether the solver pulling bootstrap/fixtures itself duplicates the collector's data: that is how the upstream code is designed, and the plan leaves it as it is.
