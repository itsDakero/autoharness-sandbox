#!/usr/bin/env python3
"""qBittorrent settings for the homelab, idempotent. Credentials come from .env and are never printed.

  scripts/qbit-setup.py seed    # before first start (or with qbittorrent stopped): Web UI login, PBKDF2-hashed
  scripts/qbit-setup.py apply   # running: paths, categories, speed schedule, queueing, share limits (ratio/time) (Web API)
"""
import base64
import hashlib
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
URL = "http://localhost:8083"
DL = "/mnt/media/downloads"
CATEGORIES = ["movies", "tv", "movies-remote", "tv-remote"]
PREFS = {
    "save_path": DL,
    "temp_path_enabled": True,
    "temp_path": f"{DL}/temp",
    "auto_tmm_enabled": True,             # category decides the save path
    "category_changed_tmm_enabled": True,
    # Alternative limits 5 KiB/s, scheduled daily 19:00-23:59
    "alt_dl_limit": 5 * 1024,
    "alt_up_limit": 5 * 1024,
    "scheduler_enabled": True,
    "schedule_from_hour": 19, "schedule_from_min": 0,
    "schedule_to_hour": 23, "schedule_to_min": 59,
    "scheduler_days": 0,                  # every day
    # Queueing
    "queueing_enabled": True,
    "max_active_torrents": 10,
    "max_active_uploads": 5,
    # Stop at ratio 1.0, or after 14 days seeding, or after 3 days with no upload, whichever comes first
    # (times are in minutes). NordVPN has no port forwarding, so slow torrents never reach 1.0; Radarr/Sonarr's
    # HasReachedSeedLimit counts the global time limits too. max_ratio_act 0 (stop) covers all three limits.
    # The arr apps ("Remove Completed") then delete torrent + files once imported;
    # qBittorrent removing them itself races the import, so Radarr/Sonarr refuse that setup.
    "max_ratio_enabled": True,
    "max_ratio": 1.0,
    "max_ratio_act": 0,
    "max_seeding_time_enabled": True,
    "max_seeding_time": 14 * 24 * 60,
    "max_inactive_seeding_time_enabled": True,
    "max_inactive_seeding_time": 3 * 24 * 60,
    # Only ever use the VPN tunnel (on top of Gluetun's firewall)
    "current_network_interface": "tun0",
    "upnp": False,
    "web_ui_upnp": False,
    # Host header validation on; the allowed names are set in apply() (IPs from .env)
    "web_ui_host_header_validation_enabled": True,
}


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


def creds() -> tuple[str, str]:
    e = env()
    user, pw = e.get("QBITTORRENT_USERNAME", ""), e.get("QBITTORRENT_PASSWORD", "")
    if not user or not pw:
        sys.exit("QBITTORRENT_USERNAME / QBITTORRENT_PASSWORD missing in .env")
    return user, pw


def seed() -> None:
    running = subprocess.run(["docker", "ps", "-q", "-f", "name=^qbittorrent$"],
                             capture_output=True, text=True).stdout.strip()
    if running:
        sys.exit("qbittorrent is running; it rewrites its config on exit. Stop it first.")
    user, pw = creds()
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha512", pw.encode(), salt, 100_000, 64)
    pbkdf2 = f"@ByteArray({base64.b64encode(salt).decode()}:{base64.b64encode(key).decode()})"
    conf = Path(env().get("APPDATA_PATH", "/srv/homelab")) / "qbittorrent/qBittorrent/qBittorrent.conf"
    conf.parent.mkdir(parents=True, exist_ok=True)
    lines = conf.read_text().splitlines() if conf.exists() else []
    if "[Preferences]" not in lines:
        lines += ["", "[Preferences]"]
    lines = [l for l in lines if not l.startswith(("WebUI\\Username=", "WebUI\\Password_PBKDF2="))]
    i = lines.index("[Preferences]") + 1
    lines[i:i] = [f"WebUI\\Username={user}", f'WebUI\\Password_PBKDF2="{pbkdf2}"']
    if "[LegalNotice]" not in lines:
        lines += ["", "[LegalNotice]", "Accepted=true"]
    conf.write_text("\n".join(lines).lstrip("\n") + "\n")
    print(f"Web UI login written to {conf} (password hashed)")


def apply() -> None:
    user, pw = creds()
    e = env()
    # Names the Web UI is reached by: dashboard tile, .lan via Traefik, arr apps (gluetun), this script (localhost)
    PREFS["web_ui_domain_list"] = ";".join(
        ["homelab", "*.lan", "qbittorrent.lan", "gluetun", e["LAN_IP"], e["TAILSCALE_IP"], "localhost"])
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    opener.addheaders = [("Referer", URL)]

    def post(path: str, data: dict) -> tuple[int, str]:
        body = urllib.parse.urlencode(data).encode()
        try:
            with opener.open(f"{URL}/api/v2/{path}", body, timeout=15) as r:
                return r.status, r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    def get(path: str):
        with opener.open(f"{URL}/api/v2/{path}", timeout=15) as r:
            return json.load(r)

    status, _ = post("auth/login", {"username": user, "password": pw})
    if status not in (200, 204) or not any(c.name == "SID" or c.name.startswith("QBT_SID_") for c in jar):  # 5.x: 204 + QBT_SID_<port>
        sys.exit(f"login failed (HTTP {status})")

    status, text = post("app/setPreferences", {"json": json.dumps(PREFS)})
    if not 200 <= status < 300:
        sys.exit(f"setPreferences failed (HTTP {status}): {text}")

    existing = get("torrents/categories")
    for cat in CATEGORIES:
        data = {"category": cat, "savePath": f"{DL}/{cat}"}
        status, text = post("torrents/editCategory" if cat in existing else "torrents/createCategory", data)
        if not 200 <= status < 300:
            sys.exit(f"category {cat} failed (HTTP {status}): {text}")

    prefs = get("app/preferences")
    bad = {k: (v, prefs.get(k)) for k, v in PREFS.items() if prefs.get(k) != v}
    for k, (want, got) in bad.items():
        print(f"MISMATCH {k}: want {want!r}, got {got!r}")
    cats = get("torrents/categories")
    for cat in CATEGORIES:
        print(f"category {cat}: {cats.get(cat, {}).get('savePath')}")
    print(f"qBittorrent {opener.open(f'{URL}/api/v2/app/version').read().decode()}: "
          f"{len(PREFS) - len(bad)}/{len(PREFS)} preferences OK")
    if bad:
        sys.exit(1)


if __name__ == "__main__":
    {"seed": seed, "apply": apply}.get(sys.argv[1] if len(sys.argv) > 1 else "", lambda: sys.exit(__doc__))()
