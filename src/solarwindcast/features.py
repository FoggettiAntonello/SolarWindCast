"""Assemble target, calendar and weather with explicit roles and availability."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import version

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from solarwindcast.calendar_features import CalendarConfig, calendar_features
from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset, fixed_step
from solarwindcast.entsoe_csv import utc_timestamp
from solarwindcast.weather import UNITS, WeatherResult


@dataclass(frozen=True)
class FeatureConfig:
    """Declare exact output columns and roles; placeholders never become inputs."""

    calendar: CalendarConfig
    past_covariates: tuple[str, ...]
    known_future_covariates: tuple[str, ...]
    alignment_policy: str

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "FeatureConfig":
        """Load selected feature names and calendar options from the project YAML."""
        try:
            config = project["features"]
            if any(not isinstance(config[key], list)
                   for key in ("past_covariates", "known_future_covariates")):
                raise TypeError("Specificare liste esplicite di covariate.")
            result = cls(CalendarConfig.from_project_config(project), tuple(config["past_covariates"]),
                         tuple(config["known_future_covariates"]), config["alignment_policy"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Feature incomplete o DA DECIDERE.") from exc
        return result


@dataclass(frozen=True)
class WeatherBinding:
    """Bind selected variables from one source to a role with per-variable alignment."""

    name: str
    result: WeatherResult
    role: str
    variables: tuple[str, ...]
    time_alignment: tuple[tuple[str, str], ...]
    publication_delay: str | None
    availability_evidence: str | None


@dataclass
class FeatureResult:
    """Combined truth/feature table plus explicit, target-safe model input views."""

    dataset: TimeSeriesDataset
    origin_utc: str
    report: dict[str, object]

    def model_inputs(self) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Return context before origin and future known columns without future truth."""
        self.dataset.validate()
        origin = utc_timestamp(self.origin_utc)
        frame = self.dataset.frame
        context = frame.loc[frame.index < origin].copy()
        future = frame.loc[frame.index >= origin, list(self.dataset.spec.known_future_covariates)].copy()
        return context, future


def bindings_from_project_config(project: Mapping[str, object],
                                 sources: Mapping[str, WeatherResult]) -> tuple[WeatherBinding, ...]:
    """Bind named, already acquired sources; this function never downloads data."""
    try:
        declarations = project["features"]["weather_bindings"]
        if not isinstance(declarations, list):
            raise TypeError("weather_bindings deve essere una lista, anche vuota.")
        result = []
        for declaration in declarations:
            if (not isinstance(declaration["variables"], list)
                    or not isinstance(declaration["time_alignment"], dict)):
                raise TypeError("Variabili e allineamenti devono essere espliciti.")
            result.append(WeatherBinding(
                declaration["name"], sources[declaration["source"]], declaration["role"],
                tuple(declaration["variables"]), tuple(declaration["time_alignment"].items()),
                declaration["publication_delay"], declaration["availability_evidence"],
            ))
        return tuple(result)
    except (KeyError, TypeError) as exc:
        raise ValueError("Binding meteo incompleti, sorgente assente o DA DECIDERE.") from exc


def _weather_columns(binding: WeatherBinding, target: TimeSeriesDataset,
                     origin: pd.Timestamp) -> tuple[pd.DataFrame, dict[str, str], dict[str, object]]:
    """Align weather without interpolation; mask observations unavailable at origin."""
    source = binding.result
    source.request.parameters()
    if not binding.name or not binding.name.isidentifier():
        raise ValueError("Il nome del binding deve essere un identificatore non vuoto.")
    if binding.role not in ("past", "known_future"):
        raise ValueError("role deve essere past o known_future.")
    if binding.publication_delay == "DA DECIDERE" or binding.availability_evidence == "DA DECIDERE":
        raise ValueError("Completare ritardo e provenienza DA DECIDERE prima dell'unione.")
    if (not binding.variables or len(set(binding.variables)) != len(binding.variables)
            or not set(binding.variables).issubset(source.request.variables)):
        raise ValueError("Le variabili devono essere un sottoinsieme esplicito della sorgente.")
    alignment = dict(binding.time_alignment)
    if len(alignment) != len(binding.time_alignment) or set(alignment) != set(binding.variables):
        raise ValueError("Dichiarare un allineamento per ogni variabile selezionata.")
    index = source.frame.index
    if (not isinstance(index, pd.DatetimeIndex) or str(index.tz) != "UTC" or index.hasnans
            or not index.is_unique or not index.is_monotonic_increasing
            or any(t != t.floor("h") for t in index) or not source.frame.columns.is_unique):
        raise ValueError("La sorgente meteo deve avere timestamp orari UTC univoci e ordinati.")
    report: dict[str, object] = {"source": source.metadata, "role": binding.role,
                               "publication_delay": binding.publication_delay,
                               "availability_evidence": binding.availability_evidence,
                               "alignment": alignment, "unavailable_counts": {}, "nan_counts": {}}
    if binding.role == "known_future":
        checked = source.future_at(origin.isoformat(), binding.publication_delay,
                                   binding.availability_evidence)
        report["forecast_availability"] = checked.attrs["forecast_availability"]
        delay = pd.Timedelta(0)
    else:
        if source.request.product != "reanalysis":
            raise ValueError("Per meteo passato usare reanalysis; previsioni con ruolo known_future.")
        if not binding.availability_evidence or not binding.availability_evidence.strip():
            raise ValueError("Documentare la disponibilità del meteo passato.")
        if binding.publication_delay is None:
            raise ValueError("Specificare il ritardo del meteo passato.")
        delay = pd.Timedelta(binding.publication_delay)
        if pd.isna(delay) or delay < pd.Timedelta(0):
            raise ValueError("Ritardo del meteo passato non valido.")
    columns, units = {}, {}
    for variable in binding.variables:
        if variable not in source.frame:
            raise ValueError("Variabile assente nel frame meteo.")
        series = source.frame[variable].copy()
        if (not is_numeric_dtype(series.dtype) or is_bool_dtype(series.dtype)
                or np.iscomplexobj(series.to_numpy())
                or np.isinf(series.to_numpy(dtype=float, na_value=np.nan)).any()):
            raise ValueError("Il meteo richiede numeri reali finiti o NaN.")
        if source.metadata.get("units", {}).get(variable) != UNITS[variable]:
            raise ValueError("Unità della sorgente meteo assente o incompatibile.")
        semantics = source.metadata.get("time_semantics", {}).get(variable)
        if semantics == "instant_at_timestamp" and alignment[variable] == "instant_at_start":
            effective = index
        elif semantics == "mean_over_preceding_hour" and alignment[variable] == "mean_to_interval_start":
            if fixed_step(target.spec.frequency) != pd.Timedelta(hours=1):
                raise ValueError("Una media oraria richiede target orario; nessuna ripartizione implicita.")
            effective = index - pd.Timedelta(hours=1)
        else:
            raise ValueError("Allineamento incompatibile con la semantica temporale della sorgente.")
        available = pd.Series(True, index=effective)
        if binding.role == "past":
            available = pd.Series((effective < origin) & (index + delay <= origin), index=effective)
        series.index = effective
        report["unavailable_counts"][variable] = int((~available.reindex(
            target.frame.index, fill_value=True)).sum())
        series = series.where(available).reindex(target.frame.index)
        column = f"weather_{binding.name}_{variable}"
        columns[column] = series
        units[column] = UNITS[variable]
        report["nan_counts"][column] = int(series.isna().sum())
    return pd.DataFrame(columns, index=target.frame.index), units, report


def assemble_features(target: TimeSeriesDataset, config: FeatureConfig,
                      weather: tuple[WeatherBinding, ...], origin_utc: str) -> FeatureResult:
    """Join on the target UTC grid, retaining truth but never making it a future input."""
    target.validate()
    if target.spec.past_covariates or target.spec.known_future_covariates:
        raise ValueError("Passare il solo target; ogni covariata deve avere una sorgente dichiarata.")
    if config.alignment_policy != "exact":
        raise ValueError("Questo step supporta solo alignment_policy=exact, senza riempimenti.")
    origin = utc_timestamp(origin_utc)
    step = fixed_step(target.spec.frequency)
    if (origin < target.frame.index[0] or origin > target.frame.index[-1] + step
            or (origin - target.frame.index[0]) % step != pd.Timedelta(0)):
        raise ValueError("L'origine deve essere sulla griglia del periodo target.")
    frame = target.frame.copy(deep=True)
    calendar = calendar_features(frame.index, config.calendar)
    units = {name: "dimensionless" for name in calendar.columns}
    past, future = [], list(calendar.columns)
    report: dict[str, object] = {"origin_utc": origin.isoformat(), "alignment_policy": "exact",
                               "calendar_timezone": config.calendar.timezone,
                               "holidays_version": version("holidays"), "weather": {},
                               "target_publication_delay": "not modeled at Step 5"}
    frame = pd.concat([frame, calendar], axis=1)
    names = [binding.name for binding in weather]
    if len(set(names)) != len(names):
        raise ValueError("Nomi dei binding meteo duplicati.")
    for binding in weather:
        data, source_units, details = _weather_columns(binding, target, origin)
        if set(data.columns).intersection(frame.columns):
            raise ValueError("Collisione dei nomi delle covariate.")
        frame = pd.concat([frame, data], axis=1)
        units.update(source_units)
        (past if binding.role == "past" else future).extend(data.columns)
        report["weather"][binding.name] = details
    if (set(config.past_covariates) != set(past) or set(config.known_future_covariates) != set(future)
            or len(config.past_covariates) != len(past) or len(config.known_future_covariates) != len(future)):
        raise ValueError("I ruoli configurati non coincidono con calendario e binding dichiarati.")
    frame = frame.loc[:, ["target", *config.past_covariates, *config.known_future_covariates]]
    spec = DatasetSpec(target.spec.target, target.spec.frequency, config.past_covariates,
                       config.known_future_covariates, tuple(units.items()),
                       target.spec.provenance + "; Step 5 features; source details in assembly report")
    result = TimeSeriesDataset(frame, spec)
    result.validate()
    report["nan_counts"] = {column: int(frame[column].isna().sum()) for column in frame}
    return FeatureResult(result, origin.isoformat(), report)
