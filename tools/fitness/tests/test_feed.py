import json
import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, feed  # noqa: E402


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")
        db.migrate(self.con)

    def test_empty_db(self):
        out = feed.feed_data(self.con, date(2026, 10, 25))
        self.assertIsNone(out["readiness"])
        self.assertIsNone(out["weekly_summary"])
        self.assertEqual(out["last_activities"], [])
        self.assertIs(out["checked_in_today"], False)

    def test_seeded(self):
        db.upsert_activity(self.con, 1, start_local="2026-10-24 07:00:00", type="running",
                           distance_m=5000, duration_s=1500, training_load=80)
        db.upsert_checkin(self.con, "2026-10-25", 3, note="SECRET NOTE")
        db.upsert_summary(self.con, "2026-10-19", "ok", bullets=["a", "b", "c"])
        out = feed.feed_data(self.con, date(2026, 10, 25))
        self.assertEqual(out["last_activities"][0], {
            "date": "2026-10-24", "type": "running", "distance_km": 5.0, "duration_min": 25, "training_load": 80.0})
        self.assertEqual(out["weekly_summary"]["bullets"], ["a", "b", "c"])
        self.assertTrue(out["checked_in_today"])
        self.assertNotIn("note", json.dumps(out).lower().replace("notes", ""))
        self.assertNotIn("SECRET", json.dumps(out))

    def test_todays_session(self):
        plan_ctx = {"phase": "base", "week_no": 3,
                    "today": {"kind": "easy", "title": "Easy run", "target": "x", "reason": None, "adjusted": False}}
        self.assertIsNone(feed.todays_session(self.con, lambda c: None))
        self.assertIsNone(feed.todays_session(self.con, lambda c: {"today": None}))
        self.assertEqual(feed.todays_session(self.con, lambda c: plan_ctx), {
            "phase": "base", "week_no": 3, "kind": "easy", "title": "Easy run", "target": "x",
            "adjusted": False, "reason": None})
        out = feed.feed_data(self.con, date(2026, 10, 25), load_plan=lambda c: None)
        self.assertIsNone(out["todays_session"])
        out = feed.feed_data(self.con, date(2026, 10, 25), load_plan=lambda c: 1 / 0)   # a failing part is None
        self.assertIsNone(out["todays_session"])


if __name__ == "__main__":
    unittest.main()
