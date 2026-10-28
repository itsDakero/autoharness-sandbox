"""Team goals model, fits (numpy / scipy / penaltyblog)."""
import math

import numpy as np
from scipy.optimize import minimize

MIN_MATCHES = 60
RIDGE = 0.05
LAM_MIN, LAM_MAX = 0.05, 6.0


def implied_goals(prices, rho):
    """Odds prices (core.median_prices) -> {lh, la, rho, ou: bool} or None.
    Power-method de-vig, then expected goals matched to 1X2 (+ over/under 2.5 when present). Never raises."""
    try:
        from penaltyblog import models as pm
        from penaltyblog.implied import calculate_implied
        if not all(k in prices for k in ("home", "draw", "away")):
            return None
        p = calculate_implied([prices["home"], prices["draw"], prices["away"]], method="power").probabilities
        if "over" in prices and "under" in prices:
            q = calculate_implied([prices["over"], prices["under"]], method="power").probabilities
            res = pm.goal_expectancy_extended(p[0], p[1], p[2], q[0], q[1], remove_overround=False)
            used_rho, ou = res.get("implied_rho"), True
        else:
            res = pm.goal_expectancy(p[0], p[1], p[2], dc_adj=True, rho=rho, remove_overround=False)
            used_rho, ou = rho, False
        if not res.get("success"):
            return None
        lh, la = float(res["home_exp"]), float(res["away_exp"])
        if not (LAM_MIN <= lh <= LAM_MAX and LAM_MIN <= la <= LAM_MAX):
            return None
        if used_rho is None or not math.isfinite(float(used_rho)):
            used_rho = rho
        return {"lh": lh, "la": la, "rho": float(used_rho), "ou": ou}
    except Exception:
        return None


def fit_ratings(rows, xi, ref_date):
    """rows: [{date, home, away, gh, ga}] with continuous targets (market lambdas or non-penalty xG).
    Weighted quasi-Poisson log-linear fit: log lh = mu + home + att_h - def_a, log la = mu + att_a - def_h.
    Time weights exp(-xi * days) from penaltyblog. Returns params or None with fewer than 60 matches."""
    from penaltyblog.models import dixon_coles_weights
    rows = [r for r in rows if r["date"] <= ref_date]
    if len(rows) < MIN_MATCHES:
        return None
    teams = sorted({r["home"] for r in rows} | {r["away"] for r in rows})
    idx = {t: i for i, t in enumerate(teams)}
    n = len(teams)
    hi = np.array([idx[r["home"]] for r in rows])
    ai = np.array([idx[r["away"]] for r in rows])
    yh = np.array([float(r["gh"]) for r in rows])
    ya = np.array([float(r["ga"]) for r in rows])
    w = np.asarray(dixon_coles_weights([r["date"] for r in rows], xi, ref_date), dtype=float)

    def f(p):
        att, de = p[2:2 + n], p[2 + n:]
        eh = p[0] + p[1] + att[hi] - de[ai]
        ea = p[0] + att[ai] - de[hi]
        lh, la = np.exp(eh), np.exp(ea)
        loss = np.sum(w * (lh - yh * eh)) + np.sum(w * (la - ya * ea)) + RIDGE * (att @ att + de @ de)
        rh, ra = w * (lh - yh), w * (la - ya)
        g = np.zeros_like(p)
        g[0] = rh.sum() + ra.sum()
        g[1] = rh.sum()
        np.add.at(g, 2 + hi, rh)
        np.add.at(g, 2 + ai, ra)
        np.add.at(g, 2 + n + ai, -rh)
        np.add.at(g, 2 + n + hi, -ra)
        g[2:2 + n] += 2 * RIDGE * att
        g[2 + n:] += 2 * RIDGE * de
        return loss, g

    x0 = np.zeros(2 + 2 * n)
    x0[0] = math.log(max(float(np.mean(np.concatenate([yh, ya]))), 0.1))
    res = minimize(f, x0, jac=True, method="L-BFGS-B")
    if not np.all(np.isfinite(res.x)):
        return None
    mu, home = float(res.x[0]), float(res.x[1])
    att, de = res.x[2:2 + n], res.x[2 + n:]
    mu += float(att.mean() - de.mean())
    att, de = att - att.mean(), de - de.mean()
    return {"mu": mu, "home": home, "att": {t: float(att[idx[t]]) for t in teams},
            "def": {t: float(de[idx[t]]) for t in teams}, "n": len(rows)}


def log_lambdas(fit, home, away):
    """(log lh, log la) from a ratings fit, or None when either team is unknown to it."""
    if fit is None or home not in fit["att"] or away not in fit["att"]:
        return None
    return (fit["mu"] + fit["home"] + fit["att"][home] - fit["def"][away],
            fit["mu"] + fit["att"][away] - fit["def"][home])


def log_means(fit):
    """League mean log rates (home side, away side) of a fit."""
    return fit["mu"] + fit["home"], fit["mu"]
