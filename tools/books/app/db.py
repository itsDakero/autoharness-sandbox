"""SQLite for the books app (stdlib only). One short-lived connection per call site."""
import datetime
import os
import sqlite3
import time

MIGRATIONS = [
    """
    CREATE TABLE books(
        id INTEGER PRIMARY KEY,
        goodreads_id TEXT, isbn13 TEXT, isbn10 TEXT,
        title TEXT NOT NULL, authors TEXT NOT NULL DEFAULT '',
        pages INTEGER, ol_cover_id INTEGER,
        shelf TEXT NOT NULL DEFAULT 'want' CHECK(shelf IN ('reading','want','read','dnf')),
        rating INTEGER CHECK(rating IS NULL OR rating BETWEEN 1 AND 5),
        date_added TEXT, date_started TEXT, date_finished TEXT,
        current_page INTEGER, percent INTEGER, notes TEXT, review TEXT,
        cover_status TEXT CHECK(cover_status IS NULL OR cover_status IN ('ok','none','error')),
        cover_checked_at TEXT,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX books_shelf ON books(shelf);
    CREATE INDEX books_gr ON books(goodreads_id);
    CREATE INDEX books_isbn13 ON books(isbn13);
    CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    """,
]

SHELVES = ("reading", "want", "read", "dnf")
SHELF_NAMES = {"reading": "Reading", "want": "Want to read", "read": "Read", "dnf": "Did not finish"}
EDIT_FIELDS = ("title", "authors", "isbn13", "isbn10", "pages", "shelf", "rating", "date_added",
               "date_started", "date_finished", "current_page", "percent", "notes", "review")
IMPORT_FIELDS = ("goodreads_id", "isbn13", "isbn10", "authors", "pages", "ol_cover_id", "rating",
                 "date_added", "date_finished", "notes", "review")
RETRY_HOURS = 24


def now():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.date.today().isoformat()


def connect(path):
    if path != ":memory:":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    con = sqlite3.connect(path, timeout=10)
    con.row_factory = sqlite3.Row
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


def first_author(authors):
    return (authors or "").split(",")[0].strip().lower()


def find_match(con, book):
    """goodreads_id, then isbn13, then lower(title)+first author. Returns a row or None."""
    if book.get("goodreads_id"):
        r = con.execute("SELECT * FROM books WHERE goodreads_id=?", (book["goodreads_id"],)).fetchone()
        if r:
            return r
    if book.get("isbn13"):
        r = con.execute("SELECT * FROM books WHERE isbn13=?", (book["isbn13"],)).fetchone()
        if r:
            return r
    title, fa = book["title"].strip().lower(), first_author(book.get("authors"))
    for r in con.execute("SELECT * FROM books WHERE lower(title)=?", (title,)):
        if first_author(r["authors"]) == fa:
            return r
    return None


def _fill_progress(book):
    if book.get("shelf") == "read":
        book.setdefault("percent", 100)
    return book


def insert_book(con, book):
    ts = now()
    shelf = book.get("shelf") or "want"
    cols = {k: book.get(k) for k in IMPORT_FIELDS + ("title", "date_started", "current_page", "percent")}
    cols["shelf"] = shelf
    if shelf == "reading" and not cols.get("date_started"):
        cols["date_started"] = today()
    if shelf == "read" and cols.get("percent") is None:
        cols["percent"] = 100
    if cols.get("authors") is None:
        cols["authors"] = ""
    cols["created_at"] = cols["updated_at"] = ts
    names = ",".join(cols)
    cur = con.execute(f"INSERT INTO books({names}) VALUES({','.join('?' * len(cols))})",
                      list(cols.values()))
    return cur.lastrowid


def fill_empty(con, row, book):
    """Fill fields that are empty in the app. Never overwrite. Returns the changed field names."""
    changed = {}
    for k in IMPORT_FIELDS:
        if book.get(k) not in (None, "") and row[k] in (None, ""):
            changed[k] = book[k]
    if changed:
        sets = ",".join(f"{k}=?" for k in changed)
        con.execute(f"UPDATE books SET {sets}, updated_at=? WHERE id=?",
                    list(changed.values()) + [now(), row["id"]])
    return list(changed)


def import_books(con, parsed, skipped=()):
    """parsed: list of (line, book). One transaction. Returns a summary dict."""
    added, updated, skips = [], [], [(t, r) for t, r in skipped]
    seen = set()
    with con:
        for _n, book in parsed:
            key = book.get("goodreads_id") or (book["title"].lower(), first_author(book.get("authors")))
            if key in seen:
                skips.append((book["title"], "duplicate in file"))
                continue
            seen.add(key)
            row = find_match(con, book)
            if row is None:
                insert_book(con, book)
                added.append((book["title"], book["shelf"]))
            else:
                changed = fill_empty(con, row, book)
                if changed:
                    updated.append((book["title"], "filled " + ", ".join(changed)))
                else:
                    skips.append((book["title"], "already in library"))
    return {"added": added, "updated": updated, "skipped": skips}


def get(con, book_id):
    return con.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()


def list_books(con, shelf="", year="", q=""):
    sql, args = "SELECT * FROM books WHERE 1=1", []
    if shelf in SHELVES:
        sql += " AND shelf=?"
        args.append(shelf)
    if year.isdigit():
        sql += " AND substr(date_finished,1,4)=?"
        args.append(year)
    if q.strip():
        sql += " AND (title LIKE ? OR authors LIKE ?)"
        args += [f"%{q.strip()}%"] * 2
    sql += " ORDER BY COALESCE(date_finished, date_started, date_added, created_at) DESC, id DESC"
    return con.execute(sql, args).fetchall()


def years(con):
    return [r[0] for r in con.execute(
        "SELECT DISTINCT substr(date_finished,1,4) y FROM books WHERE date_finished IS NOT NULL "
        "ORDER BY y DESC")]


def stats(con, year=None):
    year = year or str(datetime.date.today().year)
    one = lambda sql, a=(): con.execute(sql, a).fetchone()[0]  # noqa: E731
    return {
        "read_this_year": one("SELECT COUNT(*) FROM books WHERE shelf='read' AND "
                              "substr(date_finished,1,4)=?", (year,)),
        "want_to_read": one("SELECT COUNT(*) FROM books WHERE shelf='want'"),
        "reading": one("SELECT COUNT(*) FROM books WHERE shelf='reading'"),
    }


def percent_of(b):
    if b["pages"] and b["current_page"] is not None:
        return min(100, round(100 * b["current_page"] / b["pages"]))
    return b["percent"]


def current(con):
    out = []
    for b in con.execute("SELECT * FROM books WHERE shelf='reading' ORDER BY date_started DESC, id DESC"):
        out.append({"title": b["title"],
                    "authors": [a.strip() for a in b["authors"].split(",") if a.strip()],
                    "percent_read": percent_of(b), "current_page": b["current_page"],
                    "started": b["date_started"]})
    return out


def update_book(con, book_id, **f):
    """Set edit fields. Marking Reading sets date_started if empty."""
    row = get(con, book_id)
    if row is None:
        return False
    f = {k: v for k, v in f.items() if k in EDIT_FIELDS}
    if f.get("shelf") == "reading" and not (f.get("date_started") or row["date_started"]):
        f["date_started"] = today()
    if f.get("shelf") == "read" and not (f.get("date_finished") or row["date_finished"]):
        f["date_finished"] = today()
    if f:
        sets = ",".join(f"{k}=?" for k in f)
        with con:
            con.execute(f"UPDATE books SET {sets}, updated_at=? WHERE id=?",
                        list(f.values()) + [now(), book_id])
    return True


def set_progress(con, book_id, page=None, percent=None):
    row = get(con, book_id)
    if row is None:
        return False
    if page is not None:
        if row["pages"]:
            page = min(page, row["pages"])
            percent = min(100, round(100 * page / row["pages"]))
        update_book(con, book_id, current_page=page, percent=percent)
    elif percent is not None:
        percent = max(0, min(100, percent))
        page = round(row["pages"] * percent / 100) if row["pages"] else row["current_page"]
        update_book(con, book_id, percent=percent, current_page=page)
    return True


def finish(con, book_id, rating, date):
    return update_book(con, book_id, shelf="read", rating=rating, date_finished=date, percent=100)


def delete(con, book_id):
    with con:
        con.execute("DELETE FROM books WHERE id=?", (book_id,))


def meta_get(con, key):
    r = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else None


def meta_set(con, key, value):
    with con:
        con.execute("INSERT INTO meta(key,value) VALUES(?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def next_cover_job(con):
    """A book needing a cover: never checked, or errored more than RETRY_HOURS ago."""
    limit = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(time.time() - RETRY_HOURS * 3600))
    return con.execute(
        "SELECT * FROM books WHERE cover_status IS NULL OR "
        "(cover_status='error' AND cover_checked_at < ?) ORDER BY cover_checked_at IS NOT NULL, id LIMIT 1",
        (limit,)).fetchone()


def set_cover(con, book_id, status, ol_cover_id=None):
    with con:
        con.execute("UPDATE books SET cover_status=?, cover_checked_at=?, "
                    "ol_cover_id=COALESCE(?, ol_cover_id) WHERE id=?",
                    (status, now(), ol_cover_id, book_id))
