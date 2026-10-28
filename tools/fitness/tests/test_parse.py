import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import garmin  # noqa: E402  (imports no garminconnect at module level)


class ParseTests(unittest.TestCase):
    def test_missing_fields_give_none(self):
        for fn in (garmin.parse_sleep, garmin.parse_hrv, garmin.parse_summary, garmin.parse_readiness,
                   garmin.parse_training_status):
            for junk in (None, {}, [], "x", {"dailySleepDTO": None}):
                self.assertTrue(all(v is None for v in fn(junk).values()), (fn.__name__, junk))

    def test_values(self):
        s = garmin.parse_sleep({"dailySleepDTO": {"sleepTimeSeconds": 25000, "sleepScores": {"overall": {"value": 80}}},
                                "restingHeartRate": 48, "avgOvernightHrv": 55.5, "hrvStatus": "BALANCED"})
        self.assertEqual((s["sleep_s"], s["sleep_score"], s["rhr"], s["hrv_avg"]), (25000, 80, 48, 55.5))
        self.assertEqual(garmin.parse_readiness([{"score": 40}, {"score": 62}])["readiness"], 62)
        t = garmin.parse_training_status({"mostRecentTrainingStatus": {"latestTrainingStatusData": {
            "1": {"trainingStatusFeedbackPhrase": "PRODUCTIVE_1", "acuteTrainingLoadDTO": {"dailyTrainingLoadAcute": 310}}}}})
        self.assertEqual((t["training_status"], t["acute_load"]), ("PRODUCTIVE_1", 310))

    def test_vo2_and_weight(self):
        self.assertEqual(garmin.parse_vo2([{"generic": {"calendarDate": "2026-10-01", "vo2MaxPreciseValue": 47.2}}]),
                         {"2026-10-01": 47.2})
        self.assertEqual(garmin.parse_vo2(None), {})
        w = garmin.parse_weights({"dateWeightList": [{"calendarDate": "2026-10-01", "weight": 80500, "bodyFat": None},
                                                     {"calendarDate": "2026-10-02", "weight": None}, "x"]})
        self.assertEqual(w, {"2026-10-01": (80.5, None)})
        self.assertEqual(garmin.parse_weights({}), {})

    def test_activity_and_laps(self):
        self.assertIsNone(garmin.parse_activity({}))
        a = garmin.parse_activity({"activityId": 5, "activityType": {"typeKey": "running"}, "distance": "5000"})
        self.assertEqual((a["id"], a["type"], a["distance_m"], a["avg_hr"]), (5, "running", 5000.0, None))
        self.assertEqual(garmin.parse_laps({}), [])
        self.assertEqual(len(garmin.parse_laps({"lapDTOs": [{"distance": 1000}, "x"]})), 1)

    def test_hr_zones(self):
        z = garmin.parse_hr_zones([{"zoneNumber": 2, "secsInZone": 120.5, "zoneLowBoundary": 114},
                                   {"zoneNumber": 1, "secsInZone": 60, "zoneLowBoundary": 95},
                                   {"zoneNumber": 6, "secsInZone": 5}, {"zoneNumber": 3}, "x", None])
        self.assertEqual(z, [(1, 60.0, 95.0), (2, 120.5, 114.0)])
        self.assertEqual(garmin.parse_hr_zones({"zones": [{"zoneNumber": 5, "secsInZone": 9}]}), [(5, 9.0, None)])
        for junk in (None, {}, [], "x", 5):
            self.assertEqual(garmin.parse_hr_zones(junk), [])

    def test_samples(self):
        d = {"metricDescriptors": [{"key": "directHeartRate", "metricsIndex": 0},
                                   {"key": "sumDuration", "metricsIndex": 1},
                                   {"key": "sumDistance", "metricsIndex": 2}],
             "activityDetailMetrics": [{"metrics": [140, 1.0, 3.5]}, {"metrics": [None, 2.0, 7.0]},
                                       {"metrics": [150, None, 9.0]}, {"metrics": [150]}, {"x": 1}, "x"]}
        self.assertEqual(garmin.parse_samples(d), [(1.0, 3.5, 140.0), (2.0, 7.0, None)])
        self.assertEqual(garmin.parse_samples({"metricDescriptors": [], "activityDetailMetrics": [{"metrics": [1]}]}), [])
        no_hr = {"metricDescriptors": [{"key": "sumDuration", "metricsIndex": 0}],
                 "activityDetailMetrics": [{"metrics": [1.0]}]}
        self.assertEqual(garmin.parse_samples(no_hr), [(1.0, None, None)])
        for junk in (None, {}, [], "x"):
            self.assertEqual(garmin.parse_samples(junk), [])

    def test_run_details_failures(self):
        from app import db
        con = db.connect(":memory:")
        for i, (aid, typ) in enumerate(((1, "running"), (2, "running"), (3, "cycling"))):
            db.upsert_activity(con, aid, start_local=f"2026-10-0{9 - i} 07:00:00", type=typ, distance_m=1000)
        db.replace_laps(con, 1, [{"distance_m": 1000, "duration_s": 300, "avg_hr": 140}])
        good = {"metricDescriptors": [{"key": "sumDuration", "metricsIndex": 0},
                                      {"key": "sumDistance", "metricsIndex": 1},
                                      {"key": "directHeartRate", "metricsIndex": 2}],
                "activityDetailMetrics": [{"metrics": [float(i), i * 3.0, 140]} for i in range(400)]}

        class Api:
            def __init__(self, fail):
                self.fail = fail

            def get_activity_hr_in_timezones(self, aid):
                if aid in self.fail:
                    raise ValueError("404")
                return [{"zoneNumber": 1, "secsInZone": 60, "zoneLowBoundary": 90}]

            def get_activity_details(self, aid, a=0, b=0):
                return good

        import types
        fake = types.ModuleType("garminconnect")
        fake.GarminConnectAuthenticationError = type("A", (Exception,), {})
        fake.GarminConnectTooManyRequestsError = type("T", (Exception,), {})
        had = sys.modules.get("garminconnect")
        sys.modules["garminconnect"] = fake
        old = garmin.CALL_DELAY_S
        garmin.CALL_DELAY_S = 0
        try:
            api = Api({"1"})
            for n in range(3):    # activity 1 (newest) fails: each sync stops there, activity 2 waits
                f = garmin._Fetcher()
                garmin._run_details(con, f, api)
                self.assertEqual(db.get_state(con, "detail_fail:1"), str(n + 1))
            self.assertEqual(con.execute("SELECT COUNT(*) c FROM raw WHERE kind='details' AND key='1'").fetchone()["c"], 1)
            self.assertEqual(db.get_state(con, "detail_fail:1"), "3")
            f = garmin._Fetcher()
            garmin._run_details(con, f, api)     # 1 is skipped now, 2 succeeds, the cycling ride is ignored
            self.assertEqual(con.execute("SELECT COUNT(*) c FROM activity_zones WHERE activity_id=2").fetchone()["c"], 1)
            self.assertGreater(con.execute("SELECT COUNT(*) c FROM activity_hr WHERE activity_id=2").fetchone()["c"], 0)
            self.assertEqual(con.execute("SELECT source FROM best_efforts WHERE activity_id=2 AND distance='1k'"
                                         ).fetchone()[0], "details")
            self.assertIsNone(con.execute("SELECT 1 FROM raw WHERE key='3'").fetchone())
        finally:
            garmin.CALL_DELAY_S = old
            if had is None:
                del sys.modules["garminconnect"]
            else:
                sys.modules["garminconnect"] = had

    def test_backoff_beats_cached_client(self):
        import tempfile
        import time
        from app import db
        with tempfile.TemporaryDirectory() as d:
            con = db.connect(os.path.join(d, "t.db"))
            db.set_state(con, "backoff_until", time.time() + 3600)
            old = garmin._api
            garmin._api = object()
            try:
                with self.assertRaises(garmin.Backoff):
                    garmin.get_api(con)
            finally:
                garmin._api = old


if __name__ == "__main__":
    unittest.main()
