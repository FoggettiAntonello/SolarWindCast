"""Synthetic load intervals, signed residuals, secret protection and monthly extension integration."""

import json
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from solarwindcast.dataset import DatasetSpec, TimeSeriesDataset
from solarwindcast.load_data import (
    acquire_product,
    inspect_product,
    parse_load_xml,
    read_load_csv,
    residual_load,
)
from solarwindcast.load_experiment import (
    download_history,
    monthly_frame,
    read_response,
    run_extension,
)
from solarwindcast.load_results_html import save_probe_report
from solarwindcast.monthly_forecasting import MonthlyPrediction

AREA = "10Y1001A1001A788"
START, END = "2024-01-01T00:00Z", "2024-01-01T02:00Z"


def load_xml(points: str, curve: str = "A01", process: str = "A16",
             start: str = START, end: str = END, resolution: str = "PT15M") -> str:
    """Build namespace-qualified total load XML; fixture dates do not set real parameters."""
    return f'''<Publication_MarketDocument xmlns="urn:synthetic"><type>A65</type>
<process.processType>{process}</process.processType><TimeSeries><businessType>A04</businessType>
<outBiddingZone_Domain.mRID>{AREA}</outBiddingZone_Domain.mRID><quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>
<curveType>{curve}</curveType><Period><timeInterval><start>{start}</start><end>{end}</end></timeInterval>
<resolution>{resolution}</resolution>{points}</Period></TimeSeries></Publication_MarketDocument>'''


def point(position: int, value: str | None) -> str:
    """One explicit quantity or provider missing quantity."""
    quantity = f"<quantity>{value}</quantity>" if value is not None else ""
    return f"<Point><position>{position}</position>{quantity}</Point>"


def test_load_complete_hours_missing_quarters_and_a03_boundaries() -> None:
    xml = load_xml("".join(point(i, str(i)) for i in (1, 2, 3, 4, 5, 7, 8)))
    series = parse_load_xml(xml, START, END, "1h", AREA, "synthetic").frame.target
    assert series.iloc[0] == 2.5
    assert pd.isna(series.iloc[1])
    xml = load_xml(point(1, "4") + point(5, None), curve="A03")
    series = parse_load_xml(xml, START, END, "1h", AREA, "synthetic").frame.target
    assert series.iloc[0] == 4 and pd.isna(series.iloc[1])
    xml = load_xml(point(2, "4"), curve="A03")
    assert pd.isna(parse_load_xml(xml, START, END, "1h", AREA, "synthetic").frame.target.iloc[0])


@pytest.mark.parametrize("mutate", [
    lambda xml: xml.replace("A16", "A32"),
    lambda xml: xml.replace("A04", "A60"),
    lambda xml: xml.replace(AREA, "OTHER"),
    lambda xml: xml.replace("MAW", "MWH"),
    lambda xml: xml.replace("A01</curve", "A05</curve"),
    lambda xml: xml.replace("<quantity>1</quantity>", "<quantity>inf</quantity>"),
    lambda xml: xml.replace("</Period>", point(1, "2") + "</Period>"),
    lambda xml: "<!DOCTYPE x>" + xml,
])
def test_refuse_wrong_semantics_and_ambiguous_xml(mutate: Callable[[str], str]) -> None:
    with pytest.raises(ValueError):
        parse_load_xml(mutate(load_xml(point(1, "1"))), START, END, "1h", AREA, "synthetic")


def test_no_upsampling_and_overlap_between_series() -> None:
    xml = load_xml(point(1, "4"), resolution="PT2H")
    with pytest.raises(ValueError, match="espansione"):
        parse_load_xml(xml, START, END, "1h", AREA, "synthetic")
    xml = load_xml(point(1, "4"))
    root_end = "</Publication_MarketDocument>"
    duplicate = xml[xml.index("<TimeSeries>"):xml.index("</TimeSeries>") + len("</TimeSeries>")]
    with pytest.raises(ValueError, match="sovrapposti"):
        parse_load_xml(xml.replace(root_end, duplicate + root_end), START, END, "1h", AREA, "synthetic")


def test_csv_mapping_sign_and_complete_month_contract(tmp_path: Path) -> None:
    path = tmp_path / "load.csv"
    path.write_text("MTU (UTC);Area;Total Load (MW)\n01/01/2024 00:00:00 - 01/01/2024 01:00:00;SUD;10,5\n"
        "01/01/2024 01:00:00 - 01/01/2024 02:00:00;SUD;N/A\n", encoding="utf-8")
    load = read_load_csv(path, START, END, "1h", {"interval": "MTU (UTC)", "area": "Area", "value": "Total Load (MW)"},
        "SUD", ";", ",", "utf-8")
    solar = TimeSeriesDataset(pd.DataFrame({"target": [8., 8.]}, index=load.frame.index),
        DatasetSpec("solar", "1h", (), (), (), "synthetic"))
    wind = TimeSeriesDataset(pd.DataFrame({"target": [5., 5.]}, index=load.frame.index),
        DatasetSpec("wind", "1h", (), (), (), "synthetic"))
    residual = residual_load(load, solar, wind)
    assert residual.frame.target.iloc[0] == -2.5
    assert pd.isna(residual.frame.target.iloc[1])
    assert monthly_frame(residual, "UTC").energy_mwh.isna().all()
    assert load.frame.target.iloc[0] == 10.5
    solar.frame.index = solar.frame.index + pd.Timedelta(hours=1)
    with pytest.raises(ValueError, match="griglie"):
        residual_load(load, solar, wind)


def test_transport_secret_boundary_and_hashes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    token = "SECRET_TEST_TOKEN"
    monkeypatch.setenv("ENTSOE_API_KEY", token)
    settings = {"authorized": True, "market_area": "IT_SUD", "maximum_request_days": 31,
        "timeout_seconds": 1, "retry_attempts": 1, "pause_seconds": 1}

    class Broken:
        """Simulate a library exception whose URL contains a secret."""

        def __init__(self, **kwargs: object) -> None:
            pass

        def query_load(self, **kwargs: object) -> str:
            raise RuntimeError(token)

    meta = acquire_product("actual_load", START, END, tmp_path / "broken", settings, tmp_path / ".env", Broken)
    assert meta["status"] == "transport_failed_details_omitted"
    assert token not in (tmp_path / "broken/metadata.json").read_text()
    assert not (tmp_path / "broken/response.xml").exists()
    config = {"step12": {"authorized": True, "acquisition": {"history_download_authorized": False}}}
    with pytest.raises(RuntimeError, match="autorizzazione"):
        download_history(config, tmp_path)


def test_real_semantics_inspection_without_energy_from_extrema() -> None:
    info = inspect_product(load_xml(point(1, "40"), process="A32").replace("A04", "A60"))
    assert info["process_type"] == "A32" and info["series"][0]["business_type"] == "A60"


def test_sources_html_preserves_absence_and_hashes(tmp_path: Path) -> None:
    probes = [{"request": {"product": "day_ahead_renewables", "start_utc": START, "end_exclusive_utc": END},
        "metadata": {"status": "no_matching_data"}}]
    output = tmp_path / "source_report"
    save_probe_report(probes, output)
    page = (output / "presentazione.html").read_text(encoding="utf-8")
    assert "no_matching_data" in page and "non viene assunto uguale a zero" in page
    assert "Nessun nuovo risultato mensile" in page
    assert "<script src=" not in page
    for name, digest in json.loads((output / "manifest.json").read_text())["files_sha256"].items():
        assert sha256((output / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        save_probe_report(probes, output)


def test_end_to_end_extension_on_synthetic_observations(tmp_path: Path) -> None:
    original = yaml.safe_load((Path(__file__).resolve().parents[1] / "configs/project.yaml").read_text(encoding="utf-8"))
    protocol = original["monthly_protocol"]
    protocol.update(context_months=3, minimum_valid_context_months=2, baseline_seasonal_lag_months=2,
        residual_lookback_months=3, minimum_calibration_errors=2)
    protocol["models"] = protocol["models"][:1]
    index = pd.date_range("2024-01-01", "2024-11-01", freq="1h", inclusive="left", tz="UTC", name="timestamp_utc")
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    quality = {}
    for name, value in (("solar", 8.), ("wind_onshore", 5.), ("wind_offshore", 1.)):
        frame = pd.DataFrame({"target": value}, index=index)
        if name == "solar":
            frame.loc[index[-1], "target"] = np.nan
        frame.to_parquet(prepared / (name + ".parquet"))
        quality[name] = {"unit": "MW", "frequency": "1h"}
    (prepared / "quality.json").write_text(json.dumps(quality))
    hashes = {path.name: sha256(path.read_bytes()).hexdigest() for path in prepared.iterdir()}
    (prepared / "manifest.json").write_text(json.dumps({"status": "complete", "files_sha256": hashes}))
    periods = {"development_start_utc": "2024-01-01T00:00Z", "test_start_utc": "2024-07-01T00:00Z", "test_end_exclusive_utc": "2024-11-01T00:00Z"}
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    snapshot = {"settings": protocol, "settings_sha256": sha256(json.dumps(protocol, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        "source_prepared_manifest_sha256": sha256((prepared / "manifest.json").read_bytes()).hexdigest(), "evaluation_periods": periods}
    path = frozen / "protocol_snapshot.json"
    path.write_text(json.dumps(snapshot))
    (frozen / "manifest.json").write_text(json.dumps({"files_sha256": {path.name: sha256(path.read_bytes()).hexdigest()}}))
    raw = tmp_path / "raw"
    raw.mkdir()
    xml = load_xml("".join(point(i + 1, str(10 + int(stamp.month))) for i, stamp in enumerate(index)),
        start="2024-01-01T00:00Z", end="2024-11-01T00:00Z", resolution="PT60M")
    (raw / "response.xml").write_text(xml)
    (raw / "metadata.json").write_text(json.dumps({"product": "actual_load", "process_type": "A16", "area_eic": AREA,
        "status": "complete", "sha256": sha256((raw / "response.xml").read_bytes()).hexdigest(),
        "start_utc": "2024-01-01T00:00Z", "end_exclusive_utc": "2024-11-01T00:00Z"}))
    settings = {"authorized": True, "targets": ["load", "residual_load"], "production_directory": "prepared",
        "acquisition": {"market_area": "IT_SUD"},
        "output_directory": "out", "start_utc": "2024-01-01T00:00Z", "end_exclusive_utc": "2024-11-01T00:00Z"}
    config = {"step12": settings, "data": {"frequency": "1h"}, "monthly_protocol": protocol,
        "monthly_execution": {"authorized": True, "frozen_protocol_directory": "frozen", "cpu_threads": 1},
        "monthly_inspection": {"prepared_directory": "prepared"}}

    class SyntheticModel:
        """Deterministic model substitute; output must be explicitly marked synthetic."""

        def __init__(self, settings: dict[str, object], model: dict[str, str]) -> None:
            self.size, self.provenance = model["size"], {"backend": "synthetic"}

        def predict(self, months: pd.DataFrame, month: pd.Period, variant: str) -> MonthlyPrediction:
            value = float(months.loc[month - 2, "mean_power_mw"] * months.loc[month, "duration_hours"])
            return MonthlyPrediction("timestral_5M_" + variant, str(month), value,
                pd.Series({.05: value - 2, .1: value - 1, .5: value, .9: value + 1, .95: value + 2}), {})

    result = run_extension(config, tmp_path, [raw], [], SyntheticModel)
    assert result["kind"] == "synthetic_step12_test"
    assert len(result["frozen_snapshot_sha256"]) == 64
    assert result["inference_calls"] > 0
    assert "pandas" in result["versions"]
    inventory = json.loads((tmp_path / "out/source_inventory.json").read_text())
    assert inventory[0]["metadata_sha256"] == sha256((raw / "metadata.json").read_bytes()).hexdigest()
    assert result["quality"]["load"]["complete_months"] == 10
    assert result["quality"]["residual_load"]["complete_months"] == 9
    assert result["quality"]["residual_load"]["negative_hours"] > 0
    assert result["scores"]["load"]["test"]["observed_months"] == 4
    assert result["scores"]["residual_load"]["test"]["observed_months"] == 3
    html = (tmp_path / "out/presentazione.html").read_text(encoding="utf-8")
    assert "Step 12" in html and "backend simulato" in html and "<svg" in html
    assert "può essere negativo" in html and "Day-ahead" in html
    for name, digest in json.loads((tmp_path / "out/manifest.json").read_text())["files_sha256"].items():
        assert sha256((tmp_path / "out" / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        run_extension(config, tmp_path, [raw], [], SyntheticModel)
    (raw / "response.xml").write_text("tamper")
    with pytest.raises(ValueError, match="Hash"):
        read_response(raw)
