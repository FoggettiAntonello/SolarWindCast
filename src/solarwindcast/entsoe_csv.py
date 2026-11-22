"""Strict ENTSO-E generation CSV import with explicit diagnostics and no repairs."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from re import escape

import numpy as np
import pandas as pd

from solarwindcast.dataset import DatasetSpec, Target, TimeSeriesDataset, fixed_step

COLUMNS = ("MTU (UTC)", "Area", "Production Type", "Generation (MW)")
PRODUCTION_TYPES = {"solar": {"Solar"}, "wind": {"Wind Onshore", "Wind Offshore"}}


def utc_timestamp(value: str) -> pd.Timestamp:
    """Require an explicitly UTC timestamp rather than guessing a timezone."""
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp) or timestamp.tzinfo is None or str(timestamp.tzinfo) != "UTC":
        raise ValueError("Il periodo deve dichiarare UTC esplicitamente.")
    return timestamp


@dataclass(frozen=True)
class ImportConfig:
    """Select one target, source components and a requested half-open UTC grid."""

    target: Target
    area: str
    production_types: tuple[str, ...]
    start_utc: str
    end_exclusive_utc: str
    frequency: str
    separator: str
    decimal: str
    encoding: str

    def grid(self) -> pd.DatetimeIndex:
        """Validate selections and construct the exact requested grid."""
        allowed = PRODUCTION_TYPES.get(self.target, set())
        if (not self.production_types or len(set(self.production_types)) != len(self.production_types)
                or not set(self.production_types).issubset(allowed)):
            raise ValueError("Selezionare componenti esplicite per solar o wind; carico allo Step 12.")
        if not self.area or self.area == "DA DECIDERE":
            raise ValueError("Specificare l'etichetta Area del CSV.")
        if (len(self.separator) != 1 or self.decimal not in (".", ",")
                or self.separator == self.decimal or self.encoding == "DA DECIDERE"):
            raise ValueError("Specificare separatore, decimale e codifica compatibili.")
        start, end = utc_timestamp(self.start_utc), utc_timestamp(self.end_exclusive_utc)
        step = fixed_step(self.frequency)
        if end <= start or (end - start) % step != pd.Timedelta(0):
            raise ValueError("Il periodo deve contenere un numero intero positivo di intervalli.")
        return pd.date_range(start, end, freq=step, inclusive="left", name="timestamp_utc")

    @classmethod
    def from_project_config(cls, project: Mapping[str, object]) -> "ImportConfig":
        """Read adapter settings from the single YAML structure, rejecting placeholders."""
        try:
            target, data, source = project["target"], project["data"], project["sources"]["entsoe"]
            values = {
                "target": target["selected"], "area": source["csv_area"],
                "production_types": source["production_types"], "start_utc": data["start_utc"],
                "end_exclusive_utc": data["end_exclusive_utc"], "frequency": data["frequency"],
                "separator": source["csv_separator"], "decimal": source["csv_decimal"],
                "encoding": source["csv_encoding"],
            }
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione ENTSO-E incompleta.") from exc
        if any(v is None or (isinstance(v, str) and v == "DA DECIDERE") for v in values.values()):
            raise ValueError("Completare i parametri ENTSO-E DA DECIDERE.")
        if not isinstance(values["production_types"], (list, tuple)):
            raise TypeError("production_types deve essere una lista esplicita.")
        values["production_types"] = tuple(values["production_types"])
        result = cls(**values)
        result.grid()
        return result


@dataclass
class ImportResult:
    """Dataset is absent on blocking anomalies; report always explains decisions."""

    dataset: TimeSeriesDataset | None
    report: dict[str, object] = field(default_factory=dict)


def convert_records(records: pd.DataFrame, config: ImportConfig,
                    provenance: str) -> ImportResult:
    """Validate normalized component records, align gaps and sum with full coverage.

    Required columns: start/end (UTC), component, value (raw text), source_row.
    Duplicates or bad numbers block conversion; negative values are retained.
    """
    grid = config.grid()
    step = fixed_step(config.frequency)
    rows = records.copy(deep=True)
    issues: list[dict[str, object]] = []
    report: dict[str, object] = {"issues": issues, "selected_rows": len(rows),
                                "expected_intervals": len(grid), "provenance": provenance}

    def issue(code: str, severity: str, selected: pd.DataFrame) -> None:
        """Attach source row references without replacing original observations."""
        if not selected.empty:
            issues.append({"code": code, "severity": severity,
                           "rows": selected["source_row"].tolist()})

    if rows.empty:
        issues.append({"code": "no_selected_rows", "severity": "error", "rows": []})
        return ImportResult(None, report)
    bad_time = rows["start"].isna() | rows["end"].isna()
    issue("invalid_interval", "error", rows.loc[bad_time])
    duration = rows["end"] - rows["start"]
    issue("frequency_mismatch", "error", rows.loc[~bad_time & (duration != step)])
    offgrid = ~bad_time & ((rows["start"] - grid[0]) % step != pd.Timedelta(0))
    issue("off_grid", "error", rows.loc[offgrid])
    outside = ~bad_time & ((rows["start"] < grid[0]) | (rows["start"] >= utc_timestamp(
        config.end_exclusive_utc)))
    issue("outside_requested_period", "info", rows.loc[outside])
    rows = rows.loc[~outside].copy()
    duplicate = rows.duplicated(["start", "component"], keep=False)
    issue("duplicate_component_interval", "error", rows.loc[duplicate])
    raw = rows["value"].astype(str).str.strip()
    missing = raw.isin(["", "n/e", "N/A"])
    # Only declared decimal notation is accepted. No thousands separator is guessed.
    point = escape(config.decimal)
    pattern = rf"[+-]?(?:\d+(?:{point}\d*)?|{point}\d+)(?:[eE][+-]?\d+)?"
    valid_number = raw.str.fullmatch(pattern)
    numeric = pd.to_numeric(raw.str.replace(config.decimal, ".", regex=False), errors="coerce")
    bad_number = ~missing & (~valid_number | ~np.isfinite(numeric.to_numpy(dtype=float)))
    issue("invalid_number", "error", rows.loc[bad_number])
    issue("declared_missing", "info", rows.loc[missing])
    issue("negative_value", "warning", rows.loc[numeric < 0])
    if any(item["severity"] == "error" for item in issues):
        return ImportResult(None, report)
    rows["value"] = numeric.mask(missing).astype(float)
    wide = rows.pivot(index="start", columns="component", values="value").reindex(
        index=grid, columns=list(config.production_types))
    observed = rows.assign(present=True).pivot(
        index="start", columns="component", values="present").reindex(
            index=grid, columns=list(config.production_types)).fillna(False)
    report["missing_component_intervals"] = {
        component: [t.isoformat() for t in grid[~observed[component].astype(bool)]]
        for component in config.production_types
    }
    # Requiring all configured components prevents missing offshore/onshore becoming zero.
    target = wide.sum(axis=1, min_count=len(config.production_types))
    report["target_nan_intervals"] = int(target.isna().sum())
    dataset = TimeSeriesDataset(target.to_frame("target"), DatasetSpec(
        target=config.target, frequency=config.frequency, past_covariates=(),
        known_future_covariates=(), covariate_units=(), provenance=provenance))
    dataset.validate()
    return ImportResult(dataset, report)


def read_csv(paths: Sequence[Path], config: ImportConfig) -> ImportResult:
    """Read originals unchanged, record SHA-256, and inspect selected CSV rows."""
    config.grid()
    if not paths:
        raise ValueError("Specificare almeno un CSV.")
    sources: list[dict[str, object]] = []
    frames: list[pd.DataFrame] = []
    ignored = 0
    for path in paths:
        content = Path(path).read_bytes()
        source = str(Path(path).resolve())
        sources.append({"path": source, "sha256": sha256(content).hexdigest()})
        raw = pd.read_csv(BytesIO(content), sep=config.separator, encoding=config.encoding,
                          dtype=str, keep_default_na=False, na_filter=False)
        if not set(COLUMNS).issubset(raw.columns):
            raise ValueError("CSV incompatibile: servono le quattro colonne ENTSO-E di produzione.")
        selected = raw["Area"].eq(config.area) & raw["Production Type"].isin(config.production_types)
        ignored += int((~selected).sum())
        rows = raw.loc[selected].copy()
        intervals = rows["MTU (UTC)"].str.extract(
            r"^(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}) - (\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})$")
        frames.append(pd.DataFrame({
            "start": pd.to_datetime(intervals[0], format="%d/%m/%Y %H:%M:%S", utc=True, errors="coerce"),
            "end": pd.to_datetime(intervals[1], format="%d/%m/%Y %H:%M:%S", utc=True, errors="coerce"),
            "component": rows["Production Type"], "value": rows["Generation (MW)"],
            "source_row": [f"{source}:record={i + 1}" for i in rows.index],
        }))
    result = convert_records(pd.concat(frames, ignore_index=True), config,
                             "ENTSO-E manual CSV; source hashes in import report")
    result.report.update(sources=sources, ignored_rows=ignored,
                         availability="Publication delays and revisions not reconstructed")
    return result
