"""Open-Meteo point data, immutable raw cache and explicit forecast availability."""

import json
import math
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from solarwindcast.entsoe_csv import utc_timestamp

ENDPOINTS = {
    "reanalysis": "https://archive-api.open-meteo.com/v1/archive",
    "forecast": "https://api.open-meteo.com/v1/forecast",
    "historical_forecast": "https://historical-forecast-api.open-meteo.com/v1/forecast",
    "single_run": "https://single-runs-api.open-meteo.com/v1/forecast",
}
UNITS = {"temperature_2m": "°C", "cloud_cover": "%", "shortwave_radiation": "W/m²",
         "wind_speed_10m": "m/s", "wind_speed_80m": "m/s", "wind_speed_100m": "m/s",
         "wind_speed_120m": "m/s", "wind_speed_180m": "m/s"}


@dataclass(frozen=True)
class Location:
    """A requested point, independent of the model's returned grid coordinates."""

    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True)
class WeatherRequest:
    """Hourly raw point request; no experiment choices are supplied as defaults."""

    product: str
    location: Location
    start_utc: str
    end_exclusive_utc: str
    model: str
    variables: tuple[str, ...]
    run_utc: str | None = None
    archive_origin: str = "unverified"

    def parameters(self) -> dict[str, object]:
        """Build UTC requests without provider model selection or silent rounding."""
        if self.product not in ENDPOINTS:
            raise ValueError("Prodotto Open-Meteo non supportato.")
        point = self.location
        if (not point.name or not math.isfinite(point.latitude) or not math.isfinite(point.longitude)
                or not -90 <= point.latitude <= 90 or not -180 <= point.longitude <= 180):
            raise ValueError("Coordinate o nome del punto non validi.")
        if not self.model or self.model in ("DA DECIDERE", "best_match") or "," in self.model:
            raise ValueError("Specificare un singolo modello esplicito.")
        if (not self.variables or len(set(self.variables)) != len(self.variables)
                or not set(self.variables).issubset(UNITS)):
            raise ValueError("Selezionare variabili supportate, senza duplicati.")
        start, end = utc_timestamp(self.start_utc), utc_timestamp(self.end_exclusive_utc)
        if end <= start or any(t != t.floor("h") for t in (start, end)):
            raise ValueError("Periodo non vuoto con estremi UTC su ore intere richiesto.")
        if self.archive_origin not in ("unverified", "operational_archive", "hindcast"):
            raise ValueError("Origine archivio non valida.")
        params = {"latitude": point.latitude, "longitude": point.longitude,
                  "hourly": ",".join(self.variables), "models": self.model,
                  "start_date": start.strftime("%Y-%m-%d"),
                  "end_date": (end - pd.Timedelta(hours=1)).strftime("%Y-%m-%d"),
                  "timezone": "UTC", "timeformat": "iso8601",
                  "temperature_unit": "celsius", "wind_speed_unit": "ms"}
        if self.product == "single_run":
            if self.run_utc is None:
                raise ValueError("Single Runs richiede run_utc.")
            run = utc_timestamp(self.run_utc)
            if run != run.floor("h"):
                raise ValueError("run_utc deve essere su un'ora intera.")
            if end <= run:
                raise ValueError("Il periodo richiesto deve raggiungere tempi successivi al run.")
            # Live verification: Single Runs rejects start_date/end_date despite
            # the docs describing the common Forecast API parameter set.
            params.pop("start_date")
            params.pop("end_date")
            params["forecast_hours"] = int((end - run) / pd.Timedelta(hours=1))
            params["run"] = run.strftime("%Y-%m-%dT%H:%M")
        elif self.run_utc is not None:
            raise ValueError("run_utc è ammesso soltanto per Single Runs.")
        return params

    @classmethod
    def from_project_config(cls, project: Mapping[str, object], location_name: str,
                            product: str) -> "WeatherRequest":
        """Read a named configured point and period from the single project YAML."""
        try:
            weather, data = project["sources"]["weather"], project["data"]
            locations = weather["locations"]
            if not isinstance(locations, list):
                raise TypeError("locations: completare la lista di punti DA DECIDERE.")
            matches = [p for p in locations if p["name"] == location_name]
            if len(matches) != 1:
                raise ValueError("Il nome del punto deve comparire una sola volta.")
            variables = weather["variables"]
            if not isinstance(variables, list):
                raise TypeError("variables: completare la lista DA DECIDERE.")
            run = weather["run_utc"] if product == "single_run" else None
            origin = weather["archive_provenance_policy"]
            result = cls(product, Location(**matches[0]), data["start_utc"],
                         data["end_exclusive_utc"], weather["model"], tuple(variables), run,
                         "unverified" if origin == "DA DECIDERE" else origin)
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione meteo incompleta o DA DECIDERE.") from exc
        result.parameters()
        return result


@dataclass
class WeatherResult:
    """Point frame in provider valid-time semantics, never silently resampled."""

    frame: pd.DataFrame
    request: WeatherRequest
    metadata: dict[str, object]

    def future_at(self, origin_utc: str, publication_delay: str | None = None,
                  availability_evidence: str | None = None) -> pd.DataFrame:
        """Expose future values only with an eligible run or already acquired snapshot.

        A declared delay/evidence is an auditable assumption, not provider proof.
        Reanalyses, stitched history and unverified/hindcast archives are blocked.
        """
        origin = utc_timestamp(origin_utc)
        if self.request.product == "single_run":
            if self.request.archive_origin != "operational_archive":
                raise ValueError("Archivio non verificato come operativo: covariate future bloccate.")
            if not availability_evidence or not availability_evidence.strip() or publication_delay is None:
                raise ValueError("Specificare ritardo di pubblicazione e fonte/assunzione documentata.")
            delay = pd.Timedelta(publication_delay)
            if pd.isna(delay) or delay < pd.Timedelta(0):
                raise ValueError("Ritardo di pubblicazione non valido.")
            available = utc_timestamp(self.request.run_utc) + delay
        elif self.request.product == "forecast":
            available = utc_timestamp(self.metadata["retrieved_at_utc"])
        else:
            raise ValueError("Rianalisi e storico continuo non sono covariate future operative.")
        if available > origin:
            raise ValueError("Previsione non disponibile all'origine richiesta.")
        selected = self.frame.loc[self.frame.index >= origin].copy()
        selected.attrs["forecast_availability"] = {
            "origin_utc": origin.isoformat(), "available_at_utc": available.isoformat(),
            "publication_delay_assumption": publication_delay,
            "availability_evidence": availability_evidence,
            "product": self.request.product, "run_utc": self.request.run_utc,
        }
        return selected


def parse_response(payload: dict[str, object], request: WeatherRequest,
                   metadata: dict[str, object]) -> WeatherResult:
    """Preserve nulls as NaN, flag gaps/ranges and retain original variable semantics."""
    request.parameters()
    if payload.get("error"):
        raise ValueError(f"Open-Meteo: {payload.get('reason', 'errore API')}")
    if payload.get("utc_offset_seconds") != 0:
        raise ValueError("Risposta meteo non in UTC.")
    hourly, units = payload.get("hourly"), payload.get("hourly_units")
    if not isinstance(hourly, dict) or not isinstance(units, dict) or "time" not in hourly:
        raise ValueError("Risposta senza dati orari e unità.")
    # ISO dates from the API are UTC because timezone=UTC and offset=0 are checked.
    index = pd.DatetimeIndex(pd.to_datetime(hourly["time"], utc=True), name="timestamp_utc")
    if index.hasnans or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("Timestamp meteo nulli, duplicati o non ordinati.")
    if any(t != t.floor("h") for t in index):
        raise ValueError("Timestamp meteo non allineati alle ore.")
    values: dict[str, np.ndarray] = {}
    for variable in request.variables:
        if units.get(variable) != UNITS[variable]:
            raise ValueError(f"Unità inattesa per {variable}.")
        raw = hourly.get(variable)
        if not isinstance(raw, list) or len(raw) != len(index):
            raise ValueError(f"Lunghezza dati inattesa per {variable}.")
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))) for v in raw):
            raise ValueError(f"Valori non numerici per {variable}.")
        array = np.asarray(raw, dtype=float)
        if np.isinf(array).any():
            raise ValueError(f"Valori infiniti per {variable}.")
        values[variable] = array
    frame = pd.DataFrame(values, index=index)
    start, end = utc_timestamp(request.start_utc), utc_timestamp(request.end_exclusive_utc)
    expected = pd.date_range(start, end, freq="h", inclusive="left", name="timestamp_utc")
    selected = frame.loc[(index >= start) & (index < end)]
    missing_times = expected.difference(selected.index)
    selected = selected.reindex(expected)
    anomalies = {}
    for variable in request.variables:
        series = selected[variable]
        invalid = ((series < 0) if variable.startswith("wind_speed") or variable == "shortwave_radiation"
                   else ((series < 0) | (series > 100)) if variable == "cloud_cover"
                   else pd.Series(False, index=expected))
        anomalies[variable] = [t.isoformat() for t in expected[invalid]]
    info = dict(metadata)
    info.update(product=request.product, model=request.model, run_utc=request.run_utc,
                archive_origin=request.archive_origin, requested_location=request.location.__dict__,
                returned_grid={k: payload.get(k) for k in ("latitude", "longitude", "elevation")},
                units={v: UNITS[v] for v in request.variables},
                time_semantics={v: "mean_over_preceding_hour" if v == "shortwave_radiation"
                                else "instant_at_timestamp" for v in request.variables},
                missing_timestamps=[t.isoformat() for t in missing_times],
                nan_counts={v: int(selected[v].isna().sum()) for v in request.variables},
                anomaly_timestamps=anomalies, excluded_rows=len(frame) - len(frame.index.intersection(expected)))
    return WeatherResult(selected, request, info)


@dataclass(frozen=True)
class WeatherClient:
    """Immutable content-addressed cache; network is explicitly opt-in."""

    cache_directory: Path
    timeout_seconds: int
    retry_attempts: int
    pause_seconds: float
    network_enabled: bool = False
    cache_policy: str = "immutable"

    @classmethod
    def from_project_config(cls, project: Mapping[str, object], project_root: Path) -> "WeatherClient":
        """Load explicit cache/network settings without enabling services by default."""
        try:
            weather = project["sources"]["weather"]
            return cls(project_root / project["paths"]["cache"] / "open_meteo",
                       weather["timeout_seconds"], weather["retry_attempts"], weather["pause_seconds"],
                       weather["enabled"] is True and project["execution"]["real_data_enabled"] is True,
                       weather["cache_policy"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione client meteo incompleta.") from exc

    def fetch(self, request: WeatherRequest,
              get: Callable[..., requests.Response] = requests.get) -> WeatherResult:
        """Fetch one point or reuse its exact response; never overwrite cache entries."""
        params = request.parameters()
        if self.cache_policy not in ("immutable", "cache_only"):
            raise ValueError("cache_policy deve essere immutable o cache_only.")
        identity = {"schema": 1, "endpoint": ENDPOINTS[request.product], "parameters": params}
        canonical = json.dumps(identity, sort_keys=True, ensure_ascii=False)
        key = sha256(canonical.encode("utf-8")).hexdigest()
        path = self.cache_directory / f"{key}.json"
        if path.exists():
            entry = json.loads(path.read_text(encoding="utf-8"))
            if (entry.get("request") != identity or sha256(entry["raw_text"].encode("utf-8")).hexdigest()
                    != entry["response_sha256"]):
                raise ValueError("Cache corrotta o richiesta incompatibile: nessuna riparazione automatica.")
            cached = True
        else:
            if self.network_enabled is not True or self.cache_policy == "cache_only":
                raise RuntimeError("Cache assente e accesso alla rete disattivato.")
            if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, int)
                    or self.timeout_seconds <= 0 or isinstance(self.retry_attempts, bool)
                    or not isinstance(self.retry_attempts, int) or self.retry_attempts <= 0
                    or not isinstance(self.pause_seconds, (int, float))
                    or not math.isfinite(self.pause_seconds) or self.pause_seconds < 0):
                raise ValueError("Specificare timeout, tentativi e pausa validi.")
            for attempt in range(self.retry_attempts):
                try:
                    response = get(identity["endpoint"], params=params, timeout=self.timeout_seconds)
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    retryable = exc.response is None or exc.response.status_code == 429 or exc.response.status_code >= 500
                    if not retryable or attempt + 1 == self.retry_attempts:
                        raise
                    time.sleep(self.pause_seconds)
            raw_text = response.content.decode("utf-8")
            payload = json.loads(raw_text)
            entry = {"request": identity, "raw_text": raw_text,
                     "response_sha256": sha256(raw_text.encode("utf-8")).hexdigest(),
                     "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat()}
            # Validate before caching; malformed responses must not poison the cache.
            parse_response(payload, request, entry)
            self.cache_directory.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as output:
                json.dump(entry, output, ensure_ascii=False, indent=2)
            cached = False
        metadata = {k: v for k, v in entry.items() if k != "raw_text"}
        metadata.update(cache_hit=cached, cache_path=str(path.resolve()))
        return parse_response(json.loads(entry["raw_text"]), request, metadata)


def fetch_points(client: WeatherClient, requests_by_point: tuple[WeatherRequest, ...]) -> dict[str, WeatherResult]:
    """Fetch configured points sequentially; no spatial aggregation or concurrency."""
    names = [r.location.name for r in requests_by_point]
    if len(set(names)) != len(names):
        raise ValueError("I nomi dei punti devono essere univoci.")
    return {request.location.name: client.fetch(request) for request in requests_by_point}
