"""Assumption variants: robust z-scores under each baseline rule, anomaly flags and persistence.

D0 is the screening's rule (``screening.stage2.robust_z`` for a reach without regime changes);
every other variant changes one thing. Episodes merge anomalous scenes that are close in time.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np

from climate_pipeline.screening.stage2 import MAD_TO_SIGMA, SIGNALS
from climate_pipeline.validation.config import Variant

INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class Scores:
    """Leave-one-out z-scores of one signal, with the baseline group of each value."""

    z: list[float]
    group: list[str]  # "season", "all", "month", "window", "insufficient", or "" when missing
    size: list[int]  # values in the baseline group (0 when insufficient or missing)


def _options(
    variant: Variant,
    i: int,
    others: np.ndarray,
    season: np.ndarray,
    months: np.ndarray,
    ordinals: np.ndarray,
) -> list[tuple[str, np.ndarray, int]]:
    same_season = others & (season == season[i])
    if variant.baseline == "season-then-all":
        return [("season", same_season, variant.season_min), ("all", others, variant.all_min)]
    if variant.baseline == "season":
        return [("season", same_season, variant.season_min)]
    if variant.baseline == "month-window":
        diff = (months - months[i]) % 12
        near = np.minimum(diff, 12 - diff) <= variant.month_halfwidth
        return [("month", others & near, variant.window_min)]
    near = np.abs(ordinals - ordinals[i]) <= variant.day_halfwidth
    return [("window", others & near, variant.window_min)]


def zscores(
    values: Sequence[float],
    days: Sequence[date],
    rainy: set[int],
    variant: Variant,
    mad_floor: float,
) -> Scores:
    """Leave-one-out robust z-scores of one signal under a variant's baseline rule.

    The baseline of a value is the first of the variant's groups with enough other finite
    values; sigma = max(1.4826 * MAD, ``mad_floor``). Without such a group the value is
    "insufficient" (NaN), never "not anomalous".

    Args:
        values: One value per scene (NaN allowed).
        days: The scenes' days.
        rainy: Rainy-season months.
        variant: The variant (its baseline kind and minimums).
        mad_floor: Lower bound of sigma.

    Returns:
        z-scores, baseline groups and group sizes.
    """
    x = np.array(values, dtype=np.float64)
    finite = np.isfinite(x)
    season = np.array([d.month in rainy for d in days], dtype=bool)
    months = np.array([d.month for d in days], dtype=np.int64)
    ordinals = np.array([d.toordinal() for d in days], dtype=np.int64)
    zs: list[float] = []
    groups: list[str] = []
    sizes: list[int] = []
    for i, value in enumerate(x):
        if not finite[i]:
            zs.append(math.nan)
            groups.append("")
            sizes.append(0)
            continue
        others = finite.copy()
        others[i] = False
        for label, sel, minimum in _options(variant, i, others, season, months, ordinals):
            n = int(sel.sum())
            if n >= minimum:
                ref = x[sel]
                median = float(np.median(ref))
                mad = float(np.median(np.abs(ref - median)))
                zs.append((float(value) - median) / max(MAD_TO_SIGMA * mad, mad_floor))
                groups.append(label)
                sizes.append(n)
                break
        else:
            zs.append(math.nan)
            groups.append(INSUFFICIENT)
            sizes.append(0)
    return Scores(zs, groups, sizes)


@dataclass(frozen=True)
class SceneRecord:
    """One observable scene of a reach, measured at every pixel glint limit the variants use."""

    key: str
    day: date
    values: dict[float, dict[str, float]]  # glint limit -> signal -> NDTI
    usable: dict[float, bool]  # glint limit -> passed every check
    glint_share: float  # largest sub-reach glint share at the screening's limit (NaN if unknown)


@dataclass(frozen=True)
class VariantScene:
    """One scene under one variant."""

    status: str  # "scored", "insufficient", "excluded" (failed a check) or "removed" (G2)
    z: dict[str, float]
    group: dict[str, str]
    size: dict[str, int]
    signals: tuple[str, ...]  # signals at or above the variant's threshold

    @property
    def anomalous(self) -> bool:
        """At least one signal reached the threshold."""
        return bool(self.signals)

    @property
    def scored(self) -> bool:
        """At least one signal has a z-score."""
        return self.status == "scored"


def evaluate(
    records: Sequence[SceneRecord], variant: Variant, rainy: set[int], mad_floor: float
) -> list[VariantScene]:
    """Score every scene of a reach under one variant.

    Args:
        records: The reach's observable scenes, in time order.
        variant: The variant.
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.

    Returns:
        One entry per record, in the same order.
    """
    limit = variant.swir16_max
    removed = [
        variant.max_glint_share is not None
        and math.isfinite(r.glint_share)
        and r.glint_share > variant.max_glint_share
        for r in records
    ]
    included = [i for i, r in enumerate(records) if r.usable[limit] and not removed[i]]
    days = [records[i].day for i in included]
    per_signal = {
        signal: zscores(
            [records[i].values[limit][signal] for i in included], days, rainy, variant, mad_floor
        )
        for signal in SIGNALS
    }
    position = {i: k for k, i in enumerate(included)}
    out = []
    for i, record in enumerate(records):
        if i not in position:
            status = "removed" if record.usable[limit] and removed[i] else "excluded"
            out.append(VariantScene(status, {}, {}, {}, ()))
            continue
        k = position[i]
        z = {s: per_signal[s].z[k] for s in SIGNALS}
        signals = tuple(s for s in SIGNALS if abs(z[s]) >= variant.anomaly_z)
        status = "scored" if any(math.isfinite(v) for v in z.values()) else INSUFFICIENT
        out.append(
            VariantScene(
                status,
                z,
                {s: per_signal[s].group[k] for s in SIGNALS},
                {s: per_signal[s].size[k] for s in SIGNALS},
                signals,
            )
        )
    return out


def persistence(flags: Sequence[Sequence[bool]]) -> list[int]:
    """In how many variants each scene is anomalous.

    Args:
        flags: Per variant, one anomalous flag per scene (same scene order in every variant).

    Returns:
        One count per scene.
    """
    if not flags:
        return []
    return [sum(1 for variant in flags if variant[i]) for i in range(len(flags[0]))]


def episodes(days: Sequence[date], gap_days: int) -> list[list[date]]:
    """Merge days into episodes: a day at most ``gap_days`` after the previous one joins it.

    Args:
        days: Days of the anomalous scenes (any order; repeats collapse).
        gap_days: Largest gap inside an episode.

    Returns:
        Episodes in time order, each a sorted list of days.
    """
    out: list[list[date]] = []
    for day in sorted(set(days)):
        if out and (day - out[-1][-1]).days <= gap_days:
            out[-1].append(day)
        else:
            out.append([day])
    return out


def share(scenes: Sequence[VariantScene]) -> tuple[int, int]:
    """Anomalous and scored scenes (a scored scene has at least one z-score).

    Args:
        scenes: A reach's scenes under one variant.

    Returns:
        ``(anomalous, scored)``.
    """
    scored = [s for s in scenes if s.scored]
    return sum(1 for s in scored if s.anomalous), len(scored)


@dataclass(frozen=True)
class Persistence:
    """Every variant's verdict on a reach's scenes, and what criterion (a) keeps."""

    evaluations: dict[str, list[VariantScene]]  # variant id -> one entry per record
    counts: list[int]  # variants in which each record is anomalous
    distinct_counts: list[int]  # the same over the variants marked distinct
    candidates: list[date]  # persistent, not rain-coincident scene days
    episodes: list[list[date]]


def criterion_a(
    records: Sequence[SceneRecord],
    variants: Sequence[Variant],
    rainy: set[int],
    mad_floor: float,
    coincident: Sequence[bool],
    persistence_min: int,
    gap_days: int,
) -> Persistence:
    """Score every variant and keep the persistent scenes that are not rain-coincident.

    Args:
        records: The reach's observable scenes, in time order.
        variants: The ten variants.
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.
        coincident: Per record, rain-coincident under the union rule (unknown counts as True).
        persistence_min: Variants a scene must be anomalous in.
        gap_days: Largest gap inside an episode.

    Returns:
        The evaluations, persistence counts, candidate days and their episodes.
    """
    evaluations = {v.id: evaluate(records, v, rainy, mad_floor) for v in variants}
    counts = persistence([[s.anomalous for s in evaluations[v.id]] for v in variants])
    distinct = persistence(
        [[s.anomalous for s in evaluations[v.id]] for v in variants if v.distinct]
    )
    candidates = [
        r.day
        for r, n, wet in zip(records, counts, coincident, strict=True)
        if n >= persistence_min and not wet
    ]
    return Persistence(
        evaluations,
        counts,
        distinct or [0] * len(records),
        candidates,
        episodes(candidates, gap_days),
    )
