import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from model import core  # noqa: E402  (stdlib only)

FPL = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Chelsea", "Coventry City",
       "Crystal Palace", "Everton", "Fulham", "Hull City", "Ipswich Town", "Leeds", "Liverpool", "Man City",
       "Man Utd", "Newcastle", "Nott'm Forest", "Spurs", "Sunderland"]
FD = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea", "Crystal Palace",
      "Everton", "Fulham", "Leeds", "Liverpool", "Man City", "Man United", "Newcastle", "Nott'm Forest",
      "Sunderland", "Tottenham", "West Ham", "Wolves", "Coventry", "Hull", "Ipswich"]
US = ["Arsenal", "Aston Villa", "Bournemouth", "Brentford", "Brighton", "Burnley", "Chelsea", "Crystal Palace",
      "Everton", "Fulham", "Leeds", "Liverpool", "Manchester City", "Manchester United", "Newcastle United",
      "Nottingham Forest", "Sunderland", "Tottenham", "West Ham", "Wolverhampton Wanderers", "Coventry",
      "Hull", "Ipswich"]


class Names(unittest.TestCase):
    def test_all_sources_map_to_23_keys(self):
        fpl = {core.canon(n) for n in FPL}
        self.assertEqual(len(fpl), 20)
        fd, us = {core.canon(n) for n in FD}, {core.canon(n) for n in US}
        self.assertEqual(len(fd), 23)
        self.assertEqual(fd, us)
        self.assertTrue(fpl <= fd)
        self.assertEqual(fd - fpl, {"burnley", "west ham", "wolves"})

    def test_odds_api_style(self):
        self.assertEqual(core.canon("Brighton and Hove Albion"), core.canon("Brighton"))
        self.assertEqual(core.canon("Leicester City FC"), "leicester")
        self.assertEqual(core.canon("AFC Bournemouth"), "bournemouth")

    def test_unknown_passes_through(self):
        self.assertEqual(core.canon("Real Madrid CF"), "real madrid cf")


class Maths(unittest.TestCase):
    def test_matrix_sums_to_one_and_cs_axes(self):
        m = core.score_matrix(2.0, 0.5, -0.05)
        self.assertAlmostEqual(sum(map(sum, m)), 1.0, places=9)
        csh, csa = core.cs(m)
        self.assertGreater(csh, csa)  # strong home side keeps more clean sheets
        self.assertAlmostEqual(csh, sum(m[i][0] for i in range(11)))
        self.assertAlmostEqual(csa, sum(m[0]))
        self.assertAlmostEqual(csh, math.exp(-0.5), delta=0.03)
        ph, pd, pa = core.outcome_probs(m)
        self.assertAlmostEqual(ph + pd + pa, 1.0, places=9)
        self.assertGreater(ph, pa)

    def test_blend(self):
        self.assertAlmostEqual(core.blend(0.7, -1.0, 1.0), 0.7)
        self.assertAlmostEqual(core.blend(0.7, -1.0, 0.0), -1.0)
        self.assertAlmostEqual(core.blend(1.0, 0.0, 0.5), 0.5)

    def test_shrink(self):
        self.assertEqual(core.shrink_k(10, 10), 0.0)
        self.assertEqual(core.shrink_k(100, 10), 1.0)
        self.assertAlmostEqual(core.shrink(1.0, 0.0, 0.0), 1.0)
        self.assertAlmostEqual(core.shrink(1.0, 0.0, 1.0), 0.0)


def row(market, outcome, price, point=None, home="A", away="B"):
    return {"market": market, "outcome": outcome, "price": price, "point": point, "home": home, "away": away}


class Prices(unittest.TestCase):
    def test_median_ignores_other_lines(self):
        rows = [row("h2h", "A", 2.0), row("h2h", "A", 2.2), row("h2h", "A", 2.4), row("h2h", "Draw", 3.4),
                row("h2h", "B", 3.6), row("totals", "Over", 1.9, 2.5), row("totals", "Under", 1.95, 2.5),
                row("totals", "Over", 1.4, 1.5), row("totals", "Over", 3.5, 3.5)]
        p = core.median_prices(rows)
        self.assertEqual(p, {"home": 2.2, "draw": 3.4, "away": 3.6, "over": 1.9, "under": 1.95})

    def test_missing_draw(self):
        self.assertNotIn("draw", core.median_prices([row("h2h", "A", 2.0), row("h2h", "B", 3.0)]))


HEAD = "Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,AvgH,AvgD,AvgA,Avg>2.5,Avg<2.5,AvgCH,AvgCD,AvgCA,AvgC>2.5,AvgC<2.5\n"


class FootballData(unittest.TestCase):
    def test_bom_closing_columns(self):
        csv = "﻿" + HEAD + "E0,15/08/2025,Man United,Arsenal,0,1,2.5,3.4,2.9,1.9,1.9,2.4,3.5,3.0,1.8,2.0\n"
        r = core.parse_football_data(csv)[0]
        self.assertEqual((r["home"], r["away"], r["hg"], r["ag"]), ("man utd", "arsenal", 0, 1))
        self.assertEqual(r["prices"], {"home": 2.4, "draw": 3.5, "away": 3.0, "over": 1.8, "under": 2.0})
        self.assertEqual(str(r["date"]), "2025-08-15")

    def test_fallback_to_opening(self):
        csv = HEAD + "E0,16/08/2025,Chelsea,Fulham,2,0,1.5,4.2,6.0,1.7,2.1,,,,,\n"
        p = core.parse_football_data(csv)[0]["prices"]
        self.assertEqual(p, {"home": 1.5, "draw": 4.2, "away": 6.0, "over": 1.7, "under": 2.1})

    def test_row_without_1x2_skipped(self):
        csv = HEAD + "E0,16/08/2025,Chelsea,Fulham,2,0,,,,,,,,,,\n"
        self.assertEqual(core.parse_football_data(csv), [])


if __name__ == "__main__":
    unittest.main()
