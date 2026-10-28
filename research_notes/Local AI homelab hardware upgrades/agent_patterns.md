# Always-on local-LLM agents that watch a homelab: patterns and compute needs (as of Oct 2026)

Scope note: about 15 web lookups, plus read-only measurements on this homelab (2026-10-25). Most
public material is blogs, small GitHub repos and vendor docs. I found no controlled study of a
"homelab AIOps agent", and no r/selfhosted or r/homelab threads came up in search results. Anecdotes
are marked as such.

## 1. Existing projects and patterns (2025-2026): what works in practice?

### Takeaway
What people actually run is a scheduled pipeline, not a free-roaming agent: collect logs, filter
out noise with plain code, have a 7-14B local model summarise or classify, then send a digest or
alert (ntfy/Discord). Agent-style tool use (MCP, n8n tools) works for small, well-named tool sets.
It gets less reliable as tools multiply or look alike.

### Cited Findings
- **Homelab *arr log monitor (Apr 2026, dev.to):** a cron job every 30 min. Docker logs go to a
  Python script, then local Ollama (Qwen2.5 7B on CPU, or 14B on an 8 GB GPU), then ntfy.
  Substring filters drop known noise ("ffprobe", "429", "invalid torrent"…) and remove 60-70% of
  log volume on a normal day. INFO goes into a 09:00 daily digest; WARNING/CRITICAL are pushed at
  once with a per-container cooldown. LLM calls take 2-4 s on "a modest GPU". There is no formal
  evaluation, and false positives are not discussed. The author claims CPU-only needs 16 GB RAM or
  more. — [dev.to/pdegidio](https://dev.to/pdegidio/i-built-an-ai-log-monitor-for-my-homelab-local-llm-reads-my-arr-logs-so-i-dont-have-to-503n)
- **loki-log-summary sidecar (2026, 11 commits, 0 stars):**
  - Reads Loki `query_range`, groups lines into quiet-period windows and writes summaries back
    to Loki as `job="log_summary"`, with a separate scheduled "fleet report" worker.
  - The default model is `qwen2.5:7b`. The local profile is sized for a 4k context; the hosted
    profiles allow e.g. 200 lines, 30k chars and 512 output tokens.
  - It switches providers by profile (Ollama, OpenAI-compatible, OpenRouter, Anthropic).
  - Redaction is done in code, not by asking the model ("a miss is silent"). Identifiers become
    stable pseudonyms so correlation survives.
  — [GitHub jdbway/loki-log-summary](https://github.com/jdbway/loki-log-summary)
- **Natural-language-to-LogQL agent** (LangChain plus Ollama llama3.2) — [ravpho/langchain-log-tool](https://github.com/ravpho/langchain-log-tool)
- **Security-focused log analyser:** LogSentinelAI declares a Pydantic schema to get structured
  output, and supports Ollama and vLLM — [call518/LogSentinelAI](https://github.com/call518/LogSentinelAI)
- **CLI tools:** LogLlama and llm-log-analyzer pipe journalctl or files into Ollama — [RysLabProjects/logllama](https://github.com/RysLabProjects/logllama), [stratosphereips/llm-log-analyzer](https://github.com/stratosphereips/llm-log-analyzer)
- **Tutorial pattern:** a periodic Loki pull, then local-model classification, then a
  Discord/Slack/Telegram alert, with an 8-9B model on 8 GB. It warns that Ollama installs default
  to a small context window even when the model supports more. — [virtua.cloud](https://www.virtua.cloud/learn/en/tutorials/ai-log-analysis-ollama-vps), [selfvps.net](https://selfvps.net/en/post/ai-vps-log-analysis-llm/)
- **"Homelab AI stack 2026" survey-style post (Mar 2026):**
  - What people keep: Ollama, Open WebUI, n8n (which replaced Flowise and custom scripts),
    LiteLLM as a single endpoint, and Loki+Grafana / Netdata / Uptime Kuma for monitoring.
  - The LLM part of monitoring is just one n8n flow ("server logs → Ollama anomaly check →
    alert"), next to RSS/email digests.
  - Hardware tiers given: 16 GB → 14B, 24 GB → 32B (an M4 Mac mini at 10-15 tok/s), 32 GB+ → 70B.
  - Its performance claims are unsourced. — [dev.to/signal-weekly](https://dev.to/signal-weekly/the-homelab-ai-stack-in-2026-what-self-hosters-are-actually-running-2d58)
- **XDA (Aug 5 2026), "local LLM controls my homelab":**
  - Setup: Qwen 3.5 4B on an 8 GB laptop with Ollama and Open WebUI, Home Assistant's built-in
    MCP server, and n8n workflows as tools (list unhealthy containers, read logs, restart
    *approved* services, NAS space, backup status).
  - What worked: routine checks and multi-step chains (check, then read logs, then restart, then
    re-check).
  - What failed: tool selection errors, mainly when workflows had similar names. The author
    advises a small tool set with clear descriptions. There is no fallback when the model
    misreads a request.
  — [XDA](https://www.xda-developers.com/gave-local-llm-control-homelab-nothing-touched-cloud/)
- **Grafana's official MCP server** queries metrics and logs (Prometheus, Loki datasources),
  dashboards, alerting and incidents. It is self-hostable, authenticates with a service-account
  token, needs Grafana ≥9, and you choose which tools to enable. The docs page does not describe a
  read-only flag, and I did not verify one. — [Grafana docs v13.1](https://grafana.com/docs/grafana/v13.1/developer-resources/mcp/)
- **Community MCP servers:** an "LGTM MCP" server gives read-only access to Loki, Prometheus and
  Tempo by plain URL (e.g. `localhost:3100`, `:9090`); observability-mcp has separate Loki and
  PromQL packages. I did not check their maintenance status. — [glama LGTM MCP](https://glama.ai/mcp/servers/bsdvpn46u2), [lobehub pokgak/lgtm-mcp](https://lobehub.com/ko/mcp/pokgak-lgtm-mcp)
- **Home Assistant local LLM experience:**
  - Qwen3 8B is the most often recommended model; one claim is "94% intent accuracy", from an
    unverified commercial blog.
  - Guides advise against think-mode/reasoning models for tool calls, which they say invent
    calls and add latency.
  - Exposing fewer entities helps: 30 entities take about 1,300 tokens.
  - qwen3.5:9b is selectable in HA's Ollama integration as of June 2026.
  — [bestllmfor.com](https://bestllmfor.com/guides/best-local-llm-smart-home-privacy/), [botmonster](https://botmonster.com/smart-home/build-private-local-ai-voice-assistant-2026/), [acon96/home-llm](https://github.com/acon96/home-llm)
- **Concurrency:** Ollama serves one request per model at a time by default and queues the rest,
  which matters if many containers are scanned at once. — (search summary of the [compacthost guide](https://compacthost.com/tutorials/running-local-llms-with-ollama-in-docker-containers/); not verified in full)
- **This homelab's own bench** (Mac mini M2 16 GB, Ollama 0.40.4, 64K ctx, 23K-token prompt,
  2026-10-15):

  | Model | Prefill | Decode | Resident | Right tool+args |
  |---|---|---|---|---|
  | gemma4:12b-it-qat | 83 tok/s | 11.2 tok/s | 7.6 GB | 9/10 |
  | qwen3.5:9b-q4_K_M | 148 tok/s | 16.3 tok/s | 6.9 GB | 8/10 |
  | qwen3.5:9b MLX | 112 tok/s | 18.5 tok/s | 8.9 GB | 10/10 |

  macOS gives the GPU about 2/3 of the 16 GB. — local file `/home/dan/homelab/docs/mac-mini.md`

### Inferences
- The pattern that holds up in practice is "deterministic collector + noise filter + LLM summary
  → human". The filter and the aggregation do most of the work; the model mostly turns
  pre-reduced text into readable prose and a ranked list.
- Tool-calling agents work in homelabs at 4-12B for narrow, well-named tools. "Suggest
  improvements based on usage" is an open-ended reasoning task, not a tool-routing task, and
  that is where small models are weakest. Larger models, or a frontier model for the final step,
  help most there.
- Dan's setup already has the right ingredients: Hermes reads the status file, the scout writes
  `ideas/proposed/`, and the Claude build loop builds approved ideas. A "usage watcher" fits as
  a nightly batch producer of structured usage facts that feeds the scout, not as a new agent
  with its own tools.

### Gaps
- I found no measured precision or false-positive rates for any homelab LLM log monitor; every
  report is an anecdote.
- I found no Reddit threads with first-hand experience via search.
- I did not verify whether the Grafana MCP server has a read-only mode, nor the maintenance status
  of the community MCP servers.

## 2. Batch vs continuous; token volumes of a nightly digest

### Takeaway
Batch wins. Every working example runs on cron (every 30 min to daily) or windows logs before
calling the model. Measured on this homelab, a day of logs is about 10 MB (about 2.5M tokens raw).
After masking numbers and hashes it collapses to about 1,100 unique line templates (about 67K
tokens), and to about 73 unique warning/error templates (about 4.5K tokens). That fits one
nightly prompt for a 9-14B model with 64K context. At the bench's prefill speed it takes about
1-8 minutes on the Mac mini, so speed is irrelevant and a slower, larger model is affordable.

### Cited Findings
- The *arr monitor runs every 30 min; only WARNING/CRITICAL are realtime, everything else goes
  into a daily digest. — [dev.to/pdegidio](https://dev.to/pdegidio/i-built-an-ai-log-monitor-for-my-homelab-local-llm-reads-my-arr-logs-so-i-dont-have-to-503n)
- loki-log-summary analyses every 10 s, but only on windows bounded by line, char and token
  limits; its fleet report is a separate scheduled job. — [jdbway/loki-log-summary](https://github.com/jdbway/loki-log-summary)
- n8n flows in the 2026 stack post are scheduled digests (e.g. a 7 am RSS digest; logs → anomaly
  check). — [dev.to/signal-weekly](https://dev.to/signal-weekly/the-homelab-ai-stack-in-2026-what-self-hosters-are-actually-running-2d58)
- **Local measurement** (`docker logs --since 24h`, byte and line counts only, 2026-10-25):
  - Total across 26 containers: 10.2 MB, 58,342 lines.
  - docker-socket-proxy (HAProxy access log): 7.5 MB, 42,854 lines (73%), which collapses to 34
    unique templates.
  - Next largest: omada 726 KB, scrutiny 622 KB, changedetection 528 KB, ntfy 406 KB, seerr
    160 KB. Several services log nothing.
  - Excluding the proxy, masking digits and hex gives 1,094 unique templates (270 KB, about 67K
    tokens at about 4 chars/token).
  - Lines matching warn/error/fail/exception: 73 unique templates (18 KB, about 4.5K tokens).
- **Mac mini prefill:** 83-148 tok/s at 64K context, so a 67K-token prompt takes about 8-13
  minutes of prefill and a 5-20K-token prompt takes 1-4 minutes. Decode runs at 11-18 tok/s, so a
  1-2K-token digest takes about 1-3 minutes. — local file `/home/dan/homelab/docs/mac-mini.md` (bench); the arithmetic is mine.

### Inferences
- "Always-on" should mean always *collecting* (cheap, on the server) and *periodically reasoning*
  (nightly or weekly on the Mac mini). Realtime alerting already belongs to Uptime Kuma, ntfy,
  Scrutiny and the disk checks.
- Usage patterns ("which services are used, by whom, when") come from aggregates, not raw lines:
  - Traefik access-log counts per router and hour;
  - Jellyfin playback history;
  - Seerr requests, arr queue and grab counts;
  - dashboard tile clicks.

  These reduce to a few KB per day. Even a week of aggregates is far below 64K tokens. This
  suggests a weekly "usage digest" fed into the scout is the natural cadence.
- Since speed isn't the constraint, the hardware question becomes "how big a model fits in memory
  with a 32-64K context". That is a memory-capacity question (16 GB → about 9-14B; 24-32 GB →
  about 27-32B; 64 GB+ → 70B-class or MoE), not a throughput one.

### Gaps
- No public source gives token counts for a typical homelab nightly digest. The numbers above are
  this homelab's own single-day measurement, and log volume varies (e.g. during heavy downloads).
- Traefik access logs are not enabled in this sample (traefik logged 16 lines), so request-pattern
  volume is unmeasured.

## 3. Data-collection prerequisites and their resource costs on a 16 GB server

### Takeaway
The light option is Beszel (about 10-80 MB) for host and container metrics plus the existing
Dozzle, Scrutiny and Uptime Kuma, with logs pulled straight from Docker. A full
Prometheus + Grafana (+ cAdvisor, node_exporter) stack is estimated at 400-750 MB, and Loki adds
roughly 0.1-1.5 GB depending on volume and queries. Netdata uses 150-500 MB. All of these fit on
the 16 GB server (about 9.4 GB available on 2026-10-25), but Loki's query spikes are the main
risk.

### Cited Findings
- **Beszel:** agent about 10 MB, hub about 30 MB (one estimate); agent 10-20 MB, 10-node hub
  50-80 MB (another). Netdata 150-300 MB or 200-500 MB, with 1-s resolution and 2,000+ metrics.
  Grafana+Prometheus with node_exporter and cAdvisor about 400-750 MB. — [selfhosting.sh Grafana vs Beszel](https://selfhosting.sh/compare/grafana-vs-beszel/), [selfhosting.sh Beszel vs Netdata](https://selfhosting.sh/compare/beszel-vs-netdata/), [instapods](https://instapods.com/apps/beszel/vs/netdata/)
- **Jun 2026 comparison (estimates, no method given):** Prometheus 200-400 MB (depends on
  cardinality), Grafana 100-200 MB, node_exporter 10-30 MB, cAdvisor 50-100 MB, total 400-700 MB.
  It recommends Beszel for under about 20 nodes, and Prometheus+Grafana when you need PromQL or
  multi-service correlation. — [ricardogil.com](https://ricardogil.com/blog/beszel-vs-grafana-prometheus-proxmox-2026)
- One source claims 2-4 GB minimum for Prometheus+Grafana, which looks high next to the others. — [aicoolies](https://aicoolies.com/comparisons/grafana-vs-beszel)
- **Loki monolithic, anecdotes:**
  - A small setup used 50-100 MB, with a rise while buffering. — [Grafana community / GitHub issue 6501](https://github-redirect.dependabot.com/grafana/loki/issues/6501)
  - A Helm monolithic setup climbed to about 1.5 GB, and a `| json | line_format` query spiked
    it to 4 GB+. — [Grafana community](https://community.grafana.com/t/loki-monolithic-memory-consumption/112032)
  - An outlier hit 35 GB RSS with long retention and heavy search on unstructured logs. — [Grafana community](https://community.grafana.com/t/loki-right-choice-for-unstructured-data-using-a-lot-of-memory/46324)
  - All of these are forum anecdotes, and the threads are 2021-2024 (older material).
- **This server:** 15 GiB total, 6.2 GiB used, 9.4 GiB available, 6 cores (`free -h` and `nproc`,
  2026-10-25).

### Inferences
- For an LLM digest, Loki is optional: the measured volume (10 MB a day) is small enough that a
  nightly script reading `docker logs --since 24h` (through the socket proxy) plus Traefik access
  logs is enough. Loki/Grafana pays off only if Dan also wants interactive dashboards or the
  Grafana MCP route.
- Prometheus is worth it mainly for usage *trends* (requests per router, CPU and RAM per
  container over weeks). Traefik exposes Prometheus metrics natively, and cAdvisor gives
  per-container data. Beszel covers host and container resources at a fraction of the cost but
  has no per-route request data.
- None of the collectors push the server toward a RAM upgrade on their own. Running the *LLM* on
  the server would: the GTX 970 has 4 GB of VRAM, and 9 GB of free system RAM is tight for a
  14B model on CPU.

### Gaps
- I found no authoritative (Grafana-published) homelab sizing for single-binary Loki or for Alloy.
- The Beszel, Netdata and Prometheus figures are mostly estimates from comparison sites, some of
  them commercial.

## 4. Hybrid patterns: local triage plus cloud/frontier final review — evidence on quality

### Takeaway
The research literature supports cascades and routing: a cheap model handles most of the work and
the costly model is used selectively. Whether that pays off depends on a good quality or deferral
signal. Log-specific work reports that small models over-flag anomalies. I found no
homelab-specific evaluation. The practical hybrid is: local model compresses and drafts, and the
frontier model (here Claude in the build loop or scout) does the final judgement on a small,
redacted, structured input.

### Cited Findings
- **Semantic-agreement cascades (CMU, 2025):** they match or beat the large-model quality at about
  40% of the cost, with up to 60% lower latency, across 500M-70B models. — [arXiv 2509.21837](https://arxiv.org/html/2509.21837v3)
- **Decision-theoretic cascade analysis (ICML 2026):** a lightweight pre-generation router beat
  the best cascade policy on 4 of 5 datasets, because the cheap model's generation cost limits
  cascades. — [ICML 2026](https://icml.cc/virtual/2026/75267), [emergentmind 2605.06350](https://www.emergentmind.com/papers/2605.06350)
- Unified routing and cascading names quality estimators as the critical factor. — [ICML 2025](https://icml.cc/virtual/2025/poster/46183)
- **Survey:** quality estimation decides whether to accept the small model's output or escalate,
  which cuts large-model calls while keeping quality. — [arXiv 2603.04445](https://arxiv.org/pdf/2603.04445)
- **Logs specifically:**
  - CLSLog (FSE 2025) uses a small model for routine logs and an LLM for evolving or novel logs. — [FSE 2025](https://conf.researchr.org/details/fse-2025/fse-2025-ideas-visions-and-reflections/34/CLSLog-Collaborating-Large-and-Small-Models-for-Log-based-Anomaly-Detection)
  - LoRA-tuned tiny LLMs reach about 98% accuracy on Thunderbird. — [arXiv 2507.11071](https://papers.cool/arxiv/2507.11071)
  - An April 2026 benchmark compares LLM and traditional detectors on LogHub data. — [arXiv 2604.12218](https://arxiv.org/pdf/2604.12218)
- **Unverified:** a search summary said arXiv 2512.11997 (Dec 2025) found that smaller models flag
  almost every event as anomalous, while larger ones are more precise but still produce false
  positives. The abstract page I fetched does not state this. — [arXiv 2512.11997](https://arxiv.org/abs/2512.11997)
- loki-log-summary already does a practical hybrid: local Ollama for the per-window summaries,
  and a `claude` profile by default for the scheduled fleet report, with redaction in code before
  anything leaves. — [jdbway/loki-log-summary](https://github.com/jdbway/loki-log-summary)
- The 2026 stack post puts LiteLLM in front of local and cloud models to switch per task. — [dev.to/signal-weekly](https://dev.to/signal-weekly/the-homelab-ai-stack-in-2026-what-self-hosters-are-actually-running-2d58)

### Inferences
- For Dan, the "deferral signal" can be structural rather than learned:
  1. the local model produces structured findings (JSON: service, evidence counts,
     suggestion);
  2. only those findings, a few KB, reach Claude in the weekly scout, which judges them and
     writes proposals;
  3. Dan approves.

  This matches the research advice (expensive model on a small, filtered input) and keeps raw
  logs local.
- If the frontier model does the final judgement, the local model's job is extraction and
  summarisation, where 9-14B models are adequate. A bigger local model mainly helps if Dan wants
  the *proposals themselves* written locally without cloud review.

### Gaps
- I found no study comparing local-only and local-plus-frontier quality for ops or log
  *improvement suggestions*; the evidence is from QA/MMLU-style benchmarks and log anomaly
  classification.

## 5. Safety: keeping the agent read-only, with proposals reviewed by a human

### Takeaway
Consensus practice: give the model only narrow, read-only tools, enforce permissions outside the
model (proxy, policy, human approval), treat logs and tool output as untrusted text, and redact
in code. Read-only access limits the damage from prompt injection but does not prevent it.

### Cited Findings
- Red Hat (MCP security):
  - assume text from external sources contains hidden instructions;
  - treat tool output that fetches external data as possibly malicious;
  - prefer read-only query tools and keep destructive actions out of fully automated reach;
  - beware tool poisoning;
  - use MCP elicitation, where the host requires user approval before sensitive tools run.
  — [Red Hat blog](https://www.redhat.com/en/blog/mcp-security-logging-and-runtime-security-measures)
- Policy belongs at the gateway; model text cannot grant privileges (vendor marketing). — [Gravitee](https://gravitee.io/corpus/gen-1230/tisamenus-summaleonilae/secure-prompt-injection-mitigation-for-ai-agents-and-mcp-toolchains.html)
- XDA homelab:
  - the model only calls author-defined tools, each n8n workflow does one task, and only
    *approved* services can be restarted;
  - Home Assistant exposes chosen entities, with control optionally off (read-only);
  - no outbound network or cloud fallback.
  — [XDA](https://www.xda-developers.com/gave-local-llm-control-homelab-nothing-touched-cloud/)
- loki-log-summary: redaction in code (secrets dropped, identifiers pseudonymised), on by default;
  disabling it is "not recommended for a hosted provider". — [jdbway/loki-log-summary](https://github.com/jdbway/loki-log-summary)
- LGTM MCP is read-only by design; for Grafana's official MCP you select which tools to enable. — [glama](https://glama.ai/mcp/servers/bsdvpn46u2), [Grafana docs](https://grafana.com/docs/grafana/v13.1/developer-resources/mcp/)

### Inferences
- Dan's existing design already matches best practice:
  - Docker access only through the read-only socket proxy;
  - Hermes is read-only and writes only `ideas/proposed/`;
  - the guard hook blocks env dumps;
  - human approval comes before anything is queued or deployed.

  A usage watcher should keep to that: a collector script (no LLM) writes aggregates, the LLM
  sees only those, its output goes only to `ideas/proposed/` or Discord, and it has no tools that
  act.
- Log lines are attacker-influenced. For example, Traefik logs user-agents and paths, and arr
  logs contain release names from indexers. So the model must not hold tools that act on
  instructions it reads. Proposals should be reviewed as untrusted suggestions, as the
  Proposed-tab flow already does.

### Gaps
- I found no log- or telemetry-specific prompt-injection incidents or guidance dated 2026.
