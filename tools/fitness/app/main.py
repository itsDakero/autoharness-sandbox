"""Fitness: Garmin stats, morning check-in and FiiT log (FastAPI, server-rendered)."""
import asyncio
import contextlib
import logging
import os
import threading
import json
import time
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import analysis, db, feed, garmin, insights, logic, plan, running

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("fitness")

HERE = Path(__file__).parent
DB_PATH = os.path.join(garmin.DATA_DIR, "fitness.db")
SYNC_EVERY_S = 30 * 60
STALE_S = 3 * 3600
STARTED = time.time()
SYNC_LOCK = threading.Lock()
SUMMARY_LOCK = threading.Lock()

templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.globals.update(
    fmt_dur=logic.fmt_dur, fmt_pace=logic.fmt_pace, fmt_dist=logic.fmt_dist, num=logic.num,
    feel_colours=logic.FEEL_COLOURS)


def _dash(v, digits=0):
    f = logic.num(v)
    return "–" if f is None else f"{f:.{digits}f}"


templates.env.filters["dash"] = _dash


def get_con():
    con = db.connect(DB_PATH)
    try:
        yield con
    finally:
        con.close()


def do_sync():
    """Run one sync under the lock. Returns a short message."""
    if not SYNC_LOCK.acquire(blocking=False):
        return "sync already running"
    con = db.connect(DB_PATH)
    try:
        garmin.run_sync(con)
        return "sync finished"
    except garmin.NotConfigured:
        return "not configured"
    except garmin.MfaNeeded:
        return "MFA code needed"
    except garmin.Backoff as e:
        return str(e)
    except Exception as e:  # noqa: BLE001  (already logged + stored by run_sync)
        return f"sync failed: {type(e).__name__}"
    finally:
        con.close()
        SYNC_LOCK.release()


async def sync_loop():
    await asyncio.sleep(20)
    while True:
        if garmin.configured():
            await asyncio.to_thread(do_sync)
        await asyncio.sleep(SYNC_EVERY_S)


@contextlib.asynccontextmanager
async def lifespan(app):
    os.makedirs(garmin.DATA_DIR, exist_ok=True)
    con = db.connect(DB_PATH)
    if db.get_state(con, "mfa_needed") == "1":   # the pending login did not survive the restart
        db.set_state(con, "mfa_needed", "0")
        db.set_state(con, "last_login_attempt", "0")
    con.close()
    task = asyncio.create_task(sync_loop())
    yield
    task.cancel()


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")


def status(con):
    """Sync status for the banner and /healthz/sync."""
    ok = db.get_state(con, "last_ok")
    ok_f = float(ok) if ok else None
    err = db.get_state(con, "last_error", "") or ""
    until = float(db.get_state(con, "backoff_until", "0") or 0)
    s = {"configured": garmin.configured(), "mfa": garmin.mfa_pending(), "error": err,
         "last_ok": time.strftime("%Y-%m-%d %H:%M", time.localtime(ok_f)) if ok_f else None,
         "stale": (time.time() - (ok_f or STARTED)) > STALE_S,
         "backoff": time.strftime("%Y-%m-%d %H:%M", time.localtime(until)) if until > time.time() else None,
         "running": SYNC_LOCK.locked(), "backfill": db.get_state(con, "backfill_cursor")}
    if not s["configured"]:
        s["error"] = "not configured"
    return s


def render(request, name, con, status_code=200, **ctx):
    unit = "km" if request.query_params.get("unit") == "km" else "mi"
    other = "mi" if unit == "km" else "km"
    q = urlencode({**request.query_params, "unit": other})
    ctx.update(status=status(con), unit=unit, other_unit=other, unit_url=f"{request.url.path}?{q}",
               path=request.url.path)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def is_date(s):
    try:
        date.fromisoformat(s)
        return True
    except (TypeError, ValueError):
        return False


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/healthz/sync")
def healthz_sync(con=Depends(get_con)):
    s = status(con)
    if not s["configured"]:
        return PlainTextResponse("not configured", status_code=503)
    if s["stale"]:
        return PlainTextResponse(f"stale: last ok {s['last_ok'] or 'never'}; {s['error'] or 'no error'}"[:300],
                                 status_code=503)
    return PlainTextResponse("ok")


@app.post("/sync")
async def sync_now(request: Request):
    msg = await asyncio.to_thread(do_sync)
    return RedirectResponse(f"/?msg={msg}"[:200], status_code=303)


def load_analysis(con):
    """(series, summary) of training load; never raises on odd rows."""
    t = date.today()
    since = (t - timedelta(days=400)).isoformat()
    acts = [dict(r) for r in con.execute(
        "SELECT id, start_local, training_load FROM activities WHERE start_local >= ?", (since,))]
    fiit = [dict(r) for r in con.execute(
        "SELECT f.date AS date, f.srpe AS srpe, f.activity_id AS act_id, a.training_load AS act_load "
        "FROM fiit f LEFT JOIN activities a ON a.id=f.activity_id WHERE f.date >= ?", (since,))]
    return analysis.compute(acts, fiit, t)


def load_recovery(con, load_series):
    """Recovery context (bands, score, debt, consistency, warning); never raises on odd rows."""
    t = date.today()
    since = (t - timedelta(days=250)).isoformat()
    daily = con.execute("SELECT date, hrv_avg, rhr, sleep_s FROM daily WHERE date >= ?", (since,)).fetchall()
    checkins = con.execute("SELECT * FROM checkins WHERE date >= ?", (since,)).fetchall()
    raw = {r["key"]: r["json"] for r in con.execute(
        "SELECT key, json FROM raw WHERE kind='sleep' AND key >= ?", ((t - timedelta(days=13)).isoformat(),))}
    need = db.get_setting(con, "sleep_need_h")
    return analysis.recovery(daily, checkins, raw, need, load_series, t)


def load_running(con, unit="mi"):
    """Running analysis for Trends and PBs; never raises on odd rows (an empty result shows dashes)."""
    try:
        return running.load(con, date.today(), unit)
    except Exception:  # noqa: BLE001
        log.exception("running analysis failed")
        return None


def load_run_extras(con, a, laps):
    try:
        return running.load_run(con, a, laps, date.today())
    except Exception:  # noqa: BLE001
        log.exception("run analysis failed")
        return None


def load_plan(con, write=False, unit="mi", rec=None, load=None):
    """Plan context (goal, weeks, today's session). None with no active goal; {"error": ...} if it fails.
    write=True (Today and Plan pages) stores missing weeks and today's plan_days row; the feed passes False."""
    try:
        goal = db.active_goal(con)
        if goal is None:
            return None
        t = date.today()
        stored = [dict(r) for r in con.execute("SELECT * FROM plan_weeks ORDER BY week_start")]
        new = plan.missing_weeks(goal, stored, t)
        if new and write:
            db.insert_plan_weeks(con, goal["id"], new)
            con.commit()
        weeks = stored + new
        cur = plan.monday(t).isoformat()
        # data for done/missed, adjustments and bonus; each piece may be missing
        if rec is None or load is None:
            try:
                series, load = load_analysis(con)
                rec = load_recovery(con, series)
            except Exception:  # noqa: BLE001
                log.exception("plan: recovery failed")
                rec, load = None, None
        ti = t.isoformat()
        run_dates = {r["d"] for r in con.execute(
            "SELECT substr(start_local,1,10) AS d FROM activities WHERE type LIKE '%running%' AND start_local >= ?",
            (cur,))}
        fiit_dates = {r["d"] for r in con.execute("SELECT date AS d FROM fiit WHERE date >= ?", (cur,))}
        pdays = {r["date"]: dict(r) for r in con.execute("SELECT * FROM plan_days WHERE date >= ?", (cur,))}
        checkins = [dict(r) for r in con.execute(
            "SELECT * FROM checkins WHERE date >= ?", ((t - timedelta(days=8)).isoformat(),))]
        daily = con.execute("SELECT readiness FROM daily WHERE date=?", (ti,)).fetchone()
        pb = con.execute("SELECT seconds FROM pbs WHERE distance='5k'").fetchone()
        chips = (rec or {}).get("chips") or {}
        env = {"goal": goal, "today": t, "unit": unit, "run_dates": run_dates, "fiit_dates": fiit_dates,
               "pdays": pdays, "checkins": checkins,
               "checkin_today": next((c for c in checkins if c["date"] == ti), None),
               "readiness": logic.num(daily["readiness"]) if daily else None,
               "rec_score": logic.num(((rec or {}).get("score") or {}).get("score")),
               "warning": bool((rec or {}).get("warning")),
               "hrv_tone": (chips.get("hrv") or {}).get("tone"),
               "zone": ((load or {}).get("zone") or [None])[0],
               "pc": plan.paces(goal, pb["seconds"] if pb else None)}
        res = plan.compute(env, weeks)
        td = res.get("today")
        if write and td:
            db.upsert_plan_day(con, ti, td["planned"], td["adjusted_kind"], td["reason"])
        return res
    except Exception as e:  # noqa: BLE001
        log.exception("plan failed")
        return {"error": type(e).__name__}


@app.get("/plan", response_class=HTMLResponse)
def plan_page(request: Request, con=Depends(get_con)):
    unit = "km" if request.query_params.get("unit") == "km" else "mi"
    return render(request, "plan.html", con, plan=load_plan(con, True, unit),
                  today_iso=date.today().isoformat())


@app.get("/", response_class=HTMLResponse)
def today(request: Request, con=Depends(get_con)):
    t = date.today().isoformat()
    rows = con.execute("SELECT * FROM daily WHERE date >= ? ORDER BY date", ((date.today() - timedelta(days=40)).isoformat(),)).fetchall()
    cur = next((r for r in rows if r["date"] == t), None)
    metrics = []
    days14 = [(date.today() - timedelta(days=i)).isoformat() for i in range(13, -1, -1)]
    by_date = {r["date"]: r for r in rows}
    # better: 1 = higher is better, -1 = lower is better
    for label, key, digits, fmt, better in (
        ("Sleep", "sleep_s", 0, "dur", 1), ("Sleep score", "sleep_score", 0, None, 1),
        ("HRV", "hrv_avg", 0, None, 1), ("Resting HR", "rhr", 0, None, -1),
        ("Body Battery", "bb_max", 0, None, 1), ("Stress", "stress_avg", 0, None, -1),
    ):
        v = cur[key] if cur else None
        b7, b30 = logic.baseline(rows, key, t, 7), logic.baseline(rows, key, t, 30)
        show = (lambda x: logic.fmt_dur(x)) if fmt == "dur" else (lambda x: _dash(x, digits))
        if fmt == "dur":
            d7 = logic.delta_text(*(None if x is None else x / 60 for x in (logic.num(v), b7)))
            d7 = d7 if d7 == "–" else d7 + "m"
        else:
            d7 = logic.delta_text(v, b7)
        spark = [by_date[d][key] if d in by_date else None for d in days14]
        metrics.append({"label": label, "value": show(v), "b7": show(b7), "b30": show(b30), "d7": d7,
                        "tone": logic.delta_tone(v, b7, better), "spark": logic.svg_sparkline(spark),
                        "unit": {"hrv_avg": "ms", "rhr": "bpm"}.get(key, "")})
    readiness = logic.num(cur["readiness"]) if cur else None
    r7 = logic.baseline(rows, "readiness", t, 7)
    last = con.execute("SELECT vo2max, date FROM daily WHERE vo2max IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
    wt = con.execute("SELECT weight_kg, date FROM daily WHERE weight_kg IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()
    checkin = con.execute("SELECT * FROM checkins WHERE date=?", (t,)).fetchone()
    load_series, load = load_analysis(con)
    rec = load_recovery(con, load_series)
    for m, key in zip(metrics, ("sleep_s", "sleep_score", "hrv_avg", "rhr", "bb_max", "stress_avg")):
        m["band"] = rec["chips"].get({"hrv_avg": "hrv", "rhr": "rhr"}.get(key, ""))
    unit = "km" if request.query_params.get("unit") == "km" else "mi"
    return render(request, "today.html", con, load=load, rec=rec, plan=load_plan(con, True, unit, rec, load),
                  rec_band=analysis.score_band(rec["score"]["score"] if rec["score"] else None), metrics=metrics, vo2=last, weight=wt, checkin=checkin,
                  has_today=cur is not None, today=t, msg=request.query_params.get("msg", "")[:100],
                  training_status=cur["training_status"] if cur else None, readiness=readiness,
                  readiness_band=logic.readiness_band(readiness), readiness_d7=logic.delta_text(readiness, r7))


@app.get("/runs", response_class=HTMLResponse)
def runs(request: Request, con=Depends(get_con)):
    unit = "km" if request.query_params.get("unit") == "km" else "mi"
    acts = con.execute("SELECT * FROM activities WHERE type LIKE '%running%' ORDER BY start_local DESC LIMIT 200").fetchall()
    this_week = logic.week_start(date.today().isoformat())
    weekly = dict(logic.weekly_distance([dict(a) for a in acts], unit))
    prev = [weekly.get((date.fromisoformat(this_week) - timedelta(weeks=i)).isoformat(), 0.0) for i in range(1, 5)]
    week = {"dist": weekly.get(this_week, 0.0), "avg4": sum(prev) / 4,
            "runs": sum(1 for a in acts if (a["start_local"] or "")[:10] >= this_week)}
    longest = max((logic.num(a["distance_m"]) or 0 for a in acts), default=0)
    today = date.today()
    since = (date.fromisoformat(this_week) - timedelta(weeks=analysis.SUMMARY_WEEKS - 1)).isoformat()
    summary, streak = [], None
    try:
        wruns = [dict(r) for r in con.execute(
            "SELECT start_local, distance_m, duration_s FROM activities "
            "WHERE type LIKE '%running%' AND start_local >= ?", (since,))]
        wfiit = [dict(r) for r in con.execute("SELECT date FROM fiit WHERE date >= ?", (since,))]
        summary = analysis.weekly_summary(wruns, wfiit, today)
        streak = analysis.run_streak(_streak_runs(con, today), today)
    except Exception:
        log.exception("weekly summary failed")
        summary, streak = [], None
    return render(request, "runs.html", con, acts=acts, week=week, longest=longest, summary=summary, streak=streak)


def _streak_runs(con, today):
    since = (today - timedelta(weeks=60)).isoformat()
    return [dict(r) for r in con.execute(
        "SELECT start_local FROM activities WHERE type LIKE '%running%' AND start_local >= ?", (since,))]


@app.get("/runs/{act_id}", response_class=HTMLResponse)
def run_detail(request: Request, act_id: int, con=Depends(get_con)):
    a = con.execute("SELECT * FROM activities WHERE id=?", (act_id,)).fetchone()
    if a is None:
        return render(request, "error.html", con, status_code=404, message="No such activity.")
    laps = con.execute("SELECT * FROM laps WHERE activity_id=? ORDER BY idx", (act_id,)).fetchall()
    return render(request, "run.html", con, a=a, laps=laps, rx=load_run_extras(con, a, laps))


@app.get("/trends", response_class=HTMLResponse)
def trends(request: Request, con=Depends(get_con)):
    unit = "km" if request.query_params.get("unit") == "km" else "mi"
    since = (date.today() - timedelta(days=180)).isoformat()
    rows = con.execute("SELECT * FROM daily WHERE date >= ? ORDER BY date", (since,)).fetchall()
    markers = {}
    for c in con.execute("SELECT * FROM checkins WHERE date >= ?", (since,)).fetchall():
        flags = [n for n, k in (("above-neck", "ill_neck"), ("chest/fever", "ill_chest"), ("sore legs", "sore_legs"),
                                ("stressed", "stressed"), ("slept badly", "slept_badly")) if c[k]]
        tip = f"{c['date']}: feeling {c['feeling']}/5" + (f" ({', '.join(flags)})" if flags else "")
        markers[c["date"]] = (logic.FEEL_COLOURS.get(c["feeling"], "#888"), tip, bool(c["ill_neck"] or c["ill_chest"]))

    def series(key, sparse=False):
        pts = [(r["date"], r[key]) for r in rows]
        return [p for p in pts if p[1] is not None] if sparse else pts

    acts = [dict(r) for r in con.execute("SELECT type, start_local, distance_m FROM activities WHERE start_local >= ?", (since,))]
    weekly = logic.weekly_distance(acts, unit)
    load_series, _ = load_analysis(con)
    rec = load_recovery(con, load_series)
    charts = [
        analysis.svg_heatmap(load_series, date.today()),
        analysis.svg_load_chart(load_series),
        analysis.svg_strain_recovery_chart(load_series, rec["rec_series"]),
        analysis.svg_band_chart(rec["rhr_series"], "Resting HR (bpm)", " bpm", markers),
        analysis.svg_band_chart(rec["hrv_series"], "Overnight HRV (ms)", " ms", markers),
        logic.svg_line_chart(series("vo2max", True), "VO2max", markers),
        logic.svg_line_chart(weekly, f"Weekly running distance ({unit})"),
        logic.svg_line_chart(series("weight_kg", True), "Weight (kg)", markers),
    ]
    rn = load_running(con, unit)
    if rn:
        charts += [
            running.svg_zone_bars(rn["weekly_zones"]),
            logic.svg_line_chart(rn["ef_points"], "Aerobic efficiency of easy runs ((m/min)/bpm)"),
            logic.svg_line_chart(rn["cadence_points"], "Cadence of easy runs (steps/min)"),
            logic.svg_line_chart(rn["vo2_points"], "Effective VO2max per run"),
            running.svg_pace_curve(rn["curve_recent"], rn["curve_all"], unit),
        ]
    return render(request, "trends.html", con, charts=charts, acc=rec["accuracy"], rn=rn)


def _summary_facts(con, today):
    """The week's numbers for the model (None = no data)."""
    load_series, load_sum = load_analysis(con)
    rec = load_recovery(con, load_series)
    rn = load_running(con, "km")
    this_week = logic.week_start(today.isoformat())
    since = (date.fromisoformat(this_week) - timedelta(weeks=analysis.SUMMARY_WEEKS - 1)).isoformat()
    wruns = [dict(r) for r in con.execute(
        "SELECT start_local, distance_m, duration_s FROM activities "
        "WHERE type LIKE '%running%' AND start_local >= ?", (since,))]
    wfiit = [dict(r) for r in con.execute("SELECT date FROM fiit WHERE date >= ?", (since,))]
    weeks = analysis.weekly_summary(wruns, wfiit, today)
    streak = analysis.run_streak(_streak_runs(con, today), today)
    checkins = con.execute(
        "SELECT feeling, ill_neck, ill_chest, sore_legs, stressed, slept_badly FROM checkins "
        "WHERE date >= ? AND date <= ?", (this_week, today.isoformat())).fetchall()
    return insights.build_facts(load_series, load_sum, rec, rn, weeks, streak, checkins, today)


def _make_summary():
    """Build, ask, store. Returns (http status, text). Runs in a thread under SUMMARY_LOCK."""
    con = db.connect(DB_PATH)
    try:
        today = date.today()
        week = logic.week_start(today.isoformat())
        try:
            facts = _summary_facts(con, today)
        except Exception as e:  # noqa: BLE001
            log.exception("summary facts failed")
            db.upsert_summary(con, week, "failed", reason=f"could not build the numbers ({type(e).__name__})")
            return 500, "facts failed"
        if facts is None:
            return 204, ""
        try:
            text = insights.ask_model(facts)
        except insights.Offline as e:
            log.warning("summary skipped: %s", e)
            db.upsert_summary(con, week, "skipped", model=insights.MODEL, facts=facts,
                              reason="Mac mini unreachable: skipped this week")
            return 503, "Mac mini unreachable"
        except Exception as e:  # noqa: BLE001
            log.exception("summary model call failed")
            db.upsert_summary(con, week, "failed", model=insights.MODEL, facts=facts,
                              reason=f"model call failed ({type(e).__name__})")
            return 502, "model call failed"
        bullets = insights.parse_bullets(text)
        if len(bullets) < insights.MIN_BULLETS:
            db.upsert_summary(con, week, "failed", model=insights.MODEL, facts=facts,
                              reason="model reply unusable")
            return 502, "model reply unusable"
        db.upsert_summary(con, week, "ok", model=insights.MODEL, facts=facts, bullets=bullets)
        return 200, f"Fitness week of {week}\n" + "\n".join(f"- {b}" for b in bullets)
    finally:
        con.close()


def _run_summary():
    if not SUMMARY_LOCK.acquire(blocking=False):
        return 409, "already running"
    try:
        return _make_summary()
    finally:
        SUMMARY_LOCK.release()


@app.get("/api/feed.json")
def feed_json(con=Depends(get_con)):
    """Read-only summary for the dashboard's Hermes feed (no check-in notes, no raw Garmin data)."""
    return feed.feed_data(con, date.today(), load_analysis, load_recovery, lambda c: load_plan(c, False))


@app.post("/api/weekly-summary")
async def weekly_summary_api():
    code, text = await asyncio.to_thread(_run_summary)
    if code == 204:
        return Response(status_code=204)
    return PlainTextResponse(text, status_code=code)


@app.get("/insights", response_class=HTMLResponse)
def insights_page(request: Request, con=Depends(get_con)):
    items = []
    for r in con.execute("SELECT * FROM summaries ORDER BY week_start DESC LIMIT 52"):
        try:
            facts = json.loads(r["facts"]) if r["facts"] else None
            bullets = json.loads(r["bullets"]) if r["bullets"] else []
        except ValueError:
            facts, bullets = None, []
        items.append({"week_start": r["week_start"], "status": r["status"], "reason": r["reason"],
                      "model": r["model"], "bullets": bullets,
                      "facts": json.dumps(facts, indent=1, sort_keys=True) if facts else None})
    rec = load_recovery(con, load_analysis(con)[0])
    return render(request, "insights.html", con, items=items, acc=rec["accuracy"])


@app.get("/pbs", response_class=HTMLResponse)
def pbs(request: Request, con=Depends(get_con)):
    rows = {r["distance"]: r for r in con.execute("SELECT * FROM pbs")}
    return render(request, "pbs.html", con, pbs=[(d, rows.get(d)) for d in ("5k", "10k", "half")],
                  rn=load_running(con, "km" if request.query_params.get("unit") == "km" else "mi"),
                  half_label={"5k": "5 km", "10k": "10 km", "half": "Half marathon"})


@app.get("/checkin", response_class=HTMLResponse)
def checkin_form(request: Request, con=Depends(get_con)):
    d = request.query_params.get("date") or date.today().isoformat()
    if not is_date(d):
        d = date.today().isoformat()
    row = con.execute("SELECT * FROM checkins WHERE date=?", (d,)).fetchone()
    recent = con.execute("SELECT * FROM checkins ORDER BY date DESC LIMIT 14").fetchall()
    return render(request, "checkin.html", con, d=d, c=row, recent=recent, saved=request.query_params.get("saved"))


@app.post("/checkin")
def checkin_save(request: Request, date_: str = Form("", alias="date"), feeling: int = Form(0),
                 ill_neck: str = Form(""), ill_chest: str = Form(""), sore_legs: str = Form(""),
                 stressed: str = Form(""), slept_badly: str = Form(""), note: str = Form(""),
                 con=Depends(get_con)):
    if not is_date(date_) or not 1 <= feeling <= 5:
        return render(request, "error.html", con, status_code=400,
                      message="Pick a date and a feeling from 1 to 5.")
    db.upsert_checkin(con, date_, feeling, ill_neck, ill_chest, sore_legs, stressed, slept_badly, note[:1000])
    return RedirectResponse(f"/checkin?date={date_}&saved=1", status_code=303)


@app.get("/settings", response_class=HTMLResponse)
def settings_form(request: Request, con=Depends(get_con)):
    need = analysis.parse_need(db.get_setting(con, "sleep_need_h")) or analysis.SLEEP_NEED_DEFAULT_H
    try:
        st = running.settings(con)
    except Exception:  # noqa: BLE001
        log.exception("settings failed")
        st = {"max_hr_setting": None, "auto_max_hr": None, "max_hr": None, "zone_source": "maxhr"}
    goals = [dict(r) for r in con.execute("SELECT * FROM goals ORDER BY id DESC LIMIT 10")]
    return render(request, "settings.html", con, need=need, st=st, saved=request.query_params.get("saved"),
                  goal=db.active_goal(con), goals=goals)


@app.post("/settings/goal")
def goal_save(request: Request, distance: str = Form(""), custom_m: str = Form(""), target: str = Form(""),
              race_date: str = Form(""), con=Depends(get_con)):
    g, err = plan.parse_goal(distance, custom_m, target, race_date, date.today())
    if err:   # nothing is written on a 400
        return render(request, "error.html", con, status_code=400, message=err)
    db.save_goal(con, g, date.today())
    return RedirectResponse("/plan", status_code=303)


@app.post("/settings")
def settings_save(request: Request, sleep_need_h: str | None = Form(None), max_hr: str | None = Form(None),
                  zone_source: str | None = Form(None), con=Depends(get_con)):
    writes = []
    if sleep_need_h is not None:
        v = analysis.parse_need(sleep_need_h)
        if v is None:
            return render(request, "error.html", con, status_code=400,
                          message="Sleep need must be a number of hours from 4 to 12.")
        writes.append(("sleep_need_h", v))
    if max_hr is not None:
        mh = max_hr.strip()
        if mh and running.parse_max_hr(mh) is None:
            return render(request, "error.html", con, status_code=400,
                          message="Max HR must be a whole number from 100 to 230, or blank for automatic.")
        writes.append(("max_hr", mh))
    if zone_source is not None:
        if zone_source not in running.ZONE_SOURCES:
            return render(request, "error.html", con, status_code=400,
                          message="Zone source must be max HR or Garmin.")
        writes.append(("zone_source", zone_source))
    for key, val in writes:   # all fields validated above; nothing is written on a 400
        if key == "max_hr" and val == "":
            con.execute("DELETE FROM settings WHERE key='max_hr'")
        else:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, str(val)))
    con.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)


def _fiit_context(con):
    rows = con.execute("SELECT f.*, a.name AS act_name, a.type AS act_type, a.start_local AS act_start "
                       "FROM fiit f LEFT JOIN activities a ON a.id=f.activity_id "
                       "ORDER BY f.date DESC, f.id DESC LIMIT 60").fetchall()
    options = {}
    for r in rows:
        options[r["id"]] = con.execute(
            "SELECT id, name, type, start_local FROM activities WHERE substr(start_local,1,10)=? "
            "ORDER BY start_local", (r["date"],)).fetchall()
    return rows, options


@app.get("/fiit", response_class=HTMLResponse)
def fiit_page(request: Request, con=Depends(get_con)):
    rows, options = _fiit_context(con)
    return render(request, "fiit.html", con, rows=rows, options=options, today=date.today().isoformat())


@app.post("/fiit")
def fiit_add(request: Request, date_: str = Form("", alias="date"), start_time: str = Form(""),
             ftype: str = Form("", alias="type"), minutes: int = Form(0), effort: int = Form(0),
             con=Depends(get_con)):
    st = start_time.strip()
    st_ok = not st or (len(st) == 5 and st[2] == ":" and st[:2].isdigit() and st[3:].isdigit())
    if (not is_date(date_) or ftype not in ("strength", "hiit", "mobility", "other")
            or not 1 <= minutes <= 300 or not 1 <= effort <= 10 or not st_ok):
        return render(request, "error.html", con, status_code=400,
                      message="Check the date, type, minutes (1-300), effort (1-10) and start time (HH:MM).")
    db.add_fiit(con, date_, st, ftype, minutes, effort)
    garmin.rematch_fiit(con)
    return RedirectResponse("/fiit", status_code=303)


@app.post("/fiit/{fid}/match")
def fiit_match(fid: int, activity: str = Form(""), con=Depends(get_con)):
    if activity == "none":
        con.execute("UPDATE fiit SET activity_id=NULL, match_manual=1 WHERE id=?", (fid,))
    elif activity == "auto":
        con.execute("UPDATE fiit SET match_manual=0 WHERE id=?", (fid,))
        con.commit()
        garmin.rematch_fiit(con)
    elif activity.isdigit():
        con.execute("UPDATE fiit SET activity_id=?, match_manual=1 WHERE id=?", (int(activity), fid))
    con.commit()
    return RedirectResponse("/fiit", status_code=303)


@app.post("/fiit/{fid}/delete")
def fiit_delete(fid: int, con=Depends(get_con)):
    con.execute("DELETE FROM fiit WHERE id=?", (fid,))
    con.commit()
    return RedirectResponse("/fiit", status_code=303)


@app.get("/garmin/mfa", response_class=HTMLResponse)
def mfa_form(request: Request, con=Depends(get_con)):
    return render(request, "mfa.html", con, message="")


@app.post("/garmin/mfa")
async def mfa_submit(request: Request, code: str = Form(""), con=Depends(get_con)):
    code = code.strip()
    if not code.isdigit() or not 4 <= len(code) <= 10:
        return render(request, "mfa.html", con, status_code=400, message="Enter the numeric code from Garmin.")
    ok, msg = await asyncio.to_thread(garmin.submit_mfa, con, code)
    if ok:
        asyncio.get_running_loop().run_in_executor(None, do_sync)
        return RedirectResponse("/?msg=logged in, syncing", status_code=303)
    return render(request, "mfa.html", con, status_code=400, message=msg)
