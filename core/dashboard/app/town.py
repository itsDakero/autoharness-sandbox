"""Homelab Town: the JSON behind /town (read-only). Every part has its own `ok`, so one failure never fails the
whole response. Nothing here writes, and nothing secret goes out (service ids, statuses, note titles)."""
import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException

from . import ideas

OPS_ACTIONS_DIR = Path(os.environ.get("OPS_ACTIONS_DIR", "/ops-actions"))
AUDIT_TAIL = 64 * 1024
AUDIT_KEEP = 20
FIELD_MAX = 200
log = logging.getLogger("uvicorn.error")

# Lower = worse; a building shows its worst member.
SEVERITY = {"down": 0, "starting": 1, "unknown": 2, "maintenance": 3, "up": 4}
KUMA_TO_TOWN = {"down": "down", "pending": "starting", "maintenance": "maintenance", "up": "up"}

# building id -> (Docker/external service ids, Kuma monitor names). Kuma names match exactly or as <name>-*.
BUILDINGS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "watchtower": (("uptime-kuma",), ()),
    "hall": (("dashboard",), ()),
    "library": (("books",), ()),
    "gym": (("fitness",), ()),
    "tailor": (("wardrobe",), ()),
    "arcade": (("leafgreen",), ()),
    "post": (("ntfy",), ()),
    "cinema": (("jellyfin",), ()),
    "warehouse": (("radarr", "sonarr", "prowlarr", "seerr", "radarr-remote", "sonarr-remote"), ()),
    "tunnel": (("qbittorrent", "gluetun"), ("qbittorrent-vpn",)),
    "market": (("changedetection",), ()),
    "clinic": ((), ("cron-ops-actions",)),
    "guild": ((), ("cron-idea-actions",)),
    "vault": ((), ("ha-backups",)),
    "observatory": (("mac-mini",), ()),
    "wall": (("adguard",), ()),
}


def town_status(service: dict) -> str:
    if service.get("status") == "down":
        return "down"
    if service.get("starting") or service.get("status") == "pending":
        return "starting"
    s = service.get("status")
    return s if s in SEVERITY else "unknown"


def _kuma_matches(monitors: dict[str, str], name: str) -> list[str]:
    return [s for n, s in monitors.items() if n == name or n.startswith(f"{name}-")]


def _worst(states: list[str]) -> str:
    return min(states, key=SEVERITY.__getitem__) if states else "unknown"


def buildings(services: list[dict], monitors: dict[str, str]) -> dict[str, str]:
    by_id = {s["id"]: town_status(s) for s in services}
    out = {}
    for bid, (ids, kuma) in BUILDINGS.items():
        states = [by_id[i] for i in ids if i in by_id]
        states += [KUMA_TO_TOWN.get(s, "unknown") for k in kuma for s in _kuma_matches(monitors, k)]
        out[bid] = _worst(states)
    cron = [KUMA_TO_TOWN.get(s, "unknown") for n, s in monitors.items() if n.startswith("cron-")]
    out["clock"] = _worst(cron)
    return out


def cron(monitors: dict[str, str]) -> list[dict]:
    return [{"name": n[len("cron-"):], "status": KUMA_TO_TOWN.get(s, "unknown")}
            for n, s in sorted(monitors.items()) if n.startswith("cron-")]


def read_audit(path: Path | None = None) -> list[dict]:
    """The last AUDIT_KEEP parsed lines of audit.jsonl, from only the last 64 KB. A missing file gives [];
    bad lines and the partial first/last line are skipped."""
    path = path or OPS_ACTIONS_DIR / "audit.jsonl"
    try:
        with path.open("rb") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(max(0, size - AUDIT_TAIL))
            data = f.read(AUDIT_TAIL)
            cut = size > AUDIT_TAIL
    except OSError:
        return []
    lines = data.split(b"\n")
    if cut:
        lines = lines[1:]  # the first line may start mid-way
    if lines and lines[-1] != b"":
        lines = lines[:-1]  # a last line without its newline may still be being written
    out = []
    for raw in lines:
        try:
            rec = json.loads(raw.decode("utf-8"))
        except ValueError:
            continue
        if not isinstance(rec, dict) or not isinstance(rec.get("time"), str):
            continue
        out.append({k: str(rec.get(k, ""))[:FIELD_MAX] for k in ("time", "service", "action", "result")})
    return out[-AUDIT_KEEP:]


def read_ops() -> dict:
    return {"ok": True, "paused": (OPS_ACTIONS_DIR / "PAUSE").exists(), "recent": read_audit()}


def read_scout() -> dict:
    d = ideas.IDEAS_DIR / "proposed"
    count = sum(1 for p in d.glob("*.md") if ideas.SLUG.match(p.stem))
    try:
        last = datetime.fromtimestamp((d / ".last-scout").stat().st_mtime).astimezone().isoformat(timespec="seconds")
    except OSError:
        last = None
    return {"ok": True, "proposed": count, "last_run": last}


def read_loop() -> dict:
    q = ideas.queue()
    d = ideas.deploys()
    return {"ok": True,
            "queued": [i["title"] for i in q.get("ideas", [])] if q.get("ok") else [],
            "building": [str(s) for s in d.get("building", [])],
            "ready": [{"slug": b.get("slug"), "title": b.get("title")} for b in d.get("ready", [])],
            "parked": len(q.get("parked", [])),
            "runner": d.get("runner", "missing")}


async def _part(fn, *args):
    try:
        return await asyncio.to_thread(fn, *args)
    except Exception as e:  # noqa: BLE001  one failing part must not fail the page
        log.warning("Town part %s failed: %s", fn.__name__, type(e).__name__)
        return {"ok": False}


async def _services(fetch) -> tuple[dict, dict, dict]:
    try:
        data, monitors = await fetch()
    except HTTPException:
        return {"ok": False}, {"ok": False}, {"ok": False}
    except Exception as e:  # noqa: BLE001
        log.warning("Town services failed: %s", type(e).__name__)
        return {"ok": False}, {"ok": False}, {"ok": False}
    svc = {"ok": True, "kuma": bool(data.get("kuma")),
           "items": [{"id": s["id"], "name": s["name"], "status": town_status(s)} for s in data["services"]]}
    return svc, {"ok": True, "map": buildings(data["services"], monitors)}, \
        {"ok": True, "items": cron(monitors)}


async def snapshot(fetch) -> dict:
    """`fetch` is an async function returning (all_services() data, raw Kuma monitor dict)."""
    (svc, bld, crn), loop, scout, ops = await asyncio.gather(
        _services(fetch), _part(read_loop), _part(read_scout), _part(read_ops))
    hermes = next((s["status"] for s in svc.get("items", []) if s["id"] == "hermes"), "unknown")
    return {"services": svc, "buildings": bld, "cron": crn, "loop": loop, "scout": scout, "ops": ops,
            "hermes": {"ok": svc["ok"], "status": hermes},
            "now": datetime.now().astimezone().isoformat(timespec="seconds")}
