"""Gap analysis (stdlib only, pure functions): which missing item would unlock the most outfits.

Uses the outfit rules from outfits.py. Names the item only; no product links."""
import itertools
import math
import random

from . import outfits, tags

GAP_CATS = ("top", "bottom", "shoes", "outerwear", "dress")
SEASONS = ("spring", "summer", "autumn", "winter")
GAP_COMBOS = 5_000  # per candidate; the outfit generator's cap (outfits.MAX_COMBOS) is the upper bound
SIZE_KEY = {"top": "top_size", "bottom": "bottom_size", "shoes": "shoe_size",
            "dress": "dress_size", "outerwear": "top_size"}


def _enum(lists, rng):
    """Like outfits._combos with a smaller cap. -> (iterator, total)."""
    total = 1
    for lst in lists:
        total *= len(lst)
    cap = min(outfits.MAX_COMBOS, GAP_COMBOS)
    if total <= cap:
        return itertools.product(*lists), total
    return (tuple(rng.choice(lst) for lst in lists) for _ in range(cap)), total


def _count(shapes):
    """Valid outfits over the shapes (lists of lists). Sampled shapes are scaled to their size."""
    rng = random.Random(0)
    valid_total = 0
    for lists in shapes:
        if not all(lists):
            continue
        it, total = _enum(lists, rng)
        n = ok = 0
        for combo in it:
            n += 1
            items = list(combo)
            if outfits.colour_rule(items) and outfits.style_rule(items):
                ok += 1
        if n:
            valid_total += ok if n == total else round(ok * total / n)
    return valid_total


def _base_shapes(by_cat, extra=None, replace=None):
    """Base shapes (no outer layer); `replace` swaps one category's list for [candidate]."""
    def get(c):
        return [replace[1]] if replace and replace[0] == c else by_cat.get(c, [])
    shapes = [[get("top"), get("bottom"), get("shoes")], [get("dress"), get("shoes")]]
    if extra is not None:
        shapes = [s + [extra] for s in shapes]
    return shapes


def _price(profile, cat):
    """-> None (no limit), 0 (skip category) or a positive float."""
    try:
        v = float(str((profile or {}).get(f"max_price_{cat}", "")).strip().replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(v) or v < 0:
        return None
    return v


def _fmt(v):
    return str(int(v)) if v == int(v) else f"{v:.2f}"


def _in_season(items, season):
    full = outfits.build_pool(items)
    by_cat = {}
    for it in full:
        if outfits.fits_season(it, season):
            by_cat.setdefault(it["category"], []).append(it)
    return full, by_cat


def analyse(items, season, profile=None, wishlist=()):
    """-> (rows, current, reason). rows: dicts {category, colour, season, unlocks, size, max_price,
    on_wishlist}, best first. current: valid base outfits now. reason: why rows is empty, else None."""
    profile = profile or {}
    full_pool, by_cat = _in_season(items, season)
    current = _count(_base_shapes(by_cat))
    wish = {(w.get("category"), c) for w in wishlist for c in (w.get("colours") or [])}
    cur = (profile.get("currency") or "GBP").strip() or "GBP"
    rows = []
    n = 0
    for cat in GAP_CATS:
        price = _price(profile, cat)
        if price == 0:
            continue
        owned_cols = {c for it in by_cat.get(cat, []) for c in (it.get("colours") or [])}
        for colour in tags.COLOURS:
            if colour in owned_cols:
                continue
            n -= 1
            cand = {"id": n, "kind": "owned", "status": "active", "category": cat,
                    "colours": [colour], "seasons": [season], "style": None,
                    "tag_status": "tagged"}
            if cat == "outerwear":
                shapes = _base_shapes(by_cat, extra=[cand])
            else:
                shapes = _base_shapes(by_cat, replace=(cat, cand))
                if cat in ("top", "bottom"):
                    shapes = shapes[:1]
                elif cat == "dress":
                    shapes = shapes[1:]
            unlocks = _count(shapes)
            if unlocks <= 0:
                continue
            size = (profile.get(SIZE_KEY[cat]) or "").strip()
            rows.append({"category": cat, "colour": colour, "season": season, "unlocks": unlocks,
                         "size": size or "size not set",
                         "max_price": "no limit" if price is None else f"up to {cur} {_fmt(price)}",
                         "on_wishlist": (cat, colour) in wish})
    order = {c: i for i, c in enumerate(GAP_CATS)}
    corder = {c: i for i, c in enumerate(tags.COLOURS)}
    rows.sort(key=lambda r: (-r["unlocks"], order[r["category"]], corder[r["colour"]]))
    reason = None
    if not rows:
        reason = outfits._missing_reason(full_pool, by_cat) or "Nothing to suggest yet"
    return rows, current, reason


def rank(items, season, profile=None, wishlist=()):
    return analyse(items, season, profile, wishlist)[0]
