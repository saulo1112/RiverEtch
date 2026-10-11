"""``climate-pipeline reach baseline`` and ``reach run``: observation records v2 of a reach.

``baseline`` runs once per reach. On the frozen baseline's usable scenes it measures NIR/red per
sub-reach and the estimate station's windows, and NDTI again (compared with the frozen value as a
reproduction check). It writes them under ``docs/water-quality/reach/<site>/``.

``run`` publishes the scenes after the baseline, incrementally:

1. STAC search (Earth Search L2A), then SCL first: the screening's observable rule decides which
   scenes are read further.
2. The bands over the sub-reaches' box: NDTI and NIR/red per sub-reach; the estimate station's
   windows and features.
3. The product's model cards give each target's estimate at its level; D0 z-scores compare the
   scene with the frozen baseline only, so a sealed record never changes.
4. One sealed record per usable scene under ``pipeline/out/reach/<site>/records/``, with
   ``latest.json``, ``series.json`` and ``ledger.jsonl``, an append-only list whose lines chain by
   hash (ready for anchoring).

``state.json`` remembers every acquisition already decided; one that failed is retried by the next
run. Exit codes: 0 done, 2 partial (an acquisition failed), 3 a cap stopped the run.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.config import CalibrationConfig, load_calibration_config
from climate_pipeline.calibration.fetching import _csv, _reader, candidate_of, read_stations
from climate_pipeline.calibration.models import window_abstain_reason
from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.contract.observation import RainFlags
from climate_pipeline.provenance import head
from climate_pipeline.quality import cards, features, imagery, values
from climate_pipeline.quality.config import QualityConfig, load_quality_config
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.quality.route_a import scenes_from_windows
from climate_pipeline.quality.values import BAND_MB, SCL_MB, WINDOW_COLUMNS
from climate_pipeline.reach import measure as m
from climate_pipeline.reach import records
from climate_pipeline.reach.config import Reach, ReachConfig
from climate_pipeline.screening import stage1
from climate_pipeline.screening.config import (
    ScreeningConfig,
    SiteConfig,
    load_screening_config,
    load_site,
)
from climate_pipeline.screening.rain import OpenMeteoClient, rain_context
from climate_pipeline.screening.rio import AcquisitionReader, Grid
from climate_pipeline.screening.stac import Acquisition, make_source
from climate_pipeline.screening.stage2 import measure_acquisition

log = logging.getLogger(__name__)

EXIT_OK, EXIT_PARTIAL, EXIT_CAP = 0, 2, 3
BASELINE_COLUMNS = ("key", "date", "exclusion", "ndti_upstream", "ndti_downstream",
                    "frozen_ndti_upstream", "frozen_ndti_downstream", "nir_red_upstream",
                    "nir_red_downstream")  # fmt: skip


class ReachError(RuntimeError):
    """A reach cannot run (no geometry, no baseline, no cards)."""


@dataclass
class Setup:
    """Everything a reach run loads once."""

    cfg: ReachConfig
    reach: Reach
    root: Path
    screening: ScreeningConfig
    quality: QualityConfig
    d15: CalibrationConfig
    site: SiteConfig
    full: stage1.Stage1Result  # the frozen geometry on the site grid
    corridor: stage1.Stage1Result  # the same, cropped to the sub-reaches' box
    station: m.Station | None
    reader: m.MemoReader
    cards: dict[str, dict[str, Any]]
    window: str


def corridor_mb(grid: Grid) -> float:
    """Estimated download of one scene's corridor bands (Earth Search block sizes).

    Red and green at 10 m in 1024-pixel blocks, B11, B8A and SCL at 20 m in 512-pixel blocks;
    about 1.5 MB and 0.4 MB per block.

    Args:
        grid: The corridor's 20 m grid.

    Returns:
        Megabytes.
    """

    def blocks(n: int, size: int) -> int:
        return math.ceil(n / size) + 1  # a box rarely starts on a block edge

    b10 = blocks(grid.width * 2, 1024) * blocks(grid.height * 2, 1024)
    b20 = blocks(grid.width, 512) * blocks(grid.height, 512)
    return 2 * b10 * 1.5 + 3 * b20 * 0.4


def load_cards(folder: Path) -> dict[str, dict[str, Any]]:
    """The product's model cards by target.

    Args:
        folder: ``docs/water-quality/results/models``.

    Returns:
        Target -> card (empty when none was written).
    """
    out = {}
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        card = json.loads(path.read_text(encoding="utf-8"))
        out[str(card["target"])] = card
    return out


def setup(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int) -> Setup:
    """Load the settings, the frozen geometry, the estimate station and the model cards.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads.

    Returns:
        The setup.

    Raises:
        ReachError: When the geometry fails or the cards disagree on their window.
    """
    reach = cfg.reach(site_id)
    screening = load_screening_config(root / cfg.screening_config)
    quality = load_quality_config(root / cfg.quality_config)
    d15 = load_calibration_config(root / cfg.calibration_config)
    site = load_site(root / "pipeline" / "sites" / f"{site_id}.yaml")
    source = make_source(screening.stac.source, screening.stac.sources, screening.stac.page_size)
    span = (reach.geometry_start, reach.geometry_end)
    full = stage1.run_stage1(site, screening, source, AcquisitionReader(source, cache / "bands"),
                             None, workers, period=span, geometry_period=span)  # fmt: skip
    if full.geometry.failed:
        raise ReachError(f"{site_id}: no geometry ({full.geometry.failed})")
    model_cards = load_cards(root / cfg.models)
    windows = {str(c["window"]) for c in model_cards.values()}
    if len(windows) > 1:
        raise ReachError(f"the model cards use different windows: {sorted(windows)}")
    window = windows.pop() if windows else "300m"
    rows = read_stations(root / quality.outputs.inputs / "stations" / "stations.csv")
    row = next((r for r in rows if r["station_id"] == reach.estimate_station), None)
    station = None
    if row is not None:
        cand = candidate_of({**row, "files": ""})
        bbox = extract.bbox_around(cand.lon, cand.lat, quality.stations.grid_half_size_m)
        acqs = extract.search(d15, d15.imagery.primary, bbox, quality.geometry_period.start,
                              quality.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, acqs, _reader(d15, screening, cache), d15, screening,
                                       workers)  # fmt: skip
        if geo.selected:
            station = m.Station(cand.station_id, geo.width_m, imagery.small_windows(geo, quality))
    reader = m.MemoReader(make_source("earth-search", screening.stac.sources,
                                      screening.stac.page_size), cache / "bands")  # fmt: skip
    return Setup(cfg, reach, root, screening, quality, d15, site, full, m.corridor(full), station,
                 reader, model_cards, window)  # fmt: skip


def _bbox(site: SiteConfig) -> tuple[float, float, float, float]:
    west, south, east, north = site.aoi_bbox
    return west, south, east, north


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return math.nan


def frozen_ndti(path: Path, site_id: str) -> dict[str, dict[str, Any]]:
    """The frozen NDTI of the reach's usable scenes, by acquisition key.

    Args:
        path: The validation's ``scenes.csv``.
        site_id: The reach.

    Returns:
        Key -> ``date``, ``upstream``, ``downstream``.
    """
    out = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            if r["site_id"] == site_id and not r["excluded"]:
                out[r["acquisition"]] = {"date": date.fromisoformat(r["date"]),
                                         "upstream": _num(r["upstream_ndti"]),
                                         "downstream": _num(r["downstream_ndti"])}  # fmt: skip
    return out


def station_estimates(s: Setup, text: str) -> dict[str, list[float]]:
    """The station's historical estimates per target (the scenes no rule abstains on).

    Args:
        s: The setup.
        text: The station windows CSV of the baseline.

    Returns:
        Target -> estimates.
    """
    scenes = {w: scenes_from_windows(text, w) for w in ("300m", "core")}
    width = s.station.width_m if s.station else math.nan
    full = features.with_features(s.quality.features, scenes,
                                  {sc.station: width for sc in scenes["300m"]})  # fmt: skip
    window = s.quality.window.as_calibration()
    lab = s.root / s.quality.outputs.inputs / "lab"
    out: dict[str, list[float]] = {}
    for target, card in s.cards.items():
        values = []
        for sc in full.get(s.window, []):
            if window_abstain_reason(sc.stats, window) or cards.outside_range(card, sc.features):
                continue
            values.append(cards.estimate(card, sc.features, lab))
        out[target] = [v for v in values if math.isfinite(v)]
    return out


def load_baseline(s: Setup) -> records.Baseline:
    """The frozen history: NDTI from the validation, NIR/red and the station from ``baseline``.

    Args:
        s: The setup.

    Returns:
        The baseline (days in order).

    Raises:
        ReachError: When the NIR/red baseline has not been written.
    """
    ndti = frozen_ndti(s.root / s.reach.ndti_scenes, s.reach.site)
    path = s.root / s.reach.nir_red_baseline
    if not path.exists():
        raise ReachError(f"no NIR/red baseline at {path}: run `reach baseline` first")
    ratio = {r["key"]: r for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))}
    keys = sorted(ndti, key=lambda k: (ndti[k]["date"], k))
    days = tuple(ndti[k]["date"] for k in keys)

    def series(get: Any) -> dict[str, list[float]]:
        up = [get(k, "upstream") for k in keys]
        down = [get(k, "downstream") for k in keys]
        return {"upstream": up, "downstream": down,
                "delta": [d - u for u, d in zip(up, down, strict=True)]}  # fmt: skip

    windows = path.with_name("station-windows.csv")
    text = windows.read_text(encoding="utf-8") if windows.exists() else ""
    return records.Baseline(
        days,
        series(lambda k, side: float(ndti[k][side])),
        series(lambda k, side: _num(ratio.get(k, {}).get(f"nir_red_{side}", "nan"))),
        station_estimates(s, text) if text and s.station else {},
    )  # fmt: skip


def rain_flags(s: Setup, acquisition: Acquisition, http: httpx.Client | None,
               cache: Path) -> RainFlags:  # fmt: skip
    """The screening's point rule: more than 20 mm in the 72 h before, at any rain point.

    Catchment rain is not computed by a reach run.

    Args:
        s: The setup.
        acquisition: The pass.
        http: HTTP client (injectable).
        cache: Cache folder.

    Returns:
        The flags (unknown when Open-Meteo has no data yet).
    """
    rain = s.screening.rain
    try:
        client = OpenMeteoClient(rain.url, http=http, cache_dir=cache / "rain")
        day = acquisition.datetime.date()
        series = stage1.fetch_rain(s.site, client, day, day)
        mm = rain_context(series, acquisition.datetime, (rain.coincident_window_h,),
                          rain.timezone).max_over_points(rain.coincident_window_h)  # fmt: skip
    except (httpx.HTTPError, ValueError, KeyError) as error:
        log.info("rain unavailable for %s: %s", acquisition.key, error)
        mm = math.nan
    if not math.isfinite(mm):
        return RainFlags(point=None, catchment=None, union="unknown")
    point = mm > rain.coincident_mm
    return RainFlags(point=point, catchment=None, union="yes" if point else "unknown")


@dataclass
class State:
    """What earlier runs decided, by acquisition key."""

    decided: dict[str, str] = field(default_factory=dict)  # key -> "recorded", "not observable"..

    @classmethod
    def load(cls, path: Path) -> State:
        """Read the state (empty when absent).

        Args:
            path: ``state.json``.

        Returns:
            The state.
        """
        if not path.exists():
            return cls()
        return cls(dict(json.loads(path.read_text(encoding="utf-8"))["decided"]))

    def save(self, path: Path) -> None:
        """Write the state.

        Args:
            path: ``state.json``.
        """
        text = json.dumps({"decided": dict(sorted(self.decided.items()))}, indent=2)
        path.write_text(text + "\n", encoding="utf-8", newline="\n")


def append_ledger(path: Path, rec: v2.ObservationRecordV2, file: str, created: str) -> None:
    """Append one record to the ledger; each line names the SHA-256 of the line before.

    Args:
        path: ``ledger.jsonl``.
        rec: The sealed record.
        file: Its file, relative to the reach folder.
        created: UTC time of the run.
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else None
    line = {"sceneId": rec.scene_id, "date": rec.date, "recordSha256": rec.record_sha256,
            "file": file, "createdUtc": created, "previousLineSha256": previous}  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")


def ledger_ok(path: Path) -> bool:
    """Whether every ledger line names the hash of the line before it.

    Args:
        path: ``ledger.jsonl``.

    Returns:
        True for an intact chain (or no ledger).
    """
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = None
    for text in lines:
        if json.loads(text)["previousLineSha256"] != previous:
            return False
        previous = hashlib.sha256(text.encode()).hexdigest()
    return True


def summary_row(rec: v2.ObservationRecordV2, file: str) -> dict[str, Any]:
    """What the web needs from one record for a time series.

    Args:
        rec: The record.
        file: Its file, relative to the reach folder.

    Returns:
        The row.
    """
    data = rec.model_dump(mode="json", by_alias=True)
    return {"date": rec.date, "sceneId": rec.scene_id, "file": file,
            "recordSha256": rec.record_sha256, "indices": data["indices"],
            "verdict": data["verdict"], "rain": data["rain"],
            "estimates": [{k: e.get(k) for k in ("target", "unit", "level", "value", "interval",
                                                 "relativeClass", "abstainReason")}
                          for e in data["estimates"]]}  # fmt: skip


def write_views(folder: Path) -> None:
    """``series.json`` (every record, by date) and ``latest.json`` (the newest record).

    Args:
        folder: The reach's output folder.
    """
    rows = []
    for path in sorted((folder / "records").glob("*.json")):
        rec = v2.ObservationRecordV2.model_validate_json(path.read_text(encoding="utf-8"))
        rows.append((rec, path.relative_to(folder).as_posix()))
    rows.sort(key=lambda r: (r[0].date, r[0].scene_id))
    series = [summary_row(rec, file) for rec, file in rows]
    (folder / "series.json").write_text(json.dumps(series, indent=2) + "\n", encoding="utf-8",
                                        newline="\n")  # fmt: skip
    if rows:
        latest = rows[-1][0].model_dump(mode="json", by_alias=True)
        (folder / "latest.json").write_text(json.dumps(latest, indent=2) + "\n",
                                            encoding="utf-8", newline="\n")  # fmt: skip


@dataclass
class RunSummary:
    """What one run did."""

    exit_code: int
    recorded: list[str] = field(default_factory=list)
    skipped: dict[str, str] = field(default_factory=dict)
    failed: dict[str, str] = field(default_factory=dict)
    network_mb: float = 0.0
    stopped: str = ""


def run(cfg: ReachConfig, root: Path, site_id: str, since: date | None, until: date | None,
        cache: Path, workers: int = 8, http: httpx.Client | None = None,
        prepared: Setup | None = None) -> RunSummary:  # fmt: skip
    """Publish the reach's new scenes (see the module docstring).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        since: First day (default: ``lookback_days`` before today, never before the baseline).
        until: Last day (default: today).
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        http: HTTP client for rain (injectable).
        prepared: A setup already loaded (tests).

    Returns:
        The summary; ``exit_code`` is 0, 2 or 3.
    """
    check_disk(root, cfg.budgets.keep_free_gb)
    s = prepared or setup(cfg, root, site_id, cache, workers)
    today = datetime.now(UTC).date()
    until = until or today
    first = s.reach.baseline_end + timedelta(days=1)
    since = max(since or today - timedelta(days=cfg.lookback_days), first)
    folder = root / cfg.out / site_id
    (folder / "records").mkdir(parents=True, exist_ok=True)
    state = State.load(folder / "state.json")
    baseline = load_baseline(s)
    lab = root / s.quality.outputs.inputs / "lab"
    hashes = {t: cards.card_hash(c) for t, c in s.cards.items()}
    guards = s.quality.window.as_calibration()
    params = hashlib.sha256(b"".join((root / p).read_bytes() for p in (
        "pipeline/reach.yaml", cfg.screening_config, cfg.quality_config))).hexdigest()  # fmt: skip
    commit = head()
    created = datetime.now(UTC).isoformat(timespec="seconds")
    acqs, sun = imagery.search(s.quality, "earth-search", _bbox(s.site), since, until)
    summary = RunSummary(EXIT_OK)
    scene_mb = corridor_mb(s.corridor.grid) + (BAND_MB["earth-search"] if s.station else 0.0)
    for acq in sorted(acqs, key=lambda a: (a.datetime, a.key)):
        if acq.key in state.decided:
            continue
        if summary.network_mb / 1000 >= cfg.budgets.max_gb:
            summary.stopped = f"network cap of {cfg.budgets.max_gb:g} GB reached"
            summary.exit_code = EXIT_CAP
            break
        try:
            check_disk(root, cfg.budgets.keep_free_gb)
        except RuntimeError as error:
            summary.stopped, summary.exit_code = str(error), EXIT_CAP
            break
        try:
            summary.network_mb += SCL_MB * 5
            if not m.observable(acq, s.reader, s.full, s.screening):
                state.decided[acq.key] = summary.skipped[acq.key] = "not observable"
                continue
            summary.network_mb += scene_mb
            measure = m.measure(acq, s.reader, s.corridor, s.station, s.window, sun, s.quality,
                                s.d15, s.screening)  # fmt: skip
            if measure.exclusion:
                state.decided[acq.key] = summary.skipped[acq.key] = f"excluded: {measure.exclusion}"
                continue
            estimates = [
                records.estimate(s.cards.get(t.id), hashes.get(t.id, ""), t, measure,
                                 baseline.estimates.get(t.id, []), guards, lab)
                for t in s.quality.targets
            ]  # fmt: skip
            rec = records.record(site_id, measure, baseline, estimates,
                                 rain_flags(s, acq, http, cache), set(s.reach.rainy_months),
                                 s.screening, cfg.threshold, commit, params)  # fmt: skip
        except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run retries
            log.warning("%s failed: %s", acq.key, error)
            summary.failed[acq.key] = str(error)
            summary.exit_code = EXIT_PARTIAL
            continue
        file = f"records/{rec.date}_{acq.key}.json"
        (folder / file).write_text(rec.model_dump_json(indent=2, by_alias=True) + "\n",
                                   encoding="utf-8", newline="\n")  # fmt: skip
        append_ledger(folder / "ledger.jsonl", rec, file, created)
        state.decided[acq.key] = "recorded"
        summary.recorded.append(file)
    state.save(folder / "state.json")
    write_views(folder)
    return summary


def build_baseline(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
                   prepared: Setup | None = None) -> dict[str, Any]:  # fmt: skip
    """Measure NIR/red and the station windows on the frozen baseline's usable scenes, once.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        prepared: A setup already loaded (tests).

    Returns:
        Counts, the estimated network volume and the NDTI reproduction check.
    """
    check_disk(root, cfg.budgets.keep_free_gb)
    s = prepared or setup(cfg, root, site_id, cache, workers)
    ndti = frozen_ndti(root / s.reach.ndti_scenes, site_id)
    days = sorted(v["date"] for v in ndti.values())
    acqs, sun = imagery.search(s.quality, "earth-search", _bbox(s.site),
                               days[0] - timedelta(days=1),
                               days[-1] + timedelta(days=1))  # fmt: skip
    wanted = [a for a in sorted(acqs, key=lambda a: (a.datetime, a.key)) if a.key in ndti]
    scene_mb = corridor_mb(s.corridor.grid) + (BAND_MB["earth-search"] if s.station else 0.0)
    rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    spent, stopped = 0.0, ""
    for acq in wanted:
        if spent / 1000 >= cfg.budgets.baseline_max_gb:
            stopped = f"network cap of {cfg.budgets.baseline_max_gb:g} GB reached"
            break
        check_disk(root, cfg.budgets.keep_free_gb)
        spent += scene_mb
        scene = measure_acquisition(s.corridor, acq, s.reader, s.screening)
        ratio = m.nir_red(s.corridor, acq, s.reader, s.screening)
        if s.station is not None:
            window_rows += values.measure(acq, "earth-search", s.reader, s.station.windows,
                                          s.station.station_id, sun, s.d15, s.screening,
                                          s.quality.timezone)  # fmt: skip
        s.reader.forget(acq)
        frozen = ndti[acq.key]
        rows.append({
            "key": acq.key, "date": frozen["date"].isoformat(), "exclusion": scene.exclusion,
            "ndti_upstream": scene.sub["upstream"].ndti if "upstream" in scene.sub else math.nan,
            "ndti_downstream": (scene.sub["downstream"].ndti if "downstream" in scene.sub
                                else math.nan),
            "frozen_ndti_upstream": frozen["upstream"],
            "frozen_ndti_downstream": frozen["downstream"],
            "nir_red_upstream": ratio.get("upstream", math.nan),
            "nir_red_downstream": ratio.get("downstream", math.nan),
        })  # fmt: skip
    path = root / s.reach.nir_red_baseline
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_csv(rows, BASELINE_COLUMNS))
    path.with_name("station-windows.csv").write_bytes(_csv(window_rows, WINDOW_COLUMNS))
    gaps = [abs(r[f"ndti_{side}"] - r[f"frozen_ndti_{side}"])
            for r in rows for side in ("upstream", "downstream")
            if math.isfinite(r[f"ndti_{side}"] - r[f"frozen_ndti_{side}"])]  # fmt: skip
    info = {
        "site": site_id, "frozen_scenes": len(ndti), "found": len(wanted), "measured": len(rows),
        "station": s.station.station_id if s.station else None,
        "network_gb_estimated": round(spent / 1000, 3), "stopped": stopped,
        "ndti_max_abs_difference": round(max(gaps), 6) if gaps else None,
        "code_commit": head(), "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }  # fmt: skip
    path.with_name("baseline.json").write_text(json.dumps(info, indent=2) + "\n",
                                               encoding="utf-8", newline="\n")  # fmt: skip
    return info
