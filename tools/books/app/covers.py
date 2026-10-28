"""Background cover worker: one daemon thread, one request at a time, never blocks a page."""
import logging
import os
import threading
import time

from . import db, openlibrary

log = logging.getLogger("books.covers")
PAUSE = 1
IDLE = 30
_wake = threading.Event()


def wake():
    _wake.set()


def cover_path(data_dir, book_id):
    return os.path.join(data_dir, "covers", f"{book_id}.jpg")


def fetch_one(con, data_dir, b):
    """Try ISBN, then cover id, then one title+author search. Records ok/none/error."""
    dest = cover_path(data_dir, b["id"])
    cover_id = b["ol_cover_id"]
    try:
        urls = []
        for isbn in (b["isbn13"], b["isbn10"]):
            if isbn:
                urls.append(f"https://covers.openlibrary.org/b/isbn/{isbn}-M.jpg?default=false")
        if cover_id:
            urls.append(f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg?default=false")
        elif not urls:
            cover_id = openlibrary.lookup_cover_id(b["title"], b["authors"])
            if cover_id:
                urls.append(f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg?default=false")
        for i, url in enumerate(urls):
            try:
                openlibrary.fetch_image(url, dest)
                db.set_cover(con, b["id"], "ok", cover_id)
                return "ok"
            except openlibrary.CoverMissing:
                if i < len(urls) - 1:
                    time.sleep(PAUSE)
        db.set_cover(con, b["id"], "none", cover_id)
        return "none"
    except Exception as e:  # noqa: BLE001
        log.warning("cover %s failed: %s", b["id"], type(e).__name__)
        db.set_cover(con, b["id"], "error")
        return "error"


def run(db_path, data_dir):
    os.makedirs(os.path.join(data_dir, "covers"), exist_ok=True)
    while True:
        try:
            con = db.connect(db_path)
            try:
                b = db.next_cover_job(con)
                if b is not None:
                    fetch_one(con, data_dir, b)
            finally:
                con.close()
            if b is not None:
                time.sleep(PAUSE)
                continue
        except Exception:  # noqa: BLE001
            log.exception("cover worker")
        _wake.wait(IDLE)
        _wake.clear()


def start(db_path, data_dir):
    t = threading.Thread(target=run, args=(db_path, data_dir), daemon=True, name="covers")
    t.start()
    return t
