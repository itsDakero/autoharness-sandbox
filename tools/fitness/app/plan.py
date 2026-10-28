"""Training plan engine (phase 3): goal -> block of weeks -> a session per day (stdlib only).

Pure functions: they take rows (dicts) and dates and return dicts. Missing data never raises: it gives
"-" or "no change". All thresholds and offsets are the constants below. Suggestions, not medical advice."""
from datetime import date, timedelta

from . import logic, running

# ---- constants (one place) ----
WED = 2                  # work run club, fixed
WEEKEND_DAY = 5          # Saturday: the quality session
FIIT_DAYS = (0, 1)       # Monday, then Tuesday
FIIT_FRIDAY = 4          # also allowed when the weekend session is easy
TAPER_WEEKS = {"5k": 1, "10k": 1, "half": 2}
SHARPEN_FRAC, BUILD_FRAC = 0.2, 0.4
AHEAD_WEEKS = 12         # rolling weeks kept ahead
MIN_AHEAD = 2            # append when fewer than this many weeks follow the current one
SOFTEN_READINESS, SOFTEN_RECOVERY = 50, 34
BONUS_READINESS_MIN = 75
# pace offsets in s/km: (low, high). Base is P5 (5k PB / 5, else the goal's 5k pace), G5 = goal in 5k terms.
EASY_OFF, STEADY_OFF, TEMPO_OFF = (60, 90), (35, 55), (15, 25)
INTERVAL_OFF, RACE_OFF = (-5, 0), (-3, 3)   # from G5 / goal pace
MIN_PACE_S_KM = 150      # 2:30/km: faster targets are refused
MIN_TARGET_S, MAX_TARGET_S = 300, 21600
DISTANCES_M = {"5k": 5000.0, "10k": 10000.0, "half": 21097.5}
DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
FIIT_BY_PHASE = {"base": "strength", "build": "hiit", "sharpen": "hiit", "taper": "mobility"}
RUN_KINDS = ("run_club", "quality", "long_easy", "easy", "steady", "race")
LOOSE_KINDS = ("quality", "long_easy", "easy")     # the weekend slot
CAP_EASY_DOWN = ("quality", "steady", "run_club", "race", "long_easy", "bonus")


def monday(d):
    return d - timedelta(days=d.weekday())


def _day(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


# ---- goal ----
def parse_target(text):
    """'mm:ss' or 'h:mm:ss' -> seconds, or None."""
    parts = str(text or "").strip().split(":")
    if len(parts) not in (2, 3) or not all(p.strip().isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts]
    if nums[-1] >= 60 or (len(nums) == 3 and nums[1] >= 60):
        return None
    secs = nums[-1] + 60 * nums[-2] + (3600 * nums[0] if len(nums) == 3 else 0)
    return secs if MIN_TARGET_S <= secs <= MAX_TARGET_S else None


def parse_goal(distance, custom_m, target, race, today):
    """(goal dict, None) or (None, message). Nothing is written by this function."""
    if distance not in ("5k", "10k", "half", "custom"):
        return None, "Distance must be 5k, 10k, half or custom."
    if distance == "custom":
        cm = str(custom_m or "").strip()
        if not cm.isdigit() or not 400 <= int(cm) <= 50000:
            return None, "Custom distance must be a whole number of metres from 400 to 50000."
        dm = float(int(cm))
    else:
        dm = DISTANCES_M[distance]
    secs = parse_target(target)
    if secs is None:
        return None, "Target time must be mm:ss or h:mm:ss, between 5 minutes and 6 hours."
    if secs / dm * 1000 < MIN_PACE_S_KM:
        return None, "That target is faster than 2:30 per km."
    race = str(race or "").strip()
    rd = None
    if race:
        d = _day(race) if len(race) == 10 else None
        if d is None or not today < d <= today + timedelta(days=365):
            return None, "Race date must be blank, or after today and within a year."
        rd = d.isoformat()
    return {"distance": distance, "distance_m": dm, "target_s": secs, "race_date": rd}, None


def paces(goal, pb5k_s):
    """{'p5','g5','goal'} in s/km, or None when the goal is unusable."""
    try:
        t, d = float(goal["target_s"]), float(goal["distance_m"])
        if t <= 0 or d <= 0:
            return None
        g5 = running.riegel(t, d, 5000.0) / 5
        pb = logic.num(pb5k_s)
        return {"p5": pb / 5 if pb and pb > 0 else g5, "g5": g5, "goal": t / d * 1000}
    except (TypeError, ValueError, KeyError):
        return None


# ---- block ----
def taper_weeks(distance, distance_m):
    if distance in TAPER_WEEKS:
        return TAPER_WEEKS[distance]
    return 1 if (logic.num(distance_m) or 0) <= 10000 else 2


def phase_split(n, distance, distance_m):
    """(base, build, sharpen, taper) week counts for n weeks up to and including race week."""
    n = max(int(n), 0)
    taper = min(taper_weeks(distance, distance_m), n)
    rest = n - taper
    sharpen = int(SHARPEN_FRAC * rest + 0.5)
    build = int(BUILD_FRAC * rest + 0.5)
    return max(rest - sharpen - build, 0), build, sharpen, taper


def rolling_weeks(first, start_no, count):
    return [{"week_start": (first + timedelta(weeks=i)).isoformat(), "phase": "base",
             "week_no": start_no + i, "easy": int((start_no + i) % 4 == 0), "race_date": None}
            for i in range(max(count, 0))]


def generate_weeks(goal, first, start_no=1):
    """Rows for plan_weeks from the Monday `first`. Dated goal: back-planned; else (or race passed): rolling."""
    race = _day(goal.get("race_date"))
    if race is not None and monday(race) >= first:
        n = (monday(race) - first).days // 7 + 1
        base, build, sharpen, taper = phase_split(n, goal.get("distance"), goal.get("distance_m"))
        phases = ["base"] * base + ["build"] * build + ["sharpen"] * sharpen + ["taper"] * taper
        return [{"week_start": (first + timedelta(weeks=i)).isoformat(), "phase": p, "week_no": start_no + i,
                 "easy": 0, "race_date": race.isoformat() if i == n - 1 else None}
                for i, p in enumerate(phases)]
    return rolling_weeks(first, start_no, AHEAD_WEEKS)


def missing_weeks(goal, stored, today):
    """New rolling rows to append (never rewrites a stored row). Empty store: the whole block."""
    if goal is None:
        return []
    cur = monday(today)
    if not stored:
        return generate_weeks(goal, cur, 1)
    last = max(stored, key=lambda w: w["week_start"])
    ahead = sum(1 for w in stored if w["week_start"] > cur.isoformat())
    last_d = _day(last["week_start"])
    if ahead >= MIN_AHEAD or last_d is None:
        return []
    first = max(last_d + timedelta(weeks=1), cur)
    count = (cur + timedelta(weeks=AHEAD_WEEKS) - first).days // 7 + 1
    return rolling_weeks(first, int(logic.num(last["week_no"]) or 0) + 1, count)


# ---- session text ----
def _rng(rng, base, unit):
    if base is None:
        return ""
    f = 1.609344 if unit == "mi" else 1.0
    lo, hi = sorted((round((base + rng[0]) * f), round((base + rng[1]) * f)))
    return f"{logic.fmt_dur(lo)}-{logic.fmt_dur(hi)}/{unit}"


def paces_text(pc, unit):
    if not pc:
        return {k: "" for k in ("easy", "steady", "tempo", "intervals", "race")}
    return {"easy": _rng(EASY_OFF, pc["p5"], unit), "steady": _rng(STEADY_OFF, pc["p5"], unit),
            "tempo": _rng(TEMPO_OFF, pc["p5"], unit), "intervals": _rng(INTERVAL_OFF, pc["g5"], unit),
            "race": _rng(RACE_OFF, pc["goal"], unit)}


def fiit_type_for(week):
    return "mobility" if week.get("easy") else FIIT_BY_PHASE.get(week.get("phase"), "mobility")


def describe(kind, week, goal, pc, unit, fiit_type=None, mins=None):
    """(title, target) for a session kind."""
    pt = paces_text(pc, unit)
    at = lambda s, p: f"{s} at {p}" if p else s   # noqa: E731
    phase = week.get("phase")
    if kind == "rest":
        return "Rest", "No planned session."
    if kind == "run_club":
        return "Work run club", "3-4 miles steady, 9:00-9:30/mile"
    if kind == "fiit":
        ft = fiit_type or fiit_type_for(week)
        return f"FiiT class: {ft}", "Light and easy." if ft == "mobility" else f"One {ft} class."
    if kind == "long_easy":
        return "Long easy run", at("60-75 min easy", pt["easy"])
    if kind == "easy":
        return "Easy run", at(f"{mins or '20-30'} min easy", pt["easy"])
    if kind == "steady":
        return "Steady run", at("30-40 min steady", pt["steady"])
    if kind == "bonus":
        return "Optional extra", "optional: easy 20-30 min or mobility"
    if kind == "race":
        dist = goal.get("distance") if goal.get("distance") != "custom" else f"{int(goal['distance_m'])} m"
        return "Race day", f"{dist}, goal {logic.fmt_dur(goal.get('target_s'))}"
    if kind == "quality":
        long_race = goal.get("distance") == "half" or (goal.get("distance_m") or 0) > 10000
        if phase == "build":
            if (week.get("week_no") or 0) % 2 == 1:
                return "Tempo run", at("2 x 10 min", pt["tempo"])
            return "Intervals", at("5 x 1 km, 2 min jog", pt["intervals"])
        if phase == "sharpen":
            return "Race-pace session", at("3 x 3 km" if long_race else "3 x 1 mile", pt["race"])
        return "Taper sharpener", at("20 min easy + 4 x 400 m", pt["race"])
    return str(kind), ""


# ---- week ----
def race_of(week, goal):
    r = week.get("race_date")
    if not r and goal.get("race_date") and monday(_day(goal["race_date"]) or date.min).isoformat() == week["week_start"]:
        r = goal["race_date"]
    return r


def template_week(week, goal):
    ws = _day(week["week_start"])
    days = [{"date": (ws + timedelta(i)).isoformat(), "kind": "rest"} for i in range(7)]
    race = _day(race_of(week, goal))
    days[WED]["kind"] = "run_club"
    if not race:
        days[FIIT_DAYS[0]].update(kind="fiit", fiit_type=fiit_type_for(week))
    easy = bool(week.get("easy"))
    days[WEEKEND_DAY]["kind"] = "easy" if easy else ("long_easy" if week["phase"] == "base" else "quality")
    if easy:
        days[WEEKEND_DAY]["mins"] = "45"
    if race:
        for i, d in enumerate(days):
            dd = ws + timedelta(i)
            if dd == race:
                d.update(kind="race")
            elif dd > race:
                d.update(kind="rest")
            elif dd == race - timedelta(days=1) and d["kind"] in LOOSE_KINDS:
                d.update(kind="easy", mins=None)
    return days


def week_view(week, env):
    """7 day dicts: date, kind, title, target, status (done|missed|planned|rest|optional), reason."""
    goal, today = env["goal"], env["today"]
    ws = _day(week["week_start"])
    ti = today.isoformat()
    days = template_week(week, goal)
    runs, pdays = env["run_dates"], env["pdays"]
    for i, d in enumerate(days):
        d.setdefault("reason", None)
        d["status"] = None
        d["dow"] = DAYS[i]
    # FiiT: done in the week, or re-suggested on the next allowed day
    fi = next((i for i, d in enumerate(days) if d["kind"] == "fiit"), None)
    if fi is not None:
        allowed = list(FIIT_DAYS) + ([FIIT_FRIDAY] if days[WEEKEND_DAY]["kind"] in ("long_easy", "easy") else [])
        allowed = [i for i in allowed if days[i]["kind"] in ("rest", "fiit")]
        week_end = (ws + timedelta(6)).isoformat()
        done = sorted(x for x in env["fiit_dates"] if ws.isoformat() <= x <= min(week_end, ti))
        proto = dict(days[fi])
        if done:
            idx = (_day(done[0]) - ws).days
            if idx != fi and days[idx]["kind"] == "rest":
                days[fi].update(kind="rest", fiit_type=None)
                days[idx].update(kind="fiit", fiit_type=proto["fiit_type"])
                fi = idx
            days[fi]["status"] = "done"
        elif ws > today:
            days[fi]["status"] = "planned"
        else:
            cur_week = today <= ws + timedelta(6)
            cands = [i for i in allowed if ws + timedelta(i) >= today] if cur_week else []
            target = cands[0] if cands else allowed[-1]
            status = "planned" if cands else "missed"
            if target != fi:
                days[fi].update(kind="rest", fiit_type=None)
                days[target].update(kind="fiit", fiit_type=proto["fiit_type"], reason=f"moved from {DAYS[fi]}")
            days[target]["status"] = status
    # weekend session: a missed or swapped quality run moves once, to Sunday, never into the next week
    wk = days[WEEKEND_DAY]
    sat = ws + timedelta(WEEKEND_DAY)
    if wk["kind"] in LOOSE_KINDS and sat < today and days[6]["kind"] == "rest":
        pd = pdays.get(sat.isoformat()) or {}
        swapped = bool(pd.get("adjusted")) and pd["adjusted"] != pd.get("planned")
        sun = (sat + timedelta(1)).isoformat()
        if (sat.isoformat() not in runs or swapped) and (sun in runs or sat + timedelta(1) >= today):
            days[6].update(kind=wk["kind"], mins=wk.get("mins"),
                           reason=f"moved from Saturday ({'swapped' if swapped else 'missed'})")
            if not swapped:
                wk["status"], wk["reason"] = "missed", "moved to Sunday"
    # earlier days keep what was adjusted at the time
    for i, d in enumerate(days):
        pd = pdays.get(d["date"])
        if pd and pd.get("adjusted") and _day(d["date"]) < today and d["reason"] is None:
            d.update(kind=pd["adjusted"], reason=pd.get("reason"), mins=None)
    for d in days:
        k, iso = d["kind"], d["date"]
        if d["status"]:
            pass
        elif k == "rest":
            d["status"] = "rest"
        elif k == "bonus":
            d["status"] = "done" if iso in runs or iso in env["fiit_dates"] else "optional"
        elif k == "fiit":
            d["status"] = "planned"
        elif iso in runs:
            d["status"] = "done"
        else:
            d["status"] = "missed" if iso < ti else "planned"
        d["title"], d["target"] = describe(k, week, goal, env["pc"], env["unit"], d.get("fiit_type"), d.get("mins"))
    return days


# ---- today ----
def apply_cap(kind, cap):
    """(kind, fiit_type) after capping at 'rest', 'easy' or 'steady'."""
    if cap == "rest":
        return "rest", None
    if kind == "fiit":
        return ("fiit", "mobility") if cap == "easy" else ("fiit", None)
    if cap == "easy" and kind in CAP_EASY_DOWN:
        return "easy", None
    if cap == "steady" and kind in ("quality", "race"):
        return "steady", None
    return kind, None


def last_ill(checkins, today):
    """{'date','chest'} of the latest ill check-in before today within 7 days, else None."""
    best = None
    for c in checkins or []:
        d = _day(c.get("date"))
        if d is None or not (0 < (today - d).days <= 7) or not (c.get("ill_neck") or c.get("ill_chest")):
            continue
        if best is None or d > best[0]:
            best = (d, bool(c.get("ill_chest")))
    return {"date": best[0], "chest": best[1]} if best else None


def adjust_today(days, week, env):
    """Daily adjustment. The first rule that applies wins. Returns the changes to today's row."""
    today = env["today"]
    ti = (today - _day(week["week_start"])).days
    row = days[ti]
    kind = row["kind"]
    out = {"planned": kind, "kind": kind, "fiit_type": row.get("fiit_type"), "mins": row.get("mins"),
           "reason": row.get("reason"), "moved_to": None, "changed": False}
    if row["status"] == "done":
        return out

    def set_(k, reason, ft=None, mins=None):
        out.update(kind=k, fiit_type=ft, mins=mins, reason=reason, changed=True)
        return out

    c = env.get("checkin_today") or {}
    if c.get("ill_chest"):                                           # 1
        return set_("rest", "chest symptoms or fever: rest")
    cap = why = None
    if c.get("ill_neck"):                                            # 2
        cap, why = "easy", "above-neck symptoms: easy only"
    else:                                                            # 3
        ill = last_ill(env.get("checkins"), today)
        if ill:
            delta = (today - ill["date"]).days
            if ill["chest"]:
                cap = "easy" if delta <= 2 else ("steady" if delta == 3 else None)
                what = "chest symptoms or fever"
            else:
                cap = "easy" if delta == 1 else ("steady" if delta == 2 else None)
                what = "above-neck symptoms"
            if cap:
                why = f"coming back after {what}: {'easy only' if cap == 'easy' else 'steady at most'}"
    if cap:
        nk, ft = apply_cap(kind, cap)
        if nk != kind or ft:
            return set_(nk, why, ft)
        return out
    r, rs, warn = env.get("readiness"), env.get("rec_score"), env.get("warning")   # 4
    soft = None
    if r is not None and r < SOFTEN_READINESS:
        soft = f"readiness {r:.0f} is low"
    elif rs is not None and rs < SOFTEN_RECOVERY:
        soft = f"recovery score {rs:.0f} is low"
    elif warn:
        soft = "illness warning"
    if soft and kind == "quality":
        free = [i for i in range(ti + 1, 7) if i != WED and days[i]["kind"] == "rest"]
        if free:
            out["moved_to"] = days[free[0]]["date"]
            return set_("easy", f"{soft}: easy today, quality moved to {DAYS[free[0]]}")
        return set_("steady", f"{soft}: steady instead of quality")
    if kind == "rest" and r is not None and r >= BONUS_READINESS_MIN and env.get("hrv_tone") == "good" \
            and env.get("zone") not in (None, "High risk") and _bonus_free(days, env):   # 5
        return set_("bonus", "readiness and HRV are good")
    return out


def _bonus_free(days, env):
    """No run or FiiT yet on a free day this week (today included)."""
    ti = env["today"].isoformat()
    for d in days:
        if d["kind"] in ("rest", "bonus") and d["date"] <= ti and (
                d["date"] in env["run_dates"] or d["date"] in env["fiit_dates"]):
            return False
    return True


def compute(env, weeks):
    """The whole plan context for the pages and the feed. env keys: see main.load_plan and the tests."""
    today = env["today"]
    goal = env["goal"]
    cur = monday(today)
    byw = {w["week_start"]: w for w in weeks}
    cw = byw.get(cur.isoformat())
    out = {"goal": goal, "pc": env["pc"], "weeks": [], "today": None, "phase": None, "week_no": None,
           "easy": False, "race_date": goal.get("race_date"), "timeline": svg_timeline(weeks, today)}
    if cw is None:
        return out
    days = week_view(cw, env)
    adj = adjust_today(days, cw, env)
    ti = (today - cur).days
    row = days[ti]
    row.update(kind=adj["kind"], reason=adj["reason"], fiit_type=adj["fiit_type"])
    row["title"], row["target"] = describe(adj["kind"], cw, goal, env["pc"], env["unit"],
                                           adj["fiit_type"], adj["mins"])
    if adj["moved_to"]:
        mi = (_day(adj["moved_to"]) - cur).days
        days[mi].update(kind=adj["planned"], reason=f"moved from {DAYS[ti]} (softened)", status="planned")
        days[mi]["title"], days[mi]["target"] = describe(adj["planned"], cw, goal, env["pc"], env["unit"])
    nxt = byw.get((cur + timedelta(weeks=1)).isoformat())
    out.update(phase=cw["phase"], week_no=cw["week_no"], easy=bool(cw.get("easy")),
               weeks=[{"label": "This week", "start": cw["week_start"], "phase": cw["phase"], "days": days},
                      {"label": "Next week", "start": nxt["week_start"], "phase": nxt["phase"],
                       "days": week_view(nxt, env)} if nxt else None],
               today={"planned": adj["planned"], "adjusted_kind": adj["kind"] if adj["changed"] else None,
                      "kind": adj["kind"], "title": row["title"], "target": row["target"],
                      "reason": adj["reason"], "adjusted": bool(adj["reason"]), "status": row["status"]})
    out["weeks"] = [w for w in out["weeks"] if w]
    return out


def svg_timeline(weeks, today):
    """Inline SVG strip of the stored weeks, coloured by phase."""
    ws = sorted(weeks, key=lambda w: w["week_start"])
    if not ws:
        return ""
    w = max(4, min(18, 640 // len(ws)))
    cur = monday(today).isoformat()
    parts = [f'<svg class="tl" viewBox="0 0 {w * len(ws) + 2} 34" role="img" aria-label="Training block">']
    for i, wk in enumerate(ws):
        x = 1 + i * w
        cls = f'{wk["phase"]}{" now" if wk["week_start"] == cur else ""}{" easywk" if wk.get("easy") else ""}'
        parts.append(f'<rect x="{x}" y="4" width="{w - 1}" height="22" class="{cls}">'
                     f'<title>Week {wk["week_no"]} ({wk["week_start"]}): {wk["phase"]}'
                     f'{", easier week" if wk.get("easy") else ""}</title></rect>')
        if wk.get("race_date"):
            parts.append(f'<text x="{x + w / 2:.1f}" y="33" class="race" text-anchor="middle">race</text>')
    parts.append("</svg>")
    return "".join(parts)
