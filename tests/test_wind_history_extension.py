"""Synthetic bounded history recovery, unchanged calibration and matched-window comparisons."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest
import yaml

from solarwindcast.monthly_forecasting import MonthlyPrediction
from solarwindcast.wind_calibration import run_calibration
from solarwindcast.wind_history_extension import recover_history


def test_recover_exactly_five_origins_and_recalibrate_without_parameter_search(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import solarwindcast.wind_calibration as calibration_module
    import solarwindcast.wind_history_extension as extension_module

    config = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/project.yaml").read_text(encoding="utf-8"))
    config["wind_calibration"].update(source_directory="source", output_directory="previous")
    config["wind_history_extension"].update(source_directory="source", previous_calibration_directory="previous",
        output_directory="extended_source", calibrated_output_directory="extended_calibration")
    index = pd.period_range("2021-11", periods=36, freq="M", name="month")
    durations = [(month.end_time + pd.Timedelta(nanoseconds=1) - month.start_time) / pd.Timedelta(hours=1) for month in index]
    months = pd.DataFrame({"mean_power_mw": 100., "duration_hours": durations, "energy_mwh": [100 * h for h in durations],
        "complete": True, "start_utc": [month.start_time.tz_localize("UTC").isoformat() for month in index]}, index=index)
    months.loc[index[:7], ["mean_power_mw", "energy_mwh"]] = float("nan")
    months.loc[index[:7], "complete"] = False
    frozen = {"settings_sha256": "synthetic", "evaluation_periods": {
        "development_start_utc": "2021-11-01T00:00Z", "test_start_utc": "2024-11-01T00:00Z"}}
    monkeypatch.setattr(calibration_module, "check_frozen_protocol", lambda *args: frozen)
    monkeypatch.setattr(extension_module, "check_frozen_protocol", lambda *args: frozen)
    monkeypatch.setattr(extension_module, "load_monthly_targets", lambda *args: {"wind": months})
    rows = []
    for month in pd.period_range("2023-12", "2024-10", freq="M"):
        value = float(months.loc[month, "energy_mwh"])
        for model in (config["wind_calibration"]["candidate"], config["wind_calibration"]["reference"], "same_month_previous_year"):
            rows.append({"model": model, "month": str(month), "target": "wind", "phase": "development",
                "point_mwh": value, "actual_mwh": value, "target_start_utc": months.loc[month, "start_utc"], "metadata": {},
                "quantiles_mwh": ({"0.05": value - 20000, "0.1": value - 10000, "0.5": value,
                    "0.9": value + 10000, "0.95": value + 20000} if model.startswith("timestral_") else None)})
    source = tmp_path / "source"
    source.mkdir()
    data = source / "development_predictions.json"
    data.write_text(json.dumps(rows))
    (source / "manifest.json").write_text(json.dumps({"files_sha256": {data.name: sha256(data.read_bytes()).hexdigest()}}))
    old = run_calibration(config, tmp_path)
    assert old["evaluation_cases"] == 4
    original_manifest = sha256((tmp_path / "previous/manifest.json").read_bytes()).hexdigest()
    calls = []

    class SyntheticModel:
        """Record only approved origins, predicting from known duration in a synthetic constant series."""

        def __init__(self, settings: dict[str, object], specification: dict[str, object]) -> None:
            self.provenance = {"backend_mode": "synthetic"}
            assert settings["context_months"] == 12

        def predict(self, frame: pd.DataFrame, month: pd.Period, variant: str) -> MonthlyPrediction:
            calls.append(str(month))
            value = float(100 * frame.loc[month, "duration_hours"])
            return MonthlyPrediction("timestral_28M_known_calendar", str(month), value,
                pd.Series({.05: value - 20000, .1: value - 10000, .5: value, .9: value + 10000, .95: value + 20000}), {})

    result = recover_history(config, tmp_path, SyntheticModel)
    assert calls == config["wind_history_extension"]["additional_origins"]
    assert len(calls) == result["history_extension"]["new_inferences"] == 5
    assert result["evaluation_cases"] == 9 and result["operational_promotion"] is False
    assert result["scored_months"] == [str(month) for month in pd.period_range("2024-02", "2024-10", freq="M")]
    assert result["matched_previous_window_scores"]["wind"]["development"]["models"][config["wind_calibration"]["candidate"]]["point_cases"] == 4
    assert sha256((tmp_path / "previous/manifest.json").read_bytes()).hexdigest() == original_manifest
    for field in ("minimum_past_errors", "scale_lower", "scale_upper", "identity_penalty", "lookback_months"):
        assert result["settings"][field] == old["settings"][field]
    html = (tmp_path / "extended_calibration/presentazione.html").read_text(encoding="utf-8")
    assert "Solo 9 mesi" in html and "storico ridotto" in html
    assert "5 inferenze" in html and "Controllo sui mesi" in html
    for folder in (tmp_path / "extended_source", tmp_path / "extended_calibration"):
        for name, digest in json.loads((folder / "manifest.json").read_text())["files_sha256"].items():
            assert sha256((folder / name).read_bytes()).hexdigest() == digest
    changed = deepcopy(config)
    changed["wind_calibration"]["identity_penalty"] = .2
    with pytest.raises(ValueError, match="cambiata"):
        recover_history(changed, tmp_path, SyntheticModel)
    with pytest.raises(FileExistsError):
        recover_history(config, tmp_path, SyntheticModel)
