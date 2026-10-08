"""Report-only tables: the same time of year in other years, and the January-February scenes."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date

import numpy as np

from climate_pipeline.screening.stage2 import SIGNALS
from climate_pipeline.validation.variants import SceneRecord, VariantScene


def day_distance(a: date, b: date) -> int:
    """Days between two days of the year, around the year end (0 to 182).

    Args:
        a: A day.
        b: Another day.

    Returns:
        The circular distance between their days of the year.
    """
    gap = abs(a.timetuple().tm_yday - b.timetuple().tm_yday)
    return min(gap, 365 - gap)


def seasonal_rows(
    records: Sequence[SceneRecord],
    d0: Sequence[VariantScene],
    limit: float,
    halfwidth: int,
) -> list[dict[str, object]]:
    """For each D0-anomalous signal, the same signal near the same day of year in other years.

    Args:
        records: The reach's scenes.
        d0: Their D0 evaluation (same order).
        limit: The screening's glint limit (the values D0 uses).
        halfwidth: Days around the day of year.

    Returns:
        One row per anomalous scene and signal.
    """
    rows = []
    for record, scene in zip(records, d0, strict=True):
        for signal in scene.signals:
            value = record.values[limit][signal]
            neighbours = [
                other.values[limit][signal]
                for other in records
                if other.day.year != record.day.year
                and other.usable[limit]
                and day_distance(other.day, record.day) <= halfwidth
                and math.isfinite(other.values[limit][signal])
            ]
            rows.append(
                {
                    "date": record.day.isoformat(),
                    "signal": signal,
                    "ndti": round(value, 4),
                    "z_d0": round(scene.z[signal], 2),
                    "other_years_n": len(neighbours),
                    "other_years_median": round(float(np.median(neighbours)), 4)
                    if neighbours
                    else math.nan,
                    "other_years_min": round(min(neighbours), 4) if neighbours else math.nan,
                    "other_years_max": round(max(neighbours), 4) if neighbours else math.nan,
                }
            )
    return rows


def january_february_rows(
    records: Sequence[SceneRecord],
    evaluations: dict[str, list[VariantScene]],
    limit: float,
    variant_ids: Sequence[str] = ("D0", "B2", "B3"),
) -> list[dict[str, object]]:
    """Every January and February scene: its difference signal, z under some variants, glint.

    Args:
        records: The reach's scenes.
        evaluations: Variant id -> evaluation (same order as records).
        limit: The screening's glint limit.
        variant_ids: Variants whose z is shown.

    Returns:
        One row per scene.
    """
    rows = []
    for k, record in enumerate(records):
        if record.day.month not in (1, 2):
            continue
        row: dict[str, object] = {
            "date": record.day.isoformat(),
            "usable": record.usable[limit],
            "delta_ndti": round(record.values[limit]["delta"], 4),
            "glint_share_max": round(record.glint_share, 3),
        }
        for vid in variant_ids:
            scene = evaluations[vid][k]
            row[f"z_delta_{vid}"] = round(scene.z.get("delta", math.nan), 2)
            row[f"anomalous_{vid}"] = scene.anomalous
        rows.append(row)
    return rows


def signal_split(evaluations: dict[str, list[VariantScene]]) -> list[dict[str, object]]:
    """Anomalous scenes per variant and signal.

    Args:
        evaluations: Variant id -> evaluation.

    Returns:
        One row per variant.
    """
    rows = []
    for vid, scenes in evaluations.items():
        row: dict[str, object] = {"variant": vid}
        for signal in SIGNALS:
            row[f"anomalous_{signal}"] = sum(1 for s in scenes if signal in s.signals)
        rows.append(row)
    return rows
