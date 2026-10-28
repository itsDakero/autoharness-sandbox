# Homelab autonomy and assistant gaps (audit of /home/dan/homelab, 2026-10-25)

Method: read CLAUDE.md, docs/README.md, docs/m1-core.md, docs/m5-pipeline.md, docs/m6-research.md,
tools/hermes/{SOUL.md,config.yaml}, tools/fitness/README.md, tools/wardrobe/README.md, scripts/install-cron.sh,
every note title/header in ideas/{done,parked,rejected,dismissed,proposed,terminal}/ and the "Also spotted" lists
of the four scout reports (ideas/proposed/_report-2026-10-{15,16,19,23}.md). Grepped the repo (excluding the env
file) for common self-hosting tools. Then 10 web lookups. Repo citations are file paths; web citations are URLs.

## What exists today (and what must not be re-proposed)

### Takeaway
The homelab is strong on media, monitoring-by-alert, backups and an LLM-driven build pipeline; it already has a
fenced, read-only Discord assistant (Hermes) and three personal-data apps (fitness, wardrobe, jelu) plus price
watches. It has no HTTPS, no password manager, no documents or money app, no metrics history, and Hermes is
text-only with no access to the personal data the homelab holds.

### Cited Findings
- Services: core = docker-socket-proxy, traefik, adguard, uptime-kuma (+AutoKuma), ntfy, dashboard, ha-backups
  (SMB for HA), omada; media = gluetun+qbittorrent, prowlarr, radarr/sonarr (+ remote 720p pair), jellyfin, seerr;
  tools = dozzle, scrutiny, hermes, fitness, changedetection, jelu, wardrobe; games = leafgreen — `CLAUDE.md`, `ls core media tools games`.
- "HTTP only for now; HTTPS comes later." — `CLAUDE.md` (Access model); cookie/`Secure` follow-ups wait for HTTPS — `docs/m1-core.md` lines ~124, ~142; Omada UI uses a self-signed cert "until HTTPS comes" — `docs/m3-omada.md`.
- Phone access today = Tailscale + ntfy iPhone app subscribed to `http://homelab:8081`; dashboard is checked at 390 px — `docs/m1-core.md` (lines ~70, ~108).
- Alert routing already split: ntfy = urgent, Discord = non-urgent (`scripts/discord.sh`) — `CLAUDE.md`.
- Cron jobs (12, all in dan's crontab): idea-actions, seerr-route (every minute), ha-backup-check, scrutiny-check, disk-space-check, arr-missing-search, storage-cleanup report, image-check, card-prices, install-cron --check, wardrobe-daily (07:00), fitness-weekly (Sun 19:00) — `scripts/install-cron.sh` lines 12-23.
- Update handling is digest-only: `image-check.py` (Monday Discord digest, ntfy on security releases, read-only) and manual `/update-stack` — `CLAUDE.md`, `ideas/done/image-freshness-digest.md`, `ideas/done/apply-pending-image-upgrades.md`.
- Auto-deploy exists for approved Risk-1 builds — `ideas/done/auto-deploy.md`, `scripts/idea-actions.py` (per CLAUDE.md). The "always-manual list (AdGuard, Omada, Tailscale, firewall, SSH, DNS, deletes, media writes)" is parked by the planner — `docs/m5-pipeline.md` line ~108.
- Self-healing today is narrow: `qbit-watchdog.sh`, a Gluetun-unhealthy alert (`ideas/done/gluetun-stuck-monitor.md`), and a nightly AutoKuma restart workaround (`docs/m1-core.md` ~48-50). Only 3 compose files define a `healthcheck` (`core/ha-backups`, `tools/dozzle`, `media/qbittorrent`); all have a restart policy. Grep finds no autoheal/watchtower/renovate.
- Hermes: `nousresearch/hermes-agent:v0.22.2`, Discord text only, model qwen3.5:9b on the Mac mini at 64K context; toolsets on = file, todo, memory, session_search, clarify; off = terminal, code_execution, browser, web, delegation, cronjob, discord_admin, tts; approvals auto-deny; no fallback provider — `docs/m6-research.md` (Stage D Built), `tools/hermes/config.yaml` (lines 16-33).
- Hermes can read only: `status.json` (services up/down + idea queues, written each minute by the dashboard), `ideas/`, `docs/`, the forensics README; it can write only `ideas/proposed/` — `tools/hermes/SOUL.md`; "You can't run commands, restart or deploy anything, browse the web or reach other machines." — `tools/hermes/SOUL.md`.
- Hermes network fence: own network, no proxy/socket-proxy; "a DOCKER-USER fence is due if a network tool is ever turned on" — `docs/m6-research.md`.
- Personal data already held (none of it visible to Hermes): Garmin sync, HRV/sleep/readiness, morning check-in, FiiT log, load/recovery/zones, Sunday LLM summary via the Mac mini, with a numbers-only whitelist to the model (`tools/fitness/README.md` ~136-139, `ideas/done/fitness-*.md`); wardrobe catalogue, outfits, gaps, wear log, `GET /api/daily.txt` (`tools/wardrobe/app/main.py` route list; `tools/wardrobe/README.md`); Jelu reading list (`ideas/done/jelu-*.md`); changedetection price/restock watches (`tools/changedetection/README.md`); card price history (`scripts/card-prices.py`); Jellyfin/Seerr activity (`docs/m2-media.md`).
- The Mac mini's Ollama is shared by Hermes (qwen3.5:9b), wardrobe tagging (default gemma4:12b-it-qat) and the fitness summary; README warns about model swaps in 16 GB — `tools/wardrobe/README.md` ~17-21; a scout saw qwen3.5:9b resident at 12.7 GB vs 8.9 GB benched — `ideas/proposed/_report-2026-10-19.md`.
- Do-not-repeat list: rejected = ntfy-auth ("ntfy only reachable via Tailscale. Revisit if exposed publicly"), discord-hermes-agent ("Too broad … each undoing a Stage D fence (web, discord_admin, paid image API) … web access later if a real need shows up"), books-deals-aggregator (split into jelu + changedetection) — `ideas/rejected/*.md`. Dismissed = obsidian-livesync-vault ("Not an Obsidian user") — `ideas/dismissed/obsidian-livesync-vault.md`. Parked = wardrobe-pinterest. Proposed/pending = os-disk-ssd-swap (Risk 4; hardware deferred to after Christmas 2026 per memory). Terminal = loop-stopfailure-alert.
- Repeated scout runners-up, never proposed as a top-3 and never dismissed: Beszel (metrics history; 10-19 and 10-23 reports), Mealie (four times, "fourth time a score-12 runner-up"), Immich (needs a B2 cost estimate), Karakeep, Homebox, Donetick, Open WebUI family chat, a `cron-run.sh` failure wrapper, Hermes container healthcheck ("the Kuma docker monitor can't see a dead Discord gateway"), Hermes idle-session reset — `ideas/proposed/_report-2026-10-{16,19,23}.md`.

### Inferences
- Beszel, Mealie, cron-failure wrapper and Hermes healthcheck are "spotted but not decided": a report writer may raise them, but should mark them as already surfaced by the scout rather than new.
- Anything that needs Tailscale config changes (e.g. `tailscale serve`) or DNS falls on the always-manual list, so it fits the "bigger changes need Dan's approval" model naturally.

### Gaps
- I did not read the dashboard code or every script; whether the dashboard compares running containers to repo compose (config drift) is unverified.

## Infrastructure gaps vs common practice

### Takeaway
The biggest single blocker is the lack of HTTPS: it gates a password manager, passkey SSO, browser microphone
access for voice, and the cookie hardening the docs already defer. After that, the gaps that fit Dan's
"safe actions run automatically" rule are cron dead-man's-switch monitoring, healthcheck-driven auto-restart,
and turning the read-only image digest into auto-proposed (Risk-1, auto-deployable) patch bumps.

### Cited Findings
1. **HTTPS (gap, prerequisite).** Repo: `CLAUDE.md` "HTTP only for now", `docs/m1-core.md` (~124, ~142), `docs/m3-omada.md` (self-signed). The dismissed Obsidian note's Risk 4 came partly from "phones need `tailscale serve` for HTTPS, which is on the always-manual list" — `ideas/dismissed/obsidian-livesync-vault.md`.
   - Common patterns: `tailscale serve` as reverse proxy with automatic HTTPS for tailnet names, or a proxy (Caddy/Traefik) using Tailscale's Let's Encrypt certs; HTTPS and MagicDNS must be enabled in the admin console — [autobrr docs](https://autobrr.com/installation/reverse-proxy/tailscale-serve), [hhf forum guide](https://forum.hhf.technology/t/tailscale-and-caddy-proxy-to-expose-docker-containers-over-tailscale-with-https-access/304). Tailscale Services (beta, Oct 2025) gives containers MagicDNS names instead of ports — [Tailscale blog](https://tailscale.com/blog/services-beta).
2. **Password manager (absent; grep finds no vaultwarden/bitwarden).** Vaultwarden appears in 2026 must-have roundups — [Pinggy best self-hosted apps 2026](https://pinggy.io/blog/best_self_hosted_apps). The web vault needs a secure context (HTTPS or localhost) because of Web Crypto; there is no setting to bypass it — [Vaultwarden wiki (Enabling HTTPS)](https://github.com/dani-garcia/bitwarden_rs/wiki/Enabling-HTTPS?ref=jussiroine.com), [evezone guide](https://evezone.evetech.co.za/build-lab/how-to-self-host-a-password-manager-at-home-without-a-subscription).
3. **SSO / passkeys (absent; dashboard has its own login, Dozzle/Traefik UI sit behind it — `ideas/done/admin-tools-login.md`).** Pocket ID is a passkey-only OIDC provider aimed at homelabs; WebAuthn needs HTTPS — [korben.info](https://korben.info/en/pocket-id-passkey-auth-homelab.html), [virtualizationhowto, Oct 2026](https://www.virtualizationhowto.com/2026/10/i-tried-pocket-id-to-simplify-home-lab-logins-heres-what-i-found/); reportedly OpenID-certified at v2.10.0 (July 2026) — [jacar.es](https://jacar.es/?p=5440) (single secondary source). Pocket ID also appears in the Pinggy 2026 list.
4. **Metrics/log history (absent).** Only live logs (Dozzle) and up/down (Kuma); no Prometheus/Grafana/Loki in the repo (a "prometheus" grep hit is only in `core/dashboard/app/main.py`). Beszel (hub+agent, server and Docker monitoring with alerts) is in the 2026 roundup — [Pinggy](https://pinggy.io/blog/best_self_hosted_apps); scout already spotted it twice (`_report-2026-10-19.md`, `_report-2026-10-23.md`).
5. **Cron dead-man's switch (gap).** 12 cron jobs (`scripts/install-cron.sh`), "no MTA, output discarded" — `_report-2026-10-23.md`. Common practice is Healthchecks: each job pings a URL; silence past a grace period alerts (ntfy and Discord supported); idles well under 300 MB — [elest.io](https://blog.elest.io/self-host-healthchecks-know-the-instant-a-cron-job-dies/), [Railway Healthchecks](https://railway.com/deploy/healthchecks-monitoring), [vormox guide](https://vormox.com/blog/how-to-install-healthchecks-in-an-lxc-container-on-proxmox-ve-cron-job-and-dead-man-s-switch-monitoring-for-beginners). Uptime Kuma (already running) has push monitors that can do the same — same elest.io source notes Kuma push monitors as the general-purpose alternative.
6. **Auto-remediation (narrow).** Only 3 healthchecks in compose files; no autoheal-style restarter; Hermes has no healthcheck (scout 10-16, 10-19). No external source fetched on autoheal specifically — see Gaps.
7. **Update automation (digest only).** `image-check.py` lists newer tags; bumps go through manual `/update-stack`. Repo already has the safe-action lane: approved Risk-1 builds auto-deploy (`ideas/done/auto-deploy.md`).
8. **Notifications routing / mobile.** Already covered (ntfy urgent + Discord feed; ntfy app over Tailscale). Not a gap; ntfy auth was rejected.

### Inferences
- A single "HTTPS over the tailnet" milestone (most likely `tailscale serve` or Traefik with a Tailscale/LE cert) unlocks Vaultwarden, Pocket ID, browser mic access for voice, and the deferred `Secure` cookie. It touches Tailscale config (always-manual) and Traefik (brief restart, no host reboot), so it respects the no-downtime-before-Christmas constraint but needs Dan's approval.
- Lowest-risk autonomy wins: (a) Kuma push monitors or Healthchecks pings for all 12 cron jobs; (b) healthchecks on the services lacking them plus a restarter limited to an allowlist; (c) image-check.py writing patch-level bump proposals with `Risk: 1` so the existing auto-deploy lane applies them, minors/majors still waiting for Dan.
- Vaultwarden data would need to go into the nightly restic pause list like the other SQLite apps (`ideas/done/backup-pause-*.md` pattern).

### Gaps
- No primary source fetched for autoheal / docker healthcheck-restart tools in 2026; recommend the report writer treat this as a pattern, not a named product.
- No authoritative r/selfhosted 2026 "must-have" thread found; the search returned secondary roundups only ([Pinggy](https://pinggy.io/blog/best_self_hosted_apps), [digitalbiztalk summaries](https://digitalbiztalk.com/article/what-s-actually-better-self-hosted-in-2026)), treat lists as indicative.
- Tailscale Services beta status in Oct 2026 not re-checked.

## Assistant / autonomy gaps (Hermes and the data it could use)

### Takeaway
Hermes is a well-fenced Q&A bot about the homelab itself; it cannot see Dan's health, wardrobe, reading or deal
data, cannot speak or listen, cannot remind or brief on a schedule, and cannot take even safe actions. Hermes
already supports local voice (faster-whisper STT, Piper TTS) on Discord and MCP servers with per-tool allowlists,
so most gaps can be closed without loosening the "no web, no shell" fence.

### Cited Findings
- Voice: Hermes gateway voice on Discord — `/voice on` replies with voice to voice messages, `/voice tts` to all; Discord voice-channel mode too. Local STT = Faster-Whisper (tiny…large-v3/turbo, no API key); local/free TTS = Piper, NeuTTS, Edge TTS (default). Needs `voice`/`messaging` extras, ffmpeg, Opus — [Hermes voice mode docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode). Repo: `tts` is in Hermes's disabled toolsets — `tools/hermes/config.yaml` line ~30.
  - Note: Edge TTS is Microsoft's online service (free, but not local); Piper is the local option. Piper was archived 6 Oct 2025 but still works; Kokoro suggested for new builds — [kunalganglani.com](https://www.kunalganglani.com/blog/local-ai-voice-assistant-whisper-piper-ollama) (single blog).
- Alternative voice path: Home Assistant has a built-in Ollama integration usable as the Assist conversation agent (Whisper + Wyoming + Piper pipeline) — [promptquorum HA Ollama](https://www.promptquorum.com/smart-home/home-assistant-ollama-integration), [kunalganglani.com](https://www.kunalganglani.com/blog/local-ai-voice-assistant-whisper-piper-ollama). Dan already runs an HA Pi (`core/ha-backups`, `scripts/ha-backup-check.sh`), on HA Core 2026.2.1, ~8 months behind — `_report-2026-10-19.md`, `_report-2026-10-23.md`.
- Tools without web/shell: Hermes reads `mcp_servers` from config.yaml; stdio or HTTP transport; per-server `tools.include` allowlist (fnmatch globs), `tools.exclude`, `enabled`, timeouts — [Hermes MCP docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp). Repo precedent: status reaches Hermes as a file because "with the minimal toolset Hermes has no tool that makes HTTP calls" — `docs/m6-research.md`.
- Data an assistant could use, already on disk: fitness (readiness, recovery, sleep debt, illness warning, weekly summary), wardrobe (`/api/daily.txt` outfit, wear log, gaps), Jelu (reading list), changedetection (deal hits), card prices, Jellyfin/Seerr requests — see first section. Fitness already enforces a numbers-only whitelist to the model — `tools/fitness/README.md` ~138.
- Scheduling: Hermes `cronjob` toolset off (`tools/hermes/config.yaml`); host-cron jobs already push single-topic posts (wardrobe 07:00, fitness Sunday 19:00) — `scripts/install-cron.sh`.
- Actions: Hermes's only write is a proposal file (`tools/hermes/SOUL.md`). The dashboard already executes allowlisted button actions from a file queue via cron (`scripts/idea-actions.py`: answer, requeue, deploy, reject) — `CLAUDE.md`.
- Documents (absent; grep finds no paperless): Paperless-ngx 3.0 (22 Jul 2026) ships native AI suggestions (title, tags, correspondent, type) with Ollama support; 3.1 adds a workflow action to auto-apply them; Paperless-AI add-on unmaintained since Mar 2026 — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/), [jacar.es](https://jacar.es/en/paperless-ngx-3-local-ai-ollama/) (CPU-only Gemma 4 E4B median 25.8 s/suggestion; reasoning models produce extra tokens or 400 errors). Version facts are from secondary blogs; not verified against the changelog.
- Money (absent; grep finds no actual/firefly service): Actual Budget is the simpler option, Firefly III heavier (app + MariaDB + cron, data importer) — [beancount.io comparison (Jul 2026)](https://beancount.io/blog/2026/07/26/firefly-iii-vs-actual-budget-self-hosted-open-source-budgeting-guide). GoCardless stopped new Bank Account Data sign-ups in July 2025, so UK bank auto-sync for a new user is not available via Actual's built-in route; SimpleFIN covers US/Canada only; fallback is OFX/QFX/CSV import — [Actual docs: GoCardless](https://actualbudget.org/docs/advanced/bank-sync/gocardless/).

### Inferences (candidate gaps, in rough priority for Dan's stated priorities)
1. **Personal-data feed for Hermes (health first).** Extend the dashboard's `agent-feed/` pattern (or a read-only HTTP MCP with an include-list) with today's fitness readiness/recovery, the weekly summary, today's outfit, current book, recent deal hits. Read-only, same fence; Risk ~1-2.
2. **Voice from the phone.** Enable Hermes Discord voice messages with local faster-whisper (on the homelab CPU, i5-9400F — small/base model; or the Mac mini) and Piper TTS; Discord's iPhone app already gives push-to-talk voice notes without HTTPS. HA Assist + Ollama is the alternative if Dan wants hands-free/Siri-style, but the HA Pi is 8 months behind and would contend for the Mac mini's 16 GB.
3. **Morning brief.** One host-cron post (07:00) merging wardrobe-daily, fitness readiness/illness warning, deals, Kuma status — the scheduler stays on the host (cronjob toolset stays off).
4. **Safe-action lane for Hermes.** Hermes writes an action request (like proposals) to a queue; an allowlisted runner (the idea-actions.py pattern) executes only Risk-1 actions (restart a named non-core container, re-run an arr search, trigger fitness sync), everything else becomes a proposal. Matches "safe actions automatic, bigger changes need approval".
5. **Documents.** Paperless-ngx 3.x with Ollama on the Mac mini for tagging; Hermes later gets read-only search of document metadata. Needs a model-contention plan for the Mac mini (three apps already share it).
6. **Money.** Actual Budget with CSV/OFX import (no UK auto-sync for new users); a monthly summary to Discord like fitness-weekly. Sensitive data → restic pause list, never sent to a cloud model.
7. **Reminders/calendar.** Neither Hermes nor any service holds a calendar, tasks or reminders (cronjob off, no CalDAV). Not researched further.

### Gaps
- Whether Hermes v0.22.x's Docker image includes the `voice` extras, ffmpeg and Opus is not verified; it may require a custom image or a newer tag (scout notes the image is already 4.55 GB).
- No reliable 2026 source on UK bank aggregators usable by self-hosters after GoCardless closed sign-ups (e.g. Enable Banking, TrueLayer, Lunch Flow); flagged, not researched.
- Faster-whisper latency on an i5-9400F (no AVX-512, GTX 970 Maxwell too old for current CUDA builds likely) not measured; GTX 970 CUDA compatibility for faster-whisper/CTranslate2 unverified.
- No source checked on calendar/tasks self-hosting (Radicale, Baïkal, Vikunja) or iPhone integration.

## What r/selfhosted / r/homelab 2025-2026 "must-have" lists include that this setup lacks

### Takeaway
Against 2026 roundups, the clear absentees are a password manager (Vaultwarden), SSO (Pocket ID), server
metrics (Beszel), document management (Paperless-ngx), photos (Immich), and file/calendar sync (Nextcloud);
media, DNS blocking, reverse proxy, uptime and dashboards are already covered.

### Cited Findings
- Pinggy's 2026 list: Nextcloud, Plex/Streamyfin, Pinchflat, Docmost, Memos, Karakeep, Beaver Habit Tracker, Dawarich (location history), Metabase, Homepage, Vaultwarden, Beszel, GoDoxy, Pocket ID — [Pinggy best self-hosted apps 2026](https://pinggy.io/blog/best_self_hosted_apps).
- Community-summary articles on r/selfhosted threads ("what's actually better self-hosted", "not worth self-hosting") exist but are secondary write-ups — [digitalbiztalk](https://digitalbiztalk.com/article/what-s-actually-better-self-hosted-in-2026), [digitalbiztalk (not worth)](https://digitalbiztalk.com/article/services-not-worth-self-hosting-in-2026-the-smart-guide); not fetched in full.
- Already present here: reverse proxy (Traefik), DNS blocking (AdGuard), uptime (Kuma), push alerts (ntfy), dashboard (own), media stack (Jellyfin + arr + Seerr), disk SMART (Scrutiny), offsite backups (restic → B2) — `CLAUDE.md`.
- Already surfaced by the scout but undecided: Immich (needs B2 cost estimate), Mealie, Karakeep, Homebox, Donetick, Beszel — `_report-2026-10-16.md`, `_report-2026-10-19.md`, `_report-2026-10-23.md`.

### Inferences
- Of the absentees, Vaultwarden, Paperless-ngx and an Actual-style budget map directly to Dan's "documents, money" priorities; Pocket ID and Vaultwarden both wait on HTTPS.
- Immich is the biggest storage/B2-cost item; the 10-16 scout already called it a milestone needing a cost estimate, and the HDD OS disk (os-disk-ssd-swap, deferred) argues against more SQLite/Postgres load before the SSD swap.

### Gaps
- Could not retrieve an actual r/selfhosted or r/homelab 2026 thread; findings rely on one roundup plus repo-internal scout reports.
