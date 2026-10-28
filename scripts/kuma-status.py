#!/usr/bin/env python3
"""Read-only Uptime Kuma status from its SQLite DB (no login needed).

Usage: scripts/kuma-status.py [name-prefix] [--beats N]
Shows each monitor (name, url, active, interval), its attached notifications (names only,
never their config) and the last N heartbeats. Name matches <name> or <name>-*.
"""
import argparse
import os
import sqlite3
from datetime import UTC, datetime

STATUS = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}

p = argparse.ArgumentParser()
p.add_argument("name", nargs="?", default="")
p.add_argument("--beats", type=int, default=3)
args = p.parse_args()

db = os.path.join(os.environ.get("APPDATA_PATH", "/srv/homelab"), "uptime-kuma", "kuma.db")
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
rows = con.execute(
    "SELECT id, name, type, url, hostname, active, interval, docker_container FROM monitor"
    " WHERE ? = '' OR name = ? OR name LIKE ? || '-%' ORDER BY name",
    (args.name, args.name, args.name),
).fetchall()
if not rows:
    raise SystemExit(f"no Kuma monitor named {args.name!r}")
for mid, name, mtype, url, host, active, interval, docker_container in rows:
    notes = [n for (n,) in con.execute(
        "SELECT n.name FROM notification n JOIN monitor_notification mn ON mn.notification_id = n.id"
        " WHERE mn.monitor_id = ? ORDER BY n.name", (mid,))]
    target = url if mtype == "http" else (docker_container if mtype == "docker" else host or url)
    print(f"{name} [{mtype}] {target}  active={bool(active)} every {interval}s  "
          f"notifications={','.join(notes) or 'none'}")
    for status, msg, t in con.execute(
            "SELECT status, msg, time FROM heartbeat WHERE monitor_id = ? ORDER BY time DESC LIMIT ?",
            (mid, args.beats)):
        print(f"  {t}  {STATUS.get(status, status):<8} {msg or ''}"[:160])
print(f"(heartbeat times UTC; now {datetime.now(UTC):%H:%M:%S} UTC)")
