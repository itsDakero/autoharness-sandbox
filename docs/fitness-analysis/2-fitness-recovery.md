# Fitness recovery: normal ranges, recovery score, sleep debt, illness warning (fitness analysis 2 of 5)

## Problem
Today compares last night with a 7-day median only. Athlytic, Oura and Whoop show a personal
"normal range" and a recovery score built from several signals. Phase 1's real problem was that Dan
felt ill while his numbers looked fine; an early warning from his own patterns needs these ranges.

## Proposal
- **Normal range bands** for HRV and resting HR: 60-day mean ± 1 SD. Plot the 7-day rolling average
  against the band on Trends. The Today tile chip says "in range", "below" or "above".
- **Own recovery score 0–100** (Whoop style), next to Garmin's readiness: HRV z-score, RHR z-score
  (inverted), sleep vs need. Check-in overrides: ill = capped at 33; sore legs / stressed / slept
  badly = −10 each. Show the parts, not only the total.
- **Sleep debt**: 7-day sum of (need − actual); need defaults to 8 h. **Sleep consistency**: SD of
  bedtime and wake time over 14 days (sleep start/end from the raw sleep JSON in the `raw` table).
- **Strain vs recovery**: daily chart of load (from note 1) vs recovery score; flag high load on a
  red recovery day.
- **Illness early warning**: flag when resting HR is ≥ 3 bpm above its band and HRV is below its band
  for 2 nights in a row, or one of those plus a "slept badly"/"stressed" check-in. Warn banner on
  Today: "your numbers look like the start of illness: consider an easy day".
- After 60 days of check-ins, show on Trends how often a flag came 1–3 days before an "ill" check-in.
- A small **Settings** page (new `settings` table): sleep need.

## Notes
- Needs note 1 (`fitness-load`) deployed first, for the strain vs recovery chart.

## Shared rules (all fitness analysis notes)
- Background and the full list of analyses: `docs/fitness-analysis-prompt.md`.
- Maths is stdlib only, in `tools/fitness/app/logic.py` or a new `app/analysis.py`. Each formula gets a
  unit test with a worked example. Thresholds live in one place as constants.
- Look: same as the 2026-10-17 redesign. Tiles, chips coloured with `--good`/`--warn`/`--bad`, chart cards.
  Charts are inline SVG, no CDN. Each new number gets a one-line "what this means".
- Schema: append migrations at the end of `MIGRATIONS` in `app/db.py`; never edit an old one.
- Bump the image tag in `tools/fitness/compose.yaml` (minor version).
- Not medical advice: keep the footer; word warnings as suggestions.
