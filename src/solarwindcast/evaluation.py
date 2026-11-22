"""Explicitly aligned forecast metrics with auditable missing-value exclusions."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from numbers import Real

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from solarwindcast.dataset import quantile_levels, validate_quantile_frame


@dataclass
class MetricReport:
    """Scores and their denominator; exclusions never alter the original data."""

    scores: dict[str, float]
    total: int
    used: int
    excluded_timestamps: tuple[str, ...]
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationConfig:
    """Explicit missing policy and requested probability/interval levels."""

    missing_policy: str
    levels: tuple[float, ...]
    interval_levels: tuple[float, ...]

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "EvaluationConfig":
        """Read evaluation settings; never supply an 80% default interval."""
        try:
            forecast = project["forecast"]
            if not isinstance(forecast["quantile_levels"], list) or not isinstance(forecast["interval_levels"], list):
                raise TypeError("Specificare liste di probabilità e livelli degli intervalli.")
            result = cls(project["evaluation"]["missing_policy"], tuple(forecast["quantile_levels"]),
                         tuple(forecast["interval_levels"]))
        except (KeyError, TypeError) as exc:
            raise ValueError("Valutazione incompleta o DA DECIDERE.") from exc
        if result.missing_policy not in ("raise", "omit"):
            raise ValueError("missing_policy deve essere raise o omit.")
        quantile_levels(result.levels)
        for level in result.interval_levels:
            _interval_level(level)
        if len(set(result.interval_levels)) != len(result.interval_levels):
            raise ValueError("Livelli degli intervalli duplicati.")
        return result


def _values(data: pd.Series | pd.DataFrame) -> np.ndarray:
    """Validate numeric data and a nonempty ordered UTC scoring index."""
    if not isinstance(data, (pd.Series, pd.DataFrame)):
        raise TypeError("Passare Series o DataFrame con timestamp espliciti.")
    index = data.index
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing or len(index) == 0):
        raise ValueError("Metriche: serve un indice UTC non vuoto, univoco e ordinato.")
    frame = data.to_frame() if isinstance(data, pd.Series) else data
    for name in frame:
        values = frame[name]
        if (not is_numeric_dtype(values.dtype) or is_bool_dtype(values.dtype)
                or np.iscomplexobj(values.to_numpy())):
            raise ValueError("Metriche: richiesti numeri reali o NaN.")
    array = frame.to_numpy(dtype=float, na_value=np.nan)
    if np.isinf(array).any():
        raise ValueError("Metriche: infiniti non ammessi.")
    return array


def _aligned(actual: pd.Series, *forecasts: pd.Series | pd.DataFrame) -> list[np.ndarray]:
    """Require identical timestamps/order rather than silently joining by position."""
    if not isinstance(actual, pd.Series):
        raise TypeError("Il target osservato deve essere una Series univariata.")
    arrays = [_values(actual)]
    for predicted in forecasts:
        if not actual.index.equals(predicted.index):
            raise ValueError("Metriche: timestamp non allineati esattamente.")
        arrays.append(_values(predicted))
    return arrays


def _mask(actual: pd.Series, arrays: list[np.ndarray], missing_policy: str,
          evaluation_mask: pd.Series | None) -> tuple[np.ndarray, MetricReport]:
    """Combine an explicit comparison mask and complete-case validity, with counts."""
    if missing_policy not in ("raise", "omit"):
        raise ValueError("missing_policy deve essere raise o omit.")
    eligible = np.ones(len(actual), dtype=bool)
    if evaluation_mask is not None:
        if (not actual.index.equals(evaluation_mask.index) or not is_bool_dtype(evaluation_mask.dtype)
                or evaluation_mask.isna().any()):
            raise ValueError("Maschera di valutazione: richiesti booleani allineati senza NaN.")
        eligible = evaluation_mask.to_numpy(dtype=bool)
    complete = np.all(~np.isnan(np.column_stack(arrays)), axis=1)
    if missing_policy == "raise" and (eligible & ~complete).any():
        raise ValueError("Valori mancanti nei casi da valutare: nessuna esclusione implicita.")
    valid = eligible & complete
    report = MetricReport({}, len(actual), int(valid.sum()),
                          tuple(t.isoformat() for t in actual.index[~valid]),
                          {"missing_policy": missing_policy, "excluded_by_mask": int((~eligible).sum()),
                           "excluded_missing_selected": int((eligible & ~complete).sum())})
    return valid, report


def common_valid_mask(actual: pd.Series,
                      forecasts: Mapping[str, pd.Series | pd.DataFrame]) -> pd.Series:
    """Identify common observed cases across models; no model gets easier cases."""
    if not forecasts:
        raise ValueError("Specificare almeno una previsione per il confronto.")
    arrays = _aligned(actual, *forecasts.values())
    for forecast in forecasts.values():
        if isinstance(forecast, pd.DataFrame):
            validate_quantile_frame(forecast)
    valid = np.all(~np.isnan(np.column_stack(arrays)), axis=1)
    return pd.Series(valid, index=actual.index, name="common_valid")


def point_metrics(actual: pd.Series, predicted: pd.Series, missing_policy: str,
                  evaluation_mask: pd.Series | None = None) -> MetricReport:
    """Compute MAE, RMSE and signed bias in MW over the same explicit cases."""
    if not isinstance(predicted, pd.Series):
        raise TypeError("La previsione puntuale deve essere una Series.")
    arrays = _aligned(actual, predicted)
    valid, report = _mask(actual, arrays, missing_policy, evaluation_mask)
    if report.used == 0:
        report.scores = {"mae_mw": float("nan"), "rmse_mw": float("nan"), "bias_mw": float("nan")}
    else:
        error = arrays[1][valid, 0] - arrays[0][valid, 0]
        report.scores = {"mae_mw": float(np.abs(error).mean()),
                         "rmse_mw": float(np.sqrt(np.square(error).mean())),
                         "bias_mw": float(error.mean())}
    return report


def pinball_metrics(actual: pd.Series, predicted: pd.DataFrame, missing_policy: str,
                    evaluation_mask: pd.Series | None = None) -> MetricReport:
    """Compute quantile loss per level and its unweighted mean, using common rows."""
    validate_quantile_frame(predicted)
    arrays = _aligned(actual, predicted)
    valid, report = _mask(actual, arrays, missing_policy, evaluation_mask)
    levels = np.asarray(predicted.columns, dtype=float)
    if report.used == 0:
        losses = np.full(len(levels), np.nan)
    else:
        error = arrays[0][valid] - arrays[1][valid]
        losses = np.maximum(levels * error, (levels - 1) * error).mean(axis=0)
    report.scores = {"pinball_loss_mw": float(losses.mean())}
    report.details["pinball_by_quantile"] = dict(zip(levels.tolist(), losses.tolist(), strict=True))
    return report


def _interval_level(level: float) -> None:
    """Validate a nominal coverage independently of the supplied interval bounds."""
    if isinstance(level, bool) or not isinstance(level, Real) or not np.isfinite(level) or not 0 < level < 1:
        raise ValueError("Il livello nominale deve essere una probabilità tra 0 e 1 esclusi.")


def interval_metrics(actual: pd.Series, lower: pd.Series, upper: pd.Series,
                     nominal_level: float, missing_policy: str,
                     evaluation_mask: pd.Series | None = None) -> MetricReport:
    """Report inclusive coverage and mean width; nominal level is never hardcoded."""
    if not isinstance(lower, pd.Series) or not isinstance(upper, pd.Series):
        raise TypeError("I limiti degli intervalli devono essere Series.")
    _interval_level(nominal_level)
    arrays = _aligned(actual, lower, upper)
    if (arrays[1] > arrays[2]).any():
        raise ValueError("Limite inferiore maggiore del superiore: nessuna correzione automatica.")
    valid, report = _mask(actual, arrays, missing_policy, evaluation_mask)
    coverage, width = float("nan"), float("nan")
    if report.used:
        y, lo, hi = (array[valid, 0] for array in arrays)
        coverage = float(((lo <= y) & (y <= hi)).mean())
        width = float((hi - lo).mean())
    report.scores = {"coverage": coverage, "mean_width_mw": width,
                     "coverage_minus_nominal": coverage - nominal_level}
    report.details["nominal_level"] = nominal_level
    return report


def central_interval(predicted: pd.DataFrame, nominal_level: float) -> tuple[pd.Series, pd.Series]:
    """Extract equal-tailed bounds from supplied quantiles, without interpolation."""
    _interval_level(nominal_level)
    validate_quantile_frame(predicted)
    bounds = []
    for probability in ((1 - nominal_level) / 2, (1 + nominal_level) / 2):
        positions = np.flatnonzero(np.isclose(predicted.columns.to_numpy(dtype=float), probability,
                                              rtol=0, atol=1e-12))
        if len(positions) != 1:
            raise ValueError("Quantile necessario assente o ambiguo; nessuna interpolazione.")
        bounds.append(predicted.iloc[:, positions[0]].copy())
    return bounds[0], bounds[1]




