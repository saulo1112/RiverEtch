"""Network snapshots of every raw input, each recorded with URL, status, bytes, SHA-256 and time.

Snapshots are written under the calibration's ``inputs`` folder and committed, so the analysis
reruns offline. Long IDEAM series are committed as the verbatim header plus the lines inside the
period; the full file's SHA-256 and size stay in the manifest. Nothing here interprets a value.
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
import math
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

log = logging.getLogger(__name__)
ACOLITE_FILES = (
    "data/Shared/algorithms/Nechad/Nechad_calibration_201609.txt",
    "data/Shared/algorithms/Dogliotti/defaults.txt",
)
ACOLITE_COMMIT = "ca477dd91dfb5f8eb77333824b38cb0bcce5e083"  # pinned 2026-10-09, before any run


@dataclass(frozen=True)
class Snapshot:
    """One fetched input."""

    path: str  # relative to the inputs folder
    url: str
    status: int
    bytes: int
    sha256: str
    fetched_utc: str
    note: str = ""


@dataclass
class Recorder:
    """Writes snapshots and keeps the fetch manifest."""

    root: Path
    records: list[Snapshot] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def save(self, relative: str, body: bytes, url: str, status: int = 200, note: str = "") -> Path:
        """Write a snapshot and record it.

        Args:
            relative: Path inside the inputs folder.
            body: Bytes to write (as fetched, or the stated subset).
            url: Where it came from.
            status: HTTP status.
            note: E.g. how the body relates to the full response.

        Returns:
            The written file.
        """
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        self.records.append(
            Snapshot(
                relative, url, status, len(body), hashlib.sha256(body).hexdigest(),
                datetime.now(UTC).isoformat(timespec="seconds"), note,
            )
        )  # fmt: skip
        return path

    def fail(self, url: str, error: object) -> None:
        """Record an input that could not be fetched.

        Args:
            url: The address.
            error: What went wrong.
        """
        self.failures.append(f"{url}: {error}")
        self.records.append(
            Snapshot("", url, 0, 0, "", datetime.now(UTC).isoformat(timespec="seconds"),
                     f"failed: {error}")
        )  # fmt: skip

    def manifest(self) -> str:
        """The fetch manifest as CSV text (sorted by path, then URL).

        Returns:
            CSV with LF line ends.
        """
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["path", "url", "status", "bytes", "sha256", "fetched_utc", "note"])
        for r in sorted(self.records, key=lambda r: (r.path, r.url)):
            writer.writerow([r.path, r.url, r.status, r.bytes, r.sha256, r.fetched_utc, r.note])
        return out.getvalue()


def get(http: httpx.Client, url: str, params: dict[str, str] | None = None) -> bytes:
    """GET with one retry; raises on an HTTP error.

    Args:
        http: Client.
        url: Address.
        params: Query parameters.

    Returns:
        The body.
    """
    for attempt in range(2):
        try:
            response = http.get(url, params=params)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError:
            if attempt == 1:
                raise
    raise AssertionError("unreachable")


def period_lines(body: bytes, start: date, end: date) -> bytes:
    """The header and the lines whose first field's date lies in the period, verbatim.

    Args:
        body: An IDEAM series CSV (``fechaObservacion,valorObservado,nivelAprobacion``).
        start: First day.
        end: Last day.

    Returns:
        The subset, byte for byte (line ends kept).
    """
    lines = body.splitlines(keepends=True)
    if not lines:
        return body
    kept = [lines[0]]
    for line in lines[1:]:
        try:
            day = date.fromisoformat(line.split(b",", 1)[0].decode()[:10])
        except ValueError:
            continue
        if start <= day <= end:
            kept.append(line)
    return b"".join(kept)


def quality_samples(
    http: httpx.Client, url: str, points: Sequence[str], variables: Sequence[str], since: str
) -> tuple[bytes, str]:
    """Raw water-quality rows of the selected points (SODA JSON).

    Args:
        http: Client.
        url: The SODA resource.
        points: Exact point names.
        variables: Observed properties.
        since: First date (ISO).

    Returns:
        The response body and the full request URL.
    """
    names = ", ".join("'" + p.replace("'", "''") + "'" for p in points)
    props = ", ".join(f"'{v}'" for v in variables)
    params = {
        "$select": "nombre_del_punto_de_monitoreo, fecha, propiedad_observada, resultado, "
        "unidad_del_resultado",
        "$where": f"nombre_del_punto_de_monitoreo in ({names}) AND propiedad_observada in "
        f"({props}) AND fecha >= '{since}'",
        "$order": "nombre_del_punto_de_monitoreo, fecha, propiedad_observada, resultado",
        "$limit": "50000",
    }
    request = http.build_request("GET", url, params=params)
    return get(http, url, params), str(request.url)


def open_meteo_daily(
    http: httpx.Client, url: str, lon: float, lat: float, start: date, end: date
) -> tuple[bytes, str]:
    """Daily precipitation sums (local days, America/Bogota) at one point.

    Args:
        http: Client.
        url: Open-Meteo archive endpoint.
        lon: Longitude.
        lat: Latitude.
        start: First day.
        end: Last day.

    Returns:
        The JSON body and the request URL.
    """
    params = {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": start.isoformat(),
        "end_date": end.isoformat(), "daily": "precipitation_sum",
        "timezone": "America/Bogota", "precipitation_unit": "mm",
    }  # fmt: skip
    request = http.build_request("GET", url, params=params)
    return get(http, url, params), str(request.url)


def chirps_days(
    template: str,
    points: Sequence[tuple[str, float, float]],
    start: date,
    end: date,
    sample: Callable[[str, list[tuple[float, float]]], list[float]],
    workers: int,
) -> tuple[list[dict[str, object]], list[str]]:
    """CHIRPS daily rain at the grid points, one COG per day.

    Args:
        template: URL template with ``{year}`` and ``{date}`` (``YYYY.MM.DD``).
        points: ``(id, lon, lat)``.
        start: First day.
        end: Last day.
        sample: Point reader (``screening.rio.sample_points``; injectable for tests).
        workers: Parallel reads.

    Returns:
        One row per day (point id -> mm, NaN when unreadable) and the days that failed.
    """
    days = [start + timedelta(days=k) for k in range((end - start).days + 1)]
    lonlats = [(lon, lat) for _, lon, lat in points]

    def one(day: date) -> tuple[date, list[float] | None]:
        url = template.format(year=day.year, date=day.strftime("%Y.%m.%d"))
        try:
            return day, sample(url, lonlats)
        except Exception as error:  # unreadable day: recorded, never guessed
            log.warning("CHIRPS %s: %s", day, error)
            return day, None

    rows, failed = [], []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for day, values in pool.map(one, days):
            if values is None:
                failed.append(day.isoformat())
                values = [math.nan] * len(points)
            rows.append(
                {"date": day.isoformat(), **{p[0]: v for p, v in zip(points, values, strict=True)}}
            )
    return rows, failed


def acolite_file_url(path: str, commit: str = ACOLITE_COMMIT) -> str:
    """Raw GitHub URL of an ACOLITE file at the pinned commit.

    Args:
        path: Path in the repository.
        commit: Commit SHA.

    Returns:
        The URL.
    """
    return f"https://raw.githubusercontent.com/acolite/acolite/{commit}/{path}"
