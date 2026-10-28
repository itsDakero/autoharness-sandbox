"""Live widgets: the backend fetches and caches; the browser only gets display fields, never credentials.

Every widget returns {"ok": true, ...} or {"ok": false} (logged here, shown as "unavailable").
"""
import asyncio
import logging
import os
import re
import time
from datetime import date, datetime
from functools import wraps
from pathlib import Path

import httpx

QBIT_URL = os.environ.get("QBITTORRENT_URL", "http://gluetun:8083")
QBIT_USERNAME = os.environ.get("QBITTORRENT_USERNAME", "")
QBIT_PASSWORD = os.environ.get("QBITTORRENT_PASSWORD", "")
GLUETUN_URL = os.environ.get("GLUETUN_URL", "http://gluetun:8000")
GLUETUN_API_KEY = os.environ.get("GLUETUN_API_KEY", "")  # once Gluetun's control server has auth
JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://jellyfin:8096")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")
SEERR_URL = os.environ.get("SEERR_URL", "http://seerr:5055")
SEERR_API_KEY = os.environ.get("SEERR_API_KEY", "")
TMDB_POSTER = "https://image.tmdb.org/t/p/w185"  # public, no key
# Remote pair's 720p libraries (same paths as in the arr apps / Jellyfin)
REMOTE_PATHS = ("/mnt/media/movies-720p/", "/mnt/media/tv-720p/")

LIVE_TTL = 3     # browser polls every 5 s
SLOW_TTL = 25    # browser polls every 30 s
QBIT_NO_ETA = 8640000
# qBittorrent states that mean "not finished, not seeding"
QBIT_ACTIVE = {"downloading", "metaDL", "forcedMetaDL", "forcedDL", "stalledDL", "queuedDL",
               "checkingDL", "allocating", "moving", "stoppedDL", "checkingResumeData", "error", "missingFiles"}

log = logging.getLogger("uvicorn.error")
client = httpx.AsyncClient(timeout=4)


def cached(ttl: int):
    """Cache a widget's result (success or failure) for ttl seconds; one fetch at a time."""
    def deco(fn):
        state = {"at": -1e9, "data": None}
        lock = asyncio.Lock()

        @wraps(fn)
        async def wrapper():
            async with lock:
                if time.monotonic() - state["at"] < ttl:
                    return state["data"]
                try:
                    data = {"ok": True, **await fn()}
                except Exception as e:  # any failure -> "unavailable", never a broken page
                    log.warning("widget %s unavailable: %s: %s", fn.__name__, type(e).__name__, e)
                    data = {"ok": False}
                state.update(at=time.monotonic(), data=data)
                return data
        wrapper.clear = lambda: state.update(at=-1e9)  # next call fetches fresh
        return wrapper
    return deco


class QBit:
    """qBittorrent Web API session; logs in again when the session expires.

    Never sends Origin/Referer (and never passes the browser's headers on): qBittorrent's CSRF check
    accepts a request with neither."""
    def __init__(self, url: str = QBIT_URL):
        self.client = httpx.AsyncClient(base_url=f"{url}/api/v2/", timeout=4)  # own cookie jar

    async def login(self) -> None:
        if not QBIT_USERNAME or not QBIT_PASSWORD:
            raise RuntimeError("QBITTORRENT_USERNAME / QBITTORRENT_PASSWORD not set")
        r = await self.client.post("auth/login", data={"username": QBIT_USERNAME, "password": QBIT_PASSWORD})
        # 5.x: 204 + QBT_SID_<port>; 4.x: 200 "Ok." + SID
        if r.status_code not in (200, 204) or not r.cookies:
            raise RuntimeError(f"qBittorrent login failed (HTTP {r.status_code})")

    async def _send(self, method: str, path: str) -> httpx.Response:
        for attempt in (1, 2):
            r = await self.client.request(method, path)
            # 403 = session expired, nothing was done: safe to retry once, even a POST. Timeouts aren't retried.
            if r.status_code == 403 and attempt == 1:
                await self.login()
                continue
            r.raise_for_status()
            return r

    async def get(self, path: str):
        return (await self._send("GET", path)).json()

    async def post(self, path: str) -> None:
        await self._send("POST", path)


qbit = QBit()


@cached(LIVE_TTL)
async def downloads():
    torrents, transfer, alt = await asyncio.gather(
        qbit.get("torrents/info"), qbit.get("transfer/info"), qbit.get("transfer/speedLimitsMode"))
    active = [t for t in torrents if t["state"] in QBIT_ACTIVE and t["progress"] < 1]
    active.sort(key=lambda t: (t["state"] != "downloading", -t["dlspeed"], t["added_on"]))
    return {
        "items": [{
            "name": t["name"],
            "progress": round(t["progress"], 4),
            "speed": t["dlspeed"],
            "eta": None if t["eta"] >= QBIT_NO_ETA else t["eta"],
            "state": t["state"],
        } for t in active[:8]],
        "more": max(0, len(active) - 8),
        "seeding": sum(t["progress"] >= 1 for t in torrents),
        "down": transfer["dl_info_speed"],
        "up": transfer["up_info_speed"],
        "evening_limit": alt == 1,
        "limit": transfer["dl_rate_limit"] if alt == 1 else None,
    }


_limit_lock = asyncio.Lock()


async def set_limit(expected: bool) -> dict:
    """Flip the evening limit (qBittorrent's alternative speed mode), only if it is still `expected` (the state
    the tile showed), so a double tap or a stale tile can't flip it back. Only these two endpoints; the
    schedule and the limits themselves are never touched."""
    async with _limit_lock:
        try:
            on = await qbit.get("transfer/speedLimitsMode") == 1
            if on == expected:
                await qbit.post("transfer/toggleSpeedLimitsMode")
                on = await qbit.get("transfer/speedLimitsMode") == 1
                log.info("speed limit %s: evening limit %s (manual)",
                         datetime.now().isoformat(timespec="seconds"), "on" if on else "off")
            downloads.clear()
            return {"ok": True, "evening_limit": on}
        except Exception as e:  # down/unreachable -> the tile shows "unknown"
            log.warning("speed limit toggle failed: %s", type(e).__name__)
            return {"ok": False}


@cached(SLOW_TTL)
async def vpn():
    headers = {"X-API-Key": GLUETUN_API_KEY} if GLUETUN_API_KEY else {}
    status, ip = await asyncio.gather(
        client.get(f"{GLUETUN_URL}/v1/vpn/status", headers=headers),
        client.get(f"{GLUETUN_URL}/v1/publicip/ip", headers=headers))
    status.raise_for_status()
    ip.raise_for_status()
    running = status.json().get("status") == "running"
    info = ip.json()
    # Gluetun looks up its public IP through the tunnel, so an answer while running = traffic exits via the VPN
    return {
        "protected": running and bool(info.get("public_ip")),
        "country": info.get("country") or None,
        "city": info.get("city") or None,
    }


# ---- Jellyfin -------------------------------------------------------------------------------------

def jf_headers() -> dict:
    if not JELLYFIN_API_KEY:
        raise RuntimeError("JELLYFIN_API_KEY not set")
    return {"Authorization": f'MediaBrowser Token="{JELLYFIN_API_KEY}"'}


async def jf_get(path: str, **params):
    r = await client.get(f"{JELLYFIN_URL}{path}", params=params, headers=jf_headers())
    r.raise_for_status()
    return r.json()


_jf_admin: dict = {}


async def jf_admin_id() -> str:
    """An administrator's user id (sees every library); /Items needs a user."""
    if "id" not in _jf_admin:
        users = await jf_get("/Users")
        _jf_admin["id"] = next(u["Id"] for u in users if u["Policy"]["IsAdministrator"])
    return _jf_admin["id"]


def ticks_to_s(t) -> int | None:
    return int(t / 10_000_000) if t else None


@cached(LIVE_TTL)
async def now_playing():
    sessions = await jf_get("/Sessions", activeWithinSeconds=960)
    items = []
    for s in sessions:
        np = s.get("NowPlayingItem")
        if not np:
            continue
        ps = s.get("PlayState") or {}
        ti = s.get("TranscodingInfo") or {}
        method = ps.get("PlayMethod") or "DirectPlay"
        if method == "Transcode":
            hw = ti.get("HardwareAccelerationType")
            mode = "Transcoding (HW)" if hw and hw.lower() != "none" else "Transcoding"
            if ti.get("IsVideoDirect"):
                mode = "Transcoding audio"
        else:
            mode = "Direct stream" if method == "DirectStream" else "Direct play"
        episode = np.get("Type") == "Episode"
        items.append({
            "user": s.get("UserName") or "?",
            "device": s.get("DeviceName") or s.get("Client") or "",
            "title": np.get("SeriesName") if episode else np.get("Name"),
            "subtitle": (f"S{np.get('ParentIndexNumber') or 0:02}E{np.get('IndexNumber') or 0:02} · {np.get('Name')}"
                         if episode else (str(np["ProductionYear"]) if np.get("ProductionYear") else "")),
            "image": np.get("SeriesId") if episode and np.get("SeriesId") else np.get("Id"),
            "position": ticks_to_s(ps.get("PositionTicks")),
            "runtime": ticks_to_s(np.get("RunTimeTicks")),
            "paused": bool(ps.get("IsPaused")),
            "mode": mode,
        })
    return {"items": items}


@cached(SLOW_TTL)
async def recently_added():
    """Newest movies and episodes, episodes grouped into their series (Latest's own dates are unreliable)."""
    return {"items": (await _recent_groups())[:16]}


async def _recent_groups() -> list[dict]:
    uid = await jf_admin_id()
    data = await jf_get("/Items", userId=uid, Recursive="true", IncludeItemTypes="Movie,Episode",
                        SortBy="DateCreated", SortOrder="Descending", Limit=300, Fields="DateCreated,Path")
    out: dict[str, dict] = {}
    for i in data.get("Items", []):
        episode = i["Type"] == "Episode"
        key = i.get("SeriesId") if episode else i["Id"]
        day = date.fromisoformat((i.get("DateCreated") or "1970-01-01")[:10])
        if not key:
            continue
        if key in out:
            # count the series' episodes added within a week of its newest one
            if episode and (out[key]["_day"] - day).days <= 7:
                out[key]["episodes"] += 1
            continue
        if len(out) >= 40:
            continue
        out[key] = {
            "id": key,
            "title": i.get("SeriesName") if episode else i["Name"],
            "year": None if episode else i.get("ProductionYear"),
            "type": "series" if episode else "movie",
            "episodes": 1 if episode else 0,
            "added": i.get("DateCreated"),
            "remote": (i.get("Path") or "").startswith(REMOTE_PATHS),
            "_day": day,
        }
    return [{k: v for k, v in i.items() if k != "_day"} for i in out.values()]


JF_ID = re.compile(r"^[0-9a-f]{32}$")


async def jellyfin_poster(item_id: str) -> tuple[bytes, str] | None:
    """Primary image, resized; the browser never talks to Jellyfin or sees the key."""
    if not JF_ID.match(item_id):
        return None
    r = await client.get(f"{JELLYFIN_URL}/Items/{item_id}/Images/Primary",
                         params={"fillHeight": 360, "quality": 85}, headers=jf_headers())
    if r.status_code != 200:
        return None
    return r.content, r.headers.get("content-type", "image/jpeg")


# ---- Seerr ----------------------------------------------------------------------------------------

async def seerr_get(path: str, **params):
    if not SEERR_API_KEY:
        raise RuntimeError("SEERR_API_KEY not set")
    r = await client.get(f"{SEERR_URL}/api/v1{path}", params=params, headers={"X-Api-Key": SEERR_API_KEY})
    r.raise_for_status()
    return r.json()


_titles: dict[tuple[str, int], tuple[float, dict]] = {}
TITLE_TTL = 86400


async def seerr_title(media_type: str, tmdb_id: int) -> dict:
    """Title, year and poster for a TMDB id (via Seerr), cached for a day."""
    key = (media_type, tmdb_id)
    hit = _titles.get(key)
    if hit and time.monotonic() - hit[0] < TITLE_TTL:
        return hit[1]
    d = await seerr_get(f"/{'tv' if media_type == 'tv' else 'movie'}/{tmdb_id}")
    date = d.get("releaseDate") or d.get("firstAirDate") or ""
    info = {
        "title": d.get("title") or d.get("name") or "Unknown",
        "year": int(date[:4]) if date[:4].isdigit() else None,
        "poster": f"{TMDB_POSTER}{d['posterPath']}" if d.get("posterPath") else None,
    }
    if len(_titles) > 500:
        _titles.clear()
    _titles[key] = (time.monotonic(), info)
    return info


def download_progress(media: dict) -> float | None:
    """0..1 across the request's active downloads, from Radarr/Sonarr's queue as Seerr sees it."""
    dl = [d for d in media.get("downloadStatus") or [] if d.get("size")]
    if not dl:
        return None
    size = sum(d["size"] for d in dl)
    return round(1 - sum(d.get("sizeLeft", 0) for d in dl) / size, 4)


async def seerr_requests(filter_: str, take: int) -> tuple[int, list[dict]]:
    d = await seerr_get("/request", take=take, skip=0, filter=filter_, sort="modified")
    results = d.get("results", [])
    titles = await asyncio.gather(*(seerr_title(r["media"]["mediaType"], r["media"]["tmdbId"]) for r in results))
    items = []
    for r, t in zip(results, titles):
        m = r["media"]
        items.append({
            **t,
            "type": m["mediaType"],
            "user": (r.get("requestedBy") or {}).get("displayName") or "?",
            "updated": r.get("updatedAt"),
            "progress": download_progress(m),
            "downloading": bool(m.get("downloadStatus")),
        })
    return d.get("pageInfo", {}).get("results", len(items)), items


@cached(SLOW_TTL)
async def requests():
    (np, pending), (nproc, processing), (_, available) = await asyncio.gather(
        seerr_requests("pending", 10), seerr_requests("processing", 10), seerr_requests("available", 6))
    return {"pending": pending, "pending_total": np, "processing": processing, "processing_total": nproc,
            "available": available}


# ---- Server health (host-wide /proc and /sys, read-only mounts for disks, nvidia-smi) --------------

# label=path pairs; each path is a read-only bind mount on the disk to report
DISKS = [tuple(x.split("=", 1)) for x in os.environ.get("HEALTH_DISKS", "").split(",") if "=" in x]
GPU_FIELDS = ["name", "utilization.gpu", "utilization.encoder", "utilization.decoder", "memory.used",
              "memory.total", "temperature.gpu", "power.draw", "encoder.stats.sessionCount"]
_cpu_prev: dict = {}


def cpu_sample() -> tuple[int, int]:
    """(busy, total) jiffies from the host-wide /proc/stat (not namespaced)."""
    with open("/proc/stat") as f:
        v = [int(x) for x in f.readline().split()[1:]]
    idle = v[3] + v[4]  # idle + iowait
    return sum(v) - idle, sum(v)


async def cpu_percent() -> float:
    prev = _cpu_prev.get("s")
    if not prev or time.monotonic() - _cpu_prev["at"] > 60:  # first call: take a short window
        prev = cpu_sample()
        await asyncio.sleep(0.5)
    cur = cpu_sample()
    _cpu_prev.update(s=cur, at=time.monotonic())
    busy, total = cur[0] - prev[0], cur[1] - prev[1]
    return round(100 * busy / total, 1) if total > 0 else 0.0


def cpu_temp() -> float | None:
    """CPU package temperature from coretemp/k10temp in /sys (read-only in the container)."""
    for hw in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            name = (hw / "name").read_text().strip()
            if name not in ("coretemp", "k10temp", "zenpower"):
                continue
            for label in sorted(hw.glob("temp*_label")):
                if label.read_text().strip() in ("Package id 0", "Tctl", "Tdie"):
                    return int(Path(str(label).replace("_label", "_input")).read_text()) / 1000
            return int((hw / "temp1_input").read_text()) / 1000
        except (OSError, ValueError):
            continue
    return None


def memory() -> dict:
    info = {}
    with open("/proc/meminfo") as f:
        for line in f:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0]) * 1024
    total, avail = info["MemTotal"], info["MemAvailable"]
    return {"used": total - avail, "total": total}


def disks() -> list[dict]:
    out = []
    for label, path in DISKS:
        try:
            st = os.statvfs(path)
        except OSError:
            out.append({"label": label, "used": None, "total": None})
            continue
        total = st.f_blocks * st.f_frsize
        out.append({"label": label, "used": total - st.f_bfree * st.f_frsize, "total": total})
    return out


def num(x: str):
    try:
        return float(x)
    except ValueError:  # "[N/A]", "[Not Supported]"
        return None


async def gpu() -> dict | None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "nvidia-smi", f"--query-gpu={','.join(GPU_FIELDS)}", "--format=csv,noheader,nounits",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=4)
    except (OSError, asyncio.TimeoutError) as e:
        log.warning("nvidia-smi unavailable: %s", type(e).__name__)
        return None
    if proc.returncode != 0 or not out.strip():
        return None
    v = dict(zip(GPU_FIELDS, (x.strip() for x in out.decode().splitlines()[0].split(","))))
    return {
        "name": v["name"],
        "util": num(v["utilization.gpu"]),
        "encoder": num(v["utilization.encoder"]),
        "decoder": num(v["utilization.decoder"]),
        "mem_used": num(v["memory.used"]),
        "mem_total": num(v["memory.total"]),
        "temp": num(v["temperature.gpu"]),
        "power": num(v["power.draw"]),
        "sessions": int(num(v["encoder.stats.sessionCount"]) or 0),
    }


@cached(LIVE_TTL)
async def health():
    cpu, g = await asyncio.gather(cpu_percent(), gpu())
    with open("/proc/loadavg") as f:
        load = [float(x) for x in f.read().split()[:3]]
    with open("/proc/uptime") as f:
        uptime = int(float(f.read().split()[0]))
    return {
        "cpu": cpu, "cores": os.cpu_count(), "load": load, "cpu_temp": cpu_temp(),
        "memory": memory(), "disks": disks(), "gpu": g, "uptime": uptime,
    }


# ---- Family view (no login): household-level fields only, no usernames or technical detail ---------

@cached(SLOW_TTL)
async def family_recent():
    """Main libraries only: the remote 720p copies aren't in the household's Jellyfin libraries."""
    items = [i for i in await _recent_groups() if not i["remote"]][:8]
    return {"items": [{"id": i["id"], "title": i["title"], "series": i["type"] == "series",
                       "added": i["added"]} for i in items]}


@cached(SLOW_TTL)
async def family_requests():
    (_, pending), (_, processing), (_, available) = await asyncio.gather(
        seerr_requests("pending", 10), seerr_requests("processing", 10), seerr_requests("available", 6))
    out: dict[tuple, dict] = {}
    for state, items in (("ready", available), ("coming", processing), ("waiting", pending)):
        for r in items:  # a title asked for twice shows once, in its most advanced state
            out.setdefault((r["title"], r["year"]),
                           {"title": r["title"], "year": r["year"], "poster": r["poster"], "state": state})
    return {"items": list(out.values())}
