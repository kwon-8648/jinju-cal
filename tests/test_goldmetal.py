"""고금 매입 탭 확인 — 고금시세계산 v1.16 원본 검사를 옮겨 온 모듈에 그대로 돌림.

  python tests/test_goldmetal.py

1) 원본 단위 검사: 계산(기준값 967,600 등)·시세 조회(POST·보안 토큰)·엑셀 저장·엑셀 호환
2) 원본 화면 자체 검사(selftest_gui): 자동 갱신 30분·수동 확인 시간·직접 입력·비교·설정·엑셀 누적 …
   (19줄 표 검사는 [금] [은] 탭별로 바꿈, 960×560 작은 화면 추가)
3) 원본 확인창 한글 검사(timer_checks)
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "goldmetal"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen") if not sys.platform.startswith(("win", "darwin")) else None
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import shim  # noqa: E402

fails = []

print("== 1) 원본 단위 검사")
suite = unittest.defaultTestLoader.loadTestsFromNames(["test_core", "test_fetch", "test_save_group", "test_excel_compatibility"])
r = unittest.TextTestRunner(verbosity=1).run(suite)
if not r.wasSuccessful():
    fails.append("unit")

print("== 2) 원본 화면 자체 검사")
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication([])
app.setStyle("Fusion")
panel = shim.load_app()
panel.init_fonts(app)
import selftest_gui  # noqa: E402

report = tempfile.mktemp(suffix=".json")
rc = selftest_gui.run_self_test(report, app)
d = json.load(open(report, encoding="utf-8"))
if rc != 0 or not d.get("ok"):
    print(d.get("error", d))
    fails.append("selftest")
else:
    print("  ok ", {k: v for k, v in d.items() if isinstance(v, dict)})

print("== 3) 확인창 한글")
import timer_checks  # noqa: E402

prev = os.environ.get("APPDATA")
with tempfile.TemporaryDirectory() as folder:
    os.environ["APPDATA"] = folder
    w = panel.Calculator(auto_fetch=False)
    w.show()
    try:
        timer_checks.check_korean_question(w, app)
        timer_checks.check_all_dialogs_korean(w, app)
        print("  ok  네/아니요·확인 버튼")
    except Exception as e:
        import traceback
        traceback.print_exc()
        fails.append("dialogs")
    w.close()
if prev is None:
    os.environ.pop("APPDATA", None)
else:
    os.environ["APPDATA"] = prev

print("실패: " + ", ".join(fails) if fails else "모두 통과", flush=True)
# 검사가 끝난 뒤 파이썬이 닫히며 Qt 창을 정리하다 리눅스에서 멈추는 일(종료 순서 문제)이 있어, 결과를 낸 뒤 바로 끝냄
sys.stdout.flush()
sys.stderr.flush()
code = 1 if fails else 0
if sys.platform == "win32":  # 윈도우는 os._exit 도 Qt DLL 정리 중에 멈춰서, 프로세스를 그 자리에서 끝냄
    import ctypes
    k = ctypes.windll.kernel32
    k.TerminateProcess(k.GetCurrentProcess(), code)
os._exit(code)
