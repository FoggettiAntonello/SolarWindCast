"""Synthetic quality checks retained independently of the removed API prototypes."""

import pandas as pd

from solarwindcast.quality import report


def test_report_detects_missing_edges_and_nulls() -> None:
    index = pd.date_range("2026-01-01", periods=4, freq="h", tz="UTC")
    frame = pd.DataFrame({"wind": [1, None]}, index=index[1:3])
    result = report(frame, index[0], index[0] + pd.Timedelta(hours=4), "1h")
    assert result["missing_timestamps"] == 2
    assert result["columns"][0]["missing"] == 1
    assert result["complete"] is False


def test_report_detects_duplicates_offgrid_and_nonfinite() -> None:
    frame = pd.DataFrame({"value": [1, float("inf"), 2]}, index=pd.to_datetime([
        "2026-01-01T00:00Z", "2026-01-01T00:00Z", "2026-01-01T00:30Z",
    ]))
    result = report(frame, "2026-01-01T00:00Z", "2026-01-01T01:00Z", "1h")
    assert result["duplicate_timestamps"] == 1
    assert result["off_grid_timestamps"] == 1
    assert result["columns"][0]["non_finite"] == 1
    assert result["complete"] is False


def test_negative_temperature_is_not_automatically_invalid() -> None:
    frame = pd.DataFrame({"temperature": [-4, 0]}, index=pd.date_range(
        "2026-01-01", periods=2, freq="h", tz="UTC"))
    result = report(frame, "2026-01-01T00:00Z", "2026-01-01T02:00Z", "1h")
    assert result["complete"] is True
    assert result["columns"][0]["negative"] == 1
    assert report(frame, "2026-01-01T00:00Z", "2026-01-01T02:00Z")["complete"] is False
