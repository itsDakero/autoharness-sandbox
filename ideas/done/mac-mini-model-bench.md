# Benchmark candidate models on the Mac mini before picking the assistant's model

Value: 3   (settles Stage C's model with numbers, so the Stage D assistant (Hermes) gets a model that works)
Effort: 2  (one script plus a results table in the Mac mini runbook)
Risk: 1    (read/generate calls to Ollama on the Mac only; no container, no homelab state)
Score: 12
Source: scout 2026-10-15

## Problem
The scout's assistant pick for Stage D is **Hermes Agent** (NousResearch, v0.22.2 of 2026-10-15, MIT,
official image `nousresearch/hermes-agent`): Discord gateway with deny-by-default user allowlist,
per-platform toolsets, OpenAI-compatible endpoint (Ollama `/v1`), no paid fallback unless configured. But
Hermes **rejects models with under 64K context**, and its docs only call gemma4:31b (20 GB) reliable at tool
calls, which doesn't fit 16 GB. Nothing published tests a 16 GB M2 with tool calls at 64K context; the
estimates for qwen3.5:9b on 16 GB Macs disagree (25-52K "safe" context, 14-58 tok/s). By default macOS lets
the GPU use about two-thirds of 16 GB (~10.7 GB). Hermes issue #46833: it requests the model's full advertised
context and runs out of memory unless `model.context_length` is pinned. Picking blind risks Hermes refusing
the model, or the Mac swapping and falling over.

## Proposal
`scripts/model-bench.py`, run by hand from the homelab against the Mac mini's Ollama over the tailnet (URL as
an argument; Ollama has no auth and no secret is involved). For each candidate at `num_ctx` 65536:
- prefill and decode tok/s;
- how many of 10 canned tool-call prompts (homelab-shaped: "status of jellyfin", "list parked ideas") return
  valid `tool_calls` JSON;
- resident memory and CPU/GPU split from `/api/ps`.
Candidates: gemma4:12b-it-qat (7.2 GB, 256K native, tools), qwen3.5:9b q4_K_M (6.6 GB, tools),
granite4.1:8b. Mac settings under test (from the Stage C runbook): `OLLAMA_CONTEXT_LENGTH=65536`,
`OLLAMA_FLASH_ATTENTION=1`, `OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=24h`. Output: a Markdown table
written into `docs/mac-mini.md` (Stage C's runbook; create the section if the doc doesn't exist yet). It pulls
no models itself: Dan pulls them on the Mac. Writes nothing on the homelab except that doc table.
Needs Stage C done (Ollama running on the Mac); until then the script can be built and checked with `--help`
and `py_compile` only.

## Existing tools checked
- Hermes Agent (https://github.com/NousResearch/hermes-agent): v0.22.2, 2026-10-15, MIT, 254k stars, Docker Hub
  `nousresearch/hermes-agent` with version tags. Fast churn (3 releases in 2 days), ~2 GB idle RAM. Its local
  Ollama guide (https://hermes-agent.nousresearch.com/docs/guides/local-ollama-setup) sets the 64K floor.
- Ollama tags (https://ollama.com/library/gemma4/tags, https://ollama.com/library/qwen3.5/tags); Ollama
  v0.40.5-rc1 (2026-10-14). The MLX engine preview needed >32 GB (https://ollama.com/blog/mlx), so the M2 uses
  the GGUF path; LM Studio's MLX engine is the fallback runtime.
- willitrunai / llmcheck estimates: unverified and inconsistent, hence this bench.
- capitalandcompute.net "Best local models for Hermes" (2026-09-04): picks gemma4:12b-it-qat for 16 GB.

## Rough plan
1. Script: argparse (Ollama URL, models, ctx, prompts file), stdlib-only HTTP, timeouts, clear error when the Mac is down.
2. Ten canned tool-call prompts with a small tool schema; score valid `tool_calls` JSON.
3. Read `/api/ps` after each model's run for memory; unload between models (`keep_alive: 0`).
4. Write/replace a "Model bench" table in `docs/mac-mini.md`; add the doc to `docs/README.md` if new.
5. After Dan runs it: the winner goes into Stage D's Hermes config (`model.context_length: 65536`).

_Approved on the dashboard, 2026-10-15._

## Plan
Goal: Add a stdlib-only script, run by hand, that benchmarks the candidate models on the Mac mini's Ollama at 64K context (speed, memory, tool-call accuracy) and writes the results table into docs/mac-mini.md.
Kind: script (run by hand, no cron) + docs
Facts checked on 2026-10-15:
- Stage C is done. Ollama 0.40.4 answers at http://100.74.81.122:11434.
- Three models are pulled: gemma4:12b-it-qat (gguf Q4_0), granite4.1:8b (gguf Q4_K_M) and qwen3.5:9b.
- The pulled qwen3.5:9b is **safetensors on the MLX runner**, not the q4_K_M GGUF the note names. That may explain its 6 tok/s in the smoke test. The GGUF build is the tag `qwen3.5:9b-q4_K_M` (6.6 GB, ollama.com/library/qwen3.5/tags), so the bench covers both builds.
- No earlier rejection matches this idea. The only rejected note is ntfy-auth.

Files:
- scripts/model-bench.py (new, executable, `#!/usr/bin/env python3`, stdlib only: argparse, json, urllib.request, datetime, pathlib, time). Docstring gives the usage. CLI:
  - positional `url`, e.g. `http://100.74.81.122:11434`; strip any trailing `/`.
  - `--models`: comma list. Default `gemma4:12b-it-qat,qwen3.5:9b-q4_K_M,qwen3.5:9b,granite4.1:8b`.
  - `--ctx` int, default 65536. Sent as `options.num_ctx` on **every** request, so the model never reloads.
  - `--prompts FILE`: optional JSON list of `{"prompt","tool","args"}` that replaces the built-in ten.
  - `--prefill-tokens` int, default 16000: approximate size of the long prompt.
  - `--timeout` seconds per request, default 900.
  - `--doc` path, default `<repo>/docs/mac-mini.md`, where repo = `Path(__file__).resolve().parent.parent`.
  - `--no-write`: print the table only.
  - `--verbose`: print each tool prompt's result.
  Flow:
  1. GET `/api/version`. On URLError, timeout or connection refused, print `Ollama at <url> not reachable (is the Mac up? try: ssh mac-mini true)` to stderr and exit 2.
  2. GET `/api/tags` and map name to `details` (format, quantization_level, runner). A model that isn't there gets a row of `not pulled` and a stderr hint `ssh mac-mini ollama pull <m>`. Skip it.
  3. GET `/api/ps`. Unload anything loaded: POST `/api/generate {"model": m, "keep_alive": 0}`. Do this because OLLAMA_KEEP_ALIVE=24h keeps models loaded.
  4. Per model:
     a. **Decode run**: POST `/api/chat`, stream false, prompt "Write about 200 words on why a home server needs backups.", `options {num_ctx, num_predict: 256}`. Load s = `load_duration`/1e9. Decode tok/s = `eval_count`/`eval_duration`*1e9.
     b. **Prefill run**: build a deterministic filler of about prefill-tokens tokens (numbered homelab-log-style lines, about 0.75 words per token) and ask "Summarise the log above in 3 bullet points." with num_predict 128. Prefill tok/s = `prompt_eval_count`/`prompt_eval_duration`*1e9. Record `prompt_eval_count`.
     c. GET `/api/ps` and find the entry with name == m:
        - Resident GB = `size`/1e9, one decimal.
        - GPU % = `size_vram`/`size`*100.
        - ctx = `context_length`, if present.
     d. **Tool prompts**: POST `/api/chat`, stream false, num_predict 256, with a system message: "You are the homelab assistant. Answer by calling exactly one of the tools." Tools are OpenAI-style function schemas:
        - `service_status(name: string, required)`
        - `list_ideas(state: enum queued|parked|done|proposed|rejected, required)`
        - `disk_health(disk: string, optional)`
        - `backup_status()` (no parameters)
        - `propose_idea(title: string, body: string, both required)`
        The ten built-in prompts, as prompt → expected tool and args:
        - "What's the status of jellyfin?" → service_status name=jellyfin
        - "List the parked ideas." → list_ideas parked
        - "Is qbittorrent running?" → service_status qbittorrent
        - "Any problems with the disks?" → disk_health {}
        - "When did the last backup run?" → backup_status {}
        - "What's waiting in the idea queue?" → list_ideas queued
        - "Suggest an idea: a weekly report of Jellyfin's most-watched shows." → propose_idea (title and body only need to be non-empty strings)
        - "Check sonarr for me." → service_status sonarr
        - "Which ideas are done already?" → list_ideas done
        - "Is sda healthy?" → disk_health disk=sda
        Scoring:
        - **valid**: `message.tool_calls` is non-empty, and every call has `function.name` among the five tools and `function.arguments` as a dict, or a str that `json.loads` turns into a dict.
        - **right**: the first call's name == the expected tool, each expected arg matches case-insensitively after strip (for the propose_idea prompt, both are non-empty strings), and the required params are present.
        - Also record the mean wall-clock seconds per tool prompt.
     e. Unload the model (keep_alive 0). Wrap any HTTP error or timeout for that model into the row (`error: <short msg>`) and carry on with the next model.
  5. Output a Markdown table:
     - Header line: `Run <YYYY-MM-DD HH:MM> UTC, Ollama <version>, num_ctx <ctx>, prefill prompt <n> tokens.`
     - Columns: `Model | Format | Load s | Prefill tok/s | Decode tok/s | Resident GB | GPU % | ctx | Valid tool calls | Right tool+args | s/tool call`.
     - Format = `<format> <quantization_level or runner>`, e.g. `gguf Q4_0`, `safetensors mlx`.
     - Valid and right are shown as `n/10`.
     Always print it to stdout. Unless `--no-write`, replace the text between `<!-- model-bench:start -->` and `<!-- model-bench:end -->` in the doc. If the markers are missing, print the table, say so on stderr and exit 1. The script writes nothing else.
  The script sends no `think` field and does no pulls, deletes or other model management beyond keep_alive unloads.
- docs/mac-mini.md: add `## Model bench` before `## Maintenance` (wording below). The step 11 pull list adds `ollama pull qwen3.5:9b-q4_K_M` with a note: plain `qwen3.5:9b` is the MLX build.
  The section says:
  - Hermes needs at least 64K context, and macOS gives the GPU about 2/3 of the 16 GB.
  - Run from the homelab: `scripts/model-bench.py http://<TS_IP>:11434`. It takes roughly 10-20 min. Add `--no-write` to print only.
  - It unloads models between runs, so the Mac has no model loaded afterwards until the next request.
  - What the columns mean. Resident GB near 11.8 GiB, or GPU % under 100, means it won't hold up under Hermes.
  - Commit the updated table after a run.
  - Then the markers with the placeholder line `Not run yet.` between them.
- docs/m6-research.md line 120: change "`mac-mini-model-bench` (Proposed) does the real comparison" to "`scripts/model-bench.py` (results in `docs/mac-mini.md`) does the real comparison". Line 163: change "Still proposed: `mac-mini-model-bench` … It needs Stage C first." to say it is built and waits on Dan's run. Note the MLX vs GGUF qwen finding in one line under Stage C.
- docs/README.md: change the mac-mini.md row's Covers to end "…, checks, model bench".
- CLAUDE.md: in the scripts list, after `kuma-status.py,`, add `model-bench.py` (by hand: Ollama model bench on the Mac mini, table into `docs/mac-mini.md`).
New service: none.
New env vars: None.
Checks the builder must run (in the worktree):
- `python3 -m py_compile scripts/model-bench.py`
- `python3 scripts/model-bench.py --help`
- `python3 scripts/model-bench.py http://127.0.0.1:9 --no-write; echo $?` must print the not-reachable message and 2.
- `grep -c 'model-bench:' docs/mac-mini.md` must print 2.
- `test -x scripts/model-bench.py`
Do NOT run the bench against the Mac (100.74.81.122). It loads models for 10-20 min and rewrites the doc; Dan runs it.
Docs: CLAUDE.md scripts list (one entry); docs/mac-mini.md (new Model bench section + step 11 pull line); docs/m6-research.md lines 120 and 163; docs/README.md mac-mini row. No port table change.

## Manual steps
1. On the Mac: `ssh mac-mini ollama pull qwen3.5:9b-q4_K_M`. That's the GGUF build the scout meant; the qwen3.5:9b you have is the MLX/safetensors one. 6.6 GB more disk.
2. Run `scripts/model-bench.py http://100.74.81.122:11434` from the homelab, then commit the updated table in docs/mac-mini.md.
3. Pick the winner for Stage D's Hermes config (`model.context_length: 65536`). The loaded models unload afterwards, so the first request after the bench takes a cold load.
