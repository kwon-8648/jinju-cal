"""2026-10 한국금거래소 변경(GET 405, X-Requested-With 없는 POST 403) 대응 검사."""
import json
import tempfile
import os
import unittest
from unittest.mock import patch

import core

# 2026-10-31 실제 /api/main 응답 중 officialPrice4 부분
PAYLOAD = {"date": "2026-10-31 15:40:50", "officialPrice4": {
    "date": "2026-10-31 08:45:57", "s_pure": 731000, "p_pure": 626000,
    "s_silver": 8860, "p_silver": 7530, "s_white": 268000, "p_white": 217000,
    "s_18k": 537285, "p_18k": 460200, "s_14k": 416670, "p_14k": 356900}}


class FakeResponse:
    def __init__(self, status, payload=None, text=""):
        self.status_code, self._payload, self.text = status, payload, text
        self.url = core.MAIN_API

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class SiteSession:
    """Behaves like the site: only POST with X-Requested-With succeeds."""
    def __init__(self, require_csrf=False):
        self.headers, self.calls, self.require_csrf = {}, [], require_csrf

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        if url == core.HOME_URL:
            return FakeResponse(200, text='<meta name="csrf-token" content="TOKEN123">')
        return FakeResponse(405)

    def post(self, url, headers=None, **kwargs):
        merged = {**self.headers, **(headers or {})}
        self.calls.append(("POST", url, merged.get("X-CSRF-Token")))
        if merged.get("X-Requested-With") != "XMLHttpRequest":
            return FakeResponse(403)
        if self.require_csrf and merged.get("X-CSRF-Token") != "TOKEN123":
            return FakeResponse(403)
        return FakeResponse(200, PAYLOAD)


class FetchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"APPDATA": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_post_with_xrw_header(self):
        site = SiteSession()
        with patch.object(core.requests, "Session", return_value=site):
            prices, details = core.fetch_koreagoldx_prices()
        self.assertEqual(prices, {"GOLD": 626000, "SILVER": 7530, "PLATINUM": 217000})
        self.assertEqual(details["method"], "POST")
        self.assertEqual(site.calls[0][0], "POST")

    def test_csrf_fallback(self):
        site = SiteSession(require_csrf=True)
        with patch.object(core.requests, "Session", return_value=site):
            prices, details = core.fetch_koreagoldx_prices()
        self.assertEqual(prices["GOLD"], 626000)
        self.assertEqual(details["method"], "POST+CSRF")

    def test_all_fail_reports_each_method(self):
        class Down(SiteSession):
            def post(self, url, **kwargs):
                return FakeResponse(503)
        with patch.object(core.requests, "Session", return_value=Down()):
            with self.assertRaises(RuntimeError) as ctx:
                core.fetch_koreagoldx_prices()
        message = str(ctx.exception)
        for label in ("POST ", "POST+CSRF", "GET(legacy)"):
            self.assertIn(label, message)


if __name__ == "__main__":
    unittest.main()
