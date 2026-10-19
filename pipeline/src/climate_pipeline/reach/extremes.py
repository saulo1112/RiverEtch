"""Extreme days of a demo reach's gauge record (rule v1: docs/water-quality/prospective.md, 5).

They are counted from the gauge's own daily record (the ``reach climate`` snapshot), never from
satellite values:

* **low-flow day**: a daily mean discharge at or below the 10th percentile of the gauge's approved
  daily means from its first day to 2025-12-31;
* **high-flow day**: at or above the 90th percentile of the same days;
* **warm-water day**: a June-September daily mean water temperature at or above the 90th
  percentile of the approved June-September daily means from 2002 to 2025 (only where the gauge
  measures temperature).

Per calendar year: the count of each kind, its rank among the years the climate context ranks
(most first; the year of the last value is shown to date and never ranked), and how many of those
days the satellite saw (a usable pass that day: for 2019-2025 a gauge-matched scene of the v5
inputs, for 2026 a sealed record with a value). And the lock box's pairs on each kind of day,
beside the 20 an error comparison needs. No error is computed here.
"""

from __future__ import annotations

import csv
import io
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from climate_pipeline.reach import climate as ctx

RULE = "docs/water-quality/prospective.md"
REFERENCE_LAST = date(2025, 12, 31)
WARM_FIRST_YEAR = 2002
LOW_QUANTILE, HIGH_QUANTILE = 0.1, 0.9
V5_YEARS = (2019, 2025)  # the satellite years of the v5 inputs (first, last)
RECORDS_FROM = 2026  # from this year, the reach's sealed records
MIN_PAIRS = 20  # the levels' minimum (preregistration v5)
V5_INPUTS = Path("docs/water-quality/inputs/usgs-v5/turbidity.csv")


@dataclass(frozen=True)
class Thresholds:
    """The three thresholds, in the gauge's published units (ft³/s, °C)."""

    low: float
    high: float
    warm: float | None
    flow_days: int
    warm_days: int


def one_per_day(snapshot: Mapping[str, Sequence[ctx.Daily]]) -> dict[str, list[ctx.Daily]]:
    """The snapshot with one value per day and parameter: a day counts once.

    A gauge can publish two overlapping series (the Platte's temperature, June-July 2007): such a
    day takes the mean of its values, provisional if any of them is.

    Args:
        snapshot: The gauge's daily values per parameter.

    Returns:
        The same, one value per day, in day order.
    """
    out: dict[str, list[ctx.Daily]] = {}
    for parameter, values in snapshot.items():
        by_day: dict[date, list[ctx.Daily]] = {}
        for d in values:
            by_day.setdefault(d.day, []).append(d)
        out[parameter] = [ctx.Daily(day, sum(d.value for d in ds) / len(ds),
                                    any(d.provisional for d in ds))
                          for day, ds in sorted(by_day.items())]  # fmt: skip
    return out


def quantile(values: Sequence[float], q: float) -> float:
    """A quantile by linear interpolation between order statistics (NumPy's default).

    Args:
        values: The sample (not empty).
        q: The probability, 0-1.

    Returns:
        The quantile.
    """
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = math.floor(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def thresholds(snapshot: Mapping[str, Sequence[ctx.Daily]]) -> Thresholds:
    """The thresholds from the approved days of the reference periods.

    Args:
        snapshot: The gauge's daily values per parameter.

    Returns:
        The thresholds (``warm`` None where the gauge has no summer temperature).
    """
    flow = [d.value for d in snapshot.get(ctx.DISCHARGE, [])
            if not d.provisional and d.day <= REFERENCE_LAST]  # fmt: skip
    warm = [d.value for d in snapshot.get(ctx.TEMPERATURE, [])
            if not d.provisional and d.day.month in ctx.SUMMER
            and WARM_FIRST_YEAR <= d.day.year <= REFERENCE_LAST.year]  # fmt: skip
    return Thresholds(quantile(flow, LOW_QUANTILE), quantile(flow, HIGH_QUANTILE),
                      quantile(warm, HIGH_QUANTILE) if warm else None, len(flow),
                      len(warm))  # fmt: skip


def kinds_by_day(snapshot: Mapping[str, Sequence[ctx.Daily]], t: Thresholds
                 ) -> dict[date, set[str]]:  # fmt: skip
    """Each extreme day and its kinds ("low", "high", "warm").

    Args:
        snapshot: The gauge's daily values per parameter.
        t: The thresholds.

    Returns:
        ``day -> kinds`` (a day absent is not extreme).
    """
    out: dict[date, set[str]] = {}
    for d in snapshot.get(ctx.DISCHARGE, []):
        if d.value <= t.low:
            out.setdefault(d.day, set()).add("low")
        if d.value >= t.high:
            out.setdefault(d.day, set()).add("high")
    if t.warm is not None:
        for d in snapshot.get(ctx.TEMPERATURE, []):
            if d.day.month in ctx.SUMMER and d.value >= t.warm:
                out.setdefault(d.day, set()).add("warm")
    return out


def _v5_rows(root: Path, station: str) -> list[dict[str, str]]:
    text = (root / V5_INPUTS).read_text(encoding="utf-8")
    return [r for r in csv.DictReader(io.StringIO(text)) if r["site_id"] == station]


def satellite_days(root: Path, site_id: str, station: str) -> set[date]:
    """The days the reach has a usable pass: v5 inputs for 2019-2025, sealed records from 2026.

    Args:
        root: Repository root.
        site_id: The reach.
        station: Its gauge, e.g. ``USGS-06805500``.

    Returns:
        The days (UTC dates of the passes).
    """
    v5 = {date.fromisoformat(r["datetime_utc"][:10]) for r in _v5_rows(root, station)}
    days = {d for d in v5 if V5_YEARS[0] <= d.year <= V5_YEARS[1]}
    series = root / "docs/water-quality/reach" / site_id / "examples" / "series.json"
    for row in json.loads(series.read_text(encoding="utf-8")):
        estimate = next((e for e in row["estimates"] if e["target"] == "turbidity"), None)
        day = date.fromisoformat(row["date"])
        if day.year >= RECORDS_FROM and estimate is not None and estimate.get("value") is not None:
            days.add(day)
    return days


def lockbox_days(root: Path, site_id: str, station: str) -> tuple[tuple[str, str], list[date]]:
    """The lock box's window (from the turbidity card) and the days of its pairs (v5 inputs).

    Args:
        root: Repository root.
        site_id: The reach.
        station: Its gauge.

    Returns:
        ``(first, last)`` and one day per pair.
    """
    card = root / "docs/water-quality/results/models" / site_id / "turbidity.json"
    first, last = json.loads(card.read_text(encoding="utf-8"))["lockbox"]
    days = [date.fromisoformat(r["datetime_utc"][:10]) for r in _v5_rows(root, station)
            if r["value"] != "" and first <= r["datetime_utc"][:10] <= last]  # fmt: skip
    return (first, last), days


def _seen(kind: str, days: Iterable[date], kinds: Mapping[date, set[str]], seen: set[date]
          ) -> int:  # fmt: skip
    return sum(1 for d in days if kind in kinds.get(d, ()) and d in seen)


def _source(year: int) -> str | None:
    if V5_YEARS[0] <= year <= V5_YEARS[1]:
        return "v5 inputs"
    return "sealed records" if year >= RECORDS_FROM else None


def summarise(snapshot: Mapping[str, Sequence[ctx.Daily]], doc: Mapping[str, Any],
              seen: Iterable[date], window: tuple[str, str], pairs: Sequence[date]
              ) -> dict[str, Any]:  # fmt: skip
    """The ``extremes`` block of ``climate.json``.

    Args:
        snapshot: The gauge's daily values per parameter.
        doc: The rest of ``climate.json`` (its years say which are complete).
        seen: The days with a usable pass (see ``satellite_days``).
        window: The lock box's first and last day.
        pairs: The days of the lock box's pairs.

    Returns:
        The thresholds, the years, the satellite era's totals and the lock box's counts.
    """
    snapshot = one_per_day(snapshot)
    t = thresholds(snapshot)
    kinds = kinds_by_day(snapshot, t)
    seen_days = set(seen)
    flow_years = {r["year"]: r for r in doc["discharge"]["years"]}
    heat = doc.get("temperature")
    heat_years = {r["year"]: r for r in heat["years"]} if heat else {}
    flow_by_year: dict[int, list[date]] = {}
    for d in snapshot.get(ctx.DISCHARGE, []):
        flow_by_year.setdefault(d.day.year, []).append(d.day)
    summer_by_year: dict[int, list[date]] = {}
    for d in snapshot.get(ctx.TEMPERATURE, []):
        if d.day.month in ctx.SUMMER:
            summer_by_year.setdefault(d.day.year, []).append(d.day)
    rows: list[dict[str, Any]] = []
    for year in sorted(flow_by_year):
        days = flow_by_year[year]
        summer = summer_by_year.get(year)
        source = _source(year)
        count = {k: sum(1 for d in days if k in kinds.get(d, ())) for k in ("low", "high")}
        warm = None if summer is None or t.warm is None else sum(
            1 for d in summer if "warm" in kinds.get(d, ()))  # fmt: skip

        rows.append({
            "year": year, "complete": flow_years[year]["complete"],
            "toDate": flow_years[year]["toDate"], "low": count["low"], "high": count["high"],
            "warm": warm,
            "warmComplete": bool(heat_years.get(year, {}).get("complete", False)),
            "seenFrom": source,
            "passes": None if source is None else sum(1 for d in seen_days if d.year == year),
            "lowSeen": None if source is None else _seen("low", days, kinds, seen_days),
            "highSeen": None if source is None else _seen("high", days, kinds, seen_days),
            "warmSeen": None if source is None or warm is None or summer is None
            else _seen("warm", summer, kinds, seen_days),
        })  # fmt: skip
    for kind, complete in (("low", "complete"), ("high", "complete"), ("warm", "warmComplete")):
        counts = {r["year"]: r[kind] for r in rows if r[complete] and r[kind] is not None}
        ranks = ctx._ranks(counts, highest_first=True)
        for r in rows:
            r[f"{kind}Rank"] = ranks.get(r["year"])
    era = [d for year, ds in flow_by_year.items() if V5_YEARS[0] <= year <= V5_YEARS[1] for d in ds]
    era_summer = [d for year, ds in summer_by_year.items()
                  if V5_YEARS[0] <= year <= V5_YEARS[1] for d in ds]  # fmt: skip

    def total(of: Sequence[date], kind: str | None) -> dict[str, int]:
        match = [d for d in of if (not kinds.get(d) if kind is None else kind in kinds.get(d, ()))]
        return {"days": len(match), "seen": sum(1 for d in match if d in seen_days)}

    lock = {k: sum(1 for d in pairs if k in kinds.get(d, ())) for k in ("low", "high", "warm")}
    return {
        "rule": RULE,
        "thresholds": {
            "low": round(t.low * ctx.FT3_TO_M3, 1), "high": round(t.high * ctx.FT3_TO_M3, 1),
            "warm": None if t.warm is None else round(t.warm, 1),
            "flowUnit": "m³/s", "warmUnit": "°C",
            "reference": {"first": doc["discharge"]["first"], "last": REFERENCE_LAST.isoformat(),
                          "warmFirstYear": WARM_FIRST_YEAR, "flowDays": t.flow_days,
                          "warmDays": t.warm_days},
        },
        "years": rows,
        "rankedYears": {"flow": sum(1 for r in rows if r["complete"]),
                        "warm": sum(1 for r in rows if r["warmComplete"])},
        "satelliteEra": {
            "first": V5_YEARS[0], "last": V5_YEARS[1],
            "low": total(era, "low"), "high": total(era, "high"), "normal": total(era, None),
            "warm": None if t.warm is None else total(era_summer, "warm"),
        },
        "lockbox": {"first": window[0], "last": window[1], "pairs": len(pairs),
                    "low": lock["low"], "high": lock["high"],
                    "warm": None if t.warm is None else lock["warm"], "minimum": MIN_PAIRS},
    }  # fmt: skip


def document(root: Path, site_id: str, station: str,
             snapshot: Mapping[str, Sequence[ctx.Daily]], doc: Mapping[str, Any]
             ) -> dict[str, Any]:  # fmt: skip
    """The ``extremes`` block of a demo reach, from the committed files.

    Args:
        root: Repository root.
        site_id: The reach.
        station: Its gauge.
        snapshot: The gauge's daily values per parameter.
        doc: The rest of ``climate.json``.

    Returns:
        The block.
    """
    window, pairs = lockbox_days(root, site_id, station)
    return summarise(snapshot, doc, satellite_days(root, site_id, station), window, pairs)
