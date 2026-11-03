"""프로그램 시작점."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME, __version__, storage
from .ui import C, MainWindow, body_font_family, stylesheet


def resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.join(base, "assets", name)


def light_palette() -> QPalette:
    # 맥 다크 모드여도 매장관리 웹과 같은 밝은 색으로
    p = QPalette()
    for role, col in ((QPalette.Window, C["bg"]), (QPalette.WindowText, C["ink"]), (QPalette.Base, C["panel"]),
                      (QPalette.AlternateBase, C["soft"]), (QPalette.Text, C["ink"]), (QPalette.Button, C["panel"]),
                      (QPalette.ButtonText, C["ink"]), (QPalette.Highlight, C["gold"]), (QPalette.HighlightedText, C["gold_ink"]),
                      (QPalette.ToolTipBase, C["panel"]), (QPalette.ToolTipText, C["ink"]), (QPalette.PlaceholderText, "#a39b8c"),
                      (QPalette.Link, C["gold"])):
        p.setColor(role, QColor(col))
    return p


def main() -> int:
    if sys.platform == "win32":
        try:  # 작업 표시줄에 이 프로그램 아이콘이 보이게
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JinjuCal.PriceCalculator")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setStyle("Fusion")  # 맥·윈도우에서 같은 모양
    app.setPalette(light_palette())
    font = QFont(body_font_family())
    font.setPixelSize(14)
    app.setFont(font)
    app.setStyleSheet(stylesheet())
    icon = resource("icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    # 두 개를 동시에 열면 한쪽 저장이 다른 쪽을 덮어쓸 수 있어 하나만 열리게 함
    root = storage.data_dir()
    root.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(root / "running.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        b = QMessageBox(QMessageBox.Information, APP_NAME, "상품가격계산기가 이미 열려 있습니다.\n작업 표시줄(Dock)에서 열린 창을 찾아 주세요.")
        b.addButton("확인", QMessageBox.AcceptRole)
        b.exec()
        return 0

    win = MainWindow()
    if not storage.load().get("window"):
        scr = app.primaryScreen().availableGeometry()
        win.resize(min(1180, scr.width()), min(900, scr.height() - 40))
    win.show()
    code = app.exec()
    lock.unlock()
    return code
