"""Within-season placebo: shuffle the target's scenes between dates of the same season.

A scene's measurements (NDTI at every glint limit, its checks and its glint share) move to
another date of the same season; the date's rain flag stays. S1, the number of D0 anomalies that
are not rain-coincident, can only change through that pairing with rain: within a season each
value keeps its D0 baseline group, so the set of D0-anomalous values cannot change. S2, the number
of criterion-(a) episodes, recomputes every variant, the date-dependent ones included.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass, replace

from climate_pipeline.validation.config import Criteria, Variant
from climate_pipeline.validation.variants import SceneRecord, criterion_a, evaluate


@dataclass(frozen=True)
class PlaceboResult:
    """Observed statistics, their shuffled distributions and one-sided p-values."""

    observed_s1: int
    observed_s2: int
    s1: list[int]
    s2: list[int]

    @property
    def p_s1(self) -> float:
        """(1 + shuffles at or above the observed S1) / (shuffles + 1)."""
        return (1 + sum(1 for v in self.s1 if v >= self.observed_s1)) / (len(self.s1) + 1)

    @property
    def p_s2(self) -> float:
        """(1 + shuffles at or above the observed S2) / (shuffles + 1)."""
        return (1 + sum(1 for v in self.s2 if v >= self.observed_s2)) / (len(self.s2) + 1)


def shuffle_within_season(
    records: Sequence[SceneRecord], movable: Sequence[bool], rainy: set[int], rng: random.Random
) -> list[SceneRecord]:
    """Move the movable records' measurements between dates of the same season.

    Args:
        records: Scenes in time order.
        movable: Which records move (the usable ones); the others stay in place.
        rainy: Rainy-season months.
        rng: Random source.

    Returns:
        New records: same keys and days in the same order, measurements permuted.
    """
    out = list(records)
    for wet in (True, False):
        slots = [i for i, r in enumerate(records) if movable[i] and (r.day.month in rainy) == wet]
        sources = slots[:]
        rng.shuffle(sources)
        for slot, source in zip(slots, sources, strict=True):
            out[slot] = replace(records[source], key=records[slot].key, day=records[slot].day)
    return out


def s1(
    records: Sequence[SceneRecord],
    d0: Variant,
    rainy: set[int],
    mad_floor: float,
    coincident: Sequence[bool],
) -> int:
    """D0-anomalous scenes that are not rain-coincident.

    Args:
        records: Scenes.
        d0: The screening variant.
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.
        coincident: Rain-coincident (union rule, unknown counts) per position.

    Returns:
        The count.
    """
    scenes = evaluate(records, d0, rainy, mad_floor)
    return sum(1 for s, wet in zip(scenes, coincident, strict=True) if s.anomalous and not wet)


def run_placebo(
    records: Sequence[SceneRecord],
    variants: Sequence[Variant],
    rainy: set[int],
    mad_floor: float,
    coincident: Sequence[bool],
    criteria: Criteria,
    shuffles: int,
    seed: int,
) -> PlaceboResult:
    """The placebo distributions of S1 and S2.

    Args:
        records: The target's scenes.
        variants: The ten variants (D0 first is not required).
        rainy: Rainy-season months.
        mad_floor: Lower bound of sigma.
        coincident: Rain-coincident per position.
        criteria: Persistence minimum and episode gap.
        shuffles: Number of shuffles.
        seed: Random seed.

    Returns:
        The result.
    """
    d0 = next(v for v in variants if v.id == "D0")
    default_limit = d0.swir16_max
    movable = [r.usable[default_limit] for r in records]

    def s2(current: Sequence[SceneRecord]) -> int:
        result = criterion_a(
            current,
            variants,
            rainy,
            mad_floor,
            coincident,
            criteria.persistence_min,
            criteria.episode_gap_days,
        )
        return len(result.episodes)

    rng = random.Random(seed)
    values1, values2 = [], []
    for _ in range(shuffles):
        shuffled = shuffle_within_season(records, movable, rainy, rng)
        values1.append(s1(shuffled, d0, rainy, mad_floor, coincident))
        values2.append(s2(shuffled))
    return PlaceboResult(
        s1(records, d0, rainy, mad_floor, coincident), s2(records), values1, values2
    )
