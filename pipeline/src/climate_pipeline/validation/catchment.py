"""Rain coincidence for the validation: the screening's point rule, the catchment rule, the union.

The catchment rule samples Open-Meteo at the committed grid points; points that Open-Meteo serves
from the same grid cell are merged. Window sums follow ``RainSeries.window_sum`` exactly (whole
hours ending at or before the moment; unknown with more than 10 % of the hours missing), computed
for many moments at once with cumulative sums.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np
from numpy.typing import NDArray

from climate_pipeline.screening.rain import RainSeries
from climate_pipeline.validation.config import Window

log = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]
HourArray = NDArray[np.datetime64]
StatKey = tuple[str, int]  # (statistic, window hours)


# ----------------------------------------------------------------------------------------------
# Window sums
# ----------------------------------------------------------------------------------------------


def hour_ends(moments: Sequence[datetime]) -> HourArray:
    """The whole UTC hour at or before each moment (the end of the last full hour counted).

    Args:
        moments: Timezone-aware moments.

    Returns:
        ``datetime64[h]`` values.
    """
    return np.array(
        [np.datetime64(m.astimezone(UTC).replace(tzinfo=None), "h") for m in moments],
        dtype="datetime64[h]",
    )


def window_sums(series: RainSeries, ends: HourArray, hours: int) -> FloatArray:
    """Rain over the ``hours`` hours ending at each end, as ``RainSeries.window_sum`` computes it.

    Args:
        series: Hourly rain (hour-ending times, sorted).
        ends: Window ends.
        hours: Window length.

    Returns:
        Millimetres, NaN where fewer than ``hours`` values exist or more than 10 % are missing.
    """
    times = series.times.astype("datetime64[h]")
    values = series.mm
    stop = np.searchsorted(times, ends, side="right")
    start = np.searchsorted(times, ends - np.timedelta64(hours, "h"), side="right")
    totals = np.concatenate([[0.0], np.cumsum(np.nan_to_num(values))])
    missing = np.concatenate([[0], np.cumsum(np.isnan(values))])
    count = stop - start
    total = totals[stop] - totals[start]
    lost = missing[stop] - missing[start]
    bad = (count < hours) | (lost > 0.1 * hours)
    return np.where(bad, np.nan, total)


# ----------------------------------------------------------------------------------------------
# Point rule (the screening's)
# ----------------------------------------------------------------------------------------------


def point_values(
    series: Sequence[RainSeries], moments: Sequence[datetime], hours: int
) -> FloatArray:
    """The wettest rain point's sum before each moment (NaN when every point is unknown).

    Args:
        series: One series per rain point.
        moments: Acquisition times.
        hours: Window length.

    Returns:
        Millimetres per moment.
    """
    if not series:
        return np.full(len(moments), np.nan)
    ends = hour_ends(moments)
    sums = np.vstack([window_sums(s, ends, hours) for s in series])
    known = np.isfinite(sums).any(axis=0)
    best = np.where(known, np.nanmax(np.where(np.isfinite(sums), sums, -np.inf), axis=0), np.nan)
    return np.asarray(best, dtype=np.float64)


def point_flags(values: FloatArray, threshold_mm: float) -> list[bool | None]:
    """The screening's rule: rain-coincident above the threshold, unknown when the sum is unknown.

    Args:
        values: The wettest point's sum per scene.
        threshold_mm: Strictly above this is coincident.

    Returns:
        True, False or None (unknown) per scene.
    """
    return [None if not np.isfinite(v) else bool(v > threshold_mm) for v in values]


# ----------------------------------------------------------------------------------------------
# Catchment rule
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CellSeries:
    """Hourly rain of one Open-Meteo grid cell and the grid points it serves."""

    point_ids: tuple[str, ...]
    cell_lon: float
    cell_lat: float
    series: RainSeries


def catchment_statistics(
    cells: Sequence[CellSeries],
    ends: HourArray,
    windows_h: Sequence[int],
    statistics: Sequence[str],
) -> dict[StatKey, FloatArray]:
    """Mean and maximum over the grid cells of the window sums ending at each end.

    Args:
        cells: The grid cells.
        ends: Window ends.
        windows_h: Window lengths.
        statistics: ``mean`` and/or ``max``.

    Returns:
        Values per (statistic, window), NaN where any cell is unknown.
    """
    out: dict[StatKey, FloatArray] = {}
    for hours in windows_h:
        sums = np.vstack([window_sums(c.series, ends, hours) for c in cells])
        unknown = np.isnan(sums).any(axis=0)
        filled = np.where(np.isnan(sums), 0.0, sums)
        for stat in statistics:
            value = filled.mean(axis=0) if stat == "mean" else filled.max(axis=0)
            out[(stat, hours)] = np.where(unknown, np.nan, value)
    return out


def daily_ends(period: Window, hour_utc: int) -> HourArray:
    """One moment per day of a period, at a fixed UTC hour.

    Args:
        period: The period.
        hour_utc: Hour of day (UTC).

    Returns:
        ``datetime64[h]`` values.
    """
    days = (period.end - period.start).days + 1
    first = np.datetime64(period.start.isoformat(), "h") + np.timedelta64(hour_utc, "h")
    return first + np.arange(days) * np.timedelta64(24, "h")


@dataclass(frozen=True)
class Thresholds:
    """Percentile thresholds of each catchment statistic and how many days they rest on."""

    values: dict[StatKey, float]
    days: dict[StatKey, int]
    day_share_flagged: float  # share of sampled days where any statistic reaches its threshold


def thresholds(
    cells: Sequence[CellSeries],
    period: Window,
    hour_utc: int,
    windows_h: Sequence[int],
    statistics: Sequence[str],
    percentile: float,
) -> Thresholds:
    """The percentile of each statistic over its daily values (numpy's linear interpolation).

    Args:
        cells: The grid cells.
        period: Days sampled.
        hour_utc: Sampling hour (UTC).
        windows_h: Window lengths.
        statistics: ``mean`` and/or ``max``.
        percentile: E.g. 90.

    Returns:
        The thresholds.
    """
    stats = catchment_statistics(cells, daily_ends(period, hour_utc), windows_h, statistics)
    values: dict[StatKey, float] = {}
    days: dict[StatKey, int] = {}
    for key, daily in stats.items():
        known = daily[np.isfinite(daily)]
        values[key] = float(np.percentile(known, percentile)) if known.size else float("nan")
        days[key] = int(known.size)
    flagged = np.zeros(len(next(iter(stats.values()))), dtype=bool)
    for key, daily in stats.items():
        flagged |= np.nan_to_num(daily, nan=-np.inf) >= values[key]
    return Thresholds(values, days, float(flagged.mean()) if flagged.size else float("nan"))


def catchment_flags(
    cells: Sequence[CellSeries],
    moments: Sequence[datetime],
    limits: Thresholds,
    windows_h: Sequence[int],
    statistics: Sequence[str],
) -> tuple[list[bool | None], dict[StatKey, FloatArray]]:
    """Catchment rule per scene: coincident when any statistic reaches its threshold.

    Args:
        cells: The grid cells.
        moments: Acquisition times.
        limits: The thresholds.
        windows_h: Window lengths.
        statistics: ``mean`` and/or ``max``.

    Returns:
        True, False or None (unknown: no statistic reached its threshold and one is unknown)
        per scene, and the statistics themselves.
    """
    stats = catchment_statistics(cells, hour_ends(moments), windows_h, statistics)
    flags: list[bool | None] = []
    for k in range(len(moments)):
        values = {key: float(v[k]) for key, v in stats.items()}
        threshold = limits.values
        if any(np.isfinite(v) and v >= threshold[key] for key, v in values.items()):
            flags.append(True)
        elif any(
            not np.isfinite(v) or not np.isfinite(threshold[key]) for key, v in values.items()
        ):
            flags.append(None)
        else:
            flags.append(False)
    return flags, stats


def union(point: bool | None, catchment: bool | None, use_catchment: bool) -> str:
    """The union rule: ``yes`` when either rule flags the scene, ``unknown`` when either is unknown.

    Args:
        point: The point rule's flag.
        catchment: The catchment rule's flag.
        use_catchment: False when the grid is unbuildable (point rule only).

    Returns:
        ``yes``, ``no`` or ``unknown``; criterion (a) treats ``unknown`` as coincident.
    """
    flags = [point, catchment] if use_catchment else [point]
    if any(flag is True for flag in flags):
        return "yes"
    if any(flag is None for flag in flags):
        return "unknown"
    return "no"


# ----------------------------------------------------------------------------------------------
# Open-Meteo with pacing, backoff and cell coordinates
# ----------------------------------------------------------------------------------------------


def _cache_key(params: dict[str, str | float]) -> str:
    # The same key as the screening's OpenMeteoClient, so the two share cached responses.
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]


def fetch_hourly(
    http: httpx.Client,
    url: str,
    lon: float,
    lat: float,
    start: date,
    end: date,
    cache_dir: Path | None,
    max_attempts: int,
    sleep: Callable[[float], Any] = time.sleep,
) -> tuple[dict[str, Any], bool]:
    """Hourly precipitation at a point, retried with growing waits after HTTP 429 or errors.

    Args:
        http: HTTP client.
        url: Open-Meteo archive endpoint.
        lon: Longitude.
        lat: Latitude.
        start: First day (UTC).
        end: Last day (UTC).
        cache_dir: Where responses are kept (None disables caching).
        max_attempts: Attempts before giving up.
        sleep: Sleep function (injectable for tests).

    Returns:
        The JSON payload and whether it came from the cache.

    Raises:
        httpx.HTTPError: When every attempt failed.
    """
    params: dict[str, str | float] = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "hourly": "precipitation",
        "timezone": "UTC",
        "precipitation_unit": "mm",
    }
    cache = cache_dir / f"open-meteo-{_cache_key(params)}.json" if cache_dir else None
    if cache is not None and cache.exists():
        cached: dict[str, Any] = json.loads(cache.read_text(encoding="utf-8"))
        return cached, True
    for attempt in range(max_attempts):
        try:
            response = http.get(url, params=params)
            response.raise_for_status()
            break
        except httpx.HTTPError as error:
            if attempt == max_attempts - 1:
                raise
            wait = min(300.0, 15.0 * 2**attempt)
            if isinstance(error, httpx.HTTPStatusError):
                retry_after = error.response.headers.get("retry-after", "")
                if retry_after.isdigit():
                    wait = min(600.0, float(retry_after))
            log.warning("Open-Meteo request failed (%s); waiting %.0f s", error, wait)
            sleep(wait)
    payload: dict[str, Any] = response.json()
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload), encoding="utf-8")
    return payload, False


def series_from_payload(label: str, lon: float, lat: float, payload: dict[str, Any]) -> RainSeries:
    """An hourly series from an Open-Meteo payload (each value is the rain of the hour before).

    Args:
        label: Name of the point.
        lon: Requested longitude.
        lat: Requested latitude.
        payload: The JSON payload.

    Returns:
        The series.
    """
    hourly: dict[str, Any] = payload["hourly"]
    ends = np.array([np.datetime64(t, "h") for t in hourly["time"]], dtype="datetime64[h]")
    values = np.array(
        [np.nan if v is None else float(v) for v in hourly["precipitation"]], dtype=np.float64
    )
    return RainSeries(label, lon, lat, ends, values)


def fetch_grid(
    points: Sequence[tuple[str, float, float]],
    url: str,
    start: date,
    end: date,
    cache_dir: Path | None,
    pause_s: float,
    max_attempts: int,
    http: httpx.Client | None = None,
    sleep: Callable[[float], Any] = time.sleep,
) -> list[CellSeries]:
    """Hourly rain at every grid point, one series per Open-Meteo cell.

    Points answered with the same cell coordinates are merged, keeping the first point's series.

    Args:
        points: ``(point_id, lon, lat)``.
        url: Open-Meteo archive endpoint.
        start: First day.
        end: Last day.
        cache_dir: Response cache.
        pause_s: Pause before each request that is not served from the cache.
        max_attempts: Attempts per request.
        http: HTTP client (injectable for tests).
        sleep: Sleep function (injectable for tests).

    Returns:
        The cells, in the order of their first point.
    """
    client = http or httpx.Client(timeout=120)
    cells: dict[tuple[float, float], CellSeries] = {}
    for point_id, lon, lat in points:
        payload, cached = fetch_hourly(
            client, url, lon, lat, start, end, cache_dir, max_attempts, sleep
        )
        if not cached:
            sleep(pause_s)
        cell = (round(float(payload["longitude"]), 4), round(float(payload["latitude"]), 4))
        if cell in cells:
            known = cells[cell]
            cells[cell] = CellSeries(
                (*known.point_ids, point_id), known.cell_lon, known.cell_lat, known.series
            )
            continue
        series = series_from_payload(point_id, lon, lat, payload)
        cells[cell] = CellSeries((point_id,), cell[0], cell[1], series)
    return list(cells.values())


def rain_start(period: Window, lead_days: int) -> date:
    """The first day of rain to fetch, so the first windows of the period are full.

    Args:
        period: The study period.
        lead_days: Days before it.

    Returns:
        The first day.
    """
    return period.start - timedelta(days=lead_days)
