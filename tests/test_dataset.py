"""Synthetic tests for the UTC dataset contract and its non-mutating checks."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset, fixed_step


def sample() -> TimeSeriesDataset:
    """Build a small frame including distinct covariate roles and missing data."""
    frame = pd.DataFrame(
        {"target": [1.0, np.nan, -2.0], "temperature": [-3.0, 0.0, np.nan],
         "calendar_signal": [0.0, 1.0, 0.0]},
        index=pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC",
                            name="timestamp_utc"),
    )
    spec = DatasetSpec("residual_load", "1h", ("temperature",), ("calendar_signal",),
                       (("temperature", "degC"), ("calendar_signal", "dimensionless")),
                       "synthetic fixture")
    return TimeSeriesDataset(frame, spec)


def test_valid_dataset_preserves_nan_and_negative_values() -> None:
    dataset = sample()
    original = dataset.frame.copy(deep=True)
    dataset.validate()
    pd.testing.assert_frame_equal(dataset.frame, original)


@pytest.mark.parametrize("fault", ["naive", "local", "duplicate", "unordered", "gap",
                                    "nat", "empty", "wrong_name", "text", "inf", "extra"])
def test_rejects_invalid_frame_without_repair(fault: str) -> None:
    dataset = sample()
    frame = dataset.frame
    if fault == "naive":
        frame.index = frame.index.tz_localize(None)
    elif fault == "local":
        frame.index = frame.index.tz_convert("Europe/Rome")
    elif fault == "duplicate":
        frame.index = frame.index.take([0, 0, 2])
    elif fault == "unordered":
        frame = frame.iloc[::-1]
    elif fault == "gap":
        frame = frame.iloc[[0, 2]]
    elif fault == "nat":
        frame.index = pd.DatetimeIndex([frame.index[0], pd.NaT, frame.index[2]],
                                       name="timestamp_utc")
    elif fault == "empty":
        frame = frame.iloc[:0]
    elif fault == "wrong_name":
        frame.index.name = "time"
    elif fault == "text":
        frame["target"] = ["1", "N/A", "2"]
    elif fault == "inf":
        frame.loc[frame.index[0], "target"] = np.inf
    elif fault == "extra":
        frame["undeclared"] = 1.0
    dataset.frame = frame
    original = frame.copy(deep=True)
    with pytest.raises(ValueError):
        dataset.validate()
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize("change", [
    {"known_future_covariates": ("temperature",)},
    {"past_covariates": ("target",)}, {"covariate_units": ()},
    {"target": "DA DECIDERE"}, {"target_unit": "MWh"}, {"provenance": ""},
])
def test_rejects_ambiguous_metadata(change: dict[str, object]) -> None:
    dataset = sample()
    dataset.spec = replace(dataset.spec, **change)
    with pytest.raises(ValueError):
        dataset.validate()


@pytest.mark.parametrize("frequency", ["0h", "-1h", "ME", "DA DECIDERE"])
def test_rejects_invalid_or_nonfixed_frequency(frequency: str) -> None:
    with pytest.raises(ValueError):
        fixed_step(frequency)
