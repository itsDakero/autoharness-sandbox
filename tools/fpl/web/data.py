"""Reads for the page and the jobs: the collector's Parquet (DuckDB), projection files, JSON files in /data/web."""
import datetime as dt
import json
import os
import re
from pathlib import Path

DATA = Path(os.environ.get("DATA_DIR", "/data"))
TABLES = DATA / "tables"
PROJ = DATA / "projections"
WEB = DATA / "web"
SOLVER = DATA / "solver"
OVERRIDES = DATA / "overrides" / "minutes.csv"
STAMP = re.compile(r"^(\d{8}T\d{6}Z)\.parquet$")

KEYS = {"players": "id", "events": "id", "teams": "id", "fixtures": "id", "player_history": "element, round"}


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def newest_files(table):
    """Parquet files of the newest date= partition, or []."""
    base = TABLES / table
    try:
        parts = sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith("date="))
    except OSError:
        return []
    for part in reversed(parts):
        files = sorted(f for f in part.glob("*.parquet") if not f.name.startswith("."))
        if files:
            return files
    return []


def latest_rows(table):
    """Rows of the newest partition, the latest pulled_at per key, as dicts. Missing/unreadable table -> []."""
    files = newest_files(table)
    if not files:
        return []
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        paths = ", ".join("'" + str(f).replace("'", "''") + "'" for f in files)
        key = KEYS[table]
        cur = con.execute(
            f"SELECT * FROM read_parquet([{paths}], union_by_name=true) "
            f"QUALIFY row_number() OVER (PARTITION BY {key} ORDER BY pulled_at DESC) = 1")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception:  # corrupt or half-written file: treat as no data, the page says so
        return []
    finally:
        con.close()


def load_inputs():
    """-> dict with players, events, teams, fixtures, history ({element: [minutes by round]}), next_gw, or None
    when the collector has not produced the tables yet."""
    players, events = latest_rows("players"), latest_rows("events")
    if not players or not events:
        return None
    nxt = [e for e in events if e.get("is_next")]
    if not nxt:
        return None
    hist = {}
    for r in sorted(latest_rows("player_history"), key=lambda r: (r["element"], r["round"])):
        hist.setdefault(int(r["element"]), []).append(r.get("minutes"))
    return {"players": players, "events": sorted(events, key=lambda e: e["id"]), "teams": latest_rows("teams"),
            "fixtures": latest_rows("fixtures"), "history": hist, "next_gw": int(nxt[0]["id"])}


def parse_deadline(e):
    return dt.datetime.fromisoformat(str(e["deadline_time"]).replace("Z", "+00:00"))


def file_stamp(path):
    m = STAMP.match(Path(path).name)
    if not m:
        return None
    return dt.datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)


def list_candidates():
    """Projection files under /data/projections/<source>/: [{source, path, generated_at, gws}] (unreadable skipped)."""
    out = []
    try:
        sources = [d for d in PROJ.iterdir() if d.is_dir()]
    except OSError:
        return out
    import duckdb
    for d in sources:
        for f in d.glob("*.parquet"):
            ts = file_stamp(f)
            if ts is None:
                continue
            try:
                con = duckdb.connect(":memory:")
                try:
                    gws = {r[0] for r in con.execute("SELECT DISTINCT gw FROM read_parquet(?)", [str(f)]).fetchall()}
                finally:
                    con.close()
            except Exception:
                continue
            out.append({"source": d.name, "path": f, "generated_at": ts, "gws": gws})
    return out


def read_team_model():
    """Newest team goals file (/data/model/teams) + status.json -> {rows, status, generated_at}, or None when
    there is none or it cannot be read."""
    d = DATA / "model" / "teams"
    try:
        files = sorted(f for f in d.glob("*.parquet") if STAMP.match(f.name))
    except OSError:
        return None
    if not files:
        return None
    import duckdb
    try:
        con = duckdb.connect(":memory:")
        try:
            cur = con.execute("SELECT fixture_id, gw, team_h, team_a, xg_h, xg_a, cs_h, cs_a, source "
                              "FROM read_parquet(?) ORDER BY gw, fixture_id", [str(files[-1])])
            cols = [c[0] for c in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        finally:
            con.close()
    except Exception:
        return None
    status = read_json(d / "status.json", {})
    return {"rows": rows, "status": status if isinstance(status, dict) else {},
            "generated_at": file_stamp(files[-1])}


def read_model_extras():
    """Newest `model` projection file -> {"rows": {(element, gw): {pts, p10, q90}}, "generated_at": datetime},
    or None when there is no file or it cannot be read (the page then leaves the extra columns out)."""
    d = PROJ / "model"
    try:
        files = sorted(f for f in d.glob("*.parquet") if STAMP.match(f.name))
        if not files:
            return None
        import duckdb
        con = duckdb.connect(":memory:")
        try:
            cur = con.execute("SELECT element, gw, pts, p10, q90 FROM read_parquet(?)", [str(files[-1])])
            rows = {(int(a), int(b)): {"pts": float(c), "p10": float(p), "q90": float(q)}
                    for a, b, c, p, q in cur.fetchall()}
        finally:
            con.close()
        return {"rows": rows, "generated_at": file_stamp(files[-1])}
    except Exception:
        return None


def read_projection_file(path):
    import duckdb
    con = duckdb.connect(":memory:")
    try:
        cur = con.execute("SELECT element, gw, pts, xmins FROM read_parquet(?)", [str(path)])
        return [{"element": int(a), "gw": int(b), "pts": float(c), "xmins": float(d)} for a, b, c, d in cur.fetchall()]
    finally:
        con.close()


def write_projection_file(source, rows, now=None):
    import pandas as pd
    now = now or utcnow()
    df = pd.DataFrame(rows, columns=["element", "gw", "pts", "xmins"])
    df["element"] = df["element"].astype("int64")
    df["gw"] = df["gw"].astype("int64")
    df["generated_at"] = pd.Timestamp(now)
    d = PROJ / source
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{now.strftime('%Y%m%dT%H%M%SZ')}.parquet"
    tmp = d / f".{p.name}.{os.getpid()}.tmp"
    df.to_parquet(tmp, index=False)
    os.replace(tmp, p)
    return p


def prune_projection_files(source, keep=14):
    d = PROJ / source
    files = sorted(d.glob("*.parquet")) if d.is_dir() else []
    for f in files[:-keep]:
        try:
            f.unlink()
        except OSError:
            pass


# ---- page settings, overrides, state ------------------------------------------------------------------------

DEFAULT_SETTINGS = {"horizon": 8, "secs": 300, "decay_base": 0.9, "ft_value": 1.5, "plan_chips": True,
                    "projection_source": "auto"}
LIMITS = {"horizon": (1, 12, int), "secs": (30, 900, int), "decay_base": (0.5, 1.0, float), "ft_value": (0.0, 5.0, float)}


def clean_settings(raw):
    """Fill defaults, clamp numbers; anything unusable falls back to the default."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_SETTINGS)
    for k, (lo, hi, typ) in LIMITS.items():
        try:
            v = typ(raw.get(k, out[k]))
            out[k] = min(max(v, lo), hi)
        except (TypeError, ValueError):
            pass
    if "plan_chips" in raw:
        out["plan_chips"] = raw["plan_chips"] in (True, "on", "true", "1", 1)
    src = str(raw.get("projection_source", "auto")).strip()
    out["projection_source"] = src if re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,40}", src) else "auto"
    return out


def read_settings():
    return clean_settings(read_json(WEB / "settings.json", {}))


def write_json(path, obj):
    from collector import store
    store.atomic_write(path, json.dumps(obj, indent=1, sort_keys=True, default=str).encode())


def read_overrides():
    """-> (valid rows, bad lines)."""
    from . import projections
    try:
        text = OVERRIDES.read_text()
    except OSError:
        return [], []
    return projections.parse_overrides(text)


def write_overrides(rows):
    from collector import store
    from . import projections
    store.atomic_write(OVERRIDES, projections.dump_overrides(rows).encode())


def read_state():
    s = read_json(WEB / "state.json", {})
    return s if isinstance(s, dict) else {}


def update_state(**kw):
    s = read_state()
    s.update(kw)
    write_json(WEB / "state.json", s)
