"""Execute a predeclared zero-shot context screen; promote only before exploratory test evaluation."""

import argparse
import json
import math
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from hashlib import sha256
from html import escape
from pathlib import Path

import pandas as pd
import yaml

from solarwindcast.monthly_experiment import (
    _json_safe,
    check_frozen_protocol,
    score_predictions,
)
from solarwindcast.monthly_forecasting import (
    MonthlyTimestral,
    baseline_predictions,
    context_periods,
)
from solarwindcast.monthly_protocol import fold_preview, load_monthly_targets
from solarwindcast.monthly_results_html import forecast_chart, model_label
from solarwindcast.real_data_html import _fmt


def verify_manifest(folder: Path) -> dict[str, object]:
    """Require every recorded artifact to match its digest and stay inside its directory."""
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for name, digest in manifest["files_sha256"].items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Manifest manomesso o percorso non valido.")
    return manifest


def candidate_label(name: str) -> str:
    """Show size, covariate variant and context separately in the report."""
    if "__ctx" not in name:
        return model_label(name)
    base, context = name.rsplit("__ctx", 1)
    return model_label(base) + f" · {context} mesi"


def gate_label(name: str) -> str:
    """Translate fixed decision gates without hiding which rule rejected the candidate."""
    labels = {"mae_vs_original": "MAE vs originale", "mae_vs_baseline": "MAE vs baseline",
        "paired_wins": "numero di vittorie", "rmse": "RMSE", "pinball": "pinball"}
    if name.startswith("coverage_"):
        return f"copertura {float(name.split('_')[1]):.0%}"
    if name.startswith("width_"):
        return f"ampiezza {float(name.split('_')[1]):.0%}"
    return labels.get(name, name)


def assess_candidates(rows: list[dict[str, object]], scores: dict[str, object],
                       proposal: dict[str, object], original_context: int) -> dict[str, object]:
    """Apply all fixed gates on identical development months, never use held-out performance."""
    if any(row["phase"] != "development" for row in rows):
        raise ValueError("La selezione non può usare righe del test.")
    decisions = {}
    for target, phases in scores.items():
        metrics = phases["development"]["models"]
        originals = [name for name in metrics if name.startswith("timestral_") and name.endswith(f"__ctx{original_context}")]
        deterministic = [name for name in metrics if not name.startswith("timestral_")]
        reference = min(originals, key=lambda name: metrics[name]["point_scores"]["mae_mwh"])
        baseline = min(deterministic, key=lambda name: metrics[name]["point_scores"]["mae_mwh"])
        original, simple = metrics[reference], metrics[baseline]
        lookup = {(row["model"], row["month"]): row for row in rows if row["target"] == target}
        common = {stamp[:7] for stamp in phases["development"]["point_common_months"]}
        assessments = {}
        for name, candidate in metrics.items():
            if not name.startswith("timestral_"):
                continue
            mae = candidate["point_scores"]["mae_mwh"]
            wins = sum(abs(lookup[name, month]["point_mwh"] - lookup[name, month]["actual_mwh"]) <
                abs(lookup[reference, month]["point_mwh"] - lookup[reference, month]["actual_mwh"]) for month in common)
            gates = {
                "mae_vs_original": original["point_scores"]["mae_mwh"] > 0 and mae <= original["point_scores"]["mae_mwh"] * (1 - proposal["minimum_relative_mae_improvement"]),
                "mae_vs_baseline": (not proposal["require_improvement_over_best_deterministic_baseline"] or
                    (simple["point_scores"]["mae_mwh"] > 0 and mae <= simple["point_scores"]["mae_mwh"] * (1 - proposal["minimum_relative_mae_improvement"]))),
                "paired_wins": wins >= math.ceil(len(common) * proposal["minimum_paired_win_fraction"]),
                "rmse": not proposal["require_rmse_not_worse"] or candidate["point_scores"]["rmse_mwh"] <= original["point_scores"]["rmse_mwh"],
                "pinball": not proposal["require_pinball_not_worse"] or candidate["pinball_mwh"] <= original["pinball_mwh"],
            }
            for level, interval in original["intervals"].items():
                current = candidate["intervals"][level]
                gates["coverage_" + level] = (not proposal["require_coverage_not_worse"] or current["coverage"] >= interval["coverage"])
                gates["width_" + level] = current["mean_width_mwh"] <= interval["mean_width_mwh"] * proposal["maximum_width_ratio"]
            assessments[name] = {"gates": gates, "passed": all(gates.values()), "paired_wins": wins,
                "paired_cases": len(common), "relative_mae_improvement_vs_original":
                    1 - mae / original["point_scores"]["mae_mwh"] if original["point_scores"]["mae_mwh"] else None,
                "relative_mae_improvement_vs_baseline":
                    1 - mae / simple["point_scores"]["mae_mwh"] if simple["point_scores"]["mae_mwh"] else None}
        eligible = [name for name, assessment in assessments.items() if assessment["passed"]]

        def order(name: str, metric_values: dict[str, object] = metrics) -> tuple:
            """Resolve ties in the already declared order, without introducing new comparisons."""
            return (metric_values[name]["point_scores"]["mae_mwh"], metric_values[name]["pinball_mwh"],
                int(name.split("_")[1][:-1]), -int(name.rsplit("__ctx", 1)[1]), "known_calendar" in name)

        selected = min(eligible, key=order) if eligible else None
        decisions[target] = {"original_reference": reference, "deterministic_reference": baseline,
            "selected": selected, "retained": selected or reference, "assessments": assessments,
            "decision": "promote_for_exploratory_comparison" if selected else "no_promotion_stop"}
    return decisions


def checked_cached_row(rows: list[dict[str, object]], target: str, month: str,
                       base: str, phase: str, months: pd.DataFrame, protocol: dict[str, object]) -> dict[str, object]:
    """Reuse a single verified original forecast only if its context and target observation match."""
    matches = [row for row in rows if row["target"] == target and row["month"] == month
        and row["model"] == base and row["phase"] == phase]
    if len(matches) != 1:
        raise ValueError("Cache incompleta o duplicata: nessun ricalcolo fuori budget.")
    row = deepcopy(matches[0])
    expected = [str(period) for period in context_periods(pd.Period(month, freq="M"), protocol)]
    truth = months.loc[pd.Period(month, freq="M"), "energy_mwh"]
    if row["metadata"]["context_months"] != expected:
        raise ValueError("Contesto della cache diverso dal protocollo.")
    if (pd.isna(truth) and row["actual_mwh"] is not None) or (pd.notna(truth) and row["actual_mwh"] != float(truth)):
        raise ValueError("Verità osservata diversa dalla cache.")
    row.update(model=base + f"__ctx{protocol['context_months']}", reused=True)
    return row


def run_screen(config: dict[str, object], root: Path, model_factory: Callable[..., MonthlyTimestral] | None = None) -> dict[str, object]:
    """Execute only the exact approved proposal, reusing originals and respecting both call budgets."""
    settings = config["timestral_improvement"]
    if settings["execution_authorized"] is not True or settings["training_authorized"] is not False:
        raise RuntimeError("Esperimento non autorizzato o training inatteso.")
    proposal = settings["proposal"]
    protocol_folder = root / proposal["output_protocol_directory"]
    verify_manifest(protocol_folder)
    approved = json.loads((protocol_folder / "protocol_proposal.json").read_text(encoding="utf-8"))
    if approved["proposal"] != proposal:
        raise ValueError("Impostazioni diverse dalla proposta approvata.")
    frozen = check_frozen_protocol(config, root)
    if frozen["settings_sha256"] != approved["protocol_sha256"]:
        raise ValueError("Protocollo originale modificato.")
    old = root / proposal["old_forecasts_directory"]
    verify_manifest(old)
    if sha256((old / "manifest.json").read_bytes()).hexdigest() != approved["source_previous_manifest_sha256"]:
        raise ValueError("Cache originale diversa da quella approvata.")
    output = root / settings["results_directory"]
    if output.exists():
        raise FileExistsError("Serve una nuova cartella risultati.")
    original = config["monthly_protocol"]
    if (proposal["device"] != original["device"] or proposal["local_files_only"] is not True
            or proposal["weather_enabled"] is not False or proposal["adaptation_enabled"] is not False):
        raise ValueError("Modifiche non previste a dispositivo, rete o adattamento.")
    cached = json.loads((old / "predictions.json").read_text(encoding="utf-8"))["forecasts"]
    previous = json.loads((old / "results.json").read_text(encoding="utf-8"))
    if previous["protocol_sha256"] != frozen["settings_sha256"]:
        raise ValueError("Cache con protocollo diverso.")
    targets = load_monthly_targets(root / config["monthly_inspection"]["prepared_directory"],
        original["calendar_timezone"], original["wind_components"])
    import torch

    torch.set_num_threads(proposal["cpu_threads"])
    models = {}
    calls = {"development": 0, "test": 0}
    provenance = {}
    output.mkdir(parents=True, exist_ok=False)
    approval = {"approved_proposal": approved, "execution_authorization": settings,
        "kind": "synthetic_screen" if model_factory else "real_zero_shot_screen"}
    (output / "approval_snapshot.json").write_text(json.dumps(approval, indent=2), encoding="utf-8")
    rows, probabilistic = [], []
    periods = frozen["evaluation_periods"]

    def predict(target: str, month: str, phase: str, context: int, size: str, variant: str) -> dict[str, object]:
        """Acquire one forecast, enforcing the phase budget before touching the backend."""
        months = targets[target]
        base = f"timestral_{size}_{variant}"
        if context == original["context_months"]:
            return checked_cached_row(cached, target, month, base, phase, months, original)
        budget = approved["new_development_inferences"] if phase == "development" else approved["maximum_new_exploratory_inferences"]
        if calls[phase] >= budget:
            raise RuntimeError("Budget di inferenza esaurito.")
        cfg = deepcopy(original)
        cfg["context_months"] = context
        label = pd.Period(month, freq="M")
        context_values = months.mean_power_mw.reindex(context_periods(label, cfg))
        if int(context_values.notna().sum()) < cfg["minimum_valid_context_months"]:
            return {"model": base + f"__ctx{context}", "month": month, "point_mwh": None,
                "quantiles_mwh": None, "target": target, "phase": phase, "reused": False,
                "metadata": {"reason": "insufficient_valid_context_no_inference", "valid_context_months": int(context_values.notna().sum())},
                "target_start_utc": months.loc[label, "start_utc"],
                "actual_mwh": float(months.loc[label, "energy_mwh"]) if months.loc[label, "complete"] else None}
        key = (size, context)
        if key not in models:
            specification = next(item for item in original["models"] if item["size"] == size)
            models[key] = (model_factory or MonthlyTimestral)(cfg, specification)
        prediction = models[key].predict(months, label, variant)
        calls[phase] += 1
        provenance[f"{size}__ctx{context}"] = models[key].provenance
        row = asdict(prediction)
        row["quantiles_mwh"] = {str(level): float(value) for level, value in prediction.quantiles_mwh.items()}
        row.update(model=base + f"__ctx{context}", target=target, phase=phase, reused=False,
            target_start_utc=months.loc[label, "start_utc"],
            issue_utc=(pd.Timestamp(months.loc[label, "start_utc"]) - pd.Timedelta(hours=original["issue_lead_hours"])).isoformat(),
            actual_mwh=float(months.loc[label, "energy_mwh"]) if months.loc[label, "complete"] else None)
        return row

    def baselines(target: str, month: str, phase: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
        """Keep baseline context fixed and keep the sparse probabilistic comparison separate."""
        label, months = pd.Period(month, freq="M"), targets[target]
        deterministic, probabilistic_rows = [], []
        for prediction in baseline_predictions(months, label, original):
            row = asdict(prediction)
            row["quantiles_mwh"] = ({str(level): float(value) for level, value in prediction.quantiles_mwh.items()}
                if prediction.quantiles_mwh is not None else None)
            row.update(target=target, phase=phase, target_start_utc=months.loc[label, "start_utc"],
                actual_mwh=float(months.loc[label, "energy_mwh"]) if months.loc[label, "complete"] else None)
            (probabilistic_rows if prediction.model == original["probabilistic_baseline"] else deterministic).append(row)
        return deterministic, probabilistic_rows

    for target in proposal["targets"]:
        eligible = []
        for context in proposal["context_months"]:
            cfg = deepcopy(original)
            cfg["context_months"] = context
            folds = fold_preview(targets[target], periods["development_start_utc"], periods["test_start_utc"], cfg)
            eligible.append({fold["target_month"] for fold in folds if fold["scorable_without_model_run"]})
        common = sorted(set.intersection(*eligible))
        if common != approved["availability"][target]["common_origins"]:
            raise ValueError("Origini comuni diverse dall'anteprima approvata.")
        for month in common:
            simple, probabilistic_rows = baselines(target, month, "development")
            rows.extend(simple)
            probabilistic.extend(probabilistic_rows)
            for context in proposal["context_months"]:
                for size in proposal["model_sizes"]:
                    for variant in proposal["variants"]:
                        rows.append(predict(target, month, "development", context, size, variant))
        print(f"Sviluppo {target}: {len(common)} origini, griglia completata", flush=True)
    (output / "development_predictions.json").write_text(json.dumps(_json_safe(rows), indent=2, allow_nan=False), encoding="utf-8")
    scores = score_predictions(rows, original)
    decisions = assess_candidates(rows, scores, proposal, original["context_months"])
    selection_path = output / "selection_before_test.json"
    selection_path.write_text(json.dumps(_json_safe(decisions), indent=2, allow_nan=False), encoding="utf-8")
    selection_hash = sha256(selection_path.read_bytes()).hexdigest()
    exploratory = []
    for target, decision in decisions.items():
        if decision["selected"] is None:
            print(f"{target}: nessuna promozione, confronto sul test non eseguito", flush=True)
            continue
        selected = decision["selected"]
        base, context = selected.rsplit("__ctx", 1)
        size, variant = base[len("timestral_"):].split("_", 1)
        reference_base = decision["original_reference"].rsplit("__ctx", 1)[0]
        first = pd.Period(periods["test_start_utc"][:7], freq="M")
        stop = pd.Period(periods["test_end_exclusive_utc"][:7], freq="M")
        for label in pd.period_range(first, stop - 1, freq="M"):
            month = str(label)
            row = predict(target, month, "test", int(context), size, variant)
            exploratory.append(row)
            exploratory.append(checked_cached_row(cached, target, month, reference_base, "test", targets[target], original))
            simple, _ = baselines(target, month, "test")
            exploratory.extend(simple)
    if sha256(selection_path.read_bytes()).hexdigest() != selection_hash:
        raise ValueError("Selezione modificata dopo il test.")
    supplemental = [row for row in rows if row["model"].startswith("timestral_") or row["model"] == "same_month_previous_year"] + probabilistic
    result = {"kind": approval["kind"], "status": "complete", "proposal": proposal, "decisions": decisions,
        "development_scores": scores, "supplemental_probabilistic_scores": _json_safe(score_predictions(supplemental, original)),
        "exploratory_scores": _json_safe(score_predictions(exploratory, original)) if exploratory else {},
        "new_inference_calls": calls, "reused_development_forecasts": sum(row.get("reused", False) for row in rows),
        "selection_before_test_sha256": selection_hash, "new_models": provenance, "original_models": previous["models"],
        "original_protocol_sha256": frozen["settings_sha256"], "protocol": original,
        "independent_test": False, "training_performed": False, "search_expanded": False}
    (output / "exploratory_predictions.json").write_text(json.dumps(_json_safe(exploratory), indent=2, allow_nan=False), encoding="utf-8")
    (output / "probabilistic_baseline_predictions.json").write_text(json.dumps(_json_safe(probabilistic), indent=2, allow_nan=False), encoding="utf-8")
    (output / "results.json").write_text(json.dumps(_json_safe(result), indent=2, allow_nan=False), encoding="utf-8")
    (output / "presentazione.html").write_text(render_screen(result, rows), encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    return result


def render_screen(result: dict[str, object], rows: list[dict[str, object]]) -> str:
    """Show all candidates, failed gates and unpromoted outcomes without claiming a tuned winner."""
    sections = []
    for target, decision in result["decisions"].items():
        metrics = result["development_scores"][target]["development"]
        table, interval_rows, panels, options, origin_rows = [], [], [], [], []
        for name, item in sorted(metrics["models"].items(), key=lambda pair: pair[1]["point_scores"]["mae_mwh"]):
            assessment = decision["assessments"].get(name)
            failed = ", ".join(gate_label(key) for key, passed in assessment["gates"].items() if not passed) if assessment else "riferimento"
            table.append(f'<tr><td>{escape(candidate_label(name))}</td><td>{_fmt(item["point_scores"]["mae_mwh"])}</td>'
                f'<td>{_fmt(item["point_scores"]["rmse_mwh"])}</td><td>{_fmt(item.get("pinball_mwh"))}</td>'
                f'<td>{item["point_cases"]}</td><td>{"PROMOSSO" if assessment and assessment["passed"] else "NO" if assessment else "—"}</td><td>{escape(failed or "nessuno")}</td></tr>')
            if assessment:
                for level, interval in item["intervals"].items():
                    interval_rows.append(f'<tr><td>{escape(candidate_label(name))}</td><td>{float(level):.0%}</td>'
                        f'<td>{_fmt(interval["coverage"] * 100)}%</td><td>{_fmt(interval["mean_width_mwh"])}</td><td>{item["quantile_cases"]}</td></tr>')
                chart_rows = [row for row in rows if row["target"] == target and row["model"] == name]
                active = name == decision["retained"]
                options.append(f'<option value="{escape(name)}"{" selected" if active else ""}>{escape(candidate_label(name))}</option>')
                panels.append(f'<div class="chart" data-panel="{target}:{name}"{" hidden" if not active else ""}>{forecast_chart(chart_rows, result["protocol"]["interval_levels"])}</div>')
                for row in chart_rows:
                    origin_rows.append(f'<tr><td>{row["month"]}</td><td>{escape(candidate_label(name))}</td>'
                        f'<td>{_fmt(row["actual_mwh"])}</td><td>{_fmt(row["point_mwh"])}</td><td>{_fmt(abs(row["point_mwh"] - row["actual_mwh"]))}</td></tr>')
        secondary = result["supplemental_probabilistic_scores"][target]["development"]["models"]
        secondary_rows = []
        for name, item in secondary.items():
            if "pinball_mwh" in item:
                secondary_rows.append(f'<tr><td>{escape(candidate_label(name))}</td><td>{item["quantile_cases"]}</td>'
                    f'<td>{_fmt(item["pinball_mwh"])}</td><td>{_fmt(item["intervals"]["0.8"]["coverage"] * 100)}%</td>'
                    f'<td>{_fmt(item["intervals"]["0.9"]["coverage"] * 100)}%</td></tr>')
        sections.append(f'''<section><h2>{'Solare' if target == 'solar' else 'Eolico terra + mare'}</h2>
<p><b>{'Candidato promosso' if decision['selected'] else 'Nessun candidato supera tutti i criteri'}</b>.
Riferimento originale: {escape(candidate_label(decision['original_reference']))}. Baseline deterministica: {escape(candidate_label(decision['deterministic_reference']))}.</p>
<div class="scroll"><table><thead><tr><th>Variante</th><th>MAE MWh</th><th>RMSE MWh</th><th>Pinball MWh</th><th>Mesi</th><th>Promozione</th><th>Criteri non superati</th></tr></thead><tbody>{''.join(table)}</tbody></table></div>
<h3>Previsioni e intervalli: scegli la variante</h3><label>Variante <select data-target="{target}">{''.join(options)}</select></label>{''.join(panels)}
<p>Grafico sullo sviluppo, non nuova prova indipendente. Intervalli mensili diretti: nessuna somma di quantili orari.</p>
<h3>Copertura e ampiezza sulle stesse origini</h3><div class="scroll"><table><thead><tr><th>Variante</th><th>Livello nominale</th><th>Copertura osservata</th><th>Ampiezza media MWh</th><th>Mesi comuni</th></tr></thead><tbody>{''.join(interval_rows)}</tbody></table></div>
<details><summary>Confronto separato con la baseline probabilistica rolling</summary><p>I mesi comuni possono essere meno di quelli della selezione principale. Non si confrontano punteggi calcolati su insiemi diversi.</p><div class="scroll"><table><thead><tr><th>Modello</th><th>Mesi comuni</th><th>Pinball MWh</th><th>Copertura 80%</th><th>Copertura 90%</th></tr></thead><tbody>{''.join(secondary_rows)}</tbody></table></div></details>
<details><summary>Tutte le previsioni di sviluppo, origine per origine</summary><div class="scroll"><table><thead><tr><th>Mese UTC</th><th>Variante</th><th>Osservato MWh</th><th>Previsione MWh</th><th>Errore assoluto MWh</th></tr></thead><tbody>{''.join(origin_rows)}</tbody></table></div></details></section>''')
    for target, phases in result.get("exploratory_scores", {}).items():
        comparison_rows = ''.join(f'<tr><td>{escape(candidate_label(name))}</td><td>{_fmt(item["point_scores"]["mae_mwh"])}</td><td>{item["point_cases"]}</td></tr>'
            for name, item in phases["test"]["models"].items())
        sections.append(f'<section><h2>Confronto esplorativo: {escape(target)}</h2><p>Selezione già congelata prima di questo confronto; nessuna nuova scelta basata sul vecchio test.</p>'
            f'<div class="scroll"><table><thead><tr><th>Modello</th><th>MAE MWh</th><th>Mesi comuni</th></tr></thead><tbody>{comparison_rows}</tbody></table></div></section>')
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Esperimento contesto Timestral</title><style>body{{font:15px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}main{{max-width:1200px;margin:auto;padding:24px}}header,section{{padding:25px;border-radius:16px;margin:20px 0;background:white;overflow-wrap:anywhere}}header{{background:#16313e;color:white}}.scroll,.chart{{overflow:auto}}table{{width:100%;min-width:1000px;border-collapse:collapse;font-size:13px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}svg{{width:100%;min-width:700px}}.note{{padding:18px;background:#fff0d7}}select{{box-sizing:border-box;max-width:100%;padding:10px}}summary{{cursor:pointer}}</style></head><body><main>
<header><h1>Un anno o due di contesto: il confronto reale</h1><p>Solare ed eolico · 5M/28M · Solo serie/calendario · Sviluppo comune</p></header>
<p class="note">Nessun training. Nuove inferenze sviluppo: {result['new_inference_calls']['development']}; esplorative: {result['new_inference_calls']['test']}. Previsioni originali riutilizzate: {result['reused_development_forecasts']}.</p>
{''.join(sections)}<section><h2>Criteri e limiti</h2><p>MAE almeno -5% rispetto al migliore originale e alla migliore baseline, vittorie almeno nel 60% dei mesi, RMSE/pinball/copertura non peggiori e ampiezza al massimo +10%. Tutti i criteri devono passare.</p>
<p>Le sigle coverage/width indicano copertura e ampiezza ai livelli 80% e 90%; i valori numerici completi sono nel JSON. Il confronto probabilistico con la baseline rolling usa un sottoinsieme separato e non altera i mesi della selezione principale.</p>
<p>Undici mesi e selezione tra varianti non dimostrano superiorità generale. Il vecchio test è già stato esaminato: un eventuale confronto successivo resta esplorativo. Se nessuno passa non viene eseguito e la ricerca non viene allargata.</p>
<p>Le previsioni precedenti e il protocollo congelato sono conservati. JSON affiancati con ogni previsione, criteri, punteggi e hash; selezione salvata prima di qualsiasi confronto esplorativo.</p></section></main>
<script>document.querySelectorAll('select[data-target]').forEach(select=>select.addEventListener('change',()=>{{document.querySelectorAll('[data-panel]').forEach(panel=>{{if(panel.dataset.panel.startsWith(select.dataset.target+':'))panel.hidden=panel.dataset.panel!==select.dataset.target+':'+select.value;}});}}));</script></body></html>'''


def main() -> None:
    """Run the approved fixed-grid screen, never train, download or expand its search."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    run_screen(config, args.config.resolve().parent.parent)
    print(config["timestral_improvement"]["results_directory"] + "/presentazione.html")


if __name__ == "__main__":
    main()
