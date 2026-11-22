"""End-to-end synthetic profile tests with no model download or persistent fixtures."""

from collections.abc import Iterator
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from solarwindcast.backtest import BacktestConfig, build_models
from solarwindcast.backtest_demo import demonstration_project, main, run_demonstration


@pytest.fixture
def scratch(tmp_path: Path) -> Iterator[Path]:
    """Remove generated input/output files immediately after each test."""
    with TemporaryDirectory(dir=tmp_path) as directory:
        yield Path(directory)


def project() -> dict[str, object]:
    """Read the one project YAML without resolving operational placeholders."""
    path = Path(__file__).resolve().parents[1] / "configs/project.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_profile_does_not_change_operational_parameters() -> None:
    original = project()
    before = deepcopy(original)
    effective = demonstration_project(original, "step8")
    assert original == before and original["forecast"]["horizon_steps"] == "DA DECIDERE"
    assert original["models"]["timestral"]["enabled"] is False
    assert effective["forecast"]["horizon_steps"] == 8
    assert len(build_models(effective)) == 6  # constructors do not load model weights
    assert BacktestConfig.from_project_config(effective).number_of_windows == 3
    with pytest.raises(ValueError):
        BacktestConfig.from_project_config(original)


def test_complete_generation_features_prediction_evaluation_and_save(scratch: Path) -> None:
    config = project()
    config["demonstrations"]["step8"]["overrides"]["models"]["timestral"]["enabled"] = False
    result = run_demonstration(config, "step8")
    assert len(result.predictions) == 3 * 3 * 8
    assert result.metadata["purpose"] == "synthetic_validation_only"
    assert len(result.windows) == 3
    assert all("feature_report" not in window["models"]["baseline_persistence"]["forecast_metadata"]
               for window in result.windows)  # baseline uses target only
    assert result.input_snapshot["spec"]["provenance"].startswith("synthetic")
    result.save(scratch / "output")
    assert (scratch / "output/manifest.json").is_file()


def test_cli_and_existing_output_guard(scratch: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = project()
    config["demonstrations"]["step8"]["overrides"]["models"]["timestral"]["enabled"] = False
    config_path = scratch / "fixture.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["demo", "--config", str(config_path), "--profile", "step8",
                                    "--output", str(scratch / "result")])
    main()
    with pytest.raises(FileExistsError):
        main()


def test_synthetic_demo_cannot_enable_real_data_or_model_downloads() -> None:
    for key in ("data", "download"):
        config = project()
        overrides = config["demonstrations"]["step8"]["overrides"]
        if key == "data":
            overrides["execution"] = {"real_data_enabled": True}
        else:
            overrides["models"]["timestral"]["local_files_only"] = False
        with pytest.raises(ValueError):
            demonstration_project(config, "step8")


def test_baselines_only_does_not_construct_timestral(monkeypatch: pytest.MonkeyPatch) -> None:
    config = project()
    def fail_if_model_is_constructed(*args: object, **kwargs: object) -> None:
        """Fail before a model could load cached weights or attempt any download."""
        raise AssertionError('La demo senza pesi non deve costruire Timestral.')
    monkeypatch.setattr('solarwindcast.backtest.TimestralWrapper', fail_if_model_is_constructed)
    result = run_demonstration(config, 'step8', baselines_only=True)
    assert set(result.predictions['model']) == {'baseline_persistence','baseline_seasonal_naive','baseline_historical_quantiles'}
    assert result.metadata['baselines_only'] is True
    assert config['demonstrations']['step8']['overrides']['models']['timestral']['enabled'] is True
