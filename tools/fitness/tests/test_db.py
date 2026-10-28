import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db  # noqa: E402


class DbTests(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")

    def test_seed_and_migrate_idempotent(self):
        db.migrate(self.con)
        self.assertEqual(self.con.execute("SELECT MAX(version) v FROM schema_version").fetchone()["v"], 5)
        pbs = {r["distance"]: r["seconds"] for r in self.con.execute("SELECT * FROM pbs")}
        self.assertEqual(pbs, {"5k": 1503, "10k": 3130, "half": 8090})

    def test_goal_seed_and_one_active(self):
        g = db.active_goal(self.con)
        self.assertEqual((g["distance"], g["distance_m"], g["target_s"], g["race_date"]), ("5k", 5000.0, 1439, None))
        with self.assertRaises(Exception):
            self.con.execute("INSERT INTO goals(distance,distance_m,target_s,created_at,active) "
                             "VALUES('10k',10000,3000,'x',1)")
        self.con.rollback()
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM plan_weeks").fetchone()["c"], 0)
        db.upsert_plan_day(self.con, "2026-10-26", "rest", None, None)
        db.upsert_plan_day(self.con, "2026-10-26", "rest", "bonus", "ok")
        self.assertEqual(self.con.execute("SELECT adjusted FROM plan_days").fetchone()["adjusted"], "bonus")

    def test_summaries_upsert_replaces_week(self):
        db.upsert_summary(self.con, "2026-10-19", "skipped", reason="down")
        db.upsert_summary(self.con, "2026-10-19", "ok", model="m", facts={"a": 1}, bullets=["x", "y", "z"])
        db.upsert_summary(self.con, "2026-10-12", "failed", reason="bad")
        rows = self.con.execute("SELECT * FROM summaries ORDER BY week_start").fetchall()
        self.assertEqual([r["week_start"] for r in rows], ["2026-10-12", "2026-10-19"])
        self.assertEqual(rows[1]["status"], "ok")
        self.assertIsNone(rows[1]["reason"])
        self.assertEqual(json.loads(rows[1]["bullets"]), ["x", "y", "z"])

    def test_running_tables_exist(self):
        names = {r["name"] for r in self.con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"activity_zones", "activity_hr", "best_efforts"} <= names)
        db.replace_zones(self.con, 1, [(1, 10, 90.0), (2, 20, None)])
        db.replace_zones(self.con, 1, [(3, 5, 130.0)])
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM activity_zones").fetchone()["c"], 1)
        db.replace_hr_hist(self.con, 1, {140: 3.0, 141: 1.0}.items())
        db.replace_best_efforts(self.con, 1, {"1k": 300.0}, "details")
        db.replace_best_efforts(self.con, 1, {"5k": 1500.0}, "laps")
        r = self.con.execute("SELECT distance, source FROM best_efforts").fetchall()
        self.assertEqual([(x[0], x[1]) for x in r], [("5k", "laps")])

    def test_settings_round_trip(self):
        self.assertIsNone(db.get_setting(self.con, "sleep_need_h"))
        self.assertEqual(db.get_setting(self.con, "sleep_need_h", "8"), "8")
        db.set_setting(self.con, "sleep_need_h", 7.5)
        db.set_setting(self.con, "sleep_need_h", 7.25)
        self.assertEqual(db.get_setting(self.con, "sleep_need_h"), "7.25")

    def test_checkin_one_row_per_day(self):
        db.upsert_checkin(self.con, "2026-10-16", 3, ill_neck=1, note="a")
        db.upsert_checkin(self.con, "2026-10-16", 4, note="b")
        rows = self.con.execute("SELECT * FROM checkins").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["feeling"], rows[0]["ill_neck"], rows[0]["note"]), (4, 0, "b"))

    def test_daily_null_does_not_overwrite(self):
        db.upsert_daily(self.con, "2026-10-16", rhr=50, hrv_avg=40)
        db.upsert_daily(self.con, "2026-10-16", rhr=None, sleep_s=1000)
        r = self.con.execute("SELECT * FROM daily").fetchone()
        self.assertEqual((r["rhr"], r["hrv_avg"], r["sleep_s"]), (50, 40, 1000))

    def test_activity_upsert_and_laps(self):
        for _ in range(2):
            db.upsert_activity(self.con, 7, start_local="2026-10-16 07:00:00", type="running", distance_m=5000)
            db.replace_laps(self.con, 7, [{"distance_m": 1000}, {"distance_m": None}])
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM activities").fetchone()["c"], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) c FROM laps").fetchone()["c"], 2)

    def test_pb_merge_only_faster(self):
        self.assertFalse(db.merge_pb(self.con, "5k", 1600, "2026-01-01"))
        self.assertTrue(db.merge_pb(self.con, "5k", 1400, "2026-01-01"))
        r = self.con.execute("SELECT * FROM pbs WHERE distance='5k'").fetchone()
        self.assertEqual((r["seconds"], r["source"]), (1400, "garmin"))

    def test_fiit_srpe_and_state(self):
        i = db.add_fiit(self.con, "2026-10-16", "07:30", "hiit", 45, 7)
        self.assertEqual(self.con.execute("SELECT srpe FROM fiit WHERE id=?", (i,)).fetchone()["srpe"], 315)
        db.set_state(self.con, "k", "v1")
        db.set_state(self.con, "k", "v2")
        self.assertEqual(db.get_state(self.con, "k"), "v2")
        self.assertIsNone(db.get_state(self.con, "nope"))


if __name__ == "__main__":
    unittest.main()
