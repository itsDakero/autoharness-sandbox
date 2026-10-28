#!/usr/bin/env python3
"""Seerr wiring, idempotent. SEERR_API_KEY from .env, arr API keys from their config.xml; never printed.

  scripts/seerr-setup.py           # libraries, Radarr/Sonarr servers, Jellyfin users, permissions
  scripts/seerr-setup.py status    # current settings (read-only)

Run after the first-run wizard (Jellyfin sign-in as dan). Main Radarr/Sonarr are the defaults; the
remote pair is added as non-default servers that scripts/seerr-route.py moves remote users' requests to.
Remote users (SEERR_REMOTE_USERS, Jellyfin usernames, comma-separated) get Request without
auto-approve, so their requests wait for the router; everyone else is auto-approved.
"""
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = "http://localhost:5055/api/v1"
LIBRARIES = {"Movies", "TV"}  # synced; the remote libraries stay off (one availability status per title)
# name: (kind, container port, host port, root folder, quality profile, default)
SERVERS = {
    "radarr":        ("radarr", 7878, 7878, "/mnt/media/movies",      "Up to 2160p", True),
    "sonarr":        ("sonarr", 8989, 8989, "/mnt/media/tv",          "Up to 2160p", True),
    "radarr-remote": ("radarr", 7878, 7879, "/mnt/media/movies-720p", "HD-720p",     False),
    "sonarr-remote": ("sonarr", 8989, 8990, "/mnt/media/tv-720p",     "HD-720p",     False),
}
LABEL = {"radarr": "Radarr", "sonarr": "Sonarr", "radarr-remote": "Radarr (Remote)", "sonarr-remote": "Sonarr (Remote)"}
# Seerr permission bits (server/lib/permissions.ts)
ADMIN, MANAGE_REQUESTS, REQUEST, AUTO_APPROVE = 2, 16, 32, 128
AUTO_APPROVE_MOVIE, AUTO_APPROVE_TV, REQUEST_ADVANCED = 256, 512, 8192
# Bits that would let a remote user's request skip the router (approved straight to the default server)
REMOTE_STRIP = ADMIN | MANAGE_REQUESTS | AUTO_APPROVE | AUTO_APPROVE_MOVIE | AUTO_APPROVE_TV | REQUEST_ADVANCED
DEFAULT_PERMISSIONS = REQUEST  # new sign-ins: requests wait for approval until set up here


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


ENV = env()
KEY = ENV.get("SEERR_API_KEY") or sys.exit("SEERR_API_KEY missing in .env")
REMOTE_USERS = {u.strip().lower() for u in ENV.get("SEERR_REMOTE_USERS", "").split(",") if u.strip()}
LAN_IP = ENV.get("LAN_IP", "192.168.0.210")


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method,
                                 headers={"X-Api-Key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")


def arr_key(name: str) -> str:
    cfg = (Path(ENV.get("APPDATA_PATH", "/srv/homelab")) / name / "config.xml").read_text()
    return re.search(r"<ApiKey>([^<]+)</ApiKey>", cfg)[1]


def username(u: dict) -> str:
    return (u.get("jellyfinUsername") or u.get("username") or "").lower()


def status() -> None:
    for lib in call("GET", "/settings/jellyfin/library"):
        print(f"library {lib['name']!r}: {'synced' if lib['enabled'] else 'off'}")
    for kind in ("radarr", "sonarr"):
        for s in call("GET", f"/settings/{kind}"):
            print(f"{kind} {s['name']!r} id={s['id']} {s['hostname']}:{s['port']} profile={s['activeProfileName']!r} "
                  f"root={s['activeDirectory']} default={s['isDefault']} 4k={s['is4k']}")
    print(f"default permissions: {call('GET', '/settings/main')['defaultPermissions']}")
    for u in call("GET", "/user?take=100")["results"]:
        p = u["permissions"]
        kind = "owner" if u["id"] == 1 else "remote" if username(u) in REMOTE_USERS else "main"
        print(f"user {username(u)!r} id={u['id']} {kind}: permissions={p} "
              f"auto-approve={bool(p & (ADMIN | AUTO_APPROVE))}")


def setup_libraries() -> None:
    call("POST", "/settings/jellyfin/library/sync")
    for lib in call("GET", "/settings/jellyfin/library"):
        want = lib["name"] in LIBRARIES
        if lib["enabled"] != want:
            call("PUT", f"/settings/jellyfin/library/{lib['id']}", {"enabled": want})
        print(f"library {lib['name']!r}: {'synced' if want else 'off'}")


def setup_servers() -> None:
    for name, (kind, port, host_port, root, profile, default) in SERVERS.items():
        conn = {"hostname": name, "port": port, "apiKey": arr_key(name), "useSsl": False, "baseUrl": ""}
        test = call("POST", f"/settings/{kind}/test", conn)
        prof = next((p for p in test["profiles"] if p["name"] == profile), None)
        if not prof:
            sys.exit(f"{name}: quality profile {profile!r} not found (run scripts/arr-setup.py)")
        if root not in {f["path"].rstrip("/") for f in test["rootFolders"]}:
            sys.exit(f"{name}: root folder {root} not found (run scripts/arr-setup.py)")
        body = {**conn, "name": LABEL[name], "activeProfileId": prof["id"], "activeProfileName": profile,
                "activeDirectory": root, "tags": [], "is4k": False, "isDefault": default,
                "externalUrl": f"http://{LAN_IP}:{host_port}", "syncEnabled": True, "preventSearch": False,
                "tagRequests": False, "overrideRule": []}
        if kind == "radarr":
            body["minimumAvailability"] = "released"
        else:
            body |= {"seriesType": "standard", "animeSeriesType": "anime", "activeAnimeProfileId": prof["id"],
                     "activeAnimeProfileName": profile, "activeAnimeDirectory": root, "animeTags": [],
                     "enableSeasonFolders": True, "monitorNewItems": "all"}
        existing = next((s for s in call("GET", f"/settings/{kind}") if s["hostname"] == name), None)
        if existing:
            body["overrideRule"] = existing.get("overrideRule") or []
            call("PUT", f"/settings/{kind}/{existing['id']}", body)
        else:
            call("POST", f"/settings/{kind}", body)
        print(f"{kind} {LABEL[name]!r}: {'updated' if existing else 'added'} ({profile}, {root}"
              f"{', default' if default else ''})")


def setup_users() -> None:
    call("POST", "/settings/main", {"defaultPermissions": DEFAULT_PERMISSIONS,
                                    "applicationUrl": f"http://{LAN_IP}:5055"})
    known = {u.get("jellyfinUserId") for u in call("GET", "/user?take=100")["results"]}
    new = [u for u in call("GET", "/settings/jellyfin/users") if u["id"] not in known
           and u["id"].replace("-", "") not in known]
    if new:
        call("POST", "/user/import-from-jellyfin", {"jellyfinUserIds": [u["id"] for u in new]})
        print("imported from Jellyfin: " + ", ".join(u["username"] for u in new))
    users = call("GET", "/user?take=100")["results"]
    missing = REMOTE_USERS - {username(u) for u in users}
    if missing:
        sys.exit(f"SEERR_REMOTE_USERS not found in Seerr/Jellyfin: {', '.join(sorted(missing))}")
    for u in users:
        if u["id"] == 1:  # owner: permissions can't be changed
            print(f"user {username(u)!r}: owner (admin, auto-approve)")
            continue
        p = u["permissions"]
        remote = username(u) in REMOTE_USERS
        want = (p & ~REMOTE_STRIP) | REQUEST if remote else p | REQUEST | AUTO_APPROVE
        if want != p:
            call("POST", f"/user/{u['id']}/settings/permissions", {"permissions": want})
        print(f"user {username(u)!r}: {'remote (requests routed by seerr-route.py)' if remote else 'auto-approve'}")


def setup() -> None:
    setup_libraries()
    setup_servers()
    setup_users()
    for job in ("jellyfin-full-scan", "radarr-scan", "sonarr-scan"):
        call("POST", f"/settings/jobs/{job}/run")
    print("scans started: jellyfin-full-scan, radarr-scan, sonarr-scan")


if __name__ == "__main__":
    status() if sys.argv[1:] == ["status"] else setup()
