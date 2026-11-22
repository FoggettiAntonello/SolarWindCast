"""Offline contract tests plus an explicitly enabled smoke test with cached weights."""

import json
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.calendar_features import CalendarConfig
from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.features import (
    FeatureConfig,
    FeatureResult,
    WeatherBinding,
    assemble_features,
)
from solarwindcast.synthetic import SyntheticConfig, generate
from solarwindcast.timestral_model import TimestralSettings, TimestralWrapper
from solarwindcast.weather import Location, WeatherRequest, parse_response

CODE_REVISION = "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff"
WEIGHTS_REVISION = "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"
LEVELS = (.01, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5, .55, .6, .65, .7, .75, .8, .85, .9, .95, .99)


def settings() -> TimestralSettings:
    """Explicit fixture values, never approved experiment defaults."""
    return TimestralSettings("5M", "mistralai/Timestral-5M", WEIGHTS_REVISION, CODE_REVISION,
        "1.0.0", "cpu", 8, 4, "0h", "target_only", "native_mask", False, False, 0., 1, 1e30,
        local_files_only=True, enabled=True)


def dataset() -> TimeSeriesDataset:
    """Small regular grid including evaluation truth that must never enter inputs."""
    index = pd.date_range("2026-01-01", periods=16, freq="15min", tz="UTC", name="timestamp_utc")
    return TimeSeriesDataset(pd.DataFrame({"target": np.arange(16, dtype=float)}, index=index),
                             DatasetSpec("solar", "15min", (), (), (), "synthetic fixture"))


class FakeBackend:
    """Record model arguments and return monotone synthetic quantiles without torch."""

    def __init__(self, context_steps: int = 8) -> None:
        self.config = SimpleNamespace(context_length=32768, block_size=32)
        self.device = "cpu"
        self.max_context = context_steps
        self.supports_covariates = self.supports_known_covariates = True
        self.quantile_levels = LEVELS
        self.received: dict[str, object] = {}

    def forecast(self, context: np.ndarray, prediction_length: int, **kwargs: object) -> object:
        """Record arrays unchanged, including any NaN masks."""
        self.received = {"context": context.copy(), "prediction_length": prediction_length, **kwargs}
        values = np.tile(LEVELS, (1, 1, prediction_length, 1)) + np.nanmean(context)
        return SimpleNamespace(quantile_levels=LEVELS, quantiles=values)


def features() -> FeatureResult:
    """A directly declared fixture, clearly labelled as synthetic, not real provenance."""
    data = dataset()
    data.frame["past_temperature"] = np.arange(16, dtype=float)
    data.frame["known_calendar"] = data.frame.index.hour.astype(float)
    data.frame.loc[data.frame.index >= pd.Timestamp("2026-01-01T02:00Z"), "past_temperature"] = np.nan
    data.spec = replace(data.spec, past_covariates=("past_temperature",),
                        known_future_covariates=("known_calendar",),
                        covariate_units=(("past_temperature", "°C"), ("known_calendar", "dimensionless")))
    return FeatureResult(data, "2026-01-01T02:00:00Z", {"source": "synthetic fixture"})


@pytest.mark.parametrize("target", ["solar", "wind", "load", "residual_load"])
def test_shared_output_shapes_and_median_for_all_targets(target: str) -> None:
    data = dataset()
    data.spec = replace(data.spec, target=target)
    backend = FakeBackend()
    result = TimestralWrapper(settings(), backend).predict(data, "2026-01-01T02:00Z")
    assert result.target == target and result.quantiles.shape == (4, 21)
    pd.testing.assert_series_equal(result.point, result.quantiles[.5].rename("prediction"))
    assert backend.received["context"].shape == (1, 1, 8)
    assert result.point.index[0] == pd.Timestamp("2026-01-01T02:00Z")
    assert result.metadata["backend_mode"] == "injected_test_backend"


def test_future_target_changes_cannot_change_sent_arrays_or_predictions() -> None:
    data = dataset()
    backend = FakeBackend()
    model = TimestralWrapper(settings(), backend)
    before = model.predict(data, "2026-01-01T02:00Z")
    sent = backend.received["context"].copy()
    data.frame.iloc[8:, 0] = 999999
    after = model.predict(data, "2026-01-01T02:00Z")
    np.testing.assert_equal(sent, backend.received["context"])
    pd.testing.assert_frame_equal(before.quantiles, after.quantiles)


def test_missing_native_input_is_not_imputed_in_wrapper() -> None:
    data = dataset()
    data.frame.iloc[1, 0] = np.nan
    backend = FakeBackend()
    model = TimestralWrapper(settings(), backend)
    result = model.predict(data, "2026-01-01T02:00Z")
    assert np.isnan(backend.received["context"][0, 0, 1])
    assert result.metadata["missing_input_counts"]["context"] == 1
    assert pd.isna(data.frame.iloc[1, 0])
    with pytest.raises(ValueError, match="reject"):
        TimestralWrapper(replace(settings(), missing_input_policy="reject"), backend).predict(
            data, "2026-01-01T02:00Z")


def test_delayed_target_gap_is_forecast_not_filled_with_real_values() -> None:
    backend = FakeBackend(context_steps=4)
    config = replace(settings(), context_steps=4, publication_delay="30min")
    result = TimestralWrapper(config, backend).predict(dataset(), "2026-01-01T02:00Z")
    assert backend.received["context"][0, 0].tolist() == [2, 3, 4, 5]
    assert backend.received["prediction_length"] == 6
    assert result.metadata["publication_gap_steps"] == 2
    assert len(result.point) == 4 and result.point.index[0] == pd.Timestamp("2026-01-01T02:00Z")


@pytest.mark.parametrize("variant", ["target_only", "past", "past_known"])
def test_covariate_roles_have_official_shapes(variant: str) -> None:
    backend = FakeBackend()
    TimestralWrapper(replace(settings(), variant=variant), backend).predict(features(), "2026-01-01T02:00Z")
    past, known = backend.received["past_covariates"], backend.received["known_covariates"]
    assert backend.received["symmetric_averaging"] is False
    assert backend.received["clip_nonnegative"] is False
    if variant == "target_only":
        assert past is None and known is None
    else:
        assert past.shape == (1, 1, 8) and np.isfinite(past).all()
        if variant == "past_known":
            assert known.shape == (1, 1, 12)
        else:
            assert known is None


def test_covariate_provenance_and_origin_cannot_be_bypassed_by_column_names() -> None:
    config = replace(settings(), variant="past_known")
    with pytest.raises(ValueError, match="FeatureResult"):
        TimestralWrapper(config, FakeBackend()).predict(features().dataset, "2026-01-01T02:00Z")
    data = features()
    data.origin_utc = "2026-01-01T01:00:00Z"
    with pytest.raises(ValueError, match="stessa origine"):
        TimestralWrapper(config, FakeBackend()).predict(data, "2026-01-01T02:00Z")


def test_disabled_missing_context_and_all_missing_fail_before_inference() -> None:
    backend = FakeBackend()
    with pytest.raises(RuntimeError, match="disattivato"):
        TimestralWrapper(replace(settings(), enabled=False), backend).predict(dataset(), "2026-01-01T02:00Z")
    with pytest.raises(ValueError, match="insufficiente"):
        TimestralWrapper(settings(), backend).predict(dataset(), "2026-01-01T01:00Z")
    data = dataset()
    data.frame.iloc[:8, 0] = np.nan
    with pytest.raises(ValueError, match="interamente"):
        TimestralWrapper(settings(), backend).predict(data, "2026-01-01T02:00Z")
    assert backend.received == {}


def test_download_requires_separate_explicit_authorization() -> None:
    model = TimestralWrapper(replace(settings(), local_files_only=False))
    with pytest.raises(RuntimeError, match="non autorizzato"):
        model.load()


@pytest.mark.parametrize("change", [{"revision": "main"}, {"code_revision": "DA DECIDERE"},
    {"device": "auto"}, {"size": "28M"}, {"context_steps": 0}, {"horizon_steps": True},
    {"symmetric_averaging": "DA DECIDERE"}, {"quantile_real_cap_k": -1},
    {"missing_input_policy": "fill"}, {"package_version": "unknown"}])
def test_invalid_settings(change: dict[str, object]) -> None:
    with pytest.raises((ValueError, TypeError)):
        replace(settings(), **change).validate()


def test_checkpoint_capabilities_and_device_mismatch_are_explicit() -> None:
    backend = FakeBackend()
    backend.supports_known_covariates = False
    with pytest.raises(ValueError, match="future note"):
        TimestralWrapper(replace(settings(), variant="past_known"), backend).predict(features(), "2026-01-01T02:00Z")
    backend.device = "cuda:1"
    with pytest.raises(ValueError, match="Dispositivo"):
        TimestralWrapper(settings(), backend).predict(dataset(), "2026-01-01T02:00Z")


def test_malformed_model_output_is_rejected() -> None:
    class CrossingBackend(FakeBackend):
        """Return invalid quantiles to prove no wrapper repair happens."""

        def forecast(self, context: np.ndarray, prediction_length: int, **kwargs: object) -> object:
            result = super().forecast(context, prediction_length, **kwargs)
            result.quantiles[..., 0] = 100
            return result

    with pytest.raises(ValueError, match="incrociati"):
        TimestralWrapper(settings(), CrossingBackend()).predict(dataset(), "2026-01-01T02:00Z")


def test_project_settings_remain_unresolved_and_disabled() -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    assert project["models"]["timestral"]["enabled"] is False
    with pytest.raises(ValueError, match="DA DECIDERE"):
        TimestralSettings.from_project_config(project, "target_only")


@pytest.mark.skipif(os.environ.get("SOLARWINDCAST_RUN_CACHED_TIMESTRAL") != "1",
                    reason="Prova reale opt-in, solo pesi già in cache: vedere docs/timestral.md")
def test_cached_timestral_smoke() -> None:
    """One small real CPU forecast with synthetic target, past and known covariates."""
    synthetic = SyntheticConfig("solar", "2026-01-01T00:00:00Z", "1h", 72,
                                 100., 10., 72, 5., 1., .05, 42)
    data = generate(synthetic)
    origin = data.frame.index[64].isoformat()
    request = WeatherRequest("reanalysis", Location("synthetic_point", 41, 16),
        data.frame.index[0].isoformat(), (data.frame.index[-1] + pd.Timedelta(hours=1)).isoformat(),
        "synthetic_fixture", ("temperature_2m",))
    payload = {"utc_offset_seconds": 0, "hourly_units": {"temperature_2m": "°C"},
               "hourly": {"time": data.frame.index.strftime("%Y-%m-%dT%H:%M").tolist(),
                          "temperature_2m": (10 + np.sin(np.arange(72) / 24)).tolist()}}
    observed = parse_response(payload, request, {"provenance": "synthetic fixture, no weather download"})
    binding = WeatherBinding("synthetic", observed, "past", ("temperature_2m",),
                              (("temperature_2m", "instant_at_start"),), "0h", "synthetic fixture only")
    config = FeatureConfig(CalendarConfig("IT", "UTC", ("hour",), True),
                           ("weather_synthetic_temperature_2m",), ("calendar_hour",), "exact")
    combined = assemble_features(data, config, (binding,), origin)
    model = TimestralWrapper(replace(settings(), context_steps=64, horizon_steps=8, variant="past_known"))
    result = model.predict(combined, origin)
    assert result.quantiles.shape == (8, 21)
    assert result.metadata["backend_mode"] == "loaded_timestral"
    assert result.metadata["weights_revision"] == WEIGHTS_REVISION
    assert np.isfinite(result.quantiles.to_numpy()).all()
    print(json.dumps({"provenance": {k: result.metadata[k] for k in (
        "package_version", "code_revision", "weights_revision", "checkpoint_hashes", "torch_version", "device")},
        "shape": list(result.quantiles.shape), "missing_inputs": result.metadata["missing_input_counts"],
        "first_medians": result.point.iloc[:3].tolist()}, indent=2))
