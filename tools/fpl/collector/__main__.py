"""CLI: python -m collector <idle|bootstrap|fixtures|odds|odds-deadline|gameweek|understat>.
Prints one summary line; exit 0 on success, 1 on failure (reason on the last line)."""
import datetime as dt
import sys
import time

from . import fpl_api, odds, store, understat

JOBS = ("bootstrap", "fixtures", "odds", "odds-deadline", "gameweek", "understat")


def _parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _season(events):
    return store.season_of(events) if events else None


def job_bootstrap():
    d = fpl_api.bootstrap()
    if not d["events"] or not d["elements"]:
        return "nothing due (no events or players yet)"
    season = store.season_of(d["events"])
    now = store.utcnow()
    nxt = next((e["id"] for e in d["events"] if e.get("is_next")), None)
    players = [{**p, "next_gw": nxt} for p in d["elements"]]
    store.save_raw("fpl", "bootstrap", d)
    store.save_table("players", players, season, now)
    store.save_table("events", d["events"], season, now)
    store.save_table("teams", d["teams"], season, now)
    return f"bootstrap: {len(players)} players, {len(d['events'])} events, {len(d['teams'])} teams"


def job_fixtures():
    fx = fpl_api.fixtures()
    if not fx:
        return "nothing due (no fixtures yet)"
    d = fpl_api.bootstrap()
    if not d["events"]:
        return "nothing due (no events yet)"
    season = store.season_of(d["events"])
    store.save_raw("fpl", "fixtures", fx)
    store.save_table("fixtures", fx, season)
    return f"fixtures: {len(fx)} rows"


def job_odds():
    d = fpl_api.bootstrap()
    season = _season(d["events"]) or store.season_str(store.utcnow().year)
    return odds.pull(season)[1]


def job_odds_deadline():
    d = fpl_api.bootstrap()
    now = store.utcnow()
    up = [e for e in d["events"] if e.get("deadline_time") and _parse(e["deadline_time"]) > now]
    if not up:
        return "nothing due (no upcoming deadline)"
    e = min(up, key=lambda x: _parse(x["deadline_time"]))
    hours = (_parse(e["deadline_time"]) - now).total_seconds() / 3600
    if not 1 <= hours <= 3:
        return "nothing due"
    if e["id"] in store.read_state()["deadline_odds_gws"]:
        return "nothing due (gw already pulled)"
    pulled, msg = odds.pull(_season(d["events"]))
    if pulled:
        with store.state() as s:
            if e["id"] not in s["deadline_odds_gws"]:
                s["deadline_odds_gws"].append(e["id"])
    return f"gw {e['id']} deadline in {hours:.1f} h; {msg}"


def job_gameweek():
    d = fpl_api.bootstrap()
    if not d["events"]:
        return "nothing due (no events yet)"
    season = store.season_of(d["events"])
    st = store.read_state()
    new = [e["id"] for e in d["events"]
           if e.get("finished") and e.get("data_checked") and e["id"] not in st["collected_gws"]]
    backfill = not st["backfill_done"]
    if not new and not backfill:
        return "nothing due"
    # Everything is fetched into memory first; files are written only when all calls succeeded.
    lives = {gw: fpl_api.live(gw) for gw in new}
    summaries = fpl_api.all_summaries([p["id"] for p in d["elements"]])
    vaastav = None
    last_season = store.season_str(int(season[:4]) - 1)
    if backfill:
        try:
            vaastav = fpl_api.vaastav_merged_gw(last_season)
        except RuntimeError as e:
            raise RuntimeError(f"backfill: {e}")
    now = store.utcnow()
    for gw, lv in lives.items():
        store.save_raw("fpl", f"live_gw{gw}", lv)
        rows = [{"gw": gw, "element": x["id"], **x.get("stats", {})} for x in lv["elements"]]
        store.save_table("live", rows, season, now)
    store.save_raw("fpl", "element_summary", {str(k): v for k, v in summaries.items()})
    hist = [{"element": i, **h} for i, s in summaries.items() for h in s.get("history", [])]
    past = [{"element": i, **h} for i, s in summaries.items() for h in s.get("history_past", [])]
    store.save_table("player_history", hist, season, now)
    store.save_table("player_history_past", past, season, now)
    if vaastav:
        store.save_raw("vaastav", f"merged_gw_{last_season}.csv", raw_bytes=vaastav)
    with store.state() as s:
        s["collected_gws"] = sorted(set(s["collected_gws"]) | set(new))
        if backfill:
            s["backfill_done"] = True
    return (f"gameweek: gws {new or 'none'}, {len(summaries)} players, {len(hist)} history rows, "
            f"{len(past)} past-season rows" + (", backfill done" if backfill else ""))


def job_understat():
    d = fpl_api.bootstrap()
    y = int(store.season_of(d["events"])[:4]) if d["events"] else store.utcnow().year
    return understat.pull(y)


def job_idle():
    store.ensure_dirs()
    while True:
        time.sleep(3600)


FUNCS = {"bootstrap": job_bootstrap, "fixtures": job_fixtures, "odds": job_odds,
         "odds-deadline": job_odds_deadline, "gameweek": job_gameweek, "understat": job_understat}


def main(argv):
    if len(argv) != 2 or argv[1] not in JOBS + ("idle",):
        print(f"usage: python -m collector <{'|'.join(('idle',) + JOBS)}>", file=sys.stderr)
        return 2
    job = argv[1]
    if job == "idle":
        job_idle()
        return 0
    try:
        store.ensure_dirs()
        with store.job_lock(job) as got:
            if not got:
                print("already running")
                return 0
            print(FUNCS[job]())
            return 0
    except Exception as e:  # noqa: BLE001 - one-line reason, exit 1
        msg = " ".join(str(e).split())[:300] or type(e).__name__
        print(f"{job}: FAILED: {msg}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
