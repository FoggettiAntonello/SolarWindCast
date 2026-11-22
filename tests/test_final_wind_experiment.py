"""Synthetic checks for causal test calibration, immutable settings and common-case gates."""

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from solarwindcast.final_wind_experiment import (
    assess_gates,
    causal_calibration,
    render_report,
    run_final,
)
from solarwindcast.monthly_experiment import score_predictions


def fixture() -> tuple[dict, dict, list[dict], list[dict]]:
    """Build predictable overdispersed forecasts across the development/test boundary."""
    config = yaml.safe_load((Path(__file__).resolve().parents[1] / 'configs/project.yaml').read_text(encoding='utf-8'))
    settings = config['final_wind_experiment']
    rows = []
    for i, month in enumerate(pd.period_range('2024-01', periods=15, freq='M')):
        rows.append({'model': settings['uncalibrated_control'], 'target': 'wind',
                     'phase': 'development' if i < 10 else 'test', 'month': str(month),
                     'target_start_utc': month.start_time.tz_localize('UTC').isoformat(),
                     'point_mwh': 100., 'actual_mwh': 98. if i % 2 else 102., 'metadata': {},
                     'quantiles_mwh': {'0.05': 60., '0.1': 70., '0.5': 100., '0.9': 130., '0.95': 140.}})
    return config['monthly_protocol'], settings, rows[:10], rows[10:]


def test_unavailable_months_do_not_affect_first_test_scale() -> None:
    protocol, settings, warmup, evaluation = fixture()
    original = deepcopy(warmup + evaluation)
    calibrated, trace = causal_calibration(warmup, evaluation, protocol, settings)
    assert trace[0]['available_through_month'] == '2024-09'
    assert trace[0]['calibration_months'] == [f'2024-{i:02}' for i in range(1, 10)]
    assert all(p['phase'] == 'test' for p in calibrated)
    changed_warmup, changed_eval = deepcopy(warmup), deepcopy(evaluation)
    changed_warmup[-1]['actual_mwh'] = 100000.
    changed_eval[0]['actual_mwh'] = -100000.
    changed_eval[-1]['actual_mwh'] = 999999.
    new, new_trace = causal_calibration(changed_warmup, changed_eval, protocol, settings)
    assert new[0]['quantiles_mwh'] == calibrated[0]['quantiles_mwh']
    assert new_trace[0]['scale'] == trace[0]['scale']
    assert warmup + evaluation == original
    assert '2024-10' in trace[1]['calibration_months']
    assert '2024-11' not in trace[1]['calibration_months']
    for before, after in zip(evaluation, calibrated, strict=True):
        assert before['point_mwh'] == after['point_mwh'] == after['quantiles_mwh']['0.5']
        values = list(after['quantiles_mwh'].values())
        assert values == sorted(values)


def test_duplicate_origins_and_phase_changes_rejected() -> None:
    protocol, settings, warmup, evaluation = fixture()
    with pytest.raises(ValueError):
        causal_calibration(warmup, evaluation + evaluation[:1], protocol, settings)
    changed = deepcopy(evaluation)
    changed[0]['phase'] = 'development'
    with pytest.raises(ValueError):
        causal_calibration(warmup, changed, protocol, settings)


def test_missing_warmup_is_excluded_instead_of_fitting_to_test_label() -> None:
    protocol, settings, _, evaluation = fixture()
    calibrated, trace = causal_calibration([], evaluation, protocol, settings)
    assert not calibrated and all(r['status'] == 'insufficient_history' for r in trace)


def test_stronger_rolling_baseline_can_fail_joint_mae_gate() -> None:
    protocol, settings, warmup, evaluation = fixture()
    calibrated, _ = causal_calibration(warmup, evaluation, protocol, settings)
    rows = calibrated + evaluation
    for name in [settings['reference'], *settings['baseline_methods']]:
        for row in evaluation:
            item = deepcopy(row)
            item['model'] = name
            item['point_mwh'] = item['actual_mwh'] if name == 'seasonal_empirical_rolling_errors' else 110.
            item['quantiles_mwh'] = {'0.05': 20., '0.1': 30., '0.5': item['point_mwh'], '0.9': 170., '0.95': 180.}
            rows.append(item)
    scores = score_predictions(rows, protocol)['wind']['test']
    result = assess_gates(scores, rows, settings)
    assert result['gates']['mae_vs_' + settings['reference']]
    assert not result['gates']['mae_vs_seasonal_empirical_rolling_errors']
    assert not result['gates']['minimum_point_cases']
    assert not result['all_pass'] and not result['operational_promotion']


def test_authorization_checked_before_reading_sources(tmp_path: Path) -> None:
    protocol, settings, _, _ = fixture()
    settings = deepcopy(settings)
    settings['execution_authorized'] = False
    with pytest.raises(RuntimeError, match='autorizzati'):
        run_final({'final_wind_experiment': settings, 'monthly_protocol': protocol}, tmp_path)


def test_report_shows_failures_common_cases_and_before_after() -> None:
    protocol, settings, warmup, evaluation = fixture()
    calibrated, trace = causal_calibration(warmup, evaluation, protocol, settings)
    rows = calibrated + evaluation
    for name in [settings['reference'], *settings['baseline_methods']]:
        for row in evaluation:
            item = deepcopy(row)
            item['model'] = name
            rows.append(item)
    scores = score_predictions(rows, protocol)['wind']['test']
    for m in scores['models'].values():
        m['point_excluded_utc'] = []
    result = {'settings': settings, 'scores': scores, 'trace': trace, 'new_inferences': 0,
              'assessment': assess_gates(scores, rows, settings)}
    html = render_report(result, rows)
    assert 'FALLITO' in html and 'Prima / dopo' in html
    assert 'Media recente' in html and 'Errori per mese' in html
    assert 'Nessuna ulteriore modifica del modello' in html and 'N/D%' not in html
