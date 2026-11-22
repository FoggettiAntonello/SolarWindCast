"""Known-answer metrics checked against independent formulas and scikit-learn."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml
from sklearn.metrics import (
    mean_absolute_error,
    mean_pinball_loss,
    root_mean_squared_error,
)

from solarwindcast.dataset import validate_quantile_frame
from solarwindcast.evaluation import (
    EvaluationConfig,
    central_interval,
    common_valid_mask,
    interval_metrics,
    pinball_metrics,
    point_metrics,
)


def test_metrics_and_interval_coverage_are_calculated_on_actuals() -> None:
    metrics = point_metrics(series([0, 10]), series([2, 6]), "raise")
    assert metrics.scores["mae_mw"] == 3
    assert metrics.scores["rmse_mw"] == pytest.approx(np.sqrt(10))
    intervals = interval_metrics(series([0, 10]), series([0, 0]), series([3, 5]), .8, "raise")
    assert intervals.scores["coverage"] == .5
    assert intervals.details["nominal_level"] == .8


def series(values: list[float]) -> pd.Series:
    """Build a fixture with explicit common UTC scoring timestamps."""
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), freq="h",
                                                 tz="UTC", name="timestamp_utc"), dtype=float)


def test_point_metrics_match_independent_library() -> None:
    actual, predicted = series([0, 3, -4, 10]), series([1, 2, -2, 6])
    result = point_metrics(actual, predicted, "raise")
    assert result.scores["mae_mw"] == pytest.approx(mean_absolute_error(actual, predicted))
    assert result.scores["rmse_mw"] == pytest.approx(root_mean_squared_error(actual, predicted))
    assert result.used == result.total == 4


def test_pinball_known_answers_and_independent_reference() -> None:
    actual = series([0, 10])
    predicted = pd.DataFrame({.1: [-2., 6.], .5: [2., 6.], .9: [3., 12.]}, index=actual.index)
    result = pinball_metrics(actual, predicted, "raise")
    assert result.details["pinball_by_quantile"][.5] == 1.5
    for level in predicted:
        assert result.details["pinball_by_quantile"][level] == pytest.approx(
            mean_pinball_loss(actual, predicted[level], alpha=level))
    assert result.scores["pinball_loss_mw"] == pytest.approx((.3 + 1.5 + .25) / 3)


def test_interval_coverage_includes_boundaries_and_reports_width() -> None:
    result = interval_metrics(series([0, 10, 11]), series([0, 0, 0]), series([10, 10, 10]), .9, "raise")
    assert result.scores["coverage"] == pytest.approx(2 / 3)
    assert result.scores["mean_width_mw"] == 10
    assert result.scores["coverage_minus_nominal"] == pytest.approx(2 / 3 - .9)


def test_missing_policy_is_explicit_and_reports_exclusions() -> None:
    actual, predicted = series([1, np.nan, 3]), series([1, 2, np.nan])
    with pytest.raises(ValueError, match="mancanti"):
        point_metrics(actual, predicted, "raise")
    result = point_metrics(actual, predicted, "omit")
    assert result.used == 1 and result.total == 3
    assert result.scores["mae_mw"] == 0
    assert len(result.excluded_timestamps) == 2
    assert pd.isna(actual.iloc[1]) and pd.isna(predicted.iloc[2])


def test_no_valid_cases_gives_nan_not_zero() -> None:
    result = point_metrics(series([np.nan]), series([1]), "omit")
    assert result.used == 0 and np.isnan(result.scores["mae_mw"])
    quantiles = pd.DataFrame({.1: [np.nan], .9: [np.nan]}, index=series([1]).index)
    assert np.isnan(pinball_metrics(series([1]), quantiles, "omit").scores["pinball_loss_mw"])
    assert np.isnan(interval_metrics(series([np.nan]), series([0]), series([1]), .8, "omit").scores["coverage"])


def test_quantile_scores_share_cases_when_one_level_is_missing() -> None:
    actual = series([0, 10])
    predicted = pd.DataFrame({.1: [0., np.nan], .9: [1., 12.]}, index=actual.index)
    result = pinball_metrics(actual, predicted, "omit")
    assert result.used == 1
    assert result.details["pinball_by_quantile"][.9] == pytest.approx(.1)


def test_common_mask_uses_same_cases_across_models() -> None:
    actual = series([0, 100, 3])
    first, second = series([0, np.nan, 3]), series([1, 0, 3])
    mask = common_valid_mask(actual, {"first": first, "second": second})
    assert mask.tolist() == [True, False, True]
    reports = [point_metrics(actual, p, "raise", mask) for p in (first, second)]
    assert reports[0].used == reports[1].used == 2
    assert reports[0].excluded_timestamps == reports[1].excluded_timestamps


@pytest.mark.parametrize("columns, values", [
    ([.9, .1], [[1, 2]]), ([.1, .1], [[1, 2]]), (["0.1", "0.9"], [[1, 2]]),
    ([-.1, .9], [[1, 2]]), ([.1, .9], [[4, 3]]),
    ([.1, .5, .9], [[4, np.nan, 3]]), ([.1, .9], [[0, np.inf]]),
])
def test_invalid_quantiles_are_never_repaired(columns: list[object], values: list[list[float]]) -> None:
    frame = pd.DataFrame(values, columns=columns, index=series([0]).index)
    original = frame.copy(deep=True)
    with pytest.raises(ValueError):
        validate_quantile_frame(frame)
    pd.testing.assert_frame_equal(frame, original)


def test_invalid_intervals_and_misaligned_times_are_rejected() -> None:
    with pytest.raises(ValueError, match="inferiore"):
        interval_metrics(series([0]), series([2]), series([1]), .8, "raise")
    shifted = series([0, 1])
    shifted.index = shifted.index + pd.Timedelta(minutes=15)
    with pytest.raises(ValueError, match="allineati"):
        point_metrics(series([0, 1]), shifted, "raise")


@pytest.mark.parametrize("level", [0, 1, -.1, float("nan"), True])
def test_invalid_nominal_levels(level: float) -> None:
    with pytest.raises(ValueError):
        interval_metrics(series([0]), series([0]), series([1]), level, "raise")


def test_central_interval_requires_existing_levels_without_interpolation() -> None:
    predicted = pd.DataFrame({.1: [0.], .5: [1.], .9: [2.]}, index=series([0]).index)
    lower, upper = central_interval(predicted, .8)
    assert lower.iloc[0] == 0 and upper.iloc[0] == 2
    with pytest.raises(ValueError, match="assente"):
        central_interval(predicted, .9)


def test_no_positional_arrays_or_matrix_point_predictions() -> None:
    with pytest.raises(TypeError):
        point_metrics([0], [1], "raise")
    with pytest.raises(TypeError):
        point_metrics(series([0]), series([1]).to_frame(), "raise")


def test_unresolved_evaluation_yaml_fails() -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        EvaluationConfig.from_project_config(project)
    project["forecast"].update(quantile_levels=[.1, .5, .9], interval_levels=[.8])
    project["evaluation"]["missing_policy"] = "omit"
    assert EvaluationConfig.from_project_config(project).interval_levels == (.8,)
