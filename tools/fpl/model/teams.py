"""Hourly team goals run: fixtures in the next 8 gameweeks -> expected goals, clean sheets, score matrix.
Writes /data/model/teams/<ts>.parquet + status.json (see tools/fpl/README.md)."""
import contextlib
import datetime as dt
import fcntl
import json
import math
import os
import re
import statistics
from pathlib import Path

from collector import store

from . import core, fit

DATA = Path(os.environ.get("DATA_DIR", "/data"))
MODEL = DATA / "model"
OUT = MODEL / "teams"
HIST = MODEL / "history"
LOCK = MODEL / ".lock"
PARAMS = OUT / "params.json"
STATUS = OUT / "status.json"
HIST_MARKET = HIST / "market.parquet"
HIST_XG = HIST / "understat_team_match.parquet"
DEFAULTS = {"xi_market": 0.0019, "xi_xg": 0.0019, "w_market": 0.5, "rho": -0.05}
HORIZON = 8
KEEP = 14
FRESH = dt.timedelta(hours=48)
MATCH_WINDOW = dt.timedelta(hours=36)
MAX_AGE = dt.timedelta(hours=24)
STAMP = re.compile(r"^\d{8}T\d{6}Z\.parquet$")


@contextlib.contextmanager
def lock():
    """Non-blocking model lock (/data/model/.lock); yields False when another run (tune, history) holds it."""
    MODEL.mkdir(parents=True, exist_ok=True)
    f = open(LOCK, "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        f.close()


def to_dt(v):
    if isinstance(v, dt.datetime):
        return v if v.tzinfo else v.replace(tzinfo=dt.timezone.utc)
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


def load_params():
    """-> (params, tuned: bool). A missing or unreadable params.json means defaults."""
    p = dict(DEFAULTS)
    try:
        raw = json.loads(PARAMS.read_text())
        for k, (lo, hi) in {"xi_market": (0, 0.1), "xi_xg": (0, 0.1), "w_market": (0, 1), "rho": (-0.5, 0.5)}.items():
            v = float(raw[k])
            if not lo <= v <= hi:
                return dict(DEFAULTS), False
            p[k] = v
        return p, True
    except (OSError, ValueError, KeyError, TypeError):
        return dict(DEFAULTS), False


def table_files(table):
    base = DATA / "tables" / table
    return sorted(f for f in base.glob("date=*/*.parquet") if not f.name.startswith(".")) if base.is_dir() else []


def _list_sql(files):
    return "[" + ", ".join("'" + str(f).replace("'", "''") + "'" for f in files) + "]"


def load_xg_rows():
    """Non-penalty xG per played match: collector table (latest pull per match) + history file; collector wins."""
    rows = {}
    if HIST_XG.exists():
        import duckdb
        con = duckdb.connect(":memory:")
        try:
            for d, h, a, xh, xa in con.execute(
                    "SELECT date, home, away, hxg, axg FROM read_parquet(?)", [str(HIST_XG)]).fetchall():
                rows[(d, h, a)] = {"date": d, "home": h, "away": a, "gh": xh, "ga": xa}
        finally:
            con.close()
    files = table_files("understat_team_match")
    if files:
        import duckdb
        con = duckdb.connect(":memory:")
        try:
            cur = con.execute(
                f"SELECT CAST(date AS DATE), home_team, away_team, home_np_xg, away_np_xg "
                f"FROM read_parquet({_list_sql(files)}, union_by_name=true) "
                f"WHERE home_np_xg IS NOT NULL AND away_np_xg IS NOT NULL "
                f"QUALIFY row_number() OVER (PARTITION BY home_team, away_team, CAST(date AS DATE) "
                f"ORDER BY pulled_at DESC) = 1")
            for d, h, a, xh, xa in cur.fetchall():
                h, a = core.canon(h), core.canon(a)
                rows[(d, h, a)] = {"date": d, "home": h, "away": a, "gh": float(xh), "ga": float(xa)}
        finally:
            con.close()
    return list(rows.values())


def load_odds(now, rho):
    """-> (past, future): past = market rows [{date, home, away, gh, ga}] from each finished event's last snapshot
    before kickoff; future = [{kick, home, away, lh, la, rho, pts}] for events kicking off later whose odds
    were pulled within 48 h. A bad event is skipped, never fatal."""
    files = table_files("odds")
    if not files:
        return [], []
    import duckdb
    import pandas as pd
    con = duckdb.connect(":memory:")
    try:
        src = f"read_parquet({_list_sql(files)}, union_by_name=true)"
        snaps = con.execute(
            f"SELECT event_id, any_value(commence_time), any_value(home), any_value(away), epoch(pulled_at) "
            f"FROM {src} GROUP BY event_id, pulled_at").fetchall()
        by_event = {}
        for ev, ct, h, a, pts in snaps:
            kick = to_dt(ct)
            if kick is None or ev is None:
                continue
            by_event.setdefault(ev, {"kick": kick, "home": h, "away": a, "pts": []})["pts"].append(float(pts))
        chosen = {}
        for ev, e in by_event.items():
            if e["kick"] <= now:
                ok = [p for p in e["pts"] if p <= e["kick"].timestamp()]
                if ok:
                    chosen[ev] = (max(ok), False)
            else:
                p = max(e["pts"])
                if p >= (now - FRESH).timestamp():
                    chosen[ev] = (p, True)
        if not chosen:
            return [], []
        sel = pd.DataFrame([{"event_id": ev, "pts": p} for ev, (p, _) in chosen.items()])
        con.register("sel", sel)
        cur = con.execute(
            f"SELECT o.event_id, o.home, o.away, o.market, o.outcome, o.point, o.price FROM {src} o "
            f"JOIN sel s ON o.event_id = s.event_id AND epoch(o.pulled_at) = s.pts")
        cols = [d[0] for d in cur.description]
        grouped = {}
        for r in cur.fetchall():
            grouped.setdefault(r[0], []).append(dict(zip(cols, r)))
    finally:
        con.close()
    past, future = [], []
    for ev, (pts, is_future) in chosen.items():
        e = by_event[ev]
        res = fit.implied_goals(core.median_prices(grouped.get(ev, [])), rho)
        if res is None:
            continue
        if is_future:
            future.append({"kick": e["kick"], "home": e["home"], "away": e["away"], "lh": res["lh"],
                           "la": res["la"], "rho": res["rho"], "pts": pts})
        else:
            past.append({"date": e["kick"].date(), "home": core.canon(e["home"]), "away": core.canon(e["away"]),
                         "gh": res["lh"], "ga": res["la"]})
    return past, future


def load_market_rows(now, rho):
    """Market lambdas of past fixtures: collector snapshots win over the history file. Also returns future fits."""
    past, future = load_odds(now, rho)
    rows = {}
    if HIST_MARKET.exists():
        import duckdb
        con = duckdb.connect(":memory:")
        try:
            for d, h, a, lh, la in con.execute(
                    "SELECT date, home, away, lh, la FROM read_parquet(?)", [str(HIST_MARKET)]).fetchall():
                rows[(d, h, a)] = {"date": d, "home": h, "away": a, "gh": lh, "ga": la}
        finally:
            con.close()
    for r in past:
        rows[(r["date"], r["home"], r["away"])] = r
    return list(rows.values()), future


def goals_for(market_fit, xg_fit, home, away, w, weeks_ahead=0):
    """Blended (lh, la) from the two ratings fits (log space), shrunk toward the league mean; None when no fit
    knows both teams."""
    m = fit.log_lambdas(market_fit, home, away)
    x = fit.log_lambdas(xg_fit, home, away)
    if m is None and x is None:
        return None
    if m is not None and x is not None:
        lh, la = core.blend(m[0], x[0], w), core.blend(m[1], x[1], w)
        means = [fit.log_means(f) for f in (market_fit, xg_fit)]
        mh, ma = core.blend(means[0][0], means[1][0], w), core.blend(means[0][1], means[1][1], w)
    else:
        lh, la = m or x
        mh, ma = fit.log_means(market_fit if m is not None else xg_fit)
    k = min(1.0, 0.02 * weeks_ahead)
    return math.exp(core.shrink(lh, mh, k)), math.exp(core.shrink(la, ma, k))


def inputs_key():
    parts = []
    for t in ("events", "fixtures", "teams", "odds", "understat_team_match"):
        fs = table_files(t)
        parts.append(f"{t}={fs[-1].parent.name}/{fs[-1].name}" if fs else f"{t}=-")
    for p in (PARAMS, HIST_MARKET, HIST_XG):
        try:
            parts.append(f"{p.name}={int(p.stat().st_mtime)}")
        except OSError:
            parts.append(f"{p.name}=-")
    return "|".join(parts)


def newest_output():
    files = sorted(f for f in OUT.glob("*.parquet") if STAMP.match(f.name)) if OUT.is_dir() else []
    return files[-1] if files else None


def read_status():
    try:
        s = json.loads(STATUS.read_text())
        return s if isinstance(s, dict) else {}
    except (OSError, ValueError):
        return {}


def _result(status, msg, unmapped=()):
    return {"status": status, "msg": msg, "unmapped": list(unmapped)}


def run(now=None):
    """-> {status: ok|busy|nodata|nothing, msg, unmapped}. Exceptions are real failures."""
    now = now or store.utcnow()
    with lock() as got:
        if not got:
            return _result("busy", "team model busy (tune or history running)")
        return _run_locked(now)


def _run_locked(now):
    from web import data
    key = inputs_key()
    last = newest_output()
    if last is not None and read_status().get("inputs_key") == key:
        stamp = data.file_stamp(last)
        if stamp is not None and now - stamp < MAX_AGE:
            return _result("nothing", "nothing new")
    events, fixtures, teams = data.latest_rows("events"), data.latest_rows("fixtures"), data.latest_rows("teams")
    nxt = [e for e in events if e.get("is_next")]
    if not nxt or not fixtures or not teams:
        return _result("nodata", "no data: events, fixtures or teams table missing")
    next_gw = int(nxt[0]["id"])
    cmap = {core.canon(t["name"]): int(t["id"]) for t in teams if t.get("name")}
    params, tuned = load_params()
    market_rows, future = load_market_rows(now, params["rho"])
    xg_rows = load_xg_rows()
    ref = now.date()
    market_fit = fit.fit_ratings(market_rows, params["xi_market"], ref)
    xg_fit = fit.fit_ratings(xg_rows, params["xi_xg"], ref)

    fx = {}
    for f in fixtures:
        ev = f.get("event")
        if ev is None or f.get("finished") or not next_gw <= int(ev) < next_gw + HORIZON:
            continue
        fx[int(f["id"])] = f
    by_pair = {}
    for fid, f in fx.items():
        by_pair.setdefault((int(f["team_h"]), int(f["team_a"])), []).append(fid)
    matched, unmapped = {}, set()
    for e in sorted(future, key=lambda e: e["pts"]):
        hid, aid = cmap.get(core.canon(e["home"])), cmap.get(core.canon(e["away"]))
        if hid is None or aid is None:
            unmapped.update(n for n, i in ((e["home"], hid), (e["away"], aid)) if i is None)
            continue
        for fid in by_pair.get((hid, aid), []):
            ko = to_dt(fx[fid].get("kickoff_time"))
            if ko is not None and abs(ko - e["kick"]) <= MATCH_WINDOW:
                matched[fid] = e
    run_rho = statistics.median(e["rho"] for e in matched.values()) if matched else params["rho"]
    names = {v: k for k, v in cmap.items()}
    rows, omitted = [], 0
    for fid, f in sorted(fx.items()):
        gw = int(f["event"])
        e = matched.get(fid)
        if e is not None:
            lh, la, rho, source = e["lh"], e["la"], e["rho"], "market"
        else:
            g = goals_for(market_fit, xg_fit, names.get(int(f["team_h"])), names.get(int(f["team_a"])),
                          params["w_market"], gw - next_gw)
            if g is None:
                omitted += 1
                continue
            (lh, la), rho, source = g, run_rho, "ratings"
        m = core.score_matrix(lh, la, rho)
        ph, pd_, pa = core.outcome_probs(m)
        csh, csa = core.cs(m)
        ko = to_dt(f.get("kickoff_time"))
        rows.append({"fixture_id": fid, "gw": gw, "team_h": int(f["team_h"]), "team_a": int(f["team_a"]),
                     "kickoff_time": ko.isoformat() if ko else None, "xg_h": lh, "xg_a": la, "cs_h": csh,
                     "cs_a": csa, "p_h": ph, "p_d": pd_, "p_a": pa, "source": source, "rho": rho,
                     "matrix": json.dumps([[round(v, 5) for v in r] for r in m], separators=(",", ":"))})
    status = {"generated_at": now.isoformat(), "market": sum(r["source"] == "market" for r in rows),
              "ratings": sum(r["source"] == "ratings" for r in rows), "omitted": omitted,
              "fit_market": market_fit["n"] if market_fit else 0, "fit_xg": xg_fit["n"] if xg_fit else 0,
              "params": "tuned" if tuned else "default", "unmapped": sorted(unmapped), "inputs_key": key}
    if not rows:
        store.atomic_write(STATUS, json.dumps({**status, "generated_at": None}, indent=1).encode())
        return _result("nodata", f"no data: no odds or xG fit yet, {omitted} fixture(s) omitted", unmapped)
    import pandas as pd
    df = pd.DataFrame(rows)
    df["generated_at"] = pd.Timestamp(now)
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{now.strftime('%Y%m%dT%H%M%SZ')}.parquet"
    tmp = OUT / f".{p.name}.{os.getpid()}.tmp"
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
    store.atomic_write(STATUS, json.dumps(status, indent=1).encode())
    for old in sorted(f for f in OUT.glob("*.parquet") if STAMP.match(f.name))[:-KEEP]:
        with contextlib.suppress(OSError):
            old.unlink()
    return _result("ok", f"{status['market']} market, {status['ratings']} ratings, {omitted} omitted", unmapped)
