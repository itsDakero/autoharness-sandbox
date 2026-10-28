# Docs index

Read this first, then only the doc you need. One line per doc; add a line when you add a doc.

| Doc | Covers |
|---|---|
| `CLAUDE.md` (repo root) | Rules, layout, ports, labels, the Claude Code kit. Always loaded. |
| `docs/m1-core.md` | Core services: Traefik, AdGuard, Kuma, ntfy, Dozzle, the dashboard (widgets, admin login), phone alerts |
| `docs/m2-media.md` | Media stack: GPU, Gluetun + qBittorrent, arr apps and the remote 720p pair, Jellyfin, Seerr |
| `docs/m3-omada.md` | Omada controller: host networking, UFW ports, the restore, auto-backup, upgrades |
| `docs/m4-backups.md` | restic backups (local + B2), Home Assistant backups over SMB, Scrutiny disk health |
| `docs/m5-pipeline.md` | Idea pipeline: dashboard idea box, Discord feed, the background build loop and deploys |
| `docs/m6-research.md` | M6 plan: scout agent + scoring/Proposed tab, Mac mini model server, assistant agent (Hermes), pre-planner researcher |
| `docs/mac-mini.md` | Mac mini model server (M6 stage C): headless setup, Tailscale, Ollama as a launchd agent, checks, model bench |
| `docs/restore.md` | Restoring a file, an app, or the whole server from backups |
| `forensics/README.md` | Forensic parsers: layout, Python setup, where test data lives (never in git) |
| `tools/fitness/README.md` | Fitness app (Garmin sync, check-in, FiiT log, plan engine (goal, block, today's session)): first run, MFA, re-login, bumping the library, schema |
| `tools/fpl/README.md` | FPL model: data collector (jobs, data layout, tables, DuckDB queries, Odds API key) and the page on 8092: projections, squad, overrides, solver, team goals model, player points model; failure behaviour |
| `tools/changedetection/README.md` | changedetection.io: price/restock watches, first-start password, Apprise URLs, urgent-to-ntfy convention |
| `tools/books/README.md` | Books reading tracker: first run, Goodreads CSV import, covers, removing Jelu |
| `tools/wardrobe/README.md` | Wardrobe catalogue (photo upload, Mac mini vision tagging, wishlist from pin links, outfits, gap analysis): first run, data, failures |
| `tools/lms/README.md` | Last Man Standing picker (Odds API odds, safest pick per round, used teams, Discord nudges): first run, rules as built, credits, failures |
| `docs/fitness-analysis-prompt.md` | Fitness phase 2 idea note: the analysis top apps do (load, recovery bands, zones, predictions, illness warning); `docs/fitness-analysis/` = the 5 queueable notes, one at a time |
| `games/leafgreen/CLAUDE.md` | LeafGreen Field Notes web app: build, files, game logic |
| `docs/ops-actions.md` | Ops actions runner: auto-restart of unhealthy non-core containers, caps, breaker, PAUSE file, action tiers |
| `docs/town-mockup.html` | Homelab Town mockup (sample data): the look the live /town page (docs/m1-core.md) is built from |
