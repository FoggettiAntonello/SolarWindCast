"""Acquire approved ENTSO-E history in immutable, resumable local chunks."""

import argparse
import json
import time
from dataclasses import replace
from hashlib import sha256
from itertools import pairwise
from pathlib import Path
from xml.etree import ElementTree as ET

import pandas as pd
import yaml

from solarwindcast.entsoe_api import (
    ApiSettings,
    NoGenerationDataError,
    fetch_raw_generation,
)
from solarwindcast.entsoe_csv import ImportConfig
from solarwindcast.real_data_report import (
    InspectionSettings,
    inspect_acquisition,
    save_inspection,
)

CODES = {"Solar": "B16", "Wind Onshore": "B19", "Wind Offshore": "B18"}


def acquire_chunk(folder: Path, start: str, end: str, settings: ApiSettings,
                  components: tuple[str, ...]) -> list[InspectionSettings]:
    """Resume only hash-verified raw files; publish a complete manifest after validation."""
    folder.mkdir(parents=True, exist_ok=True)
    items, periods, absent_components = [], [], []
    for index, component in enumerate(components, start=1):
        request_folder = folder / f"request_{index:02d}"
        raw = request_folder / "response.xml"
        metadata_file = request_folder / "metadata.json"
        if metadata_file.exists() and (raw.exists() or json.loads(metadata_file.read_text(encoding="utf-8")).get("status") == "no_matching_data"):
            metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            if (metadata["start_utc"] != pd.Timestamp(start).isoformat()
                    or metadata["end_exclusive_utc"] != pd.Timestamp(end).isoformat()
                    or metadata["area_eic"] != "10Y1001A1001A788"
                    or (raw.exists() and sha256(raw.read_bytes()).hexdigest() != metadata["sha256"])):
                raise ValueError("Cache non coerente: nessuna sovrascrittura o riacquisizione nascosta.")
        else:
            # This grid bounds requests only; actual resolution is inspected below.
            config = ImportConfig("solar" if component == "Solar" else "wind", "IT_SUD",
                                  (component,), start, end, "1h", ",", ".", "utf-8")
            try:
                raw, metadata = fetch_raw_generation(config, replace(settings, raw_directory=request_folder),
                                                      psr_type=CODES[component])
            except NoGenerationDataError:
                metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
            time.sleep(settings.pause_seconds)
        if metadata.get("status") == "no_matching_data":
            if metadata.get("psr_type") != CODES[component]:
                raise ValueError("Assenza riferita a una componente diversa.")
            absent_components.append(component)
            items.append({"raw_file": metadata_file.relative_to(folder).as_posix(),
                "status": "no_matching_data", "component": component,
                "sha256": sha256(metadata_file.read_bytes()).hexdigest(),
                "retrieved_utc": metadata["received_at_utc"]})
            continue
        xml = raw.read_text(encoding="utf-8")
        if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise ValueError("XML con DTD non supportato.")
        document = ET.fromstring(xml)
        for node in document.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        for series in document.findall("TimeSeries"):
            if (series.findtext("MktPSRType/psrType") == CODES[component]
                    and series.findtext("inBiddingZone_Domain.mRID") == "10Y1001A1001A788"):
                for period in series.findall("Period"):
                    periods.append((component, pd.Timestamp(period.findtext("timeInterval/start")),
                                    pd.Timestamp(period.findtext("timeInterval/end")),
                                    pd.Timedelta(period.findtext("resolution"))))
        items.append({"raw_file": raw.relative_to(folder).as_posix(), "status": "complete",
                      "sha256": metadata["sha256"], "retrieved_utc": metadata["received_at_utc"]})
    segments = native_segments(periods, start, end, tuple(name for name in components if name not in absent_components))
    frequency = segments[0][2] if len(segments) == 1 else "mixed; see native_segments"
    plan = {"source": "entsoe", "start_utc": start, "end_exclusive_utc": end,
            "expected_frequency": frequency, "native_segments": segments}
    # Only local manifests are updated; immutable responses are never overwritten.
    (folder / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (folder / "manifest.json").write_text(json.dumps({"source": "entsoe", "complete": True,
                                                    "items": items}, indent=2), encoding="utf-8")
    inspections = [InspectionSettings(folder, begin, finish, step,
                   "10Y1001A1001A788", components, True, True, True) for begin, finish, step in segments]
    for inspection in inspections:
        inspect_acquisition(inspection)
    return inspections


def native_segments(periods: list[tuple[str, pd.Timestamp, pd.Timestamp, pd.Timedelta]],
                    start: str, end: str, components: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Separate changes of native resolution without copying, filling or resampling source values."""
    begin, finish = pd.Timestamp(start), pd.Timestamp(end)
    bounds = sorted({begin, finish} | {bound for _, a, b, _ in periods
                                      for bound in (a, b) if begin < bound < finish})
    segments = []
    for left, right in pairwise(bounds):
        frequencies = set()
        for component in components:
            steps = {step for name, a, b, step in periods
                     if name == component and a < right and b > left}
            if not steps:
                # A gap retains the unique resolution of that source; values remain NaN.
                steps = {step for name, _, _, step in periods if name == component}
            if len(steps) != 1:
                raise ValueError("Risoluzione ambigua nel blocco; nessuna conversione automatica.")
            frequencies.update(steps)
        if len(frequencies) != 1:
            raise ValueError("Frequenze diverse tra componenti: serve una scelta esplicita.")
        step = frequencies.pop()
        if step <= pd.Timedelta(0):
            raise ValueError("Risoluzione non positiva.")
        frequency = f"{step.value}ns"
        if segments and segments[-1][2] == frequency:
            segments[-1] = (segments[-1][0], right.isoformat(), frequency)
        else:
            segments.append((left.isoformat(), right.isoformat(), frequency))
    return segments


def main() -> None:
    """Run three approved probes or the approved monthly history, with a separate report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--phase", choices=("samples", "history"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Scegliere una nuova cartella per il rapporto.")
    project = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    root = args.config.resolve().parent.parent
    approved = project["planning"]["step10"]
    if approved["acquisition_authorized"] is not True:
        raise RuntimeError("Acquisizione non autorizzata.")
    components = tuple(approved["proposed_components"])
    options = approved["acquisition"]
    base = root / options["raw_directory"]
    settings = ApiSettings(root / ".env", base, "IT_SUD", options["timeout_seconds"],
                           options["retry_attempts"], options["pause_seconds"],
                           options["chunk_days"], True, True)
    if args.phase == "samples":
        for start in options["sample_dates_utc"]:
            begin = pd.Timestamp(start)
            end = begin + pd.Timedelta(days=1)
            chunk = acquire_chunk(base / "samples" / begin.strftime("%Y%m%d"),
                                   begin.isoformat(), end.isoformat(), settings, components)[0]
            result = inspect_acquisition(chunk)
            save_inspection(result, args.output / begin.strftime("%Y%m%d"))
            print(json.dumps({"sample": str(begin), "frequency": chunk.native_frequency,
                              "statistics": result.summary["statistics"]}), flush=True)
    else:
        # Refuse bulk work until all probes have been acquired and validated.
        for start in options["sample_dates_utc"]:
            date = pd.Timestamp(start)
            directory = base / "samples" / date.strftime("%Y%m%d")
            plan = json.loads((directory / "plan.json").read_text(encoding="utf-8"))
            inspect_acquisition(InspectionSettings(directory, plan["start_utc"],
                plan["end_exclusive_utc"], plan["expected_frequency"],
                "10Y1001A1001A788", components, True))
        boundaries = pd.date_range(approved["proposed_start_utc"],
                                   approved["proposed_end_exclusive_utc"], freq="MS")
        chunks = []
        for start, end in pairwise(boundaries):
            directory = base / "months" / start.strftime("%Y%m")
            if options.get("reuse_directory"):
                existing = root / options["reuse_directory"] / "months" / start.strftime("%Y%m")
                if (existing / "manifest.json").exists():
                    directory = existing
            month = acquire_chunk(directory,
                                   start.isoformat(), end.isoformat(), settings, components)
            chunks.extend(month)
            print(f"Verificato {start:%Y-%m}: {[part.native_frequency for part in month]}", flush=True)
        from solarwindcast.history_report import save_history_report

        print(save_history_report(chunks, args.output).resolve(), flush=True)


if __name__ == "__main__":
    main()
