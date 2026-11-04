import tempfile
import unittest
from datetime import datetime
from xml.etree import ElementTree as E
from zipfile import ZipFile
from excel_export import export_purchase, normalize_columns, NS


class SaveGroupTests(unittest.TestCase):
    def test_first_row_only_and_same_minute_separate(self):
        cols = normalize_columns()
        for c in cols:
            c['enabled'] = c['key'] in {'timestamp','item_name','customer_price','total_customer_price'}
        rows = [dict(item_name='빈 품목', input_weight='0', customer_price=0),
                dict(item_name='금', input_weight='1', customer_price=100000),
                dict(item_name='은', input_weight='2', customer_price=2000)]
        with tempfile.TemporaryDirectory() as folder:
            for _ in range(2):
                path = export_purchase(rows, {}, '검증', 102000, folder, cols, datetime(2026,10,2,17,30))
            with ZipFile(path) as z:
                sheet = E.fromstring(z.read('xl/worksheets/sheet1.xml'))
            data = sheet.find(f'{{{NS}}}sheetData')
            self.assertEqual(len(data), 5)
            for index in (1,3):
                self.assertIsNotNone(data[index][0].find(f'{{{NS}}}v'))
                self.assertEqual(data[index][3].find(f'{{{NS}}}v').text, '102000')
            for index in (2,4):
                self.assertEqual(len(data[index][0]), 0)
                self.assertEqual(len(data[index][3]), 0)
                self.assertEqual(data[index][2].find(f'{{{NS}}}v').text, '2000')
            # Identity, not a label or column position, controls the blank cells.
            cols.reverse()
            for c in cols:
                c['label'] = '변경 ' + c['label']
            path = export_purchase(rows, {}, '검증', 102000, folder, cols)
            with ZipFile(path) as z:
                sheet = E.fromstring(z.read('xl/worksheets/goldmetal2.xml'))
            data = sheet.find(f'{{{NS}}}sheetData')
            self.assertEqual(len(data[2][0]), 0)
            self.assertEqual(len(data[2][3]), 0)
