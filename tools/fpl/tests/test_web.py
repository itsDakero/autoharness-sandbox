import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from web import projections as pj  # noqa: E402  (pure module, no third-party imports)

U = dt.timezone.utc


def fx(event, h, a, dh=3, da=3):
    return {"event": event, "team_h": h, "team_a": a, "team_h_difficulty": dh, "team_a_difficulty": da}


def player(i, team, ep, form=2.0, chance=None):
    return {"id": i, "team": team, "ep_next": str(ep), "form": str(form), "chance_of_playing_next_round": chance}


class Maths(unittest.TestCase):
    def test_scales_double_and_blank(self):
        sc = pj.fixture_scales([fx(5, 1, 2, 2, 5), fx(5, 1, 3, 4, 3), fx(6, 2, 3)])
        self.assertEqual(sc[5][1], [1.1, 0.85])  # team 1 has two fixtures in GW5
        self.assertEqual(sc[5][2], [0.7])
        self.assertNotIn(1, sc[6])                # blank for team 1 in GW6

    def test_fpl_ep(self):
        sc = pj.fixture_scales([fx(5, 1, 2, 2, 5), fx(6, 1, 2, 4, 5), fx(7, 2, 1)])
        rows = pj.build_fpl_ep([player(10, 1, 5.5)], sc, {10: [90, 90, 60, 0, 90, 90]}, 5, 3)
        by = {r["gw"]: r for r in rows}
        base = 5.5 / 1.1
        self.assertAlmostEqual(by[5]["pts"], 5.5)
        self.assertAlmostEqual(by[6]["pts"], base * 0.85)
        self.assertEqual(by[7]["pts"], 3 * 0 + base * 1.0)  # team 1 away vs 2: difficulty 3 -> scale 1.0
        self.assertAlmostEqual(by[5]["xmins"], (90 + 60 + 0 + 90 + 90) / 5)

    def test_double_adds_up_and_blank_is_zero(self):
        sc = pj.fixture_scales([fx(5, 1, 2), fx(6, 1, 2), fx(6, 3, 1), fx(7, 2, 3)])
        rows = {r["gw"]: r for r in pj.build_fpl_ep([player(10, 1, 4.0)], sc, {}, 5, 3)}
        self.assertAlmostEqual(rows[6]["pts"], 8.0)
        self.assertEqual(rows[7]["pts"], 0.0)
        self.assertEqual(rows[7]["xmins"], 0.0)
        self.assertEqual(rows[5]["xmins"], 45.0)  # no history -> default

    def test_no_ep_falls_back_to_form_for_later_weeks(self):
        sc = pj.fixture_scales([fx(5, 1, 2), fx(6, 1, 2)])
        rows = {r["gw"]: r for r in pj.build_fpl_ep([player(10, 1, 0, form=3.0)], sc, {}, 5, 2)}
        self.assertEqual(rows[5]["pts"], 0.0)
        self.assertAlmostEqual(rows[6]["pts"], 3.0)

    def test_chance_of_playing_next_gw_only(self):
        sc = pj.fixture_scales([fx(5, 1, 2), fx(6, 1, 2)])
        rows = {r["gw"]: r for r in pj.build_fpl_ep([player(10, 1, 4.0, chance=50)], sc, {10: [90]}, 5, 2)}
        self.assertAlmostEqual(rows[5]["xmins"], 45.0)
        self.assertAlmostEqual(rows[6]["xmins"], 90.0)


class Overrides(unittest.TestCase):
    def setUp(self):
        self.sc = pj.fixture_scales([fx(5, 1, 2), fx(6, 1, 2), fx(6, 3, 1)])
        self.rows = [{"element": 10, "gw": 5, "pts": 4.0, "xmins": 90.0}, {"element": 10, "gw": 6, "pts": 8.0, "xmins": 180.0}]

    def test_out_zeroes(self):
        r = pj.apply_overrides(self.rows, [{"element": 10, "gw": 5, "xmins": 0.0}], {}, self.sc, {10: 1})
        self.assertEqual((r[0]["pts"], r[0]["xmins"]), (0.0, 0.0))
        self.assertEqual(r[1]["pts"], 8.0)

    def test_scaled_and_capped(self):
        r = pj.apply_overrides(self.rows, [{"element": 10, "gw": 5, "xmins": 45.0}], {}, self.sc, {10: 1})
        self.assertAlmostEqual(r[0]["pts"], 2.0)
        low = [{"element": 10, "gw": 5, "pts": 4.0, "xmins": 30.0}]
        r = pj.apply_overrides(low, [{"element": 10, "gw": 5, "xmins": 90.0}], {}, self.sc, {10: 1})
        self.assertAlmostEqual(r[0]["pts"], 6.0)  # capped at x1.5

    def test_from_zero_minutes_uses_form(self):
        z = [{"element": 10, "gw": 5, "pts": 0.0, "xmins": 0.0}]
        r = pj.apply_overrides(z, [{"element": 10, "gw": 5, "xmins": 90.0}], {10: 3.0}, self.sc, {10: 1})
        self.assertAlmostEqual(r[0]["pts"], 3.0)

    def test_blank_gw_stays_zero(self):
        z = [{"element": 10, "gw": 9, "pts": 0.0, "xmins": 0.0}]
        r = pj.apply_overrides(z, [{"element": 10, "gw": 9, "xmins": 90.0}], {10: 3.0}, self.sc, {10: 1})
        self.assertEqual(r[0]["pts"], 0.0)

    def test_parse_and_roundtrip_tolerates_garbage(self):
        text = ("element,gw,xmins,note,updated_at\n10,5,out,injured,2026-10-26\n10,6,60,,\nx,5,30,,\n"
                "11,5,500,,\n12,5\n\n")
        good, bad = pj.parse_overrides(text)
        self.assertEqual([(o["element"], o["gw"], o["xmins"]) for o in good], [(10, 5, 0.0), (10, 6, 60.0)])
        self.assertEqual(len(bad), 3)
        again, _ = pj.parse_overrides(pj.dump_overrides(good))
        self.assertEqual(good, again)

    def test_bad_header_and_empty(self):
        self.assertEqual(pj.parse_overrides(""), ([], []))
        good, bad = pj.parse_overrides("a,b\n1,2\n")
        self.assertEqual(good, [])
        self.assertTrue(bad)

    def test_split_outside_horizon_or_unknown(self):
        ovs = [{"element": 10, "gw": 5, "xmins": 0}, {"element": 10, "gw": 3, "xmins": 0},
               {"element": 10, "gw": 20, "xmins": 0}, {"element": 99, "gw": 5, "xmins": 0}]
        active, ignored = pj.split_overrides(ovs, [10], 5, 8)
        self.assertEqual(len(active), 1)
        self.assertEqual(len(ignored), 3)


class Source(unittest.TestCase):
    now = dt.datetime(2026, 11, 1, tzinfo=U)

    def cand(self, source, days, gws=(5,)):
        return {"source": source, "path": f"/x/{source}", "generated_at": self.now - dt.timedelta(days=days), "gws": set(gws)}

    def test_auto_prefers_fresh_other_source(self):
        c, _ = pj.pick_source([self.cand("fpl-ep", 0), self.cand("model", 2), self.cand("model2", 1)], "auto", 5, self.now)
        self.assertEqual(c["source"], "model2")

    def test_auto_ignores_old_or_not_covering(self):
        self.assertIsNone(pj.pick_source([self.cand("model", 9)], "auto", 5, self.now)[0])
        self.assertIsNone(pj.pick_source([self.cand("model", 1, gws=(6,))], "auto", 5, self.now)[0])
        self.assertIsNone(pj.pick_source([], "auto", 5, self.now)[0])

    def test_named_source(self):
        c, note = pj.pick_source([self.cand("model", 20), self.cand("fpl-ep", 0)], "model", 5, self.now)
        self.assertEqual(c["source"], "model")  # an explicit choice has no age limit
        c, note = pj.pick_source([self.cand("fpl-ep", 0)], "model", 5, self.now)
        self.assertIsNone(c)
        self.assertIn("model", note)


class Chips(unittest.TestCase):
    def test_left_per_half(self):
        left = pj.chips_left([{"name": "wildcard", "event": 4}, {"name": "3xc", "event": 22}, {"name": "weird", "event": 1}, {}])
        self.assertNotIn("wildcard", left[1])
        self.assertIn("wildcard", left[2])
        self.assertNotIn("3xc", left[2])
        self.assertIn("3xc", left[1])

    def test_windows_within_horizon(self):
        left = pj.chips_left([{"name": "wildcard", "event": 4}])
        limits, allowed = pj.chip_settings(left, list(range(17, 25)), True)
        self.assertEqual(allowed["wc"], [20, 21, 22, 23, 24])   # only the second half's weeks
        self.assertEqual(allowed["fh"], list(range(17, 25)))    # unused in both halves
        self.assertEqual(limits["wc"], 1)

    def test_off_means_zero(self):
        limits, allowed = pj.chip_settings(pj.chips_left([]), [5, 6], False)
        self.assertEqual(set(limits.values()), {0})
        self.assertEqual(allowed, {})

    def test_all_used_in_half_gives_no_window(self):
        used = [{"name": n, "event": 3} for n in pj.CHIPS]
        limits, allowed = pj.chip_settings(pj.chips_left(used), [5, 6, 7], True)
        self.assertEqual(allowed, {})
        self.assertEqual(set(limits.values()), {0})


class Deadline(unittest.TestCase):
    now = dt.datetime(2026, 11, 6, 18, 0, tzinfo=U)

    def test_window(self):
        d = self.now + dt.timedelta(hours=24)
        self.assertTrue(pj.deadline_due(d, self.now, [], 12))
        self.assertTrue(pj.deadline_due(self.now + dt.timedelta(hours=36), self.now, [], 12))
        self.assertFalse(pj.deadline_due(self.now + dt.timedelta(hours=37), self.now, [], 12))
        self.assertFalse(pj.deadline_due(self.now - dt.timedelta(minutes=1), self.now, [], 12))

    def test_only_once_per_gw(self):
        d = self.now + dt.timedelta(hours=24)
        self.assertFalse(pj.deadline_due(d, self.now, [12], 12))
        self.assertTrue(pj.deadline_due(d, self.now, [11], 12))
        self.assertTrue(pj.deadline_due(d, self.now, None, 12))


class JobsText(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from web import jobs  # needs pandas via collector.store; skipped where it is not installed
        except ImportError as e:
            raise unittest.SkipTest(f"job module needs the container's packages: {e}")
        cls.jobs = jobs

    def test_line_with_moves(self):
        d = dt.datetime(2026, 11, 6, 18, 30)  # a Friday
        step = {"out": ["A", "B"], "in": ["C", "D"], "captain": "Haaland", "vice": "Salah", "chip": None}
        line = self.jobs.deadline_line(12, d, step, 2, "fpl-ep")
        self.assertIn("deadline Fri 18:30", line)
        self.assertIn("A -> C, B -> D", line)
        self.assertIn("captain Haaland (vice Salah); chip none; source fpl-ep", line)

    def test_roll_and_failure(self):
        d = dt.datetime(2026, 11, 6, 18, 30)
        self.assertIn("roll, 3 FTs", self.jobs.deadline_line(12, d, {"captain": "X"}, 3, "s"))
        bad = self.jobs.deadline_line(12, d, {}, None, "s", failure="solver timed out")
        self.assertIn("solver failed (solver timed out), no plan", bad)
        self.assertNotIn("captain", bad)

    def test_fresh_plan(self):
        now = dt.datetime(2026, 11, 6, 18, 0, tzinfo=U)
        latest = {"last_run": {"ok": True}, "plan": {"12": {}}, "plan_at": (now - dt.timedelta(hours=3)).isoformat(),
                  "plan_next_gw": 12}
        self.assertTrue(self.jobs.plan_is_fresh(latest, 12, now))
        self.assertFalse(self.jobs.plan_is_fresh(latest, 13, now))
        self.assertFalse(self.jobs.plan_is_fresh({**latest, "last_run": {"ok": False}}, 12, now))
        self.assertFalse(self.jobs.plan_is_fresh({**latest, "plan_at": (now - dt.timedelta(hours=13)).isoformat()}, 12, now))


if __name__ == "__main__":
    unittest.main()
