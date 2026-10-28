"""My squad from the public FPL entry endpoints (no login): picks, bank, free transfers, chips left per half.
10 s timeout, 15 min cache in /data/web/entry.json; on failure the cached data is returned with its age."""
import datetime as dt
import os
import sys

import requests

from . import data, projections

BASE = "https://fantasy.premierleague.com/api"
UA = {"User-Agent": "homelab-fpl-web/0.2 (personal use)"}
CACHE = data.WEB / "entry.json"
TTL = dt.timedelta(minutes=15)
RETRY_AFTER = dt.timedelta(seconds=90)  # after a failure, serve the cache without calling the API again
_last_fail = None


def team_id():
    v = os.environ.get("FPL_TEAM_ID", "").strip()
    return int(v) if v.isdigit() and int(v) > 0 else None


def _get(path):
    try:
        r = requests.get(f"{BASE}/{path}", headers=UA, timeout=10)
    except requests.RequestException as e:
        raise RuntimeError(f"request failed: {type(e).__name__} for {path}")
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} from {path}")
    try:
        return r.json()
    except ValueError:
        raise RuntimeError(f"not JSON from {path}")


def free_transfers(transfers, history, events):
    """Free transfers for the next gameweek, via the solver's own calculate_fts. None if it can't be done."""
    try:
        sd = os.environ.get("SOLVER_DIR", "/opt/solver")
        if sd not in sys.path:
            sys.path.insert(0, sd)
        from dev.solver import calculate_fts
        chips = history.get("chips", [])
        nxt = next(e["id"] for e in events if e.get("is_next"))
        first = history["current"][0]["event"]
        return int(calculate_fts(transfers[::-1], first, nxt,
                                 [c["event"] for c in chips if c["name"] == "freehit"],
                                 [c["event"] for c in chips if c["name"] == "wildcard"]))
    except Exception:
        return None


def fetch(tid, next_gw):
    """Fresh entry data. Raises RuntimeError on any API problem."""
    entry = _get(f"entry/{tid}/")
    history = _get(f"entry/{tid}/history/")
    transfers = _get(f"entry/{tid}/transfers/")
    cur = [x for x in history.get("current", []) if x.get("event")]
    gw = cur[-1]["event"] if cur else (entry.get("current_event") or max(next_gw - 1, 1))
    picks = _get(f"entry/{tid}/event/{gw}/picks/")
    return {"entry": {k: entry.get(k) for k in ("name", "player_first_name", "player_last_name", "summary_overall_points")},
            "gw": gw, "picks": picks.get("picks", []), "bank": (picks.get("entry_history") or {}).get("bank"),
            "history_chips": history.get("chips", []), "history_current": history.get("current", []),
            "transfers": transfers, "fetched_at": data.utcnow().isoformat()}


def get(next_gw, events, force=False):
    """-> {"data", "age_min", "error", "fts", "chips_left"} or {"error": ...} when nothing is known."""
    tid = team_id()
    if tid is None:
        return {"error": "no FPL_TEAM_ID", "data": None}
    cached = data.read_json(CACHE)
    now = data.utcnow()
    age = None
    if cached and cached.get("team_id") == tid:
        try:
            age = now - dt.datetime.fromisoformat(cached["data"]["fetched_at"])
        except (KeyError, ValueError):
            cached = None
    else:
        cached = None
    err = None
    global _last_fail
    if cached is None or age is None or age > TTL or force:
        if _last_fail is not None and now - _last_fail < RETRY_AFTER and not force:
            err = "FPL API failed a moment ago"
        else:
            try:
                fresh = fetch(tid, next_gw)
                cached = {"team_id": tid, "data": fresh}
                try:
                    data.write_json(CACHE, cached)
                except OSError:
                    pass
                age = dt.timedelta(0)
                _last_fail = None
            except RuntimeError as e:
                err = str(e)
                _last_fail = now
    if cached is None:
        return {"error": err or "no data", "data": None}
    d = cached["data"]
    return {"data": d, "error": err, "age_min": int(age.total_seconds() // 60) if age is not None else None,
            "fts": free_transfers(d["transfers"], {"chips": d["history_chips"], "current": d["history_current"]}, events),
            "chips_left": projections.chips_left(d["history_chips"])}
