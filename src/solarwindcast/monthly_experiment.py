"""Run the frozen calendar-month benchmark and persist all forecasts before reporting scores."""

import argparse
import json
import time
from collections.abc import Callable
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from solarwindcast.evaluation import (
    central_interval,
    common_valid_mask,
    interval_metrics,
    pinball_metrics,
    point_metrics,
)
from solarwindcast.monthly_forecasting import MonthlyTimestral, baseline_predictions
from solarwindcast.monthly_protocol import fold_preview, load_monthly_targets


def check_frozen_protocol(config: dict[str, object], root: Path) -> dict[str, object]:
    """Require separate execution authorization and unchanged approved settings/data fingerprints."""
    execution = config["monthly_execution"]
    protocol = config["monthly_protocol"]
    if execution["authorized"] is not True or protocol["approved"] is not True:
        raise RuntimeError("Esperimento mensile non autorizzato.")
    folder = root / execution["frozen_protocol_directory"]
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Protocollo congelato modificato.")
    snapshot = json.loads((folder / "protocol_snapshot.json").read_text(encoding="utf-8"))
    actual = sha256(json.dumps(protocol, sort_keys=True, allow_nan=False).encode()).hexdigest()
    if actual != snapshot["settings_sha256"] or snapshot["settings"] != protocol:
        raise ValueError("Impostazioni diverse dal protocollo congelato.")
    prepared = root / config["monthly_inspection"]["prepared_directory"]
    if sha256((prepared / "manifest.json").read_bytes()).hexdigest() != snapshot["source_prepared_manifest_sha256"]:
        raise ValueError("Dati di ingresso diversi da quelli congelati.")
    if protocol["local_files_only"] is not True or protocol["weather_enabled"] is not False:
        raise ValueError("Questo esperimento usa solo pesi locali e calendario verificato.")
    return snapshot


def score_predictions(rows: list[dict[str, object]], protocol: dict[str, object]) -> dict[str, object]:
    """Compare identical observed UTC target months; use a separate common mask for quantile models."""
    results = {}
    for target in sorted({row["target"] for row in rows}):
        results[target] = {}
        for phase in sorted({row["phase"] for row in rows}):
            selected = [row for row in rows if row["target"] == target and row["phase"] == phase]
            if not selected:
                continue
            model_names = sorted({row["model"] for row in selected})
            dates = sorted({row["target_start_utc"] for row in selected})
            index = pd.DatetimeIndex(pd.to_datetime(dates, utc=True), name="timestamp_utc")
            lookup = {(row["model"], row["target_start_utc"]): row for row in selected}
            observed = {row["target_start_utc"]: row["actual_mwh"] for row in selected}
            actual = pd.Series([observed[date] for date in dates], index=index, dtype=float)
            points, quantiles = {}, {}
            for model in model_names:
                records = [lookup.get((model, date)) for date in dates]
                points[model] = pd.Series([row["point_mwh"] if row else None for row in records], index=index, dtype=float)
                if any(row and row["quantiles_mwh"] for row in records):
                    quantiles[model] = pd.DataFrame([
                        {float(key): value for key, value in row["quantiles_mwh"].items()} if row and row["quantiles_mwh"] else {}
                        for row in records], index=index).reindex(columns=protocol["comparison_quantile_levels"])
            point_mask = common_valid_mask(actual, points)
            quantile_mask = common_valid_mask(actual, quantiles) if quantiles else None
            scores = {}
            reference = points["same_month_previous_year"]
            for model in model_names:
                report = point_metrics(actual, points[model], "omit", point_mask)
                entry = {"point_scores": {key.replace("_mw", "_mwh"): value for key, value in report.scores.items()},
                    "point_cases": report.used, "issued_forecasts": int(points[model].notna().sum()),
                    "point_excluded_utc": list(report.excluded_timestamps),
                    "negative_point_forecasts": int((points[model] < 0).sum())}
                entry["negative_quantile_forecast_months"] = sum(
                    bool(row["quantiles_mwh"] and any(value < 0 for value in row["quantiles_mwh"].values()))
                    for row in selected if row["model"] == model)
                mask = point_mask & reference.notna()
                delta = (points[model] - actual).abs() - (reference - actual).abs()
                entry["versus_seasonal"] = {"cases": int(mask.sum()), "wins": int((delta[mask] < 0).sum()),
                    "losses": int((delta[mask] > 0).sum()), "ties": int((delta[mask] == 0).sum()),
                    "mean_absolute_error_difference_mwh": float(delta[mask].mean())}
                if model in quantiles:
                    losses = pinball_metrics(actual, quantiles[model], "omit", quantile_mask)
                    entry["pinball_mwh"] = losses.scores["pinball_loss_mw"]
                    entry["quantile_cases"] = losses.used
                    entry["intervals"] = {}
                    for level in protocol["interval_levels"]:
                        lower, upper = central_interval(quantiles[model], level)
                        coverage = interval_metrics(actual, lower, upper, level, "omit", quantile_mask)
                        entry["intervals"][str(level)] = {key.replace("_mw", "_mwh"): value for key, value in coverage.scores.items()}
                scores[model] = entry
            results[target][phase] = {"candidate_forecast_months": len(dates), "observed_months": int(actual.notna().sum()),
                "point_common_months": [str(index[i]) for i in np.flatnonzero(point_mask.to_numpy())],
                "quantile_common_months": [str(index[i]) for i in np.flatnonzero(quantile_mask.to_numpy())] if quantile_mask is not None else [],
                "models": scores}
    return results


def _json_safe(value: object) -> object:
    """Represent undefined scores as JSON null rather than fabricated zero or nonstandard NaN."""
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


def run_experiment(config: dict[str, object], root: Path, output: Path,
                   model_factory: Callable[..., MonthlyTimestral] | None = None) -> dict[str, object]:
    """Run development first, then untouched test settings; no tuning or silent retry on failures."""
    if output.exists():
        raise FileExistsError("Usare una nuova directory per l'esperimento.")
    frozen = check_frozen_protocol(config, root)
    protocol = config["monthly_protocol"]
    import torch

    torch.set_num_threads(config["monthly_execution"]["cpu_threads"])
    targets = load_monthly_targets(root / config["monthly_inspection"]["prepared_directory"],
                                   protocol["calendar_timezone"], protocol["wind_components"])
    requested = protocol["targets"]
    if not requested or len(set(requested)) != len(requested) or not set(requested).issubset(targets):
        raise ValueError("Target non presenti nella preparazione mensile: nessuna sostituzione implicita.")
    targets = {name: targets[name] for name in requested}
    models = [(model_factory or MonthlyTimestral)(protocol, model) for model in protocol["models"]]
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    rows, skipped = [], []
    plan = frozen["evaluation_periods"]
    for phase, start, end in (("development", plan["development_start_utc"], plan["test_start_utc"]),
                               ("test", plan["test_start_utc"], plan["test_end_exclusive_utc"])):
        for target, months in targets.items():
            folds = fold_preview(months, start, end, protocol)
            completed = 0
            for fold in folds:
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
                    row["quantiles_mwh"] = ({str(key): float(value) for key, value in prediction.quantiles_mwh.items()}
                                             if prediction.quantiles_mwh is not None else None)
                    row.update(target=target, phase=phase, issue_utc=fold["issue_utc"],
                        target_start_utc=months.loc[month, "start_utc"],
                        actual_mwh=float(months.loc[month, "energy_mwh"]) if fold["target_complete"] else None)
                    rows.append(row)
                completed += 1
            checkpoint = {"status": "in_progress", "completed_phase": phase, "completed_target": target,
                          "forecasts": _json_safe(rows), "skipped": skipped}
            (output / "predictions.json").write_text(json.dumps(checkpoint, indent=2, allow_nan=False), encoding="utf-8")
            print(f"{phase} / {target}: {completed} mesi previsti", flush=True)
    result = {"status": "complete", "kind": "synthetic_injected_monthly_test" if model_factory else "retrospective_monthly_backtest", "unit": "MWh",
        "protocol_sha256": frozen["settings_sha256"], "protocol": protocol,
        "evaluation_periods": frozen["evaluation_periods"],
        "frozen_snapshot_sha256": sha256((root / config["monthly_execution"]["frozen_protocol_directory"] /
                                          "protocol_snapshot.json").read_bytes()).hexdigest(),
        "source_prepared_manifest_sha256": frozen["source_prepared_manifest_sha256"],
        "execution": config["monthly_execution"], "elapsed_seconds": time.perf_counter() - started,
        "torch_version": torch.__version__, "models": {model.size: model.provenance for model in models},
        "scores": _json_safe(score_predictions(rows, protocol)), "skipped": skipped}
    (output / "predictions.json").write_text(json.dumps({"status": "complete", "forecasts": _json_safe(rows)}, indent=2, allow_nan=False), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    from solarwindcast.monthly_results_html import render_results

    (output / "presentazione.html").write_text(render_results(result, rows), encoding="utf-8")
    hashes = {name: sha256((output / name).read_bytes()).hexdigest()
              for name in ("predictions.json", "results.json", "presentazione.html")}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    return result


def main() -> None:
    """Execute only the explicitly authorized frozen monthly experiment from local data/cache."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    run_experiment(config, args.config.resolve().parent.parent, args.output)
    print((args.output / "presentazione.html").resolve())


if __name__ == "__main__":
    main()
