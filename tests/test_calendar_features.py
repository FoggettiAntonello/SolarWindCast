"""Date-only fixture tests, including Italian local dates and DST changes."""

from dataclasses import replace

import pandas as pd
import pytest

from solarwindcast.calendar_features import CalendarConfig, calendar_features


def settings() -> CalendarConfig:
    """Select fixture features without setting the project defaults."""
    return CalendarConfig("IT", "Europe/Rome", ("hour", "day_of_week", "is_holiday"), True)


def test_holiday_follows_selected_timezone_and_keeps_utc_index() -> None:
    index = pd.DatetimeIndex(["2025-12-31T23:00Z", "2026-01-01T23:00Z"], name="timestamp_utc")
    local = calendar_features(index, settings())
    utc = calendar_features(index, replace(settings(), timezone="UTC"))
    assert local["calendar_is_holiday"].tolist() == [1, 0]
    assert utc["calendar_is_holiday"].tolist() == [0, 1]
    assert local["calendar_hour"].tolist() == [0, 0]
    pd.testing.assert_index_equal(local.index, index)


def test_easter_monday_is_in_the_national_calendar() -> None:
    index = pd.date_range("2026-04-06T12:00Z", periods=1, name="timestamp_utc")
    result = calendar_features(index, settings())
    assert result["calendar_is_holiday"].iloc[0] == 1
    assert result["calendar_day_of_week"].iloc[0] == 0


@pytest.mark.parametrize("start, expected", [("2026-03-29T00:00Z", [1, 3]),
                                            ("2026-10-25T00:00Z", [2, 2])])
def test_dst_does_not_create_or_remove_utc_rows(start: str, expected: list[int]) -> None:
    index = pd.date_range(start, periods=2, freq="h", name="timestamp_utc")
    result = calendar_features(index, settings())
    assert result["calendar_hour"].tolist() == expected
    assert result.index.is_unique


def test_optional_features_and_empty_selection() -> None:
    index = pd.date_range("2026-01-03T10:15Z", periods=1, name="timestamp_utc")
    cfg = replace(settings(), features=("minute", "month", "day_of_year", "is_weekend"))
    assert calendar_features(index, cfg).iloc[0].tolist() == [15, 1, 3, 1]
    assert calendar_features(index, replace(cfg, features=())).shape == (1, 0)


@pytest.mark.parametrize("change", [{"country": "XX"}, {"timezone": "DA DECIDERE"},
    {"features": ("unknown",)}, {"features": ("hour", "hour")}, {"observed": "DA DECIDERE"}])
def test_invalid_calendar_settings(change: dict[str, object]) -> None:
    with pytest.raises((ValueError, TypeError)):
        replace(settings(), **change).validate()


def test_naive_index_is_rejected() -> None:
    with pytest.raises(ValueError, match="UTC"):
        calendar_features(pd.date_range("2026-01-01", periods=1), settings())
