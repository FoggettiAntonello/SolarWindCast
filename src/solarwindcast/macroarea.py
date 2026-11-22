"""Strict observed-power aggregation for explicitly declared disjoint geographical areas."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace

import pandas as pd

from solarwindcast.dataset import TimeSeriesDataset


@dataclass(frozen=True)
class AreaRegime:
    """Explicit half-open UTC validity interval and separately documented area membership."""

    start_utc: str
    end_exclusive_utc: str
    required_eics: tuple[str, ...]
    provenance: str


def aggregate_observed_areas(datasets: Mapping[str, TimeSeriesDataset],
                             required_eics: tuple[str, ...], name: str) -> TimeSeriesDataset:
    """Sum MW only on identical grids; caller must document disjoint areas and date validity.

    This function does not reconstruct historical geography, assume structural zeros,
    merge covariates or aggregate forecast quantiles. Every required area's value
    must be observed; one missing input leaves the aggregate missing.
    """
    if (not name.strip() or not required_eics or len(set(required_eics)) != len(required_eics)
            or set(datasets) != set(required_eics) or any(not eic.strip() for eic in required_eics)):
        raise ValueError("Nome e domini espliciti, univoci e presenti obbligatori.")
    reference = datasets[required_eics[0]]
    values, provenance = [], {}
    for eic in required_eics:
        dataset = datasets[eic]
        dataset.validate()
        if (list(dataset.frame.columns) != ["target"] or dataset.spec.frequency != reference.spec.frequency
                or dataset.spec.target != reference.spec.target
                or not dataset.frame.index.equals(reference.frame.index)):
            raise ValueError("Solo osservazioni dello stesso target, frequenza e griglia UTC; nessun riallineamento.")
        values.append(dataset.frame.target)
        provenance[eic] = dataset.spec.provenance
    series = pd.concat(values, axis=1).sum(axis=1, min_count=len(required_eics))
    spec = replace(reference.spec, provenance="custom observed macroarea " + name + "; " + json.dumps(provenance, sort_keys=True))
    result = TimeSeriesDataset(series.to_frame("target"), spec)
    result.validate()
    return result


def aggregate_regimes(datasets: Mapping[str, TimeSeriesDataset], regimes: tuple[AreaRegime, ...],
                       name: str) -> TimeSeriesDataset:
    """Apply explicit contiguous geographical regimes on one grid, without overlap or hidden fills.

    Every input uses the same requested UTC grid, with NaN outside its observed
    span. Only areas declared for the active regime are summed. This validates
    arithmetic and time alignment, not historical completeness or approval.
    """
    if not regimes or not datasets:
        raise ValueError("Servono regimi e osservazioni espliciti.")
    reference = next(iter(datasets.values()))
    reference.validate()
    required_union = {eic for regime in regimes for eic in regime.required_eics}
    if set(datasets) != required_union:
        raise ValueError("Domini mancanti o aggiuntivi rispetto ai regimi dichiarati.")
    for dataset in datasets.values():
        dataset.validate()
        if (not dataset.frame.index.equals(reference.frame.index) or dataset.spec.target != reference.spec.target
                or dataset.spec.frequency != reference.spec.frequency or list(dataset.frame.columns) != ["target"]):
            raise ValueError("Target, frequenze e griglie devono coincidere: nessun reindex implicito.")
    pieces, descriptions, previous = [], [], None
    for regime in regimes:
        first, stop = pd.Timestamp(regime.start_utc), pd.Timestamp(regime.end_exclusive_utc)
        if (str(first.tzinfo) != "UTC" or str(stop.tzinfo) != "UTC" or stop <= first
                or not regime.provenance.strip() or (previous is not None and first != previous)):
            raise ValueError("Regimi UTC contigui e documentati obbligatori, senza sovrapposizioni.")
        previous = stop
        index = reference.frame.index
        step = pd.tseries.frequencies.to_offset(reference.spec.frequency)
        if first not in index or (stop not in index and stop != index[-1] + step):
            raise ValueError("Confine fuori dalla griglia richiesta.")
        selection = (index >= first) & (index < stop)
        selected = {eic: TimeSeriesDataset(datasets[eic].frame.loc[selection].copy(), datasets[eic].spec)
            for eic in regime.required_eics}
        combined = aggregate_observed_areas(selected, regime.required_eics, name)
        pieces.append(combined.frame)
        descriptions.append({"start_utc": regime.start_utc, "end_exclusive_utc": regime.end_exclusive_utc,
            "areas": regime.required_eics, "evidence": regime.provenance, "sources": combined.spec.provenance})
    frame = pd.concat(pieces)
    if not frame.index.equals(reference.frame.index):
        raise ValueError("I regimi non coprono esattamente la griglia richiesta.")
    result = TimeSeriesDataset(frame, replace(reference.spec, provenance="explicit macroarea regimes " + name + "; " + json.dumps(descriptions)))
    result.validate()
    return result
