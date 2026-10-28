"""Rule-based outfit generator (stdlib only, pure functions; the caller supplies rng and data)."""
import itertools
import random

NEUTRALS = {"black", "white", "grey", "navy", "beige", "brown"}
CLASHES = {frozenset(p) for p in (("sport", "smart"), ("sport", "formal"), ("casual", "formal"))}
OK_STATUS = ("tagged", "reviewed")
MAX_COMBOS = 50_000
NOTE_NO_OUTER = "No suitable outer layer owned"
NOTE_REPEAT = "Everything fits the no-repeat window; showing a repeat"
W_MIN, W_MAX = 0.2, 3.0


def key_of(items):
    return "-".join(str(i) for i in sorted(it["id"] for it in items))


def build_pool(items):
    """Owned, active, tagged items with a real category. Accessories are ignored."""
    return [it for it in items
            if it.get("kind") == "owned" and it.get("status") == "active"
            and it.get("category") and it["category"] != "accessory"
            and it.get("tag_status") in OK_STATUS]


def fits_season(it, season):
    return not it.get("seasons") or season in it["seasons"]


def outer_need(weather):
    """'required', 'none' or 'optional' from the forecast (no forecast: optional)."""
    if not weather or weather.get("tmax") is None:
        return "optional"
    rain = weather.get("rain") or 0
    if weather["tmax"] < 14 or rain >= 50:
        return "required"
    if weather["tmax"] >= 20:
        return "none"
    return "optional"


def colour_rule(items):
    """<=2 distinct non-neutral colours across the outfit (shoes count), <=1 item with 'multi'."""
    non_neutral, multi = set(), 0
    for it in items:
        cols = it.get("colours") or []
        if "multi" in cols:
            multi += 1
        non_neutral.update(c for c in cols if c != "multi" and c not in NEUTRALS)
    return multi <= 1 and len(non_neutral) <= 2


def style_rule(items):
    styles = [it["style"] for it in items if it.get("style")]
    for a, b in itertools.combinations(styles, 2):
        if frozenset((a, b)) in CLASHES:
            return False
    return True


def features(items):
    out = []
    for a, b in itertools.combinations(items, 2):
        for ca in a.get("colours") or []:
            for cb in b.get("colours") or []:
                if ca != cb:
                    out.append("c:" + "|".join(sorted((ca, cb))))
        if a.get("style") and b.get("style") and a["style"] != b["style"]:
            out.append("s:" + "|".join(sorted((a["style"], b["style"]))))
    return out


def weights(votes, items_by_id):
    """votes: [(vote, [item ids])]. Recomputed every time: clamp(1 + 0.2 ups - 0.3 downs)."""
    ups, downs = {}, {}
    for vote, ids in votes:
        its = [items_by_id[i] for i in ids if i in items_by_id]
        for f in set(features(its)):
            d = ups if vote == 1 else downs
            d[f] = d.get(f, 0) + 1
    return {f: max(W_MIN, min(W_MAX, 1 + 0.2 * ups.get(f, 0) - 0.3 * downs.get(f, 0)))
            for f in set(ups) | set(downs)}


def score(items, w, rng):
    fs = features(items)
    base = sum(w.get(f, 1.0) for f in fs) / len(fs) if fs else 1.0
    return base * rng.uniform(0.85, 1.15)


def _missing_reason(pool, by_cat):
    """Why no shape can be built: names the missing category."""
    def have(c):
        return bool(by_cat.get(c))

    def owned(c):
        return any(it["category"] == c for it in pool)
    if not have("shoes"):
        if owned("shoes"):
            return "No shoes item fits this season; tag some for it"
        return "Add at least one shoes item marked bought"
    if have("dress") or (have("top") and have("bottom")):
        return None
    for c in ("top", "bottom"):
        if not have(c):
            if owned(c):
                return f"No {c} item fits this season; tag some for it"
            return f"Add at least one {c} item marked bought (or a dress)"
    return "Nothing to wear yet"


def _combos(lists, rng):
    total = 1
    for lst in lists:
        total *= len(lst)
    if total <= MAX_COMBOS:
        yield from itertools.product(*lists)
    else:
        for _ in range(MAX_COMBOS):
            yield tuple(rng.choice(lst) for lst in lists)


def pick(pool, season, weather=None, w=None, rng=None, exclude_keys=(), recent_ids=()):
    """-> (items or None, note). note is the reason when items is None.

    exclude_keys: never returned (down-voted, or today's key for 'Another').
    recent_ids: top/bottom/dress ids worn in the window; used unless nothing else is left."""
    rng = rng or random.Random()
    w = w or {}
    pool = build_pool(pool)
    in_season = [it for it in pool if fits_season(it, season)]
    by_cat = {}
    for it in in_season:
        by_cat.setdefault(it["category"], []).append(it)
    reason = _missing_reason(pool, by_cat)
    if reason:
        return None, reason
    need = outer_need(weather)
    outers = by_cat.get("outerwear", [])
    note = ""
    if need == "none":
        outer_opts = [None]
    elif need == "required":
        if outers:
            outer_opts = list(outers)
        else:
            outer_opts, note = [None], NOTE_NO_OUTER
    else:
        outer_opts = [None] + outers
    shapes = []
    if by_cat.get("top") and by_cat.get("bottom"):
        shapes.append([by_cat["top"], by_cat["bottom"], by_cat["shoes"]])
    if by_cat.get("dress"):
        shapes.append([by_cat["dress"], by_cat["shoes"]])
    exclude_keys, recent_ids = set(exclude_keys), set(recent_ids)
    fresh, repeats = [], []
    for base in shapes:
        for combo in _combos(base + [outer_opts], rng):
            items = [it for it in combo if it is not None]
            if not colour_rule(items) or not style_rule(items):
                continue
            k = key_of(items)
            if k in exclude_keys:
                continue
            s = score(items, w, rng)
            core = [it["id"] for it in items if it["category"] in ("top", "bottom", "dress")]
            (repeats if recent_ids.intersection(core) else fresh).append((s, k, items))
    if not fresh and not repeats:
        return None, "No combination passes the colour and style rules"
    if not fresh:
        note = (note + "; " if note else "") + NOTE_REPEAT
    best = max(fresh or repeats, key=lambda t: t[0])
    items = sorted(best[2], key=lambda it: ("top", "dress", "bottom", "shoes", "outerwear").index(it["category"]))
    return items, note
