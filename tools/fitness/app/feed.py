"""Read-only summary of today for GET /api/feed.json (the dashboard turns it into Hermes's personal.json).

Never includes check-in note text, raw Garmin JSON, facts, settings or tokens. A part that fails is None
and is logged; the function itself never raises because of odd rows."""
import json
import logging

from . import logic

log = logging.getLogger("uvicorn.error")


def _part(name, fn):
    try:
        return fn()
    except Exception:  # noqa: BLE001
        log.exception("feed part %s failed", name)
        return None


def _round(v, digits=1):
    f = logic.num(v)
    return None if f is None else round(f, digits)


def todays_session(con, load_plan):
    """Today's planned session (read-only), or None with no goal / no plan. No check-in text."""
    p = load_plan(con)
    t = p.get("today") if p else None
    if not t:
        return None
    return {"phase": p["phase"], "week_no": p["week_no"], "kind": t["kind"], "title": t["title"],
            "target": t["target"], "adjusted": bool(t["adjusted"]), "reason": t["reason"]}


def feed_data(con, today, load_analysis=None, load_recovery=None, load_plan=None):
    """today: a date. load_analysis(con) -> (series, summary); load_recovery(con, series) -> dict."""
    t = today.isoformat()
    out = {"date": t, "readiness": None, "recovery_score": None, "illness_warning": None,
           "form_zone": None, "checked_in_today": None, "last_activities": [], "weekly_summary": None,
           "todays_session": None}

    def readiness():
        r = con.execute("SELECT readiness FROM daily WHERE date=?", (t,)).fetchone()
        v = logic.num(r["readiness"]) if r else None
        if v is None:
            return None
        band = logic.readiness_band(v)
        return {"value": v, "band": band[0] if band else None}
    out["readiness"] = _part("readiness", readiness)

    series = summary = None
    if load_analysis:
        res = _part("load", lambda: load_analysis(con))
        if res:
            series, summary = res
    if summary:
        out["form_zone"] = _part("form_zone", lambda: summary["zone"][0] if summary.get("zone") else None)
    if load_recovery and series is not None:
        rec = _part("recovery", lambda: load_recovery(con, series))
        if rec:
            out["recovery_score"] = _part("recovery_score", lambda: _round(rec["score"]["score"], 0) if rec.get("score") else None)
            out["illness_warning"] = _part("illness_warning", lambda: bool(rec.get("warning")))

    out["checked_in_today"] = _part(
        "checkin", lambda: con.execute("SELECT 1 FROM checkins WHERE date=?", (t,)).fetchone() is not None)

    def acts():
        rows = con.execute(
            "SELECT start_local, type, distance_m, duration_s, training_load FROM activities "
            "ORDER BY start_local DESC LIMIT 3").fetchall()
        res = []
        for r in rows:
            d, s = logic.num(r["distance_m"]), logic.num(r["duration_s"])
            res.append({"date": (r["start_local"] or "")[:10], "type": r["type"],
                        "distance_km": None if d is None else round(d / 1000, 2),
                        "duration_min": None if s is None else round(s / 60),
                        "training_load": _round(r["training_load"])})
        return res
    out["last_activities"] = _part("activities", acts) or []

    def weekly():
        r = con.execute("SELECT week_start, status, bullets, reason FROM summaries "
                        "ORDER BY week_start DESC LIMIT 1").fetchone()
        if not r:
            return None
        bullets = json.loads(r["bullets"]) if r["bullets"] else None
        return {"week_start": r["week_start"], "status": r["status"], "bullets": bullets, "reason": r["reason"]}
    out["weekly_summary"] = _part("weekly_summary", weekly)
    if load_plan:
        out["todays_session"] = _part("todays_session", lambda: todays_session(con, load_plan))
    return out
