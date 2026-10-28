import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import db, goodreads  # noqa: E402

HEAD = "Book Id,Title,Author,ISBN,ISBN13,My Rating,Number of Pages,Date Read,Date Added,Exclusive Shelf\n"
CSV = HEAD + (
    '10,Dune,Frank Herbert,,"=""9780441172719""",5.0,412,2026/01/02,2026/01/01,read\n'
    '11,No Isbn Book,Jane Doe,,"=""""",0,,,2026/02/01,to-read\n'
    '12,Now Reading,Jo Bloggs,,"=""""",0,300,,2026/03/01,currently-reading\n')


def run(con, text):
    parsed, skipped = goodreads.parse_csv(text)
    return db.import_books(con, parsed, skipped)


class DbTests(unittest.TestCase):
    def setUp(self):
        self.con = db.connect(":memory:")

    def test_migrate_idempotent(self):
        db.migrate(self.con)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], len(db.MIGRATIONS))

    def test_import_and_reimport(self):
        r = run(self.con, CSV)
        self.assertEqual((len(r["added"]), len(r["updated"]), len(r["skipped"])), (3, 0, 0))
        r = run(self.con, CSV)
        self.assertEqual((len(r["added"]), len(r["updated"])), (0, 0))
        self.assertEqual(r["skipped"][0][1], "already in library")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM books").fetchone()[0], 3)

    def test_duplicate_row_in_file(self):
        r = run(self.con, CSV + '10,Dune,Frank Herbert,,"=""9780441172719""",5.0,412,,,read\n')
        self.assertEqual(len(r["added"]), 3)
        self.assertEqual(r["skipped"], [("Dune", "duplicate in file")])

    def test_edits_not_overwritten_but_empty_filled(self):
        run(self.con, CSV)
        b = self.con.execute("SELECT id FROM books WHERE title='Dune'").fetchone()
        db.update_book(self.con, b["id"], rating=2, pages=None)
        r = run(self.con, CSV)
        row = db.get(self.con, b["id"])
        self.assertEqual(row["rating"], 2)
        self.assertEqual(row["pages"], 412)
        self.assertEqual([t for t, _ in r["updated"]], ["Dune"])

    def test_match_order(self):
        db.insert_book(self.con, {"title": "Alpha", "authors": "A One", "goodreads_id": "1"})
        db.insert_book(self.con, {"title": "Beta", "authors": "B Two", "isbn13": "9781111111111"})
        db.insert_book(self.con, {"title": "Gamma", "authors": "C Three, D Four"})
        m = db.find_match
        self.assertEqual(m(self.con, {"title": "Other", "goodreads_id": "1"})["title"], "Alpha")
        self.assertEqual(m(self.con, {"title": "Other", "isbn13": "9781111111111"})["title"], "Beta")
        self.assertEqual(m(self.con, {"title": "GAMMA", "authors": "c three"})["title"], "Gamma")
        self.assertIsNone(m(self.con, {"title": "Gamma", "authors": "Someone Else"}))
        # goodreads id wins over a conflicting isbn13
        self.assertEqual(m(self.con, {"title": "x", "goodreads_id": "1", "isbn13": "9781111111111"})["title"], "Alpha")

    def test_unknown_shelf_becomes_read(self):
        r = run(self.con, HEAD + '1,Odd,X,,,0,,,,favourites\n')
        self.assertEqual(r["added"], [("Odd", "read")])
        row = self.con.execute("SELECT * FROM books").fetchone()
        self.assertEqual(row["notes"], "Goodreads shelf: favourites")

    def test_progress_and_finish(self):
        run(self.con, CSV)
        b = self.con.execute("SELECT * FROM books WHERE shelf='reading'").fetchone()
        self.assertEqual(b["date_started"], db.today())
        db.set_progress(self.con, b["id"], page=150)
        self.assertEqual(db.current(self.con)[0]["percent_read"], 50)
        db.finish(self.con, b["id"], 4, "2026-10-01")
        b = db.get(self.con, b["id"])
        self.assertEqual((b["shelf"], b["rating"], b["percent"]), ("read", 4, 100))
        self.assertEqual(db.current(self.con), [])

    def test_stats(self):
        run(self.con, CSV)
        s = db.stats(self.con, "2026")
        self.assertEqual((s["read_this_year"], s["want_to_read"], s["reading"]), (1, 1, 1))

    def test_cover_jobs(self):
        run(self.con, CSV)
        j = db.next_cover_job(self.con)
        db.set_cover(self.con, j["id"], "error")
        self.assertNotEqual(db.next_cover_job(self.con)["id"], j["id"])
        self.con.execute("UPDATE books SET cover_checked_at='2000-01-01 00:00:00' WHERE id=?", (j["id"],))
        for r in self.con.execute("SELECT id FROM books WHERE id!=?", (j["id"],)).fetchall():
            db.set_cover(self.con, r["id"], "none")
        self.assertEqual(db.next_cover_job(self.con)["id"], j["id"])


if __name__ == "__main__":
    unittest.main()
