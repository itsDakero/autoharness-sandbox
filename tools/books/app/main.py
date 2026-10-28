"""Books: a small phone-first reading tracker (FastAPI, server-rendered, no login)."""
import contextlib
import datetime
import logging
import os
import re
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import covers, db, goodreads, openlibrary

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("books")

HERE = Path(__file__).parent
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "books.db")
COVERS = os.path.join(DATA_DIR, "covers")
SEED = os.path.join(DATA_DIR, "seed", "goodreads_library_export.csv")
MAX_CSV = 5 * 1024 * 1024
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.globals.update(SHELVES=db.SHELVES, SHELF_NAMES=db.SHELF_NAMES, percent_of=db.percent_of)

os.makedirs(COVERS, exist_ok=True)


def import_seed(con):
    """First run: import the Goodreads CSV on disk once."""
    if db.meta_get(con, "seed_imported") or not os.path.isfile(SEED):
        return
    with open(SEED, "rb") as f:
        parsed, skipped = goodreads.parse_csv(f.read(MAX_CSV))
    res = db.import_books(con, parsed, skipped)
    db.meta_set(con, "seed_imported", db.now())
    log.info("seed import: %d added, %d updated, %d skipped",
             len(res["added"]), len(res["updated"]), len(res["skipped"]))


@contextlib.asynccontextmanager
async def lifespan(_app):
    con = db.connect(DB_PATH)
    try:
        try:
            import_seed(con)
        except Exception:  # noqa: BLE001
            log.exception("seed import failed")
    finally:
        con.close()
    covers.start(DB_PATH, DATA_DIR)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
app.mount("/covers", StaticFiles(directory=COVERS), name="covers")


def page(request, name, status_code=200, **ctx):
    ctx.update(path=request.url.path, today=db.today())
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def error(request, msg, code=400):
    return page(request, "error.html", status_code=code, message=msg)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return error(request, "Page not found." if exc.status_code == 404 else "Something went wrong.",
                 exc.status_code)


def to_int(v, lo=None, hi=None):
    try:
        n = int(str(v).strip())
    except ValueError:
        return None
    if lo is not None and n < lo:
        return None
    if hi is not None and n > hi:
        return None
    return n


def to_date(v):
    v = (v or "").strip()
    return v if DATE_RE.match(v) else None


@app.get("/healthz")
def healthz():
    try:
        con = db.connect(DB_PATH)
        try:
            con.execute("select 1").fetchone()
        finally:
            con.close()
    except Exception:  # noqa: BLE001
        return PlainTextResponse("db error", status_code=503)
    return PlainTextResponse("ok")


@app.get("/api/current")
def api_current():
    con = db.connect(DB_PATH)
    try:
        return JSONResponse(db.current(con))
    finally:
        con.close()


@app.get("/api/stats")
def api_stats():
    con = db.connect(DB_PATH)
    try:
        return JSONResponse(db.stats(con))
    finally:
        con.close()


@app.get("/")
def home(request: Request):
    con = db.connect(DB_PATH)
    try:
        return page(request, "home.html", reading=db.list_books(con, "reading"),
                    want=db.list_books(con, "want"), stats=db.stats(con),
                    year=datetime.date.today().year)
    finally:
        con.close()


@app.get("/library")
def library(request: Request, shelf: str = "", year: str = "", q: str = ""):
    con = db.connect(DB_PATH)
    try:
        return page(request, "library.html", books=db.list_books(con, shelf, year, q),
                    years=db.years(con), shelf=shelf, year=year, q=q)
    finally:
        con.close()


@app.get("/book/{book_id}")
def book_page(request: Request, book_id: int):
    con = db.connect(DB_PATH)
    try:
        b = db.get(con, book_id)
    finally:
        con.close()
    if b is None:
        return error(request, "No such book.", 404)
    return page(request, "book.html", b=b)


@app.post("/book/{book_id}")
def book_save(request: Request, book_id: int, title: str = Form(""), authors: str = Form(""),
              shelf: str = Form("want"), rating: str = Form(""), pages: str = Form(""),
              isbn13: str = Form(""), date_started: str = Form(""), date_finished: str = Form(""),
              current_page: str = Form(""), notes: str = Form(""), review: str = Form("")):
    if not title.strip():
        return error(request, "Title can't be empty.")
    if shelf not in db.SHELVES:
        return error(request, "Pick a shelf.")
    con = db.connect(DB_PATH)
    try:
        ok = db.update_book(
            con, book_id, title=title.strip(), authors=authors.strip(), shelf=shelf,
            rating=to_int(rating, 1, 5), pages=to_int(pages, 1),
            isbn13=goodreads.clean_isbn(isbn13), date_started=to_date(date_started),
            date_finished=to_date(date_finished), current_page=to_int(current_page, 0),
            notes=notes.strip() or None, review=review.strip() or None)
    finally:
        con.close()
    if not ok:
        return error(request, "No such book.", 404)
    return RedirectResponse(f"/book/{book_id}", status_code=303)


@app.post("/book/{book_id}/progress")
def book_progress(request: Request, book_id: int, page_no: str = Form(""), percent: str = Form("")):
    p, pc = to_int(page_no, 0), to_int(percent, 0, 100)
    if p is None and pc is None:
        return error(request, "Enter a page number or a percentage.")
    con = db.connect(DB_PATH)
    try:
        ok = db.set_progress(con, book_id, page=p, percent=None if p is not None else pc)
    finally:
        con.close()
    if not ok:
        return error(request, "No such book.", 404)
    return RedirectResponse("/", status_code=303)


@app.post("/book/{book_id}/start")
def book_start(book_id: int):
    con = db.connect(DB_PATH)
    try:
        db.update_book(con, book_id, shelf="reading")
    finally:
        con.close()
    return RedirectResponse("/", status_code=303)


@app.get("/book/{book_id}/finish")
def finish_form(request: Request, book_id: int):
    con = db.connect(DB_PATH)
    try:
        b = db.get(con, book_id)
    finally:
        con.close()
    if b is None:
        return error(request, "No such book.", 404)
    return page(request, "finish.html", b=b)


@app.post("/book/{book_id}/finish")
def finish_submit(request: Request, book_id: int, rating: str = Form(""), date: str = Form("")):
    con = db.connect(DB_PATH)
    try:
        ok = db.finish(con, book_id, to_int(rating, 1, 5), to_date(date) or db.today())
    finally:
        con.close()
    if not ok:
        return error(request, "No such book.", 404)
    return RedirectResponse("/", status_code=303)


@app.get("/book/{book_id}/delete")
def delete_confirm(request: Request, book_id: int):
    con = db.connect(DB_PATH)
    try:
        b = db.get(con, book_id)
    finally:
        con.close()
    if b is None:
        return error(request, "No such book.", 404)
    return page(request, "delete.html", b=b)


@app.post("/book/{book_id}/delete")
def delete_submit(book_id: int):
    con = db.connect(DB_PATH)
    try:
        db.delete(con, book_id)
    finally:
        con.close()
    with contextlib.suppress(OSError):
        os.unlink(covers.cover_path(DATA_DIR, book_id))
    return RedirectResponse("/library", status_code=303)


@app.get("/add")
def add_form(request: Request, q: str = ""):
    results, err = [], None
    q = q.strip()
    if q:
        try:
            results = openlibrary.search(q)
            if not results:
                err = "No matches on Open Library. Use the manual form below."
        except Exception:  # noqa: BLE001
            err = "Open Library didn't answer. Use the manual form below, or try again."
    return page(request, "add.html", q=q, results=results, err=err)


@app.post("/add")
def add_submit(request: Request, title: str = Form(""), authors: str = Form(""),
               isbn13: str = Form(""), isbn10: str = Form(""), pages: str = Form(""),
               cover_id: str = Form(""), shelf: str = Form("want")):
    if not title.strip() or not authors.strip():
        return error(request, "Title and author are both needed.")
    if shelf not in db.SHELVES:
        return error(request, "Pick a shelf.")
    book = {"title": title.strip(), "authors": authors.strip(), "shelf": shelf,
            "isbn13": goodreads.clean_isbn(isbn13), "isbn10": goodreads.clean_isbn(isbn10),
            "pages": to_int(pages, 1), "ol_cover_id": to_int(cover_id, 1),
            "date_added": db.today()}
    if shelf == "read":
        book["date_finished"] = db.today()
    con = db.connect(DB_PATH)
    try:
        with con:
            new_id = db.insert_book(con, book)
    finally:
        con.close()
    covers.wake()
    return RedirectResponse(f"/book/{new_id}", status_code=303)


@app.get("/import")
def import_form(request: Request):
    return page(request, "import.html", result=None)


@app.post("/import")
async def import_submit(request: Request, file: UploadFile | None = None):
    if file is None or not file.filename:
        return error(request, "No file chosen.")
    data = await file.read(MAX_CSV + 1)
    if len(data) > MAX_CSV:
        return error(request, "File is over 5 MB.", 413)
    try:
        parsed, skipped = goodreads.parse_csv(data)
    except Exception:  # noqa: BLE001
        return error(request, "That file isn't a readable CSV.")
    if not parsed and not skipped:
        return error(request, "No rows found. Is this a Goodreads library export?")
    con = db.connect(DB_PATH)
    try:
        res = db.import_books(con, parsed, skipped)
    finally:
        con.close()
    covers.wake()
    return page(request, "import.html", result=res)
