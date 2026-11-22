"""Date-only calendar covariates with an explicit timezone and Italian holidays."""

from collections.abc import Mapping
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import holidays
import pandas as pd

FEATURES = ("hour", "minute", "day_of_week", "month", "day_of_year", "is_weekend", "is_holiday")


@dataclass(frozen=True)
class CalendarConfig:
    """No timezone or feature selection is inferred from the host environment."""

    country: str
    timezone: str
    features: tuple[str, ...]
    observed: bool

    def validate(self) -> None:
        """Reject unsupported feature names and unresolved experiment choices."""
        if self.country != "IT":
            raise ValueError("Questo step supporta il calendario nazionale italiano (IT).")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError) as exc:
            raise ValueError("Specificare un fuso calendario valido, non DA DECIDERE.") from exc
        if len(set(self.features)) != len(self.features) or not set(self.features).issubset(FEATURES):
            raise ValueError("Feature di calendario sconosciute o duplicate.")
        if not isinstance(self.observed, bool):
            raise TypeError("observed deve essere esplicitamente true o false.")

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "CalendarConfig":
        """Read calendar options from the single YAML structure."""
        try:
            config = project["features"]["calendar"]
            if not isinstance(config["features"], list):
                raise TypeError("calendar.features deve essere una lista esplicita.")
            result = cls(config["country"], config["holiday_timezone_policy"],
                         tuple(config["features"]), config["observed"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Calendario incompleto o DA DECIDERE.") from exc
        result.validate()
        return result


def calendar_features(index: pd.DatetimeIndex, config: CalendarConfig) -> pd.DataFrame:
    """Return numeric date-only columns, retaining the input UTC index unchanged."""
    config.validate()
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing):
        raise ValueError("Il calendario richiede timestamp UTC ordinati, univoci e senza NaT.")
    local = index.tz_convert(config.timezone)
    values = {"hour": local.hour, "minute": local.minute, "day_of_week": local.day_of_week,
              "month": local.month, "day_of_year": local.day_of_year,
              "is_weekend": (local.day_of_week >= 5).astype(int)}
    if "is_holiday" in config.features:
        national = holidays.country_holidays("IT", years=sorted(set(local.year)),
                                             expand=False, observed=config.observed, language="it_IT")
        values["is_holiday"] = [int(day in national) for day in local.date]
    return pd.DataFrame({f"calendar_{name}": values[name] for name in config.features},
                        index=index, dtype=float)
