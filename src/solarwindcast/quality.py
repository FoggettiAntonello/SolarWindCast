"""Report gaps without filling them or changing the original cadence."""

import math

import pandas as pd


def report(
    frame: pd.DataFrame,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    expected_frequency: str | None = None,
) -> dict[str, object]:
    if not isinstance(frame.index, pd.DatetimeIndex) or frame.index.tz is None:
        raise ValueError("Il rapporto richiede timestamp con fuso orario.")
    frame = frame.copy()
    frame.index = frame.index.tz_convert("UTC")
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    frame = frame.loc[(frame.index >= start) & (frame.index < end)]
    unique = frame.index.drop_duplicates().sort_values()
    result = {
        "rows": len(frame), "duplicate_timestamps": int(frame.index.duplicated().sum()),
        "first_utc": unique.min().isoformat() if len(unique) else None,
        "last_utc": unique.max().isoformat() if len(unique) else None,
        "observed_step_seconds": sorted(set(unique.to_series().diff().dropna().dt.total_seconds())),
        "expected_frequency": expected_frequency, "missing_timestamps": None,
        "off_grid_timestamps": None, "columns": [],
    }
    if expected_frequency is not None:
        expected = pd.date_range(start, end, freq=expected_frequency, inclusive="left")
        result["expected_rows"] = len(expected)
        result["missing_timestamps"] = len(expected.difference(unique))
        result["off_grid_timestamps"] = len(unique.difference(expected))
    for column in frame.columns:
        values = pd.to_numeric(frame[column], errors="coerce")
        finite = values.dropna().map(math.isfinite)
        result["columns"].append({
            "name": list(column) if isinstance(column, tuple) else str(column),
            "non_null": int(values.notna().sum()), "missing": int(values.isna().sum()),
            "non_finite": int((~finite).sum()), "negative": int((values < 0).sum()),
            "missing_times_utc": [t.isoformat() for t in frame.index[values.isna()]],
        })
    # No expected grid means that completeness cannot be established.
    result["complete"] = (
        expected_frequency is not None and len(frame) > 0 and len(frame.columns) > 0
        and result["missing_timestamps"] == 0 and result["off_grid_timestamps"] == 0
        and result["duplicate_timestamps"] == 0
        and all(c["missing"] == 0 and c["non_finite"] == 0 for c in result["columns"])
    )
    return result
