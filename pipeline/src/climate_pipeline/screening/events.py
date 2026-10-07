"""The documented event catalog and how events are matched to scenes.

An event is "observable" when at least one usable scene falls in its window (a few days before
to a week or so after). An observable event is a hit when any anomaly score in the window
reaches the threshold, else a miss. A chance rate from randomly shifted windows of the same
length shows how often a window would "hit" anyway.
"""

from __future__ import annotations

import calendar
import csv
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from climate_pipeline.screening.config import EventConfig

EVENT_COLUMNS = (
    "event_id",
    "site_id",
    "date_start",
    "date_end",
    "date_precision",
    "river",
    "event_type",
    "description",
    "source_url",
    "source_type",
    "confidence",
    "verification",
    "notes",
)


@dataclass(frozen=True)
class CatalogEvent:
    """One documented event (dates exactly as the source gives them)."""

    event_id: str
    site_id: str
    date_start: date
    date_end: date
    date_precision: str
    river: str
    event_type: str
    description: str
    source_url: str
    source_type: str
    confidence: str
    verification: str
    notes: str


def _parse_day(text: str, end: bool) -> date:
    parts = [int(p) for p in text.strip().split("-")]
    if len(parts) == 3:
        return date(parts[0], parts[1], parts[2])
    if len(parts) == 2:
        last = calendar.monthrange(parts[0], parts[1])[1]
        return date(parts[0], parts[1], last if end else 1)
    if len(parts) == 1:
        return date(parts[0], 12, 31) if end else date(parts[0], 1, 1)
    raise ValueError(f"bad date {text!r}")


def load_events(path: Path) -> list[CatalogEvent]:
    """Read ``events.csv``.

    Args:
        path: The catalog file.

    Returns:
        The events (a month-only date spans the whole month).

    Raises:
        ValueError: If the header differs from the expected columns.
    """
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EVENT_COLUMNS:
            raise ValueError(f"{path}: columns must be {', '.join(EVENT_COLUMNS)}")
        events = []
        for row in reader:
            start = _parse_day(row["date_start"], end=False)
            end = _parse_day(row["date_end"] or row["date_start"], end=True)
            events.append(
                CatalogEvent(
                    **{k: row[k] for k in EVENT_COLUMNS if k not in ("date_start", "date_end")},
                    date_start=start,
                    date_end=max(start, end),
                )
            )
        return events


def event_window(event: CatalogEvent, cfg: EventConfig) -> tuple[date, date]:
    """The days in which a scene can show the event.

    Args:
        event: The event.
        cfg: Window settings.

    Returns:
        First and last day (inclusive).
    """
    return (
        event.date_start - timedelta(days=cfg.window_before_days),
        event.date_end + timedelta(days=cfg.window_after_days),
    )


def is_scored(event: CatalogEvent, cfg: EventConfig, start: date, end: date) -> bool:
    """Whether an event counts in the score and the hit/miss table.

    Only events dated to the day or week, with a window inside the study period, are scored;
    month-precision events stay in the catalog as context.

    Args:
        event: The event.
        cfg: Event settings.
        start: Study period start.
        end: Study period end.

    Returns:
        True if scored.
    """
    first, last = event_window(event, cfg)
    return event.date_precision in cfg.scored_precisions and last >= start and first <= end


def window_days(event: CatalogEvent, cfg: EventConfig) -> int:
    """Length of an event's window in days (inclusive).

    Args:
        event: The event.
        cfg: Window settings.

    Returns:
        Number of days.
    """
    first, last = event_window(event, cfg)
    return (last - first).days + 1


def observable(event: CatalogEvent, cfg: EventConfig, scene_days: Iterable[date]) -> list[date]:
    """The usable scene days inside an event's window.

    Args:
        event: The event.
        cfg: Window settings.
        scene_days: Days with a usable scene.

    Returns:
        The scene days in the window, sorted.
    """
    first, last = event_window(event, cfg)
    return sorted(day for day in scene_days if first <= day <= last)


@dataclass(frozen=True)
class EventOutcome:
    """What the imagery shows around one event."""

    event: CatalogEvent
    status: str  # hit | miss | unobservable | insufficient-baseline
    scene_days: tuple[date, ...]
    max_abs_z: float | None
    signal: str


def evaluate(
    event: CatalogEvent,
    cfg: EventConfig,
    scores: dict[date, dict[str, float]],
    threshold: float,
) -> EventOutcome:
    """Classify an event as hit, miss, unobservable or insufficient baseline.

    Unobservable means no usable scene in the window. Usable scenes whose z-scores could not be
    computed (too few values for a baseline) give "insufficient-baseline", never a miss.

    Args:
        event: The event.
        cfg: Window settings.
        scores: Per scene day, anomaly scores by signal name (NaN when not computable).
        threshold: |z| at or above which a scene is anomalous.

    Returns:
        The outcome, with the largest |z| in the window and the signal it came from.
    """
    days = observable(event, cfg, scores)
    best, best_signal = None, ""
    for day in days:
        for signal, z in scores[day].items():
            if z == z and (best is None or abs(z) > best):  # z == z skips NaN
                best, best_signal = abs(z), signal
    if best is None:
        status = "insufficient-baseline" if days else "unobservable"
        return EventOutcome(event, status, tuple(days), None, "")
    status = "hit" if best >= threshold else "miss"
    return EventOutcome(event, status, tuple(days), best, best_signal)


def chance_rate(
    window_days: int,
    scores: dict[date, dict[str, float]],
    threshold: float,
    start: date,
    end: date,
    avoid: Sequence[tuple[date, date]],
    shifts: int,
    seed: int,
) -> tuple[float, int]:
    """How often a random window of the same length, away from catalog events, "hits".

    Args:
        window_days: Window length in days.
        scores: Per scene day, anomaly scores by signal.
        threshold: |z| threshold.
        start: Study period start.
        end: Study period end.
        avoid: Event windows to stay clear of.
        shifts: Number of random windows.
        seed: Random seed (fixed, so the rate is reproducible).

    Returns:
        Share of observable random windows that hit, and how many were observable.
    """
    rng = random.Random(seed)
    # Window starts from the period's first day to the last day that still fits the window.
    span = (end - start).days + 1 - window_days
    if span < 0:
        return float("nan"), 0
    hits = observed = 0
    for _ in range(shifts):
        first = start + timedelta(days=rng.randrange(span + 1))
        last = first + timedelta(days=window_days - 1)
        if any(first <= a_end and a_start <= last for a_start, a_end in avoid):
            continue
        zs = [
            abs(z)
            for day, by_signal in scores.items()
            if first <= day <= last
            for z in by_signal.values()
            if z == z
        ]
        if not zs:
            continue
        observed += 1
        hits += max(zs) >= threshold
    return (hits / observed if observed else float("nan")), observed
