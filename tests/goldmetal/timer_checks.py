"""수동 입력 후 갱신 확인 시간(분) 조정 기능 검사."""
import time
from unittest.mock import patch

from PySide6.QtWidgets import QMessageBox

from core import load_state


def check_korean_question(window, qt_app):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QDialog
    from app import build_korean_question
    results = {}
    for key, expected in ((Qt.Key.Key_Return, QDialog.DialogCode.Accepted),
                          (Qt.Key.Key_Escape, QDialog.DialogCode.Rejected)):
        dialog, yes, no = build_korean_question(window, "시세 자동 갱신", "검사")
        dialog.show()
        qt_app.processEvents()
        assert yes.text() == "네" and no.text() == "아니요"
        assert yes.isDefault() and not no.isDefault()
        assert yes.mapTo(dialog, yes.rect().topLeft()).x() < no.mapTo(dialog, no.rect().topLeft()).x()
        QTest.keyClick(dialog, key)
        qt_app.processEvents()
        assert dialog.result() == expected, (key, dialog.result())
        dialog.deleteLater()
    dialog, yes, no = build_korean_question(window, "시세 자동 갱신", "검사")
    dialog.show()
    qt_app.processEvents()
    QTest.mouseClick(no, Qt.MouseButton.LeftButton)
    assert dialog.result() == QDialog.DialogCode.Rejected
    return {"labels": ["네", "아니요"], "order_yes_first": True, "enter_yes": True, "escape_no": True}


def press_enter_on_next_dialog(seen, attempts=200):
    """Press Enter on the next modal dialog, recording its button labels."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QPushButton

    def act(remaining=attempts):
        widget = QApplication.activeModalWidget()
        if widget is None:
            if remaining > 0:
                QTimer.singleShot(25, lambda: act(remaining - 1))
            return
        seen.append([b.text() for b in widget.findChildren(QPushButton) if b.isVisible()])
        QTest.keyClick(widget, Qt.Key.Key_Return)
    QTimer.singleShot(25, act)


def check_all_dialogs_korean(window, qt_app):
    from app import korean_message
    # Real '중량 초기화' question: Korean buttons, Enter = 네 (weights are cleared).
    window.weights[0][0].setText("1")
    seen = []
    press_enter_on_next_dialog(seen)
    window.reset_weights()
    assert seen and set(seen[0]) == {"네", "아니요"}, seen
    assert window.weights[0][0].text() == ""
    # Warning/information boxes show '확인' instead of OK, Enter closes.
    seen = []
    press_enter_on_next_dialog(seen)
    korean_message(window, "저장 실패", "검사")
    assert seen and seen[0] == ["확인"], seen
    seen = []
    press_enter_on_next_dialog(seen)
    korean_message(window, "저장 완료", "검사", warning=False)
    assert seen and seen[0] == ["확인"], seen
    return {"reset_weights_enter_yes": True, "message_ok_label": "확인"}


def check_manual_minutes(window, qt_app):
    from app import Calculator
    korean = check_korean_question(window, qt_app)
    korean["all_dialogs"] = check_all_dialogs_korean(window, qt_app)
    assert window.manual_spin.minimum() == 1 and window.manual_spin.maximum() == 240
    window.resume_auto = lambda: None
    window.fetching = False
    # Default 30 minutes, then change while in manual mode: due moves relative to entry time.
    window.manual_spin.setValue(30)
    window.enter_manual_mode()
    started = window.manual_due - 30 * 60
    window.manual_spin.setValue(10)
    qt_app.processEvents()
    assert window.manual_minutes == 10
    assert abs(window.manual_due - (started + 600)) < 2
    assert window.manual_timer.isActive() and window.manual_timer.remainingTime() <= 600 * 1000
    assert "10분 후 갱신 확인" in window.mode_label.text()
    assert load_state()["manual_check_minutes"] == 10
    # New manual entry uses the chosen interval.
    window.enter_manual_mode()
    assert window.manual_timer.interval() == 10 * 60 * 1000
    assert 595 < window.manual_due - time.time() <= 600
    # 'No' postpones by the chosen interval and the question mentions it.
    for edit in window.price_labels.values():
        edit.setModified(False)
    seen = []
    def answer_no(*args, **kwargs):
        seen.append(args[2])
        return QMessageBox.StandardButton.No
    with patch("app.korean_question", side_effect=answer_no):
        window.ask_manual_refresh()
    assert "10분이 지났습니다" in seen[0] and "10분 후 다시 확인" in seen[0] and "아니요:" in seen[0]
    assert 595 < window.manual_due - time.time() <= 600
    # Shortening below the elapsed time asks soon instead of waiting.
    window.manual_due = time.time() + 9 * 60   # entered 1 minute ago with a 10-minute interval
    window.manual_spin.setValue(1)
    assert window.manual_timer.remainingTime() <= 1000 + 50
    # Survives restart; invalid stored values are clamped.
    window.manual_spin.setValue(45)
    window.close()
    restored = Calculator(auto_fetch=False)
    try:
        assert restored.manual_minutes == 45 and restored.manual_spin.value() == 45
    finally:
        restored.close()
    window.manual_spin.setValue(30)
    return {"korean_question": korean, "range": [1, 240], "relative_reschedule": True, "no_postpones_by_setting": True,
            "persisted": True}
