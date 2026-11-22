"""Strict load ingestion and residual demand on identical UTC grids, without imputation."""

import json
import logging
import os
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from dotenv import dotenv_values

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset, fixed_step
from solarwindcast.entsoe_csv import utc_timestamp

PRODUCTS = {
    "actual_load": ("query_load", "A65", "A16"),
    "day_ahead_load": ("query_load_forecast", "A65", "A01"),
    "month_ahead_load": ("query_load_forecast", "A65", "A32"),
    "day_ahead_renewables": ("query_wind_and_solar_forecast", "A69", "A01"),
}


def acquire_product(product: str, start: str, end: str, output: Path,
                    settings: dict[str, object], dotenv: Path,
                    client_factory: Callable[..., object] | None = None) -> dict[str, object]:
    """Save one bounded raw response before parsing; suppress secret-bearing transport errors."""
    if settings["authorized"] is not True or product not in PRODUCTS:
        raise RuntimeError("Acquisizione non autorizzata o prodotto sconosciuto.")
    first, stop = utc_timestamp(start), utc_timestamp(end)
    if (stop <= first or stop - first > pd.Timedelta(days=settings["maximum_request_days"])
            or any(stamp != stamp.floor("h") for stamp in (first, stop))):
        raise ValueError("Limiti della richiesta non validi; nessun arrotondamento.")
    if output.exists():
        raise FileExistsError("La risposta originale non può essere sovrascritta.")
    token = os.environ.get("ENTSOE_API_KEY")
    if token is None:
        token = dotenv_values(dotenv, interpolate=False).get("ENTSOE_API_KEY")
    if not token or not token.strip():
        raise RuntimeError("Token assente: nessuna richiesta eseguita.")
    from entsoe import EntsoeRawClient
    from entsoe.exceptions import NoMatchingDataError
    from entsoe.mappings import lookup_area

    method, document, process = PRODUCTS[product]
    area = lookup_area(settings["market_area"]).value
    metadata = {"product": product, "document_type": document, "process_type": process,
        "area_eic": area, "start_utc": first.isoformat(), "end_exclusive_utc": stop.isoformat(),
        "requested_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "availability": "current revision; first publication not reconstructed"}
    output.mkdir(parents=True, exist_ok=False)
    previous = logging.root.manager.disable
    xml, status = None, "complete"
    try:
        logging.disable(logging.CRITICAL)
        client = (client_factory or EntsoeRawClient)(api_key=token,
            timeout=settings["timeout_seconds"], retry_count=settings["retry_attempts"],
            retry_delay=settings["pause_seconds"])
        parameters = {"country_code": settings["market_area"], "start": first, "end": stop}
        if product != "actual_load":
            parameters["process_type"] = process
        xml = getattr(client, method)(**parameters)
    except NoMatchingDataError:
        status = "no_matching_data"
    except Exception:  # noqa: BLE001 -- URLs in any client exception may contain the token.
        status = "transport_failed_details_omitted"
    finally:
        logging.disable(previous)
    if status == "complete":
        if not isinstance(xml, str) or token in xml:
            status = "unsafe_response_not_saved"
        else:
            raw = output / "response.xml"
            raw.write_text(xml, encoding="utf-8")
            metadata["sha256"] = sha256(raw.read_bytes()).hexdigest()
    metadata.update(status=status, received_at_utc=pd.Timestamp.now(tz="UTC").isoformat())
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def xml_root(xml: str) -> ET.Element:
    """Parse namespace-independent XML while rejecting entity declarations."""
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("DTD ed entità non supportate.")
    root = ET.fromstring(xml)
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    return root


def inspect_product(xml: str) -> dict[str, object]:
    """Describe a response without interpreting weekly maxima/minima as interval mean power."""
    root = xml_root(xml)
    series = []
    for item in root.findall("TimeSeries"):
        series.append({"business_type": item.findtext("businessType"),
            "psr_type": item.findtext("MktPSRType/psrType"), "curve_type": item.findtext("curveType"),
            "unit": item.findtext("quantity_Measure_Unit.name"),
            "in_domain": item.findtext("inBiddingZone_Domain.mRID"),
            "out_domain": item.findtext("outBiddingZone_Domain.mRID"),
            "periods": [{"start": p.findtext("timeInterval/start"), "end": p.findtext("timeInterval/end"),
                "resolution": p.findtext("resolution"), "points": len(p.findall("Point"))}
                for p in item.findall("Period")]})
    return {"document_type": root.findtext("type"), "process_type": root.findtext("process.processType"),
        "created_utc": root.findtext("createdDateTime"), "revision": root.findtext("revisionNumber"),
        "series": series}


def intervals_to_dataset(records: list[tuple[pd.Timestamp, pd.Timestamp, float]],
                         start: str, end: str, frequency: str, provenance: str) -> TimeSeriesDataset:
    """Average only complete disjoint intervals; refuse overlap, upsampling and invalid values."""
    first, stop, step = utc_timestamp(start), utc_timestamp(end), fixed_step(frequency)
    if stop <= first or (stop - first) % step != pd.Timedelta(0):
        raise ValueError("Periodo incompatibile con la griglia.")
    grid = pd.date_range(first, stop, freq=step, inclusive="left", name="timestamp_utc")
    sums, covered, valid = np.zeros(len(grid)), np.zeros(len(grid), dtype=np.int64), np.ones(len(grid), dtype=bool)
    previous = None
    for left, right, value in sorted(records, key=lambda row: row[0]):
        if left.tzinfo is None or right.tzinfo is None or right <= left or np.isinf(value):
            raise ValueError("Intervallo o quantità non validi.")
        if previous is not None and left < previous:
            raise ValueError("Intervalli duplicati/sovrapposti: nessuna selezione nascosta di revisioni.")
        previous = right
        if right <= first or left >= stop:
            continue
        duration = right - left
        position = int((left - first) // step)
        if (left < first or right > stop or duration > step
                or step % duration != pd.Timedelta(0) or right > grid[position] + step):
            raise ValueError("Nessuna espansione; gli intervalli devono stare dentro la griglia richiesta.")
        covered[position] += duration.value
        if pd.isna(value):
            valid[position] = False
        else:
            sums[position] += value * (duration / step)
    values = np.where((covered == step.value) & valid, sums, np.nan)
    dataset = TimeSeriesDataset(pd.DataFrame({"target": values}, index=grid),
        DatasetSpec("load", frequency, (), (), (), provenance))
    dataset.validate()
    return dataset


def parse_load_xml(xml: str, start: str, end: str, frequency: str,
                   area_eic: str, provenance: str, process: str = "A16") -> TimeSeriesDataset:
    """Decode observed/day-ahead total load A65, A01/A03; never decode forecast extrema as energy."""
    root = xml_root(xml)
    if process not in ("A16", "A01") or root.findtext("type") != "A65" or root.findtext("process.processType") != process:
        raise ValueError("Serve carico totale A65 osservato o day-ahead; estremi mensili esclusi.")
    records = []
    for series in root.findall("TimeSeries"):
        if (series.findtext("outBiddingZone_Domain.mRID") != area_eic
                or series.findtext("quantity_Measure_Unit.name") != "MAW"
                or series.findtext("businessType") != "A04"
                or series.find("inBiddingZone_Domain.mRID") is not None):
            raise ValueError("Dominio, unità o business type del carico inattesi.")
        curve = series.findtext("curveType")
        if curve not in ("A01", "A03"):
            raise ValueError("Curva non supportata.")
        for period in series.findall("Period"):
            left, right = utc_timestamp(period.findtext("timeInterval/start")), utc_timestamp(period.findtext("timeInterval/end"))
            step = pd.Timedelta(period.findtext("resolution"))
            if step <= pd.Timedelta(0) or right <= left or (right - left) % step != pd.Timedelta(0):
                raise ValueError("Periodo XML non valido.")
            points = period.findall("Point")
            positions = [int(point.findtext("position")) for point in points]
            count = int((right - left) // step)
            if positions != sorted(set(positions)) or any(not 1 <= p <= count for p in positions):
                raise ValueError("Posizioni duplicate, non ordinate o fuori periodo.")
            for number, (point, position) in enumerate(zip(points, positions, strict=True)):
                raw = point.findtext("quantity")
                value = np.nan if raw in (None, "", "n/e", "N/A") else float(raw)
                stop = positions[number + 1] if number + 1 < len(positions) else count + 1
                for location in range(position, stop if curve == "A03" else position + 1):
                    timestamp = left + (location - 1) * step
                    records.append((timestamp, timestamp + step, value))
    if not root.findall("TimeSeries"):
        raise ValueError("Nessuna serie di carico; non equivale a zero.")
    return intervals_to_dataset(records, start, end, frequency, provenance)


def read_load_csv(path: Path, start: str, end: str, frequency: str,
                  columns: dict[str, str], area: str, separator: str,
                  decimal: str, encoding: str) -> TimeSeriesDataset:
    """Read explicitly mapped manual CSV columns; dates are day/month/year UTC intervals."""
    frame = pd.read_csv(path, sep=separator, encoding=encoding, dtype=str, keep_default_na=False)
    if not set(columns.values()).issubset(frame.columns) or set(columns) != {"interval", "area", "value"}:
        raise ValueError("Specificare colonne interval/area/value realmente presenti nel CSV.")
    records = []
    for _, row in frame.loc[frame[columns["area"]].eq(area)].iterrows():
        boundaries = row[columns["interval"]].split(" - ")
        if len(boundaries) != 2:
            raise ValueError("Intervallo CSV non riconosciuto.")
        left, right = [pd.to_datetime(value, format="%d/%m/%Y %H:%M:%S", utc=True) for value in boundaries]
        raw = row[columns["value"]].strip()
        value = np.nan if raw in ("", "n/e", "N/A") else float(raw.replace(decimal, "."))
        records.append((left, right, value))
    if not records:
        raise ValueError("Nessun record per l'area richiesta.")
    return intervals_to_dataset(records, start, end, frequency, "CSV SHA-256 " + sha256(path.read_bytes()).hexdigest())


def residual_load(load: TimeSeriesDataset, solar: TimeSeriesDataset,
                  wind: TimeSeriesDataset) -> TimeSeriesDataset:
    """Subtract observed renewables from observed load, retaining negative values and all missingness."""
    for dataset, target in ((load, "load"), (solar, "solar"), (wind, "wind")):
        dataset.validate()
        if (dataset.spec.target != target or dataset.spec.frequency != load.spec.frequency
                or not dataset.frame.index.equals(load.frame.index)):
            raise ValueError("Target, frequenze o griglie incompatibili; nessun riallineamento implicito.")
    values = load.frame.target - solar.frame.target - wind.frame.target
    provenance = "observed load - solar - wind; " + "; ".join(d.spec.provenance for d in (load, solar, wind))
    result = TimeSeriesDataset(values.to_frame("target"), DatasetSpec("residual_load", load.spec.frequency,
        (), (), (), provenance))
    result.validate()
    return result
