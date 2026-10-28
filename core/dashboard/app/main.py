"""Homelab dashboard: tiles from homelab.* container labels, status from Uptime Kuma, live widgets."""
import asyncio
import html
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse, Response

from . import auth, ideas, personal, town, widgets

DOCKER_URL = os.environ.get("DOCKER_URL", "http://docker-socket-proxy:2375")
KUMA_URL = os.environ.get("KUMA_URL", "http://uptime-kuma:3001")
KUMA_API_KEY = os.environ.get("KUMA_API_KEY", "")
CACHE_SECONDS = 15
# Hermes assistant (M6 stage D): a status summary it reads from a read-only mount. Empty = not written.
AGENT_FEED_DIR = os.environ.get("AGENT_FEED_DIR", "")
AGENT_FEED_SECONDS = 60
PERSONAL_FEED_SECONDS = 900
INDEX = Path(__file__).parent / "static" / "index.html"
TOWN = Path(__file__).parent / "static" / "town.html"
LOGIN = Path(__file__).parent / "static" / "login.html"
# Without a login, /api/services lists only the family tiles, without status
PUBLIC_FIELDS = ("id", "name", "group", "icon", "audience", "description", "port", "lan_host")

HOST_RULE = re.compile(r"Host\(`([^`]+)`\)")
# Tiles for things outside Docker (the Mac mini): homelab.external.<id>.<field> on any container's labels
EXTERNAL = re.compile(r"^homelab\.external\.([a-z0-9][a-z0-9-]*)\.(name|group|icon|audience|description)$")
METRIC = re.compile(r"^monitor_status\{([^}]*)\}\s+(\S+)", re.M)
METRIC_LABEL = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
KUMA_STATUS = {0: "down", 1: "up", 2: "pending", 3: "maintenance"}
# Lower = worse; a service with several monitors shows its worst one.
SEVERITY = {"down": 0, "pending": 1, "unknown": 2, "maintenance": 3, "up": 4}

log = logging.getLogger("uvicorn.error")


async def agent_feed() -> None:
    """Writes status.json for the Hermes assistant every minute: what the admin page shows, nothing secret
    (labels, Kuma states, note titles). Hermes has no network tools, so this file is how it sees the homelab."""
    path = Path(AGENT_FEED_DIR) / "status.json"
    while True:
        try:
            data = await all_services()
            queue, parked, proposed, deploys = await asyncio.gather(*(asyncio.to_thread(f) for f in (
                ideas.queue, ideas.parked, ideas.proposed, ideas.deploys)))
            feed = {
                "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
                "kuma_reachable": data["kuma"],
                "services": [{k: s[k] for k in ("id", "name", "group", "description", "status")}
                             for s in data["services"]],
                "ideas": {
                    "queued": [{"title": i["title"], "note": f"ideas/{i['file']}"} for i in queue.get("ideas", [])],
                    "built": queue.get("done", 0),
                    "parked": [{"title": i["title"], "note": f"ideas/parked/{i['slug']}.md"}
                               for i in parked["items"]],
                    "proposed": [{"title": i["title"], "score": i["score"], "risk": i["risk"], "source": i["source"],
                                  "note": f"ideas/proposed/{i['slug']}.md"} for i in proposed["items"]],
                    "ready_to_deploy": [{"title": b.get("title"), "slug": b.get("slug")} for b in deploys["ready"]],
                    "building": deploys["building"],
                    "rejected": [{"title": i["title"], "reason": i["reason"], "note": f"ideas/rejected/{i['file']}"}
                                 for i in queue.get("rejected", [])],
                },
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(feed, indent=1))
            os.replace(tmp, path)
        except Exception as e:  # keep going: a stale file is better than none
            log.warning("Agent feed not written: %s", e)
        await asyncio.sleep(AGENT_FEED_SECONDS)


async def personal_feed() -> None:
    """Writes personal.json every 15 min (fitness, outfit, books, deals; see app/personal.py). Atomic: tmp in
    the same dir + os.replace. If a run fails as a whole, the old file stays and its `updated` shows its age."""
    path = Path(AGENT_FEED_DIR) / "personal.json"
    while True:
        try:
            feed = await personal.build()
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(feed, indent=1))
            os.replace(tmp, path)
        except Exception as e:  # noqa: BLE001
            log.warning("Personal feed not written: %s", type(e).__name__)
        await asyncio.sleep(PERSONAL_FEED_SECONDS)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(f()) for f in (agent_feed, personal_feed)] if AGENT_FEED_DIR else []
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
_cache: dict = {"at": 0.0, "data": None, "monitors": {}}   # monitors: raw Kuma names -> status, for /api/town only
_background: set[asyncio.Task] = set()


async def fetch_containers(client: httpx.AsyncClient) -> list[dict]:
    filters = json.dumps({"label": ["homelab.name"]})
    # all=1: stopped services stay on the dashboard (as down) instead of vanishing.
    r = await client.get(f"{DOCKER_URL}/containers/json", params={"all": 1, "filters": filters})
    r.raise_for_status()
    return r.json()


async def fetch_kuma_status(client: httpx.AsyncClient) -> dict[str, str]:
    """Monitor name -> status, from Uptime Kuma's Prometheus endpoint."""
    if not KUMA_API_KEY:
        return {}
    try:
        r = await client.get(f"{KUMA_URL}/metrics", auth=("", KUMA_API_KEY))
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("Uptime Kuma metrics unavailable: %s", e)
        return {}
    status = {}
    seen: dict[str, str] = {}  # monitor_id -> name
    for labels, value in METRIC.findall(r.text):
        fields = dict(METRIC_LABEL.findall(labels))
        name, mid = fields.get("monitor_name"), fields.get("monitor_id", "")
        if not name:
            continue
        # Kuma keeps a stale series after a monitor's URL changes; the current one is listed first.
        if mid in seen:
            log.warning("Kuma monitor %s (%s) has several metric series; using the first. "
                        "Restart uptime-kuma to clear it.", mid, name)
            continue
        seen[mid] = name
        status[name] = KUMA_STATUS.get(int(float(value)), "unknown")
    return status


def service_status(cid: str, kuma: dict[str, str]) -> str:
    """Worst status of monitors named <cid> or <cid>-<anything>."""
    states = [s for name, s in kuma.items() if name == cid or name.startswith(f"{cid}-")]
    return min(states, key=SEVERITY.__getitem__) if states else "unknown"


def to_service(container: dict, kuma: dict[str, str]) -> dict:
    labels = container.get("Labels") or {}
    cid = container["Names"][0].lstrip("/")
    rule = HOST_RULE.search(labels.get(f"traefik.http.routers.{cid}.rule", ""))
    port = labels.get("homelab.port", "")
    running = container.get("State") == "running"
    # Docker's own healthcheck verdict, e.g. "Up 2 hours (unhealthy)"; "(health: starting)" or none -> Kuma decides
    unhealthy = "(unhealthy)" in str(container.get("Status") or "")
    return {
        "id": cid,
        "name": labels["homelab.name"],
        "group": labels.get("homelab.group", "Other"),
        "icon": labels.get("homelab.icon", ""),
        "audience": labels.get("homelab.audience", "admin"),
        "description": labels.get("homelab.description", ""),
        "port": int(port) if port.isdigit() else None,
        "lan_host": rule.group(1) if rule else None,
        "status": "down" if not running or unhealthy else service_status(cid, kuma),
        "starting": "(health: starting)" in str(container.get("Status") or ""),
    }


def external_services(containers: list[dict], kuma: dict[str, str]) -> list[dict]:
    """Status from the Kuma monitors named <id> or <id>-*, like containers; no link (no port on this host)."""
    found: dict[str, dict] = {}
    for c in containers:
        for key, value in (c.get("Labels") or {}).items():
            m = EXTERNAL.match(key)
            if m:
                found.setdefault(m.group(1), {})[m.group(2)] = value
    return [{"id": sid, "name": f["name"], "group": f.get("group", "Other"), "icon": f.get("icon", ""),
             "audience": f.get("audience", "admin"), "description": f.get("description", ""),
             "port": None, "lan_host": None, "status": service_status(sid, kuma)}
            for sid, f in found.items() if "name" in f]


@app.get("/api/services")
async def services(request: Request):
    data = await all_services()
    if auth.is_admin(request):
        return {**data, "admin": True}
    family = [{k: s[k] for k in PUBLIC_FIELDS} for s in data["services"] if s["audience"] == "family"]
    return {"services": family, "kuma": data["kuma"], "admin": False}


async def all_services() -> dict:
    now = time.monotonic()
    if _cache["data"] and now - _cache["at"] < CACHE_SECONDS:
        return _cache["data"]
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            containers = await fetch_containers(client)
        except httpx.HTTPError as e:
            log.error("Docker API unavailable: %s", e)
            if _cache["data"]:
                return _cache["data"]
            raise HTTPException(503, "Docker API unavailable")
        kuma = await fetch_kuma_status(client)
    items = [to_service(c, kuma) for c in containers] + external_services(containers, kuma)
    items.sort(key=lambda s: (s["group"], s["name"].lower()))
    _cache.update(at=now, data={"services": items, "kuma": bool(kuma)}, monitors=kuma)
    return _cache["data"]


# Admin widgets: login required (401 otherwise)
admin_api = APIRouter(prefix="/api/widgets", dependencies=[Depends(auth.require_admin)])


@admin_api.get("/downloads")
async def widget_downloads():
    return await widgets.downloads()


@admin_api.get("/vpn")
async def widget_vpn():
    return await widgets.vpn()


@admin_api.get("/requests")
async def widget_requests():
    return await widgets.requests()


@admin_api.get("/now-playing")
async def widget_now_playing():
    return await widgets.now_playing()


@admin_api.get("/recently-added")
async def widget_recently_added():
    return await widgets.recently_added()


@admin_api.get("/health")
async def widget_health():
    return await widgets.health()


@admin_api.get("/ideas")
async def widget_ideas():
    return await asyncio.to_thread(ideas.queue)


@admin_api.get("/parked")
async def widget_parked():
    return await asyncio.to_thread(ideas.parked)


@admin_api.get("/deploys")
async def widget_deploys():
    return await asyncio.to_thread(ideas.deploys)


@admin_api.get("/proposed")
async def widget_proposed():
    return await asyncio.to_thread(ideas.proposed)


app.include_router(admin_api)


# Admin write: the origin check runs before the login check (admin_api's would run first), so a
# cross-site request is refused without looking at the session.
@app.post("/api/widgets/downloads/limit",
          dependencies=[Depends(auth.require_same_origin), Depends(auth.require_admin)])
async def downloads_limit(request: Request):
    """Body {"from": <evening limit as the tile showed it>}: flips it if it is still that."""
    body = await request.body()
    if len(body) > 256:
        raise HTTPException(413)
    try:
        expected = json.loads(body)["from"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422)
    if not isinstance(expected, bool):
        raise HTTPException(422)
    return await widgets.set_limit(expected)


@app.post("/api/ideas", dependencies=[Depends(auth.require_same_origin), Depends(auth.require_admin)])
async def add_idea(request: Request):
    """Body {"title", "details", "value"?, "effort"?, "research"?}: writes ideas/<slug>.md for the build loop (/build-ideas)."""
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413)
    try:
        data = json.loads(body)
        title, details = data["title"], data.get("details", "")
        value, effort = data.get("value"), data.get("effort")
        research = data.get("research", False)
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(422)
    if not isinstance(title, str) or not isinstance(details, str):
        raise HTTPException(422)
    if any(v is not None and (type(v) is not int) for v in (value, effort)) or type(research) is not bool:
        raise HTTPException(422)
    try:
        result = await asyncio.to_thread(ideas.add, title, details, value, effort, research)
    except ideas.IdeaError as e:
        return {"ok": False, "error": str(e)}
    except OSError as e:
        log.error("Idea not saved: %s", e)
        return {"ok": False, "error": "The server couldn't save it."}
    log.info("Idea added: %s", result["file"])
    task = asyncio.create_task(ideas.announce(result["title"], result["file"]))
    _background.add(task)  # keep a reference until it's done
    task.add_done_callback(_background.discard)
    return result


@app.post("/api/ideas/actions", dependencies=[Depends(auth.require_same_origin), Depends(auth.require_admin)])
async def idea_action(request: Request):
    """Body {"action": answer|requeue|deploy|reject, "slug", "text"?, "sensitive_ok"?}: queued for scripts/idea-actions.py."""
    body = await request.body()
    if len(body) > 32768:
        raise HTTPException(413)
    try:
        data = json.loads(body)
        action, slug = data["action"], data["slug"]
        text, sensitive_ok = data.get("text", ""), data.get("sensitive_ok", False)
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422)
    if not all(isinstance(v, str) for v in (action, slug, text)) or not isinstance(sensitive_ok, bool):
        raise HTTPException(422)
    try:
        result = await asyncio.to_thread(ideas.request, action, slug, text, sensitive_ok)
    except ideas.IdeaError as e:
        return {"ok": False, "error": str(e)}
    except OSError as e:
        log.error("Idea action not saved: %s", e)
        return {"ok": False, "error": "The server couldn't save it."}
    log.info("Idea action queued: %s", result["id"])
    return result


@app.post("/api/ideas/proposed", dependencies=[Depends(auth.require_same_origin), Depends(auth.require_admin)])
async def proposed_action(request: Request):
    """Body {"action": approve|dismiss|later, "slug", "reason"?}: done here, no runner (files move inside /ideas)."""
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(413)
    try:
        data = json.loads(body)
        action, slug, reason = data["action"], data["slug"], data.get("reason", "")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(422)
    if not all(isinstance(v, str) for v in (action, slug, reason)):
        raise HTTPException(422)
    try:
        result = await asyncio.to_thread(ideas.decide, action, slug, reason)
    except ideas.IdeaError as e:
        return {"ok": False, "error": str(e)}
    except OSError as e:
        log.error("Proposal %s not done: %s", action, e)
        return {"ok": False, "error": "The server couldn't move the note."}
    log.info("Proposal %s: %s", action, slug)
    if action == "approve":
        task = asyncio.create_task(ideas.announce(result["title"], f"{slug}.md"))
        _background.add(task)
        task.add_done_callback(_background.discard)
    return result


@app.get("/api/family/recently-added")
async def family_recently_added():
    return await widgets.family_recent()


@app.get("/api/family/requests")
async def family_requests():
    return await widgets.family_requests()


@app.get("/api/img/jellyfin/{item_id}")
async def jellyfin_image(item_id: str):
    try:
        img = await widgets.jellyfin_poster(item_id)
    except Exception:  # Jellyfin down/misconfigured -> broken poster falls back to a letter
        img = None
    if not img:
        raise HTTPException(404)
    return Response(img[0], media_type=img[1], headers={"Cache-Control": "public, max-age=86400"})


@app.get("/auth/verify")
async def auth_verify(request: Request):
    """Traefik forward auth (middleware admin-auth): 200 with a valid admin cookie, else a redirect to the login.
    No next= parameter, so there is no open redirect."""
    if auth.is_admin(request):
        return Response(status_code=200)
    url = auth.verify_redirect(request)
    if url:
        return RedirectResponse(url, 302)
    return PlainTextResponse("login required", 401)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.get("/")
async def index():
    return FileResponse(INDEX, headers={"Cache-Control": "no-cache"})


@app.get("/admin")
async def admin(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/login", 303)
    response = FileResponse(INDEX, headers={"Cache-Control": "no-cache"})
    auth.set_session(response, auth.new_session())  # sliding: 30 days from the last visit
    return response


@app.get("/town")
async def town_page(request: Request):
    if not auth.is_admin(request):
        return RedirectResponse("/login", 303)
    response = FileResponse(TOWN, headers={"Cache-Control": "no-cache"})
    auth.set_session(response, auth.new_session())
    return response


async def _town_fetch():
    data = await all_services()
    return data, dict(_cache["monitors"])


@app.get("/api/town", dependencies=[Depends(auth.require_admin)])
async def api_town():
    return await town.snapshot(_town_fetch)


def login_page(status: int = 200, message: str = "", username: str = "") -> HTMLResponse:
    if not auth.CONFIGURED:
        status, message = 503, "Login isn't set up on the server yet."
    msg = f'<p class="error" role="alert">{html.escape(message)}</p>' if message else ""
    page = LOGIN.read_text().replace("<!--MSG-->", msg).replace("__USERNAME__", html.escape(username, quote=True))
    return HTMLResponse(page, status, headers={"Cache-Control": "no-store"})


@app.get("/login")
async def login_form(request: Request):
    if auth.is_admin(request):
        return RedirectResponse("/admin", 303)
    return login_page()


@app.post("/login")
async def login(request: Request):
    if not auth.same_origin(request):
        raise HTTPException(403)
    ip = await auth.client_ip(request)
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(413)
    form = parse_qs(body.decode(errors="replace"))
    username = form.get("username", [""])[0].strip()
    password = form.get("password", [""])[0]
    # No awaits from here to the verdict, so parallel guesses can't slip past the counters.
    wait = auth.limiter.wait(ip)
    if wait:
        return login_page(429, f"Too many failed attempts. Try again in {(wait + 59) // 60} min.", username)
    if auth.check_credentials(username, password):
        auth.limiter.succeeded(ip)
        log.info("Admin login from %s", ip)
        response = RedirectResponse("/admin", 303)
        auth.set_session(response, auth.new_session())
        return response
    auth.limiter.failed(ip)
    log.warning("Admin login failed from %s", ip)
    await asyncio.sleep(auth.FAIL_DELAY)
    return login_page(401, "Wrong username or password.", username)


@app.post("/logout")
async def logout(request: Request):
    if not auth.same_origin(request, allow_null=True):  # a forced logout is harmless
        raise HTTPException(403)
    response = RedirectResponse("/", 303)
    auth.clear_session(response)
    return response
