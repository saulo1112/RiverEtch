"""The USGS Water Data APIs (``api.waterdata.usgs.gov``): sites, continuous values, samples.

The legacy WaterServices are retired in 2027, so only the modernized OGC APIs are used. Requests
retry with backoff on rate limits and server errors; every response body can be hashed into a
fetch manifest by the caller. Nothing here interprets a value beyond the preregistered overpass
rule (:func:`overpass_value`).
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

SAMPLES = "https://api.waterdata.usgs.gov/samples-data/results/narrow"
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_RATE_WAIT_S = 1800.0  # a rate limit's Retry-After is honored up to 30 minutes
ABBREVIATIONS = {"MISS": "MISSISSIPPI"}


def get(client: httpx.Client, url: str, params: Mapping[str, str] | None = None,
        attempts: int = 5) -> httpx.Response:  # fmt: skip
    """GET with backoff on rate limits and server errors.

    A rate limit (429) waits for its ``Retry-After`` (up to 30 minutes: the quota is hourly);
    a server error backs off for at most a minute. A free API key in ``USGS_API_KEY`` raises the
    quota; it travels in the ``X-Api-Key`` header, so no URL, log or manifest holds it.

    Args:
        client: HTTP client.
        url: Address.
        params: Query parameters.
        attempts: Tries before giving up.

    Returns:
        The successful response.

    Raises:
        httpx.HTTPStatusError: On a client error, or when every try failed.
    """
    key = os.environ.get("USGS_API_KEY", "").strip()
    headers = {"X-Api-Key": key} if key else None
    for attempt in range(attempts):
        response = client.get(url, params=params, headers=headers)
        if response.status_code not in RETRY_STATUS or attempt == attempts - 1:
            response.raise_for_status()
            return response
        wait = float(response.headers.get("Retry-After", 0) or 0) or 2.0 * 2**attempt
        time.sleep(min(wait, MAX_RATE_WAIT_S if response.status_code == 429 else 60.0))
    raise AssertionError("unreachable")


def features(client: httpx.Client, url: str, params: Mapping[str, str]
             ) -> tuple[list[dict[str, Any]], list[bytes]]:  # fmt: skip
    """Every feature of an OGC API items query, following ``next`` links.

    Args:
        client: HTTP client.
        url: The collection's ``items`` URL.
        params: Query parameters of the first page.

    Returns:
        The features and each page's raw body.
    """
    out: list[dict[str, Any]] = []
    bodies: list[bytes] = []
    next_url: str | None = url
    query: Mapping[str, str] | None = params
    while next_url:
        response = get(client, next_url, query)
        bodies.append(response.content)
        page = response.json()
        out += page.get("features", [])
        next_url = next((link["href"] for link in page.get("links", [])
                         if link.get("rel") == "next"), None)  # fmt: skip
        query = None  # the next link carries the query
    return out, bodies


def river_group(name: str) -> str:
    """The river a site name names (``Mississippi River at Memphis, TN`` -> ``MISSISSIPPI``).

    Args:
        name: The monitoring location's name.

    Returns:
        Upper-case river name; abbreviations (``MISS R``) expanded.
    """
    upper = re.sub(r"\s+", " ", name.upper()).strip()
    match = re.match(r"^(.*?)\s+(?:RIVER|R)\b", upper)
    river = (match.group(1) if match else upper.split(" AT ")[0]).strip()
    return ABBREVIATIONS.get(river, river)


@dataclass(frozen=True)
class Reading:
    """One continuous value."""

    time: datetime
    value: float
    approval: str
    qualified: bool


def parse_readings(rows: Sequence[Mapping[str, Any]]) -> list[Reading]:
    """Readings from ``continuous`` features' properties.

    Args:
        rows: Feature properties (``time``, ``value``, ``approval_status``, ``qualifier``).

    Returns:
        Readings with a numeric value.
    """
    out = []
    for p in rows:
        try:
            value = float(p.get("value"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if not math.isfinite(value):
            continue
        approval = str(p.get("approval_status") or "")
        when = datetime.fromisoformat(str(p["time"]))
        out.append(Reading(when, value, approval, bool(p.get("qualifier"))))
    return out


def overpass_value(readings: Sequence[Reading], when: datetime, median_minutes: int,
                   nearest_minutes: int, approval: str = "Approved",
                   exclude_qualified: bool = True) -> tuple[float, str, int]:  # fmt: skip
    """The preregistered value at an overpass.

    The median of approved, unqualified values within ``median_minutes``; else the nearest such
    value within ``nearest_minutes``; else none.

    Args:
        readings: The site's readings around the overpass.
        when: Acquisition time (aware).
        median_minutes: Half-width of the median window.
        nearest_minutes: Half-width of the nearest-value window.
        approval: Required approval status.
        exclude_qualified: Drop qualified values.

    Returns:
        ``(value, rule, n)``: NaN and ``none`` when nothing qualifies.
    """
    ok = [r for r in readings
          if r.approval == approval and not (exclude_qualified and r.qualified)]  # fmt: skip
    near = [r for r in ok if abs(r.time - when) <= timedelta(minutes=median_minutes)]
    if near:
        values = sorted(r.value for r in near)
        mid = len(values) // 2
        median = values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2
        return median, f"median {median_minutes} min", len(near)
    within = [r for r in ok if abs(r.time - when) <= timedelta(minutes=nearest_minutes)]
    if within:
        best = min(within, key=lambda r: (abs(r.time - when), r.time))
        return best.value, f"nearest {nearest_minutes} min", 1
    return math.nan, "none", 0


def continuous(client: httpx.Client, api: str, site: str, parameter: str, start: datetime,
               end: datetime) -> tuple[list[Reading], list[bytes]]:  # fmt: skip
    """Continuous values of one site between two times.

    Args:
        client: HTTP client.
        api: OGC API root.
        site: E.g. ``USGS-07374000``.
        parameter: E.g. ``63680``.
        start: First time (aware).
        end: Last time (aware).

    Returns:
        The readings and the raw page bodies.
    """
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    params = {
        "monitoring_location_id": site, "parameter_code": parameter, "f": "json",
        "datetime": f"{start.strftime(stamp)}/{end.strftime(stamp)}", "limit": "1000",
        "skipGeometry": "true", "properties": "time,value,approval_status,qualifier",
    }  # fmt: skip
    _, bodies = features(client, f"{api}/collections/continuous/items", params)
    return readings_from_bodies(bodies), bodies


def continuous_many(client: httpx.Client, api: str, site: str, parameter: str,
                    windows: Sequence[tuple[datetime, datetime]]
                    ) -> tuple[list[Reading], list[bytes]]:  # fmt: skip
    """Continuous values of one site in several time windows, in one query.

    The windows are joined in a CQL2 filter (``time`` between each start and end, ORed), so the
    API's hourly quota (1,000 requests without a key) covers many overpasses per request. Every
    reading of every window comes back; the caller picks each overpass's own.

    Args:
        client: HTTP client.
        api: OGC API root.
        site: E.g. ``USGS-07374000``.
        parameter: E.g. ``63680``.
        windows: ``(start, end)`` pairs (aware).

    Returns:
        The readings and the raw page bodies.
    """
    stamp = "%Y-%m-%dT%H:%M:%SZ"
    clauses = " OR ".join(
        f"(time >= TIMESTAMP('{a.astimezone(UTC).strftime(stamp)}') AND "
        f"time <= TIMESTAMP('{b.astimezone(UTC).strftime(stamp)}'))"
        for a, b in windows
    )
    params = {
        "monitoring_location_id": site, "parameter_code": parameter, "f": "json",
        "filter": clauses, "filter-lang": "cql2-text", "limit": "1000", "skipGeometry": "true",
        "properties": "time,value,approval_status,qualifier",
    }  # fmt: skip
    _, bodies = features(client, f"{api}/collections/continuous/items", params)
    return readings_from_bodies(bodies), bodies


def readings_from_bodies(bodies: Sequence[bytes]) -> list[Reading]:
    """The readings of ``continuous`` pages (fresh or cached).

    Args:
        bodies: The raw page bodies.

    Returns:
        Readings with a numeric value.
    """
    return parse_readings([f.get("properties", {}) for body in bodies
                           for f in json.loads(body).get("features", [])])  # fmt: skip


def samples(client: httpx.Client, site: str, parameter: str, start: str, end: str) -> bytes:
    """Discrete sample results of one site (the samples-data API, narrow CSV).

    Args:
        client: HTTP client.
        site: E.g. ``USGS-07374000``.
        parameter: E.g. ``80154`` (suspended-sediment concentration).
        start: First date (ISO).
        end: Last date (ISO).

    Returns:
        The CSV body.
    """
    params = {"monitoringLocationIdentifier": site, "usgsPCode": parameter,
              "activityStartDateLower": start, "activityStartDateUpper": end,
              "mimeType": "text/csv"}  # fmt: skip
    return get(client, SAMPLES, params).content


def parse_samples(body: bytes) -> list[dict[str, str]]:
    """The rows a matchup needs from a samples CSV.

    Args:
        body: The CSV body.

    Returns:
        ``date``, ``time``, ``zone``, ``value``, ``unit``, ``status`` per result with a value.
    """
    out = []
    for row in csv.DictReader(io.StringIO(body.decode("utf-8", errors="replace"))):
        value = row.get("Result_Measure", "")
        if not value:
            continue
        out.append({"date": row.get("Activity_StartDate", ""),
                    "time": row.get("Activity_StartTime", ""),
                    "zone": row.get("Activity_StartTimeZone", ""), "value": value,
                    "unit": row.get("Result_MeasureUnit", ""),
                    "status": row.get("Result_MeasureStatusIdentifier", "")})  # fmt: skip
    return out
