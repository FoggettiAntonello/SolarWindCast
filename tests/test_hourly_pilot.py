"""Synthetic delay/leakage and hourly score checks for the short pilot."""

import numpy as np
import pandas as pd
import pytest

from solarwindcast.hourly_pilot import baseline_arrays, metrics


def test_cutoff_excludes_unpublished_and_future_values() -> None:
    cfg = dict(assumed_delay_hours=24, context_hours=672, horizon_hours=24,
               seasonal_lags_hours=[48,168], minimum_hour_samples=20,
               quantiles=[.05,.1,.5,.9,.95])
    index = pd.date_range('2025-01-01', periods=1000, freq='h', tz='UTC')
    series = pd.Series(np.arange(1000, dtype=float), index=index)
    origin = index[800]
    original = baseline_arrays(series, origin, cfg)
    series.loc[index[776]:] = -9999
    changed = baseline_arrays(series, origin, cfg)
    for name in original:
        np.testing.assert_array_equal(original[name], changed[name])
    assert original['persistence'][0] == 775
    cfg['seasonal_lags_hours'] = [24]
    with pytest.raises(ValueError, match='disponibili'):
        baseline_arrays(series, origin, cfg)


def test_hourly_metrics_exact_error_and_coverage() -> None:
    cfg = dict(quantiles=[.05,.1,.5,.9,.95], interval_levels=[.8,.9])
    actual=np.array([10.,20.])
    point=np.array([12.,18.])
    q=np.array([[8,9,12,14,15],[15,16,18,21,22]],dtype=float)
    result=metrics(actual,point,q,cfg)
    assert result['mae_mw']==result['rmse_mw']==2
    assert result['coverage_0.8']==1 and result['width_0.8_mw']==5
