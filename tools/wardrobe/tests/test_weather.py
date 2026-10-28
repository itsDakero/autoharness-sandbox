import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import weather  # noqa: E402

SAMPLE = {"daily": {"time": ["2026-10-23"], "temperature_2m_max": [12.4],
                    "temperature_2m_min": [7.1], "precipitation_probability_max": [60]}}


class WeatherTests(unittest.TestCase):
    def test_parse_sample(self):
        self.assertEqual(weather.parse(SAMPLE), {"tmax": 12.4, "tmin": 7.1, "rain": 60.0})

    def test_parse_garbage(self):
        for bad in (None, "x", 5, [], {}, {"daily": 3}, {"daily": {}},
                    {"daily": {"temperature_2m_max": []}},
                    {"daily": {"temperature_2m_max": ["hot"]}},
                    {"daily": {"temperature_2m_max": [True]}},
                    {"daily": {"temperature_2m_max": [float("nan")]}},
                    {"daily": {"temperature_2m_max": [999]}}):
            self.assertIsNone(weather.parse(bad), bad)

    def test_parse_missing_rain(self):
        w = weather.parse({"daily": {"temperature_2m_max": [20]}})
        self.assertEqual(w, {"tmax": 20.0, "tmin": None, "rain": None})

    def test_season_with_forecast(self):
        self.assertEqual(weather.season_for(1, 20), "summer")
        self.assertEqual(weather.season_for(7, 11), "winter")
        self.assertEqual(weather.season_for(4, 15), "spring")
        self.assertEqual(weather.season_for(10, 15), "autumn")
        self.assertEqual(weather.season_for(6, 11.5), "spring")
        self.assertEqual(weather.season_for(7, 12), "autumn")

    def test_season_by_month(self):
        got = [weather.season_for(m) for m in range(1, 13)]
        self.assertEqual(got, ["winter"] * 2 + ["spring"] * 3 + ["summer"] * 3 + ["autumn"] * 3
                         + ["winter"])

    def test_fetch_without_location(self):
        self.assertIsNone(weather.fetch(None, 1.0))

    def test_describe(self):
        self.assertEqual(weather.describe(None), "No forecast; using the month")
        self.assertIn("60% rain", weather.describe(weather.parse(SAMPLE)))


if __name__ == "__main__":
    unittest.main()
