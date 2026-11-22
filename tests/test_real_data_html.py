"""Synthetic rendering checks for self-contained charts, nulls and escaped provenance."""

import pandas as pd

from solarwindcast.real_data_html import _fmt, render_html
from solarwindcast.real_data_report import InspectionResult


def test_html_embeds_charts_and_distinguishes_observations_from_forecasts() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="15min", tz="UTC", name="timestamp_utc")
    frame = pd.DataFrame({"solar": [0., 10., None, 0.]}, index=index)
    summary = {"start_utc": index[0].isoformat(), "end_exclusive_utc": "2026-01-01T01:00:00Z",
        "native_frequency": "15min", "duration_hours": 1., "generated_at_utc": "2026-01-02T00:00:00Z",
        "statistics": {"solar": {"label": "Solare", "valid": 3, "expected": 4, "missing": 1,
            "mean_mw": 10 / 3, "max_mw": 10., "energy_mwh": None, "raw_points": 3,
            "represented_intervals": 4, "negative": 0}},
        "daily": [{"date_utc": "2026-01-01", "component": "solar", "valid": 3,
                   "expected": 4, "coverage": .75}],
        "sources": [{"file": "<script>malicious</script>", "retrieved_utc": "2026-01-02T00:00:00Z",
                     "revision": "1", "sha256": "a" * 64}]}
    original = frame.copy(deep=True)
    page = render_html(InspectionResult(frame, summary))
    assert page.count("<svg") == 2
    assert "75%" in page and "<script>malicious</script>" not in page
    assert "&lt;script&gt;malicious&lt;/script&gt;" in page
    assert "non sono state calcolate previsioni" in page
    assert '<script src=' not in page and '<link rel="stylesheet"' not in page
    assert "aria-selected" in page and "ArrowRight" in page
    pd.testing.assert_frame_equal(frame, original)
    assert _fmt(None) == "—" and _fmt(1629.) == "1.629,0"
