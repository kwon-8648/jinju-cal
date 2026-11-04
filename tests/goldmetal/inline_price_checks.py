from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QPushButton
from core import load_state


def check_inline_prices(w, qt_app):
    assert not hasattr(w, 'manual_dialog')
    assert not any(b.text()=='수동 시세 입력' for b in w.findChildren(QPushButton))
    w.show()
    w.activateWindow()
    w.table.setFocus()
    qt_app.processEvents()
    w.prices['GOLD']=375000
    w.refresh_cards()
    for pair in w.weights:
        for edit in pair:
            edit.clear()
    w.weights[0][0].setText('7.5')
    w.weights[0][1].setText('0.5')
    w.multipliers[w.keys[0]]=1
    assert w.calculate_all()==700000
    edit=w.price_labels['GOLD']
    edit.setFocus()
    edit.selectAll()
    old_revision=w.price_revision
    QTest.keyClicks(edit,'450000')
    assert w.prices['GOLD']==375000 and w.calculate_all()==700000
    w.apply_fetched_prices({'GOLD':1},{},old_revision)
    assert edit.text()=='450000' and w.prices['GOLD']==375000
    QTest.keyClick(edit,Qt.Key.Key_Return)
    assert w.prices['GOLD']==450000 and edit.text()=='450,000'
    assert w.calculate_all()==840000 and w.refresh_mode=='manual'
    assert w.manual_timer.isActive() and not w.refresh_timer.isActive()
    assert load_state()['prices']['GOLD']==450000
    deadline=w.manual_due
    QTest.keyClick(edit,Qt.Key.Key_Return)
    assert w.manual_due==deadline  # No double commit.
    edit.selectAll()
    QTest.keyClicks(edit,'500000')
    w.weights[0][0].setFocus()
    qt_app.processEvents()
    assert w.prices['GOLD']==500000 and edit.text()=='500,000'
    edit.setFocus()
    edit.selectAll()
    QTest.keyClick(edit,Qt.Key.Key_Backspace)
    w.table.setFocus()
    qt_app.processEvents()
    assert w.prices['GOLD']==500000 and edit.text()=='500,000'
    edit.setFocus()
    edit.selectAll()
    QTest.keyClicks(edit,'100')
    QTest.keyClick(edit,Qt.Key.Key_Escape)
    assert w.prices['GOLD']==500000 and edit.text()=='500,000'
    for metal in ('SILVER','PLATINUM'):
        e=w.price_labels[metal]
        e.setFocus()
        e.selectAll()
        QTest.keyClicks(e,'12345')
        QTest.keyClick(e,Qt.Key.Key_Return)
        assert w.prices[metal]==12345 and e.text()=='12,345'
    w.table.setFocus()
    return dict(enter_commit=True, focus_loss_commit=True, pending_fetch_protected=True,
                invalid_and_escape_restore=True, manual_30min=True, three_metals=True, old_dialog_removed=True)
