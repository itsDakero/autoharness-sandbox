import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import gaps, outfits  # noqa: E402

_n = [1000]


def item(cat, colours=("black",), seasons=(), style="casual", **kw):
    _n[0] += 1
    d = {"id": _n[0], "kind": "owned", "status": "active", "category": cat,
         "colours": list(colours), "seasons": list(seasons), "style": style,
         "tag_status": "tagged", "brand": ""}
    d.update(kw)
    return d


def basic():
    return [item("top"), item("bottom"), item("shoes")]


def find(rows, cat, colour):
    return [r for r in rows if r["category"] == cat and r["colour"] == colour]


class GapTests(unittest.TestCase):
    def test_grey_bottom_unlocks_one(self):
        rows = gaps.rank(basic(), "autumn")
        r = find(rows, "bottom", "grey")
        self.assertEqual(r[0]["unlocks"], 1)
        self.assertEqual(r[0]["size"], "size not set")
        self.assertEqual(r[0]["max_price"], "no limit")

    def test_owned_colour_not_suggested(self):
        rows = gaps.rank(basic(), "autumn")
        self.assertEqual(find(rows, "bottom", "black"), [])
        # owned only for winter: still missing in autumn
        pool = [item("top"), item("bottom", seasons=["winter"]), item("shoes")]
        self.assertEqual(find(gaps.rank(pool, "winter"), "bottom", "black"), [])
        self.assertTrue(find(gaps.rank(pool, "autumn"), "bottom", "black"))

    def test_dress_budget_zero(self):
        pool = basic()
        self.assertTrue(find(gaps.rank(pool, "autumn"), "dress", "grey"))
        rows = gaps.rank(pool, "autumn", {"max_price_dress": "0"})
        self.assertFalse([r for r in rows if r["category"] == "dress"])

    def test_clash_and_colour_not_counted(self):
        pool = [item("top", style="sport"), item("bottom", colours=("red",)),
                item("shoes", colours=("green",))]
        # red + green already 2 non-neutral; a pink top would be a 3rd
        pool2 = [item("top", colours=("red",)), item("bottom", colours=("green",)), item("shoes")]
        self.assertEqual(find(gaps.rank(pool2, "autumn"), "shoes", "pink"), [])
        self.assertTrue(find(gaps.rank(pool2, "autumn"), "shoes", "grey"))
        # candidates have no style, so a clash among owned items does not hide them
        pool3 = [item("top", style="sport"), item("bottom", style="smart"), item("shoes")]
        self.assertEqual(gaps.analyse(pool3, "autumn")[1], 0)
        self.assertEqual(pool[0]["style"], "sport")

    def test_empty_pool(self):
        rows, current, reason = gaps.analyse([], "autumn")
        self.assertEqual(rows, [])
        self.assertEqual(current, 0)
        self.assertIn("shoes", reason)

    def test_bad_profile(self):
        prof = {"max_price_top": "abc", "max_price_bottom": "nan", "max_price_shoes": "-3",
                "currency": ""}
        rows = gaps.rank(basic(), "autumn", prof)
        self.assertTrue(rows)
        self.assertTrue(all(r["max_price"] == "no limit" for r in rows))
        rows = gaps.rank(basic(), "autumn", {"max_price_top": "40.5", "currency": "EUR"})
        self.assertEqual(find(rows, "top", "grey")[0]["max_price"], "up to EUR 40.50")

    def test_large_pool_deterministic(self):
        cols = ["black", "white", "grey", "navy", "beige", "brown"]
        pool = ([item("top", colours=(cols[i % 6],)) for i in range(30)]
                + [item("bottom", colours=(cols[i % 6],)) for i in range(30)]
                + [item("shoes", colours=(cols[i % 6],)) for i in range(30)])
        self.assertGreater(30 ** 3, gaps.GAP_COMBOS)
        t = time.time()
        a = gaps.rank(pool, "autumn")
        self.assertLess(time.time() - t, 15)
        self.assertEqual(a, gaps.rank(pool, "autumn"))

    def test_wishlist_flag(self):
        wish = [{"category": "bottom", "colours": ["grey"]}]
        rows = gaps.rank(basic(), "autumn", wishlist=wish)
        self.assertTrue(find(rows, "bottom", "grey")[0]["on_wishlist"])
        self.assertFalse(find(rows, "bottom", "navy")[0]["on_wishlist"])

    def test_all_season_items_count(self):
        pool = [item("top", seasons=[]), item("bottom", seasons=[]), item("shoes", seasons=[])]
        for s in gaps.SEASONS:
            self.assertEqual(gaps.analyse(pool, s)[1], 1)
        self.assertEqual(outfits.MAX_COMBOS, 50_000)


if __name__ == "__main__":
    unittest.main()
