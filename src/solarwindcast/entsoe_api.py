"""Opt-in entsoe-py acquisition preserving raw XML, with strict point parsing."""

import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import version
from itertools import pairwise
from pathlib import Path
from typing import Protocol
from xml.etree import ElementTree as ET

import pandas as pd
from dotenv import dotenv_values

from solarwindcast.entsoe_csv import (
    ImportConfig,
    ImportResult,
    convert_records,
    utc_timestamp,
)

PSR_TYPES = {"B16": "Solar", "B18": "Wind Offshore", "B19": "Wind Onshore"}


class NoGenerationDataError(RuntimeError):
    """Provider explicitly reports no matching data; never interpreted as zero generation."""


class RawClient(Protocol):
    """Minimal client interface, replaceable by a fake in offline tests."""

    def query_generation(self, country_code: str, start: pd.Timestamp,
                         end: pd.Timestamp) -> str:
        """Return generation XML text without parsing or normalizing points."""
        ...


@dataclass(frozen=True)
class ApiSettings:
    """Explicit opt-in and request budget; no token is stored in this object."""

    dotenv_path: Path
    raw_directory: Path
    market_area: str
    timeout_seconds: int
    retry_attempts: int
    pause_seconds: int
    chunk_days: int
    api_enabled: bool = False
    real_data_enabled: bool = False

    @classmethod
    def from_project_config(cls, project: Mapping[str, object],
                            dotenv_path: Path, raw_directory: Path) -> "ApiSettings":
        """Read flags and request limits; paths are explicit, never auto-discovered."""
        try:
            source = project["sources"]["entsoe"]
            return cls(dotenv_path=dotenv_path, raw_directory=raw_directory,
                       market_area=project["target"]["market_area"],
                       timeout_seconds=source["timeout_seconds"],
                       retry_attempts=source["retry_attempts"], pause_seconds=source["pause_seconds"],
                       chunk_days=source["chunk_days"], api_enabled=source["api_enabled"],
                       real_data_enabled=project["execution"]["real_data_enabled"])
        except (KeyError, TypeError) as exc:
            raise ValueError("Configurazione API incompleta.") from exc


def parse_generation_xml(xml: str, config: ImportConfig, area_eic: str,
                         provenance: str, allow_a03: bool = False,
                         restrict_periods: bool = False,
                         exclude_consumption: bool = False) -> ImportResult:
    """Parse A01 or explicitly opted-in A03 blocks, never imputing genuine gaps.

    A03 quantities hold until the next block or the end of that same Period,
    according to ENTSO-E CurveType v1.4 section 4.3. This is source decoding,
    not inference across missing observations. Empty quantities remain missing.
    """
    config.grid()
    if not isinstance(allow_a03, bool):
        raise TypeError("allow_a03 deve essere un consenso booleano esplicito alla decodifica.")
    if "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
        raise ValueError("XML con DTD o entità non supportato.")
    root = ET.fromstring(xml)
    # Drop namespace prefixes only from element names, preserving all point rows.
    for node in root.iter():
        node.tag = node.tag.rsplit("}", 1)[-1]
    if (root.findtext("type") != "A75" or root.findtext("process.processType") != "A16"):
        raise ValueError("Richiesto documento A75 di produzione osservata A16.")
    records: list[dict[str, object]] = []
    decoding: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for series_number, series in enumerate(root.findall("TimeSeries"), start=1):
        component = PSR_TYPES.get(series.findtext("MktPSRType/psrType"))
        if component not in config.production_types:
            continue
        if (exclude_consumption is True and series.find("inBiddingZone_Domain.mRID") is None
                and series.findtext("outBiddingZone_Domain.mRID") == area_eic):
            excluded.append({"component": component, "series_number": series_number,
                             "reason": "actual consumption; excluded, never subtracted from generation"})
            continue
        if (series.findtext("inBiddingZone_Domain.mRID") != area_eic
                or series.find("outBiddingZone_Domain.mRID") is not None):
            raise ValueError("Dominio inatteso o serie di consumo nella produzione selezionata.")
        curve = series.findtext("curveType")
        allowed_curves = ("A01", "A03") if allow_a03 else ("A01",)
        if series.findtext("quantity_Measure_Unit.name") != "MAW" or curve not in allowed_curves:
            raise ValueError("Supportati solo MW e punti espliciti con curva A01; nessun riempimento.")
        for period_number, period in enumerate(series.findall("Period"), start=1):
            start = utc_timestamp(period.findtext("timeInterval/start"))
            end = utc_timestamp(period.findtext("timeInterval/end"))
            if restrict_periods and (end <= utc_timestamp(config.start_utc)
                                     or start >= utc_timestamp(config.end_exclusive_utc)):
                continue
            step = pd.Timedelta(period.findtext("resolution"))
            if step <= pd.Timedelta(0) or end <= start or (end - start) % step != pd.Timedelta(0):
                raise ValueError("Periodo o risoluzione XML non validi.")
            points = period.findall("Point")
            positions = [int(point.findtext("position")) for point in points]
            number_of_intervals = int((end - start) // step)
            if any(not 1 <= position <= number_of_intervals for position in positions):
                raise ValueError("Posizione XML fuori dal periodo.")
            if curve == "A03" and any(a >= b for a, b in pairwise(positions)):
                raise ValueError("A03 con posizioni duplicate o non ordinate: decodifica ambigua.")
            expanded = 0
            for index, (point, position) in enumerate(zip(points, positions, strict=True)):
                stop = (positions[index + 1] if index + 1 < len(positions) else number_of_intervals + 1)
                if curve == "A01":
                    stop = position + 1
                for native_position in range(position, stop):
                    timestamp = start + (native_position - 1) * step
                    records.append({"start": timestamp, "end": timestamp + step,
                                    "component": component, "value": point.findtext("quantity", ""),
                                    "source_row": f"TS={series_number}/P={period_number}/point={position}"})
                    expanded += 1
            decoding.append({"component": component, "curve_type": curve,
                             "raw_points": len(points), "represented_intervals": expanded,
                             "period_start_utc": start.isoformat(), "period_end_utc": end.isoformat(),
                             "resolution": str(step)})
    columns = ["start", "end", "component", "value", "source_row"]
    result = convert_records(pd.DataFrame(records, columns=columns), config, provenance)
    result.report["curve_decoding"] = decoding
    result.report["excluded_consumption_series"] = excluded
    return result


def fetch_raw_generation(config: ImportConfig, settings: ApiSettings,
                         client_factory: Callable[..., RawClient] | None = None,
                         psr_type: str | None = None) -> tuple[Path, dict[str, object]]:
    """Acquire one bounded request only after two explicit flags and a nonempty token.

    A fresh output directory is required. XML is saved before conversion, including
    on parsing failure. Transport exceptions and library debug logs are suppressed
    to prevent securityToken URLs entering output. No actual call occurs in tests.
    """
    if settings.api_enabled is not True or settings.real_data_enabled is not True:
        raise RuntimeError("API disattivata: servono api_enabled e real_data_enabled espliciti.")
    if psr_type is not None and psr_type not in PSR_TYPES:
        raise ValueError("Tipo di produzione non supportato.")
    grid = config.grid()
    for name in ("timeout_seconds", "retry_attempts", "pause_seconds", "chunk_days"):
        value = getattr(settings, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name}: specificare un intero positivo.")
    start, end = grid[0], utc_timestamp(config.end_exclusive_utc)
    if end - start > pd.Timedelta(days=settings.chunk_days):
        raise ValueError("Richiesta oltre chunk_days: suddividerla esplicitamente prima dell'acquisizione.")
    # Installed entsoe-py 0.8.1 rounds request limits to the nearest hour.
    if any(t != t.floor("h") for t in (start, end)):
        raise ValueError("entsoe-py 0.8.1 richiede limiti API allineati all'ora; nessun arrotondamento.")
    token = os.environ.get("ENTSOE_API_KEY")
    if token is None:
        token = dotenv_values(settings.dotenv_path, interpolate=False).get("ENTSOE_API_KEY")
    if not token or not token.strip():
        raise RuntimeError("Token ENTSO-E assente: nessuna richiesta eseguita.")
    from entsoe import EntsoeRawClient
    from entsoe.exceptions import NoMatchingDataError
    from entsoe.mappings import lookup_area

    area_eic = lookup_area(settings.market_area).value
    # No existing raw response or directory is overwritten.
    settings.raw_directory.mkdir(parents=True, exist_ok=False)
    metadata = {
        "source": "ENTSO-E API via entsoe-py", "entsoe_py_version": version("entsoe-py"),
        "market_area": settings.market_area, "area_eic": area_eic,
        "start_utc": start.isoformat(), "end_exclusive_utc": end.isoformat(),
        "requested_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "publication_availability": "not reconstructed; raw revisions preserved",
        "psr_type": psr_type,
    }
    failed, no_data = False, False
    previous_logging = logging.root.manager.disable
    try:
        # Installed 0.8.1 logs the token at DEBUG; also silence urllib3 request URLs.
        logging.disable(logging.CRITICAL)
        client = (client_factory or EntsoeRawClient)(api_key=token,
            timeout=settings.timeout_seconds, retry_count=settings.retry_attempts,
            retry_delay=settings.pause_seconds)
        parameters = {"country_code": settings.market_area, "start": start, "end": end}
        if psr_type is not None:
            parameters["psr_type"] = psr_type
        xml = client.query_generation(**parameters)
    except NoMatchingDataError:
        no_data = True
    except Exception:  # noqa: BLE001 -- secret boundary: any client exception may contain the token.
        failed = True
    finally:
        logging.disable(previous_logging)
    if no_data:
        metadata.update(status="no_matching_data", received_at_utc=pd.Timestamp.now(tz="UTC").isoformat(),
                        response_note="entsoe-py raised NoMatchingDataError; response body unavailable")
        (settings.raw_directory / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        raise NoGenerationDataError("La fonte non restituisce dati per questa richiesta: non sono zeri.")
    if failed:
        metadata["status"] = "transport_failed_details_omitted_for_secret_protection"
        (settings.raw_directory / "metadata.json").write_text(
            json.dumps(metadata, indent=2), encoding="utf-8")
        raise RuntimeError("Richiesta ENTSO-E fallita; dettagli omessi per proteggere il token.")
    if not isinstance(xml, str) or token in xml:
        raise RuntimeError("Risposta inattesa: non salvata per proteggere il token.")
    raw_path = settings.raw_directory / "response.xml"
    raw_path.write_text(xml, encoding="utf-8")
    metadata.update(received_at_utc=pd.Timestamp.now(tz="UTC").isoformat(),
                    sha256=sha256(raw_path.read_bytes()).hexdigest())
    (settings.raw_directory / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8")
    return raw_path, metadata


def fetch_generation(config: ImportConfig, settings: ApiSettings,
                     client_factory: Callable[..., RawClient] | None = None) -> ImportResult:
    """Fetch immutable XML and parse strict A01; native inspection may use the raw helper."""
    raw_path, metadata = fetch_raw_generation(config, settings, client_factory)
    xml = raw_path.read_text(encoding="utf-8")
    result = parse_generation_xml(xml, config, str(metadata["area_eic"]),
                                  f"ENTSO-E API XML: {raw_path.resolve()}")
    result.report["acquisition"] = metadata
    return result
