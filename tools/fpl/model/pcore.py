"""Player points model, pure parts (stdlib only, host-testable): scoring rules, minutes, rates, availability,
bonus points. The Monte Carlo itself is in players.py (numpy). See tools/fpl/README.md, "Player points model"."""
import math
import re
import unicodedata

# ---- constants the API's game_config does not carry ---------------------------------------------------------
# Checked by the planner on 2026-10-26 against the Premier League's Fantasy scoring table and BPS explainer
# (premierleague.com, Fantasy "Points system" and "Bonus Points System" pages).
# Defensive contributions: points are in game_config.scoring; the thresholds are not.
# element_type -> count needed: DEF 10 CBIT, MID/FWD 12 CBIRT.
DEFCON_THRESHOLD = {2: 10, 3: 12, 4: 12}
SAVES_PER_PT = 3        # one saves point per 3 saves
GC_PER_PT = 2           # goals_conceded applies per 2 goals conceded (GKP, DEF)
LONG_PLAY_MIN = 60      # long_play (2 pts) from 60 minutes, short_play (1 pt) for 1-59
# BPS event values (the baseline BPS of a player = his bps minus these events)
BPS_GOAL = {1: 12, 2: 12, 3: 18, 4: 24}
BPS_ASSIST = 9
BPS_CS = {1: 12, 2: 12, 3: 0, 4: 0}
BPS_SAVE = 2
BONUS_BY_PLACE = (3, 2, 1)

# ---- rates (all per match or per 90; measured on 2023/24-2025/26, see the README) ---------------------------
OG_SHARE = 0.035                 # share of a team's goals that are own goals by the other side: no FPL scorer
PEN_MISS_PER_TEAM_MATCH = 0.02   # missed or saved penalty by the team's first-choice taker
RED_PER90 = 0.005
OWN_GOAL_PER90 = 0.005
ASSIST_RATE = 0.75               # share of goals with an assist, until the data has 200+ goals
ASSIST_MIN_GOALS = 200
DEFCON_UNDISP = 0.19             # 1 - variance/mean of the defensive-contribution count for MID/FWD (0.81)
SAVES_LAMBDA_REF = 1.4           # opponent goals a save rate is measured at

# ---- priors ---------------------------------------------------------------------------------------------------
PRIOR_MINUTES = {"p_start": 0.3, "m_start": 80.0, "p60": 0.75, "p_sub": 0.3, "m_sub": 20.0}
PRIOR_PSEUDO = 2.0               # each minutes prior is worth this many matches
MINUTES_DECAY = 0.92             # per match, newest first
RATE_DECAY = 0.97
RATE_PSEUDO_MIN = 900.0
# by element_type (1 GKP, 2 DEF, 3 MID, 4 FWD), per 90
PRIOR_XG = {1: 0.0, 2: 0.04, 3: 0.10, 4: 0.25}
PRIOR_XA = {1: 0.0, 2: 0.04, 3: 0.09, 4: 0.12}
PRIOR_DEFCON = {1: 0.0, 2: 7.0, 3: 6.0, 4: 3.5}
PRIOR_SAVES = {1: 2.8, 2: 0.0, 3: 0.0, 4: 0.0}
PRIOR_YELLOW = 0.17
PRIOR_BPS_BASE = {1: 12.0, 2: 14.0, 3: 10.0, 4: 9.0}

SCORING_KEYS = ("goals_scored", "assists", "clean_sheets", "goals_conceded", "saves", "defensive_contribution",
                "long_play", "short_play", "yellow_cards", "red_cards", "own_goals", "penalties_missed", "bonus")
TYPE_OF = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}


def num(v, default=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    return f if math.isfinite(f) else default


def scoring_from_bootstrap(d):
    """Bootstrap JSON -> {key: {element_type: points}} from game_config.scoring. Scalars apply to every position.
    Raises ValueError on a missing key (nothing is guessed: the rules change by season)."""
    try:
        sc = d["game_config"]["scoring"]
        if not isinstance(sc, dict):
            raise TypeError
    except (KeyError, TypeError):
        raise ValueError("bootstrap has no game_config.scoring")
    out = {}
    for k in SCORING_KEYS:
        if k not in sc:
            raise ValueError(f"game_config.scoring has no {k}")
        v = sc[k]
        try:
            if isinstance(v, dict):
                out[k] = {t: float(v[n]) for n, t in TYPE_OF.items()}
            else:
                out[k] = {t: float(v) for t in TYPE_OF.values()}
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"game_config.scoring.{k} is not usable")
    return out


_FOLD = str.maketrans({"\u00f8": "o", "\u0111": "d", "\u0142": "l", "\u00e6": "ae", "\u0153": "oe", "\u00df": "ss"})


def norm_name(s):
    s = unicodedata.normalize("NFKD", str(s or "")).lower().translate(_FOLD)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def kick_key(v):
    """Sortable form of a kickoff time (ISO string with T/Z, or a datetime)."""
    return str(v or "").replace("T", " ").replace("Z", "")[:19]


def match_log(rows, etype):
    """FPL history rows (+ mapped vaastav rows, same key names) -> list of dicts, newest first:
    minutes, starts, xg, xa, defcon, bps, bps_base, saves, yellows, goals, assists, cs."""
    out = []
    for r in sorted(rows, key=lambda r: kick_key(r.get("kickoff_time")), reverse=True):
        mins = num(r.get("minutes"))
        starts = r.get("starts")
        started = (mins > 45) if starts is None or starts == "" else num(starts) > 0
        if any(r.get(k) not in (None, "") for k in ("clearances_blocks_interceptions", "tackles")):
            dc = num(r.get("clearances_blocks_interceptions")) + num(r.get("tackles"))
            if etype in (3, 4):
                dc += num(r.get("recoveries"))
        else:
            dc = num(r.get("defensive_contribution"))
        if etype == 1:
            dc = 0.0
        goals, assists, cs, saves = (num(r.get("goals_scored")), num(r.get("assists")),
                                     num(r.get("clean_sheets")) if mins >= LONG_PLAY_MIN else 0.0,
                                     num(r.get("saves")))
        bps = num(r.get("bps"))
        base = bps - goals * BPS_GOAL[etype] - assists * BPS_ASSIST - cs * BPS_CS[etype] - saves * BPS_SAVE
        out.append({"minutes": mins, "starts": 1.0 if started else 0.0, "xg": num(r.get("expected_goals")),
                    "xa": num(r.get("expected_assists")), "defcon": dc, "bps": bps, "bps_base": base,
                    "saves": saves, "yellows": num(r.get("yellow_cards")), "goals": goals, "assists": assists,
                    "cs": cs})
    return out


def minutes_params(log, prior=None, decay=MINUTES_DECAY, pseudo=PRIOR_PSEUDO):
    """Decayed (per match, newest first) minutes behaviour with priors worth `pseudo` matches each.
    -> p_start, m_start (mean minutes per start), p60 (given a start), p_sub (given no start), m_sub."""
    pr = {**PRIOR_MINUTES, **(prior or {})}
    sw = s60 = sm = 0.0        # matches he started: weight, 60+ weight, minutes
    nw = nsub = nmin = 0.0     # matches he did not: weight, appearances, minutes
    pw = pstart = 0.0          # all matches: weight, starts
    for i, m in enumerate(log):
        w = decay ** i
        pw += w
        if m["starts"] > 0:
            sw += w
            sm += w * m["minutes"]
            s60 += w * (m["minutes"] >= LONG_PLAY_MIN)
            pstart += w
        else:
            nw += w
            if m["minutes"] > 0:
                nsub += w
                nmin += w * m["minutes"]
    return {"p_start": (pseudo * pr["p_start"] + pstart) / (pseudo + pw),
            "m_start": (pseudo * pr["m_start"] + sm) / (pseudo + sw),
            "p60": (pseudo * pr["p60"] + s60) / (pseudo + sw),
            "p_sub": (pseudo * pr["p_sub"] + nsub) / (pseudo + nw),
            "m_sub": (pseudo * pr["m_sub"] + nmin) / (pseudo + nsub)}


def rate90(log, field, prior90, decay=RATE_DECAY, pseudo_min=RATE_PSEUDO_MIN):
    """Decayed per-90 rate of a log field, shrunk toward prior90 by pseudo_min minutes. Empty log -> prior90."""
    k = pseudo_min / 90.0
    num_, den = prior90 * k, k
    for i, m in enumerate(log):
        w = decay ** i
        num_ += w * m[field]
        den += w * m["minutes"] / 90.0
    return num_ / den


def assist_rate(goals, assists):
    return min(0.95, max(0.5, assists / goals)) if goals >= ASSIST_MIN_GOALS else ASSIST_RATE


def availability(status, cop, k):
    """Chance a player is available, k gameweeks after the next one (0 = next). `u` (left the club): 0 always.
    Next gameweek: chance_of_playing_next_round / 100 (None = 1, except flagged i/s/n which then count 0);
    the one after: min(1, next + 0.5); later: 1."""
    if status == "u":
        return 0.0
    if cop is None or cop != cop:
        a_next = 0.0 if status in ("i", "s", "n") else 1.0
    else:
        a_next = min(1.0, max(0.0, float(cop) / 100.0))
    if k <= 0:
        return a_next
    if k == 1:
        return min(1.0, a_next + 0.5)
    return 1.0


def override_minutes(xmins_gw, n_fixtures):
    """Dan's override for one gameweek -> per fixture ("start"|"sub"|"out", minutes). Minutes per fixture =
    override / n; 45 or more is a fixed start, above 0 a fixed sub appearance, 0 is out. Sum = the override."""
    n = max(int(n_fixtures), 1)
    if xmins_gw <= 0:
        return [("out", 0.0)] * n
    m = xmins_gw / n
    return [("start" if m >= 45 else "sub", m)] * n


def bonus_from_greater(g):
    """Bonus points for a player with g players strictly ahead on BPS (ties share the place's points)."""
    return BONUS_BY_PLACE[g] if 0 <= g < len(BONUS_BY_PLACE) else 0


def bonus_points(bps_list):
    """3/2/1 under the official tie rules: players tied for a place all get its points; the next distinct BPS
    skips the places they took. [30,30,20] -> 3,3,1; [30,20,20] -> 3,2,2."""
    return [bonus_from_greater(sum(1 for o in bps_list if o > b)) for b in bps_list]


def defcon_binom_n(mu):
    """Binomial n for an under-dispersed count with mean mu (variance/mean 0.81): n = round(mu / 0.19), p = mu / n."""
    return max(1, int(round(mu / DEFCON_UNDISP)))


def start_mix(mean_start, p60):
    """Minutes given a start: with p60 a 60-90 spell (90 with chance g, else uniform 60-90), else uniform 15-59.
    -> (g, p60 clipped), so the mean matches mean_start as closely as the bounds allow."""
    p = min(1.0, max(0.02, p60))
    m_a = (mean_start - (1 - p) * 37.0) / p
    g = (m_a - 74.5) / 15.5
    return min(1.0, max(0.0, g)), p


def quantiles(sorted_vals, qs):
    """Linear-interpolated quantiles of an ascending sequence."""
    n = len(sorted_vals)
    out = []
    for q in qs:
        pos = q * (n - 1)
        lo = int(math.floor(pos))
        hi = min(lo + 1, n - 1)
        out.append(float(sorted_vals[lo]) + (pos - lo) * (float(sorted_vals[hi]) - float(sorted_vals[lo])))
    return out
