#!/usr/bin/env python3
"""Cron (Sundays 10:00, user dan): READ-ONLY dry-run report of watched media that could be cleaned up.

Part A of the watched-media cleanup (B apply, C Seerr clear, D recycle bin come later). This script only
does HTTP GETs against Jellyfin, Seerr, Radarr and Sonarr (main + remote pairs); the one POST is the ntfy
message. It deletes, unmonitors and changes nothing.

Rules (constants at the top of the file; items are matched to Jellyfin by exact file path):
  - A movie or episode file is a candidate only if ALL hold:
    * it has a requester in Seerr (movie by tmdbId, series by tvdbId, else tmdbId). Titles with no
      requester are never candidates (counted, and listed in the stale section only);
    * every user in (requesters + anyone who started it: Played or a playback position) has Played;
    * the latest LastPlayedDate of those users + GRACE_DAYS (30) is in the past. Played without a date:
      not a candidate, counted as "watched, no date";
    * the series/movie has no "keep" tag in its arr app;
    * no Jellyfin user has favourited the episode, its season, its series or the movie;
    * episodes: not one of the KEEP_LATEST (3) most recent aired regular episodes (season > 0) of the series.
  - Candidates are sorted oldest due date first. The first CAP_EPISODES (20) episodes and CAP_MOVIES (5)
    movies, across all four apps, are "would delete this run"; the rest are "over cap".
  - If the media disk is under FULL_PCT (85) % full, the report says nothing would be deleted; candidates
    are still listed for information.
  - Stale list (for Dan's approval, never deleted): titles with a file added 90+ days ago (STALE_DAYS) that
    no user played in the last 90 days, tagged "no requester" or "requested by <names>".

  scripts/storage-cleanup.py report           # write report file, ntfy, syslog (what cron runs)
  scripts/storage-cleanup.py report --print   # only print the report: no file, no ntfy
  scripts/storage-cleanup.py -h

Exit code 1 if any app or service failed (listed under errors). Logs: journalctl -t storage-cleanup.
"""
import json
import re
import shutil
import sys
import syslog
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GRACE_DAYS = 30
KEEP_LATEST = 3
FULL_PCT = 85
CAP_EPISODES = 20
CAP_MOVIES = 5
STALE_DAYS = 90
PROTECT_TAG = "keep"
APPS = {"radarr": ("radarr", 7878), "sonarr": ("sonarr", 8989),
        "radarr-remote": ("radarr", 7879), "sonarr-remote": ("sonarr", 8990)}
JELLYFIN = "http://localhost:8096"
SEERR = "http://localhost:5055/api/v1"
NTFY = "http://localhost:8081"
NTFY_MAX = 3500


def env() -> dict:
    out = {}
    try:
        for line in (REPO / ".env").read_text().splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if m:
                out[m[1]] = m[2].strip().strip("'\"")
    except OSError:
        pass
    return out


ENV = env()
APPDATA = ENV.get("APPDATA_PATH") or "/srv/homelab"
MEDIA = ENV.get("MEDIA_PATH") or "/mnt/media"


def http_get(url: str, headers: dict):
    req = urllib.request.Request(url, method="GET", headers=headers)
    short = url.split("?")[0]
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {short} -> HTTP {e.code}") from None
    except OSError as e:
        raise RuntimeError(f"GET {short} -> {e}") from None
    return json.loads(raw) if raw else None


class Api:
    """Radarr/Sonarr v3 API, GET only. The key comes from the app's config.xml and is never printed."""

    def __init__(self, name: str, port: int, root: str):
        self.base = f"http://localhost:{port}/api/v3"
        cfg = (Path(root) / name / "config.xml").read_text()
        self._key = re.search(r"<ApiKey>([^<]+)</ApiKey>", cfg)[1]

    def get(self, path: str):
        return http_get(f"{self.base}/{path}", {"X-Api-Key": self._key})


def parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def day(d) -> str:
    return d.strftime("%Y-%m-%d") if d else "?"


def jf_get(path: str):
    key = ENV.get("JELLYFIN_API_KEY", "")
    return http_get(f"{JELLYFIN}{path}", {"Authorization": f'MediaBrowser Token="{key}"'})


def load_jellyfin():
    """Returns (pmap: path -> {series, season, users: {user: (played, last, ticks, fav)}}, favs, users)."""
    pmap: dict = {}
    favs: set = set()
    users = jf_get("/Users")
    q = "Recursive=true&IncludeItemTypes=Movie,Episode&Fields=Path&EnableUserData=true"
    fq = "Recursive=true&IncludeItemTypes=Series,Season&Filters=IsFavorite"
    for u in users:
        name = u["Name"].lower()
        for it in jf_get(f"/Users/{u['Id']}/Items?{q}").get("Items", []):
            p, ud = it.get("Path"), it.get("UserData") or {}
            if not p:
                continue
            ent = pmap.setdefault(p, {"series": it.get("SeriesId"), "season": it.get("SeasonId"),
                                      "users": {}})
            ent["users"][name] = (bool(ud.get("Played")), parse(ud.get("LastPlayedDate")),
                                  ud.get("PlaybackPositionTicks") or 0, bool(ud.get("IsFavorite")))
        for it in jf_get(f"/Users/{u['Id']}/Items?{fq}").get("Items", []):
            favs.add(it["Id"])
    return pmap, favs, [u["Name"].lower() for u in users]


def load_seerr():
    """Returns {(kind, id): set of requester names}; kind is movie, tv (tvdbId) or tvtmdb (tmdbId)."""
    key = ENV.get("SEERR_API_KEY", "")
    out: dict = {}
    skip = 0
    while True:
        d = http_get(f"{SEERR}/request?take=500&skip={skip}&filter=all", {"X-Api-Key": key})
        recs = (d or {}).get("results", [])
        for r in recs:
            by = r.get("requestedBy") or {}
            who = (by.get("jellyfinUsername") or by.get("username") or "").lower()
            m = r.get("media") or {}
            if not who:
                continue
            if m.get("mediaType") == "movie":
                keys = [("movie", m.get("tmdbId"))]
            else:
                keys = [("tv", m.get("tvdbId")), ("tvtmdb", m.get("tmdbId"))]
            for k in keys:
                if k[1]:
                    out.setdefault(k, set()).add(who)
        if len(recs) < 500:
            return out
        skip += 500


def judge(path, requesters, jf, favs):
    """Returns (status, last played, names). Status: norequester, unwatched, fav, nodate or ok."""
    if not requesters:
        return "norequester", None, None
    ent = jf.get(path)
    if not ent:
        return "unwatched", None, None
    users = ent["users"]
    if any(v[3] for v in users.values()) or ent["series"] in favs or ent["season"] in favs:
        return "fav", None, None
    part = set(requesters) | {n for n, v in users.items() if v[0] or v[2] > 0}
    last = None
    for n in part:
        v = users.get(n)
        if not v or not v[0]:
            return "unwatched", None, None
        if not v[1]:
            return "nodate", None, None
        last = v[1] if last is None or v[1] > last else last
    return "ok", last, sorted(part)


def scan_app(name, kind, port, jf, favs, seerr, now):
    """Returns (candidates, stats, stale lines, count of titles with no requester)."""
    api = Api(name, port, APPDATA)
    tags = {t["id"]: t["label"].lower() for t in api.get("tag")}
    cands, stale, stats, noreq = [], [], {"protected": 0, "nodate": 0}, 0
    cut = now - timedelta(days=STALE_DAYS)

    def protected(rec):
        return any(tags.get(t) == PROTECT_TAG for t in rec.get("tags", []))

    def stale_check(title, added, played, req):
        if added and added <= cut and not (played and played > cut):
            who = "requested by " + ", ".join(sorted(req)) if req else "no requester"
            stale.append(f"[{name}] {title} - added {day(added)}, {who}")

    if kind == "radarr":
        for m in api.get("movie"):
            if not m.get("hasFile") or not m.get("movieFile"):
                continue
            path, label = m["movieFile"].get("path"), f"{m['title']} ({m.get('year', '?')})"
            req = seerr.get(("movie", m.get("tmdbId")), set())
            noreq += not req
            ent = jf.get(path)
            played = max((v[1] for v in ent["users"].values() if v[1]), default=None) if ent else None
            stale_check(label, parse(m["movieFile"].get("dateAdded")), played, req)
            st, last, names = judge(path, req, jf, favs)
            stats["nodate"] += st == "nodate"
            if st == "fav" or (st == "ok" and protected(m)):
                stats["protected"] += 1
            elif st == "ok" and last + timedelta(days=GRACE_DAYS) <= now:
                due = last + timedelta(days=GRACE_DAYS)
                cands.append((due, "movie", f"[{name}] {label} - watched by {', '.join(names)} "
                              f"{day(last)}, due {day(due)}"))
    else:
        for s in api.get("series"):
            sid = s["id"]
            eps = api.get(f"episode?seriesId={sid}")
            files = {f["id"]: f for f in api.get(f"episodefile?seriesId={sid}")}
            req = seerr.get(("tv", s.get("tvdbId"))) or seerr.get(("tvtmdb", s.get("tmdbId"))) or set()
            aired = sorted((e for e in eps if e.get("seasonNumber", 0) > 0 and parse(e.get("airDateUtc"))
                            and parse(e["airDateUtc"]) <= now),
                           key=lambda e: (e["airDateUtc"], e["seasonNumber"], e["episodeNumber"]))
            latest = {e["id"] for e in aired[-KEEP_LATEST:]}
            prot = protected(s)
            noreq += not req
            added, played = [], []
            for e in eps:
                f = files.get(e.get("episodeFileId")) if e.get("hasFile") else None
                if not f:
                    continue
                added.append(parse(f.get("dateAdded")))
                ent = jf.get(f["path"])
                if ent:
                    played += [v[1] for v in ent["users"].values() if v[1]]
                st, last, names = judge(f["path"], req, jf, favs)
                stats["nodate"] += st == "nodate"
                if st == "fav" or (st == "ok" and (prot or e["id"] in latest)):
                    stats["protected"] += 1
                elif st == "ok" and last + timedelta(days=GRACE_DAYS) <= now:
                    due = last + timedelta(days=GRACE_DAYS)
                    cands.append((due, "episode", f"[{name}] {s['title']} "
                                  f"S{e['seasonNumber']:02d}E{e['episodeNumber']:02d} - watched by "
                                  f"{', '.join(names)} {day(last)}, due {day(due)}"))
            added = [a for a in added if a]
            if added:
                stale_check(s["title"], min(added), max(played, default=None), req)
    return cands, stats, stale, noreq


def build_report(now):
    errors = []
    try:
        jf, favs, users = load_jellyfin()
    except (RuntimeError, KeyError, TypeError, ValueError, AttributeError) as e:
        return None, [f"jellyfin: {e}"]
    try:
        seerr = load_seerr()
    except (RuntimeError, KeyError, TypeError, ValueError, AttributeError) as e:
        errors.append(f"seerr: {e} (no requesters known, so nothing is a candidate)")
        seerr = {}
    cands, stale, prot, nodate, noreq = [], [], 0, 0, 0
    for name, (kind, port) in APPS.items():
        try:
            c, st, sl, nr = scan_app(name, kind, port, jf, favs, seerr, now)
        except (RuntimeError, OSError, TypeError, KeyError, ValueError, AttributeError) as e:
            errors.append(f"{name}: {e}"[:400])
            continue
        cands += c
        stale += sl
        prot += st["protected"]
        nodate += st["nodate"]
        noreq += nr
    cands.sort(key=lambda c: c[0])
    eps = [c for c in cands if c[1] == "episode"]
    movies = [c for c in cands if c[1] == "movie"]
    try:
        du = shutil.disk_usage(MEDIA)
        pct = round(du.used * 100 / du.total)
    except OSError as e:
        pct = None
        errors.append(f"disk: {e}")
    lines = []
    if pct is None:
        lines.append("Disk: unknown")
    elif pct >= FULL_PCT:
        lines.append(f"Disk {pct}% >= {FULL_PCT}%: the first {CAP_EPISODES} episodes and {CAP_MOVIES} "
                     "movies below would be deleted this run (dry run: nothing is)")
    else:
        lines.append(f"Disk {pct}% < {FULL_PCT}%: nothing would be deleted (candidates listed for "
                     "information)")
    lines.append(f"Jellyfin users: {', '.join(users)}. Grace {GRACE_DAYS} days, keep latest {KEEP_LATEST}.")
    lines += ["", f"Would delete: episodes ({min(len(eps), CAP_EPISODES)})"]
    lines += [c[2] for c in eps[:CAP_EPISODES]] or ["(none)"]
    lines += ["", f"Would delete: movies ({min(len(movies), CAP_MOVIES)})"]
    lines += [c[2] for c in movies[:CAP_MOVIES]] or ["(none)"]
    lines += ["", f"Over cap: {max(0, len(eps) - CAP_EPISODES)} episodes, "
              f"{max(0, len(movies) - CAP_MOVIES)} movies"]
    lines += ["", f"Protected, skipped (favourite, keep tag, latest {KEEP_LATEST}): {prot}",
              f"Watched, no date (not candidates): {nodate}",
              f"Titles with no requester (never auto-deleted): {noreq}"]
    lines += ["", f"Stale, for approval, never auto-deleted ({len(stale)}): no plays for {STALE_DAYS} days"]
    lines += sorted(stale) or ["(none)"]
    if errors:
        lines += ["", f"Errors ({len(errors)})"] + errors
    return "\n".join(lines), errors


def notify(title: str, msg: str) -> None:
    """Low-priority ntfy. The topic is a secret: read here, never printed."""
    topic = ENV.get("NTFY_ALERT_TOPIC")
    if not topic:
        syslog.syslog("NTFY_ALERT_TOPIC not set: no notification")
        return
    req = urllib.request.Request(f"{NTFY}/{topic}", data=msg.encode(), method="POST",
                                 headers={"Title": title, "Priority": "low", "Tags": "broom"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except OSError:
        syslog.syslog("ntfy post failed")


def main() -> int:
    args = sys.argv[1:]
    if not args or "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    if args[0] != "report" or any(a != "--print" for a in args[1:]):
        print("usage: storage-cleanup.py report [--print]", file=sys.stderr)
        return 2
    now = datetime.now(timezone.utc)
    text, errors = build_report(now)
    if text is None:
        text = "Errors (1)\n" + "\n".join(errors)
    if "--print" in args:
        print(text)
        return 1 if errors else 0
    syslog.openlog("storage-cleanup")
    out = Path(APPDATA) / "cleanup" / f"storage-report-{now.strftime('%Y-%m-%d')}.txt"
    try:
        out.write_text(text + "\n")
    except OSError as e:
        errors.append(f"report file: {e}")
        text += f"\nErrors: report file: {e}"
    syslog.syslog(text.splitlines()[0])
    syslog.syslog(f"errors: {len(errors)}")
    raw = text.encode()
    body = raw[:NTFY_MAX].decode(errors="ignore")
    notify("Storage cleanup report (dry run)", body + f"\n... full report: {out}")
    if sys.stdout.isatty():
        print(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
