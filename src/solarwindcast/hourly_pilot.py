"""Small prespecified real-data hourly pilot, with delayed inputs and matched baselines."""

import argparse
import json
from hashlib import sha256
from html import escape
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.monthly_improvement import verify_manifest
from solarwindcast.timestral_model import TimestralSettings, TimestralWrapper


def baseline_arrays(series: pd.Series, origin: pd.Timestamp, cfg: dict) -> dict:
    """Use only intervals whose end plus assumed publication delay precedes issue time."""
    step = pd.Timedelta(hours=1)
    past = series.loc[series.index + step + pd.Timedelta(hours=cfg['assumed_delay_hours']) <= origin].tail(cfg['context_hours'])
    future = pd.date_range(origin, periods=cfg['horizon_hours'], freq='h')
    if len(past) != cfg['context_hours'] or past.isna().any():
        raise ValueError('Contesto incompleto: nessuna imputazione.')
    result = {'persistence': np.repeat(past.iloc[-1], len(future))}
    for lag in cfg['seasonal_lags_hours']:
        dates = future - pd.Timedelta(hours=lag)
        if dates.max() > past.index.max() or not dates.isin(past.index).all():
            raise ValueError('Baseline richiede dati non disponibili al cutoff.')
        result[f'lag_{lag}h'] = past.reindex(dates).to_numpy()
    quantiles = []
    for stamp in future:
        values = past.loc[past.index.hour == stamp.hour]
        if len(values) < cfg['minimum_hour_samples']:
            raise ValueError('Campione orario insufficiente.')
        quantiles.append(np.quantile(values, cfg['quantiles']))
    result['hour_of_day_distribution'] = np.asarray(quantiles)
    return result


def metrics(actual: np.ndarray, point: np.ndarray, quantiles: np.ndarray | None, cfg: dict) -> dict:
    """Evaluate hourly MW, never interpreting marginal quantiles as daily energy quantiles."""
    error = point - actual
    result = {'cases': len(actual), 'mae_mw': float(np.abs(error).mean()),
              'rmse_mw': float(np.sqrt(np.mean(error**2))), 'bias_mw': float(error.mean())}
    if quantiles is not None:
        levels = cfg['quantiles']
        residual = actual[:, None] - quantiles
        result['pinball_mw'] = float(np.maximum(residual * np.asarray(levels), residual * (np.asarray(levels)-1)).mean())
        for level in cfg['interval_levels']:
            lo, hi = round((1-level)/2, 5), round((1+level)/2, 5)
            lower, upper = quantiles[:, levels.index(lo)], quantiles[:, levels.index(hi)]
            result[f'coverage_{level}'] = float(((actual >= lower) & (actual <= upper)).mean())
            result[f'width_{level}_mw'] = float((upper-lower).mean())
    return result


def run(config: dict, root: Path) -> dict:
    """Save settings before inference, enforce budget and preserve every chosen origin."""
    cfg, pinned = config['hourly_pilot'], config['monthly_protocol']
    if cfg['authorized'] is not True:
        raise RuntimeError('Pilota non autorizzato.')
    out, source = root/cfg['output'], root/cfg['source']
    if out.exists():
        raise FileExistsError('Output esistente.')
    verify_manifest(source)
    origins = planned_origins(cfg)
    if len(origins)*len(cfg['targets']) > cfg['maximum_inferences']:
        raise ValueError('Budget insufficiente.')
    spec = next(m for m in pinned['models'] if m['size'] == cfg['model_size'])
    settings = TimestralSettings(cfg['model_size'], 'mistralai/Timestral-'+cfg['model_size'],
        spec['revision'], pinned['code_revision'], pinned['package_version'], cfg['device'],
        cfg['context_hours'], cfg['horizon_hours'], f"{cfg['assumed_delay_hours']}h", 'target_only',
        'reject', False, False, 0., 1, 1e30, True, True)
    import torch

    torch.set_num_threads(cfg['cpu_threads'])
    model = TimestralWrapper(settings)
    out.mkdir(parents=True)
    snapshot = {'settings': cfg, 'model': settings.__dict__,
                'source_manifest_sha256': sha256((source/'manifest.json').read_bytes()).hexdigest(),
                'note': 'Exploratory revised-data pilot; delay assumed; no weather; no independent test'}
    (out/'snapshot.json').write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
    rows, skipped, provenance = [], [], None
    calls = 0
    for target, components in cfg['targets'].items():
        frame = pd.concat([pd.read_parquet(source/f'{c}.parquet').target for c in components], axis=1)
        series = frame.sum(axis=1, min_count=len(components))
        ds = TimeSeriesDataset(series.to_frame('target'), DatasetSpec(target, '1h', (), (), (), str(source)))
        for origin in origins:
            idx = pd.date_range(origin, periods=cfg['horizon_hours'], freq='h')
            actual = series.reindex(idx)
            try:
                bases = baseline_arrays(series, origin, cfg)
                if actual.isna().any():
                    raise ValueError('Target incompleto.')
            except ValueError as exc:
                skipped.append({'target': target, 'origin': origin.isoformat(), 'reason': str(exc)})
                continue
            forecast = model.predict(ds, origin.isoformat())
            calls += 1
            provenance = forecast.metadata
            predictions = {**bases, 'timestral_'+cfg['model_size']: forecast.quantiles[cfg['quantiles']].to_numpy()}
            for name, values in predictions.items():
                quantiles = values if values.ndim == 2 else None
                point = values[:, cfg['quantiles'].index(.5)] if quantiles is not None else values
                rows.append({'target': target, 'origin': origin.isoformat(), 'model': name,
                             'actual': actual.tolist(), 'point': point.tolist(),
                             'quantiles': quantiles.tolist() if quantiles is not None else None,
                             'metrics': metrics(actual.to_numpy(), point, quantiles, cfg)})
            print(f'{calls}/{cfg["maximum_inferences"]}: {target} {origin.date()}', flush=True)
    summary = {}
    for target in cfg['targets']:
        summary[target] = {}
        for name in sorted({r['model'] for r in rows if r['target'] == target}):
            subset = [r for r in rows if r['target'] == target and r['model'] == name]
            q = np.concatenate([r['quantiles'] for r in subset]) if subset[0]['quantiles'] is not None else None
            summary[target][name] = metrics(np.concatenate([r['actual'] for r in subset]),
                                           np.concatenate([r['point'] for r in subset]), q, cfg)
            summary[target][name]['origins'] = len(subset)
    result = {'settings': cfg, 'summary': summary, 'skipped': skipped, 'new_inferences': calls,
              'model_provenance': provenance, 'independent_test': False, 'operational_promotion': False}
    (out/'predictions.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    (out/'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (out/'presentazione.html').write_text(render(result, rows), encoding='utf-8')
    hashes = {p.name: sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
    (out/'manifest.json').write_text(json.dumps({'status': 'complete', 'files_sha256': hashes}, indent=2), encoding='utf-8')
    return result


def planned_origins(cfg: dict) -> list[pd.Timestamp]:
    """Select unique calendar dates before looking at outcomes, refusing duplicate days."""
    days = cfg.get('days_of_month', [cfg.get('day_of_month')])
    if not days or len(set(days)) != len(days) or any(not isinstance(d, int) or not 1 <= d <= 28 for d in days):
        raise ValueError('Giorni univoci tra 1 e 28 obbligatori.')
    return [pd.Timestamp(f'{m}-{d:02}T00:00:00Z')
            for m in pd.period_range(cfg['first_month'], cfg['last_month'], freq='M') for d in sorted(days)]


def render(result: dict, rows: list[dict]) -> str:
    """Explain matched baseline skill and hourly interval quality in an offline HTML report."""
    def fmt(v: object) -> str:
        """Format missing metrics explicitly."""
        return 'N/D' if v is None else f'{v:,.2f}'.translate(str.maketrans(',.', '.,'))
    sections = []
    for target, scores in result['summary'].items():
        best = min((n for n in scores if not n.startswith('timestral')), key=lambda n: scores[n]['mae_mw'])
        candidate = 'timestral_'+result['settings']['model_size']
        baseline, model = scores[best], scores[candidate]
        change = 100*(model['mae_mw']/baseline['mae_mw']-1)
        deltas = []
        for key in ('mae_mw', 'rmse_mw', 'pinball_mw', 'coverage_0.8', 'width_0.8_mw', 'coverage_0.9', 'width_0.9_mw'):
            a, b = model.get(key), baseline.get(key)
            delta = a-b if a is not None and b is not None else None
            relative = 100*delta/b if delta is not None and b else None
            deltas.append(f'<tr><td>{key}</td><td>{fmt(b)}</td><td>{fmt(a)}</td><td>{fmt(delta)}</td><td>{fmt(relative)}</td></tr>')
        sections.append(f'<section><h2>{target}: differenze rispetto a {best}</h2><div class="scroll"><table><tr><th>Metrica</th><th>Baseline</th><th>Timestral</th><th>Delta assoluto</th><th>Delta %</th></tr>{"".join(deltas)}</table></div><p>Coperture espresse come proporzioni: moltiplicare il delta assoluto per100 per ottenere punti percentuali. Non sono variazioni rispetto al vecchio esperimento mensile.</p></section>')
        table = ''.join('<tr><td>'+escape(name)+'</td><td>'+str(s['cases'])+'</td>'+
            ''.join('<td>'+fmt(s.get(k))+'</td>' for k in ('mae_mw','rmse_mw','pinball_mw','coverage_0.8','width_0.8_mw','coverage_0.9','width_0.9_mw'))+'</tr>' for name,s in scores.items())
        monthly = []
        for r in rows:
            if r['target'] != target or r['model'] != candidate:
                continue
            b = next(v for v in rows if v['target']==target and v['origin']==r['origin'] and v['model']==best)
            delta = r['metrics']['mae_mw']-b['metrics']['mae_mw']
            monthly.append(f'<tr><td>{r["origin"][:10]}</td><td>{fmt(b["metrics"]["mae_mw"])}</td><td>{fmt(r["metrics"]["mae_mw"])}</td><td>{fmt(delta)}</td><td>{"migliora" if delta<0 else "peggiora" if delta>0 else "pari"}</td></tr>')
        sections.append(f'<section><h2>{target}</h2><p>{model["origins"]} giornate, {model["cases"]} ore. Migliore baseline descrittiva: {best}. MAE baseline {fmt(baseline["mae_mw"])} → Timestral {fmt(model["mae_mw"])} MW; differenza {fmt(model["mae_mw"]-baseline["mae_mw"])} MW ({fmt(change)}%). Negativo significa miglioramento.</p><div class="scroll"><table><tr><th>Modello</th><th>Ore</th><th>MAE MW</th><th>RMSE MW</th><th>Pinball MW</th><th>Copertura80 (0–1)</th><th>Ampiezza80 MW</th><th>Copertura90 (0–1)</th><th>Ampiezza90 MW</th></tr>{table}</table></div><h3>Confronto giorno per giorno</h3><div class="scroll"><table><tr><th>Origine UTC</th><th>MAE baseline MW</th><th>MAE Timestral MW</th><th>Delta MW</th><th>Esito</th></tr>{"".join(monthly)}</table></div></section>')
    return f'''<!doctype html><html lang="it"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SolarWindCast · Pilota 24 ore</title><style>body{{font:16px/1.6 system-ui;background:#edf2f2;color:#17343b;margin:0}}main{{max-width:1150px;margin:auto;padding:20px}}header,section{{background:white;padding:24px;margin:20px 0;border-radius:15px;overflow-wrap:anywhere}}header{{background:#123e46;color:white}}.scroll{{overflow:auto}}table{{border-collapse:collapse;min-width:850px;width:100%}}td,th{{padding:10px;border-bottom:1px solid #ddd;text-align:left}}</style><main><header><h1>Pilota sulle prossime 24 ore</h1><p>Sud · solare ed eolico terra + mare · Timestral5M senza meteo</p></header><section><h2>Disegno fissato prima del test</h2><p>Giorno15 di ciascun mese novembre2024–ottobre2026, emissione00UTC. Contesto28giorni, ritardo dati assunto24ore: si prevedono48ore e si valutano le ultime24. {result['new_inferences']} inferenze locali, nessun download o training. Le scelte sono parametri del pilota, non nuovi standard operativi.</p><p>Baseline: ultimo valore disponibile, stessa ora48ore prima, stessa ora settimana precedente, distribuzione empirica della stessa ora nei28giorni disponibili. Quest'ultima è un riferimento probabilistico semplice, non una calibrazione degli errori. Tutti usano lo stesso cutoff.</p><p>Le ore dello stesso giorno sono correlate: non sono centinaia di test indipendenti. Giorni prestabiliti, non campionamento esaustivo. Dati revisionati, disponibilità storica non certificata, mesi già studiati: solo evidenza esplorativa. Esclusioni: {escape(str(result['skipped']))}.</p></section>{''.join(sections)}<section><h2>Come interpretare il confronto</h2><p>MAE/RMSE/pinball inferiori sono preferibili; copertura va confrontata con80/90% e ampiezza. Nessun confronto diretto tra questi errori in MW e gli errori mensili in MWh. Nessuna somma dei quantili orari per inventare intervalli giornalieri. Nessuna promozione automatica.</p><p><a href="results.json">Metriche e provenienza</a> · <a href="predictions.json">Tutte le ore previste</a> · <a href="snapshot.json">Scelte prima delle inferenze</a></p></section></main></html>'''


def main() -> None:
    """Execute the configured limited pilot once into a new output folder."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    result = run(yaml.safe_load(args.config.read_text(encoding='utf-8')), args.config.resolve().parent.parent)
    print(json.dumps(result['summary'], indent=2))


if __name__ == '__main__':
    main()
