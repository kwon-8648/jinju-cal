"""Append a purchase to an existing OOXML workbook without rebuilding old cells."""
import hashlib
import json
import posixpath
from copy import deepcopy
from lxml import etree as E
from zipfile import ZipFile

N = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
C = 'http://schemas.openxmlformats.org/package/2006/content-types'
MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'


def parse_xml(data):
    if isinstance(data, str):
        data = data.encode('utf-8')
    return E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True))


def validate_compatibility(contents):
    # Namespace names inside attribute values must remain bound in their scope.
    for name, data in contents.items():
        if not name.endswith(('.xml', '.rels')):
            continue
        root = parse_xml(data)
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            values = [node.get(f'{{{MC}}}{attr}', '') for attr in
                      ('Ignorable', 'MustUnderstand', 'ProcessContent', 'PreserveElements', 'PreserveAttributes')]
            if node.tag == f'{{{MC}}}Choice':
                values.append(node.get('Requires', ''))
            for value in values:
                for token in value.split():
                    prefix = token.split(':', 1)[0]
                    if prefix not in node.nsmap:
                        raise ValueError('엑셀 파일의 호환성 정보가 이미 손상되어 저장을 중단했습니다. '
                                         '엑셀에서 복구 후 다른 이름으로 보관하거나 새 저장 폴더를 선택해주세요.')


def xml(value):
    return E.tostring(value, encoding='utf-8', xml_declaration=True)


def merge_styles(old, new):
    def merge_group(name):
        source, target = new.find(f'{{{N}}}{name}'), old.find(f'{{{N}}}{name}')
        mapping = {}
        for i, item in enumerate(source):
            key = E.tostring(item)
            match = next((j for j, existing in enumerate(target) if E.tostring(existing) == key), None)
            if match is None:
                match = len(target)
                target.append(deepcopy(item))
            mapping[i] = match
        target.set('count', str(len(target)))
        return mapping

    target = old.find(f'{{{N}}}numFmts')
    if target is None:
        target = E.Element(f'{{{N}}}numFmts', count='0')
        old.insert(0, target)
    formats = {}
    for item in new.find(f'{{{N}}}numFmts'):
        original = int(item.get('numFmtId'))
        match = next((c for c in target if c.get('formatCode') == item.get('formatCode')), None)
        if match is None:
            new_id = max([163] + [int(c.get('numFmtId')) for c in target]) + 1
            item.set('numFmtId', str(new_id))
            target.append(deepcopy(item))
            match = item
        formats[original] = int(match.get('numFmtId'))
    target.set('count', str(len(target)))
    fonts, fills, borders = (merge_group(group) for group in ('fonts', 'fills', 'borders'))
    for item in new.find(f'{{{N}}}cellXfs'):
        for attr, mapping in (('fontId', fonts), ('fillId', fills), ('borderId', borders), ('numFmtId', formats)):
            value = int(item.get(attr, '0'))
            item.set(attr, str(mapping.get(value, value)))
    return merge_group('cellXfs')


def accumulate(path, generated, columns):
    signature = hashlib.sha256(json.dumps([(c['key'], c['label']) for c in columns], ensure_ascii=False).encode()).hexdigest()
    incoming = parse_xml(generated['xl/worksheets/sheet1.xml'])
    if path.exists():
        with ZipFile(path) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
        validate_compatibility(contents)
        styles = parse_xml(contents['xl/styles.xml'])
        mapping = merge_styles(styles, parse_xml(generated['xl/styles.xml']))
        for cell in incoming.iter(f'{{{N}}}c'):
            cell.set('s', str(mapping[int(cell.get('s', '0'))]))
        contents['xl/styles.xml'] = xml(styles)
    else:
        contents = {name: value.encode('utf-8') for name, value in generated.items()}
    workbook = parse_xml(contents['xl/workbook.xml'])
    sheets = workbook.find(f'{{{N}}}sheets')
    names = workbook.find(f'{{{N}}}definedNames')
    if names is None:
        names = E.SubElement(workbook, f'{{{N}}}definedNames')
    last = sheets[-1]
    schema_name = '_GoldMetalSchema_' + last.get('sheetId')
    prior = next((d.text for d in names if d.get('name') == schema_name), None)
    rels = parse_xml(contents['xl/_rels/workbook.xml.rels'])
    if not path.exists():
        target_path = 'xl/worksheets/sheet1.xml'
        E.SubElement(names, f'{{{N}}}definedName', name=schema_name, hidden='1').text = '"' + signature + '"'
        contents[target_path] = xml(incoming)
    elif prior == '"' + signature + '"':
        relationship = next(r for r in rels if r.get('Id') == last.get(f'{{{R}}}id'))
        target = relationship.get('Target')
        target_path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        sheet = parse_xml(contents[target_path])
        rows = sheet.find(f'{{{N}}}sheetData')
        offset = max((int(r.get('r')) for r in rows), default=1)
        extra = list(incoming.find(f'{{{N}}}sheetData'))[1:]
        if offset + len(extra) > 1048576:
            raise ValueError('엑셀 최대 행 수에 도달했습니다. 새 저장 폴더를 선택해주세요.')
        for i, row in enumerate(extra, offset + 1):
            row.set('r', str(i))
            for cell in row:
                column = ''.join(c for c in cell.get('r') if c.isalpha())
                cell.set('r', column + str(i))
            rows.append(row)
        end = incoming.find(f'{{{N}}}dimension').get('ref').split(':')[-1]
        column = ''.join(c for c in end if c.isalpha())
        area = f'A1:{column}{offset + len(extra)}'
        sheet.find(f'{{{N}}}dimension').set('ref', area)
        auto_filter = sheet.find(f'{{{N}}}autoFilter')
        if auto_filter is not None:
            auto_filter.set('ref', area)
        contents[target_path] = xml(sheet)
    else:
        number = max(int(s.get('sheetId')) for s in sheets) + 1
        target_path = f'xl/worksheets/goldmetal{number}.xml'
        while target_path in contents:
            number += 1
            target_path = f'xl/worksheets/goldmetal{number}.xml'
        rid = 'rIdGoldMetal' + str(number)
        while any(r.get('Id') == rid for r in rels):
            rid += 'x'
        sheet_name = f'매입내역_{number}'
        while any(s.get('name') == sheet_name for s in sheets):
            sheet_name += '_'
        E.SubElement(sheets, f'{{{N}}}sheet', name=sheet_name, sheetId=str(number), attrib={f'{{{R}}}id': rid})
        E.SubElement(rels, f'{{{P}}}Relationship', Id=rid, Type=R+'/worksheet', Target=target_path[3:])
        E.SubElement(names, f'{{{N}}}definedName', name='_GoldMetalSchema_'+str(number), hidden='1').text = '"'+signature+'"'
        types = parse_xml(contents['[Content_Types].xml'])
        E.SubElement(types, f'{{{C}}}Override', PartName='/'+target_path, ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
        contents['[Content_Types].xml'] = xml(types)
        contents[target_path] = xml(incoming)
    contents['xl/workbook.xml'] = xml(workbook)
    contents['xl/_rels/workbook.xml.rels'] = xml(rels)
    validate_compatibility(contents)
    return contents
