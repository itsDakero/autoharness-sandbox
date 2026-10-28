import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import logic  # noqa: E402


class LogicTests(unittest.TestCase):
    def test_pace(self):
        self.assertEqual(logic.fmt_pace(1609.344, 540), "9:00/mi")
        self.assertEqual(logic.fmt_pace(1000, 300, "km"), "5:00/km")
        self.assertEqual(logic.fmt_pace(None, 300), "–")
        self.assertEqual(logic.fmt_pace(0, 300), "–")

    def test_baseline(self):
        rows = [{"date": f"2026-10-{d:02d}", "v": d} for d in range(1, 11)]
        rows.append({"date": "2026-10-05", "v": None})
        self.assertEqual(logic.baseline(rows, "v", "2026-10-11", 7), 7.0)
        self.assertIsNone(logic.baseline(rows, "v", "2026-09-01", 7))

    def test_match_fiit(self):
        acts = [
            {"id": 1, "start_local": "2026-10-16 07:00:00", "type": "hiit"},
            {"id": 2, "start_local": "2026-10-16 07:50:00", "type": "strength_training"},
            {"id": 3, "start_local": "2026-10-16 07:10:00", "type": "running"},
            {"id": 4, "start_local": "2026-10-15 07:00:00", "type": "hiit"},
        ]
        self.assertEqual(logic.match_fiit("2026-10-16", "07:45", acts), 2)
        self.assertEqual(logic.match_fiit("2026-10-16", "07:05", acts), 1)
        self.assertIsNone(logic.match_fiit("2026-10-16", "12:00", acts))
        self.assertIsNone(logic.match_fiit("2026-10-16", None, acts))
        self.assertEqual(logic.match_fiit("2026-10-15", None, acts), 4)

    def test_pbs(self):
        recs = [{"typeId": 3, "activityType": "running", "value": 1490.5, "actStartDateTimeInGMT": "2026-09-01T10:00:00.0"},
                {"typeId": 7, "value": 5}, {"typeId": "x"}, "junk", {"typeId": 5, "value": None}]
        self.assertEqual(logic.pbs_from_garmin(recs), [("5k", 1490, "2026-09-01")])
        self.assertEqual(logic.pbs_from_garmin(None), [])

    def test_chart(self):
        self.assertIn("Not enough data", logic.svg_line_chart([("2026-10-01", None)], "t"))
        svg = logic.svg_line_chart([("2026-10-01", 50), ("2026-10-02", None), ("2026-10-04", 55)], "RHR",
                                   {"2026-10-02": ("#d33", "ill <b>", True)})
        self.assertIn("<svg", svg)
        self.assertNotIn("<b>", svg)

    def test_delta_tone(self):
        self.assertEqual(logic.delta_tone(60, 50), "good")
        self.assertEqual(logic.delta_tone(60, 50, better=-1), "bad")
        self.assertEqual(logic.delta_tone(50.5, 50), "flat")
        self.assertEqual(logic.delta_tone(None, 50), "flat")

    def test_readiness_band(self):
        self.assertEqual(logic.readiness_band(80), ("High", "good"))
        self.assertEqual(logic.readiness_band(0), ("Poor", "bad"))
        self.assertIsNone(logic.readiness_band(None))

    def test_sparkline(self):
        self.assertEqual(logic.svg_sparkline([1, None]), "")
        self.assertIn("<polyline", logic.svg_sparkline([1, None, 3, 2]))

    def test_weekly(self):
        acts = [{"type": "running", "start_local": "2026-10-12 07:00:00", "distance_m": 1609.344},
                {"type": "running", "start_local": "2026-10-14 07:00:00", "distance_m": 1609.344},
                {"type": "hiit", "start_local": "2026-10-14 07:00:00", "distance_m": 5}]
        self.assertEqual(logic.weekly_distance(acts), [("2026-10-12", 2.0)])


if __name__ == "__main__":
    unittest.main()
