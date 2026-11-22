"""Synthetic protocol previews check calendar cutoffs, component missingness and quantile units."""

import json
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from solarwindcast.monthly_protocol import (
    fold_preview,
    load_monthly_targets,
    monthly_quantiles_to_energy,
    save_preview,
)


def monthly_fixture() -> pd.DataFrame:
    """Five calendar years, with a synthetic missing month that must remain missing."""
    index = pd.period_range("2021-11", "2026-10", freq="M", name="month")
    starts = pd.date_range("2021-11-01", periods=len(index), freq="MS", tz="UTC")
    frame = pd.DataFrame({"mean_power_mw": np.arange(len(index), dtype=float) + 10,
        "complete": True, "start_utc": [start.isoformat() for start in starts]}, index=index)
    frame.loc[pd.Period("2026-04", freq="M"), ["mean_power_mw", "complete"]] = [np.nan, False]
    return frame


def draft() -> dict[str, object]:
    """Fixture settings, no model or real-data parameters are inferred."""
    return {"context_months": 24, "unavailable_recent_months": 1,
            "minimum_valid_context_months": 12, "prediction_length_months": 2,
            "issue_lead_hours": 12, "baseline_seasonal_lag_months": 12,
            "residual_lookback_months": 24, "minimum_calibration_errors": 12}


def test_monthly_quantile_scaling_is_not_a_sum_of_hourly_quantiles() -> None:
    power = pd.Series([10., 20., 30.], index=[.1, .5, .9])
    energy = monthly_quantiles_to_energy(power, 696.)
    np.testing.assert_allclose(energy.to_numpy(), [6960., 13920., 20880.])
    pd.testing.assert_series_equal(power, pd.Series([10., 20., 30.], index=[.1, .5, .9]))
    with pytest.raises(ValueError, match="durata"):
        monthly_quantiles_to_energy(power, 0)
    with pytest.raises(ValueError, match="incrociati"):
        monthly_quantiles_to_energy(pd.Series([20., 10.], index=[.1, .9]), 720)


def test_fold_cutoff_omits_current_month_and_scores_only_target_month() -> None:
    frame = monthly_fixture()
    rows = fold_preview(frame, "2024-11-01T00:00Z", "2026-11-01T00:00Z", draft())
    first = rows[0]
    assert len(rows) == 24
    assert first["available_through_month"] == "2024-09"
    assert first["context_start_month"] == "2022-10"
    assert first["forecast_months"] == ["2024-10", "2024-11"]
    assert first["issue_utc"] == "2024-10-31T12:00:00+00:00"
    assert first["scored_forecast_index"] == 1
    assert first["eligible_calibration_pairs"] == 23
    assert first["probabilistic_baseline_input_ready"]
    assert sum(row["scorable_without_model_run"] for row in rows) == 23
    frame.loc[pd.Period("2024-10", freq="M"), "mean_power_mw"] = 1e20
    changed = fold_preview(frame, "2024-11-01T00:00Z", "2026-11-01T00:00Z", draft())
    assert changed[0] == first  # The still-open October value cannot affect November's context.


def test_insufficient_history_is_visible_not_padded_as_observations() -> None:
    rows = fold_preview(monthly_fixture(), "2021-11-01T00:00Z", "2024-11-01T00:00Z", draft())
    assert not rows[0]["context_within_observed_span"]
    assert not rows[0]["forecast_input_ready"]
    assert sum(row["forecast_input_ready"] for row in rows) == 11
    with pytest.raises(ValueError, match="coerenti"):
        fold_preview(monthly_fixture(), "2024-11", "2025-01", {**draft(), "prediction_length_months": 1})


def test_wind_sum_requires_all_components_and_verifies_input_hashes(tmp_path: Path) -> None:
    index = pd.date_range("2024-01-01", "2024-02-01", freq="1h", inclusive="left", tz="UTC", name="timestamp_utc")
    values = {"solar": 2., "wind_onshore": 1., "wind_offshore": np.nan}
    quality = {}
    for name, value in values.items():
        pd.DataFrame({"target": value}, index=index).to_parquet(tmp_path / (name + ".parquet"))
        quality[name] = {"target": "solar" if name == "solar" else "wind", "unit": "MW",
                         "frequency": "1h", "provenance": "synthetic"}
    (tmp_path / "quality.json").write_text(json.dumps(quality))
    files = {path.name: sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir() if path.is_file()}
    (tmp_path / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": files}))
    combined = load_monthly_targets(tmp_path, "UTC", ["wind_onshore", "wind_offshore"])
    assert pd.isna(combined["wind"].mean_power_mw.iloc[0])
    assert combined["solar"].mean_power_mw.iloc[0] == 2.
    onshore = load_monthly_targets(tmp_path, "UTC", ["wind_onshore"])
    assert onshore["wind"].energy_mwh.iloc[0] == 744.
    (tmp_path / "solar.parquet").write_bytes(b"broken fixture")
    with pytest.raises(ValueError, match="Hash"):
        load_monthly_targets(tmp_path, "UTC", ["wind_onshore"])


@pytest.mark.parametrize("approved", [False, True])
def test_preview_is_inactive_reviewable_and_exclusive(tmp_path: Path, approved: bool) -> None:
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    index = pd.date_range("2024-01-01", "2024-02-01", freq="1h", inclusive="left", tz="UTC", name="timestamp_utc")
    quality = {}
    for name, target in (("solar", "solar"), ("wind_onshore", "wind")):
        pd.DataFrame({"target": 10.}, index=index).to_parquet(prepared / (name + ".parquet"))
        quality[name] = {"target": target, "unit": "MW", "frequency": "1h", "provenance": "synthetic"}
    (prepared / "quality.json").write_text(json.dumps(quality))
    files = {path.name: sha256(path.read_bytes()).hexdigest() for path in prepared.iterdir()}
    (prepared / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": files}))
    config = {"monthly_protocol": {**draft(), "experiment_enabled": False, "approved": approved,
        "calendar_timezone": "UTC", "wind_components": ["wind_onshore"],
        "preview_calendar_timezone": "UTC", "preview_wind_components": ["wind_onshore"],
        "models": [{"size": "5M"}], "interval_levels": [.8, .9]},
        "monthly_inspection": {"prepared_directory": "prepared"}, "planning": {"step10": {"evaluation_proposal": {
            "development_start_utc": "2023-12-01T00:00Z", "test_start_utc": "2024-01-01T00:00Z",
            "test_end_exclusive_utc": "2024-02-01T00:00Z"}}}}
    output = tmp_path / "preview"
    page = save_preview(config, tmp_path, output)
    assert "Nessun modello eseguito" in page.read_text(encoding="utf-8")
    filename = "protocol_snapshot.json" if approved else "protocol_preview.json"
    result = json.loads((output / filename).read_text())
    assert result["kind"] == ("frozen_protocol_no_forecasts" if approved else "protocol_preview_no_forecasts")
    assert result["settings"]["experiment_enabled"] is False
    assert len(result["settings_sha256"]) == 64
    assert result["source_prepared_manifest_sha256"] == sha256((prepared / "manifest.json").read_bytes()).hexdigest()
    if approved:
        assert "Step 10 concluso" in page.read_text(encoding="utf-8")
    assert result["targets"]["solar"]["test"]["scorable_months"] == 0
    with pytest.raises(FileExistsError):
        save_preview(config, tmp_path, output)
