"""Recover only authorized local-history wind origins, then apply the unchanged rolling calibrator."""

import argparse
import json
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path

import pandas as pd
import yaml

from solarwindcast.monthly_experiment import _json_safe, check_frozen_protocol
from solarwindcast.monthly_forecasting import MonthlyTimestral
from solarwindcast.monthly_improvement import verify_manifest
from solarwindcast.monthly_protocol import fold_preview, load_monthly_targets
from solarwindcast.wind_calibration import run_calibration


def recover_history(config: dict[str, object], root: Path,
                     model_factory: Callable[..., MonthlyTimestral] | None = None) -> dict[str, object]:
    """Generate exactly the approved missing origins; preserve all scientific calibration settings."""
    settings = config["wind_history_extension"]
    if settings["authorized"] is not True or settings["local_files_only"] is not True:
        raise RuntimeError("Estensione non autorizzata o rete non ammessa.")
    frozen = check_frozen_protocol(config, root)
    original_calibration = config["wind_calibration"]
    source, previous = root / settings["source_directory"], root / settings["previous_calibration_directory"]
    verify_manifest(source)
    verify_manifest(previous)
    earlier_settings = json.loads((previous / "settings_before_fit.json").read_text(encoding="utf-8"))["settings"]
    if earlier_settings != original_calibration:
        raise ValueError("La calibrazione è cambiata rispetto alla versione precedente.")
    output, calibrated_output = root / settings["output_directory"], root / settings["calibrated_output_directory"]
    if output.exists() or calibrated_output.exists():
        raise FileExistsError("Servono cartelle nuove per preservare i risultati precedenti.")
    protocol = deepcopy(config["monthly_protocol"])
    if protocol["device"] != settings["device"]:
        raise ValueError("Dispositivo diverso da quello autorizzato.")
    base, context = original_calibration["candidate"].rsplit("__ctx", 1)
    size, variant = base[len("timestral_"):].split("_", 1)
    protocol["context_months"] = int(context)
    months = load_monthly_targets(root / config["monthly_inspection"]["prepared_directory"],
        protocol["calendar_timezone"], protocol["wind_components"])[original_calibration["target"]]
    periods = frozen["evaluation_periods"]
    folds = fold_preview(months, periods["development_start_utc"], periods["test_start_utc"], protocol)
    eligible = {fold["target_month"]: fold for fold in folds if fold["scorable_without_model_run"]}
    rows = json.loads((source / "development_predictions.json").read_text(encoding="utf-8"))
    candidates = [row for row in rows if row["model"] == original_calibration["candidate"] and row["target"] == original_calibration["target"]]
    if (any(row["phase"] != "development" for row in rows)
            or len({row["month"] for row in candidates}) != len(candidates)):
        raise ValueError("Previsioni sorgente duplicate o del test.")
    missing = sorted(set(eligible) - {row["month"] for row in candidates})
    if missing != settings["additional_origins"] or len(missing) != settings["new_inference_budget"]:
        raise ValueError("Le origini mancanti non coincidono con il lotto autorizzato.")
    import torch

    torch.set_num_threads(settings["cpu_threads"])
    specification = next(item for item in protocol["models"] if item["size"] == size)
    model = (model_factory or MonthlyTimestral)(protocol, specification)
    output.mkdir(parents=True, exist_ok=False)
    snapshot = {"settings": settings, "calibration_settings": original_calibration,
        "source_manifest_sha256": sha256((source / "manifest.json").read_bytes()).hexdigest(),
        "previous_calibration_manifest_sha256": sha256((previous / "manifest.json").read_bytes()).hexdigest(),
        "original_protocol_sha256": frozen["settings_sha256"]}
    (output / "settings_before_inference.json").write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    for month in missing:
        label = pd.Period(month, freq="M")
        prediction = model.predict(months, label, variant)
        row = asdict(prediction)
        row["quantiles_mwh"] = {str(q): float(value) for q, value in prediction.quantiles_mwh.items()}
        row.update(model=original_calibration["candidate"], target=original_calibration["target"], phase="development",
            target_start_utc=months.loc[label, "start_utc"], actual_mwh=float(months.loc[label, "energy_mwh"]),
            issue_utc=eligible[month]["issue_utc"], reused=False)
        rows.append(row)
        print(f"Origine recuperata: {month}", flush=True)
    metadata = {"kind": "synthetic_extension" if model_factory else "real_local_history_extension",
        "new_inferences": len(missing), "additional_origins": missing,
        "candidate": original_calibration["candidate"], "model_provenance": model.provenance,
        "calibration_settings_changed": False, "old_test_used": False,
        "independent_validation": False, "settings_before_inference_sha256":
            sha256((output / "settings_before_inference.json").read_bytes()).hexdigest()}
    (output / "development_predictions.json").write_text(json.dumps(_json_safe(rows), indent=2, allow_nan=False), encoding="utf-8")
    (output / "history_extension.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    extended_config = deepcopy(config)
    extended_config["wind_calibration"].update(source_directory=settings["output_directory"],
        output_directory=settings["calibrated_output_directory"], previous_comparison_directory=settings["previous_calibration_directory"])
    return run_calibration(extended_config, root)


def main() -> None:
    """Recover the predeclared missing origins and recalibrate once without altering hyperparameters."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    recover_history(config, args.config.resolve().parent.parent)
    print(config["wind_history_extension"]["calibrated_output_directory"] + "/presentazione.html")


if __name__ == "__main__":
    main()
