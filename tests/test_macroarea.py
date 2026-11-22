"""Synthetic strict geographical sums preserving missing values, units and original datasets."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.macroarea import (
    AreaRegime,
    aggregate_observed_areas,
    aggregate_regimes,
)


def observed(values: list[float], target: str = "solar") -> TimeSeriesDataset:
    """Small synthetic hourly UTC observed series, independent of real area values."""
    index = pd.date_range("2026-01-01", periods=len(values), freq="1h", tz="UTC", name="timestamp_utc")
    return TimeSeriesDataset(pd.DataFrame({"target": values}, index=index), DatasetSpec(target,"1h",(),(),(),"synthetic"))


def test_strict_observed_sum_preserves_missing_sign_and_inputs() -> None:
    first, second = observed([10., np.nan, -3.]), observed([2., 5., 1.])
    original = first.frame.copy(deep=True)
    result = aggregate_observed_areas({"SUD":first,"CALA":second},("SUD","CALA"),"Sud + Calabria")
    assert result.frame.target.iloc[0] == 12
    assert pd.isna(result.frame.target.iloc[1])
    assert result.frame.target.iloc[2] == -2
    assert result.spec.target_unit == "MW" and "CALA" in result.spec.provenance
    pd.testing.assert_frame_equal(first.frame,original)


@pytest.mark.parametrize("required", [("SUD","SUD"),("SUD",),("SUD","CALA","EXTRA")])
def test_refuse_missing_extra_or_duplicate_area_identity(required: tuple[str, ...]) -> None:
    with pytest.raises(ValueError):
        aggregate_observed_areas({"SUD":observed([1.]),"CALA":observed([2.])},required,"example")


def test_refuse_mismatched_target_grid_or_covariates() -> None:
    first,second=observed([1.,2.]),observed([3.,4.],"wind")
    with pytest.raises(ValueError):
        aggregate_observed_areas({"SUD":first,"CALA":second},("SUD","CALA"),"example")


def test_regime_switch_uses_only_active_areas_and_does_not_double_count_boundary() -> None:
    index = pd.date_range("2020-12-31T22:00Z", periods=4, freq="1h", name="timestamp_utc")

    def series(values: list[float]) -> TimeSeriesDataset:
        """Synthetic transition values, without assuming anything about real Rossano."""
        return TimeSeriesDataset(pd.DataFrame({"target":values},index=index),DatasetSpec("wind","1h",(),(),(),"synthetic"))

    areas={"SUD":series([10.,10.,10.,10.]),"ROSN":series([2.,np.nan,np.nan,np.nan]),"CALA":series([np.nan,3.,4.,5.])}
    regimes=(AreaRegime("2020-12-31T22:00Z","2020-12-31T23:00Z",("SUD","ROSN"),"synthetic old scope"),
        AreaRegime("2020-12-31T23:00Z","2021-01-01T02:00Z",("SUD","CALA"),"synthetic new scope"))
    result=aggregate_regimes(areas,regimes,"test")
    assert result.frame.target.tolist()==[12.,13.,14.,15.]
    assert result.frame.index.equals(index)
    with pytest.raises(ValueError,match="contigui"):
        aggregate_regimes(areas,(regimes[0],replace(regimes[1],start_utc="2021-01-01T00:00Z")),"test")
    with pytest.raises(ValueError,match="coprono"):
        aggregate_regimes(areas,(replace(regimes[0],start_utc="2020-12-31T23:00Z",end_exclusive_utc="2021-01-01T00:00Z"),
            replace(regimes[1],start_utc="2021-01-01T00:00Z")),"test")
    areas["CALA"].spec = replace(areas["CALA"].spec, target="solar")
    with pytest.raises(ValueError, match="Target"):
        aggregate_regimes(areas, (regimes[0], replace(regimes[1], required_eics=("CALA",))), "test")


def test_misaligned_and_covariate_inputs_are_refused() -> None:
    first = observed([1., 2.])
    second=observed([3.,4.])
    second.frame.index += pd.Timedelta(hours=1)
    with pytest.raises(ValueError):
        aggregate_observed_areas({"SUD":first,"CALA":second},("SUD","CALA"),"example")
    second=observed([3.,4.])
    second.frame["known"]=1.
    second.spec=replace(second.spec,known_future_covariates=("known",),covariate_units=(("known","dimensionless"),))
    with pytest.raises(ValueError):
        aggregate_observed_areas({"SUD":first,"CALA":second},("SUD","CALA"),"example")
