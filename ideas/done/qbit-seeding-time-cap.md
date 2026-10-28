# Cap qBittorrent seeding time so the arr apps can always clean up

Value: 3   (stops download copies from piling up on the media disk when slow torrents never reach ratio 1.0)
Effort: 1  (a few PREFS keys in one script plus a doc line)
Risk: 2    (changes qBittorrent settings; deletion stays with the arr apps' existing Remove Completed)
Score: 15
Source: scout 2026-10-19

## Problem
The only share limit is ratio 1.0, then stop (`scripts/qbit-setup.py`, `max_ratio*` in PREFS). NordVPN has
no port forwarding, so seeding is slow (`docs/m2-media.md` already says so). Radarr/Sonarr only remove a
torrent once it is stopped and has reached its seed limit. On 2026-10-19 all 9 torrents were below 1.0:
the oldest was 12 days at 0.98, the next 9 days at 0.46, and 4 of 9 were paused or queued below the ratio.
A torrent that never reaches 1.0 keeps its download copy forever. Once the main pair upgrades the file,
that copy is space nothing else uses. `/mnt/media/downloads` grew from 174G (2026-10-16) to 204G.

## Proposal
Add a time limit next to the ratio in PREFS in `scripts/qbit-setup.py`:
`max_seeding_time_enabled` + `max_seeding_time` (e.g. 14 days) and `max_inactive_seeding_time_enabled` +
`max_inactive_seeding_time` (e.g. 3 days). Keep `max_ratio_act: 0` (stop), so qBittorrent never deletes
anything itself and the arr apps' "Remove Completed" stays the only remover (the script's comment explains
why). Radarr's `QBittorrent.cs` `HasReachedSeedLimit` honours the global MaxSeedingTime and
MaxInactiveSeedingTime, so a stopped torrent past the time limit counts as done.
Touches only the qBittorrent settings via its Web API and `docs/m2-media.md`. No `/mnt/media` access.

## Existing tools checked
- qBittorrent built-in share limits (running `linuxserver/qbittorrent:5.2.4_v2.0.15-ls479`): seeding-time
  and inactive-seeding-time limits exist; this is the fix.
- Radarr develop `QBittorrent.cs`
  (https://github.com/Radarr/Radarr/blob/develop/src/NzbDrone.Core/Download/Clients/QBittorrent/QBittorrent.cs):
  CanBeRemoved = RemoveCompleted && pausedUP/stoppedUP && HasReachedSeedLimit, with time limits included.
- Cleanuparr v2.10.12 (https://github.com/Cleanuparr/Cleanuparr), 2026-10-18: a whole service for stalled
  torrents; not needed for 9 torrents when a setting does it.

## Rough plan
1. Add the four keys to PREFS with a comment; check `apply` reads them back and reports drift.
2. Run `qbit-setup.py apply`; confirm in the Web UI that the limits show.
3. Update the share-limit line in `docs/m2-media.md` (ratio 1.0 or 14 days, or 3 days inactive, then stop).
4. Over the next days, confirm one arr app removes a stopped torrent that passed the time limit (the 12-day
   one is the first candidate).

_Approved on the dashboard, 2026-10-19._

## Plan
Goal: Add seeding-time limits next to the ratio-1.0 stop in qBittorrent, so torrents that never reach 1.0 still stop and the arr apps' "Remove Completed" can clean them up.
Kind: change to scripts/qbit-setup.py (qBittorrent share limits)
Files:
- scripts/qbit-setup.py: in PREFS, straight after `"max_ratio_act": 0,`, add
  `"max_seeding_time_enabled": True,`, `"max_seeding_time": 14 * 24 * 60,` (minutes, 14 days),
  `"max_inactive_seeding_time_enabled": True,`, `"max_inactive_seeding_time": 3 * 24 * 60,` (minutes, 3 days).
  Expand the existing comment above the share-limit block so it reads: stop at ratio 1.0, or after
  14 days seeding, or after 3 days with no upload, whichever comes first. The action stays stop (`max_ratio_act: 0`
  covers all three limits). Say why: NordVPN has no port forwarding, so slow torrents never reach 1.0, and
  Radarr/Sonarr's HasReachedSeedLimit counts the global time limits too. Keep the line saying the arr apps
  stay the only remover. Change nothing else: apply() already compares every PREFS key with the value it
  reads back and exits 1 on a mismatch, so the new keys get drift reporting with no code change.
  Update the module docstring's apply line: "share limits (ratio/time)".
- docs/m2-media.md: line 29, the share-limit bullet: "ratio 1.0, 14 days seeding or 3 days inactive
  → **stop**", then the existing text unchanged. Line 34 (NordVPN): add "hence the time limits".
New service: None
New env vars: None
Checks the builder must run:
- python3 -m py_compile scripts/qbit-setup.py
- python3 -c "import ast,sys; src=open('scripts/qbit-setup.py').read(); print('ok')" plus a grep showing the
  four new keys with integer minute values (20160 and 4320 once evaluated)
- Do NOT run `qbit-setup.py apply` from the worktree. It changes live settings, so it belongs to Dan at deploy.
Review focus:
- Units -> both values are in minutes (the Web API uses minutes, not seconds or days): 20160 and 4320.
- Read-back drift -> qBittorrent returns these as ints, and PREFS holds ints (no floats like 20160.0), so
  apply reports 4 more keys OK and doesn't give a false MISMATCH.
- Deletion -> `max_ratio_act` stays 0 (stop). No key may set remove or remove-with-files. qBittorrent
  itself never deletes.
- Hand-added torrents (no arr category) -> they now stop after 14 days or 3 days idle and stay put
  (no remover). The doc's "Torrents added by hand stay stopped" line still holds.
Docs: docs/m2-media.md share-limit bullet (line 29) and NordVPN line (line 34). No CLAUDE.md or port-table change.
Not in scope: torrents waiting in the queue (queuedUP) don't build up seeding time, so the time limits
won't reach them. If they pile up, a later idea could look at qBittorrent's `dont_count_slow_torrents`.

## Manual steps
After deploy: run `scripts/qbit-setup.py apply` (qbittorrent running). It should report all preferences OK.
Then check Web UI > Options > BitTorrent > Seeding Limits. Over the next days, check that Radarr/Sonarr
remove the 12-day 0.98 torrent once it has stopped.

## Review notes
1. I checked the drift claim by reading apply() in /home/dan/homelab/.worktrees/qbit-seeding-time-cap/scripts/qbit-setup.py (lines 138-148). It compares every PREFS key with what `app/preferences` sends back, prints MISMATCH for each one that differs and exits 1 if any do. The four new keys get the same check with no code change, as the plan said.
2. I checked the qBittorrent release-5.2.4 source (`src/webui/api/appcontroller.cpp`, lines 318-321 and 853-860). The four key names are exactly the ones used. The values are in minutes. With `*_enabled` True, setPreferences stores `max_seeding_time` / `max_inactive_seeding_time` as ints. Reading them back gives an int and a bool, and those equal the Python values `20160`, `4320` and `True`, so there is no false MISMATCH.
3. Deletion is safe. `max_ratio_act` stays 0 and no key sets remove or delete-files. Sonarr main `QBittorrent.cs` line 415 warns about short seeding times only when the action is Remove or DeleteFiles, so the arr apps won't complain about the 14-day limit. `HasReachedSeedingTimeLimit` and `HasReachedInactiveSeedingTimeLimit` (lines 655 and 719) use the global limits when a torrent has none of its own (-2), as the plan said.
4. The m2-media.md line 29 bullet is now longer than the lines around it (about 130 columns). This is cosmetic only.
5. Changes are uncommitted in the worktree (3 files, M). That is what I'd expect at this stage of the loop.

## Declined to judge
- Queued (queuedUP) torrents never building up seeding time: the plan lists it as not in scope.
- 3-day inactive limit stopping rare torrents early: it is in the plan on purpose, and the action is stop, not delete.
