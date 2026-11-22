"""Rolling-origin evaluation with shared cases, hidden future truth and immutable outputs."""

import json
import math
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from solarwindcast.baselines import BaselineConfig, forecast_baseline
from solarwindcast.dataset import (
    TARGETS,
    ForecastResult,
    TimeSeriesDataset,
    fixed_step,
    quantile_levels,
)
from solarwindcast.entsoe_csv import utc_timestamp
from solarwindcast.evaluation import (
    EvaluationConfig,
    MetricReport,
    central_interval,
    common_valid_mask,
    interval_metrics,
    pinball_metrics,
    point_metrics,
)
from solarwindcast.features import FeatureResult
from solarwindcast.timestral_model import TimestralSettings, TimestralWrapper


class Predictor(Protocol):
    """Common baseline/Timestral interface, keeping settings available for consistency checks."""

    settings: BaselineConfig | TimestralSettings

    def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
        """Predict at one origin without using held-out target values."""
        ...


@dataclass
class BaselinePredictor:
    """Adapt Step 6 baselines to the same interface as the Timestral wrapper."""

    settings: BaselineConfig

    def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str) -> ForecastResult:
        """Use the target only; any prepared covariates are ignored explicitly."""
        dataset = data.dataset if isinstance(data, FeatureResult) else data
        return forecast_baseline(dataset, origin_utc, self.settings)


@dataclass(frozen=True)
class BacktestConfig:
    """Explicit schedule and comparison policies, with no operational defaults."""

    target: str
    frequency: str
    first_origin_utc: str
    context_steps: int
    horizon_steps: int
    stride_steps: int
    number_of_windows: int
    publication_delay: str
    context_window_policy: str
    overlap_scoring_policy: str
    aggregation: str
    failure_policy: str
    evaluation: EvaluationConfig

    def validate(self) -> None:
        """Reject unresolved policies and inconsistent quantile/interval requests."""
        if self.target not in TARGETS:
            raise ValueError("Target del backtest non valido.")
        fixed_step(self.frequency)
        utc_timestamp(self.first_origin_utc)
        for name in ("context_steps", "horizon_steps", "stride_steps", "number_of_windows"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} deve essere un intero positivo.")
        if not isinstance(self.publication_delay, str):
            raise TypeError("publication_delay deve essere esplicito.")
        delay = pd.Timedelta(self.publication_delay)
        if pd.isna(delay) or delay < pd.Timedelta(0):
            raise ValueError("Ritardo del target non valido.")
        if self.context_window_policy != "fixed":
            raise ValueError("Questo motore usa contesto fixed; nessuna espansione implicita.")
        if self.overlap_scoring_policy not in ("all_origins", "reject"):
            raise ValueError("Scegliere overlap_scoring_policy: all_origins o reject.")
        if (self.overlap_scoring_policy == "reject" and self.number_of_windows > 1
                and self.stride_steps < self.horizon_steps):
            raise ValueError("Le finestre si sovrappongono ma la politica è reject.")
        if self.aggregation != "pooled_cases" or self.failure_policy not in ("raise", "record"):
            raise ValueError("Specificare aggregation=pooled_cases e failure_policy=raise/record.")
        if self.evaluation.missing_policy not in ("raise", "omit"):
            raise ValueError("Specificare missing_policy=raise/omit.")
        quantile_levels(self.evaluation.levels)
        if len(set(self.evaluation.interval_levels)) != len(self.evaluation.interval_levels):
            raise ValueError("Livelli nominali duplicati.")
        empty = pd.DataFrame(columns=self.evaluation.levels, dtype=float)
        for level in self.evaluation.interval_levels:
            central_interval(empty, level)

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "BacktestConfig":
        """Read schedule, frequency, horizon and policies from the single YAML."""
        try:
            config, forecast, data = project["backtest"], project["forecast"], project["data"]
            if config["strategy"] != "rolling_origin":
                raise ValueError("La strategia deve essere rolling_origin.")
            result = cls(project["target"]["selected"], data["frequency"], config["first_origin_utc"],
                         forecast["context_steps"], forecast["horizon_steps"], config["stride_steps"],
                         config["number_of_windows"], data["publication_delay"], config["context_window_policy"],
                         config["overlap_scoring_policy"], project["evaluation"]["aggregation"],
                         config["failure_policy"], EvaluationConfig.from_project_config(project))
        except (KeyError, TypeError) as exc:
            raise ValueError("Backtest incompleto o DA DECIDERE.") from exc
        result.validate()
        return result


def build_models(project: Mapping[str, object]) -> dict[str, Predictor]:
    """Construct all selected baseline and Timestral variants without loading weights."""
    methods = project["models"]["baselines"]["methods"]
    if not isinstance(methods, list) or len(set(methods)) != len(methods):
        raise ValueError("Completare methods DA DECIDERE con una lista senza duplicati.")
    models: dict[str, Predictor] = {
        f"baseline_{method}": BaselinePredictor(BaselineConfig.from_project_config(project, method))
        for method in methods
    }
    timestral = project["models"]["timestral"]
    if timestral["enabled"] is True:
        variants = timestral["covariate_variants"]
        if not isinstance(variants, list) or len(set(variants)) != len(variants):
            raise ValueError("Specificare covariate_variants senza duplicati.")
        for variant in variants:
            models[f"timestral_{variant}"] = TimestralWrapper(TimestralSettings.from_project_config(project, variant))
    if not models:
        raise ValueError("Selezionare almeno un modello.")
    return models


def _json_ready(value: object) -> object:
    """Encode NaN as JSON null; reject unsupported objects instead of stringifying them."""
    if isinstance(value, Mapping):
        return {str(k): _json_ready(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(v) for v in value]
    if isinstance(value, np.generic):
        return _json_ready(value.item())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, float):
        if math.isnan(value):
            return None
        if not math.isfinite(value):
            raise ValueError("Non serializzare infiniti come risultati validi.")
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("Tipo non supportato nella provenienza del backtest.")


def _json_bytes(value: object) -> bytes:
    """Return deterministic strict JSON bytes for hashes and persisted results."""
    return json.dumps(_json_ready(value), ensure_ascii=False, allow_nan=False,
                       sort_keys=True, indent=2).encode("utf-8")


@dataclass
class BacktestResult:
    """Complete forecasts, scores, audit reports and input snapshot for one run."""

    predictions: pd.DataFrame
    metrics: pd.DataFrame
    summary: pd.DataFrame
    windows: list[dict[str, object]]
    metadata: dict[str, object]
    input_snapshot: dict[str, object]

    def save(self, directory: Path) -> Path:
        """Write a new directory only; final manifest marks a fully written run."""
        directory = Path(directory)
        # Serialize before creating the directory so malformed metadata leaves no partial run.
        payloads = {"predictions.json": _json_bytes(self.predictions.to_dict("records")),
                    "metrics.json": _json_bytes(self.metrics.to_dict("records")),
                    "summary.json": _json_bytes(self.summary.to_dict("records")),
                    "windows.json": _json_bytes(self.windows), "run.json": _json_bytes(self.metadata),
                    "input.json": _json_bytes(self.input_snapshot)}
        if sha256(payloads["input.json"]).hexdigest() != self.metadata["input_sha256"]:
            raise ValueError("Lo snapshot dei dati è stato modificato dopo il backtest.")
        directory.mkdir(parents=True, exist_ok=False)
        hashes = {}
        for filename, content in payloads.items():
            with (directory / filename).open("xb") as output:
                output.write(content)
            hashes[filename] = sha256(content).hexdigest()
        manifest = {"status": "complete", "files_sha256": hashes,
                    "nan_representation": "JSON null; never imputed"}
        with (directory / "manifest.json").open("xb") as output:
            output.write(_json_bytes(manifest))
        return directory


def _summary(metrics: pd.DataFrame) -> pd.DataFrame:
    """Pool losses by evaluated case count; RMSE pools squared errors before the root."""
    records = []
    for (model, family, metric), group in metrics.groupby(["model", "family", "metric"], sort=False):
        valid = group["n_used"] > 0
        count = int(group["n_used"].sum())
        value = float("nan")
        if count:
            scores = group.loc[valid, "value"].to_numpy(dtype=float)
            weights = group.loc[valid, "n_used"].to_numpy(dtype=float)
            value = float(np.sqrt(np.average(scores ** 2, weights=weights)) if metric == "rmse_mw"
                          else np.average(scores, weights=weights))
        records.append({"model": model, "family": family, "metric": metric, "value": value,
                        "n_total": int(group["n_total"].sum()), "n_used": count})
    return pd.DataFrame(records)


def run_backtest(dataset: TimeSeriesDataset, config: BacktestConfig,
                 models: Mapping[str, Predictor],
                 feature_builder: Callable[[TimeSeriesDataset, str], FeatureResult] | None = None) -> BacktestResult:
    """Run all models on identical UTC origins and family-specific common scoring cases.

    Every model receives a copy with unavailable/future target values masked out.
    Truth is retained only by the evaluator. Features are rebuilt at every origin.
    """
    config.validate()
    dataset.validate()
    if dataset.spec.target != config.target or fixed_step(dataset.spec.frequency) != fixed_step(config.frequency):
        raise ValueError("Target o frequenza del dataset diversi dalla configurazione.")
    if dataset.spec.past_covariates or dataset.spec.known_future_covariates:
        raise ValueError("Passare il solo target e un feature_builder da richiamare per ogni origine.")
    if not models:
        raise ValueError("Nessun modello selezionato.")
    probabilistic: dict[str, bool] = {}
    for name, model in models.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("I nomi dei modelli devono essere stringhe non vuote.")
        settings = model.settings
        settings.validate()
        if (settings.context_steps != config.context_steps or settings.horizon_steps != config.horizon_steps
                or pd.Timedelta(settings.publication_delay) != pd.Timedelta(config.publication_delay)):
            raise ValueError("Contesto, orizzonte e ritardo devono coincidere per tutti i modelli.")
        probabilistic[name] = isinstance(settings, TimestralSettings) or settings.method == "historical_quantiles"
        if (isinstance(settings, BaselineConfig) and probabilistic[name]
                and not set(config.evaluation.levels).issubset(settings.levels)):
            raise ValueError("La baseline probabilistica non include i quantili richiesti.")
        if isinstance(settings, TimestralSettings) and settings.variant != "target_only" and feature_builder is None:
            raise ValueError("Le varianti con covariate richiedono feature_builder.")
    step = fixed_step(config.frequency)
    first = utc_timestamp(config.first_origin_utc)
    if first < dataset.frame.index[0] or (first - dataset.frame.index[0]) % step != pd.Timedelta(0):
        raise ValueError("Prima origine fuori griglia.")
    origins = [first + i * config.stride_steps * step for i in range(config.number_of_windows)]
    if origins[-1] + config.horizon_steps * step > dataset.frame.index[-1] + step:
        raise ValueError("Dataset insufficiente per coprire l'ultima finestra; nessuna finestra troncata.")
    # Check every context before any expensive model invocation.
    starts = []
    for origin in origins:
        eligible = dataset.frame.index[(dataset.frame.index < origin) & (
            dataset.frame.index + step + pd.Timedelta(config.publication_delay) <= origin)]
        if len(eligible) < config.context_steps:
            raise ValueError("Contesto disponibile insufficiente per una finestra.")
        starts.append(eligible[-config.context_steps])
    predictions, metrics, audits = [], [], []

    def add_scores(window: int, model: str, family: str, report: MetricReport) -> None:
        """Keep every score's denominator and preserve its detailed exclusions separately."""
        for metric, value in report.scores.items():
            metrics.append({"window": window, "model": model, "family": family, "metric": metric,
                            "value": value, "n_total": report.total, "n_used": report.used})

    for window, (origin, start) in enumerate(zip(origins, starts, strict=True)):
        future_index = pd.date_range(origin, periods=config.horizon_steps, freq=step, name="timestamp_utc")
        window_frame = dataset.frame.loc[(dataset.frame.index >= start) & (
            dataset.frame.index < origin + config.horizon_steps * step)].copy(deep=True)
        unavailable = window_frame.index + step + pd.Timedelta(config.publication_delay) > origin
        window_frame.loc[unavailable, "target"] = np.nan
        prepared: TimeSeriesDataset | FeatureResult = TimeSeriesDataset(window_frame, dataset.spec)
        if feature_builder is not None:
            prepared = feature_builder(deepcopy(prepared), origin.isoformat())
            if (not isinstance(prepared, FeatureResult) or utc_timestamp(prepared.origin_utc) != origin
                    or prepared.dataset.spec.target != dataset.spec.target
                    or prepared.dataset.spec.frequency != dataset.spec.frequency):
                raise ValueError("Feature preparate con origine, target o frequenza errati.")
            if not prepared.dataset.frame["target"].equals(window_frame["target"]):
                raise ValueError("Il feature_builder ha modificato il target o la griglia della finestra.")
        forecasts, errors = {}, {}
        for name, model in models.items():
            try:
                result = model.predict(deepcopy(prepared), origin.isoformat())
                result.validate()
                if (result.target != dataset.spec.target or fixed_step(result.frequency) != step
                        or not result.point.index.equals(future_index)):
                    raise ValueError("La previsione non coincide con target, frequenza e finestra richiesti.")
                if probabilistic[name]:
                    if result.quantiles is None or not set(config.evaluation.levels).issubset(result.quantiles.columns):
                        raise ValueError("Modello probabilistico senza i quantili richiesti per il confronto.")
                elif result.quantiles is not None:
                    raise ValueError("Baseline puntuale con quantili non dichiarati.")
            except (ValueError, RuntimeError, OSError) as exc:
                if config.failure_policy == "raise":
                    raise
                errors[name] = {"status": "failed", "exception_type": type(exc).__name__,
                                "message": "details omitted; forecast unavailable"}
                result = ForecastResult(pd.Series(np.nan, index=future_index, name="prediction"),
                    pd.DataFrame(np.nan, index=future_index, columns=config.evaluation.levels)
                    if probabilistic[name] else None, dataset.spec.target, dataset.spec.frequency,
                    {"status": "failed"})
            forecasts[name] = result
        actual = dataset.frame["target"].reindex(future_index)
        point_mask = common_valid_mask(actual, {name: f.point for name, f in forecasts.items()})
        selected_quantiles = {name: f.quantiles.loc[:, list(config.evaluation.levels)]
                              for name, f in forecasts.items() if probabilistic[name]}
        prob_mask = common_valid_mask(actual, selected_quantiles) if selected_quantiles else None
        audit = {"window": window, "origin_utc": origin.isoformat(), "context_start_utc": start.isoformat(),
                 "errors": errors, "models": {}, "actual_nan_count": int(actual.isna().sum()),
                 "point_common_timestamps": [t.isoformat() for t in future_index[point_mask]],
                 "probability_common_timestamps": [t.isoformat() for t in future_index[prob_mask]]
                 if prob_mask is not None else []}
        for name, forecast in forecasts.items():
            if config.evaluation.missing_policy == "raise" and (
                actual.isna().any() or forecast.point.isna().any()
                or (name in selected_quantiles and selected_quantiles[name].isna().any().any())):
                raise ValueError("Casi mancanti nel backtest con missing_policy=raise.")
            point_report = point_metrics(actual, forecast.point, config.evaluation.missing_policy, point_mask)
            add_scores(window, name, "point", point_report)
            details = {"forecast_metadata": forecast.metadata, "point": asdict(point_report),
                       "missing_point_predictions": int(forecast.point.isna().sum()),
                       "probabilistic": probabilistic[name]}
            if name in selected_quantiles:
                quantiles = selected_quantiles[name]
                details["missing_quantile_predictions"] = int(quantiles.isna().any(axis=1).sum())
                report = pinball_metrics(actual, quantiles, config.evaluation.missing_policy, prob_mask)
                add_scores(window, name, "pinball", report)
                details["pinball"] = asdict(report)
                for level in config.evaluation.interval_levels:
                    lower, upper = central_interval(quantiles, level)
                    report = interval_metrics(actual, lower, upper, level,
                                              config.evaluation.missing_policy, prob_mask)
                    family = f"interval_{level}"
                    add_scores(window, name, family, report)
                    details[family] = asdict(report)
            audit["models"][name] = details
            for lead, timestamp in enumerate(future_index, start=1):
                record = {"window": window, "origin_utc": origin, "timestamp_utc": timestamp,
                          "lead_step": lead, "model": name, "actual": actual.loc[timestamp],
                          "prediction": forecast.point.loc[timestamp], "point_common": bool(point_mask.loc[timestamp]),
                          "probability_common": bool(prob_mask.loc[timestamp])
                          if probabilistic[name] and prob_mask is not None else False,
                          "status": "failed" if name in errors else "ok"}
                if forecast.quantiles is not None:
                    record.update({f"q_{float(q)}": forecast.quantiles.loc[timestamp, q] for q in forecast.quantiles})
                predictions.append(record)
        audits.append(audit)
    scores = pd.DataFrame(metrics)
    snapshot = {"spec": asdict(dataset.spec), "rows": dataset.frame.reset_index().to_dict("records")}
    all_times = [origin + lead * step for origin in origins for lead in range(config.horizon_steps)]
    metadata = {"backtest": asdict(config), "models": {name: asdict(model.settings) for name, model in models.items()},
                "created_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "final_test_validated": False,
                "window_count": len(origins), "repeated_target_timestamps": len(all_times) - len(set(all_times)),
                "comparison_groups": {"point": list(models), "probability": list(selected_quantiles)},
                "input_sha256": sha256(_json_bytes(snapshot)).hexdigest(),
                "versions": {package: version(package) for package in ("numpy", "pandas", "timestral")}}
    return BacktestResult(pd.DataFrame(predictions), scores, _summary(scores), audits, metadata, snapshot)
