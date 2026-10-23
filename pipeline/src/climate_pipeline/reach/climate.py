"""A reach's gauge record, year by year: the climate context of its passes (never an estimate).

``reach climate`` fetches the estimate station's daily mean discharge, and its daily mean water
temperature where the gauge measures it, for the whole period of record from the USGS OGC API. It
keeps them as a snapshot (``docs/water-quality/reach/<site>/climate/daily.csv``) and writes
``climate.json`` beside the reach's examples for the web. Per calendar year:

* **peak**: the highest daily mean discharge, and its day;
* **7-day low**: the lowest mean of 7 consecutive days inside the year (all seven measured), and
  the last of those days;
* **warmest**: the highest daily mean water temperature, and its day.

A year is ranked when at least 90 % of its days have a discharge (for the temperature, 90 % of the
days from June to September). The year of the last value is shown to date and never ranked. A year
with a provisional value is labelled. For the demo reaches it also counts each year's extreme days
(low-flow, high-flow, warm-water) as rule v1 defines them (``reach/extremes.py``). These are the
gauge's own measurements: nothing here comes from a satellite, and nothing states a trend or a
cause.

Once preregistration-daily-record.md is anchored it also writes the river's **usual flow** for each
calendar day (``discharge.typical``): over the complete years up to 2025, the values from 3 days
before to 3 days after that day (29 February as 28 February), their median and their 10th and 90th
percentiles; and the **latest day** against it (``discharge.latest``): its flow and the share of
those values that were higher.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.sources import usgs

DISCHARGE, TEMPERATURE = "00060", "00010"
FT3_TO_M3 = 0.028316846592  # (0.3048 m)³, exact
COVERAGE = 0.9  # share of a year's days (of June-September's for the temperature) to rank it
LOW_WINDOW = 7
SUMMER = (6, 7, 8, 9)
FIRST_DAY = "1800-01-01"  # before any USGS daily value
SNAPSHOT_COLUMNS = ("day", "parameter", "value", "approval")
# The usual flow (preregistration-daily-record.md, section 4): reference years up to this one, a
# window of this many days on each side of the day, and the percentiles of the usual range.
REFERENCE_LAST = 2025
BAND_HALF_DAYS = 3
BAND_PERCENTILES = (10.0, 50.0, 90.0)
LEAP = 2000  # a leap year: its 366 days index the calendar days (29 February is index 59)
# A flood model's daily flow, already in m³/s (GloFAS v4 through the Open-Meteo flood API).
MODELLED = "river_discharge"
MODELLED_APPROVAL = "Modelled"
GLOFAS_API = "https://flood-api.open-meteo.com/v1/flood"
GLOFAS_FIRST_DAY = "1984-01-01"  # GloFAS v4's first day (Open-Meteo flood API documentation)
GLOFAS_SOURCE = (
    "GloFAS v4 river discharge (Global Flood Awareness System, Copernicus Emergency Management "
    "Service), through the Open-Meteo flood API: modelled, not measured"
)


@dataclass(frozen=True)
class Daily:
    """One daily mean value of the gauge."""

    day: date
    value: float
    provisional: bool


def fetch(client: httpx.Client, api: str, station: str, until: date) -> list[dict[str, Any]]:
    """The station's daily mean discharge and water temperature over its period of record.

    Args:
        client: HTTP client.
        api: OGC API root.
        station: E.g. ``USGS-06805500``.
        until: Last day.

    Returns:
        Snapshot rows (``day``, ``parameter``, ``value`` in ft³/s or °C, ``approval``), sorted.
    """
    rows = []
    for parameter in (DISCHARGE, TEMPERATURE):
        readings, _ = usgs.daily(client, api, station, parameter, FIRST_DAY, until.isoformat())
        rows += [{"day": r.time.date().isoformat(), "parameter": parameter, "value": r.value,
                  "approval": r.approval} for r in readings]  # fmt: skip
    return sorted(rows, key=lambda r: (r["parameter"], r["day"]))


def fetch_modelled(client: httpx.Client, lat: float, lon: float, until: date
                   ) -> list[dict[str, Any]]:  # fmt: skip
    """A GloFAS cell's daily river discharge (m³/s) from 1984, through the Open-Meteo flood API.

    Args:
        client: HTTP client.
        lat: The cell's latitude.
        lon: The cell's longitude.
        until: Last day.

    Returns:
        Snapshot rows (``parameter`` "river_discharge", ``approval`` "Modelled"), sorted.

    Raises:
        ReachError: When the API answers with no daily values.
    """
    response = client.get(GLOFAS_API, params={
        "latitude": lat, "longitude": lon, "daily": "river_discharge",
        "start_date": GLOFAS_FIRST_DAY, "end_date": until.isoformat(),
        "cell_selection": "nearest",
    })  # fmt: skip
    response.raise_for_status()
    daily = response.json().get("daily") or {}
    days, values = daily.get("time") or [], daily.get("river_discharge") or []
    if not days:
        raise reach_run.ReachError(f"GloFAS at {lat}, {lon}: no daily values")
    return [{"day": d, "parameter": MODELLED, "value": v, "approval": MODELLED_APPROVAL}
            for d, v in zip(days, values, strict=True) if v is not None]  # fmt: skip


def write_snapshot(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    """The fetched values, one row per day and parameter (LF line ends).

    Args:
        path: The CSV.
        rows: Snapshot rows.
    """
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(SNAPSHOT_COLUMNS)
    for r in rows:
        writer.writerow([r[c] for c in SNAPSHOT_COLUMNS])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(out.getvalue(), encoding="utf-8", newline="\n")


def read_snapshot(path: Path) -> dict[str, list[Daily]]:
    """A snapshot's values per parameter, in day order.

    Args:
        path: The CSV.

    Returns:
        ``parameter -> values``.
    """
    out: dict[str, list[Daily]] = {}
    for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))):
        provisional = r["approval"] not in ("Approved", MODELLED_APPROVAL)
        out.setdefault(r["parameter"], []).append(
            Daily(date.fromisoformat(r["day"]), float(r["value"]), provisional)
        )
    for values in out.values():
        values.sort(key=lambda d: d.day)
    return out


def _days_in(year: int, months: Sequence[int] | None = None) -> int:
    first, last = date(year, 1, 1), date(year, 12, 31)
    days = (last - first).days + 1
    if months is None:
        return days
    return sum(1 for k in range(days) if (first + timedelta(days=k)).month in months)


def _ranks(values: Mapping[int, float], highest_first: bool) -> dict[int, int]:
    # Competition ranking: a tie shares the better rank.
    sign = -1.0 if highest_first else 1.0
    return {y: 1 + sum(1 for w in values.values() if sign * w < sign * v)
            for y, v in values.items()}  # fmt: skip


def discharge_years(values: Sequence[Daily], through: date, factor: float = FT3_TO_M3
                    ) -> list[dict[str, Any]]:  # fmt: skip
    """Each calendar year's peak and 7-day low discharge (m³/s), ranked over the complete years.

    Args:
        values: Daily mean discharge (ft³/s as the USGS publishes it, or m³/s), in day order.
        through: The last day with a value: its year is shown to date, never ranked.
        factor: To m³/s (1 for a model's m³/s).

    Returns:
        One row per year with a value.
    """
    by_year: dict[int, dict[date, Daily]] = {}
    for d in values:
        by_year.setdefault(d.day.year, {})[d.day] = d
    rows: list[dict[str, Any]] = []
    for year, days in sorted(by_year.items()):
        peak = max(days.values(), key=lambda d: (d.value, -d.day.toordinal()))
        low: tuple[float, date] | None = None
        for first in sorted(days):
            window = [first + timedelta(days=k) for k in range(LOW_WINDOW)]
            if window[-1].year != year or any(w not in days for w in window):
                continue
            mean = sum(days[w].value for w in window) / LOW_WINDOW
            if low is None or mean < low[0]:
                low = (mean, window[-1])
        complete = year != through.year and len(days) >= COVERAGE * _days_in(year)
        rows.append({
            "year": year, "days": len(days), "complete": complete, "toDate": year == through.year,
            "provisional": any(d.provisional for d in days.values()),
            "peak": round(peak.value * factor, 1), "peakDay": peak.day.isoformat(),
            "low7": None if low is None else round(low[0] * factor, 1),
            "low7Day": None if low is None else low[1].isoformat(),
        })  # fmt: skip
    ranked = [r for r in rows if r["complete"]]
    peaks = _ranks({r["year"]: r["peak"] for r in ranked}, highest_first=True)
    lows = _ranks({r["year"]: r["low7"] for r in ranked if r["low7"] is not None}, False)
    for r in rows:
        r["peakRank"] = peaks.get(r["year"])
        r["low7Rank"] = lows.get(r["year"])
    return rows


def temperature_years(values: Sequence[Daily], through: date) -> list[dict[str, Any]]:
    """Each calendar year's warmest daily mean water temperature (°C), ranked over complete years.

    Args:
        values: Daily mean water temperature (°C), in day order.
        through: The last day with a discharge or temperature: its year is never ranked.

    Returns:
        One row per year with a summer value.
    """
    by_year: dict[int, list[Daily]] = {}
    for d in values:
        if d.day.month in SUMMER:
            by_year.setdefault(d.day.year, []).append(d)
    rows: list[dict[str, Any]] = []
    for year, days in sorted(by_year.items()):
        warmest = max(days, key=lambda d: (d.value, -d.day.toordinal()))
        complete = year != through.year and len(days) >= COVERAGE * _days_in(year, SUMMER)
        rows.append({
            "year": year, "days": len(days), "complete": complete, "toDate": year == through.year,
            "provisional": any(d.provisional for d in days),
            "warmest": round(warmest.value, 1), "warmestDay": warmest.day.isoformat(),
        })  # fmt: skip
    ranks = _ranks({r["year"]: r["warmest"] for r in rows if r["complete"]}, highest_first=True)
    for r in rows:
        r["warmestRank"] = ranks.get(r["year"])
    return rows


def summarise(snapshot: Mapping[str, Sequence[Daily]], station: Mapping[str, Any]
              ) -> dict[str, Any]:  # fmt: skip
    """``climate.json``: the station, the rules and each year's extremes.

    Args:
        snapshot: The snapshot's values per parameter.
        station: The station as ``reach.json`` names it (``id``, ``name``, ``url``).

    Returns:
        The document (deterministic for a given snapshot).
    """
    modelled = MODELLED in snapshot  # a flood model's m³/s, not a gauge's ft³/s
    flow = list(snapshot.get(MODELLED if modelled else DISCHARGE, []))
    warm = list(snapshot.get(TEMPERATURE, []))
    if not flow:
        raise reach_run.ReachError(f"{station.get('id')}: no daily discharge")
    through = max(d.day for d in [*flow, *warm])
    years = discharge_years(flow, through, 1.0 if modelled else FT3_TO_M3)
    out: dict[str, Any] = {
        "station": dict(station),
        "source": GLOFAS_SOURCE if modelled else "USGS Water Data, daily mean values (OGC API)",
        "through": through.isoformat(),
        "rules": {"coverage": COVERAGE, "lowWindowDays": LOW_WINDOW, "summerMonths": list(SUMMER)},
        "discharge": {"unit": "m³/s", "first": flow[0].day.isoformat(),
                      "rankedYears": sum(1 for r in years if r["complete"]), "years": years},
        "temperature": None,
    }  # fmt: skip
    if warm:
        rows = temperature_years(warm, through)
        out["temperature"] = {"unit": "°C", "first": warm[0].day.isoformat(),
                              "rankedYears": sum(1 for r in rows if r["complete"]),
                              "years": rows}  # fmt: skip
    return out


def calendar_index(day: date) -> int:
    """A day's place in the calendar, 0 (1 January) to 365 (31 December); 29 February as 28.

    Args:
        day: The day.

    Returns:
        Its index in a leap year's days.
    """
    month_day = (day.month, 28) if (day.month, day.day) == (2, 29) else (day.month, day.day)
    return (date(LEAP, *month_day) - date(LEAP, 1, 1)).days


def _windows(values: Sequence[Daily], years: set[int]) -> list[list[float]]:
    """For each calendar day, the reference years' values from 3 days before to 3 days after it."""
    out: list[list[float]] = [[] for _ in range(366)]
    for d in values:
        if d.day.year not in years:
            continue
        # Each value once per calendar day it is near (29 February would count 28 February twice).
        near = {calendar_index(d.day - timedelta(days=k))
                for k in range(-BAND_HALF_DAYS, BAND_HALF_DAYS + 1)}  # fmt: skip
        for index in near:
            out[index].append(d.value)
    out[calendar_index(date(LEAP, 2, 29)) + 1] = list(out[calendar_index(date(LEAP, 2, 28))])
    return out


def typical_flow(values: Sequence[Daily], complete: set[int], factor: float = FT3_TO_M3
                 ) -> dict[str, Any] | None:  # fmt: skip
    """The river's usual flow for each calendar day, over the complete years up to 2025.

    Args:
        values: Daily mean discharge, in day order.
        complete: The record's complete years (as ``discharge_years`` ranks them).
        factor: To m³/s.

    Returns:
        ``first``, ``last``, ``years``, ``windowDays`` and the 366 values of ``p10``, ``p50`` and
        ``p90`` (index 0 is 1 January, 59 is 29 February, the same as 28 February), in m³/s;
        None without a reference year.
    """
    years = {y for y in complete if y <= REFERENCE_LAST}
    if not years:
        return None
    windows = _windows(values, years)
    bands: dict[str, list[float | None]] = {"p10": [], "p50": [], "p90": []}
    for window in windows:
        cut = (np.percentile(window, BAND_PERCENTILES) if window
               else [float("nan")] * len(BAND_PERCENTILES))  # fmt: skip
        for key, value in zip(bands, cut, strict=True):
            bands[key].append(round(float(value) * factor, 1) if np.isfinite(value) else None)
    return {"first": min(years), "last": max(years), "years": len(years),
            "windowDays": 2 * BAND_HALF_DAYS + 1, **bands}  # fmt: skip


def latest_flow(values: Sequence[Daily], complete: set[int], factor: float = FT3_TO_M3
                ) -> dict[str, Any] | None:  # fmt: skip
    """The latest day's flow, and the share of its 7 days' reference values that were higher.

    Args:
        values: Daily mean discharge, in day order.
        complete: The record's complete years.
        factor: To m³/s.

    Returns:
        ``day``, ``value`` (m³/s), ``provisional``, ``higherShare`` (0 to 1) and ``values`` (how
        many reference values); None without a value or a reference year.
    """
    years = {y for y in complete if y <= REFERENCE_LAST}
    if not values or not years:
        return None
    last = values[-1]
    window = _windows(values, years)[calendar_index(last.day)]
    if not window:
        return None
    higher = sum(1 for v in window if v > last.value) / len(window)
    return {"day": last.day.isoformat(), "value": round(last.value * factor, 1),
            "provisional": last.provisional, "higherShare": round(higher, 2),
            "values": len(window)}  # fmt: skip


def add_usual_flow(doc: dict[str, Any], snapshot: Mapping[str, Sequence[Daily]]) -> None:
    """Add the usual flow and the latest day to ``climate.json`` (section 4 of the file).

    Args:
        doc: ``climate.json``, changed in place.
        snapshot: The snapshot's values per parameter.
    """
    modelled = MODELLED in snapshot
    flow = list(snapshot.get(MODELLED if modelled else DISCHARGE, []))
    factor = 1.0 if modelled else FT3_TO_M3
    complete = {y["year"] for y in doc["discharge"]["years"] if y["complete"]}
    doc["discharge"]["typical"] = typical_flow(flow, complete, factor)
    doc["discharge"]["latest"] = latest_flow(flow, complete, factor)


def unrank_lows(doc: dict[str, Any]) -> None:
    """Drop the 7-day low's ranks and say its spread instead (a model whose low barely moves).

    Args:
        doc: ``climate.json``, changed in place.
    """
    flow = doc["discharge"]
    lows = [y["low7"] for y in flow["years"] if y["complete"] and y["low7"] is not None]
    for y in flow["years"]:
        y["low7Rank"] = None
    flow["lowsRanked"] = False
    flow["lowsNote"] = (
        f"The model's 7-day low stays between {min(lows):,.1f} and {max(lows):,.1f} "
        f"{flow['unit']} in every complete year, so the years are not ranked by it (decided "
        "after seeing the record)."
    )


def snapshot_path(root: Path, site_id: str) -> Path:
    """Where a reach's daily snapshot lives (beside its examples, not served to the web).

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        The CSV path.
    """
    return root / "docs" / "water-quality" / "reach" / site_id / "climate" / "daily.csv"


def climate(cfg: ReachConfig, root: Path, site_id: str, until: date | None = None,
            http: httpx.Client | None = None, fetch_new: bool = True
            ) -> dict[str, Any]:  # fmt: skip
    """Fetch a reach's gauge record and write its snapshot and ``climate.json``.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        until: Last day to fetch (default: yesterday).
        http: HTTP client (injectable).
        fetch_new: False rebuilds ``climate.json`` from the committed snapshot, fetching nothing.

    Returns:
        The counts written.

    Raises:
        ReachError: For a reach with no USGS gauge, climate station or climate model.
    """
    reach = cfg.reach(site_id)
    context = reach.climate_station
    model = reach.climate_model
    if reach.station_source != "usgs" and context is None and model is None:
        raise reach_run.ReachError(f"{site_id}: the climate context needs a USGS gauge")
    path = snapshot_path(root, site_id)
    station: dict[str, Any]
    if model is not None:  # no open station record of the river: a flood model, named so
        if fetch_new:
            client = http or httpx.Client(timeout=120, follow_redirects=True)
            last = until or date.today() - timedelta(days=1)
            write_snapshot(path, fetch_modelled(client, model.lat, model.lon, last))
        station = {"id": f"GloFAS-{model.lat:.3f}N-{model.lon:.3f}E", "name": model.name,
                   "basis": model.basis, "url": "https://open-meteo.com/en/docs/flood-api",
                   "context": True, "modelled": True}  # fmt: skip
    else:
        # A reach with no station of its own reads a station on the same river, named as such.
        gauge = reach.estimate_station if context is None else context.id
        if fetch_new:
            api = load_quality_config(root / cfg.quality_config).usgs.api
            client = http or httpx.Client(timeout=120, follow_redirects=True)
            last = until or date.today() - timedelta(days=1)
            write_snapshot(path, fetch(client, api, gauge, last))
        station = (
            reach_run.reach_info(cfg, root, site_id)["station"]
            if context is None
            else {"id": context.id, "name": context.name, "basis": context.basis,
                  "url": f"https://waterdata.usgs.gov/monitoring-location/{context.id}/",
                  "context": True}
        )  # fmt: skip
    snapshot = read_snapshot(path)
    doc = summarise(snapshot, station)
    if model is not None and not model.rank_lows:
        unrank_lows(doc)
    from climate_pipeline.reach import along, daily_record

    if along.anchored(root, daily_record.PREREGISTRATION):
        add_usual_flow(doc, snapshot)
    from climate_pipeline.reach import extremes
    from climate_pipeline.reach.score import SCORED

    if site_id in SCORED:  # rule v1 defines extreme days for the demo reaches
        doc["extremes"] = extremes.document(root, site_id, reach.estimate_station, snapshot, doc)
    out = root / "docs" / "water-quality" / "reach" / site_id / "examples" / "climate.json"
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                   newline="\n")  # fmt: skip
    counts = {p: len(values) for p, values in snapshot.items()}
    return {"days": counts, "through": doc["through"],
            "rankedYears": doc["discharge"]["rankedYears"]}  # fmt: skip
