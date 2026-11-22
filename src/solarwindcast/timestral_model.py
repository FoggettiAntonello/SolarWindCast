"""Pinned Timestral adapter with explicit preprocessing, covariate roles and UTC output."""

import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import file_digest
from importlib.metadata import distribution, version
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from solarwindcast.dataset import (
    ForecastResult,
    TimeSeriesDataset,
    fixed_step,
    quantile_levels,
)
from solarwindcast.entsoe_csv import utc_timestamp
from solarwindcast.features import FeatureResult


class ForecastBackend(Protocol):
    """Minimal injectable forecaster surface for offline unit tests."""

    config: object
    device: object
    max_context: int
    supports_covariates: bool
    supports_known_covariates: bool
    quantile_levels: tuple[float, ...]

    def forecast(self, context: np.ndarray, prediction_length: int, **kwargs: object) -> object:
        """Return a Timestral-like object exposing tensor/array quantiles and levels."""
        ...


@dataclass(frozen=True)
class TimestralSettings:
    """Required model and inference choices; no benchmark setting is adopted silently."""

    size: str
    repository_id: str
    revision: str
    code_revision: str
    package_version: str
    device: str
    context_steps: int
    horizon_steps: int
    publication_delay: str
    variant: str
    missing_input_policy: str
    symmetric_averaging: bool
    clip_nonnegative: bool
    quantile_real_cap_k: float
    per_shot_horizon_patches: int
    extreme_value_threshold: float
    local_files_only: bool = True
    enabled: bool = False

    def validate(self) -> None:
        """Require immutable revisions and supported, explicitly selected options."""
        if (self.size not in ("5M", "28M", "123M", "209M")
                or self.repository_id != f"mistralai/Timestral-{self.size}"):
            raise ValueError("Taglia e repository Timestral ufficiale non coerenti.")
        for revision in (self.revision, self.code_revision):
            if not isinstance(revision, str) or re.fullmatch(r"[a-f0-9]{40}", revision) is None:
                raise ValueError("Fissare revisioni complete di codice e pesi, non main o DA DECIDERE.")
        if self.package_version != "1.0.0":
            raise ValueError("Questo adattatore è verificato per l'API Timestral 1.0.0.")
        if re.fullmatch(r"cpu|cuda(?::\d+)?", self.device) is None:
            raise ValueError("Scegliere esplicitamente cpu oppure cuda[:indice].")
        for name in ("context_steps", "horizon_steps", "per_shot_horizon_patches"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} deve essere un intero positivo.")
        if self.variant not in ("target_only", "past", "past_known"):
            raise ValueError("Variante ammessa: target_only, past o past_known.")
        if self.missing_input_policy not in ("reject", "native_mask"):
            raise ValueError("missing_input_policy deve essere reject o native_mask.")
        for name in ("symmetric_averaging", "clip_nonnegative", "local_files_only", "enabled"):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} deve essere booleano esplicito.")
        for name in ("quantile_real_cap_k", "extreme_value_threshold"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} deve essere finito e non negativo.")
        if self.extreme_value_threshold == 0:
            raise ValueError("extreme_value_threshold deve essere positivo.")
        if not isinstance(self.publication_delay, str):
            raise TypeError("publication_delay deve essere una durata esplicita.")
        delay = pd.Timedelta(self.publication_delay)
        if pd.isna(delay) or delay < pd.Timedelta(0):
            raise ValueError("Ritardo del target non valido.")

    @classmethod
    def from_project_config(cls, project: Mapping[str, object], variant: str) -> "TimestralSettings":
        """Read selected variant and all inference options from the single YAML."""
        try:
            model, forecast = project["models"]["timestral"], project["forecast"]
            if not isinstance(model["covariate_variants"], list) or variant not in model["covariate_variants"]:
                raise ValueError("Selezionare la variante nella lista covariate_variants, ora DA DECIDERE.")
            options = model["inference_options"]
            result = cls(model["size"], model["repository_id"], model["revision"], model["code_revision"],
                         model["package_version"], model["device"], forecast["context_steps"],
                         forecast["horizon_steps"], project["data"]["publication_delay"], variant,
                         options["missing_input_policy"], options["symmetric_averaging"],
                         options["clip_nonnegative"], options["quantile_real_cap_k"],
                         options["per_shot_horizon_patches"], options["extreme_value_threshold"],
                         model["local_files_only"], model["enabled"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione Timestral incompleta o DA DECIDERE.") from exc
        result.validate()
        return result


class TimestralWrapper:
    """Load pinned weights once and produce the shared point/quantile forecast format."""

    def __init__(self, settings: TimestralSettings, backend: ForecastBackend | None = None) -> None:
        """An injected backend is labelled as a test backend, not loaded model evidence."""
        settings.validate()
        self.settings = settings
        self._backend = backend
        self._provenance: dict[str, object] = {"backend_mode": "injected_test_backend"}

    def load(self, download_authorized: bool = False) -> None:
        """Load a full revision from cache; network loading requires separate explicit opt-in."""
        cfg = self.settings
        if not cfg.enabled:
            raise RuntimeError("Timestral è disattivato nella configurazione.")
        if self._backend is not None:
            return
        if not cfg.local_files_only and not download_authorized:
            raise RuntimeError("Download dei pesi non autorizzato: usare local_files_only=True.")
        from huggingface_hub import snapshot_download

        package = distribution("timestral")
        installed = json.loads(package.read_text("direct_url.json") or "{}")
        if (version("timestral") != cfg.package_version
                or installed.get("vcs_info", {}).get("commit_id") != cfg.code_revision):
            raise ValueError("Versione o revisione del codice installato diversa da quella dichiarata.")
        snapshot = Path(snapshot_download(cfg.repository_id, revision=cfg.revision,
                         local_files_only=cfg.local_files_only, token=False,
                         allow_patterns=["config.json", "model.safetensors"]))
        if snapshot.name != cfg.revision:
            raise ValueError("La revisione effettiva del checkpoint non coincide con quella richiesta.")
        config_path, weights_path = snapshot / "config.json", snapshot / "model.safetensors"
        architecture = json.loads(config_path.read_text(encoding="utf-8"))
        if cfg.context_steps > architecture["context_length"]:
            raise ValueError("Contesto oltre il limite addestrato: nessun troncamento silenzioso.")
        if cfg.per_shot_horizon_patches > architecture["block_size"]:
            raise ValueError("Blocco richiesto oltre quello addestrato: nessuna riduzione implicita.")
        from timestral import TimestralForecaster

        self._backend = TimestralForecaster.from_pretrained(snapshot, device=cfg.device,
            max_context=cfg.context_steps, per_shot_horizon_patches=cfg.per_shot_horizon_patches,
            quantile_real_cap_k=cfg.quantile_real_cap_k, local_files_only=True, token=False)
        self._backend.extreme_value_threshold = cfg.extreme_value_threshold
        hashes = {}
        for path in (config_path, weights_path):
            with path.open("rb") as file:
                hashes[path.name] = file_digest(file, "sha256").hexdigest()
        self._provenance = {"backend_mode": "loaded_timestral", "package_version": cfg.package_version,
                            "code_revision": cfg.code_revision, "weights_revision": snapshot.name,
                            "checkpoint_hashes": hashes, "torch_version": version("torch")}

    def verified_backend(self) -> tuple[ForecastBackend, dict[str, object]]:
        """Expose the verified loader to calendar adapters without inventing fixed-time indices."""
        self.load()
        return self._backend, json.loads(json.dumps(self._provenance))

    def predict(self, data: TimeSeriesDataset | FeatureResult, origin_utc: str,
                download_authorized: bool = False) -> ForecastResult:
        """Bridge delayed-target gaps with forecasts, never with future observed values."""
        cfg = self.settings
        if not cfg.enabled:
            raise RuntimeError("Timestral è disattivato nella configurazione.")
        feature_result = data if isinstance(data, FeatureResult) else None
        dataset = feature_result.dataset if feature_result is not None else data
        dataset.validate()
        origin = utc_timestamp(origin_utc)
        if feature_result is not None and utc_timestamp(feature_result.origin_utc) != origin:
            raise ValueError("Le covariate devono essere preparate per la stessa origine della previsione.")
        if cfg.variant != "target_only" and feature_result is None:
            raise ValueError("Le covariate richiedono FeatureResult con disponibilità verificata nello Step 5.")
        step = fixed_step(dataset.spec.frequency)
        if origin < dataset.frame.index[0] or (origin - dataset.frame.index[0]) % step != pd.Timedelta(0):
            raise ValueError("Origine non allineata alla griglia UTC.")
        index = dataset.frame.index
        available = (index < origin) & (index + step + pd.Timedelta(cfg.publication_delay) <= origin)
        context = dataset.frame.loc[available].tail(cfg.context_steps)
        if len(context) != cfg.context_steps:
            raise ValueError("Contesto target disponibile insufficiente.")
        target = context["target"].to_numpy(dtype=float, na_value=np.nan)
        if np.isnan(target).all():
            raise ValueError("Il contesto target è interamente mancante.")
        decode_start = context.index[-1] + step
        gap = int((origin - decode_start) / step)
        total_horizon = cfg.horizon_steps + gap
        decode_index = pd.date_range(decode_start, periods=total_horizon, freq=step, name="timestamp_utc")
        past_names = dataset.spec.past_covariates if cfg.variant != "target_only" else ()
        known_names = dataset.spec.known_future_covariates if cfg.variant == "past_known" else ()
        if cfg.variant == "past" and not past_names:
            raise ValueError("La variante past richiede covariate passate dichiarate.")
        if cfg.variant == "past_known" and not known_names:
            raise ValueError("La variante past_known richiede covariate future note dichiarate.")
        past = context.loc[:, list(past_names)].to_numpy(dtype=float, na_value=np.nan).T[None] if past_names else None
        known_index = context.index.append(decode_index)
        known = dataset.frame.reindex(known_index).loc[:, list(known_names)].to_numpy(
            dtype=float, na_value=np.nan).T[None] if known_names else None
        arrays = {"context": target[None, None], "past_covariates": past, "known_covariates": known}
        missing_counts = {}
        for name, values in arrays.items():
            if values is None:
                continue
            missing_counts[name] = int(np.isnan(values).sum())
            if cfg.missing_input_policy == "reject" and np.isnan(values).any():
                raise ValueError("Input mancante: politica reject, nessun riempimento nel wrapper.")
            with np.errstate(over="ignore"):
                values = values.astype(np.float32)
            if np.isinf(values).any():
                raise ValueError("Input fuori dall'intervallo rappresentabile in float32.")
            arrays[name] = values
        self.load(download_authorized=download_authorized)
        backend = self._backend
        if cfg.context_steps > backend.config.context_length or backend.max_context != cfg.context_steps:
            raise ValueError("Il backend troncherebbe il contesto richiesto.")
        if cfg.per_shot_horizon_patches > backend.config.block_size:
            raise ValueError("Il backend ridurrebbe il blocco richiesto.")
        if (past is not None or known is not None) and not backend.supports_covariates:
            raise ValueError("Checkpoint senza supporto alle covariate.")
        if known is not None and not backend.supports_known_covariates:
            raise ValueError("Checkpoint senza supporto alle covariate future note.")
        actual_device = str(backend.device)
        if not (actual_device.split(":")[0] == "cuda" if cfg.device == "cuda" else actual_device == cfg.device):
            raise ValueError("Dispositivo effettivo diverso da quello richiesto; nessun fallback CPU.")
        raw = backend.forecast(**arrays, prediction_length=total_horizon,
                               symmetric_averaging=cfg.symmetric_averaging, clip_nonnegative=cfg.clip_nonnegative)
        levels = tuple(float(q) for q in raw.quantile_levels)
        quantile_levels(levels)
        if len(levels) != 21 or .5 not in levels or levels != tuple(backend.quantile_levels):
            raise ValueError("Griglia dei 21 quantili Timestral inattesa.")
        output = raw.quantiles
        values = np.asarray(output.detach().cpu().numpy() if hasattr(output, "detach") else output)
        if values.shape != (1, 1, total_horizon, len(levels)) or not np.isfinite(values).all():
            raise ValueError("Forma o valori della previsione Timestral non validi.")
        quantiles = pd.DataFrame(values[0, 0, gap:], index=decode_index[gap:], columns=levels)
        point = quantiles[.5].copy().rename("prediction")
        metadata = {**self._provenance, "settings": asdict(cfg), "device": str(backend.device),
                    "origin_utc": origin.isoformat(), "context_start_utc": context.index[0].isoformat(),
                    "context_end_utc": context.index[-1].isoformat(), "publication_gap_steps": gap,
                    "decoded_steps": total_horizon, "missing_input_counts": missing_counts,
                    "past_columns": list(past_names), "known_columns": list(known_names),
                    "native_missing_behavior": "mask + internal forward fill, leading zeros, patch padding",
                    "target_revisions": "not reconstructed"}
        if feature_result is not None:
            metadata["feature_report"] = feature_result.report
        result = ForecastResult(point, quantiles, dataset.spec.target, dataset.spec.frequency, metadata)
        result.validate()
        return result
