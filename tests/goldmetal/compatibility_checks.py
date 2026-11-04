"""Regression for Excel-authored namespace declarations and column formatting."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from excel_export import export_purchase, normalize_columns
from xlsx_append import N, MC, parse_xml, validate_compatibility


def check_excel_roundtrip(folder):
    folder = Path(folder) / 'excel_roundtrip'
    row = dict(item_name='검증 골드바', input_weight='1', customer_price=100000)
    cols = normalize_columns()
    p = export_purchase([row], {}, '검증', 100000, folder, cols)
    ns = {'mc': MC, 'x14ac':'http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac',
          'xr':'http://schemas.microsoft.com/office/spreadsheetml/2014/revision',
          'x15':'http://schemas.microsoft.com/office/spreadsheetml/2010/11/main'}
    with ZipFile(p) as z:
        parts = {name:z.read(name) for name in z.namelist()}
    edited = {}
    for name in ('xl/workbook.xml','xl/styles.xml','xl/worksheets/sheet1.xml'):
        root = parse_xml(parts[name])
        expanded = E.Element(root.tag, nsmap={**root.nsmap, **ns})
        expanded.attrib.update(root.attrib)
        expanded.set(f'{{{MC}}}Ignorable', 'x14ac xr x15')
        for child in list(root):
            expanded.append(child)
        if 'sheet1' in name:
            expanded.find(f'{{{N}}}cols')[0].set('width','37.25')
            expanded.find(f'{{{N}}}sheetFormatPr').set(f'{{{ns["x14ac"]}}}dyDescent','0.45')
        if name=='xl/workbook.xml':
            alt=E.SubElement(expanded,f'{{{MC}}}AlternateContent')
            choice=E.SubElement(alt,f'{{{MC}}}Choice',Requires='x15')
            E.SubElement(choice,f'{{{ns["x15"]}}}workbookPr',chartTrackingRefBase='1')
        edited[name]=E.tostring(expanded)
        parts[name]=edited[name]
    with ZipFile(p,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items():
            z.writestr(name,data)
    validate_compatibility(parts)
    # Prove this fixture catches the original ElementTree failure.
    from xml.etree import ElementTree as Old
    broken=Old.tostring(Old.fromstring(edited['xl/workbook.xml']))
    try:
        validate_compatibility({'xl/workbook.xml':broken})
        raise AssertionError('Regression fixture did not detect old serializer')
    except ValueError:
        pass
    for _ in range(3):
        export_purchase([row],{},'検証',100000,folder,cols)
        with ZipFile(p) as z:
            saved={name:z.read(name) for name in z.namelist()}
        validate_compatibility(saved)
        for name in edited:
            root=parse_xml(saved[name])
            for prefix,uri in ns.items():
                assert root.nsmap[prefix]==uri
        sheet=parse_xml(saved['xl/worksheets/sheet1.xml'])
        assert sheet.find(f'{{{N}}}cols')[0].get('width')=='37.25'
        assert sheet.find(f'{{{N}}}sheetFormatPr').get(f'{{{ns["x14ac"]}}}dyDescent')=='0.45'
    assert len(sheet.find(f'{{{N}}}sheetData'))==5
    cols.reverse()
    export_purchase([row],{},'검증',100000,folder,cols)
    with ZipFile(p) as z:
        validate_compatibility({name:z.read(name) for name in z.namelist()})
        assert z.read('xl/worksheets/sheet1.xml')==saved['xl/worksheets/sheet1.xml']
    # A pre-existing damaged file must never be overwritten.
    saved['xl/workbook.xml']=broken
    with ZipFile(p,'w',ZIP_DEFLATED) as z:
        for name,data in saved.items():
            z.writestr(name,data)
    before=p.read_bytes()
    try:
        export_purchase([row],{},'검증',100000,folder,cols)
        raise AssertionError('Damaged workbook accepted')
    except ValueError:
        assert p.read_bytes()==before
    return {'excel_namespaces_preserved':True,'width_and_format_preserved':True,
            'three_appends_passed':True,'schema_change_preserved':True,'damaged_input_unchanged':True}
