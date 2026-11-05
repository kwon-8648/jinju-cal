"""고금 매입 탭 — 고금시세계산 v1.16 의 app.py 를 그대로 옮겨 온 화면.

달라진 점 (기능은 그대로):
- 창(QMainWindow) 대신 상품가격계산기 안의 탭(QWidget). 따로 띄우면 예전처럼 창으로도 동작.
- 19품목 표를 [금] [은] 탭으로 나눔 (저해상도 화면에서 스크롤 없이 보이게). 비교·설정 창의 표도 같음.
- 버전 표시는 상품가격계산기 맨 아래에 (원래의 v1.16 표시 대신).
- 색·글자·계산·저장·자동 갱신·수동 확인 시간은 원본과 같음.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import time
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from PySide6.QtCore import QObject, QRegularExpression, Qt, QTimer, Signal, QStandardPaths
from PySide6.QtGui import QFont, QFontDatabase, QFontMetrics, QIcon, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMessageBox, QPushButton, QSpinBox, QStyle, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QFileDialog,
)
from .excel_export import DEFAULT_COLUMNS, normalize_columns, export_purchase, grams_to_don

from .core import (
    METAL_DISPLAY, RATE_ITEMS, append_purchase_record, calculate_row,
    calculate_unit_price, fetch_koreagoldx_prices, load_state, log,
    parse_decimal, row_key, save_state,
)

METALS = ("GOLD", "SILVER", "PLATINUM")
ALIGN = Qt.AlignmentFlag.AlignCenter
FAMILY = "Malgun Gothic"
AUTO_REFRESH_MS = 30 * 60 * 1000
MANUAL_MINUTES_DEFAULT, MANUAL_MINUTES_MIN, MANUAL_MINUTES_MAX = 30, 1, 240
IS_MAC = sys.platform == "darwin"
# Windows renders 1pt = 96/72 px; macOS renders 1pt = 1px (72 dpi). To keep every
# label exactly the size it was on Windows, point sizes are scaled on macOS.
POINT_SCALE = 1.0
FONT_CANDIDATES = ("Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "AppleSDGothicNeo",
                   "Noto Sans KR", "Noto Sans CJK KR", "AppleGothic")


def pt(points):
    """Actual Qt point size used for a Windows-equivalent point size."""
    return points * POINT_SCALE


def text_font(points=10, bold=False):
    font = QFont(FAMILY)
    font.setPointSizeF(pt(points))
    font.setWeight(QFont.Weight.Bold if bold else QFont.Weight.Normal)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def detect_point_scale(app):
    override = os.environ.get("GOLDMETAL_POINT_SCALE")
    if override:
        try:
            value = float(override)
            if 0.5 <= value <= 3:
                return value
        except ValueError:
            pass
    if not IS_MAC:
        return 1.0
    screen = app.primaryScreen()
    dpi = screen.logicalDotsPerInchY() if screen is not None else 72.0
    return 96.0 / dpi if dpi and dpi > 0 else 96.0 / 72.0


GOLD_COUNT = sum(1 for item in RATE_ITEMS if item.metal_type == "GOLD")  # 금 12품목, 은 7품목
_FONTS_READY = False


def init_fonts(app=None):
    """원본 make_application 의 글꼴 부분: 맑은 고딕(맥은 Apple SD Gothic Neo), 맥은 윈도우와 같은 크기로 보정."""
    global FAMILY, POINT_SCALE, _FONTS_READY
    if _FONTS_READY:
        return
    app = app or QApplication.instance()
    POINT_SCALE = detect_point_scale(app)
    families = set(QFontDatabase.families())
    FAMILY = next((name for name in FONT_CANDIDATES if name in families), app.font().family())
    _FONTS_READY = True


# 원본 색 그대로. 상품가격 탭의 스타일이 섞여 들지 않게 원본이 정하지 않던 값도 원래 기본값으로 되돌림.
STYLE = """
    QWidget { color: #172635; }
    GoldPanel, QDialog { background: #f3f5f8; }
    QFrame#card { background: white; border: 1px solid #cbd3dc; border-radius: 4px; }
    QPushButton { background: white; color: #172635; border: 1px solid #b7c2cd; border-radius: 3px; padding: 3px 10px; font-weight: normal; min-height: 0px; }
    QPushButton:hover { background: #e8eff7; }
    QPushButton:disabled { color: #7a8794; background: #e7ebef; border-color: #b7c2cd; }
    QPushButton#primary { background: #167344; color: white; border-color: #167344; }
    QPushButton#accent { background: #2262a3; color: white; border-color: #2262a3; }
    QLineEdit { background: white; color: #14202d; border: 1px solid #aebac7; border-radius: 2px; padding: 0px 3px; min-height: 0px; selection-background-color: #2262a3; selection-color: white; }
    QLineEdit:focus { border: 1px solid #2262a3; background: #f2f7ff; padding: 0px 3px; }
    QTableWidget { background: white; alternate-background-color: #eef3f8; gridline-color: #c7d0da; border: 1px solid #b2bfcc; }
    QHeaderView::section { background: #dfe7f0; color: #162d46; border: none; border-right: 1px solid #b2bfcc; border-bottom: 1px solid #b2bfcc; padding: 2px; }
    QComboBox { background: white; border: 1px solid #aebac7; border-radius: 0px; padding: 2px 5px; min-width: 56px; min-height: 0px; }
    QComboBox QAbstractItemView { background: white; selection-background-color: #e8eff7; selection-color: #172635; }
    QTabWidget::pane { border: 1px solid #b2bfcc; top: -1px; background: white; }
    QTabBar::tab { background: #dfe7f0; color: #162d46; border: 1px solid #b2bfcc; border-bottom: none; padding: 3px 16px; margin-right: 2px; border-top-left-radius: 3px; border-top-right-radius: 3px; }
    QTabBar::tab:selected { background: white; font-weight: bold; }
    QTabBar::tab:!selected:hover { background: #e8eff7; }
"""


def button(text, callback, kind=""):
    result = QPushButton(text)
    result.setObjectName(kind)
    # Clicking a button must take focus (as on Windows) so a price being typed
    # is committed first; macOS otherwise lets buttons skip focus.
    result.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    result.clicked.connect(callback)
    return result


def build_korean_question(parent, title, text):
    """'네' / '아니요' 순서가 항상 고정된 확인창. Enter = 네, Esc·창 닫기 = 아니요."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setModal(True)
    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(16, 14, 16, 12)
    layout.setSpacing(12)
    body = QHBoxLayout()
    body.setSpacing(12)
    icon = QLabel()
    icon.setPixmap(dialog.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion).pixmap(32, 32))
    icon.setAlignment(Qt.AlignmentFlag.AlignTop)
    body.addWidget(icon)
    message = QLabel(text)
    message.setWordWrap(False)
    body.addWidget(message, 1)
    layout.addLayout(body)
    buttons = QHBoxLayout()
    buttons.addStretch(1)
    yes = QPushButton("네")
    no = QPushButton("아니요")
    for item in (yes, no):
        item.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        item.setMinimumWidth(80)
        buttons.addWidget(item)
    yes.setDefault(True)
    yes.clicked.connect(dialog.accept)
    no.clicked.connect(dialog.reject)
    layout.addLayout(buttons)
    yes.setFocus()
    return dialog, yes, no


def korean_message(parent, title, text, warning=True):
    """경고/안내창: 영어 OK 대신 '확인' 버튼. Enter = 확인."""
    box = QMessageBox(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information,
                      title, text, QMessageBox.StandardButton.NoButton, parent)
    ok = box.addButton("확인", QMessageBox.ButtonRole.AcceptRole)
    box.setDefaultButton(ok)
    box.setEscapeButton(ok)
    box.exec()


def korean_question(parent, title, text):
    dialog, yes, _no = build_korean_question(parent, title, text)
    yes.setFocus()
    accepted = dialog.exec() == QDialog.DialogCode.Accepted
    return QMessageBox.StandardButton.Yes if accepted else QMessageBox.StandardButton.No


def readonly_item(text, left=False):
    item = QTableWidgetItem(str(text))
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft if left else ALIGN)
    return item


def setup_table(table, headers):
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setAlternatingRowColors(True)
    table.setWordWrap(False)
    table.setTextElideMode(Qt.TextElideMode.ElideNone)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.horizontalHeader().setFont(text_font(10, True))
    table.horizontalHeader().setFixedHeight(max(22, QFontMetrics(text_font(10, True)).height() + 4))
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
    table.horizontalHeader().setMinimumSectionSize(36)
    table.verticalHeader().setMinimumSectionSize(20)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)


class FittedTable(QTableWidget):
    """Fit rows to the available area without changing text or font size."""
    def __init__(self, weights, parent=None, rows=None):
        super().__init__(len(RATE_ITEMS) if rows is None else rows, len(weights), parent)
        self.weights = weights
        self.row_minimum = 20

    def fit(self):
        if self.viewport().width() < 50:
            return
        available = self.viewport().width()
        boundaries = [round(available * sum(self.weights[:i]) / sum(self.weights))
                      for i in range(len(self.weights) + 1)]
        for column in range(len(self.weights)):
            self.setColumnWidth(column, boundaries[column + 1] - boundaries[column])
        height = max(self.row_minimum * self.rowCount(), self.viewport().height())
        for row in range(self.rowCount()):
            self.setRowHeight(row, round(height * (row + 1) / self.rowCount()) - round(height * row / self.rowCount()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def set_readable_font(self, points):
        font = text_font(points)
        self.setFont(font)
        self.row_minimum = max(20, QFontMetrics(font).height() + 4)
        self.setMinimumHeight(self.row_minimum * self.rowCount() + self.horizontalHeader().height() + 2)
        for row in range(self.rowCount()):
            for col in range(self.columnCount()):
                widget = self.cellWidget(row, col)
                if widget is not None:
                    widget.setFont(font)
        self.fit()


class SplitTable:
    """19품목 표를 [금] [은] 두 탭의 표로 나누어 보여주되, 코드에서는 예전처럼 한 표(줄 0~18)로 다룸."""
    def __init__(self, weights, headers, tab_titles=("금", "은")):
        self.gold = FittedTable(weights, rows=GOLD_COUNT)
        self.silver = FittedTable(weights, rows=len(RATE_ITEMS) - GOLD_COUNT)
        self.tables = (self.gold, self.silver)
        for table in self.tables:
            setup_table(table, headers)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tab_titles = tab_titles
        self.tabs.addTab(self.gold, tab_titles[0])
        self.tabs.addTab(self.silver, tab_titles[1])

    def locate(self, row):
        return (self.gold, row) if row < GOLD_COUNT else (self.silver, row - GOLD_COUNT)

    def item(self, row, col):
        table, r = self.locate(row)
        return table.item(r, col)

    def setItem(self, row, col, item):
        table, r = self.locate(row)
        table.setItem(r, col, item)

    def cellWidget(self, row, col):
        table, r = self.locate(row)
        return table.cellWidget(r, col)

    def setCellWidget(self, row, col, widget):
        table, r = self.locate(row)
        table.setCellWidget(r, col, widget)

    def rowCount(self):
        return len(RATE_ITEMS)

    def columnCount(self):
        return self.gold.columnCount()

    def set_readable_font(self, points):
        for table in self.tables:
            table.set_readable_font(points)

    def fit(self):
        for table in self.tables:
            table.fit()

    def font(self):
        return self.gold.font()

    def setFocus(self):
        self.tabs.currentWidget().setFocus()

    def show_row(self, row):
        """그 줄이 있는 탭으로."""
        self.tabs.setCurrentIndex(0 if row < GOLD_COUNT else 1)

    def set_tab_totals(self, gold_total, silver_total):
        self.tabs.setTabText(0, f"{self.tab_titles[0]}  ·  {gold_total:,}")
        self.tabs.setTabText(1, f"{self.tab_titles[1]}  ·  {silver_total:,}")


class PriceEdit(QLineEdit):
    committed = Signal()
    cancelled = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.committed.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.committed.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class FetchSignals(QObject):
    success = Signal(object, object, int)
    failure = Signal(str, bool, int)


class GoldPanel(QWidget):
    def __init__(self, parent=None, auto_fetch=True):
        super().__init__(parent)
        init_fonts()
        self.setObjectName("GoldPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(STYLE)
        self.setFont(text_font())
        self.setWindowTitle("고금시세계산")
        self.state_data = load_state()
        self.refresh_mode = self.state_data.get("refresh_mode", "auto")
        self.manual_due = self.state_data.get("manual_due")
        try:
            minutes = int(self.state_data.get("manual_check_minutes", MANUAL_MINUTES_DEFAULT))
        except (TypeError, ValueError):
            minutes = MANUAL_MINUTES_DEFAULT
        self.manual_minutes = min(MANUAL_MINUTES_MAX, max(MANUAL_MINUTES_MIN, minutes))
        self.pending_auto_fetch = False
        self.export_columns = normalize_columns(self.state_data.get("export_columns"))
        default_folder = str(Path(
            QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or str(Path.home())) / "고금시세계산")
        saved_folder = self.state_data.get("export_folder")
        # A settings file copied from Windows holds a Windows path (C:\Users\...); it is
        # not a valid folder on macOS, so fall back to ~/Documents/고금시세계산.
        if not saved_folder or not Path(str(saved_folder)).expanduser().is_absolute() or (
                IS_MAC and re.match(r"^[A-Za-z]:[\\/]", str(saved_folder))):
            saved_folder = default_folder
        self.export_folder = saved_folder
        self.prices = {m: int(parse_decimal(self.state_data.get("prices", {}).get(m, 0))) for m in METALS}
        self.price_source = self.state_data.get("price_source") or "미조회"
        self.updated_at = self.state_data.get("price_updated_at")
        self.keys = [row_key(i, item) for i, item in enumerate(RATE_ITEMS)]
        self.names = {}
        self.multipliers = {}
        self.comparison_multipliers = {}
        for key, item in zip(self.keys, RATE_ITEMS):
            name = (self.state_data.get("item_names") or {}).get(key, item.item_name)
            self.names[key] = name.strip() if isinstance(name, str) and name.strip() else item.item_name
            value = parse_decimal((self.state_data.get("multipliers") or {}).get(key), item.multiplier)
            self.multipliers[key] = value if value.is_finite() and 0 <= value <= 10 else item.multiplier
            comparison = parse_decimal((self.state_data.get("comparison_multipliers") or {}).get(key), self.multipliers[key])
            self.comparison_multipliers[key] = comparison if comparison.is_finite() and 0 <= comparison <= 10 else self.multipliers[key]
        self.fetching = False
        self.price_revision = 0
        self.signals = FetchSignals(self)
        self.signals.success.connect(self.apply_fetched_prices)
        self.signals.failure.connect(self.fetch_failed)
        self._build_ui()
        self.calculate_all()
        self.refresh_cards()
        if self.isWindow():  # 따로 띄울 때만 (탭 안에서는 상품가격계산기 창 크기를 따름)
            screen = QApplication.primaryScreen().availableGeometry()
            geometry = re.match(r"(\d+)x(\d+)", str(self.state_data.get("window_geometry", "")))
            width, height = (int(geometry[1]), int(geometry[2])) if geometry else (1280, 760)
            self.resize(max(1060, min(width, screen.width() - 24)),
                        max(self.minimumHeight(), min(height, screen.height() - 40)))
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(AUTO_REFRESH_MS)
        self.refresh_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.refresh_timer.timeout.connect(self.auto_tick)
        self.manual_timer = QTimer(self)
        self.manual_timer.setSingleShot(True)
        self.manual_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.manual_timer.timeout.connect(self.ask_manual_refresh)
        if auto_fetch:
            if self.refresh_mode == "manual":
                remaining = max(1, int((float(self.manual_due or time.time()) - time.time()) * 1000))
                self.manual_timer.start(min(remaining, self.manual_interval_ms()))
            else:
                self.refresh_timer.start()
                QTimer.singleShot(200, self.auto_tick)
        self.update_mode_label()

    def manual_interval_ms(self):
        return self.manual_minutes * 60 * 1000

    def update_mode_label(self):
        if self.refresh_mode == "manual":
            due = ""
            try:
                due = datetime.fromtimestamp(float(self.manual_due)).strftime(" (%H:%M)")
            except (TypeError, ValueError, OverflowError, OSError):
                pass
            mode = f"수동 시세 유지 · {self.manual_minutes}분 후 갱신 확인{due}"
        else:
            mode = "30분마다 자동 갱신"
        self.mode_label.setText("내가 팔 때 · 3.75g 기준 | " + mode)

    def change_manual_minutes(self, minutes):
        """수동 입력 후 갱신 확인 시간 변경. 수동 모드 중이면 입력 시점 기준으로 다시 계산."""
        minutes = min(MANUAL_MINUTES_MAX, max(MANUAL_MINUTES_MIN, int(minutes)))
        old = self.manual_minutes
        if minutes == old:
            return
        self.manual_minutes = minutes
        if self.refresh_mode == "manual" and hasattr(self, "manual_timer"):
            start = float(self.manual_due or time.time()) - old * 60
            self.manual_due = start + minutes * 60
            remaining = max(1000, int((self.manual_due - time.time()) * 1000))
            self.manual_timer.start(remaining)
        self.update_mode_label()
        try:
            self.persist_state()
        except Exception as error:
            korean_message(self, "설정 저장 실패", str(error))

    def auto_tick(self):
        if self.refresh_mode == "auto" and not any(e.hasFocus() or e.isModified() for e in self.price_labels.values()):
            self.fetch_prices(False)

    def postpone_manual(self):
        self.manual_due = time.time() + self.manual_minutes * 60
        self.manual_timer.start(self.manual_interval_ms())
        self.persist_state()

    def enter_manual_mode(self):
        self.refresh_mode = "manual"
        self.pending_auto_fetch = False
        self.refresh_timer.stop()
        self.postpone_manual()
        self.update_mode_label()

    def ask_manual_refresh(self):
        if self.refresh_mode != "manual":
            return
        if QApplication.activeModalWidget() is not None or any(e.isModified() for e in self.price_labels.values()):
            self.manual_timer.start(1000)
            return
        answer = korean_question(self, "시세 자동 갱신", f"수동 시세 입력 후 {self.manual_minutes}분이 지났습니다.\n지금 시세를 갱신하고 30분 자동 갱신을 재개할까요?\n아니요: 현재 시세를 유지하고 {self.manual_minutes}분 후 다시 확인합니다.")
        if answer == QMessageBox.StandardButton.Yes:
            self.resume_auto()
        else:
            self.postpone_manual()
            self.update_mode_label()

    def resume_auto(self):
        self.refresh_mode = "auto"
        self.manual_due = None
        self.manual_timer.stop()
        self.refresh_timer.start(AUTO_REFRESH_MS)
        self.update_mode_label()
        self.persist_state()
        if self.fetching:
            self.pending_auto_fetch = True
        else:
            self.fetch_prices(True)

    def finish_pending_fetch(self):
        if self.pending_auto_fetch and self.refresh_mode == "auto":
            self.pending_auto_fetch = False
            self.fetch_prices(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 4)
        layout.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(6)
        self.price_labels, self.date_labels = {}, {}
        for metal in METALS:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 2, 6, 2)
            card_layout.setSpacing(0)
            title = QLabel(METAL_DISPLAY[metal])
            title.setFont(text_font(10, True))
            value = PriceEdit("0")
            value.setFont(text_font(18, True))
            value.setMaxLength(16)
            value.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9,]*"), value))
            value.setToolTip("시세를 직접 입력한 뒤 Enter 또는 다른 칸 클릭 · Esc 취소")
            value.setMinimumHeight(QFontMetrics(value.font()).height() + 4)
            value.committed.connect(lambda m=metal: self.commit_price(m))
            value.cancelled.connect(lambda m=metal: self.cancel_price(m))
            value.textEdited.connect(self.price_edit_started)
            date = QLabel("적용일 -")
            date.setFont(text_font(9))
            for label in (title, value, date):
                label.setAlignment(ALIGN)
                card_layout.addWidget(label)
            top.addWidget(card, 1)
            self.price_labels[metal], self.date_labels[metal] = value, date
        actions = QGridLayout()
        actions.setSpacing(2)
        self.status = QLabel("시세 확인 전")
        self.status.setFont(text_font(9))
        self.status.setAlignment(ALIGN)
        self.status.setMinimumWidth(0)
        self.status.setMaximumWidth(330)
        actions.addWidget(self.status, 0, 0, 1, 2)
        self.fetch_button = button("시세 불러오기 / 자동 갱신 재개", self.resume_auto, "primary")
        actions.addWidget(self.fetch_button, 1, 0, 1, 2)
        actions.addWidget(button("중량 초기화", self.reset_weights), 2, 0, 1, 2)
        top.addLayout(actions)
        layout.addLayout(top)
        summary = QHBoxLayout()
        summary.setSpacing(6)
        note = self.mode_label = QLabel()
        note.setFont(text_font(9))
        summary.addWidget(note, 1)
        manual_title = QLabel("수동 입력 후 확인")
        manual_title.setFont(text_font(9))
        summary.addWidget(manual_title)
        self.manual_spin = QSpinBox()
        self.manual_spin.setRange(MANUAL_MINUTES_MIN, MANUAL_MINUTES_MAX)
        self.manual_spin.setSuffix(" 분")
        self.manual_spin.setAlignment(ALIGN)
        self.manual_spin.setKeyboardTracking(False)   # 숫자 입력 후 Enter/다른 칸 클릭 시 적용
        self.manual_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.manual_spin.setToolTip("시세를 직접 입력한 뒤 몇 분 후에 자동 갱신 여부를 물을지 정합니다 (1~240분)")
        self.manual_spin.setValue(self.manual_minutes)
        self.manual_spin.valueChanged.connect(self.change_manual_minutes)
        summary.addWidget(self.manual_spin)
        summary.addSpacing(8)
        summary.addWidget(QLabel("최종합계"))
        self.total_label = QLabel("0")
        self.total_label.setFont(text_font(18, True))
        self.total_label.setStyleSheet("color: #175591;")
        summary.addWidget(self.total_label)
        summary.addWidget(button("계산 / 조회", self.calculate_all, "accent"))
        summary.addWidget(button("저장", self.save_purchase, "primary"))
        layout.addLayout(summary)

        self.table = SplitTable((40, 11, 9, 7, 9, 11, 13), ("기준품목", "단가(g)", "입고중량(g)", "환산(돈)", "차감중량(g)", "차감금액", "고객매입가"),
                                ("금 12품목", "은 7품목"))
        self.weights = []
        self.dons = []
        stored = self.state_data.get("weights") or {}
        for i, (key, item) in enumerate(zip(self.keys, RATE_ITEMS)):
            for col, value in ((0, self.names[key]), (1, "0"), (3, "0.00"), (5, "0"), (6, "0")):
                self.table.setItem(i, col, readonly_item(value, col == 0))
            pair = []
            for col, field in ((2, "input_weight"), (4, "deduction_weight")):
                edit = QLineEdit(str(stored.get(key, {}).get(field, "") or ""))
                edit.setAlignment(ALIGN)
                edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9,]*(?:\.[0-9]{0,6})?"), edit))
                edit.textChanged.connect(self.calculate_all)
                self.table.setCellWidget(i, col, edit)
                pair.append(edit)
            self.weights.append(pair)
            # 환산(돈)도 입력 가능 (상품가격 탭처럼): 돈을 넣으면 입고중량(g) = 돈 × 3.75
            don = QLineEdit(f"{grams_to_don(pair[0].text()):.2f}" if pair[0].text() else "")
            don.setPlaceholderText("0.00")
            don.setAlignment(ALIGN)
            don.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9,]*(?:\.[0-9]{0,4})?"), don))
            don.textEdited.connect(lambda _t, row=i: self.don_edited(row))
            pair[0].textChanged.connect(lambda _t, row=i: self.gram_changed(row))
            don.editingFinished.connect(lambda row=i: self.gram_changed(row, force=True))
            self.table.setCellWidget(i, 3, don)
            self.dons.append(don)
        layout.addWidget(self.table.tabs, 1)
        footer = QHBoxLayout()
        footer.setSpacing(4)
        units = QLabel("금 12품목 · 은 7품목 | 중량 g / 금액 원")
        units.setFont(text_font(9))
        footer.addWidget(units)
        footer.addStretch(1)
        footer.addWidget(QLabel("글자 크기"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["10 pt", "11 pt", "12 pt"])
        saved_size = self.state_data.get("ui_font_points", 10)
        self.font_combo.setCurrentIndex({10: 0, 11: 1, 12: 2}.get(saved_size, 0))
        self.font_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.font_combo.currentIndexChanged.connect(self.change_font)
        footer.addWidget(self.font_combo)
        footer.addWidget(button("다른 배율로 비교", lambda: ComparisonDialog(self).exec()))
        footer.addWidget(button("엑셀 저장 설정", lambda: ExportSettingsDialog(self).exec()))
        footer.addWidget(button("⚙ 기준품목 이름 설정", lambda: self.open_settings("names")))
        footer.addWidget(button("⚙ Multiplier 설정", lambda: self.open_settings("multipliers")))
        layout.addLayout(footer)
        self.change_font(persist=False)
        self.table.setFocus()

    def don_edited(self, row):
        """환산(돈)을 직접 입력 → 입고중량(g) 을 돈 × 3.75 로 채움 (계산은 g 기준 그대로)."""
        raw = self.dons[row].text().replace(",", "").strip()
        try:
            grams = (Decimal(raw) * Decimal("3.75")).normalize() if raw and raw != "." else None
        except Exception:
            return
        text = "" if grams is None else format(grams, "f")
        gram_edit = self.weights[row][0]
        if gram_edit.text() != text:
            gram_edit.blockSignals(True)
            gram_edit.setText(text)
            gram_edit.blockSignals(False)
            self.calculate_all()

    def gram_changed(self, row, force=False):
        """입고중량(g) 이 바뀌면 환산(돈) 칸을 맞춤 (돈 칸에 입력 중일 때는 그대로 둠)."""
        don = self.dons[row] if row < len(self.dons) else None
        if don is None or (don.hasFocus() and not force):
            return
        g = self.weights[row][0].text()
        don.setText(f"{grams_to_don(g):.2f}" if g.strip() else "")

    def change_font(self, _index=None, persist=True):
        points = 10 + self.font_combo.currentIndex()
        self.table.set_readable_font(points)
        for row in range(self.table.rowCount()):
            self.table.item(row, 6).setFont(text_font(points, True))
        self.layout().activate()
        self.setMinimumHeight(self.minimumSizeHint().height())
        if persist:
            try:
                self.persist_state()
            except Exception as error:
                korean_message(self, "설정 저장 실패", str(error))

    def calculate_all(self, *_args):
        if len(self.weights) != len(RATE_ITEMS):
            return 0
        self.rows = []
        total = 0
        for index, (key, item) in enumerate(zip(self.keys, RATE_ITEMS)):
            gross, deduct = (edit.text() for edit in self.weights[index])
            unit = calculate_unit_price(self.prices[item.metal_type], item.metal_type, self.multipliers[key])
            deduction, price = calculate_row(unit, gross, deduct)
            self.table.item(index, 1).setText(f"{unit:,}")
            self.table.item(index, 3).setText(f"{grams_to_don(gross):.2f}")
            self.table.item(index, 5).setText(f"{deduction:,}")
            self.table.item(index, 6).setText(f"{price:,}")
            total += price
            self.rows.append(dict(metal_type=item.metal_type, item_name=self.names[key],
                multiplier=str(self.multipliers[key]), unit_price=unit, input_weight=gross,
                deduction_weight=deduct, deduction_price=deduction, customer_price=price))
        self.total_label.setText(f"{total:,}")
        gold = sum(r["customer_price"] for r in self.rows if r["metal_type"] == "GOLD")
        self.table.set_tab_totals(gold, total - gold)
        return total

    def persist_state(self):
        self.state_data.update(prices=self.prices, price_source=self.price_source,
            refresh_mode=self.refresh_mode, manual_due=self.manual_due,
            manual_check_minutes=self.manual_minutes,
            export_columns=self.export_columns, export_folder=self.export_folder,
            comparison_multipliers={k: str(v) for k, v in self.comparison_multipliers.items()},
            price_updated_at=self.updated_at, multipliers={k: str(v) for k, v in self.multipliers.items()},
            item_names=dict(self.names), ui_font_points=10 + self.font_combo.currentIndex(),
            weights={key: dict(input_weight=self.weights[i][0].text(), deduction_weight=self.weights[i][1].text())
                     for i, key in enumerate(self.keys)}, window_geometry=f"{self.width()}x{self.height()}")
        save_state(self.state_data)

    def refresh_cards(self):
        date = "-"
        if self.updated_at:
            try:
                date = datetime.fromisoformat(str(self.updated_at).replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
            except ValueError:
                date = str(self.updated_at)
        for metal in METALS:
            if not self.price_labels[metal].isModified():
                self.price_labels[metal].setText(f"{self.prices[metal]:,}")
            self.date_labels[metal].setText(f"적용일 {date}")
        self.status.setText(self.price_source)

    def fetch_prices(self, show_error=True):
        if self.fetching:
            return
        self.fetching = True
        revision = self.price_revision
        self.fetch_button.setEnabled(False)
        self.status.setText("한국금거래소 시세 조회 중…")
        def worker():
            try:
                prices, details = fetch_koreagoldx_prices(timeout=10)
                self.signals.success.emit(prices, details, revision)
            except Exception as exc:
                try:
                    self.signals.failure.emit(str(exc), show_error, revision)
                except RuntimeError:
                    pass  # The window was closed while the request was running.
        threading.Thread(target=worker, daemon=True).start()

    def apply_fetched_prices(self, prices, details, revision):
        self.fetching = False
        self.fetch_button.setEnabled(True)
        if revision != self.price_revision or any(e.hasFocus() or e.isModified() for e in self.price_labels.values()):
            self.status.setText("직접 입력한 시세 유지")
            self.finish_pending_fetch()
            return
        updated = [metal for metal in METALS if prices.get(metal, 0) > 0]
        for metal in updated:
            self.prices[metal] = int(prices[metal])
        self.price_source = "한국금거래소 내가 팔 때"
        self.updated_at = details.get("fetched_at") or datetime.now().isoformat(timespec="seconds")
        self.refresh_cards()
        self.calculate_all()
        self.persist_state()
        self.status.setText("금·은·백금 시세 갱신 완료" if len(updated) == 3 else "일부 시세 갱신 · 나머지 기존값 유지")
        self.finish_pending_fetch()

    def fetch_failed(self, error, show_error, revision=None):
        self.fetching = False
        self.fetch_button.setEnabled(True)
        if revision is not None and revision != self.price_revision:
            self.finish_pending_fetch()
            return
        self.status.setText("조회 실패 · 기존 시세 유지")
        log(f"GUI fetch failed: {error}")
        if show_error:
            korean_message(self, "시세 조회 실패", f"기존 시세를 유지합니다. 수동 입력도 가능합니다.\n\n{error}")
        self.finish_pending_fetch()

    def price_edit_started(self, *_args):
        # Invalidate an in-flight request before a manual edit is committed.
        self.price_revision += 1

    def cancel_price(self, metal):
        self.price_labels[metal].setText(f"{self.prices[metal]:,}")

    def commit_price(self, metal):
        edit = self.price_labels[metal]
        if not edit.isModified():
            return
        raw = edit.text().replace(",", "").strip()
        if not raw.isdigit():
            self.cancel_price(metal)
            self.status.setText("올바른 시세가 아니어서 기존값을 유지합니다")
            return
        self.prices[metal] = int(raw)
        self.price_revision += 1
        edit.setModified(False)
        self.price_source = "수동 입력"
        self.updated_at = datetime.now().isoformat(timespec="seconds")
        self.refresh_cards()
        self.calculate_all()
        try:
            self.enter_manual_mode()
        except Exception as error:
            korean_message(self, "시세 저장 실패", str(error))

    def open_settings(self, kind):
        dlg = SettingsDialog(self, kind)
        dlg.exec()

    def reset_weights(self):
        if korean_question(self, "중량 초기화", "모든 입고중량과 차감중량을 지울까요?") != QMessageBox.StandardButton.Yes:
            return
        for pair in self.weights:
            for edit in pair:
                edit.clear()
        self.calculate_all()
        self.persist_state()

    def save_purchase(self):
        try:
            total = self.calculate_all()
            self.persist_state()
            path = export_purchase(self.rows, self.prices, self.price_source, total, self.export_folder, self.export_columns)
            korean_message(self, "저장 완료", f"현재 계산 내역을 저장했습니다.\n{path}", warning=False)
        except Exception as error:
            korean_message(self, "저장 실패", str(error))

    def save_on_quit(self):
        """macOS Cmd+Q / Dock 종료에서도 입력값과 설정을 잃지 않도록 한 번 더 저장."""
        try:
            for metal in METALS:
                self.commit_price(metal)
            self.persist_state()
        except Exception as error:
            log(f"State save on quit failed: {error}")

    def closeEvent(self, event):
        for metal in METALS:
            self.commit_price(metal)
        try:
            self.persist_state()
        except Exception as error:
            log(f"State save failed: {error}")
            if korean_question(self, "설정 저장 실패", f"설정을 저장하지 못했습니다. 그래도 종료할까요?\n{error}") != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        self.refresh_timer.stop()
        self.manual_timer.stop()
        event.accept()


class ComparisonDialog(QDialog):
    """Independent snapshot; only comparison multipliers persist on close."""
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("다른 배율로 비교")
        self.base_prices = dict(owner.prices)
        self.base_multipliers = dict(owner.multipliers)
        self.compare_multipliers = dict(owner.comparison_multipliers)
        self.keys = list(owner.keys)
        self.input_weights = [tuple(edit.text() for edit in pair) for pair in owner.weights]
        self.base_amounts = [calculate_row(calculate_unit_price(self.base_prices[item.metal_type],
            item.metal_type, self.base_multipliers[key]), *weights)[1]
            for key, item, weights in zip(self.keys, RATE_ITEMS, self.input_weights)]
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("창을 연 시점의 시세·중량·기존 배율 기준 | 차액 = 비교 − 현재 | 비교 배율은 닫을 때 기억합니다"))
        prices = QHBoxLayout()
        self.price_edits = {}
        for metal, title in (("GOLD", "금 비교 시세"), ("SILVER", "은 비교 시세")):
            prices.addWidget(QLabel(title))
            edit = QLineEdit(f"{self.base_prices[metal]:,}")
            edit.setAlignment(ALIGN)
            edit.setMaxLength(18)
            edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9,]+"), edit))
            prices.addWidget(edit)
            self.price_edits[metal] = edit
        prices.addWidget(button("처음 시세로", self.reset_prices))
        layout.addLayout(prices)
        self.setFont(text_font())
        self.table = SplitTable((32, 9, 9, 10, 14, 14, 12), ("기준품목", "입고(g)", "차감(g)", "비교 배율", "현재 매입금액", "비교 매입금액", "차액"),
                                ("금 12품목", "은 7품목"))
        self.rate_edits = {}
        for i, (key, weights) in enumerate(zip(self.keys, self.input_weights)):
            for col, value in ((0, owner.names[key]), (1, weights[0] or "0"), (2, weights[1] or "0"),
                               (4, f"{self.base_amounts[i]:,}"), (5, "0"), (6, "0")):
                self.table.setItem(i, col, readonly_item(value, col == 0))
            edit = QLineEdit(str(self.compare_multipliers[key]))
            edit.setAlignment(ALIGN)
            edit.setMaxLength(12)
            edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"[0-9]*(?:\.[0-9]{0,6})?"), edit))
            self.table.setCellWidget(i, 3, edit)
            self.rate_edits[key] = edit
        self.table.set_readable_font(10 + owner.font_combo.currentIndex())
        self.table.tabs.setCurrentIndex(owner.table.tabs.currentIndex())
        layout.addWidget(self.table.tabs, 1)
        self.message = QLabel("비교 시세와 금액은 엑셀에 저장하지 않습니다. 비교 배율만 별도 설정으로 유지합니다.")
        layout.addWidget(self.message)
        totals = QHBoxLayout()
        self.total_labels = []
        for title in ("현재 합계", "비교 합계", "합계 차액"):
            totals.addWidget(QLabel(title))
            value = QLabel("0")
            value.setFont(text_font(14, True))
            totals.addWidget(value, 1)
            self.total_labels.append(value)
        totals.addWidget(button("닫기", self.accept))
        layout.addLayout(totals)
        for edit in list(self.price_edits.values()) + list(self.rate_edits.values()):
            edit.textChanged.connect(self.recalculate)
        self.setMinimumSize(min(1060, owner.width()), layout.minimumSize().height())
        self.resize(max(self.minimumWidth(), owner.width()), max(self.minimumHeight(), min(owner.height(), 800)))
        self.recalculate()

    def reset_prices(self):
        for metal, edit in self.price_edits.items():
            edit.setText(f"{self.base_prices[metal]:,}")

    def recalculate(self, *_args):
        prices = {}
        for metal, edit in self.price_edits.items():
            raw = edit.text().replace(",", "").strip()
            prices[metal] = int(raw) if raw.isdigit() else None
        amounts = []
        for i, (key, item, weights) in enumerate(zip(self.keys, RATE_ITEMS, self.input_weights)):
            edit = self.rate_edits[key]
            try:
                rate = Decimal(edit.text())
                valid = rate.is_finite() and 0 <= rate <= 10
            except Exception:
                valid = False
            edit.setStyleSheet("" if valid else "border: 1px solid #c43d3d;")
            if valid:
                self.compare_multipliers[key] = rate
            if not valid or prices[item.metal_type] is None:
                self.table.item(i, 5).setText("—")
                self.table.item(i, 6).setText("—")
                amounts.append(None)
                continue
            unit = calculate_unit_price(prices[item.metal_type], item.metal_type, rate)
            amount = calculate_row(unit, *weights)[1]
            amounts.append(amount)
            difference = amount - self.base_amounts[i]
            self.table.item(i, 5).setText(f"{amount:,}")
            self.table.item(i, 6).setText(f"{difference:+,}" if difference else "0")
        self.total_labels[0].setText(f"{sum(self.base_amounts):,}")
        if any(value is None for value in amounts):
            self.total_labels[1].setText("—")
            self.total_labels[2].setText("—")
            self.message.setText("시세와 0~10 범위의 비교 배율을 입력해주세요. 잘못된 배율은 기억하지 않습니다.")
        else:
            self.total_labels[1].setText(f"{sum(amounts):,}")
            difference = sum(amounts) - sum(self.base_amounts)
            self.total_labels[2].setText(f"{difference:+,}" if difference else "0")
            self.message.setText("비교 시세와 금액은 엑셀에 저장하지 않습니다. 비교 배율만 별도 설정으로 유지합니다.")

    def done(self, result):
        previous = self.owner.comparison_multipliers
        self.owner.comparison_multipliers = dict(self.compare_multipliers)
        try:
            self.owner.persist_state()
        except Exception as error:
            self.owner.comparison_multipliers = previous
            korean_message(self, "비교 배율 저장 실패", str(error))
            return
        super().done(result)


class ExportSettingsDialog(QDialog):
    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self.setWindowTitle("엑셀 저장 설정")
        self.setFont(text_font())
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("체크한 항목만 위에서 아래 순서로 저장합니다. 저장 이름을 직접 수정할 수 있습니다."))
        folder_line = QHBoxLayout()
        self.folder = QLineEdit(owner.export_folder)
        folder_line.addWidget(QLabel("저장 폴더"))
        folder_line.addWidget(self.folder, 1)
        folder_line.addWidget(button("폴더 선택", self.choose_folder))
        layout.addLayout(folder_line)
        self.fields = QTableWidget(len(owner.export_columns), 3)
        self.fields.setHorizontalHeaderLabels(("저장", "항목", "엑셀에 표시할 이름"))
        self.fields.verticalHeader().hide()
        self.fields.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.fields.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.fields.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        definitions = dict(DEFAULT_COLUMNS)
        for row, col in enumerate(owner.export_columns):
            enabled = QTableWidgetItem()
            enabled.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable)
            enabled.setCheckState(Qt.CheckState.Checked if col["enabled"] else Qt.CheckState.Unchecked)
            enabled.setData(Qt.ItemDataRole.UserRole, col["key"])
            self.fields.setItem(row, 0, enabled)
            self.fields.setItem(row, 1, readonly_item(definitions[col["key"]], True))
            self.fields.setItem(row, 2, QTableWidgetItem(col["label"]))
        self.fields.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.fields.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.fields.setCurrentCell(0, 2)
        layout.addWidget(self.fields)
        controls = QHBoxLayout()
        controls.addWidget(button("위로", lambda: self.move_row(-1)))
        controls.addWidget(button("아래로", lambda: self.move_row(1)))
        controls.addWidget(QLabel("입고중량 > 0인 품목만 매입내역.xlsx에 누적 저장"), 1)
        controls.addWidget(button("취소", self.reject))
        controls.addWidget(button("적용", self.apply_values, "primary"))
        layout.addLayout(controls)
        self.resize(850, 620)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "엑셀 저장 폴더 선택", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def move_row(self, delta):
        row, target = self.fields.currentRow(), self.fields.currentRow() + delta
        if row < 0 or target < 0 or target >= self.fields.rowCount():
            return
        for col in range(3):
            first, second = self.fields.takeItem(row, col), self.fields.takeItem(target, col)
            self.fields.setItem(row, col, second)
            self.fields.setItem(target, col, first)
        self.fields.setCurrentCell(target, 2)

    def validated_values(self):
        columns = []
        for row in range(self.fields.rowCount()):
            item = self.fields.item(row, 0)
            label = self.fields.item(row, 2).text().strip()
            if not label or len(label) > 60 or "\n" in label:
                raise ValueError("항목 이름은 줄바꿈 없이 1~60자로 입력해주세요.")
            columns.append(dict(key=item.data(Qt.ItemDataRole.UserRole), label=label,
                enabled=item.checkState() == Qt.CheckState.Checked))
        if not any(c["enabled"] for c in columns):
            raise ValueError("저장할 항목을 하나 이상 선택해주세요.")
        folder = self.folder.text().strip()
        if not folder or not Path(folder).expanduser().is_absolute():
            raise ValueError("저장 폴더를 선택하거나 전체 경로를 입력해주세요.")
        return columns, str(Path(folder).expanduser())

    def apply_values(self):
        try:
            columns, folder = self.validated_values()
            old_columns, old_folder = self.owner.export_columns, self.owner.export_folder
            self.owner.export_columns, self.owner.export_folder = columns, folder
            try:
                self.owner.persist_state()
            except Exception:
                self.owner.export_columns, self.owner.export_folder = old_columns, old_folder
                raise
            self.accept()
        except Exception as error:
            korean_message(self, "저장 설정 오류", str(error))


class SettingsDialog(QDialog):
    def __init__(self, owner, kind):
        super().__init__(owner)
        self.owner, self.kind = owner, kind
        self.setWindowTitle("기준품목 이름 설정" if kind == "names" else "Multiplier 설정")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)
        description = "표와 저장 내역에 사용할 이름을 입력하세요. (1~60자)" if kind == "names" else "단가 = 반올림(시세 ÷ Divisor × Multiplier) · 적용 즉시 재계산"
        layout.addWidget(QLabel(description))
        self.setFont(text_font())
        self.table = SplitTable((6, 47, 47) if kind == "names" else (6, 54, 20, 20),
                                ("금속", "원본 기준품목", "변경할 이름") if kind == "names" else ("금속", "기준품목", "원본값", "현재값"),
                                ("금 12품목", "은 7품목"))
        self.edits = {}
        for i, (key, item) in enumerate(zip(owner.keys, RATE_ITEMS)):
            self.table.setItem(i, 0, readonly_item("금" if item.metal_type == "GOLD" else "은"))
            self.table.setItem(i, 1, readonly_item(item.item_name if kind == "names" else owner.names[key], True))
            if kind == "multipliers":
                self.table.setItem(i, 2, readonly_item(f"{item.multiplier:.4f}"))
            edit = QLineEdit(owner.names[key] if kind == "names" else str(owner.multipliers[key]))
            if kind == "names":
                edit.setMaxLength(60)
            else:
                edit.setAlignment(ALIGN)
            self.table.setCellWidget(i, self.table.columnCount() - 1, edit)
            self.edits[key] = edit
        self.table.set_readable_font(10)
        self.table.tabs.setCurrentIndex(owner.table.tabs.currentIndex())
        layout.addWidget(self.table.tabs, 1)
        controls = QHBoxLayout()
        controls.addWidget(button("원본값으로 전체 되돌리기", self.restore_defaults))
        controls.addStretch(1)
        controls.addWidget(button("취소", self.reject))
        controls.addWidget(button("적용", self.apply_values, "primary"))
        layout.addLayout(controls)
        self.setMinimumSize(min(960, owner.width()), layout.minimumSize().height())
        self.resize(max(self.minimumWidth(), min(1060, owner.width())), max(self.minimumHeight(), 560))

    def validated_values(self):
        values = {}
        for key, edit in self.edits.items():
            text = edit.text().strip()
            if self.kind == "names":
                if not text or len(text) > 60 or any(ord(char) < 32 for char in text):
                    raise ValueError("품목 이름을 줄바꿈 없이 1~60자로 입력해주세요.")
                values[key] = text
            else:
                value = Decimal(text.replace(",", ""))
                if not value.is_finite() or not 0 <= value <= 10:
                    raise ValueError("Multiplier는 0~10 사이의 숫자로 입력해주세요.")
                values[key] = value
        return values

    def apply_values(self):
        try:
            values = self.validated_values()
            if self.kind == "names":
                self.owner.names.update(values)
                for i, key in enumerate(self.owner.keys):
                    self.owner.table.item(i, 0).setText(self.owner.names[key])
            else:
                self.owner.multipliers.update(values)
            self.owner.calculate_all()
            self.owner.persist_state()
            self.owner.status.setText("설정 저장 완료")
            self.accept()
        except Exception as error:
            korean_message(self, "설정 오류", str(error))

    def restore_defaults(self):
        if korean_question(self, "원본값 복원", "원본값을 불러올까요? 적용을 눌러야 저장됩니다.") == QMessageBox.StandardButton.Yes:
            for key, item in zip(self.owner.keys, RATE_ITEMS):
                self.edits[key].setText(item.item_name if self.kind == "names" else str(item.multiplier))


Calculator = GoldPanel  # 원본 검사 코드와 같은 이름
