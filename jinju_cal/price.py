"""한국금거래소 '내가 살 때' 시세 조회 (PC 프로그램이라 금거래소에 바로 접속, 안 되면 서울 중계 주소).

2026-10 사이트 변경: /api/main 은 GET 이면 405, X-Requested-With 없는 POST 는 403.
홈페이지(jQuery $.ajax type:'post')와 같은 방식으로 요청함 — 고금시세계산 v1.15 와 같은 해결.
응답 형식(officialPrice4)은 그대로.
"""
from __future__ import annotations

import http.cookiejar
import re
import socket
import ssl
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

from .core import PriceError, parse_api

KGX_BASE = "https://www.koreagoldx.co.kr"
RELAY_URL = "https://gold-cal.web.app/api/price"  # 매장관리 웹의 서울 중계 (마지막 수단)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _ssl_context():
    try:
        import certifi  # 맥에서 인증서 목록이 비어 있어도 접속되게
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _reason(e: BaseException) -> str:
    """접속 실패 원인을 알아볼 수 있는 말로."""
    if isinstance(e, urllib.error.HTTPError):
        return f"HTTP {e.code}"
    r = e.reason if isinstance(e, urllib.error.URLError) else e
    if isinstance(r, ssl.SSLCertVerificationError):
        return "보안 인증서 확인 실패"
    if isinstance(r, ssl.SSLError):
        return "보안 연결 실패"
    if isinstance(r, (socket.timeout, TimeoutError)):
        return "응답 시간 초과"
    if isinstance(r, socket.gaierror):
        return "주소를 찾지 못함 (인터넷 연결 확인)"
    if isinstance(r, ConnectionRefusedError):
        return "서버가 접속을 거부함"
    if isinstance(r, (ConnectionResetError, ConnectionAbortedError)):
        return "서버가 연결을 끊음"
    if isinstance(r, OSError) and getattr(r, "errno", None) in (50, 51, 65, 101):
        return "인터넷 연결 없음"
    return f"접속 실패 ({type(r).__name__})"


def _send(opener, url, method="GET", headers=None, timeout=15.0) -> str:
    data = b"" if method == "POST" else None
    req = urllib.request.Request(url, data=data, method=method, headers={**HEADERS, **(headers or {})})
    try:
        with opener.open(req, timeout=timeout) as resp:
            if resp.status != 200:
                raise PriceError(f"HTTP {resp.status}")
            try:
                return resp.read().decode("utf-8", errors="replace")
            except Exception:
                raise PriceError("응답이 중간에 끊김")
    except PriceError:
        raise
    except Exception as e:
        raise PriceError(_reason(e))


def _opener():
    """쿠키를 이어 쓰는 연결 (보안 토큰을 받은 뒤 다시 요청할 때 필요)."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        urllib.request.HTTPSHandler(context=_ssl_context()))


def _csrf_token(html: str):
    m = re.search(r"""<meta[^>]+name=["']csrf-token["'][^>]+content=["']([^"']+)""", html)
    if not m:
        m = re.search(r"""<meta[^>]+content=["']([^"']+)["'][^>]+name=["']csrf-token""", html)
    return m.group(1) if m else None


def fetch_koreagoldx(base_url: str = None, timeout: float = 15.0):
    """금거래소에 홈페이지와 같은 방식으로 요청. 방식마다 실패 원인을 모아 알려 줌."""
    base_url = (base_url or KGX_BASE).rstrip("/")
    home, api = base_url + "/", base_url + "/api/main"
    opener = _opener()
    site = {"Referer": home, "Origin": base_url, "X-Requested-With": "XMLHttpRequest"}
    form = {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8"}

    def with_token():
        page = _send(opener, home, headers={"Accept": "text/html,*/*"}, timeout=timeout)
        token = _csrf_token(page)
        if not token:
            raise PriceError("보안 토큰 없음")
        return _send(opener, api, "POST", {**site, **form, "X-CSRF-TOKEN": token}, timeout)

    steps = [
        ("POST", lambda: _send(opener, api, "POST", {**site, **form}, timeout)),
        ("POST+토큰", with_token),
        ("GET", lambda: _send(opener, api, "GET", {"Referer": home}, timeout)),
    ]
    errs = []
    for label, send in steps:
        try:
            return parse_api(send())
        except PriceError as e:
            errs.append(f"{label} {e}")
    raise PriceError("금거래소 " + ", ".join(errs))


def fetch_quote(url: str, timeout: float = 15.0):
    """주소 하나에 GET 으로 묻기 (중계 주소용)."""
    return parse_api(_send(_opener(), url, "GET", {"Accept": "application/json"}, timeout))


def fetch_any():
    """금거래소 → 안 되면 중계. 둘 다 실패하면 각각의 원인을 함께 알려 줌."""
    try:
        return fetch_koreagoldx()
    except PriceError as e1:
        first = str(e1)
    try:
        return fetch_quote(RELAY_URL)
    except PriceError as e2:
        raise PriceError(f"{first} / 중계: {e2}")


class PriceFetcher(QObject):
    """백그라운드에서 조회하고 화면 스레드로 결과를 보냄."""
    done = Signal(object, object)  # (quote | None, 오류 문구 | None)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            q = fetch_any()
            self.done.emit(q, None)
        except PriceError as e:
            self.done.emit(None, str(e))
        except Exception as e:  # 예상 못 한 오류도 화면에는 알림
            self.done.emit(None, str(e) or "조회 실패")
