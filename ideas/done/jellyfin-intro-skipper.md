# Intro Skipper plugin for Jellyfin (skip intro/credits button)

Value: 4   (the family watches TV weekly; a skip button on every episode)
Effort: 1  (an idempotent plugin install in jellyfin-setup.py plus one restart)
Risk: 2    (Jellyfin config/plugins only; /mnt/media stays :ro, no new container or port)
Score: 20
Source: scout 2026-10-16

## Problem
TV is the biggest library (/mnt/media/tv 473G, plus tv-720p for the remote pair). Jellyfin
12.2.20261005 shows a native skip button for media segments, but nothing here creates the segments, so
there is no skip intro or skip credits.

## Proposal
Extend `scripts/jellyfin-setup.py` to do the following, idempotently, through Jellyfin's
Repositories/Packages API:
- add the plugin repository `https://intro-skipper.org/manifest.json`
- install the stable 12.0/v12.0.5.0 (not the prerelease)
- turn off plugin auto-update so the version stays pinned like our images
- restart Jellyfin once.

The plugin uses the ffmpeg in the official image and keeps its analysis in Jellyfin's data
(`/srv/homelab/jellyfin`, backed up). It never writes to media files. Schedule the first analysis
overnight so the CPU-heavy first pass over 473G doesn't slow playback. No compose port or mount changes.

## Existing tools checked
- intro-skipper (https://github.com/intro-skipper/intro-skipper): 12.0/v12.0.5.0 stable, released
  2026-10-09; 12.0 prerelease 2026-10-15; 2.9k stars, GPL-3.0, Jellyfin plugin (no image). Targets
  Jellyfin 12.0+, so 12.2 is covered.
- Client caveat: Infuse users report no skip prompt
  (https://community.firecore.com/t/jellyfin-intro-skipper-infuse-no-prompt-to-skip/58898). Check which
  clients the family uses.
- Setup guide: https://www.jellywatch.app/blog/jellyfin-intro-skipper-setup-configuration-troubleshooting-2026

## Rough plan
1. Find the Jellyfin API calls for repository add, package install by version, and auto-update off. Add a
   `--plugins` step to jellyfin-setup.py that changes nothing when the plugin is already at the pinned
   version.
2. Restart Jellyfin through dc.sh (this needs Dan's approval) and confirm the plugin is loaded.
3. Set the analysis task to a night window and run it on one show first to check CPU and segment accuracy.
4. Test the skip button on the family's clients (web, TV app, phones). Write it up in a docs runbook and
   add the pin to the image-check notes.

_Approved on the dashboard, 2026-10-16._

## Plan
Goal: Jellyfin gets skip-intro/credits segments from the Intro Skipper plugin, pinned at 12.0.5.0. `scripts/jellyfin-setup.py plugins` installs it idempotently, and the analysis runs at night.
Kind: change to scripts/jellyfin-setup.py (no compose, port or mount change)
Files:
- scripts/jellyfin-setup.py: new `plugins` subcommand; `status` also prints the plugin line and the task triggers
- docs/m2-media.md: Stage D bullet for the plugin (the pin, how to run it, the restart, the night window, the client caveat)
- CLAUDE.md: scripts list, change `jellyfin-setup.py` (libraries + NVENC) to (libraries + NVENC; `plugins` = Intro Skipper)

Design (constants at the top of the script):
  REPO_NAME = "Intro Skipper", REPO_URL = "https://intro-skipper.org/manifest.json",
  PLUGIN_NAME = "Intro Skipper", PLUGIN_VERSION = "12.0.5.0" (stable 12.0/v12.0.5.0, 2026-10-09,
  https://github.com/intro-skipper/intro-skipper; not the 12.0 prerelease),
  NIGHT_TICKS = 2h as .NET ticks (72000000000), MAX_RUNTIME_TICKS = 4h (144000000000).
`plugins` runs these steps in order, and each step prints one line saying "present", "set" or "done":
1. Repository: GET /Repositories. If no entry has Url == REPO_URL, POST /Repositories with the
   existing list plus {"Name": REPO_NAME, "Url": REPO_URL, "Enabled": true}. Never drop or replace
   existing entries (the default Jellyfin repo stays).
2. Install: GET /Plugins.
   - The plugin is present at PLUGIN_VERSION: do nothing.
   - The plugin is present at another version: print a WARNING with both versions and change nothing.
   - The plugin is missing: GET /Packages, find the entry with name == PLUGIN_NAME, and check that
     PLUGIN_VERSION is in its versions. If it's not there, exit non-zero with a clear message. Then
     POST /Packages/Installed/{name}, with params assemblyGuid=<guid from the package>,
     version=PLUGIN_VERSION, repositoryUrl=REPO_URL. Take the guid from the API; don't hardcode it.
     Print "installed, restart needed: scripts/dc.sh media/jellyfin restart".
3. Pin: GET /ScheduledTasks and find the built-in plugin-update task (Key == "PluginUpdates").
   If it has triggers, POST /ScheduledTasks/{Id}/Triggers with []. This pins every plugin, the same way
   the images are pinned. If no task has that Key, print a WARNING and continue.
4. Night window: only when the plugin shows as loaded in GET /Plugins (Status "Active"). Take the
   tasks with Category == PLUGIN_NAME (match case-insensitively; if none match, also accept a Name
   containing "intro" or "credit"). Set each task's triggers to exactly
   [{"Type":"DailyTrigger","TimeOfDayTicks":NIGHT_TICKS,"MaxRuntimeTicks":MAX_RUNTIME_TICKS}].
   Skip the POST when they already match. If the plugin isn't loaded yet, print "restart Jellyfin,
   then run `plugins` again to set the night window".
No restart from the script, and no library refresh in `plugins`. Reuse the existing call()/KEY
helpers. The API key is never printed. Default setup() and `status` keep their current behaviour,
and `status` only adds read-only lines.
Argument handling: `[]` -> setup, `["status"]` -> status, `["plugins"]` -> plugins. Anything else
prints the usage and exits 2. Update the module docstring to match.

New service: None
New env vars: None (it uses the existing JELLYFIN_API_KEY)
Checks the builder must run:
- python3 -m py_compile /home/dan/homelab/.worktrees/jellyfin-intro-skipper/scripts/jellyfin-setup.py
- python3 /home/dan/homelab/.worktrees/jellyfin-intro-skipper/scripts/jellyfin-setup.py bogus (expect usage, exit 2)
- `status` against the live server (read-only GETs) still prints the libraries and encoding, plus the
  plugin and task lines. Do not run `plugins` or the default setup (they write).
Review focus:
- manifest unreachable or PLUGIN_VERSION missing from /Packages -> clear message, exit non-zero, no
  install call, repository list otherwise unchanged
- run twice -> second run makes no POSTs (repo present, plugin at the pinned version, triggers equal)
- plugin installed at a different version (e.g. a manual update) -> warning only, no reinstall or downgrade
- POST /Repositories -> sends the full existing list plus the new entry, so the default repo isn't lost
- plugin not loaded yet (before the restart) -> the trigger step is skipped with the restart hint, not a crash
Docs: m2-media.md Stage D: a new bullet "Intro Skipper plugin". It covers: pinned 12.0.5.0; plugin
auto-update task triggers cleared; analysis daily at 02:00, max 4h; data in
/srv/homelab/jellyfin/config (backed up); media stays :ro. It also says a Jellyfin major bump via
/update-stack must check plugin compatibility (targetAbi), and that Infuse shows no skip prompt
(web and the Jellyfin apps do). CLAUDE.md scripts-list wording as above. No port or layout change.

Notes: the note's "add the pin to the image-check notes" is left out because image-check.py only
tracks container images. The pin lives in the script constant and the doc. Nothing in the note asks
to break the rules.

## Manual steps
1. Deploy, then run `scripts/jellyfin-setup.py plugins` (repo + install + pin).
2. Run `scripts/dc.sh media/jellyfin restart` (approval prompt).
3. Run `scripts/jellyfin-setup.py plugins` again to set the night window. Then check
   `scripts/jellyfin-setup.py status` shows Intro Skipper 12.0.5.0 Active.
4. Optionally run the analysis by hand on one show first (Dashboard > Scheduled Tasks) and watch the CPU.
5. Check the skip button on the family's clients (web, TV app, phones; Infuse won't show it).

## Review notes
1. `scripts/idea.sh diff` makes it look as if this build reverts `scripts/deploy-idea.sh`, `docs/m5-pipeline.md` and the install-missing-cron-jobs notes. It doesn't. The worktree is based on 44a8e9e, and main has moved on since (78a7aa7). Against its own base the worktree only changes CLAUDE.md, docs/m2-media.md, the idea note and scripts/jellyfin-setup.py. Those files don't overlap with what main changed (`git diff --stat 44a8e9e main`), so the merge will be clean.
2. The manifest URL only works for clients that look like Jellyfin. https://intro-skipper.org/manifest.json picks where to redirect from the User-Agent: a browser or curl gets the GitHub org page (HTML), while `-A Jellyfin-Server/12.2.0` gets a jsDelivr manifest. I fetched that manifest. It lists "Intro Skipper", guid c83d86bb-a1e0-4c35-a113-e2101cf4ee6b, with 12.0.5.0 (targetAbi 12.1.0.0, 2026-10-09), so it works with the server's 12.2.0. The builder guessed the field names `name`, `guid` and `versions[].version`, and they match both the manifest and Jellyfin's PackageInfo DTO. The live `status` was not run by the builder or by me (it needs the API key), so Dan's `status` in manual step 3 is the first real test.
3. scripts/jellyfin-setup.py:80-81 (`plugin_info`) takes the first /Plugins entry named "Intro Skipper". After a manual update and before a restart, Jellyfin can list both the old version (Superceded) and the new one (Active or Restart). The script could then say the pinned version is present, or keep printing the restart hint. Picking the Active entry first, if there is one, would fix this.
4. Step 4 puts the same daily 02:00 trigger on every task in the plugin's category, as the plan says. Intro Skipper has several tasks: the combined analysis, separate intro/credit detection and probably a cache cleanup. Normally only the combined one is scheduled. All of them running at 02:00 could repeat the first, heavy pass. After the first `plugins` run with the plugin loaded, Dan should check `status` and clear the triggers on the extra tasks if they overlap.
5. The step 1 POST /Repositories happens before the /Packages check. If the version check fails, the new repository entry stays in Jellyfin's list. That matches the plan's step order and the review focus wording ("otherwise unchanged"), and nothing is installed.

## Declined to judge
- The image-check pin note: the plan leaves it out on purpose, because image-check.py only tracks container images.
- Clearing the triggers on PluginUpdates pins every plugin, not just Intro Skipper: the plan chose this.
- The night window uses the container's TZ (`TZ: ${TZ}` in media/jellyfin/compose.yaml): local 02:00 is what was meant.
- Whether Infuse or other clients show the skip button: this is the manual client check in step 5.
