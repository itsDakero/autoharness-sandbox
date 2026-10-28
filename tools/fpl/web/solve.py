"""Projections (source choice + minutes overrides) and the open-fpl-solver run. State in /data/solver/latest.json."""
import csv
import datetime as dt
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

from collector import store

from . import data, projections as pj, squad

SOLVER_DIR = Path(os.environ.get("SOLVER_DIR", "/opt/solver"))
LATEST = data.SOLVER / "latest.json"
SETTINGS_OUT = data.SOLVER / "settings.json"
RUNNING = data.WEB / "running.json"
POS = {1: "G", 2: "D", 3: "M", 4: "F"}


class SolveError(Exception):
    """A one-line reason; the job prints it on stderr and exits 1."""


class NoData(Exception):
    """Nothing to do yet (no collector data, no team id): the job says so and exits 0."""


def build_projection(inp, settings, now=None):
    """-> (rows with overrides applied, info). info: source, generated_at, note, overrides_active/ignored/bad."""
    now = now or data.utcnow()
    next_gw, horizon = inp["next_gw"], settings["horizon"]
    players = inp["players"]
    scales = pj.fixture_scales(inp["fixtures"])
    cand, note = pj.pick_source(data.list_candidates(), settings["projection_source"], next_gw, now)
    if cand is None:
        rows = pj.build_fpl_ep(players, scales, inp["history"], next_gw, horizon)
        info = {"source": pj.OWN_SOURCE, "generated_at": now.isoformat(), "note": note}
    else:
        gws = set(pj.gw_range(next_gw, horizon))
        rows = [r for r in data.read_projection_file(cand["path"]) if r["gw"] in gws]
        info = {"source": cand["source"], "generated_at": cand["generated_at"].isoformat(), "note": note}
    ovs, bad = data.read_overrides()
    active, ignored = pj.split_overrides(ovs, [int(p["id"]) for p in players], next_gw, horizon)
    forms = {int(p["id"]): pj.num(p.get("form")) for p in players}
    teams = {int(p["id"]): int(p["team"]) for p in players}
    rows = pj.apply_overrides(rows, active, forms, scales, teams)
    info.update(overrides_active=len(active), overrides_ignored=len(ignored), overrides_bad=len(bad), own_rows=cand is None)
    return rows, info


def solver_csv(inp, rows, path):
    """The solio format: ID,Name,Pos,Value,Team,<gw>_Pts,<gw>_xMins."""
    gws = sorted({r["gw"] for r in rows})
    by = {}
    for r in rows:
        by.setdefault(r["element"], {})[r["gw"]] = r
    team_names = {int(t["id"]): t.get("short_name") or str(t["id"]) for t in inp["teams"]}
    cols = ["ID", "Name", "Pos", "Value", "Team"] + [f"{g}_{k}" for g in gws for k in ("Pts", "xMins")]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for p in inp["players"]:
            el = int(p["id"])
            if el not in by:
                continue
            line = [el, p.get("web_name") or el, POS.get(int(p["element_type"]), "M"),
                    f"{int(p['now_cost']) / 10:.1f}", team_names.get(int(p["team"]), "")]
            for g in gws:
                r = by[el].get(g)
                line += [f"{r['pts']:.3f}", f"{r['xmins']:.1f}"] if r else ["0", "0"]
            w.writerow(line)
    return gws


def solver_settings(settings, tid, gws, chips_left):
    limits, allowed = pj.chip_settings(chips_left, gws, settings["plan_chips"])
    return {"datasource": "homelab", "team_data": "id", "team_id": tid, "horizon": settings["horizon"],
            "secs": settings["secs"], "decay_base": settings["decay_base"], "ft_value": settings["ft_value"],
            "chip_limits": limits, "allowed_chip_gws": allowed, "use_wc": [], "use_bb": [], "use_fh": [], "use_tc": [],
            "export_image": False, "verbose": False}


def parse_plan(csv_path):
    """Result CSV -> {gw: {...}} with names; tolerant of missing columns."""
    import pandas as pd
    df = pd.read_csv(csv_path)
    df["chip"] = df["chip"].fillna("") if "chip" in df else ""
    plan = {}
    for gw, g in df.groupby("week"):
        gw = int(gw)

        def names(mask):
            return [str(n) for n in g[mask]["name"].tolist()]
        squad_rows = g[(g["lineup"] > 0.5) | (g["bench"] >= 0)]
        cap = g[g["captain"] > 0.5]["name"].tolist()
        vice = g[g["vicecaptain"] > 0.5]["name"].tolist()
        chips = sorted({str(c) for c in g["chip"].tolist() if str(c)})
        bench = squad_rows[squad_rows["bench"] >= 0].sort_values("bench")["name"].tolist()
        plan[str(gw)] = {"out": names(g["transfer_out"] > 0.5), "in": names(g["transfer_in"] > 0.5),
                         "captain": cap[0] if cap else None, "vice": vice[0] if vice else None,
                         "chip": ", ".join(chips) or None, "bench": [str(b) for b in bench],
                         "lineup": [str(n) for n in squad_rows[squad_rows["lineup"] > 0.5]["name"].tolist()]}
    return plan


def read_latest():
    d = data.read_json(LATEST, {})
    return d if isinstance(d, dict) else {}


def run_solver(config_path, timeout):
    env = {**os.environ, "PYTHONPATH": str(SOLVER_DIR)}
    try:
        p = subprocess.run([sys.executable, "solve.py", "--config", str(config_path)], cwd=SOLVER_DIR / "run", env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SolveError(f"solver timed out after {timeout} s")
    except OSError as e:
        raise SolveError(f"could not start the solver: {type(e).__name__}")
    if p.returncode != 0:
        tail = (p.stderr or p.stdout).strip().splitlines()[-1:] or ["no output"]
        raise SolveError(f"solver failed (rc {p.returncode}): {tail[0][:200]}")
    return p.stdout


def solve_once(now=None):
    """The whole solve, under the caller's lock. Raises NoData / SolveError; always updates latest.json."""
    now = now or data.utcnow()
    started = now.isoformat()
    settings = data.read_settings()
    prev = read_latest()

    def fail(msg):
        rec = {**prev, "last_run": {"ok": False, "started": started, "finished": data.utcnow().isoformat(), "error": msg}}
        data.write_json(LATEST, rec)
        raise SolveError(msg)

    inp = data.load_inputs()
    if inp is None:
        raise NoData("no data")
    tid = squad.team_id()
    if tid is None:
        raise NoData("no FPL_TEAM_ID")
    try:
        rows, info = build_projection(inp, settings, now)
        if info.pop("own_rows"):
            data.write_projection_file(pj.OWN_SOURCE, rows, now)
            data.prune_projection_files(pj.OWN_SOURCE)
    except Exception as e:
        fail(f"projections failed: {type(e).__name__}: {str(e)[:150]}")
    sq = squad.get(inp["next_gw"], inp["events"], force=True)
    if sq.get("data") is None:
        fail(f"squad unavailable: {sq.get('error')}")
    csv_path = SOLVER_DIR / "data" / "homelab.csv"
    try:
        gws = solver_csv(inp, rows, csv_path)
        cfg = solver_settings(settings, tid, gws, sq["chips_left"])
        data.SOLVER.mkdir(parents=True, exist_ok=True)
        data.write_json(SETTINGS_OUT, cfg)
    except OSError as e:
        fail(f"could not write solver input: {type(e).__name__}")
    for old in glob.glob(str(SOLVER_DIR / "data" / "results" / "homelab_*.csv")):
        _rm(old)
    try:
        run_solver(SETTINGS_OUT, settings["secs"] + 180)
    except SolveError as e:
        fail(str(e))
    results = sorted(glob.glob(str(SOLVER_DIR / "data" / "results" / "homelab_*.csv")))
    try:
        if not results:
            raise ValueError("no result file")
        plan = parse_plan(results[-1])
        if not plan:
            raise ValueError("empty result")
    except Exception as e:
        fail(f"solver result unreadable: {type(e).__name__}: {str(e)[:100]}")
    finally:
        for f in results:
            _rm(f)
    finished = data.utcnow().isoformat()
    rec = {"last_run": {"ok": True, "started": started, "finished": finished, "error": None},
           "plan": plan, "plan_at": finished, "plan_source": info["source"], "plan_settings": settings,
           "plan_next_gw": inp["next_gw"], "plan_fts": sq.get("fts"), "plan_overrides": info["overrides_active"]}
    data.write_json(LATEST, rec)
    return rec


def _rm(p):
    try:
        os.unlink(p)
    except OSError:
        pass


def running_since():
    """ISO start time when a solve holds the lock, else None."""
    with store.job_lock("solve") as got:
        if got:
            return None
    return (data.read_json(RUNNING, {}) or {}).get("since") or "?"


def locked_solve():
    """solve_once under the lock; returns the record, or None when another solve holds the lock."""
    with store.job_lock("solve") as got:
        if not got:
            return None
        data.write_json(RUNNING, {"since": data.utcnow().isoformat()})
        try:
            return solve_once()
        finally:
            _rm(RUNNING)
