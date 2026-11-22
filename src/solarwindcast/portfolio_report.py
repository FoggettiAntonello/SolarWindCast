"""Build a portable evidence report from verified aggregate metrics, without running models."""

import argparse
import json
from hashlib import sha256
from html import escape
from pathlib import Path

import yaml

from solarwindcast.monthly_improvement import verify_manifest
from solarwindcast.portfolio_slides import render_slides


def normalize_models(models: dict, kind: str) -> dict:
    """Retain every baseline and model, with explicit units supplied by the study."""
    normalized = {}
    for name, row in models.items():
        if kind in ('hourly', 'calibration'):
            item = {'cases':row['cases'], 'origins':row['origins'], 'mae':row['mae_mw'],
                    'rmse':row['rmse_mw'], 'bias':row['bias_mw'], 'pinball':row.get('pinball_mw'),
                    'quantile_cases':row['cases'] if 'pinball_mw' in row else None}
            for level in ('0.8', '0.9'):
                item['coverage_'+level] = row.get('coverage_'+level)
                item['width_'+level] = row.get('width_'+level+'_mw')
        else:
            item = {'cases':row['point_cases'], 'origins':row['issued_forecasts'],
                    'mae':row['point_scores']['mae_mwh'], 'rmse':row['point_scores']['rmse_mwh'],
                    'bias':row['point_scores']['bias_mwh'], 'pinball':row.get('pinball_mwh'),
                    'quantile_cases':row.get('quantile_cases')}
            for level in ('0.8', '0.9'):
                interval = row.get('intervals', {}).get(level, {})
                item['coverage_'+level] = interval.get('coverage')
                item['width_'+level] = interval.get('mean_width_mwh')
        normalized[name] = item
    return normalized


def summarize_source(result: dict, source: dict) -> dict:
    """Extract aggregate evidence only; exclude raw observations and machine-specific metadata."""
    kind = source['kind']
    study = {k:source[k] for k in ('id','title','kind','period','unit')}
    if kind == 'hourly':
        study['targets'] = {t:normalize_models(models, kind) for t,models in result['summary'].items()}
        study['exclusions'] = result['skipped']
    elif kind == 'calibration':
        study['targets'] = {t:normalize_models(data['models'], kind) for t,data in result['summary'].items()}
        study['decisions'] = result['decisions']
        study['excluded_for_history'] = {t:sum(r['target']==t and r['status']!='calibrated' for r in result['trace']) for t in study['targets']}
        study['original_exclusions'] = result['original_exclusions']
    elif kind == 'monthly':
        study['targets'] = {t:normalize_models(data['test']['models'], kind) for t,data in result['scores'].items()}
        study['development'] = {t:normalize_models(data['development']['models'], kind) for t,data in result['scores'].items()}
        study['excluded_point_timestamps'] = {t:sorted({s for m in data['test']['models'].values() for s in m['point_excluded_utc']}) for t,data in result['scores'].items()}
    elif kind == 'final_monthly':
        study['targets'] = {result['settings']['target']:normalize_models(result['scores']['models'], kind)}
        study['decision'] = result['assessment']
    elif kind in ('context_screen', 'development'):
        source_scores = result['development_scores'] if kind == 'context_screen' else result['scores']
        study['targets'] = {t:normalize_models(data['development']['models'], kind) for t,data in source_scores.items()}
        study['evaluation_phase'] = 'development_only_not_independent_test'
    else:
        raise ValueError('Tipo di studio sconosciuto.')
    return study


def build_bundle(config: dict, root: Path) -> dict:
    """Verify existing manifests and derive explicitly scoped claims without choosing new models."""
    cfg = config['release_v1']
    studies, provenance = [], []
    for source in cfg['sources']:
        folder = root/source['directory']
        verify_manifest(folder)
        path = folder/'results.json'
        result = json.loads(path.read_text(encoding='utf-8'))
        studies.append(summarize_source(result, source))
        provenance.append({'study':source['id'], 'results_sha256':sha256(path.read_bytes()).hexdigest(),
                           'manifest_sha256':sha256((folder/'manifest.json').read_bytes()).hexdigest()})
    by_id = {s['id']:s for s in studies}
    highlights = []
    for target in ('solar','wind'):
        models = by_id['hourly_extension']['targets'][target]
        baseline = min((n for n in models if not n.startswith('timestral')), key=lambda n:models[n]['mae'])
        model = models['timestral_5M']
        reference = models[baseline]
        highlights.append({'study':'hourly_extension', 'target':target, 'metric':'mae', 'reference':baseline,
                           'before':reference['mae'], 'after':model['mae'],
                           'change_pct':100*(model['mae']/reference['mae']-1),
                           'origins':model['origins'], 'cases':model['cases']})
    models = by_id['hourly_calibration']['targets']['wind']
    raw, calibrated = models['timestral_5M'], models['timestral_5M__additive_calibrated']
    highlights.append({'study':'hourly_calibration', 'target':'wind', 'metric':'pinball', 'reference':'timestral_5M',
                       'before':raw['pinball'], 'after':calibrated['pinball'],
                       'change_pct':100*(calibrated['pinball']/raw['pinball']-1),
                       'origins':calibrated['origins'], 'cases':calibrated['cases']})
    return {'schema_version':1, 'generated_date':cfg['generated_date'], 'status':'release_candidate_documentation',
            'new_inferences':0, 'new_fits':0, 'operational_validation':False,
            'highlights':highlights, 'studies':studies, 'provenance':provenance}


def model_label(name: str) -> str:
    """Render baseline meaning and model size/context in plain language."""
    labels = {'persistence':'Persistenza', 'lag_48h':'Stessa ora 48h prima', 'lag_168h':'Settimana precedente',
              'hour_of_day_distribution':'Distribuzione della stessa ora', 'last_complete_month':'Ultimo mese completo',
              'recent_complete_months':'Media recente', 'same_month_previous_year':'Stesso mese anno precedente',
              'seasonal_empirical_rolling_errors':'Stagionale + errori passati'}
    if name in labels:
        return labels[name]
    text = 'Timestral '+name.split('_')[1]
    if 'known_calendar' in name:
        text += ' · calendario'
    elif 'target_only' in name:
        text += ' · solo target'
    if '__ctx' in name:
        text += ' · '+name.split('__ctx')[1].split('__')[0]+' mesi'
    if 'calibrated' in name:
        text += ' · calibrato'
    return text


def render(bundle: dict) -> str:
    """Present favorable evidence alongside nearby limitations and complete model tables."""
    def fmt(v: object) -> str:
        """Format Italian numbers and undefined scores."""
        return 'N/D' if v is None else f'{v:,.2f}'.translate(str.maketrans(',.','.,'))
    target_names = {'solar':'Solare','wind':'Eolico terra + mare','load':'Carico','residual_load':'Carico residuo'}
    cards = []
    for claim in bundle['highlights']:
        title = ('MAE '+target_names[claim['target']]+' · 24 ore' if claim['metric']=='mae' else 'Pinball eolica · calibrazione')
        cards.append(f'<article><p>{title}</p><strong>{fmt(claim["change_pct"])}%</strong><p>{claim["origins"]} giornate · {claim["cases"]} ore</p><p>Riferimento: {escape(model_label(claim["reference"]))}. {fmt(claim["before"])} → {fmt(claim["after"])} MW.</p></article>')
    metric_labels = {'mae':'MAE','rmse':'RMSE','bias':'Bias','pinball':'Pinball','coverage_0.8':'Copertura80',
                     'width_0.8':'Ampiezza80','coverage_0.9':'Copertura90','width_0.9':'Ampiezza90'}
    def model_table(models: dict, unit: str) -> str:
        """Retain losing models and meaningful denominators alongside winners."""
        table = []
        for name, m in models.items():
            values = [escape(model_label(name)),str(m['origins']),str(m['cases']),str(m['quantile_cases'] or 'N/D')]
            for key in metric_labels:
                value = m[key]
                values.append(fmt(100*value)+'%' if key.startswith('coverage') and value is not None else fmt(value))
            table.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
        return '<p>Metriche dimensionali in '+unit+'. Copertura osservata, non probabilità garantita.</p><div class="scroll"><table><tr><th>Metodo</th><th>Origini emesse</th><th>Casi puntuali</th><th>Casi quantili</th>'+''.join('<th>'+v+'</th>' for v in metric_labels.values())+'</tr>'+''.join(table)+'</table></div>'
    study_sections = []
    for study in bundle['studies']:
        targets = ''.join('<h4>'+target_names.get(t,t)+'</h4>'+model_table(models,study['unit']) for t,models in study['targets'].items())
        notes = ''
        if 'decisions' in study:
            notes = '<p class="warning">I criteri complessivi della calibrazione non sono tutti superati per entrambi i target.</p>'
        if 'decision' in study:
            notes = '<p class="warning">Ultimo candidato mensile: criteri non superati; nessuna promozione.</p>'
        if study.get('evaluation_phase') == 'development_only_not_independent_test':
            notes += '<p class="warning">Solo sviluppo: non confrontare questi punteggi con quelli dei periodi di test diversi. Le relative varianti non hanno ottenuto una promozione generale.</p>'
        exclusions = {k:study[k] for k in ('exclusions','excluded_for_history','original_exclusions','excluded_point_timestamps') if k in study}
        if exclusions:
            notes += '<details><summary>Esclusioni e numerosità</summary><pre>'+escape(json.dumps(exclusions,ensure_ascii=False,indent=2))+'</pre></details>'
        development = ''
        if 'development' in study:
            development = '<details><summary>Risultati dello sviluppo, separati dal test</summary>'+''.join('<h4>'+target_names[t]+'</h4>'+model_table(m,study['unit']) for t,m in study['development'].items())+'</details>'
        study_sections.append(f'<details class="study" id="{study["id"]}"><summary>{study["title"]}</summary><p>{study["period"]} · {study["unit"]}. Tutti i metodi sono conservati, compresi quelli peggiori.</p>{notes}{targets}{development}</details>')
    provenance_rows = ''.join('<tr><td>'+escape(p['study'])+'</td><td><code>'+p['results_sha256']+'</code></td></tr>' for p in bundle['provenance'])
    payload = json.dumps(bundle,ensure_ascii=False,allow_nan=False).replace('</','<\\/')
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SolarWindCast · Previsioni energetiche e valutazione</title>
<style>:root{{--ink:#193a44;--teal:#087e8b;--paper:#eef4f4}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:17px/1.65 system-ui}}main{{max-width:1180px;margin:auto;padding:clamp(16px,4vw,48px)}}header{{background:#123b47;color:white;padding:clamp(24px,5vw,56px);border-radius:22px}}h1{{font-size:clamp(30px,5vw,52px);line-height:1.12;max-width:900px}}h2{{line-height:1.3}}nav{{display:flex;gap:18px;flex-wrap:wrap;margin:22px 0}}a{{color:#086979}}section,.study{{background:white;border-radius:16px;padding:clamp(18px,3vw,28px);margin:22px 0}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin:22px 0}}article{{background:white;border-radius:16px;padding:22px;border-top:5px solid var(--teal)}}article strong{{font-size:38px;color:#086979}}.warning{{background:#fff1d9;border-left:5px solid #be8a26;padding:16px}}.scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:1050px}}th,td{{padding:10px;text-align:left;border-bottom:1px solid #dce5e6}}summary{{cursor:pointer;font-weight:700}}details details{{margin:16px 0}}pre,code{{white-space:pre-wrap;overflow-wrap:anywhere}}.muted{{color:#526c73}}li{{margin:8px 0}}.chart{{width:100%;height:auto;display:block}}</style></head><body><main>
<header><p>SolarWindCast · Progetto di forecasting energetico</p><h1>Prevedere la produzione rinnovabile. Misurare quando il modello aiuta.</h1><p>Solare ed eolico della zona di mercato Sud, con Timestral, baseline semplici e valutazione degli intervalli.</p><p>Stato: versione 1.0 in preparazione. Valutazione retrospettiva esplorativa; nessuna soluzione operativa certificata.</p></header>
<nav><a href="#evidence">Risultati in evidenza</a><a href="#method">Come funziona</a><a href="#complete">Valutazione completa</a><a href="#limits">Limiti</a><a href="../../README.md">Codice e avvio</a></nav>
<section id="evidence"><h2>Risultati favorevoli, con un perimetro preciso</h2><p>Su giornate prestabilite, Timestral 5M riduce l'errore centrale rispetto alla migliore baseline osservata nel campione. Una calibrazione successiva migliora la copertura degli intervalli eolici. Sono confronti distinti, con numerosità diverse.</p></section>
<div class="cards">{''.join(cards)}</div>
<p class="warning"><strong>Il compromesso è parte del risultato.</strong> Nel campione orario esteso la pinball del 5M grezzo è peggiore della baseline probabilistica (+18,70% solare, +24,02% eolico). Dopo calibrazione eolica la copertura 80/90 arriva al 79,32%/90,28%, ma la pinball resta peggiore della baseline (+7,91%) e l'ampiezza 90 è superiore del 37%. Nessuna promozione complessiva.</p>
<section id="method"><h2>Due domande, due valutazioni separate</h2><ul><li><strong>Mensile:</strong> energia totale del prossimo mese UTC in MWh, prevista direttamente e confrontata con baseline. La riduzione del contesto eolico a 12 mesi non ha superato il confronto finale.</li><li><strong>24 ore:</strong> potenza media oraria in MW, contesto 28 giorni, ritardo dati assunto24 ore. Pilota giorno 15, poi estensione giorni1/8/22. Nessun meteo reale nel pilota.</li><li><strong>Calibrazione:</strong> allarga i quantili laterali usando solo errori disponibili al cutoff; mediana e MAE restano identici sui casi comuni.</li></ul><h3>Che cosa spiega il risultato?</h3><p>È verificato che la correzione delle bande avvicina la copertura al nominale. Il ruolo di un contesto più dettagliato e dell'orizzonte più breve è un'ipotesi plausibile: gli esperimenti non isolano una causa del vantaggio. Il MAE orario non si confronta direttamente con quello mensile.</p><p>Gli intervalli sono marginali per ora: non si sommano quantili orari per dichiarare intervalli del totale giornaliero o mensile.</p></section>
<section id="complete"><h2>Valutazione completa</h2><p>Apri ogni confronto per vedere tutte le baseline e varianti. Le migliori nel test sono riepiloghi descrittivi; non sono automaticamente selezioni effettuate prima degli esiti. Metriche di sviluppo e test restano separate.</p><p>Più basso è preferibile per MAE, RMSE e pinball. Bias vicino a zero; coperture da leggere rispetto al nominale e insieme alle ampiezze. I mesi e le giornate sono correlati: i conteggi di ore non sono prove indipendenti.</p>{''.join(study_sections)}</section>
<section id="limits"><h2>Limiti che restano visibili</h2><ul><li>Zona Sud, non sola Puglia. La macroarea Sud+Calabria è un'estensione dei dati, non la geografia di questi risultati.</li><li>Dati energetici revisionati. Il ritardo24 ore è un'ipotesi, non una ricostruzione delle pubblicazioni storiche.</li><li>Periodi già esaminati e pochi giorni per mese: verifica esplorativa. Non abbiamo una conferma prospettica indipendente.</li><li>Sul sottoinsieme della calibrazione solare il MAE del 5M non batte la baseline: il vantaggio non è uniforme.</li><li>Intervalli corretti possono essere troppo ampi; nessuna garanzia conformale automatica per serie correlate.</li><li>Nessun risparmio economico aziendale misurato. I benchmark pubblicati da Mistral non sono risultati SolarWindCast.</li></ul></section>
<section><h2>Riproducibilità e provenienza</h2><p>Configurazione unica, cutoff espliciti, originali conservati e sorgenti verificate tramite SHA-256. Questa pagina contiene soltanto statistiche aggregate; non incorpora token, dati grezzi o percorsi del computer.</p><p><a href="index.html">Presentazione in 12 slide</a> · <a href="metrics.json">Metriche aggregate complete (JSON)</a> · <a href="../../configs/project.yaml">Configurazione</a> · <a href="../../docs/setup.md">Setup</a></p><p class="muted">Il setup in ambiente pulito da wheel locali è documentato nel collaudo; CPU e recupero completo da Internet non ripetuti. GitHub Actions, licenze di redistribuzione e collaudo del clone restano attività di rilascio. Non sono certificati da questa pagina.</p><details><summary>Hash dei risultati sorgente</summary><div class="scroll"><table><tr><th>Studio</th><th>SHA-256 risultati</th></tr>{provenance_rows}</table></div></details></section>
<footer><p>Generato il{bundle['generated_date']} da metriche esistenti. Zero nuove inferenze o fit. Il confronto completo resta accessibile anche quando Timestral perde.</p></footer>
<script type="application/json" id="evidence-data">{payload}</script></main></body></html>'''


def main() -> None:
    """Generate a new report destination, refusing to overwrite an existing publication candidate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    config=yaml.safe_load(args.config.read_text(encoding='utf-8'))
    root=args.config.resolve().parent.parent
    output=root/config['release_v1']['output_directory']
    if output.exists():
        raise FileExistsError('Destinazione esistente: nessuna sovrascrittura implicita.')
    bundle=build_bundle(config,root)
    output.mkdir(parents=True)
    (output/'metrics.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
    (output/'index.html').write_text(render_slides(bundle, config),encoding='utf-8')
    (output/'details.html').write_text(render(bundle),encoding='utf-8')
    hashes={p.name:sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    (output/'manifest.json').write_text(json.dumps({'status':'release_candidate_documentation','files_sha256':hashes},indent=2),encoding='utf-8')
    print(output/'index.html')


if __name__ == '__main__':
    main()
