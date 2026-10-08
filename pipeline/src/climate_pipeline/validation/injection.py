"""Injection-recovery: what the unchanged detector finds when a known step is added to a copy.

A step of a given size is added to the downstream sub-reach's NDTI of one real scene at a time
(the difference signal moves with it); the D0 detector then scores that copy. Every eligible
scene receives every step once, so there is no sampling. A step of zero (the uninjected copy) is
always included: its detection share is the false-positive rate of the same rule. The real series
is never changed: each injection works on its own copy. The result is a property of the detector
on this series, not a measurement of any real event.

The detector's baseline leaves the scored scene out, so a step moves only that scene's z, and
linearly: z(step) = z(0) + step * (z(1) - z(0)). Each scene is therefore scored by the unchanged
detector on two copies (steps 0 and 1) and every grid step follows exactly; ``direct=True``
scores every step on its own copy instead (the tests check that both agree).
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date

import numpy as np

from climate_pipeline.screening.stage2 import MAD_TO_SIGMA
from climate_pipeline.validation.config import DemoEventConfig, InjectionConfig, Variant
from climate_pipeline.validation.variants import SceneRecord, VariantScene, evaluate


def robust_sigma(values: Sequence[float], floor: float) -> float:
    """The robust sigma the detector uses: max(1.4826 * MAD, floor) over finite values.

    Args:
        values: Values.
        floor: Lower bound.

    Returns:
        Sigma (the floor when there are no finite values).
    """
    x = np.array([v for v in values if math.isfinite(v)], dtype=np.float64)
    if x.size == 0:
        return floor
    return max(MAD_TO_SIGMA * float(np.median(np.abs(x - np.median(x)))), floor)


def eligible(records: Sequence[SceneRecord], d0: Sequence[VariantScene], limit: float) -> list[int]:
    """Scenes an event can be injected into: usable, scored under D0, both sub-reaches measured.

    Args:
        records: The reach's scenes.
        d0: Their D0 evaluation.
        limit: The screening's glint limit.

    Returns:
        Record indices.
    """
    return [
        k
        for k, (r, s) in enumerate(zip(records, d0, strict=True))
        if r.usable[limit]
        and s.scored
        and math.isfinite(r.values[limit]["upstream"])
        and math.isfinite(r.values[limit]["downstream"])
    ]


def inject(record: SceneRecord, limit: float, step: float) -> SceneRecord:
    """A copy of a scene with a step added to its downstream NDTI (the difference follows).

    Args:
        record: The real scene.
        limit: The glint limit whose values are changed.
        step: NDTI added downstream.

    Returns:
        The modified copy.
    """
    values = dict(record.values[limit])
    values["downstream"] = values["downstream"] + step
    values["delta"] = values["downstream"] - values["upstream"]
    return replace(record, values={**record.values, limit: values})


def glint_class(share: float, limits: tuple[float, float]) -> str:
    """``low``, ``mid`` or ``high`` glint (``unknown`` without a share).

    Args:
        share: Largest sub-reach glint share.
        limits: Upper limits of low and mid.

    Returns:
        The class.
    """
    if not math.isfinite(share):
        return "unknown"
    return "low" if share <= limits[0] else "mid" if share <= limits[1] else "high"


@dataclass(frozen=True)
class Injection:
    """One injected step and what the detector made of it."""

    key: str
    day: date
    season: str
    glint: str
    scale: str  # "ndti" or "sigma"
    size: float  # the grid value (NDTI, or multiples of sigma)
    step: float  # NDTI added
    z_downstream: float
    z_delta: float
    detected_downstream: bool
    detected_delta: bool

    @property
    def detected(self) -> bool:
        """Any signal reached the threshold (the D0 anomaly rule)."""
        return self.detected_downstream or self.detected_delta


def _scored(
    records: Sequence[SceneRecord], k: int, step: float, d0: Variant, rainy: set[int], floor: float
) -> tuple[float, float]:
    copy = list(records)
    copy[k] = inject(records[k], d0.swir16_max, step)
    scene = evaluate(copy, d0, rainy, floor)[k]
    return scene.z.get("downstream", math.nan), scene.z.get("delta", math.nan)


def run_injections(
    records: Sequence[SceneRecord],
    d0: Variant,
    rainy: set[int],
    mad_floor: float,
    cfg: InjectionConfig,
    direct: bool = False,
) -> tuple[list[Injection], float]:
    """Inject every step into every eligible scene, one at a time, and run D0.

    Args:
        records: The real scenes (not modified).
        d0: The screening variant (the unchanged detector).
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.
        cfg: Steps and glint classes.
        direct: Score every step on its own copy (slow; the default uses the exact linearity).

    Returns:
        The injections and the downstream signal's robust sigma used for the sigma grid.
    """
    limit = d0.swir16_max
    baseline = evaluate(records, d0, rainy, mad_floor)
    targets = eligible(records, baseline, limit)
    sigma = robust_sigma([records[k].values[limit]["downstream"] for k in targets], mad_floor)
    steps = [("ndti", 0.0, 0.0)] + [("ndti", s, s) for s in cfg.raw_ndti]
    steps += [("sigma", m, m * sigma) for m in cfg.sigma_multiples]
    out = []
    for k in targets:
        record = records[k]
        season = "rainy" if record.day.month in rainy else "dry"
        glint = glint_class(record.glint_share, cfg.glint_classes)
        base = baseline[k].z.get("downstream", math.nan), baseline[k].z.get("delta", math.nan)
        unit = _scored(records, k, 1.0, d0, rainy, mad_floor)
        for scale, size, step in steps:
            if direct:
                z_down, z_delta = _scored(records, k, step, d0, rainy, mad_floor)
            else:
                z_down = base[0] + step * (unit[0] - base[0])
                z_delta = base[1] + step * (unit[1] - base[1])
            out.append(
                Injection(
                    record.key, record.day, season, glint, scale, size, step, z_down, z_delta,
                    abs(z_down) >= d0.anomaly_z, abs(z_delta) >= d0.anomaly_z,
                )
            )  # fmt: skip
    return out, sigma


def detection_rows(injections: Sequence[Injection]) -> list[dict[str, object]]:
    """Detection probability per step, overall, by season and by glint class.

    Args:
        injections: The injections.

    Returns:
        One row per scale, step and stratum.
    """
    groups: dict[tuple[str, float, str, str], list[Injection]] = {}
    for inj in injections:
        for stratum, value in (("all", "all"), ("season", inj.season), ("glint", inj.glint)):
            groups.setdefault((inj.scale, inj.size, stratum, value), []).append(inj)
    rows = []
    for (scale, size, stratum, value), items in sorted(groups.items()):
        n = len(items)
        rows.append(
            {
                "scale": scale,
                "size": size,
                "step_ndti": round(items[0].step, 5),
                "stratum": stratum,
                "value": value,
                "injections": n,
                "detected": round(sum(i.detected for i in items) / n, 4),
                "detected_downstream": round(sum(i.detected_downstream for i in items) / n, 4),
                "detected_delta": round(sum(i.detected_delta for i in items) / n, 4),
            }
        )
    return rows


def threshold(
    injections: Sequence[Injection], scale: str, rate: float
) -> tuple[float | None, float | None]:
    """The smallest step detected with at least ``rate`` probability (all scenes).

    Args:
        injections: The injections.
        scale: ``ndti`` or ``sigma``.
        rate: E.g. 0.8.

    Returns:
        The smallest grid value reaching the rate, and a linear interpolation between grid values
        (None when no grid value reaches it). Both are in the grid's own unit.
    """
    by_size: dict[float, list[Injection]] = {}
    for inj in injections:
        if inj.scale == scale:
            by_size.setdefault(inj.size, []).append(inj)
    curve = sorted(
        (size, sum(i.detected for i in items) / len(items)) for size, items in by_size.items()
    )
    for k, (size, value) in enumerate(curve):
        if value >= rate:
            if k == 0:
                return size, size
            s0, v0 = curve[k - 1]
            interpolated = s0 + (rate - v0) * (size - s0) / (value - v0) if value > v0 else size
            return size, interpolated
    return None, None


@dataclass(frozen=True)
class DemoEvent:
    """The demo's synthetic event, fixed by rule before its outcome is looked at."""

    key: str
    day: date
    step: float
    real_downstream: float
    real_z: float
    overlay_z: float
    detected: bool
    eligible_scenes: int
    label: str


def choose_demo(
    records: Sequence[SceneRecord],
    d0_variant: Variant,
    rainy: set[int],
    mad_floor: float,
    clear_keys: set[str],
    avoid: Sequence[tuple[date, date]],
    threshold_ndti: float | None,
    cfg: DemoEventConfig,
) -> DemoEvent | None:
    """Pick the demo event by the pre-registered rule, then score it once.

    Magnitude: ``magnitude_factor`` times the interpolated detection threshold, rounded up.
    Date: a seeded random draw among scenes in the window that are clear, usable with both
    sub-reaches, not anomalous under D0, at most ``max_glint_share`` glint and at least
    ``min_days_from_events`` from every dated event.

    Args:
        records: The real scenes.
        d0_variant: The detector.
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.
        clear_keys: Acquisitions that are clear under the screening's clear rule.
        avoid: Date ranges of dated events (catalogued or post-hoc).
        threshold_ndti: Interpolated NDTI step detected with the target probability.
        cfg: The rule.

    Returns:
        The event, or None when no threshold or no eligible scene exists.
    """
    if threshold_ndti is None:
        return None
    limit = d0_variant.swir16_max
    d0 = evaluate(records, d0_variant, rainy, mad_floor)
    step = (
        math.ceil(cfg.magnitude_factor * threshold_ndti / cfg.round_up_to - 1e-9) * cfg.round_up_to
    )
    step = round(step, 6)

    def far(day: date) -> bool:
        return all(
            (first - day).days >= cfg.min_days_from_events
            or (day - last).days >= cfg.min_days_from_events
            for first, last in avoid
        )

    candidates = [
        k
        for k in eligible(records, d0, limit)
        if cfg.window.contains(records[k].day)
        and records[k].key in clear_keys
        and not d0[k].anomalous
        and math.isfinite(records[k].glint_share)
        and records[k].glint_share <= cfg.max_glint_share
        and far(records[k].day)
    ]
    if not candidates:
        return None
    k = random.Random(cfg.seed).choice(candidates)
    copy = list(records)
    copy[k] = inject(records[k], limit, step)
    scene = evaluate(copy, d0_variant, rainy, mad_floor)[k]
    z = max((v for v in scene.z.values() if math.isfinite(v)), key=abs, default=math.nan)
    real = max((v for v in d0[k].z.values() if math.isfinite(v)), key=abs, default=math.nan)
    return DemoEvent(
        records[k].key, records[k].day, step, records[k].values[limit]["downstream"], real, z,
        scene.anomalous, len(candidates), cfg.label,
    )  # fmt: skip
