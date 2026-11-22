"""Report native mixed-resolution history without imposing an experimental sampling grid."""

import json
from hashlib import sha256
from html import escape
from itertools import pairwise
from pathlib import Path

import pandas as pd

from solarwindcast.real_data_html import COLORS, _chart, _fmt
from solarwindcast.real_data_report import InspectionSettings, inspect_acquisition


def save_history_report(chunks: list[InspectionSettings], output: Path) -> Path:
    """Audit every chunk and show daily descriptive means; keep native data in JSON."""
    if not chunks or output.exists():
        raise ValueError("Servono blocchi e una nuova cartella di risultati.")
    results = [inspect_acquisition(chunk) for chunk in chunks]
    for previous, current in pairwise(results):
        if previous.summary["end_exclusive_utc"] != current.summary["start_utc"]:
            raise ValueError("Blocchi non contigui o sovrapposti: nessuna correzione nascosta.")
    tables, cards, native = [], [], []
    totals = {}
    for name, item in results[0].summary["statistics"].items():
        daily_means, daily_dates = [], []
        valid, expected, missing, negative = 0, 0, 0, 0
        energies = []
        for result in results:
            stats = result.summary["statistics"][name]
            valid += stats["valid"]
            expected += stats["expected"]
            missing += stats["missing"]
            negative += stats["negative"]
            energies.append(stats["energy_mwh"])
            frequency = _fmt(pd.Timedelta(result.summary["native_frequency"]).total_seconds() / 60, 0) + " min"
            period_label = result.summary["start_utc"][:10] + " → " + result.summary["end_exclusive_utc"][:10]
            tables.append(f'<tr><td>{escape(period_label)}</td>'
                          f'<td>{escape(item["label"])}</td><td>{escape(frequency)}</td>'
                          f'<td>{stats["valid"]}/{stats["expected"]}</td><td>{stats["missing"]}</td>'
                          f'<td>{stats["negative"]}</td><td>{_fmt(stats["max_mw"])}</td>'
                          f'<td>{_fmt(stats["energy_mwh"])}</td></tr>')
            for row in result.summary["daily"]:
                if row["component"] == name:
                    daily_dates.append(pd.Timestamp(row["date_utc"], tz="UTC"))
                    # Complete-day means only: NaN remains a visible gap, not a biased partial mean.
                    complete = (row["valid"] == row["expected"]
                                and row["expected"] * pd.Timedelta(result.summary["native_frequency"])
                                == pd.Timedelta(days=1))
                    daily_means.append(row["mean_mw"] if complete else float("nan"))
        energy = sum(energies) if all(value is not None for value in energies) else None
        totals[name] = {"valid_native_intervals": valid, "expected_native_intervals": expected,
                        "missing_native_intervals": missing, "negative": negative,
                        "energy_mwh_complete_period_only": energy}
        daily_series = pd.Series(daily_means, index=pd.DatetimeIndex(daily_dates))
        svg = _chart(daily_series, "1D", COLORS[name])
        cards.append(f'<section><h2>{escape(item["label"])}</h2>'
                     f'<p><b>{_fmt(valid, 0)}</b> intervalli nativi validi su {_fmt(expected, 0)} · '
                     f'{missing} mancanti · {negative} negativi · Energia completa: {_fmt(energy)} MWh</p>'
                     f'<p class="muted">Ogni gradino è la potenza media di un giorno UTC completo '
                     f'(MW). Le giornate incomplete restano interruzioni del grafico. '
                     f'È una sintesi descrittiva, non la frequenza scelta per i modelli.</p>{svg}</section>')
    sources = []
    for chunk, result in zip(chunks, results, strict=True):
        data = json.loads(result.frame.reset_index().to_json(orient="records", date_format="iso", double_precision=15))
        native.append({"start_utc": result.summary["start_utc"],
                       "native_frequency": result.summary["native_frequency"], "records": data})
        for source in result.summary["sources"]:
            sources.append({**source, "acquisition_directory": chunk.acquisition_directory.as_posix()})
    excluded = {}
    for source in sources:
        for component, details in source["components"].items():
            for item in details.get("excluded_consumption_series", []):
                key = (source["acquisition_directory"], source["file"], component, item["series_number"])
                excluded[key] = {"directory": key[0], "file": key[1], **item}
    summaries = [result.summary for result in results]
    summary = {"kind": "real_observations_quality_only", "model_predictions_computed": False,
               "start_utc": summaries[0]["start_utc"], "end_exclusive_utc": summaries[-1]["end_exclusive_utc"],
               "totals": totals, "chunks": summaries,
               "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
               "excluded_consumption_series": list(excluded.values()),
               "daily_chart_policy": "mean MW only for complete UTC days; no native resampling exported",
               "publication_availability": "unknown; historical revisions not reconstructed"}
    rows = "".join(tables)
    source_rows = "".join(f'<tr><td>{escape(source["acquisition_directory"])}/{escape(source["file"])}</td>'
                          f'<td><code>{escape(source["sha256"])}</code></td>'
                          f'<td>{escape(str(source["retrieved_utc"]))}</td></tr>' for source in sources)
    start, end = summary["start_utc"][:10], summary["end_exclusive_utc"][:10]
    begin_date, end_date = pd.Timestamp(start), pd.Timestamp(end)
    month_count = (end_date.year - begin_date.year) * 12 + end_date.month - begin_date.month
    gaps = [f'{escape(item["label"])}: {escape(timestamp)}'
            for result in results for item in result.summary["statistics"].values()
            for timestamp in item.get("missing_timestamps", [])]
    gaps_note = ('<p><b>Intervalli mancanti, UTC:</b> ' + '; '.join(gaps[:20]) +
                 f'. Totale: {len(gaps)}; elenco completo in analysis.json. '
                 'Restano NaN: nessuna sostituzione.</p>') if gaps else '<p>Nessun intervallo mancante.</p>'
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SolarWindCast · Storico reale di {month_count} mesi</title><style>
body{{margin:0;background:#f2f6f7;color:#16313e;font:16px/1.6 system-ui,sans-serif}}
main{{max-width:1160px;margin:auto;padding:32px 20px}}header{{background:#16313e;color:white;padding:40px;border-radius:20px}}
h1{{font-size:clamp(28px,5vw,48px);line-height:1.15}}h2{{margin-top:0}}section{{background:white;padding:28px;border-radius:16px;margin:24px 0}}
.muted{{color:#526574;font-size:14px}}.notice{{background:#fff0d7;border-left:4px solid #d98b12;padding:18px;margin:22px 0}}
svg{{width:100%;height:auto}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;min-width:900px;width:100%;font-size:13px}}
td,th{{padding:10px;text-align:left;border-bottom:1px solid #dce5e9}}code{{font-size:11px}}button{{padding:9px 15px;cursor:pointer}}
@media(max-width:600px){{main{{padding:14px}}header,section{{padding:20px}}}}
@media print{{button{{display:none}}section{{break-inside:avoid}}}}
</style></head><body><main><header><p>SolarWindCast · Fase B / Step 10 · Zona di mercato Sud</p>
<h1>Lo storico reale, prima delle previsioni</h1><p>{start} → {end} (fine esclusa), UTC · {len(results)} blocchi verificati</p>
<p>Solare, eolico a terra ed eolico in mare. Nessuna prestazione di Timestral è stata calcolata.</p></header>
<div class="notice"><b>Risoluzione della fonte variabile.</b> Gli originali sono conservati alla frequenza nativa,
riportata mese per mese. Non abbiamo creato quarti d'ora artificiali dai valori orari.
I conteggi degli intervalli non equivalgono a prove statistiche indipendenti.</div>
<button onclick="window.print()">Stampa / Salva PDF</button>{''.join(cards)}
<section><h2>Copertura e qualità per periodo</h2><p>Picchi in MW, energia in MWh solo per periodi completi.
Un mese è separato in più righe quando cambia il passo nativo.
I negativi sono segnalati e conservati. Gli zeri sono osservazioni, non mancanti.</p>{gaps_note}<div class="scroll"><table>
<thead><tr><th>Periodo UTC · fine esclusa</th><th>Fonte</th><th>Passo nativo</th><th>Validi/attesi</th><th>Mancanti</th><th>Negativi</th><th>Picco MW</th><th>MWh</th></tr></thead>
<tbody>{rows}</tbody></table></div></section><section><h2>Che cosa manca per valutare i modelli</h2>
<p>Concordare frequenza comune, orizzonte, contesto, ritardi e finestre. La proposta è usare il primo anno per sviluppo
e il secondo per test finale, senza scegliere i parametri guardando i risultati del test.</p>
<p>La qualità dei dati non misura l'affidabilità delle previsioni. Nel test confronteremo errori, copertura e ampiezza
degli intervalli con le baseline, separando stagioni, ore diurne/notturne e distanza della previsione.</p>
<p>La zona Sud non coincide con la sola Puglia. Revisioni storiche e tempi di prima pubblicazione non sono ricostruiti.
Il meteo per questo periodo non è stato acquisito con questo comando; le future covariate richiedono run disponibili all'origine.</p></section>
<section><h2>Provenienza verificata</h2><p>Decodifica ENTSO-E A01/A03, controlli su zona, unità e duplicati;
nessuna interpolazione dei mancanti. Hash verificati prima di ogni importazione.</p>
<p>Serie di consumo degli impianti escluse esplicitamente: {len(excluded)}.
Restano negli XML originali e sono elencate in analysis.json; non sono sottratte alla produzione.</p><div class="scroll"><table>
<thead><tr><th>Originale</th><th>SHA-256</th><th>Acquisizione UTC</th></tr></thead><tbody>{source_rows}</tbody></table></div></section>
<footer>Pagina autonoma offline · Dati e controlli in analysis.json e native_series.json · Hash in manifest.json</footer>
</main></body></html>'''
    files = {"presentazione.html": html,
             "analysis.json": json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False),
             "native_series.json": json.dumps(native, ensure_ascii=False, allow_nan=False)}
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for filename, text in files.items():
        with (output / filename).open("x", encoding="utf-8") as stream:
            stream.write(text)
        hashes[filename] = sha256((output / filename).read_bytes()).hexdigest()
    with (output / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump({"status": "complete", "files_sha256": hashes}, stream, indent=2)
    return output / "presentazione.html"
