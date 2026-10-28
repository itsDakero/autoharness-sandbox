"""Weekly written summary: a numbers-only facts dict, a prompt and the Mac mini's Ollama (stdlib only)."""
import json
import os
import re
import urllib.error
import urllib.request
from datetime import timedelta

from .logic import num

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://100.74.81.122:11434").rstrip("/")
MODEL = os.environ.get("FITNESS_MODEL", "qwen3.5:9b")
TIMEOUT_S = 240
MIN_BULLETS = 3
MAX_BULLETS = 5
PREV_WEEKS = 4


class Offline(Exception):
    """The Mac mini can't be reached or answered badly; the week is skipped."""


def _r(v, d=1):
    f = num(v)
    return None if f is None else round(f, d)


def _mean(vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def _hms(seconds):
    f = num(seconds)
    if f is None:
        return None
    s = int(round(f))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def _load_facts(series, summ, start):
    if not series:
        return None
    last = series[-1]
    ago = series[-8] if len(series) > 7 else None
    this_w = sum(p["load"] for p in series if p["date"] >= start.isoformat())
    prev_w = sum(p["load"] for p in series
                 if (start - timedelta(days=7)).isoformat() <= p["date"] < start.isoformat())
    zone = (summ or {}).get("zone")
    return {
        "ctl": _r(last["ctl"]), "atl": _r(last["atl"]), "tsb": _r(last["tsb"]),
        "ctl_7d_ago": _r(ago["ctl"]) if ago else None, "atl_7d_ago": _r(ago["atl"]) if ago else None,
        "tsb_7d_ago": _r(ago["tsb"]) if ago else None,
        "form_zone": zone[0] if zone else None,
        "acwr": _r((summ or {}).get("acwr"), 2), "ramp": _r((summ or {}).get("ramp")),
        "monotony": _r((summ or {}).get("monotony"), 2),
        "week_load": _r(this_w), "last_week_load": _r(prev_w),
    }


def _recovery_facts(rec, start, today):
    if not rec:
        return None
    this_s, prev_s, warn = [], [], 0
    prev_start = (start - timedelta(days=7)).isoformat()
    for p in rec.get("rec_series") or []:
        d = p["date"]
        if d >= start.isoformat():
            this_s.append(num(p.get("score")))
        elif d >= prev_start:
            prev_s.append(num(p.get("score")))
    warn = sum(1 for d in rec.get("warn_dates") or [] if start.isoformat() <= d <= today.isoformat())
    debt = num(rec.get("debt"))
    cons = rec.get("consistency")
    chips = rec.get("chips") or {}
    return {
        "recovery_avg": _r(_mean(this_s)), "recovery_avg_last_week": _r(_mean(prev_s)),
        "sleep_debt_h": None if debt is None else _r(debt / 3600),
        "bedtime_sd_min": _r(cons["bed_sd"]) if cons else None,
        "wake_sd_min": _r(cons["wake_sd"]) if cons else None,
        "hrv": (chips.get("hrv") or {}).get("text"), "rhr": (chips.get("rhr") or {}).get("text"),
        "illness_warning_days": warn,
    }


def _running_facts(rn):
    if not rn:
        return None
    et = rn.get("ef_trend")
    preds = rn.get("predictions") or {}
    return {
        "easy_share_pct": None if num(rn.get("easy_share")) is None else _r(rn["easy_share"] * 100, 0),
        "efficiency_change_pct": _r(et[2]) if et else None,
        "vo2_current": _r(rn.get("vo2_current")),
        "predictions": {k: (_hms(preds[k][1]) if preds.get(k) else None) for k in ("5k", "10k", "half")}
        if preds else None,
        "vdot": _r(rn.get("vdot")),
        "long_run_readiness": _r(rn.get("ready"), 0),
    }


def _volume_facts(weeks, streak):
    if not weeks:
        return None

    def row(w):
        return {"km": _r((w.get("dist_m") or 0) / 1000), "hours": _r((w.get("time_s") or 0) / 3600),
                "runs": w.get("runs"), "fiit": w.get("fiit"),
                "long_share_pct": None if num(w.get("long_share")) is None else _r(w["long_share"] * 100, 0)}

    prev = weeks[1:1 + PREV_WEEKS]
    avg = None
    if prev:
        avg = {"km": _r(_mean([(w.get("dist_m") or 0) / 1000 for w in prev])),
               "hours": _r(_mean([(w.get("time_s") or 0) / 3600 for w in prev])),
               "runs": _r(_mean([w.get("runs") or 0 for w in prev])),
               "fiit": _r(_mean([w.get("fiit") or 0 for w in prev]))}
    return {"this_week": row(weeks[0]), "previous_4_week_average": avg, "run_streak_weeks": streak}


def _checkin_facts(checkins):
    cs = list(checkins or [])
    if not cs:
        return None
    # Explicit whitelist: the note text is never read.
    feel = [num(c["feeling"]) for c in cs]
    flag = lambda *keys: sum(1 for c in cs if any(c[k] for k in keys))  # noqa: E731
    return {"count": len(cs), "average_feeling": _r(_mean(feel)),
            "ill_days": flag("ill_neck", "ill_chest"), "sore_legs_days": flag("sore_legs"),
            "stressed_days": flag("stressed"), "slept_badly_days": flag("slept_badly")}


def build_facts(load_series, load_sum, rec, rn, weeks, streak, checkins, today):
    """Numbers only, from a whitelist. None when the week has no data at all."""
    start = today - timedelta(days=today.weekday())
    week = weeks[0] if weeks else {}
    load = _load_facts(load_series, load_sum, start)
    recovery = _recovery_facts(rec, start, today)
    checks = _checkin_facts(checkins)
    has_data = bool(
        (load and (load["week_load"] or 0) > 0) or (week.get("runs") or 0) > 0 or (week.get("fiit") or 0) > 0
        or checks or (recovery and recovery["recovery_avg"] is not None))
    if not has_data:
        return None
    return {"week_start": start.isoformat(), "week_end": today.isoformat(), "load": load,
            "recovery": recovery, "running": _running_facts(rn), "volume": _volume_facts(weeks, streak),
            "checkins": checks}


SYSTEM = (
    "You write a short weekly training summary for one recreational runner. You are given a JSON of this "
    "week's numbers. Reply with exactly 5 lines, each starting with \"- \": 1) what improved, 2) what "
    "slipped, 3) recovery and sleep, 4) what it means, 5) one suggestion. Use only the numbers given. "
    "Say \"not enough data\" rather than guess. Null means missing. No diagnosis; word any warning as a "
    "suggestion, not advice. Plain text, no headings, no extra lines. "
    "Start each line with the finding, with no filler opener or closer such as \"Great question\" or \"I hope this helps\". "
    "No em dashes. No \"not X but Y\" phrasing and no closing moral. "
    "Use active voice and lead with the number."
)


def prompt(facts):
    return SYSTEM, "This week's numbers:\n" + json.dumps(facts, indent=1, sort_keys=True)


def ask_model(facts):
    system, user = prompt(facts)
    body = json.dumps({"model": MODEL, "stream": False, "think": False,
                       "messages": [{"role": "system", "content": system},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
            if r.status != 200:
                raise Offline(f"Ollama HTTP {r.status}")
            reply = json.loads(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        raise Offline(f"Ollama HTTP {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:   # incl. timeouts and bad JSON
        raise Offline(str(e)) from None
    msg = reply.get("message") if isinstance(reply, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, str):
        raise Offline("Ollama reply had no text")
    return content


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
_MARK = re.compile(r"^\s*(?:[-*•]|[1-5][.)])\s+")


_OPENER = re.compile(r"^\s*(?:great question[,!.]?|(?:sure|certainly|absolutely)[,!]|"
                     r"here(?:'s| is) (?:your|the) (?:summary|weekly)[^.!?:]*[:.!]?)\s*", re.I)
_CLOSER = re.compile(r"^\s*(?:i hope this helps|let me know if|feel free to|keep up the (?:great|good) work)", re.I)


def clean_bullet(text):
    """Drop chatbot filler sentences and swap em dashes for commas."""
    text = re.sub(r"\s*\u2014\s*", ", ", text or "")
    kept = []
    for sent in re.split(r"(?<=[.!?])\s+", text):
        sent = _OPENER.sub("", sent, count=1)
        if sent.strip() and not _CLOSER.match(sent):
            kept.append(sent.strip())
    text = " ".join(kept)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r",(\s*,)+", ",", text)
    return text.strip(" \t,;:")


def parse_bullets(text):
    text = _THINK.sub("", text or "")
    text = re.sub(r"<think>.*", "", text, flags=re.S | re.I)   # an unclosed block
    out = []
    for line in text.splitlines():
        if _MARK.match(line):
            b = clean_bullet(_MARK.sub("", line, count=1).strip())
            if b:
                out.append(b)
    return out[:MAX_BULLETS]
