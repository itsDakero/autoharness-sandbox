import json
import os
import sys
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import analysis as an  # noqa: E402


class AnalysisTests(unittest.TestCase):
    def test_scale_fit(self):
        self.assertAlmostEqual(an.fiit_scale([(100, 50), (200, 100), (100, 50)]), 0.5)
        self.assertEqual(an.fiit_scale([(100, 50), (200, 100)]), 1.0)
        self.assertEqual(an.fiit_scale([(0, 50), (0, 50), (0, 50)]), 1.0)

    def test_matched_fiit_not_double_counted(self):
        d0 = date(2026, 1, 1)
        acts = [{"start_local": "2026-01-01 07:00:00", "training_load": 80}]
        fiit = [{"date": "2026-01-01", "srpe": 300, "act_load": 80},      # matched with load: skipped
                {"date": "2026-01-02", "srpe": 100, "act_load": None},    # unmatched: srpe*scale
                {"date": "2026-01-02", "srpe": 100, "act_load": 0}]       # matched, no load: counted
        out = an.daily_load(acts, fiit, 0.5, d0, date(2026, 1, 3))
        self.assertEqual([l for _, l in out], [80.0, 100.0, 0.0])

    def test_zero_fill_and_nulls(self):
        acts = [{"start_local": "2026-01-03 07:00", "training_load": None},
                {"start_local": None, "training_load": 99},
                {"start_local": "2026-01-03 18:00", "training_load": 40}]
        out = an.daily_load(acts, [], 1.0, date(2026, 1, 1), date(2026, 1, 4))
        self.assertEqual([l for _, l in out], [0.0, 0.0, 40.0, 0.0])
        self.assertEqual(len(out), 4)

    def test_ewma(self):
        v = an.ewma([100, 0, 0], 7)
        self.assertEqual([round(x, 2) for x in v], [14.29, 12.24, 10.50])

    def test_tsb_takes_previous_day(self):
        ctl, atl = [10.0, 20.0, 30.0], [15.0, 18.0, 40.0]
        self.assertEqual(an.tsb_series(ctl, atl), [0.0, -5.0, 2.0])

    def test_ramp(self):
        ctl = [float(i) for i in range(10)]    # +1 per day
        self.assertEqual(an.ramp(ctl), 7.0)
        self.assertIsNone(an.ramp(ctl[:7]))

    def test_acwr(self):
        loads = [0.0] * 21 + [40.0] * 7        # 7d mean 40, 28d mean 10
        self.assertAlmostEqual(an.acwr(loads), 4.0)
        self.assertIsNone(an.acwr([0.0] * 28))
        self.assertIsNone(an.acwr([10.0] * 27))
        self.assertEqual(an.acwr_tone(1.0), "good")
        self.assertEqual(an.acwr_tone(1.4), "warn")
        self.assertEqual(an.acwr_tone(1.6), "bad")
        self.assertEqual(an.acwr_tone(0.5), "")

    def test_monotony_strain(self):
        loads = [0, 0, 0, 0, 0, 0, 0, 10, 20, 10, 20, 10, 20, 10]  # last 7: mean 100/7 -> 14.2857
        m = an.monotony([float(x) for x in loads])
        # last 7 = 10,20,10,20,10,20,10: mean 14.2857, pstdev 4.9487
        self.assertAlmostEqual(m, 14.2857 / 4.9487, places=3)
        self.assertAlmostEqual(an.strain([float(x) for x in loads], m), 100 * m)
        self.assertIsNone(an.monotony([30.0] * 7))
        self.assertIsNone(an.monotony([0.0] * 7))
        self.assertIsNone(an.strain([30.0] * 7, None))

    def test_zone_boundaries(self):
        z = lambda v: an.form_zone(v)[0]
        self.assertEqual(z(5.1), "Fresh")
        self.assertEqual(z(5), "Neutral")
        self.assertEqual(z(-10), "Neutral")
        self.assertEqual(z(-10.1), "Optimal")
        self.assertEqual(z(-30), "Optimal")
        self.assertEqual(z(-30.1), "High risk")
        self.assertEqual(an.form_zone(-40)[1], "bad")

    def test_chart(self):
        self.assertIn("Not enough data yet.", an.svg_load_chart([]))
        s, _ = an.compute([{"start_local": f"2026-01-0{i} 07:00", "training_load": 50 * i} for i in (1, 2, 3)],
                          [], date(2026, 1, 3))
        svg = an.svg_load_chart(s)
        self.assertEqual(svg.count("<rect"), 3)
        self.assertIn('class="ctl"', svg)
        self.assertIn('class="atl"', svg)

    def test_compute_edge_cases(self):
        s, sm = an.compute([], [], date(2026, 1, 3))
        self.assertEqual(s, [])
        self.assertIsNone(sm["tsb"])
        s, sm = an.compute([{"start_local": "2026-01-01 07:00", "training_load": 50}], [], date(2026, 1, 10))
        self.assertEqual(len(s), 10)
        self.assertIsNone(sm["acwr"])
        self.assertIsNone(sm["monotony"] if sm["monotony"] is None else None)
        self.assertEqual(sm["days_of_data"], 10)


def _ms(y, mo, d, h, mi):
    from datetime import datetime, timezone
    return int(datetime(y, mo, d, h, mi, tzinfo=timezone.utc).timestamp() * 1000)


def _sleep_json(bed, wake):
    return json.dumps({"dailySleepDTO": {"sleepStartTimestampLocal": bed, "sleepEndTimestampLocal": wake}})


BAND = {"mean": 50.0, "sd": 10.0, "lo": 40.0, "hi": 60.0, "n": 60}


class RecoveryTests(unittest.TestCase):
    def test_band(self):
        d = date(2026, 3, 1)
        vals = {(d - timedelta(days=i)).isoformat(): float(i % 2 * 2 + 10) for i in range(1, 21)}  # 12,10,... mean 11 sd 1
        b = an.band(vals, d)
        self.assertAlmostEqual(b["mean"], 11.0)
        self.assertAlmostEqual(b["sd"], 1.0)
        vals[d.isoformat()] = 999.0   # d itself is excluded
        self.assertAlmostEqual(an.band(vals, d)["mean"], 11.0)

    def test_band_edge_cases(self):
        d = date(2026, 3, 1)
        few = {(d - timedelta(days=i)).isoformat(): 50.0 + i for i in range(1, 14)}
        self.assertIsNone(an.band(few, d))
        flat = {(d - timedelta(days=i)).isoformat(): 50.0 for i in range(1, 30)}
        self.assertIsNone(an.band(flat, d))
        self.assertIsNone(an.band({}, d))
        self.assertIsNone(an.band_pos(5, None))
        self.assertIsNone(an.band_pos(None, BAND))

    def test_band_pos_and_tone(self):
        self.assertEqual(an.band_pos(39, BAND), "below")
        self.assertEqual(an.band_pos(40, BAND), "in range")
        self.assertEqual(an.band_pos(61, BAND), "above")
        self.assertEqual(an.band_tone("hrv", "below"), "warn")
        self.assertEqual(an.band_tone("hrv", "above"), "good")
        self.assertEqual(an.band_tone("rhr", "above"), "warn")
        self.assertEqual(an.band_tone("rhr", "below"), "good")
        self.assertEqual(an.band_tone("rhr", "in range"), "good")

    def test_roll_avg(self):
        d = date(2026, 3, 10)
        v = {"2026-03-10": 10.0, "2026-03-08": 20.0, "2026-03-03": 99.0}   # 03-03 is outside d-6..d
        self.assertIsNone(an.roll_avg(v, d))
        v["2026-03-06"] = 30.0
        self.assertAlmostEqual(an.roll_avg(v, d), 20.0)

    def test_recovery_worked_example(self):
        hb = {"mean": 50.0, "sd": 10.0, "lo": 40.0, "hi": 60.0, "n": 60}
        rb = {"mean": 60.0, "sd": 4.0, "lo": 56.0, "hi": 64.0, "n": 60}
        r = an.recovery_score(60, 60, 7 * 3600, hb, rb, 8 * 3600)
        self.assertAlmostEqual(r["base"], 71.25)
        self.assertEqual(r["score"], 71)
        r = an.recovery_score(60, 60, 7 * 3600, hb, rb, 8 * 3600, {"stressed": 1})
        self.assertEqual((r["score"], r["label"], r["tone"]), (61, "Yellow", "warn"))
        r = an.recovery_score(60, 60, 7 * 3600, hb, rb, 8 * 3600, {"stressed": 1, "ill_chest": 1})
        self.assertEqual((r["score"], r["label"], r["tone"]), (33, "Red", "bad"))
        r = an.recovery_score(60, 60, 7 * 3600, hb, rb, 8 * 3600, {"sore_legs": 1, "stressed": 1, "slept_badly": 1})
        self.assertEqual(r["score"], 41)

    def test_recovery_missing_parts(self):
        hb = {"mean": 50.0, "sd": 10.0, "lo": 40.0, "hi": 60.0, "n": 60}
        self.assertIsNone(an.recovery_score(None, None, None, None, None, 28800))
        self.assertIsNone(an.recovery_score(60, 55, None, None, None, 28800, {"ill_neck": 1}))   # no band, no sleep
        r = an.recovery_score(60, None, None, hb, None, 28800)       # only HRV: weight renormalised to 1
        self.assertEqual(r["score"], 75)
        r = an.recovery_score(None, None, 14400, None, None, 28800)  # only sleep: 50
        self.assertEqual(r["score"], 50)
        self.assertEqual(an.recovery_score(500, None, None, hb, None, 28800)["score"], 100)   # clamped
        self.assertEqual(an.recovery_score(-500, None, None, hb, None, 28800)["score"], 0)

    def test_score_band_edges(self):
        self.assertEqual(an.score_band(67)[0], "Green")
        self.assertEqual(an.score_band(66)[0], "Yellow")
        self.assertEqual(an.score_band(34)[0], "Yellow")
        self.assertEqual(an.score_band(33)[0], "Red")
        self.assertEqual(an.score_band(None)[0], "-")

    def test_sleep_debt(self):
        today = date(2026, 3, 10)
        need = 8 * 3600
        s = {f"2026-03-{d:02d}": 7 * 3600 for d in (10, 9, 8, 7)}
        self.assertEqual(an.sleep_debt(s, need, today), 4 * 3600)
        self.assertIsNone(an.sleep_debt({k: v for k, v in list(s.items())[:3]}, need, today))
        s2 = {f"2026-03-{d:02d}": 9 * 3600 for d in (10, 9, 8, 7)}
        self.assertEqual(an.sleep_debt(s2, need, today), 0)      # floored
        s["2026-03-03"] = 0                                     # outside the window, ignored
        self.assertEqual(an.sleep_debt(s, need, today), 4 * 3600)
        self.assertEqual(an.debt_tone(1.9 * 3600), "good")
        self.assertEqual(an.debt_tone(5 * 3600), "warn")
        self.assertEqual(an.debt_tone(5.1 * 3600), "bad")

    def test_parse_sleep_times_bad_input(self):
        for bad in (None, "", "not json", "[]", "{}", '{"dailySleepDTO": null}',
                    _sleep_json(None, 5), _sleep_json(5, None), _sleep_json("x", "y"), _sleep_json(1e30, 1e30)):
            self.assertIsNone(an.parse_sleep_times(bad))

    def test_consistency_across_midnight(self):
        today = date(2026, 3, 14)
        raw = {}
        for i in range(6):
            d = today - timedelta(days=i)
            bed = (23, 30) if i % 2 else (0, 30)     # 23:30 and 00:30
            bed_day = d - timedelta(days=1) if i % 2 or True else d
            raw[d.isoformat()] = _sleep_json(_ms(bed_day.year, bed_day.month, bed_day.day, *bed),
                                             _ms(d.year, d.month, d.day, 7, 0))
        c = an.consistency(raw, today)
        self.assertAlmostEqual(c["bed_sd"], 30.0)      # not ~11 h
        self.assertAlmostEqual(c["wake_sd"], 0.0)
        self.assertEqual(c["wake_mean"], "07:00")
        self.assertEqual(c["bed_mean"], "00:00")
        self.assertEqual(c["tone"], "good")

    def test_consistency_needs_five_valid_nights(self):
        today = date(2026, 3, 14)
        good = _sleep_json(_ms(2026, 3, 13, 23, 0), _ms(2026, 3, 14, 7, 0))
        raw = {(today - timedelta(days=i)).isoformat(): good for i in range(4)}
        raw["2026-03-10"] = "garbage"
        raw["2026-03-09"] = _sleep_json(None, None)
        self.assertIsNone(an.consistency(raw, today))
        raw["2026-03-08"] = good
        self.assertIsNotNone(an.consistency(raw, today))

    def test_high_load_and_signals(self):
        ser = [{"date": f"d{i}", "load": 10.0, "ctl": 10.0} for i in range(40)]
        ser[30]["load"] = 15.0     # exactly 1.5 x 10
        ser[10]["load"] = 99.0     # before index 28: ignored
        ser[35]["load"] = 0.0
        self.assertEqual(an.high_load_days(ser), {"d30"})
        hb = {"mean": 50.0, "sd": 10.0, "lo": 40.0, "hi": 60.0, "n": 60}
        rb = {"mean": 60.0, "sd": 2.0, "lo": 58.0, "hi": 62.0, "n": 60}
        self.assertEqual(an.illness_signals(39, 65, hb, rb), (True, True))
        self.assertEqual(an.illness_signals(39, 64.9, hb, rb), (False, True))
        self.assertEqual(an.illness_signals(None, 70, hb, None), (False, False))
        self.assertEqual(an.illness_signals(30, 70, None, None), (False, False))

    def test_parse_need(self):
        self.assertEqual(an.parse_need("7.5"), 7.5)
        self.assertEqual(an.parse_need(" 8 "), 8.0)
        for bad in ("", "abc", "20", "3.9", "nan", "inf", None):
            self.assertIsNone(an.parse_need(bad))

    def _history(self, today, days, hrv_fn, rhr_fn, sleep=8 * 3600):
        return [{"date": (today - timedelta(days=i)).isoformat(), "hrv_avg": hrv_fn(i), "rhr": rhr_fn(i),
                 "sleep_s": sleep} for i in range(days, -1, -1)]

    def test_recovery_no_data_or_short_history(self):
        today = date(2026, 6, 1)
        r = an.recovery([], [], {}, None, [], today)
        self.assertIsNone(r["score"])
        self.assertFalse(r["warning"])
        self.assertIsNone(r["debt"])
        self.assertIsNone(r["consistency"])
        self.assertEqual(r["need_h"], 8.0)
        self.assertIn("learning (0/14)", r["chips"]["hrv"]["text"])
        short = self._history(today, 10, lambda i: 50.0 + i, lambda i: 55.0)
        r = an.recovery(short, [], {}, "garbage", [], today)
        self.assertIsNone(r["chips"]["hrv"]["band"])
        self.assertFalse(r["warning"])
        self.assertEqual(r["score"]["parts"][0]["score"], None)    # HRV part missing
        self.assertEqual(r["score"]["score"], 100)                 # sleep only, 8 of 8 h
        self.assertEqual(an.svg_band_chart(r["hrv_series"], "t", "ms").count("<polygon"), 0)

    def test_recovery_flat_series_no_zero_division(self):
        today = date(2026, 6, 1)
        flat = self._history(today, 80, lambda i: 50.0, lambda i: 55.0)
        r = an.recovery(flat, [], {}, 8, [], today)
        self.assertIsNone(r["chips"]["rhr"]["band"])
        self.assertFalse(r["warning"])

    def test_missing_today_row_no_banner_no_red(self):
        today = date(2026, 6, 1)
        rows = [x for x in self._history(today, 80, lambda i: 50.0 + (i % 5), lambda i: 55.0 + (i % 3))
                if x["date"] != today.isoformat()]
        r = an.recovery(rows, [{"date": today.isoformat(), "slept_badly": 1, "stressed": 1, "ill_neck": 0,
                                "ill_chest": 0, "sore_legs": 0}], {}, 8, [], today)
        self.assertIsNone(r["score"])
        self.assertFalse(r["warning"])
        self.assertFalse(r["red_high_load"])

    def test_illness_warning_two_nights_and_checkin(self):
        today = date(2026, 6, 1)

        def hrv(i):
            return 30.0 if i <= 1 else 50.0 + (i % 4)

        def rhr(i):
            return 70.0 if i <= 1 else 55.0 + (i % 3)

        rows = self._history(today, 80, hrv, rhr)
        r = an.recovery(rows, [], {}, 8, [], today)
        self.assertTrue(r["warning"])
        # one night only: no warning ...
        rows1 = self._history(today, 80, lambda i: 30.0 if i == 0 else 50.0 + (i % 4),
                              lambda i: 70.0 if i == 0 else 55.0 + (i % 3))
        self.assertFalse(an.recovery(rows1, [], {}, 8, [], today)["warning"])
        # ... unless the check-in says slept badly
        ck = [{"date": today.isoformat(), "slept_badly": 1, "stressed": 0, "ill_neck": 0, "ill_chest": 0,
               "sore_legs": 0}]
        self.assertTrue(an.recovery(rows1, ck, {}, 8, [], today)["warning"])

    def test_charts_render(self):
        self.assertIn("Not enough data yet.", an.svg_band_chart([], "t", "ms"))
        self.assertIn("Not enough data yet.", an.svg_strain_recovery_chart([], []))
        pts = [{"date": f"2026-01-0{i}", "v": 50.0 + i, "avg": 50.0 + i, "lo": 45.0 if i > 1 else None,
                "hi": 55.0 if i > 1 else None} for i in range(1, 6)]
        svg = an.svg_band_chart(pts, "HRV", "ms", {"2026-01-03": ("#fff", "tip", True)})
        self.assertIn('class="band"', svg)
        self.assertIn('class="ravg"', svg)
        rec = [{"date": f"2026-01-0{i}", "score": 30 + i, "flag": i == 3} for i in range(1, 6)]
        svg = an.svg_strain_recovery_chart([{"date": "2026-01-03", "load": 90.0}], rec)
        self.assertIn('class="flag"', svg)
        self.assertIn('class="rec"', svg)
        self.assertEqual(svg.count('class="loadbar"'), 1)

    def test_accuracy(self):
        today = date(2026, 6, 1)

        def hrv(i):
            return 30.0 if i in (21, 20) else 50.0 + (i % 4)

        def rhr(i):
            return 70.0 if i in (21, 20) else 55.0 + (i % 3)

        rows = self._history(today, 120, hrv, rhr)
        ck = [{"date": (today - timedelta(days=i)).isoformat(), "slept_badly": 0, "stressed": 0, "ill_neck": 0,
               "ill_chest": 0, "sore_legs": 0} for i in range(0, 70) if i != 18]
        for c in ck:
            if c["date"] == (today - timedelta(days=18)).isoformat() or c["date"] == (today - timedelta(days=19)).isoformat():
                c["ill_neck"] = 1
        r = an.recovery(rows, ck, {}, 8, [], today)
        a = r["accuracy"]
        self.assertTrue(a["enabled"])
        self.assertEqual((a["starts"], a["hits"], a["false"]), (1, 1, 0))
        self.assertFalse(an.recovery(rows, ck[:10], {}, 8, [], today)["accuracy"]["enabled"])


class VolumeTests(unittest.TestCase):
    today = date(2026, 10, 21)    # Wednesday; week starts Monday 2026-10-19

    def run_(self, d, km):
        return {"start_local": f"{d} 07:00:00", "distance_m": km * 1000, "duration_s": km * 360}

    def test_heat_levels(self):
        self.assertEqual(an.heat_levels([0, 0, None]), (0.0, 0.0, 0.0))
        self.assertEqual(an.heat_levels([0, 10, 20, 30, 40]), (17.5, 25.0, 32.5))

    def test_weekly_summary(self):
        runs = [self.run_("2026-10-12", 5), self.run_("2026-10-13", 5), self.run_("2026-10-15", 10),
                self.run_("2026-10-20", 8)]
        out = an.weekly_summary(runs, [{"date": "2026-10-14"}, {"date": "2026-10-15"}], self.today)
        self.assertEqual(len(out), 12)
        self.assertEqual(out[0]["week"], "2026-10-19")
        self.assertEqual((out[0]["runs"], out[0]["long_share"], out[0]["long_tone"]), (1, None, ""))
        w = out[1]
        self.assertEqual((w["runs"], w["fiit"], w["dist_m"]), (3, 2, 20000))
        self.assertEqual((w["long_share"], w["long_tone"]), (0.5, "warn"))
        self.assertEqual(out[2]["runs"], 0)
        self.assertEqual((out[2]["dist_m"], out[2]["fiit"], out[2]["long_share"]), (0, 0, None))

    def test_run_streak(self):
        def two(mon):
            d = date.fromisoformat(mon)
            return [self.run_(d.isoformat(), 5), self.run_((d + timedelta(days=2)).isoformat(), 5)]
        runs = two("2026-10-12") + two("2026-10-05") + [self.run_("2026-09-28", 5)] + two("2026-09-14")
        self.assertEqual(an.run_streak(runs, self.today), 2)             # 09-28 has 1 run: broken
        self.assertEqual(an.run_streak(runs + [self.run_("2026-10-19", 3)], self.today), 2)   # 1 run this week
        self.assertEqual(an.run_streak(runs + two("2026-10-19"), self.today), 3)
        self.assertEqual(an.run_streak([], self.today), 0)

    def test_svg_heatmap(self):
        self.assertIn("Not enough data", an.svg_heatmap([], self.today))
        series = [{"date": (self.today - timedelta(days=i)).isoformat(), "load": float(i % 5 * 20)}
                  for i in range(400, -1, -1)]
        svg = an.svg_heatmap(series, self.today)
        n = svg.count("<rect")
        self.assertTrue(0 < n <= 371)
        self.assertIn("<title>2026-10-21: load 0</title>", svg)
        self.assertNotIn("2026-10-22", svg)


if __name__ == "__main__":
    unittest.main()
