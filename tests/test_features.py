"""Synthetic feature assembly tests: roles, publication delays and interval alignment."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.calendar_features import CalendarConfig
from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.features import (
    FeatureConfig,
    WeatherBinding,
    assemble_features,
    bindings_from_project_config,
)
from solarwindcast.weather import Location, WeatherRequest, parse_response

ORIGIN = "2026-01-01T02:00:00Z"


def target(frequency: str = "1h", periods: int = 4) -> TimeSeriesDataset:
    """Keep future truth as an evaluation fixture, including a missing observation."""
    index = pd.date_range("2026-01-01T00:00Z", periods=periods, freq=frequency, name="timestamp_utc")
    values = np.arange(periods, dtype=float)
    values[1] = np.nan
    return TimeSeriesDataset(pd.DataFrame({"target": values}, index=index),
                             DatasetSpec("solar", frequency, (), (), (), "synthetic target"))


def binding(role: str = "past", variable: str = "temperature_2m", hours: int = 5) -> WeatherBinding:
    """Build a fake source with an explicitly declared availability assumption."""
    product = "reanalysis" if role == "past" else "single_run"
    req = WeatherRequest(product, Location("fixture_point", 41, 16), "2026-01-01T00:00:00Z",
                         f"2026-01-01T{hours:02d}:00:00Z", "fixture_model", (variable,),
                         "2025-12-31T18:00:00Z" if product == "single_run" else None,
                         "operational_archive")
    data = {"utc_offset_seconds": 0,
            "hourly_units": {variable: "W/m²" if variable == "shortwave_radiation" else "°C"},
            "hourly": {"time": [f"2026-01-01T{i:02d}:00" for i in range(hours)],
                       variable: [10 * (i + 1) for i in range(hours)]}}
    result = parse_response(data, req, {})
    policy = "mean_to_interval_start" if variable == "shortwave_radiation" else "instant_at_start"
    return WeatherBinding("fixture", result, role, (variable,), ((variable, policy),),
                          "0h" if role == "past" else "6h", "synthetic assumption only")


def settings(weather: tuple[WeatherBinding, ...] = ()) -> FeatureConfig:
    """Derive explicit role lists for fixtures, not automatic production selection."""
    past = tuple(f"weather_{b.name}_{v}" for b in weather if b.role == "past" for v in b.variables)
    future = ("calendar_hour", "calendar_day_of_week", "calendar_is_holiday") + tuple(
        f"weather_{b.name}_{v}" for b in weather if b.role == "known_future" for v in b.variables)
    return FeatureConfig(CalendarConfig("IT", "UTC", ("hour", "day_of_week", "is_holiday"), True),
                         past, future, "exact")


@pytest.mark.parametrize("identity", ["solar", "wind", "load", "residual_load"])
def test_calendar_join_all_targets_and_safe_model_inputs(identity: str) -> None:
    source = target()
    source.spec = replace(source.spec, target=identity)
    original = source.frame.copy(deep=True)
    result = assemble_features(source, settings(), (), ORIGIN)
    assert result.dataset.spec.target == identity
    pd.testing.assert_series_equal(result.dataset.frame["target"], source.frame["target"])
    pd.testing.assert_frame_equal(source.frame, original)
    context, future = result.model_inputs()
    assert len(context) == len(future) == 2
    assert context.index.max() < pd.Timestamp(ORIGIN)
    assert "target" not in future
    assert set(future) == set(result.dataset.spec.known_future_covariates)


def test_observations_at_and_after_origin_are_masked() -> None:
    source = binding()
    original = source.result.frame.copy(deep=True)
    result = assemble_features(target(), settings((source,)), (source,), ORIGIN)
    values = result.dataset.frame["weather_fixture_temperature_2m"]
    assert values.iloc[:2].tolist() == [10, 20]
    assert values.iloc[2:].isna().all()
    assert result.report["weather"]["fixture"]["unavailable_counts"]["temperature_2m"] == 2
    pd.testing.assert_frame_equal(source.result.frame, original)


def test_publication_delay_masks_unavailable_past_values() -> None:
    source = replace(binding(), publication_delay="2h")
    result = assemble_features(target(), settings((source,)), (source,), ORIGIN)
    values = result.dataset.frame["weather_fixture_temperature_2m"]
    assert values.iloc[0] == 10
    assert values.iloc[1:].isna().all()


def test_preceding_hour_mean_is_shifted_using_timestamps_not_rows() -> None:
    source = binding(variable="shortwave_radiation")
    result = assemble_features(target(), settings((source,)), (source,), ORIGIN)
    values = result.dataset.frame["weather_fixture_shortwave_radiation"]
    assert values.iloc[:2].tolist() == [20, 30]
    assert values.iloc[2:].isna().all()


def test_missing_source_boundary_stays_nan_after_alignment() -> None:
    source = binding(role="known_future", variable="shortwave_radiation", hours=4)
    result = assemble_features(target(), settings((source,)), (source,), ORIGIN)
    assert result.dataset.frame["weather_fixture_shortwave_radiation"].iloc[:3].tolist() == [20, 30, 40]
    assert pd.isna(result.dataset.frame["weather_fixture_shortwave_radiation"].iloc[3])


def test_instantaneous_weather_on_quarter_hours_has_no_implicit_fill() -> None:
    source = binding()
    result = assemble_features(target("15min", 8), settings((source,)), (source,), ORIGIN)
    values = result.dataset.frame["weather_fixture_temperature_2m"]
    assert values.iloc[0] == 10 and values.iloc[4] == 20
    assert values.isna().sum() == 6


def test_hourly_mean_is_not_replicated_to_quarter_hours() -> None:
    source = binding(variable="shortwave_radiation")
    with pytest.raises(ValueError, match="media oraria"):
        assemble_features(target("15min", 8), settings((source,)), (source,), ORIGIN)


def test_future_weather_requires_forecast_availability_checks() -> None:
    source = binding(role="known_future")
    result = assemble_features(target(), settings((source,)), (source,), ORIGIN)
    assert not result.dataset.frame["weather_fixture_temperature_2m"].isna().any()
    assert result.report["weather"]["fixture"]["forecast_availability"]["run_utc"] is not None
    late = replace(source, publication_delay="10h")
    with pytest.raises(ValueError, match="non disponibile"):
        assemble_features(target(), settings((late,)), (late,), ORIGIN)
    retrospective = replace(binding(), role="known_future")
    with pytest.raises(ValueError, match="operative"):
        assemble_features(target(), settings((retrospective,)), (retrospective,), ORIGIN)


def test_hindcast_cannot_become_operational_future_weather() -> None:
    source = binding(role="known_future")
    source.result.request = replace(source.result.request, archive_origin="hindcast")
    with pytest.raises(ValueError, match="operativo"):
        assemble_features(target(), settings((source,)), (source,), ORIGIN)


def test_mixed_sources_preserve_roles_and_units() -> None:
    past = replace(binding(), name="observed")
    future = replace(binding(role="known_future", variable="shortwave_radiation"), name="forecast")
    sources = (past, future)
    result = assemble_features(target(), settings(sources), sources, ORIGIN)
    assert result.dataset.spec.past_covariates == ("weather_observed_temperature_2m",)
    assert "weather_forecast_shortwave_radiation" in result.dataset.spec.known_future_covariates
    assert dict(result.dataset.spec.covariate_units)["weather_forecast_shortwave_radiation"] == "W/m²"
    assert result.dataset.frame["target"].isna().sum() == 1


@pytest.mark.parametrize("change", [{"role": "unknown"}, {"publication_delay": None},
    {"publication_delay": "-1h"}, {"availability_evidence": ""},
    {"availability_evidence": "DA DECIDERE"},
    {"variables": ("unrequested",)}, {"time_alignment": ()},
    {"time_alignment": (("temperature_2m", "mean_to_interval_start"),)}])
def test_invalid_binding_fails(change: dict[str, object]) -> None:
    source = replace(binding(), **change)
    with pytest.raises(ValueError):
        assemble_features(target(), settings((source,)), (source,), ORIGIN)


def test_duplicate_names_mismatched_roles_and_interpolation_are_rejected() -> None:
    source = binding()
    with pytest.raises(ValueError, match="duplicati"):
        assemble_features(target(), settings((source, source)), (source, source), ORIGIN)
    with pytest.raises(ValueError, match="ruoli configurati"):
        assemble_features(target(), replace(settings(), past_covariates=("undeclared",)), (), ORIGIN)
    with pytest.raises(ValueError, match="exact"):
        assemble_features(target(), replace(settings(), alignment_policy="interpolate"), (), ORIGIN)


def test_project_yaml_rejects_unresolved_settings_and_loads_explicit_bindings() -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        FeatureConfig.from_project_config(project)
    with pytest.raises(ValueError, match="DA DECIDERE"):
        bindings_from_project_config(project, {})
    source = binding()
    cfg = settings((source,))
    project["features"] = {
        "alignment_policy": "exact", "past_covariates": list(cfg.past_covariates),
        "known_future_covariates": list(cfg.known_future_covariates),
        "calendar": {"country": "IT", "holiday_timezone_policy": "UTC",
                     "features": ["hour", "day_of_week", "is_holiday"], "observed": True},
        "weather_bindings": [{"name": "fixture", "source": "observed", "role": "past",
            "variables": ["temperature_2m"], "time_alignment": {"temperature_2m": "instant_at_start"},
            "publication_delay": "0h", "availability_evidence": "synthetic assumption"}],
    }
    declared = bindings_from_project_config(project, {"observed": source.result})
    assembled = assemble_features(target(), FeatureConfig.from_project_config(project), declared, ORIGIN)
    assert len(assembled.dataset.frame) == 4


def test_future_real_values_cannot_change_model_inputs() -> None:
    truth = target()
    observed = binding()
    before = assemble_features(truth, settings((observed,)), (observed,), ORIGIN).model_inputs()
    truth.frame.loc[truth.frame.index >= pd.Timestamp(ORIGIN), "target"] = 999999
    observed.result.frame.loc[observed.result.frame.index >= pd.Timestamp(ORIGIN),
                              "temperature_2m"] = -999999
    after = assemble_features(truth, settings((observed,)), (observed,), ORIGIN).model_inputs()
    for original, changed in zip(before, after, strict=True):
        pd.testing.assert_frame_equal(original, changed)


def test_source_nan_is_preserved_and_past_columns_are_not_future_inputs() -> None:
    observed = binding()
    observed.result.frame.iloc[0, 0] = np.nan
    result = assemble_features(target(), settings((observed,)), (observed,), ORIGIN)
    assert pd.isna(result.dataset.frame["weather_fixture_temperature_2m"].iloc[0])
    _, future = result.model_inputs()
    assert "weather_fixture_temperature_2m" not in future


@pytest.mark.parametrize("fault", ["duplicate", "units", "origin"])
def test_incompatible_sources_and_origin_fail(fault: str) -> None:
    observed = binding()
    origin = ORIGIN
    if fault == "duplicate":
        observed.result.frame.index = observed.result.frame.index.take([0, 0, 2, 3, 4])
    elif fault == "units":
        observed.result.metadata["units"]["temperature_2m"] = "unknown"
    else:
        origin = "2026-01-01T02:15:00Z"
    with pytest.raises(ValueError):
        assemble_features(target(), settings((observed,)), (observed,), origin)
