"""Run real Qt widgets in isolated storage; no network or user files touched."""
import json
import os
import sys
import tempfile
import traceback
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics

from core import RATE_ITEMS, append_purchase_record, load_state, row_key, save_state


def run_self_test(report_path, qt_app, screenshot_dir=None):
    import shim
    ui = shim.load_app()
    from app import Calculator, SettingsDialog

    def split_rows_visible(split):
        """[금] [은] 탭마다: 모든 줄이 스크롤 없이 보이고 칸이 표 너비 안에 들어감 (원본의 19줄 검사를 탭별로)."""
        for table in split.tables:
            split.tabs.setCurrentWidget(table)
            qt_app.processEvents()
            table.fit()
            qt_app.processEvents()
            last = table.rowCount() - 1
            assert not table.verticalScrollBar().isVisible()
            assert not table.horizontalScrollBar().isVisible()
            assert table.rowViewportPosition(last) + table.rowHeight(last) <= table.viewport().height(), (table.rowCount(), table.viewport().height())
            assert sum(table.columnWidth(i) for i in range(table.columnCount())) <= table.viewport().width()
        split.tabs.setCurrentIndex(0)
        qt_app.processEvents()

    def points_ok(font, windows_points):
        # macOS scales point sizes so text keeps the same pixel size as Windows.
        return abs(font.pointSizeF() - ui.pt(windows_points)) < 0.01

    result = {"ok": False}
    previous = os.environ.get("APPDATA")
    qt_app.setQuitOnLastWindowClosed(False)
    window = None
    try:
        with tempfile.TemporaryDirectory(prefix="goldmetal-test-") as folder:
            os.environ["APPDATA"] = folder
            # Seed the actual pre-Qt format, including stable original item keys.
            keys = [row_key(i, item) for i, item in enumerate(RATE_ITEMS)]
            save_state({"prices": {"GOLD": 375000, "SILVER": 4030, "PLATINUM": 200000},
                "price_source": "검증용 예시", "price_updated_at": "2026-10-02T12:00:00",
                "item_names": {keys[0]: "순금 골드바"}, "multipliers": {keys[0]: "1.0"},
                "weights": {key: {"input_weight": "1", "deduction_weight": "0"} for key in keys[:12]},
                "window_geometry": "1280x740"})
            window = Calculator(auto_fetch=False)
            window.show()
            qt_app.processEvents()
            assert window.windowTitle() == "고금시세계산"
            assert window.table.gold.rowCount() == 12 and window.table.silver.rowCount() == 7
            if sys.platform == "win32":
                assert ui.FAMILY in ("Malgun Gothic", "맑은 고딕"), "Windows Malgun Gothic not available"
            if sys.platform == "darwin":
                assert abs(ui.POINT_SCALE - 96 / 72) < 0.01 or os.environ.get("GOLDMETAL_POINT_SCALE"), ui.POINT_SCALE
            assert window.refresh_timer.interval() == 1800000
            assert not window.refresh_timer.isActive()
            # Exercise a real timer event with a short test-only interval.
            from PySide6.QtCore import QEventLoop, QTimer
            calls = []
            original_fetch = window.fetch_prices
            window.fetch_prices = lambda show_error=True: calls.append(show_error)
            window.refresh_timer.start(5)
            loop = QEventLoop()
            QTimer.singleShot(40, loop.quit)
            loop.exec()
            window.refresh_timer.stop()
            window.refresh_timer.setInterval(ui.AUTO_REFRESH_MS)
            window.fetch_prices = original_fetch
            assert calls and all(value is False for value in calls)
            window.fetching = True
            window.fetch_prices(False)
            assert window.fetching
            window.fetching = False
            assert window.names[keys[0]] == "순금 골드바"
            total = window.calculate_all()
            assert total == 967600, total
            geometry_checks = []
            for size in ((960, 560), (1060, 640), (1280, 720), (1600, 900)):
                window.resize(*size)
                qt_app.processEvents()
                table = window.table
                table.fit()
                qt_app.processEvents()
                assert points_ok(table.font(), 10)
                assert table.rowCount() == 19
                split_rows_visible(table)
                for i, key in enumerate(keys):
                    assert table.item(i, 0).text() == window.names[key]
                    assert points_ok(window.weights[i][0].font(), 10)
                    assert window.weights[i][0].height() >= QFontMetrics(table.font()).height() + 2
                geometry_checks.append([window.width(), window.height()])
            # Font growth is explicit and persistent, never silently reduced.
            window.font_combo.setCurrentIndex(1)
            qt_app.processEvents()
            assert points_ok(window.table.font(), 11)
            window.resize(1060, 640)
            qt_app.processEvents()
            assert points_ok(window.table.font(), 11)
            split_rows_visible(window.table)
            dialog = SettingsDialog(window, "names")
            dialog.show()
            qt_app.processEvents()
            dialog.edits[keys[0]].setText("")
            try:
                dialog.validated_values()
                raise AssertionError("Blank name was accepted")
            except ValueError:
                pass
            assert window.names[keys[0]] == "순금 골드바"
            dialog.edits[keys[0]].setText("선명한 골드바")
            dialog.apply_values()
            assert window.table.item(0, 0).text() == "선명한 골드바"
            assert window.calculate_all() == 967600
            assert window.rows[0]["item_name"] == "선명한 골드바"
            dialog = SettingsDialog(window, "multipliers")
            dialog.edits[keys[0]].setText("0.5")
            dialog.apply_values()
            assert window.calculate_all() == 917600
            csv_file = append_purchase_record(window.rows, window.prices, window.price_source, 917600)
            assert "선명한 골드바" in csv_file.read_text(encoding="utf-8-sig")
            # Failed or partial updates cannot zero existing prices.
            old_prices = dict(window.prices)
            window.fetch_failed("simulated", False)
            assert window.prices == old_prices
            window.apply_fetched_prices({"GOLD": 375000}, {"fetched_at": "2026-10-02T12:00:00"}, window.price_revision)
            assert window.prices["SILVER"] == old_prices["SILVER"]
            assert window.prices["PLATINUM"] == old_prices["PLATINUM"]
            window.close()
            window = Calculator(auto_fetch=False)
            window.show()
            qt_app.processEvents()
            assert window.names[keys[0]] == "선명한 골드바"
            assert window.multipliers[keys[0]] == Decimal("0.5")
            assert window.calculate_all() == 917600
            assert points_ok(window.table.font(), 11)
            if screenshot_dir:
                target = Path(screenshot_dir)
                target.mkdir(parents=True, exist_ok=True)
                window.resize(1320, 800)
                window.price_source = "검증용 예시 · 실시간 시세 아님"
                window.refresh_cards()
                qt_app.processEvents()
                assert window.grab().save(str(target / "main.png"))
                settings = SettingsDialog(window, "names")
                settings.show()
                qt_app.processEvents()
                assert settings.grab().save(str(target / "names.png"))
                settings.close()
            result = {"ok": True, "gold_total": total, "multiplier_total": 917600,
                "migration_v14": True, "names_csv_persistence": True, "font_points": 11,
                "auto_refresh_ms": ui.AUTO_REFRESH_MS, "timer_callback_verified": True,
                "font_family": ui.FAMILY, "point_scale": ui.POINT_SCALE, "device_pixel_ratio": window.devicePixelRatioF(),
                "tested_window_sizes": geometry_checks, "rows_visible": 19,
                "scrollbars": 0, "failure_keeps_prices": True, "partial_update_keeps_missing_prices": True}
            from feature_checks import check_features
            result["v17_features"] = check_features(window, qt_app, folder)
            from append_checks import check_accumulation
            result["v18_accumulation"] = check_accumulation(folder)
            from compatibility_checks import check_excel_roundtrip
            result["v110_excel_compatibility"] = check_excel_roundtrip(folder)
            from comparison_checks import check_comparison
            result["v111_comparison"] = check_comparison(window, qt_app, folder)
            from inline_price_checks import check_inline_prices
            result["v112_inline_prices"] = check_inline_prices(window, qt_app)
            from timer_checks import check_manual_minutes
            result["manual_minutes"] = check_manual_minutes(window, qt_app)
            window.close()
            window = None
    except Exception:
        result["error"] = traceback.format_exc()
    finally:
        if window is not None:
            window.close()
        if previous is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = previous
        Path(report_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1
