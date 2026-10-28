# changedetection

changedetection.io (`dgtlmoon/changedetection.io`, pinned in `compose.yaml`) watches shop pages for price
drops and restocks. Admin only: http://192.168.0.210:8087 (also http://changedetection.lan).

## Where things live
- Watches, history and notification URLs: the UI and the datastore `/srv/homelab/changedetection`.
  It is under APPDATA, so restic backs it up, and watches survive a container recreate or upgrade.
- The container gets only `TZ`, `BASE_URL` and `LOGGER_LEVEL=WARNING`. No webhook or topic is in its env; paste
  them into the UI. The default level, DEBUG, makes Apprise print the webhook URL into the logs, which Dozzle
  can read. Stay at WARNING (or ERROR). Never set INFO or DEBUG: INFO prints the full notification URL (the
  webhook) on every send. If INFO is ever needed, recreate the container afterwards to drop those logs.
- WARNING stops the leak on successful sends only. A failed send still logs the webhook at CRITICAL, because
  changedetection dumps Apprise's DEBUG capture (incl. `Discord POST URL: ...`) and no LOGGER_LEVEL setting can
  hide that without also hiding the failure. After any failed alert, re-run the grep in "Webhook rotation";
  if it isn't 0, recreate the container (and rotate the webhook if needed).

## First start
1. Set the UI password first (Settings > General), before pasting any webhook URL. Until then the UI is open on the LAN.
2. Settings > Notifications: add the Discord URL as the global default. Leave "notify on filter not found"
   OFF, so a broken shop page shows an error in the UI instead of spamming Discord.
3. Delete the demo watches a fresh install adds (news.ycombinator.com, changedetection.io CHANGELOG). Keep
   only real shop watches.

## Add a price or restock watch
- Add the URL, choose the "Re-stock & Price detection" processor.
- The first check of a new watch does not alert; only a real price or stock change does.
- A shop that blocks the fetch (403/captcha) or a missing price element shows as an error on the watch.
- Keep the check interval at 3 h or more, and prune history in Settings. `disk-space-check.sh` alerts on the system disk.

## Notifications (Apprise)
- Discord (global default): `discord://<webhook_id>/<webhook_token>?overflow=truncate`, taken from
  DISCORD_WEBHOOK_URL. Discord rejects bodies over 2000 characters with a 400, and Apprise's default
  `overflow=upstream` doesn't trim them, so long diffs failed. The option goes on the Discord URL only.
  Test it: Settings > Notifications, "Send test notification" with a body over 2000 characters; it should
  arrive in Discord trimmed.
- ntfy, only on watches tagged `urgent`: `ntfy://192.168.0.210:8081/<NTFY_ALERT_TOPIC>`.

## Webhook rotation
The webhook leaked into the logs before `LOGGER_LEVEL` was set. Recreating the container drops its old json-file
logs; check with `scripts/dc.sh tools/changedetection logs --since 1h | grep -c 'discord.com/api/webhooks'`
(expect 0). That only proves no send failed in that hour: LOGGER_LEVEL=WARNING stops the leak on successful
sends only, and a failed send logs the webhook at CRITICAL. Re-run the grep after any failed alert and recreate
the container (and rotate) when it isn't 0. Then rotate the webhook in Discord, update DISCORD_WEBHOOK_URL in the env file, and paste the new
Discord URL (with `?overflow=truncate`) into changedetection. It is the same webhook as the main Discord feed,
so `scripts/discord.sh` changes too; check with `scripts/discord.sh test`.

## Browser fetcher
Not installed. Add one (sockpuppetbrowser) only with a pinned tag or digest, and only if LEGO.com fails with
the plain fetcher. Upstream ships it as `:latest` only.

## Related
`books-deals-aggregator` is parked: its books half is `tools/books` and its deals half is this service.
