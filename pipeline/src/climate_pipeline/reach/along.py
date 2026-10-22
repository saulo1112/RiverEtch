"""Turbidity classes along a whole reach (preregistration-along-river.md).

A record's estimate is read on one window: the station's, or a reach's reading spot. This module
reads the same kind of window all along the reach. Its windows are placed on the reach's frozen
centreline every ``SPACING_M``, from ``FIRST_M`` downstream of its upstream end; each is snapped to
the main channel and sized exactly as a station's window (``extract.evaluate_channel``,
``calibration.stations.window_mask``), on the reach's own water-frequency layer (the same SCL rule
and period as the station geometry). The plan of windows is geometry only, written and frozen
(``docs/water-quality/reach/<site>/along/windows.json``) before any of them is read.

Each pass that has an observation record is then read on every window, all in one read of the
scene over a grid that holds every window, and given a class by the frozen four-class transfer
card (the model tested on rivers it never saw), or an abstention with its reason. The classes of
one pass form an along-river record, sealed like an observation record (the SHA-256 of its
canonical JSON) and chained in the reach's own ``along`` ledger.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.stations import largest_component, window_mask
from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.provenance import head
from climate_pipeline.quality import cards, imagery
from climate_pipeline.reach import measure as m
from climate_pipeline.reach import records
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening import rio
from climate_pipeline.screening.mask import path_chainage
from climate_pipeline.screening.rio import Grid
from climate_pipeline.screening.stac import Acquisition

log = logging.getLogger(__name__)

SPACING_M = 600.0  # one window every 600 m: 300 m windows touch, never overlap
FIRST_M = 300.0  # the first window's centre, downstream of the centreline's upstream end
SCHEMA = "riveretch.along-river.v1"
# The four-class transfer card that reads a reach's windows: the US card for every US reach, the
# reach's own card outside the tested region (preregistration-along-river.md, section 3).
US_CARD = "docs/water-quality/ungauged/mississippi-st-joseph/turbidity-4.json"
NOT_PLACED = "no main channel here"
PREREGISTRATION = "docs/water-quality/preregistration-along-river.md"
FROZEN_LABEL = "terrachain:riveretch:frozen-artifacts"


def anchored(root: Path, preregistration: str = PREREGISTRATION) -> bool:
    """Whether a preregistration is listed and its line anchored on Sepolia.

    Its line in ``docs/ledgers/frozen-artifacts.jsonl`` must be covered by an anchor of that
    ledger in ``docs/ledgers/anchors.jsonl`` (rebuilt from the chain): until then nothing is read.

    Args:
        root: Repository root.
        preregistration: Its repository-relative path (this module's by default).

    Returns:
        True once an anchor covers the line.
    """
    frozen = root / "docs" / "ledgers" / "frozen-artifacts.jsonl"
    log_path = root / "docs" / "ledgers" / "anchors.jsonl"
    if not frozen.exists() or not log_path.exists():
        return False
    lines = [json.loads(t) for t in frozen.read_text(encoding="utf-8").splitlines() if t.strip()]
    position = next((k + 1 for k, x in enumerate(lines) if x["path"] == preregistration), None)
    if position is None:
        return False
    anchors = [json.loads(t) for t in log_path.read_text(encoding="utf-8").splitlines()
               if t.strip()]  # fmt: skip
    return any(a["label"] == FROZEN_LABEL and int(a["lines"]) >= position for a in anchors)


@dataclass(frozen=True)
class Window:
    """One window along the reach: where it sits, its width, and whether it can be read."""

    id: str
    chainage_m: float
    lon: float
    lat: float
    width_m: float
    snap_m: float
    selected: bool
    reason: str


def plan_path(root: Path, site_id: str) -> Path:
    """Where a reach's frozen plan of windows lives (beside its baseline).

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        ``docs/water-quality/reach/<site>/along/windows.json``.
    """
    return root / "docs" / "water-quality" / "reach" / site_id / "along" / "windows.json"


def folder(cfg: ReachConfig, root: Path, site_id: str) -> Path:
    """Where a reach's along-river records and ledger live (beside its observation records).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        ``<out>/<site>/along``.
    """
    return root / cfg.out / site_id / "along"


def card_path(cfg: ReachConfig, site_id: str) -> str:
    """The card that reads a reach's windows (repository-relative).

    Args:
        cfg: Reach settings.
        site_id: The reach.

    Returns:
        The reach's own turbidity card outside the tested region; the US card otherwise.
    """
    reach = cfg.reach(site_id)
    own = reach.cards.get("turbidity", "")
    return own if "/ungauged/" in own and site_id != "mississippi-st-joseph" else US_CARD


def _geometries(s: reach_run.Setup) -> list[tuple[Window, extract.StationGeometry | None]]:
    full = s.full
    geo = full.geometry
    if full.frequency is None or not geo.centerline:
        raise reach_run.ReachError(f"{s.reach.site}: no water frequency or centreline")
    st = s.d15.stations  # the station geometry's own rule (calibration.yaml)
    main = largest_component(np.nan_to_num(full.frequency, nan=0.0) >= st.water_frequency_min)
    chain = path_chainage(geo.centerline, full.grid.resolution)
    out: list[tuple[Window, extract.StationGeometry | None]] = []
    at = FIRST_M
    while at <= float(chain[-1]):
        k = min(int(np.searchsorted(chain, at)), len(geo.centerline) - 1)
        wid = f"w{len(out) + 1:02d}"
        g = extract.evaluate_channel(wid, full.grid, main, geo.centerline[k], full.mask_source, st)
        pixel = g.snapped if g.snapped is not None else geo.centerline[k]
        lon, lat = rio.rowcols_lonlat(full.grid, [pixel[0]], [pixel[1]])[0]
        window = Window(wid, round(at, 1), round(lon, 6), round(lat, 6),
                        round(g.width_m, 1) if math.isfinite(g.width_m) else math.nan,
                        round(g.snap_m, 1) if math.isfinite(g.snap_m) else math.nan,
                        g.selected, g.reason)  # fmt: skip
        out.append((window, g if g.selected else None))
        at += SPACING_M
    return out


def plan(s: reach_run.Setup) -> list[Window]:
    """The reach's windows (geometry only: no pass is read).

    Args:
        s: The reach's setup.

    Returns:
        The windows, upstream first.

    Raises:
        ReachError: When the reach has no water frequency or centreline.
    """
    return [w for w, _ in _geometries(s)]


def _num(x: float) -> float | None:
    return x if math.isfinite(x) else None


def plan_document(site_id: str, windows: list[Window], card: str) -> dict[str, Any]:
    """The plan as published (``windows.json``).

    Args:
        site_id: The reach.
        windows: The windows.
        card: The card that reads them (repository-relative).

    Returns:
        The document.
    """
    return {
        "site": site_id, "spacingM": SPACING_M, "firstM": FIRST_M,
        "card": card,
        "windows": [{"id": w.id, "chainageM": w.chainage_m, "lon": w.lon, "lat": w.lat,
                     "widthM": _num(w.width_m), "snapM": _num(w.snap_m), "selected": w.selected,
                     "reason": w.reason} for w in windows],
    }  # fmt: skip


def _write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def write_plan(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8
               ) -> Path:  # fmt: skip
    """Write the reach's plan of windows, once (an existing plan is frozen and kept).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads.

    Returns:
        The plan's path.
    """
    path = plan_path(root, site_id)
    if path.exists():
        return path
    s = reach_run.setup(cfg, root, site_id, cache, workers)
    _write_json(path, plan_document(site_id, plan(s), card_path(cfg, site_id)))
    return path


def _same_plan(frozen: dict[str, Any], windows: list[Window]) -> bool:
    now = plan_document(str(frozen["site"]), windows, str(frozen["card"]))
    return bool(now["windows"] == frozen["windows"])


def _grid(s: reach_run.Setup, placed: list[tuple[Window, extract.StationGeometry]]
          ) -> extract.Windows:  # fmt: skip
    """One read grid holding every window, each window's two masks on it (a station's masks)."""
    full = s.full.grid
    res = full.resolution
    w = s.quality.window
    radius = w.radius_m / res
    half = math.ceil(s.quality.imagery.read_half_size_m / res) + 2
    rows = [g.snapped[0] for _, g in placed if g.snapped is not None]
    cols = [g.snapped[1] for _, g in placed if g.snapped is not None]
    r0, c0 = max(0, min(rows) - half), max(0, min(cols) - half)
    r1, c1 = min(full.height, max(rows) + half + 1), min(full.width, max(cols) + half + 1)
    grid = Grid(full.epsg, res, full.x0 + c0 * res, full.y0 - r0 * res, c1 - c0, r1 - r0)
    main = placed[0][1].main[r0:r1, c0:c1]
    core = math.ceil(w.core_min_distance_m / res)
    masks: dict[str, Any] = {}
    for window, g in placed:
        assert g.snapped is not None  # placed windows are snapped
        center = (g.snapped[0] - r0, g.snapped[1] - c0)
        masks[f"{window.id}|300m"] = window_mask(main, center, radius, w.erosion_px)
        masks[f"{window.id}|core"] = window_mask(main, center, radius, core)
    return extract.Windows(grid, masks)


def seal(doc: dict[str, Any]) -> str:
    """An along-river record's seal, as an observation record's.

    The SHA-256 of its canonical JSON: keys sorted, no spaces, the seal itself left out.

    Args:
        doc: The record.

    Returns:
        The hex digest.
    """
    body = {k: v for k, v in doc.items() if k != "recordSha256"}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _classes(s: reach_run.Setup, acq: Acquisition, sun: dict[str, float], grid: extract.Windows,
             plan_windows: list[Window], card: dict[str, Any], card_sha: str,
             lab: Path) -> list[dict[str, str]]:  # fmt: skip
    """Every window's class for one pass, or why it has none, in the plan's order."""
    placed = [w for w in plan_windows if w.selected]
    names = [f"{w.id}|{k}" for w in placed for k in ("300m", "core")]
    stats = extract.measure_window(acq, s.reader, grid, names, s.d15, s.screening)
    base = {
        "source": "earth-search", "key": acq.key,
        "datetime_utc": acq.datetime.astimezone(UTC).isoformat(timespec="seconds"),
        "local_date": extract.local_date(acq, s.quality.timezone).isoformat(),
        "family": extract.family(acq), "sun_zenith": imagery.acquisition_sun(acq, sun),
    }  # fmt: skip
    target = next(t for t in s.quality.targets if t.id == "turbidity")
    guards = s.quality.window.as_calibration()
    window_name = str(card["window"])
    out: list[dict[str, str]] = []
    for w in plan_windows:
        if not w.selected:
            out.append({"id": w.id, "abstainReason": NOT_PLACED})
            continue
        rows = [{**base, "station": w.id, "window": k, **stats[f"{w.id}|{k}"]}
                for k in ("300m", "core")]  # fmt: skip
        scenes = m.scene_rows(rows, m.Station(w.id, w.width_m, grid), s.quality)
        scene = scenes.get(window_name)
        measure = records.Measure(
            key=acq.key, day=extract.local_date(acq, s.quality.timezone), items=m.items(acq),
            exclusion="", ndti={}, nir_red={},
            window=scene.features if scene else {}, stats=scene.stats if scene else {},
            window_problem="" if scene else "the window was not measured",
        )  # fmt: skip
        e = records.estimate(card, card_sha, target, measure, [], guards, lab)
        if e.fnu_class is not None:
            out.append({"id": w.id, "fnuClass": str(e.fnu_class)})
        else:
            out.append({"id": w.id, "abstainReason": e.abstain_reason or "no class"})
    return out


def _ledger_lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]


def _append(path: Path, doc: dict[str, Any], file: str, created: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else None
    line = {"sceneId": doc["sceneId"], "date": doc["date"], "recordSha256": doc["recordSha256"],
            "file": file, "createdUtc": created, "previousLineSha256": previous}  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")


def _observations(cfg: ReachConfig, root: Path, site_id: str) -> list[v2.ObservationRecordV2]:
    """The reach's current observation records (a replaced record leaves for its replacement)."""
    out = root / cfg.out / site_id
    lines = _ledger_lines(out / "ledger.jsonl")
    sealed = [v2.ObservationRecordV2.model_validate_json(
        (out / x["file"]).read_text(encoding="utf-8")) for x in lines]  # fmt: skip
    replaced = {r.supersedes for r in sealed if r.supersedes is not None}
    return [r for r in sealed if r.record_sha256 not in replaced]


@dataclass
class Summary:
    """What one ``reach along`` did."""

    recorded: list[str]
    failed: dict[str, str]
    exit_code: int = reach_run.EXIT_OK


def run(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
        http: httpx.Client | None = None) -> Summary:  # fmt: skip
    """Read every pass that has an observation record and no along-river record yet.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        http: Unused (the catalogue client is the reach's own).

    Returns:
        The records written and the passes that failed (the next run retries them).

    Raises:
        ReachError: When the plan is missing or the geometry no longer matches it.
    """
    del http
    if not anchored(root):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    frozen_path = plan_path(root, site_id)
    if not frozen_path.exists():
        raise reach_run.ReachError(f"{site_id}: no frozen plan of windows")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    s = reach_run.setup(cfg, root, site_id, cache, workers)
    geos = _geometries(s)
    windows = [w for w, _ in geos]
    if not _same_plan(frozen, windows):
        raise reach_run.ReachError(f"{site_id}: the geometry no longer matches the frozen plan")
    placed = [(w, g) for w, g in geos if g is not None]
    grid = _grid(s, placed)
    card = json.loads((root / str(frozen["card"])).read_text(encoding="utf-8"))
    card_sha = cards.card_hash(card)
    lab = root / s.quality.outputs.inputs / "lab"
    out = folder(cfg, root, site_id)
    ledger = out / "ledger.jsonl"
    done = {x["sceneId"] for x in _ledger_lines(ledger)}
    todo = sorted((r for r in _observations(cfg, root, site_id) if r.scene_id not in done),
                  key=lambda r: (r.date, r.scene_id))  # fmt: skip
    summary = Summary([], {})
    if todo:
        days = [date.fromisoformat(r.date) for r in todo]
        acqs, sun = imagery.search(s.quality, "earth-search", reach_run._bbox(s.site),
                                   min(days) - timedelta(days=1),
                                   max(days) + timedelta(days=1))  # fmt: skip
        by_key = {a.key: a for a in acqs}
        commit = head()
        created = datetime.now(UTC).isoformat(timespec="seconds")
        (out / "records").mkdir(parents=True, exist_ok=True)
        for rec in todo:
            key = rec.scene_id.split(":", 1)[1]
            acq = by_key.get(key)
            if acq is None:
                summary.failed[key] = "the pass is no longer in the catalogue"
                continue
            try:
                classes = _classes(s, acq, sun, grid, windows, card, card_sha, lab)
            except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run
                log.warning("%s failed: %s", key, error)
                summary.failed[key] = str(error)
                summary.exit_code = reach_run.EXIT_PARTIAL
                continue
            finally:
                s.reader.forget(acq)
            doc: dict[str, Any] = {
                "schema": SCHEMA, "reach": site_id, "sceneId": rec.scene_id, "date": rec.date,
                "observationRecordSha256": rec.record_sha256, "planSha256": plan_sha,
                "card": frozen["card"], "modelCardSha256": card_sha,
                "modelId": card["modelId"], "basis": card["basis"],
                "items": [{"id": i.id, "processingBaseline": i.processing_baseline}
                          for i in m.items(acq)],
                "windows": classes, "codeCommit": commit,
            }  # fmt: skip
            doc["recordSha256"] = seal(doc)
            file = f"records/{rec.date}_{key}.{doc['recordSha256'][:12]}.json"
            _write_json(out / file, doc)
            _append(ledger, doc, file, created)
            summary.recorded.append(file)
    publish(cfg, root, site_id)
    return summary


def series(cfg: ReachConfig, root: Path, site_id: str) -> list[dict[str, Any]]:
    """What the web needs from each along-river record, oldest first.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        One row per pass: its classes and reasons in the plan's order.
    """
    out = folder(cfg, root, site_id)
    rows = []
    for line in _ledger_lines(out / "ledger.jsonl"):
        doc = json.loads((out / line["file"]).read_text(encoding="utf-8"))
        rows.append({
            "sceneId": doc["sceneId"], "date": doc["date"], "recordSha256": doc["recordSha256"],
            "file": line["file"],
            "classes": [w.get("fnuClass") for w in doc["windows"]],
            "reasons": [w.get("abstainReason") for w in doc["windows"]],
        })  # fmt: skip
    return sorted(rows, key=lambda r: (r["date"], r["sceneId"]))


def publish(cfg: ReachConfig, root: Path, site_id: str) -> Path:
    """Copy the plan, the ledger, the records and the web's series beside the examples.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        ``examples/along/``.
    """
    out = folder(cfg, root, site_id)
    dest = root / "docs" / "water-quality" / "reach" / site_id / "examples" / "along"
    (dest / "records").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(plan_path(root, site_id), dest / "windows.json")
    if (out / "ledger.jsonl").exists():
        shutil.copyfile(out / "ledger.jsonl", dest / "ledger.jsonl")
        for line in _ledger_lines(out / "ledger.jsonl"):
            shutil.copyfile(out / line["file"], dest / line["file"])
    _write_json(dest / "series.json", series(cfg, root, site_id))
    return dest


def verify(cfg: ReachConfig, root: Path, site_id: str) -> list[str]:
    """Check a reach's along-river outputs: every seal, the chain, the plan and the card.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        One line per problem (empty when everything checks out, or the reach has none).
    """
    out = folder(cfg, root, site_id)
    lines = _ledger_lines(out / "ledger.jsonl")
    if not lines:
        return []
    problems = []
    if not reach_run.ledger_ok(out / "ledger.jsonl"):
        problems.append("along/ledger.jsonl: a line does not name the hash of the line before it")
    plan_sha = hashlib.sha256(plan_path(root, site_id).read_bytes()).hexdigest()
    for line in lines:
        doc = json.loads((out / line["file"]).read_text(encoding="utf-8"))
        if seal(doc) != doc.get("recordSha256") or doc["recordSha256"] != line["recordSha256"]:
            problems.append(f"along/{line['file']}: its content no longer matches its seal")
        if doc["planSha256"] != plan_sha:
            problems.append(f"along/{line['file']}: it names another plan of windows")
        card = json.loads((root / str(doc["card"])).read_text(encoding="utf-8"))
        if cards.card_hash(card) != doc["modelCardSha256"]:
            problems.append(f"along/{line['file']}: its card is not the published one")
    return problems
