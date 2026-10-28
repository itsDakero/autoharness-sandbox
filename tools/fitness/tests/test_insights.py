import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import insights  # noqa: E402

TODAY = date(2026, 10, 25)   # a Sunday; the week starts Monday 2026-10-19


def ck(feeling, note="", **flags):
    d = {"feeling": feeling, "ill_neck": 0, "ill_chest": 0, "sore_legs": 0, "stressed": 0,
         "slept_badly": 0, "note": note}
    d.update(flags)
    return d


def series():
    out = []
    for i in range(14):   # 2026-10-12 .. 2026-10-25
        d = date(2026, 10, 12 + i).isoformat()
        out.append({"date": d, "load": 10.0, "ctl": 20.0 + i, "atl": 30.0 + i, "tsb": -10.0})
    return out


class FactsTests(unittest.TestCase):
    def test_worked_example_and_privacy(self):
        rec = {"rec_series": [{"date": "2026-10-20", "score": 60}, {"date": "2026-10-21", "score": 80},
                              {"date": "2026-10-14", "score": 50}],
               "warn_dates": ["2026-10-21", "2026-10-15"], "debt": 7200.0, "consistency": None,
               "chips": {"hrv": {"text": "in range"}, "rhr": {"text": "learning (3/14)"}}}
        weeks = [{"dist_m": 20000, "time_s": 7200, "runs": 2, "fiit": 1, "long_share": 0.6},
                 {"dist_m": 10000, "time_s": 3600, "runs": 1, "fiit": 0, "long_share": None},
                 {"dist_m": 30000, "time_s": 7200, "runs": 3, "fiit": 2, "long_share": 0.4}]
        cks = [ck(4, note="secret note", sore_legs=1), ck(2, ill_neck=1, stressed=1), ck(3, ill_chest=1)]
        f = insights.build_facts(series(), {"zone": ("Neutral", ""), "acwr": 1.234, "ramp": 2.0,
                                            "monotony": None}, rec, None, weeks, 3, cks, TODAY)
        self.assertNotIn("secret", json.dumps(f))
        self.assertNotIn("note", json.dumps(f))
        self.assertEqual(f["week_start"], "2026-10-19")
        self.assertEqual(f["load"]["week_load"], 70.0)        # 7 days x 10
        self.assertEqual(f["load"]["last_week_load"], 70.0)
        self.assertEqual(f["load"]["ctl"], 33.0)
        self.assertEqual(f["load"]["ctl_7d_ago"], 26.0)
        self.assertEqual(f["load"]["acwr"], 1.23)
        self.assertEqual(f["recovery"]["recovery_avg"], 70.0)
        self.assertEqual(f["recovery"]["recovery_avg_last_week"], 50.0)
        self.assertEqual(f["recovery"]["sleep_debt_h"], 2.0)
        self.assertEqual(f["recovery"]["illness_warning_days"], 1)
        self.assertEqual(f["checkins"], {"count": 3, "average_feeling": 3.0, "ill_days": 2,
                                         "sore_legs_days": 1, "stressed_days": 1, "slept_badly_days": 0})
        self.assertEqual(f["volume"]["this_week"]["km"], 20.0)
        self.assertEqual(f["volume"]["previous_4_week_average"]["km"], 20.0)   # (10 + 30) / 2
        self.assertEqual(f["volume"]["run_streak_weeks"], 3)
        self.assertIsNone(f["running"])

    def test_missing_sections_are_null(self):
        weeks = [{"dist_m": 5000, "time_s": 1800, "runs": 1, "fiit": 0, "long_share": None}]
        f = insights.build_facts([], None, None, None, weeks, 0, [], TODAY)
        self.assertIsNone(f["load"])
        self.assertIsNone(f["recovery"])
        self.assertIsNone(f["checkins"])
        self.assertIsNone(f["volume"]["previous_4_week_average"])

    def test_empty_week_is_none(self):
        weeks = [{"dist_m": 0, "time_s": 0, "runs": 0, "fiit": 0, "long_share": None}]
        flat = [dict(p, load=0.0) for p in series()]
        self.assertIsNone(insights.build_facts(flat, None, {"rec_series": [], "warn_dates": []}, None,
                                               weeks, 0, [], TODAY))
        self.assertIsNone(insights.build_facts([], None, None, None, [], 0, [], TODAY))


class BulletTests(unittest.TestCase):
    def test_dash_lines(self):
        t = "\n".join(f"- point {i}" for i in range(5))
        self.assertEqual(insights.parse_bullets(t), [f"point {i}" for i in range(5)])

    def test_numbered(self):
        self.assertEqual(insights.parse_bullets("1. a\n2) b\n3. c"), ["a", "b", "c"])

    def test_think_and_cap(self):
        t = "<think>\n- not me\n</think>\n" + "\n".join(f"* b{i}" for i in range(6))
        self.assertEqual(insights.parse_bullets(t), [f"b{i}" for i in range(5)])

    def test_prose(self):
        self.assertEqual(insights.parse_bullets("A good week overall.\nKeep going."), [])
        self.assertEqual(insights.parse_bullets(""), [])


class CleanTests(unittest.TestCase):
    def test_em_dash(self):
        self.assertEqual(insights.clean_bullet("Load rose \u2014 recovery fell."), "Load rose, recovery fell.")
        self.assertEqual(insights.clean_bullet("Load rose\u2014recovery fell."), "Load rose, recovery fell.")

    def test_opener(self):
        self.assertEqual(insights.clean_bullet("Great question! Load rose 12%."), "Load rose 12%.")
        self.assertEqual(insights.clean_bullet("Sure, load rose 12%."), "load rose 12%.")

    def test_closer(self):
        self.assertEqual(insights.clean_bullet("Load rose 12%. I hope this helps."), "Load rose 12%.")

    def test_real_content_stays(self):
        self.assertEqual(insights.clean_bullet("Sure footing improved."), "Sure footing improved.")
        self.assertEqual(insights.clean_bullet("Absolutely flat week."), "Absolutely flat week.")

    def test_numbers_untouched(self):
        t = "Ran 5\u20136 km with TSB -10."
        self.assertEqual(insights.clean_bullet(t), t)
        t = "-10 TSB means fatigue."
        self.assertEqual(insights.clean_bullet(t), t)
        self.assertEqual(insights.parse_bullets("- -12 TSB, rest more."), ["-12 TSB, rest more."])

    def test_pure_filler_dropped(self):
        self.assertEqual(insights.parse_bullets("- Let me know if you have questions."), [])
        self.assertEqual(insights.parse_bullets("\n".join(["- Let me know if you have questions."] * 5)), [])

    def test_five_with_filler(self):
        t = "\n".join(f"- Great question! Point {i} \u2014 up. I hope this helps." for i in range(5))
        self.assertEqual(insights.parse_bullets(t), [f"Point {i}, up." for i in range(5)])

    def test_empty_and_think(self):
        self.assertEqual(insights.parse_bullets(None), [])
        self.assertEqual(insights.parse_bullets("<think>- x</think>\n- a\n- b\n- c"), ["a", "b", "c"])


class ModelTests(unittest.TestCase):
    def test_unreachable_is_offline(self):
        old = insights.OLLAMA_URL
        insights.OLLAMA_URL = "http://127.0.0.1:9"
        try:
            with self.assertRaises(insights.Offline):
                insights.ask_model({"week_start": "2026-10-19"})
        finally:
            insights.OLLAMA_URL = old


if __name__ == "__main__":
    unittest.main()
