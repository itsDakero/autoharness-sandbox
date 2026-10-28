"""personal.json for the Hermes assistant: a small, read-only summary of Dan's own data.

Every block is {"updated_at", "data" | None, "error" | None}. A failed source is None with a short error
string (never an env value, header or response body); nothing from an earlier run is reused."""
import asyncio
import logging
import os
import time
from datetime import datetime, timedelta

import httpx

log = logging.getLogger("uvicorn.error")

FITNESS_URL = os.environ.get("FITNESS_URL", "http://fitness:8080")
WARDROBE_URL = os.environ.get("WARDROBE_URL", "http://wardrobe:8080")
BOOKS_URL = os.environ.get("BOOKS_URL", "http://books:8080")
CHANGEDETECTION_URL = os.environ.get("CHANGEDETECTION_URL", "http://changedetection:5000")
LEAFGREEN_URL = os.environ.get("LEAFGREEN_URL", "http://leafgreen:8080")
DEAL_DAYS = 7
TIMEOUT = 5


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _err(e: Exception) -> str:
    if isinstance(e, LookupError):
        return "not configured"
    if isinstance(e, httpx.TimeoutException):
        return "timeout"
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    return type(e).__name__


def _block(data, error) -> dict:
    return {"updated_at": _now(), "data": data, "error": error}


async def _get(c: httpx.AsyncClient, url: str, **kw) -> httpx.Response:
    r = await c.get(url, **kw)
    r.raise_for_status()
    return r


async def _fitness(c) -> dict:
    try:
        return _block((await _get(c, f"{FITNESS_URL}/api/feed.json")).json(), None)
    except Exception as e:  # noqa: BLE001
        return _block(None, _err(e))


async def _wardrobe(c) -> dict:
    try:
        r = await _get(c, f"{WARDROBE_URL}/api/daily.txt")
        if r.status_code == 204:
            return _block(None, "daily outfit toggle is off in the wardrobe profile")
        return _block({"outfit": r.text.strip()}, None)
    except Exception as e:  # noqa: BLE001
        return _block(None, _err(e))


async def _reading(c) -> dict:
    try:
        r = await _get(c, f"{BOOKS_URL}/api/current")
        j = r.json()
        out = []
        for b in j if isinstance(j, list) else []:
            out.append({
                "title": b.get("title"),
                "authors": b.get("authors") or [],
                "percent_read": b.get("percent_read"),
                "current_page": b.get("current_page"),
                "started": b.get("started"),
            })
        return _block(out, None)
    except Exception as e:  # noqa: BLE001
        return _block(None, _err(e))


async def _watches(c) -> list:
    key = os.environ.get("CHANGEDETECTION_API_KEY", "")
    if not key:
        raise LookupError("not configured")
    r = await _get(c, f"{CHANGEDETECTION_URL}/api/v1/watch", headers={"x-api-key": key})
    since = time.time() - DEAL_DAYS * 86400
    out = []
    for w in (r.json() or {}).values():
        try:
            lc = float(w.get("last_changed") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if lc and lc >= since:
            out.append({"title": w.get("title") or w.get("url"), "url": w.get("url"),
                        "last_changed": datetime.fromtimestamp(lc).astimezone().isoformat(timespec="seconds")})
    return out


async def _card_drops(c) -> list:
    r = await _get(c, f"{LEAFGREEN_URL}/api/cards/prices")
    since = (datetime.now() - timedelta(days=DEAL_DAYS)).date().isoformat()
    out = []
    for e in (r.json() or {}).values():
        alerted = e.get("alerted")
        if not alerted or str(alerted) < since:
            continue
        hist = e.get("hist") or []
        low = hist[-1][1] if hist and len(hist[-1]) >= 2 else None
        out.append({"name": e.get("name"), "set": e.get("set"), "low": low, "alerted": alerted})
    return out


async def _deals(c) -> dict:
    res = await asyncio.gather(_watches(c), _card_drops(c), return_exceptions=True)
    errors = [_err(r) for r in res if isinstance(r, Exception)]
    data = {"watches": None if isinstance(res[0], Exception) else res[0],
            "card_drops": None if isinstance(res[1], Exception) else res[1]}
    if len(errors) == 2:
        data = None
    return _block(data, "; ".join(errors) or None)


async def build() -> dict:
    """Fetches every source in parallel; never raises for a source failure."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        names = ("fitness", "wardrobe", "reading", "deals")
        blocks = await asyncio.gather(_fitness(c), _wardrobe(c), _reading(c), _deals(c))
    for name, b in zip(names, blocks):
        if b["error"] and "not configured" not in b["error"] and "toggle is off" not in b["error"]:
            log.warning("Personal feed: %s unavailable: %s", name, b["error"])
    return {"updated": _now(), **dict(zip(names, blocks))}
