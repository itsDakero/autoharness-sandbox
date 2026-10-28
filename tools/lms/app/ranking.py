"""Margin removal and the ranked table (pure functions)."""


def implied(home, draw, away):
    """Decimal odds -> probabilities with the bookmaker margin removed (proportional)."""
    raw = [1.0 / home, 1.0 / draw, 1.0 / away]
    s = sum(raw)
    return [x / s for x in raw]


def aggregate(lines):
    """lines: [(home, draw, away)] decimal odds, one per bookmaker.
    -> dict p_home, p_draw, p_away (averages), best_home, best_away (highest price)."""
    if not lines:
        return None
    ps = [implied(*ln) for ln in lines]
    n = len(ps)
    return {
        "p_home": sum(p[0] for p in ps) / n,
        "p_draw": sum(p[1] for p in ps) / n,
        "p_away": sum(p[2] for p in ps) / n,
        "best_home": max(ln[0] for ln in lines),
        "best_away": max(ln[2] for ln in lines),
    }


def rank(fixtures, odds, used, voided):
    """fixtures: dicts with event_id, league, home, away, commence.
    odds: {event_id: [(h, d, a)]}. used/voided: sets of team names.
    Order: eligible with odds by P(win) desc, eligible without odds, then used/voided teams."""
    rows = []
    for f in fixtures:
        agg = aggregate(odds.get(f["event_id"], []))
        for side in ("home", "away"):
            team = f[side]
            opp = f["away" if side == "home" else "home"]
            row = {
                "team": team, "opp": opp, "ha": "H" if side == "home" else "A",
                "league": f["league"], "event_id": f["event_id"], "commence": f["commence"],
                "used": team in used, "voided": team in voided,
                "p_win": None, "p_draw": None, "best": None,
            }
            if agg:
                row["p_win"] = agg["p_" + side]
                row["p_draw"] = agg["p_draw"]
                row["best"] = agg["best_" + side]
            rows.append(row)

    def key(r):
        blocked = r["used"] or r["voided"]
        return (blocked, r["p_win"] is None, -(r["p_win"] or 0), r["team"])

    rows.sort(key=key)
    return rows


def top(rows, n=3):
    return [r for r in rows if not r["used"] and not r["voided"] and r["p_win"] is not None][:n]
