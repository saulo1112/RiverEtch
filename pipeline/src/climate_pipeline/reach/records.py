"""Observation records v2 of a reach's scenes: z-scores, estimates and the sealed record.

A record never changes once sealed, so a new scene's z-scores compare it with the frozen baseline
only (the reach's scenes up to ``baseline_end``), under the D0 rule of the screening: season group
of at least 8 values, else all of at least 12, sigma = max(1.4826 MAD, floor). The verdict follows
from the NDTI z-scores alone; NIR/red gets the same rule as context. An estimate shows a value only
where its model card's level for the predicted range is validated or estimated, and nothing when
any abstention rule applies.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration.config import WindowSettings
from climate_pipeline.calibration.models import window_abstain_reason
from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.contract.observation import (
    ClimateContext,
    Provenance,
    RainFlags,
    StacItemRef,
    ZScores,
    verdict_from_z,
)
from climate_pipeline.quality import cards
from climate_pipeline.quality.config import Target
from climate_pipeline.screening.config import ScreeningConfig
from climate_pipeline.screening.stage2 import SIGNALS, robust_z

SUBREACHES = ("upstream", "downstream")
COVERAGE = 0.9
NOT_RUN_RULE = "climate context not run"
MIN_HISTORY = 12  # the D0 rule's minimum baseline


@dataclass(frozen=True)
class Item:
    """One STAC item behind a scene."""

    id: str
    url: str
    processing_baseline: str
    boa_offset_applied: bool | None


@dataclass(frozen=True)
class Measure:
    """What one scene of the reach measured."""

    key: str
    day: date
    items: tuple[Item, ...]
    exclusion: str  # why the scene is unusable ("" when it is usable)
    ndti: Mapping[str, float]  # per sub-reach
    nir_red: Mapping[str, float]  # per sub-reach
    window: Mapping[str, float] = field(default_factory=dict)  # the estimate station's features
    stats: Mapping[str, float] = field(default_factory=dict)  # its window statistics
    window_problem: str = ""  # why the window could not be measured


@dataclass(frozen=True)
class Baseline:
    """The frozen history of the reach: its days, signals and the station's estimates."""

    days: tuple[date, ...]
    ndti: Mapping[str, Sequence[float]]  # signal -> one value per day
    nir_red: Mapping[str, Sequence[float]]
    estimates: Mapping[str, Sequence[float]] = field(default_factory=dict)  # target -> values


def signals(sub: Mapping[str, float]) -> dict[str, float]:
    """The three signals of an index: each sub-reach and downstream minus upstream.

    Args:
        sub: Index per sub-reach.

    Returns:
        Signal -> value (NaN where missing).
    """
    up, down = sub.get("upstream", math.nan), sub.get("downstream", math.nan)
    return {"upstream": up, "downstream": down, "delta": down - up}


def _num(value: float, digits: int) -> float | None:
    return round(value, digits) if math.isfinite(value) else None


def z_scores(history: Mapping[str, Sequence[float]], days: Sequence[date],
             value: Mapping[str, float], day: date, rainy: set[int],
             screening: ScreeningConfig) -> ZScores:  # fmt: skip
    """D0 z-scores of one scene against the frozen history.

    Args:
        history: Signal -> historical values.
        days: The historical days.
        value: Signal -> the scene's value.
        day: The scene's day.
        rainy: Rainy-season months.
        screening: Screening settings (D0's minimums and floor).

    Returns:
        The z-scores (None where the value or the baseline is missing).
    """
    out = {}
    for s in SIGNALS:
        zs, _ = robust_z([*history[s], value[s]], [*days, day], rainy, [], screening)
        out[s] = _num(zs[-1], 2)
    return ZScores(upstream=out["upstream"], downstream=out["downstream"], delta=out["delta"])


def index(sub: Mapping[str, float], z: ZScores, digits: int = 4) -> v2.Index:
    """One relative index of a record.

    Args:
        sub: Index per sub-reach.
        z: Its z-scores.
        digits: Decimals kept.

    Returns:
        The index block.
    """
    s = signals(sub)
    measured = [v for v in (s["upstream"], s["downstream"]) if math.isfinite(v)]
    reach = sum(measured) / len(measured) if measured else math.nan
    return v2.Index(upstream=_num(s["upstream"], digits), downstream=_num(s["downstream"], digits),
                    reach=_num(reach, digits), delta=_num(s["delta"], digits),
                    z_score=z)  # fmt: skip


def relative_class(value: float, history: Sequence[float]) -> v2.RelativeClass | None:
    """Low, medium or high: the tercile of a value in the station's own history.

    Args:
        value: The scene's estimate.
        history: The station's historical estimates.

    Returns:
        The class, or None with fewer than 12 historical values.
    """
    finite = np.array([h for h in history if math.isfinite(h)])
    if len(finite) < MIN_HISTORY or not math.isfinite(value):
        return None
    low, high = np.quantile(finite, [1 / 3, 2 / 3])
    return "low" if value < low else "medium" if value < high else "high"


def estimate(
    card: Mapping[str, Any] | None, card_sha256: str, target: Target, measure: Measure,
    history: Sequence[float], window: WindowSettings, lab_dir: Path,
) -> v2.Estimate:  # fmt: skip
    """One target's estimate for a scene, at its card's level, or why there is none.

    Args:
        card: The product's model card for the target (None: no model).
        card_sha256: The card's hash (:func:`cards.card_hash`).
        target: The target.
        measure: The scene.
        history: The station's historical estimates (for a relative class).
        window: D15's window guards.
        lab_dir: Where an A4 card's forest lives.

    Returns:
        The estimate.
    """
    unit = str(card.get("unit", target.unit)) if card is not None else target.unit
    none = v2.Estimate(target=target.id, unit=unit, level="none")
    if card is None:
        return none
    reason = (measure.exclusion or measure.window_problem
              or window_abstain_reason(measure.stats, window)
              or cards.outside_range(card, measure.window))  # fmt: skip
    value = math.nan if reason else cards.estimate(card, measure.window, lab_dir)
    if not reason and not (math.isfinite(value) and value > 0):
        reason = "no estimate from the window's features"
    if reason:
        level, mdsa = cards.level_of(card, target, math.nan)
        overall = next((r for r in card.get("levels", []) if r["predicted_range"] == "all"), None)
        level = str(overall["level"]) if overall else level
    else:
        level, mdsa = cards.level_of(card, target, value)
    if level == "none":
        return none
    model: dict[str, Any] = {
        "target": target.id, "unit": unit, "level": level, "modelId": card["modelId"],
        "modelVersion": card["version"], "modelCardSha256": card_sha256,
        "rangeMdsa": _num(mdsa, 1), "basis": card.get("basis", "preregistered_test"),
        "atmosphericCorrection": v2.AtmosphericCorrection(
            processor="sen2cor", collection="sentinel-2-l2a",
            processing_baseline=[i.processing_baseline for i in measure.items]),
    }  # fmt: skip
    if not reason and level in ("validated", "estimated"):
        low, high = cards.interval(card, value, COVERAGE)
        if math.isfinite(high) and low > 0:
            return v2.Estimate.model_validate({
                **model, "value": round(value, 2), "validRange": tuple(card["targetRange"]),
                "interval": v2.Interval(low=round(low, 2), high=round(high, 2), coverage=COVERAGE,
                                        method="mondrian_split_conformal_log"),
            })  # fmt: skip
        reason = "no finite 90 % interval"
    if not reason and level == "indicative":
        cls = relative_class(value, history)
        if cls is not None:
            return v2.Estimate.model_validate({**model, "relativeClass": cls})
        reason = "the station's history is too short for a relative class"
    return v2.Estimate.model_validate({**model, "abstainReason": reason})


def record(reach_id: str, measure: Measure, baseline: Baseline, estimates: Sequence[v2.Estimate],
           rain: RainFlags, rainy: set[int], screening: ScreeningConfig, threshold: float,
           code_commit: str, params_sha256: str) -> v2.ObservationRecordV2:  # fmt: skip
    """The sealed record of one usable scene.

    Args:
        reach_id: The reach's site id.
        measure: The scene.
        baseline: The frozen history.
        estimates: One per target.
        rain: The scene's rain flags.
        rainy: Rainy-season months.
        screening: Screening settings (D0).
        threshold: D0 threshold.
        code_commit: The code's commit.
        params_sha256: SHA-256 of the settings that shaped the record.

    Returns:
        The sealed record.
    """
    ndti_z = z_scores(baseline.ndti, baseline.days, signals(measure.ndti), measure.day, rainy,
                      screening)  # fmt: skip
    nir_z = z_scores(baseline.nir_red, baseline.days, signals(measure.nir_red), measure.day,
                     rainy, screening)  # fmt: skip
    day = measure.day.isoformat()
    ids = [i.id for i in measure.items]
    rec = v2.ObservationRecordV2(
        reach_id=reach_id, date=day, scene_id=f"{reach_id}:{day}", stac_item_ids=ids,
        indices=v2.Indices(ndti=index(measure.ndti, ndti_z),
                           nir_red=index(measure.nir_red, nir_z)),
        verdict=verdict_from_z(ndti_z, threshold), rain=rain, estimates=list(estimates),
        climate_context=ClimateContext(status="not_run", label="not_evaluated",
                                       rule=NOT_RUN_RULE),
        provenance=Provenance(
            collection="sentinel-2-l2a",
            stac_items=[StacItemRef(id=i.id, url=i.url) for i in measure.items],
            code_commit=code_commit, processing_params_sha256=params_sha256,
            boa_offset_applied=[i.boa_offset_applied for i in measure.items],
            processing_baseline=[i.processing_baseline for i in measure.items]),
    )  # fmt: skip
    return v2.seal(rec)
