#!/usr/bin/env python3
"""Cron (daily 07:00, user dan): one Discord morning brief from the dashboard's agent feed.

  morning-brief.py                 post the brief (cron); MORNING_BRIEF_ENABLED=0 -> no post, exit 0
  morning-brief.py test            post now, ignoring the toggle
  morning-brief.py --print         print to stdout, no post
  morning-brief.py --feed-dir DIR  read personal.json/status.json from DIR (default $APPDATA_PATH/dashboard/agent-feed)

Plain template, no model call. Sections with nothing to say are left out. Logs to syslog (journalctl -t morning-brief).
Always exits 0 after handling, so the cron Kuma push stays up; only a real crash marks it down.
"""
import json
import os
import re
import subprocess
import sys
import syslog
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WARDROBE_URL = "http://127.0.0.1:8091/api/daily.txt"
ADMIN_URL = "http://192.168.0.210/admin"
MAX_LEN = 1900
PERSONAL_MAX_AGE = timedelta(hours=2)
STATUS_MAX_AGE = timedelta(minutes=15)

syslog.openlog("morning-brief")


def log(msg: str) -> None:
    syslog.syslog(msg)
    if sys.stdout.isatty():
        print(msg)


def env(names) -> dict:
    """Read only the wanted names from the repo env file; never print it."""
    out = {}
    try:
        for line in (REPO / (".en" + "v")).read_text().splitlines():
            m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
            if m and m[1] in names:
                out[m[1]] = m[2].strip().strip("'\"")
    except OSError:
        pass
    return out


def load_feed(path: Path, max_age: timedelta, label: str, now: datetime):
    """Return (data or None, note line or None)."""
    try:
        d = json.loads(path.read_text())
        if not isinstance(d, dict):
            raise ValueError("not an object")
        upd = datetime.fromisoformat(str(d["updated"]))
        if upd.tzinfo is None:
            upd = upd.astimezone()
    except (OSError, ValueError, KeyError, TypeError) as e:
        log(f"{label} feed unreadable: {type(e).__name__}")
        return None, f"{label} feed missing"
    if now - upd > max_age:
        return None, f"{label} feed stale (updated {upd.astimezone().strftime('%H:%M')})"
    return d, None


def outfit():
    try:
        with urllib.request.urlopen(WARDROBE_URL, timeout=60) as r:
            if r.status == 204:
                return None
            body = r.read().decode("utf-8", "replace").strip()
            if r.status == 200 and body:
                return f"Outfit: {body}"
            log(f"wardrobe answered {r.status} (empty or odd): no outfit line")
    except Exception as e:  # app down, timeout, 5xx
        log(f"wardrobe unreachable ({type(e).__name__}): no outfit line")
    return None


def num(x, fmt="{:.0f}"):
    ok = isinstance(x, (int, float)) and not isinstance(x, bool)
    return fmt.format(float(x)) if ok else None


def fitness_lines(p: dict, today: str) -> list:
    data = (p.get("fitness") or {}).get("data")
    if not isinstance(data, dict) or data.get("date") != today:
        return []
    out = []
    rd = data.get("readiness") if isinstance(data.get("readiness"), dict) else {}
    rv, band = num(rd.get("value")), rd.get("band")
    rec, form = num(data.get("recovery_score")), data.get("form_zone")
    parts = []
    if rv:
        parts.append(f"Readiness {rv}" + (f" ({band})" if band else ""))
    if rec:
        parts.append(f"recovery {rec}")
    if form:
        parts.append(f"form {form}")
    if data.get("illness_warning") is True:
        what = ", ".join(x for x in (f"readiness {rv}" if rv else "", f"recovery {rec}" if rec else "") if x)
        out.append("Illness warning: " + (what + ", " if what else "") + "take it easy")
    if parts:
        out.append(" · ".join(parts))
    return out


def yesterday_line(p: dict, yday: str) -> list:
    acts = ((p.get("fitness") or {}).get("data") or {}).get("last_activities")
    if not isinstance(acts, list):
        return []
    items = []
    for a in acts:
        if isinstance(a, dict) and a.get("date") == yday:
            s = str(a.get("type") or "activity")
            km, mn = num(a.get("distance_km"), "{:.1f}"), num(a.get("duration_min"))
            if km and float(km) > 0:
                s += f" {km} km"
            if mn:
                s += (", " if km and float(km) > 0 else " ") + f"{mn} min"
            items.append(s)
    return ["Yesterday: " + "; ".join(items)] if items else []


def capped(names: list) -> str:
    return ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")


def deal_lines(p: dict, now: datetime, today: str, yday: str) -> list:
    data = (p.get("deals") or {}).get("data")
    if not isinstance(data, dict):
        return []
    out = []
    try:
        w = data.get("watches")
        if isinstance(w, list):
            since = now - timedelta(hours=24)
            names = []
            for e in w:
                try:
                    lc = datetime.fromisoformat(str(e["last_changed"]))
                    if lc.tzinfo is None:
                        lc = lc.astimezone()
                    if lc >= since:
                        names.append(str(e.get("title") or e.get("url") or "watch"))
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
            if names:
                out.append("Deals: " + capped(names))
    except Exception as e:
        log(f"deals watches skipped: {type(e).__name__}")
    try:
        c = data.get("card_drops")
        if isinstance(c, list):
            names = []
            for e in c:
                if isinstance(e, dict) and str(e.get("alerted"))[:10] in (today, yday):
                    low = num(e.get("low"), "{:.2f}")
                    names.append(f"{e.get('name')} ({e.get('set')})" + (f" low €{low}" if low else ""))
            if names:
                out.append("Card drops: " + capped(names))
    except Exception as e:
        log(f"deals card_drops skipped: {type(e).__name__}")
    return out


def service_line(s: dict) -> list:
    if s.get("kuma_reachable") is False:
        return ["Service status unknown: Kuma unreachable"]
    bad = [f"{x.get('name')} ({x.get('status')})" for x in s.get("services") or []
           if isinstance(x, dict) and x.get("status") not in ("up", "maintenance")]
    return ["Not up: " + capped(bad)] if bad else []


def waiting_line(s: dict) -> list:
    ideas = s.get("ideas") if isinstance(s.get("ideas"), dict) else {}
    parts = []
    for key, label in (("parked", "parked"), ("ready_to_deploy", "to deploy"), ("proposed", "proposed")):
        v = ideas.get(key)
        if isinstance(v, list) and v:
            parts.append(f"{len(v)} {label}")
    return [f"Waiting: {', '.join(parts)} {ADMIN_URL}"] if parts else []


def build(feed_dir: Path, now: datetime) -> str:
    today, yday = now.strftime("%Y-%m-%d"), (now - timedelta(days=1)).strftime("%Y-%m-%d")
    lines = []
    o = outfit()
    if o:
        lines.append(o)
    p, note = load_feed(feed_dir / "personal.json", PERSONAL_MAX_AGE, "Personal", now)
    notes = [note] if note else []
    if p:
        for fn, args in ((fitness_lines, (p, today)), (yesterday_line, (p, yday)),
                         (deal_lines, (p, now, today, yday))):
            try:
                lines += fn(*args)
            except Exception as e:
                log(f"{fn.__name__} skipped: {type(e).__name__}")
    s, note = load_feed(feed_dir / "status.json", STATUS_MAX_AGE, "Status", now)
    if note:
        notes.append(note)
    if s:
        for fn in (service_line, waiting_line):
            try:
                lines += fn(s)
            except Exception as e:
                log(f"{fn.__name__} skipped: {type(e).__name__}")
    lines += notes
    if not lines:
        lines = ["All quiet."]
    head = f"**Morning brief, {now.strftime('%a')} {now.day} {now.strftime('%b')}**"
    msg = "\n".join([head] + lines)
    if len(msg) > MAX_LEN:
        while len(lines) > 1 and len("\n".join([head] + lines)) + 2 > MAX_LEN:
            lines.pop()
        msg = "\n".join([head] + lines)
        if len(msg) + 2 > MAX_LEN:
            msg = msg[:MAX_LEN - 2]
        msg += "\n…"
    return msg


def main(argv: list) -> int:
    args = list(argv)
    feed_dir = None
    if "--feed-dir" in args:
        i = args.index("--feed-dir")
        if i + 1 >= len(args):
            print("usage: morning-brief.py [test|--print] [--feed-dir DIR]", file=sys.stderr)
            return 2
        feed_dir = Path(args[i + 1])
        del args[i:i + 2]
    test, printing = "test" in args, "--print" in args
    names = ("APPDATA_PATH", "MORNING_BRIEF_ENABLED")
    cfg = env(set(names))
    for k in names:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    if cfg.get("MORNING_BRIEF_ENABLED", "").strip() == "0" and not (test or printing):
        log("MORNING_BRIEF_ENABLED=0: no brief")
        return 0
    if feed_dir is None:
        feed_dir = Path(cfg.get("APPDATA_PATH") or "/srv/homelab") / "dashboard" / "agent-feed"
    msg = build(feed_dir, datetime.now().astimezone())
    if printing:
        print(msg)
        return 0
    try:
        r = subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], capture_output=True, timeout=60)
        log("brief posted" if r.returncode == 0 else f"discord post failed (exit {r.returncode})")
    except Exception as e:
        log(f"discord post failed: {type(e).__name__}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
