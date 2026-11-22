"""Standalone scientific report of actual monthly backtest results, including losses and uncertainty limits."""

from html import escape
from io import StringIO

import matplotlib as mpl
import matplotlib.dates as mdates
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from solarwindcast.real_data_html import _fmt


def model_label(name: str) -> str:
    """Translate model identifiers into readable Italian without changing stored identities."""
    names = {"last_complete_month": "Ultimo mese valido", "same_month_previous_year": "Stesso mese anno prima",
             "recent_complete_months": "Media mesi recenti", "seasonal_empirical_rolling_errors": "Stagionale + errori storici"}
    if name in names:
        return names[name]
    if name.startswith("timestral_"):
        size, variant = name[len("timestral_"):].split("_", 1)
        return "Timestral " + size + " · " + {"target_only": "solo serie", "known_calendar": "con calendario"}[variant]
    return name


def _svg(figure: Figure) -> str:
    """Embed vector charts with stable fonts and no external resources."""
    stream = StringIO()
    with mpl.rc_context({"svg.fonttype": "none", "svg.hashsalt": "solarwindcast-step11"}):
        figure.savefig(stream, format="svg", metadata={"Date": None})
    result = stream.getvalue()
    return result[result.index("<svg"):]


def forecast_chart(rows: list[dict[str, object]], intervals: list[float]) -> str:
    """Show every issued month, keeping the missing observation and any unavailable forecast as gaps."""
    ordered = sorted(rows, key=lambda row: row["target_start_utc"])
    dates = pd.to_datetime([row["target_start_utc"] for row in ordered], utc=True)
    actual = np.asarray([row["actual_mwh"] for row in ordered], dtype=float) / 1000
    point = np.asarray([row["point_mwh"] for row in ordered], dtype=float) / 1000
    figure = Figure(figsize=(11, 3.7), layout="constrained")
    axes = figure.subplots()
    colors = ["#d3e9e7", "#90c5c1"]
    if any(row["quantiles_mwh"] for row in ordered):
        for level, color in zip(sorted(intervals, reverse=True), colors, strict=False):
            lower, upper = [], []
            for row in ordered:
                quantiles = row["quantiles_mwh"]
                if quantiles:
                    lower.append(next(value for key, value in quantiles.items() if np.isclose(float(key), (1-level)/2)))
                    upper.append(next(value for key, value in quantiles.items() if np.isclose(float(key), (1+level)/2)))
                else:
                    lower.append(np.nan)
                    upper.append(np.nan)
            axes.fill_between(dates, np.asarray(lower) / 1000, np.asarray(upper) / 1000,
                              color=color, label=f"Intervallo {level:.0%}")
    axes.plot(dates, point, color="#007c78", linewidth=1.8, marker="o", markersize=3, label="Previsione")
    axes.plot(dates, actual, color="#243b4a", linewidth=1.8, marker="o", markersize=3, label="Osservato")
    axes.set_ylabel("Energia (GWh)")
    axes.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=7))
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    axes.grid(axis="y", alpha=.2)
    axes.legend(frameon=False, fontsize=8, ncols=4)
    axes.set_xlim(dates[0], dates[-1] + pd.Timedelta(days=1))
    return _svg(figure)


def seasonal_error_chart(rows: list[dict[str, object]], selected_model: str) -> str:
    """Compare mean absolute error by calendar month, annotating the very small sample counts."""
    figure = Figure(figsize=(11, 3.3), layout="constrained")
    axes = figure.subplots()
    labels = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]
    for offset, model, color in ((-.19, "same_month_previous_year", "#adbac0"), (.19, selected_model, "#007c78")):
        means, counts = [], []
        for month in range(1, 13):
            values = [abs(row["point_mwh"] - row["actual_mwh"]) / 1000 for row in rows
                      if row["model"] == model and pd.Timestamp(row["target_start_utc"]).month == month
                      and row["point_mwh"] is not None and row["actual_mwh"] is not None]
            means.append(float(np.mean(values)) if values else np.nan)
            counts.append(len(values))
        positions = np.arange(12) + offset
        axes.bar(positions, means, width=.36, color=color, label=model_label(model))
        if model == selected_model:
            for position, mean, count in zip(positions, means, counts, strict=True):
                if np.isfinite(mean):
                    axes.annotate(f"n={count}", (position, mean), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)
    axes.set_xticks(np.arange(12), labels)
    axes.set_ylabel("Errore assoluto medio (GWh)")
    axes.grid(axis="y", alpha=.15)
    axes.legend(frameon=False, fontsize=8)
    return _svg(figure)


def render_results(result: dict[str, object], predictions: list[dict[str, object]]) -> str:
    """Render test and development separately, without turning small differences into certainty."""
    sections, loss_rows = [], []
    protocol = result["protocol"]
    default_model = f"timestral_{protocol['models'][-1]['size']}_{protocol['model_variants'][0]}"
    for target, phases in result["scores"].items():
        test = phases["test"]
        records = [row for row in predictions if row["target"] == target and row["phase"] == "test"]
        models = test["models"]
        score_rows, interval_rows, panels, options = [], [], [], []
        for model, scores in sorted(models.items(), key=lambda item: (
                item[1]["point_scores"]["mae_mwh"] is None, item[1]["point_scores"]["mae_mwh"] or 0)):
            point = scores["point_scores"]
            versus = scores["versus_seasonal"]
            score_rows.append(f'<tr><td>{escape(model_label(model))}</td><td>{_fmt(point["mae_mwh"])}</td>'
                f'<td>{_fmt(point["rmse_mwh"])}</td><td>{scores["point_cases"]}</td><td>{versus["wins"]} / {versus["losses"]}</td>'
                f'<td>{_fmt(versus["mean_absolute_error_difference_mwh"])}</td></tr>')
            if "intervals" in scores:
                for level, values in scores["intervals"].items():
                    interval_rows.append(f'<tr><td>{escape(model_label(model))}</td><td>{float(level):.0%}</td>'
                        f'<td>{_fmt(values["coverage"] * 100)}%</td><td>{_fmt(values["mean_width_mwh"] / 1000)} GWh</td>'
                        f'<td>{_fmt(scores["pinball_mwh"])}</td><td>{scores["quantile_cases"]}</td>'
                        f'<td>{scores["negative_quantile_forecast_months"]}</td></tr>')
            subset = [row for row in records if row["model"] == model]
            selected = model == default_model
            options.append(f'<option value="{escape(model)}"{" selected" if selected else ""}>{escape(model_label(model))}</option>')
            panels.append(f'<div class="chart" data-panel="{target}:{model}"{" hidden" if not selected else ""}>'
                          f'{forecast_chart(subset, protocol["interval_levels"])}</div>')
        reference = {row["month"]: row for row in records if row["model"] == "same_month_previous_year"}
        for row in records:
            if row["model"].startswith("timestral_") and row["actual_mwh"] is not None:
                baseline = reference[row["month"]]["point_mwh"]
                if baseline is not None and row["point_mwh"] is not None:
                    delta = abs(row["point_mwh"] - row["actual_mwh"]) - abs(baseline - row["actual_mwh"])
                    if delta > 0:
                        loss_rows.append((delta, target, row["month"], row["model"]))
        dev_rows = ''.join(f'<tr><td>{escape(model_label(model))}</td><td>{_fmt(scores["point_scores"]["mae_mwh"])}</td><td>{scores["point_cases"]}</td></tr>'
                           for model, scores in phases["development"]["models"].items())
        title = {"solar": "Solare", "wind": "Eolico terra + mare", "load": "Carico elettrico",
                 "residual_load": "Carico residuo"}.get(target, target)
        negative_note = ("Il carico residuo può essere negativo: indica produzione solare/eolica superiore al carico zonale."
                         if target == "residual_load" else "Valori negativi segnalati, conservati senza clipping.")
        sections.append(f'''<section><h2>{escape(title)}</h2><p><b>{test['observed_months']}/{test['candidate_forecast_months']} mesi osservati completi</b> nel test finale.
I punteggi usano gli stessi mesi validi per tutti i concorrenti del rispettivo confronto.</p>
<h3>Errori sul totale mensile</h3><div class="scroll"><table><thead><tr><th>Modello</th><th>MAE MWh</th><th>RMSE MWh</th><th>Mesi comuni</th><th>Vince / perde vs anno prima</th><th>Δ MAE MWh</th></tr></thead><tbody>{''.join(score_rows)}</tbody></table></div>
<p class="small">Δ negativo: errore inferiore alla baseline stesso mese anno prima. La classifica descrive questo campione, non prova superiorità generale.</p>
<h3>Previsioni, osservazioni e intervalli</h3><label>Modello da visualizzare <select data-target="{target}">{''.join(options)}</select></label>{''.join(panels)}
<p class="small">Gli intervalli provengono dal singolo valore mensile, scalato nelle ore del mese. Nessuna somma di quantili orari. Un punto osservato mancante resta un'interruzione.</p>
<h3>Gli intervalli coprono davvero?</h3><div class="scroll"><table><thead><tr><th>Modello</th><th>Copertura nominale</th><th>Copertura osservata</th><th>Ampiezza media</th><th>Pinball MWh</th><th>Mesi comuni</th><th>Mesi con quantili negativi</th></tr></thead><tbody>{''.join(interval_rows)}</tbody></table></div>
<p class="small">Copertura e ampiezza vanno lette insieme: bande molto larghe possono coprire bene ma essere poco utili. Con pochi mesi le percentuali sono instabili.
Pinball è la media sui {len(protocol['comparison_quantile_levels'])} livelli comuni, non una metrica del singolo intervallo.</p>
<p class="small">Quantili negativi: diagnostica sulla griglia salvata (21 livelli Timestral, 5 per la baseline), non una classifica confrontabile. {negative_note}</p>
<h3>Errore per mese dell'anno · {escape(model_label(default_model))}</h3><div class="chart">{seasonal_error_chart(records, default_model)}</div>
<p class="small">Confronto predefinito {escape(model_label(default_model))} contro stesso mese anno prima: scelta di visualizzazione fissata dall'ordine del protocollo, non dal vincitore del test. Ogni barra usa soltanto uno o due casi.</p>
<details><summary>Risultati del periodo di sviluppo, separati dal test</summary><div class="scroll"><table><thead><tr><th>Modello</th><th>MAE MWh</th><th>Mesi comuni</th></tr></thead><tbody>{dev_rows}</tbody></table></div>
<p>Il warm-up e il minimo di coppie di calibrazione possono ridurre i casi comuni di sviluppo. Nessuna impostazione è stata scelta guardando il test finale.</p></details></section>''')
    losses = ''.join(f'<tr><td>{escape({"solar": "Solare", "wind": "Eolico"}.get(target, target))}</td><td>{escape(month)}</td><td>{escape(model_label(model))}</td><td>{_fmt(delta)}</td></tr>'
                     for delta, target, month, model in sorted(loss_rows, reverse=True))
    provenance = ''.join(f'<li>Timestral {escape(size)}: pesi {escape(info.get("weights_revision", "backend sintetico"))}; codice {escape(info.get("code_revision", "backend sintetico"))}</li>'
                         for size, info in result["models"].items())
    subtitle = ("Test sintetico con backend simulato" if result["kind"].startswith("synthetic_")
                else "Backtest reale retrospettivo")
    test_months = sorted({row["month"] for row in predictions if row["phase"] == "test"})
    test_period = test_months[0] + " → " + test_months[-1] if test_months else "nessun mese eseguito"
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SolarWindCast · Previsioni mensili e confronto reale</title><style>
body{{margin:0;background:#f2f6f7;color:#16313e;font:15px/1.6 system-ui}}main{{max-width:1200px;margin:auto;padding:30px 18px}}
header{{background:#16313e;color:white;padding:35px;border-radius:18px}}h1{{font-size:clamp(28px,4vw,44px);line-height:1.2}}
section{{background:white;padding:25px;border-radius:16px;margin:24px 0}}h3{{margin-top:30px}}svg{{width:100%;height:auto;display:block}}
.notice{{background:#fff0d7;border-left:4px solid #d98b12;padding:18px;margin:20px 0}}.scroll{{overflow-x:auto}}
table{{width:100%;border-collapse:collapse;min-width:760px;font-size:13px}}td,th{{padding:11px;text-align:left;border-bottom:1px solid #dce5e9}}
th{{font-size:11px;color:#526574}}.small{{font-size:12px;color:#526574}}select,button{{padding:9px;margin:6px;max-width:100%}}summary{{cursor:pointer}}
@media print{{button,select{{display:none}}[data-panel][hidden]{{display:block!important}}section{{break-inside:auto}}}}
@media(max-width:600px){{main{{padding:14px}}section,header{{padding:20px}}.chart{{overflow-x:auto}}.chart svg{{min-width:740px}}}}
</style></head><body><main><header><p>SolarWindCast · Step {result.get('step', 11)} · Zona di mercato Sud</p>
<h1>Quanto prevediamo per il mese successivo?</h1><p>{subtitle} · Test {escape(test_period)} · Totali in MWh · Calendario UTC</p></header>
<div class="notice"><b>Questi sono risultati di previsioni eseguite.</b> Gli errori del test sono separati dallo sviluppo. Non sono una previsione operativa del prossimo mese reale.
I dati sono revisionati e la disponibilità storica non è ricostruita. Pochi mesi non giustificano conclusioni certe su piccole differenze.</div>
<button onclick="window.print()">Stampa / Salva PDF</button>{''.join(sections)}
<section><h2>Quando Timestral perde contro la baseline annuale</h2><p>Tutti i casi del test in cui l'errore assoluto di Timestral supera quello dello stesso mese dell'anno precedente, ordinati dal peggior divario.</p>
<details><summary>Apri i {len(loss_rows)} confronti persi</summary><div class="scroll"><table><thead><tr><th>Target</th><th>Mese</th><th>Modello</th><th>Errore aggiuntivo MWh</th></tr></thead><tbody>{losses}</tbody></table></div></details></section>
<section><h2>Metodo e limiti</h2><p>{protocol['context_months']} mesi di contesto, emissione {protocol['issue_lead_hours']} ore prima dell'inizio del mese; il mese in corso è escluso.
Si prevedono {protocol['prediction_length_months']} passi mensili e si valuta solo l'ultimo. I target sono trattati separatamente; NaN conservati, nessun clipping nascosto.</p>
<p>Il meteo non è stato usato: non è stato verificato un archivio mensile coerente per tutto lo storico. La variante con calendario usa solo mese-seno e mese-coseno noti all'emissione.
Le varianti con meteo passato e futuro restano da eseguire dopo una verifica dedicata; non sono presentate come completate.</p>
<p>Non sono ricostruite revisioni storiche o capacità installata. Non è certificata l'assenza di sovrapposizione con il pretraining.
I benchmark dichiarati da Mistral non sono i risultati di questa pagina. CPU, pesi solo dalla cache; nessun riaddestramento.</p>
<ul>{provenance}</ul><p class="small">Hash dei pesi, codice, dati e protocollo nei JSON affiancati. predictions.json conserva ogni previsione e tutti i quantili nativi;
results.json conserva punteggi, denominatori ed esclusioni. manifest.json verifica i file.</p></section></main>
<script>document.querySelectorAll('select[data-target]').forEach(select=>select.addEventListener('change',()=>{{document.querySelectorAll('[data-panel]').forEach(panel=>{{if(panel.dataset.panel.startsWith(select.dataset.target+':'))panel.hidden=panel.dataset.panel!==select.dataset.target+':'+select.value;}});}}));</script>
</body></html>'''
