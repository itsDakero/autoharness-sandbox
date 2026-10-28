"""FPL page: projections, my squad, minutes overrides, solver plan (FastAPI, server-rendered, no login)."""
import datetime as dt
import logging
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from collector import store

from . import data, projections as pj, solve, squad

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
HERE = Path(__file__).parent

app = FastAPI(title="fpl", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")


@app.on_event("startup")
def _startup():
    store.ensure_dirs()


def back(msg=""):
    return RedirectResponse("/" + (f"?msg={quote(msg)}" if msg else ""), status_code=303)


def age_text(iso, now):
    try:
        mins = int((now - dt.datetime.fromisoformat(iso)).total_seconds() // 60)
    except (TypeError, ValueError):
        return None
    if mins < 90:
        return f"{max(mins, 0)} min ago"
    if mins < 60 * 36:
        return f"{mins // 60} h ago"
    return f"{mins // 1440} days ago"


@app.get("/healthz")
def healthz():
    return PlainTextResponse("ok")


def local(iso):
    try:
        return dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone().strftime("%a %d %b %H:%M")
    except ValueError:
        return str(iso)


def team_grid(teams, gws, next_gw, now):
    """Teams x gameweeks grid from the newest team goals file, or None when there is no model yet."""
    tm = data.read_team_model()
    if tm is None:
        return None
    cells = {}
    for r in tm["rows"]:
        bold = r["source"] == "market"
        for tid, f, a, c in ((r["team_h"], r["xg_h"], r["xg_a"], r["cs_h"]), (r["team_a"], r["xg_a"], r["xg_h"], r["cs_a"])):
            cells.setdefault(int(tid), {}).setdefault(int(r["gw"]), []).append(
                {"text": f"{f:.1f}\u2013{a:.1f} \u00b7 {c * 100:.0f}%", "market": bold})
    grid = [{"team": name, "cells": [cells.get(tid, {}).get(g, []) for g in gws]}
            for tid, name in sorted(teams.items(), key=lambda kv: str(kv[1]))]
    st = tm["status"]
    gen = tm["generated_at"]
    return {"grid": grid, "age": age_text(gen.isoformat(), now) if gen else None, "params": st.get("params", "default"),
            "unmapped": st.get("unmapped") or [], "market": st.get("market"), "ratings": st.get("ratings")}


@app.get("/", response_class=HTMLResponse)
def index(request: Request, msg: str = ""):
    now = data.utcnow()
    settings = data.read_settings()
    ctx = {"request": request, "msg": msg[:200], "settings": settings, "inp": None, "now": now, "local": local,
           "latest": solve.read_latest(), "running": solve.running_since(), "age": lambda i: age_text(i, now)}
    plan = ctx["latest"].get("plan")
    ctx["plan_items"] = sorted(((int(k), v) for k, v in plan.items()), key=lambda kv: kv[0]) if isinstance(plan, dict) else []
    inp = data.load_inputs()
    if inp is None:
        return templates.TemplateResponse(request, "index.html", ctx)
    next_gw = inp["next_gw"]
    ctx["inp"] = inp
    ev = next((e for e in inp["events"] if e["id"] == next_gw), None)
    ctx["deadline"] = local(ev["deadline_time"]) if ev else None
    names = {int(p["id"]): p.get("web_name") for p in inp["players"]}
    teams = {int(t["id"]): t.get("short_name") for t in inp["teams"]}
    pos = {1: "GKP", 2: "DEF", 3: "MID", 4: "FWD"}
    pinfo = {int(p["id"]): f"{p.get('web_name')} ({teams.get(int(p['team']), '?')} {pos.get(int(p['element_type']), '?')})"
             for p in inp["players"]}
    ctx["names"] = names
    ctx["pinfo"] = pinfo
    ctx["datalist"] = sorted(f"{v} #{k}" for k, v in pinfo.items())
    gws = pj.gw_range(next_gw, settings["horizon"])
    ctx["gws"] = gws
    try:
        rows, info = solve.build_projection(inp, settings, now)
        info.pop("own_rows", None)
        by = {}
        for r in rows:
            by.setdefault(r["element"], {})[r["gw"]] = r
        table = []
        for el, per in by.items():
            tot = sum(per.get(g, {"pts": 0})["pts"] for g in gws)
            table.append({"el": el, "name": pinfo.get(el, el), "per": [per.get(g, {"pts": 0.0})["pts"] for g in gws],
                          "mins": per.get(next_gw, {"xmins": 0.0})["xmins"], "total": tot})
        table.sort(key=lambda x: -x["total"])
        ctx["proj"] = table[:40]
        ctx["model_cols"] = None
        try:
            ex = data.read_model_extras()
            if ex is not None:
                fpl = {r["element"]: r["pts"] for r in pj.build_fpl_ep(
                    inp["players"], pj.fixture_scales(inp["fixtures"]), inp["history"], next_gw, settings["horizon"])
                    if r["gw"] == next_gw}
                for r in ctx["proj"]:
                    m = ex["rows"].get((r["el"], next_gw))
                    r["model"], r["p10"], r["q90"] = (m["pts"], m["p10"], m["q90"]) if m else (None, None, None)
                    r["fpl"] = fpl.get(r["el"])
                ctx["model_cols"] = {"age": age_text(ex["generated_at"].isoformat(), now) if ex["generated_at"] else "?"}
        except Exception:  # the comparison columns are optional: leave them out
            ctx["model_cols"] = None
        ctx["pinfo_src"] = info
        ctx["src_age"] = age_text(info["generated_at"], now) if info["source"] != pj.OWN_SOURCE else "computed now"
    except Exception as e:  # a bad projection file must not take the page down
        ctx["proj"] = []
        ctx["pinfo_src"] = None
        ctx["proj_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    try:
        ctx["tm"] = team_grid(teams, gws, next_gw, now)
    except Exception as e:  # the team model must not take the page down
        ctx["tm"] = None
        ctx["tm_error"] = f"{type(e).__name__}: {str(e)[:150]}"
    ovs, bad = data.read_overrides()
    active, ignored = pj.split_overrides(ovs, list(names), next_gw, settings["horizon"])
    ctx["ov_active"], ctx["ov_ignored"], ctx["ov_bad"] = active, ignored, bad
    sq = squad.get(next_gw, inp["events"])
    ctx["squad"] = sq
    if sq.get("data"):
        ctx["picks"] = [{"name": names.get(p["element"], p["element"]), "pos": p["position"],
                         "cap": p.get("is_captain"), "vice": p.get("is_vice_captain")} for p in sq["data"]["picks"]]
    return templates.TemplateResponse(request, "index.html", ctx)


@app.post("/settings")
def save_settings(horizon: str = Form(""), secs: str = Form(""), decay_base: str = Form(""), ft_value: str = Form(""),
                  plan_chips: str = Form(""), projection_source: str = Form("auto")):
    s = data.clean_settings({"horizon": horizon, "secs": secs, "decay_base": decay_base, "ft_value": ft_value,
                             "plan_chips": plan_chips == "on", "projection_source": projection_source})
    data.write_json(data.WEB / "settings.json", s)
    return back("Settings saved.")


@app.post("/solve")
def run_solve():
    if solve.running_since():
        return back("A solve is already running.")
    try:
        subprocess.Popen([sys.executable, "-m", "web.jobs", "solve"], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as e:
        return back(f"Could not start the solver: {type(e).__name__}")
    return back("Solver started; reload in a few minutes.")


def _player_id(text, players):
    m = re.search(r"#(\d+)\s*$", text or "")
    if m:
        return int(m.group(1))
    hits = [int(p["id"]) for p in players if (p.get("web_name") or "").lower() == (text or "").strip().lower()]
    return hits[0] if len(hits) == 1 else None


@app.post("/overrides/add")
def add_override(player: str = Form(""), gw: str = Form(""), xmins: str = Form(""), note: str = Form("")):
    inp = data.load_inputs()
    if inp is None:
        return back("No data yet.")
    el = _player_id(player, inp["players"])
    if el is None:
        return back("Pick a player from the list.")
    try:
        g = int(gw)
    except ValueError:
        return back("Gameweek must be a number.")
    x = xmins.strip().lower()
    try:
        val = 0.0 if x == "out" else float(x)
    except ValueError:
        return back('Minutes must be a number or "out".')
    if not 0 <= val <= 120:
        return back("Minutes must be 0-120.")
    ovs, _ = data.read_overrides()
    ovs = [o for o in ovs if (o["element"], o["gw"]) != (el, g)]
    ovs.append({"element": el, "gw": g, "xmins": val, "note": note.strip()[:120].replace("\n", " "),
                "updated_at": data.utcnow().strftime("%Y-%m-%d %H:%M")})
    data.write_overrides(ovs)
    return back("Override saved.")


@app.post("/overrides/delete")
def delete_override(element: int = Form(...), gw: int = Form(...)):
    ovs, _ = data.read_overrides()
    data.write_overrides([o for o in ovs if (o["element"], o["gw"]) != (element, gw)])
    return back("Override removed.")
