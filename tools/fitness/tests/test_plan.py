import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, plan  # noqa: E402

GOAL = {"id": 1, "distance": "5k", "distance_m": 5000.0, "target_s": 1439, "race_date": None}
# Monday 2026-10-26 is the week used below; Saturday is 2026-10-31.
WEEK = {"week_start": "2026-10-26", "phase": "build", "week_no": 1, "easy": 0, "race_date": None}


def env(today, **kw):
    e = {"goal": GOAL, "today": today, "unit": "mi", "run_dates": set(), "fiit_dates": set(), "pdays": {},
         "checkins": [], "checkin_today": None, "readiness": None, "rec_score": None, "warning": False,
         "hrv_tone": None, "zone": None, "pc": plan.paces(GOAL, 1503)}
    e.update(kw)
    return e


def day(today, **kw):
    e = env(today, **kw)
    out = plan.compute(e, [WEEK])
    return out["today"], out


class GoalTests(unittest.TestCase):
    def test_target_parse(self):
        self.assertEqual(plan.parse_target("23:59"), 1439)
        self.assertEqual(plan.parse_target("1:45:00"), 6300)
        for bad in ("", "4:59", "6:00:01", "12", "a:b", "10:75"):
            self.assertIsNone(plan.parse_target(bad), bad)

    def test_goal_validation(self):
        t = date(2026, 10, 26)
        g, err = plan.parse_goal("5k", "", "23:59", "2027-01-10", t)
        self.assertIsNone(err)
        self.assertEqual((g["distance_m"], g["target_s"], g["race_date"]), (5000.0, 1439, "2027-01-10"))
        for args in (("7k", "", "23:59", ""), ("custom", "399", "23:59", ""), ("custom", "50001", "23:59", ""),
                     ("5k", "", "0:59", ""), ("5k", "", "10:00", "2026-10-26"), ("5k", "", "10:00", "2027-10-27"),
                     ("5k", "", "10:00", "tomorrow"), ("5k", "", "11:00", ""), ("custom", "abc", "20:00", "")):
            self.assertIsNone(plan.parse_goal(*args, t)[0], args)
        self.assertIsNotNone(plan.parse_goal("5k", "", "12:30", "", t)[0])    # exactly 2:30/km

    def test_paces(self):
        pc = plan.paces(GOAL, 1503)
        self.assertAlmostEqual(pc["p5"], 300.6)
        self.assertAlmostEqual(pc["goal"], 287.8)
        self.assertAlmostEqual(plan.paces(GOAL, None)["p5"], 287.8)   # no PB -> goal pace
        self.assertIsNone(plan.paces({"target_s": 0, "distance_m": 5000}, None))


class BlockTests(unittest.TestCase):
    def test_split_worked_examples(self):
        self.assertEqual(plan.phase_split(12, "5k", 5000), (5, 4, 2, 1))
        self.assertEqual(plan.phase_split(16, "half", 21097.5), (5, 6, 3, 2))
        self.assertEqual(plan.phase_split(1, "5k", 5000), (0, 0, 0, 1))
        self.assertEqual(plan.taper_weeks("custom", 8000), 1)
        self.assertEqual(plan.taper_weeks("custom", 15000), 2)

    def test_dated_block_and_race_row(self):
        g = dict(GOAL, race_date="2027-01-16")   # Saturday; race week starts 2027-01-11
        rows = plan.generate_weeks(g, date(2026, 10, 26))
        self.assertEqual(len(rows), 12)
        self.assertEqual([r["phase"] for r in rows].count("base"), 5)
        self.assertEqual(rows[-1]["phase"], "taper")
        self.assertEqual(rows[-1]["week_start"], "2027-01-11")
        self.assertEqual([r["race_date"] for r in rows if r["race_date"]], ["2027-01-16"])

    def test_rolling_easy_every_fourth(self):
        rows = plan.generate_weeks(GOAL, date(2026, 10, 26))
        self.assertEqual(len(rows), plan.AHEAD_WEEKS)
        self.assertEqual([r["week_no"] for r in rows if r["easy"]], [4, 8, 12])
        self.assertTrue(all(r["phase"] == "base" for r in rows))

    def test_race_passed_rolls_on_and_lazy_append(self):
        g = dict(GOAL, race_date="2026-10-10")
        self.assertEqual(plan.generate_weeks(g, date(2026, 10, 26))[0]["week_no"], 1)
        stored = [{"week_start": "2026-10-19", "phase": "taper", "week_no": 9, "easy": 0, "race_date": None},
                  {"week_start": "2026-10-26", "phase": "base", "week_no": 10, "easy": 0, "race_date": None}]
        new = plan.missing_weeks(g, stored, date(2026, 10, 27))
        self.assertEqual(new[0]["week_start"], "2026-11-02")
        self.assertEqual(new[0]["week_no"], 11)
        self.assertEqual(len(new), 12)
        self.assertEqual(plan.missing_weeks(g, stored + new, date(2026, 10, 27)), [])
        self.assertEqual(plan.missing_weeks(None, [], date(2026, 10, 27)), [])


class WeekTests(unittest.TestCase):
    def test_fixed_days(self):
        _, out = day(date(2026, 10, 26))
        days = out["weeks"][0]["days"]
        self.assertEqual([d["kind"] for d in days],
                         ["fiit", "rest", "run_club", "rest", "rest", "quality", "rest"])
        self.assertEqual(days[2]["target"], "3-4 miles steady, 9:00-9:30/mile")
        self.assertEqual(days[5]["title"], "Tempo run")      # build, week 1 (odd)
        self.assertIn("2 x 10 min at 8:28-8:44/mi", days[5]["target"])   # P5 300.6 + 15..25 s/km, x1.609
        self.assertEqual(days[0]["fiit_type"], "hiit")

    def test_weekend_by_phase_and_pace_text(self):
        for phase, no, title in (("base", 1, "Long easy run"), ("build", 2, "Intervals"),
                                 ("sharpen", 1, "Race-pace session"), ("taper", 1, "Taper sharpener")):
            wk = dict(WEEK, phase=phase, week_no=no)
            d = plan.template_week(wk, GOAL)[5]
            self.assertEqual(plan.describe(d["kind"], wk, GOAL, env(date(2026, 10, 26))["pc"], "mi")[0], title)
        wk = dict(WEEK, phase="sharpen")
        half = dict(GOAL, distance="half", distance_m=21097.5)
        self.assertIn("3 x 3 km", plan.describe("quality", wk, half, None, "km")[1])
        self.assertIn("3 x 1 mile", plan.describe("quality", wk, GOAL, None, "km")[1])
        self.assertEqual(plan.template_week(dict(WEEK, easy=1), GOAL)[5]["kind"], "easy")

    def test_fiit_resuggested_then_missed(self):
        # Monday FiiT not done: on Tuesday it is suggested Tuesday; on Wednesday (no allowed day left) missed.
        tue = plan.compute(env(date(2026, 10, 27)), [WEEK])["weeks"][0]["days"]
        self.assertEqual((tue[1]["kind"], tue[1]["status"], tue[1]["reason"]), ("fiit", "planned", "moved from Monday"))
        wed = plan.compute(env(date(2026, 10, 28)), [WEEK])["weeks"][0]["days"]
        self.assertEqual((wed[1]["kind"], wed[1]["status"]), ("fiit", "missed"))
        done = plan.compute(env(date(2026, 10, 28), fiit_dates={"2026-10-26"}), [WEEK])["weeks"][0]["days"]
        self.assertEqual((done[0]["kind"], done[0]["status"]), ("fiit", "done"))
        base = dict(WEEK, phase="base")     # weekend long_easy: Friday allowed
        thu = plan.compute(env(date(2026, 10, 29)), [base])["weeks"][0]["days"]
        self.assertEqual((thu[4]["kind"], thu[4]["status"]), ("fiit", "planned"))

    def test_done_missed_from_running_activity(self):
        out = plan.compute(env(date(2026, 10, 29), run_dates={"2026-10-28"}), [WEEK])["weeks"][0]["days"]
        self.assertEqual(out[2]["status"], "done")
        out = plan.compute(env(date(2026, 10, 29)), [WEEK])["weeks"][0]["days"]
        self.assertEqual(out[2]["status"], "missed")

    def test_missed_saturday_moves_to_sunday_only(self):
        sun = plan.compute(env(date(2026, 11, 1)), [WEEK])["weeks"][0]["days"]
        self.assertEqual((sun[5]["status"], sun[5]["reason"]), ("missed", "moved to Sunday"))
        self.assertEqual((sun[6]["kind"], sun[6]["reason"]), ("quality", "moved from Saturday (missed)"))
        self.assertEqual(sun[2]["kind"], "run_club")           # Wednesday never moves
        # Monday of next week: nothing moves into the new week, last week's Saturday stays missed
        prior = plan.week_view(WEEK, env(date(2026, 11, 2)))
        self.assertEqual((prior[5]["status"], prior[6]["kind"]), ("missed", "rest"))
        # done Saturday: no move
        ok = plan.compute(env(date(2026, 11, 1), run_dates={"2026-10-31"}), [WEEK])["weeks"][0]["days"]
        self.assertEqual((ok[5]["status"], ok[6]["kind"]), ("done", "rest"))

    def test_race_week(self):
        wk = dict(WEEK, phase="taper", race_date="2026-10-31")
        days = plan.template_week(wk, GOAL)
        self.assertEqual((days[5]["kind"], days[6]["kind"], days[0]["kind"]), ("race", "rest", "rest"))
        self.assertEqual(plan.describe("race", wk, GOAL, None, "mi"), ("Race day", "5k, goal 23:59"))


class TodayTests(unittest.TestCase):
    SAT = date(2026, 10, 31)

    def test_no_change_by_default(self):
        t, _ = day(self.SAT)
        self.assertEqual((t["kind"], t["reason"], t["adjusted"]), ("quality", None, False))

    def test_chest_is_rest(self):
        t, _ = day(self.SAT, checkin_today={"ill_chest": 1, "ill_neck": 0})
        self.assertEqual((t["kind"], t["adjusted"]), ("rest", True))
        self.assertIn("chest", t["reason"])

    def test_neck_caps_at_easy_including_run_club_and_fiit(self):
        c = {"ill_neck": 1, "ill_chest": 0}
        self.assertEqual(day(self.SAT, checkin_today=c)[0]["kind"], "easy")
        self.assertEqual(day(date(2026, 10, 28), checkin_today=c)[0]["kind"], "easy")
        t, _ = day(date(2026, 10, 26), checkin_today=c)
        self.assertEqual(t["title"], "FiiT class: mobility")

    def test_graded_return(self):
        neck = [{"date": "2026-10-29", "ill_neck": 1, "ill_chest": 0}]
        self.assertEqual(day(date(2026, 10, 30), checkins=neck)[0]["kind"], "rest")   # nothing to cap on a rest day
        self.assertEqual(day(date(2026, 10, 31), checkins=neck)[0]["kind"], "steady")  # day 2: steady cap
        chest = [{"date": "2026-10-28", "ill_neck": 0, "ill_chest": 1}]
        self.assertEqual(day(date(2026, 10, 30), checkins=chest)[0]["kind"], "rest")
        self.assertEqual(day(self.SAT, checkins=chest)[0]["kind"], "steady")           # day 3 after chest: steady
        later = [{"date": "2026-10-27", "ill_neck": 0, "ill_chest": 1}]
        self.assertEqual(day(self.SAT, checkins=later)[0]["kind"], "quality")          # day 4: normal
        self.assertEqual(day(date(2026, 10, 31), checkins=[{"date": "2026-10-30", "ill_neck": 0, "ill_chest": 1}])[0]["kind"], "easy")
        self.assertEqual(plan.last_ill(neck, date(2026, 11, 10)), None)    # beyond 7 days

    def test_soften_moves_quality_to_sunday(self):
        t, out = day(self.SAT, readiness=42)
        self.assertEqual((t["planned"], t["kind"], t["adjusted_kind"]), ("quality", "easy", "easy"))
        self.assertIn("moved to Sunday", t["reason"])
        sun = out["weeks"][0]["days"][6]
        self.assertEqual(sun["kind"], "quality")
        self.assertEqual(day(self.SAT, rec_score=30)[0]["kind"], "easy")
        self.assertEqual(day(self.SAT, warning=True)[0]["kind"], "easy")
        # Sunday with a moved quality and no free day left: steady
        wk = dict(WEEK)
        e = env(date(2026, 11, 1), readiness=40, pdays={"2026-10-31": {"planned": "quality", "adjusted": "easy"}},
                run_dates={"2026-10-31"})
        self.assertEqual(plan.compute(e, [wk])["today"]["kind"], "steady")

    def test_missing_data_changes_nothing(self):
        t, _ = day(self.SAT, readiness=None, rec_score=None, warning=False)
        self.assertEqual(t["kind"], "quality")
        t, _ = day(date(2026, 10, 30))      # free day, no readiness: no bonus
        self.assertEqual(t["kind"], "rest")

    def test_bonus_needs_everything(self):
        free = date(2026, 10, 30)
        good = dict(readiness=80, hrv_tone="good", zone="Optimal")
        self.assertEqual(day(free, **good)[0]["kind"], "bonus")
        self.assertEqual(day(free, **dict(good, readiness=74))[0]["kind"], "rest")
        self.assertEqual(day(free, **dict(good, hrv_tone="warn"))[0]["kind"], "rest")
        self.assertEqual(day(free, **dict(good, zone="High risk"))[0]["kind"], "rest")
        self.assertEqual(day(free, **dict(good, zone=None))[0]["kind"], "rest")
        self.assertEqual(day(free, **dict(good, run_dates={"2026-10-29"}))[0]["kind"], "rest")   # free day already used
        neck = [{"date": "2026-10-29", "ill_neck": 1, "ill_chest": 0}]
        self.assertEqual(day(free, **dict(good, checkins=neck))[0]["kind"], "rest")

    def test_done_today_is_not_adjusted(self):
        t, _ = day(self.SAT, readiness=30, run_dates={"2026-10-31"})
        self.assertEqual((t["kind"], t["status"]), ("quality", "done"))

    def test_no_week_row(self):
        out = plan.compute(env(date(2027, 5, 5)), [WEEK])
        self.assertIsNone(out["today"])
        self.assertEqual(out["weeks"], [])

    def test_save_goal_keeps_past_and_current(self):
        con = db.connect(":memory:")
        today = date(2026, 10, 28)
        db.insert_plan_weeks(con, 1, plan.generate_weeks(db.active_goal(con), plan.monday(today)))
        db.upsert_plan_day(con, "2026-10-27", "fiit", None, None)
        db.upsert_plan_day(con, "2026-10-30", "rest", None, None)
        g, _ = plan.parse_goal("10k", "", "50:00", "2027-01-20", today)
        db.save_goal(con, g, today)
        rows = {r["week_start"]: r for r in con.execute("SELECT * FROM plan_weeks")}
        self.assertEqual(rows["2026-10-26"]["phase"], "base")      # current week untouched
        self.assertEqual(rows["2026-10-26"]["week_no"], 1)
        self.assertEqual(rows["2026-11-02"]["week_no"], 2)
        self.assertEqual(sorted(r["date"] for r in con.execute("SELECT date FROM plan_days")), ["2026-10-27"])
        self.assertEqual(db.active_goal(con)["distance"], "10k")
        self.assertEqual(con.execute("SELECT COUNT(*) c FROM goals").fetchone()["c"], 2)
        self.assertEqual(con.execute("SELECT COUNT(*) c FROM goals WHERE active=1").fetchone()["c"], 1)


if __name__ == "__main__":
    unittest.main()
