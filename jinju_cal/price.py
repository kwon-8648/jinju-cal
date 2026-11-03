"""한국금거래소 '내가 살 때' 시세 조회 (PC 프로그램이라 금거래소에 바로 접속, 안 되면 서울 중계 주소)."""
from __future__ import annotations

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
    except urllib.error.HTTPError as e:
        raise PriceError(f"HTTP {e.code}")
    except Exception:
        raise PriceError("인터넷 연결 또는 서버 접속 실패")
    return parse_api(text)


def fetch_any(urls=None):
    """주소를 차례로 시도. 모두 실패하면 첫 주소의 오류를 냄."""
    first = None
    for url in urls or PRICE_URLS:
        try:
            return fetch_quote(url)
        except PriceError as e:
            if first is None:
                first = e
    raise first or PriceError("조회 실패")


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
