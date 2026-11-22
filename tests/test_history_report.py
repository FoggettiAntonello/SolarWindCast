"""Synthetic mixed-frequency reports preserve native values and disclose gaps."""

import json
from pathlib import Path

import pandas as pd
import pytest

from solarwindcast.history_report import save_history_report
from solarwindcast.real_data_report import InspectionResult, InspectionSettings


@pytest.mark.parametrize("missing", [False, True])
def test_mixed_resolution_html_preserves_native_series(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing: bool,
) -> None:
    def fake_inspect(settings: InspectionSettings) -> InspectionResult:
        start, end = pd.Timestamp(settings.start_utc), pd.Timestamp(settings.end_exclusive_utc)
        index = pd.date_range(start, end, freq=settings.native_frequency, inclusive="left", name="timestamp_utc")
        frame = pd.DataFrame({"solar": 20.0}, index=index)
        if missing:
            frame.iloc[0, 0] = float("nan")
        valid = len(frame) - int(missing)
        stats = {"label": "Solare", "valid": valid, "expected": len(frame), "missing": int(missing),
                 "negative": 0, "max_mw": 20.0, "energy_mwh": None if missing else 480.0}
        daily = [{"date_utc": start.strftime("%Y-%m-%d"), "component": "solar",
                  "valid": valid, "expected": len(frame), "mean_mw": 20.0}]
        return InspectionResult(frame, {"start_utc": start.isoformat(), "end_exclusive_utc": end.isoformat(),
            "native_frequency": settings.native_frequency, "statistics": {"solar": stats},
            "daily": daily, "sources": []})

    monkeypatch.setattr("solarwindcast.history_report.inspect_acquisition", fake_inspect)
    chunks = [InspectionSettings(tmp_path, "2024-01-01T00:00Z", "2024-01-02T00:00Z", "1h", "eic", ("Solar",), True),
              InspectionSettings(tmp_path, "2024-01-02T00:00Z", "2024-01-03T00:00Z", "15min", "eic", ("Solar",), True)]
    page = save_history_report(chunks, tmp_path / "report")
    records = json.loads((page.parent / "native_series.json").read_text())
    assert len(records[0]["records"]) == 24 and len(records[1]["records"]) == 96
    assert all(row["solar"] in (20, None) for part in records for row in part["records"])
    if missing:
        assert all(part["records"][0]["solar"] is None for part in records)
    text = page.read_text(encoding="utf-8")
    assert "<svg" in text and "Risoluzione della fonte variabile" in text
    assert "Nessuna prestazione di Timestral" in text and "<script src" not in text
    summary = json.loads((page.parent / "analysis.json").read_text())
    assert summary["totals"]["solar"]["energy_mwh_complete_period_only"] == (None if missing else 960)
    with pytest.raises(ValueError, match="nuova"):
        save_history_report(chunks, page.parent)
    broken = [chunks[1], chunks[0]]
    with pytest.raises(ValueError, match="contigui"):
        save_history_report(broken, tmp_path / "invalid")
