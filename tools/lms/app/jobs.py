"""Cron jobs: python -m app.jobs <odds|alerts|results>.
stdout = the Discord text only (scripts/lms-job.sh posts it); logs and errors go to stderr, one line each.
The API key never reaches stdout/stderr: oddsapi raises only league, endpoint, HTTP status or class name."""
import datetime as dt
import os
import sys

from . import db, oddsapi, rounds, ranking
from .oddsapi import OddsError

LOW_QUOTA = 40
STALE_ODDS = dt.timedelta(hours=6)
PULL_BACKOFF = dt.timedelta(hours=1)
STUCK_AFTER = dt.timedelta(hours=6)


def log(msg):
    print(f"lms: {msg}", file=sys.stderr)


def utcnow():
    return dt.datetime.now(rounds.UTC)


def store_quota(con):
    def hook(q):
        if q.get("remaining") is not None:
            db.kv_set(con, "quota_remaining", q["remaining"])
            db.kv_set(con, "quota_used", q.get("used") or "")
            db.kv_set(con, "quota_at", rounds.fmt_utc(utcnow()))
    oddsapi.quota_hook = hook


def quota_low(con):
    try:
        return int(db.kv_get(con, "quota_remaining", "")) < LOW_QUOTA
    except ValueError:
        return False


def refresh_events(con, now):
    """/events is free: all three leagues. Future fixtures that vanish are marked gone.
    An empty or all-malformed list while future fixtures are stored is an error, never "all gone"."""
    cutoff = rounds.fmt_utc(now)
    for lg in rounds.LEAGUES:
        evs = oddsapi.events(lg)
        keep = set()
        for e in evs:
            try:
                rk = rounds.round_key(rounds.parse_utc(e["commence"]))
            except ValueError:
                continue
            db.upsert_fixture(con, e, rk)
            keep.add(e["id"])
        con.commit()
        if keep:
            db.mark_gone(con, lg, keep, cutoff)
        elif con.execute("SELECT 1 FROM fixtures WHERE league=? AND gone=0 AND commence>? LIMIT 1",
                         (lg, cutoff)).fetchone():
            raise OddsError(f"{lg} /events: no usable events returned; stored fixtures kept")
    db.kv_set(con, "events_at", rounds.fmt_utc(now))


def pull_odds(con, now, rnd):
    """/odds for the pool leagues of the round (1 credit each). False when skipped for quota."""
    if quota_low(con):
        return False
    for lg in rounds.pool_leagues(db.round_fixtures(con, rnd)):
        res, bad = oddsapi.odds(lg)
        for eid, lines in res.items():
            db.store_odds(con, eid, lines)
        if bad:
            log(f"{lg}: {bad} unusable bookmaker lines skipped")
    db.kv_set(con, "odds_at", rounds.fmt_utc(now))
    return True


def active_game(con):
    g = db.current_game(con)
    return g if g and g["status"] == "active" else None


def notices(con, now):
    """Quota (once a month) and postponed-fixture lines."""
    out = []
    if quota_low(con) and db.claim(con, f"quota:{now:%Y-%m}"):
        out.append(f"LMS: Odds API credits low ({db.kv_get(con, 'quota_remaining')} left); odds and results pulls "
                   "paused to leave room for FPL.")
    g = active_game(con)
    p = db.pending_pick(con, g["id"]) if g else None
    why = rounds.pick_flag(con, p)
    if why and db.claim(con, f"postponed:{p['id']}:{p['event_id']}"):
        out.append(f"LMS: your pick {p['team']} looks postponed ({why}). Open the page and choose "
                   "through / re-pick / out.")
    if p and p["result"] == "pending" and (p["kickoff"] or p["event_id"]):
        f = db.get_fixture(con, p["event_id"]) if p["event_id"] else None
        try:
            ko = rounds.parse_utc(f["commence"] if f else p["kickoff"])
        except (ValueError, TypeError):
            ko = None
        if ko and now - ko >= STUCK_AFTER and db.claim(con, f"stuck:{p['id']}"):
            out.append(f"LMS: no result yet for {p['team']} (round {p['round']}); set it on the page, "
                       "next round's nudges wait for it.")
    return out


def job_odds(con, now):
    if not oddsapi.key() or not active_game(con):
        return 0, []
    refresh_events(con, now)
    rnd = rounds.current_round(con, active_game(con)["id"], now)
    if rnd:
        dl, _ = rounds.deadline_for(con, rnd)
        if dl is None or now < dl:
            if not pull_odds(con, now, rnd):
                log("credits low: odds pull skipped")
    return 0, notices(con, now)


def _fresh_odds(con, now, rnd):
    """Pull fresh odds when the stored ones are older than 6 h. False when a needed pull failed or is backed off."""
    at = db.kv_get(con, "odds_at")
    if at and now - rounds.parse_utc(at) <= STALE_ODDS:
        return True
    failed = db.kv_get(con, "pull_fail_at")
    if failed and now - rounds.parse_utc(failed) < PULL_BACKOFF:
        return False
    try:
        refresh_events(con, now)
        return pull_odds(con, now, rnd) or bool(at)
    except OddsError as e:
        db.kv_set(con, "pull_fail_at", rounds.fmt_utc(now))
        log(f"pull failed: {e}")
        return False


def top3_text(con, rnd, game_id, dl, now):
    _, rows = rounds.round_state(con, rnd, game_id)
    best = ranking.top(rows, 3)
    if not best:
        return None
    lines = [f"LMS round {rnd}: safest picks (deadline {rounds.fmt_local(dl)})"]
    for i, r in enumerate(best, 1):
        lines.append(f"{i}. {r['team']} ({r['ha']}) v {r['opp']}: {r['p_win'] * 100:.0f}% win, "
                     f"best {r['best']:.2f}, {rounds.fmt_local(rounds.parse_utc(r['commence']))}")
    return "\n".join(lines)


def job_alerts(con, now):
    g = db.current_game(con)
    if not g or not oddsapi.key():
        return 0, []
    loc = rounds.to_london(now)
    if g["status"] == "out":
        wk = loc.isocalendar()
        if loc.weekday() == 0 and loc.hour >= 9 and db.claim(con, f"out-weekly:{wk[0]}-W{wk[1]:02d}"):
            return 0, ["Still out of LMS; press New game on the page when the next one starts."]
        return 0, []
    rnd = rounds.current_round(con, g["id"], now)
    if not rnd:
        return 0, notices(con, now)
    dl, _ = rounds.deadline_for(con, rnd)
    out, rc = [], 0
    pick = db.round_pick(con, g["id"], rnd)
    if dl:
        if now < dl and now >= dl - dt.timedelta(hours=24) and not db.is_sent(con, f"top3:{rnd}"):
            if pick:
                db.claim(con, f"top3:{rnd}")
            elif _fresh_odds(con, now, rnd):
                txt = top3_text(con, rnd, g["id"], dl, now)
                if txt and db.claim(con, f"top3:{rnd}"):
                    out.append(txt)
            else:
                rc = 1
        if not pick and dl - dt.timedelta(hours=2) <= now < dl and db.claim(con, f"remind:{rnd}"):
            out.append(f"LMS: no pick recorded for round {rnd}; deadline {rounds.fmt_local(dl)}.")
        if not pick and now >= dl and db.claim(con, f"nopick:{rnd}"):
            out.append(f"No pick recorded for round {rnd}; record it on the page.")
    return rc, out + notices(con, now)


def job_results(con, now):
    g = active_game(con)
    if not g or not oddsapi.key():
        return 0, []
    p = con.execute("SELECT * FROM picks WHERE game=? AND result='pending' ORDER BY id DESC LIMIT 1",
                    (g["id"],)).fetchone()
    if not p or not p["event_id"] or rounds.pick_flag(con, p):
        return 0, []
    f = db.get_fixture(con, p["event_id"])
    ko = rounds.parse_utc(f["commence"] if f else p["kickoff"])
    if not (ko + dt.timedelta(hours=2) <= now <= ko + dt.timedelta(days=3)):
        return 0, []
    if quota_low(con):
        log("credits low: scores pull skipped")
        return 0, []
    sc = oddsapi.scores(p["league"]).get(p["event_id"])
    if not sc or not sc["completed"]:
        return 0, []
    opp_name = sc["away"] if p["team"] == sc["home"] else sc["home"]
    mine, theirs = sc["scores"].get(p["team"]), sc["scores"].get(opp_name)
    if mine is None or theirs is None:
        log("completed game without a usable score; set the result by hand")
        return 0, []
    won = mine > theirs
    db.apply_result(con, p, "through" if won else "out")
    word = "won" if won else ("drew" if mine == theirs else "lost")
    line = f"LMS round {p['round']}: {p['team']} {word} {mine}-{theirs} v {opp_name}. "
    line += "Through." if won else "You're out. Press New game on the page when the next one starts."
    return 0, [line] if db.claim(con, f"result:{p['id']}") else []


JOBS = {"odds": job_odds, "alerts": job_alerts, "results": job_results}


def main(argv):
    if len(argv) != 2 or argv[1] not in JOBS:
        print("usage: python -m app.jobs <odds|alerts|results>", file=sys.stderr)
        return 2
    con = db.connect(os.path.join(os.environ.get("DATA_DIR", "/data"), "lms.db"))
    store_quota(con)
    try:
        rc, lines = JOBS[argv[1]](con, utcnow())
    except OddsError as e:
        log(f"{argv[1]} failed: {e}")
        return 1
    except Exception as e:  # keep the key out of tracebacks: class name only
        log(f"{argv[1]} failed: {type(e).__name__}")
        return 1
    if lines:
        print("\n".join(lines))
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
