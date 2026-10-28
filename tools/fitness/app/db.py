"""SQLite schema, migrations and small helpers (stdlib only)."""
import json
import sqlite3
import time

SCHEMA_VERSION = 5

# Migrations: index i upgrades version i -> i+1. Append, never edit.
MIGRATIONS = [
    """
    CREATE TABLE raw(
        kind TEXT NOT NULL, key TEXT NOT NULL, fetched_at TEXT NOT NULL, json TEXT,
        PRIMARY KEY(kind, key));
    CREATE TABLE daily(
        date TEXT PRIMARY KEY, sleep_s INTEGER, sleep_score REAL, hrv_avg REAL,
        hrv_status TEXT, rhr REAL, readiness REAL, bb_max REAL, bb_min REAL,
        stress_avg REAL, vo2max REAL, training_status TEXT, acute_load REAL,
        weight_kg REAL, body_fat_pct REAL);
    CREATE TABLE activities(
        id INTEGER PRIMARY KEY, start_local TEXT, type TEXT, name TEXT,
        distance_m REAL, duration_s REAL, avg_hr REAL, max_hr REAL, cadence REAL,
        aerobic_te REAL, anaerobic_te REAL, training_load REAL);
    CREATE INDEX activities_start ON activities(start_local);
    CREATE TABLE laps(
        activity_id INTEGER NOT NULL, idx INTEGER NOT NULL, distance_m REAL,
        duration_s REAL, avg_hr REAL, cadence REAL, PRIMARY KEY(activity_id, idx));
    CREATE TABLE checkins(
        date TEXT PRIMARY KEY, feeling INTEGER NOT NULL CHECK(feeling BETWEEN 1 AND 5),
        ill_neck INTEGER NOT NULL DEFAULT 0, ill_chest INTEGER NOT NULL DEFAULT 0,
        sore_legs INTEGER NOT NULL DEFAULT 0, stressed INTEGER NOT NULL DEFAULT 0,
        slept_badly INTEGER NOT NULL DEFAULT 0, note TEXT, updated_at TEXT);
    CREATE TABLE fiit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, start_time TEXT,
        type TEXT NOT NULL CHECK(type IN ('strength','hiit','mobility','other')),
        minutes INTEGER NOT NULL, effort INTEGER NOT NULL CHECK(effort BETWEEN 1 AND 10),
        srpe INTEGER NOT NULL, activity_id INTEGER, match_manual INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE pbs(
        distance TEXT PRIMARY KEY CHECK(distance IN ('5k','10k','half')),
        seconds INTEGER NOT NULL, date TEXT, source TEXT NOT NULL);
    CREATE TABLE sync_state(key TEXT PRIMARY KEY, value TEXT);
    INSERT INTO pbs(distance, seconds, date, source) VALUES
        ('5k', 1503, NULL, 'seed'), ('10k', 3130, NULL, 'seed'), ('half', 8090, NULL, 'seed');
    """,
    """
    CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    """
    CREATE TABLE activity_zones(
        activity_id INTEGER NOT NULL, zone INTEGER NOT NULL CHECK(zone BETWEEN 1 AND 5),
        seconds REAL NOT NULL, low_bpm REAL, PRIMARY KEY(activity_id, zone));
    CREATE TABLE activity_hr(
        activity_id INTEGER NOT NULL, bpm INTEGER NOT NULL, seconds REAL NOT NULL,
        PRIMARY KEY(activity_id, bpm));
    CREATE TABLE best_efforts(
        activity_id INTEGER NOT NULL,
        distance TEXT NOT NULL CHECK(distance IN ('400m','1k','1mi','5k','10k','half')),
        seconds REAL NOT NULL, source TEXT NOT NULL CHECK(source IN ('details','laps')),
        PRIMARY KEY(activity_id, distance));
    """,
    """
    CREATE TABLE summaries(
        week_start TEXT PRIMARY KEY, created_at TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('ok','skipped','failed')),
        model TEXT, facts TEXT, bullets TEXT, reason TEXT);
    """,
    """
    CREATE TABLE goals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        distance TEXT NOT NULL CHECK(distance IN ('5k','10k','half','custom')),
        distance_m REAL NOT NULL, target_s INTEGER NOT NULL, race_date TEXT,
        created_at TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 0);
    CREATE UNIQUE INDEX goals_one_active ON goals(active) WHERE active=1;
    CREATE TABLE plan_weeks(
        week_start TEXT PRIMARY KEY, goal_id INTEGER NOT NULL,
        phase TEXT NOT NULL CHECK(phase IN ('base','build','sharpen','taper')),
        week_no INTEGER NOT NULL, easy INTEGER NOT NULL DEFAULT 0, race_date TEXT);
    CREATE TABLE plan_days(
        date TEXT PRIMARY KEY, planned TEXT NOT NULL, adjusted TEXT, reason TEXT,
        updated_at TEXT NOT NULL);
    INSERT INTO goals(distance, distance_m, target_s, race_date, created_at, active)
        VALUES ('5k', 5000, 1439, NULL, '2026-10-26T00:00:00', 1);
    """,
]


def connect(path):
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    migrate(con)
    return con


def migrate(con):
    con.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
    row = con.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    cur = row["v"] if row and row["v"] is not None else 0
    for i in range(cur, len(MIGRATIONS)):
        con.executescript("BEGIN;" + MIGRATIONS[i] + ";COMMIT;")
        con.execute("INSERT INTO schema_version(version) VALUES (?)", (i + 1,))
        con.commit()


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def get_state(con, key, default=None):
    r = con.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_state(con, key, value):
    con.execute(
        "INSERT INTO sync_state(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, None if value is None else str(value)))
    con.commit()


def get_setting(con, key, default=None):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(con, key, value):
    con.execute(
        "INSERT INTO settings(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    con.commit()


def save_raw(con, kind, key, data):
    con.execute(
        "INSERT INTO raw(kind,key,fetched_at,json) VALUES(?,?,?,?) "
        "ON CONFLICT(kind,key) DO UPDATE SET fetched_at=excluded.fetched_at, json=excluded.json",
        (kind, str(key), now_iso(), json.dumps(data)))


_DAILY_COLS = ("sleep_s", "sleep_score", "hrv_avg", "hrv_status", "rhr", "readiness", "bb_max", "bb_min",
               "stress_avg", "vo2max", "training_status", "acute_load", "weight_kg", "body_fat_pct")


def upsert_daily(con, date, **fields):
    """Set the given columns; None values never overwrite existing data."""
    vals = {k: v for k, v in fields.items() if k in _DAILY_COLS and v is not None}
    con.execute("INSERT OR IGNORE INTO daily(date) VALUES(?)", (date,))
    if vals:
        sets = ", ".join(f"{k}=?" for k in vals)
        con.execute(f"UPDATE daily SET {sets} WHERE date=?", (*vals.values(), date))


_ACT_COLS = ("start_local", "type", "name", "distance_m", "duration_s", "avg_hr", "max_hr", "cadence",
             "aerobic_te", "anaerobic_te", "training_load")


def upsert_activity(con, act_id, **fields):
    vals = {k: fields.get(k) for k in _ACT_COLS}
    cols = ", ".join(_ACT_COLS)
    ph = ", ".join("?" for _ in _ACT_COLS)
    upd = ", ".join(f"{c}=excluded.{c}" for c in _ACT_COLS)
    con.execute(f"INSERT INTO activities(id, {cols}) VALUES(?, {ph}) ON CONFLICT(id) DO UPDATE SET {upd}",
                (act_id, *vals.values()))


def replace_laps(con, act_id, laps):
    con.execute("DELETE FROM laps WHERE activity_id=?", (act_id,))
    for i, lap in enumerate(laps):
        con.execute("INSERT INTO laps(activity_id, idx, distance_m, duration_s, avg_hr, cadence) "
                    "VALUES(?,?,?,?,?,?)",
                    (act_id, i, lap.get("distance_m"), lap.get("duration_s"), lap.get("avg_hr"),
                     lap.get("cadence")))


def replace_zones(con, act_id, zones):
    """zones: [(zone 1-5, seconds, low_bpm or None)]."""
    con.execute("DELETE FROM activity_zones WHERE activity_id=?", (act_id,))
    for z, secs, low in zones:
        con.execute("INSERT INTO activity_zones(activity_id, zone, seconds, low_bpm) VALUES(?,?,?,?)",
                    (act_id, int(z), float(secs), low))


def replace_hr_hist(con, act_id, hist):
    """hist: [(bpm, seconds)]."""
    con.execute("DELETE FROM activity_hr WHERE activity_id=?", (act_id,))
    for bpm, secs in hist:
        con.execute("INSERT INTO activity_hr(activity_id, bpm, seconds) VALUES(?,?,?)",
                    (act_id, int(bpm), float(secs)))


def replace_best_efforts(con, act_id, efforts, source):
    """efforts: {distance: seconds}."""
    con.execute("DELETE FROM best_efforts WHERE activity_id=?", (act_id,))
    for dist, secs in efforts.items():
        con.execute("INSERT INTO best_efforts(activity_id, distance, seconds, source) VALUES(?,?,?,?)",
                    (act_id, dist, float(secs), source))


def upsert_checkin(con, date, feeling, ill_neck=0, ill_chest=0, sore_legs=0, stressed=0,
                   slept_badly=0, note=""):
    con.execute(
        "INSERT INTO checkins(date,feeling,ill_neck,ill_chest,sore_legs,stressed,slept_badly,note,updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(date) DO UPDATE SET feeling=excluded.feeling, "
        "ill_neck=excluded.ill_neck, ill_chest=excluded.ill_chest, sore_legs=excluded.sore_legs, "
        "stressed=excluded.stressed, slept_badly=excluded.slept_badly, note=excluded.note, "
        "updated_at=excluded.updated_at",
        (date, int(feeling), int(bool(ill_neck)), int(bool(ill_chest)), int(bool(sore_legs)),
         int(bool(stressed)), int(bool(slept_badly)), note or "", now_iso()))
    con.commit()


def add_fiit(con, date, start_time, ftype, minutes, effort):
    minutes, effort = int(minutes), int(effort)
    cur = con.execute(
        "INSERT INTO fiit(date,start_time,type,minutes,effort,srpe) VALUES(?,?,?,?,?,?)",
        (date, start_time or None, ftype, minutes, effort, minutes * effort))
    con.commit()
    return cur.lastrowid


def merge_pb(con, distance, seconds, date):
    """Replace the stored PB only when Garmin's time is faster."""
    r = con.execute("SELECT seconds FROM pbs WHERE distance=?", (distance,)).fetchone()
    if r is None or seconds < r["seconds"]:
        con.execute(
            "INSERT INTO pbs(distance,seconds,date,source) VALUES(?,?,?, 'garmin') "
            "ON CONFLICT(distance) DO UPDATE SET seconds=excluded.seconds, date=excluded.date, "
            "source='garmin'", (distance, int(seconds), date))
        return True
    return False


def upsert_summary(con, week_start, status, model=None, facts=None, bullets=None, reason=None):
    """One row per week; a re-run replaces it. facts/bullets are stored as JSON text."""
    con.execute(
        "INSERT INTO summaries(week_start,created_at,status,model,facts,bullets,reason) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(week_start) DO UPDATE SET created_at=excluded.created_at, status=excluded.status, "
        "model=excluded.model, facts=excluded.facts, bullets=excluded.bullets, reason=excluded.reason",
        (week_start, now_iso(), status, model, None if facts is None else json.dumps(facts),
         None if bullets is None else json.dumps(bullets), reason))
    con.commit()


def active_goal(con):
    """The one active goal as a dict, or None."""
    r = con.execute("SELECT * FROM goals WHERE active=1").fetchone()
    return dict(r) if r else None


def insert_plan_weeks(con, goal_id, rows):
    """Append week rows; an existing week is never rewritten."""
    for w in rows:
        con.execute("INSERT OR IGNORE INTO plan_weeks(week_start,goal_id,phase,week_no,easy,race_date) "
                    "VALUES(?,?,?,?,?,?)",
                    (w["week_start"], goal_id, w["phase"], w["week_no"], w["easy"], w.get("race_date")))


def save_goal(con, goal, today):
    """New active goal + regenerated future weeks, in one transaction. goal: distance, distance_m,
    target_s, race_date. Past and current week rows and past plan_days are left alone."""
    from datetime import timedelta
    from . import plan
    this_monday = plan.monday(today)
    try:
        con.execute("UPDATE goals SET active=0 WHERE active=1")
        cur = con.execute(
            "INSERT INTO goals(distance,distance_m,target_s,race_date,created_at,active) VALUES(?,?,?,?,?,1)",
            (goal["distance"], goal["distance_m"], goal["target_s"], goal.get("race_date"), now_iso()))
        gid = cur.lastrowid
        con.execute("DELETE FROM plan_weeks WHERE week_start > ?", (this_monday.isoformat(),))
        con.execute("DELETE FROM plan_days WHERE date > ?", (today.isoformat(),))
        this = con.execute("SELECT week_no FROM plan_weeks WHERE week_start=?", (this_monday.isoformat(),)).fetchone()
        first, start_no = (this_monday + timedelta(weeks=1), this["week_no"] + 1) if this else (this_monday, 1)
        insert_plan_weeks(con, gid, plan.generate_weeks(goal, first, start_no))
        con.commit()
        return gid
    except Exception:
        con.rollback()
        raise


def upsert_plan_day(con, date, planned, adjusted, reason):
    con.execute(
        "INSERT INTO plan_days(date,planned,adjusted,reason,updated_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(date) DO UPDATE SET planned=excluded.planned, adjusted=excluded.adjusted, "
        "reason=excluded.reason, updated_at=excluded.updated_at",
        (date, planned, adjusted, reason, now_iso()))
    con.commit()
