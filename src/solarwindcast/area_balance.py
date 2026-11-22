"""Diagnose an observed national/area partition without inferring zeros or geographical validity."""

import math
from collections.abc import Mapping

from solarwindcast.dataset import TimeSeriesDataset, fixed_step
from solarwindcast.macroarea import aggregate_observed_areas


def compare_partition(national: TimeSeriesDataset, areas: Mapping[str, TimeSeriesDataset],
                       required_eics: tuple[str, ...], pole_eic: str,
                       numerical_tolerance_mw: float) -> dict[str, object]:
    """Compare the same intervals with/without one pole; classify only when coverage is complete.

    A successful single-day closure is empirical support, not proof of historical
    geographical equivalence or independence of the provider's national totals.
    The tolerance is numerical only and must not be fitted to obtain a closure.
    """
    if (not math.isfinite(numerical_tolerance_mw) or numerical_tolerance_mw < 0
            or pole_eic not in required_eics or len(required_eics) < 2):
        raise ValueError("Polo, partizione e tolleranza numerica non validi.")
    national.validate()
    included = aggregate_observed_areas(areas, required_eics, "partition with pole")
    remaining = tuple(eic for eic in required_eics if eic != pole_eic)
    excluded = aggregate_observed_areas({eic: areas[eic] for eic in remaining}, remaining, "partition without pole")
    if (national.spec.target != included.spec.target or national.spec.frequency != included.spec.frequency
            or not national.frame.index.equals(included.frame.index)):
        raise ValueError("Totale nazionale e zone non hanno stesso target/frequenza/griglia.")
    actual = national.frame.target
    valid = actual.notna() & included.frame.target.notna() & excluded.frame.target.notna()
    residual_with = actual - included.frame.target
    residual_without = actual - excluded.frame.target
    maximum_with = float(residual_with[valid].abs().max()) if valid.any() else None
    maximum_without = float(residual_without[valid].abs().max()) if valid.any() else None
    complete = bool(valid.all())
    with_close = complete and maximum_with <= numerical_tolerance_mw
    without_close = complete and maximum_without <= numerical_tolerance_mw
    if not complete:
        classification = "incomplete_coverage_no_inference"
    elif with_close and not without_close:
        classification = "sample_supports_disjoint_pole"
    elif without_close and not with_close:
        classification = "sample_supports_pole_already_in_other_areas"
    elif with_close and without_close:
        classification = "both_close_pole_uninformative"
    else:
        classification = "neither_partition_closes"
    hours = fixed_step(national.spec.frequency).total_seconds() / 3600
    return {"classification": classification, "expected_intervals": len(actual), "common_intervals": int(valid.sum()),
        "numerical_tolerance_mw": numerical_tolerance_mw,
        "maximum_absolute_residual_with_pole_mw": maximum_with,
        "maximum_absolute_residual_without_pole_mw": maximum_without,
        "national_energy_mwh": float(actual.sum() * hours) if complete else None,
        "sum_with_pole_energy_mwh": float(included.frame.target.sum() * hours) if complete else None,
        "sum_without_pole_energy_mwh": float(excluded.frame.target.sum() * hours) if complete else None,
        "pole_energy_mwh": float(areas[pole_eic].frame.target.sum() * hours) if complete else None,
        "historical_rule_proven_for_all_dates": False,
        "records": [{"timestamp_utc": stamp.isoformat(), "national_mw": None if not valid.loc[stamp] else float(actual.loc[stamp]),
            "residual_with_pole_mw": None if not valid.loc[stamp] else float(residual_with.loc[stamp]),
            "residual_without_pole_mw": None if not valid.loc[stamp] else float(residual_without.loc[stamp])} for stamp in actual.index]}
