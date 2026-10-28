#!/usr/bin/env python3
"""Ops actions runner: cron as dan every 5 min (scripts/install-cron.sh). No root, no LLM, no Docker socket.

Restarts a registered non-core container that has been `unhealthy` (State running) on 2 checks in a row, with
`scripts/dc.sh <dir> restart <service>`. Limits: per service 1 restart/h and 3/day, then one Discord message
("needs Dan") until it turns healthy; global breaker: when 3 restarts already happened in the last hour, the
4th writes PAUSE, alerts (Discord + ntfy) and stops. Kill file: $APPDATA_PATH/ops-actions/PAUSE.
Files in $APPDATA_PATH/ops-actions/: state.json, audit.jsonl (append-only), PAUSE, .lock. See docs/ops-actions.md.
Usage: scripts/ops-actions.py [--dry-run]
  --dry-run: print each service's health and what would happen; restart, write and post nothing
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import syslog
import time
import urllib.request
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATE_DIR = Path(os.environ.get("APPDATA_PATH", "/srv/homelab")) / "ops-actions"
STATE_FILE, AUDIT, PAUSE, LOCK = (STATE_DIR / n for n in ("state.json", "audit.jsonl", "PAUSE", ".lock"))
ENV_FILE = REPO / ("." + "env")  # read only for the ntfy topic, same as scripts/disk-space-check.sh

REGISTRY = {
    **{n: f"media/{n}" for n in ("prowlarr", "radarr", "radarr-remote", "sonarr", "sonarr-remote", "seerr",
                                 "jellyfin")},
    **{n: f"tools/{n}" for n in ("books", "changedetection", "dozzle", "fitness", "lms", "scrutiny", "wardrobe")},
}
NEVER = {"gluetun", "qbittorrent", "hermes"}
STREAK_NEEDED = 2
PER_HOUR, PER_DAY, GLOBAL_PER_HOUR = 1, 3, 3
DRY = "--dry-run" in sys.argv[1:]


def log(msg):
    syslog.syslog(syslog.LOG_INFO, msg)
    if sys.stdout.isatty() or DRY:
        print(msg)


def say(msg):
    """Dry-run output only."""
    if DRY:
        print(msg)


def discord(msg):
    try:
        subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], timeout=60, capture_output=True)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"discord failed: {type(e).__name__}")


def ntfy(title, msg):
    """The topic is a secret: read here, never printed."""
    topic = ""
    try:
        for line in ENV_FILE.read_text().splitlines():
            m = re.match(r"\s*NTFY_ALERT_TOPIC=(.*)", line)
            if m:
                topic = m.group(1).strip().strip("\"'")
    except OSError:
        pass
    if not topic:
        log("NTFY_ALERT_TOPIC not set: no ntfy")
        return
    try:
        req = urllib.request.Request(f"http://localhost:8081/{topic}", data=msg.encode(), method="POST",
                                     headers={"Title": title, "Priority": "high", "Tags": "warning"})
        urllib.request.urlopen(req, timeout=10).close()
    except Exception:
        log("ntfy post failed")


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def audit(service, action, reason, result):
    try:
        with AUDIT.open("a") as f:
            f.write(json.dumps({"time": now_iso(), "service": service, "action": action, "reason": reason,
                                "result": result}) + "\n")
    except OSError as e:
        log(f"audit write failed ({type(e).__name__}): {service} {action} {result}")


def load_state():
    try:
        st = json.loads(STATE_FILE.read_text())
        if not isinstance(st, dict) or not isinstance(st.get("services", {}), dict):
            raise ValueError("bad shape")
        st.setdefault("services", {})
        return st
    except FileNotFoundError:
        return {"services": {}}
    except (ValueError, OSError) as e:
        log(f"state.json unreadable ({e}): starting empty, kept as state.json.bad")
        if not DRY:
            try:
                os.replace(STATE_FILE, STATE_DIR / "state.json.bad")
            except OSError:
                pass
        return {"services": {}}


def save_state(st):
    tmp = STATE_DIR / "state.json.tmp"
    tmp.write_text(json.dumps(st, indent=1))
    os.replace(tmp, STATE_FILE)


def health(service, d):
    """Return (state, health), or None when dc.sh failed, timed out or returned garbage."""
    try:
        p = subprocess.run([str(REPO / "scripts" / "dc.sh"), d, "ps", "--format", "json", service],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"{service}: dc.sh ps failed ({type(e).__name__})")
        return None
    if p.returncode != 0:
        log(f"{service}: dc.sh ps rc={p.returncode}")
        return None
    out = p.stdout.strip()
    if not out:
        log(f"{service}: dc.sh ps returned nothing")
        return None
    try:
        rows = json.loads(out) if out.startswith("[") else [json.loads(x) for x in out.splitlines() if x.strip()]
    except ValueError:
        log(f"{service}: dc.sh ps output not JSON")
        return None
    for r in rows:
        if isinstance(r, dict) and r.get("Service", service) == service:
            return r.get("State", ""), r.get("Health", "")
    return "", ""


def main():
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__)
        return 0
    bad = [n for n in REGISTRY if n in NEVER] + [n for n, d in REGISTRY.items() if d.startswith("core/")]
    if bad:
        print(f"registry violates the never-list: {bad}", file=sys.stderr)
        return 2
    syslog.openlog("ops-actions")
    if not DRY:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        lock = open(LOCK, "w")  # held until exit
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return 0
    if PAUSE.exists():
        log("PAUSE file present: doing nothing")
        return 0
    st = load_state()
    sv = st["services"]
    t = time.time()
    for rec in sv.values():
        rec["restarts"] = [x for x in rec.get("restarts", []) if t - x < 86400]

    for service, d in REGISTRY.items():
        rec = sv.setdefault(service, {"streak": 0, "restarts": [], "needs_dan": False})
        h = health(service, d)
        if h is None:
            say(f"{service}: health unknown (dc.sh failed), streak unchanged")
            continue
        state, hl = h
        if hl == "unhealthy" and state == "running":
            rec["streak"] = rec.get("streak", 0) + 1
        else:
            rec["streak"] = 0
            rec["needs_dan"] = False
        line = f"{service}: state={state or '-'} health={hl or '-'} streak={rec['streak']}"
        if rec["streak"] < STREAK_NEEDED:
            say(line + " -> nothing")
            continue

        hour = sum(1 for x in rec["restarts"] if t - x < 3600)
        if hour >= PER_HOUR or len(rec["restarts"]) >= PER_DAY:
            if rec.get("needs_dan"):
                say(line + " -> cap reached, already reported")
            elif DRY:
                say(line + " -> cap reached: would send 'needs Dan'")
            else:
                discord(f"ops-actions: {service} still unhealthy, restart cap reached - needs Dan")
                audit(service, "none", f"unhealthy x{rec['streak']}", "cap reached")
                rec["needs_dan"] = True
            continue

        total_hour = sum(1 for r in sv.values() for x in r.get("restarts", []) if t - x < 3600)
        if total_hour >= GLOBAL_PER_HOUR:
            if DRY:
                say(line + f" -> breaker: {total_hour} restarts in the last hour, would write PAUSE and stop")
                break
            reason = "breaker: >3 restarts/hour"
            try:
                PAUSE.write_text(f"{now_iso()} {reason} (next: {service})\n")
            except OSError as e:
                log(f"PAUSE write failed ({type(e).__name__}): stopping this run without restarting")
            audit(service, "pause", reason, "PAUSE written")
            msg = f"ops-actions: breaker tripped ({reason}); PAUSE written, all actions stopped. Needs Dan."
            discord(msg)
            ntfy("ops-actions paused", msg)
            log(msg)
            break

        if DRY:
            say(line + " -> would restart")
            continue
        reason = f"unhealthy x{rec['streak']}"
        # Persist the restart BEFORE running it, so a failed write can never cause an uncounted restart.
        rec["restarts"].append(time.time())
        rec["streak"] = 0
        try:
            save_state(st)
        except OSError as e:
            log(f"state save failed ({type(e).__name__}): not restarting {service}, stopping run")
            return 1
        try:
            p = subprocess.run([str(REPO / "scripts" / "dc.sh"), d, "restart", service],
                               capture_output=True, timeout=180)
            result = "ok" if p.returncode == 0 else f"failed rc={p.returncode}"
        except subprocess.TimeoutExpired:
            result = "timeout"
        except OSError as e:
            result = f"failed {type(e).__name__}"
        audit(service, "restart", reason, result)
        log(f"restarted {service} ({reason}): {result}")
        discord(f"ops-actions: restarted {service} ({reason}): {result}")

    if not DRY:
        try:
            save_state(st)
        except OSError as e:
            log(f"final state save failed ({type(e).__name__})")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
