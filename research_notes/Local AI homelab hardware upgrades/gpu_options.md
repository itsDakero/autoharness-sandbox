# GPU upgrade options under ~£500 for local LLMs (UK, Oct 2026)

Host context: i5-9400F (no iGPU), 16 GB DDR4, GTX 970 4 GB (Maxwell) doing Jellyfin NVENC, NVIDIA driver 580 pinned.
Priority: answer quality over speed, 24/7 background agent. Research date 2026-10-25. 20 tool calls; several
key price trackers are SEO/affiliate sites with internally inconsistent numbers, flagged where relevant.

## Candidate comparison: VRAM, UK price, power, software, transcoding

### Takeaway
The 2026 AI-driven memory shortage has pushed 16 GB+ cards well above their launch prices. A used RTX 3090
is no longer reachable at £500 (roughly £850-1,100 used). Within £500, the sane choices are a 16 GB card (RTX 5060 Ti 16GB,
about £500 used or £485+ new; RX 9060 XT 16GB, about £435-600 new) or a cheap used RTX 3060 12GB (about £185-220).
The only 24 GB+ options at this price are datacenter cards (P40, MI50) with real software and cooling caveats.

### Cited Findings
Prices
- Memory costs are driving GPU price hikes through 2026. TrendForce expected phased NVIDIA/AMD hikes from Q1 2026,
  and Bernstein does not expect the shortage to ease before 2027. Cards with 16/24 GB+ VRAM see the largest hikes — [Astute Group](https://www.astutegroup.com/news/general/gpu-pricing-set-for-reset-as-ai-driven-memory-shortages-push-costs-sharply-higher/); [tech-insider](https://tech-insider.org/gpu-relief-pushed-2028-dram-price-jump-2026/)
- RTX 3090 used, UK: gpudojo (updated 19 Sep 2026) gives a floor of about £860 and a high of about £1,050. pcprice.watch (8 Oct 2026) gives a median sold price of €1,180 from 228 eBay sales,
  trending up, with the cheapest listing about €664 shipped from China. bestvaluegpu's title says £1,077 used (Oct 2026), but its body says £751, so it is inconsistent — [gpudojo](https://gpudojo.com/uk/rtx-3090); [pcprice.watch](https://www.pcprice.watch/search/RTX3090/GB/GPU); [bestvaluegpu](https://bestvaluegpu.com/en-gb/history/new-and-used-rtx-3090-price-history-and-specs/)
- RTX 3090 used, US (Oct 2026): the median sold price is about $1,376 from 235 eBay sales over 90 days, 9% below a $1,623 September 2026 peak.
  Older "$600-800" figures (e.g. XDA) predate the rise — [pcprice.watch US](https://www.pcprice.watch/search/RTX3090/US/GPU); [XDA](https://www.xda-developers.com/used-rtx-3090-still-best-for-local-ai-in-value/)
- One HP RTX 3090 sold for £479.99 on eBay UK, likely in Oct 2025. It is an outlier and stale — [eBay](https://www.ebay.co.uk/itm/147628060751)
- RTX 5060 Ti 16GB: launch MSRP £399 — [OC3D](https://overclock3d.net/news/gpu-displays/nvidia-confirms-the-uk-msrps-for-their-rtx-5060-ti/). About 73 days before this search (around Aug 2026),
  the cheapest Overclockers UK 16GB card was £578.99, above an RTX 5070 at £569.99 — [OC3D](https://overclock3d.net/news/gpu-displays/nvidias-rtx-5060-ti-16gb-now-costs-more-than-an-rtx-5070/).
  Used on eBay UK: £499 (7 Oct 2026) — [gpudojo](https://gpudojo.com/uk/rtx-5060-ti-16gb). New PriceSpy listings start around £485-660, undated — [PriceSpy](https://pricespy.co.uk/s/5060-ti-16gb/)
- RX 9060 XT 16GB: PriceSpy lows are about £435 (Asus TUF) and £496 (ASRock), with most boards at £500-600. Scan has one at £679.99 — [PriceSpy](https://pricespy.co.uk/s/rx-9060-xt-16gb/); [Scan](https://www.scan.co.uk/shop/computer-hardware/gpu-amd-gaming/amd-radeon-rx-9060-xt-16gb-graphics-cards). bestvaluegpu's title says £510 new (Oct 2026) — [bestvaluegpu](https://bestvaluegpu.com/en-gb/history/new-and-used-rx-9060-xt-16gb-price-history-and-specs/)
- Arc B580 12GB: £291 (gpuprix, Jul 2026); £399 with a £462 market average (gpupricehistory, Sep 2026); launch MSRP about £239 — [gpuprix](https://gpuprix.com/uk/gpus/arc-b580); [gpupricehistory](https://gpupricehistory.com/uk/arc-b580); [bestvaluegpu](https://bestvaluegpu.com/en-gb/history/new-and-used-b580-price-history-and-specs/)
- Arc Pro B60 24GB: the lowest UK price is £620 (gpuprix, updated 29 Jun 2026). US MSRP is $599 — [gpuprix](https://gpuprix.com/uk/gpus/arc-pro-b60); [Guru3D](https://www.guru3d.com/story/intel-arc-pro-b60-workstation-gpu-listed-at-with-24gb-memory)
- RTX 3060 12GB used, UK eBay: asking prices about £185-220, plus a refurbished one at £199 (listings undated) — [eBay](https://www.ebay.co.uk/itm/168657756901). The 3060 12GB was "reintroduced"
  in 2026, and new prices reportedly rose about 45% in two months, with some near $500 (Guru3D, 29 Aug 2026) — [Guru3D](https://www.guru3d.com/publish/comments/geforce-rtx-3060-12gb-prices-reportedly-jump-after-relaunch/)
- Tesla P40 24GB: about $420 renewed on Amazon US (22 Oct 2026); other guides say $220-345. P100 16GB: about $155. V100 16GB: about $365; V100 32GB: about $860 —
  [computingforgeeks](https://computingforgeeks.com/best-used-datacenter-gpu-local-ai/); [openclawdc](https://openclawdc.com/blog/tesla-p40-local-llm-worth-it/)
- MI50 32GB: price claims differ 3-4x, from $120-210 on the Chinese export market to $600-830 for live eBay asks (Sep 2026) —
  [openclawdc](https://openclawdc.com/blog/amd-mi50-32gb-local-llm/); [pasqualepillitteri](https://pasqualepillitteri.it/en/news/10761/used-server-gpu-local-llm-prices-europe)

Software support
- Ollama: NVIDIA needs compute capability 5.0+ and driver 550+. CC 5.0-6.2 (Maxwell/Pascal) needs driver 570+. AMD on Linux needs the ROCm v7 driver.
  The RX 9060 XT and RX 7600 XT are on the supported list. The MI50 (gfx906) is not. Vulkan is enabled by default when its backend is installed (Linux needs Mesa or vendor packages)
  and can be disabled with OLLAMA_VULKAN=0. Vulkan VRAM reporting needs root or cap_perfmon. Intel has no dedicated section and is covered via Vulkan — [Ollama GPU docs](https://docs.ollama.com/gpu)
- ROCm 7.0.2 officially supports the RX 9060 / 9060 XT (RDNA4) — [Phoronix](https://www.phoronix.com/news/AMD-ROCm-7.0.2-Released)
- Intel archived IPEX-LLM (its Ollama/llama.cpp acceleration fork) on 28 Jan 2026, and Vulkan is the recommended path — [insiderllm](https://insiderllm.com/guides/intel-arc-b580-local-llm/).
  Community tests show Vulkan beating SYCL on the B580 in llama.cpp. On an Arc Pro B60, one user measured Qwen3.5 9B Q4 at about 17.8 tok/s on Vulkan
  and about 23.0 tok/s on SYCL, with Vulkan faster at prompt processing. Intel's vLLM fork is described as less dependable than llama.cpp —
  [Level1Techs](https://forum.level1techs.com/t/arc-pro-b60-for-local-llms/246971); [bentech](https://bentech.substack.com/p/running-local-llms-on-intel-arc-pro)
- P40/P100/V100: CUDA 12.x only (CUDA 13 dropped Pascal and Volta). R580 is their last driver branch. llama.cpp works with CUDA 12 builds. vLLM does not support them
  (V100 is CC 7.0; vLLM needs 7.5). MI50: ROCm dropped it, so it runs on Vulkan or community gfx906 forks (the first fork is unmaintained and points to
  mxxm-t/mx-llama.cpp) — [computingforgeeks](https://computingforgeeks.com/best-used-datacenter-gpu-local-ai/); [Tesla/MI50 search summary via computingforgeeks + openclawdc](https://openclawdc.com/blog/amd-mi50-32gb-local-llm/)

Power (24/7 matters)
- RTX 5060 Ti 16GB: idles at about 14-17 W (IgorsLab) and is rated at 180 W TDP. On Linux, Phoronix measured 138 W average and 183 W peak in graphics load —
  [IgorsLab](https://www.igorslab.de/en/nvidia-geforce-rtx-5060-ti-16-gb-in-test-economical-consumption-surprisingly-fast-but-not-with-8gb/10); [Phoronix](https://www.phoronix.com/review/nvidia-rtx-5060ti-linux-gaming/6)
- RX 9060 XT averages about 175 W in 1080p gaming, against 156 W for the 5060 Ti — [IgorsLab](https://www.igorslab.de/en/xfx-swift-radeon-rx-9060-xt-und-sapphire-nitro-rx-9060-xt-im-test-amds-antwort-auf-die-geforce-rtx-5060-ti/12/)
- Arc B580/B570: on Linux, minimum (idle) power is "much higher than the NVIDIA and AMD graphics cards" (Phoronix). Intel says the B580 idles below 10 W only with
  ASPM/L1 enabled, and that figure is from Windows. VRAM stays at full clock at idle — [Phoronix](https://www.phoronix.com/review/intel-arc-b570-linux/5); [Intel](https://www.intel.com/content/www/us/en/support/articles/000101330.html)
- RTX 3090: Linux users report 100 W+ idle in some setups. Switching PowerMizer to Adaptive brought it down to about 40 W — [NVIDIA forums](https://forums.developer.nvidia.com/t/bug-report-idle-power-draw-is-astronomical-with-rtx-3090/155632)
- P40: 11 W idle before a model loads, but owners report about 50 W in P0 with a model resident. The nvidia-pstated daemon can force P8. P100 idles at 28 W —
  [computingforgeeks](https://computingforgeeks.com/best-used-datacenter-gpu-local-ai/)

Jellyfin transcoding
- Jellyfin ranks encoder quality Apple >= Intel >= NVIDIA >>> AMD and says Intel QSV is the easiest to set up. AMD's H.264 quality is "no match" for QSV/NVENC, but AMD
  has no limit on concurrent sessions. AV1 encode is available on Arc A-series and newer, RX 7000+, and NVENC 8th gen (Ada/Blackwell). Ampere (RTX 30xx) decodes AV1 but cannot encode it —
  [Jellyfin hardware selection](https://jellyfin.org/docs/general/administration/hardware-selection); [Jellyfin Intel](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/intel); [Jellyfin AMD](https://jellyfin.org/docs/general/post-install/transcoding/hardware-acceleration/amd); [aicybr](https://aicybr.com/blog/jellyfin-hardware-transcoding-intel-nvidia-amd)
- The NVIDIA GeForce driver caps simultaneous NVENC sessions (12 per the guide) — [aicybr](https://aicybr.com/blog/jellyfin-hardware-transcoding-intel-nvidia-amd)

### Inferences
Dense table. Prices come from the cited findings. The TDP, power connector, PSU and size columns are standard reference-board specs from
memory, NOT verified this session, and partner boards vary, so check the exact SKU. Yearly cost = idle W x 8.76 kWh x £0.265, which is about **£2.32 per idle watt per year**.

| Card | VRAM | UK price Oct 2026 | Idle / load | Idle £/yr | TDP, power, PSU, size (reference, unverified) | LLM software | Jellyfin |
|---|---|---|---|---|---|---|---|
| RTX 3060 12GB (used) | 12 GB | ~£185-220 used | ~10-15 W idle (unverified) / ~170 W | ~£25-35 | 170 W, 1x8-pin, 550 W PSU, 2-slot ~200-240 mm | CUDA, best support: Ollama, llama.cpp, vLLM | NVENC 7th gen: H.264/HEVC, no AV1 encode |
| RTX 4060 Ti 16GB | 16 GB | not found (EOL; used probably ~£400-450, unverified) | similar to 5060 Ti | ~£30-40 | 165 W, 1x8-pin, 550 W, 2-slot | CUDA, full | NVENC 8th gen, AV1 encode |
| RTX 5060 Ti 16GB | 16 GB | £499 used; £485-580+ new | 14-17 W / ~140-180 W | ~£32-40 | 180 W, 1x8-pin (some 16-pin), ~450-550 W, 2-slot | CUDA, full; Blackwell needs the open kernel module and a 570+ driver | NVENC Blackwell, AV1 encode |
| RTX 3090 (used) | 24 GB | ~£850-1,100: **not reachable at £500** | 20-40 W (can stick at 100 W) / 350 W | ~£50-90+ | 350 W, 2x8-pin (FE 12-pin), 750 W+, 3-slot ~300-330 mm | CUDA, full | NVENC 7th gen |
| Arc B580 12GB | 12 GB | ~£290-400 new | high idle on Linux / ~190 W | likely £50+ unless ASPM works | 190 W, 1x8-pin, ~600 W, 2-slot; needs ReBAR | Vulkan (llama.cpp/Ollama); IPEX archived; weak vLLM | Best Jellyfin encoder (QSV, AV1) |
| Arc A770 16GB | 16 GB | not found (EOL) | Arc idle issue (high) | likely £60+ | 225 W, 8+6-pin, ~650 W; needs ReBAR | Vulkan | QSV, AV1 encode |
| Arc Pro B60 24GB | 24 GB | ~£620 (Jun 2026): over budget | not found | ? | ~200 W, blower, 1x8-pin (unverified) | Vulkan/SYCL llama.cpp | QSV, AV1 |
| RX 7600 XT 16GB | 16 GB | not found | not found | ? | 190 W, 2x8-pin (ref), ~600 W | ROCm v7 listed; Vulkan | AMD VAAPI, weakest quality; AV1 encode |
| RX 9060 XT 16GB | 16 GB | ~£435-600 new | not found / ~175 W | ? | ~160-180 W, 1x8-pin, ~450-500 W, 2-slot | ROCm 7.0.2 official, listed by Ollama; Vulkan fallback | AMD VAAPI/AV1, weakest quality |
| Tesla P40 24GB | 24 GB | ~$220-420 used (US; UK not found) | 11 W idle, ~50 W with a model loaded / 250 W | ~£25-115 | 250 W, **EPS CPU 8-pin** via adapter, passive (needs blower+shroud), full-length, no display, Above 4G | llama.cpp CUDA 12 only; R580 last branch; no vLLM; slow FP16 | NVENC Pascal (H.264/HEVC); no display |
| Tesla P100 16GB | 16 GB | ~$155 | 28 W idle | ~£65 | same as P40 (passive, EPS) | same as P40 | same |
| MI50 32GB | 32 GB | $120-830 (prices conflict) | not found | ? | 300 W, passive, no display | Not in Ollama's ROCm list; Vulkan or fork; hobbyist only | no |
| 2x RTX 3060 12GB | 24 GB | ~£370-440 used | ~2x the 3060 idle (~20-30 W) / ~340 W | ~£50-70 | 2x 8-pin, 650 W+, two x16-size slots (second slot likely x4 via the chipset on a 9th-gen board) | llama.cpp/Ollama split layers fine; vLLM tensor-parallel needs equal cards (OK) | one card can NVENC |

- **Most usable VRAM per £ with sane support:** a used RTX 3060 12GB at ~£16-18/GB is the cheapest CUDA VRAM. 2x 3060 gives 24 GB for ~£400,
  which is the only CUDA route to 24 GB within budget, at the cost of more idle watts, a PCIe x4 second slot and PSU demands. A 16 GB 5060 Ti at ~£500 (~£31/GB) is the clean single-card
  option with low idle and modern NVENC (AV1), so it can also take over Jellyfin. The P40 is the cheapest 24 GB card, but with cooling, power-connector, driver (R580, CUDA 12 only) and no-display pitfalls.
- **"Quality over speed" reading:** VRAM sets the largest model and quant that fits. 12 GB covers ~14B Q4-Q5 models. 16 GB covers ~14B Q8 or ~24B Q4. 24 GB covers ~32B Q4 (my estimate
  from typical GGUF sizes, unsourced). With 16 GB system RAM, CPU offload of larger models is barely possible, so a RAM upgrade may pair with any choice.
- **Driver constraint:** a Maxwell 970 needs the proprietary kernel module, and Blackwell (5060 Ti) needs the open one, so the two cannot share a host. The computingforgeeks note says
  Pascal/Volta "can't share a system with any Blackwell card", and Maxwell is in the same position. **Keeping the 970 for NVENC therefore rules out a 5060 Ti.** An RTX 3060/3090 (Ampere) or 4060 Ti (Ada) can coexist with the 970
  on branch 580. Dropping the 970 removes the 580 pin unless a P40/P100 is chosen, since R580 is Pascal's last branch too.
- **Display:** the 9400F has no iGPU. A P40/MI50 alone gives no console output, so it needs the 970 kept or another card. Moving to the i5-9500 (UHD 630 QSV) fixes both
  display and transcoding and frees the slot.
- **Arc on this host:** Arc needs Resizable BAR for good performance. ReBAR on a Coffee Lake (300-series) board depends on a vendor BIOS update. Combined with high Linux idle draw,
  this makes Arc the weakest 24/7 choice despite having the best Jellyfin encoder.
- Electricity: going from a ~15 W idle card to a 3090 at ~30-40 W idle costs about £35-60/yr more. A P40 that stays in P0 at 50 W costs ~£115/yr.

### Gaps
- No verified UK price found for the RTX 4060 Ti 16GB, A770 16GB, RX 7600 XT, P40/P100/MI50 (UK) or CEX listings. The CEX site was not reached.
- No verified idle figures for the 3060, 9060 XT, 7600 XT or A770, or for any card with an LLM resident in VRAM. TechPowerUp power pages returned 403.
- TDP, power connector, PSU and length values in the table are unverified reference specs. Confirm them for the exact SKU, plus the host's actual PSU wattage and connectors and the case length.
- The motherboard model is unknown, so the PCIe lane layout for dual cards and ReBAR availability could not be checked.
- Whether stock Ollama auto-uses Vulkan on Arc on Linux could not be confirmed in release notes. Sources conflict.
- No 2026 tokens/s benchmarks were gathered per card. Bandwidth matters for speed (3090 > 5060 Ti > 3060), but it was not quantified here.
