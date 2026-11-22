"""Synthetic checks for slide limits, visual evidence and retention of negative conclusions."""

from copy import deepcopy
from html.parser import HTMLParser
from xml.etree import ElementTree

from solarwindcast.portfolio_slides import (
    bars,
    energy_background_uri,
    regional_map,
    render_slides,
    sources_visual,
)


class SlidesParser(HTMLParser):
    """Count story sections and their adjacent evidence without a browser dependency."""

    def __init__(self) -> None:
        super().__init__()
        self.slides = 0
        self.figures = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == 'section' and ('class', 'slide') in attrs:
            self.slides += 1
        if tag == 'figure':
            self.figures += 1


def fixture_bundle() -> tuple[dict, dict]:
    """Build deliberately unfavorable fictional results rather than use private observations."""
    row = {'mae': 10., 'pinball': 2., 'coverage_0.8': .5, 'coverage_0.9': .6,
           'width_0.9': 30., 'origins': 6, 'cases': 144}
    models = {'baseline': row, 'hour_of_day_distribution': row,
              'timestral_5M': {**row, 'mae': 20., 'pinball': 4.},
              'timestral_5M__additive_calibrated': {**row, 'mae': 20., 'coverage_0.8': .8,
                                                 'coverage_0.9': .9, 'width_0.9': 50.}}
    final = {'timestral_28M_known_calendar__ctx24': row,
             'timestral_28M_known_calendar__ctx12__calibrated': {**row, 'mae': 30., 'pinball': 6.}}
    studies = [{'id': name, 'targets': {'solar': deepcopy(models), 'wind': deepcopy(models)}}
               for name in ('monthly_original', 'hourly_extension', 'hourly_calibration')]
    studies.append({'id': 'monthly_final', 'targets': {'wind': final}})
    studies[2]['original_exclusions'] = {'solar': [{}, {}, {}], 'wind': []}
    studies[2]['excluded_for_history'] = {'solar': 15, 'wind': 0}
    bundle = {'studies': studies, 'highlights': [
        {'target': t, 'metric': 'mae', 'change_pct': 100.} for t in ('solar', 'wind')]}
    config = {'monthly_protocol': {'context_months': 24, 'issue_lead_hours': 12},
              'hourly_pilot': {'context_hours': 672, 'assumed_delay_hours': 24},
              'hourly_calibration': {'lookback_days': 180, 'minimum_complete_origins': 20}}
    return bundle, config


def test_twelve_slides_have_adjacent_evidence_and_link_to_complete_failures() -> None:
    bundle, config = fixture_bundle()
    original = deepcopy(bundle)
    page = render_slides(bundle, config)
    parsed = SlidesParser()
    parsed.feed(page)
    assert parsed.slides == parsed.figures == 12
    assert 'details.html#complete' in page
    assert 'Criteri non superati' in page and 'nessuna promozione generale' in page
    assert '300,00' in page  # Losing final candidate must remain visibly worse than reference.
    assert '3 esclusioni originarie' in page and '15 origini solari' in page
    assert '<svg' in page and 'aria-label=' in page and 'ArrowRight' in page
    assert bundle == original


def test_svg_preserves_exact_values_and_nominal_markers() -> None:
    figure = bars([('Calibrato <fixture>', 79.32, '#087e8b')], 'Copertura', '%', [80])
    assert '79,32' in figure and 'stroke-dasharray' in figure
    assert 'Calibrato &lt;fixture&gt;' in figure
    assert 'origine delle barre: zero' in figure


def test_map_has_real_regions_and_sources_keep_weather_out_of_results() -> None:
    svg = regional_map()
    parsed = ElementTree.fromstring(svg)
    regions = {p.attrib['data-region'] for p in parsed.iter() if 'data-region' in p.attrib}
    assert len(regions) == 20 and {'Puglia', 'Calabria'} <= regions
    assert 'Non rappresenta le zone di mercato' in svg
    assert 'Openpolis' in svg and 'CC BY 4.0' in svg
    sources = sources_visual()
    assert 'ENTSO-E' in sources and 'Open-Meteo' in sources
    assert 'Meteo escluso dagli esperimenti mostrati' in sources
    assert 'src="https://' not in sources
    assert energy_background_uri().startswith('data:image/png;base64,iVBOR')
