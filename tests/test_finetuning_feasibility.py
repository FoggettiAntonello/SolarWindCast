"""Synthetic chronological split checks and differentiability without parameter updates."""

import pandas as pd
import pytest
import torch
from timestral.config import TimestralConfig
from timestral.forecaster import TimestralForecaster
from timestral.model import TimestralModel

from solarwindcast.finetuning_feasibility import (
    development_audit,
    state_digest,
    synthetic_gradient_probe,
)


def test_development_audit_purges_unavailable_labels_and_ignores_test() -> None:
    index = pd.period_range("2021-11", periods=60, freq="M")
    months = pd.DataFrame({"mean_power_mw": 100., "complete": True,
        "start_utc": [period.start_time.tz_localize("UTC").isoformat() for period in index]}, index=index)
    protocol = {"context_months": 24, "unavailable_recent_months": 1, "minimum_valid_context_months": 12,
        "prediction_length_months": 2, "baseline_seasonal_lag_months": 12, "residual_lookback_months": 24,
        "minimum_calibration_errors": 12, "issue_lead_hours": 12}
    periods = {"development_start_utc": "2021-11-01T00:00Z", "test_start_utc": "2024-11-01T00:00Z"}
    result = development_audit(months, periods, protocol, [3, 6])
    assert result["usable_origins"] == 11
    assert [len(split["training_months"]) for split in result["split_examples"]] == [7, 4]
    assert [len(split["purged_months"]) for split in result["split_examples"]] == [1, 1]
    months.loc[months.index >= pd.Period("2024-11", freq="M"), "mean_power_mw"] = 1e20
    assert development_audit(months, periods, protocol, [3, 6]) == result
    with pytest.raises(ValueError):
        development_audit(months, periods, protocol, [11])


@pytest.mark.parametrize("variant", ["target_only", "known_calendar"])
def test_tiny_random_model_gradients_match_public_inference_and_preserve_weights(variant: str) -> None:
    config = TimestralConfig(patch_size=4, d_model=16, num_heads=2, mlp_hidden_dim=32,
        block_schedule=("time", "variate", "time"), quantile_knots=(.05, .1, .5, .9, .95),
        block_size=2, context_length=32)
    with torch.random.fork_rng():
        torch.manual_seed(7)
        model = TimestralModel(config)
    forecaster = TimestralForecaster(model, max_context=24, per_shot_horizon_patches=1, quantile_real_cap_k=0)
    before = state_digest(model)
    result = synthetic_gradient_probe(forecaster, 24, 2, variant)
    assert result["optimizer_steps"] == 0
    assert result["public_private_agree"] and result["finite_nonzero_gradients"]
    assert result["output_shape"] == [1, 1, 2, 5]
    assert result["state_sha256_after"] == before == state_digest(model)
    assert all(parameter.requires_grad for parameter in model.parameters())
    assert all(parameter.grad is None for parameter in model.parameters())
