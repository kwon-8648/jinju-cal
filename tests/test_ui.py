"""화면·시세 조회 동작 확인 (화면 없이 실행): python tests/test_ui.py"""
import http.server
import json
import os
from pathlib import Path
import sys
import tempfile
import threading

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["JINJU_CAL_DATA"] = tempfile.mkdtemp()
os.environ["APPDATA"] = tempfile.mkdtemp()  # 고금 매입 설정(OldTownMetalCalculator)도 시험용 폴더에
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLineEdit, QPushButton, QLabel  # noqa: E402

from jinju_cal import core, price, storage, ui  # noqa: E402

fails = []


def main(lbl):
    """두 줄 결과 칸의 첫 줄(금액)만."""
    return lbl.text().split("<br>")[0]


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
w = ui.MainWindow(gold_auto_fetch=False)
w.resize(1180, 900)
w.show()
pump(1500)
check("실행 시 자동조회", w.has_price and w.price == 731000 and w.source == "api", w.o_status.text())
check("상태줄 문구", w.o_status.text().startswith("API 조회 완료") and "제공일 2026-10-31 08:45:57" in w.o_status.text(), w.o_status.text())
check("10분 자동조회 타이머", w.auto_timer.isActive() and w.auto_timer.interval() == 600000)

# 검색·코드·상품명·상호·품목·저장·삭제가 없어야 함
pg = w.price_scroll.widget()  # 상품가격 탭만 (고금 매입 탭에는 원래 '저장' 이 있음)
texts = [x.text() for x in pg.findChildren(QLabel)] + [x.text() for x in pg.findChildren(QPushButton)] + [x.text() for x in w.findChildren(QPushButton) if x is w.b_check]
holders = [x.placeholderText() for x in pg.findChildren(QLineEdit)]
for word in ("검색", "코드", "상품명", "상호", "품목"):
    check(f"'{word}' 칸 없음", not any(t.strip() == word or t.startswith(word + " ") for t in texts) and not any(word in h for h in holders))
check("'공임' 이름 (공통 공임 아님)", "공임 (부가세 별도)" in texts and "공통 공임 (부가세 별도)" not in texts)
check("색상 고르기 없음, 화이트 체크만", not any(t in texts for t in ("색상", "핑크", "옐로우", "무도금")) and w.k_white.text() == "화이트 도금")
for word in ("저장", "삭제"):
    check(f"'{word}' 버튼 없음", word not in [b.text() for b in pg.findChildren(QPushButton)])

exp = {k: core.karat(731000, 10, 3.75, 50000, 0, 0, p, 30, 100) for k, p in (("10", 41.7), ("14", 58.5), ("18", 75))}
for k, p in (("10", 41.7), ("14", 58.5), ("18", 75)):
    check(f"{k}K 기본값 판매가 · 포함", main(w.krows[k][5]) == core.won(exp[k]["final"]), (w.krows[k][5].text(), exp[k]["final"]))
    x = core.karat_excl(731000, 10, 3.75, 50000, 0, 0, p, 30, 100)
    check(f"{k}K 기본값 판매가 · 별도", main(w.krows[k][4]) == core.won(x), (w.krows[k][4].text(), x))
    raw_x = (731000 / 1.1 * (3.75 / 3.75) * (p / 100) + 50000) / 0.7
    check(f"{k}K 별도 = 올림((금+공임) ÷ (1−마진))", x == -(-round(raw_x * 1e6) / 1e6 // 100) * 100, (x, raw_x))
    check(f"{k}K 별도 × 1.1 ≈ 포함", abs(x * 1.1 - exp[k]["final"]) <= 110, (x, exp[k]["final"]))
# 금값 · 공임(공임+알값+셋팅비) · 매입원가(부가세 별도)
r14 = exp["14"]
check("금값 칸", w.krows["14"][1].text() == core.won(r14["gold"]), w.krows["14"][1].text())
check("공임 칸 (알값·셋팅비 없음)", w.krows["14"][2].text() == core.won(50000), w.krows["14"][2].text())
check("매입원가 = 금값 + 공임 (부가세 별도)", w.krows["14"][3].text() == core.won(r14["gold"] + 50000), w.krows["14"][3].text())
# 10K·14K·18K 1돈 (순금 1돈 × 함량)
check("1돈 금액: 10K 는 없음 (14K·18K 만)", sorted(w.dons) == ["14", "18"])
check("1돈 금액 제목", "1돈 금액" in texts and not any("기준값 함량 비율" in t for t in texts))
for k, p in (("14", 58.5), ("18", 75)):
    cap, v, sub = w.dons[k]
    check(f"{k}K 1돈: 부가세 별도가 크게, 포함은 작게", v.text() == core.won(731000 / 1.1 * p / 100) and sub.text() == "부가세 포함 " + core.won(731000 * p / 100)
          and f"({p:g}%)" in cap.text() and "부가세 별도" in cap.text(), (cap.text(), v.text(), sub.text()))
# 조회 정보가 제목 줄 오른쪽 끝에
check("조회 정보는 맨 위 오른쪽", w.o_status.mapTo(w, w.o_status.rect().topRight()).y() < w.o_incl.mapTo(w, w.o_incl.rect().topLeft()).y()
      and w.o_status.mapTo(w, w.o_status.rect().topRight()).x() > w.width() - 80, w.o_status.geometry())
pp = core.pure(731000, 10, 3.75, 0, 50000, 100)
check("순금: 매입원가·판매가 별도·포함 세 칸만", sorted(w.pcells) == ["cost", "fin", "finx"])
check("순금 매입원가 = 금값 + 고리 + 공임", w.pcells["cost"].text() == core.won(731000 / 1.1 * 3.75 / 3.75 + 0 + 50000), w.pcells["cost"].text())
check("순금 최종 판매가 = 공임 2배 (별도·포함)", w.pcells["finx"].text() == core.won(pp["x2"]) and w.pcells["fin"].text() == core.won(pp["i2"]), (w.pcells["finx"].text(), w.pcells["fin"].text()))
check("공임 1배 칸 없음", not any("공임 1배" in t for t in texts))
check("맨 위: 부가세 별도가 먼저", w.o_base.mapTo(w, w.o_base.rect().topLeft()).x() < w.o_incl.mapTo(w, w.o_incl.rect().topLeft()).x())
check("부가세 별도", w.o_base.text() == core.won(731000 / 1.1))

w.i_price.setText("598,000")
w.apply_manual()
check("수동 시세", w.price == 598000 and w.source == "manual" and w.o_status.text().startswith("수동 입력 시세 적용"))

# 돈 입력 → g (계산은 원래 값), 화이트 추가금, 알값·셋팅비, 1,000원 올림
w.f["ad"].setText("1.333")
w.k_white.setChecked(True)
w.f["dia"].setText("30,000")
w.f["set"].setText("15000")
w.f_unit.setCurrentIndex(1)
pump(50)
check("돈 → g 표시", w.f["ag"].text() == "5.00" and abs(w.ag_exact - 1.333 * 3.75) < 1e-12, (w.f["ag"].text(), w.ag_exact))
e = core.karat(598000, 10, 1.333 * 3.75, 50000, 30000, 15000, 58.5, 30, 1000)
check("14K 화이트 판매가 · 포함 (+20,000)", w.krows["14"][5].text().startswith(core.won(e["final"] + 20000)), w.krows["14"][5].text())
ex = core.karat_excl(598000, 10, 1.333 * 3.75, 50000, 30000, 15000, 58.5, 30, 1000, 20000)
ex0 = core.karat_excl(598000, 10, 1.333 * 3.75, 50000, 30000, 15000, 58.5, 30, 1000)
check("14K 화이트 판매가 · 별도 (+20,000 그대로)", ex == ex0 + 20000 and w.krows["14"][4].text().startswith(core.won(ex)) and "도금 +20,000 포함" in w.krows["14"][4].text(), w.krows["14"][4].text())
hs_on = [w.krows["14"][j].sizeHint().height() for j in range(6)] + [w.kgrid.cellRect(1, 0).height() if w.kgrid.cellRect(1, 0).isValid() else -1]
w.k_white.setChecked(False)
pump(50)
hs_off = [w.krows["14"][j].sizeHint().height() for j in range(6)] + [w.kgrid.cellRect(1, 0).height() if w.kgrid.cellRect(1, 0).isValid() else -1]
check("화이트 도금 체크해도 결과 칸 높이 고정", hs_on == hs_off, (hs_on, hs_off))
check("화이트 해제하면 추가금 빠짐", main(w.krows["14"][5]) == core.won(e["final"]) and main(w.krows["14"][4]) == core.won(ex0) and "+20,000" not in w.krows["14"][4].text(), (w.krows["14"][4].text(), w.krows["14"][5].text()))
w.k_white.setChecked(True)
check("공임 칸 = 공임 + 알값 + 셋팅비", w.krows["14"][2].text() == core.won(50000 + 30000 + 15000), w.krows["14"][2].text())
check("매입원가 = 금값 + 공임 합계", w.krows["14"][3].text() == core.won(e["gold"] + 95000), (w.krows["14"][3].text(), e["gold"]))
w.f["m14"].setText("100")
pump(50)
check("마진 100% → 빨간 칸", w.f["m14"].property("invalid") == "true" and main(w.krows["14"][5]) == "입력 확인" and main(w.krows["14"][4]) == "-" and w.krows["14"][3].text() == "-")
w.f["p14"].setText("0")
pump(50)
check("함량 잘못되면 1돈 칸 '-'", w.dons["14"][1].text() == "-" and w.dons["14"][2].text() == "함량 확인")
w.f["p14"].setText("58.5")
w.f["m14"].setText("30")
w.kchk["10"].setChecked(False)
pump(50)
check("10K 숨김", not w.krows["10"][5].isVisible() and w.krows["14"][5].isVisible())
w.f["pg"].setText("11.25")
pump(50)
w.f["ring"].setText("20000")
pump(50)
pp2 = core.pure(598000, 10, 11.25, 20000, 50000, 1000)
check("순금 고리 넣으면 매입원가·판매가에 반영", w.pcells["cost"].text() == core.won(598000 / 1.1 * 11.25 / 3.75 + 20000 + 50000) and w.pcells["fin"].text() == core.won(pp2["i2"]), (w.pcells["cost"].text(), w.pcells["fin"].text()))
check("순금 g → 돈", w.f["pd"].text() == "3.00")

check("초기화 버튼은 수동 시세 적용과 같은 색", w.k_clear.objectName() == w.b_manual.objectName() == w.p_clear.objectName()
      and w.k_clear.palette().button().color() == w.b_manual.palette().button().color())
w.clear_section("p")
check("순금 초기화", all(w.f[k].text() == "" for k in ("pg", "pd", "ring", "pl")) and w.pcells["finx"].text() == "-" and w.pcells["cost"].text() == "-")
# 업데이트 버튼
said = []
w.say = lambda t, m: said.append(m)
check("업데이트 버튼은 새 버전이 있을 때만", not w.b_update.isVisible() and w.b_check.text() == "업데이트 확인")
w._quiet = True
w.on_update_checked(None, None)
check("새 버전 없으면 조용히", not w.b_update.isVisible() and not said)
w._quiet = False
w.on_update_checked(None, None)
check("직접 확인했는데 최신이면 알림", said and "최신 버전" in said[-1], said)
w.on_update_checked(None, "주소를 찾지 못함 (인터넷 연결 확인)")
check("확인 실패 알림", "확인하지 못했습니다" in said[-1], said[-1:])
asked, started = [], []
w.ask_update = lambda info: (asked.append(info["version"]), False)[1]
w._quiet = True
w.on_update_checked({"version": "9.9.9", "url": "x", "size": 1, "digest": "", "name": "x"}, None)
check("새 버전 있으면 오른쪽 위에 버튼", w.b_update.isVisible() and w.b_update.text() == "새 버전 9.9.9 업데이트")
check("개발 실행(바꿀 수 없는 곳)에서는 실행 시 묻지 않음", not asked, asked)
# 실행할 때 새 버전 → 바로 묻기
_ct, _su = ui.update.current_target, w.start_update
ui.update.current_target = lambda: (Path("/Applications/x.app"), "")
w.start_update = lambda info, confirm=True: started.append((info["version"], confirm))
w.b_update.hide()
w.on_update_checked({"version": "9.9.9", "url": "x", "size": 1, "digest": "", "name": "x"}, None)
check("실행 시 새 버전 → 업데이트할지 물음, '나중에'면 넘어가고 버튼은 남김", asked == ["9.9.9"] and not started and w.b_update.isVisible(), (asked, started))
w.ask_update = lambda info: (asked.append(info["version"]), True)[1]
w.on_update_checked({"version": "9.9.9", "url": "x", "size": 1, "digest": "", "name": "x"}, None)
check("'지금 업데이트' → 다시 묻지 않고 바로 받기", started == [("9.9.9", False)], started)
w._quiet = False
started.clear()
w.on_update_checked({"version": "9.9.9", "url": "x", "size": 1, "digest": "", "name": "x"}, None)
check("직접 확인 버튼은 기존대로 (받을지 한 번 물음)", started == [("9.9.9", True)] and len(asked) == 2, (started, asked))
ui.update.current_target, w.start_update = _ct, _su
w._quiet = True
w.start_update(w.update_info)
check("개발 실행에서는 바꾸지 않고 안내", "만들어진 프로그램" in said[-1], said[-1:])

# 화면 촘촘하게: 설명 글은 ⓘ 에 마우스를 올리면 보임
from PySide6.QtWidgets import QLabel as _QL
tips = [x for x in w.price_scroll.widget().findChildren(_QL) if x.objectName() == "tip"]
check("설명 글은 ⓘ 로 (3곳)", len(tips) == 3 and any("매입원가 = 금값 + 고리 + 공임" in t.toolTip() for t in tips)
      and any("알값" in t.toolTip() for t in tips) and any("올림 단위" in t.toolTip() for t in tips), [t.toolTip()[:20] for t in tips])
check("화면에 늘 보이는 긴 설명 글 없음", not any(x.objectName() == "note" and x.isVisible() for x in w.price_scroll.widget().findChildren(_QL)))
h = w.price_scroll.widget().sizeHint().height()
check("화면 높이 줄어듦 (예전 약 1,100)", h <= 900, h)

# 화면 크기
from jinju_cal import app as appmod
check("화면 크기 기본 100%", w.f_scale.currentData() == 100 and [w.f_scale.itemData(i) for i in range(w.f_scale.count())] == [100, 90, 80, 70])
quits = []
_q = ui.QApplication.quit
ui.QApplication.quit = lambda: quits.append(1)
w.ask = lambda t, m: False
w.f_scale.setCurrentIndex(2)  # 80%
check("화면 크기 저장 (지금 다시 열기 '아니요')", storage.load().get("scale") == "80" and not quits and not w.restart_requested)
check("다음에 열 때 80% 적용", appmod.apply_scale() == 80 and os.environ.get("QT_SCALE_FACTOR") == "0.8")
w.ask = lambda t, m: True
w.f_scale.setCurrentIndex(3)  # 70%, '예' → 다시 열기
check("'예' 누르면 다시 열기 요청", storage.load().get("scale") == "70" and quits and w.restart_requested and "window" not in storage.load())
check("다시 열 명령 (개발 실행)", appmod.restart_command()[0] == sys.executable)
ui.QApplication.quit = _q
w.restart_requested = False
w.f_scale.setCurrentIndex(0)
check("100%로 되돌리면 배율 없음", storage.load().get("scale") == "100" and appmod.apply_scale() == 100 and "QT_SCALE_FACTOR" not in os.environ)

# 탭: [상품가격] [고금 매입], 고금 매입 안에 [금] [은]
check("위쪽 탭 두 개", [w.tabs.tabText(i) for i in range(w.tabs.count())] == ["상품가격", "고금 매입"])
g = w.gold
check("고금 매입 안 [금 12품목] [은 7품목]", g.table.gold.rowCount() == 12 and g.table.silver.rowCount() == 7
      and g.table.tabs.tabText(0).startswith("금 12품목") and g.table.tabs.tabText(1).startswith("은 7품목"))
g.prices.update(GOLD=626000, SILVER=7530, PLATINUM=217000)
g.weights[0][0].setText("3.75")
g.weights[13][0].setText("100")
pump(30)
from jinju_cal.goldmetal import core as gcore
e0 = gcore.calculate_row(gcore.calculate_unit_price(626000, "GOLD", gcore.RATE_ITEMS[0].multiplier), "3.75", "")[1]
e13 = gcore.calculate_row(gcore.calculate_unit_price(7530, "SILVER", gcore.RATE_ITEMS[13].multiplier), "100", "")[1]
check("고금 계산 (원본 계산식: 24k골드바 3.75g, 99은수저 100g)", (e0, e13) == (625999, 180300) and g.table.item(0, 6).text() == f"{e0:,}" and g.table.item(13, 6).text() == f"{e13:,}"
      and g.total_label.text() == f"{e0 + e13:,}", (g.table.item(0, 6).text(), g.table.item(13, 6).text(), g.total_label.text()))
check("[금] [은] 탭 제목에 합계", g.table.tabs.tabText(0).endswith(f"{e0:,}") and g.table.tabs.tabText(1).endswith(f"{e13:,}"), [g.table.tabs.tabText(i) for i in (0, 1)])
check("고금은 원래 색 (초록 저장 버튼)", "#167344" in g.styleSheet())
w.tabs.setCurrentIndex(1)
w.save_settings()
check("마지막 탭 기억", storage.load().get("tab") == "1")

w.close()
pump(50)
s = storage.load()
check("설정 저장", s.get("dia") == "30,000" and s.get("show10") == "0" and s.get("unit") == "1" and s.get("price") == "598000", s)

w2 = ui.MainWindow(gold_auto_fetch=False)
check("다시 열면 복원", w2.f["dia"].text() == "30,000" and not w2.kchk["10"].isChecked() and w2.f_unit.currentIndex() == 1 and w2.i_price.text() == "598,000")
check("최소 너비 안에서 가로로 안 잘림", w2.minimumWidth() <= 1100, w2.minimumWidth())
w2.k_white.setChecked(True)
w2.clear_section("k")
check("초기화하면 화이트 체크 해제", not w2.k_white.isChecked() and w2.f["al"].text() == "")
check("다시 열면 고금 매입 탭으로", w2.tabs.currentIndex() == 1)
gs = gcore.load_state()
check("닫을 때 고금 입력값도 저장", gs.get("weights", {}).get(g.keys[0], {}).get("input_weight") == "3.75", gs.get("weights", {}).get(g.keys[0]))
check("다시 열면 고금 중량 그대로", w2.gold.weights[0][0].text() == "3.75" and w2.gold.prices["GOLD"] == 626000)
check("버전 표시", w2.ver.text() == "v" + __import__("jinju_cal").__version__)
w2.close()

print("실패 %d건" % len(fails) if fails else "모두 통과")
srv.shutdown()
sys.exit(1 if fails else 0)
