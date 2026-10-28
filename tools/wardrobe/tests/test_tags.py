import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import tags  # noqa: E402


class TagTests(unittest.TestCase):
    def test_good_reply(self):
        r = tags.parse_reply('{"category":"Top","colours":["Navy","white"],"seasons":["summer"],'
                             '"style":"casual","brand":"Acme"}')
        self.assertEqual(r["category"], "top")
        self.assertEqual(r["colours"], ["navy", "white"])
        self.assertEqual(r["brand"], "Acme")

    def test_stray_values_dropped(self):
        r = tags.parse_reply('{"category":"top","colours":["teal","red","x","black","blue"],'
                             '"seasons":["monsoon","winter"],"style":"goth"}')
        self.assertEqual(r["colours"], ["red", "black", "blue"])
        self.assertEqual(r["seasons"], ["winter"])
        self.assertIsNone(r["style"])

    def test_bad_category_fails(self):
        with self.assertRaises(tags.TagError):
            tags.parse_reply('{"category":"hat","colours":[]}')
        with self.assertRaises(tags.TagError):
            tags.parse_reply('{"colours":["red"]}')

    def test_non_json_and_empty(self):
        for bad in ("", "   ", None, "sorry, no", "[1,2]", "{broken"):
            with self.assertRaises(tags.TagError):
                tags.parse_reply(bad)

    def test_fenced_and_wrapped_json(self):
        r = tags.parse_reply('```json\n{"category":"shoes"}\n```')
        self.assertEqual(r["category"], "shoes")
        r = tags.parse_reply('Here: {"category":"dress"} done')
        self.assertEqual(r["category"], "dress")

    def test_schema_enums(self):
        s = tags.json_schema()
        self.assertEqual(s["properties"]["category"]["enum"], tags.CATEGORIES)


if __name__ == "__main__":
    unittest.main()
