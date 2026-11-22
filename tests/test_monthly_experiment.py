"""Synthetic calendar forecasts, leakage checks, common-case metrics and frozen end-to-end execution."""

import json
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from solarwindcast.monthly_experiment import (
    check_frozen_protocol,
    run_experiment,
    score_predictions,
)
from solarwindcast.monthly_forecasting import MonthlyTimestral, baseline_predictions

LEVELS = (.01, .05, .1, .15, .2, .25, .3, .35, .4, .45, .5, .55, .6, .65, .7, .75, .8, .85, .9, .95, .99)


def protocol() -> dict[str, object]:
    """Small fixture values, explicitly different from approved real-data history lengths."""
    return {"approved": True, "experiment_enabled": False, "calendar_timezone": "UTC", "targets": ["solar", "wind"],
        "wind_components": ["wind_onshore", "wind_offshore"], "context_months": 3,
        "unavailable_recent_months": 1, "issue_lead_hours": 12, "prediction_length_months": 2,
        "minimum_valid_context_months": 2, "minimum_calibration_errors": 2,
        "baseline_methods": ["last_complete_month", "same_month_previous_year", "recent_complete_months"],
        "baseline_recent_months": 2, "baseline_seasonal_lag_months": 2,
        "probabilistic_baseline": "seasonal_empirical_rolling_errors", "residual_lookback_months": 3,
        "residual_quantile_method": "linear", "comparison_quantile_levels": [.05, .1, .5, .9, .95],
        "interval_levels": [.8, .9], "model_variants": ["target_only", "known_calendar"],
        "future_calendar_features": ["month_sin", "month_cos"], "device": "cpu",
        "missing_input_policy": "native_mask", "symmetric_averaging": False, "clip_nonnegative": False,
        "quantile_real_cap_k": 0., "per_shot_horizon_patches": 1, "extreme_value_threshold": 1e30,
        "local_files_only": True, "weather_enabled": False, "package_version": "1.0.0",
        "code_revision": "a534bdbd244d64f3d9d743f46c7bf6fc330ed4ff",
        "models": [{"size": "5M", "revision": "bdd20cfc15a3fea0e4cb5ccef37f8d3ca7aa335f"}]}


def monthly_data() -> pd.DataFrame:
    """Ten complete UTC months with power trends; no model generated observations."""
    index = pd.period_range("2024-01", "2024-10", freq="M", name="month")
    starts = pd.date_range("2024-01-01", periods=11, freq="MS", tz="UTC")
    hours = np.asarray([(end - start) / pd.Timedelta(hours=1) for start, end in pairwise(starts)])
    values = np.arange(10, dtype=float) + 10
    return pd.DataFrame({"mean_power_mw": values, "energy_mwh": values * hours, "duration_hours": hours,
        "start_utc": [value.isoformat() for value in starts[:-1]], "complete": True}, index=index)


class FakeBackend:
    """Record arrays and create monotone quantiles with distinguishable horizon steps."""

    def __init__(self, context: int) -> None:
        self.config = SimpleNamespace(context_length=32768, block_size=32)
        self.max_context, self.device = context, "cpu"
        self.supports_known_covariates = True
        self.quantile_levels = LEVELS
        self.received = {}

    def forecast(self, context: np.ndarray, prediction_length: int, **kwargs: object) -> object:
        self.received = {"context": context.copy(), "prediction_length": prediction_length, **kwargs}
        values = (np.tile(LEVELS, (1, 1, prediction_length, 1)) + float(np.nanmean(context))
                  + np.arange(prediction_length)[None, None, :, None] * 10)
        return SimpleNamespace(quantile_levels=LEVELS, quantiles=values)


def test_monthly_model_uses_second_step_and_calendar_only_known_at_origin() -> None:
    cfg = protocol()
    frame = monthly_data()
    backend = FakeBackend(3)
    wrapper = MonthlyTimestral(cfg, cfg["models"][0], backend)
    target = pd.Period("2024-07", freq="M")
    result = wrapper.predict(frame, target, "known_calendar")
    # Context March-May, June is the gap; score July, with 744 hours.
    expected = (13 + 10 + .5) * 744
    assert result.point_mwh == pytest.approx(expected)
    assert result.metadata["decoded_months"] == ["2024-06", "2024-07"]
    assert backend.received["known_covariates"].shape == (1, 2, 5)
    before = backend.received["context"].copy()
    frame.loc[pd.Period("2024-06", freq="M"), "mean_power_mw"] = 1e20
    frame.loc[target, "mean_power_mw"] = -1e20
    changed = wrapper.predict(frame, target, "known_calendar")
    np.testing.assert_array_equal(backend.received["context"], before)
    pd.testing.assert_series_equal(result.quantiles_mwh, changed.quantiles_mwh)


def test_baseline_weights_durations_and_calibration_never_reads_future() -> None:
    frame, cfg = monthly_data(), protocol()
    target = pd.Period("2024-07", freq="M")
    outputs = {value.model: value for value in baseline_predictions(frame, target, cfg)}
    assert outputs["same_month_previous_year"].point_mwh == 14 * 744  # Fixture lag is two months.
    assert outputs["recent_complete_months"].point_mwh == pytest.approx((13*720 + 14*744) / (720+744) * 744)
    empirical = outputs[cfg["probabilistic_baseline"]]
    assert empirical.metadata["calibration_pairs"] == 3
    assert empirical.quantiles_mwh.loc[.5] == 16 * 744
    frame.loc[pd.Period("2024-06", freq="M"), "mean_power_mw"] = 1e30
    changed = {value.model: value for value in baseline_predictions(frame, target, cfg)}
    pd.testing.assert_series_equal(empirical.quantiles_mwh, changed[cfg["probabilistic_baseline"]].quantiles_mwh)


def test_common_scores_do_not_reward_missing_predictions() -> None:
    cfg = protocol()
    rows = []
    for month, actual in (("2024-07", 100.), ("2024-08", 200.), ("2024-09", None)):
        for model in ("same_month_previous_year", "toy"):
            rows.append({"target": "solar", "phase": "test", "model": model, "month": month,
                "target_start_utc": month + "-01T00:00:00+00:00", "actual_mwh": actual,
                "point_mwh": None if model == "toy" and month == "2024-08" else 110., "quantiles_mwh": None})
    result = score_predictions(rows, cfg)["solar"]["test"]
    assert result["models"]["toy"]["point_cases"] == 1
    assert result["models"]["same_month_previous_year"]["point_cases"] == 1
    assert result["models"]["toy"]["point_scores"]["mae_mwh"] == 10
    rows[1]["quantiles_mwh"] = {"0.05": -10., "0.1": 0., "0.5": 110., "0.9": 120., "0.95": 130.}
    diagnostics = score_predictions(rows, cfg)["solar"]["test"]["models"]["toy"]
    assert diagnostics["negative_quantile_forecast_months"] == 1


def test_end_to_end_synthetic_frozen_run_and_tamper_rejection(tmp_path: Path) -> None:
    cfg = protocol()
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    index = pd.date_range("2024-01-01", "2024-11-01", inclusive="left", freq="1h", tz="UTC", name="timestamp_utc")
    quality = {}
    for name in ("solar", "wind_onshore", "wind_offshore"):
        frame = pd.DataFrame({"target": index.month.astype(float) + 10}, index=index)
        if name == "solar":
            frame.loc[pd.Timestamp("2024-10-01", tz="UTC"), "target"] = np.nan
        frame.to_parquet(prepared / (name + ".parquet"))
        quality[name] = {"target": "solar" if name == "solar" else "wind", "frequency": "1h", "unit": "MW", "provenance": "synthetic"}
    (prepared / "quality.json").write_text(json.dumps(quality))
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in prepared.iterdir()}
    (prepared / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}))
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    periods = {"development_start_utc": "2024-01-01T00:00Z", "test_start_utc": "2024-07-01T00:00Z", "test_end_exclusive_utc": "2024-11-01T00:00Z"}
    snapshot = {"settings": cfg, "settings_sha256": sha256(json.dumps(cfg, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "source_prepared_manifest_sha256": sha256((prepared / "manifest.json").read_bytes()).hexdigest(), "evaluation_periods": periods}
    path = frozen / "protocol_snapshot.json"
    path.write_text(json.dumps(snapshot))
    (frozen / "manifest.json").write_text(json.dumps({"files_sha256": {path.name: sha256(path.read_bytes()).hexdigest()}}))
    project = {"monthly_protocol": cfg, "monthly_execution": {"authorized": True, "frozen_protocol_directory": "frozen", "cpu_threads": 1},
               "monthly_inspection": {"prepared_directory": "prepared"}}

    def factory(settings: dict[str, object], model: dict[str, str]) -> MonthlyTimestral:
        return MonthlyTimestral(settings, model, FakeBackend(settings["context_months"]))

    result = run_experiment(project, tmp_path, tmp_path / "result", factory)
    assert result["kind"] == "synthetic_injected_monthly_test"
    assert result["evaluation_periods"] == periods
    assert len(result["frozen_snapshot_sha256"]) == 64
    assert result["scores"]["solar"]["test"]["observed_months"] == 3
    assert result["scores"]["wind"]["test"]["observed_months"] == 4
    assert "<svg" in (tmp_path / "result/presentazione.html").read_text(encoding="utf-8")
    cfg["context_months"] = 4
    with pytest.raises(ValueError, match="Impostazioni"):
        check_frozen_protocol(project, tmp_path)
