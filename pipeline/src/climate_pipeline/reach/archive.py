"""The earlier years, 2019 to 2025, along the river and at the station (preregistration-archive.md).

The sealed records start in 2026. This module reads the years before them once, with the same
frozen models and the same code paths as the records: every observable Sentinel-2 pass of a reach,
on every window of its frozen plan (``along._classes``) and on the station's window (a record's
estimate, ``records.estimate``); and, on a reach with a water-temperature card, every Landsat pass,
on the station's core (``thermal.estimate``) and on every window's core
(``along_temperature.classes``). Nothing here is sealed: a pass read after the fact is not a
record. The results are written per reach and per year beside the examples, each naming the code
commit, the plan and the cards, so anyone can read the same passes again and compare. A year's
file is written after every pass, so an interrupted run resumes where it stopped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.calibration import extract
from climate_pipeline.provenance import head
from climate_pipeline.quality import cards, imagery, landsat, values, variables
from climate_pipeline.reach import along, along_temperature, records, thermal
from climate_pipeline.reach import measure as m
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import Acquisition, group_acquisitions, search_items

log = logging.getLogger(__name__)

SCHEMA = "riveretch.archive.v1"
# Each class beside the value it was made from (preregistration-values.md).
SCHEMA_V2 = "riveretch.archive.v2"
SCHEMA_TEMPERATURE = "riveretch.archive-temperature.v1"
PREREGISTRATION = "docs/water-quality/preregistration-archive.md"
YEARS = tuple(range(2019, 2026))  # 2019 to 2025: the years before the sealed records
LOCKBOX = (date(2023, 12, 1), date(2026, 9, 30))  # preregistration.md, "Splits"


@dataclass
class Summary:
    """What one archive run did."""

    read: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    exit_code: int = reach_run.EXIT_OK


def phase(card: dict[str, Any] | None, day: date, ungauged: bool) -> str:
    """What a pass was to the model (section 2).

    Args:
        card: The card (its own training dates, when it names them).
        day: The pass's local date.
        ungauged: The reach has no station.

    Returns:
        ``unseen`` on a reach with no station; else ``training``, ``test`` or ``after``.
    """
    if ungauged:
        return "unseen"
    train = (card or {}).get("training") or []
    if len(train) == 2 and date.fromisoformat(train[0]) <= day <= date.fromisoformat(train[1]):
        return "training"
    if LOCKBOX[0] <= day <= LOCKBOX[1]:
        return "test"
    return "training" if day < LOCKBOX[0] else "after"


def folder(root: Path, site_id: str, kind: str = "archive") -> Path:
    """Where a reach's earlier years are written (beside its examples).

    Args:
        root: Repository root.
        site_id: The reach.
        kind: ``archive`` (Sentinel-2) or ``archive-temperature`` (Landsat).

    Returns:
        ``docs/water-quality/reach/<site>/examples/<kind>``.
    """
    return root / "docs" / "water-quality" / "reach" / site_id / "examples" / kind


def _num(x: float | None, digits: int = 2) -> float | None:
    return round(x, digits) if x is not None and math.isfinite(x) else None


def _load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def write_index(root: Path, site_id: str, kind: str) -> Path:
    """List the years written and how many passes each holds (the app's year menu).

    Args:
        root: Repository root.
        site_id: The reach.
        kind: ``archive`` or ``archive-temperature``.

    Returns:
        The index's path.
    """
    out = folder(root, site_id, kind)
    years = []
    for path in sorted(out.glob("[0-9][0-9][0-9][0-9].json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        years.append({"year": doc["year"], "passes": len(doc["passes"]),
                      "failed": len(doc.get("failed", {}))})  # fmt: skip
    index = out / "index.json"
    _write(index, {"schema": SCHEMA if kind == "archive" else SCHEMA_TEMPERATURE, "years": years})
    return index


def _station(s: reach_run.Setup, acq: Acquisition, sun: dict[str, float],
             card: dict[str, Any] | None, card_sha: str, lab: Path, with_value: bool = False
             ) -> dict[str, Any] | None:  # fmt: skip
    """The start's estimate for one pass, exactly as a record's (no record-level exclusion)."""
    if s.station is None or card is None:
        return None
    target = next(t for t in s.quality.targets if t.id == "turbidity")
    try:
        rows = values.measure(acq, "earth-search", s.reader, s.station.windows,
                              s.station.station_id, sun, s.d15, s.screening,
                              s.quality.timezone)  # fmt: skip
        scenes = m.scene_rows(rows, s.station, s.quality)
        scene = scenes.get(s.window)
        problem = "" if scene else "the station's windows were not measured"
    except (OSError, RuntimeError, ValueError) as error:
        scene, problem = None, f"window read failed: {error}"
    measure = records.Measure(
        key=acq.key, day=extract.local_date(acq, s.quality.timezone), items=m.items(acq),
        exclusion="", ndti={}, nir_red={},
        window=scene.features if scene else {}, stats=scene.stats if scene else {},
        window_problem=problem,
    )  # fmt: skip
    e = records.estimate(card, card_sha, target, measure, [], s.quality.window.as_calibration(),
                         lab, with_value)  # fmt: skip
    return {
        "level": e.level, "value": _num(e.value),
        "low": _num(e.interval.low) if e.interval else None,
        "high": _num(e.interval.high) if e.interval else None,
        "fnuClass": e.fnu_class, "reason": e.abstain_reason,
    }  # fmt: skip


def run(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
        years: tuple[int, ...] = YEARS, http: httpx.Client | None = None) -> Summary:  # fmt: skip
    """Read a reach's earlier Sentinel-2 passes along the river and at the start (resumable).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        years: The years to read (2019 to 2025).
        http: Unused (the catalogue client is the reach's own).

    Returns:
        How many passes were read, and which failed (the next run retries them).

    Raises:
        ReachError: Before the anchor, without a plan, or when the geometry no longer matches it.
    """
    del http
    if not along.anchored(root, PREREGISTRATION):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    frozen_path = along.plan_path(root, site_id)
    if not frozen_path.exists():
        raise reach_run.ReachError(f"{site_id}: no frozen plan of windows")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    s = reach_run.setup(cfg, root, site_id, cache, workers)
    geos = along._geometries(s)
    windows = [w for w, _ in geos]
    if not along._same_plan(frozen, windows):
        raise reach_run.ReachError(f"{site_id}: the geometry no longer matches the frozen plan")
    grid = along._grid(s, [(w, g) for w, g in geos if g is not None])
    card = json.loads((root / str(frozen["card"])).read_text(encoding="utf-8"))
    card_sha = cards.card_hash(card)
    station_card = s.cards.get("turbidity")
    station_sha = cards.card_hash(station_card) if station_card is not None else ""
    lab = root / s.quality.outputs.inputs / "lab"
    ungauged = s.reach.station_source != "usgs"
    commit = head()
    out = folder(root, site_id)
    with_value = along.anchored(root, records.VALUES_PREREGISTRATION)
    summary = Summary()
    for year in years:
        path = out / f"{year}.json"
        fresh = {
            "schema": SCHEMA_V2 if with_value else SCHEMA, "reach": site_id, "year": year,
            "planSha256": plan_sha, "card": frozen["card"], "modelCardSha256": card_sha,
            "stationCard": s.reach.cards.get("turbidity"), "stationCardSha256": station_sha,
            "codeCommit": commit, "passes": [], "failed": {}, "notObservable": [],
        }  # fmt: skip
        doc = _load(path) or fresh
        # Once preregistration-values.md is anchored, a year written without values is read again
        # once, from the start (its passes found not observable stay so: the rule is unchanged).
        if with_value and doc.get("schema") != SCHEMA_V2:
            doc = {**fresh, "notObservable": list(doc.get("notObservable", []))}
        # Read once: a pass already written, or already found not observable, is not read again.
        done = {p["sceneId"] for p in doc["passes"]} | set(doc.setdefault("notObservable", []))
        acqs, sun = imagery.search(s.quality, "earth-search", reach_run._bbox(s.site),
                                   date(year, 1, 1), date(year, 12, 31))  # fmt: skip
        for acq in sorted(acqs, key=lambda a: (a.datetime, a.key)):
            scene_id = f"{site_id}:{acq.key}"
            if scene_id in done:
                continue
            try:
                if not m.observable(acq, s.reader, s.full, s.screening):
                    doc["failed"].pop(acq.key, None)
                    doc["notObservable"].append(scene_id)
                    _write(path, doc)
                    continue
                classes = along._classes(s, acq, sun, grid, windows, card, card_sha, lab,
                                         with_value)  # fmt: skip
                station = _station(s, acq, sun, station_card, station_sha, lab, with_value)
            except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run
                log.warning("%s failed: %s", acq.key, error)
                doc["failed"][acq.key] = str(error)[:200]
                summary.failed[acq.key] = str(error)
                summary.exit_code = reach_run.EXIT_PARTIAL
                continue
            finally:
                s.reader.forget(acq)
            day = extract.local_date(acq, s.quality.timezone)
            doc["failed"].pop(acq.key, None)
            doc["passes"].append({
                "sceneId": scene_id, "date": day.isoformat(),
                "phase": phase(station_card, day, ungauged), "station": station,
                "classes": [w.get("fnuClass") for w in classes],
                **({"values": [w.get("fnuValue") for w in classes]} if with_value else {}),
                "reasons": [w.get("abstainReason") for w in classes],
            })  # fmt: skip
            doc["passes"].sort(key=lambda p: (p["date"], p["sceneId"]))
            _write(path, doc)
            summary.read += 1
        _write(path, doc)
        write_index(root, site_id, "archive")
    return summary


def run_temperature(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
                    years: tuple[int, ...] = YEARS) -> Summary:  # fmt: skip
    """Read a reach's earlier Landsat passes along the river and at the station (resumable).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        years: The years to read (2019 to 2025).

    Returns:
        How many passes were read, and which failed (the next run retries them).

    Raises:
        ReachError: Before the anchor, without a card, a station or a plan, or when the geometry
            no longer matches the plan.
    """
    if not along.anchored(root, PREREGISTRATION):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    card_file = thermal.card_path(root, site_id)
    if not card_file.exists():
        raise reach_run.ReachError(f"{site_id}: no water-temperature card")
    frozen_path = along.plan_path(root, site_id)
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    s = reach_run.setup(cfg, root, site_id, cache, workers, need_cards=False)
    if s.station is None:
        raise reach_run.ReachError(f"{site_id}: no estimate station")
    geos = along._geometries(s)
    windows = [w for w, _ in geos]
    if not along._same_plan(frozen, windows):
        raise reach_run.ReachError(f"{site_id}: the geometry no longer matches the frozen plan")
    placed = [(w, g) for w, g in geos if g is not None]
    fine = along._grid(s, placed)
    grid, cores = along_temperature._windows30(fine.grid, fine.masks, [w for w, _ in placed])
    station_grid, station_core = variables.grid30(s.station.windows.masks["core"],
                                                  s.station.windows.grid)  # fmt: skip
    card = json.loads(card_file.read_text(encoding="utf-8"))
    card_sha = cards.card_hash(card)
    minimum = int(card["minWaterPixels"])
    reader = AcquisitionReader(landsat.source(), cache / "landsat-bands", ("qa_pixel",))
    west, south, east, north = s.site.aoi_bbox
    commit = head()
    out = folder(root, site_id, "archive-temperature")
    summary = Summary()
    for year in years:
        path = out / f"{year}.json"
        doc = _load(path) or {
            "schema": SCHEMA_TEMPERATURE, "reach": site_id, "year": year,
            "planSha256": plan_sha, "card": card_file.relative_to(root).as_posix(),
            "modelCardSha256": card_sha, "codeCommit": commit, "passes": [], "failed": {},
            "unreadable": [],
        }  # fmt: skip
        done = {p["sceneId"] for p in doc["passes"]} | set(doc.setdefault("unreadable", []))
        scenes = [sc for item in search_items(landsat.STAC_URL, landsat.COLLECTION,
                                              (west, south, east, north), date(year, 1, 1),
                                              date(year, 12, 31), 100)
                  if (sc := variables.thermal_parse(item)) is not None]  # fmt: skip
        for acq in sorted(group_acquisitions(scenes), key=lambda a: (a.datetime, a.key)):
            scene_id = f"{site_id}:{acq.key}"
            if scene_id in done:
                continue
            try:
                row = variables.thermal_window(acq, reader, station_grid, station_core,
                                               s.reach.estimate_station)  # fmt: skip
                found = along_temperature.classes(acq, reader, grid, cores, windows, card)
            except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run
                log.warning("%s failed: %s", acq.key, error)
                doc["failed"][acq.key] = str(error)[:200]
                summary.failed[acq.key] = str(error)
                summary.exit_code = reach_run.EXIT_PARTIAL
                continue
            doc["failed"].pop(acq.key, None)
            classes = [w.get("temperatureClass") for w in found]
            station = None
            if row["water_px"] >= minimum and math.isfinite(row["st_k"]):
                e = thermal.estimate(card, row["st_k"])
                station = {
                    "level": e.level, "value": e.value,
                    "low": e.interval.low if e.interval else None,
                    "high": e.interval.high if e.interval else None,
                    "waterPixels": row["water_px"],
                }  # fmt: skip
            if station is None and all(c is None for c in classes):
                doc["unreadable"].append(scene_id)  # nothing readable: clouds over the reach
                _write(path, doc)
                continue
            day = date.fromisoformat(thermal.imagery_local_date(acq.datetime, s.quality.timezone))
            doc["passes"].append({
                "sceneId": scene_id, "date": day.isoformat(), "platform": acq.platform,
                "phase": phase(None, day, False),
                "station": station, "classes": classes,
                "reasons": [w.get("abstainReason") for w in found],
            })  # fmt: skip
            doc["passes"].sort(key=lambda p: (p["date"], p["sceneId"]))
            _write(path, doc)
            summary.read += 1
        _write(path, doc)
        write_index(root, site_id, "archive-temperature")
    return summary
