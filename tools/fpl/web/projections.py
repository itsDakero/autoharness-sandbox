"""Projection maths, no I/O: FPL ep_next -> per-gameweek points, minutes overrides, source choice, chip windows.

Row shape everywhere: {"element": int, "gw": int, "pts": float, "xmins": float}.
"""
import csv
import datetime as dt
import io

# own-side fixture difficulty (FPL's 1-5) -> multiplier on the per-match points
SCALE = {1: 1.25, 2: 1.1, 3: 1.0, 4: 0.85, 5: 0.7}
MINUTES_DEFAULT = 45.0  # no player_history rows yet
OVERRIDE_CAP = 1.5      # an override can lift pts by at most this factor
AUTO_MAX_AGE = dt.timedelta(days=8)
FIRST_HALF_LAST_GW = 19
CHIPS = ("wildcard", "freehit", "bboost", "3xc")
SOLVER_CHIP = {"wildcard": "wc", "freehit": "fh", "bboost": "bb", "3xc": "tc"}
OWN_SOURCE = "fpl-ep"


def num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if f == f else default


def fixture_scales(fixtures):
    """{gw: {team_id: [scale, ...]}}; blank gameweeks are absent, doubles have two entries."""
    out = {}
    for f in fixtures:
        gw = f.get("event")
        if gw is None or gw != gw:
            continue
        gw = int(gw)
        for team, diff in ((f.get("team_h"), f.get("team_h_difficulty")),
                           (f.get("team_a"), f.get("team_a_difficulty"))):
            if team is None or team != team:
                continue
            out.setdefault(gw, {}).setdefault(int(team), []).append(SCALE.get(int(num(diff, 3)), 1.0))
    return out


def gw_range(next_gw, horizon):
    return list(range(next_gw, min(39, next_gw + max(int(horizon), 1))))


def recent_minutes(history_minutes):
    """Mean of the last 5 minutes values (list, oldest first); 45 when there are none."""
    last = [num(m) for m in history_minutes[-5:]]
    return sum(last) / len(last) if last else MINUTES_DEFAULT


def build_fpl_ep(players, scales, history, next_gw, horizon):
    """players: dicts with id, team, ep_next, form, chance_of_playing_next_round. history: {element: [minutes]}."""
    rows = []
    gws = gw_range(next_gw, horizon)
    for p in players:
        el, team = int(p["id"]), int(p["team"])
        nxt = sum(scales.get(next_gw, {}).get(team, []))
        ep = num(p.get("ep_next"))
        base = ep / nxt if nxt > 0 and ep > 0 else None
        form = num(p.get("form"))
        mins = recent_minutes(history.get(el, []))
        chance = p.get("chance_of_playing_next_round")
        chance = None if chance is None or chance != chance else num(chance, None)
        for gw in gws:
            sc = scales.get(gw, {}).get(team, [])
            if gw == next_gw:
                per_match = base if base is not None else 0.0
            else:
                per_match = base if base is not None else form
            xm = len(sc) * mins
            if gw == next_gw and chance is not None:
                xm *= chance / 100.0
            rows.append({"element": el, "gw": gw, "pts": per_match * sum(sc), "xmins": xm})
    return rows


def parse_overrides(text):
    """CSV text (element,gw,xmins,note,updated_at) -> (valid rows, bad lines). Never raises."""
    good, bad = [], []
    if not text or not text.strip():
        return good, bad
    try:
        reader = csv.reader(io.StringIO(text))
        header = next(reader, None)
        if header is None:
            return good, bad
        names = [h.strip().lower() for h in header]
        if names[:3] != ["element", "gw", "xmins"]:
            return good, [",".join(header)]
        for line in reader:
            if not line or not "".join(line).strip():
                continue
            try:
                row = dict(zip(names, line))
                xm = row["xmins"].strip().lower()
                x = 0.0 if xm == "out" else float(xm)
                if not 0 <= x <= 120 or x != x:
                    raise ValueError("minutes")
                good.append({"element": int(row["element"]), "gw": int(row["gw"]), "xmins": x,
                             "note": (row.get("note") or "").strip(), "updated_at": (row.get("updated_at") or "").strip()})
            except (KeyError, ValueError, TypeError):
                bad.append(",".join(line))
    except csv.Error:
        bad.append("(unreadable CSV)")
    return good, bad


def dump_overrides(rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["element", "gw", "xmins", "note", "updated_at"])
    for r in rows:
        w.writerow([r["element"], r["gw"], f"{r['xmins']:g}", r.get("note", ""), r.get("updated_at", "")])
    return buf.getvalue()


def split_overrides(overrides, elements, next_gw, horizon):
    """-> (active, ignored). Ignored = unknown player, past gameweek or outside the horizon (shown greyed)."""
    gws = set(gw_range(next_gw, horizon))
    known = set(elements)
    active, ignored = [], []
    for o in overrides:
        (active if o["element"] in known and o["gw"] in gws else ignored).append(o)
    return active, ignored


def apply_overrides(rows, active, forms, scales, teams):
    """Return new rows with minutes overrides applied (the last override per player+gw wins).
    forms: {element: form}; teams: {element: team_id}."""
    ov = {(o["element"], o["gw"]): o["xmins"] for o in active}
    out = []
    for r in rows:
        key = (r["element"], r["gw"])
        if key not in ov:
            out.append(r)
            continue
        xo = ov[key]
        sc = scales.get(r["gw"], {}).get(teams.get(r["element"]), [])
        if xo == 0 or not sc:
            pts = 0.0
            xm = 0.0 if xo == 0 else r["xmins"]
        elif r["xmins"] > 0:
            pts = r["pts"] * min(xo / r["xmins"], OVERRIDE_CAP)
            xm = xo * len(sc)
        else:
            pts = forms.get(r["element"], 0.0) * sum(sc) * xo / (90.0 * len(sc))
            xm = xo * len(sc)
        out.append({**r, "pts": pts, "xmins": xm})
    return out


def pick_source(candidates, setting, next_gw, now):
    """candidates: [{"source", "path", "generated_at" (aware datetime), "gws" (set)}], any order.
    -> (candidate or None, note). None means: compute fpl-ep. Never raises on odd input."""
    covering = [c for c in candidates if next_gw in c["gws"]]
    if setting and setting != "auto":
        mine = sorted((c for c in covering if c["source"] == setting), key=lambda c: c["generated_at"], reverse=True)
        if mine:
            return mine[0], ""
        return None, f"source '{setting}' has no file covering GW{next_gw}; using {OWN_SOURCE}"
    fresh = sorted((c for c in covering if c["source"] != OWN_SOURCE and now - c["generated_at"] <= AUTO_MAX_AGE),
                   key=lambda c: c["generated_at"], reverse=True)
    return (fresh[0], "") if fresh else (None, "")


def half_of(gw):
    return 1 if gw <= FIRST_HALF_LAST_GW else 2


def chips_left(history_chips):
    """history['chips'] ([{name, event}]) -> {1: [names unused], 2: [...]}; unknown names are ignored."""
    used = {1: set(), 2: set()}
    for c in history_chips or []:
        try:
            if c["name"] in CHIPS:
                used[half_of(int(c["event"]))].add(c["name"])
        except (KeyError, TypeError, ValueError):
            continue
    return {h: [c for c in CHIPS if c not in used[h]] for h in (1, 2)}


def chip_settings(left, gws, plan_chips):
    """Solver keys: chip_limits and allowed_chip_gws. The solver caps an allowed chip at 1 over the whole
    horizon, so a chip unused in both halves still gets at most one use in the plan."""
    limits = {"wc": 0, "fh": 0, "bb": 0, "tc": 0}
    allowed = {}
    if not plan_chips:
        return limits, allowed
    for chip in CHIPS:
        key = SOLVER_CHIP[chip]
        window = [g for g in gws if chip in left.get(half_of(g), [])]
        if window:
            limits[key] = 1
            allowed[key] = window
    return limits, allowed


def deadline_due(deadline, now, sent_gws, gw, window=dt.timedelta(hours=36)):
    """True when the deadline is in (now, now+window] and no line was sent for this gameweek."""
    return now < deadline <= now + window and gw not in (sent_gws or [])
