"""Audit observed calendar-month energy without imputing gaps or forecasting uncertainty."""

import argparse
import json
from hashlib import sha256
from html import escape
from io import StringIO
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import pandas as pd
import yaml
from matplotlib.figure import Figure

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset, fixed_step
from solarwindcast.real_data_html import COLORS, _fmt


def monthly_energy(dataset: TimeSeriesDataset, timezone: str) -> pd.DataFrame:
    """Integrate MW over complete calendar months; calendar boundaries need an explicit timezone."""
    dataset.validate()
    step = fixed_step(dataset.spec.frequency)
    values = dataset.frame.target.copy()
    values.index = values.index.tz_convert(timezone)
    rows = []
    for start, part in values.resample("MS", closed="left", label="left"):
        end = start + pd.DateOffset(months=1)
        expected_grid = pd.date_range(start, end, freq=step, inclusive="left")
        complete = part.index.equals(expected_grid) and part.notna().all()
        energy = float(part.sum() * (step / pd.Timedelta(hours=1))) if complete else None
        rows.append({"month": start.strftime("%Y-%m"), "start_utc": start.tz_convert("UTC").isoformat(),
            "end_exclusive_utc": end.tz_convert("UTC").isoformat(), "calendar_timezone": timezone,
            "expected_intervals": len(expected_grid), "represented_intervals": len(part),
            "valid_intervals": int(part.notna().sum()), "negative_intervals": int((part < 0).sum()),
            "complete": bool(complete), "energy_mwh": energy})
    return pd.DataFrame(rows)


def _energy_chart(months: pd.DataFrame, name: str) -> str:
    """Plot observed monthly totals, leaving gaps visible and using original energy units."""
    figure = Figure(figsize=(11, 3.4), layout="constrained")
    axes = figure.subplots()
    dates = pd.to_datetime(months["start_utc"], utc=True)
    axes.plot(dates, months.energy_mwh, color=COLORS.get(name, "#007c78"), marker="o", markersize=3)
    axes.set_xlim(dates.iloc[0], pd.Timestamp(months.end_exclusive_utc.iloc[-1]))
    axes.set_ylabel("Energia mensile (MWh)")
    axes.set_xlabel("Inizio del mese · UTC")
    axes.grid(axis="y", alpha=.2)
    axes.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=8))
    axes.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    for side in ("top", "right"):
        axes.spines[side].set_visible(False)
    if months.energy_mwh.notna().any() and months.energy_mwh.min() >= 0:
        axes.set_ylim(bottom=0)
    buffer = StringIO()
    with mpl.rc_context({"svg.fonttype": "none", "svg.hashsalt": "solarwindcast-monthly"}):
        figure.savefig(buffer, format="svg", metadata={"Date": None})
    text = buffer.getvalue()
    return text[text.index("<svg"):]


def save_monthly_report(prepared: Path, output: Path, timezone: str,
                         test_start_utc: str, test_end_exclusive_utc: str) -> Path:
    """Verify prepared artifacts and publish observed totals plus descriptive test availability."""
    if output.exists():
        raise FileExistsError("Scegliere una nuova cartella per il rapporto mensile.")
    manifest_path = prepared / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("Preparazione incompleta.")
    for name, digest in manifest["files_sha256"].items():
        path = (prepared / name).resolve()
        if not path.is_relative_to(prepared.resolve()) or sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Percorso o hash dei dati preparati non valido.")
    quality = json.loads((prepared / "quality.json").read_text(encoding="utf-8"))
    sections, summary = [], {}
    labels = {"solar": "Solare", "wind_onshore": "Eolico a terra", "wind_offshore": "Eolico in mare"}
    for name, details in quality.items():
        filename = name + ".parquet"
        if not name.isidentifier() or filename not in manifest["files_sha256"]:
            raise ValueError("Serie non verificata nel manifest.")
        if details.get("unit") != "MW":
            raise ValueError("I dati di ingresso devono dichiarare potenza media in MW.")
        frame = pd.read_parquet(prepared / filename)
        spec = DatasetSpec(details["target"], details["frequency"], (), (), (), details["provenance"])
        months = monthly_energy(TimeSeriesDataset(frame, spec), timezone)
        starts, ends = pd.to_datetime(months.start_utc, utc=True), pd.to_datetime(months.end_exclusive_utc, utc=True)
        in_test = (starts >= pd.Timestamp(test_start_utc)) & (ends <= pd.Timestamp(test_end_exclusive_utc))
        complete = int(months.complete.sum())
        test_complete = int(months.loc[in_test, "complete"].sum())
        records = json.loads(months.to_json(orient="records", double_precision=15))
        summary[name] = {"unit": "MWh", "observed_months": len(months), "complete_months": complete,
            "incomplete_months": len(months) - complete, "test_months": int(in_test.sum()),
            "complete_test_months": test_complete, "negative_intervals": int(months.negative_intervals.sum()),
            "records": records}
        rows = ''.join(f'<tr><td>{row.month}</td><td>{_fmt(row.energy_mwh)}</td>'
                       f'<td>{row.valid_intervals}/{row.expected_intervals}</td><td>{row.negative_intervals}</td><td>'
                       f'{"completo" if row.complete else "INCOMPLETO: totale non dichiarato"}</td></tr>'
                       for row in months.itertuples(index=False))
        sections.append(f'<section><h2>{escape(labels.get(name, name))}</h2><p>'
            f'<b>{complete}/{len(months)}</b> mesi completi · {test_complete}/{int(in_test.sum())} mesi completi '
            f'nel periodo di test proposto</p>{_energy_chart(months, name)}<details><summary>Tabella dei totali mensili osservati</summary>'
            f'<div class="scroll"><table><thead><tr><th>Mese</th><th>MWh</th><th>Intervalli validi/attesi</th>'
            f'<th>Negativi</th><th>Qualità</th></tr></thead><tbody>{rows}</tbody></table></div></details></section>')
    result = {"kind": "observed_monthly_energy_only", "forecast_computed": False,
        "calendar_timezone": timezone, "test_start_utc": test_start_utc,
        "test_end_exclusive_utc": test_end_exclusive_utc, "series": summary,
        "input_manifest_sha256": sha256(manifest_path.read_bytes()).hexdigest()}
    first_month = min(item["records"][0]["month"] for item in summary.values())
    last_month = max(item["records"][-1]["month"] for item in summary.values())
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SolarWindCast · Energia mensile osservata</title>
<style>body{{margin:0;background:#f2f6f7;color:#16313e;font:16px/1.6 system-ui}}main{{max-width:1160px;margin:auto;padding:30px 18px}}
header{{background:#16313e;color:white;padding:35px;border-radius:18px}}h1{{font-size:clamp(28px,4vw,44px);line-height:1.2}}
section{{background:white;padding:25px;border-radius:16px;margin:24px 0}}svg{{width:100%;height:auto}}.notice{{background:#fff0d7;border-left:4px solid #d98b12;padding:18px;margin:20px 0}}
.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;min-width:650px}}td,th{{text-align:left;padding:10px;border-bottom:1px solid #dce5e9}}summary,button{{cursor:pointer}}button{{padding:8px 14px}}
@media print{{details{{display:block}}button{{display:none}}section{{break-inside:avoid}}}}</style></head><body><main>
<header><p>SolarWindCast · Step 10 · Zona di mercato Sud</p><h1>Quanta energia è stata prodotta ogni mese?</h1>
<p>{escape(first_month)} → {escape(last_month)} · Osservazioni reali, in MWh · Calendario di ispezione: {escape(timezone)} · Nessuna previsione ancora eseguita</p></header>
<div class="notice"><b>Questi sono totali osservati, non previsioni.</b> Un mese incompleto resta senza totale: nessun buco è sostituito con zero.
Il calendario di questa ispezione non decide automaticamente i confini del mese del futuro protocollo.</div>
<button onclick="window.print()">Stampa / Salva PDF</button>{''.join(sections)}
<section><h2>Come leggere i risultati</h2><p>L'energia è la somma della potenza media per la durata degli intervalli.
La base oraria conserva soltanto ore complete: se manca un quarto d'ora, l'intera ora e il totale del mese restano incompleti.
Le assenze dichiarate da ENTSO-E, comprese componenti eoliche non restituite, non dimostrano produzione nulla.</p>
<p>Solare, eolico a terra e in mare restano separati. La zona Sud comprende la Puglia ma non coincide con la sola Puglia.</p></section>
<section><h2>Prima della valutazione delle previsioni</h2><p>Il test finale proposto copre {escape(test_start_utc)} → {escape(test_end_exclusive_utc)} (fine esclusa).
I mesi precedenti sono riservati allo sviluppo e alla scelta delle impostazioni.
I conteggi qui indicano solo quanti mesi osservati sarebbero disponibili: errori e copertura degli intervalli non sono stati misurati.</p>
<p>Vanno ancora scelti metodo, contesto, emissione, confini del mese, componenti eoliche e disponibilità delle covariate.
I quantili delle singole ore non si sommano per dichiarare gli intervalli del mese.
Le revisioni storiche, la prima pubblicazione e i cambiamenti della capacità installata non sono ricostruiti.
Nessun meteo futuro ricostruito è stato usato.</p></section>
<footer>Pagina autonoma offline · monthly_energy.json e manifest SHA-256 affiancati · Originali conservati</footer>
</main></body></html>'''
    output.mkdir(parents=True, exist_ok=False)
    files = {"presentazione.html": html, "monthly_energy.json": json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False)}
    hashes = {}
    for name, text in files.items():
        with (output / name).open("x", encoding="utf-8") as stream:
            stream.write(text)
        hashes[name] = sha256((output / name).read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    return output / "presentazione.html"


def main() -> None:
    """Create the configured monthly inspection from prepared local files, without network or models."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    root = args.config.resolve().parent.parent
    selection = config["monthly_inspection"]
    proposal = config["planning"]["step10"]["evaluation_proposal"]
    print(save_monthly_report(root / selection["prepared_directory"], args.output,
        selection["calendar_timezone"], proposal["test_start_utc"], proposal["test_end_exclusive_utc"]).resolve())


if __name__ == "__main__":
    main()
