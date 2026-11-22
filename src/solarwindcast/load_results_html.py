"""Offline Step 12 results with source availability and honest official forecast comparability."""

import json
from hashlib import sha256
from html import escape
from pathlib import Path

from solarwindcast.monthly_results_html import model_label, render_results
from solarwindcast.real_data_html import _fmt


def save_probe_report(probes: list[dict[str, object]], output: Path) -> None:
    """Publish only verified source samples, with no invented history or model performance."""
    output.mkdir(parents=True, exist_ok=False)
    renewable_sources = sorted({item["psr_type"] for probe in probes
        if probe["request"]["product"] == "day_ahead_renewables"
        for item in probe.get("response", {}).get("series", []) if item["psr_type"]})
    source_note = ("Fonti restituite nel campione rinnovabile: " + ", ".join(renewable_sources) + ". "
        + ("B18 non presente: non viene assunto uguale a zero." if "B18" not in renewable_sources else "B18 presente nel campione."))
    rows = []
    for probe in probes:
        response = probe.get("response", {})
        series = response.get("series", [])
        sources = sorted({str(item["psr_type"]) for item in series if item["psr_type"]})
        business = sorted({str(item["business_type"]) for item in series})
        period = probe["request"]["start_utc"] + " → " + probe["request"]["end_exclusive_utc"]
        rows.append(f'<tr><td>{escape(probe["request"]["product"])}</td><td>{escape(period)}</td>'
            f'<td>{escape(probe["metadata"]["status"])}</td><td>{escape(", ".join(business))}</td>'
            f'<td>{escape(", ".join(sources))}</td></tr>')
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Step 12 · Verifica delle fonti</title><style>body{{font:16px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}
main{{max-width:1100px;margin:auto;padding:25px}}header,section{{padding:25px;border-radius:16px;margin:20px 0;background:white}}
header{{background:#16313e;color:white}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;min-width:800px;width:100%}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #ddd}}
.notice{{padding:18px;background:#fff0d7;border-left:4px solid #d98b12}}</style></head><body><main><header><p>SolarWindCast · Step 12 · IT-South</p>
<h1>Carico e previsioni ufficiali: fonti verificate</h1><p>Campioni reali ENTSO-E · Nessun nuovo risultato mensile in questa pagina</p></header>
<p class="notice">Il download quinquennale del carico richiede conferma separata. Questi campioni non dimostrano la copertura dell'intero storico.</p>
<section><h2>Risposte osservate</h2><div class="scroll"><table><thead><tr><th>Prodotto</th><th>Periodo UTC</th><th>Esito</th><th>Business type</th><th>Fonti PSR</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p>A04: carico; A60/A61: estremi di carico; B16: solare; B19: eolico a terra; B18: eolico in mare.
{escape(source_note)}</p></section>
<section><h2>Perché non li mettiamo nella classifica mensile?</h2><p>Le previsioni day-ahead coprono il giorno successivo. Quelle emesse durante il mese non erano note alla nostra emissione mensile: sommarle darebbe un vantaggio informativo scorretto.</p>
<p>La previsione month-ahead standard del carico descrive massimi e minimi settimanali. Le caratteristiche delle risposte sono registrate nel JSON affiancato. Non è potenza media e non è un intervallo probabilistico: non si può convertirla in un totale mensile MWh.</p>
<p>Il campo createdDateTime coincide con la generazione della risposta del servizio e non certifica la prima pubblicazione della previsione. Le revisioni sono conservate; nessuna disponibilità storica operativa è dichiarata.</p></section>
<section><h2>Come funziona l'estensione</h2><p>Carico residuo = carico − solare − eolico terra e mare. Mancanti propagati, negativi conservati, stessa griglia oraria UTC. Si prevede direttamente il residuo mensile: non si sottraggono quantili indipendenti.</p>
<p>Il codice è pronto per riutilizzare contesto, emissione, modelli e finestre già congelati, salvando i nuovi risultati separatamente dallo Step 11.</p>
<p>Fonte: <a href="https://transparencyplatform.zendesk.com/hc/en-us/articles/16648033785492-Month-ahead-Total-Load-Forecast-per-Week-6-1-D">ENTSO-E — definizione del prodotto month-ahead</a>.</p></section></main></body></html>'''
    (output / "presentazione.html").write_text(html, encoding="utf-8")
    (output / "probes.json").write_text(json.dumps(probes, indent=2, ensure_ascii=False), encoding="utf-8")
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in output.iterdir()}
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")


def render_extension(result: dict[str, object], rows: list[dict[str, object]]) -> str:
    """Reuse monthly charts and metrics while adding load-specific quality and source evidence."""
    report = render_results({**result, "step": 12}, rows).replace(
        "SolarWindCast · Previsioni mensili e confronto reale", "SolarWindCast · Carico e residuo mensili")
    report = report.replace("</style>", "section{overflow-wrap:anywhere}select{box-sizing:border-box;max-width:calc(100% - 12px)}</style>", 1)
    overview = []
    for target, phases in result["scores"].items():
        scores = phases.get("test", {}).get("models", {})
        valid = [(name, item) for name, item in scores.items() if item["point_scores"]["mae_mwh"] is not None]
        baseline = [(name, item) for name, item in valid if not name.startswith("timestral_")]
        timestral = [(name, item) for name, item in valid if name.startswith("timestral_")]
        if not baseline or not timestral:
            continue
        baseline_name, baseline_score = min(baseline, key=lambda pair: pair[1]["point_scores"]["mae_mwh"])
        model_name, model_score = min(timestral, key=lambda pair: pair[1]["point_scores"]["mae_mwh"])
        title = {"load": "Carico elettrico", "residual_load": "Carico residuo"}[target]
        overview.append(f'<tr><td>{title}</td><td>{escape(model_label(baseline_name))}</td>'
            f'<td>{_fmt(baseline_score["point_scores"]["mae_mwh"])}</td><td>{escape(model_label(model_name))}</td>'
            f'<td>{_fmt(model_score["point_scores"]["mae_mwh"])}</td><td>{model_score["point_cases"]}</td></tr>')
    summary = f'''<section><h2>Il confronto a colpo d'occhio</h2><p>MAE: errore assoluto medio sul totale del mese, in MWh. Più basso è meglio.</p>
<div class="scroll"><table><thead><tr><th>Target</th><th>Baseline con MAE minimo</th><th>MAE MWh</th><th>Timestral con MAE minimo</th><th>MAE MWh</th><th>Mesi comuni</th></tr></thead><tbody>{''.join(overview)}</tbody></table></div>
<p>Questi minimi descrivono il campione di test. Non sono una nuova scelta operativa del modello e non dimostrano superiorità generale. Le tabelle sotto riportano tutti i concorrenti, coperture e ampiezze.</p></section>'''
    quality_rows = []
    for target, quality in result["quality"].items():
        name = {"load": "Carico elettrico", "residual_load": "Carico residuo"}[target]
        quality_rows.append(f'<tr><td>{name}</td><td>{quality["hourly_valid"]}/{quality["hourly_expected"]}</td>'
            f'<td>{quality["hourly_missing"]}</td><td>{quality["complete_months"]}/{quality["months"]}</td>'
            f'<td>{escape(", ".join(quality["missing_months"]) or "nessuno")}</td><td>{quality["negative_hours"]}</td></tr>')
    source_rows = []
    renewable_sources = {series["psr_type"] for probe in result["official_probes"]
        if probe["request"]["product"] == "day_ahead_renewables"
        for series in probe.get("response", {}).get("series", [])}
    renewable_note = ("Fonti del campione rinnovabile: " + ", ".join(sorted(str(value) for value in renewable_sources))
        + (". Offshore B18 non presente: non viene assunto uguale a zero." if "B18" not in renewable_sources else ". Offshore B18 presente.")) if renewable_sources else "Nessun campione rinnovabile disponibile in questa esecuzione."
    for probe in result["official_probes"]:
        request, metadata = probe["request"], probe["metadata"]
        response = probe.get("response", {})
        details = "; ".join(sorted({str(series["business_type"]) + " / " + str(series["psr_type"])
            for series in response.get("series", [])}))
        source_rows.append(f'<tr><td>{escape(request["product"])}</td><td>{escape(request["start_utc"])}</td>'
            f'<td>{escape(metadata["status"])}</td><td>{len(response.get("series", []))}</td>'
            f'<td>{escape(details)}</td></tr>')
    section = f'''<section><h2>Da quali dati nasce il carico residuo?</h2>
<p>Carico residuo = carico osservato − solare osservato − eolico osservato (terra + mare).
Le quattro componenti devono essere presenti nella stessa ora UTC. I valori negativi sono ammessi e conservati.
È un indicatore zonale: non misura da solo importazioni, accumuli o tutte le altre fonti di generazione.</p>
<p>Il carico totale ENTSO-E non coincide con le sole bollette dei consumatori finali: è la definizione di carico del sistema pubblicata dal gestore.</p>
<div class="scroll"><table><thead><tr><th>Target</th><th>Ore valide/attese</th><th>Ore mancanti</th><th>Mesi completi</th><th>Mesi incompleti</th><th>Ore negative</th></tr></thead><tbody>{''.join(quality_rows)}</tbody></table></div>
<p>Il residuo viene calcolato sulle osservazioni e previsto direttamente. Non si sottraggono quantili dei singoli target: senza una distribuzione congiunta non formerebbero un intervallo valido.</p></section>
<section><h2>Previsioni ufficiali ENTSO-E: cosa è confrontabile?</h2>
<div class="scroll"><table><thead><tr><th>Prodotto richiesto</th><th>Inizio campione UTC</th><th>Esito</th><th>Serie</th><th>Business type / fonte</th></tr></thead><tbody>{''.join(source_rows)}</tbody></table></div>
<p>Le verifiche attestano soltanto questi campioni per IT-South; non dimostrano la copertura di cinque anni né la disponibilità della prima pubblicazione.</p>
<p>{escape(renewable_note)}</p>
<p><b>Day-ahead:</b> carico, solare ed eolico prevedono il giorno successivo. Sommare le previsioni emesse durante il mese userebbe informazioni successive alla nostra emissione mensile. Non entrano nella classifica mensile.</p>
<p><b>Month-ahead A32:</b> il prodotto standard fornisce massimi e minimi settimanali del carico (A60/A61 secondo il documento ricevuto). Questi estremi non sono MW medi né quantili probabilistici: non li integriamo per inventare MWh mensili.
La semantica ufficiale resta questa anche se una risposta usa una risoluzione più fine.</p>
<p>Non è stato identificato in questi prodotti un confronto ufficiale di energia mensile con identica scadenza e informazione disponibile. Il confronto ufficiale resta separato e non viene presentato come una vittoria dei nostri modelli.</p>
<p>Fonti: <a href="https://transparencyplatform.zendesk.com/hc/en-us/articles/16648033785492-Month-ahead-Total-Load-Forecast-per-Week-6-1-D">ENTSO-E, month-ahead load</a>;
<a href="https://github.com/EnergieID/entsoe-py">entsoe-py</a>. Risposte XML e revisioni originali conservate con SHA-256.</p></section>'''
    return report.replace('<button onclick="window.print()">', summary + section + '<button onclick="window.print()">', 1)
