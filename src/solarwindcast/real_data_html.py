"""Standalone Italian HTML presentation with embedded scientific SVG charts."""

from datetime import UTC
from html import escape
from io import StringIO
from string import Template
from typing import TYPE_CHECKING

import matplotlib as mpl
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

if TYPE_CHECKING:
    from solarwindcast.real_data_report import InspectionResult

COLORS = {"solar": "#d98b12", "wind_onshore": "#007c78", "wind_offshore": "#496cc7"}


def _fmt(value: float | None, decimals: int = 1) -> str:
    """Format measured numbers for an Italian reader without changing stored values."""
    if value is None or pd.isna(value):
        return "—"
    return f"{value:,.{decimals}f}".replace(",", "TEMP").replace(".", ",").replace("TEMP", ".")


def _chart(series: pd.Series, frequency: str, color: str, daily: bool = False) -> str:
    """Render native interval values as steps; NaN breaks stay visible."""
    figure = Figure(figsize=(12, 3.45), layout="constrained", facecolor="white")
    axes = figure.subplots()
    axes.set_facecolor("white")
    axes.grid(axis="y", color="#e7edf0", linewidth=.8)
    for side in ("top", "right", "left"):
        axes.spines[side].set_visible(False)
    axes.spines["bottom"].set_color("#d3dce2")
    axes.tick_params(axis="both", labelsize=9, colors="#526574", length=0, pad=8)
    axes.set_ylabel("Potenza media (MW)", color="#526574", fontsize=9, labelpad=12)
    if daily:
        palette = ("#007c78", "#d98b12", "#496cc7", "#a55079")
        for number, (date, part) in enumerate(series.groupby(series.index.normalize())):
            hours = np.asarray(part.index.hour + part.index.minute / 60, dtype=float)
            hours = np.append(hours, hours[-1] + pd.Timedelta(frequency) / pd.Timedelta(hours=1))
            axes.step(hours, np.append(part.to_numpy(), part.iloc[-1]), where="post", linewidth=1.8,
                      color=palette[number % len(palette)], label=date.strftime("%d/%m/%Y"))
        axes.set_xlim(0, 24)
        axes.set_xticks([0, 4, 8, 12, 16, 20, 24])
        axes.set_xlabel("Ora del giorno (UTC)", color="#526574", fontsize=9)
        axes.legend(frameon=False, ncols=3, fontsize=9, loc="upper right")
    else:
        end = series.index[-1] + pd.Timedelta(frequency)
        times = series.index.append(pd.DatetimeIndex([end]))
        values = np.append(series.to_numpy(dtype=float), series.iloc[-1])
        axes.step(times, values, where="post", color=color, linewidth=1.8)
        axes.fill_between(times, values, step="post", color=color, alpha=.09)
        axes.set_xlim(series.index[0], end)
        axes.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=5, maxticks=8))
        date_format = "%m/%Y" if end - series.index[0] >= pd.Timedelta(days=365) else "%d/%m\n%H:%M"
        axes.xaxis.set_major_formatter(mdates.DateFormatter(date_format, tz=UTC))
        axes.set_xlabel("Inizio dell'intervallo · UTC", color="#526574", fontsize=9)
    if series.notna().any() and series.min() >= 0:
        axes.set_ylim(bottom=0)
    buffer = StringIO()
    with mpl.rc_context({"svg.fonttype": "none", "svg.hashsalt": "solarwindcast-step10", "font.family": "DejaVu Sans"}):
        figure.savefig(buffer, format="svg", metadata={"Date": None})
    svg = buffer.getvalue()
    return svg[svg.index("<svg"):]


def render_html(result: "InspectionResult") -> str:
    """Compose one offline report; no external assets, forecasts or hidden data filling."""
    summary, frame = result.summary, result.frame
    stats = summary["statistics"]
    start = pd.Timestamp(summary["start_utc"])
    end = pd.Timestamp(summary["end_exclusive_utc"])
    period = f"{start:%d/%m/%Y} — {end - pd.Timedelta(summary['native_frequency']):%d/%m/%Y}"
    missing = sum(item["missing"] for item in stats.values())
    dates = sorted({row["date_utc"] for row in summary["daily"]})
    tabs, panels = [], []
    for number, (name, item) in enumerate(stats.items()):
        label = escape(item["label"])
        tabs.append(f'<button class="tab" role="tab" id="tab-{name}" aria-controls="panel-{name}" '
                    f'aria-selected="{str(number == 0).lower()}" data-component="{name}">{label}</button>')
        plot = _chart(frame[name], summary["native_frequency"], COLORS[name])
        profile = _chart(frame[name], summary["native_frequency"], COLORS[name], daily=True)
        hidden = "" if number == 0 else " hidden"
        panels.append(f'''<section class="data-panel" role="tabpanel" id="panel-{name}" aria-labelledby="tab-{name}"{hidden}>
          <div class="series-head"><div><span class="eyebrow">SERIE OSSERVATA</span><h3>{label}</h3></div>
          <span class="badge">{item['valid']} / {item['expected']} intervalli validi</span></div>
          <div class="mini-grid"><div><span>Potenza media</span><strong>{_fmt(item['mean_mw'])} <small>MW</small></strong></div>
          <div><span>Picco osservato</span><strong>{_fmt(item['max_mw'])} <small>MW</small></strong></div>
          <div><span>Energia nel periodo completo</span><strong>{_fmt(item['energy_mwh'])} <small>MWh</small></strong></div></div>
          <div class="chart" role="img" aria-label="Andamento reale {label}, timestamp UTC">{plot}</div>
          <div class="chart-subhead"><h4>I giorni a confronto</h4><span>Curve giornaliere osservate, nessuna previsione</span></div>
          <div class="chart" role="img" aria-label="Confronto dei giorni per {label}">{profile}</div>
        </section>''')
    heat_rows, decoding_rows = [], []
    for name, item in stats.items():
        cells = []
        for date in dates:
            row = next(d for d in summary["daily"] if d["component"] == name and d["date_utc"] == date)
            state = "complete" if row["valid"] == row["expected"] else "incomplete"
            cells.append(f'<td><div class="coverage {state}"><strong>{_fmt(row["coverage"] * 100, 0)}%</strong>'
                         f'<span>{row["valid"]}/{row["expected"]} intervalli</span></div></td>')
        heat_rows.append(f'<tr><th scope="row">{escape(item["label"])}</th>{"".join(cells)}</tr>')
        decoding_rows.append(f'<tr><td>{escape(item["label"])}</td><td>{item["raw_points"]}</td>'
                             f'<td>{item["represented_intervals"]}</td><td>{item["missing"]}</td>'
                             f'<td>{item["negative"]}</td></tr>')
    source_cards = []
    for source in summary["sources"]:
        source_cards.append(f'''<article class="source-card"><h4>{escape(source['file'])}</h4>
            <p>Acquisito: {escape(str(source['retrieved_utc']))}<br>Revisione dichiarata: {escape(str(source['revision']))}</p>
            <span class="eyebrow">SHA-256 VERIFICATO</span><code>{escape(source['sha256'])}</code></article>''')
    template = Template('''<!doctype html>
<html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SolarWindCast · Dati reali della zona Sud</title><style>
:root{--ink:#152d3a;--muted:#5d7380;--teal:#007c78;--paper:#f4f7f8;--line:#dce5e9;--amber:#bb7610}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--paper);color:var(--ink);font-family:Segoe UI,Arial,sans-serif;line-height:1.6}a{color:var(--teal)}button{font:inherit;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid #db9b32;outline-offset:4px}[hidden]{display:none!important}
.topbar{background:#fff;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:2}.nav-inner{max-width:1160px;margin:auto;padding:16px 24px;display:flex;align-items:center;gap:28px}.brand{font-weight:750;letter-spacing:-.7px;font-size:21px;white-space:nowrap}.brand i{display:inline-block;width:13px;height:13px;background:#d98b12;border-radius:50%;margin-right:9px}.nav-links{display:flex;gap:20px;margin-left:auto;font-size:13px}.nav-links a{color:var(--muted);text-decoration:none}.print{border:1px solid var(--line);background:white;border-radius:8px;padding:7px 13px;font-size:12px}
main{max-width:1160px;margin:auto;padding:40px 24px 70px}.hero{background:#142e3b;border-radius:22px;padding:44px 46px;color:white;display:grid;grid-template-columns:1.45fr 1fr;gap:38px;align-items:center}.eyebrow{font-size:10px;font-weight:750;letter-spacing:1.7px;text-transform:uppercase;color:var(--teal)}.hero .eyebrow{color:#73d5c6}.hero h1{font-size:clamp(30px,4.3vw,49px);line-height:1.12;letter-spacing:-1.8px;margin:16px 0 18px;font-weight:730}.hero p{color:#c5d6de;font-size:15px;max-width:530px}.period{display:inline-block;border:1px solid #45606f;border-radius:30px;padding:7px 13px;color:#e4ecef;font-size:12px}.hero-note{padding:25px;border:1px solid #415965;border-radius:16px;background:#1b3948}.hero-note h2{font-size:21px;line-height:1.3;margin:8px 0 12px}.hero-note p{font-size:13px;margin:0}.hero-note .status{color:#86dfce;font-size:12px;font-weight:650}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0 55px}.kpi{background:white;border:1px solid var(--line);border-radius:13px;padding:20px 23px}.kpi strong{font-size:32px;line-height:1.2;display:block;letter-spacing:-1px}.kpi span{font-size:12px;color:var(--muted)}.section-head{display:flex;justify-content:space-between;align-items:end;gap:26px;margin:50px 0 20px}.section-head h2{font-size:28px;line-height:1.25;margin:7px 0 0;letter-spacing:-.6px}.section-head p{font-size:13px;color:var(--muted);max-width:460px;margin:0}
.panel{background:white;border:1px solid var(--line);border-radius:16px;padding:28px}.tabs{display:flex;gap:9px;border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:24px;flex-wrap:wrap}.tab{padding:9px 18px;border:1px solid var(--line);border-radius:30px;background:#fff;font-size:13px;color:var(--muted)}.tab[aria-selected=true]{background:var(--teal);border-color:var(--teal);color:white}.series-head{display:flex;justify-content:space-between;align-items:center;gap:16px}.series-head h3{font-size:24px;margin:3px 0 0}.badge{font-size:11px;background:#e7f4ef;border-radius:30px;padding:6px 11px;color:#146e59;white-space:nowrap}.mini-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:23px 0 14px}.mini-grid>div{padding-left:15px;border-left:2px solid #e3eaed}.mini-grid span{display:block;font-size:11px;color:var(--muted)}.mini-grid strong{font-size:23px;font-weight:650}.mini-grid small{font-size:12px;color:var(--muted);font-weight:450}.chart svg{width:100%;height:auto;display:block}.chart-subhead{border-top:1px solid var(--line);padding-top:20px;display:flex;justify-content:space-between;align-items:center;gap:16px}.chart-subhead h4{margin:0;font-size:15px}.chart-subhead span{font-size:11px;color:var(--muted)}
.note{padding:15px 18px;background:#f2f7f8;border-left:3px solid var(--teal);font-size:13px;border-radius:0 8px 8px 0;margin-top:18px}.note.warm{background:#fff7e9;border-color:#d98b12}.scroll-table{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:13px;text-align:left}th,td{padding:13px 12px;border-bottom:1px solid var(--line)}thead th{font-size:10px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}tbody th{font-weight:600}.coverage{padding:13px 17px;border-radius:8px;min-width:130px}.coverage strong{display:block;font-size:20px}.coverage span{font-size:10px}.coverage.complete{background:#e6f4ee;color:#176b55}.coverage.incomplete{background:#fff0d9;color:#955e10}.two-cols{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}.two-cols h3{font-size:18px;margin:0 0 10px}.two-cols p,.two-cols li{font-size:13px;color:var(--muted)}.callout{margin-top:22px;background:#142e3b;border-radius:14px;padding:24px 28px;color:white}.callout h3{margin:0 0 9px;font-size:20px}.callout p{font-size:13px;color:#d0dee4;margin:0}.decision-table td:first-child{font-weight:650;white-space:nowrap}.pending{display:inline-block;font-size:10px;letter-spacing:.7px;padding:4px 8px;background:#fff1dc;color:#885600;border-radius:5px;white-space:nowrap}
.sources{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.source-card{border:1px solid var(--line);border-radius:12px;background:white;padding:19px;min-width:0}.source-card h4{font-size:13px;margin:0 0 8px}.source-card p{font-size:10px;overflow-wrap:anywhere;color:var(--muted)}.source-card code{font-size:10px;display:block;overflow-wrap:anywhere;margin-top:8px;color:#3b5462}.small{font-size:12px;color:var(--muted)}footer{border-top:1px solid var(--line);margin-top:35px;padding-top:20px;font-size:11px;color:var(--muted);display:flex;justify-content:space-between;gap:20px}
@media(max-width:760px){.nav-inner{padding:13px 16px;gap:12px}.nav-links{display:none}.print{margin-left:auto}main{padding:22px 14px}.hero{grid-template-columns:1fr;padding:28px 24px;gap:20px}.hero h1{letter-spacing:-1px}.kpis{grid-template-columns:1fr 1fr;gap:10px;margin-bottom:35px}.kpi{padding:16px}.kpi strong{font-size:28px}.panel{padding:20px 14px}.section-head{display:block}.section-head p{margin-top:12px}.mini-grid{gap:10px}.mini-grid strong{font-size:18px}.mini-grid>div{padding-left:9px}.series-head{align-items:start}.badge{white-space:normal;max-width:125px}.chart-subhead{display:block}.chart-subhead span{display:block;margin-top:5px}.two-cols,.sources{grid-template-columns:1fr}.decision-table{min-width:600px}footer{display:block}}
@media(max-width:760px){.chart{overflow-x:auto}.chart svg{min-width:760px}.mini-grid{grid-template-columns:1fr 1fr}.mini-grid>div:last-child{grid-column:1/-1}}
@media print{body{background:white}.topbar,.tabs,.print{display:none}main{max-width:none;padding:0}.hero{break-inside:avoid}.data-panel[hidden]{display:block!important}.data-panel{break-before:page}.panel{border:0;padding:12px 0}.section-head,.source-card{break-inside:avoid}a{color:inherit}footer{font-size:9px}}
</style></head><body>
<header class="topbar"><div class="nav-inner"><div class="brand"><i></i>SolarWindCast</div><nav class="nav-links" aria-label="Sezioni"><a href="#produzione">Produzione</a><a href="#qualita">Qualità</a><a href="#decisioni">Decisioni</a><a href="#fonti">Fonti</a></nav><button class="print" id="print-button">Stampa / PDF</button></div></header>
<main><section class="hero"><div><span class="eyebrow">FASE B · STEP 10 · DATI REALI</span><h1>La produzione rinnovabile della zona Sud.</h1><p>Solare ed eolico osservati nei dati ENTSO-E. Un primo controllo visivo di andamento, copertura e qualità, prima degli esperimenti previsivi.</p><span class="period">$period · tutti gli orari in UTC</span></div><aside class="hero-note"><span class="status">● Osservazioni reali verificate</span><h2>Un primo campione di $days giorni.</h2><p>Possiamo analizzarne la struttura e i valori. La qualità dei dati non stabilisce quanto sia affidabile un modello. In questa presentazione non sono state calcolate previsioni né prestazioni di Timestral.</p></aside></section>
<section class="kpis" aria-label="Sintesi del campione"><div class="kpi"><strong>$hours <small>h</small></strong><span>Periodo osservato</span></div><div class="kpi"><strong>$intervals</strong><span>Intervalli attesi per fonte · $frequency</span></div><div class="kpi"><strong>$components</strong><span>Fonti analizzate separatamente</span></div><div class="kpi"><strong>$missing</strong><span>Valori mancanti dopo decodifica</span></div></section>
<section id="produzione"><div class="section-head"><div><span class="eyebrow">01 / ANDAMENTO</span><h2>Come cambia la produzione</h2></div><p>Potenza media per intervallo in MW. L'energia in MWh è la somma della potenza per la durata, mostrata solo per periodi completi.</p></div><div class="panel"><div class="tabs" role="tablist" aria-label="Fonte di produzione">$tabs</div>$panels<div class="note">La zona di mercato Sud comprende la Puglia ma non coincide con la sola Puglia. Questi grafici non attribuiscono la produzione a singole regioni o impianti.</div></div></section>
<section id="qualita"><div class="section-head"><div><span class="eyebrow">02 / COPERTURA E TRACCIABILITÀ</span><h2>I dati ci sono davvero?</h2></div><p>Uno zero è un valore osservato, non un dato mancante. I mancanti restano NaN; non sono stati interpolati o sostituiti.</p></div><div class="panel"><div class="scroll-table"><table><thead><tr><th>Fonte</th>$day_headers</tr></thead><tbody>$heat_rows</tbody></table></div><div class="note">Completezza sul periodo richiesto: non certifica l'assenza di errori fisici, revisioni o ritardi di pubblicazione.</div></div>
<div class="two-cols"><article class="panel"><h3>XML A03: blocchi, non buchi</h3><p>La fonte trasmette le posizioni in cui cambia il valore. Ogni blocco vale fino al successivo, entro il proprio periodo. Lo espandiamo sulla griglia nativa e registriamo la trasformazione: non è un riempimento di osservazioni mancanti.</p><p>Le lacune fra periodi o i blocchi senza quantità restano NaN. Non si propagano valori oltre la fine del periodo.</p></article><article class="panel"><h3>Controlli applicati</h3><ul><li>Hash degli originali confrontati con il manifest.</li><li>Zona, prodotto osservato, unità MW e risoluzione verificati.</li><li>Posizioni ambigue o intervalli duplicati bloccano l'importazione.</li><li>Valori negativi segnalati e conservati, senza correzioni.</li></ul></article></div>
<div class="panel" style="margin-top:20px"><div class="scroll-table"><table><thead><tr><th>Fonte</th><th>Punti XML</th><th>Intervalli rappresentati</th><th>Mancanti</th><th>Negativi</th></tr></thead><tbody>$decoding_rows</tbody></table></div><p class="small">Gli intervalli rappresentati dopo la decodifica non sono nuove misure indipendenti. Nessuna anomalia viene corretta in silenzio.</p></div></section>
<section id="decisioni"><div class="section-head"><div><span class="eyebrow">03 / PRIMA DEL BACKTEST REALE</span><h2>Che cosa possiamo decidere adesso</h2></div><p>Il formato osservato è noto. I parametri previsivi restano aperti: verranno scelti insieme dopo aver ampliato e verificato lo storico.</p></div><div class="panel"><div class="scroll-table"><table class="decision-table"><thead><tr><th>Voce</th><th>Informazione o proposta</th><th>Stato</th></tr></thead><tbody>
<tr><td>Storico</td><td>Periodo analizzato di $days giorni. Pianificare uno storico sufficiente a separare sviluppo, validazione e test finale.</td><td><span class="pending">DA CONCORDARE</span></td></tr>
<tr><td>Frequenza</td><td>Fonte nativa a 15 minuti. Confrontare questa griglia con un'eventuale media oraria di blocchi completi.</td><td><span class="pending">DA DECIDERE</span></td></tr>
<tr><td>Orizzonte e contesto</td><td>Sceglierli in base al caso d'uso e allo storico effettivamente disponibile.</td><td><span class="pending">DA DECIDERE</span></td></tr>
<tr><td>Eolico</td><td>A terra e in mare sono visibili separatamente. La composizione del target non è stata fissata.</td><td><span class="pending">DA DECIDERE</span></td></tr>
<tr><td>Confronti</td><td>Baseline e Timestral; le taglie 5M e 28M sono già in cache. Nessun vincitore è prestabilito.</td><td><span class="pending">DA CONFERMARE</span></td></tr>
<tr><td>Meteo futuro</td><td>Usare run conoscibili all'origine, con provenienza e ritardo verificati. Nessun meteo futuro ricostruito negli input.</td><td><span class="pending">DA VERIFICARE</span></td></tr>
</tbody></table></div><div class="callout"><h3>La prossima decisione è sullo storico.</h3><p>Occorre individuare altri file già scaricati oppure concordare un'acquisizione più ampia. Nessuna nuova richiesta API è stata fatta per generare questa pagina. Lo Step 11 partirà dopo l'approvazione dei parametri.</p></div></div></section>
<section id="fonti"><div class="section-head"><div><span class="eyebrow">04 / PROVENIENZA</span><h2>Originali conservati, trasformazioni visibili</h2></div><p>Acquisizioni già presenti nel progetto. I file originali non sono stati modificati; token, URL autenticati e configurazioni riservate non sono inclusi.</p></div><div class="sources">$sources</div><div class="note warm">Gli orari di creazione della risposta e di acquisizione non ricostruiscono la prima pubblicazione del dato. La revisione dichiarata non esclude aggiornamenti successivi: questo campione non è ancora un archivio operativo “come noto allora”.</div><p class="small">Metodo A03: <a href="https://transparencyplatform.zendesk.com/hc/en-us/articles/30262342482961-CurveType-A01-vs-CurveType-A03">documentazione ufficiale ENTSO-E</a>. La pagina è autonoma: grafici SVG incorporati, nessuna libreria o risorsa caricata da rete.</p></section>
<footer><span>SolarWindCast · Portfolio di previsione energetica · Zona di mercato Sud</span><span>Analisi descrittiva · Generata $generated</span></footer></main>
<script>
const tabs = Array.from(document.querySelectorAll('[data-component]'));
function activate(tab) {
  tabs.forEach(button => { const selected = button === tab; button.setAttribute('aria-selected', String(selected)); document.getElementById('panel-' + button.dataset.component).hidden = !selected; });
}
tabs.forEach((tab, index) => { tab.addEventListener('click', () => activate(tab)); tab.addEventListener('keydown', event => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const next = tabs[(index + (event.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length]; activate(next); next.focus(); } }); });
document.getElementById('print-button').addEventListener('click', () => window.print());
</script></body></html>''')
    return template.substitute(period=escape(period), hours=_fmt(summary["duration_hours"], 0),
        intervals=len(frame), frequency=escape(summary["native_frequency"]), components=len(stats), missing=missing, days=len(dates),
        tabs="".join(tabs), panels="".join(panels),
        day_headers="".join(f'<th>{pd.Timestamp(day):%d/%m/%Y} · UTC</th>' for day in dates),
        heat_rows="".join(heat_rows), decoding_rows="".join(decoding_rows), sources="".join(source_cards),
        generated=escape(str(summary["generated_at_utc"])))
