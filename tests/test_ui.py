"""화면·시세 조회 동작 확인 (화면 없이 실행): python tests/test_ui.py"""
import http.server
import json
import os
import sys
import tempfile
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["JINJU_CAL_DATA"] = tempfile.mkdtemp()
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QLabel  # noqa: E402

from jinju_cal import core, price, storage, ui  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("  ok  " if cond else "  FAIL ") + name + (("  " + str(extra)) if extra and not cond else ""))
    if not cond:
        fails.append(name)


def pump(ms=200):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


# ---------------------------------------------------------------- 시세 조회 (가짜 서버)
# 2026-10-31 실제 /api/main 응답 중 officialPrice4 부분 (s_pure = 내가 살 때)
SAMPLE = {"date": "2026-10-31 15:40:50", "officialPrice4": {
    "date": "2026-10-31 08:45:57", "s_pure": 731000, "p_pure": 626000,
    "s_silver": 8860, "p_silver": 7530, "s_white": 268000, "p_white": 217000}}
SITE = {"mode": "xrw", "calls": []}  # xrw: X-Requested-With POST 만 / csrf: 토큰+쿠키까지 / down: 모두 실패


class H(http.server.BaseHTTPRequestHandler):
    def _json(self, code, obj=None):
        body = json.dumps(obj if obj is not None else {"error": code}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        SITE["calls"].append(("GET", self.path))
        if self.path == "/":
            body = b'<html><head><meta name="csrf-token" content="TOKEN123"></head></html>'
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Set-Cookie", "XSRF=abc; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/relay":
            self._json(200, SAMPLE) if SITE["mode"] != "down" else self._json(405)
        else:
            self._json(405)  # 바뀐 사이트: GET 거부

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        SITE["calls"].append(("POST", self.path, self.headers.get("X-CSRF-TOKEN")))
        if SITE["mode"] == "down" or self.headers.get("X-Requested-With") != "XMLHttpRequest":
            return self._json(403 if SITE["mode"] != "down" else 503)
        if SITE["mode"] == "csrf" and not (self.headers.get("X-CSRF-TOKEN") == "TOKEN123" and "XSRF=abc" in (self.headers.get("Cookie") or "")):
            return self._json(403)
        self._json(200, SAMPLE)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base_url = f"http://127.0.0.1:{srv.server_port}"
price.KGX_BASE, price.RELAY_URL = base_url, base_url + "/relay"

q = price.fetch_koreagoldx()
check("금거래소: X-Requested-With POST 로 시세 받음", q["buy"] == 731000 and q["date"] == "2026-10-31 08:45:57", q)
check("첫 요청이 POST", SITE["calls"][0][0] == "POST", SITE["calls"][:2])
SITE.update(mode="csrf", calls=[])
q = price.fetch_koreagoldx()
check("토큰이 필요하면 홈페이지 토큰·쿠키로 다시", q["buy"] == 731000 and ("POST", "/api/main", "TOKEN123") in SITE["calls"], SITE["calls"])
SITE.update(mode="down", calls=[])
try:
    price.fetch_any()
    check("모두 실패하면 오류", False)
except core.PriceError as e:
    check("모두 실패하면 방식마다 원인", str(e) == "금거래소 POST HTTP 503, POST+토큰 HTTP 503, GET HTTP 405 / 중계: HTTP 405", e)
SITE.update(mode="xrw")
try:
    price.fetch_quote("http://no-such-host.invalid/x", timeout=5)
except core.PriceError as e:
    check("주소 못 찾음", str(e).startswith("주소를 찾지 못함") or str(e).startswith("접속 실패"), e)

# ---------------------------------------------------------------- 화면
app = QApplication([])
app.setStyle("Fusion")
app.setStyleSheet(ui.stylesheet())
w = ui.MainWindow()
w.resize(1180, 900)
w.show()
pump(1500)
check("실행 시 자동조회", w.has_price and w.price == 731000 and w.source == "api", w.o_status.text())
check("상태줄 문구", w.o_status.text().startswith("API 조회 완료") and "제공일 2026-10-31 08:45:57" in w.o_status.text(), w.o_status.text())
check("10분 자동조회 타이머", w.auto_timer.isActive() and w.auto_timer.interval() == 600000)

# 검색·코드·상품명·상호·품목·저장·삭제가 없어야 함
texts = [x.text() for x in w.findChildren(QLabel)] + [x.text() for x in w.findChildren(QPushButton)]
holders = [x.placeholderText() for x in w.findChildren(QLineEdit)]
for word in ("검색", "코드", "상품명", "상호", "품목"):
    check(f"'{word}' 칸 없음", not any(t.strip() == word or t.startswith(word + " ") for t in texts) and not any(word in h for h in holders))
for word in ("저장", "삭제"):
    check(f"'{word}' 버튼 없음", word not in [b.text() for b in w.findChildren(QPushButton)])

exp = {k: core.karat(731000, 10, 3.75, 50000, 0, 0, p, 30, 100) for k, p in (("10", 41.7), ("14", 58.5), ("18", 75))}
for k in exp:
    check(f"{k}K 기본값 판매가", w.krows[k][3].text() == core.won(exp[k]["final"]), (w.krows[k][3].text(), exp[k]["final"]))
pp = core.pure(731000, 10, 3.75, 0, 50000, 100)
check("순금 4칸", [w.pcells[x].text() for x in ("p1x", "p1i", "p2x", "p2i")] == [core.won(pp[x]) for x in ("x1", "i1", "x2", "i2")])
check("부가세 별도", w.o_base.text() == core.won(731000 / 1.1))

w.i_price.setText("598,000")
w.apply_manual()
check("수동 시세", w.price == 598000 and w.source == "manual" and w.o_status.text().startswith("수동 입력 시세 적용"))

# 돈 입력 → g (계산은 원래 값), 화이트 추가금, 알값·셋팅비, 1,000원 올림
w.f["ad"].setText("1.333")
w.k_color.setCurrentIndex(w.k_color.findData("화이트"))
w.f["dia"].setText("30,000")
w.f["set"].setText("15000")
w.f_unit.setCurrentIndex(1)
pump(50)
check("돈 → g 표시", w.f["ag"].text() == "5.00" and abs(w.ag_exact - 1.333 * 3.75) < 1e-12, (w.f["ag"].text(), w.ag_exact))
e = core.karat(598000, 10, 1.333 * 3.75, 50000, 30000, 15000, 58.5, 30, 1000)
check("14K 화이트 판매가", w.krows["14"][3].text().startswith(core.won(e["final"] + 20000)), w.krows["14"][3].text())
w.f["m14"].setText("100")
pump(50)
check("마진 100% → 빨간 칸", w.f["m14"].property("invalid") == "true" and w.krows["14"][3].text() == "입력 확인")
w.f["m14"].setText("30")
w.kchk["10"].setChecked(False)
pump(50)
check("10K 숨김", not w.krows["10"][3].isVisible() and w.krows["14"][3].isVisible())
w.f["pg"].setText("11.25")
pump(50)
check("순금 g → 돈", w.f["pd"].text() == "3.00")

w.clear_section("p")
check("순금 초기화", all(w.f[k].text() == "" for k in ("pg", "pd", "ring", "pl")) and w.pcells["p1x"].text() == "-")
w.close()
pump(50)
s = storage.load()
check("설정 저장", s.get("dia") == "30,000" and s.get("show10") == "0" and s.get("unit") == "1" and s.get("price") == "598000", s)

w2 = ui.MainWindow()
check("다시 열면 복원", w2.f["dia"].text() == "30,000" and not w2.kchk["10"].isChecked() and w2.f_unit.currentIndex() == 1 and w2.i_price.text() == "598,000")
check("최소 너비 안에서 가로로 안 잘림", w2.minimumWidth() <= 1100, w2.minimumWidth())
check("버전 표시", w2.ver.text() == "v" + __import__("jinju_cal").__version__)
w2.close()

print("실패 %d건" % len(fails) if fails else "모두 통과")
srv.shutdown()
sys.exit(1 if fails else 0)
