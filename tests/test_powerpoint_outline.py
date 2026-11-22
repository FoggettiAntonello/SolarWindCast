"""Synthetic checks that PowerPoint extraction preserves chart data and unit labels."""

from pathlib import Path
from zipfile import ZipFile

from solarwindcast.powerpoint_outline import extract_slides, finalize_powerpoint


def test_outline_keeps_precision_text_and_native_table_cells() -> None:
    html = '''<section class="slide"><div class="copy"><p class="step">01 / Prova</p>
    <h1>Un risultato &amp; il suo limite</h1><p class="takeaway">MAE invariato.</p></div>
    <figure><svg class="chart"><title>Copertura</title><text>Nominale 80%</text>
    <rect data-value="79.32123456789" data-nominal="80" fill="#087e8b"/>
    <text class="value">79,32</text><text class="unit">%</text></svg>
    <table><caption>Campione</caption><tr><th>Ore</th><td>24</td></tr></table>
    <figcaption>Dati sintetici, UTC.</figcaption></figure></section>'''
    row = extract_slides(html)[0]
    assert row['title'] == 'Un risultato & il suo limite'
    assert row['charts'][0]['rows'][0]['value'] == 79.32123456789
    assert row['charts'][0]['rows'][0]['nominal'] == 80
    assert row['tables'][0]['rows'] == [['Ore', '24']]
    assert row['paragraphs'][0]['emphasis'] is True
    assert row['caption'] == 'Dati sintetici, UTC.'


def test_finalization_normalizes_only_label_formats_and_project_metadata(tmp_path: Path) -> None:
    source, output = tmp_path/'source.pptx', tmp_path/'final.pptx'
    chart = b'<c:chartSpace xmlns:c="fixture"><c:chart><c:dLbls><c:numFmt formatCode="#.##000" sourceLinked="1"/></c:dLbls><c:v>79.32123456789</c:v></c:chart></c:chartSpace>'
    with ZipFile(source, 'w') as package:
        package.writestr('ppt/charts/chart1.xml', chart)
        package.writestr('docProps/core.xml', '<dc:creator>Fixture author</dc:creator>')
        package.writestr('ppt/slides/slide1.xml', '<slide>Fixture content</slide>')
    finalize_powerpoint(source, output)
    with ZipFile(output) as package:
        repaired = package.read('ppt/charts/chart1.xml')
        assert b'formatCode="#,##0.00"' in repaired and b'sourceLinked="0"' in repaired
        assert b'79.32123456789' in repaired  # Numeric evidence must not be rounded or changed.
        assert b'SolarWindCast' in package.read('docProps/core.xml')
        assert package.read('ppt/slides/slide1.xml') == b'<slide>Fixture content</slide>'
