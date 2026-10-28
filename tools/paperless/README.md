# paperless

Paperless-ngx (`ghcr.io/paperless-ngx/paperless-ngx`, pinned in `compose.yaml`) keeps scanned documents with
OCR and full-text search. Admin tile: http://192.168.0.210:8095 (also http://paperless.lan). Redis
(`paperless-redis`) is its task broker, on the project's own network only, with no published port.

## Where things live
- Database, search index and thumbnails: `/srv/homelab/paperless/data`; the documents themselves:
  `/srv/homelab/paperless/media`. Both under APPDATA, so restic backs them up.
- `/srv/homelab/paperless/consume`: drop files here and Paperless imports them (and deletes the copy).
- `/srv/homelab/paperless/export`: target for `document_exporter`.
- `/srv/homelab/paperless/redis`: Redis queue state only; safe to lose.
- The container gets `TZ`, `PUID`/`PGID` (as `USERMAP_UID`/`GID`), the Redis URL, OCR language, the CSRF
  origins and `PAPERLESS_SECRET_KEY` from `.env` (compose refuses to start without it).

## First start
1. Add the key to `.env`: `echo "PAPERLESS_SECRET_KEY=$(openssl rand -hex 32)" >> .env`.
2. `scripts/dc.sh tools/paperless up -d`, wait for healthy, then create the admin:
   `docker exec -it paperless python3 manage.py createsuperuser`. There is no default login.

## Health
The healthcheck and the Kuma monitor hit `/accounts/login/` (unauthenticated, 200) on port 8000 inside / 8095
outside. Redis has its own `redis-cli ping` healthcheck; Paperless waits for it.
