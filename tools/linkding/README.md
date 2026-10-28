# linkding

linkding (`sissbruecker/linkding`, pinned in `compose.yaml`) keeps bookmarks with tags and full-text search.
Admin tile: http://192.168.0.210:8097 (also http://linkding.lan).

## Where things live
- Bookmarks, users, favicons and its SQLite database: `/srv/homelab/linkding` (`/etc/linkding/data`). It is
  under APPDATA, so restic backs it up, and data survives a container recreate or upgrade.
- The container gets only `TZ`. No secrets in its env (the first user is created by hand, below).

## First start
1. `scripts/dc.sh tools/linkding up -d`.
2. Create the admin user (prompts for a password, so nothing lands in `.env` or shell history):
   `docker exec -it linkding python manage.py createsuperuser --username=dan --email=dan@homelab`
3. Log in, then Settings > Integrations for the browser extension and the REST API token.

## Health
The healthcheck and the Kuma monitor hit `/health` (unauthenticated JSON) on port 9090 inside / 8097 outside.
