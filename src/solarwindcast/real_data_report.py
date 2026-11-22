"""Inspect existing ENTSO-E snapshots and build a local report without network or forecasting."""

import argparse
import json
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import yaml

from solarwindcast.entsoe_api import parse_generation_xml
from solarwindcast.entsoe_csv import ImportConfig, utc_timestamp

COMPONENTS = {"Solar": ("solar", "Solare"), "Wind Onshore": ("wind_onshore", "Eolico a terra"),
              "Wind Offshore": ("wind_offshore", "Eolico in mare")}


@dataclass(frozen=True)
class InspectionSettings:
    """Observed snapshot properties, separate from unapproved forecasting parameters."""

    acquisition_directory: Path
    start_utc: str
    end_exclusive_utc: str
    native_frequency: str
    area_eic: str
    components: tuple[str, ...]
    decode_a03: bool
    allow_period_subset: bool = False
    exclude_consumption: bool = False

    @classmethod
    def from_project_config(cls, project: Mapping[str, object], root: Path) -> "InspectionSettings":
        """Read the explicit, local-only Step 10 inspection selection."""
        try:
            config = project["inspection"]["step10"]
            if config["mode"] != "existing_local_only" or not isinstance(config["components"], list):
                raise ValueError("Specificare ispezione locale e lista delle componenti.")
            return cls(root / config["acquisition_directory"], config["start_utc"],
                       config["end_exclusive_utc"], config["native_frequency"], config["area_eic"],
                       tuple(config["components"]), config["decode_a03"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione di ispezione incompleta.") from exc


@dataclass
class InspectionResult:
    """Decoded observations and audited descriptive results; never model performance."""

    frame: pd.DataFrame
    summary: dict[str, object]


def _number(value: float) -> float | None:
    """Use JSON null for undefined descriptive statistics, never a fabricated zero."""
    return None if pd.isna(value) else float(value)


def inspect_acquisition(settings: InspectionSettings) -> InspectionResult:
    """Verify original hashes and decode source blocks without modifying the acquisition."""
    folder = settings.acquisition_directory.resolve()
    if settings.area_eic != "10Y1001A1001A788":
        raise ValueError("Questa analisi del progetto richiede la zona di mercato Sud.")
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    plan = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    if manifest.get("source") != "entsoe" or manifest.get("complete") is not True:
        raise ValueError("L'acquisizione ENTSO-E deve essere completa.")
    subset = settings.allow_period_subset is True
    if subset:
        if not (utc_timestamp(plan["start_utc"]) <= utc_timestamp(settings.start_utc)
                < utc_timestamp(settings.end_exclusive_utc) <= utc_timestamp(plan["end_exclusive_utc"])):
            raise ValueError("Sottointervallo fuori dall'acquisizione originale.")
    elif (utc_timestamp(plan["start_utc"]) != utc_timestamp(settings.start_utc)
            or utc_timestamp(plan["end_exclusive_utc"]) != utc_timestamp(settings.end_exclusive_utc)
            or pd.Timedelta(plan["expected_frequency"]) != pd.Timedelta(settings.native_frequency)):
        raise ValueError("Periodo o frequenza dell'ispezione diversi dal piano originale.")
    if (not settings.components or len(set(settings.components)) != len(settings.components)
            or not set(settings.components).issubset(COMPONENTS)):
        raise ValueError("Selezionare componenti di produzione note e senza duplicati.")
    pieces: dict[str, list[pd.Series]] = {name: [] for name in settings.components}
    sources = []
    grid = None
    for item in manifest["items"]:
        path = (folder / item["raw_file"]).resolve()
        if item["status"] == "no_matching_data":
            if (not path.is_relative_to(folder) or path.name != "metadata.json"
                    or sha256(path.read_bytes()).hexdigest() != item["sha256"]):
                raise ValueError("Metadati di assenza non validi.")
            metadata = json.loads(path.read_text(encoding="utf-8"))
            component = item["component"]
            codes = {"Solar": "B16", "Wind Onshore": "B19", "Wind Offshore": "B18"}
            if (component not in settings.components or metadata.get("status") != "no_matching_data"
                    or metadata.get("area_eic") != settings.area_eic
                    or metadata.get("psr_type") != codes[component]
                    or utc_timestamp(metadata["start_utc"]) > utc_timestamp(settings.start_utc)
                    or utc_timestamp(metadata["end_exclusive_utc"]) < utc_timestamp(settings.end_exclusive_utc)):
                raise ValueError("Assenza non riferita alla richiesta selezionata.")
            sources.append({"file": path.relative_to(folder).as_posix(), "sha256": item["sha256"],
                "retrieved_utc": utc_timestamp(item["retrieved_utc"]).isoformat(), "created_utc": None,
                "revision": None, "components": {component: {"curve_decoding": [],
                    "issues": [{"code": "no_matching_data", "severity": "warning"}],
                    "excluded_consumption_series": []}}})
            continue
        if not path.is_relative_to(folder) or path.suffix.lower() != ".xml":
            raise ValueError("Percorso originale non valido.")
        payload = path.read_bytes()
        digest = sha256(payload).hexdigest()
        if digest != item["sha256"] or item["status"] != "complete":
            raise ValueError("Hash originale non corrispondente o richiesta incompleta.")
        text = payload.decode("utf-8")
        if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("XML con DTD o entità non supportato.")
        document = ET.fromstring(text)
        for node in document.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        created = document.findtext("createdDateTime")
        revision = document.findtext("revisionNumber")
        if revision is not None and not revision.isdigit():
            raise ValueError("Revisione del documento non valida.")
        source = {"file": path.relative_to(folder).as_posix(), "sha256": digest,
                  "retrieved_utc": utc_timestamp(item["retrieved_utc"]).isoformat(),
                  "created_utc": utc_timestamp(created).isoformat() if created else None,
                  "revision": revision, "components": {}}
        codes = {"Solar": "B16", "Wind Onshore": "B19", "Wind Offshore": "B18"}
        for component in settings.components:
            matching = [series for series in document.findall("TimeSeries")
                        if series.findtext("MktPSRType/psrType") == codes[component]]
            if not matching:
                continue
            if any(series.findtext("businessType") != "A01" for series in matching
                   if series.findtext("inBiddingZone_Domain.mRID") == settings.area_eic):
                raise ValueError("La serie selezionata non è produzione aggregata osservata A01.")
            config = ImportConfig("solar" if component == "Solar" else "wind", settings.area_eic,
                (component,), settings.start_utc, settings.end_exclusive_utc,
                settings.native_frequency, ",", ".", "utf-8")
            grid = config.grid()
            parsed = parse_generation_xml(text, config, settings.area_eic,
                "ENTSO-E original snapshot; SHA-256 checked", allow_a03=settings.decode_a03,
                restrict_periods=subset, exclude_consumption=settings.exclude_consumption)
            if parsed.dataset is None:
                raise ValueError("Anomalie bloccanti nella componente selezionata: conversione rifiutata.")
            absent = pd.to_datetime(parsed.report["missing_component_intervals"][component], utc=True)
            represented = parsed.dataset.frame["target"].loc[~grid.isin(absent)]
            pieces[component].append(represented)
            source["components"][component] = {"curve_decoding": parsed.report["curve_decoding"],
                "issues": parsed.report["issues"],
                "excluded_consumption_series": parsed.report["excluded_consumption_series"]}
        sources.append(source)
    if grid is None:
        raise ValueError("Nessuna serie di produzione selezionata presente.")
    frame = pd.DataFrame(index=grid)
    statistics, daily = {}, []
    hours = pd.Timedelta(settings.native_frequency) / pd.Timedelta(hours=1)
    for component, series_parts in pieces.items():
        name, label = COMPONENTS[component]
        series = pd.concat(series_parts).sort_index() if series_parts else pd.Series(dtype=float)
        if series.index.has_duplicates:
            raise ValueError("Intervalli sovrapposti fra documenti: nessuna deduplicazione o scelta di revisione.")
        series = series.reindex(grid)
        frame[name] = series
        valid = int(series.notna().sum())
        raw_points = sum(entry["raw_points"] for source in sources
                         for entry in source["components"].get(component, {}).get("curve_decoding", []))
        statistics[name] = {"label": label, "expected": len(grid), "valid": valid,
            "missing": len(grid) - valid, "coverage": valid / len(grid),
            "negative": int((series < 0).sum()), "zeros": int((series == 0).sum()),
            "min_mw": _number(series.min()), "mean_mw": _number(series.mean()),
            "max_mw": _number(series.max()), "energy_mwh": _number(series.sum() * hours)
            if valid == len(grid) else None, "raw_points": raw_points,
            "represented_intervals": sum(len(part) for part in series_parts),
            "missing_timestamps": [t.isoformat() for t in grid[series.isna()]],
            "largest_ramp_mw": _number(series.diff().abs().max())}
        for date, part in series.groupby(series.index.strftime("%Y-%m-%d")):
            complete = part.notna().all()
            daily.append({"date_utc": date, "component": name, "expected": len(part),
                          "valid": int(part.notna().sum()), "coverage": float(part.notna().mean()),
                          "mean_mw": _number(part.mean()), "max_mw": _number(part.max()),
                          "energy_mwh": _number(part.sum() * hours) if complete else None})
    summary = {"kind": "real_observations_quality_only", "market_area": "IT-South / zona Sud",
        "area_eic": settings.area_eic, "start_utc": grid[0].isoformat(),
        "end_exclusive_utc": utc_timestamp(settings.end_exclusive_utc).isoformat(),
        "native_frequency": settings.native_frequency, "duration_hours": len(grid) * hours,
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(), "statistics": statistics,
        "daily": daily, "sources": sources, "model_predictions_computed": False,
        "input_manifest_sha256": sha256((folder / "manifest.json").read_bytes()).hexdigest(),
        "publication_availability": "unknown; response creation/acquisition is not historic publication time",
        "versions": {name: version(name) for name in ("numpy", "pandas", "matplotlib")}}
    return InspectionResult(frame, summary)


def save_inspection(result: InspectionResult, directory: Path) -> Path:
    """Save one standalone HTML and audit data to a fresh directory, without originals or secrets."""
    from solarwindcast.real_data_html import render_html

    files = {"analysis.json": json.dumps(result.summary, indent=2, ensure_ascii=False, allow_nan=False),
             "series.json": result.frame.reset_index().to_json(orient="records", date_format="iso", double_precision=15),
             "presentazione.html": render_html(result)}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, text in files.items():
        with (directory / name).open("x", encoding="utf-8") as output:
            output.write(text)
        hashes[name] = sha256((directory / name).read_bytes()).hexdigest()
    with (directory / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump({"status": "complete", "files_sha256": hashes}, output, indent=2)
    return directory / "presentazione.html"


def main() -> None:
    """Build the Step 10 report from a selected existing snapshot; never acquire data."""
    parser = argparse.ArgumentParser(description="Presentazione HTML dei dati reali già disponibili")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("La directory esiste già: nessuna sovrascrittura.")
    project = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    root = args.config.resolve().parent.parent
    result = inspect_acquisition(InspectionSettings.from_project_config(project, root))
    print(save_inspection(result, args.output).resolve())
    print(json.dumps(result.summary["statistics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
