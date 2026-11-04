"""원본 고금시세계산 검사 코드가 옮겨 온 모듈을 원래 이름(core, excel_export, xlsx_append, app)으로 찾게 함."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from jinju_cal.goldmetal import core, excel_export, xlsx_append  # noqa: E402

sys.modules.setdefault("core", core)
sys.modules.setdefault("excel_export", excel_export)
sys.modules.setdefault("xlsx_append", xlsx_append)


def load_app():
    from jinju_cal.goldmetal import panel
    sys.modules.setdefault("app", panel)
    return panel
