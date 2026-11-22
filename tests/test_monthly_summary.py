"""Synthetic energy integration checks, including leap years, DST and genuinely missing data."""

import json
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.monthly_summary import monthly_energy, save_monthly_report


@pytest.mark.parametrize("start,end,zone,hours", [
    ("2024-02-01", "2024-03-01", "UTC", 696),
    ("2025-02-01", "2025-03-01", "UTC", 672),
    ("2024-03-01", "2024-04-01", "Europe/Rome", 743),
    ("2024-10-01", "2024-11-01", "Europe/Rome", 745),
])
def test_calendar_energy_uses_actual_duration(start: str, end: str, zone: str, hours: int) -> None:
    index = pd.date_range(start, end, inclusive="left", freq="1h", tz=zone).tz_convert("UTC")
    index.name = "timestamp_utc"
    dataset = TimeSeriesDataset(pd.DataFrame({"target": 10.}, index=index),
        DatasetSpec("solar", "1h", (), (), (), "synthetic calendar fixture"))
    before = dataset.frame.copy(deep=True)
    row = monthly_energy(dataset, zone).iloc[0]
    assert row.expected_intervals == hours
    assert row.energy_mwh == 10 * hours and row.complete
    pd.testing.assert_frame_equal(dataset.frame, before)


def test_missing_or_partial_month_is_not_reported_as_complete() -> None:
    index = pd.date_range("2025-01-01", "2025-02-01", inclusive="left", freq="1h", tz="UTC", name="timestamp_utc")
    frame = pd.DataFrame({"target": 10.}, index=index)
    spec = DatasetSpec("wind", "1h", (), (), (), "synthetic missing fixture")
    frame.iloc[0, 0] = float("nan")
    row = monthly_energy(TimeSeriesDataset(frame, spec), "UTC").iloc[0]
    assert not row.complete and pd.isna(row.energy_mwh)
    row = monthly_energy(TimeSeriesDataset(frame.iloc[1:].copy(), spec), "UTC").iloc[0]
    assert not row.complete and row.valid_intervals == 743
    assert row.expected_intervals == 744
    frame.iloc[0, 0] = -5.
    row = monthly_energy(TimeSeriesDataset(frame, spec), "UTC").iloc[0]
    assert row.negative_intervals == 1
    assert row.energy_mwh == 10 * 743 - 5


@pytest.mark.parametrize("missing", [False, True])
def test_monthly_html_provenance_units_and_no_overwrite(tmp_path: Path, missing: bool) -> None:
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    index = pd.date_range("2025-01-01", "2025-02-01", inclusive="left", freq="1h", tz="UTC", name="timestamp_utc")
    value = float("nan") if missing else 10.
    pd.DataFrame({"target": value}, index=index).to_parquet(prepared / "solar.parquet")
    quality = {"solar": {"target": "solar", "frequency": "1h", "provenance": "synthetic", "unit": "MW"}}
    (prepared / "quality.json").write_text(json.dumps(quality))
    hashes = {name: sha256((prepared / name).read_bytes()).hexdigest() for name in ("solar.parquet", "quality.json")}
    (prepared / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}))
    output = tmp_path / "report"
    page = save_monthly_report(prepared, output, "UTC", "2025-01-01T00:00Z", "2025-02-01T00:00Z")
    summary = json.loads((output / "monthly_energy.json").read_text())
    assert summary["forecast_computed"] is False
    assert summary["series"]["solar"]["records"][0]["energy_mwh"] == (None if missing else 7440)
    assert summary["series"]["solar"]["complete_test_months"] == int(not missing)
    text = page.read_text(encoding="utf-8")
    assert "<svg" in text and "non previsioni" in text and "MWh" in text
    assert "<script src" not in text
    with pytest.raises(FileExistsError):
        save_monthly_report(prepared, output, "UTC", "2025-01-01T00:00Z", "2025-02-01T00:00Z")
    (prepared / "quality.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        save_monthly_report(prepared, tmp_path / "invalid", "UTC", "2025-01-01T00:00Z", "2025-02-01T00:00Z")
