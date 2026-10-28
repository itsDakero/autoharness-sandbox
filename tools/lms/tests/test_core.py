import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, oddsapi, ranking, rounds  # noqa: E402

U = rounds.UTC


def utc(*a):
    return dt.datetime(*a, tzinfo=U)


class Margin(unittest.TestCase):
    def test_sums_to_one(self):
        p = ranking.implied(1.5, 4.0, 6.0)
        self.assertAlmostEqual(sum(p), 1.0)
        self.assertGreater(p[0], p[1])

    def test_average_and_best(self):
        agg = ranking.aggregate([(2.0, 3.5, 4.0), (2.2, 3.4, 3.6)])
        self.assertAlmostEqual(agg["p_home"] + agg["p_draw"] + agg["p_away"], 1.0)
        self.assertEqual(agg["best_home"], 2.2)
        self.assertEqual(agg["best_away"], 4.0)


class Grouping(unittest.TestCase):
    def test_blocks(self):
        # 2026-10-27 is a Tuesday
        self.assertEqual(rounds.round_key(utc(2026, 10, 27, 19, 45)), "2026-10-27")
        self.assertEqual(rounds.round_key(utc(2026, 10, 29, 19, 45)), "2026-10-27")  # Thu
        self.assertEqual(rounds.round_key(utc(2026, 10, 30, 19, 45)), "2026-10-30")  # Fri
        self.assertEqual(rounds.round_key(utc(2026, 11, 2, 12, 0)), "2026-10-30")    # Mon
        self.assertEqual(rounds.round_key(utc(2026, 11, 3, 19, 45)), "2026-11-03")   # next Tue

    def test_london_time(self):
        # Clocks went back on 25 Oct 2026, so London = UTC on the 27th; in July it is UTC+1
        self.assertEqual(rounds.round_key(utc(2026, 10, 26, 23, 30)), "2026-10-23")  # Mon night, still Fri block
        self.assertEqual(rounds.to_london(utc(2026, 10, 27, 12, 0)).hour, 12)
        self.assertEqual(rounds.to_london(utc(2026, 7, 1, 12, 0)).hour, 13)
        self.assertEqual(rounds.from_london(dt.datetime(2026, 7, 1, 13, 0)), utc(2026, 7, 1, 12, 0))
        # Tuesday 00:30 BST (Mon 23:30 UTC) belongs to the Tuesday block
        self.assertEqual(rounds.round_key(utc(2026, 7, 6, 23, 30)), "2026-07-07")


def fx(eid, league, home, away, commence="2026-10-27T19:45:00Z"):
    return {"event_id": eid, "league": league, "home": home, "away": away, "commence": commence}


class Pool(unittest.TestCase):
    def test_fallback(self):
        champ = fx("1", rounds.CHAMP, "A", "B")
        l1 = fx("2", "soccer_england_league1", "C", "D")
        self.assertEqual(rounds.pool_leagues([champ, l1]), (rounds.CHAMP,))
        self.assertEqual(rounds.pool_fixtures([champ, l1]), [champ])
        self.assertEqual(rounds.pool_leagues([l1]), rounds.LOWER)

    def test_deadline(self):
        a = fx("1", rounds.CHAMP, "A", "B", "2026-10-27T19:45:00Z")
        b = fx("2", rounds.CHAMP, "C", "D", "2026-10-27T19:00:00Z")
        self.assertEqual(rounds.default_deadline([a, b]), utc(2026, 10, 27, 18, 30))


class UsedTeams(unittest.TestCase):
    def test_exclusion(self):
        fixtures = [fx("1", rounds.CHAMP, "A", "B"), fx("2", rounds.CHAMP, "C", "D")]
        odds = {"1": [(1.5, 4.0, 6.0)], "2": [(2.5, 3.2, 2.8)]}
        rows = ranking.rank(fixtures, odds, {"A"}, {"C"})
        self.assertEqual({r["team"] for r in rows[-2:]}, {"A", "C"})
        names = [r["team"] for r in ranking.top(rows)]
        self.assertNotIn("A", names)
        self.assertNotIn("C", names)
        self.assertEqual(names, ["D", "B"])

    def test_no_odds_not_ranked(self):
        rows = ranking.rank([fx("1", rounds.CHAMP, "A", "B")], {"1": []}, set(), set())
        self.assertEqual(ranking.top(rows), [])
        self.assertIsNone(rows[0]["p_win"])

    def test_db_used_and_void(self):
        con = db.connect(":memory:")
        g = db.new_game(con)
        db.add_pick(con, g, "2026-10-27", "A", result="through")
        db.add_pick(con, g, "2026-10-30", "B", result="void")
        self.assertEqual(db.used_teams(con, g), {"A"})
        self.assertEqual(db.voided_teams(con, g, "2026-10-30"), {"B"})
        self.assertTrue(db.claim(con, "x"))
        self.assertFalse(db.claim(con, "x"))


class Parsing(unittest.TestCase):
    def ev(self, names):
        return [{"id": "e1", "home_team": "A", "away_team": "B", "bookmakers": [
            {"key": "bk", "markets": [{"key": "h2h", "outcomes": [{"name": n, "price": 2.0} for n in names]}]}]}]

    def test_ok(self):
        res, bad = oddsapi.parse_odds("l", self.ev(["A", "B", "Draw"]))
        self.assertEqual(res["e1"][0][0], "bk")
        self.assertEqual(bad, 0)

    def test_odd_names_raise(self):
        with self.assertRaises(oddsapi.OddsError):
            oddsapi.parse_odds("l", self.ev(["A FC", "B", "Draw"]))

    def test_empty_raises(self):
        with self.assertRaises(oddsapi.OddsError):
            oddsapi.parse_odds("l", [])


class EmptyEvents(unittest.TestCase):
    def test_empty_list_keeps_fixtures(self):
        from app import jobs
        con = db.connect(":memory:")
        now = utc(2026, 10, 26, 12, 0)
        ev = {"id": "e1", "league": rounds.CHAMP, "home": "A", "away": "B", "commence": "2026-10-30T19:45:00Z"}
        db.upsert_fixture(con, ev, "2026-10-30")
        con.commit()
        orig = oddsapi.events
        try:
            oddsapi.events = lambda lg: []
            with self.assertRaises(oddsapi.OddsError):
                jobs.refresh_events(con, now)
        finally:
            oddsapi.events = orig
        self.assertEqual(db.get_fixture(con, "e1")["gone"], 0)
        self.assertEqual(db.team_names(con), ["A", "B"])


class StuckPick(unittest.TestCase):
    def test_stuck_line_once(self):
        from app import jobs
        con = db.connect(":memory:")
        g = db.new_game(con)
        db.add_pick(con, g, "2026-10-27", "A", kickoff="2026-10-27T19:45:00Z")
        self.assertEqual(jobs.notices(con, utc(2026, 10, 28, 1, 0)), [])
        out = jobs.notices(con, utc(2026, 10, 28, 2, 0))
        self.assertEqual(len(out), 1)
        self.assertIn("no result yet for A (round 2026-10-27)", out[0])
        self.assertEqual(jobs.notices(con, utc(2026, 10, 28, 9, 0)), [])


if __name__ == "__main__":
    unittest.main()
