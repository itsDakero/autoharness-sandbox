#!/usr/bin/env python3
"""Cron (daily 09:20, user dan): price history and drop alerts for the LeafGreen card watchlist.

Reads $APPDATA_PATH/leafgreen/state.json (the app's save; this script never writes it). The watchlist is
every pick in S.cards with got=false. For each, fetches the card from TCGdex (free, no key) and appends
[YYYY-MM-DD, low, trend, avg30] (EUR, Cardmarket) to $APPDATA_PATH/leafgreen/cards/prices.json
({id: {name, set, hist, alerted?}}): one entry per day (an existing one is replaced), newest 400 kept.
This script is the only writer of prices.json; the leafgreen server only reads it.

Alert (one Discord message per run, one line per card) when ALL hold:
  - usual = median of the past daily lows (same stat as today's low, not trend) of the entries from the last 30 days before today, at least 7 of them
  - usual >= 2 EUR, low <= 0.75 x usual, low >= 0.2 x usual (a junk floor)
  - not alerted in the last 7 days. `alerted` is cleared once low is back above 0.85 x usual.
Owned (got) cards, cards with no price, no state.json or too little history: nothing is posted.
TCGdex down: logged, exit 0, nothing posted.

  scripts/card-prices.py            # what cron runs
  scripts/card-prices.py --dry-run  # print the alerts, write nothing, post nothing
Logs: journalctl -t card-prices.
"""
import json
import os
import re
import statistics
import subprocess
import sys
import syslog
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TCGDEX = "https://api.tcgdex.net/v2/en/cards/"
KEEP = 400
WINDOW_DAYS = 30
MIN_ENTRIES = 7
MIN_USUAL = 2.0
DROP = 0.75
FLOOR = 0.2
RESET = 0.85
REALERT_DAYS = 7


def log(msg: str) -> None:
    syslog.openlog("card-prices")
    syslog.syslog(msg)
    print(msg)


def appdata() -> str:
    """APPDATA_PATH from the environment, else from the repo env file (like storage-cleanup.py), else /srv/homelab."""
    v = os.environ.get("APPDATA_PATH")
    if v:
        return v
    try:
        for line in (REPO / ".env").read_text().splitlines():
            m = re.match(r"\s*APPDATA_PATH=(.*)", line)
            if m:
                return m[1].strip().strip("'\"") or "/srv/homelab"
    except OSError:
        pass
    return "/srv/homelab"


def num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0 else None


def fetch(card_id: str):
    """(low, trend, avg30) in EUR, each None if missing. Raises on a network/parse failure."""
    err = None
    for i in range(3):
        try:
            req = urllib.request.Request(TCGDEX + urllib.parse.quote(card_id, safe=""),
                                         headers={"User-Agent": "homelab-card-prices"})
            with urllib.request.urlopen(req, timeout=15) as r:
                d = json.load(r)
            cm = ((d.get("pricing") or {}).get("cardmarket")) or {}
            return tuple(num(cm.get(k)) or num(cm.get(k + "-holo")) for k in ("low", "trend", "avg30"))
        except (urllib.error.URLError, OSError, ValueError, AttributeError) as e:
            err = e
            if i < 2:
                time.sleep(1 + i * 2)
    raise err


def write_atomic(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, path)


def usual_low(hist: list, today: str):
    since = (date.fromisoformat(today) - timedelta(days=WINDOW_DAYS)).isoformat()
    vals = [h[1] for h in hist if len(h) >= 2 and since <= h[0] < today and num(h[1])]
    return statistics.median(vals) if len(vals) >= MIN_ENTRIES else None


def main() -> int:
    args = sys.argv[1:]
    if any(a in ("-h", "--help") for a in args):
        print(__doc__)
        return 0
    dry = "--dry-run" in args
    base = Path(appdata()) / "leafgreen"
    try:
        state = json.loads((base / "state.json").read_text())
    except (OSError, ValueError):
        return 0   # no save yet
    cards = state.get("cards") if isinstance(state, dict) else None
    picks = [c for c in (cards or {}).values() if isinstance(c, dict) and c.get("id") and not c.get("got")]
    if not picks:
        return 0
    pfile = base / "cards" / "prices.json"
    try:
        prices = json.loads(pfile.read_text())
        if not isinstance(prices, dict):
            prices = {}
    except (OSError, ValueError):
        prices = {}
    today = date.today().isoformat()
    alerts, failed, seen = [], 0, set()
    for c in picks:
        cid = c["id"]
        if cid in seen:
            continue
        seen.add(cid)
        try:
            low, trend, avg30 = fetch(cid)
        except Exception as e:
            failed += 1
            log(f"{cid}: TCGdex failed ({e})")
            continue
        e = prices.setdefault(cid, {"name": c.get("name") or cid, "hist": []})
        e["name"], e["set"] = c.get("name") or cid, c.get("set")
        usual = usual_low(e["hist"], today)   # before today's entry goes in
        e["hist"] = ([h for h in e["hist"] if h[0] != today] + [[today, low, trend, avg30]])[-KEEP:]
        if low is None or usual is None:
            continue
        if low > RESET * usual:
            e.pop("alerted", None)
        if usual >= MIN_USUAL and FLOOR * usual <= low <= DROP * usual:
            prev = e.get("alerted")
            if prev and (date.fromisoformat(today) - date.fromisoformat(prev)).days < REALERT_DAYS:
                continue
            e["alerted"] = today
            link = "https://www.cardmarket.com/en/Pokemon/Products/Search?searchString=" + \
                urllib.parse.quote(e["name"])
            alerts.append(f"{e['name']} ({e.get('set') or '?'}): low €{low:.2f} vs usual €{usual:.2f} {link}")
    if failed:
        log(f"{failed} card(s) not fetched")
    if dry:
        print("\n".join(alerts) if alerts else "no alerts (dry run, nothing written)")
        return 0
    try:
        write_atomic(pfile, prices)
    except OSError as e:
        log(f"can't write prices.json: {e}")
        return 0
    if alerts:
        msg = "Pokémon card price drop:\n" + "\n".join(alerts)
        r = subprocess.run([str(REPO / "scripts" / "discord.sh"), msg], capture_output=True, text=True)
        log(f"{len(alerts)} alert(s), discord rc={r.returncode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
