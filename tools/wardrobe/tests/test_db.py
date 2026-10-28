import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db  # noqa: E402

TAGS = {"category": "top", "colours": ["red"], "seasons": ["summer"], "style": "casual", "brand": "X"}


class DbTests(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")

    def test_migrate_idempotent(self):
        db.migrate(self.con)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))

    def test_tag_flow(self):
        i = db.add_item(self.con, photo="a.jpg", thumb="a.jpg")
        self.assertEqual(db.next_pending(self.con)["id"], i)
        db.set_tagged(self.con, i, TAGS, "m")
        it = db.get_item(self.con, i)
        self.assertEqual((it["tag_status"], it["category"], it["colours"]), ("tagged", "top", ["red"]))
        self.assertIsNone(db.next_pending(self.con))
        db.save_fields(self.con, i, {"category": "bottom", "colours": [], "seasons": []})
        self.assertEqual(db.get_item(self.con, i)["tag_status"], "reviewed")

    def test_failed_and_retry(self):
        i = db.add_item(self.con, photo="a.jpg", thumb="a.jpg")
        db.set_failed(self.con, i, "nope")
        self.assertEqual(db.counts(self.con)["review"], 1)
        db.requeue(self.con, i)
        self.assertEqual(db.get_item(self.con, i)["tag_status"], "pending")

    def test_no_photo_not_pending_and_not_requeued(self):
        i = db.add_item(self.con, kind="wishlist", tag_status="failed", tag_error="x")
        db.requeue(self.con, i)
        self.assertEqual(db.get_item(self.con, i)["tag_status"], "failed")
        self.assertIsNone(db.next_pending(self.con))

    def test_late_result_does_not_overwrite_review(self):
        i = db.add_item(self.con, photo="a.jpg", thumb="a.jpg")
        db.save_fields(self.con, i, {"category": "shoes"})
        db.set_tagged(self.con, i, TAGS, "m")
        self.assertEqual(db.get_item(self.con, i)["category"], "shoes")

    def test_bought_retire_restore(self):
        i = db.add_item(self.con, kind="wishlist", photo="a.jpg", thumb="a.jpg")
        db.mark_bought(self.con, i)
        it = db.get_item(self.con, i)
        self.assertEqual(it["kind"], "owned")
        self.assertTrue(it["bought_at"])
        db.retire(self.con, i, "sold")
        self.assertEqual(db.list_items(self.con), [])
        self.assertEqual(len(db.list_items(self.con, status="retired")), 1)
        db.restore(self.con, i)
        self.assertEqual(len(db.list_items(self.con)), 1)

    def test_profile(self):
        db.set_profile(self.con, {"top_size": "M", "currency": "GBP"})
        db.set_profile(self.con, {"top_size": ""})
        self.assertEqual(db.get_profile(self.con), {"currency": "GBP"})

    def test_migration_2_keeps_v1_rows(self):
        import sqlite3
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        with con:
            for stmt in db.MIGRATIONS[0].split(";"):
                if stmt.strip():
                    con.execute(stmt)
            con.execute("PRAGMA user_version=1")
            con.execute("INSERT INTO items(kind,created_at,updated_at) VALUES('owned','t','t')")
            con.execute("INSERT INTO profile(key,value) VALUES('top_size','M')")
        db.migrate(con)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 2)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM items").fetchone()[0], 1)
        self.assertEqual(db.get_profile(con), {"top_size": "M"})
        self.assertEqual(db.list_wear(con), [])

    def test_outfit_vote_wear_daily(self):
        db.save_outfit(self.con, "1-2-3", [1, 2, 3])
        db.save_outfit(self.con, "1-2-3", [1, 2, 3])
        db.set_vote(self.con, "1-2-3", 1)
        db.set_vote(self.con, "1-2-3", -1)
        self.assertEqual(db.get_vote(self.con, "1-2-3"), -1)
        self.assertEqual(db.downvoted_keys(self.con), {"1-2-3"})
        self.assertEqual(db.list_votes(self.con), [(-1, [1, 2, 3])])
        self.assertTrue(db.add_wear(self.con, "2026-10-23", "1-2-3", [1, 2, 3]))
        self.assertFalse(db.add_wear(self.con, "2026-10-23", "1-2-3", [1, 2, 3]))
        self.assertEqual(len(db.list_wear(self.con)), 1)
        self.assertEqual(db.worn_ids(self.con), {1, 2, 3})
        db.delete_wear(self.con, db.list_wear(self.con)[0]["id"])
        self.assertEqual(db.list_wear(self.con), [])
        db.insert_daily(self.con, "d", "1-2-3", {"tmax": 1.0}, "n")
        db.insert_daily(self.con, "d", "9", None, "x")
        self.assertEqual(db.get_daily(self.con, "d"),
                         {"date": "d", "key": "1-2-3", "weather": {"tmax": 1.0}, "note": "n"})


if __name__ == "__main__":
    unittest.main()
