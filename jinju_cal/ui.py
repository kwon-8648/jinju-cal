"""계산기 화면 — 매장관리 웹의 계산기 탭에서 상품 검색·코드·저장 부분을 뺀 것."""
from __future__ import annotations

import sys
from datetime import datetime

import threading

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QApplication, QLineEdit, QMainWindow, QMessageBox, QProgressDialog, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__, storage, update
from .core import GPD, UNITS, base, commas, fixed2, js_round, karat, karat_excl, parse_num, pure, won
from .price import PriceFetcher

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
    QWidget {{ color:{C['ink']}; font-size:14px; }}
    QMainWindow, QScrollArea, #page {{ background:{C['bg']}; }}
    QFrame#card {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:6px; }}
    QLabel#h2 {{ font-size:16px; font-weight:700; }}
    QLabel#lab {{ color:{C['muted']}; font-size:12px; }}
    QLabel#note {{ color:{C['muted']}; font-size:12px; }}
    QLabel#big {{ font-size:24px; font-weight:700; }}
    QLabel#bigbase {{ font-size:24px; font-weight:700; color:{C['gold']}; }}
    QLabel#status {{ color:{C['muted']}; font-size:13px; }}
    QLabel#status[bad="true"] {{ color:{C['bad']}; }}
    QLabel#ver {{ color:{C['muted']}; font-size:11px; }}
    QLabel#title {{ color:{C['gold']}; font-size:24px; font-weight:800; }}
    QLineEdit {{ background:{C['input']}; border:1px solid {C['input_line']}; border-radius:4px;
                 padding:5px 8px; min-height:22px; selection-background-color:{C['gold']}; }}
    QLineEdit:focus {{ border:2px solid {C['gold']}; padding:4px 7px; }}
    QLineEdit[invalid="true"] {{ border:1px solid {C['bad']}; background:{C['bad_in']}; }}
    QLineEdit[invalid="true"]:focus {{ border:2px solid {C['bad']}; }}
    QComboBox {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:4px; padding:4px 8px; min-height:22px; }}
    QComboBox QAbstractItemView {{ background:{C['panel']}; selection-background-color:{C['soft']}; selection-color:{C['ink']}; }}
    QPushButton {{ background:{C['gold']}; color:{C['gold_ink']}; border:1px solid {C['gold']}; border-radius:4px;
                   padding:6px 14px; font-weight:600; min-height:22px; }}
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
    QLabel#kfinx {{ font-size:17px; font-weight:700; border:1px solid {C['line']}; border-radius:4px; padding:4px 8px; }}
    QFrame#vline {{ background:{C['line']}; border:none; }}
    QLabel#kfin {{ font-size:17px; font-weight:700; background:{C['soft']}; border-radius:4px; padding:4px 8px; }}
    QFrame#cell {{ border:1px solid {C['line']}; border-radius:4px; background:{C['panel']}; }}
    QFrame#cellincl {{ border:1px solid {C['line']}; border-radius:4px; background:{C['soft']}; }}
    QLabel#donv {{ font-size:17px; font-weight:700; }}
    QLabel#cellv {{ font-size:18px; font-weight:700; }}
    QFrame#hline {{ background:{C['line']}; max-height:1px; min-height:1px; border:none; }}
    """


def now_sec():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def card():
    f = QFrame()
    f.setObjectName("card")
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(10)
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
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
        if getattr(sys, "frozen", False):  # 만든 프로그램일 때만 실행 3초 뒤 조용히 새 버전 확인
            QTimer.singleShot(3000, lambda: self.check_update(quiet=True))

    # ------------------------------------------------------------------ 화면
    def build(self):
        page = QWidget()
        page.setObjectName("page")
        root = QVBoxLayout(page)
        root.setContentsMargins(18, 14, 18, 10)
        root.setSpacing(14)

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
        for attr, cap, name in [("o_incl", "부가세 포함 가격", "big"), ("o_base", "부가세 별도 가격 · 계산 기준", "bigbase")]:
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
            vl.setContentsMargins(12, 6, 12, 8)
            vl.setSpacing(1)
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
        grid.setSpacing(14)

        sc, sl = card()
        sc.setFixedWidth(270)
        sl.addWidget(label("기준값", "h2"))
        for key, cap, ph in [("vat", "부가세율 %", ""), ("p10", "10K 함량 %", ""), ("p14", "14K 함량 %", ""),
                             ("p18", "18K 함량 %", ""), ("white", "화이트골드 추가금 (원)", "")]:
            fd = Field(cap, ph)
            self.f[key] = fd.edit
            sl.addWidget(fd)
        uf = ComboField("판매가 올림 단위", [("100원 단위", 0), ("1,000원 단위", 1), ("10,000원 단위", 2)])
        self.f_unit = uf.combo
        sl.addWidget(uf)
        sl.addWidget(label("노란 칸을 수정하면 자동 계산\n최종 판매가는 선택한 올림 단위로 올림", "note", wrap=True))
        sl.addWidget(label("g 또는 돈 입력 시 자동 환산 · 중량 2자리 / 금액 정수 표시, 계산은 원래 값 유지.\n\n"
                           "마진율은 올림 전 판매가 기준 · 조회·입력 시세는 부가세 포함으로 고정합니다.", "note", wrap=True))
        self.b_reset = button("기본값으로 되돌리기", "ghost")
        sl.addWidget(self.b_reset)
        sl.addStretch(1)
        grid.addWidget(sc, 0, Qt.AlignTop)

        stack = QVBoxLayout()
        stack.setSpacing(14)

        # 10K·14K·18K
        kc, kl = card()
        kh = QHBoxLayout()
        kh.setSpacing(12)
        kh.addWidget(label("10K · 14K · 18K 상품", "h2"))
        kh.addStretch(1)
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
        self.k_clear = button("초기화", "plain")
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
        kl.addWidget(label("표의 공임 = 공임 + 랩다이아 알값 + 다이아 셋팅비, 매입원가 = 금값 + 공임 (모두 부가세 별도, 공란은 0원).\n"
                           "중량·공임은 캐럿 공통, 마진율은 판매가 기준입니다.", "note", wrap=True))
        self.ktable = QFrame()
        self.ktable.setObjectName("ktable")
        self.kgrid = QGridLayout(self.ktable)
        self.kgrid.setContentsMargins(12, 10, 12, 10)
        self.kgrid.setHorizontalSpacing(14)
        self.kgrid.setVerticalSpacing(8)
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
            kk = label(k + "K", "kk")
            kk.setTextFormat(Qt.RichText)
            g = label("-", "kv")
            lab_ = label("-", "kv")
            c = label("-", "kv")
            finx = label("-", "kfinx")
            finx.setTextFormat(Qt.RichText)
            fin = label("-", "kfin")
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
        stack.addWidget(kc)

        # 순금
        pcard, pcl = card()
        ph = QHBoxLayout()
        ph.addWidget(label("순금 상품", "h2"))
        ph.addStretch(1)
        self.p_clear = button("초기화", "plain")
        ph.addWidget(self.p_clear)
        pcl.addLayout(ph)
        pr = QHBoxLayout()
        pr.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(10)
        r4 = QGridLayout()
        r4.setHorizontalSpacing(10)
        for i, (key, cap, phd) in enumerate([("pg", "중량 (g)", ""), ("pd", "환산 중량 (돈)", ""),
                                             ("ring", "고리 금액 (별도)", "0"), ("pl", "개별공임 (별도)", "")]):
            fd = Field(cap, phd)
            self.f[key] = fd.edit
            r4.addWidget(fd, 0, i)
            r4.setColumnStretch(i, 1)
        left.addLayout(r4)
        left.addWidget(label("금액은 모두 부가세 별도 · 고리 금액 공란은 0원 · 공임 배수는 고리 금액에 미적용\n"
                             "공임 1배 = 공임×2, 공임 2배 = 공임×3", "note", wrap=True))
        left.addStretch(1)
        pr.addLayout(left, 3)
        cells = QGridLayout()
        cells.setSpacing(8)
        self.pcells = {}
        for i, (key, cap, incl) in enumerate([("p1x", "공임 1배 · 부가세 별도", False), ("p1i", "공임 1배 · 부가세 포함", True),
                                              ("p2x", "공임 2배 · 부가세 별도", False), ("p2i", "공임 2배 · 부가세 포함", True)]):
            fr = QFrame()
            fr.setObjectName("cellincl" if incl else "cell")
            vl = QVBoxLayout(fr)
            vl.setContentsMargins(12, 8, 12, 10)
            vl.setSpacing(2)
            vl.addWidget(label(cap, "lab"))
            v = label("-", "cellv")
            v.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vl.addWidget(v)
            self.pcells[key] = v
            cells.addWidget(fr, i // 2, i % 2)
        pr.addLayout(cells, 2)
        pcl.addLayout(pr)
        stack.addWidget(pcard)
        stack.addStretch(1)

        grid.addLayout(stack, 1)
        root.addLayout(grid, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        self.b_check = button("업데이트 확인", "small")
        foot.addWidget(self.b_check)
        self.ver = label(f"v{__version__}", "ver")
        foot.addWidget(self.ver)
        root.addLayout(foot)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setCentralWidget(scroll)
        # 가로로 잘리지 않는 최소 너비 (세로는 스크롤)
        self.setMinimumSize(page.minimumSizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 4, 560)

    # ------------------------------------------------------------------ 연결
    def wire(self):
        for key, ed in self.f.items():
            ed.textChanged.connect(lambda _t, k=key: self.on_field(k))
        for cb in self.kchk.values():
            cb.toggled.connect(self.on_change)
        self.f_unit.currentIndexChanged.connect(self.on_change)
        self.k_white.toggled.connect(self.recompute)
        self.b_manual.clicked.connect(self.apply_manual)
        self.i_price.returnPressed.connect(self.apply_manual)
        self.b_refresh.clicked.connect(self.start_fetch)
        self.c_auto.toggled.connect(self.on_auto)
        self.b_reset.clicked.connect(self.reset_defaults)
        self.k_clear.clicked.connect(lambda: self.clear_section("k"))
        self.b_check.clicked.connect(lambda: self.check_update(quiet=False))
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
                small = lambda t: f'<br><span style="font-size:11px;color:{C["muted"]};font-weight:500">{t}</span>'
                kk.setText(f"{k}K" + (f'<br><span style="font-size:11px;color:{C["muted"]};font-weight:500">화이트 도금</span>' if kw else ""))
                gl.setText(won(r["gold"]))
                ll.setText(won(labor + dia + setv))
                cl.setText(won(r["gold"] + labor + dia + setv))
                x = karat_excl(self.price, vat, g, labor, dia, setv, pct, m, unit, kx)
                fx.setText(won(x) + (small(f"도금 +{commas(kx)} 포함") if kx else ""))
                fl.setText(won(r["final"] + kx) + (small(f"도금 +{commas(kx)} 포함") if kx else ""))
                fx.setToolTip("")
                fl.setToolTip("")
            else:
                kk.setText(f"{k}K")
                gl.setText("-")
                ll.setText("-")
                cl.setText("-")
                fx.setText("-")
                fl.setText("입력 확인" if self.has_price else "-")
                tip = "노란 칸 중 빨간 칸을 확인하세요" if self.has_price else "시세를 먼저 입력하세요"
                fx.setToolTip(tip)
                fl.setToolTip(tip)
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
        pr = pure(self.price, vat, pg, ring, pl, unit) if (self.has_price and vok and pgok and rok and plok) else None
        for key, rk in (("p1x", "x1"), ("p1i", "i1"), ("p2x", "x2"), ("p2i", "i2")):
            self.pcells[key].setText(won(pr[rk]) if pr else "-")

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

    def start_update(self, info):
        if not info:
            return
        target, why = update.current_target()
        if target is None:
            self.say("업데이트", why)
            return
        if not self.ask("업데이트", f"새 버전 {info['version']}을(를) 받아 지금 프로그램과 바꿀까요?\n"
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
        s["unit"] = str(self.f_unit.currentIndex())
        if self.has_price:
            s["price"] = str(int(round(self.price)))
            s["time"] = self.price_time
            s["source"] = self.source
        if not self.isMaximized():
            s["window"] = [self.width(), self.height()]
        storage.save(s)

    def closeEvent(self, e):
        self.save_settings()
        super().closeEvent(e)
