"""Preview calendar-month evaluation folds and unit transforms without running forecasts."""

import argparse
import json
from hashlib import sha256
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from solarwindcast.dataset import (
    DatasetSpec,
    TimeSeriesDataset,
    validate_quantile_frame,
)
from solarwindcast.monthly_summary import monthly_energy


def monthly_quantiles_to_energy(power_quantiles: pd.Series, duration_hours: float) -> pd.Series:
    """Scale quantiles of ONE monthly mean by its known duration; never sum marginal quantiles."""
    validate_quantile_frame(power_quantiles.to_frame().T)
    if not np.isfinite(duration_hours) or duration_hours <= 0:
        raise ValueError("La durata del mese deve essere positiva e finita.")
    return power_quantiles * duration_hours


def load_monthly_targets(prepared: Path, timezone: str, wind_components: list[str]) -> dict[str, pd.DataFrame]:
    """Verify prepared observations and build solar/wind aggregates with strict component completeness."""
    manifest = json.loads((prepared / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Preparazione incompleta.")
    for name, digest in manifest["files_sha256"].items():
        path = (prepared / name).resolve()
        if not path.is_relative_to(prepared.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Hash o percorso della preparazione non valido.")
    metadata = json.loads((prepared / "quality.json").read_text(encoding="utf-8"))
    if (not wind_components or len(set(wind_components)) != len(wind_components)
            or not set(wind_components).issubset({"wind_onshore", "wind_offshore"})):
        raise ValueError("Componenti eoliche esplicite e univoche obbligatorie.")
    frames, frequency = {}, None
    for name in ("solar", *wind_components):
        details = metadata[name]
        if details["unit"] != "MW" or name + ".parquet" not in manifest["files_sha256"]:
            raise ValueError("Unità o provenienza della serie non valida.")
        if frequency is not None and details["frequency"] != frequency:
            raise ValueError("Frequenze non allineate.")
        frequency = details["frequency"]
        frame = pd.read_parquet(prepared / (name + ".parquet"))
        TimeSeriesDataset(frame, DatasetSpec(details["target"], frequency, (), (), (), details["provenance"])).validate()
        if frames and not frame.index.equals(next(iter(frames.values())).index):
            raise ValueError("Griglie non allineate: nessun riempimento.")
        frames[name] = frame.target
    wind = pd.concat([frames[name] for name in wind_components], axis=1).sum(axis=1, min_count=len(wind_components))
    results = {}
    for target, series in (("solar", frames["solar"]), ("wind", wind)):
        dataset = TimeSeriesDataset(series.to_frame("target"), DatasetSpec(target, frequency, (), (), (),
            "verified prepared observations; complete component sum only"))
        months = monthly_energy(dataset, timezone)
        hours = ((pd.to_datetime(months.end_exclusive_utc, utc=True) -
                  pd.to_datetime(months.start_utc, utc=True)) / pd.Timedelta(hours=1))
        months["duration_hours"] = hours
        months["mean_power_mw"] = months.energy_mwh / hours
        months.index = pd.PeriodIndex(months.month, freq="M", name="month")
        results[target] = months
    return results


def fold_preview(months: pd.DataFrame, start: str, end_exclusive: str,
                 draft: dict[str, object]) -> list[dict[str, object]]:
    """Describe contexts and gaps for each target month, exposing no future data to the context."""
    context, gap = draft["context_months"], draft["unavailable_recent_months"]
    minimum = draft["minimum_valid_context_months"]
    if (any(isinstance(value, bool) or not isinstance(value, int) for value in (context, gap, minimum))
            or context < 1 or gap < 0 or not 1 <= minimum <= context
            or draft["prediction_length_months"] != gap + 1):
        raise ValueError("Contesto e divario mensile non coerenti.")
    if not months.index.is_unique or not months.index.is_monotonic_increasing:
        raise ValueError("Mesi duplicati o non ordinati.")
    seasonal_lag = draft["baseline_seasonal_lag_months"]
    lookback = draft["residual_lookback_months"]
    calibration_minimum = draft["minimum_calibration_errors"]
    if (seasonal_lag < gap + 1 or lookback < calibration_minimum or calibration_minimum < 1
            or draft["issue_lead_hours"] <= 0):
        raise ValueError("Emissione o finestra di calibrazione non coerenti.")
    first, end = pd.Period(start[:7], freq="M"), pd.Period(end_exclusive[:7], freq="M")
    rows = []
    for target in pd.period_range(first, end - 1, freq="M"):
        cutoff = target - gap - 1
        context_months = pd.period_range(cutoff - context + 1, cutoff, freq="M")
        values = months.mean_power_mw.reindex(context_months)
        present = context_months.isin(months.index).all()
        complete = target in months.index and bool(months.loc[target, "complete"])
        valid = int(values.notna().sum())
        available = present and valid >= minimum
        target_start = pd.Timestamp(months.loc[target, "start_utc"]) if target in months.index else None
        issue = target_start - pd.Timedelta(hours=draft["issue_lead_hours"]) if target_start is not None else None
        pairs = []
        for month in pd.period_range(cutoff - lookback + 1, cutoff, freq="M"):
            previous = month - seasonal_lag
            if (month in months.index and previous in months.index
                    and pd.notna(months.loc[month, "mean_power_mw"])
                    and pd.notna(months.loc[previous, "mean_power_mw"])):
                pairs.append(str(month))
        rows.append({"target_month": str(target), "issue_utc": issue.isoformat() if issue is not None else None,
            "context_start_month": str(context_months[0]), "available_through_month": str(cutoff),
            "context_months": context, "context_valid_months": valid, "context_missing_months": context - valid,
            "context_within_observed_span": bool(present), "target_complete": complete,
            "forecast_months": [str(month) for month in pd.period_range(cutoff + 1, target, freq="M")],
            "scored_forecast_index": gap, "forecast_input_ready": bool(available),
            "eligible_calibration_pairs": len(pairs), "calibration_pair_months": pairs,
            "probabilistic_baseline_input_ready": len(pairs) >= calibration_minimum,
            "scorable_without_model_run": bool(available and complete)})
    return rows


def save_preview(config: dict[str, object], root: Path, output: Path) -> Path:
    """Publish an inactive draft or frozen protocol with fold counts, never model performance."""
    if output.exists():
        raise FileExistsError("Usare una nuova cartella: nessuna sovrascrittura.")
    draft = config["monthly_protocol"]
    approved = draft.get("approved") is True
    if draft["experiment_enabled"] is not False:
        raise ValueError("Questa anteprima non abilita esperimenti.")
    timezone = draft["calendar_timezone"] if approved else draft["preview_calendar_timezone"]
    components = draft["wind_components"] if approved else draft["preview_wind_components"]
    targets = load_monthly_targets(root / config["monthly_inspection"]["prepared_directory"],
                                   timezone, components)
    proposal = config["planning"]["step10"]["evaluation_proposal"]
    result = {"kind": "frozen_protocol_no_forecasts" if approved else "protocol_preview_no_forecasts",
              "settings": draft, "calendar_timezone": timezone, "wind_components": components, "targets": {}}
    result["source_prepared_manifest_sha256"] = sha256(
        (root / config["monthly_inspection"]["prepared_directory"] / "manifest.json").read_bytes()).hexdigest()
    result["evaluation_periods"] = {name: proposal[name] for name in (
        "development_start_utc", "test_start_utc", "test_end_exclusive_utc")}
    result["settings_sha256"] = sha256(json.dumps(draft, sort_keys=True, allow_nan=False).encode()).hexdigest()
    rows = []
    example = None
    for name, months in targets.items():
        phases = {}
        for phase, start, end in (("development", proposal["development_start_utc"], proposal["test_start_utc"]),
                                   ("test", proposal["test_start_utc"], proposal["test_end_exclusive_utc"])):
            folds = fold_preview(months, start, end, draft)
            ready = sum(row["scorable_without_model_run"] for row in folds)
            if phase == "test" and example is None and folds:
                example = folds[0]
            phases[phase] = {"folds": folds, "candidate_months": len(folds), "scorable_months": ready}
            target_label = {"solar": "Solare", "wind": "Eolico"}[name]
            phase_label = {"development": "Sviluppo", "test": "Test finale"}[phase]
            rows.append(f'<tr><td>{target_label}</td><td>{phase_label}</td><td>{len(folds)}</td><td>{ready}</td></tr>')
        result["targets"][name] = phases
    wind_label = " + ".join({"wind_onshore": "a terra", "wind_offshore": "in mare"}[name]
                            for name in components)
    title = "Protocollo mensile congelato" if approved else "Protocollo mensile da approvare"
    status_note = ("Scelte confermate. Step 10 concluso; gli esperimenti dello Step 11 sono ancora disabilitati."
                   if approved else "Queste due scelte restano da confermare. Gli esperimenti sono disabilitati.")
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SolarWindCast · {title}</title><style>body{{font:16px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}
main{{max-width:1000px;margin:auto;padding:28px 18px}}header{{background:#16313e;color:white;padding:30px;border-radius:18px}}section{{background:white;padding:24px;border-radius:14px;margin:22px 0}}
table{{border-collapse:collapse;width:100%}}td,th{{padding:10px;border-bottom:1px solid #dce5e9;text-align:left}}.note{{background:#fff0d7;border-left:4px solid #d98b12;padding:18px}}</style></head>
<body><main><header><p>SolarWindCast · Step 10</p><h1>Una previsione per il totale del mese</h1><p>{title} · Nessun modello eseguito</p></header>
<p class="note">Calendario {escape(timezone)} ed eolico {escape(wind_label)}. {status_note}</p>
<section><h2>Metodo</h2><p>Prevedere direttamente la potenza media mensile, poi moltiplicare mediana e quantili per le ore del mese obiettivo.
È una trasformazione di un unico valore mensile: non sommiamo quantili orari.</p>
<p>Contesto: {draft['context_months']} mesi. Emissione: {draft['issue_lead_hours']} ore prima dell'inizio del mese da prevedere.
Si omette il mese precedente ancora in corso e si prevedono {draft['prediction_length_months']} passi mensili, valutando soltanto l'ultimo.</p>
<p>Esempio: per {escape(example['target_month'])} si emette a {escape(example['issue_utc'])}, usando mesi fino a {escape(example['available_through_month'])}.</p></section>
<section><h2>Confronti</h2><p>Timestral {escape(', '.join(model['size'] for model in draft['models']))}, pesi già in cache, senza riaddestramento. Varianti solo target e calendario futuro noto.
Baseline: ultimo mese completo disponibile, stesso mese dell'anno precedente e media di mesi recenti completi, corrette per la durata del mese obiettivo.</p>
<p>Intervalli {escape(', '.join(str(int(level * 100)) + '%' for level in draft['interval_levels']))}, errore MAE/RMSE in MWh, pinball loss, copertura e ampiezza. Baseline probabilistica con errori rolling disponibili prima dell'emissione;
finestra di {draft['residual_lookback_months']} mesi, almeno {draft['minimum_calibration_errors']} coppie valide.
Nessuna calibrazione sul futuro. Nessun meteo non verificato.</p></section>
<section><h2>Disponibilità delle finestre</h2><p>Conta mesi osservati e contesti, non previsioni riuscite o accurate.</p><table><thead><tr><th>Target</th><th>Fase</th><th>Mesi candidati</th><th>Valutabili prima dei modelli</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<section><h2>Limiti dichiarati</h2><p>Dati revisionati del passato: confronto retrospettivo, non prova operativa. Il ritardo di prima pubblicazione non è ricostruito.
Pochi mesi di test limitano le conclusioni sugli intervalli. I NaN restano mancanti; il modello usa le proprie maschere dichiarate.
I confini dei mesi sono calendari veri: non vengono sostituiti da timestamp orari fittizi.</p><p>Dettagli, revisioni e decisioni nel protocollo Markdown e nella configurazione YAML.</p></section></main></body></html>'''
    output.mkdir(parents=True, exist_ok=False)
    filename = "protocol_snapshot.json" if approved else "protocol_preview.json"
    files = {"presentazione.html": html, filename: json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)}
    hashes = {}
    for name, text in files.items():
        (output / name).write_text(text, encoding="utf-8")
        hashes[name] = sha256((output / name).read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({"files_sha256": hashes}, indent=2), encoding="utf-8")
    return output / "presentazione.html"


def main() -> None:
    """Create only an inactive protocol preview from local data and YAML candidates."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    print(save_preview(config, args.config.resolve().parent.parent, args.output).resolve())


if __name__ == "__main__":
    main()
