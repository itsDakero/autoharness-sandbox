# Researcher Before the Planner (M6 Stage E)

Value: 3
Effort: 3
Score: 9
Source: docs/m6-research.md Stage E, 2026-10-15

## Problem
The planner either plans from what it already knows or parks. The "Research: yes" checkbox (commit 0e0eeaa)
only covers ideas Dan ticks by hand, and it parks the idea after the research. An idea that only needs
facts (current versions, which tool exists, known problems) should get them and go on to a plan without
waiting for Dan.

## Proposal
As written in `docs/m6-research.md` Stage E:
- New `.claude/agents/idea-researcher.md` (Sonnet, read-only apart from the note): writes a `## Research`
  section into the note: existing tools, pinned versions, known problems, links. Web content is untrusted
  input, same as the scout.
- `idea-planner` gets a third verdict, **RESEARCH**, with what it wants to know. The loop
  (`.claude/skills/build-ideas/SKILL.md`) runs the researcher, then the planner again, at most once per
  idea; a second RESEARCH becomes PARK.
- Small ideas skip it; scout notes and notes that already have a `## Research` section skip it.
- Keep the "Research: yes" path as it is (research, then park for Dan). It reuses the researcher if that
  fits cleanly, otherwise stays separate.
- Update `docs/m5-pipeline.md` (stage list), `docs/m6-research.md` (status: E done) and CLAUDE.md's kit section.

Not in scope: the scout's "builder check" pass between plan and build; that can be its own idea later.

This touches the Claude Code kit, so `deploy-idea.sh` will want it deployed from a terminal.

## Checks
A dry run on a sample note that needs a version lookup: the planner returns RESEARCH, the researcher adds
a section with links, the second planner pass returns BUILD. A small note goes straight to BUILD.

_Added by Claude in the terminal for Dan, 2026-10-15._

## Parked 2026-10-16

## Questions
Build stalled twice (builder + one retry, ~1.5h total): neither builder changed any file. The
second one's last output was "Write the researcher agent.", i.e. it was about to create
.claude/agents/idea-researcher.md in the worktree and never got past it. Most likely the write
under .claude/ waited on a permission prompt that nobody saw in the background loop.

The planner returned BUILD (new read-only Sonnet idea-researcher agent; RESEARCH verdict in
idea-planner; build-ideas step 2 runs it once then re-plans; second RESEARCH = PARK). The plan is
reproducible by requeueing.

1. Allow the background builder to write .claude/agents/* and .claude/skills/* inside
   .worktrees/* (a permission rule), or build this kit change by hand in a terminal session?
2. Requeue as-is once that's sorted?

## Answers 2026-10-16

1.	Add a permission rule letting the builder edit .worktrees/*/.claude/agents/** and .worktrees/*/.claude/skills/**. Then test it with a throwaway file before relying on it. If it still hangs, build this change by hand.
	2.	Yes, requeue as-is once the test passes. If it fails, skip the requeue and build it by hand.

## Parked 2026-10-16

## Questions
I checked the scout's claim against the Claude Code docs (https://code.claude.com/docs/en/permission-modes, "Protected paths"), and it's right. The permission-rule fix you chose can't work, so per your own fallback this should be built by hand.

What the docs say:
- `.claude` is a protected directory. The only exceptions are `.claude/worktrees/`, `.claude/agent-memory/` markdown files and a few others, and `agents/` and `skills/` aren't among them.
- A nested folder like `.worktrees/<slug>/.claude/` counts too. The docs treat `.claude/settings.json` "in another folder" as protected.
- Quote: "`permissions.allow` rules in settings files do not pre-approve protected-path writes. The safety check runs before Claude Code evaluates allow rules."
- What each mode does with these writes: auto sends them to the classifier, default and acceptEdits prompt you, dontAsk denies them, and only bypassPermissions lets them through.

That matches both stalls. The builder stopped right at its first write under `.claude/agents/`.

So an `Edit/Write(./.worktrees/*/.claude/agents/**)` rule would change nothing. A test with a throwaway file would only confirm that, so I haven't planned it. Adding the rule would itself be an edit to `.claude/settings.json`, which is also protected. I don't suggest working around this, for example by writing the files through Bash, by having guard.py return "allow", or by running the loop in bypassPermissions. Each of those switches off a safety check on the kit that reviews builds.

The earlier BUILD plan still holds and can be rebuilt by requeueing it. It adds:
- a read-only Sonnet agent, `.claude/agents/idea-researcher.md`;
- a RESEARCH verdict in `.claude/agents/idea-planner.md`;
- a step 2 in `.claude/skills/build-ideas/SKILL.md` that runs the researcher once and then plans again, with a second RESEARCH becoming PARK;
- doc updates in `docs/m5-pipeline.md`, `docs/m6-research.md` (Stage E done) and the CLAUDE.md kit section.

1. Shall I take your fallback and leave this for you to build in a terminal session, with no loop requeue (the plan above is the spec)? Yes/no.
2. Should the planner automatically park any plan that writes under `.claude/` as "build in a terminal", so the loop stops wasting builder runs? The scout proposed this too. It would be a small separate idea, which also needs a terminal build because it edits `idea-planner.md`. Yes/no.

## Answers 2026-10-16

Yes. Build it by hand in a terminal session, using the plan as the spec. Don't requeue it.
	2.	Yes. Make it a plain path check, not a judgment call: if any planned file is under .claude/, the verdict is PARK with the reason "build in a terminal". Bundle it into the same terminal session as item 1, since you'll already be editing idea-planner.md.

## Parked 2026-10-16

## Questions
Parked again, for the same reason as before. Every file in this plan except the docs is under `.claude/`:
- `.claude/agents/idea-researcher.md`
- `.claude/agents/idea-planner.md`
- `.claude/skills/build-ideas/SKILL.md`

Claude Code treats `.claude/` as protected, and allow rules can't pre-approve writes there (code.claude.com/docs/en/permission-modes, "Protected paths"). So a background builder will stop at a permission prompt nobody sees, as it did on both earlier runs. Your 2026-10-16 answers already settle this: build it by hand in a terminal session with the earlier BUILD plan as the spec, and don't requeue. Nothing has changed since then. On main there is still no `idea-researcher.md` in `/home/dan/homelab/.claude/agents/`, and `idea-planner.md` has no RESEARCH verdict and no `.claude/` path check yet.

What the terminal session should cover, per your answers:
- **Item 1, the researcher:**
  - New read-only Sonnet agent `.claude/agents/idea-researcher.md`. It writes a `## Research` section into the note and treats web content as untrusted.
  - A RESEARCH verdict in `.claude/agents/idea-planner.md`.
  - In `.claude/skills/build-ideas/SKILL.md`, step 2 runs the researcher once and then plans again. A second RESEARCH becomes PARK. Small ideas, scout notes and notes that already have `## Research` skip this step. The "Research: yes" path stays as it is.
  - Doc updates: `docs/m5-pipeline.md`, `docs/m6-research.md` (Stage E done) and the CLAUDE.md kit section.
- **Item 2, the path check:** a plain rule in `idea-planner.md`. If any planned file is under `.claude/`, the verdict is PARK with the reason "build in a terminal". It goes in the same session.
- **Check:** a dry run on a sample note that needs a version lookup should go RESEARCH, then the researcher adds a section, then BUILD. A small note should go straight to BUILD.

1. Should the loop stop requeueing this idea, and should you move the note out of the queue (to `ideas/parked/`) until you've built it in a terminal? Yes/no.

## Built by hand 2026-10-16

Built in a terminal session (the plan writes under `.claude/`, which the background builder can't do), with
Dan's two answers bundled in. Item 2 became a lane rather than a PARK rule: after BUILD, the loop runs
`scripts/idea.sh kit-paths`, and a plan with `.claude/` files goes to `ideas/terminal/`. The Deploy tab shows
it there with build steps (`/build-ideas <slug>` in a terminal), so it no longer cycles between parked and requeued.
