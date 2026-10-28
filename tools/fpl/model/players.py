"""Hourly player points run (stage 4): minutes + goals/assists/defence/bonus Monte Carlo per fixture on top of the
team goals model's score matrices. Writes /data/projections/model/<ts>.parquet (the stage-2 contract plus extra
columns) and /data/model/players/status.json (see tools/fpl/README.md, "Player points model")."""
import contextlib
import csv
import datetime as dt
import glob
import gzip
import json
import math
import os
from pathlib import Path

import numpy as np

from . import pcore

DATA = Path(os.environ.get("DATA_DIR", "/data"))
STATUS = DATA / "model" / "players" / "status.json"
N_DRAWS = 10000
HORIZON = 8
KEEP = 14
MAX_AGE = dt.timedelta(hours=24)
EXTRA_COLS = ("p_start", "p60", "p10", "q50", "q90", "xg", "xa", "p_cs", "p_defcon", "xbonus")
FLOOR = 1e-4  # scorer/assister weights never reach zero, so someone is always drawn while a teammate is on


# ---- the simulation (numpy only, testable on synthetic input) -------------------------------------------------

def _draw_side(rng, players, n):
    """Minutes draw for one team: start/end time (n, P) of each player's spell, and a started flag."""
    P = len(players)
    s, e, started = np.zeros((n, P)), np.zeros((n, P)), np.zeros((n, P), bool)
    for j, p in enumerate(players):
        fx = p.get("fixed")
        if fx is not None:  # Dan's override wins over everything
            kind, m = fx
            if kind == "start":
                e[:, j], started[:, j] = m, True
            elif kind == "sub":
                s[:, j], e[:, j] = 90.0 - m, 90.0
            continue
        av = rng.random(n) < p["avail"]
        st = av & (rng.random(n) < p["p_start"])
        sb = av & ~st & (rng.random(n) < p["p_sub"])
        g, p60 = pcore.start_mix(p["m_start"], p["p60"])
        long_ = rng.random(n) < p60
        full = rng.random(n) < g
        m_start = np.where(long_, np.where(full, 90.0, 60.0 + rng.random(n) * 30.0), 15.0 + rng.random(n) * 44.0)
        top = min(45.0, max(1.5, 2.0 * p["m_sub"] - 1.0))
        m_sub = 1.0 + rng.random(n) * (top - 1.0)
        e[:, j] = np.where(st, m_start, np.where(sb, 90.0, 0.0))
        s[:, j] = np.where(sb, 90.0 - m_sub, 0.0)
        started[:, j] = st
    return {"s": s, "e": e, "started": started, "goals": np.zeros((n, P)), "assists": np.zeros((n, P)),
            "conceded": np.zeros((n, P)), "xg": np.array([max(p["xg90"], FLOOR) for p in players]),
            "xa": np.array([max(p["xa90"], FLOOR) for p in players])}


def _pick(rng, w):
    """Index drawn in proportion to the rows of w (n, P); second result: rows with a positive total."""
    tot = w.sum(1)
    u = rng.random(w.shape[0]) * tot
    idx = (np.cumsum(w, axis=1) < u[:, None]).sum(1)
    return np.minimum(idx, w.shape[1] - 1), tot > 0


def _team_goals(rng, att, dfn, goals, assist_rate):
    """Place each of the attacking team's goals in time; credit a scorer and an assister among those on the
    pitch, and a goal conceded to every opposing player on the pitch."""
    n = goals.shape[0]
    rows = np.arange(n)
    for k in range(int(goals.max()) if n else 0):
        has = goals > k
        t = (rng.random(n) * 90.0)[:, None]
        on_a = (att["s"] <= t) & (t < att["e"])
        on_d = (dfn["s"] <= t) & (t < dfn["e"])
        dfn["conceded"] += has[:, None] & on_d
        og = rng.random(n) < pcore.OG_SHARE
        pick, any_on = _pick(rng, on_a * att["xg"][None, :])
        ok = has & ~og & any_on
        att["goals"][rows[ok], pick[ok]] += 1
        wa = on_a * att["xa"][None, :]
        wa[rows, pick] = 0.0
        pick2, any_a = _pick(rng, wa)
        oka = ok & (rng.random(n) < assist_rate) & any_a
        att["assists"][rows[oka], pick2[oka]] += 1


def _bonus(bps, chunk=2000):
    """bps (n, P) with -inf for players who did not play -> bonus points (n, P), ties as pcore.bonus_points."""
    out = np.zeros(bps.shape)
    places = np.array(list(pcore.BONUS_BY_PLACE) + [0])
    for a in range(0, bps.shape[0], chunk):
        b = bps[a:a + chunk]
        greater = (b[:, None, :] > b[:, :, None]).sum(2)
        out[a:a + chunk] = np.where(np.isfinite(b), places[np.minimum(greater, len(places) - 1)], 0.0)
    return out


def simulate_fixture(matrix, home, away, scoring, n=N_DRAWS, seed=0, assist_rate=pcore.ASSIST_RATE):
    """matrix[home goals][away goals]; home/away: lists of player dicts (see player_params). -> {element: {pts,
    mins, goals, assists, cs, defcon, bonus, start, p60}} with arrays of n draws."""
    rng = np.random.default_rng(seed)
    m = np.asarray(matrix, float)
    m = m / m.sum()
    idx = rng.choice(m.size, size=n, p=m.ravel())
    goals = [idx // m.shape[1], idx % m.shape[1]]
    lam = [float((m.sum(1) * np.arange(m.shape[0])).sum()), float((m.sum(0) * np.arange(m.shape[1])).sum())]
    sides = [_draw_side(rng, home, n), _draw_side(rng, away, n)]
    squads = [home, away]
    for i in (0, 1):
        _team_goals(rng, sides[i], sides[1 - i], goals[i], assist_rate)
    sc = scoring
    res, bps_cols, who = {}, [], []
    for i in (0, 1):
        sd = sides[i]
        own, opp = max(lam[i], 0.05), max(lam[1 - i], 0.05)
        scale = min(1.25, max(0.8, (opp / own) ** 0.25))
        for j, p in enumerate(squads[i]):
            t = p["type"]
            mins = sd["e"][:, j] - sd["s"][:, j]
            played = mins > 0
            f90 = mins / 90.0
            gl, asst, gc = sd["goals"][:, j], sd["assists"][:, j], sd["conceded"][:, j]
            cs = ((mins >= pcore.LONG_PLAY_MIN) & (gc == 0)).astype(float)
            pts = np.where(mins >= pcore.LONG_PLAY_MIN, sc["long_play"][t], np.where(played, sc["short_play"][t], 0.0))
            pts = pts + gl * sc["goals_scored"][t] + asst * sc["assists"][t] + cs * sc["clean_sheets"][t]
            pts = pts + np.floor(gc / pcore.GC_PER_PT) * sc["goals_conceded"][t] * played
            saves = np.zeros(n)
            if t == 1 and p["save90"] > 0:
                saves = rng.poisson(p["save90"] * (opp / pcore.SAVES_LAMBDA_REF) * f90).astype(float)
                pts = pts + np.floor(saves / pcore.SAVES_PER_PT) * sc["saves"][t]
            dc_hit = np.zeros(n)
            if t in pcore.DEFCON_THRESHOLD and p["def90"] > 0:
                mu = p["def90"] * scale * f90
                if t == 2:
                    cnt = rng.poisson(mu)
                else:
                    nb = np.maximum(1, np.rint(mu / pcore.DEFCON_UNDISP)).astype(int)
                    cnt = rng.binomial(nb, np.minimum(1.0, mu / nb))
                dc_hit = (cnt >= pcore.DEFCON_THRESHOLD[t]).astype(float)
                pts = pts + dc_hit * sc["defensive_contribution"][t]
            pts = pts + (rng.random(n) < p["yel90"] * f90) * sc["yellow_cards"][t]
            pts = pts + (rng.random(n) < pcore.RED_PER90 * f90) * sc["red_cards"][t]
            pts = pts + (rng.random(n) < pcore.OWN_GOAL_PER90 * f90) * sc["own_goals"][t]
            if p.get("taker"):
                pts = pts + (rng.random(n) < pcore.PEN_MISS_PER_TEAM_MATCH * f90) * sc["penalties_missed"][t]
            ev = (gl * pcore.BPS_GOAL[t] + asst * pcore.BPS_ASSIST + cs * pcore.BPS_CS[t]
                  + saves * pcore.BPS_SAVE)
            bps = p["bps90"] * f90 + ev + rng.normal(0.0, 4.0, n) * np.sqrt(f90)
            bps_cols.append(np.where(played, bps, -np.inf))
            who.append((p["el"], t))
            res[p["el"]] = {"pts": pts, "mins": mins, "goals": gl, "assists": asst, "cs": cs, "defcon": dc_hit,
                            "start": sd["started"][:, j].astype(float), "p60": (mins >= 60).astype(float)}
    if bps_cols:
        bonus = _bonus(np.stack(bps_cols, axis=1))
        for c, (el, t) in enumerate(who):
            res[el]["bonus"] = bonus[:, c]
            res[el]["pts"] = res[el]["pts"] + bonus[:, c] * sc["bonus"][t]
    return res


# ---- inputs ---------------------------------------------------------------------------------------------------

def _list_sql(files):
    return "[" + ", ".join("'" + str(f).replace("'", "''") + "'" for f in files) + "]"


def load_history(tables, season):
    """This season's player_history rows only (ids are reassigned every season), the latest pull per
    (element, fixture): doubles keep both rows."""
    files = sorted(f for f in (tables / "player_history").glob("date=*/*.parquet") if not f.name.startswith("."))
    if not files:
        return []
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        cur = con.execute(f"SELECT * FROM read_parquet({_list_sql(files)}, union_by_name=true) "
                          f"WHERE season = ? "
                          f"QUALIFY row_number() OVER (PARTITION BY element, fixture ORDER BY pulled_at DESC) = 1", [season])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def newest_raw(pattern):
    files = sorted(glob.glob(str(DATA / "raw" / pattern)))
    return Path(files[-1]) if files else None


def load_scoring():
    p = newest_raw("fpl/*/bootstrap_*.json.gz")
    if p is None:
        raise ValueError("no raw bootstrap file yet")
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return pcore.scoring_from_bootstrap(json.load(f))


def load_vaastav(players):
    """Newest vaastav merged_gw csv -> ({element: [rows]}, unmapped names). Mapped by normalised
    'first second' to a unique current element."""
    p = newest_raw("vaastav/*/merged_gw_*.csv.gz")
    if p is None:
        return {}, 0
    by_name = {}
    for pl in players:
        by_name.setdefault(pcore.norm_name(f"{pl.get('first_name', '')} {pl.get('second_name', '')}"),
                           []).append(int(pl["id"]))
    out, unmapped = {}, set()
    with gzip.open(p, "rt", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            nm = pcore.norm_name(row.get("name"))
            ids = by_name.get(nm, [])
            if len(ids) == 1:
                out.setdefault(ids[0], []).append(row)
            else:
                unmapped.add(nm)
    return out, len(unmapped)


def player_params(pl, log, ov_fixed, avail):
    t = int(pl["element_type"])
    mp = pcore.minutes_params(log)
    return {"el": int(pl["id"]), "type": t, "avail": avail, "fixed": ov_fixed, **mp,
            "xg90": pcore.rate90(log, "xg", pcore.PRIOR_XG[t]), "xa90": pcore.rate90(log, "xa", pcore.PRIOR_XA[t]),
            "def90": pcore.rate90(log, "defcon", pcore.PRIOR_DEFCON[t]),
            "save90": pcore.rate90(log, "saves", pcore.PRIOR_SAVES[t]),
            "yel90": pcore.rate90(log, "yellows", pcore.PRIOR_YELLOW, pseudo_min=1800.0),
            "bps90": pcore.rate90(log, "bps_base", pcore.PRIOR_BPS_BASE[t]),
            "taker": pl.get("penalties_order") == 1}


def _result(status, msg, unmapped=0):
    return {"status": status, "msg": msg, "unmapped_vaastav": unmapped}


def _write_status(obj):
    from collector import store
    store.atomic_write(STATUS, json.dumps(obj, indent=1).encode())


def newest_model_file():
    d = DATA / "projections" / "model"
    from web import data
    files = sorted(f for f in d.glob("*.parquet") if data.STAMP.match(f.name)) if d.is_dir() else []
    return files[-1] if files else None


def read_status():
    try:
        s = json.loads(STATUS.read_text())
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def read_team_matrices(path):
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        rows = con.execute("SELECT fixture_id, gw, team_h, team_a, matrix FROM read_parquet(?)", [str(path)]).fetchall()
    finally:
        con.close()
    return {int(f): {"gw": int(g), "h": int(h), "a": int(a), "matrix": np.array(json.loads(m), float)}
            for f, g, h, a, m in rows}


def run(now=None):
    """-> {status: ok|busy|nodata|no team model|incomplete|nothing, msg, unmapped_vaastav}. Exceptions are real
    failures (the job exits 1)."""
    from collector import store
    from . import teams
    now = now or store.utcnow()
    with teams.lock() as got:
        if not got:
            return _result("busy", "model lock held (team model, tune or another player run)")
        return _run_locked(now, teams)


def _run_locked(now, teams):
    from collector import store
    from web import data, projections as pj
    team_file = teams.newest_output()
    if team_file is None:
        _write_status({"generated_at": None, "msg": "no team model", "inputs_key": None})
        return _result("no team model", "no team model file yet")
    parts = [team_file.name]
    for t in ("players", "player_history"):
        fs = data.newest_files(t)
        parts.append(f"{t}={fs[-1].parent.name}/{fs[-1].name}" if fs else f"{t}=-")
    bp = newest_raw("fpl/*/bootstrap_*.json.gz")
    parts.append(f"bootstrap={bp.parent.name}/{bp.name}" if bp else "bootstrap=-")
    try:
        parts.append(f"overrides={int(data.OVERRIDES.stat().st_mtime)}")
    except OSError:
        parts.append("overrides=-")
    key = "|".join(parts)
    last = newest_model_file()
    if last is not None and read_status().get("inputs_key") == key:
        stamp = data.file_stamp(last)
        if stamp is not None and now - stamp < MAX_AGE:
            return _result("nothing", "nothing new")

    events, fixtures, plist = data.latest_rows("events"), data.latest_rows("fixtures"), data.latest_rows("players")
    nxt = [e for e in events if e.get("is_next")]
    if not nxt or not fixtures or not plist:
        return _result("nodata", "no data: events, fixtures or players table missing")
    next_gw = int(nxt[0]["id"])
    tm = read_team_matrices(team_file)

    covered, by_gw = [], {}
    for gw in range(next_gw, min(39, next_gw + HORIZON)):
        fxs = sorted((f for f in fixtures if f.get("event") is not None and int(f["event"]) == gw
                      and not f.get("finished")), key=lambda f: int(f["id"]))
        if not fxs or any(int(f["id"]) not in tm for f in fxs):
            break
        covered.append(gw)
        by_gw[gw] = fxs
    if not covered:
        msg = f"team model does not cover all GW{next_gw} fixtures"
        _write_status({"generated_at": None, "msg": msg, "inputs_key": None})
        return _result("incomplete", msg)

    scoring = load_scoring()  # ValueError (no game_config.scoring) -> the job fails, no file
    hist_rows = load_history(data.TABLES, store.season_of(sorted(events, key=lambda e: int(e["id"]))))
    vaastav, unmapped = load_vaastav(plist)
    first_kick = min((pcore.kick_key(r.get("kickoff_time")) for r in hist_rows if r.get("kickoff_time")), default=None)
    by_el = {}
    for r in hist_rows:
        by_el.setdefault(int(r["element"]), []).append(r)
    goals_all = assists_all = 0.0
    logs = {}
    for pl in plist:
        el, t = int(pl["id"]), int(pl["element_type"])
        rows = list(by_el.get(el, []))
        # last season's vaastav rows (older than anything this season's history has)
        rows += [v for v in vaastav.get(el, []) if first_kick is None or pcore.kick_key(v.get("kickoff_time")) < first_kick]
        logs[el] = pcore.match_log(rows, t)
        goals_all += sum(m["goals"] for m in logs[el])
        assists_all += sum(m["assists"] for m in logs[el])
    a_rate = pcore.assist_rate(goals_all, assists_all)

    ovs, _bad = data.read_overrides()
    active, _ignored = pj.split_overrides(ovs, [int(p["id"]) for p in plist], next_gw, HORIZON)
    ov = {(o["element"], o["gw"]): o["xmins"] for o in active}
    team_players = {}
    for pl in plist:
        team_players.setdefault(int(pl["team"]), []).append(pl)

    out = []
    for gw in covered:
        fxs = by_gw[gw]
        tfix = {}
        for f in fxs:
            for side in ("team_h", "team_a"):
                tfix.setdefault(int(f[side]), []).append(int(f["id"]))
        acc = {}
        for f in fxs:
            fid = int(f["id"])
            squads = []
            for side in ("team_h", "team_a"):
                tid = int(f[side])
                lst = []
                for pl in team_players.get(tid, []):
                    el = int(pl["id"])
                    fixed = None
                    if (el, gw) in ov:
                        fixed = pcore.override_minutes(ov[(el, gw)], len(tfix[tid]))[tfix[tid].index(fid)]
                    avail = pcore.availability(pl.get("status"), pl.get("chance_of_playing_next_round"), gw - next_gw)
                    if fixed is None and avail <= 0:
                        continue
                    lst.append(player_params(pl, logs[el], fixed, avail))
                squads.append(lst)
            res = simulate_fixture(tm[fid]["matrix"], squads[0], squads[1], scoring, N_DRAWS, fid, a_rate)
            for el, r in res.items():
                a = acc.setdefault(el, {k: np.zeros(N_DRAWS) for k in r})
                for k, v in r.items():
                    a[k] = a[k] + v
        for pl in plist:
            el = int(pl["id"])
            a = acc.get(el)
            if a is None:
                out.append({"element": el, "gw": gw, "pts": 0.0, "xmins": 0.0,
                            **{c: 0.0 for c in EXTRA_COLS}})  # blank gameweek (or nothing to simulate)
                continue
            q50, q90 = pcore.quantiles(np.sort(a["pts"]), (0.5, 0.9))
            xm = float(a["mins"].mean())
            if (el, gw) in ov:
                xm = float(ov[(el, gw)])  # exactly the override, so stage 2's apply_overrides scales by 1
            out.append({"element": el, "gw": gw, "pts": float(a["pts"].mean()), "xmins": xm,
                        "p_start": float(a["start"].mean()), "p60": float(a["p60"].mean()),
                        "p10": float((a["pts"] >= 10).mean()), "q50": q50, "q90": q90,
                        "xg": float(a["goals"].mean()), "xa": float(a["assists"].mean()),
                        "p_cs": float(a["cs"].mean()), "p_defcon": float(a["defcon"].mean()),
                        "xbonus": float(a["bonus"].mean())})
    bad = [r for r in out if not all(math.isfinite(float(v)) for v in r.values())]
    if bad:
        raise ValueError(f"non-finite value for player {bad[0]['element']} GW{bad[0]['gw']}, no file written")
    path = write_file(out, now)
    data.prune_projection_files("model", KEEP)
    _write_status({"generated_at": now.isoformat(), "gws": covered, "n_players": len(plist),
                   "n_fixtures": sum(len(v) for v in by_gw.values()), "unmapped_vaastav": unmapped,
                   "inputs_key": key, "msg": f"GW{covered[0]}-{covered[-1]}, {path.name}"})
    return _result("ok", f"GW{covered[0]}-{covered[-1]}, {len(plist)} players, {unmapped} vaastav names unmapped",
                   unmapped)


def write_file(rows, now):
    import pandas as pd
    from web import data
    df = pd.DataFrame(rows, columns=["element", "gw", "pts", "xmins", *EXTRA_COLS])
    df["element"] = df["element"].astype("int64")
    df["gw"] = df["gw"].astype("int64")
    for c in ("pts", "xmins", *EXTRA_COLS):
        df[c] = df[c].astype("float64")
    df["generated_at"] = pd.Timestamp(now)
    d = data.PROJ / "model"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{now.strftime('%Y%m%dT%H%M%SZ')}.parquet"
    tmp = d / f".{p.name}.{os.getpid()}.tmp"
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
    return p
