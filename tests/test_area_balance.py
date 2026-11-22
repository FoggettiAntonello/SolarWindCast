"""Synthetic partition closure distinguishing omitted poles, overlap, missingness and unexplained gaps."""

import numpy as np
import pandas as pd
import pytest

from solarwindcast.area_balance import compare_partition
from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset


def dataset(values: list[float]) -> TimeSeriesDataset:
    """Synthetic hourly observations, with no real Italian production values."""
    index = pd.date_range("2020-12-30", periods=len(values), freq="1h", tz="UTC", name="timestamp_utc")
    return TimeSeriesDataset(pd.DataFrame({"target": values}, index=index), DatasetSpec("solar", "1h", (), (), (), "synthetic"))


@pytest.mark.parametrize("national,expected", [
    ([5., 5.], "sample_supports_disjoint_pole"),
    ([3., 3.], "sample_supports_pole_already_in_other_areas"),
    ([7., 7.], "neither_partition_closes"),
])
def test_compare_both_hypotheses_on_identical_intervals(national: list[float], expected: str) -> None:
    result = compare_partition(dataset(national), {"other": dataset([3., 3.]), "pole": dataset([2., 2.])},
        ("other", "pole"), "pole", 1e-6)
    assert result["classification"] == expected
    assert result["common_intervals"] == 2
    assert result["historical_rule_proven_for_all_dates"] is False


def test_missing_intervals_cannot_support_a_global_closure() -> None:
    result = compare_partition(dataset([5., 5.]), {"other": dataset([3., 3.]), "pole": dataset([2., np.nan])},
        ("other", "pole"), "pole", 1e-6)
    assert result["classification"] == "incomplete_coverage_no_inference"
    assert result["common_intervals"] == 1 and result["national_energy_mwh"] is None


def test_zero_pole_and_misaligned_grid_are_not_evidence_of_disjointness() -> None:
    areas = {"other": dataset([3., 3.]), "pole": dataset([0., 0.])}
    assert compare_partition(dataset([3., 3.]), areas, ("other", "pole"), "pole", 0.)["classification"] == "both_close_pole_uninformative"
    shifted = dataset([3., 3.])
    shifted.frame.index += pd.Timedelta(hours=1)
    with pytest.raises(ValueError):
        compare_partition(shifted, areas, ("other", "pole"), "pole", 1e-6)
