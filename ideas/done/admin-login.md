# Put /admin behind a login (or Tailscale-only)

Do this before the dashboard's Now playing and Downloads widgets go live.

- Today `/admin` is only hidden, not protected: anyone on the LAN or tailnet who opens it would see
  torrent names and who is watching what.
- Options: a login in front of `/admin` and the admin `/api/*` endpoints (e.g. Traefik forward auth or
  basic auth in the dashboard), or serve them only to tailnet clients (100.64.0.0/10).
- Family devices use the main page (`/`) only, so it must keep working with no login, and the family
  endpoints must stay open.
- Not a new web service: it changes the dashboard (and maybe Traefik), so plan it as a dashboard change,
  not via add-service.
