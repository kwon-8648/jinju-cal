"""계산기 화면 — 매장관리 웹의 계산기 탭에서 상품 검색·코드·저장 부분을 뺀 것."""
from __future__ import annotations

import sys
from datetime import datetime

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QApplication, QLineEdit, QMainWindow, QMessageBox, QProgressDialog, QPushButton, QScrollArea, QTabWidget, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__, storage, update
from .core import GPD, UNITS, base, commas, fixed2, js_round, karat, karat_excl, karat_x, parse_num, pure, won
from .price import PriceFetcher
from .goldmetal.panel import GoldPanel

KARAT_KEYS = ["10", "14", "18"]
AUTO_MS = 10 * 60 * 1000

# 매장관리 웹과 같은 색
C = {
    "bg": "#f6f2e9", "panel": "#fffdf8", "soft": "#efe6d2", "line": "#e3d9c4",
    "ink": "#2d2314", "muted": "#69645c", "gold": "#884b04", "gold_ink": "#fffdf8",
    "input": "#fff6c9", "input_line": "#e6cf6b", "bad": "#a1361f", "bad_in": "#fbe1da",
}


def body_font_family():
    if sys.platform == "darwin":
        return "Apple SD Gothic Neo"
    if sys.platform == "win32":
        return "Malgun Gothic"
    return "Noto Sans CJK KR"


def display_font_family():
    if sys.platform == "darwin":
        return "AppleMyungjo"
    if sys.platform == "win32":
        return "Batang"
    return "Noto Serif CJK KR"


def stylesheet():
    return f"""
    QWidget {{ color:{C['ink']}; }}
    QTabWidget#main_tabs::pane {{ border:none; border-top:1px solid {C['line']}; }}
    QTabWidget#main_tabs > QTabBar::tab {{ background:{C['soft']}; color:{C['muted']}; padding:4px 24px; margin:4px 2px 0 0;
        border:1px solid {C['line']}; border-bottom:none; border-top-left-radius:6px; border-top-right-radius:6px; font-size:14px; font-weight:600; }}
    QTabWidget#main_tabs > QTabBar::tab:selected {{ background:{C['gold']}; color:{C['gold_ink']}; border-color:{C['gold']}; }}
    QTabWidget#main_tabs > QTabBar::tab:!selected:hover {{ background:{C['panel']}; color:{C['ink']}; }}
    QMainWindow, QScrollArea, #page {{ background:{C['bg']}; }}
    QFrame#card {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:6px; }}
    QLabel#h2 {{ font-size:16px; font-weight:700; }}
    QLabel#h3 {{ font-size:13px; font-weight:700; }}
    QLabel#lab {{ color:{C['muted']}; font-size:12px; }}
    QLabel#note {{ color:{C['muted']}; font-size:12px; }}
    QLabel#big {{ font-size:24px; font-weight:700; }}
    QLabel#bigbase {{ font-size:24px; font-weight:700; color:{C['gold']}; }}
    QLabel#status {{ color:{C['muted']}; font-size:13px; }}
    QLabel#status[bad="true"] {{ color:{C['bad']}; }}
    QLabel#tip {{ color:{C['gold']}; font-size:12px; font-weight:600; }}
    QLabel#ver {{ color:{C['muted']}; font-size:11px; }}
    QLabel#title {{ color:{C['gold']}; font-size:24px; font-weight:800; }}
    QLineEdit {{ background:{C['input']}; border:1px solid {C['input_line']}; border-radius:4px;
                 padding:3px 8px; min-height:20px; selection-background-color:{C['gold']}; }}
    QLineEdit:focus {{ border:2px solid {C['gold']}; padding:2px 7px; }}
    QLineEdit[invalid="true"] {{ border:1px solid {C['bad']}; background:{C['bad_in']}; }}
    QLineEdit[invalid="true"]:focus {{ border:2px solid {C['bad']}; }}
    QComboBox {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:4px; padding:3px 8px; min-height:20px; }}
    QComboBox QAbstractItemView {{ background:{C['panel']}; selection-background-color:{C['soft']}; selection-color:{C['ink']}; }}
    QPushButton {{ background:{C['gold']}; color:{C['gold_ink']}; border:1px solid {C['gold']}; border-radius:4px;
                   padding:4px 14px; font-weight:600; min-height:20px; }}
    QPushButton:hover {{ background:#9a5606; }}
    QPushButton:disabled {{ background:{C['soft']}; color:{C['muted']}; border-color:{C['line']}; }}
    QPushButton#ghost {{ background:transparent; color:{C['gold']}; }}
    QPushButton#ghost:hover {{ background:{C['soft']}; }}
    QPushButton#plain {{ background:transparent; color:{C['muted']}; border:1px solid {C['line']}; font-weight:500; }}
    QPushButton#small {{ background:transparent; color:{C['muted']}; border:none; font-weight:500; font-size:11px; padding:0 4px; min-height:0; text-decoration:underline; }}
    QPushButton#small:hover {{ color:{C['gold']}; }}
    QPushButton#plain:hover {{ background:{C['soft']}; color:{C['ink']}; }}
    QCheckBox {{ font-weight:600; spacing:6px; }}
    QFrame#ktable {{ border:1px solid {C['line']}; border-radius:4px; background:{C['panel']}; }}
    QLabel#th {{ color:{C['muted']}; font-size:12px; }}
    QLabel#kk {{ color:{C['gold']}; font-weight:700; font-size:15px; }}
    QLabel#kv {{ font-size:15px; }}
    QLabel#kfinx {{ font-size:17px; font-weight:700; border:1px solid {C['line']}; border-radius:4px; padding:2px 8px; }}
    QFrame#vline {{ background:{C['line']}; border:none; }}
    QLabel#kfin {{ font-size:17px; font-weight:700; background:{C['soft']}; border-radius:4px; padding:2px 8px; }}
    QFrame#cell {{ border:1px solid {C['line']}; border-radius:4px; background:{C['panel']}; }}
    QFrame#cellx {{ border:1px solid {C['line']}; border-radius:4px; background:{C['panel']}; }}
    QFrame#cellincl {{ border:1px solid {C['line']}; border-radius:4px; background:{C['soft']}; }}
    QLabel#donv {{ font-size:17px; font-weight:700; }}
    QLabel#cellv {{ font-size:18px; font-weight:700; }}
    QFrame#hline {{ background:{C['line']}; max-height:1px; min-height:1px; border:none; }}
    """


def now_sec():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


SCALES = [100, 90, 80, 70]  # 화면 크기 (%)


def info_tip(text):
    """마우스를 올리면 설명이 보이는 작은 ⓘ (화면 높이를 줄이려고 설명 글을 여기에 넣음)."""
    lb = QLabel("ⓘ 설명")
    lb.setObjectName("tip")
    lb.setToolTip(text)
    lb.setCursor(Qt.WhatsThisCursor)
    return lb


def card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(14, 10, 14, 12)
    lay.setSpacing(8)
    return f, lay


def label(text, name=None, wrap=False):
    lb = QLabel(text)
    if name:
        lb.setObjectName(name)
    if wrap:
        lb.setWordWrap(True)
    return lb


def button(text, kind=None):
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    b.setAutoDefault(False)
    return b


class Field(QWidget):
    """라벨 + 노란 입력칸."""

    def __init__(self, text, placeholder="", align=Qt.AlignRight):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        self.lab = label(text, "lab")
        self.edit = QLineEdit()
        self.edit.setAlignment(align | Qt.AlignVCenter)
        if placeholder:
            self.edit.setPlaceholderText(placeholder)
        self.lab.setBuddy(self.edit)
        lay.addWidget(self.lab)
        lay.addWidget(self.edit)


class ComboField(QWidget):
    def __init__(self, text, items):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(3)
        lay.addWidget(label(text, "lab"))
        self.combo = QComboBox()
        for t, v in items:
            self.combo.addItem(t, v)
        lay.addWidget(self.combo)


def set_bad(edit: QLineEdit, bad: bool):
    v = "true" if bad else "false"
    if edit.property("invalid") != v:
        edit.setProperty("invalid", v)
        edit.style().unpolish(edit)
        edit.style().polish(edit)


class UpdateChecker(QObject):
    """새 버전 확인 (백그라운드)."""
    done = Signal(object, object)  # (새 버전 정보 | None, 오류 문구 | None)

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        try:
            self.done.emit(update.check(), None)
        except update.UpdateError as e:
            self.done.emit(None, str(e))
        except Exception as e:
            self.done.emit(None, str(e) or "확인 실패")


class UpdateWorker(QObject):
    """받기·준비·설치 스크립트 실행 (백그라운드)."""
    progress = Signal(int, int)
    stage = Signal(str)
    done = Signal(object)  # 오류 문구 | None(성공)

    def __init__(self, info):
        super().__init__()
        self.info = info
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        def prog(got, total):
            self.progress.emit(got, total)
            if total and got >= total:
                self.stage.emit("새 버전을 준비하는 중…")
        try:
            update.install(self.info, prog, lambda: self._cancel)
            self.done.emit(None)
        except update.UpdateError as e:
            self.done.emit(str(e))
        except Exception as e:
            self.done.emit(str(e) or "업데이트 실패")


def two_line(main, sub=""):
    """잡금 결과 칸은 항상 두 줄로 그려 화이트 도금 체크 여부와 관계없이 높이를 고정한다."""
    color = C["muted"] if sub else "transparent"
    return (f'{main}<br><span style="font-size:11px;color:{color};font-weight:500">'
            f'{sub or "도금"}</span>')


class MainWindow(QMainWindow):
    def __init__(self, gold_auto_fetch=True):
        super().__init__()
        self.gold_auto_fetch = gold_auto_fetch
        self.setWindowTitle(APP_NAME)
        self.price = 0.0
        self.has_price = False
        self.price_time = ""
        self.source = ""
        self.ag_exact = None  # 돈으로 입력했을 때의 정확한 g
        self.pg_exact = None
        self.loading = False
        self.fetching = False
        self.f = {}  # 기준값·입력 칸: key → QLineEdit

        self.fetcher = PriceFetcher()
        self.fetcher.done.connect(self.on_fetched)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self.start_fetch)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.timeout.connect(self.save_settings)

        self.restart_requested = False
        self.update_info = None
        self.update_busy = False
        self.checker = UpdateChecker()
        self.checker.done.connect(self.on_update_checked)

        self.build()
        self.load_settings()
        self.wire()
        self.recompute()
        self.set_auto_timer()
        if self.c_auto.isChecked():
            QTimer.singleShot(200, self.start_fetch)
        if getattr(sys, "frozen", False) and "--smoke" not in sys.argv:  # 만든 프로그램일 때만 실행 3초 뒤 조용히 새 버전 확인
            QTimer.singleShot(3000, lambda: self.check_update(quiet=True))

    # ------------------------------------------------------------------ 화면
    def build(self):
        page = QWidget()
        page.setObjectName("page")
        root = QVBoxLayout(page)
        root.setContentsMargins(14, 10, 14, 8)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = label(APP_NAME, "title")
        tf = QFont(display_font_family())
        tf.setPixelSize(24)
        tf.setBold(True)
        title.setFont(tf)
        top.addWidget(title, 0, Qt.AlignTop)
        top.addStretch(1)
        corner = QVBoxLayout()
        corner.setSpacing(2)
        self.o_status = label("조회 전입니다. 시세를 조회하거나 수동 입력하세요.", "status", wrap=True)
        self.o_status.setAlignment(Qt.AlignRight | Qt.AlignTop)
        self.o_status.setMaximumWidth(760)
        corner.addWidget(self.o_status, 0, Qt.AlignRight)
        link = QLabel(f'<a href="https://www.koreagoldx.co.kr/" style="color:{C["gold"]}">한국금거래소 시세 보기 ↗</a>')
        link.setObjectName("lab")
        link.setOpenExternalLinks(True)
        corner.addWidget(link, 0, Qt.AlignRight)
        self.b_update = button("새 버전 업데이트")
        self.b_update.setToolTip("눌러서 새 버전을 받아 바꿉니다. 끝나면 프로그램이 다시 열립니다.")
        self.b_update.hide()
        corner.addWidget(self.b_update, 0, Qt.AlignRight)
        top.addLayout(corner)
        root.addLayout(top)

        # --- 시세
        pc, pl = card()
        head = QHBoxLayout()
        head.addWidget(label("순금 1돈(3.75g) · 내가 살 때", "h2"))
        head.addStretch(1)
        self.c_auto = QCheckBox("자동조회 (실행 시 / 10분 간격)")
        head.addWidget(self.c_auto)
        pl.addLayout(head)

        prow = QHBoxLayout()
        prow.setSpacing(24)
        for attr, cap, name in [("o_base", "부가세 별도 가격 · 계산 기준", "bigbase"), ("o_incl", "부가세 포함 가격", "big")]:
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(label(cap, "lab"))
            v = label("-", name)
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            setattr(self, attr, v)
            box.addWidget(v)
            prow.addLayout(box, 1)
        manual = QHBoxLayout()
        manual.setSpacing(8)
        self.fp = Field("시세 입력 · 부가세 포함 (원/돈)", "예: 612,000")
        self.i_price = self.fp.edit
        self.i_price.setMinimumWidth(170)
        manual.addWidget(self.fp, 1)
        self.b_manual = button("수동 시세 적용")
        self.b_refresh = button("시세 새로고침", "ghost")
        manual.addWidget(self.b_manual, 0, Qt.AlignBottom)
        manual.addWidget(self.b_refresh, 0, Qt.AlignBottom)
        prow.addLayout(manual, 2)
        pl.addLayout(prow)

        line = QFrame()
        line.setObjectName("hline")
        pl.addWidget(line)
        drow = QHBoxLayout()
        drow.setSpacing(10)
        dcap = label("1돈 금액", "lab")
        drow.addWidget(dcap, 0, Qt.AlignVCenter)
        self.dons = {}
        for k in ("14", "18"):  # 10K 는 표시하지 않음
            fr = QFrame()
            fr.setObjectName("cell")
            vl = QVBoxLayout(fr)
            vl.setContentsMargins(12, 4, 12, 5)
            vl.setSpacing(0)
            cap = label(f"{k}K 1돈 · 부가세 별도", "lab")
            v = label("-", "donv")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            sub = label("", "lab")
            vl.addWidget(cap)
            vl.addWidget(v)
            vl.addWidget(sub)
            self.dons[k] = (cap, v, sub)
            drow.addWidget(fr, 1)
        pl.addLayout(drow)
        root.addWidget(pc)

        # --- 아래: 기준값 | 상품 계산
        grid = QHBoxLayout()
        grid.setSpacing(10)

        sc, sl = card()
        sc.setFixedWidth(270)
        sh_ = QHBoxLayout()
        sh_.addWidget(label("기준값", "h2"))
        sh_.addStretch(1)
        sh_.addWidget(info_tip("노란 칸을 수정하면 자동 계산합니다. 최종 판매가는 선택한 올림 단위로 올립니다.\n"
                               "g 또는 돈을 넣으면 자동으로 바꿔 보여줍니다 (중량 2자리 / 금액 정수 표시, 계산은 넣은 값 그대로).\n"
                               "마진율은 올림 전 판매가 기준입니다. 조회·입력 시세는 부가세 포함으로 봅니다."))
        sl.addLayout(sh_)
        for key, cap, ph in [("vat", "부가세율 %", ""), ("p10", "10K 함량 %", ""), ("p14", "14K 함량 %", ""),
                             ("p18", "18K 함량 %", ""), ("white", "화이트골드 추가금 (원)", "")]:
            fd = Field(cap, ph)
            self.f[key] = fd.edit
            sl.addWidget(fd)
        uf = ComboField("판매가 올림 단위", [("100원 단위", 0), ("1,000원 단위", 1), ("10,000원 단위", 2)])
        self.f_unit = uf.combo
        sl.addWidget(uf)
        self.b_reset = button("기본값으로 되돌리기", "ghost")
        sl.addWidget(self.b_reset)
        sl.addStretch(1)
        grid.addWidget(sc, 0, Qt.AlignTop)

        stack = QVBoxLayout()
        stack.setSpacing(10)

        # 10K·14K·18K
        kc, kl = card()
        kh = QHBoxLayout()
        kh.setSpacing(12)
        kh.addWidget(label("10K · 14K · 18K 상품", "h2"))
        kh.addWidget(info_tip("표의 공임 = 공임 + 랩다이아 알값 + 다이아 셋팅비\n매입원가 = 금값 + 공임 (모두 부가세 별도, 공란은 0원)\n"
                              "중량·공임은 캐럿 공통, 마진율은 판매가 기준입니다."))
        kh.addStretch(1)
        self.k_xmode = QCheckBox("배율·할인가")
        self.k_xmode.setToolTip("체크하면 아래에 '원가 × 배율 → 카드·현금 할인가' 표를 함께 보여 줍니다")
        kh.addWidget(self.k_xmode)
        self.k_white = QCheckBox("화이트 도금")
        self.k_white.setToolTip("체크하면 최종 판매가(별도·포함)에 화이트골드 추가금을 더합니다")
        kh.addWidget(self.k_white)
        sep = QFrame()
        sep.setObjectName("vline")
        sep.setFixedSize(1, 18)
        kh.addWidget(sep)
        self.kchk = {}
        for k in KARAT_KEYS:
            cb = QCheckBox(k + "K")
            self.kchk[k] = cb
            kh.addWidget(cb)
        self.k_clear = button("초기화")  # 수동 시세 적용과 같은 색
        kh.addWidget(self.k_clear)
        kl.addLayout(kh)

        r5 = QGridLayout()
        r5.setHorizontalSpacing(10)
        for i, (key, cap, ph) in enumerate([("ag", "공통 중량 (g)", ""), ("ad", "환산 중량 (돈)", ""), ("al", "공임 (부가세 별도)", ""),
                                            ("dia", "랩다이아 알값 (부가세 별도)", "0"), ("set", "다이아 셋팅비 (부가세 별도)", "0")]):
            fd = Field(cap, ph)
            self.f[key] = fd.edit
            r5.addWidget(fd, 0, i)
            r5.setColumnStretch(i, 1)
        kl.addLayout(r5)
        r3 = QGridLayout()
        r3.setHorizontalSpacing(10)
        for i, k in enumerate(KARAT_KEYS):
            fd = Field(f"{k}K 마진 %")
            self.f["m" + k] = fd.edit
            r3.addWidget(fd, 0, i)
            r3.setColumnStretch(i, 1)
        kl.addLayout(r3)
        self.ktable = QFrame()
        self.ktable.setObjectName("ktable")
        self.kgrid = QGridLayout(self.ktable)
        self.kgrid.setContentsMargins(10, 6, 10, 6)
        self.kgrid.setHorizontalSpacing(14)
        self.kgrid.setVerticalSpacing(4)
        heads = ["금종류", "금값\n부가세 별도", "공임\n알값·셋팅비 포함", "매입원가\n부가세 별도", "최종 판매가\n부가세 별도", "최종 판매가\n부가세 포함"]
        for i, h in enumerate(heads):
            lb = label(h, "th")
            lb.setAlignment((Qt.AlignLeft if i == 0 else Qt.AlignRight) | Qt.AlignVCenter)
            self.kgrid.addWidget(lb, 0, i)
        self.kgrid.setColumnStretch(0, 2)
        for i in (1, 2, 3, 4, 5):
            self.kgrid.setColumnStretch(i, 3)
        self.krows = {}
        for r, k in enumerate(KARAT_KEYS, start=1):
            kk = label(two_line(k + "K"), "kk")
            kk.setTextFormat(Qt.RichText)
            g = label("-", "kv")
            lab_ = label("-", "kv")
            c = label("-", "kv")
            finx = label(two_line("-"), "kfinx")
            finx.setTextFormat(Qt.RichText)
            fin = label(two_line("-"), "kfin")
            fin.setTextFormat(Qt.RichText)
            for w in (g, lab_, c, finx, fin):
                w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                w.setTextInteractionFlags(Qt.TextSelectableByMouse)
            for i, w in enumerate((kk, g, lab_, c, finx, fin)):
                self.kgrid.addWidget(w, r, i)
            # (금종류, 금값, 공임, 매입원가, 판매가 별도, 판매가 포함)
            self.krows[k] = (kk, g, lab_, c, finx, fin)
        self.kempty = label("위 체크박스에서 표시할 캐럿을 선택하세요.", "note")
        self.kempty.setAlignment(Qt.AlignCenter)
        self.kgrid.addWidget(self.kempty, 4, 0, 1, 6)
        kl.addWidget(self.ktable)

        # 배율·할인 방식 (다른 금은방): 정가 = 원가 × 배율 → 카드가·현금가 = 정가에서 할인
        self.xbox = QWidget()
        xl = QVBoxLayout(self.xbox)
        xl.setContentsMargins(0, 2, 0, 0)
        xl.setSpacing(6)
        xh = QHBoxLayout()
        xh.setSpacing(10)
        xh.addWidget(label("배율·할인 판매가", "h3"))
        xh.addWidget(info_tip("원가 = 위 표의 매입원가 (금값 + 공임, 부가세 별도)\n정가 = 원가 × 판매 배율\n"
                              "카드가 = 정가 − 카드 할인 % · 현금가 = 정가 − 현금 할인 %\n"
                              "판매가 올림 단위로 올리고, 화이트 도금 체크 시 추가금을 더합니다. 마진 %는 쓰지 않습니다."))
        xh.addStretch(1)
        xl.addLayout(xh)
        r6 = QGridLayout()
        r6.setHorizontalSpacing(10)
        for i, (key, cap) in enumerate([("xm", "판매 배율 (배)"), ("dcard", "카드 할인 %"), ("dcash", "현금 할인 %")]):
            fd = Field(cap)
            self.f[key] = fd.edit
            r6.addWidget(fd, 0, i)
            r6.setColumnStretch(i, 1)
        xl.addLayout(r6)
        self.xtable = QFrame()
        self.xtable.setObjectName("ktable")
        self.xgrid = QGridLayout(self.xtable)
        self.xgrid.setContentsMargins(10, 6, 10, 6)
        self.xgrid.setHorizontalSpacing(14)
        self.xgrid.setVerticalSpacing(4)
        self.xheads = []
        for i, h in enumerate(["금종류", "원가\n매입원가 · 부가세 별도", "정가\n원가 × 배율", "카드가\n할인", "현금가\n할인"]):
            lb = label(h, "th")
            lb.setAlignment((Qt.AlignLeft if i == 0 else Qt.AlignRight) | Qt.AlignVCenter)
            self.xgrid.addWidget(lb, 0, i)
            self.xheads.append(lb)
        self.xgrid.setColumnStretch(0, 2)
        for i in (1, 2, 3, 4):
            self.xgrid.setColumnStretch(i, 3)
        self.xrows = {}
        for r, k in enumerate(KARAT_KEYS, start=1):
            cells = [label(k + "K", "kk")] + [label("-", "kv"), label("-", "kv"), label("-", "kfinx"), label("-", "kfin")]
            for i, w in enumerate(cells):
                if i:
                    w.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                    w.setTextInteractionFlags(Qt.TextSelectableByMouse)
                self.xgrid.addWidget(w, r, i)
            # (금종류, 원가, 정가, 카드가, 현금가)
            self.xrows[k] = tuple(cells)
        xl.addWidget(self.xtable)
        kl.addWidget(self.xbox)
        stack.addWidget(kc)

        # 순금
        pcard, pcl = card()
        ph = QHBoxLayout()
        ph.addWidget(label("순금 상품", "h2"))
        ph.addWidget(info_tip("금액은 모두 부가세 별도, 고리 금액 공란은 0원\n매입원가 = 금값 + 고리 + 공임\n"
                              "최종 판매가 = 매입원가 + 공임 × 공임 배율 (기본 2배 = 금값 + 고리 + 공임×3, 고리에는 배수 미적용)"))
        ph.addStretch(1)
        self.p_clear = button("초기화")  # 수동 시세 적용과 같은 색
        ph.addWidget(self.p_clear)
        pcl.addLayout(ph)
        pr = QHBoxLayout()
        pr.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(10)
        r4 = QGridLayout()
        r4.setHorizontalSpacing(10)
        for i, (key, cap, phd) in enumerate([("pg", "중량 (g)", ""), ("pd", "환산 중량 (돈)", ""),
                                             ("ring", "고리 금액 (별도)", "0"), ("pl", "개별공임 (별도)", ""),
                                             ("pm", "공임 배율 (배)", "2")]):
            fd = Field(cap, phd)
            self.f[key] = fd.edit
            r4.addWidget(fd, 0, i)
            r4.setColumnStretch(i, 1)
        left.addLayout(r4)

        pr.addLayout(left, 1)
        pcl.addLayout(pr)
        cells = QGridLayout()
        cells.setSpacing(8)
        self.pcells = {}
        self.pcaps = {}
        # (매입원가, 최종 판매가 별도, 최종 판매가 포함) — 잡금 결과표와 같은 이름
        for i, (key, cap, kind) in enumerate([("cost", "매입원가 · 부가세 별도", "cell"), ("finx", "최종 판매가 · 부가세 별도", "cellx"),
                                              ("fin", "최종 판매가 · 부가세 포함", "cellincl")]):
            fr = QFrame()
            fr.setObjectName(kind)
            vl = QVBoxLayout(fr)
            vl.setContentsMargins(12, 5, 12, 6)
            vl.setSpacing(0)
            capl = label(cap, "lab")
            self.pcaps[key] = capl
            vl.addWidget(capl)
            v = label("-", "cellv")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vl.addWidget(v)
            self.pcells[key] = v
            cells.addWidget(fr, 0, i)
            cells.setColumnStretch(i, 1)
        pcl.addLayout(cells)
        stack.addWidget(pcard)
        stack.addStretch(1)

        grid.addLayout(stack, 1)
        root.addLayout(grid, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(label("화면 크기", "ver"))
        self.f_scale = QComboBox()
        for v in SCALES:
            self.f_scale.addItem(f"{v}%", v)
        self.f_scale.setToolTip("글자와 칸을 함께 줄이거나 늘립니다. 이 컴퓨터에만 저장되고, 프로그램을 다시 열면 적용됩니다.")
        foot.addWidget(self.f_scale)
        foot.addSpacing(10)
        self.b_check = button("업데이트 확인", "small")
        foot.addWidget(self.b_check)
        self.ver = label(f"v{__version__}", "ver")
        foot.addWidget(self.ver)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.price_scroll = scroll

        # 위쪽 탭: [상품가격] [고금 매입]  (고금 매입은 고금시세계산 v1.16 그대로, 안에서 [금] [은] 탭)
        self.tabs = QTabWidget()
        self.tabs.setObjectName("main_tabs")
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(scroll, "상품가격")
        self.gold = GoldPanel(auto_fetch=self.gold_auto_fetch)
        self.tabs.addTab(self.gold, "고금 매입")

        # 맨 아래 (두 탭 공통): 화면 크기 · 업데이트 확인 · 버전
        outer = QWidget()
        outer.setObjectName("page")
        ol = QVBoxLayout(outer)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.setSpacing(0)
        ol.addWidget(self.tabs, 1)
        fw = QWidget()
        fw.setLayout(foot)
        foot.setContentsMargins(14, 1, 14, 2)
        ol.addWidget(fw)
        self.setCentralWidget(outer)
        # 가로로 잘리지 않는 최소 너비 (상품가격은 세로 스크롤, 고금 매입은 표가 창에 맞춰짐)
        width = max(page.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 4,
                    self.gold.minimumSizeHint().width() + 4)
        self.setMinimumSize(width, 560)

    # ------------------------------------------------------------------ 연결
    def wire(self):
        for key, ed in self.f.items():
            ed.textChanged.connect(lambda _t, k=key: self.on_field(k))
        for cb in self.kchk.values():
            cb.toggled.connect(self.on_change)
        self.f_unit.currentIndexChanged.connect(self.on_change)
        self.k_white.toggled.connect(self.recompute)
        self.k_xmode.toggled.connect(self.on_change)
        self.b_manual.clicked.connect(self.apply_manual)
        self.i_price.returnPressed.connect(self.apply_manual)
        self.b_refresh.clicked.connect(self.start_fetch)
        self.c_auto.toggled.connect(self.on_auto)
        self.b_reset.clicked.connect(self.reset_defaults)
        self.k_clear.clicked.connect(lambda: self.clear_section("k"))
        self.b_check.clicked.connect(lambda: self.check_update(quiet=False))
        self.f_scale.currentIndexChanged.connect(self.on_scale)
        self.b_update.clicked.connect(lambda: self.start_update(self.update_info))
        self.p_clear.clicked.connect(lambda: self.clear_section("p"))

    def on_field(self, key):
        if self.loading:
            return
        if key in ("ag", "pg", "ad", "pd"):
            self.sync_weight(key)
        self.recompute()
        self.schedule_save()

    def on_change(self, *_):
        if self.loading:
            return
        self.recompute()
        self.schedule_save()

    def on_auto(self, on):
        self.set_auto_timer()
        self.schedule_save()
        if on:
            self.start_fetch()

    # g ↔ 돈: 다른 칸에는 소수 2자리로 보여주고, 계산은 입력한 원래 값으로
    def sync_weight(self, which):
        self.loading = True
        try:
            if which == "ad":
                d, ok = parse_num(self.f["ad"].text())
                if ok and d > 0:
                    self.ag_exact = d * GPD
                    self.f["ag"].setText(fixed2(self.ag_exact))
                else:
                    self.ag_exact = None
            elif which == "ag":
                self.ag_exact = None
                g, ok = parse_num(self.f["ag"].text())
                self.f["ad"].setText(fixed2(g / GPD) if ok and g > 0 else "")
            elif which == "pd":
                d, ok = parse_num(self.f["pd"].text())
                if ok and d > 0:
                    self.pg_exact = d * GPD
                    self.f["pg"].setText(fixed2(self.pg_exact))
                else:
                    self.pg_exact = None
            elif which == "pg":
                self.pg_exact = None
                g, ok = parse_num(self.f["pg"].text())
                self.f["pd"].setText(fixed2(g / GPD) if ok and g > 0 else "")
        finally:
            self.loading = False

    # ------------------------------------------------------------------ 계산
    def num(self, key, allow_blank=False):
        return parse_num(self.f[key].text(), allow_blank)

    def recompute_x(self, vat, vok, g, gok, labor, lok, dia, setv, unit, kw, kx):
        """배율·할인 판매가 표 (정가 = 매입원가 × 배율, 카드가·현금가 = 정가에서 할인)."""
        on = self.k_xmode.isChecked()
        self.xbox.setVisible(on)
        if not on:
            return
        bad = lambda k, b: set_bad(self.f[k], b)
        xm, xok = self.num("xm")
        xok = xok and 0 < xm <= 100
        bad("xm", not xok)
        dc, dcok = self.num("dcard", True)
        dcok = dcok and 0 <= dc < 100
        bad("dcard", not dcok)
        dh, dhok = self.num("dcash", True)
        dhok = dhok and 0 <= dh < 100
        bad("dcash", not dhok)
        self.xheads[2].setText(f"정가\n원가 × {xm:g}배" if xok else "정가\n원가 × 배율")
        self.xheads[3].setText(f"카드가\n{dc:g}% 할인" if dcok else "카드가\n할인")
        self.xheads[4].setText(f"현금가\n{dh:g}% 할인" if dhok else "현금가\n할인")
        for k in KARAT_KEYS:
            cells = self.xrows[k]
            show = self.kchk[k].isChecked()
            for w in cells:
                w.setVisible(show)
            if not show:
                continue
            pct, pok = self.num("p" + k)
            pok = pok and 0 < pct <= 100
            kk, cl, ll, cd, ch = cells
            kk.setText(f"{k}K" + (" · 화이트" if kw else ""))
            ok = self.has_price and vok and gok and lok and pok
            cost = base(self.price, vat) * g / GPD * pct / 100 + labor + dia + setv if ok else 0
            r = karat_x(cost, xm, dc, dh, unit, kx) if ok and xok and dcok and dhok else None
            cl.setText(won(cost) if ok else "-")
            ll.setText(won(r["list"]) if r else "-")
            cd.setText(won(r["card"]) if r else "-")
            ch.setText(won(r["cash"]) if r else ("입력 확인" if self.has_price else "-"))

    def white_extra(self, white: bool):
        if not white:
            return 0
        v, ok = self.num("white", True)
        return js_round(v) if ok and v > 0 else 0

    def recompute(self, *_):
        bad = lambda k, b: set_bad(self.f[k], b)
        vat, vok = self.num("vat")
        vok = vok and 0 <= vat <= 100
        bad("vat", not vok)
        unit = UNITS[self.f_unit.currentData() or 0]
        self.o_incl.setText(won(self.price) if self.has_price else "-")
        self.o_base.setText(won(base(self.price, vat)) if self.has_price and vok else "-")
        # 10K·14K·18K 1돈 = 순금 1돈 × 함량 (부가세 포함 · 별도)
        for k in self.dons:
            pct, pok = self.num("p" + k)
            pok = pok and 0 < pct <= 100
            cap, v, sub = self.dons[k]
            cap.setText(f"{k}K 1돈 ({self.f['p' + k].text().strip()}%) · 부가세 별도" if pok else f"{k}K 1돈 · 부가세 별도")
            if self.has_price and vok and pok:
                v.setText(won(base(self.price, vat) * pct / 100))  # 부가세 별도가 크게
                sub.setText("부가세 포함 " + won(self.price * pct / 100))
            else:
                v.setText("-")
                sub.setText("함량 확인" if self.has_price and not pok else "")

        if self.ag_exact is not None:
            g, gok = self.ag_exact, True
        else:
            g, gok = self.num("ag")
        gok = gok and g > 0
        bad("ag", not gok)
        if self.ag_exact is None:
            bad("ad", not gok)
        else:
            d, ok = self.num("ad")
            bad("ad", not ok or d <= 0)
        labor, lok = self.num("al", True)
        bad("al", not lok)
        wx, wxok = self.num("white", True)
        bad("white", not wxok or wx < 0)
        kw = self.k_white.isChecked()
        kx = self.white_extra(kw)
        dia, dok = self.num("dia", True)
        bad("dia", not dok)
        setv, sok = self.num("set", True)
        bad("set", not sok)
        lok = lok and dok and sok

        any_row = False
        for k in KARAT_KEYS:
            pct, pok = self.num("p" + k)
            pok = pok and 0 < pct <= 100
            bad("p" + k, not pok)
            m, mok = self.num("m" + k)
            mok = mok and 0 <= m < 100
            bad("m" + k, not mok)
            kk, gl, ll, cl, fx, fl = self.krows[k]
            on = self.kchk[k].isChecked()
            for w in (kk, gl, ll, cl, fx, fl):
                w.setVisible(on)
            if not on:
                continue
            any_row = True
            r = karat(self.price, vat, g, labor, dia, setv, pct, m, unit) if (self.has_price and vok and gok and lok and pok and mok) else None
            if r:
                kk.setText(two_line(f"{k}K", "화이트 도금" if kw else ""))
                gl.setText(won(r["gold"]))
                ll.setText(won(labor + dia + setv))
                cl.setText(won(r["gold"] + labor + dia + setv))
                x = karat_excl(self.price, vat, g, labor, dia, setv, pct, m, unit, kx)
                fx.setText(two_line(won(x), f"도금 +{commas(kx)} 포함" if kx else ""))
                fl.setText(two_line(won(r["final"] + kx), f"도금 +{commas(kx)} 포함" if kx else ""))
                fx.setToolTip("")
                fl.setToolTip("")
            else:
                kk.setText(two_line(f"{k}K", ""))
                gl.setText("-")
                ll.setText("-")
                cl.setText("-")
                fx.setText(two_line("-", ""))
                fl.setText(two_line("입력 확인" if self.has_price else "-", ""))
                tip = "노란 칸 중 빨간 칸을 확인하세요" if self.has_price else "시세를 먼저 입력하세요"
                fx.setToolTip(tip)
                fl.setToolTip(tip)
        self.recompute_x(vat, vok, g, gok, labor, lok, dia, setv, unit, kw, kx)
        self.kempty.setVisible(not any_row)

        if self.pg_exact is not None:
            pg, pgok = self.pg_exact, True
        else:
            pg, pgok = self.num("pg")
        pgok = pgok and pg > 0
        bad("pg", not pgok)
        if self.pg_exact is None:
            bad("pd", not pgok)
        else:
            d, ok = self.num("pd")
            bad("pd", not ok or d <= 0)
        ring, rok = self.num("ring", True)
        bad("ring", not rok)
        pl, plok = self.num("pl", True)
        bad("pl", not plok)
        pm, pmok = self.num("pm", True)
        if self.f["pm"].text().strip() == "":
            pm = 2.0  # 비우면 기본 2배
        pmok = pmok and 0 <= pm <= 100
        bad("pm", not pmok)
        mtxt = f"{pm:g}"
        self.pcaps["finx"].setText(f"최종 판매가 · 부가세 별도 (공임 {mtxt}배)" if pmok else "최종 판매가 · 부가세 별도")
        self.pcaps["fin"].setText(f"최종 판매가 · 부가세 포함 (공임 {mtxt}배)" if pmok else "최종 판매가 · 부가세 포함")
        pr = pure(self.price, vat, pg, ring, pl, unit, pm) if (self.has_price and vok and pgok and rok and plok and pmok) else None
        # 매입원가 = 금값 + 고리 + 공임 (부가세 별도) · 최종 판매가 = 매입원가 + 공임 × 배율 (별도·포함)
        self.pcells["cost"].setText(won(self.price / (1 + vat / 100) * pg / GPD + ring + pl) if pr else "-")
        self.pcells["finx"].setText(won(pr["x2"]) if pr else "-")
        self.pcells["fin"].setText(won(pr["i2"]) if pr else "-")

    # ------------------------------------------------------------------ 시세
    def set_status(self, text, is_bad=False):
        # 한 줄에 들어가면 한 줄로 (오른쪽 위 구석), 긴 오류 문구만 줄바꿈
        self.o_status.ensurePolished()
        need = self.o_status.fontMetrics().horizontalAdvance(text) + 6
        one_line = need <= self.o_status.maximumWidth()
        self.o_status.setWordWrap(not one_line)
        self.o_status.setMinimumWidth(need if one_line else 0)
        self.o_status.setText(text)
        v = "true" if is_bad else "false"
        if self.o_status.property("bad") != v:
            self.o_status.setProperty("bad", v)
            self.o_status.style().unpolish(self.o_status)
            self.o_status.style().polish(self.o_status)

    def start_fetch(self):
        if self.fetching:
            return
        self.fetching = True
        self.b_refresh.setEnabled(False)
        self.set_status("한국금거래소 ‘내가 살 때’ 시세 조회 중…")
        self.fetcher.start()

    def on_fetched(self, q, err):
        self.fetching = False
        self.b_refresh.setEnabled(True)
        if err:
            tail = f"이전 시세 유지, 최신 아님 ({self.price_time})" if self.has_price else "수동 시세를 입력하세요"
            self.set_status(f"조회 실패 ({err}) · {tail}", True)
            return
        self.price = q["buy"]
        self.has_price = True
        self.price_time = now_sec()
        self.source = "api"
        self.i_price.setText(commas(self.price))
        self.set_status("API 조회 완료 / 조회 시각 " + self.price_time +
                        (" / 제공일 " + q["date"] if q.get("date") else " / 제공일 정보 없음"))
        self.save_settings()
        self.recompute()

    def apply_manual(self):
        v, ok = parse_num(self.i_price.text())
        if not ok or v <= 0 or v > 1e12:
            QMessageBox.information(self, "입력 확인", "0보다 큰 시세를 숫자로 입력하세요.")
            self.i_price.setFocus()
            return
        self.price = v
        self.has_price = True
        self.price_time = now_sec()
        self.source = "manual"
        self.i_price.setText(commas(v))
        self.set_status("수동 입력 시세 적용 / " + self.price_time)
        self.save_settings()
        self.recompute()

    def set_auto_timer(self):
        self.auto_timer.stop()
        if self.c_auto.isChecked():
            self.auto_timer.start(AUTO_MS)

    # ------------------------------------------------------------------ 초기화
    def ask(self, title, msg):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        yes = box.addButton("예", QMessageBox.AcceptRole)
        box.addButton("아니요", QMessageBox.RejectRole)
        box.exec()
        return box.clickedButton() is yes

    def reset_defaults(self):
        if not self.ask("기본값", "기준값·중량·공임·마진을 기본값으로 되돌릴까요?\n(시세는 그대로 둡니다)"):
            return
        self.loading = True
        for k in storage.FIELDS:
            self.f[k].setText(storage.DEFAULTS[k])
        self.ag_exact = None
        self.f["ad"].setText(fixed2(3.75 / GPD))
        self.pg_exact = None
        self.f["pd"].setText(fixed2(3.75 / GPD))
        for cb in self.kchk.values():
            cb.setChecked(True)
        self.f_unit.setCurrentIndex(0)
        self.loading = False
        self.recompute()
        self.save_settings()

    def clear_section(self, kind):
        self.loading = True
        if kind == "k":
            self.ag_exact = None
            for k in ("ag", "ad", "al", "dia", "set"):
                self.f[k].setText("")
            self.k_white.setChecked(False)
        else:
            self.pg_exact = None
            for k in ("pg", "pd", "ring", "pl"):
                self.f[k].setText("")
        self.loading = False
        self.f["ag" if kind == "k" else "pg"].setFocus()
        self.recompute()
        self.schedule_save()

    # ------------------------------------------------------------------ 업데이트
    def check_update(self, quiet=True):
        if self.update_busy:
            return
        self.update_busy = True
        self._quiet = quiet
        self.b_check.setEnabled(False)
        self.b_check.setText("확인 중…")
        self.checker.start()

    def on_update_checked(self, info, err):
        self.update_busy = False
        self.b_check.setEnabled(True)
        self.b_check.setText("업데이트 확인")
        if info:
            self.update_info = info
            self.b_update.setText(f"새 버전 {info['version']} 업데이트")
            self.b_update.show()
            if not self._quiet:
                self.start_update(info)
            elif update.current_target()[0] is not None and self.ask_update(info):
                # 실행할 때 확인한 경우: 바로 물어보고, '나중에'면 위쪽 버튼만 남김
                self.start_update(info, confirm=False)
            return
        if self._quiet:
            return
        if err:
            self.say("업데이트 확인", "새 버전을 확인하지 못했습니다.\n" + err)
        else:
            self.say("업데이트 확인", f"지금 쓰는 v{__version__} 이 최신 버전입니다.")

    def say(self, title, msg):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.addButton("확인", QMessageBox.AcceptRole)
        box.exec()

    def ask_update(self, info):
        box = QMessageBox(self)
        box.setWindowTitle("새 버전")
        box.setIcon(QMessageBox.Information)
        box.setText(f"새 버전 {info['version']}이(가) 있습니다. 지금 업데이트할까요?")
        box.setInformativeText(f"지금 v{__version__} · 받을 파일 {info['size'] / 1048576:.0f}MB\n"
                               "다 받으면 프로그램이 잠깐 닫혔다가 새 버전으로 다시 열립니다.\n"
                               "기준값과 시세는 그대로 남습니다.")
        yes = box.addButton("지금 업데이트", QMessageBox.AcceptRole)
        later = box.addButton("나중에", QMessageBox.RejectRole)
        box.setDefaultButton(yes)
        box.setEscapeButton(later)
        box.exec()
        return box.clickedButton() is yes

    def start_update(self, info, confirm=True):
        if not info:
            return
        target, why = update.current_target()
        if target is None:
            self.say("업데이트", why)
            return
        if confirm and not self.ask("업데이트", f"새 버전 {info['version']}을(를) 받아 지금 프로그램과 바꿀까요?\n"
                                   f"(지금 v{__version__} · 받을 파일 {info['size'] / 1048576:.0f}MB)\n\n"
                                   "다 받으면 프로그램이 잠깐 닫혔다가 새 버전으로 다시 열립니다.\n기준값과 시세는 그대로 남습니다."):
            return
        dlg = QProgressDialog("새 버전을 받는 중…", "취소", 0, 100, self)
        dlg.setWindowTitle("업데이트")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)
        dlg.setAutoReset(False)
        dlg.setValue(0)
        w = UpdateWorker(info)
        w.progress.connect(lambda got, total: (dlg.setMaximum(max(1, total)), dlg.setValue(min(got, max(1, total))),
                                               dlg.setLabelText(f"새 버전을 받는 중… {got / 1048576:.1f} / {total / 1048576:.1f}MB")))
        w.stage.connect(dlg.setLabelText)
        dlg.canceled.connect(w.cancel)
        result = {}
        w.done.connect(lambda err: (result.setdefault("err", err), dlg.close()))
        self._update_worker = w
        w.start()
        dlg.exec()
        if "err" not in result:  # 창을 닫았는데 아직 일하는 중이면 취소
            w.cancel()
            return
        if result["err"]:
            if result["err"] != "취소했습니다":
                self.say("업데이트", "업데이트하지 못했습니다.\n" + result["err"])
            return
        self.save_settings()
        QApplication.quit()  # 설치 스크립트가 프로그램이 닫히길 기다렸다가 바꾸고 다시 엶

    # ------------------------------------------------------------------ 화면 크기
    def on_scale(self, *_):
        if self.loading:
            return
        v = self.f_scale.currentData()
        s = storage.load()
        if str(s.get("scale", "100")) == str(v):
            return
        s["scale"] = str(v)
        s.pop("window", None)  # 크기가 바뀌면 창 크기는 화면에 맞춰 다시 정함
        storage.save(s)
        if self.ask("화면 크기", f"화면 크기를 {v}%로 바꿉니다.\n프로그램을 다시 열어야 적용됩니다. 지금 다시 열까요?\n(기준값과 시세는 그대로입니다)"):
            self.restart_requested = True
            self.save_settings()
            QApplication.quit()

    # ------------------------------------------------------------------ 저장
    def load_settings(self):
        self.loading = True
        s = storage.load()
        for k in storage.FIELDS:
            self.f[k].setText(str(s[k]) if k in s else storage.DEFAULTS[k])
        g, _ = parse_num(self.f["ag"].text())
        if g > 0:
            self.f["ad"].setText(fixed2(g / GPD))
        pg, _ = parse_num(self.f["pg"].text())
        if pg > 0:
            self.f["pd"].setText(fixed2(pg / GPD))
        for k in KARAT_KEYS:
            self.kchk[k].setChecked(str(s.get("show" + k, "1")) == "1")
        self.c_auto.setChecked(str(s.get("auto", "1")) == "1")
        self.k_xmode.setChecked(str(s.get("xmode", "1")) == "1")
        try:
            u = int(s.get("unit", "0"))
        except (TypeError, ValueError):
            u = 0
        self.f_unit.setCurrentIndex(u if 0 <= u < len(UNITS) else 0)
        p, ok = parse_num(s.get("price", ""))
        if ok and p > 0:
            self.price = p
            self.has_price = True
            self.price_time = s.get("time", "")
            self.source = s.get("source", "")
            self.i_price.setText(commas(p))
            self.set_status("저장된 이전 시세 · 최신 조회 아님 / " + self.price_time)
        sc_ = str(s.get("scale", "100"))
        self.f_scale.setCurrentIndex(max(0, self.f_scale.findData(int(sc_) if sc_.isdigit() else 100)))
        if str(s.get("tab", "0")) == "1":
            self.tabs.setCurrentIndex(1)
        geo = s.get("window")
        if isinstance(geo, list) and len(geo) == 2:
            try:
                self.resize(int(geo[0]), int(geo[1]))
            except (TypeError, ValueError):
                pass
        self.loading = False

    def schedule_save(self):
        if not self.loading:
            self.save_timer.start(800)

    def save_settings(self):
        s = storage.load()
        for k in storage.FIELDS:
            s[k] = self.f[k].text()
        for k in KARAT_KEYS:
            s["show" + k] = "1" if self.kchk[k].isChecked() else "0"
        s["auto"] = "1" if self.c_auto.isChecked() else "0"
        s["xmode"] = "1" if self.k_xmode.isChecked() else "0"
        s["unit"] = str(self.f_unit.currentIndex())
        if self.has_price:
            s["price"] = str(int(round(self.price)))
            s["time"] = self.price_time
            s["source"] = self.source
        s["tab"] = str(self.tabs.currentIndex()) if hasattr(self, "tabs") else s.get("tab", "0")
        if not self.isMaximized() and not self.restart_requested:
            s["window"] = [self.width(), self.height()]
        storage.save(s)

    def closeEvent(self, e):
        self.save_settings()
        self.gold.save_on_quit()  # 고금 매입: 원본처럼 입력 중인 시세·중량·설정 저장
        super().closeEvent(e)
