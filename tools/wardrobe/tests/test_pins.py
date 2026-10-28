import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app import pins  # noqa: E402


class PinTests(unittest.TestCase):
    def test_allowed_pages(self):
        for u in ("https://www.pinterest.com/pin/123/", "https://pinterest.co.uk/pin/1",
                  "https://pin.it/abc", "https://pinterest.de/pin/1"):
            self.assertTrue(pins.allowed_page_url(u), u)

    def test_rejected_pages(self):
        for u in ("http://www.pinterest.com/pin/1", "https://evil.com/pinterest.com",
                  "https://pinterest.com.evil.com/", "https://192.168.0.1/", "https://localhost/",
                  "https://pinterest.com@evil.com/", "https://pinterest.com:8080/x",
                  "https://notpinterest.com/", "ftp://pinterest.com/", "", "https://[::1]/",
                  "https://pinterest.xyz.de/", "https://pinterest.foo/", "https://www.pinterest.abc.uk/"):
            self.assertFalse(pins.allowed_page_url(u), u)

    def test_api_host_redirect(self):
        self.assertTrue(pins.allowed_page_url("https://api.pinterest.com/url_shortener/x/redirect/"))
        self.assertFalse(pins.allowed_page_url("https://api.pinterest.de/x"))
        self.assertFalse(pins.allowed_page_url("https://evil.api.pinterest.com/x"))

    def test_userinfo_rejected(self):
        for u in ("https://user:pw@pinterest.com/", "https://127.0.0.1\\@pinterest.com/",
                  "https://127.0.0.1%2f@pinterest.com/", "https://x@pin.it/a"):
            self.assertFalse(pins.allowed_page_url(u), u)
        self.assertFalse(pins.allowed_image_url("https://u@i.pinimg.com/a.jpg"))
        self.assertFalse(pins.allowed_image_url("https://i.pinimg.com\\@i.pinimg.com/a.jpg"))

    def test_http_exception_becomes_pinerror(self):
        import http.client
        from unittest import mock
        with mock.patch("urllib.request.OpenerDirector.open",
                        side_effect=http.client.IncompleteRead(b"x")):
            with self.assertRaises(pins.PinError):
                pins._get("https://pinterest.com/", pins.allowed_page_url, 100)

    def test_image_host(self):
        self.assertTrue(pins.allowed_image_url("https://i.pinimg.com/736x/a.jpg"))
        for u in ("https://pinimg.com/a.jpg", "http://i.pinimg.com/a.jpg",
                  "https://i.pinimg.com.evil.com/a.jpg", "https://10.0.0.1/a.jpg"):
            self.assertFalse(pins.allowed_image_url(u), u)

    def test_og_image(self):
        html = '<html><head><meta property="og:image" content="https://i.pinimg.com/x.jpg"></head>'
        self.assertEqual(pins.extract_og_image(html), "https://i.pinimg.com/x.jpg")
        self.assertIsNone(pins.extract_og_image("<html><head></head></html>"))

    def test_fetch_rejects_bad_host_without_network(self):
        with self.assertRaises(pins.PinError):
            pins.fetch_image("https://example.com/pin/1")


if __name__ == "__main__":
    unittest.main()
