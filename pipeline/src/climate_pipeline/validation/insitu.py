"""In-situ comparison: open water-quality samples and river levels against NDTI.

Samples and levels come from open-data endpoints (Socrata), fetched once and cached; every response
is hashed. A sample is matched to the usable scene nearest in time within a fixed number of days;
a level is the mean of the observations within a fixed window around the acquisition. The reading
rule is fixed in the validation's settings: "tracks", "does not track", "inconclusive" or "not
enough data". NDTI is a relative index; none of this converts it to NTU or mg/L.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import numpy as np

from climate_pipeline.validation.config import InsituConfig, InsituStation

LOCAL = ZoneInfo("America/Bogota")


@dataclass(frozen=True)
class Sample:
    """One water-quality sample."""

    station: str
    day: date
    variable: str
    value: float
    unit: str
    censored: bool  # reported as below a detection limit ("<x")


@dataclass(frozen=True)
class SceneValue:
    """What a usable scene measured (NDTI per sub-reach and their mean, median red reflectance)."""

    key: str
    when: datetime
    ndti_upstream: float
    ndti_downstream: float
    red_upstream: float
    red_downstream: float

    @property
    def ndti_reach(self) -> float:
        """Mean of the sub-reaches that were measured."""
        values = [v for v in (self.ndti_upstream, self.ndti_downstream) if math.isfinite(v)]
        return float(np.mean(values)) if values else math.nan


def fetch_rows(
    http: httpx.Client, url: str, params: dict[str, str], cache_dir: Path | None
) -> tuple[list[dict[str, Any]], str]:
    """Rows of an open-data query, cached by query.

    Args:
        http: HTTP client.
        url: The resource endpoint.
        params: Query parameters.
        cache_dir: Cache folder (None disables caching).

    Returns:
        The rows and the SHA-256 of the response body.
    """
    key = hashlib.sha256(json.dumps([url, params], sort_keys=True).encode()).hexdigest()[:16]
    cache = cache_dir / f"insitu-{key}.json" if cache_dir else None
    if cache is not None and cache.exists():
        body = cache.read_bytes()
    else:
        response = http.get(url, params=params)
        response.raise_for_status()
        body = response.content
        if cache is not None:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(body)
    rows: list[dict[str, Any]] = json.loads(body)
    return rows, hashlib.sha256(body).hexdigest()


def _number(text: object) -> tuple[float, bool]:
    raw = str(text).strip().replace(",", ".")
    censored = raw.startswith("<")
    try:
        return float(raw.lstrip("<>").strip()), censored
    except ValueError:
        return math.nan, censored


def quality_samples(
    http: httpx.Client, cfg: InsituConfig, station: InsituStation, cache_dir: Path | None
) -> tuple[list[Sample], str]:
    """A station's samples of the configured variables, all dates.

    Args:
        http: HTTP client.
        cfg: In-situ settings.
        station: The station (its code appears in brackets in the point name).
        cache_dir: Cache folder.

    Returns:
        The samples with a numeric value, and the response hash.
    """
    variables = ", ".join(f"'{v}'" for v in cfg.quality_variables)
    params = {
        "$select": "nombre_del_punto_de_monitoreo, fecha, propiedad_observada, resultado, "
        "unidad_del_resultado",
        "$where": f"nombre_del_punto_de_monitoreo like '%{station.code}%' "
        f"AND propiedad_observada in ({variables})",
        "$order": "fecha",
        "$limit": "5000",
    }
    rows, digest = fetch_rows(http, cfg.quality_resource, params, cache_dir)
    samples = []
    for row in rows:
        value, censored = _number(row.get("resultado", ""))
        if not math.isfinite(value):
            continue
        day = datetime.fromisoformat(str(row["fecha"])[:19]).date()
        samples.append(
            Sample(station.code, day, str(row["propiedad_observada"]), value,
                   str(row.get("unidad_del_resultado", "")), censored)
        )  # fmt: skip
    return samples, digest


def level_series(
    http: httpx.Client,
    cfg: InsituConfig,
    station: InsituStation,
    start: date,
    end: date,
    cache_dir: Path | None,
) -> tuple[list[tuple[datetime, float]], str, str]:
    """A station's instantaneous river levels in a period (local times, read as America/Bogota).

    Args:
        http: HTTP client.
        cfg: In-situ settings.
        station: The station.
        start: First day.
        end: Last day.
        cache_dir: Cache folder.

    Returns:
        ``(moment, level)`` pairs, the unit, and the response hash.
    """
    params = {
        "$select": "fechaobservacion, valorobservado, unidadmedida",
        "$where": f"codigoestacion = '{station.code}' AND fechaobservacion between "
        f"'{start.isoformat()}T00:00:00' and '{end.isoformat()}T23:59:59'",
        "$order": "fechaobservacion",
        "$limit": "100000",
    }
    rows, digest = fetch_rows(http, cfg.level_resource, params, cache_dir)
    series = []
    unit = ""
    for row in rows:
        value, _ = _number(row.get("valorobservado", ""))
        if not math.isfinite(value):
            continue
        moment = datetime.fromisoformat(str(row["fechaobservacion"])[:19]).replace(tzinfo=LOCAL)
        series.append((moment, value))
        unit = str(row.get("unidadmedida", unit))
    return series, unit, digest


def level_at(
    series: Sequence[tuple[datetime, float]], moment: datetime, window_h: float, min_obs: int
) -> float:
    """Mean level within ``window_h`` hours of a moment (NaN with fewer than ``min_obs``).

    Args:
        series: ``(moment, level)`` pairs.
        moment: The acquisition time.
        window_h: Half-width of the window, hours.
        min_obs: Fewest observations accepted.

    Returns:
        The level.
    """
    span = timedelta(hours=window_h)
    values = [v for t, v in series if abs(t - moment) <= span]
    return float(np.mean(values)) if len(values) >= min_obs else math.nan


# ----------------------------------------------------------------------------------------------
# Statistics
# ----------------------------------------------------------------------------------------------


def _ranks(x: np.ndarray) -> np.ndarray:
    order = np.argsort(x, kind="mergesort")
    ranks = np.empty(len(x), dtype=np.float64)
    ranks[order] = np.arange(1, len(x) + 1, dtype=np.float64)
    for value in np.unique(x):
        tied = x == value
        if tied.sum() > 1:
            ranks[tied] = ranks[tied].mean()
    return ranks


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    """Spearman's rank correlation (average ranks for ties).

    Args:
        x: Values.
        y: Paired values.

    Returns:
        rho, NaN with fewer than three pairs or a constant series.
    """
    a, b = np.array(x, dtype=np.float64), np.array(y, dtype=np.float64)
    if len(a) < 3:
        return math.nan
    ra, rb = _ranks(a), _ranks(b)
    if ra.std() == 0 or rb.std() == 0:
        return math.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def bootstrap_interval(
    x: Sequence[float], y: Sequence[float], resamples: int, seed: int
) -> tuple[float, float]:
    """95 % percentile bootstrap interval of Spearman's rho (pairs resampled together).

    Args:
        x: Values.
        y: Paired values.
        resamples: Bootstrap resamples.
        seed: Random seed.

    Returns:
        ``(low, high)``, NaN when it cannot be computed.
    """
    n = len(x)
    if n < 3:
        return math.nan, math.nan
    rng = random.Random(seed)
    values = []
    for _ in range(resamples):
        idx = [rng.randrange(n) for _ in range(n)]
        rho = spearman([x[i] for i in idx], [y[i] for i in idx])
        if math.isfinite(rho):
            values.append(rho)
    if not values:
        return math.nan, math.nan
    return float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))


def reading(n: int, rho: float, low: float, high: float, cfg: InsituConfig) -> str:
    """The pre-registered reading of a comparison.

    Args:
        n: Pairs.
        rho: Spearman's rho.
        low: Interval low end.
        high: Interval high end.
        cfg: Minimum pairs and the rho a series must reach to "track".

    Returns:
        "not enough data", "tracks", "does not track" or "inconclusive".
    """
    if n < cfg.min_pairs or not math.isfinite(rho):
        return "not enough data"
    if rho >= cfg.tracks_rho and low > 0:
        return "tracks"
    if high < cfg.tracks_rho:
        return "does not track"
    return "inconclusive"


def compare(
    label: str, x: Sequence[float], y: Sequence[float], cfg: InsituConfig
) -> dict[str, object]:
    """One comparison row: n, rho, interval and reading.

    Args:
        label: What is compared.
        x: NDTI values.
        y: The paired in-situ values.
        cfg: In-situ settings.

    Returns:
        The row.
    """
    pairs = [(a, b) for a, b in zip(x, y, strict=True) if math.isfinite(a) and math.isfinite(b)]
    xs, ys = [p[0] for p in pairs], [p[1] for p in pairs]
    rho = spearman(xs, ys)
    low, high = bootstrap_interval(xs, ys, cfg.bootstrap, cfg.seed)
    return {
        "comparison": label,
        "pairs": len(pairs),
        "spearman": round(rho, 3) if math.isfinite(rho) else math.nan,
        "ci_low": round(low, 3) if math.isfinite(low) else math.nan,
        "ci_high": round(high, 3) if math.isfinite(high) else math.nan,
        "reading": reading(len(pairs), rho, low, high, cfg),
    }


def match_samples(
    samples: Sequence[Sample], scenes: Sequence[SceneValue], max_days: int
) -> list[tuple[Sample, SceneValue, int]]:
    """Each sample with the usable scene nearest in time within ``max_days`` (ties: earlier scene).

    Args:
        samples: Samples.
        scenes: Usable scenes.
        max_days: Largest gap in days.

    Returns:
        ``(sample, scene, gap_days)``.
    """
    out = []
    for sample in samples:
        best = None
        for scene in scenes:
            gap = abs((scene.when.astimezone(LOCAL).date() - sample.day).days)
            if gap <= max_days and (best is None or gap < best[1]):
                best = (scene, gap)
        if best is not None:
            out.append((sample, best[0], best[1]))
    return out


def saturation_rows(scenes: Sequence[SceneValue], cfg: InsituConfig) -> list[dict[str, object]]:
    """Does NDTI keep responding at high red reflectance? Spearman in the lower and upper halves.

    Args:
        scenes: Usable scenes.
        cfg: The rho a half must reach to count as responding.

    Returns:
        One row per sub-reach, with the reading.
    """
    rows: list[dict[str, object]] = []
    for name in ("upstream", "downstream"):
        pairs = [
            (getattr(s, f"red_{name}"), getattr(s, f"ndti_{name}"))
            for s in scenes
            if math.isfinite(getattr(s, f"red_{name}"))
            and math.isfinite(getattr(s, f"ndti_{name}"))
        ]
        if len(pairs) < 2 * cfg.min_pairs:
            rows.append({"subreach": name, "scenes": len(pairs), "reading": "not enough data"})
            continue
        pairs.sort()
        half = len(pairs) // 2
        lower, upper = pairs[:half], pairs[half:]
        rho_low = spearman([p[0] for p in lower], [p[1] for p in lower])
        rho_high = spearman([p[0] for p in upper], [p[1] for p in upper])
        if rho_high >= cfg.saturation_rho:
            text = "responds across the range"
        elif rho_low >= cfg.saturation_rho:
            text = "flattens at high red reflectance"
        else:
            text = "weak relation in both halves"
        rows.append(
            {
                "subreach": name,
                "scenes": len(pairs),
                "red_median_split": round(upper[0][0], 4),
                "red_min": round(pairs[0][0], 4),
                "red_max": round(pairs[-1][0], 4),
                "ndti_min": round(min(p[1] for p in pairs), 4),
                "ndti_max": round(max(p[1] for p in pairs), 4),
                "spearman_lower_half": round(rho_low, 3),
                "spearman_upper_half": round(rho_high, 3),
                "spearman_all": round(spearman([p[0] for p in pairs], [p[1] for p in pairs]), 3),
                "reading": text,
            }
        )
    return rows


def percentile_rank(values: Sequence[float], value: float) -> float:
    """The share of values at or below ``value`` (0-1), NaN when either is missing.

    Args:
        values: Reference values.
        value: The value.

    Returns:
        The rank.
    """
    finite = [v for v in values if math.isfinite(v)]
    if not finite or not math.isfinite(value):
        return math.nan
    return sum(1 for v in finite if v <= value) / len(finite)
