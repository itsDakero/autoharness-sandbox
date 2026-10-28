"""By-hand commands: python -m model <history|tune>. Both hold /data/model/.lock (the hourly job then says busy)."""
import datetime as dt
import json
import sys

from collector import store

from . import core, fit, teams

FD_DIR = teams.HIST / "football-data"
ORIGIN_DAYS = 7
TEST_DAYS = 56
GRID_XI = (0.001, 0.0019, 0.003, 0.005)
GRID_W = (0.0, 0.25, 0.5, 0.75, 1.0)
FIRST_ORIGIN = dt.date(2021, 8, 1)
LAST_DATE = dt.date(2026, 6, 30)


def _write_parquet(df, path):
    import os
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def cmd_history():
    import pandas as pd
    params, _ = teams.load_params()
    files = sorted(FD_DIR.glob("*.csv"))
    if not files:
        print(f"history: no CSV files in {FD_DIR} (download E0.csv per season by hand, see the README)")
        return 1
    rows, skipped = [], 0
    for f in files:
        for r in core.parse_football_data(f.read_text(encoding="utf-8-sig", errors="replace")):
            if r["hg"] is None or r["ag"] is None:
                continue
            res = fit.implied_goals(r["prices"], params["rho"])
            if res is None:
                skipped += 1
                continue
            rows.append({"date": r["date"], "home": r["home"], "away": r["away"], "lh": res["lh"], "la": res["la"],
                         "hg": r["hg"], "ag": r["ag"]})
    if rows:
        _write_parquet(pd.DataFrame(rows), teams.HIST_MARKET)
    print(f"history: market {len(rows)} matches from {len(files)} file(s), {skipped} without a usable fit")
    import soccerdata as sd
    now = store.utcnow()
    cur = now.year if now.month >= 8 else now.year - 1
    seasons = list(range(2019, cur))
    u = sd.Understat(leagues="ENG-Premier League", seasons=seasons)
    df = u.read_team_match_stats().reset_index()
    out = pd.DataFrame({"date": pd.to_datetime(df["date"]).dt.date,
                        "home": df["home_team"].map(core.canon), "away": df["away_team"].map(core.canon),
                        "hxg": df["home_np_xg"].astype(float), "axg": df["away_np_xg"].astype(float)})
    out = out.dropna()
    if len(out):
        _write_parquet(out, teams.HIST_XG)
    print(f"history: understat {len(out)} matches, seasons {seasons[0]}..{seasons[-1]}")
    return 0


def _rows(path, cols):
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        cur = con.execute(f"SELECT {', '.join(cols)} FROM read_parquet(?)", [str(path)])
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def cmd_tune():
    import math
    if not teams.HIST_MARKET.exists():
        print("tune: no history yet (run `python -m model history` first)")
        return 1
    market = _rows(teams.HIST_MARKET, ["date", "home", "away", "lh", "la", "hg", "ag"])
    mrows = [{"date": r["date"], "home": r["home"], "away": r["away"], "gh": r["lh"], "ga": r["la"]} for r in market]
    xrows = []
    if teams.HIST_XG.exists():
        xrows = [{"date": r["date"], "home": r["home"], "away": r["away"], "gh": r["hxg"], "ga": r["axg"]}
                 for r in _rows(teams.HIST_XG, ["date", "home", "away", "hxg", "axg"])]
    combos = [(a, b, w) for a in GRID_XI for b in GRID_XI for w in GRID_W]
    loss = {c: 0.0 for c in combos}
    count = {c: 0 for c in combos}
    origin = FIRST_ORIGIN
    n_origins = 0
    while origin < LAST_DATE:
        tests = [r for r in market if origin <= r["date"] < origin + dt.timedelta(days=TEST_DAYS)]
        if tests:
            n_origins += 1
            tm = [r for r in mrows if r["date"] < origin]
            tx = [r for r in xrows if r["date"] < origin]
            mf = {xi: fit.fit_ratings(tm, xi, origin) for xi in GRID_XI}
            xf = {xi: fit.fit_ratings(tx, xi, origin) for xi in GRID_XI}
            for r in tests:
                weeks = (r["date"] - origin).days // 7
                actual = 0 if r["hg"] > r["ag"] else 1 if r["hg"] == r["ag"] else 2
                for (a, b, w) in combos:
                    g = teams.goals_for(mf[a], xf[b], r["home"], r["away"], w, weeks)
                    if g is None:
                        continue
                    p = core.outcome_probs(core.score_matrix(g[0], g[1], teams.DEFAULTS["rho"]))[actual]
                    loss[(a, b, w)] += -math.log(max(p, 1e-9))
                    count[(a, b, w)] += 1
        origin += dt.timedelta(days=ORIGIN_DAYS)
    scored = {c: loss[c] / count[c] for c in combos if count[c] > 0}
    if not scored:
        print("tune: nothing to score (history too short for the first origin 2021-08-01)")
        return 1
    best = min(scored, key=scored.get)
    dflt = (teams.DEFAULTS["xi_market"], teams.DEFAULTS["xi_xg"], teams.DEFAULTS["w_market"])
    out = {"xi_market": best[0], "xi_xg": best[1], "w_market": best[2], "rho": teams.DEFAULTS["rho"],
           "tuned_at": store.utcnow().isoformat(), "n": count[best], "logloss": scored[best],
           "default_logloss": scored.get(dflt)}
    store.atomic_write(teams.PARAMS, json.dumps(out, indent=1).encode())
    print(f"tune: xi_market {best[0]}, xi_xg {best[1]}, w_market {best[2]}; log-loss {scored[best]:.4f} "
          f"(defaults {scored.get(dflt, float('nan')):.4f}) over {count[best]} matches, {n_origins} origins")
    return 0


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd not in ("history", "tune"):
        print("usage: python -m model <history|tune>", file=sys.stderr)
        return 2
    with teams.lock() as got:
        if not got:
            print(f"{cmd}: busy (another model run holds {teams.LOCK})")
            return 0
        return cmd_history() if cmd == "history" else cmd_tune()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
