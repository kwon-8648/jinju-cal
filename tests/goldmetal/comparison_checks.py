from pathlib import Path
from zipfile import ZipFile
from core import load_state
from excel_export import export_purchase


def check_comparison(owner, qt_app, folder):
    from app import ComparisonDialog, Calculator
    for pair in owner.weights:
        for edit in pair:
            edit.clear()
    key = owner.keys[0]
    owner.prices['GOLD'] = 375000
    owner.multipliers[key] = 1
    owner.comparison_multipliers[key] = 1
    owner.weights[0][0].setText('7.5')
    owner.weights[0][1].setText('0.5')
    total = owner.calculate_all()
    assert total == 700000
    owner.persist_state()
    before = load_state()
    rows = [dict(r) for r in owner.rows]
    d = ComparisonDialog(owner)
    d.show()
    qt_app.processEvents()
    assert d.total_labels[0].text() == d.total_labels[1].text() == '700,000'
    d.rate_edits[key].setText('0.5')
    assert d.table.item(0,5).text() == '350,000'
    assert d.table.item(0,6).text() == '-350,000'
    d.price_edits['GOLD'].setText('450000')
    assert d.total_labels[1].text() == '420,000'
    assert d.total_labels[2].text() == '-280,000'
    d.rate_edits[key].setText('11')
    assert d.total_labels[1].text() == '—'
    assert d.compare_multipliers[key] == 0.5
    d.rate_edits[key].setText('0.5')
    d.price_edits['GOLD'].clear()
    assert d.total_labels[1].text() == '—'
    d.reset_prices()
    assert d.total_labels[1].text() == '350,000'
    for width, height in ((960, 560), (1060, 760), (1280, 760)):
        d.resize(width, height)
        qt_app.processEvents()
        for t in d.table.tables:  # [금] [은] 탭마다 모든 줄이 스크롤 없이
            d.table.tabs.setCurrentWidget(t)
            qt_app.processEvents()
            t.fit()
            last = t.rowCount() - 1
            assert not t.verticalScrollBar().isVisible()
            assert t.rowViewportPosition(last) + t.rowHeight(last) <= t.viewport().height()
    d.close()  # Title-bar close must persist just like the close button.
    after = load_state()
    assert after['comparison_multipliers'][key] == '0.5'
    assert all(before[k] == after[k] for k in before if k != 'comparison_multipliers')
    assert owner.rows == rows and owner.calculate_all() == total
    reopened = ComparisonDialog(owner)
    assert reopened.price_edits['GOLD'].text() == '375,000'
    assert reopened.rate_edits[key].text() == '0.5'
    reopened.reject()  # Escape/reject must preserve the same setting.
    restarted = Calculator(auto_fetch=False)
    assert restarted.comparison_multipliers[key] == 0.5
    assert restarted.multipliers[key] == 1 and restarted.prices['GOLD'] == 375000
    restarted.close()
    path = export_purchase(owner.rows, owner.prices, owner.price_source, total,
                           Path(folder)/'comparison_export', owner.export_columns)
    with ZipFile(path) as z:
        sheet = z.read('xl/worksheets/sheet1.xml').decode()
        assert '>700000<' in sheet and '>350000<' not in sheet and '>420000<' not in sheet
    return dict(independent_prices=True, independent_multipliers=True, instant_totals=True,
                persistent_comparison_rates=True, invalid_input_handled=True, excel_unchanged=True)
