"""Storage helpers: atomic writes, gzipped raw responses, Parquet tables, locks, state.json."""
import contextlib
import datetime as dt
import fcntl
import gzip
import json
import os
from pathlib import Path

import pandas as pd

DATA = Path(os.environ.get("DATA_DIR", "/data"))
STATE_DIR = DATA / "state"


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def ensure_dirs():
    for d in (STATE_DIR, DATA / "raw", DATA / "tables", DATA / "soccerdata", DATA / "home"):
        d.mkdir(parents=True, exist_ok=True)


def atomic_write(path, data: bytes):
    """Write to a tmp file next to the target, then rename: a kill leaves no half-written target."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()


def save_raw(source, name, obj=None, raw_bytes=None):
    """Gzip a JSON-able object (or raw bytes as-is) to raw/<source>/<date>/<name>_<HHMMSS>Z.<ext>.gz."""
    now = utcnow()
    ext = "json" if raw_bytes is None else name.rsplit(".", 1)[-1]
    base = name if raw_bytes is None else name.rsplit(".", 1)[0]
    body = json.dumps(obj, separators=(",", ":")).encode() if raw_bytes is None else raw_bytes
    p = DATA / "raw" / source / now.strftime("%Y-%m-%d") / f"{base}_{now.strftime('%H%M%S')}Z.{ext}.gz"
    atomic_write(p, gzip.compress(body))
    return p


def _clean(df):
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(
                lambda v: json.dumps(v, separators=(",", ":")) if isinstance(v, (dict, list)) else v)
    return df


def save_table(table, rows, season, pulled_at=None):
    """rows: list of dicts or a DataFrame. Adds pulled_at + season. Empty -> nothing written, returns None."""
    df = rows.copy() if isinstance(rows, pd.DataFrame) else pd.DataFrame(rows)
    if df.empty:
        return None
    pulled_at = pulled_at or utcnow()
    df = _clean(df)
    df["pulled_at"] = pd.Timestamp(pulled_at)
    df["season"] = season
    p = (DATA / "tables" / table / f"date={pulled_at.strftime('%Y-%m-%d')}"
         / f"{pulled_at.strftime('%Y%m%dT%H%M%SZ')}.parquet")
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f".{p.name}.{os.getpid()}.tmp")
    try:
        try:
            df.to_parquet(tmp, index=False)
        except Exception:  # mixed-type object columns: store them as text
            for c in df.columns[df.dtypes == object]:
                df[c] = df[c].map(lambda v: None if v is None or v != v else str(v))
            df.to_parquet(tmp, index=False)
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
    return p


@contextlib.contextmanager
def job_lock(job):
    """Non-blocking per-job lock; yields False when another run holds it."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    f = open(STATE_DIR / f"{job}.lock", "w")
    try:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        f.close()


DEFAULT_STATE = {"collected_gws": [], "deadline_odds_gws": [], "odds_remaining": None,
                 "odds_remaining_at": None, "backfill_done": False}


@contextlib.contextmanager
def state():
    """Locked read-modify-write of state.json. Use briefly (not around network calls)."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATE_DIR / "state.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        p = STATE_DIR / "state.json"
        try:
            s = {**DEFAULT_STATE, **json.loads(p.read_text())}
        except (FileNotFoundError, ValueError):
            s = dict(DEFAULT_STATE)
        yield s
        atomic_write(p, json.dumps(s, indent=1, sort_keys=True).encode())


def read_state():
    with state() as s:
        return dict(s)


def season_of(events):
    """'2026-27' from the first event's deadline year."""
    y = int(events[0]["deadline_time"][:4])
    return season_str(y)


def season_str(y):
    return f"{y}-{str(y + 1)[2:]}"
