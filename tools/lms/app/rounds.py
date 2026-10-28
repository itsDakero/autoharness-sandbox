"""Time helpers (Europe/London by hand: no tzdata in the slim image), rounds, pools and the page state."""
import datetime as dt

from . import db, ranking

CHAMP = "soccer_efl_champ"
LEAGUES = (CHAMP, "soccer_england_league1", "soccer_england_league2")
LOWER = LEAGUES[1:]
DEADLINE_LEAD = dt.timedelta(minutes=30)
FMT = "%Y-%m-%dT%H:%M:%SZ"
UTC = dt.timezone.utc


def parse_utc(s):
    return dt.datetime.strptime(s, FMT).replace(tzinfo=UTC)


def fmt_utc(d):
    return d.astimezone(UTC).strftime(FMT)


def _last_sunday(year, month):
    d = dt.date(year, month, 31)
    return d - dt.timedelta(days=(d.weekday() + 1) % 7)


def london_offset(utc):
    """UK summer time: from 01:00 UTC on the last Sunday of March to 01:00 UTC on the last Sunday of October."""
    y = utc.year
    start = dt.datetime.combine(_last_sunday(y, 3), dt.time(1), tzinfo=UTC)
    end = dt.datetime.combine(_last_sunday(y, 10), dt.time(1), tzinfo=UTC)
    return dt.timedelta(hours=1) if start <= utc < end else dt.timedelta(0)


def to_london(utc):
    """Aware UTC datetime -> naive London wall-clock datetime."""
    return (utc + london_offset(utc)).replace(tzinfo=None)


def from_london(naive):
    """Naive London wall-clock datetime -> aware UTC."""
    for off in (dt.timedelta(hours=1), dt.timedelta(0)):
        cand = (naive - off).replace(tzinfo=UTC)
        if london_offset(cand) == off:
            return cand
    return (naive - dt.timedelta(hours=1)).replace(tzinfo=UTC)


def round_key(utc):
    """Tue/Wed/Thu -> that Tuesday; Fri/Sat/Sun/Mon -> that Friday (London time). Key = block start date."""
    d = to_london(utc).date()
    wd = d.weekday()  # Mon 0 .. Sun 6
    if wd in (1, 2, 3):
        start = d - dt.timedelta(days=wd - 1)
    else:
        start = d - dt.timedelta(days=(wd - 4) % 7)
    return start.isoformat()


def pool_leagues(fixtures):
    """Championship if the round has any Championship fixture, else League One + League Two."""
    if any(f["league"] == CHAMP for f in fixtures):
        return (CHAMP,)
    return LOWER


def pool_fixtures(fixtures):
    lg = pool_leagues(fixtures)
    return [f for f in fixtures if f["league"] in lg]


def default_deadline(fixtures):
    pf = pool_fixtures(fixtures)
    if not pf:
        return None
    return min(parse_utc(f["commence"]) for f in pf) - DEADLINE_LEAD


def current_round(con, game_id, now):
    if game_id is not None:
        p = db.pending_pick(con, game_id)
        if p:
            return p["round"]
    cutoff = fmt_utc(now - dt.timedelta(hours=4))
    r = con.execute("SELECT MIN(round) m FROM fixtures WHERE gone=0 AND commence>?", (cutoff,)).fetchone()
    return r["m"]


def deadline_for(con, key):
    fx = db.round_fixtures(con, key)
    ov = db.get_deadline_override(con, key)
    if ov:
        return parse_utc(ov), True
    return default_deadline(fx), False


def round_state(con, key, game_id):
    """Ranked rows, used/voided sets for one round."""
    fx = pool_fixtures(db.round_fixtures(con, key))
    used = db.used_teams(con, game_id) if game_id else set()
    voided = db.voided_teams(con, game_id, key) if game_id else set()
    odds = db.odds_by_event(con, [f["event_id"] for f in fx])
    rows = ranking.rank(fx, odds, used, voided)
    return fx, rows


def pick_flag(con, pick):
    """Why a pending pick looks postponed, or None: fixture gone from /events, or moved out of its block."""
    if not pick or pick["result"] not in ("pending", "postponed") or not pick["event_id"]:
        return None
    f = db.get_fixture(con, pick["event_id"])
    if f is None:
        return None
    if f["gone"]:
        return "the fixture is no longer listed by the odds provider"
    if f["round"] != pick["round"]:
        return "the kick-off moved outside this round"
    return None


def fmt_local(utc, with_date=True):
    d = to_london(utc)
    return d.strftime("%a %d %b %H:%M" if with_date else "%H:%M")
