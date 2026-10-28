# Fitness weekly summary: a written "what's improving" each Sunday (fitness analysis 5 of 5)

## Problem
The numbers from notes 1–4 still need reading. Whoop and Oura write a short summary. Phase 1
planned the Mac mini's model for this.

## Proposal
- Sunday evening, build a small JSON of the week: load, form, ACWR, recovery, sleep debt, zones,
  efficiency, predictions, check-ins, illness flags.
- Send it to the Mac mini's model, the same way Hermes does (local model only, no paid API key).
  It writes 5 bullets: what improved, what slipped, what it means, one suggestion.
- Store it in a new `summaries` table. Show it on a new **Insights** page (newest first).
- Post it to Discord with `scripts/discord.sh`.
- The model only sees the numbers JSON: never raw Garmin JSON, tokens or check-in note text.

## Notes
- Needs notes 1–3 deployed (it summarises their numbers); works with whatever exists.
- If the Mac mini is down, skip the week and say so on Insights; no retry storm.

## Shared rules (all fitness analysis notes)
- Background and the full list of analyses: `docs/fitness-analysis-prompt.md`.
- Maths is stdlib only, in `tools/fitness/app/logic.py` or a new `app/analysis.py`. Each formula gets a
  unit test with a worked example. Thresholds live in one place as constants.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`, chart cards.
  Charts are inline SVG, no CDN. Each new number gets a one-line "what this means".
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Bump the image tag in `tools/fitness/compose.yaml` (minor version).
- Not medical advice: keep the footer; word warnings as suggestions.
