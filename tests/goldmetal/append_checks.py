from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as E
from zipfile import ZipFile
from excel_export import export_purchase, normalize_columns, NS


def check_accumulation(folder):
    folder = Path(folder) / '누적 검증'
    row = dict(item_name='골드바', metal_type='GOLD', input_weight='7.5', deduction_weight='0.5',
               unit_price=100000, deduction_price=50000, customer_price=700000, multiplier='1')
    cols = normalize_columns()
    selected = {'timestamp','item_name','input_don','customer_price','total_customer_price'}
    for col in cols:
        col['enabled'] = col['key'] in selected
    p = export_purchase([row], {'GOLD':375000}, '검증', 700000, folder, cols, datetime(2026,10,2,15,53))
    assert p.name == '매입내역.xlsx'
    with ZipFile(p) as z:
        first = E.fromstring(z.read('xl/worksheets/sheet1.xml')).find(f'{{{NS}}}sheetData')[1]
        first_xml = E.tostring(first)
    assert export_purchase([row], {'GOLD':375000}, '검증', 700000, folder, cols, datetime(2026,10,3,9,5)) == p
    with ZipFile(p) as z:
        sheet = E.fromstring(z.read('xl/worksheets/sheet1.xml'))
        rows = sheet.find(f'{{{NS}}}sheetData')
        assert len(rows)==3 and E.tostring(rows[1])==first_xml
        styles = E.fromstring(z.read('xl/styles.xml'))
        xfs = styles.find(f'{{{NS}}}cellXfs')
        formats = {c.get('numFmtId'):c.get('formatCode') for c in styles.find(f'{{{NS}}}numFmts')}
        for rownum, day in ((1,'금'),(2,'토')):
            style = int(rows[rownum][0].get('s'))
            assert f'({day})' in formats[xfs[style].get('numFmtId')]
        assert sheet.find(f'{{{NS}}}autoFilter').get('ref')=='A1:E3'
        original_sheet = z.read('xl/worksheets/sheet1.xml')
    cols.reverse()
    cols[1]['label'] = '바꾼 열 이름'
    export_purchase([row], {}, '검증', 700000, folder, cols)
    export_purchase([row], {}, '검증', 700000, folder, cols)
    with ZipFile(p) as z:
        assert z.read('xl/worksheets/sheet1.xml')==original_sheet
        wb=E.fromstring(z.read('xl/workbook.xml'))
        assert len(wb.find(f'{{{NS}}}sheets'))==2
        sheet2=E.fromstring(z.read('xl/worksheets/goldmetal2.xml'))
        assert len(sheet2.find(f'{{{NS}}}sheetData'))==3
        for name in z.namelist():
            if name.endswith('.xml') or name.endswith('.rels'):
                E.fromstring(z.read(name))
    before=p.read_bytes()
    lock=folder/'~$매입내역.xlsx'
    lock.touch()
    try:
        export_purchase([row], {}, '検証', 700000, folder, cols)
        raise AssertionError('Open workbook lock ignored')
    except PermissionError:
        assert p.read_bytes()==before
    finally:
        lock.unlink()
    assert len(list(folder.glob('*.xlsx')))==1
    return dict(same_file_appended=True, old_rows_preserved=True, weekdays_preserved=True,
                schema_change_new_sheet=True, open_file_protected=True)
