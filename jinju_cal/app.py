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


def scale_setting() -> int:
    """이 컴퓨터에 저장된 화면 크기 (%), 잘못된 값이면 100."""
    v = str(storage.load().get("scale", "100"))
    return int(v) if v in ("100", "90", "80", "70") else 100


def apply_scale():
    """화면 크기는 프로그램을 열 때 Qt 배율로 적용 (글자·칸·여백이 함께 줄어듦)."""
    v = scale_setting()
    if v == 100:
        os.environ.pop("QT_SCALE_FACTOR", None)
    else:
        os.environ["QT_SCALE_FACTOR"] = f"{v / 100:g}"
    return v


def restart_command():
    """다시 열 때 실행할 명령 (만든 프로그램이면 그 실행 파일, 개발 중이면 python run.py)."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.abspath(sys.argv[0])]


def relaunch():
    import subprocess
    from .update import child_env
    env = child_env()
    env.pop("QT_SCALE_FACTOR", None)  # 새로 열리는 쪽이 저장된 화면 크기를 다시 읽음
    kw = {"start_new_session": True} if sys.platform != "win32" else {"creationflags": 0x00000008 | 0x00000200}
    subprocess.Popen(restart_command(), env=env, close_fds=True, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)


def main() -> int:
    if sys.platform == "win32":
        try:  # 작업 표시줄에 이 프로그램 아이콘이 보이게
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JinjuCal.PriceCalculator")
        except Exception:
            pass
    apply_scale()
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

    smoke = "--smoke" in sys.argv  # 빌드 확인용: 두 탭이 다 뜨는지만 보고 바로 닫음 (자동 조회·업데이트 확인 없음)
    win = MainWindow(gold_auto_fetch=not smoke)
    app.aboutToQuit.connect(win.gold.save_on_quit)  # 맥 Cmd+Q·업데이트·다시 열기에서도 고금 입력값 저장
    if not storage.load().get("window"):
        scr = app.primaryScreen().availableGeometry()
        win.resize(min(1180, scr.width()), min(900, scr.height() - 40))
    win.show()
    if smoke:
        from PySide6.QtCore import QTimer
        import lxml.etree  # noqa: F401  (고금 엑셀 저장에 필요한 부품이 들어 있는지)
        import requests  # noqa: F401
        def done():
            ok = win.tabs.count() == 2 and win.gold.table.gold.rowCount() == 12 and win.gold.table.silver.rowCount() == 7
            app.exit(0 if ok else 3)
        win.tabs.setCurrentIndex(1)
        QTimer.singleShot(1500, done)
    code = app.exec()
    lock.unlock()
    if win.restart_requested:  # 화면 크기를 바꿔 다시 열기
        relaunch()
    return code
