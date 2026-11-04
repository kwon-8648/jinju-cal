import tempfile
import unittest
from compatibility_checks import check_excel_roundtrip

class ExcelCompatibilityTests(unittest.TestCase):
    def test_excel_edited_workbook_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertTrue(all(check_excel_roundtrip(folder).values()))
