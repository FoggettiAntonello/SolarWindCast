"""Causal additive hourly calibration and the approved, immutable forecast replay."""

import argparse
import json
import math
from copy import deepcopy
from hashlib import sha256
from html import escape
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from matplotlib.figure import Figure

from solarwindcast.hourly_pilot import metrics
from solarwindcast.monthly_improvement import verify_manifest


def _arrays(row: dict, cfg: dict, require_actual: bool = True) -> tuple[np.ndarray, np.ndarray]:
    """Require a complete finite forecast day with ordered quantiles and its unchanged median."""
    actual = np.asarray(row['actual'], dtype=float) if require_actual else np.zeros(cfg['horizon_hours'])
    q = np.array(row['quantiles'], dtype=float, copy=True)
    levels = cfg['quantiles']
    if (actual.shape != (cfg['horizon_hours'],) or q.shape != (len(actual), len(levels))
            or not np.isfinite(actual).all() or not np.isfinite(q).all()
            or np.any(np.diff(q, axis=1) < 0)
            or not np.array_equal(np.asarray(row['point']), q[:, levels.index(.5)])):
        raise ValueError('Giornata incompleta, quantili incrociati o mediana incoerente.')
    return actual, q


def available_history(rows: list[dict], current: dict, cfg: dict) -> list[dict]:
    """Use whole days only after their last hour and the assumed publication delay have elapsed."""
    origin = pd.Timestamp(current['origin'])
    if origin.tzinfo is None:
        raise ValueError('Origine con timezone obbligatoria.')
    lower = origin - pd.Timedelta(days=cfg['lookback_days'])
    identifiers = [(r['target'], pd.Timestamp(r['origin'])) for r in rows]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError('Origini duplicate: evitare il doppio conteggio degli errori.')
    selected = []
    for row in rows:
        stamp = pd.Timestamp(row['origin'])
        if stamp.tzinfo is None:
            raise ValueError('Origine storica con timezone obbligatoria.')
        if row['target'] != current['target']:
            continue
        if row['model'] != cfg['source_model']:
            raise ValueError('Sorgente del modello inattesa.')
        available_at = stamp + pd.Timedelta(hours=cfg['horizon_hours'] + cfg['assumed_delay_hours'])
        if lower <= stamp and available_at <= origin:
            _arrays(row, cfg)
            selected.append(row)
    return sorted(selected, key=lambda r: pd.Timestamp(r['origin']))


def fit_expansions(history: list[dict], cfg: dict) -> dict[str, float]:
    """Compute two nonnegative corrections using a fixed order statistic; no grid search."""
    if (len(history) < cfg['minimum_complete_origins'] or cfg['preserve_median'] is not True
            or cfg['enforce_nested_expansions'] is not True):
        raise ValueError('Storico insufficiente o invarianti disabilitate.')
    if len({(r['target'], pd.Timestamp(r['origin'])) for r in history}) != len(history):
        raise ValueError('Giornate duplicate.')
    if len({r['target'] for r in history}) != 1:
        raise ValueError('Non mescolare target.')
    result, previous = {}, 0.
    for level in sorted(cfg['interval_levels']):
        lo, hi = round((1-level)/2, 5), round((1+level)/2, 5)
        scores = []
        for row in history:
            actual, q = _arrays(row, cfg)
            values = np.maximum.reduce([q[:, cfg['quantiles'].index(lo)] - actual,
                                        actual - q[:, cfg['quantiles'].index(hi)], np.zeros_like(actual)])
            scores.extend(values.tolist())
        rank = math.ceil((len(scores)+1)*level)
        if rank > len(scores):
            raise ValueError('Campione insufficiente per il quantile richiesto.')
        correction = max(previous, float(np.partition(np.asarray(scores), rank-1)[rank-1]))
        result[str(level)] = correction
        previous = correction
    return result


def apply_expansions(row: dict, corrections: dict[str, float], cfg: dict) -> dict:
    """Expand tail quantiles only, preserving the point forecast, median and source record."""
    _, q = _arrays(row, cfg, require_actual=False)
    result = deepcopy(row)
    levels = sorted(cfg['interval_levels'])
    values = [corrections[str(level)] for level in levels]
    if any(not math.isfinite(v) or v < 0 for v in values) or values != sorted(values):
        raise ValueError('Correzioni finite, nonnegative e annidate obbligatorie.')
    for level in levels:
        lo, hi = round((1-level)/2, 5), round((1+level)/2, 5)
        q[:, cfg['quantiles'].index(lo)] -= corrections[str(level)]
        q[:, cfg['quantiles'].index(hi)] += corrections[str(level)]
    result['quantiles'] = q.tolist()
    result['model'] = row['model'] + '__additive_calibrated'
    result.pop('metrics', None)
    return result


def replay(rows: list[dict], evaluation: list[dict], cfg: dict) -> tuple[list[dict], list[dict]]:
    """Fit one frozen rule chronologically and expose availability of every historical label."""
    transformed, trace = [], []
    for current in sorted(evaluation, key=lambda r: (r['target'], pd.Timestamp(r['origin']))):
        past = available_history(rows, current, cfg)
        info = {'target': current['target'], 'origin': current['origin'],
                'past_origins': [r['origin'] for r in past], 'complete_past_days': len(past),
                'past_available_at': [(pd.Timestamp(r['origin']) + pd.Timedelta(
                    hours=cfg['horizon_hours'] + cfg['assumed_delay_hours'])).isoformat() for r in past]}
        if len(past) < cfg['minimum_complete_origins']:
            trace.append({**info, 'status': 'insufficient_history'})
            continue
        correction = fit_expansions(past, cfg)
        transformed.append(apply_expansions(current, correction, cfg))
        n = len(past)*cfg['horizon_hours']
        trace.append({**info, 'status': 'calibrated', 'past_hours': n, 'corrections_mw': correction,
                      'ranks': {str(level): math.ceil((n+1)*level) for level in cfg['interval_levels']}})
    return transformed, trace


def summarize(rows: list[dict], cfg: dict) -> dict:
    """Compute all methods on identical origins, plus day/month/hour diagnostics."""
    summary = {}
    for target in cfg['targets']:
        methods = sorted({r['model'] for r in rows if r['target'] == target})
        expected = None
        models, details = {}, {}
        for name in methods:
            subset = sorted([r for r in rows if r['target'] == target and r['model'] == name],
                            key=lambda r: pd.Timestamp(r['origin']))
            origins = [r['origin'] for r in subset]
            if len(set(origins)) != len(origins) or (expected is not None and origins != expected):
                raise ValueError('Metodi non valutati sulle stesse origini univoche.')
            expected = origins
            actual = np.asarray([r['actual'] for r in subset], dtype=float)
            points = np.asarray([r['point'] for r in subset], dtype=float)
            q = np.asarray([r['quantiles'] for r in subset], dtype=float) if all(r['quantiles'] is not None for r in subset) else None
            pooled = metrics(actual.ravel(), points.ravel(), q.reshape(-1, len(cfg['quantiles'])) if q is not None else None, cfg)
            models[name] = {**pooled, 'origins': len(origins)}
            daily = [{'origin': r['origin'], **metrics(actual[i], points[i], q[i] if q is not None else None, cfg)}
                     for i, r in enumerate(subset)]
            by_month = {}
            for month in sorted({pd.Timestamp(o).strftime('%Y-%m') for o in origins}):
                mask = np.array([pd.Timestamp(o).strftime('%Y-%m') == month for o in origins])
                by_month[month] = metrics(actual[mask].ravel(), points[mask].ravel(),
                    q[mask].reshape(-1, len(cfg['quantiles'])) if q is not None else None, cfg)
            by_hour = {str(hour): metrics(actual[:, hour], points[:, hour], q[:, hour] if q is not None else None, cfg)
                       for hour in range(cfg['horizon_hours'])}
            details[name] = {'daily': daily, 'by_month': by_month, 'by_forecast_hour': by_hour}
        summary[target] = {'models': models, 'details': details, 'common_origins': expected or []}
    return summary


def assess(summary: dict, rows: list[dict], cfg: dict) -> dict:
    """Apply the approved gates without weakening them after seeing the result."""
    decisions = {}
    gates = cfg['proposed_gates']
    candidate = cfg['source_model']+'__additive_calibrated'
    for target, data in summary.items():
        models = data['models']
        raw, calibrated, baseline = (models[n] for n in (cfg['source_model'], candidate, 'hour_of_day_distribution'))
        before = {r['origin']: r for r in rows if r['target'] == target and r['model'] == cfg['source_model']}
        after = [r for r in rows if r['target'] == target and r['model'] == candidate]
        identical = all(r['point'] == before[r['origin']]['point']
                        and [v[cfg['quantiles'].index(.5)] for v in r['quantiles']] == r['point'] for r in after)
        checks = {'minimum_origins': calibrated['origins'] >= gates['minimum_evaluation_origins'],
                  'point_predictions_unchanged': identical,
                  'point_metrics_unchanged': all(raw[k] == calibrated[k] for k in ('mae_mw','rmse_mw','bias_mw')),
                  'pinball_reduction': calibrated['pinball_mw'] <= raw['pinball_mw']*(1-gates['minimum_pinball_reduction_pct']/100),
                  'pinball_vs_baseline': calibrated['pinball_mw'] <= baseline['pinball_mw']}
        for level in cfg['interval_levels']:
            checks[f'coverage_{level}'] = abs(calibrated[f'coverage_{level}']-level) <= gates['maximum_coverage_absolute_deviation']
            checks[f'width_{level}'] = calibrated[f'width_{level}_mw'] <= baseline[f'width_{level}_mw']*gates['maximum_width_ratio_to_probabilistic_baseline']
        decisions[target] = {'checks': checks, 'all_pass': all(checks.values()), 'operational_promotion': False}
    return decisions


def run_replay(config: dict, root: Path) -> dict:
    """Verify immutable proposal, sources and planned cases, save snapshot, then replay with no model calls."""
    cfg = config['hourly_calibration']
    if (cfg['execution_authorized'] is not True or cfg['new_inference_budget'] != 0
            or cfg['training_authorized'] is not False or cfg['downloads_authorized'] is not False):
        raise RuntimeError('Autorizzato soltanto replay con zero inferenze, training e download.')
    protocol_dir, out = root/cfg['protocol_directory'], root/cfg['output_directory']
    verify_manifest(protocol_dir)
    proposal = json.loads((protocol_dir/'proposal.json').read_text(encoding='utf-8-sig'))
    mutable = {'status', 'execution_authorized'}
    if {k:v for k,v in cfg.items() if k not in mutable} != {k:v for k,v in proposal['settings'].items() if k not in mutable}:
        raise ValueError('Impostazioni diverse dal protocollo approvato.')
    if out.exists():
        raise FileExistsError('Output esistente: nessuna sovrascrittura.')
    raw_rows, evaluation_rows, input_hashes, snapshots = [], None, {}, []
    for path in cfg['source_directories']:
        folder = root/path
        verify_manifest(folder)
        digest = sha256((folder/'manifest.json').read_bytes()).hexdigest()
        expected = next(s['manifest_sha256'] for s in proposal['sources'] if s['directory'] == path)
        if digest != expected:
            raise ValueError('Sorgente diversa da quella pianificata.')
        input_hashes[path] = digest
        snapshots.append(json.loads((folder/'snapshot.json').read_text(encoding='utf-8')))
        rows = json.loads((folder/'predictions.json').read_text(encoding='utf-8'))
        raw_rows += [r for r in rows if r['model'] == cfg['source_model']]
        if path == cfg['evaluation_source_directory']:
            evaluation_rows = rows
    if (evaluation_rows is None or snapshots[0]['model'] != snapshots[1]['model']
            or snapshots[0]['source_manifest_sha256'] != snapshots[1]['source_manifest_sha256']):
        raise ValueError('Dati o impostazioni del modello incoerenti.')
    for snapshot in snapshots:
        settings = snapshot['settings']
        if (settings['assumed_delay_hours'] != cfg['assumed_delay_hours']
                or settings['horizon_hours'] != cfg['horizon_hours'] or settings['quantiles'] != cfg['quantiles']):
            raise ValueError('Ritardo, orizzonte o quantili incompatibili.')
    selected = [r for r in evaluation_rows if r['model'] == cfg['source_model'] and r['target'] in cfg['targets']
                and pd.Timestamp(cfg['evaluation_start_utc']) <= pd.Timestamp(r['origin']) < pd.Timestamp(cfg['evaluation_end_exclusive_utc'])]
    # Plan checks use timestamps only; no real calibration scores before the persisted snapshot.
    for target in cfg['targets']:
        eligible = [r['origin'] for r in selected if r['target'] == target and len(available_history(raw_rows, r, cfg)) >= cfg['minimum_complete_origins']]
        if sorted(eligible) != sorted(r['origin'] for r in proposal['plan'][target]['eligible_origins']):
            raise ValueError('Origini diverse dal piano: nessun cambio del campione.')
    out.mkdir(parents=True)
    state = {'settings': cfg, 'input_manifests': input_hashes, 'approved_by': 'user procedi pure, 2026-11-15',
             'proposal_sha256': sha256((protocol_dir/'proposal.json').read_bytes()).hexdigest(),
             'implementation_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
             'model_settings': snapshots[0]['model'], 'plan': proposal['plan']}
    snapshot_path = out/'settings_before_fit.json'
    snapshot_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
    snapshot_hash = sha256(snapshot_path.read_bytes()).hexdigest()
    transformed, trace = replay(raw_rows, selected, cfg)
    common = {(r['target'], r['origin']) for r in transformed}
    comparison = deepcopy([r for r in evaluation_rows if (r['target'], r['origin']) in common]) + transformed
    summary = summarize(comparison, cfg)
    decisions = assess(summary, comparison, cfg)
    result = {'status': 'complete', 'kind': 'exploratory_causal_hourly_calibration', 'settings': cfg,
              'summary': summary, 'decisions': decisions, 'trace': trace,
              'original_exclusions': {t:proposal['plan'][t]['original_exclusions_in_period'] for t in cfg['targets']},
              'new_inferences': 0, 'weight_updates': 0, 'downloads': 0, 'independent_test': False,
              'operational_promotion': False, 'snapshot_sha256': snapshot_hash}
    if sha256(snapshot_path.read_bytes()).hexdigest() != snapshot_hash:
        raise ValueError('Snapshot modificato durante il fit.')
    for path, digest in input_hashes.items():
        if sha256((root/path/'manifest.json').read_bytes()).hexdigest() != digest:
            raise ValueError('Input modificato durante il replay.')
    (out/'predictions.json').write_text(json.dumps(comparison, indent=2, allow_nan=False), encoding='utf-8')
    (out/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    for target in cfg['targets']:
        (out/f'{target}_diagnostics.svg').write_text(diagnostic_chart(summary[target], cfg), encoding='utf-8')
    (out/'presentazione.html').write_text(render_report(result), encoding='utf-8')
    hashes = {p.name:sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out/'manifest.json').write_text(json.dumps({'status':'complete', 'files_sha256':hashes}, indent=2), encoding='utf-8')
    return result


def diagnostic_chart(data: dict, cfg: dict) -> str:
    """Export paired daily coverage and interval width to an inspectable standalone SVG."""
    raw = data['details'][cfg['source_model']]['daily']
    calibrated = data['details'][cfg['source_model']+'__additive_calibrated']['daily']
    dates = pd.to_datetime([r['origin'] for r in raw], utc=True)
    fig = Figure(figsize=(12, 7), layout='constrained')
    axes = fig.subplots(2, 2)
    for column, level in enumerate(cfg['interval_levels']):
        for row, key in enumerate((f'coverage_{level}', f'width_{level}_mw')):
            axis = axes[row, column]
            multiplier = 100 if row == 0 else 1
            axis.plot(dates, [r[key]*multiplier for r in raw], label='Grezzo', color='#687b83')
            axis.plot(dates, [r[key]*multiplier for r in calibrated], label='Calibrato', color='#087e8b')
            if row == 0:
                axis.axhline(level*100, linestyle='--', color='#b9760c', label='Nominale')
                axis.set_ylim(0, 103)
            axis.set_title(f'{"Copertura" if row == 0 else "Ampiezza"} {level:.0%}')
            axis.set_ylabel('% delle ore del giorno' if row == 0 else 'MW')
            axis.grid(alpha=.2)
            axis.legend(fontsize=8)
            axis.tick_params(axis='x', labelrotation=25)
    buffer = StringIO()
    fig.savefig(buffer, format='svg', metadata={'Date':None})
    return buffer.getvalue()


def render_report(result: dict) -> str:
    """Explain paired before/after scores, failures, exclusions and diagnostics in Italian."""
    def fmt(value: object) -> str:
        """Display undefined metrics without substituting zeros."""
        return 'N/D' if value is None else f'{value:,.2f}'.translate(str.maketrans(',.', '.,'))
    cfg = result['settings']
    candidate = cfg['source_model']+'__additive_calibrated'
    labels = {cfg['source_model']:'5M grezzo', candidate:'5M calibrato', 'persistence':'Persistenza',
              'hour_of_day_distribution':'Distribuzione stessa ora', 'lag_48h':'Stessa ora 48h prima', 'lag_168h':'Settimana precedente'}
    metric_names = {'mae_mw':'MAE MW', 'rmse_mw':'RMSE MW', 'bias_mw':'Bias MW', 'pinball_mw':'Pinball MW',
                    'coverage_0.8':'Copertura80 %', 'width_0.8_mw':'Ampiezza80 MW',
                    'coverage_0.9':'Copertura90 %', 'width_0.9_mw':'Ampiezza90 MW'}
    sections = []
    for target, data in result['summary'].items():
        title = 'Solare' if target == 'solar' else 'Eolico terra + mare'
        models = data['models']
        before, after = models[cfg['source_model']], models[candidate]
        probabilistic = models['hour_of_day_distribution']
        raw_change = 100*(after['pinball_mw']/before['pinball_mw']-1) if before['pinball_mw'] else None
        baseline_change = 100*(after['pinball_mw']/probabilistic['pinball_mw']-1) if probabilistic['pinball_mw'] else None
        paired = []
        for key, name in metric_names.items():
            a,b = after[key], before[key]
            is_cov = key.startswith('coverage')
            delta, percent = a-b, 100*(a-b)/b if b else None
            delta_label = fmt(100*delta)+' punti percentuali' if is_cov else fmt(delta)
            tone = 'neutral' if is_cov or key == 'bias_mw' or delta == 0 else 'good' if delta < 0 else 'bad'
            paired.append(f'<tr class="{tone}"><td>{name}</td><td>{fmt(100*b if is_cov else b)}</td><td>{fmt(100*a if is_cov else a)}</td><td>{delta_label}</td><td>{fmt(percent)}</td></tr>')
        all_models = []
        for name, m in models.items():
            values = [labels.get(name,name), str(m['origins']), str(m['cases'])]
            for key in metric_names:
                v = m.get(key)
                values.append(fmt(v*100 if v is not None and key.startswith('coverage') else v))
            all_models.append('<tr>'+''.join('<td>'+escape(v)+'</td>' for v in values)+'</tr>')
        baseline_deltas = []
        for key, name in metric_names.items():
            a,b = after[key], probabilistic[key]
            delta = a-b
            is_cov = key.startswith('coverage')
            relative = 100*delta/b if b else None
            baseline_deltas.append('<tr><td>'+name+'</td><td>'+fmt(100*b if is_cov else b)+'</td><td>'+fmt(100*a if is_cov else a)
                                   +'</td><td>'+fmt(100*delta if is_cov else delta)+(' punti percentuali' if is_cov else '')
                                   +'</td><td>'+fmt(relative)+'</td></tr>')
        gate_labels = {'minimum_origins':'Almeno30giornate', 'point_predictions_unchanged':'Punti e mediane identici',
                       'point_metrics_unchanged':'MAE/RMSE/bias invariati', 'pinball_reduction':'Pinball almeno -5% rispetto al grezzo',
                       'pinball_vs_baseline':'Pinball non peggiore della baseline probabilistica',
                       'coverage_0.8':'Copertura80 entro5punti dal nominale', 'coverage_0.9':'Copertura90 entro5punti dal nominale',
                       'width_0.8':'Ampiezza80 entro110% della baseline', 'width_0.9':'Ampiezza90 entro110% della baseline'}
        gates = ''.join(f'<tr class="{"good" if value else "bad"}"><td>{gate_labels[key]}</td><td>{"SUPERATO" if value else "FALLITO"}</td></tr>' for key,value in result['decisions'][target]['checks'].items())
        diagnostics = []
        for group in ('daily','by_month','by_forecast_hour'):
            left,right = data['details'][cfg['source_model']][group],data['details'][candidate][group]
            pairs = [(r['origin'], r, right[i]) for i,r in enumerate(left)] if group == 'daily' else [(k,v,right[k]) for k,v in left.items()]
            table = ''.join('<tr><td>'+escape(k)+'</td>'+''.join('<td>'+fmt(m.get(metric))+'</td>' for m in (b,a) for metric in ('pinball_mw','coverage_0.8','width_0.8_mw','coverage_0.9','width_0.9_mw'))+'</tr>' for k,b,a in pairs)
            group_title = {'daily':'Per giornata', 'by_month':'Per mese', 'by_forecast_hour':'Per ora prevista (0–23 UTC)'}[group]
            diagnostics.append(f'<details><summary>{group_title}</summary><p>Prima cinque colonne: grezzo; dopo cinque: calibrato. Copertura qui come proporzione 0–1.</p><div class="scroll"><table><tr><th>Gruppo</th><th>Pinball prima</th><th>C80 prima</th><th>A80 prima</th><th>C90 prima</th><th>A90 prima</th><th>Pinball dopo</th><th>C80 dopo</th><th>A80 dopo</th><th>C90 dopo</th><th>A90 dopo</th></tr>{table}</table></div></details>')
        trace = [r for r in result['trace'] if r['target'] == target]
        trace_rows = ''.join('<tr><td>'+escape(r['origin'][:10])+'</td><td>'+str(r['complete_past_days'])+'</td><td>'+r['status']+'</td><td>'+fmt(r.get('corrections_mw',{}).get('0.8'))+'</td><td>'+fmt(r.get('corrections_mw',{}).get('0.9'))+'</td></tr>' for r in trace)
        excluded = [r['origin'] for r in trace if r['status'] != 'calibrated']
        status = 'Tutti i criteri superati, solo in senso esplorativo' if result['decisions'][target]['all_pass'] else 'Criteri non tutti superati: nessuna promozione'
        sections.append(f'''<section><h2>{title}</h2><p><strong>{status}</strong>. {after['origins']} giornate comuni, {after['cases']} ore. Coperture osservate:80% {fmt(100*after['coverage_0.8'])}% ({round(after['coverage_0.8']*after['cases'])}/{after['cases']}),90% {fmt(100*after['coverage_0.9'])}% ({round(after['coverage_0.9']*after['cases'])}/{after['cases']}).</p>
<p>Pinball dopo calibrazione: {fmt(raw_change)}% rispetto al grezzo e {fmt(baseline_change)}% rispetto alla baseline probabilistica. Le previsioni centrali sono identiche: un diverso MAE rispetto ai vecchi riepiloghi dipende dal sottoinsieme valutato, non dalla calibrazione.</p>
<h3>Prima / dopo sugli stessi casi</h3><div class="scroll"><table><tr><th>Metrica</th><th>Grezzo</th><th>Calibrato</th><th>Delta assoluto</th><th>Delta relativo %</th></tr>{''.join(paired)}</table></div><p>Copertura: valutare vicinanza al nominale, non semplicemente un aumento. Ampiezze maggiori sono il costo della copertura; controllare pinball e baseline insieme.</p>
<h3>Tutti i riferimenti sugli stessi giorni</h3><div class="scroll"><table><tr><th>Metodo</th><th>Giorni</th><th>Ore</th>{''.join('<th>'+v+'</th>' for v in metric_names.values())}</tr>{''.join(all_models)}</table></div>
<details><summary>Differenze rispetto alla baseline probabilistica</summary><div class="scroll"><table><tr><th>Metrica</th><th>Baseline</th><th>Calibrato</th><th>Delta assoluto</th><th>Delta %</th></tr>{''.join(baseline_deltas)}</table></div></details>
<h3>Criteri fissati prima del fit</h3><div class="scroll"><table><tr><th>Criterio</th><th>Esito</th></tr>{gates}</table></div>
<h3>Copertura e ampiezza per giornata</h3><img style="width:100%;height:auto" src="{target}_diagnostics.svg" alt="Confronto grezzo e calibrato: coperture e ampiezze per ogni giornata {title}"><p>Ogni punto riassume una giornata di24ore; il grafico non implica indipendenza tra le ore o i giorni.</p>
<h3>Diagnostica dettagliata</h3>{''.join(diagnostics)}<details><summary>Traccia e origini escluse</summary><p>Esclusioni per storico insufficiente: {escape(str(excluded))}. Esclusioni originali: {escape(str(result['original_exclusions'][target]))}.</p><div class="scroll"><table><tr><th>Giorno</th><th>Storico completo</th><th>Stato</th><th>Correzione80 MW</th><th>Correzione90 MW</th></tr>{trace_rows}</table></div></details></section>''')
    return f'''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SolarWindCast · Calibrazione oraria: risultati</title>
<style>body{{font:16px/1.6 system-ui;background:#edf2f2;color:#20383c;margin:0}}main{{max-width:1250px;margin:auto;padding:20px}}header,section{{padding:24px;background:white;border-radius:16px;margin:20px 0;overflow-wrap:anywhere}}header{{background:#123e46;color:white}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:900px}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}.note{{background:#fff2dc;padding:18px}}.good{{background:#edf8f0}}.bad{{background:#fff0ed}}summary{{cursor:pointer;font-weight:bold;margin:12px 0}}</style>
<main><header><h1>Calibrazione degli intervalli orari: risultati</h1><p>Sud · solare ed eolico terra + mare · 5M invariato · 15novembre2026</p></header><p class="note">Zero nuove inferenze, training o download. Replay causale dei forecast salvati, con mediana invariata. Stessi dati e periodi già esaminati: solo esplorativo, nessuna garanzia conformale o promozione operativa automatica.</p>
<section><h2>Come leggere il confronto</h2><p>Origini1,8,22 da maggio2025 a ottobre2026. Finestra mobile180giorni e minimo20giornate complete, disponibili solo dopo fine del giorno più24ore di ritardo assunto. Il giorno15 alimenta solo lo storico quando disponibile. Due correzioni additive nonnegative, senza cambiare il punto o scegliere parametri dopo gli esiti.</p><p>Le tabelle usano esclusivamente gli stessi casi per grezzo, calibrato e baseline; non confrontarle direttamente con i vecchi riepiloghi di69/72giorni. Le ore sono correlate, non prove indipendenti. Nessuna somma dei quantili orari per dichiarare intervalli dell'energia giornaliera.</p></section>
{''.join(sections)}<section><h2>Provenienza</h2><p>Parametri e hash salvati prima del fit. Disponibilità ricostruita con ritardo assunto, non certificata dai tempi storici di pubblicazione. Osservazioni revisionate, nessuna interpolazione, clipping o sostituzione delle origini.</p><p><a href="results.json">Metriche, tracce e decisioni</a> · <a href="predictions.json">Previsioni prima/dopo</a> · <a href="settings_before_fit.json">Snapshot prima del fit</a> · <a href="../hourly_calibration_protocol_20261115/presentazione.html">Protocollo approvato</a></p></section></main></html>'''


def main() -> None:
    """Execute the explicitly approved zero-inference calibration replay once."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding='utf-8'))
    result = run_replay(config, args.config.resolve().parent.parent)
    for target, data in result['summary'].items():
        print(target, json.dumps(data['models'], indent=2))
    print(json.dumps(result['decisions'], indent=2))


if __name__ == '__main__':
    main()
