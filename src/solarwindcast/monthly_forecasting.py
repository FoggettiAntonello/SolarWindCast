"""Monthly baselines and a pinned Timestral calendar adapter, with no fake hourly indices."""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from solarwindcast.dataset import validate_quantile_frame
from solarwindcast.monthly_protocol import monthly_quantiles_to_energy
from solarwindcast.timestral_model import TimestralSettings, TimestralWrapper


@dataclass
class MonthlyPrediction:
    """One calendar-month forecast in MWh, preserving quantiles and input provenance."""

    model: str
    month: str
    point_mwh: float | None
    quantiles_mwh: pd.Series | None
    metadata: dict[str, object] = field(default_factory=dict)


def context_periods(target: pd.Period, protocol: dict[str, object]) -> pd.PeriodIndex:
    """Return exactly the approved past months; the still-open month never enters."""
    cutoff = target - protocol["unavailable_recent_months"] - 1
    return pd.period_range(cutoff - protocol["context_months"] + 1, cutoff, freq="M")


def baseline_predictions(months: pd.DataFrame, target: pd.Period,
                         protocol: dict[str, object]) -> list[MonthlyPrediction]:
    """Forecast monthly mean power from past complete observations, then scale to target MWh."""
    periods = context_periods(target, protocol)
    cutoff = periods[-1]
    available = months.loc[months.index <= cutoff]
    valid = months.reindex(periods).dropna(subset=["mean_power_mw"])
    hours = float(months.loc[target, "duration_hours"])
    predictions = []
    for method in protocol["baseline_methods"]:
        selected = []
        point = None
        if method == "last_complete_month" and not valid.empty:
            selected = [valid.index[-1]]
            point = float(valid.mean_power_mw.iloc[-1])
        elif method == "same_month_previous_year":
            previous = target - protocol["baseline_seasonal_lag_months"]
            if previous <= cutoff and previous in available.index and pd.notna(available.loc[previous, "mean_power_mw"]):
                selected = [previous]
                point = float(available.loc[previous, "mean_power_mw"])
        elif method == "recent_complete_months":
            recent = valid.tail(protocol["baseline_recent_months"])
            if len(recent) == protocol["baseline_recent_months"]:
                selected = list(recent.index)
                point = float(recent.energy_mwh.sum() / recent.duration_hours.sum())
        elif method not in ("last_complete_month", "same_month_previous_year", "recent_complete_months"):
            raise ValueError("Baseline mensile non supportata.")
        predictions.append(MonthlyPrediction(method, str(target), None if point is None else point * hours,
            None, {"available_through_month": str(cutoff), "selected_months": [str(month) for month in selected],
                   "reason": "ok" if point is not None else "insufficient_complete_past_observations"}))
    errors, error_months = [], []
    for month in pd.period_range(cutoff - protocol["residual_lookback_months"] + 1, cutoff, freq="M"):
        previous = month - protocol["baseline_seasonal_lag_months"]
        if (month in available.index and previous in available.index
                and pd.notna(available.loc[month, "mean_power_mw"])
                and pd.notna(available.loc[previous, "mean_power_mw"])):
            errors.append(float(available.loc[month, "mean_power_mw"] - available.loc[previous, "mean_power_mw"]))
            error_months.append(str(month))
    seasonal = next(prediction for prediction in predictions if prediction.model == "same_month_previous_year")
    quantiles, point_mwh = None, None
    if seasonal.point_mwh is not None and len(errors) >= protocol["minimum_calibration_errors"]:
        levels = protocol["comparison_quantile_levels"]
        power = seasonal.point_mwh / hours + np.quantile(errors, levels, method=protocol["residual_quantile_method"])
        quantiles = monthly_quantiles_to_energy(pd.Series(power, index=levels), hours)
        point_mwh = float(quantiles.loc[.5])
    predictions.append(MonthlyPrediction(protocol["probabilistic_baseline"], str(target), point_mwh, quantiles,
        {"available_through_month": str(cutoff), "calibration_months": error_months,
         "calibration_pairs": len(errors), "reason": "ok" if quantiles is not None else "insufficient_calibration_pairs"}))
    return predictions


class MonthlyTimestral:
    """Use the shared verified loader but preserve monthly calendars and MWh output semantics."""

    def __init__(self, protocol: dict[str, object], model: dict[str, str],
                 backend: object | None = None) -> None:
        """An injected backend is only evidence for synthetic tests, never actual model results."""
        self.protocol = protocol
        self.size = model["size"]
        # The inherited 0h field is required by the hourly settings validator only.
        # We call the verified loader, never its hourly predict; context_periods controls availability.
        settings = TimestralSettings(self.size, "mistralai/Timestral-" + self.size, model["revision"],
            protocol["code_revision"], protocol["package_version"], protocol["device"], protocol["context_months"],
            protocol["prediction_length_months"], "0h", "target_only", protocol["missing_input_policy"],
            protocol["symmetric_averaging"], protocol["clip_nonnegative"], protocol["quantile_real_cap_k"],
            protocol["per_shot_horizon_patches"], protocol["extreme_value_threshold"],
            local_files_only=protocol["local_files_only"], enabled=True)
        self.loader = TimestralWrapper(settings, backend)
        self.backend = None
        self.provenance = {}

    def load(self) -> None:
        """Load and hash cached weights once, using the same version checks as the hourly adapter."""
        if self.backend is None:
            self.backend, self.provenance = self.loader.verified_backend()

    def predict(self, months: pd.DataFrame, target: pd.Period, variant: str) -> MonthlyPrediction:
        """Decode the gap and target months using only the past context and deterministic calendar."""
        cfg = self.protocol
        if variant not in cfg["model_variants"] or variant not in ("target_only", "known_calendar"):
            raise ValueError("Variante mensile non supportata.")
        periods = context_periods(target, cfg)
        if not periods.isin(months.index).all():
            raise ValueError("Contesto calendario fuori dallo storico.")
        values = months.mean_power_mw.reindex(periods).to_numpy(dtype=float)
        if np.isfinite(values).sum() < cfg["minimum_valid_context_months"] or np.isinf(values).any():
            raise ValueError("Contesto valido insufficiente o infinito.")
        if cfg["missing_input_policy"] == "reject" and np.isnan(values).any():
            raise ValueError("Input mancante con politica reject.")
        future = pd.period_range(periods[-1] + 1, target, freq="M")
        if len(future) != cfg["prediction_length_months"]:
            raise ValueError("Divario mensile non coerente con il protocollo.")
        known = None
        if variant == "known_calendar":
            labels = periods.append(future)
            phase = np.asarray([month.month for month in labels], dtype=float) * (2 * np.pi / 12)
            columns = {"month_sin": np.sin(phase), "month_cos": np.cos(phase)}
            known = np.stack([columns[name] for name in cfg["future_calendar_features"]])[None].astype(np.float32)
        self.load()
        backend = self.backend
        if backend.max_context != len(periods) or len(periods) > backend.config.context_length:
            raise ValueError("Il backend troncherebbe il contesto mensile.")
        if str(backend.device) != cfg["device"]:
            raise ValueError("Dispositivo del backend diverso dal protocollo.")
        if known is not None and not backend.supports_known_covariates:
            raise ValueError("Backend senza covariate future note.")
        raw = backend.forecast(values[None, None].astype(np.float32), prediction_length=len(future),
            known_covariates=known, symmetric_averaging=cfg["symmetric_averaging"], clip_nonnegative=cfg["clip_nonnegative"])
        levels = tuple(float(level) for level in raw.quantile_levels)
        output = raw.quantiles
        array = np.asarray(output.detach().cpu().numpy() if hasattr(output, "detach") else output)
        if (len(levels) != 21 or .5 not in levels or levels != tuple(backend.quantile_levels)
                or array.shape != (1, 1, len(future), len(levels)) or not np.isfinite(array).all()):
            raise ValueError("Output mensile Timestral inatteso.")
        validate_quantile_frame(pd.DataFrame(array[0, 0], columns=levels))
        hours = float(months.loc[target, "duration_hours"])
        quantiles = monthly_quantiles_to_energy(pd.Series(array[0, 0, -1].astype(float), index=levels), hours)
        return MonthlyPrediction(f"timestral_{self.size}_{variant}", str(target), float(quantiles.loc[.5]), quantiles,
            {"available_through_month": str(periods[-1]), "context_months": [str(month) for month in periods],
             "missing_context_months": int(np.isnan(values).sum()), "decoded_months": [str(month) for month in future],
             "scored_step": len(future) - 1, "target_duration_hours": hours, "variant": variant,
             "calendar_features": cfg["future_calendar_features"] if known is not None else [],
             "native_missing_behavior": "mask, internal forward fill, leading zeros and patch padding"})
