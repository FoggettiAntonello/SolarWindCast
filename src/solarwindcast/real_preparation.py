"""Prepare complete common-grid targets from audited native observations, without network."""

import argparse
import json
from dataclasses import replace
from hashlib import sha256
from html import escape
from pathlib import Path

import pandas as pd
import yaml

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset, fixed_step


def complete_interval_mean(dataset: TimeSeriesDataset, frequency: str) -> TimeSeriesDataset:
    """Average only fully observed aligned target intervals; never upsample or fill NaN."""
    dataset.validate()
    if list(dataset.frame.columns) != ["target"]:
        raise ValueError("Aggregare solo il target; costruire le covariate dopo questa preparazione.")
    native, output = fixed_step(dataset.spec.frequency), fixed_step(frequency)
    if output < native or output % native != pd.Timedelta(0):
        raise ValueError("Nessuna espansione o conversione con rapporti di frequenza non interi.")
    index = dataset.frame.index
    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    if ((index[0] - epoch) % output != pd.Timedelta(0)
            or (index[-1] + native - epoch) % output != pd.Timedelta(0)):
        raise ValueError("I confini del segmento devono coincidere con la griglia di destinazione.")
    grouped = dataset.frame.resample(frequency, origin="epoch", label="left", closed="left")
    expected = int(output // native)
    frame = grouped.mean().where(grouped.count().eq(expected))
    frame.index.name = "timestamp_utc"
    result = TimeSeriesDataset(frame, replace(dataset.spec, frequency=frequency,
        provenance=dataset.spec.provenance + "; complete native intervals mean; no imputation"))
    result.validate()
    return result


def prepare_targets(source: Path, rules: list[dict[str, object]], frequency: str) -> dict[str, TimeSeriesDataset]:
    """Verify all report hashes, then join contiguous native segments on an approved coarser grid."""
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = manifest["files_sha256"]
    if manifest.get("status") != "complete" or set(files) != {"analysis.json", "native_series.json", "presentazione.html"}:
        raise ValueError("Rapporto nativo incompleto o file inattesi.")
    for name, digest in files.items():
        if sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Hash del rapporto nativo non corrispondente.")
    summary = json.loads((source / "analysis.json").read_text(encoding="utf-8"))
    segments = json.loads((source / "native_series.json").read_text(encoding="utf-8"))
    if len(segments) != len(summary["chunks"]) or not segments:
        raise ValueError("Segmenti e metadati non corrispondenti.")
    names = [rule["name"] for rule in rules]
    if not rules or len(names) != len(set(names)):
        raise ValueError("Specificare serie con nomi distinti.")
    for name in names:
        if not isinstance(name, str) or not name.isidentifier():
            raise ValueError("Nome serie non valido per il salvataggio.")
    pieces = {name: [] for name in names}
    previous_end = None
    provenance = "audited native report SHA-256 " + sha256(manifest_path.read_bytes()).hexdigest()
    for segment, metadata in zip(segments, summary["chunks"], strict=True):
        frame = pd.DataFrame.from_records(segment["records"])
        frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("timestamp_utc"), utc=True, format="ISO8601"),
                                       name="timestamp_utc")
        step = fixed_step(segment["native_frequency"])
        start, end = pd.Timestamp(metadata["start_utc"]), pd.Timestamp(metadata["end_exclusive_utc"])
        if (frame.index.empty or frame.index[0] != start or frame.index[-1] + step != end
                or segment["start_utc"] != metadata["start_utc"]
                or fixed_step(metadata["native_frequency"]) != step
                or (previous_end is not None and start != previous_end)):
            raise ValueError("Segmenti non contigui o griglia incompatibile con la provenienza.")
        previous_end = end
        for rule in rules:
            components = rule["components"]
            if (not isinstance(components, list) or not components or len(set(components)) != len(components)
                    or not set(components).issubset(frame.columns)):
                raise ValueError("Componenti esplicite, presenti e univoche obbligatorie.")
            spec = DatasetSpec(rule["target"], segment["native_frequency"], (), (), (), provenance)
            for component in components:
                if frame[component].isna().all():
                    frame[component] = frame[component].astype(float)
                TimeSeriesDataset(frame[[component]].rename(columns={component: "target"}), spec).validate()
            values = frame[components].sum(axis=1, min_count=len(components))
            dataset = TimeSeriesDataset(values.to_frame("target"), spec)
            pieces[rule["name"]].append(complete_interval_mean(dataset, frequency).frame)
    result = {}
    for rule in rules:
        spec = DatasetSpec(rule["target"], frequency, (), (), (), provenance)
        dataset = TimeSeriesDataset(pd.concat(pieces[rule["name"]]), spec)
        dataset.validate()
        result[rule["name"]] = dataset
    return result


def save_prepared(datasets: dict[str, TimeSeriesDataset], output: Path, report: Path,
                  proposal: dict[str, object]) -> Path:
    """Write immutable Parquet targets, quality metadata and a standalone Italian inspection page."""
    if output.exists() or report.exists():
        raise FileExistsError("Servono cartelle nuove: nessuna sovrascrittura.")
    if not datasets or any(not name.isidentifier() for name in datasets):
        raise ValueError("Servono serie con nomi validi per il salvataggio.")
    quality, rows = {}, []
    for name, dataset in datasets.items():
        dataset.validate()
        series = dataset.frame.target
        gaps = [stamp.isoformat() for stamp in series.index[series.isna()]]
        gap_preview = ", ".join(gaps[:5]) or "nessuno"
        if len(gaps) > 5:
            gap_preview += f"; altri {len(gaps) - 5} in quality.json"
        quality[name] = {"target": dataset.spec.target, "frequency": dataset.spec.frequency,
            "expected": len(series), "valid": int(series.notna().sum()), "missing": len(gaps),
            "missing_timestamps": gaps, "negative": int((series < 0).sum()),
            "provenance": dataset.spec.provenance, "unit": "MW",
            "aggregation_policy": "complete_intervals_mean", "timestamp_label": "interval start UTC"}
        rows.append(f'<tr><td>{escape(name)}</td><td>{len(series)}</td><td>{series.notna().sum()}</td>'
                    f'<td>{len(gaps)}</td><td>{escape(gap_preview)}</td></tr>')
    output.mkdir(parents=True, exist_ok=False)
    hashes = {}
    for name, dataset in datasets.items():
        filename = name + ".parquet"
        dataset.frame.to_parquet(output / filename, index=True)
        hashes[filename] = sha256((output / filename).read_bytes()).hexdigest()
    (output / "quality.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    hashes["quality.json"] = sha256((output / "quality.json").read_bytes()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}, indent=2), encoding="utf-8")
    if proposal.get("objective") == "next_calendar_month_total_energy":
        proposal_description = ("Obiettivo confermato: energia totale del prossimo mese di calendario, in MWh, "
            "separatamente per solare ed eolico. Contesto, emissione, confini del mese e metodo di incertezza "
            "restano da decidere. La disponibilità dei mesi completi va verificata prima del backtest. "
            "I quantili orari non possono essere semplicemente sommati per dichiarare un intervallo mensile.")
    else:
        proposal_description = (f"Proposta da approvare: previsione di {escape(str(proposal['horizon_hours']))} ore "
            f"con {escape(str(proposal['context_hours']))} ore di contesto, una nuova origine ogni "
            f"{escape(str(proposal['stride_hours']))} ore. Periodi di sviluppo e test separati.")
    html = f'''<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>SolarWindCast · Griglia comune</title>
<style>body{{font:16px/1.6 system-ui;background:#f2f6f7;color:#16313e;margin:0}}main{{max-width:1050px;margin:auto;padding:30px 18px}}
header{{background:#16313e;color:white;border-radius:18px;padding:30px}}section{{background:white;padding:24px;border-radius:14px;margin:24px 0}}
.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;min-width:720px}}td,th{{text-align:left;padding:12px;border-bottom:1px solid #dce5e9}}
.note{{border-left:4px solid #d98b12;padding:16px;background:#fff0d7}}a{{color:#007c78}}</style></head><body><main>
<header><p>SolarWindCast · Step 10 · Zona Sud</p><h1>La stessa griglia per tutto lo storico</h1>
<p>Preparazione dei target · Frequenza {escape(next(iter(datasets.values())).spec.frequency)} · UTC · Nessuna previsione eseguita</p></header>
<section><h2>Copertura dopo la preparazione</h2><div class="scroll"><table><thead><tr><th>Serie</th><th>Attesi</th><th>Validi</th><th>Mancanti</th><th>Timestamp mancanti UTC</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div><p>La potenza resta in MW medi nell'intervallo. L'energia corrispondente richiede di moltiplicare per la durata in ore.</p></section>
<section><h2>Come sono stati trattati i dati</h2><p>Un valore orario originale resta tale. Quattro valori di 15 minuti diventano la loro media solo se tutti sono presenti.
Se ne manca uno, il risultato orario resta NaN: non usiamo la media dei tre rimasti. Nessun valore è interpolato, sostituito o eliminato.</p>
<p>Le serie eoliche sono preparate separatamente; la composizione del target finale resta da decidere. Il componente supporta anche carico e carico residuo tramite configurazione.</p>
<div class="note">Questa trasformazione rende confrontabili le frequenze; non ricostruisce ritardi di pubblicazione, revisioni storiche o meteo disponibile al momento della previsione.</div></section>
<section><h2>Prossima decisione: protocollo di valutazione</h2><p>{proposal_description}</p>
<p>Orario di emissione, ritardi, modelli, covariate e finestre sono ancora da concordare. Il test finale non deve guidare la scelta delle impostazioni.</p>
<p>Non sono state misurate prestazioni di Timestral o delle baseline. Questo è un controllo della preparazione, non un backtest.</p></section>
</main></body></html>'''
    report.mkdir(parents=True, exist_ok=False)
    page = report / "presentazione.html"
    page.write_text(html, encoding="utf-8")
    (report / "manifest.json").write_text(json.dumps({"files_sha256": {
        "presentazione.html": sha256(page.read_bytes()).hexdigest()}}, indent=2), encoding="utf-8")
    return page


def main() -> None:
    """Run the approved local preparation only; never acquire data or run models."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.report.exists():
        raise FileExistsError("Scegliere cartelle nuove.")
    config = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    preparation = config["preparation"]
    if preparation["enabled"] is not True or config["data"]["resampling_policy"] != "complete_intervals_mean":
        raise RuntimeError("Preparazione non autorizzata o politica inattesa.")
    root = args.config.resolve().parent.parent
    datasets = prepare_targets(root / preparation["source_report"], preparation["series"], config["data"]["frequency"])
    print(save_prepared(datasets, args.output, args.report,
                        config["planning"]["step10"]["evaluation_proposal"]).resolve())
    quality = json.loads((args.output / "quality.json").read_text(encoding="utf-8"))
    print(json.dumps({name: {field: values[field] for field in ("expected", "valid", "missing", "negative")}
                      for name, values in quality.items()}, indent=2))


if __name__ == "__main__":
    main()
