"""Wardrobe: clothes catalogue with vision auto-tagging (FastAPI, server-rendered, no login)."""
import contextlib
import datetime
import logging
import os
import random
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import db, gaps, images, outfits, pins, tagger, tags, weather

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("wardrobe")

HERE = Path(__file__).parent
DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "wardrobe.db")
# Fixed link for the daily post (the caller reaches us as 127.0.0.1, so no Host header).
OUTFITS_URL = "http://homelab:8091/outfits"
PHOTOS = os.path.join(DATA_DIR, "photos")
THUMBS = os.path.join(DATA_DIR, "thumbs")
MAX_FILE = 15 * 1024 * 1024
MAX_FILES = 25
MAX_BATCH = 400 * 1024 * 1024
SIZE_KEYS = [("top_size", "Top size"), ("bottom_size", "Bottom size"),
             ("shoe_size", "Shoe size"), ("dress_size", "Dress size")]

templates = Jinja2Templates(directory=str(HERE / "templates"))
templates.env.globals.update(
    CATEGORIES=tags.CATEGORIES, COLOURS=tags.COLOURS, SEASONS=tags.SEASONS,
    STYLES=tags.STYLES, REASONS=tags.RETIRE_REASONS)
KEY_RE = re.compile(r"^\d{1,9}(-\d{1,9}){0,5}$")
DEFAULT_REPEAT_DAYS = 7

os.makedirs(PHOTOS, exist_ok=True)
os.makedirs(THUMBS, exist_ok=True)


@contextlib.asynccontextmanager
async def lifespan(_app):
    db.connect(DB_PATH).close()
    tagger.start(DB_PATH, DATA_DIR)
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(HERE / "static")), name="static")
app.mount("/photos", StaticFiles(directory=PHOTOS), name="photos")
app.mount("/thumbs", StaticFiles(directory=THUMBS), name="thumbs")


def page(request, name, status_code=200, **ctx):
    con = db.connect(DB_PATH)
    try:
        c = db.counts(con)
    finally:
        con.close()
    ctx.update(path=request.url.path, counts=c, tagger=tagger.state, model=tagger.MODEL)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


def error(request, msg, code=400):
    return page(request, "error.html", status_code=code, message=msg)


def remove_files(photo, thumb):
    """Only ever removes uuid-named files directly under the two data dirs."""
    for d, name in ((PHOTOS, photo), (THUMBS, thumb)):
        if name and os.path.basename(name) == name:
            with contextlib.suppress(OSError):
                os.remove(os.path.join(d, name))


def save_images(data):
    """Process bytes and write them; returns (photo_name, thumb_name)."""
    photo_b, thumb_b = images.process(data)
    name = uuid.uuid4().hex + ".jpg"
    with open(os.path.join(PHOTOS, name), "wb") as f:
        f.write(photo_b)
    try:
        with open(os.path.join(THUMBS, name), "wb") as f:
            f.write(thumb_b)
    except OSError:
        remove_files(name, None)
        raise
    return name, name


def parse_price(v):
    v = (v or "").strip().replace(",", ".")
    if not v:
        return None
    f = float(v)
    if f < 0 or f > 1_000_000:
        raise ValueError("price out of range")
    return round(f, 2)


async def read_fields(request):
    form = await request.form()
    cat = form.get("category") or None
    style = form.get("style") or None
    return {
        "category": cat if cat in tags.CATEGORIES else None,
        "colours": [c for c in form.getlist("colours") if c in tags.COLOURS][:3],
        "seasons": [s for s in form.getlist("seasons") if s in tags.SEASONS],
        "style": style if style in tags.STYLES else None,
        "brand": (form.get("brand") or "").strip()[:60],
        "size": (form.get("size") or "").strip()[:20],
        "price": parse_price(form.get("price")),
        "notes": (form.get("notes") or "").strip()[:500],
    }


def safe_next(v, default):
    return v if v in ("/review", "/") else default


@app.get("/healthz")
def healthz():
    try:
        db.connect(DB_PATH).close()
    except Exception:  # noqa: BLE001
        return PlainTextResponse("db error", status_code=503)
    return PlainTextResponse("ok")


@app.get("/", response_class=HTMLResponse)
def index(request: Request, kind: str = "", category: str = "", status: str = "active"):
    status = status if status in ("active", "retired", "all") else "active"
    con = db.connect(DB_PATH)
    try:
        items = db.list_items(
            con, kind=kind if kind in ("owned", "wishlist") else None,
            category=category if category in tags.CATEGORIES else None,
            status=None if status == "all" else status)
    finally:
        con.close()
    return page(request, "index.html", items=items, kind=kind, category=category, status=status)


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return page(request, "upload.html", max_files=MAX_FILES, max_mb=MAX_FILE >> 20,
                max_batch_mb=MAX_BATCH >> 20)


@app.post("/upload", response_class=HTMLResponse)
async def upload(request: Request):
    try:
        total = int(request.headers.get("content-length") or 0)
    except ValueError:
        total = 0
    if total > MAX_BATCH + (1 << 20):
        return error(request, f"Batch too big: the limit is {MAX_BATCH >> 20} MB per upload. "
                              "Upload fewer photos at a time.", 413)
    try:
        form = await request.form(max_files=MAX_FILES + 1)
    except StarletteHTTPException:
        return error(request, f"Too many files: the limit is {MAX_FILES} per upload.", 413)
    files = [f for f in form.getlist("files") if getattr(f, "filename", "")]
    kind = "wishlist" if form.get("kind") == "wishlist" else "owned"
    if not files:
        return error(request, "No files chosen.")
    if len(files) > MAX_FILES:
        return error(request, f"Too many files: the limit is {MAX_FILES} per upload.", 413)
    saved, skipped, size = 0, [], 0
    con = db.connect(DB_PATH)
    try:
        for f in files:
            data = await f.read(MAX_FILE + 1)
            if len(data) > MAX_FILE:
                skipped.append(f"{f.filename} (over {MAX_FILE >> 20} MB)")
                continue
            size += len(data)
            if size > MAX_BATCH:
                return error(request, f"Batch too big: the limit is {MAX_BATCH >> 20} MB.", 413)
            try:
                photo, thumb = save_images(data)
            except images.BadImage:
                skipped.append(f"{f.filename} (not a readable image)")
                continue
            except OSError as e:
                skipped.append(f"{f.filename} (could not save: {e})")
                continue
            try:
                db.add_item(con, kind=kind, photo=photo, thumb=thumb)
            except Exception:
                remove_files(photo, thumb)
                raise
            saved += 1
    finally:
        con.close()
    tagger.wake.set()
    return page(request, "uploaded.html", saved=saved, skipped=skipped)


@app.get("/review", response_class=HTMLResponse)
def review(request: Request):
    con = db.connect(DB_PATH)
    try:
        items = db.list_items(con, tag_statuses=["tagged", "failed"])
    finally:
        con.close()
    return page(request, "review.html", items=items)


@app.get("/item/{item_id}", response_class=HTMLResponse)
def item_page(request: Request, item_id: int):
    con = db.connect(DB_PATH)
    try:
        it = db.get_item(con, item_id)
    finally:
        con.close()
    if not it:
        return error(request, "No such item.", 404)
    return page(request, "item.html", it=it)


@app.post("/item/{item_id}/save")
async def item_save(request: Request, item_id: int):
    try:
        fields = await read_fields(request)
    except ValueError:
        return error(request, "Price must be a number.")
    form = await request.form()
    con = db.connect(DB_PATH)
    try:
        if not db.get_item(con, item_id):
            return error(request, "No such item.", 404)
        db.save_fields(con, item_id, fields)
    finally:
        con.close()
    return RedirectResponse(safe_next(form.get("next"), f"/item/{item_id}"), status_code=303)


def _simple(action):
    def handler(item_id, *args):
        con = db.connect(DB_PATH)
        try:
            action(con, item_id, *args)
        finally:
            con.close()
    return handler


@app.post("/item/{item_id}/retry")
async def item_retry(request: Request, item_id: int):
    form = await request.form()
    _simple(db.requeue)(item_id)
    tagger.wake.set()
    return RedirectResponse(safe_next(form.get("next"), f"/item/{item_id}"), status_code=303)


@app.post("/item/{item_id}/bought")
def item_bought(item_id: int):
    _simple(db.mark_bought)(item_id)
    return RedirectResponse(f"/item/{item_id}", status_code=303)


@app.post("/item/{item_id}/retire")
async def item_retire(request: Request, item_id: int):
    form = await request.form()
    reason = form.get("reason")
    if reason not in tags.RETIRE_REASONS:
        return error(request, "Pick a reason.")
    _simple(db.retire)(item_id, reason)
    return RedirectResponse(f"/item/{item_id}", status_code=303)


@app.post("/item/{item_id}/restore")
def item_restore(item_id: int):
    _simple(db.restore)(item_id)
    return RedirectResponse(f"/item/{item_id}", status_code=303)


@app.post("/item/{item_id}/delete")
async def item_delete(request: Request, item_id: int):
    form = await request.form()
    if form.get("confirm") != "yes":
        return error(request, "Tick the confirm box to delete.")
    con = db.connect(DB_PATH)
    try:
        it = db.delete_item(con, item_id)
    finally:
        con.close()
    if it:
        remove_files(it["photo"], it["thumb"])
    return RedirectResponse("/", status_code=303)


@app.post("/item/{item_id}/photo")
async def item_photo(request: Request, item_id: int):
    form = await request.form()
    f = form.get("file")
    if not f or not getattr(f, "filename", ""):
        return error(request, "No file chosen.")
    data = await f.read(MAX_FILE + 1)
    if len(data) > MAX_FILE:
        return error(request, f"File over {MAX_FILE >> 20} MB.", 413)
    try:
        photo, thumb = save_images(data)
    except images.BadImage:
        return error(request, f"{f.filename} is not a readable image.")
    con = db.connect(DB_PATH)
    try:
        if not db.get_item(con, item_id):
            remove_files(photo, thumb)
            return error(request, "No such item.", 404)
        old = db.set_photo(con, item_id, photo, thumb)
    finally:
        con.close()
    remove_files(old["photo"], old["thumb"])
    tagger.wake.set()
    return RedirectResponse(f"/item/{item_id}", status_code=303)


@app.get("/wishlist/link", response_class=HTMLResponse)
def link_form(request: Request):
    return page(request, "link.html")


@app.post("/wishlist/link")
def link_submit(request: Request, url: str = Form("")):
    url = url.strip()
    if not pins.allowed_page_url(url):
        return error(request, "Only https links on pinterest.com (or pin.it) are accepted.")
    photo = thumb = err = None
    try:
        photo, thumb = save_images(pins.fetch_image(url))
    except (pins.PinError, images.BadImage, OSError) as e:
        log.info("pin fetch failed: %s", e)
        err = "Couldn't get the image; upload it on the item page"
    con = db.connect(DB_PATH)
    try:
        item_id = db.add_item(con, kind="wishlist", photo=photo, thumb=thumb, source_url=url,
                              tag_status="pending" if photo else "failed", tag_error=err)
    finally:
        con.close()
    if photo:
        tagger.wake.set()
    return RedirectResponse(f"/item/{item_id}", status_code=303)


def item_name(it):
    return " ".join(x for x in ((it["colours"] or [""])[0], it["category"], it.get("brand") or "") if x)


def repeat_days(prof):
    try:
        return max(0, min(60, int(prof.get("repeat_days", DEFAULT_REPEAT_DAYS))))
    except ValueError:
        return DEFAULT_REPEAT_DAYS


def float_or_none(prof, k):
    try:
        return float(prof[k])
    except (KeyError, ValueError):
        return None


def generate(con, today, wthr, rng=None, exclude=()):
    """Pick an outfit for today from the owned pool. -> (items, note); stores it in `outfits`."""
    pool = outfits.build_pool(db.list_items(con, kind="owned", status="active",
                                            tag_statuses=list(outfits.OK_STATUS)))
    by_id = {it["id"]: it for it in pool}
    prof = db.get_profile(con)
    days = repeat_days(prof)
    recent = set()
    if days:
        since = (today - datetime.timedelta(days=days)).isoformat()
        for wr in db.list_wear(con, since=since):
            recent.update(i for i in wr["ids"] if i in by_id
                          and by_id[i]["category"] in ("top", "bottom", "dress"))
    w = outfits.weights(db.list_votes(con), by_id)
    season = weather.season_for(today.month, wthr["tmax"] if wthr else None)
    items, note = outfits.pick(
        pool, season, wthr, w, rng or random.Random(),
        exclude_keys=set(exclude) | db.downvoted_keys(con), recent_ids=recent)
    if items:
        db.save_outfit(con, outfits.key_of(items), [it["id"] for it in items])
    return items, note


def stored_items(con, key):
    """Items of a stored outfit if all are still owned, active and tagged; else None."""
    o = db.get_outfit(con, key) if key else None
    if not o:
        return None
    out = []
    for i in o["ids"]:
        it = db.get_item(con, i)
        if (not it or it["kind"] != "owned" or it["status"] != "active"
                or it["tag_status"] not in outfits.OK_STATUS):
            return None
        out.append(it)
    return out or None


def ensure_daily(con, today):
    """Today's stored outfit: (items or None, weather or None, note). The forecast is fetched at most
    once per date (a failed fetch is stored as null); parallel first requests converge on one row."""
    date = today.isoformat()
    row = db.get_daily(con, date)
    if row is None:
        prof = db.get_profile(con)
        wthr = weather.fetch(float_or_none(prof, "lat"), float_or_none(prof, "lon"))
        items, note = generate(con, today, wthr, random.Random(date))
        db.insert_daily(con, date, outfits.key_of(items) if items else "", wthr, note)
        row = db.get_daily(con, date)
    items = stored_items(con, row["key"])
    if items is None:  # no outfit yet, or a stored item was retired or deleted: regenerate
        gen, note = generate(con, today, row["weather"], random.Random(date + row["key"]))
        db.update_daily(con, date, outfits.key_of(gen) if gen else "", note)
        row = db.get_daily(con, date)
        items = stored_items(con, row["key"])
    return items, row["weather"], row["note"], row["key"]


@app.get("/outfits", response_class=HTMLResponse)
def outfits_page(request: Request, another: int = 0):
    today = datetime.date.today()
    con = db.connect(DB_PATH)
    try:
        items, wthr, note, key = ensure_daily(con, today)
        if another and key:
            alt, alt_note = generate(con, today, wthr, exclude={key})
            if alt:
                items, note, key = alt, alt_note, outfits.key_of(alt)
            else:
                note = alt_note or "No other outfit available"
        vote = db.get_vote(con, key) if items else 0
        worn_today = any(wr["key"] == key for wr in db.list_wear(con, since=today.isoformat()))
    finally:
        con.close()
    return page(request, "outfits.html", items=items, key=key if items else "", note=note,
                weather_line=weather.describe(wthr), vote=vote, another=bool(another),
                worn_today=worn_today, today=today.isoformat(), item_name=item_name)


@app.get("/gaps", response_class=HTMLResponse)
def gaps_page(request: Request, season: str = ""):
    today = datetime.date.today()
    season = season or weather.season_for(today.month)
    if season != "all" and season not in gaps.SEASONS:
        return error(request, "Season must be spring, summer, autumn, winter or all.")
    con = db.connect(DB_PATH)
    try:
        items = db.list_items(con, kind="owned", status="active",
                              tag_statuses=list(outfits.OK_STATUS))
        wish = db.list_items(con, kind="wishlist", status="active")
        prof = db.get_profile(con)
    finally:
        con.close()
    rows, reason, currents = [], None, []
    for s in (gaps.SEASONS if season == "all" else (season,)):
        r, cur, why = gaps.analyse(items, s, prof, wish)
        rows += r
        currents.append((s, cur))
        reason = reason or why
    order = {c: i for i, c in enumerate(gaps.GAP_CATS)}
    rows.sort(key=lambda r: (-r["unlocks"], order[r["category"]], tags.COLOURS.index(r["colour"]),
                             gaps.SEASONS.index(r["season"])))
    rows = rows[:20]
    return page(request, "gaps.html", rows=rows, season=season, seasons=gaps.SEASONS,
                currents=currents, reason=None if rows else (reason or "Nothing to suggest yet"))


@app.post("/outfits/vote")
def outfit_vote(request: Request, key: str = Form(""), vote: int = Form(0)):
    if not KEY_RE.match(key) or vote not in (-1, 1):
        return error(request, "Bad vote.")
    today = datetime.date.today()
    con = db.connect(DB_PATH)
    try:
        if not db.get_outfit(con, key):
            return error(request, "No such outfit.", 404)
        db.set_vote(con, key, vote)
        row = db.get_daily(con, today.isoformat())
        if vote == -1 and row and row["key"] == key:  # swap a disliked daily pick right away
            gen, note = generate(con, today, row["weather"],
                                 random.Random(today.isoformat() + key))
            db.update_daily(con, today.isoformat(), outfits.key_of(gen) if gen else "", note)
    finally:
        con.close()
    return RedirectResponse("/outfits", status_code=303)


@app.post("/outfits/wear")
def outfit_wear(request: Request, key: str = Form(""), date: str = Form("")):
    if not KEY_RE.match(key):
        return error(request, "Bad outfit.")
    today = datetime.date.today()
    try:
        d = datetime.date.fromisoformat(date.strip()) if date.strip() else today
    except ValueError:
        return error(request, "Date must look like 2026-10-23.")
    if d > today:
        return error(request, "That date is in the future.")
    con = db.connect(DB_PATH)
    try:
        o = db.get_outfit(con, key)
        if not o:
            return error(request, "No such outfit.", 404)
        db.add_wear(con, d.isoformat(), key, o["ids"])
    finally:
        con.close()
    return RedirectResponse("/outfits", status_code=303)


@app.get("/worn", response_class=HTMLResponse)
def worn_page(request: Request):
    today = datetime.date.today()
    con = db.connect(DB_PATH)
    try:
        pool = outfits.build_pool(db.list_items(con, kind="owned", status="active",
                                                tag_statuses=list(outfits.OK_STATUS)))
        worn = db.worn_ids(con)
        never = []
        for it in pool:
            if it["id"] in worn:
                continue
            try:
                since = datetime.date.fromisoformat((it["bought_at"] or it["created_at"])[:10])
            except (TypeError, ValueError):
                since = today
            never.append((max(0, (today - since).days), it))
        never.sort(key=lambda t: -t[0])
        rows = []
        for wr in db.list_wear(con, limit=60):
            rows.append({"id": wr["id"], "date": wr["date"],
                         "items": [db.get_item(con, i) for i in wr["ids"]]})
    finally:
        con.close()
    return page(request, "worn.html", never=never, rows=rows, item_name=item_name)


@app.post("/worn/{wear_id}/delete")
def worn_delete(wear_id: int):
    con = db.connect(DB_PATH)
    try:
        db.delete_wear(con, wear_id)
    finally:
        con.close()
    return RedirectResponse("/worn", status_code=303)


@app.get("/api/daily.txt")
def daily_txt(request: Request):
    today = datetime.date.today()
    con = db.connect(DB_PATH)
    try:
        if db.get_profile(con).get("daily_discord") != "1":
            return Response(status_code=204)
        items, wthr, note, _key = ensure_daily(con, today)
    finally:
        con.close()
    head = f"Outfit for {today.strftime('%a')} {today.day} {today.strftime('%b')}"
    if wthr:
        head += f" ({weather.brief(wthr)})"
    if not items:
        line = f"{head}: {note or 'no outfit available'}."
    else:
        main = [item_name(it) for it in items if it["category"] != "outerwear"]
        outer = [item_name(it) for it in items if it["category"] == "outerwear"]
        line = f"{head}: {', '.join(main)}" + (f" + {outer[0]}" if outer else "") + "."
        if note:
            line += f" ({note})"
    return PlainTextResponse(f"{line} {OUTFITS_URL}")


@app.get("/profile", response_class=HTMLResponse)
def profile_form(request: Request):
    con = db.connect(DB_PATH)
    try:
        prof = db.get_profile(con)
    finally:
        con.close()
    return page(request, "profile.html", prof=prof, size_keys=SIZE_KEYS, saved=False,
                repeat_default=DEFAULT_REPEAT_DAYS)


@app.post("/profile")
async def profile_save(request: Request):
    form = await request.form()
    values = {k: (form.get(k) or "").strip()[:20] for k, _ in SIZE_KEYS}
    values["currency"] = (form.get("currency") or "GBP").strip().upper()[:3] or "GBP"
    try:
        for c in tags.CATEGORIES:
            p = parse_price(form.get(f"max_price_{c}"))
            values[f"max_price_{c}"] = "" if p is None else p
    except ValueError:
        return error(request, "Prices must be numbers.")
    try:
        for k, lim in (("lat", 90), ("lon", 180)):
            v = (form.get(k) or "").strip().replace(",", ".")
            values[k] = ""
            if v:
                f = float(v)
                if not -lim <= f <= lim:
                    raise ValueError
                values[k] = f
        if bool(values["lat"] != "") != bool(values["lon"] != ""):
            return error(request, "Set both latitude and longitude, or neither.")
    except ValueError:
        return error(request, "Latitude must be -90..90 and longitude -180..180.")
    rd = (form.get("repeat_days") or "").strip()
    values["repeat_days"] = ""
    if rd:
        if not rd.isdigit() or not 0 <= int(rd) <= 60:
            return error(request, "No-repeat days must be a whole number from 0 to 60.")
        values["repeat_days"] = int(rd)
    values["daily_discord"] = "1" if form.get("daily_discord") else ""
    con = db.connect(DB_PATH)
    try:
        db.set_profile(con, values)
    finally:
        con.close()
    return RedirectResponse("/profile", status_code=303)
