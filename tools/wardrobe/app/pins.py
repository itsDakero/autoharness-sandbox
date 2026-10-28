"""Pinterest pin link -> image. Only Pinterest hosts are ever fetched (no SSRF)."""
import http.client
import re
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

_TLDS = ("com", "co.uk", "com.au", "ca", "de", "fr", "es", "it", "nz", "ie", "at", "ch", "pt",
         "se", "dk", "jp", "co.kr", "com.mx", "cl", "ph", "ru")
PAGE_RE = re.compile(r"^(www\.|[a-z]{2}\.)?pinterest\.(" + "|".join(re.escape(t) for t in _TLDS)
                     + r")$|^pin\.it$|^api\.pinterest\.com$")
IMAGE_HOST = "i.pinimg.com"
PAGE_CAP = 2 * 1024 * 1024
IMAGE_CAP = 15 * 1024 * 1024
UA = "Mozilla/5.0 (X11; Linux x86_64) wardrobe/0.1"


class PinError(Exception):
    pass


def _parts(url):
    try:
        p = urllib.parse.urlsplit(url)
        if "@" in p.netloc or "\\" in p.netloc:
            return "", "", None  # userinfo: urllib would dial a different host than checked
        return p.scheme, (p.hostname or "").lower(), p.port
    except ValueError:
        return "", "", None


def allowed_page_url(url):
    scheme, host, port = _parts(url)
    return scheme == "https" and port in (None, 443) and bool(PAGE_RE.match(host))


def allowed_image_url(url):
    scheme, host, port = _parts(url)
    return scheme == "https" and port in (None, 443) and host == IMAGE_HOST


class _OgParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = None

    def handle_starttag(self, tag, attrs):
        if tag != "meta" or self.image:
            return
        a = dict(attrs)
        if (a.get("property") or a.get("name")) in ("og:image", "twitter:image") and a.get("content"):
            self.image = a["content"]


def extract_og_image(html):
    p = _OgParser()
    try:
        p.feed(html)
    except Exception:  # noqa: BLE001 - malformed HTML: treat as no image
        pass
    return p.image


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to allowed hosts (set per opener)."""

    def __init__(self, check):
        self.check = check

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not self.check(newurl):
            raise PinError("redirect to a host that is not allowed")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _get(url, check, cap, timeout=10):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _Redirects(check))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with opener.open(req, timeout=timeout) as r:
            if not check(r.geturl()):
                raise PinError("final host not allowed")
            data = r.read(cap + 1)
    except PinError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        raise PinError(f"fetch failed: {e}") from None
    if len(data) > cap:
        raise PinError("response too large")
    return data


def fetch_image(url):
    """Return image bytes for a pin URL, or raise PinError."""
    if not allowed_page_url(url):
        raise PinError("not a Pinterest https link")
    html = _get(url, allowed_page_url, PAGE_CAP).decode("utf-8", "replace")
    img = extract_og_image(html)
    if not img:
        raise PinError("no og:image on the page")
    if not allowed_image_url(img):
        raise PinError("image host not allowed")
    return _get(img, allowed_image_url, IMAGE_CAP)
