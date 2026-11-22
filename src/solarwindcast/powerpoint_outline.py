"""Extract editable PowerPoint content from the exact HTML slides, preserving numeric precision."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from zipfile import ZipFile

from solarwindcast.portfolio_slides import sources_visual


@dataclass
class Node:
    """Small HTML tree sufficient for the project's static presentation."""

    tag: str
    attrs: dict[str, str]
    children: list[Node | str] = field(default_factory=list)

    def text(self) -> str:
        """Read text without losing apostrophes, units or non-ASCII labels."""
        return ''.join(c.text() if isinstance(c, Node) else c for c in self.children).strip()

    def find(self, tag: str, css: str | None = None) -> list[Node]:
        """Find descendants by tag and optional class token."""
        result = []
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag and (css is None or css in child.attrs.get('class', '').split()):
                    result.append(child)
                result.extend(child.find(tag, css))
        return result


class SlideParser(HTMLParser):
    """Parse static HTML without browser, network or additional packages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node('document', {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        node = Node(tag, {k: v or '' for k, v in attrs})
        self.stack[-1].children.append(node)
        if tag not in {'meta', 'link', 'img', 'br', 'hr', 'input', 'source'}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        for i in range(len(self.stack)-1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def extract_slides(html: str) -> list[dict]:
    """Extract text, native table cells and full precision chart data from rendered slides."""
    parser = SlideParser()
    parser.feed(html)
    slides = []
    for section in parser.root.find('section', 'slide'):
        copy = section.find('div', 'copy')[0]
        figure = section.find('figure')[0]
        charts = []
        for svg in figure.find('svg', 'chart'):
            texts = svg.find('text')
            labels = [t.text() for t in texts if not t.attrs.get('class')]
            rectangles = [r for r in svg.find('rect') if 'data-value' in r.attrs]
            if len(labels) != len(rectangles):
                raise ValueError('Etichette e valori del grafico non corrispondono.')
            charts.append({'title': svg.find('title')[0].text(),
                           'unit': next(t.text() for t in texts if t.attrs.get('class') == 'unit'),
                           'rows': [{'label': label, 'value': float(r.attrs['data-value']),
                                     'color': r.attrs['fill'],
                                     'nominal': float(r.attrs['data-nominal']) if r.attrs.get('data-nominal') else None}
                                    for label, r in zip(labels, rectangles, strict=True)]})
        tables = []
        for table in figure.find('table'):
            tables.append({'caption': table.find('caption')[0].text(),
                           'rows': [[cell.text() for cell in row.children
                                     if isinstance(cell, Node) and cell.tag in ('th', 'td')]
                                    for row in table.find('tr')]})
        paragraphs = [{'text': p.text(), 'emphasis': 'takeaway' in p.attrs.get('class', ''),
                       'links': [{'text': a.text(), 'href': a.attrs.get('href', '')} for a in p.find('a')]}
                      for p in copy.find('p') if 'step' not in p.attrs.get('class', '').split()]
        artwork = ('map' if figure.find('svg', 'geography') else
                   'sources' if figure.find('svg', 'sources-visual') else None)
        slides.append({'title': copy.find('h1')[0].text(), 'chapter': copy.find('p', 'step')[0].text(),
                       'paragraphs': paragraphs, 'caption': figure.find('figcaption')[0].text(),
                       'charts': charts, 'tables': tables, 'artwork': artwork})
    if not 1 <= len(slides) <= 13:
        raise ValueError('La presentazione deve contenere da una a tredici slide.')
    return slides


def finalize_powerpoint(source: Path, output: Path) -> None:
    """Normalize Office's locale-sensitive label formats and author metadata in a new file."""
    if output.exists():
        raise FileExistsError('Il PowerPoint finale esiste già.')
    with ZipFile(source) as original, ZipFile(output, 'w') as final:
        for entry in original.infolist():
            data = original.read(entry.filename)
            if re.fullmatch(r'ppt/charts/chart\d+\.xml', entry.filename):
                def label_block(match: re.Match[bytes]) -> bytes:
                    """Use invariant OOXML decimal codes, preserving namespace declarations."""
                    text = re.sub(rb'formatCode="[^"]*"', b'formatCode="#,##0.00"', match[0])
                    return re.sub(rb'sourceLinked="[^"]*"', b'sourceLinked="0"', text)
                data = re.sub(rb'<c:dLbls\b[^>]*>.*?</c:dLbls>', label_block, data, flags=re.DOTALL)
            elif entry.filename == 'docProps/core.xml':
                for tag in (b'dc:creator', b'cp:lastModifiedBy'):
                    data = re.sub(rb'(<'+tag+rb'\b[^>]*>).*?(</'+tag+rb'>)',
                                  rb'\g<1>SolarWindCast\g<2>', data, flags=re.DOTALL)
            elif entry.filename == 'docProps/app.xml':
                data = re.sub(rb'(<Company>).*?(</Company>)', rb'\g<1>\g<2>', data, flags=re.DOTALL)
            final.writestr(entry, data)


def main() -> None:
    """Write an outline in a new temporary build directory, leaving source slides unchanged."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--finalize-pptx', type=Path)
    args = parser.parse_args()
    if args.finalize_pptx:
        finalize_powerpoint(args.finalize_pptx, args.output)
        print('PowerPoint finalizzato: etichette a due decimali e metadati del progetto.')
        return
    if args.input is None:
        parser.error('--input richiesto per estrarre le slide HTML.')
    if args.output.exists():
        raise FileExistsError('Cartella di esportazione già presente.')
    slides = extract_slides(args.input.read_text(encoding='utf-8'))
    args.output.mkdir(parents=True)
    (args.output/'outline.json').write_text(json.dumps(slides, ensure_ascii=False, indent=2), encoding='utf-8')
    (args.output/'sources.svg').write_text(sources_visual().split('</svg>')[0]+'</svg>', encoding='utf-8')
    print(f'{len(slides)} slide estratte dal documento HTML; nessuna inferenza.')


if __name__ == '__main__':
    main()
