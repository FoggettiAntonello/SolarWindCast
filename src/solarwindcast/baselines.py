"""Simple UTC baselines using only the explicitly available target context."""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from solarwindcast.dataset import (
    ForecastResult,
    TimeSeriesDataset,
    fixed_step,
    quantile_levels,
)
from solarwindcast.entsoe_csv import utc_timestamp

METHODS = ("persistence", "seasonal_naive", "historical_quantiles")


@dataclass(frozen=True)
class BaselineConfig:
    """Explicit context, horizon, target delay and method-specific parameters."""

    method: str
    context_steps: int
    horizon_steps: int
    publication_delay: str
    seasonal_lag_steps: int | None = None
    levels: tuple[float, ...] = ()
    quantile_method: str | None = None
    minimum_valid_samples: int | None = None

    def validate(self) -> None:
        """Reject unresolved settings; irrelevant method parameters may remain unset."""
        if self.method not in METHODS:
            raise ValueError("Baseline sconosciuta.")
        for name in ("context_steps", "horizon_steps"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} deve essere un intero positivo.")
        if not isinstance(self.publication_delay, str) or self.publication_delay == "DA DECIDERE":
            raise ValueError("publication_delay deve essere una durata esplicita, non DA DECIDERE.")
        delay = pd.Timedelta(self.publication_delay)
        if pd.isna(delay) or delay < pd.Timedelta(0):
            raise ValueError("Specificare un ritardo di pubblicazione non negativo.")
        if self.method == "seasonal_naive" and (
            isinstance(self.seasonal_lag_steps, bool) or not isinstance(self.seasonal_lag_steps, int)
            or not 1 <= self.seasonal_lag_steps <= self.context_steps
        ):
            raise ValueError("Il ciclo deve essere positivo e contenuto nel contesto.")
        if self.method == "historical_quantiles":
            quantile_levels(self.levels)
            if self.quantile_method not in ("linear", "inverted_cdf", "nearest"):
                raise ValueError("Scegliere quantile_method: linear, inverted_cdf o nearest.")
            if (isinstance(self.minimum_valid_samples, bool)
                    or not isinstance(self.minimum_valid_samples, int) or self.minimum_valid_samples < 1):
                raise ValueError("Specificare minimum_valid_samples positivo.")

    @classmethod
    def from_project_config(cls, project: Mapping[str, object], method: str) -> "BaselineConfig":
        """Read only the selected method's settings from the single YAML structure."""
        try:
            base, forecast = project["models"]["baselines"], project["forecast"]
            if not isinstance(base["methods"], list) or method not in base["methods"]:
                raise ValueError("Selezionare la baseline nella lista methods, ora DA DECIDERE.")
            result = cls(method, forecast["context_steps"], forecast["horizon_steps"],
                         project["data"]["publication_delay"],
                         base["seasonal_lag_steps"] if method == "seasonal_naive" else None,
                         tuple(forecast["quantile_levels"]) if method == "historical_quantiles" else (),
                         base["quantile_method"] if method == "historical_quantiles" else None,
                         base["minimum_valid_samples"] if method == "historical_quantiles" else None)
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione baseline incompleta o DA DECIDERE.") from exc
        result.validate()
        return result


def forecast_baseline(dataset: TimeSeriesDataset, origin_utc: str, config: BaselineConfig) -> ForecastResult:
    """Predict without future targets, fallback imputation or context-dependent clipping.

    Availability is interval end plus declared delay. Seasonal repetition advances
    the phase across publication gaps rather than shifting the forecast cycle.
    """
    config.validate()
    dataset.validate()
    origin = utc_timestamp(origin_utc)
    step = fixed_step(dataset.spec.frequency)
    if (origin < dataset.frame.index[0]
            or (origin - dataset.frame.index[0]) % step != pd.Timedelta(0)):
        raise ValueError("L'origine deve essere sulla griglia UTC del target.")
    delay = pd.Timedelta(config.publication_delay)
    index = dataset.frame.index
    context = dataset.frame.loc[(index < origin) & (index + step + delay <= origin), "target"].tail(
        config.context_steps)
    if len(context) != config.context_steps:
        raise ValueError("Contesto disponibile insufficiente; nessun riempimento.")
    if not context.index.equals(pd.date_range(context.index[0], periods=len(context), freq=step)):
        raise ValueError("Contesto non regolare.")
    horizon = pd.date_range(origin, periods=config.horizon_steps, freq=step, name="timestamp_utc")
    values = context.to_numpy(dtype=float, na_value=np.nan)
    metadata: dict[str, object] = {
        "method": config.method, "origin_utc": origin.isoformat(),
        "context_start_utc": context.index[0].isoformat(), "context_end_utc": context.index[-1].isoformat(),
        "context_steps": len(context), "context_nan_count": int(np.isnan(values).sum()),
        "publication_delay_assumption": config.publication_delay,
        "target_unit": "MW", "target_revisions": "not reconstructed",
    }
    quantiles = None
    if config.method == "persistence":
        predicted = np.repeat(values[-1], config.horizon_steps)
        metadata["source_timestamps"] = [context.index[-1].isoformat()] * config.horizon_steps
    elif config.method == "seasonal_naive":
        lag = config.seasonal_lag_steps
        gap = int((origin - (context.index[-1] + step)) / step)
        positions = (gap + np.arange(config.horizon_steps)) % lag
        predicted = values[-lag:][positions]
        metadata.update(seasonal_lag_steps=lag, publication_gap_steps=gap,
                        source_timestamps=[t.isoformat() for t in context.index[-lag:][positions]])
    else:
        valid = values[~np.isnan(values)]
        metadata.update(valid_samples=len(valid), quantile_method=config.quantile_method,
                        minimum_valid_samples=config.minimum_valid_samples,
                        quantile_assumption="unconditional context distribution; not calibrated forecast errors")
        if len(valid) < config.minimum_valid_samples:
            predicted = np.full(config.horizon_steps, np.nan)
            quantiles = pd.DataFrame(np.nan, index=horizon, columns=config.levels)
            metadata["status"] = "insufficient_valid_samples"
        else:
            predicted = np.repeat(np.quantile(valid, 0.5, method=config.quantile_method), config.horizon_steps)
            estimated = np.quantile(valid, config.levels, method=config.quantile_method)
            quantiles = pd.DataFrame(np.tile(estimated, (config.horizon_steps, 1)),
                                     index=horizon, columns=config.levels)
            metadata["status"] = "ok"
    result = ForecastResult(pd.Series(predicted, index=horizon, name="prediction"), quantiles,
                            dataset.spec.target, dataset.spec.frequency, metadata)
    result.validate()
    return result
