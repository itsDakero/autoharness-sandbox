import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, running  # noqa: E402


def lap(d, t, hr):
    return {"distance_m": d, "duration_s": t, "avg_hr": hr}


def steady(pace_s_per_km, km, hr=140, step=1.0):
    """(t, dist, hr) samples of a constant-pace run, one per `step` seconds."""
    v = 1000.0 / pace_s_per_km
    n = int(km * pace_s_per_km / step)
    return [(i * step, i * step * v, hr) for i in range(n + 1)]


class FormulaTests(unittest.TestCase):
    def test_vdot_and_prediction(self):
        self.assertAlmostEqual(running.vdot(5000, 1197), 50.0, delta=0.3)
        self.assertAlmostEqual(running.predict_time(50, 21097.5), 5495, delta=30)

    def test_riegel(self):
        self.assertAlmostEqual(running.riegel(1500, 5000, 10000), 3127.6, delta=0.5)

    def test_half_from_dans_5k(self):
        half = running.predict_time(running.vdot(5000, 1503), 21097.5)
        self.assertAlmostEqual(8090 - half, 19 * 60, delta=120)

    def test_predictions_dict(self):
        p = running.predictions(1197)
        self.assertAlmostEqual(p["5k"][0], 1197, delta=0.5)
        self.assertAlmostEqual(p["5k"][1], 1197, delta=3)
        self.assertAlmostEqual(p["half"][1], 5495, delta=30)

    def test_zone_bounds(self):
        b = running.zone_bounds(190)
        self.assertEqual([x[0] for x in b], [95, 114, 133, 152, 171])
        self.assertEqual(b[4][1], 190)
        self.assertEqual(running.zone_bounds(None), [])

    def test_zones_from_hist_and_share(self):
        hist = [(90, 100), (100, 60), (120, 40), (140, 30), (160, 20), (175, 10)]
        z = running.zones_from_hist(hist, 190)    # 90 bpm is below 50%: no zone
        self.assertEqual(z, [60, 40, 30, 20, 10])
        self.assertAlmostEqual(running.share_easy(z), 100 / 160)
        self.assertIsNone(running.share_easy([0] * 5))
        self.assertEqual(running.zones_from_hist(hist, None), [])
        self.assertEqual((running.easy_tone(0.8), running.easy_tone(0.65), running.easy_tone(0.4)),
                         ("good", "warn", "bad"))

    def test_hr_histogram_skips_gaps(self):
        s = [(0, 0, 140), (1, 3, 140), (2, 6, 141), (100, 9, 150), (101, 12, 150), (101, 12, 150), (102, 15, None)]
        self.assertEqual(running.hr_histogram(s), {140: 2.0, 150: 2.0})
        self.assertEqual(running.hr_histogram(None), {})

    def test_max_hr(self):
        rows = [{"start_local": "2026-10-01 07:00:00", "max_hr": 188},
                {"start_local": "2026-09-01 07:00:00", "max_hr": 195},
                {"start_local": "2024-01-01 07:00:00", "max_hr": 210},
                {"start_local": "2026-08-01 07:00:00", "max_hr": 300}]
        today = date(2026, 10, 20)
        self.assertEqual(running.default_max_hr(rows, today), 195)
        self.assertEqual(running.effective_max_hr("185", rows, today), 185)
        self.assertEqual(running.effective_max_hr("abc", rows, today), 195)
        self.assertIsNone(running.effective_max_hr(None, [], today))

    def test_efficiency_and_trend(self):
        self.assertAlmostEqual(running.efficiency(6000, 1800, 150), (6000 / 30) / 150)
        self.assertIsNone(running.efficiency(3000, 1100, 150))
        self.assertTrue(running.is_easy(130, 114, 133))
        self.assertFalse(running.is_easy(133, 114, 133))
        today = date(2026, 10, 30)
        pts = [("2026-10-25", 1.2), ("2026-10-20", 1.0), ("2026-09-20", 1.0)]
        cur, prev, pct = running.ef_trend(pts, today)
        self.assertEqual((round(cur, 2), prev, round(pct, 1)), (1.1, 1.0, 10.0))
        self.assertIsNone(running.ef_trend(pts[:2], today))

    def test_decoupling(self):
        # 8 laps of 6 min, 1 km each: first half HR 140, second half HR 154 at the same pace -> EF falls 9.1%
        laps = [lap(1000, 360, 140)] * 4 + [lap(1000, 360, 154)] * 4
        self.assertAlmostEqual(running.decoupling(laps), (1 / 140 - 1 / 154) / (1 / 140) * 100, places=4)
        self.assertEqual(running.decoupling_tone(3), "good")
        self.assertEqual(running.decoupling_tone(7), "warn")
        self.assertEqual(running.decoupling_tone(12), "bad")
        self.assertIsNone(running.decoupling(laps[:3]))                 # fewer than 4 laps
        self.assertIsNone(running.decoupling([lap(1000, 300, 140)] * 8))   # 40 min
        self.assertIsNone(running.decoupling([lap(1000, 360, None)] * 8))
        self.assertIsNone(running.decoupling(None))

    def test_effective_vo2max(self):
        # 10 km in 50 min = 200 m/min; VO2 = -4.6 + 36.45 + 4.16 = 36.01; 160/180 -> (0.889-0.37)/0.64 = 0.8108; 36.01/0.8108 = 44.42
        self.assertAlmostEqual(running.effective_vo2max(10000, 3000, 160, 180), 44.417, places=2)
        self.assertIsNone(running.effective_vo2max(10000, 3000, 90, 180))     # avg/max = 0.5
        self.assertIsNone(running.effective_vo2max(10000, 3000, None, 180))
        self.assertIsNone(running.effective_vo2max(1000, 600, 150, 180))      # under 20 min
        self.assertIsNone(running.effective_vo2max(10000, 3000, 160, 0))

    def test_correction_factor_and_clamp(self):
        today = date(2026, 10, 20)
        race = {"start_local": "2026-10-10 08:00:00", "distance_m": 5000, "duration_s": 1260, "avg_hr": 175}
        eff = running.effective_vo2max(5000, 1260, 175, 190)
        self.assertAlmostEqual(running.correction_factor([race], 190, today), running.vdot(5000, 1260) / eff)
        low = dict(race, duration_s=1800, avg_hr=120)     # implied factor below 0.8
        self.assertEqual(running.correction_factor([low], 190, today), 0.8)
        high = dict(race, avg_hr=260)                     # implausible HR: implied factor above 1.2
        self.assertEqual(running.correction_factor([high], 190, today), 1.2)
        self.assertEqual(running.correction_factor([], 190, today), 1.0)
        self.assertEqual(running.correction_factor([dict(race, distance_m=2000)], 190, today), 1.0)

    def test_endurance_gap(self):
        gap = running.endurance_gap(1503, 8090)
        self.assertAlmostEqual(gap, 8090 - running.predict_time(running.vdot(5000, 1503), 21097.5))
        self.assertEqual((running.gap_tone(200), running.gap_tone(600), running.gap_tone(1100)), ("good", "warn", "bad"))
        self.assertIsNone(running.endurance_gap(None, 8000))

    def test_readiness(self):
        v = 50.0
        target = 0.5 * v ** 1.135
        self.assertAlmostEqual(running.long_run_readiness(v, target, 18), 100.0)
        self.assertAlmostEqual(running.long_run_readiness(v, target / 2, 9), 100 * (2 / 3 * 0.5 + 1 / 3 * 0.5))
        self.assertAlmostEqual(running.long_run_readiness(v, target * 3, 40), 100.0)
        self.assertIsNone(running.long_run_readiness(None, 30, 10))
        self.assertEqual((running.readiness_tone(95), running.readiness_tone(75), running.readiness_tone(10)),
                         ("good", "warn", "bad"))

    def test_weekly_zone_secs(self):
        w = running.weekly_zone_secs([("2026-10-20 07:00:00", [10, 0, 0, 0, 0]),
                                      ("2026-10-18 07:00:00", [0, 5, 0, 0, 0])], date(2026, 10, 21))
        self.assertEqual(len(w), 26)
        self.assertEqual(w[-1], ("2026-10-19", [10, 0, 0, 0, 0]))
        self.assertEqual(w[-2], ("2026-10-12", [0, 5, 0, 0, 0]))


class EffortTests(unittest.TestCase):
    def test_constant_pace(self):
        e = running.best_efforts(steady(300, 6))      # 5:00/km
        self.assertAlmostEqual(e["1k"], 300, delta=1)
        self.assertAlmostEqual(e["5k"], 1500, delta=1)
        self.assertAlmostEqual(e["1mi"], 300 * 1.609344, delta=1)
        self.assertNotIn("10k", e)

    def test_gps_spike_and_pace_floor(self):
        s = steady(300, 6)
        spiked = s[:600] + [(t, d + 1500, h) for t, d, h in s[600:]]     # +1.5 km jump in one second
        e = running.best_efforts(spiked)
        self.assertGreaterEqual(e["1k"], 150)
        self.assertAlmostEqual(e["1k"], 300, delta=3)
        self.assertGreaterEqual(e["5k"] / 5, 150)

    def test_backwards_and_junk(self):
        s = steady(300, 3)
        s.insert(500, (500.5, 10.0, 140))     # distance goes backwards
        self.assertAlmostEqual(running.best_efforts(s)["1k"], 300, delta=1)
        self.assertEqual(running.best_efforts([]), {})
        self.assertEqual(running.best_efforts(None), {})
        self.assertEqual(running.best_efforts([(0, None, 1), (1, None, 1)]), {})

    def test_laps_fallback(self):
        laps = [lap(1000, 320, 140), lap(1000, 300, 140), lap(1000, 310, 140), lap(1000, 330, 140),
                lap(1000, 340, 140), lap(500, 160, 140)]
        e = running.best_efforts_from_laps(laps)
        self.assertEqual(e["1k"], 300)
        self.assertAlmostEqual(e["5k"], (320 + 300 + 310 + 330 + 340) , delta=0.01)
        self.assertNotIn("10k", e)
        self.assertEqual(running.best_efforts_from_laps(None), {})
        self.assertEqual(running.best_efforts_from_laps([lap(1000, 100, 1)]), {})   # 1:40/km is a glitch

    def test_pace_curve(self):
        c = running.pace_curve([("1k", 300), ("1k", 280), ("5k", 1500)], "km")
        self.assertEqual(c, [("1k", 280.0), ("5k", 300.0)])

    def test_svgs(self):
        self.assertIn("Not enough data", running.svg_zone_bars([]))
        self.assertIn("<rect", running.svg_zone_bars([("2026-10-19", [10, 20, 30, 0, 5])]))
        self.assertEqual(running.svg_zone_strip([]), "")
        self.assertIn("<rect", running.svg_zone_strip([10, 20, 30, 0, 5]))
        self.assertIn("Not enough data", running.svg_pace_curve([], []))
        self.assertIn("<polyline", running.svg_pace_curve([("1k", 280), ("5k", 300)], [("1k", 270), ("5k", 295)], "km"))


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        self.today = date(2026, 10, 20)

    def test_empty_database(self):
        r = running.load(self.con, self.today)
        self.assertTrue(r["need_max_hr"])
        self.assertIsNone(r["predictions"])
        self.assertIsNone(r["vo2_current"])
        x = running.load_run(self.con, {"id": 1, "start_local": "2026-10-01 07:00:00", "distance_m": 5000,
                                        "duration_s": 1500, "avg_hr": 150}, [], self.today)
        self.assertTrue(x["need_max_hr"])
        self.assertIsNone(x["eff_vo2"])
        self.assertEqual(x["zone_strip"], "")

    def test_with_data_and_source_switch(self):
        db.upsert_activity(self.con, 1, start_local="2026-10-10 07:00:00", type="running", distance_m=5000,
                           duration_s=1500, avg_hr=125, max_hr=190)
        db.replace_hr_hist(self.con, 1, [(120, 600), (125, 600), (150, 300)])
        db.replace_zones(self.con, 1, [(1, 100, 90), (2, 200, 110), (3, 300, 130), (4, 0, 150), (5, 0, 170)])
        db.replace_best_efforts(self.con, 1, {"5k": 1500, "1k": 290}, "details")
        a = running.load(self.con, self.today)
        self.assertEqual(a["settings"]["max_hr"], 190)
        self.assertAlmostEqual(a["easy_share"], 1200 / 1500)     # 120/125 are in Z2 (114-133), 150 in Z4
        self.assertEqual(len(a["ef_points"]), 1)
        self.assertEqual(a["best5k"], 1500)
        self.assertIn("half", a["predictions"])
        db.set_setting(self.con, "zone_source", "garmin")
        b = running.load(self.con, self.today)
        self.assertAlmostEqual(b["easy_share"], 300 / 600)
        self.assertEqual(len(b["ef_points"]), 1)      # avg 125 is inside Garmin's own Z2 (110-130)
        db.set_setting(self.con, "zone_source", "x")
        self.assertEqual(running.load(self.con, self.today)["zone_source"], "maxhr")
        db.set_setting(self.con, "max_hr", "abc")
        self.assertEqual(running.settings(self.con, self.today)["max_hr"], 190)

    def test_cadence_filter(self):
        for i, cad in enumerate([172, 85, 0, None, 250]):
            db.upsert_activity(self.con, i + 1, start_local=f"2026-10-{10 + i:02d} 07:00:00", type="running",
                               distance_m=5000, duration_s=1500, avg_hr=125, max_hr=190, cadence=cad)
            db.replace_hr_hist(self.con, i + 1, [(120, 600), (125, 600)])
        a = running.load(self.con, self.today)
        self.assertEqual(a["cadence_points"], [("2026-10-10", 172)])

    def test_cadence_from_laps(self):
        db.upsert_activity(self.con, 1, start_local="2026-10-10 07:00:00", type="running",
                           distance_m=5000, duration_s=1500, avg_hr=125, max_hr=190, cadence=None)
        db.replace_hr_hist(self.con, 1, [(120, 600), (125, 600)])
        db.replace_laps(self.con, 1, [{"distance_m": 1000, "duration_s": 300, "avg_hr": 120, "cadence": 160},
                                      {"distance_m": 1000, "duration_s": 100, "avg_hr": 120, "cadence": 180}])
        a = running.load(self.con, self.today)
        self.assertEqual(a["cadence_points"], [("2026-10-10", 165)])


if __name__ == "__main__":
    unittest.main()
