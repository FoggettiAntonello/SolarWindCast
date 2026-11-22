"""Reproducible synthetic Step 8 run from a labelled profile in the unique YAML."""

import argparse
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from solarwindcast.backtest import (
    BacktestConfig,
    BacktestResult,
    build_models,
    run_backtest,
)
from solarwindcast.dataset import TimeSeriesDataset, fixed_step
from solarwindcast.entsoe_csv import utc_timestamp
from solarwindcast.features import (
    FeatureConfig,
    FeatureResult,
    assemble_features,
    bindings_from_project_config,
)
from solarwindcast.synthetic import SyntheticConfig, generate
from solarwindcast.weather import UNITS, Location, WeatherRequest, parse_response


def demonstration_project(project: dict[str, object], profile: str) -> dict[str, object]:
    """Merge only an explicitly labelled demonstration, leaving operational choices unchanged."""
    try:
        demonstration = project["demonstrations"][profile]
        if demonstration["purpose"] != "synthetic_validation_only":
            raise ValueError("Profilo non dichiarato come sola verifica sintetica.")
        overrides = demonstration["overrides"]
        if not isinstance(overrides, dict):
            raise TypeError("Il profilo deve contenere overrides espliciti.")
    except (KeyError, TypeError) as exc:
        raise ValueError("Profilo dimostrativo assente o incompleto.") from exc
    result = deepcopy(project)
    result.pop("demonstrations")

    def merge(base: dict[str, object], updates: dict[str, object]) -> None:
        """Apply nested profile values without mutating the source configuration."""
        for key, value in updates.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                merge(base[key], value)
            else:
                base[key] = deepcopy(value)

    merge(result, overrides)
    if result["execution"]["real_data_enabled"] is not False:
        raise ValueError("La dimostrazione non deve abilitare dati reali.")
    if result["models"]["timestral"]["local_files_only"] is not True:
        raise ValueError("La dimostrazione usa solo pesi già in cache.")
    return result


def synthetic_feature_builder(project: dict[str, object]) -> Callable[[TimeSeriesDataset, str], FeatureResult]:
    """Build date-only calendar and synthetic past weather afresh at each origin."""
    feature_config = FeatureConfig.from_project_config(project)
    weather = project["synthetic_weather"]
    variable = weather["variable"]
    reference = utc_timestamp(project["synthetic"]["start_utc"])
    period = weather["period_steps"]
    if not isinstance(period, (int, float)) or not np.isfinite(period) or period <= 0:
        raise ValueError("Il periodo del meteo sintetico deve essere positivo.")
    if fixed_step(project["data"]["frequency"]) != pd.Timedelta(hours=1):
        raise ValueError("Il solo profilo meteo dimostrativo richiede dati orari.")

    def build(target: TimeSeriesDataset, origin: str) -> FeatureResult:
        """The fake weather depends on dates and profile parameters, never future targets."""
        index = target.frame.index
        steps = np.asarray((index - reference) / fixed_step(target.spec.frequency), dtype=float)
        values = weather["baseline"] + weather["amplitude"] * np.sin(2 * np.pi * steps / period)
        request = WeatherRequest("reanalysis", Location(**weather["location"]), index[0].isoformat(),
            (index[-1] + pd.Timedelta(hours=1)).isoformat(), "synthetic_fixture", (variable,))
        response = {"utc_offset_seconds": 0, "hourly_units": {variable: UNITS[variable]},
                    "hourly": {"time": index.strftime("%Y-%m-%dT%H:%M").tolist(), variable: values.tolist()}}
        source = parse_response(response, request, {"provenance": "synthetic dates-only weather; no API request"})
        bindings = bindings_from_project_config(project, {weather["source_name"]: source})
        return assemble_features(target, feature_config, bindings, origin)

    return build


def run_demonstration(project: dict[str, object], profile: str, baselines_only: bool = False) -> BacktestResult:
    """Run the selected synthetic profile without enabling operational settings or network."""
    effective = demonstration_project(project, profile)
    if baselines_only:
        effective['models']['timestral']['enabled'] = False
    synthetic = SyntheticConfig.from_project_config(effective)
    dataset = generate(synthetic)
    config = BacktestConfig.from_project_config(effective)
    result = run_backtest(dataset, config, build_models(effective), synthetic_feature_builder(effective))
    result.metadata.update(purpose="synthetic_validation_only", demonstration_profile=profile,
                           baselines_only=baselines_only,
                           synthetic_parameters=asdict(synthetic),
                           feature_configuration=deepcopy(effective["features"]),
                           synthetic_weather_parameters=deepcopy(effective["synthetic_weather"]))
    return result


def main() -> None:
    """CLI: require the YAML profile and a new output directory explicitly."""
    parser = argparse.ArgumentParser(description="Backtest sintetico, senza download o dati reali")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baselines-only", action="store_true", help="Demo senza pesi, token o richieste di rete")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("La directory di output esiste già: nessuna sovrascrittura.")
    project = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    result = run_demonstration(project, args.profile, args.baselines_only)
    result.save(args.output)
    print(result.summary.loc[result.summary.metric.isin(["mae_mw", "pinball_loss_mw"])].to_string(index=False))
    print(f"Risultati sintetici salvati in: {args.output.resolve()}")


if __name__ == "__main__":
    main()
