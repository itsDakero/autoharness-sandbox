"""Running analysis: HR zones, 80/20, efficiency, decoupling, VDOT, predictions, best efforts (stdlib only).

Pure functions on plain values. Every formula has a worked example in tests/test_running.py.
All thresholds are constants at the top.
"""
import math
from datetime import date as _date, timedelta
from html import escape

from .logic import M_PER_MILE, fmt_dur, num, week_start

# ---- zones
ZONE_PCT = (0.50, 0.60, 0.70, 0.80, 0.90)    # lower edge of Z1..Z5 as a share of max HR
MAX_HR_RANGE = (100, 230)
MAX_HR_DAYS = 365
GAP_S = 30                                   # HR samples further apart than this are not counted
ZONE_WEEKS = 26
EASY_GOOD = 0.75                             # share of time in Z1-Z2 (80/20 check, last 28 days)
EASY_WARN = 0.60
EASY_DAYS = 28

# ---- efficiency, decoupling
EF_MIN_S = 20 * 60
EF_DAYS = 180
EF_WINDOW_DAYS = 28
DECOUPLE_MIN_S = 45 * 60
DECOUPLE_MIN_LAPS = 4
DECOUPLE_GOOD = 5.0
DECOUPLE_WARN = 10.0

# ---- VO2max, predictions
VO2_MIN_S = 20 * 60
VO2_MIN_RATIO = 0.5
VO2_DAYS = 180
VO2_CURRENT_DAYS = 30
FACTOR_MIN_M = 3000
FACTOR_RANGE = (0.8, 1.2)
FACTOR_DAYS = 365
PRED_DAYS = 90
GAP_GOOD_S = 300
GAP_WARN_S = 720
HALF_M = 21097.5
HALF_WEEKLY_FACTOR = 0.5
HALF_LONG_KM = 18.0
READY_GOOD = 90
READY_WARN = 70
VOLUME_DAYS = 56
LONGEST_DAYS = 42

CADENCE_RANGE = (120, 230)                   # steps/min; anything else is a missing or stride-per-minute value

# ---- best efforts
DISTANCES = {"400m": 400.0, "1k": 1000.0, "1mi": M_PER_MILE, "5k": 5000.0, "10k": 10000.0, "half": HALF_M}
DIST_LABELS = {"400m": "400 m", "1k": "1 km", "1mi": "1 mile", "5k": "5 km", "10k": "10 km", "half": "Half"}
MIN_PACE_S_PER_KM = 150.0                    # anything faster is a GPS glitch
CURVE_DAYS = 90


def _day(s):
    try:
        return _date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _within(start_local, today, days):
    d = _day(start_local)
    return d is not None and today - timedelta(days=days) <= d <= today


# ---------------------------------------------------------------- zones

def zone_bounds(max_hr):
    """[(low, high)] for Z1..Z5; Z5 ends at max HR. Below 50% of max counts in no zone."""
    m = num(max_hr)
    if not m or m <= 0:
        return []
    lows = [round(p * m, 1) for p in ZONE_PCT]
    return [(lows[i], lows[i + 1] if i < 4 else m) for i in range(5)]


def hr_histogram(samples):
    """{bpm: seconds} from (t, dist, hr) samples; intervals with dt <= 0 or > GAP_S are skipped."""
    out = {}
    s = list(samples or [])
    for a, b in zip(s, s[1:]):
        hr = num(a[2])
        dt = b[0] - a[0]
        if hr is None or hr <= 0 or dt <= 0 or dt > GAP_S:
            continue
        k = int(round(hr))
        out[k] = out.get(k, 0.0) + dt
    return out


def zones_from_hist(hist_rows, max_hr):
    """[secs Z1..Z5] from (bpm, seconds) pairs; [] when max HR is unknown."""
    bounds = zone_bounds(max_hr)
    if not bounds:
        return []
    out = [0.0] * 5
    for bpm, secs in hist_rows or []:
        b, s = num(bpm), num(secs)
        if b is None or s is None:
            continue
        for i in range(4, -1, -1):
            if b >= bounds[i][0]:
                out[i] += s
                break
    return out


def zones_from_garmin(rows):
    """([secs Z1..Z5], {zone: low_bpm}) from (zone, seconds, low_bpm) rows; ([], {}) when empty."""
    secs, lows = [0.0] * 5, {}
    seen = False
    for z, s, low in rows or []:
        z, s = num(z), num(s)
        if z is None or s is None or not 1 <= int(z) <= 5:
            continue
        seen = True
        secs[int(z) - 1] += s
        if num(low) is not None:
            lows[int(z)] = num(low)
    return (secs, lows) if seen else ([], {})


def default_max_hr(rows, today=None):
    """Highest activities.max_hr in the last 365 days (rows: dict-likes with start_local, max_hr), else None."""
    today = today or _date.today()
    vals = [num(r["max_hr"]) for r in rows or [] if _within(r["start_local"], today, MAX_HR_DAYS)]
    vals = [v for v in vals if v is not None and MAX_HR_RANGE[0] <= v <= MAX_HR_RANGE[1]]
    return max(vals) if vals else None


def parse_max_hr(value):
    """int in 100-230 from a string/number, else None."""
    try:
        v = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return v if MAX_HR_RANGE[0] <= v <= MAX_HR_RANGE[1] else None


def effective_max_hr(setting, rows, today=None):
    v = parse_max_hr(setting)
    return float(v) if v is not None else default_max_hr(rows, today)


def share_easy(zone_secs):
    """Share of time in Z1+Z2, or None without data."""
    z = [num(x) or 0.0 for x in (zone_secs or [])]
    tot = sum(z)
    return (z[0] + z[1]) / tot if len(z) >= 2 and tot > 0 else None


def easy_tone(share):
    if share is None:
        return "flat"
    return "good" if share >= EASY_GOOD else "warn" if share >= EASY_WARN else "bad"


def weekly_zone_secs(items, today=None, weeks=ZONE_WEEKS):
    """[(week_start, [secs Z1..Z5])] for the last `weeks` weeks (Monday starts), ascending.

    items: (start_local, [secs Z1..Z5]) pairs.
    """
    today = today or _date.today()
    first = _date.fromisoformat(week_start(today.isoformat())) - timedelta(weeks=weeks - 1)
    tot = {(first + timedelta(weeks=i)).isoformat(): [0.0] * 5 for i in range(weeks)}
    for start, z in items:
        d = _day(start)
        if d is None or len(z) != 5:
            continue
        w = week_start(d.isoformat())
        if w in tot:
            tot[w] = [a + (num(b) or 0.0) for a, b in zip(tot[w], z)]
    return sorted(tot.items())


# ---------------------------------------------------------------- efficiency and decoupling

def is_easy(avg_hr, z2_low, z3_low):
    a, lo, hi = num(avg_hr), num(z2_low), num(z3_low)
    return a is not None and lo is not None and hi is not None and lo <= a < hi


def efficiency(distance_m, duration_s, avg_hr):
    """(m/min)/bpm for runs of 20 min or more, else None."""
    d, t, h = num(distance_m), num(duration_s), num(avg_hr)
    if not d or not t or not h or d <= 0 or t < EF_MIN_S or h <= 0:
        return None
    return (d / (t / 60.0)) / h


def ef_trend(points, today=None):
    """(mean last 28 days, mean of the 28 before, change %) from (date, ef) points; None without both."""
    today = today or _date.today()
    cur, prev = [], []
    for d, v in points:
        dd, f = _day(d), num(v)
        if dd is None or f is None:
            continue
        age = (today - dd).days
        if 0 <= age < EF_WINDOW_DAYS:
            cur.append(f)
        elif EF_WINDOW_DAYS <= age < 2 * EF_WINDOW_DAYS:
            prev.append(f)
    if not cur or not prev:
        return None
    a, b = sum(cur) / len(cur), sum(prev) / len(prev)
    return a, b, (a - b) / b * 100.0 if b else 0.0


def decoupling(laps):
    """Pace:HR drift in % ((EF1-EF2)/EF1*100) between the halves of a run; None when not computable.

    Needs 45 min or more and at least 4 laps with HR. A lap is in the first half when its time midpoint
    is before half the total time. Each half's EF is duration-weighted.
    """
    good = []
    for lap in laps or []:
        d, t, h = num(lap["distance_m"]), num(lap["duration_s"]), num(lap["avg_hr"])
        if d is not None and t and t > 0 and h and h > 0:
            good.append((d, t, h))
    total = sum(t for _, t, _ in good)
    if len(good) < DECOUPLE_MIN_LAPS or total < DECOUPLE_MIN_S:
        return None
    halves, elapsed = ([], []), 0.0
    for d, t, h in good:
        halves[0 if elapsed + t / 2.0 < total / 2.0 else 1].append((d, t, h))
        elapsed += t
    efs = []
    for half in halves:
        dur = sum(t for _, t, _ in half)
        if dur <= 0:
            return None
        hr = sum(h * t for _, t, h in half) / dur
        dist = sum(d for d, _, _ in half)
        if hr <= 0 or dist <= 0:
            return None
        efs.append((dist / (dur / 60.0)) / hr)
    return (efs[0] - efs[1]) / efs[0] * 100.0


def decoupling_tone(v):
    if v is None:
        return "flat"
    return "good" if v < DECOUPLE_GOOD else "warn" if v <= DECOUPLE_WARN else "bad"


# ---------------------------------------------------------------- VO2max, VDOT, predictions

def vo2_at_speed(v_m_min):
    return -4.60 + 0.182258 * v_m_min + 0.000104 * v_m_min ** 2


def pct_vo2max(t_min):
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(dist_m, secs):
    d, t = num(dist_m), num(secs)
    if not d or not t or d <= 0 or t <= 0:
        return None
    tm = t / 60.0
    return vo2_at_speed(d / tm) / pct_vo2max(tm)


def predict_time(vdot_value, dist_m, lo=60.0, hi=21600.0):
    """Seconds for dist_m at the given VDOT (bisection between 60 s and 6 h); None if out of range."""
    v = num(vdot_value)
    if not v or v <= 0:
        return None
    f_lo, f_hi = vdot(dist_m, lo), vdot(dist_m, hi)
    if f_lo is None or f_hi is None or not f_hi <= v <= f_lo:
        return None
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if vdot(dist_m, mid) > v:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def riegel(t1, d1, d2):
    return t1 * (d2 / d1) ** 1.06


def predictions(t5k):
    """{'5k': (riegel, vdot), '10k': ..., 'half': ...} predicted from a 5k effort in seconds."""
    v = vdot(5000, t5k)
    out = {}
    for key in ("5k", "10k", "half"):
        d = DISTANCES[key]
        out[key] = (riegel(t5k, 5000.0, d), predict_time(v, d)) if v else (None, None)
    return out


def effective_vo2max(dist_m, secs, avg_hr, max_hr):
    """Runalyze method: VO2 at the run's speed divided by the %VO2max implied by %HRmax."""
    d, t, h, m = num(dist_m), num(secs), num(avg_hr), num(max_hr)
    if not d or not t or not h or not m or d <= 0 or t < VO2_MIN_S or m <= 0:
        return None
    ratio = h / m
    if ratio <= VO2_MIN_RATIO:
        return None
    return vo2_at_speed(d / (t / 60.0)) / ((ratio - 0.37) / 0.64)


def correction_factor(runs, max_hr, today=None):
    """Factor that moves effective VO2max onto the best recent effort (clamped to 0.8-1.2; 1.0 without one).

    runs: dict-likes with start_local, distance_m, duration_s, avg_hr.
    """
    today = today or _date.today()
    best, best_v = None, None
    for r in runs or []:
        d, t = num(r["distance_m"]), num(r["duration_s"])
        if not d or not t or d < FACTOR_MIN_M or not _within(r["start_local"], today, FACTOR_DAYS):
            continue
        v = vdot(d, t)
        if v is not None and (best_v is None or v > best_v):
            best, best_v = r, v
    if best is None:
        return 1.0
    eff = effective_vo2max(best["distance_m"], best["duration_s"], best["avg_hr"], max_hr)
    if not eff:
        return 1.0
    return min(FACTOR_RANGE[1], max(FACTOR_RANGE[0], best_v / eff))


def endurance_gap(pb_5k, pb_half):
    """Half PB minus the half the 5k PB predicts, in seconds; None when unknown."""
    p5, ph = num(pb_5k), num(pb_half)
    if not p5 or not ph:
        return None
    pred = predict_time(vdot(5000, p5), HALF_M)
    return None if pred is None else ph - pred


def gap_tone(gap):
    if gap is None:
        return "flat"
    return "good" if gap <= GAP_GOOD_S else "warn" if gap <= GAP_WARN_S else "bad"


def long_run_readiness(vdot_value, weekly_km, longest_km):
    """0-100: 2/3 weekly volume against a VDOT-based target, 1/3 longest run against 18 km."""
    v, w, lg = num(vdot_value), num(weekly_km), num(longest_km)
    if not v or v <= 0 or w is None or lg is None:
        return None
    target = HALF_WEEKLY_FACTOR * v ** 1.135
    return 100.0 * (2.0 / 3.0 * min(1.0, w / target) + 1.0 / 3.0 * min(1.0, lg / HALF_LONG_KM))


def readiness_tone(v):
    if v is None:
        return "flat"
    return "good" if v >= READY_GOOD else "warn" if v >= READY_WARN else "bad"


def volume(runs, today=None):
    """(average weekly km over 56 days, longest run km over 42 days)."""
    today = today or _date.today()
    tot = sum(num(r["distance_m"]) or 0.0 for r in runs if _within(r["start_local"], today, VOLUME_DAYS - 1))
    longest = max([num(r["distance_m"]) or 0.0 for r in runs if _within(r["start_local"], today, LONGEST_DAYS - 1)],
                  default=0.0)
    return tot / 1000.0 / (VOLUME_DAYS / 7.0), longest / 1000.0


# ---------------------------------------------------------------- best efforts

def _clean(samples):
    """Monotone (t, dist) list. Points where time or distance goes backwards are dropped; a step faster than
    MIN_PACE_S_PER_KM (a GPS jump) is cut down to that speed, so the jump does not leak into later windows."""
    out, offset = [], 0.0
    vmax = 1000.0 / MIN_PACE_S_PER_KM
    for s in samples or []:
        t, d = num(s[0]), num(s[1])
        if t is None or d is None:
            continue
        d -= offset
        if out:
            if t <= out[-1][0] or d < out[-1][1]:
                continue
            step, cap = d - out[-1][1], vmax * (t - out[-1][0])
            if step > cap:
                offset += step - cap
                d -= step - cap
        out.append((t, d))
    return out


def best_efforts(samples):
    """{distance key: fastest seconds} from (t, dist, hr) samples (cumulative t in s, dist in m).

    Sliding window with linear interpolation. Windows faster than MIN_PACE_S_PER_KM are skipped.
    """
    pts = _clean(samples)
    out = {}
    if len(pts) < 2:
        return out
    for key, dist in DISTANCES.items():
        best, i = None, 0
        for j in range(1, len(pts)):
            target = pts[j][1] - dist
            if target < pts[0][1]:
                continue
            while i + 1 < j and pts[i + 1][1] <= target:
                i += 1
            (t0, d0), (t1, d1) = pts[i], pts[i + 1]
            ts = t0 + (target - d0) / (d1 - d0) * (t1 - t0) if d1 > d0 else t0
            secs = pts[j][0] - ts
            if secs <= 0 or secs / (dist / 1000.0) < MIN_PACE_S_PER_KM:
                continue
            if best is None or secs < best:
                best = secs
        if best is not None:
            out[key] = best
    return out


def best_efforts_from_laps(laps):
    """{distance key: seconds}: fastest run of consecutive laps that covers the distance, time scaled to it."""
    ls = []
    for lap in laps or []:
        d, t = num(lap["distance_m"]), num(lap["duration_s"])
        if d and t and d > 0 and t > 0:
            ls.append((d, t))
    out = {}
    for key, dist in DISTANCES.items():
        best = None
        for i in range(len(ls)):
            d = t = 0.0
            for k in range(i, len(ls)):
                d += ls[k][0]
                t += ls[k][1]
                if d >= dist:
                    secs = t * dist / d
                    if secs / (dist / 1000.0) >= MIN_PACE_S_PER_KM and (best is None or secs < best):
                        best = secs
                    break
        if best is not None:
            out[key] = best
    return out


def pace_curve(efforts, unit="mi"):
    """[(key, pace seconds per km or mile)] for the fastest effort of each distance.

    efforts: (distance key, seconds) pairs.
    """
    best = {}
    for k, s in efforts:
        s = num(s)
        if k in DISTANCES and s and (k not in best or s < best[k]):
            best[k] = s
    div = M_PER_MILE if unit == "mi" else 1000.0
    return [(k, best[k] / (DISTANCES[k] / div)) for k in DISTANCES if k in best]


# ---------------------------------------------------------------- SVG (inline, CSS tokens)

def svg_zone_bars(weeks, width=640, height=200):
    """Stacked weekly time-in-zone bars. weeks: [(week_start, [secs Z1..Z5])]."""
    head = '<figure class="chart card"><figcaption>Weekly time in HR zones</figcaption>'
    peak = max((sum(z) for _, z in weeks), default=0)
    if peak <= 0:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    ml, mr, mt, mb = 40, 10, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    n = len(weeks)
    bw = iw / n
    p = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Weekly time in HR zones">']
    for frac in (0, 0.5, 1):
        yy = mt + ih * (1 - frac)
        p.append(f'<line x1="{ml}" x2="{width - mr}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        p.append(f'<text x="{ml - 4}" y="{yy + 3:.1f}" class="ax" text-anchor="end">{peak * frac / 3600:.1f}h</text>')
    for i, (w, z) in enumerate(weeks):
        y = mt + ih
        for zi, secs in enumerate(z):
            h = ih * secs / peak
            if h <= 0:
                continue
            y -= h
            p.append(f'<rect x="{ml + i * bw + 1:.1f}" y="{y:.1f}" width="{max(bw - 2, 1):.1f}" height="{h:.1f}" '
                     f'class="z{zi + 1}"><title>{escape(w)} Z{zi + 1}: {fmt_dur(secs)}</title></rect>')
    p.append(f'<text x="{ml}" y="{height - 6}" class="ax">{escape(weeks[0][0])}</text>')
    p.append(f'<text x="{width - mr}" y="{height - 6}" class="ax" text-anchor="end">{escape(weeks[-1][0])}</text>')
    p.append("</svg>")
    return head + "".join(p) + "</figure>"


def svg_zone_strip(zone_secs, width=640, height=34):
    """One stacked horizontal bar for a single run; '' without time in zones."""
    z = [num(x) or 0.0 for x in (zone_secs or [])]
    tot = sum(z)
    if len(z) != 5 or tot <= 0:
        return ""
    p = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Time in HR zones" class="strip">']
    x = 0.0
    for i, s in enumerate(z):
        w = width * s / tot
        if w <= 0:
            continue
        p.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="{height}" class="z{i + 1}">'
                 f'<title>Z{i + 1}: {fmt_dur(s)} ({s / tot * 100:.0f}%)</title></rect>')
        if w > 40:
            p.append(f'<text x="{x + w / 2:.1f}" y="{height / 2 + 4:.1f}" class="zl" text-anchor="middle">Z{i + 1}</text>')
        x += w
    p.append("</svg>")
    return "".join(p)


def svg_pace_curve(recent, alltime, unit="mi", width=640, height=200):
    """Pace against distance, last 90 days vs all time. Both: [(distance key, pace s/unit)]."""
    title = f"Pace by distance (per {unit}), last {CURVE_DAYS} days vs all time"
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    vals = [v for _, v in list(recent) + list(alltime)]
    if not vals:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 5, hi + 5
    pad = (hi - lo) * 0.1
    lo, hi = lo - pad, hi + pad
    ml, mr, mt, mb = 48, 14, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    keys = list(DISTANCES)

    def x(k):
        return ml + iw * keys.index(k) / (len(keys) - 1)

    def y(v):   # faster (smaller) at the top
        return mt + ih * (v - lo) / (hi - lo)

    p = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        p.append(f'<line x1="{ml}" x2="{width - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        p.append(f'<text x="{ml - 4}" y="{y(v) + 3:.1f}" class="ax" text-anchor="end">{fmt_dur(v)}</text>')
    for k in keys:
        p.append(f'<text x="{x(k):.1f}" y="{height - 6}" class="ax" text-anchor="middle">{escape(DIST_LABELS[k])}</text>')
    for series, cls in ((alltime, "atl"), (recent, "line")):
        pts = [(x(k), y(v)) for k, v in series]
        if len(pts) > 1:
            p.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" class="{cls}" fill="none"/>')
        for a, b in pts:
            p.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3" class="dot"/>')
    p.append("</svg>")
    legend = ('<p class="legend"><span><b style="color:var(--acc)">—</b> last 90 days</span>'
              '<span><b style="color:var(--warn)">- -</b> all time</span></p>')
    return head + "".join(p) + legend + "</figure>"


# ---------------------------------------------------------------- page loaders (sqlite3 connection in, plain dicts out)

ZONE_SOURCES = ("maxhr", "garmin")
SETTING_MAX_HR = "max_hr"
SETTING_ZONE_SOURCE = "zone_source"


def _setting(con, key):
    r = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else None


def settings(con, today=None):
    """{'max_hr_setting', 'auto_max_hr', 'max_hr', 'zone_source'}; corrupt stored values fall back to defaults."""
    today = today or _date.today()
    acts = con.execute("SELECT start_local, max_hr FROM activities WHERE start_local >= ?",
                       ((today - timedelta(days=MAX_HR_DAYS + 1)).isoformat(),)).fetchall()
    raw = _setting(con, SETTING_MAX_HR)
    src = _setting(con, SETTING_ZONE_SOURCE)
    return {"max_hr_setting": parse_max_hr(raw), "auto_max_hr": default_max_hr(acts, today),
            "max_hr": effective_max_hr(raw, acts, today),
            "zone_source": src if src in ZONE_SOURCES else "maxhr"}


def _run_zones(source, max_hr, hist, gz):
    """([secs Z1..Z5], (z2_low, z3_low) or None) for one run from the stored tables."""
    if source == "garmin":
        secs, lows = zones_from_garmin(gz)
        return secs, ((lows.get(2), lows.get(3)) if secs else None)
    if not max_hr or not hist:
        return [], None
    b = zone_bounds(max_hr)
    return zones_from_hist(hist, max_hr), (b[1][0], b[2][0])


def _mean_by_date(points):
    by = {}
    for d, v in points:
        by.setdefault(d, []).append(v)
    return [(d, sum(v) / len(v)) for d, v in sorted(by.items())]


def _runs(con, today, days):
    return [dict(r) for r in con.execute(
        "SELECT a.id, a.start_local, a.distance_m, a.duration_s, a.avg_hr, a.max_hr, "
        "COALESCE(a.cadence, (SELECT SUM(l.cadence*l.duration_s)/SUM(l.duration_s) FROM laps l "
        "WHERE l.activity_id=a.id AND l.cadence > 0)) AS cadence FROM activities a "
        "WHERE a.type LIKE '%running%' AND a.start_local >= ? ORDER BY a.start_local",
        ((today - timedelta(days=days)).isoformat(),))]


def load(con, today=None, unit="mi"):
    """Everything the Trends and PBs pages need. Missing data gives None/[] values, never an exception."""
    today = today or _date.today()
    st = settings(con, today)
    max_hr, source = st["max_hr"], st["zone_source"]
    runs = _runs(con, today, FACTOR_DAYS)
    zone_since = (today - timedelta(days=ZONE_WEEKS * 7)).isoformat()
    hist, gz = {}, {}
    for r in con.execute("SELECT h.activity_id, h.bpm, h.seconds FROM activity_hr h JOIN activities a "
                         "ON a.id=h.activity_id WHERE a.start_local >= ?", (zone_since,)):
        hist.setdefault(r["activity_id"], []).append((r[1], r[2]))
    for r in con.execute("SELECT z.activity_id, z.zone, z.seconds, z.low_bpm FROM activity_zones z JOIN activities a "
                         "ON a.id=z.activity_id WHERE a.start_local >= ?", (zone_since,)):
        gz.setdefault(r["activity_id"], []).append((r[1], r[2], r[3]))

    items, ef_pts, cad_pts, recent_zones = [], [], [], [0.0] * 5
    for r in runs:
        if r["start_local"] < zone_since:
            continue
        secs, bnd = _run_zones(source, max_hr, hist.get(r["id"]), gz.get(r["id"]))
        if not secs:
            continue
        items.append((r["start_local"], secs))
        if _within(r["start_local"], today, EASY_DAYS):
            recent_zones = [a + b for a, b in zip(recent_zones, secs)]
        if bnd and _within(r["start_local"], today, EF_DAYS) and is_easy(r["avg_hr"], bnd[0], bnd[1]):
            ef = efficiency(r["distance_m"], r["duration_s"], r["avg_hr"])
            if ef is not None:
                ef_pts.append((r["start_local"][:10], ef))
            cad = num(r.get("cadence"))
            if cad is not None and CADENCE_RANGE[0] <= cad <= CADENCE_RANGE[1]:
                cad_pts.append((r["start_local"][:10], cad))
    ef_pts = _mean_by_date(ef_pts)
    cad_pts = _mean_by_date(cad_pts)
    share = share_easy(recent_zones)

    factor = correction_factor(runs, max_hr, today) if max_hr else 1.0
    vo2_pts = []
    for r in runs:
        if max_hr and _within(r["start_local"], today, VO2_DAYS):
            v = effective_vo2max(r["distance_m"], r["duration_s"], r["avg_hr"], max_hr)
            if v is not None:
                vo2_pts.append((r["start_local"][:10], v * factor))
    vo2_pts = _mean_by_date(vo2_pts)
    cur30 = [v for d, v in vo2_pts if _within(d, today, VO2_CURRENT_DAYS)]
    garmin_vo2 = con.execute("SELECT vo2max, date FROM daily WHERE vo2max IS NOT NULL ORDER BY date DESC LIMIT 1").fetchone()

    eff = [(r["distance"], r["seconds"], r["start_local"]) for r in con.execute(
        "SELECT e.distance, e.seconds, a.start_local FROM best_efforts e JOIN activities a ON a.id=e.activity_id")]
    all_curve = pace_curve([(k, s) for k, s, _ in eff], unit)
    rec_curve = pace_curve([(k, s) for k, s, d in eff if _within(d, today, CURVE_DAYS)], unit)
    e5 = [s for k, s, d in eff if k == "5k" and _within(d, today, PRED_DAYS)]
    best5 = min(e5) if e5 else None

    pb = {r["distance"]: r["seconds"] for r in con.execute("SELECT distance, seconds FROM pbs")}
    v = vdot(5000, best5) if best5 else (vdot(5000, pb["5k"]) if pb.get("5k") else None)
    weekly_km, longest_km = volume(runs, today)
    gap = endurance_gap(pb.get("5k"), pb.get("half"))
    ready = long_run_readiness(v, weekly_km, longest_km)
    return {
        "settings": st, "need_max_hr": max_hr is None, "zone_source": source,
        "weekly_zones": weekly_zone_secs(items, today), "easy_share": share, "easy_tone": easy_tone(share),
        "ef_points": ef_pts, "cadence_points": cad_pts, "ef_trend": ef_trend(ef_pts, today),
        "vo2_points": vo2_pts, "vo2_current": sum(cur30) / len(cur30) if cur30 else None, "vo2_factor": factor,
        "garmin_vo2": garmin_vo2,
        "curve_recent": rec_curve, "curve_all": all_curve,
        "best5k": best5, "predictions": predictions(best5) if best5 else None,
        "gap": gap, "gap_tone": gap_tone(gap), "vdot": v,
        "ready": ready, "ready_tone": readiness_tone(ready), "weekly_km": weekly_km, "longest_km": longest_km,
    }


def load_run(con, a, laps, today=None):
    """Extras for one run page: zone strip, decoupling, effective VO2max, best efforts."""
    today = today or _date.today()
    st = settings(con, today)
    max_hr, aid = st["max_hr"], a["id"]
    hist = [(r[0], r[1]) for r in con.execute("SELECT bpm, seconds FROM activity_hr WHERE activity_id=?", (aid,))]
    gz = [(r[0], r[1], r[2]) for r in con.execute(
        "SELECT zone, seconds, low_bpm FROM activity_zones WHERE activity_id=?", (aid,))]
    secs, _ = _run_zones(st["zone_source"], max_hr, hist, gz)
    dec = decoupling(laps)
    eff = None
    if max_hr:
        eff = effective_vo2max(a["distance_m"], a["duration_s"], a["avg_hr"], max_hr)
        if eff is not None:
            eff *= correction_factor(_runs(con, today, FACTOR_DAYS), max_hr, today)
    gv = None
    d = (a["start_local"] or "")[:10]
    if d:
        gv = con.execute("SELECT vo2max, date FROM daily WHERE vo2max IS NOT NULL AND date <= ? "
                         "ORDER BY date DESC LIMIT 1", (d,)).fetchone()
    best = [(r["distance"], r["seconds"], r["source"]) for r in con.execute(
        "SELECT distance, seconds, source FROM best_efforts WHERE activity_id=?", (aid,))]
    best.sort(key=lambda x: list(DISTANCES).index(x[0]) if x[0] in DISTANCES else 99)
    return {"need_max_hr": max_hr is None, "zone_secs": secs, "zone_strip": svg_zone_strip(secs),
            "share_easy": share_easy(secs), "decoupling": dec, "decoupling_tone": decoupling_tone(dec),
            "eff_vo2": eff, "garmin_vo2": gv, "efforts": best}
