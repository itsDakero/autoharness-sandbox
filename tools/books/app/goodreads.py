"""Goodreads CSV export parsing (stdlib only). No database here."""
import csv
import io
import re

SHELVES = {"read": "read", "to-read": "want", "currently-reading": "reading"}
WRAP_RE = re.compile(r'^=?"*(.*?)"*$')


def clean_isbn(v):
    """Strip Goodreads' ="..." wrapper. Empty -> None."""
    v = (v or "").strip()
    m = WRAP_RE.match(v)
    v = (m.group(1) if m else v).strip().replace("-", "")
    return v or None


def parse_rating(v):
    try:
        n = int(float((v or "").strip()))
    except ValueError:
        return None
    return n if 1 <= n <= 5 else None


def parse_date(v):
    v = (v or "").strip()
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", v)
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_int(v):
    try:
        n = int(float((v or "").strip()))
    except ValueError:
        return None
    return n if n > 0 else None


def parse_row(row):
    """One DictReader row -> (book dict, None) or (None, skip reason)."""
    title = (row.get("Title") or "").strip()
    if not title:
        return None, "no title"
    raw_shelf = (row.get("Exclusive Shelf") or "").strip().lower()
    shelf = SHELVES.get(raw_shelf, "read")
    notes = (row.get("Private Notes") or "").strip()
    if raw_shelf not in SHELVES:
        extra = f"Goodreads shelf: {raw_shelf or 'none'}"
        notes = f"{notes}\n{extra}".strip()
    isbn13, isbn10 = clean_isbn(row.get("ISBN13")), clean_isbn(row.get("ISBN"))
    book = {
        "goodreads_id": (row.get("Book Id") or "").strip() or None,
        "isbn13": isbn13, "isbn10": isbn10,
        "title": title,
        "authors": (row.get("Author") or "").strip(),
        "pages": parse_int(row.get("Number of Pages")),
        "shelf": shelf,
        "rating": parse_rating(row.get("My Rating")),
        "date_added": parse_date(row.get("Date Added")),
        "date_finished": parse_date(row.get("Date Read")),
        "notes": notes or None,
        "review": (row.get("My Review") or "").strip() or None,
    }
    return book, None


def parse_csv(data):
    """bytes or str -> (list of (line_no, book), list of (title, reason))."""
    if isinstance(data, bytes):
        data = data.decode("utf-8-sig", errors="replace")
    elif data.startswith("﻿"):
        data = data[1:]
    rows, skipped = [], []
    for n, row in enumerate(csv.DictReader(io.StringIO(data)), start=2):
        book, why = parse_row(row)
        if book is None:
            skipped.append(((row.get("Title") or "").strip() or f"row {n}", why))
        else:
            rows.append((n, book))
    return rows, skipped
