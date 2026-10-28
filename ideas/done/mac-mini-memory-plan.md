# Mac mini memory plan: measure the headroom, give each batch job a fixed slot

Value: 3   (decides what can safely be added to the Mac mini: voice, Paperless AI, more digests)
Effort: 2  (extend the existing bench + a schedule table)
Risk: 1    (read-only measurements; cron times only)
Score: 12
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #7)

## Problem
The Mac mini (M2, 16 GB) serves Hermes, wardrobe vision tagging and the fitness weekly summary. The scout saw
Hermes's model resident at about 12.7 GB. Voice (Whisper) and Paperless AI would compete for the same memory.
Nobody knows the real headroom, and batch jobs could collide with each other or with a Discord chat.

## Proposal
- Extend `scripts/model-bench.py` (or add a mode) to record: resident GB per model at the num_ctx actually
  used, macOS memory pressure and swap used (over SSH: `memory_pressure`, `sysctl vm.swapusage`) with
  (a) Hermes's model alone, (b) plus a second model, (c) plus a Whisper-sized load if one is installed.
- Write the result into `docs/mac-mini.md` as a "Memory budget" table.
- Add a "Batch slots" table to the same doc: every job that calls the Mac mini, with a fixed time that
  doesn't overlap (e.g. wardrobe tagging, fitness weekly Sun 19:00, later Paperless indexing at night).
  Move cron times in `install-cron.sh` if two overlap.
- Recommend Ollama settings (`OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_KEEP_ALIVE`) in the doc; Dan applies them on
  the Mac by hand.

## Notes
- The Mac is set up by hand (no compose); the build only changes the bench script, cron times and docs.
- Gate for `hermes-discord-voice` and any Paperless idea: they cite this table.

## Plan
Goal: Add a `--memory` mode to the Mac mini bench that measures resident memory, pressure and swap for stacked model loads; write its table, a Batch slots table and Ollama setting advice into docs/mac-mini.md.
Kind: change to scripts/model-bench.py + docs only (no cron moves: no two Mac mini jobs overlap today, see below)
Files:
- scripts/model-bench.py: add the `--memory` mode (below); the normal bench is unchanged
- docs/mac-mini.md: new `## Memory budget` section (with markers), `## Batch slots`, `## Ollama memory settings`; one line in `## Model bench` pointing to `--memory`
- CLAUDE.md: scripts list, `model-bench.py` entry gets "`--memory`: memory budget table"

model-bench.py `--memory`:
- New args: `--memory` (flag), `--base` (default `qwen3.5:9b`, Hermes's model per tools/hermes/config.yaml),
  `--second` (default `gemma4:12b-it-qat`, wardrobe's default), `--third` (no default: an Ollama model standing in
  for a Whisper-sized load; Whisper itself isn't in Ollama and isn't installed), `--ssh-host` (default `mac-mini`).
  `--ctx` (65536), `--timeout`, `--doc`, `--no-write` are reused.
- Scenarios: (a) base; (b) base + second; (c) base + second + third, only when `--third` is given, otherwise a
  row `(c) skipped: no --third given`. A model not in `/api/tags` gives a row `not pulled: ssh mac-mini ollama pull <m>`.
- Per scenario: unload everything in `/api/ps`; load each model in order with `/api/chat`, one short user
  message, `options.num_ctx=ctx`, `num_predict=1`, `keep_alive="10m"`; then read `/api/ps` and the Mac stats; then
  unload all. In `finally`, always unload everything the mode loaded.
- Mac stats via `subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=10",host,
  "memory_pressure -Q; sysctl -n kern.memorystatus_vm_pressure_level; sysctl vm.swapusage"], timeout=30)`.
  Parse with regexes: `free percentage:\s*(\d+)%` -> free %, the pressure level line (1 normal, 2 warn,
  4 critical -> those words), `used = ([\d.]+)M` -> swap GB. Put parsers in small pure functions.
- Table columns: Scenario | Models | Resident GB each (from `/api/ps` size, `name=GB` joined by `, `) | Total GB |
  GPU % (size_vram/size, lowest of them) | ctx | Evicted (requested models missing from `/api/ps`, or `none`) |
  Pressure | Free % | Swap used GB.
  Header line: `Memory run <UTC time>, Ollama <version>, num_ctx <ctx>.`
- Write between `<!-- memory-budget:start -->` / `<!-- memory-budget:end -->` in the doc, same replace logic as the
  bench table (missing markers -> message, exit 1). Bench table markers untouched.
- Commands: `--memory` with `--models` given -> argparse error. Reuse the existing unreachable check (exit 2).

Doc content (written now, Dan's run fills the table):
- Memory budget: how to run (`scripts/model-bench.py --memory http://<TS_IP>:11434 [--third <model>]`, ~3-5 min,
  needs the step-6 SSH key), the markers with a placeholder line `Not run yet.`, and a reading guide: any eviction,
  pressure warn/critical, or swap > 1 GB in a scenario = that combination doesn't fit; new Mac mini ideas
  (hermes-discord-voice, Paperless AI) cite the row they need.
- Batch slots (host clock is UTC): Hermes, on demand, qwen3.5:9b; wardrobe tagging, on upload (one worker,
  retries every 5 min when Ollama is down), gemma4:12b-it-qat; fitness weekly summary, Sun 19:00 (fitness-weekly.sh),
  qwen3.5:9b; model bench, by hand, never at Sun 18:30-19:30; reserved: nightly 01:00-05:00 for future Paperless
  indexing, no other batch job there. Note wardrobe-daily 07:00 does not call the model. Rule: a new cron job that
  calls the Mac takes a free slot from this table and adds its row.
- Ollama memory settings (Dan applies by hand in the plist, step 10, then bootout/bootstrap): recommend
  `OLLAMA_NUM_PARALLEL=1` (each slot adds a 64K context), keep `OLLAMA_KEEP_ALIVE=24h` for Hermes; and
  `OLLAMA_MAX_LOADED_MODELS=1` if row (b) shows eviction, pressure warn or swap > 1 GB (then also consider
  `WARDROBE_MODEL=qwen3.5:9b` so tagging shares Hermes's model), otherwise `2`.

New env vars: None
Checks the builder must run:
- `python3 -m py_compile scripts/model-bench.py`; `scripts/model-bench.py --help` lists the new flags
- `scripts/model-bench.py --memory --no-write http://127.0.0.1:9` -> unreachable message, exit 2
- `python3 -c` calls of the parse helpers on sample text: `System-wide memory free percentage: 42%`,
  `vm.swapusage: total = 2048.00M  used = 512.25M  free = 1535.75M  (encrypted)`, level `1`, and empty input -> `?`
- docs/mac-mini.md contains each of the four markers exactly once
- Do not run the bench against the real Mac (it loads models; Dan runs it at deploy)
Review focus:
- SSH fails (no key, Mac asleep, timeout) -> stats columns `?` plus one stderr line; Ollama rows still written, no crash, no password prompt (BatchMode)
- Ollama refuses or evicts a load (HTTP 500 "requires more system memory", or a model missing from `/api/ps`) -> recorded in Evicted/that row, run continues to the next scenario
- Run interrupted or errors mid-scenario -> `finally` unloads every model it loaded (Hermes reloads on its next message)
- Optional `--third` not given or model not pulled -> a skipped/not-pulled row, not a crash
- Existing bench table and its markers are byte-identical after a `--memory` run

Docs: docs/mac-mini.md (three new sections + one line in Model bench); CLAUDE.md scripts-list entry for model-bench.py. No port, layout or cron changes.

## Manual steps
- After deploy, run `scripts/model-bench.py --memory http://100.74.81.122:11434` (add `--third <model>`, an Ollama
  model of about 3 GB, for scenario c), then commit the updated table in docs/mac-mini.md.
- Apply the recommended Ollama settings on the Mac by hand (plist, step 10) according to row (b).

Notes for the loop:
- No `install-cron.sh` change: the only scheduled Mac mini job is fitness-weekly (Sun 19:00). Wardrobe tagging
  runs on upload and Hermes runs on demand, so neither can be given a time slot.
- The note's "12.7 GB resident" for Hermes conflicts with the bench's 8.9 GB for qwen3.5:9b at 64K. The new
  measurement settles which one is right.
- The mode reads stats over Dan's existing key-only SSH and doesn't change SSH config, so it isn't an
  always-manual item.

## Review notes
1. /home/dan/homelab/.worktrees/mac-mini-memory-plan/scripts/model-bench.py (mac_stats): when SSH fails, it prints one stderr line per scenario, so two or three lines in a run, not the single line the review focus asks for. The `?` columns and the no-crash behaviour are correct.
2. memory_scenario: the line `row["evicted"] += " (load failed: …)" if missing else ""` works only because Python reads it as `+= (... if missing else "")`. Parentheses would make that clear to the next reader. Also, if a load fails but the model still shows up in `/api/ps`, the failure is not recorded in the row (it only goes to stderr).
3. A model given without a tag (e.g. `llama3`) never matches the `/api/tags` names (`llama3:latest`), so it shows as "not pulled". The existing bench mode behaves the same way.
4. Each scenario also unloads models the mode didn't load (for example Hermes's model, which stays loaded for 24h). The plan says to do this and the doc warns that Hermes cold-loads afterwards, so this is just a reminder.

## Declined to judge
- Memory accuracy of `/api/ps` size vs the real macOS footprint: the plan picked `/api/ps` as the source, and Dan's run will show the numbers.
- No `install-cron.sh` change: the plan explains that fitness-weekly is the only scheduled Mac mini job, so there is nothing to move.
