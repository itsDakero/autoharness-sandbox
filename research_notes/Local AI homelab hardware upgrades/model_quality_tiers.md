# Open-weight LLM quality per memory tier for agentic homelab work (as of Oct 2026)

Baseline: Dan runs Qwen3.5-9B and Gemma 4 12B on a Mac mini M2 16 GB via Ollama (own bench: 8-10/10 tool calls).
All benchmark numbers below are vendor self-reported unless stated; harnesses differ between vendors, so
cross-vendor comparisons are rough. Research done 25 Oct 2026 (17 tool calls).

## 1. Best models per tier and their scores vs the current 9-12B models

### Takeaway
The big quality jump is from 9-12B to the ~27-35B class (24-32 GB): Qwen3.8-27B (Aug 2026, dense) and
Qwen3.6-27B / 35B-A3B post SWE-bench and Terminal-Bench scores close to Claude Opus 4.5/4.6, while Qwen3.5-9B and
Gemma 4 12B are already strong on tool calling (tau2 ~69-79) but weak on coding/agentic depth. The 64 GB tier
adds surprisingly little: the 100-120B MoEs that fit (gpt-oss-120b, Qwen3.5-122B-A10B at Q3/offload, Nemotron
3.5 Super) score at or below Qwen3.8-27B.

### Cited Findings
**Baseline (current models)**
- Qwen3.5-9B: BFCL-V4 66.1, TAU2-Bench 79.1, LiveCodeBench v6 65.6, GPQA 81.7, AA-LCR (long context) 63.0,
  LongBench v2 55.2; 262K native context. For comparison on the same card: gpt-oss-20b LCB 74.6, AA-LCR 30.7;
  gpt-oss-120b LCB 82.7, AA-LCR 50.7; Qwen3.5-4B BFCL-V4 50.3, TAU2 79.9 — [Qwen3.5-9B model card](https://huggingface.co/Qwen/Qwen3.5-9B)
- Qwen3.5 small series (0.8B-9B) released 2 Mar 2026; medium (27B-122B) 24 Feb 2026 — [techie007 Qwen 3.5 guide](https://techie007.substack.com/p/qwen-35-the-complete-guide-benchmarks)
- Gemma 4 12B ("Unified", 11.95B dense, 256K ctx): MMLU-Pro 77.2, LiveCodeBench v6 72.0, GPQA 78.8, Tau2 avg 69.0,
  MRCR v2 8-needle 128K 43.4 — [Gemma 4 model card (HF)](https://huggingface.co/google/gemma-4-31B-it)
- Third-party pages gave conflicting Gemma 4 12B tau2 figures (69.0 avg vs 36.3 telecom); the official card says
  69.0 avg — [benchlm](https://benchlm.ai/md/models/gemma-4-12b.md), [Gemma 4 card](https://huggingface.co/google/gemma-4-31B-it)

**Gemma 4 family (official card; tech report dated 2 Jul 2026)**
| Model | Params | Ctx | MMLU-Pro | LCB v6 | GPQA | Tau2 avg | MRCR 128K |
|---|---|---|---|---|---|---|---|
| 31B dense | 30.7B | 256K | 85.2 | 80.0 | 84.3 | 76.9 | 66.4 |
| 26B A4B MoE | 25.2B / 3.8B act | 256K | 82.6 | 77.1 | 82.3 | 68.2 | 44.1 |
| 12B | 11.95B | 256K | 77.2 | 72.0 | 78.8 | 69.0 | 43.4 |
| E4B | 4.5B eff | 128K | 69.4 | 52.0 | 58.6 | 42.2 | 25.4 |
— [Gemma 4 model card](https://huggingface.co/google/gemma-4-31B-it). Note: the 26B MoE is no better than the 12B on
tau2 and long context; the 31B dense is the clear step up.

**Qwen 27-35B class (vendor tables)**
| Benchmark | Qwen3.6-27B | Qwen3.6-35B-A3B | Qwen3.5-27B | Gemma4-31B | Gemma4-26B-A4B | Claude 4.5 Opus |
|---|---|---|---|---|---|---|
| SWE-bench Verified | 77.2 | 73.4 | 75.0 | 52.0 | 17.4 | 80.9 |
| Terminal-Bench 2.0 | 59.3 | 51.5 | 41.6 | 42.9 | 34.2 | 59.3 |
| LiveCodeBench v6 | 83.9 | 80.4 | 80.7 | 80.0 | 77.1 | 84.8 |
| GPQA Diamond | 87.8 | 86.0 | 85.5 | 84.3 | 82.3 | 87.0 |
| TAU3-Bench | – | 67.2 | 68.4 | 67.5 | 59.0 | – |
| MCPMark | – | 37.0 | 36.3 | 18.1 | 14.2 | – |
| MCP-Atlas | – | 62.8 | 68.4 | 57.2 | 50.0 | – |
— [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B), [Qwen3.6-35B-A3B card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B)
(Qwen3.6 cited April 2026; SWE-bench uses Qwen's internal scaffold.)

- **Qwen3.8-27B** (dense VLM, Apache 2.0, released 14 Aug 2026): Terminal-Bench 2.1 73.0 (Qwen3.6-27B 63.4; Opus 4.6
  Max 78.2), SWE-bench Pro 61.7 (vs 53.5; Opus 4.6 Max 53.4), OSWorld-Verified 84.3, LiveCodeBench v6 90.3, GPQA 89.2,
  HLE 30.8 (Opus 4.6 Max 40.0). No BFCL/tau/MCP scores published. 262K native ctx; 48 of 64 layers are Gated
  DeltaNet (linear attention), so the KV cache is ~1/4 of a conventional dense 27B. heise tested it under llama.cpp:
  generated REST API compiled first time, "indistinguishable from Claude's programming skills", but overthinks simple
  problems. Thinking on by default; reasoning_effort low/medium/xhigh — [NYU Shanghai RITS](https://rits.shanghai.nyu.edu/ai/qwen3-8-27b-one-gpu/), [DataNorth](https://datanorth.ai/news/alibaba-releases-qwen3-8-27b)
- As of 15 Aug no third party had independently scored Qwen3.8-27B — [Orcarouter summary](https://www.orcarouter.ai/blog/qwen-3-8-27b-benchmarks)
- Artificial Analysis Intelligence Index v4.3.2 (fetched Oct 2026): Qwen3.8 27B (Xhigh) = 34, the only "small"
  (4-40B) entry shown; Nemotron 3.5 Super VL (120B / 12B active) = 26, the only "medium" (40-150B) entry; large
  open models: MiMo-V2.6-Pro 46, DeepSeek V4.1 Flash (552B/16B act) 45, GLM-5.3 45, GLM-5.3-Flash (320B/18B) 42.
  Page did not list gpt-oss, Qwen3.5/3.6, Gemma 4 — [Artificial Analysis open-source](https://artificialanalysis.ai/models/open-source)

**Other 24-32 GB and 64 GB+ candidates (vdf.ai shortlist, verified 6 Oct 2026, vendor numbers)**
- GLM-4.7-Flash: tau2 79.5, 18.2 GB at 4-bit, 202K ctx, MIT. Granite 4.2 30B: BFCL v4 61.39, tau3 68.05, 17.7 GB,
  128K. Granite 4.2 8B: BFCL v4 52.39, tau3 66.34, 5.4 GB. Ministral 3 14B: 8.2 GB, 256K, no scores.
  gpt-oss-20b: 12.1 GB native MXFP4, 131K ctx, no agent scores. Qwen3.5-122B-A10B: BFCL-V4 72.2, TAU2 79.5.
  gpt-oss-120b: 63.4 GB MXFP4, 131K. Mistral Small 4: 72.2 GB GGUF / 67.8 GB MLX, 256K — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- Qwen3.5-122B-A10B: SWE-bench Verified 72.0, Terminal-Bench 2 49.4 (i.e. below Qwen3.6-27B's 77.2 / 59.3) — [Qwen3.5-122B-A10B card](https://huggingface.co/Qwen/Qwen3.5-122B-A10B)
- Qwen3.5-397B-A17B flagship: BFCL-V4 ~72.9, tau2 86.7, SWE-bench Verified ~76.2-76.4 — [techie007](https://techie007.substack.com/p/qwen-35-the-complete-guide-benchmarks)
- No Qwen3.6-122B or GLM "Air" successor found; the 122B Qwen is still 3.5 (Feb 2026) — [llmreference Qwen3.6](https://www.llmreference.com/model-family/qwen3.6)
- BFCL leaderboard last updated 12 Apr 2026 and predates Qwen3.5, Gemma 4, gpt-oss in its rankings (useful only
  for patterns: e.g. multi-turn Qwen3-32B 47.87%, Gemma 3 27B 10.75%) — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- tau-bench maintainers: results before v1.0.1 (July 2026 grading update) not comparable with later — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- insiderllm (updated 16 Oct 2026) tier picks: 16 GB = Qwen3.6-35B-A3B with `--cpu-moe`, Gemma 4 26B-A4B (needs
  thinking disabled for tool calls); 24 GB = Qwen3.6-27B dense (Q4_K_M ~17 GB) top pick; 64 GB+ unified =
  Qwen3-Coder-Next; DeepSeek V4-Flash for "serious homelabs". States no public BFCL-style score exists for Qwen3.6 — [insiderllm](https://insiderllm.com/guides/function-calling-local-llms/)
- March 2026 13-model local tool-calling test: Qwen3.5-4B 97.5% pass, GLM-4.7-Flash and Nemotron Nano 4B 95% (older) — [jdhodges](https://www.jdhodges.com/blog/local-llms-on-tool-calling-2026-pt1-local-lm/)

### Inferences
- Tool-call formatting is mostly solved at 4-12B (tau2 69-80 at 4-12B; Dan's 8-10/10 matches). What scales with
  size is multi-step agentic depth: Terminal-Bench goes ~34-43 (Gemma 4 26B/31B) -> 59 (Qwen3.6-27B) -> 73
  (Qwen3.8-27B); SWE-bench Verified 52 (Gemma 31B) -> 77 (Qwen3.6-27B). No Terminal/SWE scores were found for the
  9-12B models, so the exact delta from Dan's baseline on these is unknown, but LCB (65.6 / 72.0 -> 84-90) and
  long-context retrieval (Gemma MRCR 43 -> 66 at 31B) show a large gap.
- Suggested picks per tier (inference from the above sizes):
  - 12 GB: Qwen3.5-9B at Q6/Q8 or Gemma 4 12B Q4-Q5 — same as today; no upgrade.
  - 16 GB: gpt-oss-20b (12.1 GB) or Gemma 4 26B-A4B Q4 (14.6 GB) — marginal; neither clearly beats Qwen3.5-9B on
    tool calling (Gemma 26B tau2 68.2 < Qwen3.5-9B 79.1). Not worth a purchase.
  - 24 GB: Qwen3.8-27B Q4 (17-19 GB) + 32K ctx (~2 GB KV, community estimate). Biggest jump per GB.
    Alternatives Qwen3.6-35B-A3B Q4 (20.4 GB), Gemma 4 31B Q4 (18 GB), GLM-4.7-Flash (18.2 GB).
  - 32 GB: same models at Q6 (24 GB) or Q8 (31 GB, tight) with 64K+ context. Small quality gain, mostly reliability.
  - 64 GB: gpt-oss-120b (63.4 GB, too tight for a 64 GB box with OS + KV), Qwen3.5-122B-A10B (only Q3 fits), Nemotron
    3.5 Super. Vendor/AA numbers put these at or below Qwen3.8-27B; 64 GB buys headroom (Q8 27B + long ctx + a
    second model resident) more than intelligence.

### Gaps
- No independent (non-vendor) BFCL v4 / tau3 scores for Qwen3.6/3.8 or Gemma 4; BFCL leaderboard is stale (Apr 2026).
- No Aider polyglot or LiveBench numbers found for these releases in the searches run.
- No Qwen3.8 small (9B) or MoE variant found; only the 27B and the 2.4T Max were released per the NYU source.
- Is "Gemma 4 12B" a later addition? Some third-party pages list only four Gemma 4 sizes; the HF card lists five.

## 2. Q4 vs Q6/Q8 quality cost, and KV cache for 32-64K context

### Takeaway
At 4-bit, aggregate agent scores barely move (no statistically significant tau2 change in a July 2026 study), but
4-bit amplifies existing failure modes (tool-name hallucination up to 2.5x) that a lenient error budget hides.
Small models suffer more. Practical rule: Q4_K_M+ weights for >=27B, Q6/Q8 for <=9B if it fits, and keep KV cache at
Q8 or higher. Hybrid linear-attention models (Qwen3.5/3.6/3.8) make 32-64K context cheap.

### Cited Findings
- "Flat Score, Amplified Failures" (arXiv 2607.27275, Jul 2026): two open model families (dense + MoE), tau2-bench
  telecom + retail, 16/8/4-bit, 456 episodes per cell. No score change survives multiple-comparison correction; worst
  cell bounded within +/-7.5 pts. But 4-bit raises tool-name hallucination in telecom up to 2.5x (+17.6 pts per
  task); no new failure types (rank corr >=0.94). Shrinking the error budget from 10 to 2 reveals a 17-pt gap in the
  affected cell. A targeted error-repair prompt removed the damage — [arXiv 2607.27275](https://arxiv.org/abs/2607.27275)
- Blog claim (unverified, ~5 months old): Qwen3 4B Q4_K_M lost ~6.4 pts HumanEval+ vs Q8; recommends Q8_0 for agents
  emitting strict JSON. Other guides: Q8_0 <0.5% loss vs FP16, Q4_K_M ~1-3%; one instruct model 69.41 (Q8) vs 69.15
  (Q4_K_M) — [bestllmfor](https://bestllmfor.com/guides/quantization-q4-vs-q5-vs-q8-quality/), [runlocalmodel](https://runlocalmodel.com/choosing-quantization-2026.html), [hussain-nazary](https://hussain-nazary.github.io/q4-km-vs-q8-0.html)
- Keep KV cache at Q8 or higher for tool calling; Q4 KV hurts tool-call accuracy; contexts spilling to system RAM
  lower reliability; on 24 GB with a Q4_K_M 27B, ~16-32K ctx — [insiderllm](https://insiderllm.com/guides/function-calling-local-llms/)
- Qwen3.8-27B sizes (Unsloth): 2-bit 11-13 GB, 4-bit 17-19 GB, 6-bit 24 GB, 8-bit 31 GB, BF16 56 GB; bartowski
  Q4_K_M ~17 GB. KV community estimate ~0.5 GB @ 8K, ~2 GB @ 32K (flagged "should be verified"). heise: NVFP4 used
  ~half the VRAM of Q8_0 at comparable accuracy — [NYU Shanghai RITS](https://rits.shanghai.nyu.edu/ai/qwen3-8-27b-one-gpu/)
- Qwen3.6-35B-A3B: 40 layers, only 10 full-attention (2 KV heads, head dim 256), 30 Gated DeltaNet — [Qwen3.6-35B-A3B card](https://huggingface.co/Qwen/Qwen3.6-35B-A3B);
  this lets 5 parallel 64K runs fit on 32 GB at 16-bit KV, 11 at 8-bit KV — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- Ollama recommends >=64K tokens of context for agents; Qwen advises >=128K for Qwen3.6 to preserve thinking — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)
- Static YaRN (beyond 262K) can hurt short-text performance; enable only if needed — [Qwen3.5-9B card](https://huggingface.co/Qwen/Qwen3.5-9B)

### Inferences
- For Dan's use (a background agent where a missed/hallucinated tool call matters more than an average score), the
  arXiv result argues for Q6/Q8 when memory allows, and for validating tool names in the harness (cheap fix the paper
  shows works).
- KV for 64K on Qwen3.8-27B is likely ~4 GB at 16-bit (extrapolating the 2 GB @ 32K estimate) — so 24 GB fits Q4 +
  32-64K; 32 GB fits Q6 + 64K comfortably. Gemma 4 (conventional attention) needs more KV per token; no figure found.

### Gaps
- The arXiv abstract doesn't name the models or say how sensitivity scales with size.
- No measured Q4 vs Q8 comparison on BFCL/tau for Qwen3.6/3.8 or Gemma 4 found.
- No Gemma 4 KV-cache-per-token figure found.

## 3. MoE models with expert offload to system RAM

### Takeaway
Offload works (llama.cpp `--n-cpu-moe` / `-ot ".ffn_.*_exps.=CPU"`) and speed is tolerable (~15 tok/s for
gpt-oss-120b on a 3090 + 64 GB DDR4), but for quality the current small MoEs trail their dense siblings: Qwen3.6-35B-A3B
< Qwen3.6-27B, Gemma 4 26B-A4B << Gemma 4 31B, Qwen3.5-122B-A10B < Qwen3.6-27B on SWE/Terminal-Bench. Offload is
a GPU+system-RAM trick; on a unified-memory Mac it gains nothing.

### Cited Findings
- RTX 3090 + 64 GB DDR4, gpt-oss-120b via llama-server `--n-cpu-moe 24`: ~15 tok/s generation, ~50 tok/s prompt
  processing; nearly filled both VRAM and RAM (single anecdotal forum report) — [klotz.me gpt-oss tag](https://scuttle.klotz.me/tags/gpt-oss)
- Unsloth documents `-ot ".ffn_.*_exps.=CPU"` to send expert tensors to RAM, offloading fewer as GPU memory grows — [Unsloth gpt-oss docs](https://docs.unsloth.ai/basics/gpt-oss)
- gpt-oss-120b Q4_K_M + 32K ctx est. ~67.9 GB total — [gpuprix](https://gpuprix.com/best-gpu-for-local-llm/gpt-oss-120b)
- Qwen3.5-122B-A10B Q4_K_M est. ~84 GB (calculator); Q3_K_S ~69.5 GB; one M5 Max 128 GB run peaked at 65.6 GB
  (quant unstated) — [willitrunai](https://willitrunai.com/can-run/hf-unsloth--qwen3-5-122b-a10b-gguf-on-a4000-16gb), [oMLX](https://omlx.ai/benchmarks/jbnu0lzp)
- Qwen3.6-35B-A3B can run on a 16 GB GPU with `--cpu-moe` (experts in RAM) — [insiderllm](https://insiderllm.com/guides/function-calling-local-llms/)
- Dense vs MoE same family: Qwen3.6-27B SWE-V 77.2 / TB2 59.3 vs 35B-A3B 73.4 / 51.5 — [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B);
  Gemma 4 31B vs 26B-A4B: Tau2 76.9 vs 68.2, MRCR 128K 66.4 vs 44.1 — [Gemma 4 card](https://huggingface.co/google/gemma-4-31B-it);
  Qwen3.5-122B-A10B SWE-V 72.0 / TB2 49.4 — [card](https://huggingface.co/Qwen/Qwen3.5-122B-A10B)
- AA index: Nemotron 3.5 Super (120B/12B act) 26 vs Qwen3.8 27B 34 — [Artificial Analysis](https://artificialanalysis.ai/models/open-source)
- On NVIDIA's Nemotron 3.5 Lightning card, Qwen3.6-35B-A3B BrowseComp 48.74 vs Gemma 4 26B-A4B 26.30 — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)

### Inferences
- MoE's real advantage here is speed per GB-of-bandwidth, which Dan says doesn't matter. When speed isn't critical, a
  dense 27B at Q6/Q8 beats any MoE that fits in 64 GB on the evidence found.
- Offload would matter only for a much larger MoE (DeepSeek V4.1 Flash 552B/16B, GLM-5.3-Flash 320B/18B, AA 42-45)
  on a box with 256 GB+ RAM — outside the 64 GB tier.

### Gaps
- No measured llama.cpp offload numbers for Qwen3.5-122B-A10B or Qwen3.6-35B-A3B found.
- No benchmark measuring quality at all for offloaded MoE (it should be identical to non-offloaded; only speed changes).

## 4. Where the plateau is: local vs cloud review

### Takeaway
On vendor numbers, the 27B-class (Qwen3.8-27B, 24-32 GB) reaches roughly Claude Opus 4.5/4.6 territory on agentic
coding benchmarks and is the last big step a 64 GB budget can buy; models that score meaningfully higher (AA 42-46)
are 300B-1T MoEs. Remaining gaps are hard reasoning (HLE 30.8 vs 40.0) and no independent verification, so a cloud
review of proposals still looks prudent.

### Cited Findings
- Qwen3.8-27B vs Opus 4.6 Max: Terminal-Bench 2.1 73.0 vs 78.2, GPQA 89.2 vs 91.3, HLE 30.8 vs 40.0; "hard-reasoning
  gap to frontier models is large, especially on HLE"; linear-attention retrieval deep in long context "untested",
  left to community testing — [NYU Shanghai RITS](https://rits.shanghai.nyu.edu/ai/qwen3-8-27b-one-gpu/)
- Qwen3.6-27B Terminal-Bench 2.0 59.3 = Claude 4.5 Opus 59.3; SWE-V 77.2 vs 80.9 — [Qwen3.6-27B card](https://huggingface.co/Qwen/Qwen3.6-27B)
- AA index: small tier top = 34 (Qwen3.8 27B); best open overall = 46 (MiMo-V2.6-Pro, 1T) — [Artificial Analysis](https://artificialanalysis.ai/models/open-source)
- Long-context log-style retrieval: Gemma 4 MRCR 8-needle 128K: 12B 43.4 -> 31B 66.4; Qwen3.5-9B AA-LCR 63.0 (above
  gpt-oss-120b 50.7) — [Gemma 4 card](https://huggingface.co/google/gemma-4-31B-it), [Qwen3.5-9B card](https://huggingface.co/Qwen/Qwen3.5-9B)
- Vendor scores across vendors use different harnesses and shouldn't be ranked against each other — [vdf.ai](https://vdf.ai/blog/best-local-llm-for-agents-tool-calling/)

### Inferences
- For Dan: 9-12B (today) = reliable tool calling and summarising, weak at multi-step diagnosis; 27B dense at Q6/Q8
  (32 GB) = plausibly reliable multi-step log analysis and decent proposals; 64 GB adds headroom, not a new class.
  Keeping the existing Opus reviewer in the loop (as the build pipeline already does) remains sensible.
- Hardware note: the user's memory says hardware swaps are deferred until after Christmas 2026; a 24-32 GB tier is
  where any upgrade pays off.

### Gaps
- No independent study found on local models doing multi-step log analysis or writing improvement proposals.
- No r/LocalLLaMA threads surfaced directly in searches; community sentiment is via blog aggregators only.
- Mac-specific limit not sourced: macOS caps GPU-usable unified memory below total RAM by default, so a "16 GB" Mac
  holds less than a 16 GB GPU — verify before mapping tiers to Mac configs.
