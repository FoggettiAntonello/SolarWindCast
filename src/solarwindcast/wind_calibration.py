"""Causal single-scale wind uncertainty calibration on saved development forecasts only."""

import argparse
import json
import math
from copy import deepcopy
from hashlib import sha256
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from solarwindcast.dataset import validate_quantile_frame
from solarwindcast.monthly_experiment import (
    _json_safe,
    check_frozen_protocol,
    score_predictions,
)
from solarwindcast.monthly_improvement import verify_manifest
from solarwindcast.monthly_results_html import forecast_chart
from solarwindcast.real_data_html import _fmt


def fit_scale(history: list[dict[str, object]], levels: list[float], settings: dict[str, object]) -> float:
    """Minimize normalized pinball plus fixed quadratic shrinkage toward identity, with one scalar."""
    lo, hi, penalty = settings["scale_lower"], settings["scale_upper"], settings["identity_penalty"]
    if (not 0 < lo <= 1 <= hi or not math.isfinite(penalty) or penalty <= 0
            or not isinstance(settings["bisection_steps"], int) or settings["bisection_steps"] < 1):
        raise ValueError("Limiti scala, regolarizzazione o iterazioni non validi.")
    if len(history) < settings["minimum_past_errors"]:
        raise ValueError("Errori storici insufficienti.")
    offsets, residuals = [], []
    for row in history:
        quantiles = {float(q): float(value) for q, value in row["quantiles_mwh"].items()}
        validate_quantile_frame(pd.DataFrame([quantiles]).reindex(sorted(quantiles), axis=1))
        if not all(math.isfinite(value) for value in quantiles.values()) or not set(levels).issubset(quantiles):
            raise ValueError("Quantili storici mancanti o non finiti.")
        median = quantiles[.5]
        width = quantiles[max(levels)] - quantiles[min(levels)]
        if not math.isfinite(width) or width <= 0 or not math.isfinite(row["actual_mwh"]):
            raise ValueError("Ampiezza storica nulla o osservazione non finita.")
        offsets.append([(quantiles[level] - median) / width for level in levels])
        residuals.append((row["actual_mwh"] - median) / width)
    distance, actual, probabilities = np.asarray(offsets), np.asarray(residuals)[:, None], np.asarray(levels)[None]

    def derivative(scale: float) -> float:
        """A valid subgradient of the convex one-dimensional objective."""
        error = actual - scale * distance
        return float((-(probabilities - (error < 0)) * distance).mean() + 2 * penalty * (scale - 1))

    if derivative(lo) >= 0:
        return float(lo)
    if derivative(hi) <= 0:
        return float(hi)
    for _ in range(settings["bisection_steps"]):
        middle = (lo + hi) / 2
        if derivative(middle) > 0:
            hi = middle
        else:
            lo = middle
    return float((lo + hi) / 2)


def apply_scale(row: dict[str, object], scale: float) -> dict[str, object]:
    """Scale every quantile around the unchanged median; positive scale preserves ordering."""
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("La scala deve essere positiva e finita.")
    result = deepcopy(row)
    quantiles = {float(q): float(value) for q, value in row["quantiles_mwh"].items()}
    validate_quantile_frame(pd.DataFrame([quantiles]).reindex(sorted(quantiles), axis=1))
    if not all(math.isfinite(value) for value in quantiles.values()):
        raise ValueError("Quantili non finiti.")
    if row["point_mwh"] != quantiles[.5]:
        raise ValueError("La previsione centrale deve essere la mediana.")
    median = quantiles[.5]
    result["quantiles_mwh"] = {str(q): median + scale * (value - median) for q, value in quantiles.items()}
    result["model"] = row["model"] + "__calibrated"
    return result


def rolling_calibrate(rows: list[dict[str, object]], protocol: dict[str, object],
                       settings: dict[str, object]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Fit at each origin using only completed earlier months; log every cutoff and warmup exclusion."""
    if (settings["minimum_past_errors"] < 1 or settings["lookback_months"] < settings["minimum_past_errors"]
            or any(row["phase"] != "development" or row["target"] != settings["target"]
                   or row["model"] != settings["candidate"] for row in rows)):
        raise ValueError("Richiesti solo forecast di sviluppo del candidato configurato.")
    months = [row["month"] for row in rows]
    if len(months) != len(set(months)):
        raise ValueError("Origini duplicate.")
    calibrated, trace = [], []
    for row in sorted(rows, key=lambda item: item["month"]):
        target = pd.Period(row["month"], freq="M")
        cutoff = target - protocol["unavailable_recent_months"] - 1
        first = cutoff - settings["lookback_months"] + 1
        history = [past for past in rows if first <= pd.Period(past["month"], freq="M") <= cutoff
            and past["actual_mwh"] is not None and past["quantiles_mwh"] is not None]
        item = {"month": row["month"], "available_through_month": str(cutoff),
            "calibration_months": sorted(past["month"] for past in history), "past_errors": len(history)}
        if len(history) < settings["minimum_past_errors"]:
            trace.append({**item, "status": "warmup_excluded", "scale": None})
            continue
        scale = fit_scale(history, protocol["comparison_quantile_levels"], settings)
        prediction = apply_scale(row, scale)
        prediction["metadata"]["calibration"] = {**item, "scale": scale}
        calibrated.append(prediction)
        trace.append({**item, "status": "calibrated", "scale": scale})
    return calibrated, trace


def run_calibration(config: dict[str, object], root: Path) -> dict[str, object]:
    """Run one configured method on development only, with no model loading or later test evaluation."""
    settings = config["wind_calibration"]
    if (settings["authorized"] is not True or settings["comparison_phase"] != "development"
            or settings["keep_median"] is not True or settings["new_inference_budget"] != 0
            or settings["evaluate_old_test"] is not False or settings["alternate_methods_authorized"] is not False):
        raise RuntimeError("Questa esecuzione consente solo la calibrazione controllata dello sviluppo.")
    frozen = check_frozen_protocol(config, root)
    source, output = root / settings["source_directory"], root / settings["output_directory"]
    verify_manifest(source)
    if output.exists():
        raise FileExistsError("Usare una nuova cartella, senza sovrascrivere esperimenti.")
    output.mkdir(parents=True, exist_ok=False)
    # Persist choices before reading forecast errors or fitting any scale.
    snapshot = {"settings": settings, "protocol": config["monthly_protocol"],
        "source_manifest_sha256": sha256((source / "manifest.json").read_bytes()).hexdigest(),
        "original_protocol_sha256": frozen["settings_sha256"], "method_selected_after_prior_screen": True,
        "independent_test": False}
    snapshot_path = output / "settings_before_fit.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    snapshot_hash = sha256(snapshot_path.read_bytes()).hexdigest()
    rows = json.loads((source / "development_predictions.json").read_text(encoding="utf-8"))
    candidate = [row for row in rows if row["target"] == settings["target"] and row["model"] == settings["candidate"]]
    calibrated, trace = rolling_calibrate(candidate, config["monthly_protocol"], settings)
    common = {row["month"] for row in calibrated}
    original_rows = [row for row in rows if row["target"] == settings["target"] and row["month"] in common
        and (row["model"] in (settings["candidate"], settings["reference"]) or not row["model"].startswith("timestral_"))]
    comparison = original_rows + calibrated
    scores = score_predictions(comparison, config["monthly_protocol"]) if common else {}
    evaluation_months = ([stamp[:7] for stamp in scores[settings["target"]]["development"]["point_common_months"]]
        if scores else [])
    sufficient = len(evaluation_months) >= settings["minimum_evaluation_months"]
    result = {"kind": "exploratory_causal_wind_calibration", "status": "complete", "settings": settings,
        "scored_months": evaluation_months, "evaluation_cases": len(evaluation_months), "required_cases": settings["minimum_evaluation_months"],
        "sufficient_evaluation_months": sufficient, "scores": _json_safe(scores), "trace": trace,
        "settings_before_fit_sha256": snapshot_hash, "new_inferences": 0, "timestral_weight_updates": 0,
        "median_changed": False, "independent_test": False, "operational_promotion": False,
        "decision": "insufficient_evaluation_do_not_promote" if not sufficient else "exploratory_only_requires_new_validation"}
    extension_path = source / "history_extension.json"
    if extension_path.exists():
        result["history_extension"] = json.loads(extension_path.read_text(encoding="utf-8"))
    previous_directory = settings.get("previous_comparison_directory")
    if previous_directory:
        previous_folder = root / previous_directory
        verify_manifest(previous_folder)
        earlier = json.loads((previous_folder / "predictions.json").read_text(encoding="utf-8"))
        earlier = [row for row in earlier if row["model"] == settings["candidate"] + "__calibrated" and row["month"] in evaluation_months]
        shared = {row["month"] for row in earlier}
        matched = [deepcopy(row) for row in comparison if row["month"] in shared]
        for row in earlier:
            item = deepcopy(row)
            item["model"] += "__previous_history"
            matched.append(item)
        result["matched_previous_window_scores"] = _json_safe(score_predictions(matched, config["monthly_protocol"])) if shared else {}
    if sha256(snapshot_path.read_bytes()).hexdigest() != snapshot_hash:
        raise ValueError("Impostazioni cambiate dopo il fit.")
    (output / "predictions.json").write_text(json.dumps(_json_safe(comparison), indent=2, allow_nan=False), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(_json_safe(result), indent=2, allow_nan=False), encoding="utf-8")
    (output / "presentazione.html").write_text(render_calibration(result, comparison), encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    return result


def render_calibration(result: dict[str, object], rows: list[dict[str, object]]) -> str:
    """Report the actual common sample, warmup and uncertainty changes without promising reliability."""
    settings = result["settings"]
    labels = {settings["candidate"]: "28M/calendario · 12 mesi · originale",
        settings["candidate"] + "__calibrated": "28M/calendario · 12 mesi · calibrato",
        settings["reference"]: "28M/calendario · 24 mesi · riferimento"}
    labels[settings["candidate"] + "__calibrated__previous_history"] = "Calibrazione precedente · storico ridotto"
    metric_rows, charts = [], []
    metrics = result["scores"].get(settings["target"], {}).get("development", {}).get("models", {})
    for name, item in metrics.items():
        for level, interval in item.get("intervals", {}).items():
            metric_rows.append(f'<tr><td>{escape(labels.get(name, name))}</td><td>{item["point_cases"]}</td>'
                f'<td>{_fmt(item["point_scores"]["mae_mwh"])}</td><td>{_fmt(item["pinball_mwh"])}</td><td>{float(level):.0%}</td>'
                f'<td>{_fmt(interval["coverage"]*100)}%</td><td>{_fmt(interval["mean_width_mwh"])}</td></tr>')
        if name in labels:
            subset = [row for row in rows if row["model"] == name]
            charts.append(f'<h3>{escape(labels[name])}</h3><div class="chart">{forecast_chart(subset, [float(level) for level in item["intervals"]])}</div>')
    trace_rows = ''.join(f'<tr><td>{entry["month"]}</td><td>{entry["available_through_month"]}</td><td>{entry["past_errors"]}</td>'
        f'<td>{_fmt(entry["scale"],3)}</td><td>{"escluso: storico insufficiente" if entry["status"] == "warmup_excluded" else "calibrato"}</td></tr>' for entry in result["trace"])
    extension_note = (f"Per recuperare lo storico sono state eseguite {result['history_extension']['new_inferences']} inferenze del medesimo candidato; nessun dato o peso scaricato. "
        if result.get("history_extension") else "")
    matched_rows = []
    for item_name, item in result.get("matched_previous_window_scores", {}).get(settings["target"], {}).get("development", {}).get("models", {}).items():
        if "pinball_mwh" in item:
            matched_rows.append(f'<tr><td>{escape(labels.get(item_name,item_name))}</td><td>{item["quantile_cases"]}</td>'
                f'<td>{_fmt(item["pinball_mwh"])}</td><td>{_fmt(item["intervals"]["0.8"]["coverage"]*100)}%</td>'
                f'<td>{_fmt(item["intervals"]["0.9"]["coverage"]*100)}%</td></tr>')
    matched_section = (f'<section><h2>Controllo sui mesi già valutati prima</h2><p>Confronto sullo stesso sottoinsieme comune, per distinguere il recupero dello storico dal cambiamento dei mesi valutati. Non è un test indipendente.</p>'
        f'<div class="scroll"><table><thead><tr><th>Modello</th><th>Mesi</th><th>Pinball MWh</th><th>Copertura80</th><th>Copertura90</th></tr></thead><tbody>{"".join(matched_rows)}</tbody></table></div></section>') if matched_rows else ""
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Calibrazione eolica controllata</title><style>body{{font:15px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}main{{max-width:1200px;margin:auto;padding:24px}}header,section{{padding:25px;border-radius:16px;margin:20px 0;background:white;overflow-wrap:anywhere}}header{{background:#16313e;color:white}}.scroll,.chart{{overflow:auto}}table{{width:100%;min-width:900px;border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}svg{{width:100%;min-width:700px}}.note{{padding:18px;background:#fff0d7}}</style></head><body><main>
<header><h1>Calibrare l'incertezza senza cambiare la previsione centrale</h1><p>Eolico terra + mare · Timestral 28M/calendario · Esperimento esplorativo</p></header>
<p class="note">Solo {result['evaluation_cases']} mesi valutabili dopo il warm-up; requisito prudenziale fissato prima: {result['required_cases']}. Nessuna promozione operativa. {extension_note}Zero nuove inferenze durante il fit e nessun peso Timestral aggiornato.</p>
<section><h2>Confronto sugli stessi mesi</h2><p>{escape(', '.join(result['scored_months'])) or 'Nessun mese valutabile'}. I punteggi non sono confrontabili direttamente con quelli precedenti su undici mesi.</p>
<div class="scroll"><table><thead><tr><th>Modello</th><th>Mesi</th><th>MAE MWh</th><th>Pinball MWh</th><th>Livello nominale</th><th>Copertura osservata</th><th>Ampiezza media MWh</th></tr></thead><tbody>{''.join(metric_rows)}</tbody></table></div>
<p>La calibrazione modifica soltanto le distanze dei quantili dalla mediana, con un unico fattore positivo: MAE e RMSE della previsione centrale devono restare identici.</p>
{''.join(charts)}</section>{matched_section}<section><h2>Quali errori erano davvero disponibili?</h2><div class="scroll"><table><thead><tr><th>Mese previsto</th><th>Ultima etichetta utilizzabile</th><th>Errori passati</th><th>Fattore</th><th>Stato</th></tr></thead><tbody>{trace_rows}</tbody></table></div>
<p>Servono almeno {settings['minimum_past_errors']} errori già osservati. Per prevedere luglio, giugno è ancora in corso e non può entrare nel fit. Le origini escluse dal warm-up non vengono sostituite con previsioni calibrate sul loro stesso risultato.</p></section>
<section><h2>Metodo e limiti</h2><p>Un solo metodo: minimizzazione della pinball normalizzata per l'ampiezza 90% storica, con penalità quadratica {settings['identity_penalty']} verso fattore 1 e limiti {settings['scale_lower']}–{settings['scale_upper']}. Nessuna ricerca di iperparametri. Ordinamento dei quantili e mediana preservati, nessun clipping dei valori.</p>
<p>Metodo scelto dopo aver visto lo screening precedente: resta esplorativo anche con fit temporalmente corretto. Pochissimi mesi non garantiscono copertura nominale. Non è fine tuning della rete e non sono risultati del vecchio test.</p></section>
<section><h2>Fasi successive consigliate</h2><ol><li>Ampliare lo sviluppo con storico coerente e verificato: più errori passati e stagioni per valutare la calibrazione.</li><li>Verificare capacità installata e disponibilità delle previsioni meteo mensili al cutoff: possono spiegare variazioni che il calendario da solo non descrive.</li><li>Congelare una soluzione e registrare nuove previsioni prima dei risultati: verifica indipendente dell'utilità reale.</li><li>Solo dopo rivalutare fine tuning o taglie maggiori, se i dati lo giustificano.</li></ol><p>Nessuna di queste fasi è stata avviata automaticamente.</p></section></main></body></html>'''


def main() -> None:
    """Calibrate saved development quantiles only, under the explicit wind calibration configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    run_calibration(config, args.config.resolve().parent.parent)
    print(config["wind_calibration"]["output_directory"] + "/presentazione.html")


if __name__ == "__main__":
    main()
