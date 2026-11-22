"""Synthetic common-grid checks for missing values, target identity and immutable exports."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.real_preparation import (
    complete_interval_mean,
    prepare_targets,
    save_prepared,
)


def dataset(values: list[float], frequency: str = "15min", target: str = "solar") -> TimeSeriesDataset:
    """Build a target-only fixture on an explicit UTC interval-start grid."""
    index = pd.date_range("2025-01-01", periods=len(values), freq=frequency, tz="UTC", name="timestamp_utc")
    return TimeSeriesDataset(pd.DataFrame({"target": values}, index=index),
                             DatasetSpec(target, frequency, (), (), (), "synthetic"))


@pytest.mark.parametrize("target", ["solar", "wind", "load", "residual_load"])
def test_complete_mean_conserves_energy_and_target_identity(target: str) -> None:
    original = dataset([10., 20., 30., 40., -10., 0., 10., 20.], target=target)
    before = original.frame.copy(deep=True)
    output = complete_interval_mean(original, "1h")
    assert output.frame.target.tolist() == [25., 5.]
    assert output.frame.target.sum() == original.frame.target.sum() * .25
    assert output.spec.target == target
    pd.testing.assert_frame_equal(original.frame, before)


def test_incomplete_hour_is_nan_instead_of_mean_of_remaining_values() -> None:
    output = complete_interval_mean(dataset([10., 20., np.nan, 40., 1., 1., 1., 1.]), "1h")
    assert pd.isna(output.frame.target.iloc[0])
    assert output.frame.target.iloc[1] == 1


def test_upsampling_and_partial_boundaries_are_rejected() -> None:
    with pytest.raises(ValueError, match="espansione"):
        complete_interval_mean(dataset([1., 2.], "1h"), "15min")
    with pytest.raises(ValueError, match="confini"):
        complete_interval_mean(dataset([1., 2., 3.]), "1h")
    original = dataset([1., 2., 3., 4.], "1h")
    pd.testing.assert_frame_equal(complete_interval_mean(original, "1h").frame, original.frame)


def native_report(root: Path) -> Path:
    """A one-hour block followed by a quarter-hour block, including a genuine missing value."""
    folder = root / "native"
    folder.mkdir()
    chunks = []
    segments = []
    for start, frequency, values in [("2025-01-01T00:00:00+00:00", "1h", [20.]),
                                     ("2025-01-01T01:00:00+00:00", "15min", [10., None, 30., 40.])]:
        frame = dataset([1.])
        frame.frame = pd.DataFrame({"solar": values, "wind": [1.] * len(values)},
            index=pd.date_range(start, periods=len(values), freq=frequency, name="timestamp_utc"))
        end = frame.frame.index[-1] + pd.Timedelta(frequency)
        chunks.append({"start_utc": start, "end_exclusive_utc": end.isoformat(), "native_frequency": frequency})
        records = json.loads(frame.frame.reset_index().to_json(orient="records", date_format="iso"))
        segments.append({"start_utc": start, "native_frequency": frequency, "records": records})
    files = {"analysis.json": json.dumps({"chunks": chunks}), "native_series.json": json.dumps(segments),
             "presentazione.html": "<html>synthetic fixture only</html>"}
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    manifest = {name: sha256((folder / name).read_bytes()).hexdigest() for name in files}
    (folder / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": manifest}))
    return folder


def test_native_hashes_mixed_grids_and_complete_component_sum(tmp_path: Path) -> None:
    source = native_report(tmp_path)
    rules = [{"name": "solar", "target": "solar", "components": ["solar"]},
             {"name": "explicit_sum", "target": "residual_load", "components": ["solar", "wind"]}]
    output = prepare_targets(source, rules, "1h")
    assert output["solar"].frame.target.iloc[0] == 20
    assert pd.isna(output["solar"].frame.target.iloc[1])
    assert output["explicit_sum"].frame.target.iloc[0] == 21
    assert pd.isna(output["explicit_sum"].frame.target.iloc[1])
    (source / "analysis.json").write_text("{}")
    with pytest.raises(ValueError, match="Hash"):
        prepare_targets(source, rules, "1h")


def test_entirely_absent_json_component_stays_numeric_nan(tmp_path: Path) -> None:
    source = native_report(tmp_path)
    path = source / "native_series.json"
    segments = json.loads(path.read_text())
    for segment in segments:
        for record in segment["records"]:
            record["solar"] = None
    path.write_text(json.dumps(segments))
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files_sha256"]["native_series.json"] = sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest))
    output = prepare_targets(source, [{"name": "solar", "target": "solar", "components": ["solar"]}], "1h")
    assert output["solar"].frame.target.isna().all()
    assert len(output["solar"].frame) == 2


@pytest.mark.parametrize("monthly", [False, True])
def test_exports_roundtrip_and_reject_existing_output(tmp_path: Path, monthly: bool) -> None:
    values = complete_interval_mean(dataset([1., np.nan, 2., 3.]), "1h")
    output, report = tmp_path / "prepared", tmp_path / "report"
    proposal = ({"objective": "next_calendar_month_total_energy"} if monthly else
                {"horizon_hours": 24, "context_hours": 168, "stride_hours": 24})
    page = save_prepared({"solar": values}, output, report, proposal)
    pd.testing.assert_frame_equal(pd.read_parquet(output / "solar.parquet"), values.frame, check_freq=False)
    quality = json.loads((output / "quality.json").read_text())
    assert quality["solar"]["missing"] == 1
    assert "Nessuna previsione eseguita" in page.read_text(encoding="utf-8")
    if monthly:
        assert "energia totale del prossimo mese" in page.read_text(encoding="utf-8")
        assert "previsione di 24 ore" not in page.read_text(encoding="utf-8")
    for folder in (output, report):
        manifest = json.loads((folder / "manifest.json").read_text())
        for name, digest in manifest["files_sha256"].items():
            assert sha256((folder / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        save_prepared({"solar": values}, output, report, proposal)
