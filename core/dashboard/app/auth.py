"""Admin login: one user from .env, scrypt-hashed password, signed 30-day session cookie, failed-login limits.

Sessions are stateless: the cookie is "<expiry>.<HMAC(secret, user|expiry|password hash)>", so changing the
password or DASHBOARD_SESSION_SECRET logs out every device. Failure counters live in memory; restarting the
dashboard resets them (and lifts any lockout).
"""
import asyncio
import hashlib
import hmac
import logging
import os
import re
import socket
import time
from collections import deque
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

USERNAME = os.environ.get("DASHBOARD_ADMIN_USERNAME", "")
PASSWORD_HASH = os.environ.get("DASHBOARD_ADMIN_PASSWORD_HASH", "")
SECRET = os.environ.get("DASHBOARD_SESSION_SECRET", "")

COOKIE = "homelab_admin"
SESSION_SECONDS = 30 * 86400
WINDOW = 15 * 60           # failures counted over this window...
MAX_PER_CLIENT = 5         # ...lock one client after this many
MAX_GLOBAL = 20            # ...lock the login for everyone after this many (spread-out guessing)
LOCKOUT = 15 * 60
FAIL_DELAY = 1.0
TRAEFIK_HOST = "traefik"   # requests via port 80 arrive from Traefik; trust its X-Forwarded-For only

log = logging.getLogger("uvicorn.error")


def _parse_hash(value: str):
    """scrypt:<n>:<r>:<p>:<salt hex>:<hash hex> (scripts/dashboard-passwd.py) -> params, or None."""
    try:
        algo, n, r, p, salt, digest = value.split(":")
        if algo != "scrypt":
            return None
        return int(n), int(r), int(p), bytes.fromhex(salt), bytes.fromhex(digest)
    except ValueError:
        return None


_HASH = _parse_hash(PASSWORD_HASH)
CONFIGURED = bool(USERNAME and _HASH and len(SECRET) >= 32)
if not CONFIGURED:
    log.error("Admin login not configured (DASHBOARD_ADMIN_USERNAME / _PASSWORD_HASH / DASHBOARD_SESSION_SECRET "
              "missing or invalid): /admin refuses everyone.")


def check_credentials(username: str, password: str) -> bool:
    if not CONFIGURED:
        return False
    n, r, p, salt, digest = _HASH
    # Always hash, so a wrong username takes as long as a wrong password.
    got = hashlib.scrypt(password.encode(errors="replace"), salt=salt, n=n, r=r, p=p, dklen=len(digest), maxmem=64 * 1024 * 1024)
    user_ok = hmac.compare_digest(username.encode(errors="replace"), USERNAME.encode())
    return hmac.compare_digest(got, digest) and user_ok


def _sign(expiry: int) -> str:
    msg = f"{USERNAME}|{expiry}|{PASSWORD_HASH}".encode()
    return hmac.new(SECRET.encode(), msg, hashlib.sha256).hexdigest()


def new_session() -> str:
    expiry = int(time.time()) + SESSION_SECONDS
    return f"{expiry}.{_sign(expiry)}"


def is_admin(request: Request) -> bool:
    if not CONFIGURED:
        return False
    expiry, _, sig = request.cookies.get(COOKIE, "").partition(".")
    if not expiry.isdigit() or int(expiry) < time.time():
        return False
    return hmac.compare_digest(sig.encode(errors="replace"), _sign(int(expiry)).encode())


def verify_redirect(request: Request) -> str | None:
    """Login URL for forward auth, built from the host Traefik saw (X-Forwarded-Host); None if it looks wrong.
    With HTTPS, the scheme and port change here and the cookie gets Secure."""
    host = (urlsplit("//" + request.headers.get("x-forwarded-host", "")).hostname or "").lower()
    if not re.fullmatch(r"[a-z0-9.-]{1,253}", host):
        return None
    return f"http://{host}:8000/login"


def require_admin(request: Request) -> None:
    """Dependency for admin-only API routes."""
    if not is_admin(request):
        raise HTTPException(401, "login required")


def set_session(response, token: str) -> None:
    # Not Secure: the site is plain HTTP for now (a Secure cookie would be dropped). Add secure=True with HTTPS.
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, path="/", httponly=True, samesite="lax")


def clear_session(response) -> None:
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="lax")


def same_origin(request: Request, allow_null: bool = False) -> bool:
    """Reject form posts from other sites' pages. No Origin header (old browsers) -> SameSite=Lax still applies.
    allow_null: the admin page's no-referrer policy makes its own form posts send "Origin: null"."""
    origin = request.headers.get("origin")
    if origin is None or (allow_null and origin == "null"):
        return True
    return urlsplit(origin).netloc.lower() == request.headers.get("host", "").lower()


def require_same_origin(request: Request) -> None:
    """Dependency for admin write routes (fetch() from the admin page, which sends a real Origin with
    referrerPolicy "same-origin"). Stricter than same_origin(): Origin must be present and match Host
    (no missing or "null" Origin), and the body must be JSON, which another site's form can't send
    without a CORS preflight (never answered)."""
    origin = request.headers.get("origin", "")
    host = request.headers.get("host", "")
    if not origin or urlsplit(origin).netloc.lower() != host.lower():
        log.warning("Write refused: Origin %r does not match Host %r", origin[:100], host[:100])
        raise HTTPException(403, "cross-origin request refused")
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(415, "JSON body required")


# ---- Client address ----
_traefik = {"at": 0.0, "ips": set()}


async def client_ip(request: Request) -> str:
    peer = request.client.host if request.client else "unknown"
    now = time.monotonic()
    if now - _traefik["at"] > 60:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(TRAEFIK_HOST, None)
            _traefik["ips"] = {i[4][0] for i in infos}
        except OSError:
            _traefik["ips"] = set()
        _traefik["at"] = now
    if peer in _traefik["ips"]:
        # Traefik appends the address it saw, so the last entry is the real client; earlier ones can be forged.
        forwarded = request.headers.get("x-forwarded-for", "")
        last = forwarded.rsplit(",", 1)[-1].strip()
        if last:
            return last
    return peer


# ---- Failed-login limits ----
class Limiter:
    def __init__(self):
        self.fails: dict[str, deque] = {}
        self.locked: dict[str, float] = {}
        self.global_fails: deque = deque()
        self.global_locked = 0.0

    def _prune(self, now: float) -> None:
        for q in [*self.fails.values(), self.global_fails]:
            while q and now - q[0] > WINDOW:
                q.popleft()
        self.fails = {k: q for k, q in self.fails.items() if q}
        self.locked = {k: t for k, t in self.locked.items() if t > now}

    def wait(self, ip: str) -> int:
        """Seconds until this client may try again (0 = now)."""
        now = time.monotonic()
        self._prune(now)
        until = max(self.locked.get(ip, 0.0), self.global_locked)
        return max(0, int(until - now + 0.999))

    def failed(self, ip: str) -> None:
        now = time.monotonic()
        q = self.fails.setdefault(ip, deque())
        q.append(now)
        self.global_fails.append(now)
        if len(q) >= MAX_PER_CLIENT:
            self.locked[ip] = now + LOCKOUT
            q.clear()
            log.warning("Admin login: %s locked out for %d min after %d failures", ip, LOCKOUT // 60, MAX_PER_CLIENT)
        if len(self.global_fails) >= MAX_GLOBAL:
            self.global_locked = now + LOCKOUT
            self.global_fails.clear()
            log.warning("Admin login: locked for everyone for %d min after %d failures in %d min",
                        LOCKOUT // 60, MAX_GLOBAL, WINDOW // 60)

    def succeeded(self, ip: str) -> None:
        self.fails.pop(ip, None)


limiter = Limiter()
