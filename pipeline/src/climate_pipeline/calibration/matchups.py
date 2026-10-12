"""Samples, scene windows and their pairing (offline, from the committed snapshots).

A sample meets the usable scene of its station nearest in local date within the window; a tie
goes to the earlier scene. Same-station, same-day samples are reduced to their median first.
Each pair keeps its acquisition as its cluster, so a scene matched by several samples counts once
in every bootstrap. The hold-out is the most recent share of pairs, cut at a percentile of pair
dates; ties go to training.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from climate_pipeline.calibration.config import WindowSettings
from climate_pipeline.calibration.models import dogliotti_switch
from climate_pipeline.calibration.stations import number

BANDS = ("B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12")
CANDIDATES = ("B03", "B04", "B05", "B8A", "NDTI", "B04/B02", "B05/B04", "B8A/B04", "D15switch")


@dataclass(frozen=True)
class Sample:
    """One in-situ value (after replicates are reduced)."""

    station: str
    day: date
    target: str
    value: float
    censored: bool
    state: str = ""
    replicates: int = 1


def parse_value(text: object) -> tuple[float, bool]:
    """A sample value and whether it was reported below a detection limit (``<x``).

    Args:
        text: The reported result.

    Returns:
        ``(value, censored)``; NaN when not a number.
    """
    raw = str(text).strip()
    censored = raw.startswith("<")
    return number(raw.lstrip("<>").strip()), censored


def samples_from_soda(
    rows: Iterable[Mapping[str, object]],
    station_of_point: Mapping[str, str],
    target_of_variable: Mapping[str, str],
) -> list[Sample]:
    """Samples from the water-quality snapshot.

    Args:
        rows: SODA rows (point, date, property, result, unit).
        station_of_point: Point name -> station id.
        target_of_variable: Observed property -> target id.

    Returns:
        Samples with a numeric value.
    """
    out = []
    for row in rows:
        point = str(row.get("nombre_del_punto_de_monitoreo", ""))
        variable = str(row.get("propiedad_observada", ""))
        if point not in station_of_point or variable not in target_of_variable:
            continue
        value, censored = parse_value(row.get("resultado", ""))
        if not math.isfinite(value):
            continue
        day = date.fromisoformat(str(row["fecha"])[:10])
        out.append(Sample(station_of_point[point], day, target_of_variable[variable], value,
                          censored))  # fmt: skip
    return out


def samples_from_series(body: str, station: str, target: str) -> list[Sample]:
    """Samples from an IDEAM bucket series (one value per day; the approval level as state).

    Args:
        body: CSV text (``fechaObservacion,valorObservado,nivelAprobacion``).
        station: Station id.
        target: Target id.

    Returns:
        Samples with a numeric value.
    """
    out = []
    for row in csv.DictReader(io.StringIO(body)):
        value = number(row.get("valorObservado", ""))
        stamp = str(row.get("fechaObservacion", ""))[:10]
        if not math.isfinite(value) or len(stamp) < 10:
            continue
        out.append(Sample(station, date.fromisoformat(stamp), target, value, False,
                          str(row.get("nivelAprobacion", ""))))  # fmt: skip
    return out


def reduce_replicates(samples: Iterable[Sample]) -> list[Sample]:
    """One sample per station, day and target: the median, censored if any replicate was.

    Args:
        samples: Samples.

    Returns:
        Reduced samples, sorted by station, day and target.
    """
    groups: dict[tuple[str, date, str], list[Sample]] = {}
    for s in samples:
        groups.setdefault((s.station, s.day, s.target), []).append(s)
    out = []
    for (station, day, target), items in sorted(groups.items()):
        states = sorted({s.state for s in items})
        out.append(
            Sample(
                station, day, target, float(np.median([s.value for s in items])),
                any(s.censored for s in items), states[0] if len(states) == 1 else "mixed",
                len(items),
            )
        )  # fmt: skip
    return out


@dataclass(frozen=True)
class SceneRow:
    """One station window in one acquisition."""

    station: str
    collection: str
    key: str
    day: date
    family: str
    stats: Mapping[str, float]
    bands: Mapping[str, float]
    features: Mapping[str, float] = field(default_factory=dict)

    def usable(self, window: WindowSettings) -> bool:
        """The preregistered per-scene guards.

        Args:
            window: Window settings.

        Returns:
            True with enough valid pixels, low contamination and a passed water-B11 check.
        """
        s = self.stats
        return (
            s.get("valid_px", 0.0) >= window.min_valid_px
            and s.get("contamination", 1.0) <= window.max_contamination
            and s.get("b11_ok", 0.0) >= 1
        )


def candidate_values(
    bands: Mapping[str, float], dogliotti: tuple[tuple[float, float], tuple[float, float]] | None
) -> dict[str, float]:
    """The nine preregistered candidates from band medians.

    Args:
        bands: Band medians (reflectance).
        dogliotti: Red and NIR ``(A, C)`` of the switch, or None when not available.

    Returns:
        Candidate id -> value (NaN when undefined).
    """

    def ratio(a: str, b: str) -> float:
        x, y = bands.get(a, math.nan), bands.get(b, math.nan)
        return x / y if math.isfinite(x) and math.isfinite(y) and y > 0 else math.nan

    b03, b04 = bands.get("B03", math.nan), bands.get("B04", math.nan)
    ndti = (b04 - b03) / (b04 + b03) if math.isfinite(b03 + b04) and b03 + b04 > 0 else math.nan
    switch = (
        dogliotti_switch(b04, bands.get("B8A", math.nan), dogliotti[0], dogliotti[1])
        if dogliotti
        else math.nan
    )
    return {
        "B03": b03, "B04": b04, "B05": bands.get("B05", math.nan),
        "B8A": bands.get("B8A", math.nan), "NDTI": ndti, "B04/B02": ratio("B04", "B02"),
        "B05/B04": ratio("B05", "B04"), "B8A/B04": ratio("B8A", "B04"), "D15switch": switch,
    }  # fmt: skip


def scenes_from_csv(
    text: str,
    window: str,
    dogliotti: tuple[tuple[float, float], tuple[float, float]] | None,
) -> list[SceneRow]:
    """Scene windows from the imagery snapshot.

    Args:
        text: ``windows-<collection>.csv``.
        window: ``300m`` (primary) or ``1000m``.
        dogliotti: Coefficients of the switch candidate.

    Returns:
        One row per station and acquisition for that window.
    """
    out = []
    stat_names = ("window_px", "data_px", "valid_px", "contamination", "glint_share",
                  "b11_median", "b11_ok", "ndti_px_median")  # fmt: skip
    for row in csv.DictReader(io.StringIO(text)):
        if row["window"] != window:
            continue
        bands = {b: number(row[b]) for b in BANDS}
        out.append(
            SceneRow(
                station=row["station"], collection=row["collection"], key=row["key"],
                day=date.fromisoformat(row["local_date"]), family=row["family"],
                stats={**{k: number(row[k]) for k in stat_names},
                       "bands_read": number(row.get("bands_read") or "1")},
                bands=bands,
                features=candidate_values(bands, dogliotti),
            )
        )  # fmt: skip
    return out


@dataclass(frozen=True)
class Pair:
    """A sample and the scene it met."""

    target: str
    station: str
    sample_day: date
    scene_key: str
    scene_day: date
    gap_days: int
    value: float
    censored: bool
    state: str
    family: str
    features: Mapping[str, float]
    stats: Mapping[str, float]


def match(
    samples: Sequence[Sample], scenes: Sequence[SceneRow], max_days: int, window: WindowSettings
) -> list[Pair]:
    """Pair each sample with the nearest usable scene of its station within ``max_days``.

    Args:
        samples: Reduced samples.
        scenes: Station windows (one collection, one window size).
        max_days: Largest gap in days.
        window: Window settings (the usability guards).

    Returns:
        Pairs, in sample order.
    """
    by_station: dict[str, list[SceneRow]] = {}
    for scene in scenes:
        if scene.usable(window):
            by_station.setdefault(scene.station, []).append(scene)
    for rows in by_station.values():
        rows.sort(key=lambda r: (r.day, r.key))
    out = []
    for s in samples:
        best: tuple[int, date, str, SceneRow] | None = None
        for scene in by_station.get(s.station, []):
            gap = abs((scene.day - s.day).days)
            if gap > max_days:
                continue
            rank = (gap, scene.day, scene.key, scene)
            if best is None or rank[:3] < best[:3]:
                best = rank
        if best is None:
            continue
        scene = best[3]
        out.append(
            Pair(s.target, s.station, s.day, scene.key, scene.day, best[0], s.value, s.censored,
                 s.state, scene.family, scene.features, scene.stats)
        )  # fmt: skip
    return out


def split(
    pairs: Sequence[Pair], holdout_share: float
) -> tuple[date | None, list[Pair], list[Pair]]:
    """Training and hold-out pairs: the most recent share by sample date (ties to training).

    Args:
        pairs: One target's pairs.
        holdout_share: E.g. 0.3.

    Returns:
        The cut date (the nearest-rank percentile of pair dates), training, hold-out.
    """
    if not pairs:
        return None, [], []
    days = sorted(p.sample_day for p in pairs)
    index = max(0, math.ceil((1 - holdout_share) * len(days)) - 1)
    cut = days[index]
    train = [p for p in pairs if p.sample_day <= cut]
    holdout = [p for p in pairs if p.sample_day > cut]
    return cut, train, holdout


def fittable(pairs: Iterable[Pair]) -> list[Pair]:
    """Pairs a model may use: positive, finite, not censored.

    Args:
        pairs: Pairs.

    Returns:
        The usable ones.
    """
    return [p for p in pairs if not p.censored and math.isfinite(p.value) and p.value > 0]
