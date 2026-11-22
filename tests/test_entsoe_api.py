"""Offline XML and fake-client tests: no external API or actual token is used."""

import json
import logging
import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest
import yaml

from solarwindcast.entsoe_api import (
    ApiSettings,
    NoGenerationDataError,
    fetch_generation,
    parse_generation_xml,
)
from solarwindcast.entsoe_csv import ImportConfig

EIC = "10Y1001A1001A788"


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Clean up every disposable raw response after its test."""
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield Path(directory)


def config() -> ImportConfig:
    """Use a fixture-only range and target."""
    return ImportConfig("solar", "BZN|IT-South", ("Solar",), "2026-11-01T00:00:00Z",
                        "2026-11-01T01:00:00Z", "15min", ",", ".", "utf-8")


def xml_fixture() -> str:
    """Build a small namespaced A75/A16 document with a missing position."""
    return f'''<GL_MarketDocument xmlns="urn:synthetic-entsoe-test">
      <mRID>synthetic-only</mRID><revisionNumber>1</revisionNumber>
      <type>A75</type><process.processType>A16</process.processType>
      <TimeSeries><inBiddingZone_Domain.mRID>{EIC}</inBiddingZone_Domain.mRID>
        <quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>A01</curveType>
        <MktPSRType><psrType>B16</psrType></MktPSRType><Period>
          <timeInterval><start>2026-11-01T00:00Z</start><end>2026-11-01T01:00Z</end></timeInterval>
          <resolution>PT15M</resolution>
          <Point><position>1</position><quantity>10</quantity></Point>
          <Point><position>3</position><quantity>20</quantity></Point>
          <Point><position>4</position><quantity>-1</quantity></Point>
        </Period></TimeSeries></GL_MarketDocument>'''


def settings(root: Path) -> ApiSettings:
    """Explicitly enable only fake-client calls, with a disposable dotenv path."""
    return ApiSettings(root / ".env", root / "request", "IT_SUD", 5, 1, 1, 1, True, True)


def test_xml_preserves_point_gaps_without_forward_filling() -> None:
    result = parse_generation_xml(xml_fixture(), config(), EIC, "synthetic XML")
    assert result.dataset is not None
    assert result.dataset.frame["target"].iloc[0] == 10
    assert pd.isna(result.dataset.frame["target"].iloc[1])
    assert result.dataset.frame["target"].iloc[2] == 20
    assert result.dataset.frame["target"].iloc[3] == -1


def test_duplicate_xml_point_is_reported_not_dropped() -> None:
    point = "<Point><position>1</position><quantity>99</quantity></Point>"
    xml = xml_fixture().replace("</Period>", point + "</Period>")
    result = parse_generation_xml(xml, config(), EIC, "synthetic XML")
    assert result.dataset is None
    assert "duplicate_component_interval" in {i["code"] for i in result.report["issues"]}


@pytest.mark.parametrize("old,new", [("A01", "A03"), ("MAW", "MWH"),
                                       (EIC, "different-domain"), ("A16", "A01"),
                                       ("<position>1</position>", "<position>0</position>")])
def test_unsupported_xml_fails_explicitly(old: str, new: str) -> None:
    with pytest.raises(ValueError):
        parse_generation_xml(xml_fixture().replace(old, new), config(), EIC, "synthetic")


def test_xml_dtd_is_rejected() -> None:
    with pytest.raises(ValueError, match="DTD"):
        parse_generation_xml("<!DOCTYPE x>" + xml_fixture(), config(), EIC, "synthetic")


def test_disabled_does_not_read_dotenv_or_create_files(scratch: Path) -> None:
    cfg = replace(settings(scratch), api_enabled=False)
    with pytest.raises(RuntimeError, match="disattivata"):
        fetch_generation(config(), cfg)
    assert list(scratch.iterdir()) == []


def test_missing_token_prevents_client_creation(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENTSOE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="assente"):
        fetch_generation(config(), settings(scratch))
    assert not (scratch / "request").exists()


def test_explicit_no_data_is_distinct_from_transport_failure(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from entsoe.exceptions import NoMatchingDataError

    monkeypatch.setenv("ENTSOE_API_KEY", "fake-secret")

    class NoDataClient:
        """Report provider absence, without a response body to preserve."""

        def __init__(self, **kwargs: object) -> None:
            pass

        def query_generation(self, **kwargs: object) -> str:
            raise NoMatchingDataError("fake-secret must never be printed")

    with pytest.raises(NoGenerationDataError):
        fetch_generation(config(), settings(scratch), NoDataClient)
    metadata = (scratch / "request/metadata.json").read_text()
    assert json.loads(metadata)["status"] == "no_matching_data"
    assert "fake-secret" not in metadata
    assert not (scratch / "request/response.xml").exists()


def test_fake_acquisition_saves_originals_and_uses_dotenv(
    scratch: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ENTSOE_API_KEY", raising=False)
    (scratch / ".env").write_text("ENTSOE_API_KEY=fake-test-only\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class FakeClient:
        """Return the fixture without any HTTP connection."""

        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

        def query_generation(self, **kwargs: object) -> str:
            captured.update(kwargs)
            return xml_fixture()

    result = fetch_generation(config(), settings(scratch), FakeClient)
    assert captured["api_key"] == "fake-test-only"
    assert captured["country_code"] == "IT_SUD"
    assert captured["timeout"] == 5
    assert result.dataset is not None
    raw = scratch / "request/response.xml"
    assert raw.read_text(encoding="utf-8") == xml_fixture()
    metadata = (scratch / "request/metadata.json").read_text(encoding="utf-8")
    assert "fake-test-only" not in metadata
    assert json.loads(metadata)["entsoe_py_version"] == "0.8.1"
    assert "ENTSOE_API_KEY" not in os.environ
    with pytest.raises(FileExistsError):
        fetch_generation(config(), settings(scratch), FakeClient)


def test_transport_error_and_debug_logs_do_not_expose_token(
    scratch: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("ENTSOE_API_KEY", "fake-test-secret")
    previous = logging.root.manager.disable

    class BrokenClient:
        """Simulate the installed library logging and throwing a token-bearing URL."""

        def __init__(self, **kwargs: object) -> None:
            logging.getLogger("entsoe.entsoe").critical("fake-test-secret")
            raise RuntimeError("securityToken=fake-test-secret")

    with pytest.raises(RuntimeError) as error:
        fetch_generation(config(), settings(scratch), BrokenClient)
    assert "fake-test-secret" not in str(error.value)
    assert "fake-test-secret" not in caplog.text
    assert logging.root.manager.disable == previous
    assert "fake-test-secret" not in (scratch / "request/metadata.json").read_text()


def test_bad_xml_remains_saved_for_audit(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENTSOE_API_KEY", "fake-test-only")

    class UnsupportedClient:
        """Return A03 while the ordinary API path deliberately remains strict."""

        def __init__(self, **kwargs: object) -> None:
            pass

        def query_generation(self, **kwargs: object) -> str:
            return xml_fixture().replace("A01", "A03")

    with pytest.raises(ValueError, match="A01"):
        fetch_generation(config(), settings(scratch), UnsupportedClient)
    assert (scratch / "request/response.xml").is_file()


def test_request_budget_and_real_data_gate(scratch: Path) -> None:
    with pytest.raises(RuntimeError, match="disattivata"):
        fetch_generation(config(), replace(settings(scratch), real_data_enabled=False))
    with pytest.raises(ValueError, match="chunk_days"):
        fetch_generation(replace(config(), end_exclusive_utc="2026-11-03T00:00:00Z"),
                         settings(scratch))


def test_library_hour_rounding_is_prevented(scratch: Path) -> None:
    with pytest.raises(ValueError, match="allineati all'ora"):
        fetch_generation(replace(config(), end_exclusive_utc="2026-11-01T00:45:00Z"),
                         settings(scratch))


def test_project_api_settings_stay_disabled(scratch: Path) -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    cfg = ApiSettings.from_project_config(project, scratch / ".env", scratch / "request")
    with pytest.raises(RuntimeError, match="disattivata"):
        fetch_generation(config(), cfg)
