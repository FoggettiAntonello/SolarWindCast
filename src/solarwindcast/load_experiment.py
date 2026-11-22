"""Step 12 acquisition, exact residual demand and monthly backtesting with immutable outputs."""

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path

import pandas as pd
import yaml

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.load_data import (
    acquire_product,
    inspect_product,
    parse_load_xml,
    residual_load,
)
from solarwindcast.monthly_experiment import (
    _json_safe,
    check_frozen_protocol,
    score_predictions,
)
from solarwindcast.monthly_forecasting import MonthlyTimestral, baseline_predictions
from solarwindcast.monthly_protocol import fold_preview
from solarwindcast.monthly_summary import monthly_energy


def read_response(folder: Path) -> tuple[dict[str, object], str | None]:
    """Verify immutable response bytes and metadata before any reuse."""
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    if metadata["status"] != "complete":
        return metadata, None
    path = folder / "response.xml"
    if sha256(path.read_bytes()).hexdigest() != metadata["sha256"]:
        raise ValueError("Hash della risposta non corrispondente.")
    return metadata, path.read_text(encoding="utf-8")


def probe_sources(config: dict[str, object], root: Path) -> list[dict[str, object]]:
    """Make only the small configured source checks, reusing verified existing responses."""
    settings = config["step12"]
    if settings["authorized"] is not True:
        raise RuntimeError("Step 12 non autorizzato.")
    reports = []
    for number, probe in enumerate(settings["probes"]):
        folder = root / settings["raw_directory"] / "probes" / f"{number:02d}_{probe['product']}"
        if not folder.exists():
            acquire_product(probe["product"], probe["start_utc"], probe["end_exclusive_utc"], folder,
                settings["acquisition"], root / ".env")
            time.sleep(settings["acquisition"]["pause_seconds"])
        metadata, xml = read_response(folder)
        if (metadata["product"] != probe["product"]
                or pd.Timestamp(metadata["start_utc"]) != pd.Timestamp(probe["start_utc"])
                or pd.Timestamp(metadata["end_exclusive_utc"]) != pd.Timestamp(probe["end_exclusive_utc"])):
            raise ValueError("Il campione conservato non corrisponde alla richiesta.")
        report = {"request": probe, "metadata": metadata}
        if xml is not None:
            report["response"] = inspect_product(xml)
            if (report["response"]["document_type"] != metadata["document_type"]
                    or report["response"]["process_type"] != metadata["process_type"]):
                raise ValueError("Semantica della risposta diversa dal prodotto richiesto.")
            if probe["product"] in ("actual_load", "day_ahead_load"):
                dataset = parse_load_xml(xml, probe["start_utc"], probe["end_exclusive_utc"],
                    config["data"]["frequency"], metadata["area_eic"], metadata["sha256"], metadata["process_type"])
                report["hourly_check"] = {"expected": len(dataset.frame), "valid": int(dataset.frame.target.notna().sum())}
        reports.append(report)
        print(f"{probe['product']}: {metadata['status']}", flush=True)
    return reports


def download_history(config: dict[str, object], root: Path) -> list[Path]:
    """Acquire calendar-month chunks only after a separate explicit history authorization."""
    settings = config["step12"]
    if settings["authorized"] is not True or settings["acquisition"]["history_download_authorized"] is not True:
        raise RuntimeError("Serve l'autorizzazione esplicita al download dello storico del carico.")
    boundaries = pd.date_range(settings["start_utc"], settings["end_exclusive_utc"], freq="MS")
    if (len(boundaries) < 2 or boundaries[0] != pd.Timestamp(settings["start_utc"])
            or boundaries[-1] != pd.Timestamp(settings["end_exclusive_utc"])):
        raise ValueError("Lo storico deve avere confini mensili UTC esatti.")
    paths = []
    for first, stop in pairwise(boundaries):
        folder = root / settings["raw_directory"] / "history" / first.strftime("%Y%m")
        if not folder.exists():
            acquire_product("actual_load", first.isoformat(), stop.isoformat(), folder,
                settings["acquisition"], root / ".env")
            time.sleep(settings["acquisition"]["pause_seconds"])
        metadata, _ = read_response(folder)
        if (metadata["product"] != "actual_load" or pd.Timestamp(metadata["start_utc"]) != first
                or pd.Timestamp(metadata["end_exclusive_utc"]) != stop):
            raise ValueError("Risposta non corrispondente al lotto richiesto.")
        if metadata["status"] not in ("complete", "no_matching_data"):
            raise RuntimeError("Trasporto fallito; interrompere senza nascondere il problema.")
        paths.append(folder)
        print(f"Carico {first:%Y-%m}: {metadata['status']}", flush=True)
    return paths


def prepare_extension(config: dict[str, object], root: Path, paths: list[Path]) -> dict[str, TimeSeriesDataset]:
    """Verify production and load snapshots, then derive signed residuals before monthly integration."""
    settings, frequency = config["step12"], config["data"]["frequency"]
    from entsoe.mappings import lookup_area

    area = lookup_area(settings["acquisition"]["market_area"]).value
    if not paths:
        raise ValueError("Nessun lotto del carico: acquisire lo storico prima dell'esperimento.")
    chunks, source_hashes = [], []
    for folder in paths:
        metadata, xml = read_response(folder)
        if (metadata["product"] != "actual_load" or metadata["process_type"] != "A16"
                or metadata["area_eic"] != area):
            raise ValueError("I consumi osservati non possono provenire dalle previsioni.")
        source_hashes.append(sha256((folder / "metadata.json").read_bytes()).hexdigest())
        if xml is None and metadata["status"] != "no_matching_data":
            raise ValueError("Acquisizione non valida.")
        if xml is None:
            index = pd.date_range(metadata["start_utc"], metadata["end_exclusive_utc"],
                freq=frequency, inclusive="left", name="timestamp_utc")
            frame = pd.DataFrame({"target": float("nan")}, index=index)
        else:
            frame = parse_load_xml(xml, metadata["start_utc"], metadata["end_exclusive_utc"], frequency,
                metadata["area_eic"], metadata["sha256"]).frame
        chunks.append(frame)
    load = TimeSeriesDataset(pd.concat(chunks), DatasetSpec("load", frequency, (), (), (),
        "ENTSO-E A65/A16 metadata SHA-256 " + ",".join(source_hashes)))
    load.validate()
    expected = pd.date_range(settings["start_utc"], settings["end_exclusive_utc"],
        freq=frequency, inclusive="left", name="timestamp_utc")
    if not load.frame.index.equals(expected):
        raise ValueError("Lotti del carico incompleti, duplicati o fuori periodo.")
    prepared = root / settings["production_directory"]
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Produzione incompleta.")
    for name, digest in manifest["files_sha256"].items():
        path = (prepared / name).resolve()
        if not path.is_relative_to(prepared.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Hash di produzione non corrispondente.")
    quality = json.loads((prepared / "quality.json").read_text(encoding="utf-8"))
    components = {}
    for name in ("solar", *config["monthly_protocol"]["wind_components"]):
        if name + ".parquet" not in manifest["files_sha256"] or quality[name]["unit"] != "MW" or quality[name]["frequency"] != frequency:
            raise ValueError("Unità, frequenza o provenienza delle componenti non valide.")
        components[name] = pd.read_parquet(prepared / (name + ".parquet")).target
        if not components[name].index.equals(load.frame.index):
            raise ValueError("Griglie diverse: nessun allineamento implicito.")
    provenance = "production manifest SHA-256 " + sha256((prepared / "manifest.json").read_bytes()).hexdigest()
    solar = TimeSeriesDataset(components["solar"].to_frame("target"), DatasetSpec("solar", frequency, (), (), (), provenance))
    names = config["monthly_protocol"]["wind_components"]
    wind_series = pd.concat([components[name] for name in names], axis=1).sum(axis=1, min_count=len(names))
    wind = TimeSeriesDataset(wind_series.to_frame("target"), DatasetSpec("wind", frequency, (), (), (), provenance))
    targets = {"load": load, "residual_load": residual_load(load, solar, wind)}
    requested = settings["targets"]
    if not requested or len(set(requested)) != len(requested) or not set(requested).issubset(targets):
        raise ValueError("Target di estensione non validi.")
    return {target: targets[target] for target in requested}


def monthly_frame(dataset: TimeSeriesDataset, timezone: str) -> pd.DataFrame:
    """Convert complete observed months to the same power/energy contract as Step 11."""
    months = monthly_energy(dataset, timezone)
    months["duration_hours"] = ((pd.to_datetime(months.end_exclusive_utc, utc=True) -
        pd.to_datetime(months.start_utc, utc=True)) / pd.Timedelta(hours=1))
    months["energy_mwh"] = pd.to_numeric(months.energy_mwh, errors="raise").astype(float)
    months["mean_power_mw"] = months.energy_mwh / months.duration_hours
    months.index = pd.PeriodIndex(months.month, freq="M", name="month")
    return months


def run_extension(config: dict[str, object], root: Path, paths: list[Path],
                  probes: list[dict[str, object]], model_factory: Callable[..., MonthlyTimestral] | None = None) -> dict[str, object]:
    """Run unchanged model settings on the new targets, preserving original solar/wind test results."""
    settings = config["step12"]
    if settings["authorized"] is not True:
        raise RuntimeError("Estensione non autorizzata.")
    frozen = check_frozen_protocol(config, root)
    output = root / settings["output_directory"]
    if output.exists():
        raise FileExistsError("I risultati dello Step 12 richiedono una cartella nuova.")
    datasets = prepare_extension(config, root, paths)
    protocol = config["monthly_protocol"]
    inventory = []
    for folder in paths:
        metadata, xml = read_response(folder)
        inventory.append({"directory": str(folder.relative_to(root)).replace("\\", "/"),
            "metadata": metadata, "metadata_sha256": sha256((folder / "metadata.json").read_bytes()).hexdigest(),
            "response": inspect_product(xml) if xml is not None else None})
    import torch

    torch.set_num_threads(config["monthly_execution"]["cpu_threads"])
    models = [(model_factory or MonthlyTimestral)(protocol, model) for model in protocol["models"]]
    output.mkdir(parents=True, exist_ok=False)
    (output / "source_inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
    started = time.perf_counter()
    rows, quality, skipped = [], {}, []
    periods = frozen["evaluation_periods"]
    for target, dataset in datasets.items():
        dataset.frame.to_parquet(output / (target + ".parquet"))
        months = monthly_frame(dataset, protocol["calendar_timezone"])
        months.to_csv(output / (target + "_months.csv"), index=False)
        quality[target] = {"hourly_expected": len(dataset.frame), "hourly_valid": int(dataset.frame.target.notna().sum()),
            "hourly_missing": int(dataset.frame.target.isna().sum()), "negative_hours": int((dataset.frame.target < 0).sum()),
            "missing_timestamps_utc": [stamp.isoformat() for stamp in dataset.frame.index[dataset.frame.target.isna()]],
            "minimum_mw": dataset.frame.target.min(), "maximum_mw": dataset.frame.target.max(),
            "months": len(months), "complete_months": int(months.complete.sum()),
            "missing_months": months.loc[~months.complete, "month"].tolist(), "provenance": dataset.spec.provenance}
        for phase, start, stop in (("development", periods["development_start_utc"], periods["test_start_utc"]),
                                  ("test", periods["test_start_utc"], periods["test_end_exclusive_utc"])):
            for fold in fold_preview(months, start, stop, protocol):
                if not fold["forecast_input_ready"]:
                    skipped.append({"target": target, "phase": phase, **fold})
                    continue
                month = pd.Period(fold["target_month"], freq="M")
                predictions = baseline_predictions(months, month, protocol)
                for model in models:
                    for variant in protocol["model_variants"]:
                        predictions.append(model.predict(months, month, variant))
                for prediction in predictions:
                    row = asdict(prediction)
                    row["quantiles_mwh"] = ({str(q): float(value) for q, value in prediction.quantiles_mwh.items()}
                        if prediction.quantiles_mwh is not None else None)
                    row.update(target=target, phase=phase, issue_utc=fold["issue_utc"],
                        target_start_utc=months.loc[month, "start_utc"],
                        actual_mwh=float(months.loc[month, "energy_mwh"]) if fold["target_complete"] else None)
                    rows.append(row)
            print(f"{target} / {phase}: completato", flush=True)
    result = {"status": "complete", "kind": "synthetic_step12_test" if model_factory else "retrospective_monthly_extension",
        "unit": "MWh", "protocol": protocol, "extension": settings, "evaluation_periods": periods,
        "protocol_sha256": frozen["settings_sha256"], "source_prepared_manifest_sha256": frozen["source_prepared_manifest_sha256"],
        "frozen_snapshot_sha256": sha256((root / config["monthly_execution"]["frozen_protocol_directory"] /
            "protocol_snapshot.json").read_bytes()).hexdigest(),
        "execution": config["monthly_execution"], "elapsed_seconds": time.perf_counter() - started,
        "versions": {"torch": torch.__version__, "entsoe-py": version("entsoe-py"), "pandas": pd.__version__},
        "inference_calls": sum(row["model"].startswith("timestral_") for row in rows),
        "models": {model.size: model.provenance for model in models}, "quality": quality, "official_probes": probes,
        "scores": score_predictions(rows, protocol), "skipped": skipped,
        "official_monthly_energy_comparison": "not eligible: unequal horizon/quantity and vintage not verified"}
    result = _json_safe(result)
    (output / "predictions.json").write_text(json.dumps({"status": "complete", "forecasts": _json_safe(rows)}, indent=2, allow_nan=False), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from solarwindcast.load_results_html import render_extension

    (output / "presentazione.html").write_text(render_extension(result, rows), encoding="utf-8")
    files = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": files}, indent=2), encoding="utf-8")
    return result


def main() -> None:
    """Execute explicitly selected source probes, authorized download or local backtest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--mode", choices=("probe", "download", "run"), required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    root = args.config.resolve().parent.parent
    if args.mode == "download":
        download_history(config, root)
    else:
        probes = probe_sources(config, root)
        if args.mode == "probe":
            from solarwindcast.load_results_html import save_probe_report

            output = root / config["step12"]["source_check_directory"]
            if not output.exists():
                save_probe_report(probes, output)
            print(json.dumps(probes, indent=2))
        else:
            folders = sorted((root / config["step12"]["raw_directory"] / "history").iterdir())
            run_extension(config, root, folders, probes)
            print(config["step12"]["output_directory"] + "/presentazione.html")


if __name__ == "__main__":
    main()
