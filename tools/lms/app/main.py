"""Last Man Standing picker: ranked safest pick per round, used teams, results (FastAPI, server-rendered, no login)."""
import datetime as dt
import logging
import os
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import db, oddsapi, ranking, rounds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
HERE = Path(__file__).parent
DB_PATH = os.path.join(os.environ.get("DATA_DIR", "/data"), "lms.db")
LOW_QUOTA = 40

app = FastAPI(title="lms", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


def utcnow():
    return dt.datetime.now(rounds.UTC)


def back(msg=""):
    return RedirectResponse("/" + (f"?msg={quote(msg)}" if msg else ""), status_code=303)


def age(iso, now):
    if not iso:
        return None
    mins = int((now - rounds.parse_utc(iso)).total_seconds() // 60)
    if mins < 90:
        return f"{max(mins, 0)} min ago"
    if mins < 60 * 36:
        return f"{mins // 60} h ago"
    return f"{mins // 1440} days ago"


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
def index(request: Request, msg: str = ""):
    now = utcnow()
    con = db.connect(DB_PATH)
    try:
        g = db.current_game(con)
        ctx = {"request": request, "msg": msg[:200], "has_key": bool(oddsapi.key()), "game": g,
               "out": bool(g and g["status"] == "out"), "rnd": None, "rows": [], "top": [], "pick": None,
               "flag": None, "deadline": None, "overridden": False, "history": [], "used": [],
               "now": now, "fmt_local": rounds.fmt_local, "parse_utc": rounds.parse_utc}
        for k in ("quota_remaining", "quota_used"):
            ctx[k] = db.kv_get(con, k)
        ctx["quota_age"] = age(db.kv_get(con, "quota_at"), now)
        try:
            ctx["quota_low"] = int(ctx["quota_remaining"]) < LOW_QUOTA
        except (TypeError, ValueError):
            ctx["quota_low"] = False
        ctx["odds_age"] = age(db.kv_get(con, "odds_at"), now)
        if g:
            ctx["history"] = [{"game": x, "picks": db.picks(con, x["id"])} for x in db.games(con)]
            ctx["used"] = sorted(db.used_teams(con, g["id"]))
            ctx["team_names"] = db.team_names(con)
            ctx["earlier"] = [p for p in db.picks(con, g["id"]) if p["round"] == "earlier"]
        if g and not ctx["out"]:
            rnd = rounds.current_round(con, g["id"], now)
            ctx["rnd"] = rnd
            if rnd:
                fx, rows = rounds.round_state(con, rnd, g["id"])
                dl, ov = rounds.deadline_for(con, rnd)
                pick = db.round_pick(con, g["id"], rnd)
                ctx.update(rows=rows, top=ranking.top(rows, 3), pick=pick, deadline=dl, overridden=ov,
                           flag=rounds.pick_flag(con, pick),
                           pool="Championship" if rounds.CHAMP in {f["league"] for f in fx}
                           else "League One + League Two",
                           deadline_local=rounds.to_london(dl).strftime("%Y-%m-%dT%H:%M") if dl else "")
        return templates.TemplateResponse(request, "index.html", ctx)
    finally:
        con.close()


def _game_or_none(con):
    g = db.current_game(con)
    return g


@app.post("/newgame")
def newgame():
    con = db.connect(DB_PATH)
    try:
        db.new_game(con)
    finally:
        con.close()
    return back("New game started. Used teams are empty.")


@app.post("/pick")
def pick(event_id: str = Form(...), team: str = Form(...)):
    now = utcnow()
    con = db.connect(DB_PATH)
    try:
        g = db.current_game(con)
        if not g or g["status"] != "active":
            return back("No active game.")
        f = db.get_fixture(con, event_id)
        if not f or team not in (f["home"], f["away"]):
            return back("Unknown fixture or team.")
        if team in db.used_teams(con, g["id"]):
            return back(f"{team} is already used in this game.")
        if team in db.voided_teams(con, g["id"], f["round"]):
            return back(f"{team} was voided this round.")
        existing = db.round_pick(con, g["id"], f["round"])
        if existing and existing["result"] != "pending":
            return back("This round already has a settled pick; use the manual override.")
        if existing:
            db.delete_pick(con, existing["id"])
        db.add_pick(con, g["id"], f["round"], team, f["league"], event_id, f["commence"])
    finally:
        con.close()
    return back(f"Recorded {team}.")


def _pick_action(pick_id, fn):
    con = db.connect(DB_PATH)
    try:
        p = db.get_pick(con, pick_id)
        if not p:
            return back("Pick not found.")
        return fn(con, p)
    finally:
        con.close()


@app.post("/void")
def void(pick_id: int = Form(...)):
    def fn(con, p):
        db.apply_result(con, p, "void", 1)
        return back(f"{p['team']} voided: pick again.")
    return _pick_action(pick_id, fn)


@app.post("/postponed")
def postponed(pick_id: int = Form(...), action: str = Form(...)):
    def fn(con, p):
        res = {"through": "through", "repick": "void", "out": "out"}.get(action)
        if not res:
            return back("Unknown action.")
        db.apply_result(con, p, res, 1)
        return back("Postponed pick resolved: " + action + ".")
    return _pick_action(pick_id, fn)


@app.post("/result")
def result(pick_id: int = Form(...), result: str = Form(...)):
    def fn(con, p):
        if result not in ("through", "out", "void", "pending"):
            return back("Unknown result.")
        db.apply_result(con, p, result, 1)
        return back("Result set by hand.")
    return _pick_action(pick_id, fn)


@app.post("/out")
def imout(round: str = Form(...)):
    con = db.connect(DB_PATH)
    try:
        g = db.current_game(con)
        if not g:
            return back("No game.")
        p = db.round_pick(con, g["id"], round)
        if p:
            db.apply_result(con, p, "out", 1)
        else:
            db.set_game_out(con, g["id"], round)
    finally:
        con.close()
    return back("Marked out.")


@app.post("/deadline")
def deadline(round: str = Form(...), when: str = Form("")):
    con = db.connect(DB_PATH)
    try:
        if not when.strip():
            db.set_deadline_override(con, round, None)
            return back("Deadline back to the default.")
        try:
            local = dt.datetime.strptime(when.strip(), "%Y-%m-%dT%H:%M")
        except ValueError:
            return back("Bad date.")
        db.set_deadline_override(con, round, rounds.fmt_utc(rounds.from_london(local)))
    finally:
        con.close()
    return back("Deadline saved.")


@app.post("/used")
def used(team: str = Form(...)):
    team = team.strip()[:60]
    con = db.connect(DB_PATH)
    try:
        g = db.current_game(con)
        if not g or not team:
            return back("No game or no team.")
        known = {n.casefold(): n for n in db.team_names(con)}
        name = known.get(team.casefold())
        if not name:
            return back(f"'{team}' is not a team name from the stored fixtures; pick one from the list.")
        if name in db.used_teams(con, g["id"]):
            return back(f"{name} is already marked used.")
        team = name
        db.add_pick(con, g["id"], "earlier", team, result="through", manual=1)
    finally:
        con.close()
    return back(f"{team} marked used.")


@app.post("/unused")
def unused(pick_id: int = Form(...)):
    def fn(con, p):
        if p["round"] == "earlier":
            db.delete_pick(con, p["id"])
        return back("Removed.")
    return _pick_action(pick_id, fn)
