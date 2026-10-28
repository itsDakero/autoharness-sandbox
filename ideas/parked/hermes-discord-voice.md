# Hermes voice on Discord, all local (speech-to-text and voice replies)

Value: 4   (talk to the assistant from the phone without new hardware or HTTPS)
Effort: 3  (check the image, local STT/TTS, memory placement)
Risk: 2    (re-enables a disabled toolset; audio still passes through Discord)
Score: 12
Source: claude 2026-10-25 (reports/Homelab autonomy and assistant gaps.md, roadmap #8)
Depends on: mac-mini-memory-plan (decides where Whisper runs). Park if that isn't built yet.
Research: yes

## Problem
Dan wants voice/phone access. Hermes Agent supports Discord voice messages and voice channels with local
faster-whisper and several TTS engines, but here `tts` is in `disabled_toolsets` (tools/hermes/config.yaml)
and nothing is configured. Its default TTS, Edge TTS, is a Microsoft cloud service.

## Proposal
- Check first (research): does `nousresearch/hermes-agent:v0.22.2` include the voice extras (faster-whisper,
  ffmpeg, Opus)? Which config keys turn on STT and TTS, and does voice need `tts` removed from
  `disabled_toolsets`? Does faster-whisper run on the i5-9400F CPU fast enough (small/base model)?
- Speech-to-text: local faster-whisper, in Hermes's container on the homelab CPU (not on the Mac mini,
  unless the memory plan says it fits).
- Text-to-speech: Piper or Kokoro on the homelab CPU (Piper inside Hermes if supported, else a small
  local TTS service on Hermes's own network, no published port). **Never Edge TTS or any cloud TTS.**
- Start with voice messages (send a voice note, get text + a voice reply). Voice channels are optional.
- SOUL.md: keep spoken replies short.
- Update `docs/m6-research.md` (Hermes section) with what's on and why.

## Notes
- If the image lacks the extras, park with the options (custom image layer vs. wait for upstream) for Dan.
- Hermes's file/network fence stays as is; no web or terminal tools.

## Parked 2026-10-25

## Research
Doable: yes, if the speech-to-text and text-to-speech engines run on the homelab CPU. Unconfirmed: whether voice replies on Discord also need `tts` removed from `disabled_toolsets`, and whether they are always on or switched on per chat. The v0.22.2 source doesn't say clearly.
Size: Effort 2-3. What drives it: whether the voice packages and model files come from a download at first use or are built into our own image layer.

Facts from v0.22.2 (source: github.com/NousResearch/hermes-agent at tag v0.22.2, files Dockerfile, pyproject.toml, cli-config.yaml.example, hermes_cli/config_defaults.py):
- Already in the image: ffmpeg/ffprobe, and `discord.py[voice]==2.7.1` (with PyNaCl, needed for Discord audio) through the `messaging` extra.
- Not in the image: `faster-whisper==1.2.1` (extras `voice`/`stt-whisper`) and `piper-tts==1.8.0` (extra `piper`). Since 2026-05-12 they install from PyPI at first use (`allow_lazy_installs: True` by default).
- Speech-to-text config: `stt.enabled: true` (the default), `stt.provider` autodetects when left unset, `stt.local.model: base` (choices tiny/base/small/medium/large-v3/turbo), `stt.language: "en"`, Silero VAD on. `stt.echo_transcripts: true` posts the transcript back in the channel.
- Text-to-speech config: the default is `tts.provider: "edge"`, which is cloud, so it must be set to `piper`. Local choices: piper, kittentts, neutts. `tts.piper.voice: en_US-lessac-medium` is downloaded on first use into `~/.hermes/cache/piper-voices/`, and `voices_dir` can point at a local copy. Discord audio upload limit is 10 MiB.
- Hermes's Voice Mode docs list "Auto Voice Reply" for Discord (spoken audio sent with the text) and voice channels. `voice.auto_tts: False` is the default.
- Homelab: i5-9400F (6 cores), 15 GB RAM with about 9 GB free. faster-whisper base/small with int8 on CPU uses well under 1 GB, and Piper uses about 100 MB. Hermes's `mem_limit: 3g` probably needs raising to 4g. Neither engine touches the Mac mini, so the memory plan doesn't really gate this.

Options:
1. Config only, packages downloaded at first use. In `tools/hermes/config.yaml`: `stt.provider: local`, `stt.local.model: base` (or small), `tts.provider: piper`, take `tts` out of `disabled_toolsets` if replies need it, and raise `mem_limit`. Effort 2. Catch: on the first voice message the container pulls packages from PyPI and Whisper and Piper model files from HuggingFace/GitHub at run time, and may again after an image bump. It is also unclear whether a package installed at first use survives a container recreate, because `/opt/hermes` is read-only.
2. Our own image layer: `tools/hermes/Dockerfile` `FROM nousresearch/hermes-agent:v0.22.2` installs the `voice` and `piper` extras at the pinned versions. Model and voice files are fetched once into `${APPDATA_PATH}/hermes/` and `voices_dir` points there, with the same config as option 1. Effort 3. Catch: one more build step on every Hermes upgrade (`image-check.py`, `update-stack`). In exchange nothing is downloaded at run time.
3. Speech-to-text only: voice note in, text reply out, and `tts` stays disabled. Effort 1-2, with the same choice between downloading at first use and an image layer. Catch: no spoken replies.

Recommended: option 2. It is pinned and works offline, and it keeps the Stage D rule of no surprise downloads at run time, at the cost of one build step.
Unknowns: whether "Auto Voice Reply" on Discord needs the `tts` toolset enabled or only `voice.auto_tts`, and whether it is a per-chat `/voice` switch. Only trying it on v0.22.2 will settle that. Speech-to-text speed on the i5-9400F for a 30 s note: I estimate a few seconds with base and about 10 s with small, but it hasn't been measured.

Sources: https://github.com/NousResearch/hermes-agent/blob/v0.22.2/pyproject.toml, https://github.com/NousResearch/hermes-agent/blob/v0.22.2/Dockerfile, https://github.com/NousResearch/hermes-agent/blob/v0.22.2/cli-config.yaml.example, https://github.com/NousResearch/hermes-agent/blob/v0.22.2/hermes_cli/config_defaults.py, https://hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode

## Questions
1. Which option: 1 (download at first use), 2 (own image layer, recommended) or 3 (speech-to-text only, no spoken replies)?
2. Can this go ahead before `mac-mini-memory-plan` is built? Both engines run on the homelab CPU, not the Mac mini.
3. Whisper size: `base` (faster) or `small` (more accurate, slower)? And should Hermes always reply with voice to a voice note, or only when you switch it on?
4. OK to raise Hermes's `mem_limit` from 3g to 4g, and to take `tts` out of `disabled_toolsets` if voice replies turn out to need it (with `tts.provider` pinned to `piper`)?
