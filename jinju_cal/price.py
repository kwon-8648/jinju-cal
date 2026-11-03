"""한국금거래소 '내가 살 때' 시세 조회 (PC 프로그램이라 금거래소에 바로 접속, 안 되면 서울 중계 주소)."""
from __future__ import annotations

import socket
import ssl
import threading
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, Signal

from .core import PriceError, parse_api

PRICE_URLS = ["https://www.koreagoldx.co.kr/api/main", "https://gold-cal.web.app/api/price"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.koreagoldx.co.kr/",
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


def fetch_quote(url: str, timeout: float = 15.0):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            if resp.status != 200:
                raise PriceError(f"HTTP {resp.status}")
            try:
                text = resp.read().decode("utf-8", errors="replace")
            except Exception:
                raise PriceError("응답이 중간에 끊김")
    except PriceError:
        raise
    except Exception as e:
        raise PriceError(_reason(e))
    return parse_api(text)


SOURCE_NAMES = ["금거래소", "중계"]


def fetch_any(urls=None):
    """주소를 차례로 시도. 모두 실패하면 주소마다의 실패 원인을 함께 알려 줌."""
    urls = urls or PRICE_URLS
    errs = []
    for i, url in enumerate(urls):
        try:
            return fetch_quote(url)
        except PriceError as e:
            name = SOURCE_NAMES[i] if i < len(SOURCE_NAMES) else f"주소 {i + 1}"
            errs.append(f"{name}: {e}")
    raise PriceError(" / ".join(errs) or "조회 실패")


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
