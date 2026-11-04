"""Integration checks run by both the source and packaged EXE self-test."""
from datetime import datetime
from pathlib import Path
import time
from unittest.mock import patch
from zipfile import ZipFile
from xml.etree import ElementTree as ET

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox
from core import load_state
from excel_export import export_purchase, grams_to_don, normalize_columns, NS


def check_features(window, qt_app, folder):
    from app import Calculator, ExportSettingsDialog, AUTO_REFRESH_MS
    assert str(grams_to_don("7.5")) == "2.00"
    assert str(grams_to_don("1")) == "0.27"
    window.weights[0][0].setText("7.5")
    window.weights[0][1].setText("0.5")
    window.calculate_all()
    assert window.table.item(0, 3).text() == "2.00"
    assert window.table.item(0, 5).text() == "25,000"

    window.enter_manual_mode()
    assert window.refresh_mode == "manual"
    assert not window.refresh_timer.isActive()
    assert window.manual_timer.isActive() and window.manual_timer.interval() == AUTO_REFRESH_MS
    calls = []
    original_fetch = window.fetch_prices
    window.fetch_prices = lambda show_error=True: calls.append(show_error)
    window.auto_tick()
    assert not calls
    old_prices = dict(window.prices)
    window.price_revision += 1
    window.apply_fetched_prices({"GOLD": 1}, {}, window.price_revision - 1)
    assert window.prices == old_prices
    with patch("app.korean_question", return_value=QMessageBox.StandardButton.No):
        window.ask_manual_refresh()
    assert window.refresh_mode == "manual" and not calls
    assert 1795 < window.manual_due - time.time() <= 1800
    with patch("app.korean_question", return_value=QMessageBox.StandardButton.Yes):
        window.ask_manual_refresh()
    assert calls == [True] and window.refresh_mode == "auto"
    assert window.refresh_timer.isActive() and not window.manual_timer.isActive()
    # Yes while an old request is running must queue a fresh request.
    window.enter_manual_mode()
    window.price_revision += 1
    window.fetching = True
    window.resume_auto()
    assert window.pending_auto_fetch
    window.apply_fetched_prices({"GOLD": 1}, {}, window.price_revision - 1)
    assert len(calls) == 2 and not window.pending_auto_fetch
    window.fetch_prices = original_fetch

    settings = ExportSettingsDialog(window)
    settings.folder.setText(str(Path(folder) / "고객 엑셀"))
    for i in range(settings.fields.rowCount()):
        settings.fields.item(i, 0).setCheckState(Qt.CheckState.Unchecked)
    try:
        settings.validated_values()
        raise AssertionError("Empty column selection accepted")
    except ValueError:
        pass
    included = {"timestamp", "item_name", "input_don", "customer_price", "total_customer_price"}
    for i in range(settings.fields.rowCount()):
        key = settings.fields.item(i, 0).data(Qt.ItemDataRole.UserRole)
        if key in included:
            settings.fields.item(i, 0).setCheckState(Qt.CheckState.Checked)
        if key == "item_name":
            settings.fields.item(i, 2).setText("내 품목명")
            settings.fields.setCurrentCell(i, 2)
    while settings.fields.currentRow() > 0:
        settings.move_row(-1)
    settings.apply_values()
    assert window.export_columns[0]["key"] == "item_name"
    assert window.export_columns[0]["label"] == "내 품목명"
    assert load_state()["export_folder"] == str(Path(folder) / "고객 엑셀")

    for pair in window.weights:
        for edit in pair:
            edit.clear()
    window.weights[0][0].setText("7.5")
    window.weights[0][1].setText("0.5")
    window.weights[1][1].setText("1")  # Deduction-only row must not be exported.
    total = window.calculate_all()
    path = export_purchase(window.rows, window.prices, window.price_source, total,
        window.export_folder, window.export_columns, datetime(2026, 10, 2, 15, 53, 55))
    with ZipFile(path) as z:
        assert z.testzip() is None
        for name in z.namelist():
            ET.fromstring(z.read(name))
        sheet = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
        styles = ET.fromstring(z.read("xl/styles.xml"))
    rows = sheet.findall(f"{{{NS}}}sheetData/{{{NS}}}row")
    assert len(rows) == 2 and len(rows[0]) == 5
    labels = ["".join(c.itertext()) for c in rows[0]]
    assert labels[0] == "내 품목명" and "고객별 매입가 합계" in labels
    values = {label: cell for label, cell in zip(labels, rows[1])}
    assert values["입고중량(돈)"].find(f"{{{NS}}}v").text == "2.00"
    assert int(values["고객별 매입가 합계"].find(f"{{{NS}}}v").text) == total
    assert values["고객매입가"].get("s") == "3"
    assert values["저장일시"].get("s") == "6"
    assert styles.find(f"{{{NS}}}numFmts/{{{NS}}}numFmt").get("formatCode") == 'yyyy.mm.dd"(금)" hh:mm'
    for row in window.rows:
        row["input_weight"] = "0"
    try:
        export_purchase(window.rows, window.prices, "test", 0, folder, normalize_columns())
        raise AssertionError("Empty purchase was exported")
    except ValueError:
        pass
    window.enter_manual_mode()
    restored = Calculator(auto_fetch=True)
    assert restored.refresh_mode == "manual" and not restored.refresh_timer.isActive()
    assert restored.manual_timer.isActive()
    assert restored.export_columns == window.export_columns
    restored.close()
    assert not restored.manual_timer.isActive()
    return dict(manual_no_reprompts=True, manual_yes_resumes=True, stale_request_ignored=True,
        manual_restart_preserved=True, export_selection_order_names=True, export_folder=True,
        positive_input_only=True, timestamp_korean_weekday=True, numeric_currency=True, don_2dp=True)
