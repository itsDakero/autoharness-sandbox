import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import goodreads  # noqa: E402

HEAD = ("Book Id,Title,Author,ISBN,ISBN13,My Rating,Number of Pages,Date Read,Date Added,"
        "Exclusive Shelf,My Review,Private Notes\n")


def csv_of(*rows):
    return HEAD + "".join(rows)


class ParseTests(unittest.TestCase):
    def test_isbn_wrapper(self):
        self.assertEqual(goodreads.clean_isbn('="9781408891384"'), "9781408891384")
        self.assertEqual(goodreads.clean_isbn('=""'), None)
        self.assertEqual(goodreads.clean_isbn(""), None)
        self.assertEqual(goodreads.clean_isbn("0593820282"), "0593820282")

    def test_ratings(self):
        self.assertEqual(goodreads.parse_rating("4.0"), 4)
        self.assertEqual(goodreads.parse_rating("0"), None)
        self.assertEqual(goodreads.parse_rating(""), None)
        self.assertEqual(goodreads.parse_rating("x"), None)

    def test_row(self):
        rows, skipped = goodreads.parse_csv(csv_of(
            '1,"Dune, Part 1",Frank Herbert,"=""0441172717""","=""""",4.0,412,2026/08/28,2026/08/03,read,"Good",priv\n'))
        self.assertEqual(skipped, [])
        b = rows[0][1]
        self.assertEqual((b["isbn10"], b["isbn13"], b["rating"], b["pages"]), ("0441172717", None, 4, 412))
        self.assertEqual((b["date_finished"], b["date_added"], b["shelf"]), ("2026-08-28", "2026-08-03", "read"))
        self.assertEqual((b["review"], b["notes"], b["title"]), ("Good", "priv", "Dune, Part 1"))

    def test_shelves(self):
        rows, _ = goodreads.parse_csv(csv_of(
            '1,A,X,,,0,,,,to-read,,\n', '2,B,X,,,0,,,,currently-reading,,\n', '3,C,X,,,0,,,,abandoned,,\n'))
        self.assertEqual([r[1]["shelf"] for r in rows], ["want", "reading", "read"])
        self.assertEqual(rows[2][1]["notes"], "Goodreads shelf: abandoned")

    def test_no_title_skipped(self):
        rows, skipped = goodreads.parse_csv(csv_of('1,,X,,,0,,,,read,,\n'))
        self.assertEqual(rows, [])
        self.assertEqual(skipped[0][1], "no title")

    def test_bom(self):
        rows, _ = goodreads.parse_csv(("﻿" + csv_of('1,A,X,,,0,,,,read,,\n')).encode("utf-8"))
        self.assertEqual(rows[0][1]["title"], "A")
        rows, _ = goodreads.parse_csv(b"\xef\xbb\xbf" + csv_of('1,A,X,,,0,,,,read,,\n').encode())
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
