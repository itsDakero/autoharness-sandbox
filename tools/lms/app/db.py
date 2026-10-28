"""SQLite for LMS (stdlib only). WAL + busy_timeout so cron jobs and page clicks never hit "database is locked"."""
import os
import sqlite3
import time

MIGRATIONS = [
    """
    CREATE TABLE games(
        id INTEGER PRIMARY KEY, started TEXT NOT NULL,
        out_round TEXT, status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','out')));
    CREATE TABLE picks(
        id INTEGER PRIMARY KEY, game INTEGER NOT NULL REFERENCES games(id),
        round TEXT NOT NULL, team TEXT NOT NULL, league TEXT, event_id TEXT, kickoff TEXT,
        result TEXT NOT NULL DEFAULT 'pending'
            CHECK(result IN ('pending','through','out','void','postponed')),
        manual INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
    CREATE INDEX picks_game ON picks(game, round);
    CREATE TABLE fixtures(
        event_id TEXT PRIMARY KEY, league TEXT NOT NULL, home TEXT NOT NULL, away TEXT NOT NULL,
        commence TEXT NOT NULL, round TEXT NOT NULL, gone INTEGER NOT NULL DEFAULT 0, seen_at TEXT NOT NULL);
    CREATE INDEX fixtures_round ON fixtures(round);
    CREATE TABLE odds(
        event_id TEXT NOT NULL, bookmaker TEXT NOT NULL, home REAL NOT NULL, draw REAL NOT NULL,
        away REAL NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY(event_id, bookmaker));
    CREATE TABLE rounds(key TEXT PRIMARY KEY, deadline TEXT);
    CREATE TABLE kv(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE sent(key TEXT PRIMARY KEY, at TEXT NOT NULL);
    """,
]


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    if path != ":memory:":
        con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    migrate(con)
    return con


def migrate(con):
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    for i in range(ver, len(MIGRATIONS)):
        with con:
            for stmt in MIGRATIONS[i].split(";"):
                if stmt.strip():
                    con.execute(stmt)
            con.execute(f"PRAGMA user_version={i + 1}")


# kv and sent flags
def kv_get(con, key, default=None):
    r = con.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def kv_set(con, key, value):
    con.execute("INSERT INTO kv(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)))
    con.commit()


def claim(con, key):
    """Set a sent flag. True only for the one caller that set it (no repeats, even with overlapping runs)."""
    cur = con.execute("INSERT OR IGNORE INTO sent(key,at) VALUES(?,?)", (key, now()))
    con.commit()
    return cur.rowcount == 1


def is_sent(con, key):
    return con.execute("SELECT 1 FROM sent WHERE key=?", (key,)).fetchone() is not None


# games and picks
def current_game(con):
    return con.execute("SELECT * FROM games ORDER BY id DESC LIMIT 1").fetchone()


def new_game(con):
    cur = con.execute("INSERT INTO games(started,status) VALUES(?, 'active')", (now(),))
    con.commit()
    return cur.lastrowid


def games(con):
    return con.execute("SELECT * FROM games ORDER BY id DESC").fetchall()


def set_game_out(con, game_id, rnd):
    con.execute("UPDATE games SET status='out', out_round=? WHERE id=?", (rnd, game_id))
    con.commit()


def set_game_active(con, game_id):
    con.execute("UPDATE games SET status='active', out_round=NULL WHERE id=?", (game_id,))
    con.commit()


def picks(con, game_id):
    return con.execute("SELECT * FROM picks WHERE game=? ORDER BY round DESC, id DESC", (game_id,)).fetchall()


def get_pick(con, pick_id):
    return con.execute("SELECT * FROM picks WHERE id=?", (pick_id,)).fetchone()


def pending_pick(con, game_id):
    return con.execute("SELECT * FROM picks WHERE game=? AND result IN ('pending','postponed')"
                       " ORDER BY id DESC LIMIT 1", (game_id,)).fetchone()


def round_pick(con, game_id, rnd):
    """The live pick of a round (not a voided one)."""
    return con.execute("SELECT * FROM picks WHERE game=? AND round=? AND result!='void'"
                       " ORDER BY id DESC LIMIT 1", (game_id, rnd)).fetchone()


def add_pick(con, game_id, rnd, team, league=None, event_id=None, kickoff=None, result="pending", manual=0):
    cur = con.execute(
        "INSERT INTO picks(game,round,team,league,event_id,kickoff,result,manual,created_at)"
        " VALUES(?,?,?,?,?,?,?,?,?)", (game_id, rnd, team, league, event_id, kickoff, result, manual, now()))
    con.commit()
    return cur.lastrowid


def set_pick_result(con, pick_id, result, manual=0):
    con.execute("UPDATE picks SET result=?, manual=? WHERE id=?", (result, manual, pick_id))
    con.commit()


def delete_pick(con, pick_id):
    con.execute("DELETE FROM picks WHERE id=?", (pick_id,))
    con.commit()


def used_teams(con, game_id):
    return {r["team"] for r in con.execute(
        "SELECT team FROM picks WHERE game=? AND result!='void'", (game_id,))}


def voided_teams(con, game_id, rnd):
    return {r["team"] for r in con.execute(
        "SELECT team FROM picks WHERE game=? AND round=? AND result='void'", (game_id, rnd))}


def apply_result(con, pick, result, manual=0):
    """Set a pick's result and keep the game's in/out state in step."""
    set_pick_result(con, pick["id"], result, manual)
    g = con.execute("SELECT * FROM games WHERE id=?", (pick["game"],)).fetchone()
    if result == "out":
        set_game_out(con, g["id"], pick["round"])
    elif g["status"] == "out" and g["out_round"] == pick["round"]:
        set_game_active(con, g["id"])


# fixtures and odds
def upsert_fixture(con, ev, rnd):
    con.execute(
        "INSERT INTO fixtures(event_id,league,home,away,commence,round,gone,seen_at) VALUES(?,?,?,?,?,?,0,?)"
        " ON CONFLICT(event_id) DO UPDATE SET league=excluded.league, home=excluded.home, away=excluded.away,"
        " commence=excluded.commence, round=excluded.round, gone=0, seen_at=excluded.seen_at",
        (ev["id"], ev["league"], ev["home"], ev["away"], ev["commence"], rnd, now()))


def mark_gone(con, league, keep_ids, after):
    """Future fixtures of a league that /events no longer lists."""
    q = "SELECT event_id FROM fixtures WHERE league=? AND gone=0 AND commence>?"
    for r in con.execute(q, (league, after)).fetchall():
        if r["event_id"] not in keep_ids:
            con.execute("UPDATE fixtures SET gone=1 WHERE event_id=?", (r["event_id"],))
    con.commit()


def team_names(con):
    """Every team name seen in stored fixtures, sorted."""
    names = set()
    for r in con.execute("SELECT home, away FROM fixtures"):
        names.update((r["home"], r["away"]))
    return sorted(names)


def get_fixture(con, event_id):
    return con.execute("SELECT * FROM fixtures WHERE event_id=?", (event_id,)).fetchone()


def round_fixtures(con, rnd, include_gone=False):
    q = "SELECT * FROM fixtures WHERE round=?" + ("" if include_gone else " AND gone=0") + " ORDER BY commence"
    return con.execute(q, (rnd,)).fetchall()


def store_odds(con, event_id, lines):
    """Replace the stored lines of one event: [(bookmaker, h, d, a)]."""
    t = now()
    with con:
        con.execute("DELETE FROM odds WHERE event_id=?", (event_id,))
        for bk, h, d, a in lines:
            con.execute("INSERT INTO odds(event_id,bookmaker,home,draw,away,fetched_at) VALUES(?,?,?,?,?,?)",
                        (event_id, bk, h, d, a, t))


def odds_by_event(con, ids):
    out = {}
    for i in ids:
        out[i] = [(r["home"], r["draw"], r["away"]) for r in
                  con.execute("SELECT home,draw,away FROM odds WHERE event_id=?", (i,))]
    return out


def get_deadline_override(con, rnd):
    r = con.execute("SELECT deadline FROM rounds WHERE key=?", (rnd,)).fetchone()
    return r["deadline"] if r and r["deadline"] else None


def set_deadline_override(con, rnd, value):
    con.execute("INSERT INTO rounds(key,deadline) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET deadline=excluded.deadline",
                (rnd, value))
    con.commit()
