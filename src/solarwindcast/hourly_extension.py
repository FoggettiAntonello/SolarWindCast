"""Extend the unchanged hourly pilot on calendar dates disjoint from the initial sample."""

import argparse
import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import yaml

from solarwindcast.hourly_pilot import planned_origins, run
from solarwindcast.monthly_improvement import verify_manifest


def extension_config(config: dict, snapshot: dict) -> dict:
    """Derive scientific settings from the saved pilot, only changing dates and output budget."""
    settings = config['hourly_extension']
    if settings['authorized'] is not True or settings['calibration_authorized'] is not False:
        raise RuntimeError('Solo estensione senza calibrazione autorizzata.')
    derived = deepcopy(config)
    cfg = deepcopy(snapshot['settings'])
    old = set(planned_origins(cfg))
    cfg.update(authorized=True, output=settings['output'], days_of_month=settings['days_of_month'],
               maximum_inferences=settings['maximum_inferences'])
    if old & set(planned_origins(cfg)):
        raise ValueError('Origini sovrapposte al pilota precedente.')
    derived['hourly_pilot'] = cfg
    return derived


def run_extension(config: dict, root: Path) -> dict:
    """Run only extra origins and report old/new cohorts without claiming a model change."""
    source = root/config['hourly_extension']['previous_directory']
    verify_manifest(source)
    snapshot = json.loads((source/'snapshot.json').read_text(encoding='utf-8'))
    derived = extension_config(config, snapshot)
    data_manifest = root/snapshot['settings']['source']/'manifest.json'
    if sha256(data_manifest.read_bytes()).hexdigest() != snapshot['source_manifest_sha256']:
        raise ValueError('Dati diversi dal pilota.')
    result = run(derived, root)
    out = root/derived['hourly_pilot']['output']
    old = json.loads((source/'results.json').read_text(encoding='utf-8'))
    if result['model_provenance']['settings'] != old['model_provenance']['settings']:
        raise ValueError('Impostazioni modello cambiate.')
    for key in ('checkpoint_hashes', 'weights_revision', 'code_revision'):
        if result['model_provenance'].get(key) != old['model_provenance'].get(key):
            raise ValueError('Provenienza del modello diversa.')
    table = []
    comparison = []
    for cohort, data in [('Pilota: giorno15', old), ('Nuove giornate: 1,8,22', result)]:
        for target, scores in data['summary'].items():
            model = scores['timestral_5M']
            best = min((n for n in scores if not n.startswith('timestral')), key=lambda n: scores[n]['mae_mw'])
            change = 100*(model['mae_mw']/scores[best]['mae_mw']-1)
            comparison.append({'cohort': cohort, 'target': target, 'best_baseline': best,
                               'mae_change_pct': change, 'models': scores})
            for name in ('timestral_5M', best):
                m = scores[name]
                values = [cohort,target,name,str(m['origins']),str(m['cases'])]
                values += [f'{m.get(k):.4f}' if m.get(k) is not None else 'N/D' for k in
                           ('mae_mw','rmse_mw','pinball_mw','coverage_0.8','width_0.8_mw','coverage_0.9','width_0.9_mw')]
                table.append('<tr>'+''.join('<td>'+v+'</td>' for v in values)+'</tr>')
    note = '<section><h2>Verifica su giornate aggiuntive, modello invariato</h2><p>Giorni1,8,22 di ciascun mese, fissati prima delle nuove previsioni. Il giorno15 resta separato e non è riscaricato o riprevisto. Sono gli stessi mesi e dati revisionati: non è un test indipendente. Contesti sovrapposti e ore correlate. Nessun intervento sugli intervalli in questo step.</p><p>Il prima/dopo qui cambia il campione, non il modello. Le differenze tra campioni non sono guadagni di accuratezza attribuibili a una modifica. I confronti Timestral-baseline all’interno di ciascun campione usano le medesime origini.</p><div class="scroll"><table><tr><th>Campione</th><th>Target</th><th>Modello</th><th>Giorni</th><th>Ore</th><th>MAE MW</th><th>RMSE MW</th><th>Pinball MW</th><th>Copertura80</th><th>Ampiezza80 MW</th><th>Copertura90</th><th>Ampiezza90 MW</th></tr>'+''.join(table)+'</table></div></section>'
    html = (out/'presentazione.html').read_text(encoding='utf-8')
    html = html.replace('Giorno15 di ciascun mese', 'Giorni1,8,22 di ciascun mese')
    html = html.replace('</header>', '</header>'+note, 1)
    (out/'presentazione.html').write_text(html, encoding='utf-8')
    (out/'cohort_comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
    hashes = {p.name:sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.name != 'manifest.json'}
    (out/'manifest.json').write_text(json.dumps({'status':'complete','files_sha256':hashes},indent=2),encoding='utf-8')
    return result


def main() -> None:
    """Execute the authorized extension once; old results remain immutable."""
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,required=True)
    args=parser.parse_args()
    result=run_extension(yaml.safe_load(args.config.read_text(encoding='utf-8')),args.config.resolve().parent.parent)
    print(json.dumps(result['summary'],indent=2))


if __name__ == '__main__':
    main()
