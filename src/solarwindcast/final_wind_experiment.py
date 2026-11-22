"""Execute one approved exploratory wind comparison with a fixed causal width calibrator."""

import argparse
import json
import math
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
from solarwindcast.monthly_improvement import checked_cached_row, verify_manifest
from solarwindcast.monthly_protocol import fold_preview, load_monthly_targets
from solarwindcast.monthly_results_html import forecast_chart
from solarwindcast.wind_calibration import apply_scale, fit_scale


def causal_calibration(warmup: list[dict], evaluation: list[dict], protocol: dict,
                      settings: dict) -> tuple[list[dict], list[dict]]:
    """Use only completed earlier labels; never relabel test forecasts as development."""
    all_rows = warmup + evaluation
    if (len({r['month'] for r in all_rows}) != len(all_rows)
            or any(r['phase'] != 'development' for r in warmup)
            or any(r['phase'] != 'test' for r in evaluation)
            or any(r['model'] != settings['uncalibrated_control'] or r['target'] != settings['target']
                   for r in all_rows)
            or (warmup and evaluation and max(r['month'] for r in warmup) >= min(r['month'] for r in evaluation))):
        raise ValueError('Origini duplicate, fasi o candidato incoerenti.')
    calibrated, trace = [], []
    for row in sorted(evaluation, key=lambda r: r['month']):
        cutoff = pd.Period(row['month'], freq='M') - protocol['unavailable_recent_months'] - 1
        first = cutoff - settings['calibration']['lookback_months'] + 1
        history = [r for r in all_rows if first <= pd.Period(r['month'], freq='M') <= cutoff
                   and r['actual_mwh'] is not None and r['quantiles_mwh'] is not None]
        info = {'month': row['month'], 'available_through_month': str(cutoff),
                'calibration_months': sorted(r['month'] for r in history), 'past_errors': len(history)}
        if len(history) < settings['calibration']['minimum_past_errors']:
            trace.append({**info, 'status': 'insufficient_history', 'scale': None})
            continue
        scale = fit_scale(history, protocol['comparison_quantile_levels'], settings['calibration'])
        result = apply_scale(row, scale)
        result['metadata']['calibration'] = {**info, 'scale': scale}
        calibrated.append(result)
        trace.append({**info, 'status': 'calibrated', 'scale': scale})
    return calibrated, trace


def assess_gates(scores: dict, rows: list[dict], settings: dict) -> dict:
    """Apply every frozen condition on explicit common point and quantile masks."""
    cfg = settings['proposed_gates']
    models = scores['models']
    candidate, reference = models[settings['candidate']], models[settings['reference']]
    n, nq = candidate['point_cases'], candidate.get('quantile_cases', 0)
    gates = {'minimum_point_cases': n >= cfg['minimum_common_cases'],
             'minimum_quantile_cases': nq >= cfg['minimum_common_cases']}
    for name in [settings['reference'], *settings['baseline_methods']]:
        gates['mae_vs_' + name] = (candidate['point_scores']['mae_mwh'] <=
            models[name]['point_scores']['mae_mwh'] * (1 - cfg['minimum_mae_reduction_pct'] / 100))
    gates['rmse'] = candidate['point_scores']['rmse_mwh'] <= reference['point_scores']['rmse_mwh']
    probabilistic = settings['baseline_methods'][-1]
    for name in (settings['reference'], probabilistic):
        gates['pinball_vs_' + name] = (nq >= cfg['minimum_common_cases']
            and candidate.get('pinball_mwh', math.inf) <= models[name].get('pinball_mwh', -math.inf))
    common = {s[:7] for s in scores['point_common_months']}
    lookup = {(r['month'], r['model']): r for r in rows}
    wins = sum(abs(lookup[m, settings['candidate']]['point_mwh'] - lookup[m, settings['candidate']]['actual_mwh'])
               < abs(lookup[m, settings['reference']]['point_mwh'] - lookup[m, settings['reference']]['actual_mwh'])
               for m in common)
    gates['monthly_wins'] = n > 0 and wins / n >= cfg['minimum_monthly_win_fraction']
    for level in ('0.8', '0.9'):
        ci, ri = candidate.get('intervals', {}).get(level, {}), reference.get('intervals', {}).get(level, {})
        gates['coverage_' + level] = nq > 0 and ci.get('coverage', -1) >= ri.get('coverage', 2)
        gates['width_' + level] = (nq > 0 and ci.get('mean_width_mwh', math.inf)
            <= ri.get('mean_width_mwh', -math.inf) * cfg['maximum_interval_width_ratio'])
    return {'gates': gates, 'all_pass': all(gates.values()), 'wins': wins, 'point_cases': n,
            'quantile_cases': nq, 'required_wins': math.ceil(n * cfg['minimum_monthly_win_fraction']),
            'operational_promotion': False}


def run_final(config: dict, root: Path) -> dict:
    """Verify the approved proposal and cached references before spending at most 24 calls."""
    settings = config['final_wind_experiment']
    if (settings['execution_authorized'] is not True or settings['approved_new_inference_budget'] != 24
            or settings['training_authorized'] is not False or settings['downloads_authorized'] is not False
            or settings['alternate_methods_authorized'] is not False):
        raise RuntimeError('Esecuzione o budget non autorizzati.')
    proposal = root / settings['protocol_directory']
    verify_manifest(proposal)
    original = yaml.safe_load((proposal / 'config_snapshot.yaml').read_text(encoding='utf-8'))['final_wind_experiment']
    mutable = {'status', 'execution_authorized', 'approved_new_inference_budget'}
    if {k: v for k, v in settings.items() if k not in mutable} != {k: v for k, v in original.items() if k not in mutable}:
        raise ValueError('Proposta modificata dopo approvazione.')
    frozen = check_frozen_protocol(config, root)
    protocol = deepcopy(config['monthly_protocol'])
    output = root / settings['output_directory']
    if output.exists():
        raise FileExistsError('Output esistente: nessuna sovrascrittura o riesecuzione implicita.')
    sources = [root / settings[key] for key in ('warmup_directory', 'original_results_directory', 'previous_calibration_directory')]
    for folder in sources:
        verify_manifest(folder)
    fingerprints = {str(p.relative_to(root)): sha256((p / 'manifest.json').read_bytes()).hexdigest() for p in sources}
    previous = json.loads((sources[2] / 'results.json').read_text(encoding='utf-8'))['settings']
    if any(previous[k] != v for k, v in settings['calibration'].items()):
        raise ValueError('Calibratore diverso da quello dichiarato.')
    months = load_monthly_targets(root / config['monthly_inspection']['prepared_directory'],
                                 protocol['calendar_timezone'], protocol['wind_components'])[settings['target']]
    start = pd.Period(settings['evaluation_start_month'], freq='M')
    stop = pd.Period(settings['evaluation_end_month_inclusive'], freq='M')
    labels = pd.period_range(start, stop, freq='M')
    if len(labels) != settings['approved_new_inference_budget']:
        raise ValueError('Numero di origini diverso dal budget approvato.')
    cached = json.loads((sources[1] / 'predictions.json').read_text(encoding='utf-8'))['forecasts']
    rows = []
    for label in labels:
        truth = float(months.loc[label, 'energy_mwh']) if pd.notna(months.loc[label, 'energy_mwh']) else None
        for base in baseline_predictions(months, label, protocol):
            matches = [r for r in cached if r['target'] == settings['target'] and r['phase'] == 'test'
                       and r['month'] == str(label) and r['model'] == base.model]
            expected_q = {str(q): float(v) for q, v in base.quantiles_mwh.items()} if base.quantiles_mwh is not None else None
            if (len(matches) != 1 or matches[0]['point_mwh'] != base.point_mwh
                    or matches[0]['quantiles_mwh'] != expected_q or matches[0]['actual_mwh'] != truth):
                raise ValueError('Baseline in cache incoerente: nessun ricalcolo nascosto.')
            rows.append(deepcopy(matches[0]))
        for spec in protocol['models']:
            for variant in protocol['model_variants']:
                rows.append(checked_cached_row(cached, settings['target'], str(label),
                    f"timestral_{spec['size']}_{variant}", 'test', months, protocol))
    warmup = [r for r in json.loads((sources[0] / 'development_predictions.json').read_text(encoding='utf-8'))
              if r['target'] == settings['target'] and r['model'] == settings['uncalibrated_control']]
    candidate_protocol = deepcopy(protocol)
    candidate_protocol['context_months'] = settings['context_months']
    for r in warmup:
        label = pd.Period(r['month'], freq='M')
        if (r['actual_mwh'] != float(months.loc[label, 'energy_mwh'])
                or r['metadata']['context_months'] != [str(p) for p in context_periods(label, candidate_protocol)]):
            raise ValueError('Warm-up incoerente con i dati o il cutoff.')
    folds = fold_preview(months, str(start), str(stop + 1), candidate_protocol)
    if any(not f['scorable_without_model_run'] for f in folds):
        raise ValueError('Origine non eseguibile senza cambiare il protocollo.')
    import torch

    torch.set_num_threads(settings['cpu_threads'])
    model = MonthlyTimestral(candidate_protocol, next(m for m in protocol['models'] if m['size'] == '28M'))
    model.load()
    output.mkdir(parents=True, exist_ok=False)
    snapshot = {'settings': settings, 'protocol': protocol, 'source_manifests': fingerprints,
                'frozen_protocol_sha256': frozen['settings_sha256'], 'model_provenance': model.provenance,
                'approved_on': '2026-11-14; user procedi', 'independent_test': False}
    snapshot_path = output / 'settings_before_inference.json'
    snapshot_path.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    snapshot_hash = sha256(snapshot_path.read_bytes()).hexdigest()
    evaluation = []
    for fold in folds:
        label = pd.Period(fold['target_month'], freq='M')
        prediction = model.predict(months, label, 'known_calendar')
        row = asdict(prediction)
        row['quantiles_mwh'] = {str(q): float(v) for q, v in prediction.quantiles_mwh.items()}
        row.update(model=settings['uncalibrated_control'], target=settings['target'], phase='test',
                   actual_mwh=float(months.loc[label, 'energy_mwh']),
                   target_start_utc=pd.Timestamp(months.loc[label, 'start_utc']).isoformat(), issue_utc=fold['issue_utc'])
        evaluation.append(row)
        (output / f"raw_forecast_{label}.json").write_text(json.dumps(_json_safe(row), indent=2, default=str), encoding='utf-8')
        print(f'Inferenza {len(evaluation)}/{len(folds)}: {label}', flush=True)
    calibrated, trace = causal_calibration(warmup, evaluation, protocol, settings)
    rows += evaluation + calibrated
    for row in rows:
        row['target_start_utc'] = pd.Timestamp(row['target_start_utc']).isoformat()
    scores = score_predictions(rows, protocol)[settings['target']]['test']
    assessment = assess_gates(scores, rows, settings)
    result = {'status': 'complete', 'kind': 'exploratory_final_wind_comparison', 'settings': settings,
              'scores': _json_safe(scores), 'assessment': assessment, 'trace': trace,
              'new_inferences': len(evaluation), 'reused_reference_forecasts': len(rows) - len(evaluation) - len(calibrated),
              'model_provenance': model.provenance, 'independent_test': False, 'operational_promotion': False,
              'median_changed_by_calibration': False, 'snapshot_sha256': snapshot_hash,
              'decision': 'promising_exploratory_only' if assessment['all_pass'] else 'criteria_failed_stop_iteration'}
    if sha256(snapshot_path.read_bytes()).hexdigest() != snapshot_hash:
        raise ValueError('Snapshot modificato durante esecuzione.')
    for folder in sources:
        if sha256((folder / 'manifest.json').read_bytes()).hexdigest() != fingerprints[str(folder.relative_to(root))]:
            raise ValueError('Sorgente modificata.')
    (output / 'predictions.json').write_text(json.dumps(_json_safe(rows), indent=2, default=str, allow_nan=False), encoding='utf-8')
    (output / 'results.json').write_text(json.dumps(_json_safe(result), indent=2, allow_nan=False), encoding='utf-8')
    (output / 'presentazione.html').write_text(render_report(result, rows), encoding='utf-8')
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    (output / 'manifest.json').write_text(json.dumps({'status': 'complete', 'files_sha256': hashes}, indent=2), encoding='utf-8')
    return result


def render_report(result: dict, rows: list[dict]) -> str:
    """Show common-case metrics, before/after deltas, every failed gate and causal provenance."""
    settings, scores = result['settings'], result['scores']
    models = scores['models']
    def fmt(value: object) -> str:
        """Render undefined values explicitly, without presenting a missing score as zero."""
        return 'N/D' if value is None else f'{value:,.2f}'.translate(str.maketrans(',.', '.,'))
    def label(name: str) -> str:
        """Explain the scientific variant without exposing internal cache identifiers."""
        baselines = {'last_complete_month': 'Ultimo mese completo', 'recent_complete_months': 'Media recente',
                     'same_month_previous_year': 'Stesso mese anno precedente',
                     'seasonal_empirical_rolling_errors': 'Stagionale con errori rolling'}
        if name in baselines:
            return baselines[name]
        size = name.split('_')[1]
        context = name.split('__ctx')[1].split('__')[0]
        return f"Timestral {size} · {'calendario' if 'known_calendar' in name else 'solo target'} · {context} mesi" + (' · calibrato' if name.endswith('__calibrated') else '')
    table = []
    for name, m in models.items():
        intervals = m.get('intervals', {})
        table.append('<tr><td>' + escape(label(name)) + '</td><td>' + str(m['point_cases']) + '</td>'
                     + ''.join('<td>' + fmt(m['point_scores'][key]) + '</td>' for key in ('mae_mwh', 'rmse_mwh', 'bias_mwh'))
                     + '<td>' + fmt(m.get('pinball_mwh')) + '</td><td>' + str(m.get('quantile_cases', 'N/D')) + '</td>'
                     + ''.join('<td>' + (f"{v.get('coverage', 0):.2%} ({round(v.get('coverage', 0)*m.get('quantile_cases', 0))}/{m.get('quantile_cases', 0)})" if v else 'N/D')
                               + '</td><td>' + fmt(v.get('mean_width_mwh')) + '</td>' for v in [intervals.get('0.8', {}), intervals.get('0.9', {})]) + '</tr>')
    differences = []
    candidate = models[settings['candidate']]
    for name in (settings['uncalibrated_control'], settings['reference'], *settings['baseline_methods']):
        other = models[name]
        fields = [('MAE', candidate['point_scores']['mae_mwh'], other['point_scores']['mae_mwh']),
                  ('RMSE', candidate['point_scores']['rmse_mwh'], other['point_scores']['rmse_mwh']),
                  ('Pinball', candidate.get('pinball_mwh'), other.get('pinball_mwh'))]
        for level in ('0.8', '0.9'):
            ci, oi = candidate.get('intervals', {}).get(level, {}), other.get('intervals', {}).get(level, {})
            fields += [('Copertura ' + level + ' (punti percentuali)', 100 * ci['coverage'] if ci else None, 100 * oi['coverage'] if oi else None),
                       ('Ampiezza ' + level, ci.get('mean_width_mwh'), oi.get('mean_width_mwh'))]
        for metric, a, b in fields:
            delta = a-b if a is not None and b is not None else None
            percent = 100*delta/b if delta is not None and b else None
            state = ('da leggere rispetto al nominale' if metric.startswith('Copertura') else
                     'N/D' if delta is None else 'invariato' if delta == 0 else 'diminuisce' if delta < 0 else 'aumenta')
            tone = 'neutral' if metric.startswith('Copertura') or delta is None or delta == 0 else 'good' if delta < 0 else 'bad'
            percentage = fmt(percent) + '%' if percent is not None else 'N/D'
            differences.append(f'<tr class="{tone}"><td>{escape(label(name))}</td><td>{metric}</td><td>{fmt(b)}</td><td>{fmt(a)}</td><td>{fmt(delta)}</td><td>{percentage}</td><td>{state}</td></tr>')
    gate_names = {'minimum_point_cases': 'Almeno 12 mesi puntuali comuni', 'minimum_quantile_cases': 'Almeno 12 mesi quantili comuni',
                  'monthly_wins': 'Vittorie mensili almeno 60%', 'rmse': 'RMSE non peggiore del riferimento',
                  'coverage_0.8': 'Copertura80 non inferiore al riferimento', 'coverage_0.9': 'Copertura90 non inferiore al riferimento',
                  'width_0.8': 'Ampiezza80 entro il 110% del riferimento', 'width_0.9': 'Ampiezza90 entro il 110% del riferimento'}
    for name in [settings['reference'], *settings['baseline_methods']]:
        gate_names['mae_vs_' + name] = 'MAE almeno -5% rispetto a ' + label(name)
        gate_names['pinball_vs_' + name] = 'Pinball non peggiore di ' + label(name)
    gates = ''.join(f'<tr class="{"good" if v else "bad"}"><td>{escape(gate_names.get(k, k))}</td><td>{"SUPERATO" if v else "FALLITO"}</td></tr>' for k, v in result['assessment']['gates'].items())
    charts = ''.join('<h3>' + escape(label(name)) + '</h3><div class="scroll">'
                     + forecast_chart([r for r in rows if r['model'] == name], [0.8, 0.9]) + '</div>'
                     for name in (settings['candidate'], settings['uncalibrated_control'], settings['reference']))
    trace = ''.join(f'<tr><td>{r["month"]}</td><td>{r["available_through_month"]}</td><td>{r["past_errors"]}</td><td>{fmt(r["scale"])}</td></tr>' for r in result['trace'])
    monthly = []
    lookup = {(r['month'], r['model']): r for r in rows}
    for month in sorted({r['month'] for r in rows}):
        a, b = lookup[month, settings['candidate']], lookup[month, settings['reference']]
        ea, eb = abs(a['point_mwh'] - a['actual_mwh']), abs(b['point_mwh'] - b['actual_mwh'])
        monthly.append(f'<tr class="{"good" if ea < eb else "bad" if ea > eb else "neutral"}"><td>{month}</td><td>{fmt(a["actual_mwh"])}</td><td>{fmt(a["point_mwh"])}</td><td>{fmt(b["point_mwh"])}</td><td>{fmt(ea)}</td><td>{fmt(eb)}</td><td>{"migliora" if ea < eb else "peggiora" if ea > eb else "pareggio"}</td></tr>')
    decision = 'Segnale promettente solo esplorativo' if result['assessment']['all_pass'] else 'Criteri non superati: fermare questa iterazione'
    return f'''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Ultimo confronto eolico</title><style>body{{font:16px/1.6 system-ui;background:#edf2f2;color:#20383c;margin:0}}main{{max-width:1300px;margin:auto;padding:24px}}header,section{{padding:24px;background:white;border-radius:16px;margin:20px 0;overflow-wrap:anywhere}}header{{background:#123e46;color:white}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1000px}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}.note{{background:#fff0d7;padding:18px}}.good{{background:#edf8f0}}.bad{{background:#fff0ed}}svg{{width:100%;min-width:700px}}</style><main>
<header><h1>Ultimo confronto eolico: risultati e criteri</h1><p>Sud · terra + mare · novembre 2024–ottobre 2026 · MWh</p></header>
<p class="note">Periodo già esaminato: confronto esplorativo, nessuna promozione operativa. Decisione: {decision}. {result['new_inferences']} nuove inferenze; zero training o download. Nessuna ulteriore modifica del modello dopo il risultato.</p>
<section><h2>Metriche su mesi comuni</h2><p>Mesi puntuali: {len(scores['point_common_months'])}; mesi quantili: {len(scores['quantile_common_months'])}. MAE, RMSE e pinball: meno è meglio. Bias: considerare distanza da zero. Copertura e ampiezza vanno lette insieme, rispetto ai nominali80/90.</p>
<div class="scroll"><table><tr><th>Modello</th><th>Casi puntuali</th><th>MAE</th><th>RMSE</th><th>Bias</th><th>Pinball</th><th>Casi quantili</th><th>Copertura80</th><th>Ampiezza80</th><th>Copertura90</th><th>Ampiezza90</th></tr>{''.join(table)}</table></div></section>
<section><h2>Prima / dopo e confronto con tutti i riferimenti</h2><p>Dopo = candidato12 mesi calibrato. Nessuna variazione percentuale definita se prima=0; N/D indica assenza di metrica. Le ampiezze minori sono utili solo con coperture adeguate. La mediana è invariata dalla calibrazione.</p><div class="scroll"><table><tr><th>Prima / riferimento</th><th>Metrica</th><th>Prima</th><th>Dopo</th><th>Differenza assoluta</th><th>Variazione %</th><th>Lettura</th></tr>{''.join(differences)}</table></div></section>
<section><h2>Criteri fissati prima</h2><p>Vittorie mensili sul riferimento: {result['assessment']['wins']}/{result['assessment']['point_cases']}; richieste: {result['assessment']['required_wins']}. Tutti superati: {result['assessment']['all_pass']}.</p><div class="scroll"><table><tr><th>Criterio</th><th>Esito</th></tr>{gates}</table></div></section>
<section><h2>Errori per mese, in MWh</h2><div class="scroll"><table><tr><th>Mese</th><th>Osservato</th><th>Candidato calibrato</th><th>Riferimento24</th><th>Errore assoluto candidato</th><th>Errore assoluto riferimento</th><th>Esito</th></tr>{''.join(monthly)}</table></div></section>
<section><h2>Previsioni e intervalli per mese</h2>{charts}<p>I grafici riportano GWh, le tabelle MWh (1 GWh = 1.000 MWh). Le scale verticali possono differire.</p></section><section><h2>Tracciamento causale della calibrazione</h2><div class="scroll"><table><tr><th>Mese</th><th>Ultima etichetta disponibile</th><th>Errori storici</th><th>Fattore</th></tr>{trace}</table></div><p>Gli errori del mese ancora in corso non entrano nel fit; mediana e ordinamento dei quantili preservati. Dati revisionati: ritardi e versioni disponibili storicamente non ricostruiti.</p></section>
<section><h2>Provenienza ed esclusioni</h2><p>Puntuali esclusi dal candidato: {escape(str(candidate['point_excluded_utc']))}. Il confronto non modifica i nove mesi di sviluppo precedenti, né il loro esito. Le altre varianti a24 mesi sono controlli descrittivi: nessuna nuova selezione retroattiva.</p><p><a href="results.json">Metriche, decisione, versione e hash pesi</a> · <a href="predictions.json">Previsioni</a> · <a href="settings_before_inference.json">Snapshot prima delle inferenze</a></p></section></main></html>'''


def main() -> None:
    """Run exactly the approved experiment from the single project configuration."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    result = run_final(config, args.config.resolve().parent.parent)
    print(json.dumps(result['assessment'], indent=2))


if __name__ == '__main__':
    main()
