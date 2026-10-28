#!/usr/bin/env python3
"""Cron (daily 09:30, user dan): Discord alert when a Jellyfin library is missing, empty or not being scanned.

Read-only GETs against Jellyfin (JELLYFIN_API_KEY from .env, never printed). A problem is any of:
  - one of the four libraries from jellyfin-setup.py is gone, or its folder is not among its paths
  - a library holds no items (e.g. /mnt/media not mounted when Jellyfin started)
  - the "Scan Media Library" task (key RefreshLibrary) last ended Failed/Aborted, or not in MAX_SCAN_AGE_H hours
One Discord message per run, repeated daily until fixed; exit 1 after it (cron-run.sh --ok 0,1, no double alert).
Jellyfin unreachable: logged, exit 0 (its own Kuma monitor alerts). Missing key: exit 2 (Kuma alerts).

  scripts/jellyfin-library-check.py            # what cron runs
  scripts/jellyfin-library-check.py --dry-run  # print the problems, post nothing
Logs: journalctl -t jellyfin-library-check.
"""
import json
import re
import subprocess
import sys
import syslog
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = "http://localhost:8096"
LIBRARIES = [  # name, path; keep in sync with LIBRARIES in jellyfin-setup.py
    ("Movies", "/mnt/media/movies"),
    ("TV", "/mnt/media/tv"),
    ("Movies (Remote)", "/mnt/media/movies-720p"),
    ("TV (Remote)", "/mnt/media/tv-720p"),
]
SCAN_TASK = "RefreshLibrary"
MAX_SCAN_AGE_H = 36  # the scan runs every 12 h by default


def log(msg: str) -> None:
    syslog.openlog("jellyfin-library-check")
    syslog.syslog(msg)
    print(msg)


def env_key() -> str:
    try:
        for line in (REPO / ".env").read_text().splitlines():
            m = re.match(r"\s*JELLYFIN_API_KEY=(.*)", line)
            if m and m[1].strip().strip("'\""):
                return m[1].strip().strip("'\"")
    except OSError:
        pass
    return ""


def get(key: str, path: str, **params):
    url = f"{URL}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f'MediaBrowser Token="{key}"'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def problems(key: str) -> list[str]:
    out = []
    folders = {f.get("Name"): f for f in get(key, "/Library/VirtualFolders") or []}
    for name, path in LIBRARIES:
        f = folders.get(name)
        if not f:
            out.append(f"library {name!r} missing (scripts/jellyfin-setup.py re-adds it)")
            continue
        if path not in (f.get("Locations") or []):
            out.append(f"library {name!r} has no folder {path} (has {f.get('Locations')})")
        n = (get(key, "/Items", ParentId=f.get("ItemId", ""), Recursive="true", Limit=0) or {}).get("TotalRecordCount", 0)
        if not n:
            out.append(f"library {name!r} is empty")
    task = next((t for t in get(key, "/ScheduledTasks") or [] if t.get("Key") == SCAN_TASK), None)
    last = (task or {}).get("LastExecutionResult") or {}
    if not task:
        out.append("task 'Scan Media Library' not found")
    elif not last:
        out.append("library scan has never run")
    else:
        if last.get("Status") in ("Failed", "Aborted"):
            out.append(f"last library scan {last['Status']}: {(last.get('ErrorMessage') or '')[:150]}".rstrip(": "))
        end = datetime.fromisoformat(re.sub(r"(\.\d{6})\d*", r"\1", last.get("EndTimeUtc", "")).replace("Z", "+00:00"))
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        age_h = (datetime.now(timezone.utc) - end).total_seconds() / 3600
        if age_h > MAX_SCAN_AGE_H and task.get("State") != "Running":
            out.append(f"last library scan ended {age_h:.0f} h ago (limit {MAX_SCAN_AGE_H} h)")
    return out


def main() -> int:
    args = sys.argv[1:]
    if args not in ([], ["--dry-run"]):
        print("usage: jellyfin-library-check.py [--dry-run]", file=sys.stderr)
        return 2
    key = env_key()
    if not key:
        log("JELLYFIN_API_KEY missing in .env")
        return 2
    try:
        found = problems(key)
    except urllib.error.HTTPError as e:
        log(f"Jellyfin API -> HTTP {e.code}")
        return 2 if e.code in (401, 403) else 0
    except (urllib.error.URLError, OSError, ValueError) as e:
        log(f"Jellyfin unreachable or bad reply: {e}")
        return 0
    if not found:
        log(f"ok: {len(LIBRARIES)} libraries present, non-empty, scanned")
        return 0
    for p in found:
        log(p)
    if args:
        return 0
    msg = "Jellyfin library check:\n" + "\n".join(f"- {p}" for p in found) + \
        "\nCheck: scripts/jellyfin-setup.py status, scripts/dc.sh media/jellyfin logs --tail 50"
    r = subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], capture_output=True, text=True)
    log(f"{len(found)} problem(s), discord rc={r.returncode}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
