import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from model import pcore  # noqa: E402  (stdlib only)


def boot(**over):
    sc = {"long_play": 2, "short_play": 1, "goals_conceded": {"DEF": -1, "FWD": 0, "GKP": -1, "MID": 0},
          "saves": 1, "goals_scored": {"DEF": 6, "FWD": 4, "GKP": 10, "MID": 5}, "assists": 3,
          "clean_sheets": {"DEF": 4, "FWD": 0, "GKP": 4, "MID": 1}, "penalties_missed": -2, "yellow_cards": -1,
          "red_cards": -3, "own_goals": -2, "bonus": 1,
          "defensive_contribution": {"DEF": 2, "FWD": 2, "GKP": 0, "MID": 2}}
    sc.update(over)
    return {"game_config": {"scoring": sc}}


class Scoring(unittest.TestCase):
    def test_parse(self):
        s = pcore.scoring_from_bootstrap(boot())
        self.assertEqual(s["goals_scored"], {1: 10.0, 2: 6.0, 3: 5.0, 4: 4.0})
        self.assertEqual(s["assists"][3], 3.0)
        self.assertEqual(s["defensive_contribution"][2], 2.0)

    def test_missing_key_raises(self):
        b = boot()
        del b["game_config"]["scoring"]["clean_sheets"]
        with self.assertRaises(ValueError):
            pcore.scoring_from_bootstrap(b)
        with self.assertRaises(ValueError):
            pcore.scoring_from_bootstrap({"elements": []})
        with self.assertRaises(ValueError):
            pcore.scoring_from_bootstrap(boot(goals_scored={"DEF": 6}))


class Availability(unittest.TestCase):
    def test_cases(self):
        a = pcore.availability
        self.assertEqual([a("u", 100, k) for k in range(3)], [0.0, 0.0, 0.0])
        self.assertEqual(a("a", None, 0), 1.0)
        self.assertEqual(a("d", 25, 0), 0.25)
        self.assertEqual(a("d", 25, 1), 0.75)
        self.assertEqual(a("d", 75, 1), 1.0)
        self.assertEqual(a("d", 25, 2), 1.0)
        self.assertEqual(a("i", 0, 0), 0.0)
        self.assertEqual(a("i", None, 0), 0.0)


class Bonus(unittest.TestCase):
    def test_ties(self):
        self.assertEqual(pcore.bonus_points([30, 30, 20]), [3, 3, 1])
        self.assertEqual(pcore.bonus_points([30, 20, 20]), [3, 2, 2])
        self.assertEqual(pcore.bonus_points([30, 30, 30, 20]), [3, 3, 3, 0])
        self.assertEqual(pcore.bonus_points([40, 30, 20, 10]), [3, 2, 1, 0])


class Rates(unittest.TestCase):
    def test_empty_log_is_prior(self):
        self.assertEqual(pcore.minutes_params([]), pcore.PRIOR_MINUTES)
        self.assertEqual(pcore.rate90([], "xg", 0.25), 0.25)

    def test_regular_starter(self):
        rows = [{"kickoff_time": f"2026-09-{i:02d}T14:00:00Z", "minutes": 90, "starts": 1, "expected_goals": "0.5",
                 "tackles": 1, "clearances_blocks_interceptions": 2, "recoveries": 5} for i in range(1, 11)]
        log = pcore.match_log(rows, 3)
        self.assertEqual(log[0]["defcon"], 8.0)  # MID: cbi + tackles + recoveries
        self.assertEqual(pcore.match_log(rows, 2)[0]["defcon"], 3.0)
        mp = pcore.minutes_params(log)
        self.assertGreater(mp["p_start"], 0.7)
        self.assertGreater(mp["m_start"], 85)
        self.assertGreater(pcore.rate90(log, "xg", 0.1), 0.25)

    def test_override_minutes_double(self):
        self.assertEqual(pcore.override_minutes(90, 2), [("start", 45.0)] * 2)
        self.assertEqual(pcore.override_minutes(60, 1), [("start", 60.0)])
        self.assertEqual(pcore.override_minutes(40, 2), [("sub", 20.0)] * 2)
        self.assertEqual(pcore.override_minutes(0, 2), [("out", 0.0)] * 2)

    def test_binom_and_quantiles(self):
        self.assertEqual(pcore.defcon_binom_n(0.01), 1)
        self.assertEqual(pcore.defcon_binom_n(5.7), 30)
        self.assertEqual(pcore.quantiles([1, 2, 3, 4, 5], (0.5, 0.0, 1.0)), [3.0, 1.0, 5.0])
        self.assertEqual(pcore.norm_name("Martin Ødegaard"), "martin odegaard")


if __name__ == "__main__":
    unittest.main()
