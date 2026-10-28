"""Stdlib-only maths: baselines, pace, FiiT matching, PB mapping, SVG charts."""
from datetime import date as _date, datetime, timedelta
from html import escape
from statistics import median

M_PER_MILE = 1609.344
FIIT_TYPES = ("hiit", "cardio", "strength", "fitness_equipment")


def num(v):
    """Float or None; tolerates strings, None, bool and junk."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and abs(f) != float("inf") else None


def fmt_dur(seconds):
    s = num(seconds)
    if s is None:
        return "–"
    s = int(round(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def pace_s(distance_m, duration_s, unit="mi"):
    """Seconds per mile (unit 'mi') or per km; None when unknown."""
    d, t = num(distance_m), num(duration_s)
    if not d or not t or d <= 0 or t <= 0:
        return None
    return t / (d / (M_PER_MILE if unit == "mi" else 1000.0))


def fmt_pace(distance_m, duration_s, unit="mi"):
    p = pace_s(distance_m, duration_s, unit)
    if p is None:
        return "–"
    return f"{fmt_dur(p)}/{'mi' if unit == 'mi' else 'km'}"


def fmt_dist(distance_m, unit="mi"):
    d = num(distance_m)
    if d is None:
        return "–"
    return f"{d / (M_PER_MILE if unit == 'mi' else 1000.0):.2f} {'mi' if unit == 'mi' else 'km'}"


def baseline(rows, key, today, days):
    """Median of `key` over the `days` days before `today` (exclusive); None if no data.

    rows: iterable of dict-likes with a 'date' (YYYY-MM-DD) and the key.
    """
    t = _date.fromisoformat(today)
    lo = (t - timedelta(days=days)).isoformat()
    vals = []
    for r in rows:
        d = r["date"]
        v = num(r[key])
        if v is not None and lo <= d < today:
            vals.append(v)
    return median(vals) if vals else None


def delta_text(value, base, digits=0):
    v, b = num(value), num(base)
    if v is None or b is None:
        return "–"
    d = v - b
    return f"{d:+.{digits}f}"


def delta_tone(value, base, better=1, flat=0.03):
    """'good', 'bad' or 'flat' for value vs baseline; better=1 means higher is better, -1 lower.

    Within `flat` (fraction of the baseline) counts as flat; unknown is flat too.
    """
    v, b = num(value), num(base)
    if v is None or b is None:
        return "flat"
    d = v - b
    if abs(d) <= abs(b) * flat:
        return "flat"
    return "good" if (d > 0) == (better > 0) else "bad"


# Garmin's own training readiness levels.
READINESS_BANDS = ((95, "Prime", "good"), (75, "High", "good"), (50, "Moderate", "warn"), (25, "Low", "bad"),
                   (0, "Poor", "bad"))


def readiness_band(v):
    """(label, tone) for a 0-100 training readiness score; None when unknown."""
    f = num(v)
    if f is None:
        return None
    return next((label, tone) for lo, label, tone in READINESS_BANDS if f >= lo)


def match_fiit(fiit_date, fiit_start, activities):
    """Id of the nearest strength/HIIT-like activity on the same date within +-90 min, else None.

    activities: dicts with id, start_local ('YYYY-MM-DD HH:MM:SS'), type.
    fiit_start 'HH:MM'. Without a start time only a single candidate that day is matched.
    """
    cands = []
    for a in activities:
        sl = a.get("start_local") or ""
        if sl[:10] != fiit_date:
            continue
        typ = (a.get("type") or "").lower()
        if not any(k in typ for k in FIIT_TYPES):
            continue
        cands.append(a)
    if not cands:
        return None
    if not fiit_start:
        return cands[0]["id"] if len(cands) == 1 else None
    try:
        ft = datetime.strptime(f"{fiit_date} {fiit_start[:5]}", "%Y-%m-%d %H:%M")
    except ValueError:
        return None
    best, best_gap = None, None
    for a in cands:
        try:
            at = datetime.strptime(a["start_local"][:16].replace("T", " "), "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        gap = abs((at - ft).total_seconds())
        if gap <= 90 * 60 and (best_gap is None or gap < best_gap):
            best, best_gap = a["id"], gap
    return best


# Garmin running personal-record typeIds (from garminconnect docs): 3=5k, 4=10k, 5=half.
PB_TYPE_IDS = {3: "5k", 4: "10k", 5: "half"}


def pbs_from_garmin(records):
    """[(distance, seconds, date)] from a get_personal_record() response (list or dict)."""
    if isinstance(records, dict):
        for k in ("personalRecords", "records", "items"):
            if isinstance(records.get(k), list):
                records = records[k]
                break
        else:
            records = []
    out = []
    for r in records or []:
        if not isinstance(r, dict):
            continue
        at = r.get("activityType")
        if at is not None and str(at).lower() != "running":
            continue
        try:
            dist = PB_TYPE_IDS.get(int(r.get("typeId")))
        except (TypeError, ValueError):
            continue
        secs = num(r.get("value"))
        if dist and secs and secs > 0:
            when = str(r.get("actStartDateTimeInGMT") or r.get("prStartTimeGmtFormatted") or "")[:10] or None
            out.append((dist, int(round(secs)), when))
    return out


def week_start(d):
    dd = _date.fromisoformat(d[:10])
    return (dd - timedelta(days=dd.weekday())).isoformat()


def weekly_distance(activities, unit="mi"):
    """[(week_start, distance)] for running activities, ascending."""
    tot = {}
    for a in activities:
        if "running" not in (a.get("type") or "").lower() or not a.get("start_local"):
            continue
        d = num(a.get("distance_m"))
        if d is None:
            continue
        w = week_start(a["start_local"])
        tot[w] = tot.get(w, 0.0) + d
    div = M_PER_MILE if unit == "mi" else 1000.0
    return [(w, v / div) for w, v in sorted(tot.items())]


FEEL_COLOURS = {1: "#d33", 2: "#e8833a", 3: "#d9b72b", 4: "#7fb83d", 5: "#2f9e44"}


def svg_line_chart(points, title, markers=None, width=640, height=180, unit=""):
    """Inline SVG line chart.

    points: [(date 'YYYY-MM-DD', value or None)] ascending; None values are gaps.
    markers: {date: (colour, tooltip, ill_bool)} drawn as dots on the baseline.
    """
    pts = [(d, num(v)) for d, v in points]
    vals = [v for _, v in pts if v is not None]
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    if len(vals) < 2:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    head = (f'<figure class="chart card"><figcaption>{escape(title)}'
            f'<span class="latest">{vals[-1]:.3g}{escape(unit)}</span></figcaption>')
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    ml, mr, mt, mb = 44, 10, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    d0 = _date.fromisoformat(pts[0][0])
    span = max((_date.fromisoformat(pts[-1][0]) - d0).days, 1)

    def x(d):
        return ml + iw * (_date.fromisoformat(d) - d0).days / span

    def y(v):
        return mt + ih * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        yy = y(v)
        parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{ml - 4}" y="{yy + 3:.1f}" class="ax" text-anchor="end">{v:.3g}{escape(unit)}</text>')
    parts.append(f'<text x="{ml}" y="{height - 6}" class="ax">{escape(pts[0][0])}</text>')
    parts.append(f'<text x="{width - mr}" y="{height - 6}" class="ax" text-anchor="end">{escape(pts[-1][0])}</text>')
    seg = []
    for d, v in pts:
        if v is None:
            if seg:
                parts.append(_poly(seg, mt + ih))
            seg = []
        else:
            seg.append((x(d), y(v)))
    if seg:
        parts.append(_poly(seg, mt + ih))
    for d, (colour, tip, ill) in sorted((markers or {}).items()):
        if not (pts[0][0] <= d <= pts[-1][0]):
            continue
        cx = x(d)
        parts.append(f'<circle cx="{cx:.1f}" cy="{height - mb - 4}" r="4" fill="{escape(colour)}">'
                     f'<title>{escape(tip)}</title></circle>')
        if ill:
            parts.append(f'<text x="{cx:.1f}" y="{mt + 10}" class="ill" text-anchor="middle">+'
                         f'<title>{escape(tip)}</title></text>')
    parts.append("</svg>")
    return head + "".join(parts) + "</figure>"


def svg_sparkline(values, width=120, height=30):
    """Tiny inline SVG trend line; None values are skipped. Empty string with fewer than 2 values."""
    vals = [(i, num(v)) for i, v in enumerate(values)]
    vals = [(i, v) for i, v in vals if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(v for _, v in vals), max(v for _, v in vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    n = max(len(values) - 1, 1)
    pts = [(2 + (width - 4) * i / n, 2 + (height - 4) * (1 - (v - lo) / (hi - lo))) for i, v in vals]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    # Stretched to the tile width, so no dot (it would turn into an ellipse).
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" preserveAspectRatio="none" aria-hidden="true">'
            f'<polyline points="{line}" class="line" fill="none" vector-effect="non-scaling-stroke"/></svg>')


def _poly(seg, base_y=None):
    if len(seg) == 1:
        return f'<circle cx="{seg[0][0]:.1f}" cy="{seg[0][1]:.1f}" r="2" class="dot"/>'
    pts = " ".join(f"{a:.1f},{b:.1f}" for a, b in seg)
    area = "" if base_y is None else (
        f'<polygon points="{seg[0][0]:.1f},{base_y:.1f} {pts} {seg[-1][0]:.1f},{base_y:.1f}" class="area"/>')
    return area + f'<polyline points="{pts}" class="line" fill="none"/>'
