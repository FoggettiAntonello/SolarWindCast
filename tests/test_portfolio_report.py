"""Synthetic checks preventing selective reporting and machine-specific metadata leakage."""

from solarwindcast.portfolio_report import normalize_models, render, summarize_source


def test_normalization_preserves_losing_baseline_and_missing_quantile_metrics() -> None:
    models={'persistence':{'cases':24,'origins':1,'mae_mw':30.,'rmse_mw':40.,'bias_mw':-2.},
            'timestral_5M':{'cases':24,'origins':1,'mae_mw':50.,'rmse_mw':60.,'bias_mw':5.}}
    normalized=normalize_models(models,'hourly')
    assert set(normalized)==set(models)
    assert normalized['timestral_5M']['mae']>normalized['persistence']['mae']
    assert normalized['persistence']['pinball'] is None


def test_source_extraction_excludes_provenance_paths_and_keeps_failures() -> None:
    source={'id':'hourly_extension','title':'Synthetic','kind':'hourly','period':'fixture','unit':'MW'}
    result={'summary':{'wind':{'timestral_5M':{'cases':24,'origins':1,'mae_mw':50.,'rmse_mw':60.,'bias_mw':5.}}},
            'skipped':[], 'model_provenance':{'local_path':'PRIVATE_PATH'}}
    study=summarize_source(result,source)
    assert 'PRIVATE_PATH' not in str(study)
    bundle={'studies':[study], 'highlights':[], 'provenance':[], 'generated_date':'fixture'}
    html=render(bundle)
    assert 'Valutazione completa' in html and 'Nessuna promozione complessiva' in html
    assert '50,00' in html and 'PRIVATE_PATH' not in html
    assert 'setup in ambiente pulito' in html
