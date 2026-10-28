#!/usr/bin/env python3
"""Cron router (every minute, user dan): send remote users' Seerr requests to the remote 720p pair.

Seerr can't pick a server per user, so remote users (SEERR_REMOTE_USERS, Jellyfin usernames) have no
auto-approve: their requests wait as pending. This moves each one to Radarr (Remote) / Sonarr (Remote)
with that server's profile and root folder (as set by scripts/seerr-setup.py), then approves it.
If anything goes wrong the request just stays pending; it never lands on the main pair.

Normal-priority ntfy (NTFY_ALERT_TOPIC) when:
  - the router errors (Seerr API, missing remote server, ...): at most once an hour while it persists,
    plus one message when it recovers;
  - a remote user's request has been pending for more than 15 minutes, or Seerr marked it failed
    (couldn't add it to the remote arr): once per request.
Does nothing while the seerr container isn't running (stopped on purpose). Logs to syslog
(journalctl -t seerr-route). Install: scripts/install-cron.sh

  scripts/seerr-route.py           # route + alert (what cron runs)
  scripts/seerr-route.py status    # remote users' open requests (read-only)
  scripts/seerr-route.py test      # send a test notification
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import syslog
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = "http://localhost:5055/api/v1"
NTFY = "http://localhost:8081"
REMOTE_SERVERS = {"movie": ("radarr", "radarr-remote"), "tv": ("sonarr", "sonarr-remote")}  # Seerr hostname
STALE = 15 * 60        # seconds pending before alerting
ERROR_REPEAT = 3600    # seconds between repeated error alerts
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "homelab"
PENDING, APPROVED, FAILED = 1, 2, 4  # Seerr MediaRequestStatus


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


ENV = env()
KEY = ENV.get("SEERR_API_KEY", "")
REMOTE_USERS = {u.strip().lower() for u in ENV.get("SEERR_REMOTE_USERS", "").split(",") if u.strip()}


def log(msg: str) -> None:
    syslog.syslog(msg)
    if sys.stdout.isatty():
        print(msg)


def notify(title: str, msg: str) -> None:
    """Normal-priority ntfy. The topic is a secret: read here, never printed."""
    topic = ENV.get("NTFY_ALERT_TOPIC")
    if not topic:
        log("NTFY_ALERT_TOPIC not set: no notification")
        return
    req = urllib.request.Request(f"{NTFY}/{topic}", data=msg.encode(), method="POST",
                                 headers={"Title": title, "Priority": "default", "Tags": "clapper"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except OSError:
        log("ntfy post failed")


class SeerrError(Exception):
    pass


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{URL}{path}", data=data, method=method,
                                 headers={"X-Api-Key": KEY, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise SeerrError(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:200]}") from None
    except OSError as e:
        raise SeerrError(f"{method} {path} -> {e}") from None


def seerr_running() -> bool:
    out = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", "seerr"],
                         capture_output=True, text=True)
    return out.stdout.strip() == "running"


def title(req: dict) -> str:
    media = req.get("media") or {}
    kind = "movie" if req["type"] == "movie" else "series"
    return f"{kind} tmdb {media.get('tmdbId')} (request {req['id']})"


def media_title(req: dict) -> str:
    media = req.get("media") or {}
    try:
        info = call("GET", f"/{req['type']}/{media['tmdbId']}")
        name = info.get("title") or info.get("name")
        year = (info.get("releaseDate") or info.get("firstAirDate") or "")[:4]
        return f"{name} ({year})" if year else name
    except (SeerrError, KeyError):
        return title(req)


def remote_requests(filters=("pending", "failed")) -> tuple[dict, list[dict]]:
    """Remote servers by media type, and remote users' requests (Seerr list filters)."""
    servers = {}
    for mtype, (kind, host) in REMOTE_SERVERS.items():
        s = next((s for s in call("GET", f"/settings/{kind}") if s["hostname"] == host), None)
        if not s:
            raise SeerrError(f"no {host} server in Seerr (run scripts/seerr-setup.py)")
        servers[mtype] = s
    users = {u["id"]: u for u in call("GET", "/user?take=500")["results"]
             if (u.get("jellyfinUsername") or u.get("username") or "").lower() in REMOTE_USERS}
    missing = REMOTE_USERS - {(u.get("jellyfinUsername") or u.get("username")).lower() for u in users.values()}
    if missing:
        raise SeerrError(f"SEERR_REMOTE_USERS not in Seerr: {', '.join(sorted(missing))} (run scripts/seerr-setup.py)")
    reqs = []
    for uid in users:
        for f in filters:
            reqs += call("GET", f"/request?take=500&requestedBy={uid}&filter={f}")["results"]
    return servers, reqs


def route(req: dict, server: dict) -> None:
    body = {"mediaType": req["type"], "serverId": server["id"], "profileId": server["activeProfileId"],
            "rootFolder": server["activeDirectory"], "tags": server.get("tags") or []}
    if req["type"] == "tv":
        body["seasons"] = [s["seasonNumber"] for s in req.get("seasons", [])]
    if (req.get("serverId"), req.get("profileId"), req.get("rootFolder")) != \
            (body["serverId"], body["profileId"], body["rootFolder"]):
        call("PUT", f"/request/{req['id']}", body)
    call("POST", f"/request/{req['id']}/approve")


def age(req: dict) -> float:
    return time.time() - datetime.fromisoformat(req["createdAt"].replace("Z", "+00:00")).timestamp()


def run() -> None:
    state_file = STATE / "seerr-route.json"
    state = json.loads(state_file.read_text()) if state_file.exists() else {}
    alerted = set(state.get("alerted", []))
    errors = []
    try:
        if not KEY:
            raise SeerrError("SEERR_API_KEY missing in .env")
        if not REMOTE_USERS:
            return
        servers, reqs = remote_requests()
        open_ids = set()
        for req in reqs:
            if req["status"] == PENDING:
                open_ids.add(req["id"])
                try:
                    route(req, servers[req["type"]])
                    log(f"routed {title(req)} by {req['requestedBy'].get('displayName')} "
                        f"to {servers[req['type']]['name']}")
                    continue
                except SeerrError as e:
                    errors.append(f"{title(req)}: {e}")
                if age(req) > STALE and req["id"] not in alerted:
                    name = media_title(req)
                    log(f"{title(req)} pending for {age(req) / 60:.0f} min")
                    notify("Seerr: request stuck",
                           f"{name}, requested by {req['requestedBy'].get('displayName')}, has been pending "
                           f"for {age(req) / 60:.0f} min: it couldn't be sent to the remote server. "
                           "Check: journalctl -t seerr-route")
                    alerted.add(req["id"])
            elif req["status"] == FAILED:
                open_ids.add(req["id"])
                if req["id"] not in alerted:
                    name = media_title(req)
                    log(f"{title(req)} failed in Seerr")
                    notify("Seerr: request failed",
                           f"{name}, requested by {req['requestedBy'].get('displayName')}, failed: Seerr couldn't "
                           "add it to the remote Radarr/Sonarr. Retry it in Seerr > Requests after checking "
                           "scripts/dc.sh media/seerr logs --tail 50")
                    alerted.add(req["id"])
        alerted &= open_ids  # forget requests that are done
    except SeerrError as e:
        errors.append(str(e))

    now = time.time()
    if errors:
        for err in errors:
            log(f"error: {err}")
        if now - state.get("last_error_alert", 0) > ERROR_REPEAT:
            notify("Seerr router error", "\n".join(errors[:5]) + "\nRemote users' requests stay pending until "
                   "this is fixed. Log: journalctl -t seerr-route")
            state["last_error_alert"] = now
        state["failing"] = True
    elif state.pop("failing", False):
        log("recovered")
        notify("Seerr router recovered", "Remote users' requests are being routed again.")
        state.pop("last_error_alert", None)
    state["alerted"] = sorted(alerted)
    state_file.write_text(json.dumps(state))


def status() -> None:
    servers, reqs = remote_requests(("all",))
    names = {PENDING: "pending", APPROVED: "approved", 3: "declined", FAILED: "failed", 5: "completed"}
    by_id = {(t, s["id"]): s["name"] for t, s in servers.items()}
    for t, s in servers.items():
        print(f"{t}: remote server {s['name']!r} id={s['id']} profile={s['activeProfileName']!r} "
              f"root={s['activeDirectory']}")
    for req in reqs:
        server = by_id.get((req["type"], req.get("serverId")), f"server {req.get('serverId')} (NOT remote)")
        print(f"{media_title(req)} by {req['requestedBy'].get('displayName')}: {names.get(req['status'])}, "
              f"{server}, {req.get('rootFolder')}, {age(req) / 60:.0f} min old")


if __name__ == "__main__":
    syslog.openlog("seerr-route")
    if sys.argv[1:] == ["test"]:
        notify("Seerr router test", "Test message: Seerr router notifications work.")
        log("test notification sent")
    elif sys.argv[1:] == ["status"]:
        status()
    else:
        STATE.mkdir(parents=True, exist_ok=True)
        with open(STATE / "seerr-route.lock", "w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                sys.exit(0)
            if seerr_running():
                run()
