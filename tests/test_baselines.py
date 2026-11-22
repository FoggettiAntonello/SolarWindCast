"""Synthetic baseline checks for seasonal phase, missing values and availability."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.baselines import BaselineConfig, forecast_baseline
from solarwindcast.dataset import DatasetSpec, ForecastResult, TimeSeriesDataset
from solarwindcast.evaluation import point_metrics


def dataset(frequency: str = "15min") -> TimeSeriesDataset:
    """Keep both context and future truth to test non-use of future observations."""
    frame = pd.DataFrame({"target": np.arange(16, dtype=float)},
                         index=pd.date_range("2026-01-01", periods=16, freq=frequency,
                                             tz="UTC", name="timestamp_utc"))
    return TimeSeriesDataset(frame, DatasetSpec("solar", frequency, (), (), (), "synthetic fixture"))


def config(method: str = "persistence") -> BaselineConfig:
    """Return fixture settings only, independent of real experiment decisions."""
    return BaselineConfig(method, 8, 6, "0h", seasonal_lag_steps=4,
                          levels=(.1, .5, .9), quantile_method="linear", minimum_valid_samples=3)


@pytest.mark.parametrize("target", ["solar", "wind", "load", "residual_load"])
def test_persistence_is_configurable_for_all_targets(target: str) -> None:
    data = dataset()
    data.spec = replace(data.spec, target=target)
    result = forecast_baseline(data, "2026-01-01T02:00Z", config())
    assert result.point.tolist() == [7] * 6
    assert result.target == target and result.quantiles is None
    assert result.point.index[1] - result.point.index[0] == pd.Timedelta(minutes=15)


def test_cycle_repeats_beyond_one_season_and_keeps_missing_positions() -> None:
    data = dataset()
    data.frame.iloc[5, 0] = np.nan
    result = forecast_baseline(data, "2026-01-01T02:00Z", config("seasonal_naive"))
    np.testing.assert_equal(result.point.to_numpy(), [4, np.nan, 6, 7, 4, np.nan])


def test_persistence_does_not_fall_back_to_last_nonmissing_value() -> None:
    data = dataset()
    data.frame.iloc[7, 0] = np.nan
    assert forecast_baseline(data, "2026-01-01T02:00Z", config()).point.isna().all()


def test_publication_delay_changes_available_context_without_shifting_seasonal_phase() -> None:
    data = dataset()
    cfg = replace(config("seasonal_naive"), context_steps=4, publication_delay="30min")
    result = forecast_baseline(data, "2026-01-01T02:00Z", cfg)
    assert result.point.tolist() == [4, 5, 2, 3, 4, 5]
    assert result.metadata["context_end_utc"] == "2026-01-01T01:15:00+00:00"
    assert result.metadata["publication_gap_steps"] == 2
    persistence = forecast_baseline(data, "2026-01-01T02:00Z", replace(cfg, method="persistence"))
    assert persistence.point.tolist() == [5] * 6


@pytest.mark.parametrize("method", ["persistence", "seasonal_naive", "historical_quantiles"])
def test_changing_future_truth_cannot_change_forecasts(method: str) -> None:
    data = dataset()
    before = forecast_baseline(data, "2026-01-01T02:00Z", config(method))
    data.frame.iloc[8:, 0] = 999999
    after = forecast_baseline(data, "2026-01-01T02:00Z", config(method))
    pd.testing.assert_series_equal(before.point, after.point)
    if before.quantiles is not None:
        pd.testing.assert_frame_equal(before.quantiles, after.quantiles)


def test_historical_quantiles_known_answer_and_explicit_missing_count() -> None:
    data = dataset()
    data.frame.iloc[1, 0] = np.nan
    original = data.frame.copy(deep=True)
    result = forecast_baseline(data, "2026-01-01T02:00Z", config("historical_quantiles"))
    assert result.point.iloc[0] == 4
    assert result.quantiles.iloc[0].tolist() == pytest.approx([1.2, 4., 6.4])
    assert result.metadata["valid_samples"] == 7
    assert result.metadata["context_nan_count"] == 1
    pd.testing.assert_frame_equal(data.frame, original)


def test_insufficient_valid_history_returns_nan_forecasts_with_status() -> None:
    data = dataset()
    data.frame.iloc[:7, 0] = np.nan
    result = forecast_baseline(data, "2026-01-01T02:00Z", config("historical_quantiles"))
    assert result.point.isna().all() and result.quantiles.isna().all().all()
    assert result.metadata["status"] == "insufficient_valid_samples"


@pytest.mark.parametrize("change", [{"context_steps": 0}, {"horizon_steps": True},
    {"publication_delay": "-1h"}, {"method": "DA DECIDERE"},
    {"method": "seasonal_naive", "seasonal_lag_steps": 9},
    {"method": "historical_quantiles", "minimum_valid_samples": 0}])
def test_invalid_configuration(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(config(), **change).validate()


def test_short_context_and_off_grid_origin_are_rejected() -> None:
    with pytest.raises(ValueError, match="insufficiente"):
        forecast_baseline(dataset(), "2026-01-01T01:00Z", config())
    with pytest.raises(ValueError, match="griglia"):
        forecast_baseline(dataset(), "2026-01-01T02:01Z", config())


def test_shared_forecast_contract_rejects_misaligned_and_crossing_quantiles() -> None:
    result = forecast_baseline(dataset(), "2026-01-01T02:00Z", config("historical_quantiles"))
    result.quantiles.iloc[0, 0] = 100
    with pytest.raises(ValueError, match="incrociati"):
        result.validate()
    bad = ForecastResult(result.point, result.quantiles.iloc[1:], "solar", "15min")
    with pytest.raises(ValueError, match="allineati"):
        bad.validate()


def test_yaml_rejects_placeholders_and_loads_selected_method_only() -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        BaselineConfig.from_project_config(project, "persistence")
    project["models"]["baselines"]["methods"] = ["persistence"]
    project["forecast"].update(context_steps=8, horizon_steps=6)
    project["data"]["publication_delay"] = "0h"
    cfg = BaselineConfig.from_project_config(project, "persistence")
    assert cfg.context_steps == 8 and cfg.seasonal_lag_steps is None


def test_forecast_and_score_integration_uses_the_forecast_timestamps() -> None:
    data = dataset()
    forecast = forecast_baseline(data, "2026-01-01T02:00Z", config())
    actual = data.frame["target"].reindex(forecast.point.index)
    report = point_metrics(actual, forecast.point, "raise")
    assert report.scores["mae_mw"] == 3.5
    assert report.scores["rmse_mw"] == pytest.approx(np.sqrt(91 / 6))
