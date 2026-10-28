# Health, money and documents: self-hosted services and AI integrations for a UK personal assistant (as of Oct 2026)

Scope note: this took 15 tool calls, so a few sub-questions (Docling details, Wger/Mealie/Grocy, Open WebUI/n8n
agents, UK-specific Enable Banking coverage) have no sources and are listed under Gaps rather than stated as fact.
Several sources are third-party blogs or aggregators; they are flagged where it matters.

## Documents: Paperless-ngx plus AI add-ons, OCR, scanning, MCP

### Takeaway
The big 2026 change: Paperless-ngx 3.x (since 22 Jul 2026) has **native AI**. It suggests title, tags, correspondent
and type through Ollama, and it has a RAG chat with a vector index. paperless-ai is unmaintained, so the add-on to
consider now is **paperless-gpt**, which does LLM/vision OCR and custom fields. Several Paperless MCP servers exist,
but they are small community projects. Local vision-OCR quality on small models is uneven.

### Cited Findings
- Paperless-ngx 3.0.0 (22 Jul 2026) added native AI: suggestions for title/tags/correspondent/document type, chat
  about one document or the whole archive, a vector index, Ollama embeddings — [wz-it.com (2 Oct 2026, upd. 13 Oct)](https://wz-it.com/en/blog/paperless-ngx-ai-setup/)
- Later releases: 3.1.0 (27 Aug 2026) added the "Apply AI Suggestions" workflow action; 3.2.0 (19 Sep 2026) made
  automatic inbox suggestions switchable; 3.3.0 (6 Oct 2026) added a separate embedding API key,
  `PAPERLESS_AI_LLM_EXTRA_PARAMS`, and a choice between ML, AI or combined suggestions — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/).
  Sources disagree on the latest version (3.1.3 vs 3.2.1 vs 3.3.0); check GitHub releases — [jacar.es](https://jacar.es/en/paperless-ngx-3-local-ai-ollama/), [releasebot](https://releasebot.io/updates/paperless-ngx)
- Config: `PAPERLESS_AI_ENABLED`, `PAPERLESS_AI_LLM_BACKEND` (`ollama` or `openai-like`), `..._LLM_MODEL` (Ollama
  falls back to `llama3.1`), `..._LLM_ENDPOINT`, `..._EMBEDDING_BACKEND` (ollama/huggingface/openai-like; default
  embedding model `embeddinggemma`, 2K context; `bge-m3` suggested for mixed languages), context 8192, timeout 120 s,
  nightly index cron `10 2 * * *` — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/)
- Suggested generation models: gemma3:4b, gemma3:12b (used in the example), qwen3:8b, llama3.1:8b. No benchmarks;
  the advice is to start small and test on your own invoices, letters and bad scans — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/)
- Native AI limits (Oct 2026): chat cites at most 3 documents and retrieves 5 chunks; no conversation history; no
  custom prompts; custom fields are not part of AI suggestions; automatic suggestions add GPU load; no local LLM OCR
  (remote OCR only via Azure Document Intelligence, off by default) — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/)
- A tester reports that 3.1.3 tries to disable model reasoning, but the instruction is lost in transit, which matters
  for qwen3-style thinking models — [jacar.es](https://jacar.es/en/paperless-ngx-3-local-ai-ollama/)
- paperless-ai (clusterzx): the README says "This repo is currently not maintained". The author cites the planned
  official Paperless AI integration. Features were auto-tagging plus RAG chat with Ollama — [GitHub clusterzx/paperless-ai](https://github.com/clusterzx/paperless-ai).
  Unmaintained since about March 2026 per [jacar.es](https://jacar.es/en/paperless-ngx-3-local-ai-ollama/)
- paperless-gpt (icereed): OCR providers are LLM vision (OpenAI, Ollama, Mistral, Anthropic), Docling Server
  (self-hosted), Google Document AI, Mistral OCR and Azure. Auto/manual tag triggers, correspondent generation,
  custom-field write modes (append/update/replace), searchable PDFs with text layers; with Paperless 3.0+,
  `PDF_UPLOAD_MODE: "version"` stores the result as a new version. Example models are qwen3:8b (text) and minicpm-v
  (vision) — [GitHub icereed/paperless-gpt](https://github.com/icereed/paperless-gpt)
- Local vision-OCR quality is inconsistent. A user with minicpm-v and llama3.2-vision got "sometimes great, other
  times gibberish repeating the same paragraph" — [Level1Techs forum](https://forum.level1techs.com/t/need-help-with-ai-ocr-for-paperless-ngx/249465).
  Another found 11B vision models exhausted VRAM and timed out; a small dedicated OCR model (deepseek-ocr:3b) plus
  ocrmypdf worked better — [digitalisierung-mit-kopf forum, German](https://forum.digitalisierung-mit-kopf.de/t/ich-habe-paperless-ai-getestet/3017).
  An issue reports that even gpt-4o-mini marked legible invoices "unreadable", which the reporter blamed on image
  downscaling — [paperless-gpt #792](https://github.com/icereed/paperless-gpt/issues/792)
- Paperless-AIssist is a newer alternative with Ollama vision OCR; it recommends Nanonets-OCR-s for local OCR — [Docker Hub](https://hub.docker.com/r/nyxtronlab/paperless-aissist)
- Paperless MCP servers: nloui/paperless-mcp (npm, stdio + HTTP, the most listed, about 37 stars), freeformz/paperless-ngx-mcp
  (Go, 100+ tools), cbinckly/paperless-mcp-go (Go, Docker, stdio/HTTP), cbsmiley/paperless-ngx-mcp (TS, 50 tools),
  @baruchiro/paperless-mcp — [mcp.so](https://mcp.so/servers/paperless-mcp-nloui?tab=tools), [pkg.go.dev](https://pkg.go.dev/github.com/freeformz/paperless-ngx-mcp@v0.0.8), [glama.ai](https://glama.ai/mcp/servers/n9y6rczmxx), [Makerflix](https://github.com/Makerflix/paperless-mcp)

### Inferences
- Recommended stack for this homelab: Paperless-ngx 3.3 with native AI on the Mac mini's Ollama (gemma3:12b or
  qwen3:8b with thinking off, plus bge-m3/embeddinggemma embeddings). Keep Tesseract OCR as the baseline. Add
  paperless-gpt only for poor scans or receipts, tag-triggered (`paperless-gpt`), never on everything.
- A 16 GB M2 holds one 12B model or one vision model at a time, not both alongside an embedding run.
  Paperless's nightly index (02:10) and suggestion load must be scheduled around Hermes and other Ollama users.
  Expect model swaps and timeouts, so raise `REQUEST_TIMEOUT`.
- For Hermes, a read-only Paperless MCP server is the natural first tool: search plus get-document, with an API token
  for a Paperless user that has view-only permissions. That keeps the "read-only" stance, because the token, not the
  prompt, enforces it. Write tools (tag, upload) come later behind approval.
- Phone scanning: Paperless's consume folder or email ingestion, or a mobile app that uploads to the API. Not
  researched here (see Gaps).

### Gaps
- Docling (IBM) itself: no current sources fetched on quality or speed on CPU vs the Mac. Only confirmed as an OCR
  provider option in paperless-gpt.
- Phone scanning apps for Paperless in 2026 (e.g. Paperless Mobile, Swift Paperless, the share-sheet flow): not
  researched.
- No benchmark of Paperless's native suggestions vs paperless-gpt on 9-12B models was found.
- Which Paperless MCP server is best maintained as of Oct 2026 is not verified; only directory snippets were seen.

## Money: Actual Budget, Firefly III, UK bank sync, MCP

### Takeaway
GoCardless Bank Account Data is closed to new signups. **Enable Banking** is the replacement both Actual (experimental,
merged May 2026) and Firefly III (data importer) now support. It has a "restricted mode" for linking your own
accounts, with consent of up to about 180 days and about 4 background fetches/day. **UK bank coverage via Enable Banking
was not confirmed by any source.** Fallbacks are Lunch Flow (paid, GB-based aggregator) and CSV/OFX import.

### Cited Findings
- GoCardless Bank Account Data: Firefly docs say GoCardless is sunsetting it and registration is closed. Only existing
  accounts can follow the guide — [Firefly docs (via search)](https://docs.firefly-iii.org/how-to/data-importer/import/third-party-providers/), [Firefly GoCardless tutorial](https://docs.firefly-iii.org/tutorials/data-importer/gocardless/).
  SSD Nodes (Aug 2026) agrees it is closed to new accounts — [SSD Nodes](https://www.ssdnodes.com/learn/self-hosted-budgeting-apps).
  Beancount.io instead says new signups need a paid business account — [beancount.io (Jul 2026)](https://beancount.io/de/blog/2026/07/26/firefly-iii-vs-actual-budget-self-hosted-open-source-budgeting-guide).
  Either way, it is not free for new users. No exact closure date was found.
- Actual Budget: a native Enable Banking provider was merged 11 May 2026; it adds long-polling and PSU-header
  forwarding to get past the PSD2 limit of 4 background requests per day — [actualbudget PR #7345](https://github.com/actualbudget/actual/pull/7345).
  Docs label it "experimental", say to use nightly images and enable experimental features, need a Production app
  in Enable Banking with an https redirect `/enablebanking/auth_callback`, and say to link accounts in Enable
  Banking first — [Actual docs](https://actualbudget.org/docs/advanced/bank-sync/enable-banking).
  The Actual homepage still says "goCardless (EU/UK) and SimpleFIN (US/Canada)" (stale) — [actualbudget.org](https://actualbudget.org)
- A community bridge, enable-actual, imports Enable Banking transactions into Actual. It advises one Enable Banking
  application per bank — [GitHub 2manyvcos/enable-actual](https://github.com/2manyvcos/enable-actual)
- Firefly III data importer supports GoCardless, Enable Banking, Spectre, SimpleFIN, Lunch Flow (paid), CSV and
  CAMT.053. Firefly docs say Enable Banking has "a free restricted mode" for your own pre-authorised accounts —
  [Firefly docs (via search snippet; page returned 403)](https://docs.firefly-iii.org/how-to/data-importer/import/third-party-providers/).
  Importer v2.3.5 fixed Enable Banking bugs (a fatal error, a consent-validity 422 at DST) — [newreleases.io](https://newreleases.io/project/github/firefly-iii/data-importer/release/v2.3.5)
- Enable Banking FAQ: restricted mode means a production app accesses only accounts you link yourself; the FAQ does
  not explicitly call it free. Consent `valid_until` is capped per bank (`maximum_consent_validity`, 180 days for most),
  so you must re-authorise. Many banks allow about 4 background fetches/day; on a 429, wait 6 h —
  [Enable Banking FAQ](https://enablebanking.com/docs/faq/)
- Lunch Flow: GB-headquartered open-banking aggregator, account information only, claims about 2,400 institutions
  including UK banks (Ulster Bank, Bank of Scotland pages). Support in Actual and Firefly was "in progress" per its own
  forum — [banq.ai](https://banq.ai/lunchflow), [openbankingtracker](https://openbankingtracker.com/lunchflow/ulster-bank), [Lunch Flow feature board](https://lunchflow.featurebase.app/p/monetr)
  (aggregator/vendor sources; unverified)
- SimpleFIN is US/Canada (about $15/yr); no UK coverage — [beancount.io](https://beancount.io/de/blog/2026/07/26/firefly-iii-vs-actual-budget-self-hosted-open-source-budgeting-guide), [actualbudget.org](https://actualbudget.org)
- Starling has its own independent API outside open banking (older community thread, date unclear) — [QuickFile community](https://community.quickfile.co.uk/t/open-banking-beta-testing/25464)
- Actual MCP server: agigante80/actual-mcp-server (Docker / npx, Node 22+; stdio or HTTP on port 3600; needs the
  server URL, password and budget sync ID; can query, analyse and create transactions) — [mcpservers.org](https://mcpservers.org/de/servers/agigante80/actual-mcp-server)
  (mirror of README; repo not opened)

### Inferences
- For a UK user in Oct 2026: try Enable Banking first. Check the UK bank list in the Enable Banking control panel
  before choosing an app. Actual's integration is experimental and nightly-only; Firefly's importer is the more
  mature Enable Banking path. If the user's banks are not covered, use a scheduled CSV/OFX export import (fully local),
  or Lunch Flow (paid, third party sees the data).
- The ~180-day re-consent means a recurring "re-link your bank" reminder; a good Hermes/Discord cron task.
- The Enable Banking callback must be https, which conflicts with the homelab's HTTP-only stance. It needs a
  Tailscale cert/`tailscale serve` or similar for the callback (inference; not verified).
- Actual is envelope budgeting and simpler; Firefly is double-entry with a rules engine and a richer API. For an
  assistant, both have MCP servers (Actual confirmed; Firefly MCP not researched).
- Safe-autonomy pattern: give Hermes a read-only budget tool (balances, category spend, upcoming bills). Any
  transaction creation should be a proposal Dan approves. The Actual MCP server exposes create-transaction, so filter
  its tools (Hermes supports MCP tool filtering).

### Gaps
- **Enable Banking's UK bank coverage (Monzo, Starling, Nationwide, HSBC, Barclays, Amex UK) is not confirmed.**
  openbankingtracker returned 429 and no other source covered it. This is the key open question for the report.
- Whether Enable Banking's restricted mode is truly free with no monthly minimum (Firefly docs say free; the Enable
  Banking FAQ mentions a volume-based price with a monthly minimum and does not say free).
- TrueLayer/Yapily as DIY options for individuals: not researched; they appear to be business-focused.
- r/UKPersonalFinance sentiment on self-hosted budgeting: not found.
- Firefly III MCP servers, receipt capture (e.g. Paperless → Firefly), AI categorisation tools (e.g. Actual's
  rules vs LLM categorisers): not researched.

## Health: beyond fitness: meds, appointments, sleep/nutrition, phone health export, records

### Takeaway
There is no single mature self-hosted "health hub". The practical pieces are: Health Auto Export (iOS, paid
automation) → a small ingester (apple-health-ingester → InfluxDB, or HealthLog → TimescaleDB); Health Connect via an
Android webhook app or Open Health Sync; ntfy-based medication reminders (Pillminder). Health records (NHS letters,
results) fit naturally in Paperless with a restricted tag/permission set.

### Cited Findings
- apple-health-ingester (Go): an HTTP server that receives Health Auto Export REST pushes and writes JSON or InfluxDB
  (or VictoriaMetrics), with optional Bearer auth. Health Auto Export's Automation needs Premium or a trial —
  [GitHub irvinlim/apple-health-ingester](https://github.com/irvinlim/apple-health-ingester)
- HealthLog (Docker): ingests Health Auto Export JSON into TimescaleDB with token auth, a nightly analysis job and
  Grafana dashboards — [Docker Hub anym001/healthlog](https://hub.docker.com/r/anym001/healthlog)
- Open Health Sync: self-hosted, covers Apple Health and Health Connect plus wearables; a Go binary + Postgres with a
  REST API — [AlternativeTo](https://alternativeto.net/software/open-health-sync/about/) (directory listing; not verified at source)
- mcnaveen/health-connect-webhook: an Android app forwarding Health Connect data to custom webhooks (via search
  summary) — no direct link fetched; see [search context](https://alternativeto.net/software/open-health-sync/about/)
- apple-health-mcp exists (MCP over Apple Health exports) — [GitHub mikipalet/apple-health-mcp](https://github.com/mikipalet/apple-health-mcp)
- Medication: Pillminder sends reminders through ntfy and repeats until the dose is logged, with adherence tracking
  and multiple users — [GitHub ollien/pillminder](https://github.com/ollien/pillminder).
  MedAssist (Node + SQLite, Docker) tracks medication stock and emails reorder reminders; **no built-in auth** —
  [selfhostyourself](https://selfhostyourself.com/services/medassist).
  Ambys (diaries + medication plans) is beta/"unstable" — [GitHub stegobrg/ambys](https://github.com/stegobrg/ambys)

### Inferences
- The fitness app already has Garmin data. On Android, Health Connect → webhook → a new `/ingest` endpoint on the
  fitness app could add phone-only metrics (steps, weight from scales, nutrition apps) without a new service. On iOS,
  Health Auto Export → the same endpoint. That avoids adding InfluxDB/Grafana just for this.
- Medication/appointment reminders: the homelab already has ntfy (urgent) and Discord (non-urgent). A small reminder
  table in the fitness app, or Pillminder alone, fits. MedAssist's missing auth rules it out unless it sits behind the
  dashboard login.
- Health records: store NHS letters/results in Paperless under an owner-only permission set. Turn off native AI
  chat indexing for those documents, or accept that embeddings stay local (Ollama). A cloud OCR provider in
  paperless-gpt must never touch them.
- Safe summaries: the assistant should report trends from the user's own logged data, cite the source rows, avoid
  diagnosis or dosage advice, and route anything alarming to "talk to your GP/111". The fitness weekly summary is
  the model to copy.

### Gaps
- Wger, Mealie, Grocy (nutrition, meal planning, pantry) 2026 status and AI features: not researched.
- Sleep logging beyond Garmin: not researched.
- NHS App data export (GP records, test results) to self-hosted, e.g. FHIR or PDF export options: not researched.
- No source on established practice for LLMs summarising health data safely; the inferences above are design
  judgement.

## Privacy: local vs cloud model

### Takeaway
Every needed AI step can run locally in Oct 2026: Paperless native AI and paperless-gpt both target Ollama; Actual,
Firefly and health ingesters are local. Cloud models should get only derived, minimised text (aggregates, redacted
excerpts), never raw statements, scans or health records.

### Cited Findings
- Paperless native AI supports `ollama` and `openai-like` backends, with `PAPERLESS_AI_LLM_ALLOW_INTERNAL_ENDPOINTS`
  (default true) for a LAN Ollama. Its only remote OCR option sends files to Microsoft Azure — [wz-it.com](https://wz-it.com/en/blog/paperless-ngx-ai-setup/)
- paperless-gpt's OCR providers include cloud ones (Google Document AI, Mistral OCR, Azure, OpenAI/Anthropic vision),
  each of which would send document images off-box — [GitHub icereed/paperless-gpt](https://github.com/icereed/paperless-gpt)
- Lunch Flow/Enable Banking are third-party AIS providers that see your transactions by design — [Enable Banking FAQ](https://enablebanking.com/docs/faq/), [banq.ai](https://banq.ai/lunchflow)

### Inferences
- Tiering: (1) local only: raw documents, OCR, bank transactions, health metrics, medication; (2) OK for Claude:
  anonymised aggregates ("groceries £412 vs £380 avg"), planning or reasoning over summaries the local model made,
  code and config work; (3) never in the cloud: account numbers, NI number, full statements, NHS records, scans.
- Bank sync itself already involves a third party (Enable Banking/Lunch Flow); CSV import is the only zero-third-party
  path.
- Restic already sends `/srv/homelab` off-site to B2. Adding Paperless/Actual data means that data reaches B2 too
  (encrypted by restic). Decide whether that's acceptable or exclude like forensics.

### Gaps
- No UK-specific guidance (ICO/GDPR on personal use) was looked up; personal household use is generally out of scope
  of UK GDPR, but this was not verified here.

## Personal assistant layer: Hermes, Khoj, Open WebUI, n8n

### Takeaway
Hermes Agent already covers most of what's needed: MCP client with tool filtering, a built-in cron scheduler that
delivers to Discord, persistent memory, skills, and Discord voice channels. That makes it the right integration layer.
Add MCP servers (Paperless, Actual, fitness) rather than a second assistant. Khoj overlaps but adds little.

### Cited Findings
- Hermes Agent: connects to MCP servers and can filter which tools they expose; voice mode works in CLI, Telegram and
  Discord incl. voice channels — [Hermes docs](https://hermes-agent.nousresearch.com/docs)
- Hermes has a built-in cron scheduler that delivers results to any platform (daily reports etc.); voice memo
  transcription in the gateway — [dsebastien.net](https://dsebastien.net/hermes-agent/), [jimmysong landscape](https://landscape.jimmysong.io/projects/hermes-agent/)
- Hermes memory: persistent across sessions, FTS5 search with LLM summaries, pluggable backends (Honcho, Mem0);
  skills follow the agentskills.io standard, and the agent writes and refines its own skills — [agentic-ai readthedocs](https://agentic-ai.readthedocs.io/en/latest/AgentPlatforms/hermes-agent/), [claudemarket mem0 plugin](https://www.claudemarket.ai/skills/hermes/plugin-memory-mem0)
  (sources differ on tool count 40+/47/60+ and launch date)
- Khoj: automations run a query on a schedule and email results; self-hosters need Resend + auth for email. It works
  with Ollama — [Khoj docs](https://docs.khoj.dev/features/automations), [KDnuggets (undated)](https://www.kdnuggets.com/hosting-khoj-for-free-your-personal-autonomous-ai-app)

### Inferences
- Architecture: Hermes (Discord, voice) → MCP servers (Paperless read-only, Actual read-only, fitness API) → data
  stays local; Mac mini Ollama for routine summaries; Claude for heavy reasoning on minimised inputs. Morning briefing
  = Hermes cron combining fitness check-in, today's bills/budget, new documents needing action, and medication.
- Safe autonomy: enforce permissions at the token/tool level (read-only API users, MCP tool allow-lists), not in
  prompts. Writes become proposals: the existing `ideas/proposed/` approval pattern can be mirrored for "assistant
  actions".
- Khoj's email-only automations and separate memory would duplicate Hermes. Not worth adding.
- Voice/phone: Hermes's Discord voice channel support is the shortest route to phone voice access; no new service.

### Gaps
- Open WebUI tools/functions and n8n AI agents (2026 state): not researched.
- Hermes's own security model for MCP write tools (per-call approval?) is not verified.
- Whether a 9-12B local model reliably drives multi-tool MCP calls in Hermes: no source found.
