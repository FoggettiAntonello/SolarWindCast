"""Configurable synthetic signals for plumbing tests, never real energy estimates."""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite

import numpy as np
import pandas as pd

from solarwindcast.dataset import (
    TARGETS,
    DatasetSpec,
    Target,
    TimeSeriesDataset,
    fixed_step,
)


@dataclass(frozen=True)
class SyntheticConfig:
    """All signal parameters are explicit; no experiment settings are defaults."""

    target: Target
    start_utc: str
    frequency: str
    number_of_steps: int
    baseline_mw: float
    daily_cycle_amplitude: float
    seasonal_period_steps: int
    seasonal_amplitude: float
    noise_scale: float
    missing_fraction: float
    random_seed: int

    def validate(self) -> None:
        """Reject unresolved settings and invalid ranges before allocation."""
        if self.target not in TARGETS:
            raise ValueError("target deve essere solar, wind, load o residual_load.")
        fixed_step(self.frequency)
        start = pd.Timestamp(self.start_utc)
        if pd.isna(start) or start.tzinfo is None or str(start.tzinfo) != "UTC":
            raise ValueError("start_utc deve dichiarare esplicitamente UTC (es. suffisso Z).")
        for name in ("number_of_steps", "seasonal_period_steps", "random_seed"):
            value = getattr(self, name)
            minimum = 0 if name == "random_seed" else 1
            if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
                raise ValueError(f"{name}: richiesto intero >= {minimum}.")
        for name in ("baseline_mw", "daily_cycle_amplitude", "seasonal_amplitude",
                     "noise_scale", "missing_fraction"):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not isfinite(value)):
                raise ValueError(f"{name}: richiesto numero finito.")
        if min(self.daily_cycle_amplitude, self.seasonal_amplitude, self.noise_scale) < 0:
            raise ValueError("Ampiezze e deviazione del rumore devono essere >= 0.")
        if not 0 <= self.missing_fraction <= 1:
            raise ValueError("missing_fraction deve essere tra 0 e 1.")

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "SyntheticConfig":
        """Read only synthetic fields and selected target; reject placeholders."""
        synthetic, target = project.get("synthetic"), project.get("target")
        if not isinstance(synthetic, Mapping) or not isinstance(target, Mapping):
            raise TypeError("Servono le sezioni synthetic e target della configurazione.")
        fields = {name: synthetic.get(name) for name in cls.__dataclass_fields__ if name != "target"}
        fields["target"] = target.get("selected")
        unresolved = [key for key, value in fields.items()
                      if value is None or (isinstance(value, str) and value == "DA DECIDERE")]
        if unresolved:
            raise ValueError("Parametri sintetici DA DECIDERE o assenti: " + ", ".join(unresolved))
        config = cls(**fields)
        config.validate()
        return config


def generate(config: SyntheticConfig) -> TimeSeriesDataset:
    """Generate daily + seasonal + Gaussian components with random target gaps.

    The generic signal is intentionally identical in form for all target labels.
    No clipping or filling is performed, so negative values can occur. Covariates
    are empty at Step 2: future target/noise values are never exposed as features.
    """
    config.validate()
    index = pd.date_range(config.start_utc, periods=config.number_of_steps,
                          freq=config.frequency, name="timestamp_utc")
    elapsed_days = np.asarray((index - index[0]) / pd.Timedelta(days=1), dtype=float)
    day_phase = (index[0] - index[0].normalize()) / pd.Timedelta(days=1)
    daily = config.daily_cycle_amplitude * np.sin(2 * np.pi * (elapsed_days + day_phase))
    seasonal = config.seasonal_amplitude * np.sin(
        2 * np.pi * np.arange(config.number_of_steps) / config.seasonal_period_steps
    )
    noise_rng, gap_rng = (np.random.default_rng(seed)
                          for seed in np.random.SeedSequence(config.random_seed).spawn(2))
    values = config.baseline_mw + daily + seasonal + noise_rng.normal(
        0, config.noise_scale, config.number_of_steps
    )
    gap_count = int(np.floor(config.number_of_steps * config.missing_fraction))
    values[gap_rng.choice(config.number_of_steps, size=gap_count, replace=False)] = np.nan
    dataset = TimeSeriesDataset(
        pd.DataFrame({"target": values}, index=index),
        DatasetSpec(target=config.target, frequency=config.frequency,
                    past_covariates=(), known_future_covariates=(), covariate_units=(),
                    provenance="synthetic: daily + seasonal + Gaussian; no real observations"),
    )
    dataset.validate()
    return dataset
