"""The Odds API v4 client (stdlib urllib). The key is in the query string, so nothing here ever logs a URL or
an exception text: errors carry only the league, the endpoint, the HTTP status or the exception class."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com/v4/sports"
TIMEOUT = 20
quota_hook = None  # called with {"remaining": str|None, "used": str|None} after every call


class OddsError(Exception):
    """Message is safe to print (no URL, no key)."""


def key():
    return os.environ.get("ODDS_API_KEY", "").strip()


def _get(league, path, params):
    k = key()
    if not k:
        raise OddsError("no ODDS_API_KEY")
    q = urllib.parse.urlencode(dict(params, apiKey=k))
    req = urllib.request.Request(f"{BASE}/{league}/{path}?{q}", headers={"User-Agent": "homelab-lms/0.1"})
    hdrs = None
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            hdrs = r.headers
            body = r.read()
    except urllib.error.HTTPError as e:
        _quota(e.headers)
        raise OddsError(f"{league} /{path}: HTTP {e.code}") from None
    except Exception as e:  # network, timeout, TLS: class name only
        raise OddsError(f"{league} /{path}: {type(e).__name__}") from None
    _quota(hdrs)
    try:
        return json.loads(body)
    except ValueError:
        raise OddsError(f"{league} /{path}: response is not JSON") from None


def _quota(hdrs):
    if quota_hook is None or hdrs is None:
        return
    quota_hook({"remaining": hdrs.get("x-requests-remaining"), "used": hdrs.get("x-requests-used")})


def events(league):
    return parse_events(league, _get(league, "events", {}))


def odds(league):
    data = _get(league, "odds", {"regions": "uk", "markets": "h2h", "oddsFormat": "decimal"})
    return parse_odds(league, data)


def scores(league):
    return parse_scores(league, _get(league, "scores", {"daysFrom": 3}))


def parse_events(league, data):
    if not isinstance(data, list):
        raise OddsError(f"{league} /events: unexpected response")
    out = []
    for e in data:
        try:
            out.append({"id": str(e["id"]), "league": league, "home": e["home_team"], "away": e["away_team"],
                        "commence": e["commence_time"]})
        except (KeyError, TypeError):
            continue
    return out


def parse_odds(league, data):
    """-> ({event_id: [(bookmaker, home, draw, away)]}, bad_line_count). Raises when nothing usable came back."""
    if not isinstance(data, list):
        raise OddsError(f"{league} /odds: unexpected response")
    res, bad = {}, 0
    for e in data:
        try:
            home, away, eid = e["home_team"], e["away_team"], str(e["id"])
        except (KeyError, TypeError):
            bad += 1
            continue
        for bk in e.get("bookmakers") or []:
            line = _h2h(bk, home, away)
            if line is None:
                bad += 1
            else:
                res.setdefault(eid, []).append(line)
    if not res:
        raise OddsError(f"{league} /odds: no usable bookmaker odds ({len(data)} events, {bad} unusable)")
    return res, bad


def _h2h(bk, home, away):
    try:
        for m in bk["markets"]:
            if m["key"] != "h2h":
                continue
            p = {o["name"]: float(o["price"]) for o in m["outcomes"]}
            if set(p) != {home, away, "Draw"} or min(p.values()) <= 1.0:
                return None
            return (str(bk["key"]), p[home], p["Draw"], p[away])
    except (KeyError, TypeError, ValueError):
        return None
    return None


def parse_scores(league, data):
    if not isinstance(data, list):
        raise OddsError(f"{league} /scores: unexpected response")
    out = {}
    for e in data:
        try:
            sc = {s["name"]: int(s["score"]) for s in (e.get("scores") or [])}
            out[str(e["id"])] = {"completed": bool(e.get("completed")), "home": e["home_team"],
                                 "away": e["away_team"], "scores": sc}
        except (KeyError, TypeError, ValueError):
            continue
    return out
