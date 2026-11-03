# PyInstaller 빌드 설정 — 윈도우: 상품가격계산기.exe (파일 하나) / 맥: 상품가격계산기.app
#   pyinstaller --noconfirm jinju-cal.spec
import re
import sys

NAME = "상품가격계산기"
VERSION = re.search(r'__version__ = "([^"]+)"', open("jinju_cal/__init__.py", encoding="utf-8").read()).group(1)
MAC = sys.platform == "darwin"

a = Analysis(
    ["run.py"],
    datas=[("assets/icon.png", "assets")],
    hiddenimports=["certifi"],
    excludes=["tkinter", "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
              "PySide6.QtMultimedia", "PySide6.QtPdf", "PySide6.Qt3DCore", "PySide6.QtCharts", "PySide6.QtSql"],
)
pyz = PYZ(a.pure)

if MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False, icon="assets/icon.icns")
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name=NAME + ".app",
        icon="assets/icon.icns",
        bundle_identifier="app.jinjucal.calculator",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": NAME,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleDevelopmentRegion": "ko",
            "LSMinimumSystemVersion": "12.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": True,  # 다크 모드에서도 밝은 화면
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, icon="assets/icon.ico", upx=False)
