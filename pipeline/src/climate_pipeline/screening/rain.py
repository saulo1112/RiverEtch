"""Hourly precipitation from the Open-Meteo historical archive and the rain windows used.

Open-Meteo's archive is a reanalysis-based grid (kilometres to tens of kilometres), so it can miss
convective Andean showers; the screening samples the site center plus upstream points and treats
the result as context, not measurement. Each hourly value is the rain of the preceding hour.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import numpy as np
from numpy.typing import NDArray

HOUR = np.timedelta64(1, "h")


@dataclass(frozen=True)
class RainSeries:
    """Hourly precipitation at one point: hour-ending UTC times and millimetres (NaN if missing)."""

    label: str
    lon: float
    lat: float
    times: NDArray[np.datetime64]
    mm: NDArray[np.float64]

    def window_sum(self, at: datetime, hours: int) -> float:
        """Rain in the ``hours`` before a moment (whole hours ending at or before it).

        Args:
            at: The moment (timezone-aware), e.g. the acquisition time.
            hours: Window length.

        Returns:
            Millimetres, or NaN if more than 10 % of the hours are missing or out of range.
        """
        end = np.datetime64(at.astimezone(UTC).replace(tzinfo=None), "h")
        start = end - hours * HOUR
        sel = (self.times > start) & (self.times <= end)
        values = self.mm[sel]
        if values.size < hours or np.isnan(values).sum() > 0.1 * hours:
            return float("nan")
        return float(np.nansum(values))

    def same_day(self, at: datetime, timezone: str) -> float:
        """Rain from local midnight up to a moment.

        Args:
            at: The moment (timezone-aware).
            timezone: IANA zone defining the day, e.g. ``America/Bogota``.

        Returns:
            Millimetres (NaN if the hours are missing).
        """
        local = at.astimezone(ZoneInfo(timezone))
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        hours = int((local - midnight).total_seconds() // 3600)
        return self.window_sum(at, hours) if hours > 0 else 0.0

    def daily(self, timezone: str) -> dict[date, float]:
        """Daily totals in a local timezone (days with any missing hour are left out).

        Args:
            timezone: IANA zone defining the day.

        Returns:
            Millimetres per local day.
        """
        tz = ZoneInfo(timezone)
        totals: dict[date, float] = {}
        missing: set[date] = set()
        for stamp, value in zip(self.times, self.mm, strict=True):
            hour_end = datetime.fromisoformat(str(stamp)).replace(tzinfo=UTC)
            day = (hour_end - timedelta(minutes=30)).astimezone(tz).date()
            if np.isnan(value):
                missing.add(day)
            else:
                totals[day] = totals.get(day, 0.0) + float(value)
        return {day: mm for day, mm in totals.items() if day not in missing}


def rainy_months(daily: dict[date, float]) -> tuple[int, ...]:
    """Months whose mean daily rain is above the median of the twelve monthly means.

    Args:
        daily: Daily totals.

    Returns:
        Month numbers (1-12) of the rainy season(s).
    """
    by_month: dict[int, list[float]] = {}
    for day, mm in daily.items():
        by_month.setdefault(day.month, []).append(mm)
    means = {month: float(np.mean(values)) for month, values in by_month.items()}
    if len(means) < 12:
        return ()
    median = float(np.median(list(means.values())))
    return tuple(sorted(month for month, mean in means.items() if mean > median))


class OpenMeteoClient:
    """Fetches hourly precipitation from the Open-Meteo archive API, with a JSON cache."""

    def __init__(
        self, url: str, http: httpx.Client | None = None, cache_dir: Path | None = None
    ) -> None:
        """Create the client.

        Args:
            url: Archive endpoint, e.g. ``https://archive-api.open-meteo.com/v1/archive``.
            http: HTTP client (injectable for tests).
            cache_dir: Where to keep responses (None disables caching).
        """
        self._url = url
        self._http = http or httpx.Client(timeout=60)
        self._cache_dir = cache_dir

    def hourly(self, label: str, lon: float, lat: float, start: date, end: date) -> RainSeries:
        """Hourly precipitation at a point over a period (UTC hours, hour-ending).

        Args:
            label: Name of the point.
            lon: Longitude.
            lat: Latitude.
            start: First day (UTC).
            end: Last day (UTC).

        Returns:
            The series.
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
        payload = self._get(params)
        hourly: dict[str, Any] = payload["hourly"]
        # Open-Meteo stamps each value with the start of its hour; store the hour's end instead.
        ends = np.array(
            [np.datetime64(t, "h") + HOUR for t in hourly["time"]], dtype="datetime64[h]"
        )
        values = np.array(
            [np.nan if v is None else float(v) for v in hourly["precipitation"]], dtype=np.float64
        )
        return RainSeries(label, lon, lat, ends, values)

    def _get(self, params: dict[str, str | float]) -> dict[str, Any]:
        key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:16]
        cache = self._cache_dir / f"open-meteo-{key}.json" if self._cache_dir else None
        if cache is not None and cache.exists():
            cached: dict[str, Any] = json.loads(cache.read_text(encoding="utf-8"))
            return cached
        response = self._http.get(self._url, params=params)
        response.raise_for_status()
        payload: dict[str, Any] = response.json()
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload), encoding="utf-8")
        return payload


@dataclass(frozen=True)
class RainContext:
    """Rain around one acquisition at a site's rain points."""

    sums_mm: dict[str, dict[int, float]]
    same_day_mm: dict[str, float]

    def max_over_points(self, hours: int) -> float:
        """The wettest point's sum over a window (NaN if every point is missing).

        Args:
            hours: Window length.

        Returns:
            Millimetres.
        """
        values = [sums[hours] for sums in self.sums_mm.values() if not np.isnan(sums[hours])]
        return max(values) if values else float("nan")


def rain_context(
    series: list[RainSeries], at: datetime, windows_h: tuple[int, ...], timezone: str
) -> RainContext:
    """Window sums and same-day rain at every point for one moment.

    Args:
        series: One series per rain point.
        at: The acquisition time.
        windows_h: Window lengths in hours.
        timezone: Zone defining "same day".

    Returns:
        The context.
    """
    return RainContext(
        sums_mm={s.label: {h: s.window_sum(at, h) for h in windows_h} for s in series},
        same_day_mm={s.label: s.same_day(at, timezone) for s in series},
    )
