"""Portable XLSX export using standard OOXML; no Excel installation required."""
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
import re
import uuid
import os
from .xlsx_append import accumulate
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile, ZIP_DEFLATED

from .core import parse_decimal

DEFAULT_COLUMNS = [
    ("timestamp", "저장일시"), ("source", "시세 출처"),
    ("gold_price", "금 시세"), ("silver_price", "은 시세"), ("platinum_price", "백금 시세"),
    ("metal_type", "금속"), ("item_name", "기준품목명"), ("unit_price", "단가(g)"),
    ("input_weight", "입고중량(g)"), ("input_don", "입고중량(돈)"),
    ("deduction_weight", "차감중량(g)"), ("deduction_price", "차감금액"),
    ("customer_price", "고객매입가"), ("total_customer_price", "고객별 매입가 합계"),
    ("multiplier", "Multiplier"),
]
MONEY = {"gold_price", "silver_price", "platinum_price", "unit_price", "deduction_price", "customer_price", "total_customer_price"}
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def grams_to_don(value):
    # A don is a mass unit: always 3.75g, independent of price divisors.
    return (parse_decimal(value) / Decimal("3.75")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_columns(saved=None):
    definitions = dict(DEFAULT_COLUMNS)
    result, seen = [], set()
    for col in saved or []:
        if isinstance(col, dict) and col.get("key") in definitions and col["key"] not in seen:
            key = col["key"]
            label = str(col.get("label") or definitions[key]).strip()[:60]
            result.append(dict(key=key, label=label or definitions[key], enabled=bool(col.get("enabled", True))))
            seen.add(key)
    for key, label in DEFAULT_COLUMNS:
        if key not in seen:
            result.append(dict(key=key, label=label, enabled=key != "multiplier"))
    return result


def clean_text(value):
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value))


def col_name(index):
    result = ""
    while index:
        index, rest = divmod(index - 1, 26)
        result = chr(65 + rest) + result
    return result


def export_purchase(rows, prices, source, total, folder, columns, now=None):
    selected = [c for c in normalize_columns(columns) if c["enabled"]]
    if not selected:
        raise ValueError("저장할 항목을 하나 이상 선택해주세요.")
    entered = [r for r in rows if parse_decimal(r.get("input_weight")) > 0]
    if not entered:
        raise ValueError("입고중량이 0보다 큰 품목이 없습니다.")
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    weekday = "월화수목금토일"[now.weekday()]
    date_format = f'yyyy.mm.dd"({weekday})" hh:mm'
    serial_date = Decimal(str((now - datetime(1899, 12, 30)).total_seconds())) / Decimal(86400)
    data = []
    for row in entered:
        values = dict(row, timestamp=serial_date, source=source,
            gold_price=prices.get("GOLD", 0), silver_price=prices.get("SILVER", 0),
            platinum_price=prices.get("PLATINUM", 0), total_customer_price=total,
            input_don=grams_to_don(row.get("input_weight")))
        values["metal_type"] = {"GOLD": "금", "SILVER": "은", "PLATINUM": "백금"}.get(row.get("metal_type"), row.get("metal_type", ""))
        data.append(values)

    def text_cell(ref, value, style):
        return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t xml:space="preserve">{escape(clean_text(value))}</t></is></c>'

    sheet_rows = ['<row r="1" ht="30" customHeight="1">' + "".join(
        text_cell(f"{col_name(i)}1", col["label"], 1) for i, col in enumerate(selected, 1)) + '</row>']
    for index, values in enumerate(data, 2):
        cells = []
        for i, col in enumerate(selected, 1):
            key, ref = col["key"], f"{col_name(i)}{index}"
            value = values.get(key, "")
            style = 3 if key in MONEY else 4 if key == "input_don" else 5 if key in ("input_weight", "deduction_weight", "multiplier") else 6 if key == "timestamp" else 2
            if index > 2 and key in ("timestamp", "total_customer_price"):
                # Each call is a separate purchase, even within the same minute.
                # An empty cell must stay empty, rather than becoming numeric zero.
                cells.append(f'<c r="{ref}" s="{style}"/>')
            elif style == 2:
                cells.append(text_cell(ref, value, style))
            else:
                number = parse_decimal(value)
                if not number.is_finite():
                    raise ValueError("저장할 값에 올바르지 않은 숫자가 있습니다.")
                cells.append(f'<c r="{ref}" s="{style}"><v>{number}</v></c>')
        sheet_rows.append(f'<row r="{index}" ht="24" customHeight="1">' + "".join(cells) + '</row>')
    widths = []
    for i, col in enumerate(selected, 1):
        width = 28 if col["key"] == "timestamp" else 46 if col["key"] == "item_name" else 30 if col["key"] == "source" else 24 if col["key"] == "total_customer_price" else 18
        width = max(width, min(60, sum(2 if ord(c) > 127 else 1 for c in col["label"]) + 3))
        widths.append(f'<col min="{i}" max="{i}" width="{width}" customWidth="1"/>')
    area = f'A1:{col_name(len(selected))}{len(data)+1}'
    sheet = f'''<worksheet xmlns="{NS}"><dimension ref="{area}"/>
    <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
    <sheetFormatPr defaultRowHeight="24"/><cols>{''.join(widths)}</cols><sheetData>{''.join(sheet_rows)}</sheetData><autoFilter ref="{area}"/></worksheet>'''
    styles = f'''<styleSheet xmlns="{NS}"><numFmts count="2"><numFmt numFmtId="164" formatCode={quoteattr(date_format)}/><numFmt numFmtId="165" formatCode="0.######"/></numFmts>
    <fonts count="2"><font><sz val="11"/><name val="맑은 고딕"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="맑은 고딕"/></font></fonts>
    <fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF175591"/><bgColor indexed="64"/></patternFill></fill></fills>
    <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
    <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
    <cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>'''
    for fmt in (0, 3, 2, 165, 164):
        styles += f'<xf numFmtId="{fmt}" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf>'
    styles += '</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>'
    contents = {
        '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml': f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="매입내역" sheetId="1" r:id="rId1"/></sheets></workbook>',
        'xl/_rels/workbook.xml.rels': '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/styles.xml': styles, 'xl/worksheets/sheet1.xml': sheet,
    }
    folder = Path(folder).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / '매입내역.xlsx'
    temporary = folder / ('.매입내역_' + uuid.uuid4().hex + '.tmp')
    lock = folder / '.매입내역.xlsx.lock'
    if (folder / '~$매입내역.xlsx').exists():
        raise PermissionError('매입내역.xlsx를 엑셀에서 닫은 뒤 다시 저장해주세요.')
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        raise PermissionError('다른 저장 작업이 진행 중입니다. 잠시 후 다시 저장해주세요.')
    try:
        original = path.stat() if path.exists() else None
        contents = accumulate(path, contents, selected)
        with ZipFile(temporary, 'w', ZIP_DEFLATED) as archive:
            for name, xml in contents.items():
                archive.writestr(name, xml)
        current = path.stat() if path.exists() else None
        if (original is None) != (current is None) or (original and (original.st_mtime_ns, original.st_size) != (current.st_mtime_ns, current.st_size)):
            raise PermissionError('저장 중 엑셀 파일이 변경되었습니다. 파일을 닫고 다시 저장해주세요.')
        temporary.replace(path)
    except PermissionError as error:
        raise PermissionError('엑셀 파일을 닫고 저장 폴더의 쓰기 권한을 확인한 뒤 다시 저장해주세요.') from error
    finally:
        temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
    return path
