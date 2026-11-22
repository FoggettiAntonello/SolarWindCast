"""Reproducibility, signal and missing-data tests using fixture-only parameters."""

from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.synthetic import SyntheticConfig, generate


def settings() -> SyntheticConfig:
    """Return test values, never proposed real-data experiment settings."""
    return SyntheticConfig(
        target="solar", start_utc="2026-01-01T00:00:00Z", frequency="15min",
        number_of_steps=192, baseline_mw=100.0, daily_cycle_amplitude=20.0,
        seasonal_period_steps=192, seasonal_amplitude=10.0, noise_scale=2.0,
        missing_fraction=0.1, random_seed=42,
    )


@pytest.mark.parametrize("target", ["solar", "wind", "load", "residual_load"])
def test_all_targets_reproducible_and_keep_missing_rows(target: str) -> None:
    config = replace(settings(), target=target)
    first, second = generate(config), generate(config)
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert first.spec.target == target
    assert len(first.frame) == config.number_of_steps
    assert first.frame["target"].isna().sum() == 19
    assert str(first.frame.index.tz) == "UTC"
    assert first.spec.past_covariates == first.spec.known_future_covariates == ()


def test_daily_and_seasonal_components_follow_configured_cycles() -> None:
    config = replace(settings(), noise_scale=0, missing_fraction=0, seasonal_amplitude=0)
    daily = generate(config).frame["target"]
    np.testing.assert_allclose(daily.iloc[:96], daily.iloc[96:], atol=1e-12)
    assert daily.iloc[24] == pytest.approx(120)
    assert daily.iloc[72] == pytest.approx(80)
    seasonal = generate(replace(config, daily_cycle_amplitude=0,
                                seasonal_amplitude=10, seasonal_period_steps=48)).frame["target"]
    assert seasonal.iloc[12] == pytest.approx(110)
    assert seasonal.iloc[36] == pytest.approx(90)


def test_frequency_and_start_control_calendar_phase() -> None:
    config = replace(settings(), frequency="1h", start_utc="2026-01-01T06:00:00Z",
                     noise_scale=0, missing_fraction=0, seasonal_amplitude=0)
    result = generate(config).frame
    assert result["target"].iloc[0] == pytest.approx(120)
    assert result.index[1] - result.index[0] == pd.Timedelta(hours=1)


def test_gaps_do_not_change_other_values_and_seed_changes_signal() -> None:
    config = settings()
    full = generate(replace(config, missing_fraction=0)).frame
    gaps = generate(config).frame
    mask = gaps["target"].notna()
    pd.testing.assert_frame_equal(full.loc[mask], gaps.loc[mask])
    assert not full.equals(generate(replace(config, random_seed=43)).frame)


@pytest.mark.parametrize("fraction, count", [(0, 0), (1, 192)])
def test_missing_fraction_boundaries(fraction: float, count: int) -> None:
    result = generate(replace(settings(), missing_fraction=fraction))
    assert result.frame["target"].isna().sum() == count


@pytest.mark.parametrize("change", [
    {"number_of_steps": 0}, {"number_of_steps": True}, {"seasonal_period_steps": 0},
    {"random_seed": -1}, {"missing_fraction": -0.1}, {"missing_fraction": 1.1},
    {"noise_scale": -1}, {"noise_scale": float("nan")}, {"baseline_mw": float("inf")},
    {"frequency": "ME"}, {"start_utc": "2026-01-01"}, {"target": "DA DECIDERE"},
])
def test_invalid_settings_fail_before_generation(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        generate(replace(settings(), **change))


def test_project_mapping_and_unresolved_yaml() -> None:
    values = asdict(settings())
    target = values.pop("target")
    config = SyntheticConfig.from_project_config({"target": {"selected": target},
                                                   "synthetic": values})
    assert config == settings()
    path = Path(__file__).resolve().parents[1] / "configs" / "project.yaml"
    project = yaml.safe_load(path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        SyntheticConfig.from_project_config(project)


def test_rejects_missing_config_sections() -> None:
    with pytest.raises(TypeError, match="sezioni"):
        SyntheticConfig.from_project_config({})
