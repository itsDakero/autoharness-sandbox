import os
import random
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import outfits  # noqa: E402

_n = [0]


def item(cat, colours=("black",), seasons=(), style="casual", **kw):
    _n[0] += 1
    d = {"id": _n[0], "kind": "owned", "status": "active", "category": cat,
         "colours": list(colours), "seasons": list(seasons), "style": style,
         "tag_status": "tagged", "brand": ""}
    d.update(kw)
    return d


def basic():
    return [item("top"), item("bottom"), item("shoes")]


def pick(pool, season="autumn", weather=None, **kw):
    return outfits.pick(pool, season, weather, rng=random.Random(1), **kw)


class PoolTests(unittest.TestCase):
    def test_never_picks_wishlist_retired_pending_failed(self):
        bad = [item("top", kind="wishlist"), item("top", status="retired"),
               item("bottom", tag_status="pending"), item("shoes", tag_status="failed"),
               item("top", category=None)]
        self.assertEqual(outfits.build_pool(bad), [])
        items, note = pick(bad)
        self.assertIsNone(items)
        self.assertIn("shoes", note)
        good = basic()
        items, _ = pick(good + bad)
        self.assertEqual({i["id"] for i in items}, {i["id"] for i in good})

    def test_empty_pool_reason_names_category(self):
        self.assertIn("shoes", pick([item("top"), item("bottom")])[1])
        self.assertIn("bottom", pick([item("top"), item("shoes")])[1])
        self.assertIn("shoes", pick([])[1])

    def test_dress_shape(self):
        items, _ = pick([item("dress"), item("shoes")])
        self.assertEqual(sorted(i["category"] for i in items), ["dress", "shoes"])

    def test_accessories_ignored(self):
        items, _ = pick(basic() + [item("accessory")])
        self.assertEqual(len(items), 3)

    def test_season_fit_and_empty_means_all(self):
        pool = [item("top", seasons=["summer"]), item("bottom"), item("shoes")]
        self.assertIn("top", pick(pool, "winter")[1])
        self.assertEqual(len(pick(pool, "summer")[0]), 3)


class OuterTests(unittest.TestCase):
    def test_need_thresholds(self):
        n = outfits.outer_need
        self.assertEqual(n({"tmax": 13.9, "rain": 0}), "required")
        self.assertEqual(n({"tmax": 22, "rain": 50}), "required")
        self.assertEqual(n({"tmax": 20, "rain": 49}), "none")
        self.assertEqual(n({"tmax": 14, "rain": 0}), "optional")
        self.assertEqual(n({"tmax": 19.9, "rain": 10}), "optional")
        self.assertEqual(n(None), "optional")

    def test_required_adds_outer_or_notes_missing(self):
        coat = item("outerwear")
        items, note = pick(basic() + [coat], "winter", {"tmax": 5, "rain": 0})
        self.assertIn(coat["id"], [i["id"] for i in items])
        items, note = pick(basic(), "winter", {"tmax": 5, "rain": 0})
        self.assertEqual(len(items), 3)
        self.assertIn(outfits.NOTE_NO_OUTER, note)

    def test_none_leaves_outer_out(self):
        items, _ = pick(basic() + [item("outerwear")], "summer", {"tmax": 25, "rain": 0})
        self.assertEqual(len(items), 3)


class RuleTests(unittest.TestCase):
    def test_colours(self):
        r = outfits.colour_rule
        self.assertTrue(r([item("top", ["red"]), item("bottom", ["navy"]), item("shoes", ["white"])]))
        self.assertTrue(r([item("top", ["red"]), item("bottom", ["blue"])]))
        self.assertFalse(r([item("top", ["red"]), item("bottom", ["blue"]), item("shoes", ["green"])]))
        self.assertFalse(r([item("top", ["multi"]), item("bottom", ["multi"])]))
        self.assertTrue(r([item("top", ["multi"]), item("bottom", ["black"])]))

    def test_shoes_colour_counts(self):
        pool = [item("top", ["red"]), item("bottom", ["blue"]), item("shoes", ["green"])]
        self.assertIn("colour", pick(pool)[1])

    def test_style_clash(self):
        r = outfits.style_rule
        self.assertFalse(r([item("top", style="sport"), item("bottom", style="smart")]))
        self.assertFalse(r([item("top", style="sport"), item("bottom", style="formal")]))
        self.assertFalse(r([item("top", style="casual"), item("bottom", style="formal")]))
        self.assertTrue(r([item("top", style="smart"), item("bottom", style="formal")]))
        self.assertTrue(r([item("top", style=None), item("bottom", style="formal")]))


class VoteAndWindowTests(unittest.TestCase):
    def test_downvoted_key_never_returned(self):
        pool = basic() + [item("top")]
        first, _ = pick(pool)
        bad = outfits.key_of(first)
        for seed in range(20):
            items, _ = outfits.pick(pool, "autumn", rng=random.Random(seed), exclude_keys={bad})
            self.assertNotEqual(outfits.key_of(items), bad)

    def test_all_excluded_gives_reason(self):
        pool = basic()
        k = outfits.key_of(pool)
        items, note = pick(pool, exclude_keys={k})
        self.assertIsNone(items)
        self.assertTrue(note)

    def test_weights_clamped_and_formula(self):
        a, b = item("top", ["red"]), item("bottom", ["blue"])
        by = {a["id"]: a, b["id"]: b}
        f = "c:blue|red"
        w = outfits.weights([(1, [a["id"], b["id"]])] * 2, by)
        self.assertAlmostEqual(w[f], 1.4)
        w = outfits.weights([(1, [a["id"], b["id"]])] * 50, by)
        self.assertEqual(w[f], 3.0)
        w = outfits.weights([(-1, [a["id"], b["id"]])] * 50, by)
        self.assertEqual(w[f], 0.2)
        self.assertEqual(outfits.weights([(1, [999])], by), {})

    def test_weights_steer_choice(self):
        t1, t2 = item("top", ["red"]), item("top", ["green"])
        bt, sh = item("bottom", ["black"]), item("shoes", ["black"])
        pool = [t1, t2, bt, sh]
        by = {i["id"]: i for i in pool}
        w = outfits.weights([(1, [t1["id"], bt["id"], sh["id"]])] * 10
                            + [(-1, [t2["id"], bt["id"], sh["id"]])] * 10, by)
        wins = sum(outfits.pick(pool, "autumn", w=w, rng=random.Random(s))[0][0]["id"] == t1["id"]
                   for s in range(30))
        self.assertGreater(wins, 25)

    def test_repeat_window_and_fallback(self):
        t1, t2, bt, sh = item("top"), item("top"), item("bottom"), item("shoes")
        pool = [t1, t2, bt, sh]
        for s in range(10):
            items, note = outfits.pick(pool, "autumn", rng=random.Random(s), recent_ids={t1["id"]})
            self.assertEqual(items[0]["id"], t2["id"])
            self.assertEqual(note, "")
        items, note = outfits.pick(pool, "autumn", rng=random.Random(1),
                                   recent_ids={t1["id"], t2["id"]})
        self.assertIsNotNone(items)
        self.assertIn(outfits.NOTE_REPEAT, note)

    def test_shoes_may_repeat(self):
        pool = basic()
        items, note = outfits.pick(pool, "autumn", rng=random.Random(1),
                                   recent_ids={pool[2]["id"]})
        self.assertIsNotNone(items)
        self.assertEqual(note, "")

    def test_cap_samples(self):
        pool = [item("top") for _ in range(40)] + [item("bottom") for _ in range(40)] \
            + [item("shoes") for _ in range(40)]
        items, _ = outfits.pick(pool, "autumn", rng=random.Random(1))
        self.assertEqual(len(items), 3)


if __name__ == "__main__":
    unittest.main()
