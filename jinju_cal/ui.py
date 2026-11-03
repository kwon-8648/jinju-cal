"""화면 — 매장관리 웹의 '계산기' 탭과 같은 배치·색.
위: 시세 / 왼쪽: 기준값 / 오른쪽: 10K·14K·18K 상품, 순금 상품. 노란 칸 = 입력하는 칸."""
from __future__ import annotations

import os
import ssl
import sys
import time
import urllib.error
import urllib.request

from PySide6.QtCore import QObject, QStringListModel, Qt, QThread, QTimer, QUrl, Signal, QEvent
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut, QIcon
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QCompleter, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from . import APP_NAME, __version__
from . import core
from .core import commas, won, fixed2, parse_num, GPD, UNITS, KARAT_KEYS
from .storage import Store

# ---------------------------------------------------------------- 색 (웹판과 같음)
C = dict(bg="#f6f2e9", panel="#fffdf8", soft="#efe6d2", line="#e3d9c4", ink="#2d2314", muted="#69645c",
         gold="#884b04", gold_ink="#fffdf8", input="#fff6c9", input_line="#e6cf6b", bad="#a1361f",
         bad_in="#fbe1da", good="#3d6b2f")

if sys.platform == "darwin":
    BODY_FONT, TITLE_FONT = "Apple SD Gothic Neo", "AppleMyungjo"
elif sys.platform == "win32":
    BODY_FONT, TITLE_FONT = "Malgun Gothic", "Batang"
else:
    BODY_FONT, TITLE_FONT = "Noto Sans CJK KR", "Noto Serif CJK KR"

ZOOMS = [0.9, 1.0, 1.1, 1.2, 1.35, 1.5]


def stylesheet(z: float) -> str:
    px = lambda n: f"{round(n * z)}px"  # noqa: E731
    return f"""
    QWidget {{ color:{C['ink']}; font-family:"{BODY_FONT}"; font-size:{px(14)}; }}
    QMainWindow, QScrollArea, #page {{ background:{C['bg']}; }}
    QFrame#card {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:6px; }}
    QLabel#brand {{ font-family:"{TITLE_FONT}"; font-weight:800; font-size:{px(22)}; color:{C['gold']}; }}
    QLabel#h2 {{ font-weight:700; font-size:{px(15)}; }}
    QLabel#lab {{ color:{C['muted']}; font-size:{px(12)}; }}
    QLabel#note {{ color:{C['muted']}; font-size:{px(12)}; }}
    QLabel#big {{ font-size:{px(24)}; font-weight:700; }}
    QLabel#bigbase {{ font-size:{px(24)}; font-weight:700; color:{C['gold']}; }}
    QLabel#status {{ color:{C['muted']}; font-size:{px(13)}; }}
    QLabel#status[bad="true"] {{ color:{C['bad']}; }}
    QLabel#ver {{ color:{C['muted']}; font-size:{px(11)}; }}
    QLabel#th {{ color:{C['muted']}; font-size:{px(12)}; }}
    QLabel#k {{ font-weight:700; color:{C['gold']}; font-size:{px(15)}; }}
    QLabel#cell {{ font-size:{px(15)}; }}
    QLabel#fin {{ font-weight:700; font-size:{px(17)}; background:{C['soft']}; border-radius:4px; padding:4px 8px; }}
    QLabel#sub {{ color:{C['muted']}; font-size:{px(11)}; }}
    QFrame#pcell {{ border:1px solid {C['line']}; border-radius:4px; background:{C['panel']}; }}
    QFrame#pcell[incl="true"] {{ background:{C['soft']}; }}
    QLabel#pv {{ font-size:{px(18)}; font-weight:700; }}
    QLineEdit {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:4px; padding:{px(5)} {px(8)}; min-height:{px(22)}; }}
    QLineEdit[y="true"] {{ background:{C['input']}; border:1px solid {C['input_line']}; }}
    QLineEdit[invalid="true"] {{ border:2px solid {C['bad']}; background:{C['bad_in']}; }}
    QLineEdit:focus {{ border:2px solid {C['gold']}; }}
    QComboBox {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:4px; padding:{px(4)} {px(8)}; min-height:{px(22)}; }}
    QComboBox QAbstractItemView {{ background:{C['panel']}; selection-background-color:{C['soft']}; selection-color:{C['ink']}; }}
    QPushButton {{ background:{C['gold']}; color:{C['gold_ink']}; border:1px solid {C['gold']}; border-radius:4px; padding:{px(6)} {px(14)}; font-weight:600; }}
    QPushButton:hover {{ background:#9a5606; }}
    QPushButton:disabled {{ background:{C['line']}; border-color:{C['line']}; color:{C['muted']}; }}
    QPushButton[ghost="true"] {{ background:transparent; color:{C['gold']}; }}
    QPushButton[ghost="true"]:hover {{ background:{C['soft']}; }}
    QPushButton[plain="true"] {{ background:transparent; color:{C['muted']}; border:1px solid {C['line']}; font-weight:500; }}
    QPushButton[plain="true"]:hover {{ background:{C['soft']}; color:{C['ink']}; }}
    QToolButton#menu {{ background:{C['panel']}; border:1px solid {C['line']}; border-radius:12px; padding:{px(5)} {px(14)}; font-weight:600; }}
    QToolButton#menu::menu-indicator {{ image:none; }}
    QCheckBox {{ font-weight:600; spacing:6px; }}
    QMenu {{ background:{C['panel']}; border:1px solid {C['line']}; }}
    QMenu::item {{ padding:{px(6)} {px(18)}; }}
    QMenu::item:selected {{ background:{C['soft']}; }}
    QMenu::separator {{ height:1px; background:{C['line']}; margin:4px 8px; }}
    QListView {{ background:{C['panel']}; border:1px solid {C['line']}; font-size:{px(14)}; }}
    QListView::item {{ padding:{px(5)} {px(8)}; }}
    QListView::item:selected {{ background:{C['soft']}; color:{C['ink']}; }}
    QMessageBox QLabel {{ font-size:{px(14)}; }}
    QStatusBar {{ background:{C['bg']}; }}
    """


def _restyle(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


def lab(text: str, name: str = "lab") -> QLabel:
    lb = QLabel(text)
    lb.setObjectName(name)
    return lb


def note(text: str) -> QLabel:
    lb = lab(text, "note")
    lb.setWordWrap(True)
    return lb


def card() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 16)
    v.setSpacing(10)
    return f, v


def edit(yellow=True, align_right=True, placeholder="") -> QLineEdit:
    e = QLineEdit()
    if yellow:
        e.setProperty("y", True)
    if align_right:
        e.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    if placeholder:
        e.setPlaceholderText(placeholder)
    return e


def field(label: str, w: QWidget) -> QWidget:
    box = QWidget()
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    lb = lab(label)
    lb.setBuddy(w)
    v.addWidget(lb)
    v.addWidget(w)
    return box


def button(text: str, kind: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setProperty(kind, True)
    b.setCursor(Qt.PointingHandCursor)
    return b


def set_bad(w: QLineEdit, bad: bool):
    if bool(w.property("invalid")) != bool(bad):
        w.setProperty("invalid", bool(bad))
        _restyle(w)


def now_sec() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- 시세 조회 (별도 스레드)
class Fetcher(QObject):
    done = Signal(object, str)  # (quote dict 또는 None, 오류 문구)

    def run(self):
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            pass
        first_err = ""
        for url in core.PRICE_URLS:
            try:
                req = urllib.request.Request(url, headers=core.PRICE_HEADERS)
                try:
                    with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
                        text = r.read().decode("utf-8", "replace")
                except urllib.error.HTTPError as e:
                    raise core.QuoteError("HTTP " + str(e.code))
                except Exception:
                    raise core.QuoteError("인터넷 연결 또는 서버 접속 실패")
                self.done.emit(core.parse_api(text), "")
                return
            except core.QuoteError as e:
                first_err = first_err or str(e)  # 상태줄에는 금거래소에 직접 물었을 때의 오류를 보여줌
            except Exception as e:
                first_err = first_err or (str(e) or e.__class__.__name__)
        self.done.emit(None, first_err)


# ---------------------------------------------------------------- 상품 구역 (검색·코드·이름·상호·품목·저장·삭제)
class ProductRow(QWidget):
    picked = Signal(dict)

    def __init__(self, kind: str, win: "MainWindow"):
        super().__init__()
        self.kind, self.win = kind, win
        g = QHBoxLayout(self)
        g.setContentsMargins(0, 0, 0, 0)
        g.setSpacing(8)
        self.q = edit(yellow=False, align_right=False, placeholder="코드·이름·상호·초성")
        self.code = edit(yellow=False, align_right=False)
        self.name = edit(yellow=False, align_right=False)
        self.maker = edit(yellow=False, align_right=False)
        self.cat = QComboBox()
        self.cat.addItem("자동", "")
        for c in core.CATS:
            self.cat.addItem(c, c)
        self.save_b = button("저장")
        self.del_b = button("삭제", "plain")
        for lbl, w, stretch in (("검색", self.q, 3), ("코드", self.code, 2), ("상품명", self.name, 3), ("상호", self.maker, 2), ("품목", self.cat, 1)):
            g.addWidget(field(lbl, w), stretch)
        acts = QWidget()
        h = QHBoxLayout(acts)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        h.addWidget(self.save_b)
        h.addWidget(self.del_b)
        g.addWidget(acts, 0, Qt.AlignBottom)

        self.model = QStringListModel()
        self.comp = QCompleter(self.model, self)
        self.comp.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.comp.setMaxVisibleItems(12)
        self.comp.setWidget(self.q)
        self.comp.activated[str].connect(self._on_pick)
        self.hits: dict[str, dict] = {}
        self.q.textEdited.connect(lambda _t: self.show_hits())
        self.q.installEventFilter(self)
        self.save_b.clicked.connect(lambda: win.save_product(kind))
        self.del_b.clicked.connect(lambda: win.delete_product(kind))

    def eventFilter(self, obj, ev):
        if obj is self.q and ev.type() == QEvent.FocusIn:
            QTimer.singleShot(0, self.show_hits)
        return False

    def show_hits(self):
        q = self.q.text()
        allp = [p for p in self.win.products if p["kind"] == self.kind]
        hits = [p for p in allp if core.match_product(q, p["code"], p.get("name", "") + " " + p.get("maker", "") + " " + p.get("cat", ""))]
        if not allp:
            self.win.flash("저장된 상품이 없습니다. 상품코드를 입력하고 저장하세요.")
            return
        if not hits:
            self.model.setStringList([])
            self.comp.popup().hide()
            self.win.flash(f"'{q.strip()}'와 일치하는 상품이 없습니다")
            return
        hits = hits[:200]
        self.hits = {core.product_label(p): p for p in hits}
        self.model.setStringList(list(self.hits.keys()))
        self.comp.complete()

    def _on_pick(self, label: str):
        p = self.hits.get(label)
        if p:
            self.picked.emit(p)
        QTimer.singleShot(0, lambda: self.q.setText(""))

    def fill(self, p: dict):
        self.code.setText(p["code"])
        self.name.setText(p.get("name", ""))
        self.maker.setText(p.get("maker", ""))
        i = self.cat.findData(p.get("cat", ""))
        self.cat.setCurrentIndex(max(0, i))

    def clear(self):
        for w in (self.q, self.code, self.name, self.maker):
            w.setText("")
        self.cat.setCurrentIndex(0)


# ---------------------------------------------------------------- 메인 창
class MainWindow(QMainWindow):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.products = store.products()
        self.s = store.settings()
        self.price, self.has_price, self.price_time, self.source = 0.0, False, "", ""
        self.ag_exact = None
        self.pg_exact = None
        self.loading = False
        self.fetching = False
        self.thread = None
        self.zoom = self.s.get("zoom", 1.0) if self.s.get("zoom") in ZOOMS else 1.0

        self.setWindowTitle(APP_NAME)
        self._build()
        self._load_settings()
        self.recompute()

        self.save_timer = QTimer(self, singleShot=True, interval=800, timeout=self.save_settings)
        self.auto_timer = QTimer(self, interval=10 * 60 * 1000, timeout=self.start_fetch)
        self._set_auto_timer()
        if self.auto.isChecked():
            QTimer.singleShot(300, self.start_fetch)

    # ------------------------------------------------------------ 화면 구성
    def _build(self):
        page = QWidget()
        page.setObjectName("page")
        root = QVBoxLayout(page)
        root.setContentsMargins(18, 12, 18, 16)
        root.setSpacing(14)

        # 머리줄
        top = QHBoxLayout()
        brand = lab(APP_NAME, "brand")
        top.addWidget(brand)
        top.addWidget(lab("이 PC에 저장"), 0, Qt.AlignBottom)
        top.addStretch(1)
        self.menu_b = QToolButton()
        self.menu_b.setObjectName("menu")
        self.menu_b.setText("자료")
        self.menu_b.setPopupMode(QToolButton.InstantPopup)
        self.menu_b.setCursor(Qt.PointingHandCursor)
        m = QMenu(self)
        m.addAction("상품 내보내기…", self.export_products)
        m.addAction("상품 가져오기…", self.import_products)
        self.undo_act = m.addAction("마지막 가져오기 되돌리기", self.undo_import)
        m.addSeparator()
        m.addAction("글자 크게  (Ctrl +)", lambda: self.set_zoom(+1))
        m.addAction("글자 작게  (Ctrl −)", lambda: self.set_zoom(-1))
        m.addSeparator()
        m.addAction("저장 폴더 열기", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.store.root)))
        m.addAction("프로그램 정보", self.about)
        m.aboutToShow.connect(lambda: self.undo_act.setEnabled(self.store.last_backup() is not None))
        self.menu_b.setMenu(m)
        top.addWidget(self.menu_b)
        root.addLayout(top)

        # 시세 카드
        pc, pv = card()
        head = QHBoxLayout()
        head.addWidget(lab("순금 1돈(3.75g) · 내가 살 때", "h2"))
        head.addStretch(1)
        self.auto = QCheckBox("자동조회 (실행 시 / 10분 간격)")
        head.addWidget(self.auto)
        pv.addLayout(head)
        row = QHBoxLayout()
        row.setSpacing(24)
        kv1, self.o_incl = QVBoxLayout(), lab("-", "big")
        kv1.addWidget(lab("부가세 포함 가격"))
        kv1.addWidget(self.o_incl)
        kv2, self.o_base = QVBoxLayout(), lab("-", "bigbase")
        kv2.addWidget(lab("부가세 별도 가격 · 계산 기준"))
        kv2.addWidget(self.o_base)
        row.addLayout(kv1, 2)
        row.addLayout(kv2, 2)
        self.i_price = edit(placeholder="예: 612,000")
        self.i_price.setMinimumWidth(150)
        self.b_manual = button("수동 시세 적용")
        self.b_refresh = button("시세 새로고침", "ghost")
        man = QHBoxLayout()
        man.setSpacing(8)
        man.addWidget(field("시세 입력 · 부가세 포함 (원/돈)", self.i_price), 1)
        man.addWidget(self.b_manual, 0, Qt.AlignBottom)
        man.addWidget(self.b_refresh, 0, Qt.AlignBottom)
        row.addLayout(man, 3)
        pv.addLayout(row)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet(f"color:{C['line']}")
        pv.addWidget(line)
        st = QHBoxLayout()
        self.o_status = lab("조회 전입니다. 시세를 조회하거나 수동 입력하세요.", "status")
        self.o_status.setWordWrap(True)
        st.addWidget(self.o_status, 1)
        link = QLabel(f'<a href="https://www.koreagoldx.co.kr/" style="color:{C["gold"]}">한국금거래소 시세 보기 ↗</a>')
        link.setOpenExternalLinks(True)
        st.addWidget(link)
        pv.addLayout(st)
        root.addWidget(pc)

        # 아래: 기준값 | 상품 구역
        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        sc, sv = card()
        sc.setFixedWidth(round(250 * self.zoom))
        self.settings_card = sc
        sv.addWidget(lab("기준값", "h2"))
        self.f = {}
        for key, label, ph in (("vat", "부가세율 %", ""), ("p10", "10K 함량 %", ""), ("p14", "14K 함량 %", ""),
                               ("p18", "18K 함량 %", ""), ("white", "화이트골드 추가금 (원)", "")):
            self.f[key] = edit()
            sv.addWidget(field(label, self.f[key]))
        self.unit = QComboBox()
        for t in ("100원 단위", "1,000원 단위", "10,000원 단위"):
            self.unit.addItem(t)
        sv.addWidget(field("판매가 올림 단위", self.unit))
        sv.addWidget(note("노란 칸을 수정하면 자동 계산\n최종 판매가는 선택한 올림 단위로 올림"))
        sv.addWidget(note("g 또는 돈 입력 시 자동 환산 · 중량 2자리 / 금액 정수 표시, 계산은 원래 값 유지.\n\n"
                          "마진율은 올림 전 판매가 기준 · 조회·입력 시세는 부가세 포함으로 고정합니다."))
        self.b_reset = button("기본값으로 되돌리기", "ghost")
        sv.addWidget(self.b_reset)
        sv.addStretch(1)
        body.addWidget(sc, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(14)
        body.addLayout(right, 1)

        # 10K·14K·18K
        kc, kv = card()
        kh = QHBoxLayout()
        kh.addWidget(lab("10K · 14K · 18K 상품", "h2"))
        kh.addStretch(1)
        kh.addWidget(lab("색상"))
        self.k_color = QComboBox()
        self.k_color.addItem("선택 안 함", "")
        for c in core.COLORS:
            self.k_color.addItem(c, c)
        kh.addWidget(self.k_color)
        kh.addSpacing(10)
        self.showk = {}
        for k in KARAT_KEYS:
            self.showk[k] = QCheckBox(k + "K")
            kh.addWidget(self.showk[k])
        kh.addSpacing(6)
        self.k_clear = button("초기화", "plain")
        kh.addWidget(self.k_clear)
        kv.addLayout(kh)
        self.k_prod = ProductRow("k", self)
        kv.addWidget(self.k_prod)
        r5 = QHBoxLayout()
        r5.setSpacing(8)
        for key, label, ph in (("ag", "공통 중량 (g)", ""), ("ad", "환산 중량 (돈)", ""), ("al", "공통 공임 (부가세 별도)", ""),
                               ("dia", "랩다이아 알값 (부가세 별도)", "0"), ("set", "다이아 셋팅비 (부가세 별도)", "0")):
            self.f[key] = edit(placeholder=ph)
            r5.addWidget(field(label, self.f[key]), 1)
        kv.addLayout(r5)
        r3 = QHBoxLayout()
        r3.setSpacing(8)
        for k in KARAT_KEYS:
            self.f["m" + k] = edit()
            r3.addWidget(field(f"{k}K 마진 %", self.f["m" + k]), 1)
        r3.addStretch(2)
        kv.addLayout(r3)
        kv.addWidget(note("알값·셋팅비는 공임과 함께 공임 포함 원가에 합산합니다 (공란은 0원).\n중량·공임은 캐럿 공통, 마진율은 판매가 기준입니다."))
        self.k_table = QWidget()
        self.k_grid = QGridLayout(self.k_table)
        self.k_grid.setContentsMargins(0, 4, 0, 0)
        self.k_grid.setHorizontalSpacing(12)
        self.k_grid.setVerticalSpacing(6)
        self._build_k_table()
        kv.addWidget(self.k_table)
        right.addWidget(kc)

        # 순금
        uc, uv = card()
        uh = QHBoxLayout()
        uh.addWidget(lab("순금 상품", "h2"))
        uh.addStretch(1)
        self.p_clear = button("초기화", "plain")
        uh.addWidget(self.p_clear)
        uv.addLayout(uh)
        self.p_prod = ProductRow("p", self)
        uv.addWidget(self.p_prod)
        pr = QHBoxLayout()
        pr.setSpacing(14)
        left = QVBoxLayout()
        r4 = QHBoxLayout()
        r4.setSpacing(8)
        for key, label, ph in (("pg", "중량 (g)", ""), ("pd", "환산 중량 (돈)", ""), ("ring", "고리 금액 (별도)", "0"), ("pl", "개별공임 (별도)", "")):
            self.f[key] = edit(placeholder=ph)
            r4.addWidget(field(label, self.f[key]), 1)
        left.addLayout(r4)
        left.addWidget(note("금액은 모두 부가세 별도 · 고리 금액 공란은 0원 · 공임 배수는 고리 금액에 미적용\n공임 1배 = 공임×2, 공임 2배 = 공임×3"))
        left.addStretch(1)
        pr.addLayout(left, 3)
        cells = QGridLayout()
        cells.setSpacing(8)
        self.o_p = {}
        for i, (key, label, incl) in enumerate((("p1x", "공임 1배 · 부가세 별도", False), ("p1i", "공임 1배 · 부가세 포함", True),
                                                ("p2x", "공임 2배 · 부가세 별도", False), ("p2i", "공임 2배 · 부가세 포함", True))):
            fr = QFrame()
            fr.setObjectName("pcell")
            fr.setProperty("incl", incl)
            v = QVBoxLayout(fr)
            v.setContentsMargins(12, 8, 12, 8)
            v.addWidget(lab(label))
            self.o_p[key] = lab("-", "pv")
            self.o_p[key].setAlignment(Qt.AlignRight)
            self.o_p[key].setTextInteractionFlags(Qt.TextSelectableByMouse)
            v.addWidget(self.o_p[key])
            cells.addWidget(fr, i // 2, i % 2)
        pr.addLayout(cells, 2)
        uv.addLayout(pr)
        right.addWidget(uc)
        right.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(page)
        self.setCentralWidget(scroll)

        # 아래 줄: 알림 + 버전 (항상 오른쪽 아래 작게)
        sb = self.statusBar()
        sb.setSizeGripEnabled(True)
        self.ver = lab(f"버전 {__version__}", "ver")
        sb.addPermanentWidget(self.ver)

        # 연결
        for key, w in self.f.items():
            w.textEdited.connect(lambda _t, k=key: self._on_field(k))
        for k in KARAT_KEYS:
            self.showk[k].toggled.connect(self._changed)
        self.unit.currentIndexChanged.connect(self._changed)
        self.k_color.currentIndexChanged.connect(lambda _i: self.recompute())
        self.auto.toggled.connect(self._on_auto)
        self.b_manual.clicked.connect(self.apply_manual)
        self.i_price.returnPressed.connect(self.apply_manual)
        self.b_refresh.clicked.connect(self.start_fetch)
        self.b_reset.clicked.connect(self.reset_defaults)
        self.k_clear.clicked.connect(lambda: self.clear_section("k"))
        self.p_clear.clicked.connect(lambda: self.clear_section("p"))
        self.k_prod.picked.connect(lambda p: self.apply_product("k", p))
        self.p_prod.picked.connect(lambda p: self.apply_product("p", p))
        for seq, d in (("Ctrl++", 1), ("Ctrl+=", 1), ("Ctrl+-", -1)):
            QShortcut(QKeySequence(seq), self, activated=lambda d=d: self.set_zoom(d))

    # ------------------------------------------------------------ 설정 읽기·저장
    def _load_settings(self):
        self.loading = True
        s = self.s
        for k, w in self.f.items():
            if k in ("ad", "pd"):
                continue
            w.setText(str(s[k]) if k in s else core.DEFAULTS[k])
        g, _ = parse_num(self.f["ag"].text())
        self.f["ad"].setText(fixed2(g / GPD) if g > 0 else "")
        pg, _ = parse_num(self.f["pg"].text())
        self.f["pd"].setText(fixed2(pg / GPD) if pg > 0 else "")
        for k in KARAT_KEYS:
            self.showk[k].setChecked(str(s.get("show" + k, "1")) == "1")
        self.auto.setChecked(str(s.get("auto", "1")) == "1")
        try:
            u = int(s.get("unit", 0))
        except (TypeError, ValueError):
            u = 0
        self.unit.setCurrentIndex(u if 0 <= u < len(UNITS) else 0)
        p, ok = parse_num(s.get("price", ""))
        if ok and p > 0:
            self.price, self.has_price = p, True
            self.price_time, self.source = s.get("time", ""), s.get("source", "")
            self.i_price.setText(commas(p))
            self.set_status("저장된 이전 시세 · 최신 조회 아님 / " + self.price_time)
        for kind, row in (("k", self.k_prod), ("p", self.p_prod)):
            row.code.setText(s.get(kind + "_code", ""))
            row.name.setText(s.get(kind + "_name", ""))
            row.maker.setText(s.get(kind + "_maker", ""))
            row.cat.setCurrentIndex(max(0, row.cat.findData(s.get(kind + "_cat", ""))))
        self.k_color.setCurrentIndex(max(0, self.k_color.findData(s.get("k_color", ""))))
        geo = s.get("geometry")
        if isinstance(geo, list) and len(geo) == 4:
            self.setGeometry(*geo)
        else:
            self.resize(1180, 860)
        self.loading = False

    def _changed(self, *_):
        if self.loading:
            return
        self.recompute()
        self.save_timer.start()

    def save_settings(self):
        s = self.store.settings()
        for k, w in self.f.items():
            if k not in ("ad", "pd"):
                s[k] = w.text()
        for k in KARAT_KEYS:
            s["show" + k] = "1" if self.showk[k].isChecked() else "0"
        s["auto"] = "1" if self.auto.isChecked() else "0"
        s["unit"] = str(self.unit.currentIndex())
        if self.has_price:
            s["price"], s["time"], s["source"] = str(int(core.js_round(self.price))), self.price_time, self.source
        for kind, row in (("k", self.k_prod), ("p", self.p_prod)):
            s[kind + "_code"], s[kind + "_name"], s[kind + "_maker"] = row.code.text(), row.name.text(), row.maker.text()
            s[kind + "_cat"] = row.cat.currentData() or ""
        s["k_color"] = self.k_color.currentData() or ""
        g = self.geometry()
        s["geometry"] = [g.x(), g.y(), g.width(), g.height()]
        s["zoom"] = self.zoom
        try:
            self.store.save_settings(s)
        except OSError as e:
            self.flash("설정을 저장하지 못했습니다: " + str(e))

    def closeEvent(self, ev):
        self.save_settings()
        super().closeEvent(ev)

    # ------------------------------------------------------------ 상태줄·알림
    def set_status(self, text: str, bad: bool = False):
        self.o_status.setText(text)
        if bool(self.o_status.property("bad")) != bad:
            self.o_status.setProperty("bad", bad)
            _restyle(self.o_status)

    def flash(self, text: str):
        self.statusBar().showMessage(text, 4000)

    def info(self, title: str, msg: str):
        b = QMessageBox(QMessageBox.Information, title, msg, parent=self)
        b.addButton("확인", QMessageBox.AcceptRole)
        b.exec()

    def yes_no(self, title: str, msg: str) -> bool:
        b = QMessageBox(QMessageBox.Question, title, msg, parent=self)
        y = b.addButton("예", QMessageBox.YesRole)
        b.addButton("아니요", QMessageBox.NoRole)
        b.exec()
        return b.clickedButton() is y

    # ------------------------------------------------------------ 계산
    def _num(self, key, allow_blank=False):
        return parse_num(self.f[key].text(), allow_blank)

    def recompute(self):
        f = self.f
        vat, vok = self._num("vat")
        vok = vok and 0 <= vat <= 100
        set_bad(f["vat"], not vok)
        unit = UNITS[self.unit.currentIndex()] if 0 <= self.unit.currentIndex() < 3 else 100
        self.o_incl.setText(won(self.price) if self.has_price else "-")
        self.o_base.setText(won(core.base(self.price, vat)) if self.has_price and vok else "-")

        if self.ag_exact is not None:
            g, gok = self.ag_exact, True
        else:
            g, gok = self._num("ag")
        gok = gok and g > 0
        set_bad(f["ag"], not gok)
        if self.ag_exact is None:
            set_bad(f["ad"], not gok)
        else:
            d, ok = self._num("ad")
            set_bad(f["ad"], not ok or d <= 0)
        labor, lok = self._num("al", True)
        set_bad(f["al"], not lok)
        wx, wxok = self._num("white", True)
        set_bad(f["white"], not wxok or wx < 0)
        kc = self.k_color.currentData() or ""
        kx = core.white_extra(kc, f["white"].text())
        dia, dok = self._num("dia", True)
        set_bad(f["dia"], not dok)
        setv, sok = self._num("set", True)
        set_bad(f["set"], not sok)
        lok = lok and dok and sok

        rows = []
        for k in KARAT_KEYS:
            pct, pok = self._num("p" + k)
            pok = pok and 0 < pct <= 100
            set_bad(f["p" + k], not pok)
            m, mok = self._num("m" + k)
            mok = mok and 0 <= m < 100
            set_bad(f["m" + k], not mok)
            if not self.showk[k].isChecked():
                continue
            r = core.karat(self.price, vat, g, labor, dia, setv, pct, m, unit) if (self.has_price and vok and gok and lok and pok and mok) else None
            rows.append((k, r))
        self._render_k(rows, kc, kx)

        if self.pg_exact is not None:
            pg, pgok = self.pg_exact, True
        else:
            pg, pgok = self._num("pg")
        pgok = pgok and pg > 0
        set_bad(f["pg"], not pgok)
        if self.pg_exact is None:
            set_bad(f["pd"], not pgok)
        else:
            d, ok = self._num("pd")
            set_bad(f["pd"], not ok or d <= 0)
        ring, rok = self._num("ring", True)
        set_bad(f["ring"], not rok)
        pl, plok = self._num("pl", True)
        set_bad(f["pl"], not plok)
        pr = core.pure(self.price, vat, pg, ring, pl, unit) if (self.has_price and vok and pgok and rok and plok) else None
        for key, rk in (("p1x", "x1"), ("p1i", "i1"), ("p2x", "x2"), ("p2i", "i2")):
            self.o_p[key].setText(won(pr[rk]) if pr else "-")

    def _build_k_table(self):
        grid = self.k_grid
        heads = ["금종류", "금 원가 · 부가세 별도", "공임 포함 원가 · 부가세 포함", "최종 판매가 · 부가세 포함"]
        for c, h in enumerate(heads):
            lb = lab(h, "th")
            lb.setAlignment(Qt.AlignLeft if c == 0 else Qt.AlignRight)
            grid.addWidget(lb, 0, c)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"color:{C['line']}")
        grid.addWidget(sep, 1, 0, 1, 4)
        self.k_empty = lab("위 체크박스에서 표시할 캐럿을 선택하세요.", "note")
        self.k_empty.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.k_empty, 2, 0, 1, 4)
        self.k_rows = {}
        r = 3
        for k in KARAT_KEYS:
            w = {"k": lab(k + "K", "k"), "g": lab("-", "cell"), "c": lab("-", "cell"), "f": lab("-", "fin"), "s": lab("", "sub")}
            for key in ("g", "c", "f"):
                w[key].setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                w[key].setTextInteractionFlags(Qt.TextSelectableByMouse)
            w["s"].setAlignment(Qt.AlignRight)
            grid.addWidget(w["k"], r, 0)
            grid.addWidget(w["g"], r, 1)
            grid.addWidget(w["c"], r, 2)
            grid.addWidget(w["f"], r, 3)
            grid.addWidget(w["s"], r + 1, 0, 1, 4)
            self.k_rows[k] = w
            r += 2
        for c, st in enumerate((1, 2, 2, 2)):
            grid.setColumnStretch(c, st)

    def _render_k(self, rows, kc, kx):
        shown = {k: res for k, res in rows}
        self.k_empty.setVisible(not rows)
        for k, w in self.k_rows.items():
            on = k in shown
            for x in w.values():
                x.setVisible(on)
            if not on:
                continue
            res = shown[k]
            w["k"].setText(k + "K" + (f"  {kc}" if kc and res else ""))
            if res:
                w["g"].setText(won(res["gold"]))
                w["c"].setText(won(res["cost_incl"]))
                w["f"].setText(won(res["final"] + kx))
                sub = f"화이트 +{commas(kx)} 포함" if kx else ""
            else:
                w["g"].setText("-")
                w["c"].setText("-")
                w["f"].setText("입력 확인" if self.has_price else "-")
                sub = "노란 칸 중 빨간 칸을 확인하세요" if self.has_price else "시세를 먼저 입력하세요"
            w["s"].setText(sub)
            w["s"].setVisible(bool(sub))

    def _on_field(self, key):
        if self.loading:
            return
        self._sync_weight(key)
        self.recompute()
        self.save_timer.start()

    # g ↔ 돈: 다른 칸에는 소수 2자리로 보여주고, 계산은 입력한 원래 값으로
    def _sync_weight(self, which):
        f = self.f
        if which == "ad":
            d, ok = self._num("ad")
            if ok and d > 0:
                self.ag_exact = d * GPD
                f["ag"].setText(fixed2(self.ag_exact))
            else:
                self.ag_exact = None
        elif which == "ag":
            self.ag_exact = None
            g, ok = self._num("ag")
            f["ad"].setText(fixed2(g / GPD) if ok and g > 0 else "")
        elif which == "pd":
            d, ok = self._num("pd")
            if ok and d > 0:
                self.pg_exact = d * GPD
                f["pg"].setText(fixed2(self.pg_exact))
            else:
                self.pg_exact = None
        elif which == "pg":
            self.pg_exact = None
            g, ok = self._num("pg")
            f["pd"].setText(fixed2(g / GPD) if ok and g > 0 else "")

    # ------------------------------------------------------------ 시세
    def _set_auto_timer(self):
        if self.auto.isChecked():
            self.auto_timer.start()
        else:
            self.auto_timer.stop()

    def _on_auto(self, on):
        if self.loading:
            return
        self._set_auto_timer()
        self.save_timer.start()
        if on:
            self.start_fetch()

    def start_fetch(self):
        if self.fetching:
            return
        self.fetching = True
        self.b_refresh.setEnabled(False)
        self.set_status("한국금거래소 ‘내가 살 때’ 시세 조회 중…")
        self.thread = QThread(self)
        self.worker = Fetcher()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self._fetched)
        self.worker.done.connect(self.thread.quit)
        self.thread.finished.connect(self.worker.deleteLater)
        self.thread.start()

    def _fetched(self, q, err):
        self.fetching = False
        self.b_refresh.setEnabled(True)
        if q is None:
            tail = ("이전 시세 유지, 최신 아님 (" + self.price_time + ")") if self.has_price else "수동 시세를 입력하세요"
            self.set_status("조회 실패 (" + err + ") · " + tail, True)
            return
        self.price, self.has_price, self.price_time, self.source = q["buy"], True, now_sec(), "api"
        self.i_price.setText(commas(self.price))
        self.set_status("API 조회 완료 / 조회 시각 " + self.price_time + (" / 제공일 " + q["date"] if q["date"] else " / 제공일 정보 없음"))
        self.save_settings()
        self.recompute()

    def apply_manual(self):
        v, ok = parse_num(self.i_price.text())
        if not ok or v <= 0 or v > 1e12:
            self.info("입력 확인", "0보다 큰 시세를 숫자로 입력하세요.")
            self.i_price.setFocus()
            return
        self.price, self.has_price, self.price_time, self.source = v, True, now_sec(), "manual"
        self.i_price.setText(commas(v))
        self.set_status("수동 입력 시세 적용 / " + self.price_time)
        self.save_settings()
        self.recompute()

    def reset_defaults(self):
        if not self.yes_no("기본값", "기준값·중량·공임·마진을 기본값으로 되돌릴까요?\n(시세와 상품 목록은 그대로 둡니다)"):
            return
        self.loading = True
        for k, w in self.f.items():
            if k not in ("ad", "pd"):
                w.setText(core.DEFAULTS[k])
        self.ag_exact = self.pg_exact = None
        self.f["ad"].setText(fixed2(3.75 / GPD))
        self.f["pd"].setText(fixed2(3.75 / GPD))
        for k in KARAT_KEYS:
            self.showk[k].setChecked(True)
        self.unit.setCurrentIndex(0)
        self.loading = False
        self.recompute()
        self.save_settings()

    # ------------------------------------------------------------ 상품 저장·불러오기·삭제
    def _sec(self, kind):
        if kind == "k":
            return self.k_prod, "ag", "al", ["dia", "set"]
        return self.p_prod, "pg", "pl", ["ring"]

    def apply_product(self, kind, p):
        row, wkey, lkey, extra = self._sec(kind)
        row.fill(p)
        self.f[wkey].setText(p.get("weight", ""))
        self.f[lkey].setText(p.get("labor", ""))
        for x in extra:
            self.f[x].setText(p.get(x, ""))
        self._sync_weight(wkey)
        self.recompute()
        self.save_timer.start()
        self.f[wkey].setFocus()
        self.flash(f"'{p['code']}' 불러옴")

    def save_product(self, kind):
        row, wkey, lkey, extra = self._sec(kind)
        code = core.clean(row.code.text())
        if not code:
            self.info("상품 저장", "저장하려면 코드 칸에 상품코드를 입력하세요.")
            row.code.setFocus()
            return
        g, ok = parse_num(self.f[wkey].text())
        if not ok or g <= 0:
            self.info("입력 확인", "중량을 0보다 큰 숫자로 입력한 뒤 저장하세요.")
            return
        np = {"kind": kind, "code": code, "name": row.name.text(), "maker": row.maker.text(),
              "weight": self.f[wkey].text(), "labor": self.f[lkey].text(), "ring": "", "dia": "", "set": ""}
        for x in extra:
            np[x] = self.f[x].text()
        if row.cat.currentData():
            np["cat"] = row.cat.currentData()
        np = core.make_product(np)
        self.products = self.store.products()  # 저장 직전에 다시 읽음
        if any(p["kind"] == kind and p["code"] == code for p in self.products) and \
                not self.yes_no("상품 저장", f"상품코드 '{code}'가 이미 있습니다.\n현재 값으로 바꿀까요?"):
            return
        try:
            self.products = self.store.upsert_product(np)
        except OSError as e:
            self.info("상품 저장", "상품 목록을 저장하지 못했습니다.\n" + str(e))
            return
        self.set_status_temp(f"상품코드 '{code}' 저장됨")
        self.flash(f"'{code}' 저장됨")

    def delete_product(self, kind):
        row = self._sec(kind)[0]
        code = core.clean(row.code.text())
        if not code:
            self.info("상품 삭제", "삭제할 상품을 검색해서 불러오거나 상품코드를 입력하세요.")
            return
        self.products = self.store.products()
        if not any(p["kind"] == kind and p["code"] == code for p in self.products):
            self.info("상품 삭제", f"상품코드 '{code}'인 저장된 상품이 없습니다.")
            return
        if not self.yes_no("상품 삭제", f"상품코드 '{code}' 상품을 목록에서 삭제할까요?"):
            return
        try:
            self.products = self.store.remove_product(kind, code)
        except OSError as e:
            self.info("상품 삭제", "상품 목록을 저장하지 못했습니다.\n" + str(e))
            return
        row.code.setText("")
        row.name.setText("")
        row.maker.setText("")
        row.cat.setCurrentIndex(0)
        self.save_timer.start()
        self.set_status_temp(f"상품코드 '{code}' 삭제됨")
        self.flash(f"'{code}' 삭제됨")

    def set_status_temp(self, note_text):
        b = self.o_status.text()
        i = b.find("   ·   ")
        if i >= 0:
            b = b[:i]
        self.set_status(b + "   ·   " + note_text, bool(self.o_status.property("bad")))

    def clear_section(self, kind):
        row, wkey, lkey, extra = self._sec(kind)
        row.clear()
        if kind == "k":
            self.ag_exact = None
            for k in ("ag", "ad", "al", "dia", "set"):
                self.f[k].setText("")
            self.k_color.setCurrentIndex(0)
        else:
            self.pg_exact = None
            for k in ("pg", "pd", "ring", "pl"):
                self.f[k].setText("")
        self.f[wkey].setFocus()
        self.recompute()
        self.save_timer.start()

    # ------------------------------------------------------------ 자료 메뉴
    def export_products(self):
        self.products = self.store.products()
        if not self.products:
            self.info("상품 내보내기", "저장된 상품이 없습니다.\n상품코드를 입력하고 저장한 뒤 내보내세요.")
            return
        name = "상품목록_" + time.strftime("%Y%m%d") + ".tsv"
        path, _ = QFileDialog.getSaveFileName(self, "상품 내보내기", os.path.join(os.path.expanduser("~"), name), "상품 목록 (*.tsv);;모든 파일 (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(core.products_tsv(self.products))
        except OSError as e:
            self.info("상품 내보내기", "파일을 저장하지 못했습니다.\n" + str(e))
            return
        k = sum(p["kind"] == "k" for p in self.products)
        self.info("상품 내보내기", f"상품 {len(self.products)}개 (10K·14K·18K {k}개, 순금 {len(self.products) - k}개)를 저장했습니다.\n"
                  "다른 PC나 매장관리 웹, 예전 상품가격계산기에서 가져올 수 있습니다.")

    def import_products(self):
        path, _ = QFileDialog.getOpenFileName(self, "상품 가져오기", os.path.expanduser("~"),
                                              "상품 목록·백업 (*.tsv *.txt *.json *.csv);;모든 파일 (*)")
        if not path:
            return
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("cp949", "replace")
        except OSError as e:
            self.info("상품 가져오기", "파일을 열지 못했습니다.\n" + str(e))
            return
        incoming = core.products_from_any(text)
        if not incoming:
            self.info("상품 가져오기", "이 파일에서 가져올 상품을 찾지 못했습니다.\n"
                      "'상품 내보내기'로 만든 파일이나 매장관리 웹 전체 백업 파일인지 확인하세요.")
            return
        cur = self.store.products()
        replace = False
        if cur:
            b = QMessageBox(QMessageBox.Question, "상품 가져오기",
                            f"파일에서 상품 {len(incoming)}개를 찾았습니다. 지금 목록에는 {len(cur)}개가 있습니다.\n\n"
                            "합치기: 같은 상품코드는 파일 값으로 바꿉니다.\n바꾸기: 지금 목록을 지우고 파일 목록으로 바꿉니다.\n\n"
                            "어느 쪽이든 '자료 → 마지막 가져오기 되돌리기'로 되돌릴 수 있습니다.", parent=self)
            mb = b.addButton("합치기", QMessageBox.AcceptRole)
            rb = b.addButton("바꾸기", QMessageBox.DestructiveRole)
            b.addButton("취소", QMessageBox.RejectRole)
            b.exec()
            if b.clickedButton() not in (mb, rb):
                return
            replace = b.clickedButton() is rb
            try:
                self.store.backup("가져오기")
            except OSError as e:
                self.info("상품 가져오기", "가져오기 전 백업을 만들지 못해 멈췄습니다.\n" + str(e))
                return
        lst = [] if replace else list(cur)
        added = changed = 0
        for np in incoming:
            for i, p in enumerate(lst):
                if p["kind"] == np["kind"] and p["code"] == np["code"]:
                    lst[i] = np
                    changed += 1
                    break
            else:
                lst.append(np)
                added += 1
        try:
            self.store.save_products(lst)
        except OSError as e:
            self.info("상품 가져오기", "상품 목록을 저장하지 못했습니다.\n" + str(e))
            return
        self.products = lst
        self.info("상품 가져오기", f"목록을 파일 내용으로 바꿨습니다.\n전체 {len(lst)}개" if replace
                  else f"가져오기를 마쳤습니다.\n새로 추가 {added}개, 바뀜 {changed}개, 전체 {len(lst)}개")

    def undo_import(self):
        last = self.store.last_backup()
        if not last:
            self.info("되돌리기", "되돌릴 가져오기가 없습니다.")
            return
        path, d = last
        if not self.yes_no("되돌리기", f"{d.get('at', '')} 가져오기 전 상태로 되돌릴까요?\n(상품 {len(d['products'])}개)"):
            return
        try:
            self.store.restore_backup(path, d)
        except OSError as e:
            self.info("되돌리기", str(e))
            return
        self.products = self.store.products()
        self.flash("되돌렸습니다")

    def about(self):
        self.info("프로그램 정보", f"{APP_NAME} 버전 {__version__}\n\n매장관리 웹과 같은 계산 방식을 쓰는 PC 전용 프로그램입니다.\n"
                  f"자료는 이 PC에만 저장됩니다:\n{self.store.root}")

    def set_zoom(self, d):
        i = ZOOMS.index(self.zoom) if self.zoom in ZOOMS else 1
        i = max(0, min(len(ZOOMS) - 1, i + d))
        self.zoom = ZOOMS[i]
        QApplication.instance().setStyleSheet(stylesheet(self.zoom))
        self.settings_card.setFixedWidth(round(250 * self.zoom))
        self.flash(f"글자 크기 {round(self.zoom * 100)}%")
        self.save_timer.start()
