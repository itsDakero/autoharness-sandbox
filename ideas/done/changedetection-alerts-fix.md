# Fix changedetection's failing Discord alerts and stop it logging the webhook

Value: 4   (Dan: deal/restock alerts actually arrive, and the main Discord webhook stops leaking into container logs)
Effort: 1  (one compose env line, one Apprise URL option, delete demo watches, README note)
Risk: 2    (touches changedetection's compose and its datastore settings; the webhook is a secret, rotation stays with Dan)
Score: 20
Source: scout 2026-10-23

## Problem
Every changedetection Discord notification in the last 72 h failed: 11 attempts, all for the
`https://news.ycombinator.com/` watch (looks like the demo watch a fresh install adds; it rechecks every
3 h, so about 8 failed posts a day). Discord answers 400 `{"content": ["Must be 2000 or fewer in length."]}`
(Apprise logs "Unsupported Parameters"): the diff is longer than Discord allows and Apprise's default
`overflow=upstream` sends it untrimmed. Any long price or restock diff would fail the same way, so the
deal watch shipped in 57e4e22 is unreliable for anything but small diffs.

Second: changedetection 0.60.9 logs at DEBUG by default (`LOGGER_LEVEL` is unset in
`tools/changedetection/compose.yaml`). Apprise's DEBUG lines print the full Discord webhook URL: 67 log
lines in 7 days contain it. Per `tools/changedetection/README.md` it is the same webhook as the repo's main
Discord feed. Those lines sit in the json-file logs and are readable through Dozzle. No other container
logs a webhook.

## Proposal
In `tools/changedetection/` (port 8087 unchanged, no new mounts):
- Add `LOGGER_LEVEL: WARNING` (or `INFO` if WARNING hides useful errors) to `environment:`.
- Append `overflow=truncate` to the global `discord://` notification URL (or cap the body with a Jinja
  `truncate` in the notification template), so long diffs are trimmed instead of rejected.
- Delete the HN demo watch, and the `changedetection.io/CHANGELOG.txt` watch if it is also a demo.
- Document the log level and the overflow option in `tools/changedetection/README.md`.
The builder must not print or copy the webhook URL. Settings that live in the datastore may need the UI or
changedetection's API (API key from the UI, not the env file); if neither is safe for the builder, write
the steps into the README for Dan.

Note for Dan (not the builder): rotate the Discord webhook once the old log files have rotated out
(10m x 3 cap) or after recreating the container, then update the env file and changedetection's URL.

## Existing tools checked
- changedetection.io (https://github.com/dgtlmoon/changedetection.io/releases): 0.60.9, released
  2026-10-12 (bumped Apprise 1.13.1 to 2.0.1); `LOGGER_LEVEL` TRACE..CRITICAL, DEBUG default (per
  https://www.mintlify.com/dgtlmoon/changedetection.io/installation/docker-compose, a third-party mirror).
- Apprise Discord overflow behaviour: same 400 text reported in
  https://lightrun.com/answers/caronc-apprise-discord-notifications-not-working; `overflow=truncate` is
  Apprise's standard URL option.

## Rough plan
1. Compose: add `LOGGER_LEVEL`; recreate; check `dc.sh tools/changedetection logs` no longer shows Apprise
   DEBUG lines (without echoing any URL).
2. Notification URL: add `overflow=truncate` (UI or API); remove demo watches; send a test notification
   with a long body and confirm it posts.
3. README: log level, overflow option, the "no demo watches" note, and the rotation reminder for Dan.

_Approved on the dashboard, 2026-10-23._

## Plan
Goal: Stop changedetection logging the Discord webhook (LOGGER_LEVEL), and write down the UI-only steps Dan takes to make long Discord alerts post (overflow=truncate) and to delete the demo watches.
Kind: change to tools/changedetection
Files:
- tools/changedetection/compose.yaml: under `environment:`, add `LOGGER_LEVEL: WARNING` after BASE_URL, with the comment `# DEBUG (the default) logs the Apprise webhook URL`. Nothing else changes (image 0.60.9, port 8087, volume, labels).
- tools/changedetection/README.md: edits listed under Docs.
New service: None
New env vars: None
Checks the builder must run:
- scripts/dc.sh /home/dan/homelab/.worktrees/changedetection-alerts-fix/tools/changedetection config -q
- git diff --stat shows only the two files above.
- The builder must not read /srv/homelab/changedetection (the datastore holds the webhook), must not call changedetection's API, and must not print any log line that contains the webhook. Datastore changes are manual steps for Dan (below); the global notification settings aren't in changedetection's API anyway.
Review focus:
- The webhook appears in a diff, README example or check output -> README uses only the placeholder `discord://<webhook_id>/<webhook_token>?overflow=truncate`; no real ids anywhere.
- WARNING hides the reason a send failed -> Apprise logs send failures at WARNING/ERROR, so they still show. The README says to stay at WARNING (INFO prints the notification URL on every send, so recreate the container after any INFO use). LOGGER_LEVEL=WARNING stops the webhook leak on successful sends only: a failed send logs Apprise's DEBUG capture (with the webhook) at CRITICAL, so the README tells Dan to re-run the grep after any failed alert and recreate the container (and rotate) when it isn't 0.
- A diff of more than 2000 characters -> with overflow=truncate it posts trimmed (README step includes a long test). It is not rejected with a 400.
- The ntfy URL for watches tagged urgent -> unchanged, since ntfy has no 2000-character limit. The README says the option goes on the Discord URL only.
Docs: tools/changedetection/README.md:
- "Where things live": the container gets `TZ`, `BASE_URL` and `LOGGER_LEVEL=WARNING`, plus the reason (DEBUG prints the webhook URL into logs that Dozzle can read).
- "Notifications": the Discord URL becomes `discord://<webhook_id>/<webhook_token>?overflow=truncate`, plus why (Discord rejects bodies over 2000 characters with a 400, and Apprise's default `overflow=upstream` doesn't trim).
- "First start": add step 3, "delete the demo watches a fresh install adds (news.ycombinator.com, changedetection.io CHANGELOG)". Keep only real shop watches.
- New "Webhook rotation" section: the webhook leaked into logs before LOGGER_LEVEL was set. Recreating the container drops its old json-file logs. Then rotate the webhook in Discord, update DISCORD_WEBHOOK_URL in the env file, and update changedetection's Discord URL (the same webhook as the main Discord feed, so scripts/discord.sh changes too).
- No CLAUDE.md or port-table change. The docs/README.md line stays as it is.

## Manual steps
1. Deploy (`scripts/deploy-idea.sh changedetection-alerts-fix`) recreates the container, which also drops the old logs that held the URL. Then check that this prints 0: `scripts/dc.sh tools/changedetection logs --since 1h | grep -c 'discord.com/api/webhooks'`
2. UI http://192.168.0.210:8087, Settings > Notifications: add `?overflow=truncate` to the end of the global discord:// URL (if the URL already has a `?`, use `&overflow=truncate`). Save, then use "Send test notification" with a long body (more than 2000 characters) and check that it shows up in Discord trimmed.
3. Delete the news.ycombinator.com watch, and the changedetection.io CHANGELOG watch if you didn't add it yourself.
4. Rotate the Discord webhook (Discord channel settings > Integrations), update DISCORD_WEBHOOK_URL in the env file, and paste the new discord:// URL (with `?overflow=truncate`) into changedetection. Test with `scripts/discord.sh test`.

## Review notes
1. tools/changedetection/README.md "Where things live": "Never set INFO or DEBUG" is followed by "If INFO is ever needed, recreate the container afterwards". The two lines slightly contradict each other. Something like "Avoid INFO/DEBUG; if you must use INFO..." would read better.
2. tools/changedetection/README.md "Webhook rotation": the order is muddled. The new caveat sits between the first grep and "Then rotate the webhook in Discord". Swapping them would make the one-off rotation steps read as one sequence, with the ongoing "after any failed alert" advice coming after.
3. The grep `discord.com/api/webhooks` misses a `discordapp.com` webhook URL. Apprise logs the discord.com form, so this is fine in practice.
4. The plan's Manual step 1 doesn't repeat the failed-send caveat. The README covers it, so it doesn't block.

## Declined to judge
- Whether Apprise 2.0.1 really logs send failures at WARNING/ERROR and the dumped capture at CRITICAL: the plan states this. Checking it would mean reading logs that contain the webhook.
- Whether `overflow=truncate` actually trims in practice: this is Dan's manual UI test (step 2), and the builder may not touch the datastore.
