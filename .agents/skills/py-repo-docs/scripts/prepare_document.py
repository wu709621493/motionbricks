#!/usr/bin/env python3
"""Prepare and verify a paragraph-only DOCX archive without changing its source."""

import argparse
import hashlib
import io
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile

NS = {
    'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'cp': 'http://schemas.openxmlformats.org/package/2006/metadata/core-properties',
}
W = '{' + NS['w'] + '}'
R = '{' + NS['r'] + '}'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def convert(data):
    """Return Markdown and embedded version; decline unsupported structures."""
    with ZipFile(io.BytesIO(data)) as z:
        root = ET.fromstring(z.read('word/document.xml'))
        forbidden = ('tbl', 'drawing', 'pict', 'footnoteReference', 'endnoteReference',
                     'commentRangeStart', 'ins', 'del', 'moveFrom', 'moveTo',
                     'numPr', 'fldChar', 'fldSimple', 'sdt', 'altChunk', 'sym',
                     'object', 'smartTag', 'customXml')
        for tag in forbidden:
            if root.find('.//w:' + tag, NS) is not None:
                raise ValueError('Unsupported DOCX structure: ' + tag)
        for sect in root.findall('.//w:sectPr', NS):
            if any(e.tag in (W+'headerReference', W+'footerReference') for e in sect):
                raise ValueError('Headers or footers need a document-aware conversion')
        rels = {}
        relpath = 'word/_rels/document.xml.rels'
        if relpath in z.namelist():
            for e in ET.fromstring(z.read(relpath)):
                if e.get('Type', '').endswith('/hyperlink'):
                    target = e.get('Target', '')
                    if e.get('TargetMode') != 'External' or not target.startswith(('https://', 'http://')):
                        raise ValueError('Unsupported hyperlink target')
                    rels[e.get('Id')] = target
        embedded = ''
        if 'docProps/core.xml' in z.namelist():
            embedded = ET.fromstring(z.read('docProps/core.xml')).findtext('cp:version', '', NS)

        def render(el):
            if el.tag == W+'t':
                return el.text or ''
            if el.tag == W+'tab':
                return '    '
            if el.tag == W+'br':
                return '' if el.get(W+'type') == 'page' else '\n'
            if el.tag == W+'hyperlink':
                rid = el.get(R+'id')
                if rid not in rels:
                    raise ValueError('Missing or unsupported hyperlink relationship')
                label = ''.join(render(e) for e in el)
                target = quote(rels[rid], safe=':/?&=#%+@;,$!~*-._')
                return '[' + label + '](' + target + ')'
            return ''.join(render(e) for e in el)

        blocks = []
        for para in root.findall('w:body/w:p', NS):
            text = render(para).strip()
            if not text:
                continue
            style = para.find('w:pPr/w:pStyle', NS)
            style_id = style.get(W+'val', '') if style is not None else ''
            if style_id == 'Title':
                text = '# ' + ' '.join(text.splitlines())
            elif re.fullmatch(r'Heading[1-6]', style_id):
                text = '#' * (int(style_id[-1]) + 1) + ' ' + text
            blocks.append(text)
        if not blocks:
            raise ValueError('Document has no paragraphs')
        return '\n\n'.join(blocks) + '\n', embedded


def prepare(source, output, stem, version):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', stem) or '..' in stem:
        raise ValueError('Use a plain ASCII filename stem without traversal')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', version):
        raise ValueError('Invalid version')
    if output.exists():
        raise ValueError('Output directory already exists; source and existing archives are left unchanged')
    data = source.read_bytes()
    markdown, embedded = convert(data)
    if embedded and embedded != version:
        raise ValueError('Requested version does not match DOCX version')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.document-archive-', dir=output.parent))
    try:
        files = {stem + '.docx': data, stem + '.md': markdown.encode('utf-8')}
        for name, payload in files.items():
            (stage / name).write_bytes(payload)
        manifest = {
            'schema_version': 1, 'document_version': version,
            'conversion': 'paragraph-docx-to-markdown-v1',
            'files': [{'path': name, 'size_bytes': len(payload), 'sha256': digest(payload)}
                      for name, payload in files.items()],
        }
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return verify(output)


def verify(directory):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('conversion') != 'paragraph-docx-to-markdown-v1':
        raise ValueError('Unsupported manifest schema or converter')
    records = manifest.get('files', [])
    if len(records) != 2:
        raise ValueError('Expected one DOCX and one Markdown record')
    payloads = {}
    for item in records:
        name = item['path']
        if Path(name).name != name or name in payloads or name in ('', '.', '..'):
            raise ValueError('Unsafe or duplicate manifest path')
        payload = (directory / name).read_bytes()
        if len(payload) != item['size_bytes'] or digest(payload) != item['sha256']:
            raise ValueError('Archive checksum mismatch: ' + name)
        payloads[name] = payload
    docs = [n for n in payloads if n.endswith('.docx')]
    if len(docs) != 1 or docs[0][:-5] + '.md' not in payloads:
        raise ValueError('Expected matching DOCX and Markdown names')
    markdown, embedded = convert(payloads[docs[0]])
    if markdown.encode('utf-8') != payloads[docs[0][:-5] + '.md']:
        raise ValueError('Markdown differs from DOCX conversion')
    if embedded and embedded != manifest['document_version']:
        raise ValueError('Archive version mismatch')
    return {'status': 'PASS', 'version': manifest['document_version'], 'files': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', nargs='?', type=Path)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--stem')
    parser.add_argument('--version')
    parser.add_argument('--verify', type=Path, metavar='DIRECTORY')
    args = parser.parse_args()
    try:
        if args.verify:
            if any((args.source, args.output_dir, args.stem, args.version)):
                parser.error('--verify cannot be combined with archive creation options')
            result = verify(args.verify)
        else:
            if not all((args.source, args.output_dir, args.stem, args.version)):
                parser.error('source, --output-dir, --stem and --version are required')
            result = prepare(args.source, args.output_dir, args.stem, args.version)
    except (OSError, ValueError, KeyError, BadZipFile, ET.ParseError) as exc:
        parser.exit(1, 'DECLINE: ' + str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
