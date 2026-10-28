"""Open Library search + cover download (stdlib urllib, no key). Every call has a timeout."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

UA = "homelab-books/0.1"
SEARCH_TIMEOUT = 8
COVER_TIMEOUT = 10
MAX_COVER = 2 * 1024 * 1024
FIELDS = "key,title,author_name,isbn,cover_i,number_of_pages_median"


class CoverMissing(Exception):
    """The source has no cover (404)."""


def _open(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)  # noqa: S310 (https only, fixed hosts)


def search(q, limit=10):
    """-> list of {title, authors, isbn13, isbn10, cover_id, pages}. Raises on any failure."""
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {"q": q, "limit": limit, "fields": FIELDS})
    with _open(url, SEARCH_TIMEOUT) as r:
        data = json.loads(r.read(2 * 1024 * 1024).decode("utf-8", errors="replace"))
    out = []
    for d in data.get("docs", []):
        isbns = [str(i) for i in d.get("isbn", [])]
        out.append({
            "title": d.get("title") or "",
            "authors": ", ".join(d.get("author_name", [])[:3]),
            "isbn13": next((i for i in isbns if len(i) == 13), None),
            "isbn10": next((i for i in isbns if len(i) == 10), None),
            "cover_id": d.get("cover_i"),
            "pages": d.get("number_of_pages_median"),
        })
    return [o for o in out if o["title"]]


def lookup_cover_id(title, authors):
    q = f"{title} {authors.split(',')[0] if authors else ''}".strip()
    for o in search(q, limit=3):
        if o["cover_id"]:
            return o["cover_id"]
    return None


def fetch_image(url, dest):
    """Download to dest via a tmp file + rename. Only a 200 image/* under MAX_COVER is kept.
    Raises CoverMissing on 404, another exception on any other failure. Never leaves a partial file."""
    tmp = dest + ".tmp"
    try:
        try:
            r = _open(url, COVER_TIMEOUT)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise CoverMissing() from e
            raise
        with r:
            if r.status != 200:
                raise OSError(f"status {r.status}")
            if not (r.headers.get("Content-Type") or "").lower().startswith("image/"):
                raise OSError("not an image")
            data = r.read(MAX_COVER + 1)
        if len(data) > MAX_COVER or len(data) < 200:
            raise OSError("bad size")
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, dest)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
