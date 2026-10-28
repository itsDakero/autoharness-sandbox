"""Garmin login, token store, sync and backfill.

The only module that imports garminconnect (lazily, inside functions), so the parsers below can be
unit tested without the library. Nothing here logs tokens or the password.
"""
import logging
import os
import threading
import time
from datetime import date, timedelta

from . import db, logic, running

log = logging.getLogger("fitness.garmin")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
TOKEN_DIR = os.path.join(DATA_DIR, "garmin")
TOKEN_FILE = os.path.join(TOKEN_DIR, "garmin_tokens.json")  # written by garminconnect 0.3.x

BACKFILL_DAYS = 730
DAYS_PER_RUN = 30
ACT_CHUNK_DAYS = 90
SPLITS_PER_RUN = 20
RUN_DETAILS_PER_RUN = 20
DETAIL_MAX_FAILS = 3
CALL_DELAY_S = 2.0
RELOGIN_MIN_S = 6 * 3600
BACKOFF_429_S = 24 * 3600
MAX_CONSECUTIVE_ERRORS = 5


class NotConfigured(Exception):
    pass


class MfaNeeded(Exception):
    pass


class Backoff(Exception):
    pass


def email_password():
    return os.environ.get("GARMIN_EMAIL", "").strip(), os.environ.get("GARMIN_PASSWORD", "")


def configured():
    e, p = email_password()
    return bool(e and p)


# ---------------------------------------------------------------- parsers (pure)

def _g(d, *path):
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and -len(d) <= p < len(d):
            d = d[p]
        else:
            return None
    return d


def parse_sleep(d):
    return {
        "sleep_s": logic.num(_g(d, "dailySleepDTO", "sleepTimeSeconds")),
        "sleep_score": logic.num(_g(d, "dailySleepDTO", "sleepScores", "overall", "value")),
        "rhr": logic.num(_g(d, "restingHeartRate")),
        "hrv_avg": logic.num(_g(d, "avgOvernightHrv")),
        "hrv_status": _g(d, "hrvStatus"),
    }


def parse_hrv(d):
    return {"hrv_avg": logic.num(_g(d, "hrvSummary", "lastNightAvg")),
            "hrv_status": _g(d, "hrvSummary", "status")}


def parse_summary(d):
    return {"rhr": logic.num(_g(d, "restingHeartRate")),
            "bb_max": logic.num(_g(d, "bodyBatteryHighestValue")),
            "bb_min": logic.num(_g(d, "bodyBatteryLowestValue")),
            "stress_avg": logic.num(_g(d, "averageStressLevel"))}


def parse_readiness(d):
    items = d if isinstance(d, list) else [d]
    scores = [logic.num(i.get("score")) for i in items if isinstance(i, dict)]
    scores = [s for s in scores if s is not None]
    return {"readiness": scores[-1] if scores else None}


def parse_training_status(d):
    data = _g(d, "mostRecentTrainingStatus", "latestTrainingStatusData")
    if not isinstance(data, dict) or not data:
        return {"training_status": None, "acute_load": None}
    dev = next((v for v in data.values() if isinstance(v, dict)), {})
    phrase = dev.get("trainingStatusFeedbackPhrase")
    return {"training_status": str(phrase) if phrase else None,
            "acute_load": logic.num(_g(dev, "acuteTrainingLoadDTO", "dailyTrainingLoadAcute"))}


def parse_vo2(d):
    """{date: vo2max} from a get_max_metrics_range() response of unknown nesting."""
    out = {}

    def walk(x):
        if isinstance(x, dict):
            cd = x.get("calendarDate")
            v = logic.num(x.get("vo2MaxPreciseValue")) or logic.num(x.get("vo2MaxValue"))
            if isinstance(cd, str) and v:
                out.setdefault(cd[:10], v)
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(d)
    return out


def parse_weights(d):
    """{date: (kg, body_fat_pct)} from a get_body_composition() response."""
    out = {}
    lst = _g(d, "dateWeightList")
    for e in lst if isinstance(lst, list) else []:
        if not isinstance(e, dict):
            continue
        cd, w = e.get("calendarDate"), logic.num(e.get("weight"))
        if not isinstance(cd, str) or not w:
            continue
        out[cd[:10]] = (w / 1000.0 if w > 300 else w, logic.num(e.get("bodyFat")))
    return out


def parse_activity(a):
    if not isinstance(a, dict) or a.get("activityId") is None:
        return None
    return {
        "id": int(a["activityId"]),
        "start_local": a.get("startTimeLocal"),
        "type": _g(a, "activityType", "typeKey"),
        "name": a.get("activityName"),
        "distance_m": logic.num(a.get("distance")),
        "duration_s": logic.num(a.get("duration")),
        "avg_hr": logic.num(a.get("averageHR")),
        "max_hr": logic.num(a.get("maxHR")),
        "cadence": logic.num(a.get("averageRunningCadenceInStepsPerMinute", a.get("averageRunningCadenceInSteps"))),
        "aerobic_te": logic.num(a.get("aerobicTrainingEffect")),
        "anaerobic_te": logic.num(a.get("anaerobicTrainingEffect")),
        "training_load": logic.num(a.get("activityTrainingLoad")),
    }


def parse_laps(d):
    out = []
    lst = _g(d, "lapDTOs")
    for lap in lst if isinstance(lst, list) else []:
        if isinstance(lap, dict):
            out.append({"distance_m": logic.num(lap.get("distance")), "duration_s": logic.num(lap.get("duration")),
                        "avg_hr": logic.num(lap.get("averageHR")),
                        "cadence": logic.num(lap.get("averageRunCadence"))})
    return out


def parse_hr_zones(d):
    """[(zone, seconds, low_bpm)] for zones 1-5 from get_activity_hr_in_timezones (list, or dict holding one)."""
    if isinstance(d, dict):
        d = next((v for v in d.values() if isinstance(v, list)), [])
    out = {}
    for item in d if isinstance(d, list) else []:
        if not isinstance(item, dict):
            continue
        z, secs = logic.num(item.get("zoneNumber")), logic.num(item.get("secsInZone"))
        if z is None or secs is None or int(z) != z or not 1 <= int(z) <= 5 or secs < 0:
            continue
        out[int(z)] = (int(z), secs, logic.num(item.get("zoneLowBoundary")))
    return [out[z] for z in sorted(out)]


def parse_samples(d):
    """[(t seconds, distance m, hr or None)] from get_activity_details; [] when the layout is unknown."""
    desc = _g(d, "metricDescriptors")
    rows = _g(d, "activityDetailMetrics")
    if not isinstance(desc, list) or not isinstance(rows, list):
        return []
    idx = {}
    for m in desc:
        if isinstance(m, dict) and isinstance(m.get("key"), str) and isinstance(m.get("metricsIndex"), int):
            idx[m["key"]] = m["metricsIndex"]
    if "sumDuration" not in idx:
        return []

    def at(metrics, key):
        i = idx.get(key)
        return logic.num(metrics[i]) if i is not None and 0 <= i < len(metrics) else None

    out = []
    for r in rows:
        m = _g(r, "metrics")
        if not isinstance(m, list):
            continue
        t = at(m, "sumDuration")
        if t is None:
            continue
        out.append((t, at(m, "sumDistance"), at(m, "directHeartRate")))
    return out


# ---------------------------------------------------------------- login

_lock = threading.Lock()   # guards _api / _pending
_api = None                # logged-in Garmin client
_pending = None            # Garmin client waiting for an MFA code


def _kind(exc):
    """'429' | 'auth' | 'other' for a garminconnect exception (library imported lazily)."""
    from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return "429"
    if isinstance(exc, GarminConnectAuthenticationError):
        return "auth"
    return "other"


def _token_login():
    from garminconnect import Garmin
    api = Garmin()
    api.login(TOKEN_DIR)
    return api


def get_api(con):
    """A logged-in client. Credential logins: only when no usable token store, max one per 6 h."""
    global _api, _pending
    with _lock:
        until = float(db.get_state(con, "backoff_until", "0") or 0)
        if time.time() < until:
            raise Backoff("backing off until " + time.strftime("%Y-%m-%d %H:%M", time.localtime(until)))
        if _api is not None:
            return _api
        if not configured():
            raise NotConfigured("not configured")
        if _pending is not None:
            raise MfaNeeded("MFA code needed")
        os.makedirs(TOKEN_DIR, mode=0o700, exist_ok=True)
        if os.path.exists(TOKEN_FILE):
            try:
                _api = _token_login()
                return _api
            except Exception as e:  # noqa: BLE001
                if _kind(e) != "auth":
                    raise   # network / 429 / 403: no credential login on top of that
                log.warning("saved tokens rejected; falling back to a credential login")
        last = float(db.get_state(con, "last_login_attempt", "0") or 0)
        if time.time() - last < RELOGIN_MIN_S:
            raise Backoff("credential login waits (max one per 6 h); next try after "
                          + time.strftime("%H:%M", time.localtime(last + RELOGIN_MIN_S)))
        db.set_state(con, "last_login_attempt", time.time())
        from garminconnect import Garmin
        email, password = email_password()
        api = Garmin(email, password, return_on_mfa=True)
        status, _ = api.login(None)
        if status == "needs_mfa":
            _pending = api
            db.set_state(con, "mfa_needed", "1")
            raise MfaNeeded("MFA code needed")
        api.client.dump(TOKEN_DIR)
        _api = _token_login()
        return _api


def mfa_pending():
    return _pending is not None


def submit_mfa(con, code):
    """Finish a pending MFA login. Returns (ok, message)."""
    global _api, _pending
    with _lock:
        if _pending is None:
            return False, "No MFA login is waiting."
        api = _pending
        try:
            api.resume_login({}, code.strip())
            api.client.dump(TOKEN_DIR)
        except Exception as e:  # noqa: BLE001
            still = bool(getattr(api.client, "_mfa_pending", False))
            if not still:   # issue #416: state gone, rebuild next time
                _pending = None
                db.set_state(con, "mfa_needed", "0")
                db.set_state(con, "last_login_attempt", "0")
                return False, f"Code rejected ({type(e).__name__}). Press Sync now to request a new code."
            return False, f"Code rejected ({type(e).__name__}). Try again."
        _pending = None
        _api = api
        db.set_state(con, "mfa_needed", "0")
        db.set_state(con, "last_error", "")
        return True, "Logged in."


def drop_api():
    global _api
    with _lock:
        _api = None


# ---------------------------------------------------------------- sync

class _Fetcher:
    def __init__(self):
        self.calls = 0
        self.ok = 0
        self.errors = 0
        self.consec = 0
        self.last_err = ""

    def call(self, fn, *args):
        if self.calls:
            time.sleep(CALL_DELAY_S)
        self.calls += 1
        try:
            r = fn(*args)
        except Exception as e:  # noqa: BLE001
            if _kind(e) in ("429", "auth"):
                raise
            self.errors += 1
            self.consec += 1
            self.last_err = f"{getattr(fn, '__name__', 'call')}: {type(e).__name__}: {str(e)[:120]}"
            log.warning("fetch failed: %s", self.last_err)
            if self.consec >= MAX_CONSECUTIVE_ERRORS:
                raise RuntimeError(f"{self.consec} fetch errors in a row ({self.last_err})") from e
            return None
        self.ok += 1
        self.consec = 0
        return r


def _day(con, f, api, d):
    ds = d.isoformat()
    for kind, fn, parse in (
        ("summary", api.get_user_summary, parse_summary),
        ("sleep", api.get_sleep_data, parse_sleep),
        ("hrv", api.get_hrv_data, parse_hrv),
        ("readiness", api.get_training_readiness, parse_readiness),
        ("trainstatus", api.get_training_status, parse_training_status),
    ):
        data = f.call(fn, ds)
        if data is None:
            continue
        db.save_raw(con, kind, ds, data)
        db.upsert_daily(con, ds, **parse(data))
    con.commit()


def _range_metrics(con, f, api, start, end):
    s, e = start.isoformat(), end.isoformat()
    data = f.call(api.get_max_metrics_range, s, e)
    if data is not None:
        db.save_raw(con, "vo2", f"{s}:{e}", data)
        for d, v in parse_vo2(data).items():
            db.upsert_daily(con, d, vo2max=v)
    data = f.call(api.get_body_composition, s, e)   # empty without scales: fine
    if data is not None:
        db.save_raw(con, "bodycomp", f"{s}:{e}", data)
        for d, (kg, fat) in parse_weights(data).items():
            db.upsert_daily(con, d, weight_kg=kg, body_fat_pct=fat)
    con.commit()


def _activities(con, f, api, start, end):
    data = f.call(api.get_activities_by_date, start.isoformat(), end.isoformat(), None, "asc")
    n = 0
    for a in data or []:
        p = parse_activity(a)
        if p is None:
            continue
        aid = p.pop("id")
        db.upsert_activity(con, aid, **p)
        n += 1
    con.commit()
    return n


def _splits(con, f, api):
    rows = con.execute(
        "SELECT id FROM activities a WHERE NOT EXISTS "
        "(SELECT 1 FROM raw WHERE kind='splits' AND key=CAST(a.id AS TEXT)) "
        "ORDER BY start_local DESC LIMIT ?", (SPLITS_PER_RUN,)).fetchall()
    for r in rows:
        data = f.call(api.get_activity_splits, str(r["id"]))
        if data is None:
            continue
        db.save_raw(con, "splits", r["id"], data)
        db.replace_laps(con, r["id"], parse_laps(data))
        con.commit()


def _store_efforts(con, aid, samples):
    """Best efforts from samples, else from the laps table. Returns the source used."""
    usable = [x for x in samples if x[1] is not None]
    if len(usable) >= 2:
        db.replace_best_efforts(con, aid, running.best_efforts(usable), "details")
        return "details"
    laps = con.execute("SELECT distance_m, duration_s FROM laps WHERE activity_id=?", (aid,)).fetchall()
    db.replace_best_efforts(con, aid, running.best_efforts_from_laps(laps), "laps")
    return "laps"


def _run_details(con, f, api):
    """HR zones, HR histogram and best efforts for running activities without a 'details' raw row.

    Newest first, at most RUN_DETAILS_PER_RUN per sync. A failed call is counted per activity and ends the
    step for this run; after DETAIL_MAX_FAILS the activity is skipped for good (laps-based efforts only).
    """
    rows = con.execute(
        "SELECT id FROM activities a WHERE type LIKE '%running%' AND NOT EXISTS "
        "(SELECT 1 FROM raw WHERE kind='details' AND key=CAST(a.id AS TEXT)) "
        "ORDER BY start_local DESC LIMIT ?", (RUN_DETAILS_PER_RUN,)).fetchall()
    for r in rows:
        aid = r["id"]
        zdata = f.call(api.get_activity_hr_in_timezones, str(aid))
        ddata = f.call(api.get_activity_details, str(aid), 2000, 0) if zdata is not None else None
        if zdata is None or ddata is None:
            key = f"detail_fail:{aid}"
            fails = int(db.get_state(con, key, "0") or 0) + 1
            db.set_state(con, key, fails)
            if fails >= DETAIL_MAX_FAILS:
                if zdata is not None:
                    db.save_raw(con, "hrzones", aid, zdata)
                    db.replace_zones(con, aid, parse_hr_zones(zdata))
                _store_efforts(con, aid, [])
                db.save_raw(con, "details", aid, None)
                con.commit()
            break
        db.save_raw(con, "hrzones", aid, zdata)
        keep = ddata if isinstance(ddata, dict) else {}
        db.save_raw(con, "details", aid, {"metricDescriptors": keep.get("metricDescriptors"),
                                          "activityDetailMetrics": keep.get("activityDetailMetrics")})
        samples = parse_samples(ddata)
        db.replace_zones(con, aid, parse_hr_zones(zdata))
        db.replace_hr_hist(con, aid, running.hr_histogram(samples).items())
        _store_efforts(con, aid, samples)
        con.commit()


def _pbs(con, f, api):
    data = f.call(api.get_personal_record)
    if data is None:
        return
    db.save_raw(con, "pbs", "latest", data)
    for dist, secs, when in logic.pbs_from_garmin(data):
        db.merge_pb(con, dist, secs, when)
    con.commit()


def rematch_fiit(con):
    acts = [dict(r) for r in con.execute("SELECT id, start_local, type FROM activities")]
    for r in con.execute("SELECT id, date, start_time FROM fiit WHERE match_manual=0").fetchall():
        aid = logic.match_fiit(r["date"], r["start_time"], acts)
        con.execute("UPDATE fiit SET activity_id=? WHERE id=?", (aid, r["id"]))
    con.commit()


def run_sync(con):
    """One sync run (blocking; call from a worker thread, under the caller's lock)."""
    try:
        if not configured():
            raise NotConfigured("not configured")
        api = get_api(con)
        f = _Fetcher()
        today = date.today()

        # Activities: the last 7 days every run; older chunks until BACKFILL_DAYS.
        _activities(con, f, api, today - timedelta(days=7), today)
        a_cur = db.get_state(con, "act_cursor")
        a_cur = date.fromisoformat(a_cur) if a_cur else today - timedelta(days=7)
        limit = today - timedelta(days=BACKFILL_DAYS)
        if a_cur > limit:
            start = max(a_cur - timedelta(days=ACT_CHUNK_DAYS), limit)
            _activities(con, f, api, start, a_cur)
            db.set_state(con, "act_cursor", start.isoformat())

        # Daily metrics: today and the 3 days before it (late sleep/HRV), then the backfill.
        for back in range(3, -1, -1):
            _day(con, f, api, today - timedelta(days=back))
        _range_metrics(con, f, api, today - timedelta(days=7), today)
        cur = db.get_state(con, "backfill_cursor")
        cur = date.fromisoformat(cur) if cur else today - timedelta(days=3)
        if cur > limit:
            start = max(cur - timedelta(days=DAYS_PER_RUN), limit)
            d = cur - timedelta(days=1)
            while d >= start:
                _day(con, f, api, d)
                d -= timedelta(days=1)
            _range_metrics(con, f, api, start, cur - timedelta(days=1))
            db.set_state(con, "backfill_cursor", start.isoformat())

        _splits(con, f, api)
        _pbs(con, f, api)
        rematch_fiit(con)
        try:
            _run_details(con, f, api)
        except Exception as e:  # noqa: BLE001  (a details problem must not fail the sync, except 429/auth)
            if type(e).__module__.startswith("garminconnect") and _kind(e) in ("429", "auth"):
                raise
            log.warning("run details step failed: %s: %s", type(e).__name__, str(e)[:120])
        if f.ok == 0 and f.errors:
            raise RuntimeError(f"nothing fetched ({f.last_err})")
        db.set_state(con, "last_ok", time.time())
        db.set_state(con, "last_error", f"{f.errors} fetch error(s), last: {f.last_err}" if f.errors else "")
        return "ok"
    except NotConfigured:
        db.set_state(con, "last_error", "not configured")
        raise
    except MfaNeeded:
        db.set_state(con, "last_error", "MFA code needed")
        raise
    except Backoff as e:
        db.set_state(con, "last_error", str(e))
        raise
    except Exception as e:  # noqa: BLE001
        kind = _kind(e) if type(e).__module__.startswith("garminconnect") else "other"
        msg = f"{type(e).__name__}: {str(e)[:200]}"
        if kind == "429":
            db.set_state(con, "backoff_until", time.time() + BACKOFF_429_S)
            msg = "Garmin rate-limited us (429); backing off 24 h. " + msg
        elif kind == "auth":
            drop_api()
        log.error("sync failed: %s", msg)
        db.set_state(con, "last_error", msg)
        raise
