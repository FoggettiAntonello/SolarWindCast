"""Offline Open-Meteo fixtures covering cache, UTC, nulls and forecast leakage."""

import json
from collections.abc import Iterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import pytest
import requests
import yaml

from solarwindcast.weather import (
    Location,
    WeatherClient,
    WeatherRequest,
    fetch_points,
    parse_response,
)


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Delete fake cached responses immediately after each test."""
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield Path(directory)


def request() -> WeatherRequest:
    """Return fixture parameters, not production settings."""
    return WeatherRequest("reanalysis", Location("test_point", 41.1, 16.8),
                          "2025-01-01T00:00:00Z", "2025-01-01T04:00:00Z", "era5",
                          ("temperature_2m", "wind_speed_100m", "shortwave_radiation", "cloud_cover"))


def payload() -> dict[str, object]:
    """Return synthetic hourly values, including a provider null."""
    return {"latitude": 41.0, "longitude": 16.75, "elevation": 10, "utc_offset_seconds": 0,
            "hourly_units": {"time": "iso8601", "temperature_2m": "°C", "wind_speed_100m": "m/s",
                             "shortwave_radiation": "W/m²", "cloud_cover": "%"},
            "hourly": {"time": ["2025-01-01T00:00", "2025-01-01T01:00",
                                "2025-01-01T02:00", "2025-01-01T03:00"],
                       "temperature_2m": [2.0, None, -1.0, 3.0], "wind_speed_100m": [1, 2, 3, 4],
                       "shortwave_radiation": [0, 0, 0, 0], "cloud_cover": [10, 20, 30, 40]}}


def response(data: dict[str, object], status: int = 200) -> requests.Response:
    """Build a Requests response with no network use."""
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(data).encode("utf-8")
    return result


def test_nulls_units_semantics_and_returned_grid_preserved() -> None:
    raw = payload()
    original = deepcopy(raw)
    result = parse_response(raw, request(), {})
    assert raw == original
    assert result.frame["temperature_2m"].isna().sum() == 1
    assert result.frame["temperature_2m"].iloc[2] == -1
    assert str(result.frame.index.tz) == "UTC"
    assert result.metadata["time_semantics"]["shortwave_radiation"] == "mean_over_preceding_hour"
    assert result.metadata["returned_grid"]["latitude"] == 41.0
    assert result.metadata["requested_location"]["latitude"] == 41.1


def test_gaps_and_boundary_rows_are_reported_without_interpolation() -> None:
    data = payload()
    for key in data["hourly"]:
        data["hourly"][key].pop(0)
    result = parse_response(data, request(), {})
    assert len(result.frame) == 4
    assert result.frame.iloc[0].isna().all()
    assert result.metadata["missing_timestamps"] == ["2025-01-01T00:00:00+00:00"]


@pytest.mark.parametrize("fault", ["offset", "duplicate", "length", "unit", "text", "inf", "api_error"])
def test_malformed_responses_fail(fault: str) -> None:
    data = payload()
    if fault == "offset":
        data["utc_offset_seconds"] = 3600
    elif fault == "duplicate":
        data["hourly"]["time"][1] = data["hourly"]["time"][0]
    elif fault == "length":
        data["hourly"]["temperature_2m"].pop()
    elif fault == "unit":
        data["hourly_units"]["wind_speed_100m"] = "km/h"
    elif fault == "text":
        data["hourly"]["temperature_2m"][0] = "bad"
    elif fault == "inf":
        data["hourly"]["temperature_2m"][0] = float("inf")
    else:
        data.update(error=True, reason="synthetic failure")
    with pytest.raises(ValueError):
        parse_response(data, request(), {})


def test_anomalies_reported_and_never_clipped() -> None:
    data = payload()
    data["hourly"]["cloud_cover"][0] = 120
    data["hourly"]["wind_speed_100m"][0] = -1
    result = parse_response(data, request(), {})
    assert result.frame["cloud_cover"].iloc[0] == 120
    assert len(result.metadata["anomaly_timestamps"]["wind_speed_100m"]) == 1


def test_immutable_cache_avoids_second_request_and_works_offline(scratch: Path) -> None:
    calls: list[dict[str, object]] = []

    def get(url: str, **kwargs: object) -> requests.Response:
        calls.append(kwargs)
        return response(payload())

    client = WeatherClient(scratch, 5, 1, 0, True)
    first = client.fetch(request(), get)
    second = replace(client, network_enabled=False).fetch(request(), get)
    pd.testing.assert_frame_equal(first.frame, second.frame)
    assert len(calls) == 1
    assert calls[0]["params"]["wind_speed_unit"] == "ms"
    assert first.metadata["cache_hit"] is False
    assert second.metadata["cache_hit"] is True
    assert first.metadata["retrieved_at_utc"] == second.metadata["retrieved_at_utc"]


def test_no_network_without_opt_in(scratch: Path) -> None:
    with pytest.raises(RuntimeError, match="disattivato"):
        WeatherClient(scratch, 5, 1, 0).fetch(request())


def test_cache_corruption_blocks_without_overwriting(scratch: Path) -> None:
    client = WeatherClient(scratch, 5, 1, 0, True)
    result = client.fetch(request(), lambda *args, **kwargs: response(payload()))
    path = Path(result.metadata["cache_path"])
    entry = json.loads(path.read_text())
    entry["raw_text"] = "{}"
    path.write_text(json.dumps(entry), encoding="utf-8")
    with pytest.raises(ValueError, match="corrotta"):
        client.fetch(request())


def test_request_identity_includes_model_coordinates_and_run(scratch: Path) -> None:
    client = WeatherClient(scratch, 5, 1, 0, True)
    client.fetch(request(), lambda *args, **kwargs: response(payload()))
    offline = replace(client, network_enabled=False)
    for changed in (replace(request(), model="other_model"),
                    replace(request(), location=Location("other", 42, 16)),
                    replace(request(), product="single_run", run_utc="2024-12-31T00:00:00Z")):
        with pytest.raises(RuntimeError, match="Cache assente"):
            offline.fetch(changed)


def test_retry_on_transport_failure(scratch: Path) -> None:
    calls: list[int] = []

    def get(*args: object, **kwargs: object) -> requests.Response:
        calls.append(1)
        if len(calls) == 1:
            raise requests.Timeout("synthetic timeout")
        return response(payload())

    WeatherClient(scratch, 5, 2, 0, True).fetch(request(), get)
    assert len(calls) == 2


def test_http_400_does_not_retry_or_poison_cache(scratch: Path) -> None:
    calls: list[int] = []

    def get(*args: object, **kwargs: object) -> requests.Response:
        calls.append(1)
        return response({"error": True}, status=400)

    with pytest.raises(requests.HTTPError):
        WeatherClient(scratch, 5, 2, 0, True).fetch(request(), get)
    assert len(calls) == 1
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("product", ["reanalysis", "historical_forecast"])
def test_reconstruction_and_stitched_history_cannot_be_future_features(product: str) -> None:
    result = parse_response(payload(), replace(request(), product=product), {})
    with pytest.raises(ValueError, match="operative"):
        result.future_at("2025-01-01T00:00:00Z")


def test_single_run_requires_eligible_origin_and_documented_delay() -> None:
    req = replace(request(), product="single_run", run_utc="2024-12-31T18:00:00Z",
                  archive_origin="operational_archive")
    result = parse_response(payload(), req, {})
    with pytest.raises(ValueError, match="ritardo"):
        result.future_at("2025-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="non disponibile"):
        result.future_at("2025-01-01T00:00:00Z", "7h", "synthetic assumption")
    assert len(result.future_at("2025-01-01T00:00:00Z", "6h", "synthetic assumption")) == 4
    for origin in ("unverified", "hindcast"):
        result.request = replace(req, archive_origin=origin)
        with pytest.raises(ValueError, match="operativo"):
            result.future_at("2025-01-01T00:00:00Z", "6h", "synthetic assumption")


def test_single_run_parameters_follow_live_api_constraints() -> None:
    req = replace(request(), product="single_run", run_utc="2024-12-31T18:00:00Z")
    params = req.parameters()
    assert "start_date" not in params and "end_date" not in params
    assert params["run"] == "2024-12-31T18:00"
    assert params["forecast_hours"] == 10


def test_current_forecast_snapshot_cannot_be_used_before_retrieval() -> None:
    result = parse_response(payload(), replace(request(), product="forecast"),
                            {"retrieved_at_utc": "2025-01-01T02:00:00Z"})
    with pytest.raises(ValueError, match="non disponibile"):
        result.future_at("2025-01-01T01:00:00Z")
    assert len(result.future_at("2025-01-01T02:00:00Z")) == 2


def test_yaml_placeholders_and_duplicate_points_are_rejected(scratch: Path) -> None:
    project = yaml.safe_load((Path(__file__).resolve().parents[1] /
                              "configs/project.yaml").read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="DA DECIDERE"):
        WeatherRequest.from_project_config(project, "unset", "reanalysis")
    assert WeatherClient.from_project_config(project, scratch).network_enabled is False
    with pytest.raises(ValueError, match="univoci"):
        fetch_points(WeatherClient(scratch, 5, 1, 0), (request(), request()))


@pytest.mark.parametrize("change", [{"model": "best_match"}, {"variables": ()},
    {"product": "unknown"}, {"start_utc": "2025-01-01"},
    {"end_exclusive_utc": "2025-01-01T00:30:00Z"}, {"product": "single_run"}])
def test_invalid_requests_are_rejected(change: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        replace(request(), **change).parameters()
