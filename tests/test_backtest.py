"""Synthetic rolling-origin tests for shared cases, availability and immutable artifacts."""

import json
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
import pytest

from solarwindcast.backtest import BacktestConfig, BaselinePredictor, run_backtest
from solarwindcast.baselines import BaselineConfig
from solarwindcast.calendar_features import CalendarConfig
from solarwindcast.dataset import DatasetSpec, ForecastResult, TimeSeriesDataset
from solarwindcast.evaluation import EvaluationConfig
from solarwindcast.features import FeatureConfig, FeatureResult, assemble_features


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Delete only disposable test artifacts after each test, including failures."""
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield Path(directory)


def dataset() -> TimeSeriesDataset:
    """Fixture-only regular UTC grid, including context and later verification truth."""
    frame = pd.DataFrame({"target": np.arange(16, dtype=float)}, index=pd.date_range(
        "2026-01-01", periods=16, freq="15min", tz="UTC", name="timestamp_utc"))
    return TimeSeriesDataset(frame, DatasetSpec("solar", "15min", (), (), (), "synthetic fixture"))


def settings() -> BacktestConfig:
    """Explicit small test schedule, not a decision for real experiments."""
    return BacktestConfig("solar", "15min", "2026-01-01T01:00:00Z", 4, 2, 2, 3,
        "0h", "fixed", "reject", "pooled_cases", "raise", EvaluationConfig("omit", (.1, .5, .9), (.8,)))


def models() -> dict[str, BaselinePredictor]:
    """Use all baseline methods and one common context/horizon/delay."""
    return {name: BaselinePredictor(BaselineConfig(name, 4, 2, "0h", 2, (.1, .5, .9), "linear", 2))
            for name in ("persistence", "seasonal_naive", "historical_quantiles")}


def test_same_origins_cases_and_requested_quantile_levels() -> None:
    result = run_backtest(dataset(), settings(), models())
    assert len(result.windows) == 3 and len(result.predictions) == 18
    assert result.predictions.groupby("model").size().tolist() == [6, 6, 6]
    point = result.summary.loc[result.summary.family == "point"]
    assert set(point.n_used) == {6}
    assert result.metadata["comparison_groups"]["probability"] == ["historical_quantiles"]
    assert not result.predictions.loc[result.predictions.model == "persistence", "probability_common"].any()
    mae = result.summary.loc[(result.summary.model == "persistence") & (result.summary.metric == "mae_mw")]
    assert mae.value.iloc[0] == 1.5


def test_future_truth_is_hidden_from_predictors_and_features() -> None:
    seen: list[pd.DataFrame] = []
    origins: list[str] = []

    class Spy(BaselinePredictor):
        """Observe exactly the copied frame available to a model."""

        def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
            seen.append((data.dataset if isinstance(data, FeatureResult) else data).frame.copy())
            return super().predict(data, origin_utc)

    def builder(target: TimeSeriesDataset, origin: str) -> FeatureResult:
        origins.append(origin)
        assert target.frame.loc[target.frame.index >= pd.Timestamp(origin), "target"].isna().all()
        config = FeatureConfig(CalendarConfig("IT", "UTC", ("hour",), True), (), ("calendar_hour",), "exact")
        return assemble_features(target, config, (), origin)

    selected = {"spy": Spy(models()["persistence"].settings)}
    original = dataset()
    before = run_backtest(original, replace(settings(), number_of_windows=1), selected, builder)
    changed = dataset()
    changed.frame.iloc[4:, 0] = 999999
    after = run_backtest(changed, replace(settings(), number_of_windows=1), selected, builder)
    pd.testing.assert_series_equal(before.predictions.prediction, after.predictions.prediction)
    assert len(origins) == 2
    assert all(frame.loc[frame.index >= pd.Timestamp(origins[0]), "target"].isna().all() for frame in seen)
    assert original.frame.target.iloc[4] == 4


def test_target_publication_delay_is_shared_across_models() -> None:
    cfg = replace(settings(), first_origin_utc="2026-01-01T01:15:00Z", publication_delay="15min")
    selected = {name: BaselinePredictor(replace(model.settings, publication_delay="15min"))
                for name, model in models().items()}
    result = run_backtest(dataset(), cfg, selected)
    assert result.windows[0]["models"]["persistence"]["forecast_metadata"]["context_end_utc"] == "2026-01-01T00:45:00+00:00"
    with pytest.raises(ValueError, match="coincidere"):
        run_backtest(dataset(), cfg, models())


def test_missing_prediction_removes_same_point_cases_for_all_models() -> None:
    data = dataset()
    data.frame.iloc[3, 0] = np.nan
    result = run_backtest(data, settings(), models())
    point = result.metrics.loc[(result.metrics.window == 0) & (result.metrics.family == "point")]
    assert set(point.n_used) == {0} and point.value.isna().all()
    assert result.windows[0]["models"]["persistence"]["missing_point_predictions"] == 2
    assert result.windows[0]["probability_common_timestamps"]  # separate probabilistic comparison group


def test_missing_truth_is_retained_and_exclusions_are_counted() -> None:
    data = dataset()
    data.frame.iloc[4, 0] = np.nan
    result = run_backtest(data, settings(), models())
    point = result.metrics.loc[(result.metrics.window == 0) & (result.metrics.family == "point")]
    assert set(point.n_used) == {1}
    assert result.predictions.loc[result.predictions.timestamp_utc == data.frame.index[4], "actual"].isna().all()
    strict = replace(settings(), evaluation=replace(settings().evaluation, missing_policy="raise"))
    with pytest.raises(ValueError, match="mancanti"):
        run_backtest(data, strict, models())


def test_model_failures_can_be_recorded_but_never_silently_dropped(scratch: Path) -> None:
    class Broken(BaselinePredictor):
        """Simulate a model failure with content that must not enter persisted errors."""

        def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
            raise RuntimeError("fake-test-secret-must-not-be-recorded")

    selected = {"working": models()["persistence"], "broken": Broken(models()["persistence"].settings)}
    with pytest.raises(RuntimeError):
        run_backtest(dataset(), settings(), selected)
    result = run_backtest(dataset(), replace(settings(), failure_policy="record"), selected)
    assert len(result.predictions) == 12
    assert result.predictions.loc[result.predictions.model == "broken", "status"].eq("failed").all()
    assert result.summary.n_used.eq(0).all()
    result.save(scratch / "run")
    assert "fake-test-secret" not in (scratch / "run/windows.json").read_text()


def test_overlapping_origins_require_explicit_policy() -> None:
    cfg = replace(settings(), stride_steps=1)
    with pytest.raises(ValueError, match="sovrappongono"):
        run_backtest(dataset(), cfg, models())
    result = run_backtest(dataset(), replace(cfg, overlap_scoring_policy="all_origins"), models())
    assert result.metadata["repeated_target_timestamps"] == 2
    assert len(result.predictions) == 18  # distinct origin-target cases are kept


def test_pooled_rmse_is_not_the_average_of_window_rmses() -> None:
    class Zero(BaselinePredictor):
        """Return known errors to distinguish correct pooled aggregation from mean RMSE."""

        def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
            result = super().predict(data, origin_utc)
            result.point[:] = 0
            return result

    data = dataset()
    data.frame.iloc[4:6, 0] = 1
    data.frame.iloc[6:8, 0] = 3
    result = run_backtest(data, replace(settings(), number_of_windows=2),
                          {"zero": Zero(models()["persistence"].settings)})
    score = result.summary.loc[result.summary.metric == "rmse_mw", "value"].iloc[0]
    assert score == pytest.approx(np.sqrt(5))


def test_save_is_strict_json_with_hashes_and_no_overwrite(scratch: Path) -> None:
    data = dataset()
    data.frame.iloc[4, 0] = np.nan
    result = run_backtest(data, settings(), models())
    output = result.save(scratch / "run")
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "complete"
    for name, expected in manifest["files_sha256"].items():
        content = (output / name).read_bytes()
        assert sha256(content).hexdigest() == expected
        json.loads(content, parse_constant=lambda value: pytest.fail(f"JSON non standard: {value}"))
    assert len(json.loads((output / "input.json").read_text())["rows"]) == 16
    with pytest.raises(FileExistsError):
        result.save(output)


@pytest.mark.parametrize("change", [{"context_steps": 0}, {"stride_steps": True},
    {"number_of_windows": 0}, {"context_window_policy": "expanding"},
    {"overlap_scoring_policy": "DA DECIDERE"}, {"aggregation": "mean_rmse"},
    {"failure_policy": "skip"}, {"first_origin_utc": "2026-01-01"}])
def test_invalid_backtest_settings(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(settings(), **change).validate()


def test_incomplete_last_horizon_is_rejected_without_running_models() -> None:
    with pytest.raises(ValueError, match="ultima finestra"):
        run_backtest(dataset(), replace(settings(), number_of_windows=8), models())
    with pytest.raises(ValueError, match="Contesto"):
        run_backtest(dataset(), replace(settings(), first_origin_utc="2026-01-01T00:30:00Z"), models())


@pytest.mark.parametrize("identity", ["solar", "wind", "load", "residual_load"])
def test_target_identity_is_configurable(identity: str) -> None:
    data = dataset()
    data.spec = replace(data.spec, target=identity)
    result = run_backtest(data, replace(settings(), target=identity), models())
    assert result.metadata["backtest"]["target"] == identity


def test_probability_comparison_uses_shared_requested_levels_and_cases() -> None:
    class ExtraQuantiles(BaselinePredictor):
        """Simulate a model with more native levels and one missing requested quantile."""

        def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
            result = super().predict(data, origin_utc)
            result.quantiles[.25] = (result.quantiles[.1] + result.quantiles[.5]) / 2
            result.quantiles = result.quantiles.reindex(columns=[.1, .25, .5, .9])
            result.quantiles.iloc[0, 0] = np.nan
            return result

    base = models()["historical_quantiles"]
    result = run_backtest(dataset(), replace(settings(), number_of_windows=1),
                          {"base": base, "extra": ExtraQuantiles(base.settings)})
    probability = result.metrics.loc[result.metrics.family == "pinball"]
    assert probability.n_used.tolist() == [1, 1]
    assert "q_0.25" in result.predictions  # extra native levels preserved, not mixed into comparison loss
    selected = {r["model"]: r["value"] for r in probability.to_dict("records")}
    assert selected["base"] == selected["extra"]


def test_wrong_forecast_timestamps_are_not_silently_realigned() -> None:
    class Shifted(BaselinePredictor):
        """Return a structurally valid forecast at the wrong timestamps."""

        def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
            result = super().predict(data, origin_utc)
            result.point.index += pd.Timedelta(minutes=15)
            return result

    with pytest.raises(ValueError, match="finestra richiesti"):
        run_backtest(dataset(), settings(), {"shifted": Shifted(models()["persistence"].settings)})


def test_mutated_input_snapshot_is_rejected_before_saving(scratch: Path) -> None:
    result = run_backtest(dataset(), settings(), models())
    result.input_snapshot["rows"][0]["target"] = 999
    with pytest.raises(ValueError, match="snapshot"):
        result.save(scratch / "changed")
    assert not (scratch / "changed").exists()


def test_inplace_feature_builder_cannot_modify_the_reference_target() -> None:
    def bad_builder(data: TimeSeriesDataset, origin: str) -> FeatureResult:
        data.frame.iloc[-1, 0] = 999
        return FeatureResult(data, origin, {})

    with pytest.raises(ValueError, match="modificato il target"):
        run_backtest(dataset(), settings(), models(), bad_builder)
