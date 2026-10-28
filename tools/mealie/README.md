# mealie

Mealie (`ghcr.io/mealie-recipes/mealie`, pinned in `compose.yaml`) keeps recipes, meal plans and shopping
lists. Family tile: http://192.168.0.210:8094 (also http://mealie.lan).

## Where things live
- Recipes, images, users and its SQLite database: `/srv/homelab/mealie` (`/app/data`). It is under APPDATA, so
  restic backs it up, and data survives a container recreate or upgrade.
- The container gets only `TZ`, `BASE_URL` and `ALLOW_SIGNUP=false`. No secrets in its env.

## First start
1. `scripts/dc.sh tools/mealie up -d`, then open the UI and log in with Mealie's default admin
   (`changeme@example.com` / `MyPassword`). Change the email and password straight away: until then anyone on
   the LAN can log in as admin.
2. Invite family members from the admin settings (signup stays off).

## Health
The healthcheck and the Kuma monitor hit `/api/app/about` (unauthenticated JSON) on port 9000 inside / 8094 outside.
