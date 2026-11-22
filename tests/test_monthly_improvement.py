"""Synthetic promotion gates, cache integrity and no-heldout execution when the screen fails."""

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest
import yaml

from solarwindcast.monthly_experiment import score_predictions
from solarwindcast.monthly_forecasting import MonthlyPrediction, context_periods
from solarwindcast.monthly_improvement import (
    assess_candidates,
    checked_cached_row,
    run_screen,
)


def project_defaults() -> dict[str, object]:
    """Use current declared fields with test-only overrides, never infer real scores."""
    return yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/project.yaml").read_text(encoding="utf-8"))


def candidates(wide: bool = False) -> list[dict[str, object]]:
    """Eleven synthetic months with a better candidate, optionally made excessively uncertain."""
    rows = []
    for month in pd.period_range("2023-12", periods=11, freq="M"):
        for model, error in (("same_month_previous_year", 15.),
            ("timestral_5M_target_only__ctx24", 10.), ("timestral_5M_target_only__ctx12", 4.)):
            width = 100 if wide and model.endswith("ctx12") else 20
            quantiles = None if not model.startswith("timestral_") else {
                "0.05": 100 + error - width, "0.1": 100 + error - width * .8,
                "0.5": 100 + error, "0.9": 100 + error + width * .8, "0.95": 100 + error + width}
            rows.append({"model": model, "target": "solar", "phase": "development", "month": str(month),
                "target_start_utc": month.start_time.tz_localize("UTC").isoformat(),
                "point_mwh": 100 + error, "actual_mwh": 100., "quantiles_mwh": quantiles})
    return rows


def test_promote_only_when_all_declared_gates_pass() -> None:
    project = project_defaults()
    rows = candidates()
    decision = assess_candidates(rows, score_predictions(rows, project["monthly_protocol"]),
        project["timestral_improvement"]["proposal"], 24)["solar"]
    assert decision["selected"] == "timestral_5M_target_only__ctx12"
    assert decision["assessments"][decision["selected"]]["paired_cases"] == 11
    assert decision["assessments"][decision["selected"]]["paired_wins"] == 11
    assert not decision["assessments"][decision["original_reference"]]["passed"]


def test_better_mae_does_not_override_interval_gates_or_allow_test_selection() -> None:
    project = project_defaults()
    rows = candidates(wide=True)
    decision = assess_candidates(rows, score_predictions(rows, project["monthly_protocol"]),
        project["timestral_improvement"]["proposal"], 24)["solar"]
    assert decision["selected"] is None
    gates = decision["assessments"]["timestral_5M_target_only__ctx12"]["gates"]
    assert gates["mae_vs_original"] and not gates["width_0.8"]
    rows[-1]["phase"] = "test"
    with pytest.raises(ValueError, match="test"):
        assess_candidates(rows, {}, project["timestral_improvement"]["proposal"], 24)


def monthly_fixture() -> pd.DataFrame:
    """Ten complete UTC months with constant mean power and actual calendar hours."""
    index = pd.period_range("2024-01", periods=10, freq="M", name="month")
    hours = [(period.end_time + pd.Timedelta(nanoseconds=1) - period.start_time) / pd.Timedelta(hours=1) for period in index]
    return pd.DataFrame({"mean_power_mw": 100., "duration_hours": hours,
        "energy_mwh": [100 * duration for duration in hours], "complete": True,
        "start_utc": [period.start_time.tz_localize("UTC").isoformat() for period in index]}, index=index)


def test_cached_context_and_truth_are_checked_without_mutating_original() -> None:
    months, cfg = monthly_fixture(), {"context_months": 3, "unavailable_recent_months": 1}
    month = pd.Period("2024-06", freq="M")
    row = {"target": "solar", "phase": "development", "month": str(month), "model": "timestral_5M_target_only",
        "actual_mwh": months.loc[month, "energy_mwh"],
        "metadata": {"context_months": [str(label) for label in context_periods(month, cfg)]}}
    result = checked_cached_row([row], "solar", str(month), row["model"], "development", months, cfg)
    assert result["model"].endswith("__ctx3") and not row["model"].endswith("__ctx3")
    with pytest.raises(ValueError, match="duplicata"):
        checked_cached_row([row, row], "solar", str(month), row["model"], "development", months, cfg)
    row["metadata"]["context_months"] = []
    with pytest.raises(ValueError, match="Contesto"):
        checked_cached_row([row], "solar", str(month), row["model"], "development", months, cfg)


def write_bundle(folder: Path, files: dict[str, object]) -> None:
    """Write a tiny immutable synthetic artifact bundle with matching hashes."""
    folder.mkdir(parents=True)
    for name, value in files.items():
        (folder / name).write_text(json.dumps(value), encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in folder.iterdir()}
    (folder / "manifest.json").write_text(json.dumps({"files_sha256": hashes}), encoding="utf-8")


@pytest.mark.parametrize("promote", [False, True])
def test_screen_preserves_selection_before_any_conditional_heldout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, promote: bool) -> None:
    import solarwindcast.monthly_improvement as module

    project = deepcopy(project_defaults())
    cfg = project["monthly_protocol"]
    cfg.update(context_months=3, minimum_valid_context_months=2, baseline_seasonal_lag_months=2,
        baseline_recent_months=2, residual_lookback_months=3, minimum_calibration_errors=2)
    cfg["models"] = cfg["models"][:1]
    months = monthly_fixture()
    common = ["2024-05", "2024-06", "2024-07", "2024-08"]
    proposal = project["timestral_improvement"]["proposal"]
    proposal.update(targets=["solar"], model_sizes=["5M"], context_months=[2, 3], variants=["target_only"],
        old_forecasts_directory="old", output_protocol_directory="proposal")
    if promote:
        # A perfect constant-data baseline cannot be improved by 5%; disable that gate only in this fixture.
        proposal["require_improvement_over_best_deterministic_baseline"] = False
    project["timestral_improvement"]["results_directory"] = "out"
    cached = []
    for month in common + ["2024-09", "2024-10"]:
        label = pd.Period(month, freq="M")
        value = float(months.loc[label, "energy_mwh"])
        cached.append({"target": "solar", "phase": "development" if month in common else "test", "month": month,
            "model": "timestral_5M_target_only", "actual_mwh": value, "point_mwh": value + 10,
            "target_start_utc": months.loc[label, "start_utc"],
            "quantiles_mwh": {"0.05": value - 30, "0.1": value - 20, "0.5": value + 10, "0.9": value + 20, "0.95": value + 30},
            "metadata": {"context_months": [str(period) for period in context_periods(label, cfg)]}})
    write_bundle(tmp_path / "old", {"predictions.json": {"forecasts": cached},
        "results.json": {"protocol_sha256": "synthetic", "models": {"5M": {"backend_mode": "synthetic"}}}})
    approved = {"proposal": proposal, "protocol_sha256": "synthetic", "availability": {"solar": {"common_origins": common}},
        "source_previous_manifest_sha256": sha256((tmp_path / "old/manifest.json").read_bytes()).hexdigest(),
        "new_development_inferences": 4, "maximum_new_exploratory_inferences": 2}
    write_bundle(tmp_path / "proposal", {"protocol_proposal.json": approved})
    frozen = {"settings_sha256": "synthetic", "evaluation_periods": {"development_start_utc": "2024-01-01T00:00Z",
        "test_start_utc": "2024-09-01T00:00Z", "test_end_exclusive_utc": "2024-11-01T00:00Z"}}
    monkeypatch.setattr(module, "check_frozen_protocol", lambda *args: frozen)
    monkeypatch.setattr(module, "load_monthly_targets", lambda *args: {"solar": months})

    class BadModel:
        """A deliberately bad synthetic candidate that must never cause test execution."""

        def __init__(self, settings: dict[str, object], specification: dict[str, object]) -> None:
            self.provenance = {"backend_mode": "synthetic"}

        def predict(self, values: pd.DataFrame, month: pd.Period, variant: str) -> MonthlyPrediction:
            if month >= pd.Period("2024-09", freq="M"):
                assert promote
                saved = json.loads((tmp_path / "out/selection_before_test.json").read_text())
                assert saved["solar"]["selected"] == "timestral_5M_target_only__ctx2"
            if promote:
                value = float(100 * values.loc[month, "duration_hours"])
                return MonthlyPrediction("timestral_5M_target_only", str(month), value,
                    pd.Series({.05: value - 20, .1: value - 10, .5: value, .9: value + 10, .95: value + 20}), {})
            quantiles = pd.Series({.05: 900000., .1: 950000., .5: 1000000., .9: 1050000., .95: 1100000.})
            return MonthlyPrediction("timestral_5M_target_only", str(month), 1000000., quantiles, {})

    result = run_screen(project, tmp_path, BadModel)
    assert result["kind"] == "synthetic_screen"
    assert result["new_inference_calls"] == {"development": 4, "test": 2 if promote else 0}
    assert result["decisions"]["solar"]["selected"] == ("timestral_5M_target_only__ctx2" if promote else None)
    assert bool(result["exploratory_scores"]) == promote
    assert sha256((tmp_path / "out/selection_before_test.json").read_bytes()).hexdigest() == result["selection_before_test_sha256"]
    assert ("Candidato promosso" if promote else "Nessun candidato") in (tmp_path / "out/presentazione.html").read_text(encoding="utf-8")
    for name, digest in json.loads((tmp_path / "out/manifest.json").read_text())["files_sha256"].items():
        assert sha256((tmp_path / "out" / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        run_screen(project, tmp_path, BadModel)
