"""Synthetic convex-scale fitting, chronological leakage checks and immutable calibration reports."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.wind_calibration import (
    apply_scale,
    fit_scale,
    rolling_calibrate,
    run_calibration,
)


def project_settings() -> dict[str, object]:
    """Read declared structure; synthetic fixtures never change approved real-data settings."""
    return yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/project.yaml").read_text(encoding="utf-8"))


def fixture_rows() -> list[dict[str, object]]:
    """Eleven deliberately overdispersed monthly forecasts with alternating small errors."""
    rows = []
    for number, month in enumerate(pd.period_range("2024-01", periods=11, freq="M")):
        rows.append({"model": "timestral_28M_known_calendar__ctx12", "target": "wind", "phase": "development",
            "month": str(month), "target_start_utc": month.start_time.tz_localize("UTC").isoformat(),
            "point_mwh": 100., "actual_mwh": 98. if number % 2 else 102., "metadata": {},
            "quantiles_mwh": {"0.05": 60., "0.1": 70., "0.5": 100., "0.9": 130., "0.95": 140.}})
    return rows


def test_positive_regularized_scale_minimizes_declared_objective() -> None:
    project = project_settings()
    settings = project["wind_calibration"]
    levels = project["monthly_protocol"]["comparison_quantile_levels"]
    history = fixture_rows()[:6]
    scale = fit_scale(history, levels, settings)
    assert settings["scale_lower"] <= scale < 1

    def objective(value: float) -> float:
        losses = []
        for row in history:
            for level in levels:
                error = (row["actual_mwh"] - (100 + value * (row["quantiles_mwh"][str(level)] - 100))) / 80
                losses.append(max(level * error, (level - 1) * error))
        return sum(losses) / len(losses) + settings["identity_penalty"] * (value - 1) ** 2

    assert objective(scale) <= objective(1.)
    assert objective(scale) <= min(objective(value) for value in np.linspace(.5, 1.5, 101)) + 1e-8
    with pytest.raises(ValueError, match="insufficienti"):
        fit_scale(history[:2], levels, settings)


def test_median_and_order_preserved_no_clipping_or_input_mutation() -> None:
    row = fixture_rows()[0]
    snapshot = deepcopy(row)
    result = apply_scale(row, .7)
    assert result["point_mwh"] == row["point_mwh"] == result["quantiles_mwh"]["0.5"]
    values = list(result["quantiles_mwh"].values())
    assert values == sorted(values) and row == snapshot
    negative = deepcopy(row)
    negative["point_mwh"] = 0.
    negative["quantiles_mwh"] = {q: value - 100 for q, value in row["quantiles_mwh"].items()}
    assert apply_scale(negative, .7)["quantiles_mwh"]["0.05"] < 0
    with pytest.raises(ValueError):
        apply_scale(row, 0.)


def test_current_future_and_unfinished_month_do_not_enter_fit() -> None:
    project = project_settings()
    rows = fixture_rows()
    calibrated, trace = rolling_calibrate(rows, project["monthly_protocol"], project["wind_calibration"])
    assert [row["month"] for row in calibrated] == ["2024-08", "2024-09", "2024-10", "2024-11"]
    assert trace[7]["calibration_months"] == ["2024-01", "2024-02", "2024-03", "2024-04", "2024-05", "2024-06"]
    changed = deepcopy(rows)
    for row in changed[6:]:
        row["actual_mwh"] += 1e12
    altered, _ = rolling_calibrate(changed, project["monthly_protocol"], project["wind_calibration"])
    assert altered[0]["quantiles_mwh"] == calibrated[0]["quantiles_mwh"]
    changed[0]["phase"] = "test"
    with pytest.raises(ValueError, match="sviluppo"):
        rolling_calibrate(changed, project["monthly_protocol"], project["wind_calibration"])


def test_degenerate_history_rejected() -> None:
    project = project_settings()
    rows = fixture_rows()[:6]
    rows[0]["quantiles_mwh"] = {q: 100. for q in rows[0]["quantiles_mwh"]}
    with pytest.raises(ValueError, match="nulla"):
        fit_scale(rows, project["monthly_protocol"]["comparison_quantile_levels"], project["wind_calibration"])


@pytest.mark.parametrize("missing_truth", [False, True])
def test_end_to_end_calibration_report_and_no_operational_promotion(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_truth: bool) -> None:
    import solarwindcast.wind_calibration as module

    project = project_settings()
    project["wind_calibration"].update(source_directory="source", output_directory="result")
    rows = fixture_rows()
    if missing_truth:
        rows[-1]["actual_mwh"] = None
    source = tmp_path / "source"
    source.mkdir()
    all_rows = deepcopy(rows)
    for row in rows:
        reference = deepcopy(row)
        reference["model"] = project["wind_calibration"]["reference"]
        all_rows.append(reference)
        annual = deepcopy(row)
        annual.update(model="same_month_previous_year", point_mwh=110., quantiles_mwh=None)
        all_rows.append(annual)
    path = source / "development_predictions.json"
    path.write_text(json.dumps(all_rows))
    (source / "manifest.json").write_text(json.dumps({"files_sha256": {path.name: sha256(path.read_bytes()).hexdigest()}}))
    source_digest = sha256(path.read_bytes()).hexdigest()
    monkeypatch.setattr(module, "check_frozen_protocol", lambda *args: {"settings_sha256": "synthetic"})
    result = run_calibration(project, tmp_path)
    assert result["evaluation_cases"] == (3 if missing_truth else 4)
    assert result["operational_promotion"] is False and result["new_inferences"] == 0
    metrics = result["scores"]["wind"]["development"]["models"]
    original = metrics[project["wind_calibration"]["candidate"]]
    calibrated = metrics[project["wind_calibration"]["candidate"] + "__calibrated"]
    assert calibrated["point_scores"] == original["point_scores"]
    assert calibrated["pinball_mwh"] < original["pinball_mwh"]
    assert sha256(path.read_bytes()).hexdigest() == source_digest
    assert f"Solo {result['evaluation_cases']} mesi" in (tmp_path / "result/presentazione.html").read_text(encoding="utf-8")
    predictions = json.loads((tmp_path / "result/predictions.json").read_text())
    assert len([row for row in predictions if row["model"].endswith("__calibrated")]) == 4
    for name, digest in json.loads((tmp_path / "result/manifest.json").read_text())["files_sha256"].items():
        assert sha256((tmp_path / "result" / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        run_calibration(project, tmp_path)
