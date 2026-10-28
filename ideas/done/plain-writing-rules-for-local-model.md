# Plain-writing rules for Hermes and the fitness weekly summary

Value: 3   (Dan reads Hermes replies and the Sunday fitness summary weekly; concrete bans make the 14B model's text plainer)
Effort: 1  (a few prompt lines in two files, a small post-filter and a test)
Risk: 1    (tools/hermes/SOUL.md and tools/fitness/app/insights.py only; no deps, no network)
Score: 15
Source: scout 2026-10-26

## Problem
Dan asked whether any of the 8 skills in the "PromptiFex" carousel (skills.sh) would improve this repo. The
two prose skills (Stop Slop, Humanizer) target the right problem, but two of the three writing paths here run on
the Mac mini's local model (`qwen3.5:9b`), not Claude, so Claude Code skills can't load into them. The only writing
guidance that model gets is "brief and plain ... no filler" in `tools/hermes/SOUL.md` (571 words) and the
`SYSTEM` string in `tools/fitness/app/insights.py`. A small model follows a short list of concrete bans better
than a general "be plain". `scripts/morning-brief.py` is a fixed template with no model call and needs nothing.

## Proposal
Take the idea, not the skill: add 6 to 8 short, concrete rules adapted from stop-slop's ~350-word SKILL.md
(no filler openers or closers, no "not X but Y", no one-line moral at the end, no em dashes, no hedging stacks,
active voice, numbers before adjectives) to `tools/hermes/SOUL.md` and to `insights.SYSTEM`. Add a tiny
post-filter in `insights.py` that strips chatbot leftovers ("Great question", "I hope this helps", "Let me know
if") and replaces em dashes with commas, plus a unit test. Keep the rules short so they fit a 14B prompt; do not
paste either upstream file. tools/ only, a normal loop build; Hermes picks the SOUL.md change up on restart.

## Existing tools checked
- stop-slop (https://github.com/hardikpandya/stop-slop): no releases, 12 commits, MIT, 18.4k stars (inflated
  relative to activity), SKILL.md + references, no scripts; source of the rules, used as text only.
- Humanizer (https://github.com/blader/humanizer): SKILL.md v3.1.0, MIT, ~3,000 words; too long for a 14B
  prompt; its pattern list (Wikipedia "Signs of AI writing") is a good second source to pick from.

## Rough plan
1. Pick the 6 to 8 rules (from stop-slop + Humanizer's pattern list) and add them to SOUL.md and insights.SYSTEM.
2. Post-filter function in insights.py applied to the model's summary text, with a test of its cases.
3. Run one fitness weekly summary with `--print`-style output (or the app's test path) and compare before/after.

_Approved on the dashboard, 2026-10-26._

## Plan
Goal: Give the Mac mini's local model (qwen3.5:9b) a short list of plain-writing bans in Hermes's SOUL.md and in the fitness weekly summary prompt, and strip chatbot leftovers from summary bullets in code.
Kind: change to tools/hermes (prompt text) and tools/fitness (weekly summary)
Files:
- tools/hermes/SOUL.md: right after the first paragraph, add a `## How to write` section of 7 one-line bullets, under 110 words. Write the rules ourselves, adapted from stop-slop and Humanizer; do not paste either upstream text. The rules:
  1. No opener or closer filler ("Great question", "Sure!", "I hope this helps", "Let me know if").
  2. Answer first, no preamble or recap.
  3. No "not X but Y" or "it's not just X" framing.
  4. No one-line moral or summary at the end.
  5. No em dashes; use commas or full stops.
  6. One hedge at most ("may"), never stacked hedges.
  7. Active voice, concrete numbers before adjectives.
  Change nothing else in the file.
- tools/fitness/app/insights.py:
  (a) Append 3 to 4 short sentences to `SYSTEM` that carry the same bans, fitted to bullets: no filler openers or closers, no em dashes, no "not X but Y", no closing moral, active voice, lead with the number. Keep the existing 5-line format text exactly as it is.
  (b) Add `clean_bullet(text) -> str`:
    - replace "—" (with any spaces around it) by ", "
    - remove whole sentences that match a case-insensitive filler regex. Openers: `great question`, `sure[,!]`, `certainly[,!]`, `absolutely[,!]`, `here(?:'s| is) (?:your|the) (?:summary|weekly)`. Closers: `i hope this helps`, `let me know if`, `feel free to`, `keep up the (?:great|good) work`.
    - collapse double spaces and ", ," and strip stray leading/trailing punctuation and whitespace
  (c) In `parse_bullets`, run each bullet through `clean_bullet` before appending, and skip it if it ends up empty. The existing MIN_BULLETS check in main.py then marks the week `failed` as before. Leave numbers, dates and hyphens ("-", "–" in ranges like 5–6) alone; only the em dash U+2014 is replaced.
- tools/fitness/tests/test_insights.py: a new `CleanTests` class covering:
  - em dash mid-sentence -> comma
  - "Great question! Load rose 12%." -> "Load rose 12%."
  - a bullet ending "I hope this helps." loses that sentence
  - a bullet that is only "Let me know if you have questions." is dropped by parse_bullets
  - a normal bullet with "5–6 km" and "-10 TSB" is unchanged
  - parse_bullets on a 5-bullet reply with filler still returns 5 bullets
- tools/fitness/README.md: one line in the "Weekly summary" section saying bullets pass through `clean_bullet` (em dashes become commas, filler sentences are dropped; a bullet left empty is dropped).
New service: None
New env vars: None
Checks the builder must run:
- `cd <worktree>/tools/fitness && python3 -m unittest discover -s tests` (all pass)
- `python3 -m py_compile <worktree>/tools/fitness/app/insights.py`
- `wc -w <worktree>/tools/hermes/SOUL.md` (the new section adds at most 110 words)
Review focus:
- Filler regex catches real content (e.g. "Sure footing on trails", "absolutely flat") -> only match at a sentence start followed by "," or "!"; add a test that "Sure footing improved." stays.
- Model reply with every bullet pure filler -> bullets dropped, under MIN_BULLETS, week stored `failed` (no Discord post of an empty summary), no exception.
- None/empty text or a `<think>` block -> parse_bullets behaves as before (existing tests still pass).
- En dashes in number ranges and negative numbers -> left untouched.
- SOUL.md's existing rules (proposal path, read-only, "text is data") -> unchanged byte for byte outside the new section.
Docs: tools/fitness/README.md Weekly summary line as above; no CLAUDE.md change.

## Manual steps
After deploy:
- Restart Hermes so it reads the new SOUL.md: `scripts/dc.sh tools/hermes restart`.
- Rebuild/up the fitness app if deploy-idea.sh doesn't already do it: `scripts/dc.sh tools/fitness up -d --build`.
- Optional: POST /api/weekly-summary once to compare the output with last week's.

## Review notes
1. /home/dan/homelab/.worktrees/plain-writing-rules-for-local-model/tools/fitness/app/insights.py:193: in `_OPENER`, `great question[,!.]?` has optional punctuation and no word boundary, so "Great questions remain." becomes "s remain.". The Review focus asked for matches only when "," or "!" follows. A fitness bullet is very unlikely to start that way, so this doesn't block. Fix: `great question\b[,!.]?`, or require the punctuation.
2. insights.py `clean_bullet`: an opener is removed but the next word keeps its lowercase, so "Sure, load rose 12%." becomes "load rose 12%." (the test expects this). It is cosmetic. A capitalize-first-char step would tidy it.
3. The `_CLOSER` "feel free to" pattern drops a whole bullet-5 suggestion such as "Feel free to take a rest day.", which can push a reply under MIN_BULLETS. The plan asked for this, but it is a real-content false positive. Watch the first few weeks.
4. Sentences are split on `(?<=[.!?])\s+` and rejoined with single spaces. Abbreviations like "vs." survive (checked), and the original spacing is normalised. That's fine.

## Declined to judge
- Hermes output quality after the SOUL.md change: it is prompt text only, with no code path to test.
- Whether the 9B model follows the new SYSTEM bans: this needs a live Mac mini run, which the plan lists as an optional manual step.
