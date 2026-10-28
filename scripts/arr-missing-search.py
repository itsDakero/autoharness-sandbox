#!/usr/bin/env python3
"""Cron (Sundays 02:30, user dan): re-search monitored, released titles that still have no file.

Radarr/Sonarr search once when a title is added, then only watch RSS. This asks all four apps (main +
remote pairs) for their missing items and starts a search for some of them: monitored, released, no
file, not in the queue, not searched in the last 7 days. At most 10 per app per run (movies for Radarr,
units for Sonarr), never-searched / oldest-searched first. Sonarr: 2+ missing episodes of one season
become one SeasonSearch, a single one an EpisodeSearch. Only reads, plus the search commands; never
changes monitoring, profiles or indexers.

Logs to syslog (journalctl -t arr-missing-search). Posts to Discord (scripts/discord.sh) only when
something was searched or an app failed. Install: scripts/install-cron.sh

  scripts/arr-missing-search.py               # search + Discord post (what cron runs)
  scripts/arr-missing-search.py --dry-run     # print the plan, start nothing, post nothing
  scripts/arr-missing-search.py [--dry-run] radarr sonarr-remote   # only these apps
"""
import json
import re
import subprocess
import sys
import syslog
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APPS = {"radarr": ("radarr", 7878), "sonarr": ("sonarr", 8989),
        "radarr-remote": ("radarr", 7879), "sonarr-remote": ("sonarr", 8990)}
CAP = 10
RECENT = timedelta(days=7)
PAGE = 1000
LABEL_MAX = 300
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def appdata() -> str:
    try:
        for line in (REPO / ".env").read_text().splitlines():
            m = re.match(r"\s*APPDATA_PATH=(.*)", line)
            if m and m[1].strip().strip("'\""):
                return m[1].strip().strip("'\"")
    except OSError:
        pass
    return "/srv/homelab"


class Api:
    def __init__(self, name: str, port: int, root: str):
        self.base = f"http://localhost:{port}/api/v3"
        cfg = (Path(root) / name / "config.xml").read_text()
        self._key = re.search(r"<ApiKey>([^<]+)</ApiKey>", cfg)[1]

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}/{path}", data=data, method=method,
                                     headers={"X-Api-Key": self._key, "Content-Type": "application/json"})
        short = path.split("?")[0]
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:200]
            raise RuntimeError(f"{method} {short} -> HTTP {e.code} {detail}") from None
        except OSError as e:
            raise RuntimeError(f"{method} {short} -> {e}") from None
        return json.loads(raw) if raw else None

    def pages(self, path: str, extra: str = ""):
        out, page = [], 1
        while True:
            d = self.call("GET", f"{path}?page={page}&pageSize={PAGE}{extra}")
            recs = d.get("records", [])
            out += recs
            if not recs or len(out) >= d.get("totalRecords", 0):
                return out
            page += 1


def parse(ts):
    if not ts:
        return None
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def stale(rec, now) -> bool:
    t = parse(rec.get("lastSearchTime"))
    return t is None or now - t > RECENT


def clip(labels: list) -> str:
    s = ", ".join(labels)
    return s if len(s) <= LABEL_MAX else s[:LABEL_MAX - 3] + "..."


def do_radarr(api: Api, dry: bool, now) -> str:
    queued = {q.get("movieId") for q in api.pages("queue")}
    recs = [r for r in api.pages("wanted/missing", "&monitored=true")
            if r.get("isAvailable") and r.get("monitored") and not r.get("hasFile")
            and r["id"] not in queued and stale(r, now)]
    recs.sort(key=lambda r: (parse(r.get("lastSearchTime")) or EPOCH, r.get("title", "")))
    take, left = recs[:CAP], max(0, len(recs) - CAP)
    if not take:
        return "nothing to search"
    if not dry:
        api.call("POST", "command", {"name": "MoviesSearch", "movieIds": [r["id"] for r in take]})
        time.sleep(2)
    labels = [r["title"] + " (" + str(r.get("year", "?")) + ")" for r in take]
    return f"searched {len(take)} ({clip(labels)}), {left} left for next week"


def do_sonarr(api: Api, dry: bool, now) -> str:
    queued = {q.get("episodeId") for q in api.pages("queue")}
    eps = [e for e in api.pages("wanted/missing", "&monitored=true&includeSeries=true")
           if e.get("monitored") and not e.get("hasFile") and e["id"] not in queued
           and parse(e.get("airDateUtc")) and parse(e["airDateUtc"]) <= now and stale(e, now)]
    groups: dict = {}
    for e in eps:
        groups.setdefault((e["seriesId"], e["seasonNumber"]), []).append(e)
    units = []
    for (sid, sn), g in groups.items():
        title = (g[0].get("series") or {}).get("title", f"series {sid}")
        key = (min(parse(e.get("lastSearchTime")) or EPOCH for e in g),
               min(parse(e["airDateUtc"]) for e in g))
        if len(g) >= 2:
            units.append((key, f"{title} S{sn:02d} ({len(g)} eps)",
                          {"name": "SeasonSearch", "seriesId": sid, "seasonNumber": sn}, None))
        else:
            units.append((key, f"{title} S{sn:02d}E{g[0]['episodeNumber']:02d}", None, g[0]["id"]))
    units.sort(key=lambda u: u[0])
    take, left = units[:CAP], max(0, len(units) - CAP)
    if not take:
        return "nothing to search"
    if not dry:
        for u in take:
            if u[2]:
                api.call("POST", "command", u[2])
                time.sleep(2)
        ids = [u[3] for u in take if u[3] is not None]
        if ids:
            api.call("POST", "command", {"name": "EpisodeSearch", "episodeIds": ids})
            time.sleep(2)
    return f"searched {len(take)} ({clip([u[1] for u in take])}), {left} left for next week"


def main() -> int:
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    dry = "--dry-run" in args
    names = [a for a in args if a != "--dry-run"] or list(APPS)
    bad = [n for n in names if n not in APPS]
    if bad:
        print(f"unknown app(s): {', '.join(bad)} (choose from {', '.join(APPS)})", file=sys.stderr)
        return 2
    root, now = appdata(), datetime.now(timezone.utc)
    lines, errors, searched = [], [], False
    for name in names:
        kind, port = APPS[name]
        try:
            res = (do_radarr if kind == "radarr" else do_sonarr)(Api(name, port, root), dry, now)
        except (RuntimeError, OSError, TypeError, KeyError, ValueError, AttributeError) as e:
            errors.append(f"{name}: {e}"[:400])
            continue
        searched = searched or res.startswith("searched")
        lines.append(f"{name}: {res}")
    lines += errors
    if dry:
        print("\n".join(lines))
        return 1 if errors else 0
    syslog.openlog("arr-missing-search")
    for ln in lines:
        syslog.syslog(ln)
    if sys.stdout.isatty():
        print("\n".join(lines))
    if searched or errors:
        subprocess.run([str(REPO / "scripts/discord.sh"), "Weekly missing search:\n" + "\n".join(lines)],
                       check=False)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
