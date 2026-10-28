# Voice and phone access to a self-hosted assistant (Oct 2026)

Scope: talking to the assistant (Hermes Agent on the Mac mini M2 16 GB via Ollama; Home Assistant on a Pi) by
voice at home and away, and from an iPhone or Android phone. UK, local or private first. Research date 2026-10-25.
About 24 searches and fetches. Freshness: the HA blog's Assist category lists no 2026 posts (newest is Voice
Chapter 11, Oct 2025). 2026 facts come from HA integration docs (llama.cpp integration 2026.8), Hermes docs,
and third-party blogs. Each finding is marked where the source is older or third-party.

## 1. Home Assistant Assist pipeline: components, satellites, UK prices, external-LLM handoff

### Takeaway
Assist is a mature local pipeline: STT (Whisper or Speech-to-Phrase) → conversation agent (built-in intents first,
then an LLM) → TTS (Piper) with streaming, plus wake words on satellites. As of HA 2026.8 a built-in
"llama.cpp" integration accepts any OpenAI-compatible chat-completions URL as the conversation agent. That makes
it plausible to point Assist at Hermes's own OpenAI-compatible API server, so Assist would talk to the same agent
as Discord (not tested; see Gaps). Voice Preview Edition costs about £56 in the UK.

### Cited Findings
**Pipeline and features**
- Voice Chapter 11 (22 Oct 2025): up to two wake words per satellite, each tied to its own pipeline (2025.10).
  Streaming TTS starts speaking on LLM text chunks: Piper or HA Cloud went from more than 5 s to about 0.5 s before
  speech starts ("10x"). Speech-to-Phrase is a fast, limited local STT. A fuzzy matcher (English only) arrived in
  2025.9. Short beep confirmations replace speech for same-area actions; LLM pipelines keep full spoken replies.
  The Ask Question action lets automations ask a question through a satellite and act on the spoken reply.
  — [HA blog, Voice Chapter 11](https://www.home-assistant.io/blog/2025/10/22/voice-chapter-11/)
- "Building the AI-powered local smart home" (Sep 2025): Assist handles simple device commands itself and
  passes requests it doesn't recognise to the LLM, sharing recent context. HA is both an MCP client (Assist can use
  external tools) and an MCP server (external AI can reach entities). AI Tasks are available. Recent local models
  on 8 GB+ VRAM "nearly match" the leading cloud models (Home LLM Leaderboard). Time to first speech: Piper went
  from 5.31 s to 0.56 s with streaming (test rig: RTX 3090, gemma3:4b). — [HA blog Sep 2025](https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/)
- Chapter 9 (Feb 2025, older) introduced Speech-to-Phrase for Pi or Green-class hardware, plus broadcast and
  analog-phone features. — [Notebookcheck](https://www.notebookcheck.net/Home-Assistant-Voice-chapter-9-arrives-with-new-Speech-to-Phrase-tool.963260.0.html)
- Whisper reaches HA through the Wyoming Protocol integration and can be auto-discovered. — [HA Whisper integration](https://home-assistant.io/integrations/whisper)

**Conversation agents and external LLMs**
- Ollama integration: a conversation agent with experimental "Control Home Assistant" over the Assist API, limited
  to exposed entities (fewer than 25 recommended). Only tool-capable models can control devices, and smaller models
  make mistakes. Default context is 8k. "Think before responding" is off by default and slower. The docs suggest two
  instances of the same model, one for chat and one for control. Sentence triggers are not supported. — [HA Ollama docs](https://www.home-assistant.io/integrations/ollama/)
- **llama.cpp integration (new in HA 2026.8):** "any server that implements the OpenAI-compatible chat
  completions API" can be a conversation agent (llama.cpp, vLLM, LM Studio, DeepSeek listed). Fields: URL
  (e.g. `http://host:8080/v1`), optional API key, model, instructions, control level. It has Assist API access and
  no sentence triggers. The page doesn't say whether it streams. — [HA llama.cpp docs](https://www.home-assistant.io/integrations/llama_cpp)
- The official OpenAI integration does not accept a custom base URL; maintainers pushed back on the request.
  Alternatives: the custom integrations "Local OpenAI LLM" (hass_local_openai_llm) and the "Extended OpenAI
  Conversation" fork via HACS (maintenance status not checked). — [HA discussion #981](https://github.com/orgs/home-assistant/discussions/981); [hass_local_openai_llm](https://github.com/skye-harris/hass_local_openai_llm)
- Hermes Agent ships an OpenAI-compatible API server: `API_SERVER_ENABLED=true`, default port 8642, path `/v1`,
  and `API_SERVER_KEY` is mandatory when bound to a non-loopback address. It is an agent runtime (tools run on the
  Hermes host), not a plain LLM proxy. Docs disagree on whether streaming shows progress or arrives all at once. — [Hermes API server docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server); [Open WebUI: Hermes Agent](https://docs.openwebui.com/getting-started/quick-start/connect-an-agent/hermes-agent)

**STT/TTS servers**
- Speaches: an OpenAI-API-compatible server for streaming STT (faster-whisper) and TTS (Kokoro, Piper), with a
  Realtime API, GPU or CPU, and Docker. Models load on demand and unload when idle. 3.7k stars; Apple Silicon is not
  mentioned. — [speaches-ai/speaches](https://github.com/speaches-ai/speaches)
- Kokoro-82M: Kokoro-FastAPI is an OpenAI-speech-compatible Docker wrapper, Apache-2.0, v0.7.1 (2 Aug 2026 per one
  source), and CPU-friendly. — [ariya.io Mar 2026](https://ariya.io/2026/03/local-cpu-friendly-high-quality-tts-text-to-speech-with-kokoro); [localaimaster](https://localaimaster.com/blog/local-tts-api-server-kokoro-fastapi)
- A Mac mini stack of whisper.cpp (Metal) + Ollama + Piper + Wyoming for HA is described in third-party blogs
  (latency unverified). — [aiagentskit](https://aiagentskit.com/blog/mac-mini-home-ai-server/)

**Wake word and satellites (UK prices)**
- Voice Preview Edition: £55.80 at The Pi Hut (stock varies between listings). Launch price $59 / £56. — [The Pi Hut](https://thepihut.com/products/home-assistant-voice-preview-edition); [Notebookcheck](https://www.notebookcheck.net/Home-Assistant-launches-new-privacy-first-voice-assistant-hardware.937193.0.html)
- ReSpeaker Lite with XIAO ESP32S3 (XMOS XU316 audio front end) is sold by The Pi Hut. The bare board without an
  MCU is £27.30. — [The Pi Hut](https://thepihut.com/products/respeaker-lite-with-xiao-esp32s3); [search summary of retailers](https://core-electronics.com.au/respeaker-lite-usb-2-mic-array-seeed-studio.html)
- FutureProofHomes Satellite1: ESP32-S3 + XMOS XU316, drives speakers up to 25 W. The dev kit was $79.99 and the
  HAT $54.99 (2025 pre-order, older; no current UK price found). — [CNX Software](https://www.cnx-software.com/?p=135489)
- microWakeWord runs on-device on ESPHome satellites. — [ESPHome micro_wake_word](https://esphome.io/components/micro_wake_word.html)
- A third-party 2026 guide (updated Sep 2026) gives these tiers: starter $100–150 at 3–5 s; N100 mini PC + Voice PE
  at 1–3 s with Whisper medium; GPU tier at 1–2 s. Known weaknesses: wake words misfire with TV noise, and
  built-in intents are literal. — [kunalganglani.com](https://www.kunalganglani.com/blog/self-hosted-voice-assistant-home-assistant-2026-guide.md)

### Inferences
- Most promising architecture: STT and TTS on the Mac mini or homelab as Wyoming services → HA Assist pipeline →
  conversation agent = the llama.cpp integration pointed at Hermes's `/v1` API server over Tailscale or LAN. Then
  Voice PE, the phone app and Siri or Android all reach Hermes. The alternative is HA's Ollama agent directly, which
  is simpler but doesn't use Hermes's memory or tools.
- With "prefer handling commands locally" behaviour, device commands never wait on the 9–12B model. Only open
  questions go to Hermes.
- Starter hardware: one Voice PE (~£56) per room. A ReSpeaker Lite kit is the DIY alternative, and Satellite1 suits
  better speakers.
- The GTX 970 (4 GB, Maxwell, shared with Jellyfin NVENC) can likely run Whisper small or medium via faster-whisper,
  but CTranslate2's Maxwell support isn't verified (see Gaps). Piper and Kokoro run fine on the i5-9400F CPU, so
  running TTS on the homelab CPU leaves the Mac mini's RAM for the LLM.

### Gaps
- No 2026 HA Voice Chapter post (12+) was found. The category page stops at Oct 2025, so any 2026 voice features
  (beyond llama.cpp 2026.8 and Android wake word 2026.3) are unverified.
- Not confirmed: whether HA's llama.cpp integration works with Hermes's API server in practice (tool-call format,
  streaming, timeouts on long agent turns).
- No source found for a Wyoming bridge to Speaches or Kokoro (wyoming-openai-style projects exist but were not
  verified) or for an MLX-backed Wyoming Whisper on macOS.
- Not verified: whether current faster-whisper/CTranslate2 CUDA wheels still support compute capability 5.2 (GTX 970).
- Official Voice PE MSRP in GBP was not seen on the official page.

## 2. Phone access (iPhone and Android, at home and away)

### Takeaway
Four realistic routes: (a) the HA companion app's Assist, which reaches Hermes if Hermes is HA's conversation agent;
(b) Hermes's native Telegram or Discord voice notes and Discord voice channels, using local faster-whisper STT;
(c) Open WebUI (PWA) on Hermes's API server, with voice calls needing HTTPS (tailscale cert/serve); (d) Apple
Shortcuts or Tasker calling the API over Tailscale. Android can make HA the default assistant with on-device wake
word (2026.3, battery cost). iPhone can't replace Siri, but the Action button or "Hey Siri, Assist" works.

### Cited Findings
- iOS: Assist runs in the companion app on iPhone, iPad and Mac, and can be started from the Action button or a
  lock-screen widget. It cannot replace Siri on the power-button long press (Apple restriction); Back Tap is an
  alternative. Siri shortcut: "Hey Siri, Assist". — [HA Assist on Apple](https://www.home-assistant.io/voice_control/apple); [HA blog iOS 2024.5 (older)](https://home-assistant.io/blog/2024/05/22/companion-app-for-ios-20245-assist); [peyanski](https://peyanski.com/assist-on-apple-devices-control-home-assistant-with-siri)
- Android: Home Assistant can be set as the default digital assistant (system gesture, lock screen). Assist widget.
  — [HA Assist on Android](https://www.home-assistant.io/docs/assist/android)
- Android on-device wake word (microWakeWord): experimental, HA 2026.3 / companion 2026.2.3+. Works locked or in
  the background. One report says battery use went from ~1% to ~15%, because Google doesn't expose the low-power
  DSP to third-party apps. The green mic dot stays on. — [HA Android docs](https://home-assistant.io/voice_control/android/); [HA wake word approach](https://www.home-assistant.io/voice_control/about_wake_word); [peyanski (third-party)](https://peyanski.com/google-open-android-wake-words-home-assistant/)
- Hermes voice (official docs): STT `stt.provider: local` (faster-whisper; tiny→large-v3/turbo; no key) or cloud
  (groq, openai, mistral, xai, elevenlabs, deepinfra). Local faster-whisper is excluded on Intel macOS and
  Windows ARM64 (Apple Silicon is fine). TTS `tts.provider`: edge (default, free, Microsoft cloud), openai (has
  `tts.openai.base_url`, so it can point at a local Kokoro/Speaches server), neutts, kittentts, piper (local) and
  others. TTS streams sentence by sentence. — [Hermes voice mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode)
- Hermes on Discord: voice replies as native voice bubbles (`/voice on|tts|off`). Voice channels via
  `/voice join|channel|leave|status` with transcripts in text as `[Voice] @user:`. Needs `discord.py[voice]` + Opus,
  Connect/Speak permissions and allowed users or roles. — [Hermes voice mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode); [fast.io (third-party)](https://www.fast.io/resources/hermes-agent-discord-bot/)
- Hermes on Telegram: voice notes are transcribed, and replies come back as Opus voice bubbles (ffmpeg needed for
  Edge MP3). `TELEGRAM_ALLOWED_USERS` is required, otherwise everyone is denied. `stt.enabled: false` passes the raw
  file path instead. — [Hermes Telegram docs](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/telegram)
- Turn detection in voice channels: about 1.5 s of silence after at least 0.5 s of speech (third-party). — [fast.io](https://fast.io/resources/hermes-agent-voice-mode/)
- Open WebUI connects to Hermes's API server (port 8642, `/v1`, matching key). Voice Calls need a secure context:
  plain http works only on localhost. Tailscale HTTPS certs (`tailscale cert` or `tailscale serve`) are the
  documented fix. — [Open WebUI HTTPS](https://docs.openwebui.com/reference/https/); [Open WebUI Tailscale](https://docs.openwebui.com/reference/https/tailscale); [Open WebUI audio troubleshooting](https://docs.openwebui.com/troubleshooting/audio)
- Wyoming Android TTS (F-Droid) can expose a phone's TTS engines to HA as a Wyoming server (niche). — [F-Droid](https://f-droid.org/bo/packages/home.wyoming_android_tts.indigane/)

### Inferences
- Lowest effort, already in place: Discord voice notes and voice channels to Hermes with `stt.provider: local`
  (whisper small or turbo on the Mac mini) and a local TTS. This works on both phones over the internet, but audio
  passes through Discord's servers. Telegram is the same pattern; Signal is not documented for voice.
- Most private, best for "away": Tailscale on the phone, plus either the HA app's Assist (HA is reachable on the
  tailnet) or Open WebUI as a PWA on `https://<mac>.ts.net`. The homelab currently runs HTTP only, so voice in the
  browser needs `tailscale serve` HTTPS on that one service.
- Apple Shortcuts: "Dictate text" → "Get contents of URL" (POST to `http://<tailscale-ip>:8642/v1/chat/completions`
  with the bearer key) → "Speak text". On-device dictation and Siri voice avoid running STT/TTS on the server. Tasker
  can do the same on Android. This uses only the documented API endpoints; I found no published guide.
- Edge TTS (the Hermes default) is a Microsoft cloud service. Switch to piper or kittentts, or to openai with
  `base_url` aimed at local Kokoro, for privacy.

### Gaps
- No primary source for Apple Shortcuts calling the Hermes API, or for an HA companion "Assist" Siri intent on iOS 26.
- Whether Open WebUI's voice-call flow behaves well with Hermes's non-streaming or slow agent responses is untested.
- WhatsApp and Signal voice-note handling in Hermes is not documented on the voice page.

## 3. Latency and quality of local STT/TTS on the M2 16 GB alongside the LLM

### Takeaway
Whisper on Apple Silicon is fast enough for short commands (MLX about 2x faster than whisper.cpp). Kokoro or Piper
TTS is light. The real constraint is 16 GB unified memory shared with a 9–12B model, plus LLM generation time.
Streaming TTS brings time-to-first-audio down to about 0.5 s after the first LLM tokens. Total turn time is
dominated by the LLM, typically several seconds for an agent turn.

### Cited Findings
- Benchmark (Jan 2026): mlx-whisper about 13.1 s vs whisper.cpp about 26.7 s on the same long clip, so MLX is about
  2x faster; the chip isn't stated in the snippet. — [billmill.org](https://notes.billmill.org/dev_blog/2026/01/updated_my_mlx_whisper_vs._whisper.cpp_benchmark.html)
- On an M2 with GPU, a large-v3-turbo run took about 15.8 s total with a 2.1 s encoder (clip length unclear; older,
  2024). — [Medium/axinc](https://medium.com/axinc-ai/whisper-large-v3-turbo-high-accuracy-and-fast-speech-recognition-model-be2f6af77bdc)
- A VoiceMode guide says Core ML Whisper models give 2–3x faster transcription on M1–M4 and lists RAM by model size. — [VoiceMode whisper guide](https://glama.ai/mcp/servers/@mbailey/voicemode/blob/61135913f46bd6d8612aa7d401c5c051e87b84e1/docs/guides/whisper-setup.md)
- Streaming TTS: time to first speech about 0.5 s instead of more than 5 s. — [HA Voice Chapter 11](https://www.home-assistant.io/blog/2025/10/22/voice-chapter-11/)
- Faster-whisper base is about 150 MB (third-party). — [fast.io](https://fast.io/resources/hermes-agent-voice-mode/)
- Kokoro is 82M parameters and runs well on CPU. — [ariya.io](https://ariya.io/2026/03/local-cpu-friendly-high-quality-tts-text-to-speech-with-kokoro)
- Speaches unloads idle models, which helps with memory contention. — [speaches](https://github.com/speaches-ai/speaches)

### Inferences
- Memory budget: gemma4:12b Q4 is about 8–9 GB including KV cache, and qwen3.5:9b about 6–7 GB. Whisper turbo is
  about 1.5–2 GB in fp16 (small: about 0.5 GB). Kokoro is about 0.3–0.5 GB. With macOS overhead (about 3–4 GB),
  12b + turbo is tight on 16 GB; 9b + small/turbo fits. Option: run Kokoro or Piper (CPU) and even Whisper small
  (CPU, int8) on the homelab i5-9400F to keep the Mac for the LLM. These are estimates from typical model sizes;
  measure them.
- Short voice commands (2–5 s of audio) with Whisper small or turbo on M2 Metal or MLX should transcribe in under
  about 1 s (inferred from the benchmarks above; not measured on an M2 base).
- Quality: Kokoro is widely rated above Piper for naturalness. Piper has British English voices (en_GB) and is the
  HA-native option.

### Gaps
- No clean M2 (base, 16 GB) benchmark of Whisper turbo on a short utterance was found.
- No measured figures for simultaneous Ollama + Whisper on 16 GB (swap or eviction behaviour).

## 4. Push and proactive: announcements, ntfy, morning briefings

### Takeaway
HA satellites can speak unprompted (announcements, Ask Question, broadcast), so the assistant can deliver spoken
briefings through Voice PE. On the phone, the proactive channels are Discord or Telegram voice bubbles from Hermes,
ntfy, or HA companion notifications. An LLM-written briefing can be generated by an HA AI Task or by Hermes on a
schedule, then spoken via TTS.

### Cited Findings
- The Ask Question action announces a message on a satellite and matches the spoken reply (e.g. "close the open
  garage door?"). — [HA Voice Chapter 11](https://www.home-assistant.io/blog/2025/10/22/voice-chapter-11/)
- Broadcast was added in Chapter 9 (Feb 2025). — [Notebookcheck](https://www.notebookcheck.net/Home-Assistant-Voice-chapter-9-arrives-with-new-Speech-to-Phrase-tool.963260.0.html)
- AI Tasks let automations call an LLM to generate text or structured data on a schedule or trigger. — [HA blog Sep 2025](https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/)
- Hermes `/voice tts` makes it reply with voice to every message on Telegram or Discord, delivered as native voice
  bubbles. — [Hermes voice mode](https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode)
- HA can be an MCP server, so an external agent (Hermes) could trigger `assist_satellite` announce actions. — [HA blog Sep 2025](https://www.home-assistant.io/blog/2025/09/11/ai-in-home-assistant/)

### Inferences
- Morning briefing pattern: Hermes (or the homelab's existing fitness or dashboard jobs) writes the text, then HA
  automation `assist_satellite.announce` speaks it on Voice PE when motion is detected or at a set time. The same
  text goes to Discord as a voice bubble for when Dan is away. ntfy stays for urgent text alerts, as the repo already
  does.
- Hermes reaching HA via MCP or the REST API would let it announce on its own initiative. Exposure should be limited
  to announce and notify actions.

### Gaps
- No source fetched for the exact `assist_satellite.announce` / `start_conversation` docs (introduced around
  late 2024 / 2025; older). Verify the service names in the current HA docs.
- No source on ntfy spoken notifications (ntfy doesn't do TTS natively as far as was checked; unverified).

## Summary cost table (UK, Oct 2026, best available)
- Voice PE: about £56 each ([The Pi Hut](https://thepihut.com/products/home-assistant-voice-preview-edition)).
- ReSpeaker Lite + XIAO ESP32S3 kit: Pi Hut listing; the bare board is £27.30 ([The Pi Hut](https://thepihut.com/products/respeaker-lite-with-xiao-esp32s3)).
- Satellite1 dev kit: $79.99 (2025, no GBP) ([CNX](https://www.cnx-software.com/?p=135489)).
- Software (HA Assist, Wyoming, Piper, Kokoro, Speaches, Hermes voice, Open WebUI, Tailscale personal): free.
  Phone apps: free.
