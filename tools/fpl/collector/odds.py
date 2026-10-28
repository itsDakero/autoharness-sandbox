"""The Odds API (soccer_epl, h2h + totals, UK). The key never reaches logs or raw files."""
import os

import requests

from . import store

URL = "https://api.the-odds-api.com/v4/sports/soccer_epl/odds"
FLOOR = 50


def _skip_reason(s):
    if not os.environ.get("ODDS_API_KEY"):
        return "odds: no ODDS_API_KEY, skipped"
    rem, at = s.get("odds_remaining"), s.get("odds_remaining_at")
    now = store.utcnow()
    if rem is not None and at and at[:7] == now.strftime("%Y-%m") and float(rem) < FLOOR:
        return f"odds: below floor ({rem} left), skipped"
    return None


def pull(season):
    """Returns (pulled: bool, message)."""
    with store.state() as s:
        reason = _skip_reason(s)
    if reason:
        return False, reason
    try:
        r = requests.get(URL, timeout=30, headers={"User-Agent": "homelab-fpl-collector/0.1 (personal use)"},
                         params={"regions": "uk", "markets": "h2h,totals", "oddsFormat": "decimal",
                                 "apiKey": os.environ["ODDS_API_KEY"]})
    except requests.RequestException as e:  # str(e) would carry the URL with the key
        raise RuntimeError(f"odds request failed: {type(e).__name__}")
    if r.status_code != 200:
        raise RuntimeError(f"odds API HTTP {r.status_code}")
    remaining = r.headers.get("x-requests-remaining")
    used = r.headers.get("x-requests-used")
    now = store.utcnow()
    if remaining is not None:
        with store.state() as s:
            s["odds_remaining"] = remaining
            s["odds_remaining_at"] = now.isoformat()
    try:
        data = r.json()
    except ValueError:
        raise RuntimeError("odds API returned non-JSON")
    if not isinstance(data, list):
        raise RuntimeError("odds API returned an unexpected shape")
    info = f"requests remaining {remaining}, used {used}"
    if not data:
        return True, f"odds: empty response, no table written ({info})"
    store.save_raw("odds", "odds", data)
    rows = []
    for ev in data:
        for bk in ev.get("bookmakers", []):
            for m in bk.get("markets", []):
                for o in m.get("outcomes", []):
                    rows.append({"event_id": ev.get("id"), "commence_time": ev.get("commence_time"),
                                 "home": ev.get("home_team"), "away": ev.get("away_team"),
                                 "bookmaker": bk.get("key"), "market": m.get("key"),
                                 "outcome": o.get("name"), "point": o.get("point"),
                                 "price": o.get("price"),
                                 "last_update": m.get("last_update") or bk.get("last_update")})
    store.save_table("odds", rows, season, now)
    return True, f"odds: {len(data)} matches, {len(rows)} rows ({info})"
