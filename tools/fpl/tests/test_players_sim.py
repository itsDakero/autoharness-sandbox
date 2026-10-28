import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    import numpy as np
    from model import pcore, players
except ImportError:  # the host has no numpy; the image does
    np = None

SC = {"long_play": 2, "short_play": 1, "goals_conceded": {1: -1, 2: -1, 3: 0, 4: 0}, "saves": 1,
      "goals_scored": {1: 10, 2: 6, 3: 5, 4: 4}, "assists": 3, "clean_sheets": {1: 4, 2: 4, 3: 1, 4: 0},
      "penalties_missed": -2, "yellow_cards": -1, "red_cards": -3, "own_goals": -2, "bonus": 1,
      "defensive_contribution": {1: 0, 2: 2, 3: 2, 4: 2}}
SC = {k: (v if isinstance(v, dict) else {t: v for t in (1, 2, 3, 4)}) for k, v in SC.items()}


def squad(base):
    types = [1, 2, 2, 2, 2, 3, 3, 3, 4, 4, 4]
    out = []
    for i, t in enumerate(types):
        out.append({"el": base + i, "type": t, "avail": 1.0, "fixed": None, "p_start": 1.0, "m_start": 90.0,
                    "p60": 1.0, "p_sub": 0.0, "m_sub": 20.0, "xg90": [0, .03, .03, .03, .03, .1, .1, .1, .3, .3, .3][i],
                    "xa90": 0.08, "def90": 0.0 if t == 1 else 6.0, "save90": 3.0 if t == 1 else 0.0, "yel90": 0.17,
                    "bps90": 15.0, "taker": i == 8})
    return out


@unittest.skipUnless(np is not None, "numpy not installed")
class Sim(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # fixed matrix: home 0-3 goals, away 0-2 goals (rows = home goals)
        cls.m = np.array([[0.20, 0.12, 0.04], [0.18, 0.12, 0.04], [0.10, 0.07, 0.02], [0.06, 0.04, 0.01]])
        cls.m = cls.m / cls.m.sum()
        cls.home, cls.away = squad(100), squad(200)
        cls.home.append({**squad(300)[1], "el": 399, "avail": 0.0, "p_start": 0.9})
        cls.res = players.simulate_fixture(cls.m, cls.home, cls.away, SC, n=6000, seed=7)

    def test_goals_credited(self):
        lam_h = float(self.m.sum(1) @ np.arange(4))
        got = sum(self.res[p["el"]]["goals"].mean() for p in self.home if p["el"] != 399)
        self.assertAlmostEqual(got / (lam_h * (1 - pcore.OG_SHARE)), 1.0, delta=0.05)

    def test_unavailable_scores_zero(self):
        r = self.res[399]
        self.assertEqual(float(np.abs(r["pts"]).max()), 0.0)
        self.assertEqual(float(r["mins"].max()), 0.0)

    def test_finite(self):
        for r in self.res.values():
            for v in r.values():
                self.assertTrue(np.isfinite(v).all())

    def test_clean_sheet_matches_matrix(self):
        p0 = float(self.m[:, 0].sum())  # away scores 0: home keeper keeps a clean sheet
        self.assertAlmostEqual(float(self.res[100]["cs"].mean()), p0, delta=0.02)

    def test_bonus_total(self):
        tot = sum(r["bonus"] for r in self.res.values())
        self.assertTrue((tot >= 3).all())  # someone always takes first place


if __name__ == "__main__":
    unittest.main()
