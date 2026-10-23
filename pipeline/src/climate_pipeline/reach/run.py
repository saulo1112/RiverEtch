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
from climate_pipeline.calibration.stations import Candidate
from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.contract.observation import RainFlags
from climate_pipeline.provenance import head
from climate_pipeline.quality import cards, features, imagery, posthoc, values
from climate_pipeline.quality.config import QualityConfig, load_quality_config
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.quality.route_a import scenes_from_windows
from climate_pipeline.quality.values import BAND_MB, SCL_MB, WINDOW_COLUMNS
from climate_pipeline.reach import check, records
from climate_pipeline.reach import measure as m
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
    """The product's model cards by target; v2.1's post-hoc card wins where one exists.

    Its records then name the basis "post hoc, nested LOSO on the Magdalena". A reach that
    declares its cards (:func:`reach_cards`) never reads this folder.

    Args:
        folder: ``docs/water-quality/results/models``.

    Returns:
        Target -> card (empty when none was written).
    """
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        card = json.loads(path.read_text(encoding="utf-8"))
        target = str(card["target"])
        if target not in out or card.get("basis") == posthoc.BASIS:
            out[target] = card
    return out


def reach_cards(cfg: ReachConfig, reach: Reach, root: Path, strict: bool = True
                ) -> dict[str, dict[str, Any]]:  # fmt: skip
    """The model cards of a reach's targets: the ones it declares, else the models folder.

    Args:
        cfg: Reach settings.
        reach: The reach.
        root: Repository root.
        strict: A declared card that is missing is an error (False: it is skipped, as the
            baseline needs no card).

    Returns:
        Target -> card.

    Raises:
        ReachError: When a declared card is missing (strict) or names another target.
    """
    if not reach.cards:
        return {t: c for t, c in load_cards(root / cfg.models).items() if t in reach.targets}
    out: dict[str, dict[str, Any]] = {}
    for target, path in reach.cards.items():
        file = root / path
        if not file.exists():
            if not strict:
                continue
            raise ReachError(f"{reach.site}: no model card at {path}")
        card = json.loads(file.read_text(encoding="utf-8"))
        if card["target"] != target:
            raise ReachError(f"{reach.site}: {path} is a {card['target']} card, not {target}")
        out[target] = card
    return out


USGS_LISTS = ("usgs-v5/sites.csv", "usgs/sites.csv")  # v5's list first, then the pilot's


def station_row(reach: Reach, quality: QualityConfig, root: Path) -> dict[str, str] | None:
    """The estimate station's row in its frozen station list.

    Args:
        reach: The reach.
        quality: The v2 settings (the inputs folder).
        root: Repository root.

    Returns:
        The row (None when the station is not listed, and for an ungauged reach).
    """
    inputs = root / quality.outputs.inputs
    if reach.ungauged:
        return None
    if reach.station_source == "usgs":
        for name in USGS_LISTS:
            path = inputs / name
            for r in read_stations(path) if path.exists() else []:
                if r["site_id"] == reach.estimate_station:
                    return r
        return None
    rows = read_stations(inputs / "stations" / "stations.csv")
    return next((r for r in rows if r["station_id"] == reach.estimate_station), None)


def station_candidate(reach: Reach, quality: QualityConfig, root: Path) -> Candidate | None:
    """The estimate station as a selection candidate, from its station list.

    Args:
        reach: The reach.
        quality: The v2 settings (the inputs folder).
        root: Repository root.

    Returns:
        The candidate (None when the station is not listed); an ungauged reach's window point.
    """
    if reach.estimate_point is not None:
        p = reach.estimate_point
        return Candidate(reach.estimate_station, "estimate window (no gauge)", p.lon, p.lat, "usgs")
    row = station_row(reach, quality, root)
    if row is None:
        return None
    if reach.station_source == "usgs":
        return Candidate(row["site_id"], row["name"], float(row["lon"]), float(row["lat"]), "usgs")
    return candidate_of({**row, "files": ""})


def frozen_width(reach: Reach, quality: QualityConfig, root: Path) -> float:
    """The main-channel width the models were trained with (the station list's), in metres.

    The live geometry can measure a slightly different width; the feature ``log_width_m`` must be
    the one the card saw, or a scene abstains for a width outside the training range.

    Args:
        reach: The reach.
        quality: The v2 settings.
        root: Repository root.

    Returns:
        The width (NaN when the list gives none).
    """
    row = station_row(reach, quality, root)
    return _num(row.get("width_m", "")) if row is not None else math.nan


def setup(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int,
          need_cards: bool = True) -> Setup:  # fmt: skip
    """Load the settings, the frozen geometry, the estimate station and the model cards.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads.
        need_cards: Every declared model card must exist (the baseline needs none).

    Returns:
        The setup.

    Raises:
        ReachError: When the geometry fails, a card is missing or the cards disagree on their
            window.
    """
    reach = cfg.reach(site_id)
    screening = load_screening_config(root / cfg.screening_config)
    quality = load_quality_config(root / cfg.quality_config)
    if quality.timezone != reach.timezone or screening.rain.timezone != reach.timezone:
        # Local dates (records, station windows) and the rain window follow the reach's zone.
        quality = quality.model_copy(update={"timezone": reach.timezone})
        rain = screening.rain.model_copy(update={"timezone": reach.timezone})
        screening = screening.model_copy(update={"rain": rain})
    d15 = load_calibration_config(root / cfg.calibration_config)
    site = load_site(reach.site_path(root))
    source = make_source(screening.stac.source, screening.stac.sources, screening.stac.page_size)
    span = (reach.geometry_start, reach.geometry_end)
    full = stage1.run_stage1(site, screening, source, AcquisitionReader(source, cache / "bands"),
                             None, workers, period=span, geometry_period=span)  # fmt: skip
    if full.geometry.failed:
        raise ReachError(f"{site_id}: no geometry ({full.geometry.failed})")
    model_cards = reach_cards(cfg, reach, root, strict=need_cards)
    windows = {str(c["window"]) for c in model_cards.values()}
    if len(windows) > 1:
        raise ReachError(f"the model cards use different windows: {sorted(windows)}")
    window = windows.pop() if windows else "300m"
    cand = station_candidate(reach, quality, root)
    station = None
    if cand is None:
        log.warning("%s: estimate station %s is not listed", site_id, reach.estimate_station)
    else:
        bbox = extract.bbox_around(cand.lon, cand.lat, quality.stations.grid_half_size_m)
        acqs = extract.search(d15, d15.imagery.primary, bbox, quality.geometry_period.start,
                              quality.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, acqs, _reader(d15, screening, cache), d15, screening,
                                       workers)  # fmt: skip
        if geo.selected:
            width = frozen_width(reach, quality, root)
            station = m.Station(cand.station_id, width if math.isfinite(width) else geo.width_m,
                                imagery.small_windows(geo, quality))  # fmt: skip
    reader = m.MemoReader(make_source("earth-search", screening.stac.sources,
                                      screening.stac.page_size), cache / "bands")  # fmt: skip
    return Setup(cfg, reach, root, screening, quality, d15, site, full, m.corridor(full), station,
                 reader, model_cards, window)  # fmt: skip


def _bbox(site: SiteConfig) -> tuple[float, float, float, float]:
    west, south, east, north = site.aoi_bbox
    return west, south, east, north


def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def _num(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return math.nan


def frozen_ndti(path: Path, site_id: str, end: date | None = None) -> dict[str, dict[str, Any]]:
    """The frozen NDTI of the reach's usable scenes, by acquisition key.

    Args:
        path: The validation's ``scenes.csv``.
        site_id: The reach.
        end: The baseline's last day (later scenes are left out).

    Returns:
        Key -> ``date``, ``upstream``, ``downstream``.
    """
    out = {}
    with path.open(encoding="utf-8", newline="") as handle:
        for r in csv.DictReader(handle):
            if end is not None and date.fromisoformat(r["date"]) > end:
                continue
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
    """The frozen history: NDTI, NIR/red and the station's estimates up to ``baseline_end``.

    NDTI comes from the validation's ``scenes.csv`` when the reach names one; otherwise from the
    usable scenes the reach's own baseline measured.

    Args:
        s: The setup.

    Returns:
        The baseline (days in order).

    Raises:
        ReachError: When the NIR/red baseline has not been written.
    """
    path = s.root / s.reach.nir_red_baseline
    if not path.exists():
        raise ReachError(f"no NIR/red baseline at {path}: run `reach baseline` first")
    ratio = {r["key"]: r for r in csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))}
    end = s.reach.baseline_end
    if s.reach.ndti_scenes:
        ndti = frozen_ndti(s.root / s.reach.ndti_scenes, s.reach.site, end)
    else:
        ndti = {k: {"date": date.fromisoformat(r["date"]), "upstream": _num(r["ndti_upstream"]),
                    "downstream": _num(r["ndti_downstream"])}
                for k, r in ratio.items()
                if not r["exclusion"] and date.fromisoformat(r["date"]) <= end}  # fmt: skip
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
    """What earlier runs decided, by acquisition key, and where a capped run stopped."""

    decided: dict[str, str] = field(default_factory=dict)  # key -> "recorded", "not observable"..
    resume: str | None = None  # the day of the first pass a cap left undecided (ISO date)

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
        doc = json.loads(path.read_text(encoding="utf-8"))
        return cls(dict(doc["decided"]), doc.get("resume"))

    def save(self, path: Path) -> None:
        """Write the state.

        Args:
            path: ``state.json``.
        """
        doc: dict[str, Any] = {"decided": dict(sorted(self.decided.items()))}
        if self.resume is not None:
            doc["resume"] = self.resume
        path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")


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
    keys = ("target", "unit", "level", "value", "interval", "relativeClass", "abstainReason")
    # An ungauged reach's class, only where there is one (other views unchanged).
    estimates = [{**{k: e.get(k) for k in keys},
                  **({"fnuClass": e["fnuClass"]} if e.get("fnuClass") else {})}
                 for e in data["estimates"]]  # fmt: skip
    return {"date": rec.date, "sceneId": rec.scene_id, "file": file,
            "recordSha256": rec.record_sha256, "indices": data["indices"],
            "verdict": data["verdict"], "rain": data["rain"], "estimates": estimates,
            **({"supersedes": rec.supersedes} if rec.supersedes else {})}  # fmt: skip


def write_views(folder: Path) -> None:
    """``series.json`` (every pass's current record, by date) and ``latest.json`` (the newest).

    A record another one supersedes (the pass read again with a newer card) stays in the ledger
    and in ``records/``, but the views show the record that replaced it.

    Args:
        folder: The reach's output folder.
    """
    rows = []
    for path in sorted((folder / "records").glob("*.json")):
        rec = v2.ObservationRecordV2.model_validate_json(path.read_text(encoding="utf-8"))
        rows.append((rec, path.relative_to(folder).as_posix()))
    replaced = {rec.supersedes for rec, _ in rows if rec.supersedes is not None}
    rows = [(rec, file) for rec, file in rows if rec.record_sha256 not in replaced]
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
        prepared: Setup | None = None, config_path: Path | None = None) -> RunSummary:  # fmt: skip
    """Publish the reach's new scenes (see the module docstring).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        since: First day (default: ``lookback_days`` before today, or the day a capped run
            stopped if earlier; a reach's first run starts after its baseline; never before it).
        until: Last day (default: today).
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        http: HTTP client for rain (injectable).
        prepared: A setup already loaded (tests).
        config_path: The settings file the run read (its bytes enter the parameters' hash).

    Returns:
        The summary; ``exit_code`` is 0, 2 or 3.
    """
    check_disk(root, cfg.budgets.keep_free_gb)
    s = prepared or setup(cfg, root, site_id, cache, workers)
    today = datetime.now(UTC).date()
    until = until or today
    first = s.reach.baseline_end + timedelta(days=1)
    folder = root / cfg.out / site_id
    new_reach = not (folder / "state.json").exists()  # its first run publishes every later pass
    state = State.load(folder / "state.json")
    default = first if new_reach else today - timedelta(days=cfg.lookback_days)
    if state.resume is not None:
        default = min(default, date.fromisoformat(state.resume))
    since = max(since or default, first)
    (folder / "records").mkdir(parents=True, exist_ok=True)
    baseline = load_baseline(s)
    lab = root / s.quality.outputs.inputs / "lab"
    hashes = {t: cards.card_hash(c) for t, c in s.cards.items()}
    guards = s.quality.window.as_calibration()
    with_value = values_anchored(root)
    settings = config_path or root / "pipeline" / "reach.yaml"
    params = hashlib.sha256(b"".join(p.read_bytes() for p in (
        settings, root / cfg.screening_config, root / cfg.quality_config))).hexdigest()  # fmt: skip
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
                if hasattr(s.reader, "forget"):
                    s.reader.forget(acq)
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
                                 baseline.estimates.get(t.id, []), guards, lab, with_value)
                for t in s.quality.targets if t.id in s.reach.targets
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
        if s.reach.station_source == "usgs":  # v4's prospective check: beside the record
            for e in estimates:
                card = s.cards.get(e.target)
                if card is None or e.level == "none" or e.abstain_reason is not None:
                    continue
                value = cards.estimate(card, measure.window, lab)
                if math.isfinite(value) and value > 0:
                    check.note_estimate(folder, rec.scene_id, acq.key, acq.datetime, e.target,
                                        hashes[e.target], value)  # fmt: skip
        log.info("%s: recorded %s (anomalous: %s)", site_id, file, rec.verdict.anomalous)
        state.decided[acq.key] = "recorded"
        summary.recorded.append(file)
    # A cap left passes undecided: the next run starts from the first of them, however old.
    left = [a for a in acqs if a.key not in state.decided and a.key not in summary.failed]
    capped = summary.exit_code == EXIT_CAP and left
    state.resume = min(a.datetime.date() for a in left).isoformat() if capped else None
    state.save(folder / "state.json")
    write_views(folder)
    return summary


def build_baseline(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
                   prepared: Setup | None = None) -> dict[str, Any]:  # fmt: skip
    """Measure NIR/red, NDTI and the station windows on the baseline's scenes, once.

    With ``ndti_scenes`` the scenes are the validation's frozen usable ones, and NDTI is measured
    again as a reproduction check. Without it, every acquisition from ``baseline_start`` to
    ``baseline_end`` is decided here: SCL first (the screening's observable rule), then the bands
    of the observable ones; the scene's own exclusion rule decides which enter the history.

    A rerun keeps the scenes already in the baseline files and measures only the missing ones; the
    network cap counts the earlier run's estimate too.

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
    s = prepared or setup(cfg, root, site_id, cache, workers, need_cards=False)
    reach = s.reach
    cap_gb = reach.baseline_max_gb or cfg.budgets.baseline_max_gb
    frozen_mode = reach.ndti_scenes is not None
    ndti = (frozen_ndti(root / reach.ndti_scenes, site_id, reach.baseline_end)
            if reach.ndti_scenes else {})  # fmt: skip
    if frozen_mode:
        days = sorted(v["date"] for v in ndti.values())
        first, last = days[0] - timedelta(days=1), days[-1] + timedelta(days=1)
    else:
        assert reach.baseline_start is not None  # checked by the settings
        first, last = reach.baseline_start, reach.baseline_end
    acqs, sun = imagery.search(s.quality, "earth-search", _bbox(s.site), first, last)
    ordered = sorted(acqs, key=lambda a: (a.datetime, a.key))
    wanted = [a for a in ordered if a.key in ndti] if frozen_mode else ordered
    scene_mb = corridor_mb(s.corridor.grid) + (BAND_MB["earth-search"] if s.station else 0.0)
    path = root / reach.nir_red_baseline
    windows_path = path.with_name("station-windows.csv")
    info_path = path.with_name("baseline.json")
    kept = {r["key"]: r for r in _rows(path)}
    kept_windows: dict[str, list[dict[str, Any]]] = {}
    for r in _rows(windows_path):
        kept_windows.setdefault(r["key"], []).append(r)
    earlier = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else {}
    rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    spent = float(earlier.get("network_gb_estimated", 0.0)) * 1000 if kept else 0.0
    stopped = ""
    nan = math.nan
    for acq in wanted:
        if acq.key in kept:
            rows.append(kept[acq.key])
            window_rows += kept_windows.get(acq.key, [])
            continue
        if spent / 1000 >= cap_gb:
            stopped = f"network cap of {cap_gb:g} GB reached"
            break
        check_disk(root, cfg.budgets.keep_free_gb)
        day = ndti[acq.key]["date"] if frozen_mode else extract.local_date(acq, s.quality.timezone)
        if not frozen_mode:
            spent += SCL_MB * 5
            if not m.observable(acq, s.reader, s.full, s.screening):
                s.reader.forget(acq)
                rows.append({"key": acq.key, "date": day.isoformat(),
                             "exclusion": "not observable", "ndti_upstream": nan,
                             "ndti_downstream": nan, "frozen_ndti_upstream": nan,
                             "frozen_ndti_downstream": nan, "nir_red_upstream": nan,
                             "nir_red_downstream": nan})  # fmt: skip
                continue
        spent += scene_mb
        scene = measure_acquisition(s.corridor, acq, s.reader, s.screening)
        ratio = m.nir_red(s.corridor, acq, s.reader, s.screening)
        if s.station is not None:
            window_rows += values.measure(acq, "earth-search", s.reader, s.station.windows,
                                          s.station.station_id, sun, s.d15, s.screening,
                                          s.quality.timezone)  # fmt: skip
        s.reader.forget(acq)
        frozen = ndti.get(acq.key, {"upstream": nan, "downstream": nan})
        if len(rows) % 10 == 0:
            log.info("%s: baseline scene %d of %d, about %.2f GB read", site_id, len(rows) + 1,
                     len(wanted), spent / 1000)  # fmt: skip
        rows.append({
            "key": acq.key, "date": day.isoformat(), "exclusion": scene.exclusion,
            "ndti_upstream": scene.sub["upstream"].ndti if "upstream" in scene.sub else nan,
            "ndti_downstream": (scene.sub["downstream"].ndti if "downstream" in scene.sub
                                else nan),
            "frozen_ndti_upstream": frozen["upstream"],
            "frozen_ndti_downstream": frozen["downstream"],
            "nir_red_upstream": ratio.get("upstream", nan),
            "nir_red_downstream": ratio.get("downstream", nan),
        })  # fmt: skip
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_csv(rows, BASELINE_COLUMNS))
    windows_path.write_bytes(_csv(window_rows, WINDOW_COLUMNS))
    gaps = [abs(_num(str(r.get(f"ndti_{side}"))) - _num(str(r.get(f"frozen_ndti_{side}"))))
            for r in rows for side in ("upstream", "downstream")]  # fmt: skip
    gaps = [g for g in gaps if math.isfinite(g)]
    usable = sum(1 for r in rows if not r["exclusion"])
    info = {
        "site": site_id, "frozen_scenes": len(ndti) if frozen_mode else None,
        "found": len(wanted), "measured": len(rows), "usable": usable,
        "station": s.station.station_id if s.station else None,
        "network_gb_estimated": round(spent / 1000, 3), "stopped": stopped,
        "ndti_max_abs_difference": round(max(gaps), 6) if gaps else None,
        "code_commit": head(), "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
    }  # fmt: skip
    info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8", newline="\n")
    return info


def write_examples(cfg: ReachConfig, root: Path, site_id: str, records_kept: int = 3,
                   everything: bool = False) -> Path:  # fmt: skip
    """Copy a reach's newest outputs to ``docs/water-quality/reach/<site>/examples/`` (frontend).

    The latest record, the series, the newest records and the ledger's last lines, unchanged, so
    the web can be built against real files; the README says what each field means. With
    ``everything`` (a demo reach): every record (a record file no longer in the outputs leaves),
    the whole ledger, the gauge check, the reach's model cards and ``reach.json`` (the site, the
    estimate station and the baseline's period).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        records_kept: How many of the newest records to copy.
        everything: Copy every record and the files the web reads.

    Returns:
        The examples folder.

    Raises:
        ReachError: Before the reach has a record.
    """
    folder = root / cfg.out / site_id
    files = sorted((folder / "records").glob("*.json"))
    if not files or not (folder / "series.json").exists():
        raise ReachError(f"{site_id}: no records yet; run `reach run` first")
    out = root / "docs" / "water-quality" / "reach" / site_id / "examples"
    (out / "records").mkdir(parents=True, exist_ok=True)
    for name in ("latest.json", "series.json"):
        (out / name).write_bytes((folder / name).read_bytes())
    kept = files if everything else files[-records_kept:]
    if everything:
        names = {p.name for p in kept}
        for stale in (out / "records").glob("*.json"):
            if stale.name not in names:
                stale.unlink()
    for path in kept:
        (out / "records" / path.name).write_bytes(path.read_bytes())
    lines = (folder / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    if not everything:
        tail = "\n".join(lines[-(records_kept + 2) :]) + "\n"
        (out / "ledger.tail.jsonl").write_text(tail, encoding="utf-8", newline="\n")
        return out
    (out / "ledger.tail.jsonl").unlink(missing_ok=True)
    (out / "ledger.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for name in ("checks.csv", "summary.json"):
        if (folder / check.FOLDER / name).exists():
            (out / check.FOLDER).mkdir(exist_ok=True)
            (out / check.FOLDER / name).write_bytes((folder / check.FOLDER / name).read_bytes())
    reach = cfg.reach(site_id)
    for target, card in reach.cards.items():
        (out / "cards").mkdir(exist_ok=True)
        (out / "cards" / f"{target}.json").write_bytes((root / card).read_bytes())
    # v6: water temperature (its own records and ledger) and the gauge's context at each pass.
    temperature = temperature_card(root, site_id)
    if temperature.exists():
        (out / "cards").mkdir(exist_ok=True)
        (out / "cards" / "water_temperature.json").write_bytes(temperature.read_bytes())
    thermal = folder / "thermal"
    if (thermal / "series.json").exists():
        (out / "thermal" / "records").mkdir(parents=True, exist_ok=True)
        for path in thermal.glob("records/*.json"):
            (out / "thermal" / "records" / path.name).write_bytes(path.read_bytes())
        for name in ("series.json", "ledger.jsonl", "checks.csv"):
            if (thermal / name).exists():
                (out / "thermal" / name).write_bytes((thermal / name).read_bytes())
    if (folder / check.FOLDER / "context.csv").exists():
        (out / check.FOLDER).mkdir(exist_ok=True)
        (out / check.FOLDER / "context.csv").write_bytes(
            (folder / check.FOLDER / "context.csv").read_bytes()
        )
    info = json.dumps(reach_info(cfg, root, site_id), indent=2) + "\n"
    (out / "reach.json").write_text(info, encoding="utf-8", newline="\n")
    return out


def temperature_card(root: Path, site_id: str) -> Path:
    """Where a reach's water-temperature card lives (preregistration v6).

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        The path (it may not exist: only some reaches have one).
    """
    return root / "docs/water-quality/results/models" / site_id / "water_temperature.json"


def reach_info(cfg: ReachConfig, root: Path, site_id: str) -> dict[str, Any]:
    """What the web shows about a reach beside its records.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        The site, the estimate station, the targets, the baseline's period and the card files
        (with the water-temperature card where the reach has one).
    """
    reach = cfg.reach(site_id)
    site = load_site(reach.site_path(root))
    quality = load_quality_config(root / cfg.quality_config)
    row = station_row(reach, quality, root) or {}
    baseline = root / reach.nir_red_baseline
    days = sorted(r["date"] for r in _rows(baseline) if not r.get("exclusion"))
    station: dict[str, Any] = {"id": reach.estimate_station, "source": reach.station_source,
                               "name": row.get("name", "")}  # fmt: skip
    if reach.station_source == "usgs":
        station["url"] = f"https://waterdata.usgs.gov/monitoring-location/{reach.estimate_station}/"
    if reach.estimate_point is not None:  # no gauge: the window's point and why it is there
        p = reach.estimate_point
        station["window"] = {"lon": p.lon, "lat": p.lat, "basis": p.basis,
                             "sourceUrl": p.source_url}  # fmt: skip
    files = {t: f"cards/{t}.json" for t in reach.cards}
    if temperature_card(root, site_id).exists():
        files["water_temperature"] = "cards/water_temperature.json"
    return {
        "site": site_id, "name": site.name, "river": site.river, "timezone": reach.timezone,
        "station": station, "targets": list(reach.targets),
        "cards": files,
        "baseline": {"first": days[0] if days else None, "last": days[-1] if days else None,
                     "usableScenes": len(days)},
    }  # fmt: skip


def frozen_cards(root: Path, reach: Reach) -> set[str]:
    """The canonical hashes of the cards frozen in the folder of a reach's declared cards.

    A reach whose card changed (preregistration-four-classes.md) keeps the records sealed with
    the earlier one; that card is frozen (``docs/ledgers/frozen-artifacts.jsonl``), so a record
    may name it.

    Args:
        root: Repository root.
        reach: The reach.

    Returns:
        The hashes (empty for a reach that declares no card).
    """
    folders = {Path(p).parent.as_posix() for p in reach.cards.values()}
    path = root / "docs" / "ledgers" / "frozen-artifacts.jsonl"
    if not folders or not path.exists():
        return set()
    lines = [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]
    return {x["canonicalSha256"] for x in lines
            if "canonicalSha256" in x and Path(x["path"]).parent.as_posix() in folders}  # fmt: skip


def values_anchored(root: Path) -> bool:
    """Whether an ungauged class carries its value yet (preregistration-values.md is anchored).

    Args:
        root: Repository root.

    Returns:
        True once that file's line is anchored.
    """
    from climate_pipeline.reach.along import anchored

    return anchored(root, records.VALUES_PREREGISTRATION)


def reread(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
           prepared: Setup | None = None, config_path: Path | None = None
           ) -> RunSummary:  # fmt: skip
    """Read again, with the reach's current card, every pass whose record names another card.

    Also, once preregistration-values.md is anchored, every pass whose class has no value yet.
    Preregistration-four-classes.md, section 4: each pass is measured again and sealed as a new
    record that names the one it replaces (``supersedes``), appended to the same ledger. The
    earlier record stays, unchanged. The rain flags are the earlier record's (the same pass). A
    pass the catalogue no longer lists, or that its exclusion rule now drops, keeps its record.
    Running it again finds nothing left to read.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads.
        prepared: A setup already loaded (tests).
        config_path: The settings file (its hash is the records' parameters hash).

    Returns:
        The summary (``recorded``: the new records).
    """
    check_disk(root, cfg.budgets.keep_free_gb)
    summary = RunSummary(EXIT_OK)
    folder = root / cfg.out / site_id
    ledger = folder / "ledger.jsonl"
    if not ledger.exists():
        return summary
    s = prepared or setup(cfg, root, site_id, cache, workers)
    hashes = {t: cards.card_hash(c) for t, c in s.cards.items()}
    lines = [json.loads(t) for t in ledger.read_text(encoding="utf-8").splitlines() if t.strip()]
    sealed = [v2.ObservationRecordV2.model_validate_json(
        (folder / x["file"]).read_text(encoding="utf-8")) for x in lines]  # fmt: skip
    replaced = {r.supersedes for r in sealed if r.supersedes is not None}
    with_value = values_anchored(root)
    # A record to read again: it names another card, or (once preregistration-values.md is
    # anchored) it has a class without the value it was made from.
    stale = [r for r in sealed if r.record_sha256 not in replaced and any(
        (e.model_card_sha256 and e.target in hashes and e.model_card_sha256 != hashes[e.target])
        or (with_value and e.fnu_class is not None and e.value is None)
        for e in r.estimates)]  # fmt: skip
    if not stale:
        return summary
    days = sorted(date.fromisoformat(r.date) for r in stale)
    acqs, sun = imagery.search(s.quality, "earth-search", _bbox(s.site), days[0],
                               days[-1] + timedelta(days=1))  # fmt: skip
    by_key = {a.key: a for a in acqs}
    baseline = load_baseline(s)
    lab = root / s.quality.outputs.inputs / "lab"
    guards = s.quality.window.as_calibration()
    settings = config_path or root / "pipeline" / "reach.yaml"
    params = hashlib.sha256(b"".join(p.read_bytes() for p in (
        settings, root / cfg.screening_config, root / cfg.quality_config))).hexdigest()  # fmt: skip
    commit = head()
    created = datetime.now(UTC).isoformat(timespec="seconds")
    for old in sorted(stale, key=lambda r: (r.date, r.scene_id)):
        key = old.scene_id.split(":", 1)[1]
        acq = by_key.get(key)
        if acq is None:
            summary.failed[key] = "the pass is no longer in the catalogue"
            continue
        try:
            measure = m.measure(acq, s.reader, s.corridor, s.station, s.window, sun, s.quality,
                                s.d15, s.screening)  # fmt: skip
            if measure.exclusion:
                summary.skipped[key] = f"excluded now: {measure.exclusion}; the record stays"
                continue
            estimates = [
                records.estimate(s.cards.get(t.id), hashes.get(t.id, ""), t, measure,
                                 baseline.estimates.get(t.id, []), guards, lab, with_value)
                for t in s.quality.targets if t.id in s.reach.targets
            ]  # fmt: skip
            rec = records.record(site_id, measure, baseline, estimates, old.rain,
                                 set(s.reach.rainy_months), s.screening, cfg.threshold, commit,
                                 params, supersedes=old.record_sha256)  # fmt: skip
        except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run retries
            log.warning("%s failed: %s", key, error)
            summary.failed[key] = str(error)
            summary.exit_code = EXIT_PARTIAL
            continue
        assert rec.record_sha256 is not None  # sealed
        file = f"records/{rec.date}_{key}.{rec.record_sha256[:12]}.json"
        (folder / file).write_text(rec.model_dump_json(indent=2, by_alias=True) + "\n",
                                   encoding="utf-8", newline="\n")  # fmt: skip
        append_ledger(ledger, rec, file, created)
        log.info("%s: %s read again as %s", site_id, old.scene_id, file)
        summary.recorded.append(file)
    write_views(folder)
    return summary


def verify_outputs(cfg: ReachConfig, root: Path, site_id: str) -> list[str]:
    """Check a reach's published outputs: every record's seal, the ledger and the cards.

    A record whose JSON was edited no longer matches its ``recordSha256``; a ledger line edited,
    removed or reordered breaks the chain; a record that names another hash than its file's, or
    a card whose hash differs from the one a record names, is reported too.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        One line per problem (empty when everything checks out).
    """
    folder = root / cfg.out / site_id
    problems: list[str] = []
    if not (folder / "ledger.jsonl").exists():
        return [f"{site_id}: no ledger yet"]
    if not ledger_ok(folder / "ledger.jsonl"):
        problems.append("ledger.jsonl: a line does not name the hash of the line before it")
    lines = [json.loads(t) for t in (folder / "ledger.jsonl").read_text(encoding="utf-8")
             .splitlines() if t.strip()]  # fmt: skip
    published = reach_cards(cfg, cfg.reach(site_id), root, strict=False)
    cards_now = {t: cards.card_hash(c) for t, c in published.items()}
    earlier = frozen_cards(root, cfg.reach(site_id))
    for line in lines:
        path = folder / line["file"]
        if not path.exists():
            problems.append(f"{line['file']}: in the ledger but missing")
            continue
        try:
            rec = v2.ObservationRecordV2.model_validate_json(path.read_text(encoding="utf-8"))
        except ValueError as error:
            problems.append(f"{line['file']}: not a valid record ({str(error)[:80]})")
            continue
        if not v2.is_sealed(rec):
            problems.append(f"{line['file']}: its content no longer matches its recordSha256")
        if rec.record_sha256 != line["recordSha256"]:
            problems.append(f"{line['file']}: the ledger names another record hash")
        for e in rec.estimates:
            named = e.model_card_sha256
            if (named and e.target in cards_now and named != cards_now[e.target]
                    and named not in earlier):  # fmt: skip
                problems.append(f"{line['file']}: its {e.target} card is not the published one")
    return problems
