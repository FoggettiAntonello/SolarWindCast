"""Synthetic source-block and provenance tests; no real data, network or secrets needed."""

import json
from collections.abc import Iterator
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest

from solarwindcast.entsoe_api import parse_generation_xml
from solarwindcast.entsoe_csv import ImportConfig
from solarwindcast.real_data_report import (
    InspectionSettings,
    inspect_acquisition,
    save_inspection,
)

EIC = "10Y1001A1001A788"


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Remove only disposable acquisition/report files after each test."""
    with TemporaryDirectory(dir=tmp_path) as temporary:
        yield Path(temporary)


def xml(points: tuple[tuple[int, str | None], ...] = ((1, "10"), (3, "20")),
        curve: str = "A03", periods: str | None = None) -> str:
    """Encode explicit block starts with optional genuinely missing quantities."""
    point_text = "".join(f'<Point><position>{position}</position>' +
                         (f'<quantity>{quantity}</quantity>' if quantity is not None else "") + "</Point>"
                         for position, quantity in points)
    if periods is None:
        periods = f'''<Period><timeInterval><start>2026-01-01T00:00Z</start>
            <end>2026-01-01T01:00Z</end></timeInterval><resolution>PT15M</resolution>{point_text}</Period>'''
    return f'''<GL_MarketDocument xmlns="urn:synthetic-entsoe-test"><type>A75</type>
        <process.processType>A16</process.processType><revisionNumber>1</revisionNumber>
        <createdDateTime>2026-01-02T00:00Z</createdDateTime><TimeSeries><businessType>A01</businessType>
        <inBiddingZone_Domain.mRID>{EIC}</inBiddingZone_Domain.mRID><MktPSRType><psrType>B16</psrType></MktPSRType>
        <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>{curve}</curveType>
        {periods}</TimeSeries></GL_MarketDocument>'''


def config() -> ImportConfig:
    """One hour on a quarter-hour native grid, strictly a fixture."""
    return ImportConfig("solar", EIC, ("Solar",), "2026-01-01T00:00:00Z",
                        "2026-01-01T01:00:00Z", "15min", ",", ".", "utf-8")


def acquisition(folder: Path) -> InspectionSettings:
    """Create an original snapshot containing fake request credentials that must stay private."""
    payload = xml().encode("utf-8")
    (folder / "response.xml").write_bytes(payload)
    (folder / "plan.json").write_text(json.dumps({"source": "entsoe", "start_utc": config().start_utc,
        "end_exclusive_utc": config().end_exclusive_utc, "expected_frequency": "15min",
        "private_field": "fake-private-value-not-for-report"}), encoding="utf-8")
    manifest = {"source": "entsoe", "complete": True, "items": [{"status": "complete",
        "raw_file": "response.xml", "sha256": sha256(payload).hexdigest(),
        "retrieved_utc": "2026-01-02T00:01:00Z", "request": {"securityToken": "fake-test-token"}}]}
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return InspectionSettings(folder, config().start_utc, config().end_exclusive_utc,
                              "15min", EIC, ("Solar",), True)


def test_a03_requires_explicit_opt_in_and_expands_constant_blocks() -> None:
    with pytest.raises(ValueError, match="A01"):
        parse_generation_xml(xml(), config(), EIC, "synthetic")
    result = parse_generation_xml(xml(), config(), EIC, "synthetic", allow_a03=True)
    assert result.dataset.frame.target.tolist() == [10, 10, 20, 20]
    assert result.report["curve_decoding"][0]["raw_points"] == 2
    assert result.report["curve_decoding"][0]["represented_intervals"] == 4


def test_a03_does_not_fill_missing_quantity_from_previous_block() -> None:
    result = parse_generation_xml(xml(((1, "10"), (3, None))), config(), EIC, "synthetic", allow_a03=True)
    assert result.dataset.frame.target.iloc[:2].tolist() == [10, 10]
    assert result.dataset.frame.target.iloc[2:].isna().all()


def test_a03_keeps_unrepresented_prefix_missing() -> None:
    result = parse_generation_xml(xml(((2, "10"), (4, "20"))), config(), EIC, "synthetic", allow_a03=True)
    assert pd.isna(result.dataset.frame.target.iloc[0])
    assert result.dataset.frame.target.iloc[1:].tolist() == [10, 10, 20]


def test_a03_never_propagates_values_across_period_gaps() -> None:
    periods = '''<Period><timeInterval><start>2026-01-01T00:00Z</start><end>2026-01-01T00:30Z</end></timeInterval>
        <resolution>PT15M</resolution><Point><position>1</position><quantity>10</quantity></Point></Period>
        <Period><timeInterval><start>2026-01-01T00:45Z</start><end>2026-01-01T01:00Z</end></timeInterval>
        <resolution>PT15M</resolution><Point><position>1</position><quantity>20</quantity></Point></Period>'''
    result = parse_generation_xml(xml(periods=periods), config(), EIC, "synthetic", allow_a03=True)
    assert result.dataset.frame.target.iloc[:2].tolist() == [10, 10]
    assert pd.isna(result.dataset.frame.target.iloc[2])
    assert result.dataset.frame.target.iloc[3] == 20


@pytest.mark.parametrize("points", [((1, "10"), (1, "20")), ((3, "10"), (1, "20"))])
def test_ambiguous_a03_is_rejected(points: tuple[tuple[int, str], ...]) -> None:
    with pytest.raises(ValueError, match="ambigua"):
        parse_generation_xml(xml(points), config(), EIC, "synthetic", allow_a03=True)


def test_a01_missing_positions_remain_missing_when_a03_is_enabled() -> None:
    result = parse_generation_xml(xml(curve="A01"), config(), EIC, "synthetic", allow_a03=True)
    assert result.dataset.frame.target.isna().tolist() == [False, True, False, True]


def test_inspection_statistics_units_and_original_hashes(scratch: Path) -> None:
    settings = acquisition(scratch)
    before = (scratch / "response.xml").read_bytes()
    result = inspect_acquisition(settings)
    stats = result.summary["statistics"]["solar"]
    assert stats["mean_mw"] == 15 and stats["energy_mwh"] == 15
    assert stats["expected"] == stats["valid"] == 4 and stats["missing"] == 0
    assert result.summary["model_predictions_computed"] is False
    assert (scratch / "response.xml").read_bytes() == before
    public = json.dumps(result.summary)
    assert "fake-test-token" not in public and "fake-private-value" not in public


def test_hash_mismatch_and_wrong_region_block_inspection(scratch: Path) -> None:
    settings = acquisition(scratch)
    with pytest.raises(ValueError, match="zona"):
        inspect_acquisition(replace(settings, area_eic="another-area"))
    (scratch / "response.xml").write_text(xml() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="Hash"):
        inspect_acquisition(settings)


def test_report_does_not_export_private_metadata_and_does_not_overwrite(scratch: Path) -> None:
    settings = acquisition(scratch)
    result = inspect_acquisition(settings)
    page = save_inspection(result, scratch / "report")
    text = page.read_text(encoding="utf-8")
    assert "<svg" in text and "fake-test-token" not in text and "fake-private-value" not in text
    manifest = json.loads((page.parent / "manifest.json").read_text())
    for name, digest in manifest["files_sha256"].items():
        assert sha256((page.parent / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        save_inspection(result, page.parent)


def test_genuine_missing_block_prevents_complete_period_energy(scratch: Path) -> None:
    settings = acquisition(scratch)
    payload = xml(((1, "10"), (3, None))).encode("utf-8")
    (scratch / "response.xml").write_bytes(payload)
    path = scratch / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["items"][0]["sha256"] = sha256(payload).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")
    result = inspect_acquisition(settings)
    assert result.summary["statistics"]["solar"]["missing"] == 2
    assert result.summary["statistics"]["solar"]["energy_mwh"] is None
    assert result.frame.solar.iloc[2:].isna().all()


def test_overlapping_documents_are_not_merged_silently(scratch: Path) -> None:
    settings = acquisition(scratch)
    (scratch / "second.xml").write_bytes((scratch / "response.xml").read_bytes())
    path = scratch / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["items"].append({**manifest["items"][0], "raw_file": "second.xml"})
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="sovrapposti"):
        inspect_acquisition(settings)
