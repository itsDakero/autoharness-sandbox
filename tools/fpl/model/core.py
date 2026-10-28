"""Team goals model, pure parts (stdlib only, unit tested on the host): name mapping, score matrix,
blending, odds medians, football-data.co.uk parsing."""
import csv
import datetime as dt
import io
import math
import re
import statistics

# One canonical key per club. Keys of ALIASES are names after normalisation (see canon()).
ALIASES = {
    "manchester city": "man city", "man city": "man city",
    "manchester united": "man utd", "manchester utd": "man utd", "man united": "man utd", "man utd": "man utd",
    "tottenham hotspur": "spurs", "tottenham": "spurs", "spurs": "spurs",
    "newcastle united": "newcastle", "newcastle utd": "newcastle", "newcastle": "newcastle",
    "nottingham forest": "nottm forest", "nottm forest": "nottm forest",
    "brighton and hove albion": "brighton", "brighton": "brighton",
    "wolverhampton wanderers": "wolves", "wolverhampton": "wolves", "wolves": "wolves",
    "west ham united": "west ham", "west ham": "west ham",
    "leeds united": "leeds", "leeds": "leeds",
    "leicester city": "leicester", "leicester": "leicester",
    "ipswich town": "ipswich", "ipswich": "ipswich",
    "hull city": "hull", "hull": "hull",
    "coventry city": "coventry", "coventry": "coventry",
    "sheffield utd": "sheffield utd", "sheffield united": "sheffield utd",
    "luton town": "luton", "luton": "luton",
    "west bromwich albion": "west brom", "west brom": "west brom",
    "norwich city": "norwich", "norwich": "norwich",
    "stoke city": "stoke", "cardiff city": "cardiff", "swansea city": "swansea",
    "huddersfield town": "huddersfield",
}


def canon(name):
    """FPL, Odds API, football-data and Understat spellings -> one key. Unknown names come back normalised."""
    s = str(name or "").lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", "", s)
    s = " ".join(w for w in s.split() if w not in ("fc", "afc"))
    return ALIASES.get(s, s)


def _pois(lam, n):
    return [math.exp(-lam + k * math.log(lam) - math.lgamma(k + 1)) for k in range(n)]


def score_matrix(lh, la, rho, n=11):
    """matrix[h][a]: independent Poisson with the Dixon-Coles tau on 0-0, 0-1, 1-0, 1-1, renormalised."""
    lh, la = max(lh, 1e-6), max(la, 1e-6)
    ph, pa = _pois(lh, n), _pois(la, n)
    m = [[ph[i] * pa[j] for j in range(n)] for i in range(n)]
    m[0][0] *= max(0.0, 1 - lh * la * rho)
    m[0][1] *= max(0.0, 1 + lh * rho)
    m[1][0] *= max(0.0, 1 + la * rho)
    m[1][1] *= max(0.0, 1 - rho)
    tot = sum(map(sum, m))
    return [[v / tot for v in row] for row in m]


def cs(matrix):
    """(home clean sheet, away clean sheet): home keeps one when the away side scores 0 (column 0)."""
    return sum(row[0] for row in matrix), sum(matrix[0])


def outcome_probs(matrix):
    h = d = a = 0.0
    for i, row in enumerate(matrix):
        for j, v in enumerate(row):
            if i > j:
                h += v
            elif i == j:
                d += v
            else:
                a += v
    return h, d, a


def blend(log_m, log_x, w):
    """Blend in log space; w = weight of the market fit (1 -> the market value)."""
    return w * log_m + (1 - w) * log_x


def shrink_k(gw, next_gw):
    return min(1.0, max(0.0, 0.02 * (gw - next_gw)))


def shrink(log_l, log_mean, k):
    """Pull a rating-based log goal rate toward the league mean, more for later gameweeks."""
    return (1 - k) * log_l + k * log_mean


def median_prices(odds_rows):
    """One event's odds rows -> median decimal price per outcome across bookmakers.
    Keys: home, draw, away (h2h) and over, under (totals at point 2.5 only). Missing ones are absent."""
    vals = {}
    for r in odds_rows:
        try:
            price = float(r["price"])
        except (TypeError, ValueError, KeyError):
            continue
        if not price > 1.0:
            continue
        mk, out = r.get("market"), r.get("outcome")
        key = None
        if mk == "h2h":
            if out == r.get("home"):
                key = "home"
            elif out == r.get("away"):
                key = "away"
            elif out == "Draw":
                key = "draw"
        elif mk == "totals":
            try:
                ok = float(r.get("point")) == 2.5
            except (TypeError, ValueError):
                ok = False
            if ok and out in ("Over", "Under"):
                key = out.lower()
        if key:
            vals.setdefault(key, []).append(price)
    return {k: statistics.median(v) for k, v in vals.items()}


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x else None


def _date(s):
    s = (s or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def parse_football_data(csv_text):
    """football-data.co.uk E0.csv -> [{date, home, away, hg, ag, prices}] (names canonicalised).
    Prices: closing market average (AvgCH/AvgCD/AvgCA, AvgC>2.5/AvgC<2.5); each group falls back to the
    opening Avg* columns when the closing ones are empty. Rows without a full 1X2 are skipped."""
    out = []
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("﻿")))
    for r in reader:
        d = _date(r.get("Date"))
        if d is None or not r.get("HomeTeam") or not r.get("AwayTeam"):
            continue

        def pick(*cols):
            vals = [_num(r.get(c)) for c in cols]
            return vals if all(v is not None and v > 1 for v in vals) else None
        x12 = pick("AvgCH", "AvgCD", "AvgCA") or pick("AvgH", "AvgD", "AvgA")
        if x12 is None:
            continue
        prices = {"home": x12[0], "draw": x12[1], "away": x12[2]}
        ou = pick("AvgC>2.5", "AvgC<2.5") or pick("Avg>2.5", "Avg<2.5")
        if ou:
            prices["over"], prices["under"] = ou
        hg, ag = _num(r.get("FTHG")), _num(r.get("FTAG"))
        out.append({"date": d, "home": canon(r["HomeTeam"]), "away": canon(r["AwayTeam"]),
                    "hg": None if hg is None else int(hg), "ag": None if ag is None else int(ag),
                    "prices": prices})
    return out
