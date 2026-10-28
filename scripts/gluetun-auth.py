#!/usr/bin/env python3
"""Gluetun control-server auth: one read-only API-key role for the dashboard. Idempotent; the key comes
from .env (GLUETUN_API_KEY) and is never printed.

  scripts/gluetun-auth.py   # writes ${APPDATA_PATH}/gluetun/auth/config.toml; Gluetun reads it at start

Every route not listed in a role is denied, including the unauthenticated defaults Gluetun v3.41 still
allows (with a deprecation warning). Restart Gluetun via compose afterwards (recreates qbittorrent too):
  scripts/dc.sh media/qbittorrent up -d --force-recreate
"""
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROUTES = ["GET /v1/vpn/status", "GET /v1/publicip/ip"]  # what the dashboard's VPN widget reads


def env() -> dict[str, str]:
    out = {}
    for line in (REPO / ".env").read_text().splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)", line)
        if m:
            out[m[1]] = m[2].strip().strip("'\"")
    return out


def main() -> None:
    e = env()
    key = e.get("GLUETUN_API_KEY", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", key):
        sys.exit("GLUETUN_API_KEY missing in .env or shorter than 32 chars "
                 "(echo \"GLUETUN_API_KEY=$(openssl rand -hex 32)\" >> .env)")
    conf = Path(e.get("APPDATA_PATH", "/srv/homelab")) / "gluetun/auth/config.toml"
    routes = ", ".join(f'"{r}"' for r in ROUTES)
    text = ("# Written by scripts/gluetun-auth.py. Routes not listed in a role are denied.\n"
            "[[roles]]\n"
            'name = "dashboard"\n'
            f"routes = [{routes}]\n"
            'auth = "apikey"\n'
            f'apikey = "{key}"\n')
    if conf.exists() and conf.read_text() == text:
        print(f"{conf}: unchanged")
        return
    conf.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(conf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)
    os.chmod(conf, 0o600)
    print(f"{conf}: written (role dashboard: {', '.join(ROUTES)}); restart Gluetun to apply")


if __name__ == "__main__":
    main()
