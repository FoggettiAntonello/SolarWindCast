"""Offline ENTSO-E CSV fixtures generated on demand and deleted after each test."""

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest
import yaml

from solarwindcast.entsoe_csv import COLUMNS, ImportConfig, read_csv


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Remove temporary CSV files immediately, without touching project data."""
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield Path(directory)


def config() -> ImportConfig:
    """Test-only half-hour range, not approved real-data settings."""
    return ImportConfig("solar", "BZN|IT-South", ("Solar",), "2026-11-01T00:00:00Z",
                        "2026-11-01T01:00:00Z", "15min", ",", ".", "utf-8")


def rows() -> list[list[str]]:
    """Return observed examples with an explicit missing token and a negative value."""
    return [
        ["01/11/2026 00:00:00 - 01/11/2026 00:15:00", "BZN|IT-South", "Solar", "10"],
        ["01/11/2026 00:30:00 - 01/11/2026 00:45:00", "BZN|IT-South", "Solar", "N/A"],
        ["01/11/2026 00:45:00 - 01/11/2026 01:00:00", "BZN|IT-South", "Solar", "-1"],
    ]


def write_csv(path: Path, records: list[list[str]], separator: str = ",") -> Path:
    """Write a disposable file in the manual export format."""
    pd.DataFrame(records, columns=COLUMNS).to_csv(path, index=False, sep=separator)
    return path


def test_gaps_values_hashes_and_source_unchanged(scratch: Path) -> None:
    path = write_csv(scratch / "synthetic.csv", rows())
    original = path.read_bytes()
    result = read_csv([path], config())
    assert result.dataset is not None
    frame = result.dataset.frame
    assert len(frame) == 4
    assert frame["target"].iloc[0] == 10
    assert frame["target"].iloc[3] == -1
    assert frame["target"].isna().sum() == 2
    assert result.report["missing_component_intervals"]["Solar"] == ["2026-11-01T00:15:00+00:00"]
    assert {i["code"] for i in result.report["issues"]} == {"negative_value", "declared_missing"}
    assert len(result.report["sources"][0]["sha256"]) == 64
    assert path.read_bytes() == original


@pytest.mark.parametrize("token", ["n/e", "N/A", ""])
def test_declared_missing_values(scratch: Path, token: str) -> None:
    records = rows()
    records[0][3] = token
    result = read_csv([write_csv(scratch / "data.csv", records)], config())
    assert result.dataset is not None
    assert pd.isna(result.dataset.frame["target"].iloc[0])


@pytest.mark.parametrize("value", ["oops", "inf", "NaN", "1,25", "1 000", "1e999"])
def test_unknown_numeric_anomalies_block_conversion(scratch: Path, value: str) -> None:
    records = rows()
    records[0][3] = value
    result = read_csv([write_csv(scratch / "data.csv", records)], config())
    assert result.dataset is None
    assert "invalid_number" in {i["code"] for i in result.report["issues"]}


@pytest.mark.parametrize("interval, issue", [
    ("bad interval", "invalid_interval"),
    ("01/11/2026 00:00:00 - 01/11/2026 00:30:00", "frequency_mismatch"),
    ("01/11/2026 00:01:00 - 01/11/2026 00:16:00", "off_grid"),
])
def test_bad_intervals(scratch: Path, interval: str, issue: str) -> None:
    records = rows()
    records[0][0] = interval
    result = read_csv([write_csv(scratch / "data.csv", records)], config())
    assert result.dataset is None
    assert issue in {i["code"] for i in result.report["issues"]}


def test_duplicate_files_block_instead_of_deduplicating(scratch: Path) -> None:
    first = write_csv(scratch / "one.csv", rows())
    second = write_csv(scratch / "two.csv", rows())
    result = read_csv([first, second], config())
    assert result.dataset is None
    assert "duplicate_component_interval" in {i["code"] for i in result.report["issues"]}


def test_wind_components_require_all_selected_values(scratch: Path) -> None:
    records = rows()[:1]
    records[0][2] = "Wind Onshore"
    offshore = [*records[0][:2], "Wind Offshore", "3"]
    next_onshore = ["01/11/2026 00:15:00 - 01/11/2026 00:30:00",
                    "BZN|IT-South", "Wind Onshore", "7"]
    cfg = replace(config(), target="wind", production_types=("Wind Onshore", "Wind Offshore"))
    result = read_csv([write_csv(scratch / "wind.csv", [*records, offshore, next_onshore])], cfg)
    assert result.dataset is not None
    assert result.dataset.frame["target"].iloc[0] == 13
    assert pd.isna(result.dataset.frame["target"].iloc[1])


def test_filters_area_sources_and_reports_boundary_gaps(scratch: Path) -> None:
    records = rows()
    records[0][1] = "BZN|IT-North"
    records[2][2] = "Wind Onshore"
    result = read_csv([write_csv(scratch / "filtered.csv", records)], config())
    assert result.dataset is not None
    assert result.dataset.frame["target"].isna().all()
    assert result.report["ignored_rows"] == 2
    assert len(result.report["missing_component_intervals"]["Solar"]) == 3


def test_configured_decimal_and_separator(scratch: Path) -> None:
    records = rows()
    records[0][3] = "10,5"
    cfg = replace(config(), decimal=",", separator=";")
    result = read_csv([write_csv(scratch / "decimal.csv", records, ";")], cfg)
    assert result.dataset.frame["target"].iloc[0] == 10.5


def test_no_selected_rows_and_incompatible_schema(scratch: Path) -> None:
    path = write_csv(scratch / "empty.csv", [])
    assert read_csv([path], config()).dataset is None
    bad = scratch / "wrong.csv"
    bad.write_text("time,value\n0,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="colonne"):
        read_csv([bad], config())


def test_project_yaml_rejects_unresolved_parameters() -> None:
    path = Path(__file__).resolve().parents[1] / "configs/project.yaml"
    project = yaml.safe_load(path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        ImportConfig.from_project_config(project)


@pytest.mark.parametrize("change", [
    {"start_utc": "2026-11-01"}, {"frequency": "ME"}, {"production_types": ()},
    {"target": "load"}, {"production_types": ("Solar", "Wind Onshore")},
    {"end_exclusive_utc": "2026-11-01T00:05:00Z"},
])
def test_invalid_configuration(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(config(), **change).grid()
