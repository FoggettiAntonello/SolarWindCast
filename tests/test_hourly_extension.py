"""Synthetic date separation and preservation of pilot settings."""

from copy import deepcopy

import pytest

from solarwindcast.hourly_extension import extension_config
from solarwindcast.hourly_pilot import planned_origins


def test_extension_keeps_scientific_settings_and_separates_dates() -> None:
    cfg={'first_month':'2024-11','last_month':'2026-10','day_of_month':15,
         'context_hours':672,'assumed_delay_hours':24,'model_size':'5M'}
    original=deepcopy(cfg)
    project={'hourly_extension':{'authorized':True,'calibration_authorized':False,
                               'output':'new','days_of_month':[1,8,22],'maximum_inferences':144}}
    result=extension_config(project,{'settings':cfg})['hourly_pilot']
    assert len(planned_origins(result))==72
    assert not set(planned_origins(result)) & set(planned_origins(cfg))
    assert cfg==original
    for key in ('context_hours','assumed_delay_hours','model_size'):
        assert result[key]==cfg[key]
    project['hourly_extension']['days_of_month']=[15]
    with pytest.raises(ValueError,match='sovrapposte'):
        extension_config(project,{'settings':cfg})
    project['hourly_extension']['days_of_month']=[1,1]
    with pytest.raises(ValueError,match='univoci'):
        extension_config(project,{'settings':cfg})
