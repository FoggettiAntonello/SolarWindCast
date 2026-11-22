"""Synthetic protection against leakage, missing days, crossing bands and point changes."""

from copy import deepcopy

import numpy as np
import pytest

from solarwindcast.hourly_calibration import (
    apply_expansions,
    assess,
    available_history,
    fit_expansions,
    render_report,
    replay,
    run_replay,
    summarize,
)


def settings() -> dict:
    """Use small fixture-only counts while retaining the declared method."""
    return {'quantiles': [.05, .1, .5, .9, .95], 'interval_levels': [.8, .9],
            'horizon_hours': 24, 'assumed_delay_hours': 24, 'lookback_days': 180,
            'minimum_complete_origins': 2, 'source_model': 'timestral_5M',
            'preserve_median': True, 'enforce_nested_expansions': True}


def day(origin: str, actual: float = 30.) -> dict:
    """Return a deterministic complete forecast day with known undercoverage."""
    return {'target': 'wind', 'model': 'timestral_5M', 'origin': origin,
            'actual': [actual]*24, 'point': [10.]*24,
            'quantiles': [[0., 5., 10., 15., 20.] for _ in range(24)]}


def test_whole_day_and_delay_are_required_at_the_exact_boundary() -> None:
    current = day('2025-01-03T00:00:00Z')
    rows = [day('2025-01-01T00:00:00Z'), day('2025-01-02T00:00:00Z'), current,
            day('2025-01-04T00:00:00Z'), day('2024-01-01T00:00:00Z')]
    selected = available_history(rows, current, settings())
    assert [r['origin'] for r in selected] == ['2025-01-01T00:00:00Z']
    changed = deepcopy(rows)
    for row in changed[1:]:
        row['actual'] = [100000.]*24
    assert available_history(changed, current, settings()) == selected


def test_corrections_exact_and_bands_nested_without_changing_median() -> None:
    cfg = settings()
    history = [day('2025-01-01T00:00:00Z'), day('2025-01-02T00:00:00Z')]
    correction = fit_expansions(history, cfg)
    # Raw requirements: +15 for80 and +10 for90; the fixed nesting rule raises90 to15.
    assert correction == {'0.8': 15., '0.9': 15.}
    current = day('2025-01-05T00:00:00Z')
    saved = deepcopy(current)
    result = apply_expansions(current, correction, cfg)
    assert current == saved
    assert result['point'] == saved['point']
    np.testing.assert_array_equal(np.array(result['quantiles'])[:, 2], saved['point'])
    assert np.all(np.diff(np.array(result['quantiles']), axis=1) >= 0)
    assert result['quantiles'][0][0] < 0  # No silent clipping of physical bounds.


def test_zero_correction_when_old_forecasts_already_cover_observations() -> None:
    rows = [day('2025-01-01T00:00:00Z', 10.), day('2025-01-02T00:00:00Z', 10.)]
    assert fit_expansions(rows, settings()) == {'0.8': 0., '0.9': 0.}


def test_insufficient_missing_duplicate_and_mixed_target_data_rejected() -> None:
    cfg = settings()
    first, second = day('2025-01-01T00:00:00Z'), day('2025-01-02T00:00:00Z')
    with pytest.raises(ValueError, match='insufficiente'):
        fit_expansions([first], cfg)
    bad = deepcopy(second)
    bad['actual'][0] = float('nan')
    with pytest.raises(ValueError, match='incompleta'):
        fit_expansions([first, bad], cfg)
    with pytest.raises(ValueError, match='duplicate'):
        fit_expansions([first, first], cfg)
    bad = deepcopy(second)
    bad['target'] = 'solar'
    with pytest.raises(ValueError, match='mescolare'):
        fit_expansions([first, bad], cfg)


def test_current_actual_cannot_affect_transformed_quantiles() -> None:
    cfg = settings()
    history = [day('2025-01-01T00:00:00Z'), day('2025-01-02T00:00:00Z')]
    correction = fit_expansions(history, cfg)
    a, b = day('2025-01-05T00:00:00Z'), day('2025-01-05T00:00:00Z', -999999.)
    assert apply_expansions(a, correction, cfg)['quantiles'] == apply_expansions(b, correction, cfg)['quantiles']
    b['actual'] = None  # Transformation works before the future observation exists.
    b['quantiles'] = np.array(b['quantiles'])
    saved = b['quantiles'].copy()
    assert apply_expansions(a, correction, cfg)['quantiles'] == apply_expansions(b, correction, cfg)['quantiles']
    np.testing.assert_array_equal(b['quantiles'], saved)
    with pytest.raises(ValueError, match='annidate'):
        apply_expansions(a, {'0.8': 20., '0.9': 10.}, cfg)


def test_replay_uses_only_available_unmodified_raw_errors() -> None:
    cfg = settings()
    rows = [day(f'2025-01-{d:02}T00:00:00Z') for d in (1, 3, 5, 7, 9)]
    original = deepcopy(rows)
    first, trace = replay(rows, [rows[2], rows[3]], cfg)
    assert trace[0]['past_origins'] == [rows[0]['origin'], rows[1]['origin']]
    assert trace[0]['ranks'] == {'0.8': 40, '0.9': 45}
    changed = deepcopy(rows)
    for row in changed[2:]:
        row['actual'] = [1000000.]*24
    second, _ = replay(changed, [changed[2]], cfg)
    assert first[0]['quantiles'] == second[0]['quantiles']
    assert rows == original
    assert trace[1]['complete_past_days'] == 3


def comparison_fixture() -> tuple[list[dict], dict]:
    """Create a synthetic paired comparison with perfect corrected coverage but excessive width."""
    cfg = settings()
    cfg.update(targets=['wind'], proposed_gates={'minimum_evaluation_origins':2,
        'minimum_pinball_reduction_pct':5, 'maximum_coverage_absolute_deviation':.05,
        'maximum_width_ratio_to_probabilistic_baseline':1.1})
    past = [day('2025-01-01T00:00:00Z'), day('2025-01-03T00:00:00Z')]
    future = [day('2025-01-05T00:00:00Z'), day('2025-01-07T00:00:00Z')]
    transformed, _ = replay(past+future, future, cfg)
    baseline = []
    for row in future:
        b = deepcopy(row)
        b['model'] = 'hour_of_day_distribution'
        b['point'] = b['actual']
        b['quantiles'] = [[28.,29.,30.,31.,32.] for _ in range(24)]
        baseline.append(b)
    return future+transformed+baseline, cfg


def test_good_coverage_cannot_hide_excessive_width_or_bad_baseline_score() -> None:
    rows, cfg = comparison_fixture()
    summary = summarize(rows, cfg)
    decision = assess(summary, rows, cfg)['wind']
    assert decision['checks']['point_predictions_unchanged']
    assert decision['checks']['point_metrics_unchanged']
    assert not decision['checks']['width_0.8']
    assert not decision['checks']['pinball_vs_baseline']
    assert not decision['all_pass']
    assert not decision['operational_promotion']


def test_different_origin_masks_are_rejected_instead_of_compared() -> None:
    rows, cfg = comparison_fixture()
    with pytest.raises(ValueError, match='stesse origini'):
        summarize(rows[:-1], cfg)


def test_unapproved_replay_is_stopped_before_any_source_access() -> None:
    with pytest.raises(RuntimeError, match='replay'):
        run_replay({'hourly_calibration': {'execution_authorized':False}}, None)


def test_report_contains_all_metrics_gates_and_exclusions() -> None:
    rows, cfg = comparison_fixture()
    summary = summarize(rows, cfg)
    result = {'settings':cfg, 'summary':summary, 'decisions':assess(summary, rows, cfg),
              'trace':[], 'original_exclusions':{'wind':[]}}
    html = render_report(result)
    assert 'Prima / dopo sugli stessi casi' in html
    assert 'FALLITO' in html and 'Bias MW' in html and 'Pinball MW' in html
    assert 'Copertura90 %' in html and 'Per ora prevista' in html
