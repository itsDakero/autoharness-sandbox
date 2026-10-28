# Review focus and "Declined to judge" for the build loop (from superpowers)

Value: 3   (Dan: the reviewer checks failure modes the plan implied but never named, before a build ships)
Effort: 1  (prompt edits to two agent files and one loop step; no code)
Risk: 1    (touches only `.claude/agents/idea-planner.md`, `idea-reviewer.md`, `skills/build-ideas`)
Score: 15
Source: scout 2026-10-15

## Problem
The loop has built 5 ideas (Oct 14-15); all passed review and none needed a fix commit after merge, so this
is prevention, not a measured failure. The gap: idea-reviewer checks the build "against the plan". If the
plan doesn't mention an input (an API that is down, an empty response from the arr apps, two cron runs
overlapping, a full disk), nothing checks it. superpowers v6.4.1 added a fix for exactly this; its notes say
that in their evals every implementer shipped the same crash on an input the spec implied but never named.
Also, the reviewer's side notes (what it chose not to judge) are lost today instead of reaching the Deploy tab.

## Proposal
Adapt, by copying the ideas (MIT, with a one-line credit pinned to superpowers v7.0.0), not by installing
the plugin:
1. **idea-planner**: the plan gets a `Review focus:` line with up to 5 failure modes the idea implies but the
   plan doesn't test, each with the expected behaviour. Plus one "Proportion" self-check line (plan length
   vs the size of the idea, from writing-plans v6.4.2).
2. **idea-reviewer**: checks each Review-focus item; anything the plan doesn't mention is judged by "what Dan
   or the family would reasonably expect". It ends with a `## Declined to judge` list (item + why).
3. **build-ideas**: appends that list together with the reviewer's Notes to the idea note, so they show on
   the Deploy tab.
This is a change to the kit (`.claude/`). If the planner parks it as a kit change it must not make itself,
Dan applies it by hand from this note; no service, port or mount is involved.

## Existing tools checked
- obra/superpowers (https://github.com/obra/superpowers): v7.0.0, last release 2026-10-10, ~300k stars, MIT,
  353 open issues. Read: skills/writing-plans (Review Focus, "Proportion"), requesting-code-review/
  code-reviewer.md ("spec is a vision document", "Declined to judge"). Adopt these pieces only.
- Installing the plugin: skip. Its SessionStart hook injects using-superpowers into every session including
  the /loop orchestrator; brainstorming asks a human, subagent-driven-development commits and makes its own
  rulings (vs our PARK-for-Dan rules), finishing-a-development-branch offers merge (vs "never merge"), and
  plugin updates rewrite prompts unreviewed.

## Rough plan
1. idea-planner.md: add the `Review focus:` section to the plan format and the Proportion self-check.
2. idea-reviewer.md: add the Review-focus pass, the "reasonable expectation" rule and the `## Declined to judge` output.
3. build-ideas SKILL.md: after review, append Declined-to-judge + Notes to the idea note.
4. Credit line with the upstream v7.0.0 commit SHA; mention the change in `docs/m5-pipeline.md`.
5. Watch the next 3 builds: does Review focus catch anything, and is the reviewer's output still short?

_Approved on the dashboard, 2026-10-15._

## Plan
Goal: Plans name the failure modes an idea implies but doesn't spell out (Review focus). The reviewer checks them and lists what it chose not to judge, and both lists end up in the note shown on the Deploy tab.
Note: this is a kit change (`.claude/`), which the planner rules normally don't take from a note. Dan approved it from the scout's Proposed tab, it weakens no guard, permission or rule, and `.claude/` builds are terminal-only on the Deploy tab, so Dan reads the diff before anything goes live. Nothing is copied from the plugin itself, only the ideas; the plugin is not installed.
Kind: change to the build loop kit (.claude/agents, .claude/skills/build-ideas) + docs
Files:
- .claude/agents/idea-planner.md:
  a) Directly after the frontmatter's closing `---`, add the credit line
     `<!-- Review focus and Proportion adapted from obra/superpowers v7.0.0 (commit bb92a77), MIT:
     skills/writing-plans. -->`
  b) In the reply template, between the `Checks the builder must run:` line and the `Docs:` line, add:
     `Review focus: <up to 5 inputs or conditions the idea implies but the plan doesn't otherwise cover
       (an API down or slow, an empty or odd response, two runs overlapping, a full disk, a missing file),
       each as "<condition> → <expected behaviour>"; None for docs only>`
  c) After the line "Keep the plan as short as it can be while leaving the builder nothing to guess.", add:
     "Review focus: pick the failures Dan or the family would actually notice (a crash, a silent wrong
     result, alert spam, lost data). Each one is part of the plan: the builder handles it, the reviewer
     checks it.
     Proportion: before replying, compare the plan's length with the note's. If the plan is several times
     longer than the idea needs, it is turning into the code itself, so cut it back to decisions and names."
- .claude/agents/idea-reviewer.md:
  a) Add the same style of credit line after the frontmatter:
     `<!-- Review focus, "reasonable expectation" and Declined to judge adapted from obra/superpowers
     v7.0.0 (commit bb92a77), MIT: skills/requesting-code-review/code-reviewer.md. -->`
  b) Add check 7 after check 6:
     "7. **Review focus and reasonable expectation**: check each `Review focus:` item in the plan against
        the code (skip this if the plan has none). The plan is a vision, not a list of every input. Where it
        says nothing, judge by what Dan or the family would reasonably expect. The plan not mentioning
        something doesn't make it OK to break. A crash, silent wrong result, alert spam or data loss on such
        an input is a must-fix; smaller gaps go in Notes."
  c) In the reply shape, between `## Notes` and `## Summary`, add:
     ```
     ## Declined to judge
     <each behaviour you considered and set aside as outside the plan, one line each: "<behaviour>: <why>";
     at most 5; None if you set nothing aside>
     ```
- .claude/agents/idea-builder.md: under `## Rules`, after "Follow the plan and `CLAUDE.md`. ...", add one bullet:
  "- Handle each `Review focus:` item in the plan the way it says (an error message, a skip, a retry, a lock),
  not only the main path."
  This goes slightly beyond the three files the note lists, but it saves fix rounds caused by a builder
  that ignores the Review focus line.
- .claude/skills/build-ideas/SKILL.md:
  a) Step 6 (Passed review): before the `scripts/idea.sh commit` call, add: "First append the passing
     review's lists to the end of `<wt>/ideas/<slug>.md` (Edit), word for word, so they show on the Deploy
     tab:
     ```
     ## Review notes
     <the reviewer's ## Notes, or None>

     ## Declined to judge
     <the reviewer's ## Declined to judge, or None>
     ```
     Then commit:" (keep the existing commit heredoc as it is).
  b) In `## Never`, change "edit anything except the plan sections of the note in step 2" to "edit anything
     except the plan sections of the note in step 2 and the review sections in step 6".
- docs/m5-pipeline.md, Stage C "Per idea" list:
  item 2 (idea-planner): add "; the plan has a `Review focus:` line (up to 5 implied failure modes with the
  expected behaviour)".
  item 4 (idea-reviewer): add "; it also checks Review focus and what Dan would reasonably expect, and
  lists what it declined to judge".
  item 5 (commit): add "after appending the passing review's `## Review notes` and `## Declined to judge`
  to the note (Deploy tab: Full note)".
  Add a one-line credit at the end of that list: "Review focus / Declined to judge adapted from
  obra/superpowers v7.0.0 (bb92a77, MIT); the plugin itself is not installed."
New service: none
New env vars: None
Checks the builder must run:
- `git -C /home/dan/homelab/.worktrees/build-loop-review-focus diff --stat main`: only the five files
  above (plus the note) have changed.
- `head -6` of each changed agent file and SKILL.md: the frontmatter is unchanged and still the first
  thing in the file (credit comment after the closing `---`).
- `grep -n '^## \|Review focus\|Declined to judge' <each changed file>`: the reply template sections are in
  order (planner: Plan then Manual steps; reviewer: Must fix, Notes, Declined to judge, Summary).
- `printf '## Plan\nx\n\n## Manual steps\nstep\n\n## Review notes\nn\n' | sed -n '/^## Manual steps/,/^## /p' | sed '$!b;/^## /d'`
  prints only the Manual steps heading and "step" (same extraction as scripts/deploy-idea.sh:140).
Review focus:
- A plan with no `Review focus:` line (older or requeued notes) → the reviewer skips check 7 and doesn't
  FAIL for it.
- The reviewer returns no Notes or no Declined list → the orchestrator writes "None" under the heading,
  not an empty section.
- A failed review followed by fix rounds → only the final passing review's lists are appended, once.
  Parked builds get none.
- The note after appending → deploy-idea.sh's Manual steps extraction still stops before `## Review notes`.
- Each reviewer list stays capped (Notes ≤5, Declined ≤5), so the reviewer's output stays short.
Docs: docs/m5-pipeline.md Stage C list (above). No change to CLAUDE.md, the port table or docs/README.md.

## Manual steps
- This build changes `.claude/`, so it deploys from a terminal only: read the diff, then
  `scripts/deploy-idea.sh build-loop-review-focus`.
- Restart the `/loop /build-ideas` Claude session in tmux after the merge so the subagents load the new
  prompts.
- Watch the next 3 builds: does Review focus catch anything, and do the reviewer's output and the note's
  new sections stay short?
