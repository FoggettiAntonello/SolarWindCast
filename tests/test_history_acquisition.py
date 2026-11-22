"""Offline tests for native-resolution discovery and immutable resumable history chunks."""

import json
from hashlib import sha256
from pathlib import Path

import pandas as pd
import pytest

from solarwindcast.entsoe_api import (
    ApiSettings,
    NoGenerationDataError,
    parse_generation_xml,
)
from solarwindcast.entsoe_csv import ImportConfig
from solarwindcast.history_acquisition import (
    acquire_chunk,
    native_segments,
)
from solarwindcast.real_data_report import inspect_acquisition


def source_xml() -> str:
    """A constant one-hour A03 block on its true quarter-hour native grid."""
    return '''<GL_MarketDocument><type>A75</type><process.processType>A16</process.processType>
        <TimeSeries><businessType>A01</businessType>
        <inBiddingZone_Domain.mRID>10Y1001A1001A788</inBiddingZone_Domain.mRID>
        <MktPSRType><psrType>B16</psrType></MktPSRType>
        <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>A03</curveType>
        <Period><timeInterval><start>2024-11-01T00:00Z</start><end>2024-11-01T01:00Z</end></timeInterval>
        <resolution>PT15M</resolution><Point><position>1</position><quantity>20</quantity></Point>
        </Period></TimeSeries></GL_MarketDocument>'''


def test_native_segments_split_transition_without_expanding_hourly_values() -> None:
    start = pd.Timestamp("2024-12-01T00:00Z")
    switch = pd.Timestamp("2024-12-31T00:00Z")
    end = pd.Timestamp("2025-01-01T00:00Z")
    periods = [("Solar", start, switch, pd.Timedelta(hours=1)),
               ("Solar", switch, end, pd.Timedelta(minutes=15))]
    segments = native_segments(periods, start.isoformat(), end.isoformat(), ("Solar",))
    assert len(segments) == 2
    assert segments[0][1] == segments[1][0] == switch.isoformat()
    assert pd.Timedelta(segments[0][2]) == pd.Timedelta(hours=1)
    assert pd.Timedelta(segments[1][2]) == pd.Timedelta(minutes=15)


def test_parser_selects_native_period_without_changing_original_xml() -> None:
    hourly = source_xml().replace("PT15M", "PT60M")
    quarter_period = '''<Period><timeInterval><start>2024-11-01T01:00Z</start>
        <end>2024-11-01T02:00Z</end></timeInterval><resolution>PT15M</resolution>
        <Point><position>1</position><quantity>30</quantity></Point></Period>'''
    payload = hourly.replace("</TimeSeries>", quarter_period + "</TimeSeries>")
    digest = sha256(payload.encode()).hexdigest()
    config = ImportConfig("solar", "IT_SUD", ("Solar",), "2024-11-01T00:00Z",
                          "2024-11-01T01:00Z", "1h", ",", ".", "utf-8")
    result = parse_generation_xml(payload, config, "10Y1001A1001A788", "synthetic",
                                   allow_a03=True, restrict_periods=True)
    assert result.dataset.frame.target.tolist() == [20]
    assert len(result.report["curve_decoding"]) == 1
    assert sha256(payload.encode()).hexdigest() == digest


def test_absent_component_remains_nan_and_no_data_cache_is_reused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_fetch(config: ImportConfig, settings: ApiSettings,
                   psr_type: str) -> tuple[Path, dict[str, object]]:
        calls.append(psr_type)
        settings.raw_directory.mkdir()
        metadata = {"start_utc": config.start_utc, "end_exclusive_utc": config.end_exclusive_utc,
                    "area_eic": "10Y1001A1001A788", "psr_type": psr_type,
                    "received_at_utc": "2024-11-02T00:00:00Z"}
        path = settings.raw_directory / "metadata.json"
        if psr_type == "B18":
            metadata["status"] = "no_matching_data"
            path.write_text(json.dumps(metadata))
            raise NoGenerationDataError("synthetic provider absence")
        raw = settings.raw_directory / "response.xml"
        raw.write_text(source_xml(), encoding="utf-8")
        metadata["sha256"] = sha256(raw.read_bytes()).hexdigest()
        path.write_text(json.dumps(metadata))
        return raw, metadata

    monkeypatch.setattr("solarwindcast.history_acquisition.fetch_raw_generation", fake_fetch)
    monkeypatch.setattr("solarwindcast.history_acquisition.time.sleep", lambda _: None)
    settings = ApiSettings(tmp_path / ".env", tmp_path, "IT_SUD", 5, 1, 1, 31, True, True)
    start, end = "2024-11-01T00:00:00+00:00", "2024-11-01T01:00:00+00:00"
    args = (tmp_path / "chunk", start, end, settings, ("Solar", "Wind Offshore"))
    chunk = acquire_chunk(*args)[0]
    result = inspect_acquisition(chunk)
    assert result.frame.wind_offshore.isna().all()
    assert result.summary["statistics"]["wind_offshore"]["zeros"] == 0
    assert result.summary["statistics"]["wind_offshore"]["energy_mwh"] is None
    acquire_chunk(*args)
    assert calls == ["B16", "B18"]


def test_consumption_is_excluded_only_explicitly_and_counted() -> None:
    document = source_xml()
    series = document[document.index("<TimeSeries>"):document.index("</TimeSeries>") + len("</TimeSeries>")]
    consumption = series.replace("inBiddingZone_Domain", "outBiddingZone_Domain")
    payload = document.replace("</GL_MarketDocument>", consumption + "</GL_MarketDocument>")
    config = ImportConfig("solar", "IT_SUD", ("Solar",), "2024-11-01T00:00Z",
                          "2024-11-01T01:00Z", "15min", ",", ".", "utf-8")
    with pytest.raises(ValueError, match="consumo"):
        parse_generation_xml(payload, config, "10Y1001A1001A788", "synthetic", allow_a03=True)
    parsed = parse_generation_xml(payload, config, "10Y1001A1001A788", "synthetic",
                                   allow_a03=True, exclude_consumption=True)
    assert parsed.dataset.frame.target.tolist() == [20] * 4
    assert len(parsed.report["excluded_consumption_series"]) == 1


def test_chunk_is_resumable_and_retains_original_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_fetch(config: ImportConfig, settings: ApiSettings,
                   psr_type: str) -> tuple[Path, dict[str, object]]:
        calls.append(psr_type)
        settings.raw_directory.mkdir()
        raw = settings.raw_directory / "response.xml"
        raw.write_text(source_xml(), encoding="utf-8")
        metadata = {"start_utc": config.start_utc, "end_exclusive_utc": config.end_exclusive_utc,
                    "area_eic": "10Y1001A1001A788", "sha256": sha256(raw.read_bytes()).hexdigest(),
                    "received_at_utc": "2024-11-02T00:00:00Z"}
        (settings.raw_directory / "metadata.json").write_text(json.dumps(metadata))
        return raw, metadata

    monkeypatch.setattr("solarwindcast.history_acquisition.fetch_raw_generation", fake_fetch)
    monkeypatch.setattr("solarwindcast.history_acquisition.time.sleep", lambda _: None)
    settings = ApiSettings(tmp_path / ".env", tmp_path, "IT_SUD", 5, 1, 1, 31, True, True)
    folder = tmp_path / "months" / "202411"
    start, end = "2024-11-01T00:00:00+00:00", "2024-11-01T01:00:00+00:00"
    chunk = acquire_chunk(folder, start, end, settings, ("Solar",))[0]
    assert inspect_acquisition(chunk).summary["statistics"]["solar"]["energy_mwh"] == 20
    assert inspect_acquisition(chunk).summary["sources"][0]["file"] == "request_01/response.xml"
    acquire_chunk(folder, start, end, settings, ("Solar",))
    assert calls == ["B16"]
    raw = folder / "request_01" / "response.xml"
    raw.write_text(source_xml() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="Cache"):
        acquire_chunk(folder, start, end, settings, ("Solar",))
