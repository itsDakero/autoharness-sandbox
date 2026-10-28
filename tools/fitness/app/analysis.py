"""Training-load and recovery maths (stdlib only).

Load: daily load, fitness/fatigue/form, ramp, ACWR, monotony, strain.
Recovery: normal-range bands, recovery score, sleep debt and consistency, illness warning.
"""
import json
from datetime import date as _date, datetime, timedelta, timezone
from html import escape
from statistics import mean, pstdev

from .logic import num, week_start

CTL_DAYS = 42
ATL_DAYS = 7
ACWR_SHORT = 7
ACWR_LONG = 28
RAMP_WARN = 5.0
MONOTONY_WARN = 2.0
ACWR_GREEN = (0.8, 1.3)
ACWR_AMBER_MAX = 1.5
MIN_SCALE_PAIRS = 3
WINDOW_DAYS = 365
CHART_DAYS = 180
# Form zones on TSB: fresh > +5, neutral -10..+5, optimal -30..<-10, high risk < -30.
FORM_FRESH_MIN = 5.0
FORM_NEUTRAL_MIN = -10.0
FORM_OPTIMAL_MIN = -30.0

# Recovery constants.
BAND_DAYS = 60            # band = mean +- SD of the 60 days before the day
MIN_BAND_VALUES = 14
ROLL_DAYS = 7
ROLL_MIN = 3
W_HRV, W_RHR, W_SLEEP = 0.4, 0.3, 0.3
ADJ_FLAG = 10             # points off per sore_legs / stressed / slept_badly
ILL_CAP = 33
GREEN_MIN = 67
YELLOW_MIN = 34
SLEEP_NEED_DEFAULT_H = 8.0
SLEEP_NEED_RANGE_H = (4.0, 12.0)
DEBT_DAYS = 7
DEBT_MIN_NIGHTS = 4
DEBT_GOOD_H, DEBT_WARN_H = 2.0, 5.0
CONSISTENCY_NIGHTS = 14
CONSISTENCY_MIN_NIGHTS = 5
CONSISTENCY_GOOD_MIN, CONSISTENCY_WARN_MIN = 30.0, 60.0
HIGH_LOAD_MIN_INDEX = 28
HIGH_LOAD_RATIO = 1.5
RHR_MARGIN = 3.0          # bpm above the top of the RHR band
ACC_MIN_CHECKINS = 60
ACC_LOOKAHEAD_DAYS = 3
HISTORY_DAYS = 180
STRAIN_CHART_DAYS = 90

# volume
HEATMAP_DAYS = 371        # 53 weeks
SUMMARY_WEEKS = 12
LONG_SHARE_WARN = 0.35
STREAK_MIN_RUNS = 2
LONG_SHARE_MIN_RUNS = 2


def fiit_scale(pairs):
    """pairs: [(srpe, garmin_load)]. Scale = sum(load)/sum(srpe); 1.0 with too few pairs."""
    pairs = [(num(s), num(l)) for s, l in pairs]
    pairs = [(s, l) for s, l in pairs if s is not None and l is not None]
    if len(pairs) < MIN_SCALE_PAIRS:
        return 1.0
    ssum = sum(s for s, _ in pairs)
    if ssum <= 0:
        return 1.0
    return sum(l for _, l in pairs) / ssum


def _day(s):
    try:
        return _date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def daily_load(activities, fiit, scale, start, end):
    """[(date, load)] one per day start..end inclusive (dates are date objects).

    activities: dicts with start_local, training_load. fiit: dicts with date, srpe, act_load
    (the matched activity's training_load, None when unmatched or the activity has no load).
    """
    n = (end - start).days + 1
    if n <= 0:
        return []
    totals = [0.0] * n
    for a in activities:
        d = _day(a.get("start_local"))
        if d is None or not start <= d <= end:
            continue
        totals[(d - start).days] += max(num(a.get("training_load")) or 0.0, 0.0)
    for f in fiit:
        d = _day(f.get("date"))
        if d is None or not start <= d <= end:
            continue
        if (num(f.get("act_load")) or 0.0) > 0:
            continue   # counted once, as the Garmin load
        totals[(d - start).days] += (num(f.get("srpe")) or 0.0) * scale
    return [(start + timedelta(days=i), totals[i]) for i in range(n)]


def ewma(loads, n):
    """v_t = v_(t-1) + (load_t - v_(t-1))/n, seeded at 0."""
    out, v = [], 0.0
    for x in loads:
        v += (x - v) / n
        out.append(v)
    return out


def form_zone(tsb):
    """(label, tone). Tone '' = neutral grey chip."""
    if tsb > FORM_FRESH_MIN:
        return ("Fresh", "")
    if tsb >= FORM_NEUTRAL_MIN:
        return ("Neutral", "")
    if tsb >= FORM_OPTIMAL_MIN:
        return ("Optimal", "good")
    return ("High risk", "bad")


def zone_class(tsb):
    return {"Fresh": "fresh", "Neutral": "neutral", "Optimal": "optimal", "High risk": "high"}[form_zone(tsb)[0]]


def tsb_series(ctl, atl):
    """TSB of day i = CTL - ATL of day i-1 (0 on the first day)."""
    return [0.0] + [c - a for c, a in zip(ctl[:-1], atl[:-1])]


def ramp(ctl, days=7):
    """CTL today minus CTL `days` ago; None without enough history."""
    return ctl[-1] - ctl[-1 - days] if len(ctl) > days else None


def acwr(loads):
    """Mean of last 7 / mean of last 28 days; None under 28 days or a zero 28-day mean."""
    if len(loads) < ACWR_LONG:
        return None
    long_m = mean(loads[-ACWR_LONG:])
    if long_m <= 0:
        return None
    return mean(loads[-ACWR_SHORT:]) / long_m


def acwr_tone(v):
    if v is None:
        return ""
    if ACWR_GREEN[0] <= v <= ACWR_GREEN[1]:
        return "good"
    if v < ACWR_GREEN[0]:
        return ""
    return "warn" if v <= ACWR_AMBER_MAX else "bad"


def monotony(loads, days=7):
    """mean / pstdev of the last `days` loads; None when flat or too short."""
    if len(loads) < days:
        return None
    w = loads[-days:]
    sd = pstdev(w)
    if sd <= 1e-9:
        return None
    return mean(w) / sd


def strain(loads, mono, days=7):
    return None if mono is None else sum(loads[-days:]) * mono


def summary(series, scale, scale_pairs, first_data, today):
    """series: [{date, load, ctl, atl, tsb}] ascending to today."""
    s = {"ctl": None, "atl": None, "tsb": None, "zone": None, "ramp": None, "ramp_tone": "",
         "acwr": None, "acwr_tone": "", "monotony": None, "monotony_tone": "", "strain": None,
         "scale": scale, "scale_pairs": scale_pairs,
         "days_of_data": 0 if first_data is None else (today - first_data).days + 1}
    if not series or first_data is None:
        return s
    loads = [p["load"] for p in series]
    s["ctl"], s["atl"], s["tsb"] = series[-1]["ctl"], series[-1]["atl"], series[-1]["tsb"]
    s["zone"] = form_zone(s["tsb"])
    ctl = [p["ctl"] for p in series]
    s["ramp"] = ramp(ctl)
    s["ramp_tone"] = "warn" if s["ramp"] is not None and s["ramp"] > RAMP_WARN else ""
    s["acwr"] = acwr(loads)
    s["acwr_tone"] = acwr_tone(s["acwr"])
    s["monotony"] = monotony(loads)
    s["monotony_tone"] = "warn" if s["monotony"] is not None and s["monotony"] > MONOTONY_WARN else ""
    s["strain"] = strain(loads, s["monotony"])
    return s


def compute(activities, fiit, today):
    """activities: dicts (start_local, training_load). fiit: dicts (date, srpe, act_load, act_id).

    Returns (series, summary). series is empty when there is no data at all.
    """
    dates = [d for d in (_day(a.get("start_local")) for a in activities) if d]
    dates += [d for d in (_day(f.get("date")) for f in fiit) if d]
    dates = [d for d in dates if d <= today]
    if not dates:
        return [], summary([], 1.0, 0, None, today)
    first = min(dates)
    pairs = [(f.get("srpe"), f.get("act_load")) for f in fiit
             if f.get("act_id") is not None and (num(f.get("act_load")) or 0) > 0]
    pairs = [(s, l) for s, l in pairs if num(s) is not None]
    scale = fiit_scale(pairs)
    n_pairs = len(pairs)
    start = max(first, today - timedelta(days=WINDOW_DAYS))
    days = daily_load(activities, fiit, scale, start, today)
    loads = [x for _, x in days]
    ctl, atl = ewma(loads, CTL_DAYS), ewma(loads, ATL_DAYS)
    tsb = tsb_series(ctl, atl)
    series = [{"date": d.isoformat(), "load": l, "ctl": c, "atl": a, "tsb": t}
              for (d, l), c, a, t in zip(days, ctl, atl, tsb)]
    return series, summary(series, scale, n_pairs, first, today)


def svg_load_chart(series, width=640, height=220):
    """CTL/ATL lines plus TSB bars (own symmetric y-scale) in a figure.chart.card."""
    title = "Training load: fitness, fatigue and form"
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    if not series or len(series) < 2:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    series = series[-CHART_DAYS:]
    n = len(series)
    ml, mr, mt, mb = 44, 10, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    top = max(max(p["ctl"], p["atl"]) for p in series) or 1.0
    top *= 1.08
    tmax = max(abs(p["tsb"]) for p in series) or 1.0
    tmax *= 1.08
    zero_y = mt + ih / 2

    def x(i):
        return ml + iw * i / (n - 1)

    def y(v):
        return mt + ih * (1 - v / top)

    def ty(v):
        return zero_y - (ih / 2) * v / tmax

    last = series[-1]
    head = (f'<figure class="chart card"><figcaption>{escape(title)}'
            f'<span class="latest">{last["ctl"]:.0f} / {last["atl"]:.0f}</span></figcaption>')
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for frac in (0, 0.5, 1):
        yy = mt + ih * (1 - frac)
        parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{yy:.1f}" y2="{yy:.1f}" class="grid"/>')
        parts.append(f'<text x="{ml - 4}" y="{yy + 3:.1f}" class="ax" text-anchor="end">{top * frac:.3g}</text>')
    parts.append(f'<text x="{ml}" y="{height - 6}" class="ax">{escape(series[0]["date"])}</text>')
    parts.append(f'<text x="{width - mr}" y="{height - 6}" class="ax" text-anchor="end">{escape(series[-1]["date"])}</text>')
    bw = max(iw / n * 0.8, 0.8)
    for i, p in enumerate(series):
        yt = ty(p["tsb"])
        top_y, h = min(yt, zero_y), abs(yt - zero_y)
        zl = form_zone(p["tsb"])[0]
        parts.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{top_y:.1f}" width="{bw:.1f}" height="{max(h, 0.5):.1f}" '
                     f'class="tsb {zone_class(p["tsb"])}"><title>{escape(p["date"])}: form {p["tsb"]:+.1f} ({escape(zl)})</title></rect>')
    parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{zero_y:.1f}" y2="{zero_y:.1f}" class="grid"/>')
    for cls, key in (("ctl", "ctl"), ("atl", "atl")):
        pts = " ".join(f"{x(i):.1f},{y(p[key]):.1f}" for i, p in enumerate(series))
        parts.append(f'<polyline points="{pts}" class="{cls}" fill="none"/>')
    parts.append("</svg>")
    return head + "".join(parts) + "</figure>"


# ---------------------------------------------------------------- recovery

def _iso(d):
    return d.isoformat()


def band(values, d):
    """Normal range for day d: mean +- pstdev of the BAND_DAYS days before d (d excluded).

    values: {iso date: float}. None under MIN_BAND_VALUES values or a flat (SD 0) history.
    """
    vals = [values[k] for k in (_iso(d - timedelta(days=i)) for i in range(1, BAND_DAYS + 1)) if k in values]
    if len(vals) < MIN_BAND_VALUES:
        return None
    m, sd = mean(vals), pstdev(vals)
    if sd <= 1e-9:
        return None
    return {"mean": m, "sd": sd, "lo": m - sd, "hi": m + sd, "n": len(vals)}


def band_count(values, d):
    return sum(1 for i in range(1, BAND_DAYS + 1) if _iso(d - timedelta(days=i)) in values)


def band_pos(v, b):
    """'below' / 'in range' / 'above'; None when the value or the band is missing."""
    v = num(v)
    if v is None or b is None:
        return None
    if v < b["lo"]:
        return "below"
    if v > b["hi"]:
        return "above"
    return "in range"


def band_tone(kind, pos):
    """Chip tone. kind 'hrv': below = warn, above = good. kind 'rhr': above = warn, below = good."""
    if pos == "in range":
        return "good"
    if pos is None:
        return ""
    bad_side = "below" if kind == "hrv" else "above"
    return "warn" if pos == bad_side else "good"


def roll_avg(values, d):
    """Mean of the values present in d-6..d; None under ROLL_MIN of them."""
    vals = [values[k] for k in (_iso(d - timedelta(days=i)) for i in range(ROLL_DAYS)) if k in values]
    return mean(vals) if len(vals) >= ROLL_MIN else None


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def score_band(score):
    """(label, tone) for a recovery score; ('-', '') for None."""
    if score is None:
        return ("-", "")
    if score >= GREEN_MIN:
        return ("Green", "good")
    if score >= YELLOW_MIN:
        return ("Yellow", "warn")
    return ("Red", "bad")


def recovery_score(hrv, rhr, sleep_s, hrv_band, rhr_band, need_s, checkin=None):
    """Recovery 0-100 from HRV z, RHR z (inverted) and sleep vs need; None when no part exists.

    Missing parts drop out and the remaining weights are renormalised.
    """
    checkin = checkin or {}
    parts = [{"key": "hrv", "label": "HRV", "value": num(hrv), "z": None, "score": None, "weight": W_HRV},
             {"key": "rhr", "label": "Resting HR", "value": num(rhr), "z": None, "score": None, "weight": W_RHR},
             {"key": "sleep", "label": "Sleep", "value": num(sleep_s), "z": None, "score": None, "weight": W_SLEEP}]
    h, r, sl = parts
    if h["value"] is not None and hrv_band:
        h["z"] = (h["value"] - hrv_band["mean"]) / hrv_band["sd"]
        h["score"] = _clamp(50 + 25 * h["z"])
    if r["value"] is not None and rhr_band:
        r["z"] = (r["value"] - rhr_band["mean"]) / rhr_band["sd"]
        r["score"] = _clamp(50 - 25 * r["z"])
    if sl["value"] is not None and sl["value"] > 0 and need_s and need_s > 0:
        sl["score"] = _clamp(100 * sl["value"] / need_s)
    have = [p for p in parts if p["score"] is not None]
    wsum = sum(p["weight"] for p in have)
    for p in parts:
        p["weight"] = p["weight"] / wsum if p["score"] is not None and wsum else 0.0
    if not have:
        return None
    base = sum(p["score"] * p["weight"] for p in have)
    total = base
    adjust = []
    for key, label in (("sore_legs", "sore legs"), ("stressed", "stressed"), ("slept_badly", "slept badly")):
        if checkin.get(key):
            total -= ADJ_FLAG
            adjust.append((label, -ADJ_FLAG))
    capped = bool(checkin.get("ill_neck") or checkin.get("ill_chest"))
    if capped:
        total = min(total, ILL_CAP)
    score = int(_clamp(total) + 0.5)
    label, tone = score_band(score)
    return {"score": score, "base": base, "parts": parts, "adjust": adjust, "capped": capped,
            "label": label, "tone": tone}


def sleep_debt(sleep_by_date, need_s, today):
    """Sum of (need - actual) over the nights present in today-6..today (floored at 0); None under 4 nights."""
    nights = [sleep_by_date[k] for k in (_iso(today - timedelta(days=i)) for i in range(DEBT_DAYS))
              if sleep_by_date.get(k)]
    if len(nights) < DEBT_MIN_NIGHTS:
        return None
    return max(sum(need_s - s for s in nights), 0.0)


def debt_tone(seconds):
    if seconds is None:
        return ""
    h = seconds / 3600
    return "good" if h < DEBT_GOOD_H else ("warn" if h <= DEBT_WARN_H else "bad")


def parse_sleep_times(text):
    """(bedtime, wake) from raw sleep JSON; None when missing, invalid or null.

    Timestamps are epoch ms already shifted to local time, so read them as UTC. Bedtime is minutes
    from noon (so 23:30 and 00:30 are 60 minutes apart), wake is minutes from midnight.
    """
    try:
        d = json.loads(text) if isinstance(text, (str, bytes)) else None
        dto = d.get("dailySleepDTO") if isinstance(d, dict) else None
        if not isinstance(dto, dict):
            return None
        out = []
        for k in ("sleepStartTimestampLocal", "sleepEndTimestampLocal"):
            ms = num(dto.get(k))
            if ms is None:
                return None
            t = datetime.fromtimestamp(ms / 1000, timezone.utc)
            out.append(t.hour * 60 + t.minute)
    except (ValueError, TypeError, OverflowError, OSError, AttributeError):
        return None
    return ((out[0] - 720) % 1440, out[1])


def _hhmm(minutes):
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def consistency(raw_sleep, today):
    """SD of bedtime and wake time over the last 14 nights. raw_sleep: {iso date: json text}.

    None under 5 valid nights. Returns minutes SD and mean times as HH:MM, with a tone on the larger SD.
    """
    keys = {_iso(today - timedelta(days=i)) for i in range(CONSISTENCY_NIGHTS)}
    pairs = [t for t in (parse_sleep_times(v) for k, v in raw_sleep.items() if k in keys) if t]
    if len(pairs) < CONSISTENCY_MIN_NIGHTS:
        return None
    beds, wakes = [p[0] for p in pairs], [p[1] for p in pairs]
    bsd, wsd = pstdev(beds), pstdev(wakes)
    worst = max(bsd, wsd)
    tone = "good" if worst <= CONSISTENCY_GOOD_MIN else ("warn" if worst <= CONSISTENCY_WARN_MIN else "bad")
    return {"bed_sd": bsd, "wake_sd": wsd, "bed_mean": _hhmm(mean(beds) + 720), "wake_mean": _hhmm(mean(wakes)),
            "n": len(pairs), "tone": tone}


def high_load_days(load_series):
    """Dates with load > 0 and >= 1.5 x the previous day's CTL, from day index 28 on."""
    out = set()
    for i, p in enumerate(load_series or []):
        if i < HIGH_LOAD_MIN_INDEX or i == 0:
            continue
        if p["load"] > 0 and p["load"] >= HIGH_LOAD_RATIO * load_series[i - 1]["ctl"]:
            out.add(p["date"])
    return out


def illness_signals(hrv, rhr, hrv_band, rhr_band):
    """(rhr_high, hrv_low); missing data never counts as a signal."""
    hrv, rhr = num(hrv), num(rhr)
    rhr_high = bool(rhr is not None and rhr_band and rhr >= rhr_band["mean"] + rhr_band["sd"] + RHR_MARGIN)
    hrv_low = bool(hrv is not None and hrv_band and hrv < hrv_band["mean"] - hrv_band["sd"])
    return rhr_high, hrv_low


def parse_need(value):
    """Sleep need in hours from a stored or posted value; None unless a number in 4..12."""
    v = num(value.strip() if isinstance(value, str) else value)
    if v is None or not SLEEP_NEED_RANGE_H[0] <= v <= SLEEP_NEED_RANGE_H[1]:
        return None
    return v


def recovery(daily, checkins, raw_sleep, need_h, load_series, today):
    """Everything the Today and Trends pages need for recovery.

    daily: dicts (date, hrv_avg, rhr, sleep_s). checkins: dicts. raw_sleep: {iso date: json text}.
    load_series: from compute(). today: date. Never raises on missing or odd data.
    """
    need_h = parse_need(need_h) or SLEEP_NEED_DEFAULT_H
    need_s = need_h * 3600
    hrv, rhr, slp = {}, {}, {}
    for r in daily:
        k = r["date"] or ""
        for store, col in ((hrv, "hrv_avg"), (rhr, "rhr"), (slp, "sleep_s")):
            v = num(r[col])
            if v is not None:
                store[k] = v
    ck = {c["date"]: dict(c) for c in checkins}
    high = high_load_days(load_series)

    # One info record per day: HISTORY_DAYS + 1 days so the first warning can look at the day before.
    infos = []
    for i in range(HISTORY_DAYS, -1, -1):
        d = today - timedelta(days=i)
        k = _iso(d)
        hb, rb = band(hrv, d), band(rhr, d)
        rh, hl = illness_signals(hrv.get(k), rhr.get(k), hb, rb)
        c = ck.get(k, {})
        rec = recovery_score(hrv.get(k), rhr.get(k), slp.get(k), hb, rb, need_s, c)
        infos.append({"date": k, "d": d, "hb": hb, "rb": rb, "both": rh and hl, "rec": rec, "ck": c,
                      "avg_hrv": roll_avg(hrv, d), "avg_rhr": roll_avg(rhr, d)})
    for i, inf in enumerate(infos):
        prev = infos[i - 1]["both"] if i else False
        inf["warn"] = bool(inf["both"] and (prev or inf["ck"].get("slept_badly") or inf["ck"].get("stressed")))
    infos = infos[1:]
    t = infos[-1]

    def pts(vals, key, bkey):
        return [{"date": i["date"], "v": vals.get(i["date"]), "avg": i[key],
                 "lo": i[bkey]["lo"] if i[bkey] else None, "hi": i[bkey]["hi"] if i[bkey] else None}
                for i in infos]

    score_by_date = {i["date"]: (i["rec"]["score"] if i["rec"] else None) for i in infos}
    flags = {k for k in high if (score_by_date.get(k) is not None and score_by_date[k] < YELLOW_MIN)}
    rec_series = [{"date": i["date"], "score": score_by_date[i["date"]], "flag": i["date"] in flags}
                  for i in infos]

    chips = {}
    for kind, vals, bkey in (("hrv", hrv, "hb"), ("rhr", rhr, "rb")):
        b = t[bkey]
        pos = band_pos(vals.get(t["date"]), b)
        if b is None:
            text, tone = f"learning ({band_count(vals, today)}/{MIN_BAND_VALUES})", ""
        else:
            text, tone = pos, band_tone(kind, pos)
        chips[kind] = {"band": b, "pos": pos, "text": text, "tone": tone}

    cons = consistency(raw_sleep, today)
    debt = sleep_debt(slp, need_s, today)

    # Warning accuracy against "ill" check-ins.
    ill_days = {k for k, c in ck.items() if c.get("ill_neck") or c.get("ill_chest")}
    warn_days = {i["date"] for i in infos if i["warn"]}
    acc = {"enabled": len(ck) >= ACC_MIN_CHECKINS, "n": len(ck), "starts": 0, "hits": 0, "false": 0}
    if acc["enabled"]:
        first = infos[0]["date"]
        for k in sorted(ill_days):
            d = _day(k)
            if d is None or k < first or _iso(d - timedelta(days=1)) in ill_days:
                continue
            acc["starts"] += 1
            if any(_iso(d - timedelta(days=j)) in warn_days for j in (1, 2, 3)):
                acc["hits"] += 1
        cutoff = _iso(today - timedelta(days=ACC_LOOKAHEAD_DAYS))
        for k in warn_days:
            if k > cutoff:
                continue   # the next 3 days are not over yet
            d = _day(k)
            if not any(_iso(d + timedelta(days=j)) in ill_days for j in (1, 2, 3)):
                acc["false"] += 1

    return {
        "need_h": need_h, "score": t["rec"], "red_high_load": t["date"] in flags,
        "high_load_today": t["date"] in high, "chips": chips, "debt": debt, "debt_tone": debt_tone(debt),
        "consistency": cons, "warning": t["warn"], "accuracy": acc,
        "hrv_series": pts(hrv, "avg_hrv", "hb"), "rhr_series": pts(rhr, "avg_rhr", "rb"),
        "rec_series": rec_series, "warn_dates": sorted(warn_days),
    }


# ---------------------------------------------------------------- recovery charts

def svg_band_chart(points, title, unit="", markers=None, width=640, height=180):
    """Normal-range band (shaded), 7-day average (line) and raw values (dots) in a figure.chart.card.

    points: [{date, v, avg, lo, hi}] ascending, one per day; None fields are gaps.
    markers: {date: (colour, tooltip, ill_bool)} as for logic.svg_line_chart.
    """
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    vals = [p[k] for p in points for k in ("v", "avg", "lo", "hi") if p.get(k) is not None]
    if len([p for p in points if p.get("v") is not None or p.get("avg") is not None]) < 2 or not vals:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    last = next((p["avg"] for p in reversed(points) if p.get("avg") is not None), None)
    if last is not None:
        head = (f'<figure class="chart card"><figcaption>{escape(title)}'
                f'<span class="latest">{last:.3g}{escape(unit)}</span></figcaption>')
    lo, hi = min(vals), max(vals)
    if hi == lo:
        lo, hi = lo - 1, hi + 1
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    ml, mr, mt, mb = 44, 10, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    n = len(points)

    def x(i):
        return ml + iw * i / max(n - 1, 1)

    def y(v):
        return mt + ih * (1 - (v - lo) / (hi - lo))

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for frac in (0, 0.5, 1):
        v = lo + (hi - lo) * frac
        parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
        parts.append(f'<text x="{ml - 4}" y="{y(v) + 3:.1f}" class="ax" text-anchor="end">{v:.3g}{escape(unit)}</text>')
    parts.append(f'<text x="{ml}" y="{height - 6}" class="ax">{escape(points[0]["date"])}</text>')
    parts.append(f'<text x="{width - mr}" y="{height - 6}" class="ax" text-anchor="end">{escape(points[-1]["date"])}</text>')

    def segments(ok):
        seg = []
        for i, p in enumerate(points):
            if ok(p):
                seg.append(i)
            else:
                if seg:
                    yield seg
                seg = []
        if seg:
            yield seg

    for seg in segments(lambda p: p.get("lo") is not None and p.get("hi") is not None):
        top = [f"{x(i):.1f},{y(points[i]['hi']):.1f}" for i in seg]
        bot = [f"{x(i):.1f},{y(points[i]['lo']):.1f}" for i in reversed(seg)]
        parts.append(f'<polygon points="{" ".join(top + bot)}" class="band"/>')
    for seg in segments(lambda p: p.get("avg") is not None):
        if len(seg) > 1:
            pl = " ".join(f"{x(i):.1f},{y(points[i]['avg']):.1f}" for i in seg)
            parts.append(f'<polyline points="{pl}" class="ravg" fill="none"/>')
    for i, p in enumerate(points):
        if p.get("v") is not None:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(p["v"]):.1f}" r="1.6" class="dot">'
                         f'<title>{escape(p["date"])}: {p["v"]:.3g}{escape(unit)}</title></circle>')
    idx = {p["date"]: i for i, p in enumerate(points)}
    for d, (colour, tip, ill) in sorted((markers or {}).items()):
        if d not in idx:
            continue
        cx = x(idx[d])
        parts.append(f'<circle cx="{cx:.1f}" cy="{height - mb - 4}" r="4" fill="{escape(colour)}">'
                     f'<title>{escape(tip)}</title></circle>')
        if ill:
            parts.append(f'<text x="{cx:.1f}" y="{mt + 10}" class="ill" text-anchor="middle">+'
                         f'<title>{escape(tip)}</title></text>')
    parts.append("</svg>")
    return head + "".join(parts) + "</figure>"


def svg_strain_recovery_chart(load_series, rec_series, width=640, height=200):
    """Daily load bars (own scale) and the recovery line (0-100) over 90 days; flag dots on red high-load days."""
    title = "Load vs recovery"
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    recs = (rec_series or [])[-STRAIN_CHART_DAYS:]
    if len([r for r in recs if r["score"] is not None]) < 2:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    loads = {p["date"]: p["load"] for p in (load_series or [])}
    n = len(recs)
    ml, mr, mt, mb = 44, 10, 8, 22
    iw, ih = width - ml - mr, height - mt - mb
    lmax = max([loads.get(r["date"], 0.0) for r in recs] + [1.0]) * 1.08

    def x(i):
        return ml + iw * i / max(n - 1, 1)

    def y(score):
        return mt + ih * (1 - score / 100)

    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    for v in (0, 100):
        parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>')
    for v in (0, 33, 67, 100):
        parts.append(f'<text x="{ml - 4}" y="{y(v) + 3:.1f}" class="ax" text-anchor="end">{v}</text>')
    for v in (33, 67):
        parts.append(f'<line x1="{ml}" x2="{width - mr}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid" '
                     f'stroke-dasharray="4 3"/>')
    parts.append(f'<text x="{ml}" y="{height - 6}" class="ax">{escape(recs[0]["date"])}</text>')
    parts.append(f'<text x="{width - mr}" y="{height - 6}" class="ax" text-anchor="end">{escape(recs[-1]["date"])}</text>')
    bw = max(iw / n * 0.7, 0.8)
    for i, r in enumerate(recs):
        ld = loads.get(r["date"], 0.0)
        if ld > 0:
            h = ih * ld / lmax
            parts.append(f'<rect x="{x(i) - bw / 2:.1f}" y="{mt + ih - h:.1f}" width="{bw:.1f}" height="{h:.1f}" '
                         f'class="loadbar"><title>{escape(r["date"])}: load {ld:.0f}</title></rect>')
    seg = []
    for i, r in enumerate(recs + [{"score": None, "date": ""}]):
        if r["score"] is not None:
            seg.append(f"{x(i):.1f},{y(r['score']):.1f}")
        else:
            if len(seg) > 1:
                parts.append(f'<polyline points="{" ".join(seg)}" class="rec" fill="none"/>')
            seg = []
    for i, r in enumerate(recs):
        if r.get("flag") and r["score"] is not None:
            parts.append(f'<circle cx="{x(i):.1f}" cy="{y(r["score"]):.1f}" r="4" class="flag">'
                         f'<title>{escape(r["date"])}: high load on a red recovery day ({r["score"]})</title></circle>')
    parts.append("</svg>")
    return head + "".join(parts) + "</figure>"


# ---------------------------------------------------------------- volume

def _percentile(sorted_vals, q):
    """Linear-interpolated percentile (q in 0..1) of a sorted non-empty list."""
    k = (len(sorted_vals) - 1) * q
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def heat_levels(loads):
    """3 cut points (25th/50th/75th percentile of the non-zero loads); (0, 0, 0) without non-zero loads."""
    vals = sorted(v for v in (num(x) for x in loads or []) if v is not None and v > 0)
    if not vals:
        return (0.0, 0.0, 0.0)
    return tuple(_percentile(vals, q) for q in (0.25, 0.5, 0.75))


def _heat_level(load, cuts):
    if not load or load <= 0:
        return 0
    return 1 + sum(1 for c in cuts if load > c)


def svg_heatmap(series, today, cell=11, gap=2):
    """GitHub-style calendar of daily load: 53 Monday-first columns ending in today's week, in a figure.chart.card."""
    title = "Daily load, last 12 months"
    head = f'<figure class="chart card"><figcaption>{escape(title)}</figcaption>'
    if not series or len(series) < 2:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    by_day = {}
    for p in series:
        d = _day(p.get("date"))
        if d is not None and d <= today:
            by_day[d] = num(p.get("load")) or 0.0
    if len(by_day) < 2:
        return head + '<p class="muted">Not enough data yet.</p></figure>'
    first = min(by_day)
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(weeks=HEATMAP_DAYS // 7 - 1)
    cuts = heat_levels([v for d, v in by_day.items() if d >= start])
    step = cell + gap
    ml, mt = 4, 14
    width = ml + 53 * step + 4
    height = mt + 7 * step + 18
    parts = [f'<svg class="heat" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">']
    last_month = None
    for col in range(53):
        monday = start + timedelta(weeks=col)
        if monday.month != last_month and (col == 0 or monday.day <= 7):
            parts.append(f'<text x="{ml + col * step}" y="10" class="ax">{monday.strftime("%b")[0]}</text>')
            last_month = monday.month
        for row in range(7):
            d = monday + timedelta(days=row)
            if d > today or d < first or d not in by_day:
                continue
            load = by_day[d]
            lv = _heat_level(load, cuts)
            parts.append(f'<rect x="{ml + col * step}" y="{mt + row * step}" width="{cell}" height="{cell}" '
                         f'class="h{lv}"><title>{d.isoformat()}: load {load:.0f}</title></rect>')
    ly = height - 6
    parts.append(f'<text x="{ml}" y="{ly + 3}" class="ax">less</text>')
    for i in range(5):
        parts.append(f'<circle cx="{ml + 30 + i * 14}" cy="{ly}" r="5" class="h{i}"/>')
    parts.append(f'<text x="{ml + 30 + 5 * 14}" y="{ly + 3}" class="ax">more</text>')
    parts.append("</svg>")
    return head + "".join(parts) + "</figure>"


def weekly_summary(runs, fiit, today, weeks=SUMMARY_WEEKS):
    """Newest week first, current week included. runs: dicts (start_local, distance_m, duration_s); fiit: dicts (date)."""
    this_monday = today - timedelta(days=today.weekday())
    keys = [(this_monday - timedelta(weeks=i)).isoformat() for i in range(weeks)]
    rows = {k: {"week": k, "dist_m": 0.0, "time_s": 0.0, "runs": 0, "fiit": 0, "long_m": 0.0} for k in keys}
    for r in runs or []:
        d = _day(r.get("start_local"))
        if d is None:
            continue
        row = rows.get(week_start(d.isoformat()))
        if row is None:
            continue
        dist = num(r.get("distance_m")) or 0.0
        row["dist_m"] += dist
        row["time_s"] += num(r.get("duration_s")) or 0.0
        row["runs"] += 1
        row["long_m"] = max(row["long_m"], dist)
    for f in fiit or []:
        d = _day(f.get("date"))
        row = rows.get(week_start(d.isoformat())) if d is not None else None
        if row is not None:
            row["fiit"] += 1
    out = []
    for k in keys:
        row = rows[k]
        share = None
        if row["runs"] >= LONG_SHARE_MIN_RUNS and row["dist_m"] > 0:
            share = row["long_m"] / row["dist_m"]
        row["long_share"] = share
        row["long_tone"] = "warn" if share is not None and share > LONG_SHARE_WARN else ""
        out.append(row)
    return out


def run_streak(runs, today):
    """Consecutive weeks with >= STREAK_MIN_RUNS runs, counting back from last week.
    The current week adds 1 when it already has enough runs; otherwise it neither counts nor breaks the streak."""
    counts = {}
    for r in runs or []:
        d = _day(r.get("start_local"))
        if d is not None and d <= today:
            k = week_start(d.isoformat())
            counts[k] = counts.get(k, 0) + 1
    this_monday = today - timedelta(days=today.weekday())
    n = 1 if counts.get(this_monday.isoformat(), 0) >= STREAK_MIN_RUNS else 0
    w = this_monday - timedelta(weeks=1)
    while counts.get(w.isoformat(), 0) >= STREAK_MIN_RUNS:
        n += 1
        w -= timedelta(weeks=1)
    return n
