"""SQLite for the wardrobe (stdlib only). One short-lived connection per call site."""
import json
import os
import sqlite3
import time

MIGRATIONS = [
    """
    CREATE TABLE items(
        id INTEGER PRIMARY KEY,
        kind TEXT NOT NULL DEFAULT 'owned' CHECK(kind IN ('owned','wishlist')),
        status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','retired')),
        retired_reason TEXT, retired_at TEXT, bought_at TEXT,
        category TEXT, colours TEXT NOT NULL DEFAULT '[]', seasons TEXT NOT NULL DEFAULT '[]',
        style TEXT, brand TEXT, size TEXT, price REAL, notes TEXT, source_url TEXT,
        photo TEXT, thumb TEXT,
        tag_status TEXT NOT NULL DEFAULT 'pending'
            CHECK(tag_status IN ('pending','tagged','failed','reviewed')),
        tag_error TEXT, tagged_by_model TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX items_tag ON items(tag_status, id);
    CREATE TABLE profile(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
    # 2: outfit generator (outfits, votes, wear log, one daily pick per date)
    """
    CREATE TABLE outfits(key TEXT PRIMARY KEY, items TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE votes(key TEXT PRIMARY KEY, vote INTEGER NOT NULL CHECK(vote IN (-1,1)),
        at TEXT NOT NULL);
    CREATE TABLE wear(id INTEGER PRIMARY KEY, date TEXT NOT NULL, key TEXT NOT NULL,
        items TEXT NOT NULL, at TEXT NOT NULL);
    CREATE UNIQUE INDEX wear_date_key ON wear(date, key);
    CREATE TABLE daily(date TEXT PRIMARY KEY, key TEXT NOT NULL DEFAULT '',
        weather TEXT NOT NULL DEFAULT 'null', note TEXT NOT NULL DEFAULT '');
    """,
]

FIELDS = ("category", "colours", "seasons", "style", "brand", "size", "price", "notes")


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    migrate(con)
    return con


def migrate(con):
    ver = con.execute("PRAGMA user_version").fetchone()[0]
    for i in range(ver, len(MIGRATIONS)):
        with con:
            for stmt in MIGRATIONS[i].split(";"):
                if stmt.strip():
                    con.execute(stmt)
            con.execute(f"PRAGMA user_version={i + 1}")


def _row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("colours", "seasons"):
        try:
            d[k] = json.loads(d[k] or "[]")
        except ValueError:
            d[k] = []
    return d


def add_item(con, kind="owned", photo=None, thumb=None, source_url=None,
             tag_status="pending", tag_error=None):
    t = now()
    cur = con.execute(
        "INSERT INTO items(kind,photo,thumb,source_url,tag_status,tag_error,created_at,updated_at)"
        " VALUES(?,?,?,?,?,?,?,?)", (kind, photo, thumb, source_url, tag_status, tag_error, t, t))
    con.commit()
    return cur.lastrowid


def get_item(con, item_id):
    return _row(con.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone())


def list_items(con, kind=None, category=None, status="active", tag_statuses=None):
    q, args = "SELECT * FROM items WHERE 1=1", []
    if kind:
        q += " AND kind=?"
        args.append(kind)
    if category:
        q += " AND category=?"
        args.append(category)
    if status:
        q += " AND status=?"
        args.append(status)
    if tag_statuses:
        q += " AND tag_status IN (%s)" % ",".join("?" * len(tag_statuses))
        args += list(tag_statuses)
    q += " ORDER BY id DESC"
    return [_row(r) for r in con.execute(q, args)]


def counts(con):
    r = con.execute(
        "SELECT SUM(tag_status='pending') p, SUM(tag_status IN ('tagged','failed')) r FROM items"
        " WHERE status='active'").fetchone()
    return {"pending": r["p"] or 0, "review": r["r"] or 0}


def next_pending(con):
    return _row(con.execute(
        "SELECT * FROM items WHERE tag_status='pending' AND photo IS NOT NULL"
        " ORDER BY id LIMIT 1").fetchone())


def set_tagged(con, item_id, tags, model):
    """All tag fields and the status in one UPDATE: never half-written."""
    con.execute(
        "UPDATE items SET category=?, colours=?, seasons=?, style=?,"
        " brand=COALESCE(NULLIF(brand,''), ?), tag_status='tagged', tag_error=NULL,"
        " tagged_by_model=?, updated_at=? WHERE id=? AND tag_status='pending'",
        (tags["category"], json.dumps(tags["colours"]), json.dumps(tags["seasons"]),
         tags["style"], tags["brand"], model, now(), item_id))
    con.commit()


def set_failed(con, item_id, error):
    con.execute("UPDATE items SET tag_status='failed', tag_error=?, updated_at=? WHERE id=?",
                (error[:300], now(), item_id))
    con.commit()


def requeue(con, item_id):
    """Retry tagging. Only possible with a photo."""
    con.execute("UPDATE items SET tag_status='pending', tag_error=NULL, updated_at=?"
                " WHERE id=? AND photo IS NOT NULL", (now(), item_id))
    con.commit()


def save_fields(con, item_id, f):
    """Dan's edit: sets the fields and marks the item reviewed."""
    con.execute(
        "UPDATE items SET category=?, colours=?, seasons=?, style=?, brand=?, size=?, price=?,"
        " notes=?, tag_status='reviewed', tag_error=NULL, updated_at=? WHERE id=?",
        (f.get("category"), json.dumps(f.get("colours") or []), json.dumps(f.get("seasons") or []),
         f.get("style"), f.get("brand"), f.get("size"), f.get("price"), f.get("notes"),
         now(), item_id))
    con.commit()


def set_photo(con, item_id, photo, thumb):
    old = get_item(con, item_id)
    con.execute("UPDATE items SET photo=?, thumb=?, tag_status='pending', tag_error=NULL,"
                " updated_at=? WHERE id=?", (photo, thumb, now(), item_id))
    con.commit()
    return old


def mark_bought(con, item_id):
    con.execute("UPDATE items SET kind='owned', bought_at=?, updated_at=?"
                " WHERE id=? AND kind='wishlist'", (now(), now(), item_id))
    con.commit()


def retire(con, item_id, reason):
    con.execute("UPDATE items SET status='retired', retired_reason=?, retired_at=?, updated_at=?"
                " WHERE id=?", (reason, now(), now(), item_id))
    con.commit()


def restore(con, item_id):
    con.execute("UPDATE items SET status='active', retired_reason=NULL, retired_at=NULL,"
                " updated_at=? WHERE id=?", (now(), item_id))
    con.commit()


def delete_item(con, item_id):
    """Delete the row; return the item so the caller can remove its files."""
    it = get_item(con, item_id)
    con.execute("DELETE FROM items WHERE id=?", (item_id,))
    con.commit()
    return it


def get_profile(con):
    return {r["key"]: r["value"] for r in con.execute("SELECT key,value FROM profile")}


def set_profile(con, values):
    with con:
        for k, v in values.items():
            if v in (None, ""):
                con.execute("DELETE FROM profile WHERE key=?", (k,))
            else:
                con.execute("INSERT INTO profile(key,value) VALUES(?,?)"
                            " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, str(v)))


def _ids(text):
    try:
        v = json.loads(text or "[]")
    except ValueError:
        return []
    return [i for i in v if isinstance(i, int)] if isinstance(v, list) else []


def save_outfit(con, key, ids):
    con.execute("INSERT OR IGNORE INTO outfits(key,items,created_at) VALUES(?,?,?)",
                (key, json.dumps(list(ids)), now()))
    con.commit()


def get_outfit(con, key):
    r = con.execute("SELECT * FROM outfits WHERE key=?", (key,)).fetchone()
    return None if r is None else {"key": r["key"], "ids": _ids(r["items"])}


def set_vote(con, key, vote):
    con.execute("INSERT INTO votes(key,vote,at) VALUES(?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET vote=excluded.vote, at=excluded.at",
                (key, vote, now()))
    con.commit()


def get_vote(con, key):
    r = con.execute("SELECT vote FROM votes WHERE key=?", (key,)).fetchone()
    return r["vote"] if r else 0


def list_votes(con):
    """[(vote, [item ids])] for every voted outfit that is still stored."""
    return [(r["vote"], _ids(r["items"])) for r in con.execute(
        "SELECT v.vote, o.items FROM votes v JOIN outfits o ON o.key=v.key")]


def downvoted_keys(con):
    return {r["key"] for r in con.execute("SELECT key FROM votes WHERE vote=-1")}


def add_wear(con, date, key, ids):
    """One row per (date, key): a double click is ignored. Returns True if a row was added."""
    cur = con.execute("INSERT OR IGNORE INTO wear(date,key,items,at) VALUES(?,?,?,?)",
                      (date, key, json.dumps(list(ids)), now()))
    con.commit()
    return cur.rowcount > 0


def list_wear(con, limit=None, since=None):
    q, args = "SELECT * FROM wear", []
    if since:
        q += " WHERE date>=?"
        args.append(since)
    q += " ORDER BY date DESC, id DESC"
    if limit:
        q += " LIMIT ?"
        args.append(limit)
    return [{"id": r["id"], "date": r["date"], "key": r["key"], "ids": _ids(r["items"])}
            for r in con.execute(q, args)]


def delete_wear(con, wear_id):
    con.execute("DELETE FROM wear WHERE id=?", (wear_id,))
    con.commit()


def worn_ids(con):
    out = set()
    for r in con.execute("SELECT items FROM wear"):
        out.update(_ids(r["items"]))
    return out


def get_daily(con, date):
    r = con.execute("SELECT * FROM daily WHERE date=?", (date,)).fetchone()
    if r is None:
        return None
    try:
        w = json.loads(r["weather"])
    except ValueError:
        w = None
    return {"date": r["date"], "key": r["key"], "weather": w if isinstance(w, dict) else None,
            "note": r["note"]}


def insert_daily(con, date, key, weather, note):
    """INSERT OR IGNORE: the first of two parallel requests wins; callers re-read."""
    con.execute("INSERT OR IGNORE INTO daily(date,key,weather,note) VALUES(?,?,?,?)",
                (date, key, json.dumps(weather), note))
    con.commit()


def update_daily(con, date, key, note):
    con.execute("UPDATE daily SET key=?, note=? WHERE date=?", (key, note, date))
    con.commit()
