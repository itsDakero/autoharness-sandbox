# Non-GPU local-LLM capacity for ~£500 (UK, Oct 2026): Apple Silicon, separate boxes, server RAM

Context: current Mac mini M2 16 GB (100 GB/s), Ollama, qwen3.5:9b / gemma4:12b at ~11-18 tok/s.
Server: i5-9400F, 16 GB DDR4, Ubuntu 24.04. No server downtime wanted before Christmas 2026.
Searches done 2026-10-25. Most price pages found are undated aggregator snapshots; treat all prices
as indicative and check eBay UK "sold" filter / CeX / Apple Refurb UK before buying. No eBay UK
sold-listing data and no CeX buy/sell quote could be retrieved.

## 1. Used/refurb Apple Silicon: prices, resale of the M2 16 GB, net upgrade cost

### Takeaway
UK refurb prices for 32 GB+ Macs are well above a £500 net budget in 2026: M2 Pro 32 GB from ~£1,199,
M1 Max Studio 32 GB from ~£1,175, M1 Max 64 GB ~£2,000+, M4 Pro 24 GB ~£1,100-1,450. With the M2 16 GB
selling for roughly £350-400 privately, the net cost of any 32 GB Mac is ~£750-1,100, i.e. over budget
unless a private used deal is found well below refurb-retailer prices.

### Cited Findings
- M2 Mac mini 16 GB/256 GB on eBay UK: one used "like new" listed at £395 (Leeds); one refurbished "very good" at £369.99 (sold out). Refurb tracker: last seen £449, lowest refurb £409 (16/256); 16/512 last seen £579. Original UK price £849 (16 GB). — [refurb.me M2 stats](https://www.refurb.me/gb/stats/mac-mini/mac-mini-m2-early-2023); [everymac UK prices](https://everymac.com/global-mac-prices/all-msrp-mac-mini-prices-in-united-kingdom.html); eBay listings via search (no dated sold data)
- Mac mini M2 Pro 32 GB/512 GB: lowest Excellent £1,199 at eBay Refurbished (most days over prior 30 days), £1,356 at Back Market (checked 15 Oct). 1 TB variant out of stock, last seen 18 Sept 2026 from £1,099. — [refurb.me MNH73-134](https://www.refurb.me/gb/refurbished/mac-mini/sku/MNH73-134); [refurb.me MNH73-135](https://www.refurb.me/gb/refurbished/mac-mini/sku/MNH73-135)
- Hoxton Macs lists an M2 Pro 10-core mini "Fair" at £555 — memory not confirmed (likely 16 GB base). — [Hoxton Macs](https://www.hoxtonmacs.co.uk/products/mac-mini-m2-pro-10-core-2023-fair)
- Mac mini M4 Pro 24 GB/512 GB: Amazon UK 3rd-party used avg ~£1,199 (low £1,031.71 Jun 2025, high £1,339.31 May 2026); eBay Refurbished £1,399 (Good) / £1,449 (Excellent); Back Market £1,472; Apple Certified Refurb £1,189 (undated, HotUKDeals). RRP £1,399. — [camelcamelcamel](https://uk.camelcamelcamel.com/product/B0DLC7G8BN); [refurb.me M4 Pro](https://www.refurb.me/stats/mac-mini/mac-mini-m4-pro-late-2024); [Back Market](https://www.backmarket.co.uk/en-gb/p/mac-mini-october-2024-m4-pro-45-ghz-ssd-512-gb-24gb/e8853dcb-292a-4ede-b0aa-3c9ff647e367); [HotUKDeals](https://www.hotukdeals.com/deals/refurbished-m4-mac-mini-various-models-256gb-512gb-ssd-16gb-224gb-ram-4907884)
- Mac Studio M1 Max: cheapest UK listing £1,175 (Amazon Renewed, 32 GB/512 GB; launch £1,999). 64 GB/1 TB ~£2,082 (Back Market; memory spec on page ambiguous). 64 GB/4 TB £2,499 (eBay) to £2,804 (Back Market). Back Market Ireland 64 GB/512 GB €2,077. — [refurb.me M1 Max](https://www.refurb.me/refurbished/mac-studio/with-m1-max); [Back Market IE](https://www.backmarket.ie/en-ie/p/mac-studio-m1-max-ssd-512gb-ram-64gb/be40b80d-fe7f-4939-bcef-e3c26634ac13)
- An eBay listing (UK seller, on ebay.de) showed a *new* M1 Max 64 GB/1 TB at £1,695. — [eBay](https://www.ebay.de/itm/205330779855)
- No reliable price found for a plain M4 (non-Pro) 24/32 GB used, or an M1 Pro 32 GB mini (M1 Pro was never sold in the Mac mini; only MacBook Pro).

### Inferences
- Net upgrade cost (refurb-retailer prices minus ~£350-400 private sale of the M2 16 GB):
  M2 Pro 32 GB ≈ £800-850; M4 Pro 24 GB ≈ £700-1,100; M1 Max Studio 32 GB ≈ £780-830; M1 Max 64 GB ≈ £1,300-1,700.
  None fits £500 net from retailers. Private eBay/Facebook deals may be £150-300 lower (unverified).
- M4 Pro 24 GB is a poor LLM buy: only ~16-18 GB usable for models, barely more than a 32B Q4 needs.
- M1 Max 32 GB Studio at ~£1,175 gives 400 GB/s (2x the M2 Pro) for about the same money as an M2 Pro 32 GB; for decode speed it is the better 32 GB option, at ~11 W idle vs ~5-7 W.
- Note: there is no "Mac mini M1 Pro"; the brief's M1/M2 Pro 32 GB mini means M2 Pro.

### Gaps
- No eBay UK sold-price data (search tool cannot reach eBay completed listings); no CeX trade-in quote for M2 16 GB.
- No M4 base 24/32 GB used UK price found. Apple Refurbished UK store stock not retrieved.
- The 2026 DRAM shortage may be inflating used Mac prices; no source quantified this for Macs.

## 2. macOS GPU memory limit (iogpu.wired_limit_mb): usable share of 32 GB

### Takeaway
By default ~65-75% of unified memory (≈21-24 GB on 32 GB) is GPU-wireable; `sysctl iogpu.wired_limit_mb`
can raise it to ~26-28 GB on 32 GB, leaving 4-6 GB for a headless macOS. Not persistent across reboots
without a LaunchDaemon.

### Cited Findings
- Default cap measured by the community at ~65-75% of RAM (undocumented by Apple); ≈21-24 GB on 32 GB. — [localaimaster](https://localaimaster.com/blog/mac-memory-pressure-local-llm); [mehmetbaykar.com](https://mehmetbaykar.com/posts/increase-vram-apple-silicon-local-llm/)
- Set with `sudo sysctl iogpu.wired_limit_mb=<MB>` (e.g. 28672 for 28 GB); takes effect immediately; resets at reboot, persisted via LaunchDaemon. Headroom advice ranges 4-8 GB to 8-16 GB for macOS. — [devnote override macos metal vram cap](https://github.com/ivanopcode/devnote-override-macos-metal-vram-cap); [bestllmfor.com](https://bestllmfor.com/guide/optimiser-mac-silicon-llm/)
- KV cache shares the same pool, so a model that loads can still OOM at long context. — [localaimaster](https://localaimaster.com/blog/mac-memory-pressure-local-llm)

### Inferences
- Usable for model + KV on a headless 32 GB Mac: ~24-27 GB; on 64 GB: ~56-58 GB; on 24 GB: ~16-18 GB; current 16 GB: ~10.5-12 GB (explains the 9-12B ceiling today).
- 32 GB comfortably fits a dense 27-32B at Q4_K_M (~17-20 GB) with 8-16K context, or Qwen3 30B-A3B Q4 (~18-19 GB). gpt-oss-120b (~61-65 GB MXFP4) does not fit even 64 GB with headroom.

### Gaps
- No Apple documentation; the sysctl name has changed between macOS versions before (older `debug.iogpu.wired_limit`).

## 3. Two-Mac clustering (exo, llama.cpp RPC)

### Takeaway
Not worth it for this use. Clustering only helps when a model cannot fit on one machine; single-stream
decode gets slower over Ethernet/TB, and the M2 16 GB's 100 GB/s would bottleneck any layer split.

### Cited Findings
- exo's own 2-device test (Llama 3.2 3B, M4 Pro): 1 device ~49 tok/s; 2 devices ~44 tok/s single request, ~96 tok/s aggregate with concurrent requests. — [lobsterpack.com](https://www.lobsterpack.com/blog/exo-distributed-ai-cluster-macs/)
- Jeff Geerling, 4x M3 Ultra, Qwen3 235B: llama.cpp RPC fell from 20.4 tok/s (1 node) to 15.2 tok/s (4 nodes); exo with RDMA over Thunderbolt 5 rose from ~19.5 to 32 tok/s (needs TB5 + macOS RDMA, M4 Pro/M3 Ultra-class). — [lobsterpack.com](https://www.lobsterpack.com/blog/exo-distributed-ai-cluster-macs/)
- 2x M3 Ultra running DeepSeek R1 671B: 18.6 tok/s short context dropping to ~6.4 tok/s at ~13K tokens, OOM at 16K. — [lobsterpack.com](https://www.lobsterpack.com/blog/exo-distributed-ai-cluster-macs/)
- Heise: Nemotron 70B on four M4 Pro minis with TB5 interconnect. — [heise](https://heise.de/-10015283)

### Inferences
- An M2 16 GB + another Mac via llama.cpp RPC over gigabit Ethernet would run at below the slower node's speed for the layers it holds; the M2 has no TB5/RDMA. Better to sell the M2 and buy one bigger machine; or keep the M2 serving small fast models (triage/embeddings) alongside a bigger box, as two independent Ollama endpoints rather than a cluster.

### Gaps
- No two-Mac-mini (M2 + M2 Pro class) llama.cpp RPC benchmark found.

## 4. Server RAM to 32/64 GB DDR4 and CPU-only/hybrid MoE inference on the i5-9400F

### Takeaway
Cheapest option by far (~£115-135 for +32 GB, ~£230-270 for 64 GB, prices undated) but slow: the
9400F is limited to DDR4-2666 dual-channel (~42.7 GB/s theoretical), so MoE models with ~3-5B active
params would decode at an estimated ~5-12 tok/s and dense 27-32B at ~1.5-2.5 tok/s. Requires opening the
server (≈15-30 min downtime), which conflicts with the no-downtime-before-Christmas preference.

### Cited Findings
- i5-9400F: max 128 GB, DDR4-2666, 2 channels. — [Adorama/Intel spec](https://www.adorama.com/in684i59400f.html); [cputronic](https://cputronic.com/en/cpu/intel-core-i5-9400f)
- A user report shows 32 GB dual-channel on an Asus PRIME H310M-C with an i5-9400F. — [valid.x86.fr](https://valid.x86.fr/d9iyw6)
- UK DDR4-3200 2x16 GB kits: Kingston Fury Beast 2x16 GB from £134.99; DIMM 32 GB DDR4-3200 listings from ~£119 (PriceSpy, undated). — [PriceSpy DDR4 32GB](https://pricespy.co.uk/s/ddr4-32gb-ram-3200mhz/)
- Memory per-GB prices back to "2007 levels" due to AI demand; DDR4 kits roughly half the price of comparable DDR5. — [Tom's Hardware UK, RAM shortage tag](https://www.tomshardware.com/uk/tag/ram-shortage)
- Calculated ceiling ~17 tok/s for qwen3:30b-a3b on DDR4-3200 dual-channel; real results typically 50-80% of the ceiling (calculated, not measured). — [localaimaster CPU-only](https://localaimaster.com/blog/run-llm-cpu-only)
- OpenBenchmarking llama.cpp b6401, gpt-oss-20b Q8_0 CPU-only: 17.51 tok/s TG128 (CPU/memory unknown, likely a much faster platform). — [OpenBenchmarking](https://mail.openbenchmarking.org/performance/test/pts/llama-cpp/6bd6fe7595f2848b58f6367e02f8c9600f8469a8)
- Hybrid gpt-oss-120b on RTX 3090 + 64 GB DDR4-3200 with `--n-cpu-moe 24`: ~15 tok/s TG, ~50 tok/s PP; nearly fills VRAM and RAM (secondhand summary of a Reddit post). — [scuttle.klotz.me](https://scuttle.klotz.me/tags/gpt-oss+120b)
- Laptop i7-5600U DDR3L, Qwen3-30B-A3B IQ3_XXS: ~1.9-2.7 tok/s (column ambiguous). — [gitea README](https://gitea.dmz.rs/coja/dots/raw/branch/main/lw/.config/llamacpp/README.md)

### Inferences (bandwidth math, not measured on a 9400F)
- DDR4-2666 dual = 42.7 GB/s theoretical, ~30-35 GB/s achievable. Faster DDR4-3200 sticks run at 2666 on B360/H310 (only Z390 can overclock memory, and the 9400F's controller is rated 2666).
- Qwen3 30B-A3B Q4_K_M (~3.3B active, ~2 GB read/token): ceiling ~15 tok/s, realistic ~7-11 tok/s TG; prompt processing on 6 cores without AVX-512 will be slow (~20-50 tok/s), which matters for long prompts but not much for a background loop.
- gpt-oss-20b (MXFP4, 3.6B active, ~12-13 GB file): similar ~7-11 tok/s; fits in 32 GB total RAM alongside the existing services.
- gpt-oss-120b (5.1B active, ~61-65 GB file): needs ≥96 GB RAM to coexist with Docker services; at 64 GB it would not fit. If 128 GB (4x32 GB) were installed: ~4-7 tok/s estimated. 4x32 GB DDR4 is ~£460-540 at current pricing (inferred from 2x16 kit prices; unverified).
- Dense 27-32B Q4 (~17-20 GB/token): ~1.5-2 tok/s — impractical even for background use beyond short jobs.
- Slot limits (typical, check the actual board manual): H310 boards are usually 2 DIMM slots, max 32 GB officially (2x16), often 64 GB works with 32 GB sticks after BIOS update; B360/B365 and Z390 mATX/ATX usually 4 slots, 64 GB official at launch, 128 GB with later BIOS (2x32/4x32). Run `sudo dmidecode -t memory` (via bootstrap-style root, or user reads board model from `/sys/class/dmi/id/board_name`) to learn slot count.
- Competes for the server's 6 cores with Jellyfin, the arr stack, etc. — llama.cpp at full threads would slow other services; cap threads (e.g. 4).

### Gaps
- No measured llama.cpp result for any Coffee Lake 6-core + DDR4-2666 on a 30B MoE model. No dated Oct 2026 UK DDR4 price. Board model unknown.

## 5. Mini PCs (Ryzen 7840HS/8845HS 64 GB, Ryzen AI 300) and AMD Strix Halo

### Takeaway
A used/new 8845HS mini PC with 64 GB DDR5-5600 (~89.6 GB/s, ~2x the server) is the only separate box
plausibly near £500, but 64 GB DDR5 SO-DIMM alone is now expensive and its decode speed is similar
to or below the current M2's bandwidth class. Strix Halo 128 GB (256 GB/s, up to ~96 GB to the GPU) is
the real upgrade but costs ~£1,100-1,300+ in the UK (net ~£750-950 after selling the M2), over budget.

### Cited Findings
- Ryzen 7 8845HS: 8 Zen 4 cores, 45 W default (35-54 W); GEEKOM A8 ships 32 GB DDR5-5600 dual-channel, expandable to 64 GB. — [starryhope](https://www.starryhope.com/minipcs/processor/amd-ryzen-7-8845hs/); [GEEKOM A8 listing](https://ubbcentral.com/store/item/GEEKOM-A8-Mini-PC-Gaming-PC-AMD-Ryzen-7-8845HS-32G-DDR5-1TB-SSD-Windows-11-Pro_395517802688.html)
- GMKtec K8 (8845HS) launched at 2,499 RMB (~$350) barebones-class pricing in China (old, 2024). — [pcgameshardware](https://www.pcgameshardware.de/Gaming-PC-Hardware-217554/News/GMKtec-K8-Ryzen-7-8845HS-Preis-kaufen-1440046/)
- Bosgame M5 (Ryzen AI Max+ 395, 128 GB LPDDR5X standard, up to 96 GB to GPU): US pre-order $1,699; TechRadar UK review lists £1,103 and £1,259 for two options (undated, configs unclear); German deal posts €1,450-1,581 earlier, later €2,588.95 (down from €3,193). — [TechRadar review](https://www.techradar.com/computing/bosgame-m5-ai-mini-pc-review); [liliputing](https://liliputing.com/bosgame-m5-ai-is-a-mini-pc-with-ryzen-ai-max-395-and-a-familiar-design); [mydealz](https://www.mydealz.de/deals/ryzen-ai-max-395-mini-pc-mit-128gb-ram-2tb-ssd-fur-ki-und-gaming-2655372)
- MSI Pro Max Edge AI+ (395, 128 GB) UK £4,499; Minisforum MS-S1 Max $2,959 at Newegg (sale, now out of stock); US 128 GB Strix Halo minis ~$2,400-3,200. — [KitGuru](https://www.kitguru.net/desktop-pc/mustafa-mahmoud/msis-pro-max-edge-ai-mini-pc-now-available-in-uk-for-4499/); [TechRadar MS-S1](https://www.techradar.com/pro/this-is-no-normal-mini-pc-minisforum-ms-s1-max-with-amd-ryzen-ai-max-395-cpu-128gb-ddr5-ram-and-a-2tb-ssd-is-the-best-mini-workstation-for-ai-weve-ever-tested-and-its-now-on-sale-at-newegg); [liliputing](https://liliputing.com/?p=198638)
- Strix Halo community llama.cpp result: Qwen3 30B-A3B at 100+ tok/s (laptop). — [aiweekly](https://aiweekly.co/node/2422)

### Inferences
- 8845HS/7840HS 64 GB box: Qwen3 30B-A3B / gpt-oss-20b est. ~15-25 tok/s (Vulkan on 780M iGPU or CPU), dense 32B Q4 ~3-4 tok/s. Fits gpt-oss-120b? No (64 GB total). Idle ~6-10 W typical for this class (not sourced here). Price: barebones 8845HS ~£300-400 + 64 GB DDR5 SO-DIMM (likely £200-300+ in the 2026 shortage) — roughly £500-700, no resale offset unless the M2 is also sold. Quality gain vs. a 32 GB Mac is mainly "can hold a 30B MoE"; worse for dense 27-32B.
- Ryzen AI 300 (HX 370) minis: same ~LPDDR5X-7500 dual-channel class (~120 GB/s), similar to the M4 base; not found priced.
- Strix Halo: dense 32B Q4 est. ~10-12 tok/s, 30B-A3B 50-100 tok/s, gpt-oss-120b ~30-50 tok/s (bandwidth math; community reports in this range were not fetched). Best "quality per £" if budget stretches to ~£1,100-1,300.
- The Strix Halo prices above conflict heavily (DRAM shortage moved prices up through 2026); the £1,103-1,259 TechRadar figure may be from 2025.

### Gaps
- No verified current UK price for any Strix Halo 128 GB box, Framework Desktop, or GMKtec EVO-X2; no UK used 7840HS/8845HS 64 GB prices; no measured 8845HS benchmark for 30B MoE.

## 6. Expected decode speeds (summary), idle/load power and running cost

### Takeaway
Decode speed tracks memory bandwidth: tok/s ≈ bandwidth ÷ bytes read per token. Apple's llama.cpp
table gives a reliable scale (7B Q4_0 TG): M2 21.9, M2 Pro 38.9, M1 Max 61, M4 Pro 50.7. All options idle
at 4-11 W (Macs) — about £9-27/year at 27p/kWh — so power is not a deciding factor except vs. running the
server CPU flat-out.

### Cited Findings
- llama.cpp Apple Silicon benchmark (Llama 7B, Q4_0 TG / PP512): M1 (68 GB/s) 14.2 / 118; M2 (100 GB/s) 21.9 / 180; M2 Pro 19-GPU (200 GB/s) 38.9 / 341; M1 Max 24-GPU (400 GB/s) 54.6 / 400; M1 Max 32-GPU 61.2 / 530; M4 (120 GB/s) 24.1 / 221; M4 Pro 20-GPU (273 GB/s) 50.7 / 440; M4 Max 40-GPU (546 GB/s) 83.1 / 886. (Older 2023-2025 data, still the reference.) — [llama.cpp discussion #4167](https://github.com/ggml-org/llama.cpp/discussions/4167)
- M4 Pro 64 GB measured: gpt-oss-20b 4-bit 54.2 tok/s at 16K ctx, 42.7 at 32K, 33.3 at 64K; Qwen3-Coder-30B-A3B (MLX) 62.3 tok/s at 4K, 76.5 at 1K. — [hardware-corner](https://www.hardware-corner.net/is-mac-mini-m4-pro-good-for-llms/); [oMLX benchmark](https://omlx.ai/benchmarks/ktfijjyp)
- Apple power figures (wall): Mac mini M4 4 W idle / 65 W max; M4 Pro 64 GB ~5 W idle / 140 W max; Mac Studio M1 Max 32 GB 11 W idle / 115 W max; M4 Max Studio 6 W / 145 W. Choice measured M4 Pro mini 6 W idle, 76 W heavy load. Jeff Geerling: M4 base mini 3-4 W idle. — [Apple Mac mini power](https://support.apple.com/103253); [Apple Mac Studio power](https://support.apple.com/en-gb/102027); [Choice](https://www.choice.com.au/electronics-and-technology/computers/desktop-and-laptop-computers/articles/apple-mac-mini-vs-mac-studio-how-do-these-desktop-computers-compare); [Jeff Geerling](https://www.jeffgeerling.com/blog/2024/m4-mac-minis-efficiency-incredible/)

### Inferences (estimates: scale table numbers by model size; Q4_K_M ≈ 0.6 GB per B params)
| Option | Memory for models | Dense 27-32B Q4 | 30B-A3B / gpt-oss-20b | gpt-oss-120b | Idle W | Net cost* |
|---|---|---|---|---|---|---|
| Current M2 16 GB | ~11 GB | doesn't fit | doesn't fit well (Q3 at best) | no | ~5-7 | — |
| M2 Pro 32 GB mini | ~25-27 GB | ~8-10 tok/s | ~35-45 | no | ~7 | ~£800-850 |
| M4 Pro 24 GB mini | ~16-18 GB | ~11-13 (tight, short ctx) | ~45-55 | no | ~5 | ~£700-1,100 |
| M1 Max 32 GB Studio | ~25-27 GB | ~15-18 | ~50-60 | no | ~11 | ~£780-830 |
| M1 Max 64 GB Studio | ~56 GB | ~15-18; 70B Q4 ~7-8 | ~50-60 | no (just too big) | ~11 | ~£1,300-1,700 |
| Server +32 GB (48 GB) | ~35 GB free | ~1.5-2 | ~7-11 | no | +~1-2 W | ~£120-135 |
| Server 64 GB | ~50 GB free | ~1.5-2 | ~7-11 | no | +~2 W | ~£230-270 |
| Server 128 GB | ~110 GB free | ~1.5-2 | ~7-11 | ~4-7 | +~4 W | ~£460-540 |
| 8845HS + 64 GB | ~50 GB | ~3-4 | ~15-25 | no | ~6-10 | ~£500-700 (keep M2) |
| Strix Halo 128 GB | ~96 GB GPU | ~10-12 | ~50-100 | ~30-50 | ~10-15 | ~£750-950 after M2 sale |
*Net = price minus ~£350-400 M2 16 GB sale, retailer refurb prices; private deals cheaper.
- Running cost at 27p/kWh: each 1 W continuous ≈ 8.76 kWh/yr ≈ £2.37/yr. A Mac idling at 5-11 W ≈ £12-26/yr; a background loop at ~40 W average ≈ £95/yr. The i5-9400F pushing all cores for LLM decode adds maybe 40-60 W while generating (unsourced estimate), and at 1/5 the speed it runs ~5x longer per answer, so the server-RAM route costs more energy per token.
- Quality angle (the user's priority): 32 GB unlocks dense 27-32B models (clear step up from 9-12B); 64 GB+ unlocks 70B dense or ~100B MoE at Q4. Within ~£500 net, the only routes that unlock 30B-class quality are (a) server RAM + MoE models on CPU (slow but cheap, but needs a short downtime) or (b) finding a private-sale M2 Pro / M1 Max 32 GB for ≤~£850-900 and selling the M2.

### Gaps
- No measured idle power for 8845HS minis or Strix Halo in sources fetched. No measured 9400F LLM power draw.
- Speeds in the table are bandwidth-scaled estimates, not benchmarks, except the M4 Pro row inputs and the llama.cpp 7B table.
