"""Common UTC dataset contract; validation never repairs input data."""

from dataclasses import dataclass, field
from itertools import pairwise
from numbers import Real
from typing import Literal

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

Target = Literal["solar", "wind", "load", "residual_load"]
TARGETS = ("solar", "wind", "load", "residual_load")


def quantile_levels(levels: tuple[float, ...]) -> None:
    """Require explicit numeric probabilities in increasing order without duplicates."""
    if (not levels or any(isinstance(q, bool) or not isinstance(q, Real)
                          or not np.isfinite(q) or not 0 <= q <= 1 for q in levels)
            or any(a >= b for a, b in pairwise(levels))):
        raise ValueError("Quantili: probabilità numeriche ordinate e univoche in [0, 1].")


def validate_quantile_frame(frame: pd.DataFrame) -> None:
    """Reject invalid values and crossing quantiles, including across NaN columns."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("I quantili devono essere un DataFrame.")
    quantile_levels(tuple(frame.columns))
    for name in frame:
        values = frame[name]
        if (not is_numeric_dtype(values.dtype) or is_bool_dtype(values.dtype)
                or np.iscomplexobj(values.to_numpy())):
            raise ValueError("Le previsioni dei quantili devono essere numeriche reali.")
    array = frame.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(array).any():
        raise ValueError("Quantili infiniti non ammessi.")
    previous_max = np.maximum.accumulate(np.where(np.isnan(array), -np.inf, array), axis=1)
    if (array < previous_max).any():
        raise ValueError("Quantili incrociati: nessun riordinamento automatico dei valori.")


@dataclass
class ForecastResult:
    """Shared point/quantile forecast contract for baselines and future model wrappers."""

    point: pd.Series
    quantiles: pd.DataFrame | None
    target: Target
    frequency: str
    metadata: dict[str, object] = field(default_factory=dict)

    def validate(self) -> None:
        """Check prediction grid and optional quantiles without filling missing values."""
        dataset = TimeSeriesDataset(self.point.to_frame("target"), DatasetSpec(
            self.target, self.frequency, (), (), (), "forecast validation"))
        dataset.validate()
        if self.quantiles is not None:
            if not self.quantiles.index.equals(self.point.index):
                raise ValueError("Previsione puntuale e quantili non allineati.")
            validate_quantile_frame(self.quantiles)


def fixed_step(frequency: str) -> pd.Timedelta:
    """Return a positive fixed duration; reject calendar-dependent offsets."""
    try:
        offset = pd.tseries.frequencies.to_offset(frequency)
        step = pd.Timedelta(offset.nanos, unit="ns")
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("frequency deve essere una durata fissa, es. 15min o 1h.") from exc
    if step <= pd.Timedelta(0):
        raise ValueError("frequency deve essere positiva.")
    return step


@dataclass(frozen=True)
class DatasetSpec:
    """Declare target identity, cadence, column roles, units and provenance.

    Past and future roles are explicit, disjoint column names. Future availability
    must additionally be demonstrated by source issue/publication timestamps.
    """

    target: Target
    frequency: str
    past_covariates: tuple[str, ...]
    known_future_covariates: tuple[str, ...]
    covariate_units: tuple[tuple[str, str], ...]
    provenance: str
    target_unit: str = "MW"


@dataclass
class TimeSeriesDataset:
    """Pair a numeric frame with explicit metadata; NaN is allowed everywhere."""

    frame: pd.DataFrame
    spec: DatasetSpec

    def validate(self) -> None:
        """Reject ambiguous structure, irregular grids and infinities unchanged."""
        spec, frame = self.spec, self.frame
        if spec.target not in TARGETS or spec.target_unit != "MW":
            raise ValueError("Target non supportato o unità del target diversa da MW.")
        if not isinstance(spec.provenance, str) or not spec.provenance.strip():
            raise ValueError("La provenienza è obbligatoria.")
        step = fixed_step(spec.frequency)
        roles = (*spec.past_covariates, *spec.known_future_covariates)
        if any(not isinstance(c, str) or not c for c in roles):
            raise ValueError("I nomi delle covariate devono essere stringhe non vuote.")
        if len(set(roles)) != len(roles) or "target" in roles:
            raise ValueError("I ruoli delle colonne devono essere disgiunti e univoci.")
        units = dict(spec.covariate_units)
        if (len(units) != len(spec.covariate_units) or set(units) != set(roles)
                or any(not isinstance(u, str) or not u.strip() for u in units.values())):
            raise ValueError("Dichiarare una unità per ogni covariata e solo per quelle.")
        if not frame.columns.is_unique or set(frame.columns) != {"target", *roles}:
            raise ValueError("Le colonne devono coincidere con target e covariate dichiarate.")
        index = frame.index
        if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC"
                or index.name != "timestamp_utc" or len(index) == 0 or index.hasnans):
            raise ValueError("Serve un indice non vuoto timestamp_utc, DatetimeIndex UTC senza NaT.")
        if not index.is_unique or not index.is_monotonic_increasing:
            raise ValueError("Timestamp duplicati o non ordinati.")
        expected = pd.date_range(index[0], periods=len(index), freq=step)
        if not index.equals(expected):
            raise ValueError("Griglia irregolare: rappresentare gli intervalli mancanti con NaN.")
        for column in frame.columns:
            values = frame[column]
            if (not is_numeric_dtype(values.dtype) or is_bool_dtype(values.dtype)
                    or np.iscomplexobj(values.to_numpy())):
                raise ValueError(f"Colonna {column}: servono numeri reali o NaN.")
            array = values.to_numpy(dtype=float, na_value=np.nan)
            if np.isinf(array).any():
                raise ValueError(f"Colonna {column}: valori infiniti non ammessi.")
