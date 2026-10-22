"""Water temperature classes along a whole reach (preregistration-along-temperature.md).

A water-temperature record reads one window: the station's core, on Landsat's 30 m pixels. This
module reads the same kind of window all along the reach: the windows of the reach's frozen plan
(preregistration-along-river.md), each window's core carried to Landsat's pixels exactly as the
station's is (``variables.grid30``). Each Landsat pass that has a water-temperature record is read
once, over a grid that holds every window; each window's median surface temperature of its
clear-water pixels goes through the reach's frozen card, exactly as a record's estimate does
(``thermal.estimate``), and becomes one of six classes, or an abstention with its reason. The
classes of one pass form an along-river temperature record, sealed as the along-river turbidity
records are (the SHA-256 of its canonical JSON) and chained in the reach's own ledger.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import shutil
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import numpy as np

from climate_pipeline.contract import thermal as thermal_contract
from climate_pipeline.provenance import head
from climate_pipeline.quality import cards, landsat, variables
from climate_pipeline.reach import along, thermal
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening.rio import AcquisitionReader, Grid
from climate_pipeline.screening.stac import Acquisition, group_acquisitions, search_items

log = logging.getLogger(__name__)

SCHEMA = "riveretch.along-temperature.v1"
PREREGISTRATION = "docs/water-quality/preregistration-along-temperature.md"
# The six classes and their edges in °C (section 2): a value on an edge is in the upper class.
EDGES = (10.0, 15.0, 20.0, 25.0, 30.0)
CLASSES = ("under_10", "10_to_15", "15_to_20", "20_to_25", "25_to_30", "30_and_over")
TOO_FEW = "too few clear water pixels"
OUTSIDE = "surface temperature outside the card's input range"


def temperature_class(value: float) -> str | None:
    """The preregistered class of a water-temperature estimate.

    Args:
        value: The estimate in °C.

    Returns:
        The class (None when the value is not finite).
    """
    if not math.isfinite(value):
        return None
    return CLASSES[sum(value >= e for e in EDGES)]


def folder(cfg: ReachConfig, root: Path, site_id: str) -> Path:
    """Where a reach's along-river temperature records and ledger live.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        ``<out>/<site>/along-temperature``.
    """
    return root / cfg.out / site_id / "along-temperature"


def _thermal_records(cfg: ReachConfig, root: Path, site_id: str
                     ) -> list[thermal_contract.ThermalRecordV1]:  # fmt: skip
    """The reach's water-temperature records, in their ledger's order."""
    out = root / cfg.out / site_id / thermal.FOLDER
    return [thermal_contract.ThermalRecordV1.model_validate_json(
        (out / x["file"]).read_text(encoding="utf-8"))
        for x in along._ledger_lines(out / "ledger.jsonl")]  # fmt: skip


def _windows30(grid: Grid, masks: Mapping[str, np.ndarray], placed: list[along.Window]
               ) -> tuple[Grid, dict[str, np.ndarray]]:  # fmt: skip
    """Each placed window's core on Landsat's 30 m pixels, over one grid holding them all."""
    coarse: Grid | None = None
    out: dict[str, np.ndarray] = {}
    for w in placed:
        coarse, out[w.id] = variables.grid30(masks[f"{w.id}|core"], grid)
    if coarse is None:
        raise reach_run.ReachError("no window is placed along the reach")
    return coarse, out


def classes(acq: Acquisition, reader: AcquisitionReader, grid: Grid,
            cores: dict[str, np.ndarray], plan_windows: list[along.Window],
            card: dict[str, Any]) -> list[dict[str, str]]:  # fmt: skip
    """Every window's class for one Landsat pass, or why it has none, in the plan's order.

    Args:
        acq: The pass.
        reader: Reader signing Landsat assets.
        grid: The 30 m grid holding every window.
        cores: Each placed window's core on that grid.
        plan_windows: The plan's windows.
        card: The reach's water-temperature card.

    Returns:
        One entry per window: ``{"id", "temperatureClass"}`` or ``{"id", "abstainReason"}``.
    """
    qa = np.asarray(reader.read(acq, "qa_pixel", grid)[0]).astype(np.int64)
    clear = ((qa != 0) & ((qa & variables.QA_FILL) == 0) & ((qa & variables.QA_UNUSABLE) == 0)
             & ((qa & variables.QA_WATER) != 0))  # fmt: skip
    dn: np.ndarray | None = None
    minimum = int(card["minWaterPixels"])
    out: list[dict[str, str]] = []
    for w in plan_windows:
        if not w.selected:
            out.append({"id": w.id, "abstainReason": along.NOT_PLACED})
            continue
        water = cores[w.id] & clear
        if int(water.sum()) < minimum:
            out.append({"id": w.id, "abstainReason": TOO_FEW})
            continue
        if dn is None:  # the band is read once, for the first window with enough water
            dn = np.asarray(reader.read(acq, "lwir11", grid)[0]).astype(np.float64)
        values = dn[water & (dn > 0)] * variables.ST_SCALE + variables.ST_OFFSET
        if values.size == 0:
            out.append({"id": w.id, "abstainReason": TOO_FEW})
            continue
        e = thermal.estimate(card, float(np.median(values)))
        cls = temperature_class(e.value) if e.value is not None else None
        out.append({"id": w.id, "temperatureClass": cls} if cls is not None
                   else {"id": w.id, "abstainReason": OUTSIDE})  # fmt: skip
    return out


def run(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
        http: httpx.Client | None = None) -> along.Summary:  # fmt: skip
    """Read every water-temperature pass that has no along-river temperature record yet.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        http: Unused (the catalogue is searched directly).

    Returns:
        The records written and the passes that failed (the next run retries them).

    Raises:
        ReachError: Before the anchor, without a card or a plan, or when the geometry no longer
            matches the plan.
    """
    del http
    if not along.anchored(root, PREREGISTRATION):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    card_file = thermal.card_path(root, site_id)
    if not card_file.exists():
        raise reach_run.ReachError(f"{site_id}: no water-temperature card")
    frozen_path = along.plan_path(root, site_id)
    if not frozen_path.exists():
        raise reach_run.ReachError(f"{site_id}: no frozen plan of windows")
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    plan_sha = hashlib.sha256(frozen_path.read_bytes()).hexdigest()
    s = reach_run.setup(cfg, root, site_id, cache, workers, need_cards=False)
    geos = along._geometries(s)
    windows = [w for w, _ in geos]
    if not along._same_plan(frozen, windows):
        raise reach_run.ReachError(f"{site_id}: the geometry no longer matches the frozen plan")
    placed = [(w, g) for w, g in geos if g is not None]
    fine = along._grid(s, placed)
    grid, cores = _windows30(fine.grid, fine.masks, [w for w, _ in placed])
    card = json.loads(card_file.read_text(encoding="utf-8"))
    card_sha = cards.card_hash(card)
    card_rel = card_file.relative_to(root).as_posix()
    out = folder(cfg, root, site_id)
    ledger = out / "ledger.jsonl"
    done = {x["sceneId"] for x in along._ledger_lines(ledger)}
    todo = sorted((r for r in _thermal_records(cfg, root, site_id) if r.scene_id not in done),
                  key=lambda r: (r.date, r.scene_id))  # fmt: skip
    summary = along.Summary([], {})
    if todo:
        days = [date.fromisoformat(r.date) for r in todo]
        west, south, east, north = s.site.aoi_bbox
        scenes = [scene for item in search_items(landsat.STAC_URL, landsat.COLLECTION,
                                                 (west, south, east, north),
                                                 min(days) - timedelta(days=1),
                                                 max(days) + timedelta(days=1), 100)
                  if (scene := variables.thermal_parse(item)) is not None]  # fmt: skip
        by_key = {a.key: a for a in group_acquisitions(scenes)}
        reader = AcquisitionReader(landsat.source(), cache / "landsat-bands", ("qa_pixel",))
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
                found = classes(acq, reader, grid, cores, windows, card)
            except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run
                log.warning("%s failed: %s", key, error)
                summary.failed[key] = str(error)
                summary.exit_code = reach_run.EXIT_PARTIAL
                continue
            doc: dict[str, Any] = {
                "schema": SCHEMA, "reach": site_id, "sceneId": rec.scene_id, "date": rec.date,
                "thermalRecordSha256": rec.record_sha256, "planSha256": plan_sha,
                "card": card_rel, "modelCardSha256": card_sha, "modelId": card["modelId"],
                "items": [{"id": sc.item_id} for sc in acq.scenes],
                "windows": found, "codeCommit": commit,
            }  # fmt: skip
            doc["recordSha256"] = along.seal(doc)
            file = f"records/{rec.date}_{key}.{doc['recordSha256'][:12]}.json"
            along._write_json(out / file, doc)
            along._append(ledger, doc, file, created)
            summary.recorded.append(file)
    publish(cfg, root, site_id)
    return summary


def series(cfg: ReachConfig, root: Path, site_id: str) -> list[dict[str, Any]]:
    """What the web needs from each along-river temperature record, oldest first.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        One row per pass: its classes and reasons in the plan's order.
    """
    out = folder(cfg, root, site_id)
    rows = []
    for line in along._ledger_lines(out / "ledger.jsonl"):
        doc = json.loads((out / line["file"]).read_text(encoding="utf-8"))
        rows.append({
            "sceneId": doc["sceneId"], "date": doc["date"], "recordSha256": doc["recordSha256"],
            "file": line["file"],
            "classes": [w.get("temperatureClass") for w in doc["windows"]],
            "reasons": [w.get("abstainReason") for w in doc["windows"]],
        })  # fmt: skip
    return sorted(rows, key=lambda r: (r["date"], r["sceneId"]))


def publish(cfg: ReachConfig, root: Path, site_id: str) -> Path:
    """Copy the ledger, the records and the web's series beside the examples.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        ``examples/along-temperature/``.
    """
    out = folder(cfg, root, site_id)
    dest = root / "docs" / "water-quality" / "reach" / site_id / "examples" / "along-temperature"
    (dest / "records").mkdir(parents=True, exist_ok=True)
    if (out / "ledger.jsonl").exists():
        shutil.copyfile(out / "ledger.jsonl", dest / "ledger.jsonl")
        for line in along._ledger_lines(out / "ledger.jsonl"):
            shutil.copyfile(out / line["file"], dest / line["file"])
    along._write_json(dest / "series.json", series(cfg, root, site_id))
    return dest


def verify(cfg: ReachConfig, root: Path, site_id: str) -> list[str]:
    """Check a reach's along-river temperature outputs: every seal, the chain, the plan, the card.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.

    Returns:
        One line per problem (empty when everything checks out, or the reach has none).
    """
    out = folder(cfg, root, site_id)
    lines = along._ledger_lines(out / "ledger.jsonl")
    if not lines:
        return []
    problems = []
    if not reach_run.ledger_ok(out / "ledger.jsonl"):
        problems.append("along-temperature/ledger.jsonl: a line does not name the hash of the "
                        "line before it")  # fmt: skip
    plan_sha = hashlib.sha256(along.plan_path(root, site_id).read_bytes()).hexdigest()
    for line in lines:
        doc = json.loads((out / line["file"]).read_text(encoding="utf-8"))
        name = f"along-temperature/{line['file']}"
        if (
            along.seal(doc) != doc.get("recordSha256")
            or doc["recordSha256"] != line["recordSha256"]
        ):
            problems.append(f"{name}: its content no longer matches its seal")
        if doc["planSha256"] != plan_sha:
            problems.append(f"{name}: it names another plan of windows")
        card = json.loads((root / str(doc["card"])).read_text(encoding="utf-8"))
        if cards.card_hash(card) != doc["modelCardSha256"]:
            problems.append(f"{name}: its card is not the published one")
    return problems
