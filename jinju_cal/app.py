"""프로그램 시작점."""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QApplication, QMessageBox

from . import APP_NAME
from .storage import Store
from .ui import C, MainWindow, stylesheet


def resource(name: str) -> str:
    base = getattr(sys, "_MEIPASS", os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    return os.path.join(base, "assets", name)


def light_palette() -> QPalette:
    # 맥 다크 모드여도 웹판과 같은 밝은 색으로
    p = QPalette()
    for role, col in ((QPalette.Window, C["bg"]), (QPalette.WindowText, C["ink"]), (QPalette.Base, C["panel"]),
                      (QPalette.AlternateBase, C["soft"]), (QPalette.Text, C["ink"]), (QPalette.Button, C["panel"]),
                      (QPalette.ButtonText, C["ink"]), (QPalette.Highlight, C["soft"]), (QPalette.HighlightedText, C["ink"]),
                      (QPalette.ToolTipBase, C["panel"]), (QPalette.ToolTipText, C["ink"]), (QPalette.PlaceholderText, "#a39b8c"),
                      (QPalette.Link, C["gold"])):
        p.setColor(role, QColor(col))
    return p


def main() -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    icon = resource("icon.png")
    if os.path.exists(icon):
        app.setWindowIcon(QIcon(icon))

    store = Store()
    # 두 개를 동시에 열면 한쪽 저장이 다른 쪽을 덮어쓸 수 있어 하나만 열리게 함
    lock = QLockFile(os.path.join(store.root, "running.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        b = QMessageBox(QMessageBox.Information, APP_NAME, "상품가격계산기가 이미 열려 있습니다.\n작업 표시줄(Dock)에서 열린 창을 찾아 주세요.")
        b.addButton("확인", QMessageBox.AcceptRole)
        b.exec()
        return 0

    win = MainWindow(store)
    app.setStyleSheet(stylesheet(win.zoom))
    win.show()
    code = app.exec()
    lock.unlock()
    return code


if __name__ == "__main__":
    sys.exit(main())
