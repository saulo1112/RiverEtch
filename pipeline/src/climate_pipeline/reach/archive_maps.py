"""The earlier years' images, 2019 to 2025, on the map (preregistration-archive-maps.md).

The earlier years' passes (``archive.run``) keep no image. This module draws, for every pass a
reach's ``archive/<year>.json`` lists and only those, the same two images a 2026 record's pass has,
with the same code on the same frame (``render.scene_map`` and ``render.true_color`` over
``render.Frame``): the NDTI map and the true-colour image. Nothing is read or estimated, and the
year's file is not changed. A year's index is written after every pass, so an interrupted run
resumes where it stopped. The images are published on the ``data`` branch only, never on ``main``.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any

import httpx
from PIL import Image

from climate_pipeline.provenance import head
from climate_pipeline.quality import imagery
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.reach import along, archive, render
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig
from climate_pipeline.screening import rio

log = logging.getLogger(__name__)

SCHEMA = "riveretch.archive-maps.v1"
PREREGISTRATION = "docs/water-quality/preregistration-archive-maps.md"
KIND = "archive-maps"


def _write(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip


def frame_of(frame: render.Frame) -> dict[str, Any]:
    """The images' grid: the size and corners of the reach's ``maps.json`` (section 2).

    Args:
        frame: The reach's cropped corridor.

    Returns:
        ``width``, ``height`` and ``corners`` (WGS84), as ``render.render`` writes them.
    """
    grid10 = frame.grid.with_resolution(10.0)
    return {"width": grid10.width, "height": grid10.height,
            "corners": [[round(lon, render.DIGITS), round(lat, render.DIGITS)]
                        for lon, lat in rio.corners_lonlat(grid10)]}  # fmt: skip


def run(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8,
        years: tuple[int, ...] = archive.YEARS) -> archive.Summary:  # fmt: skip
    """Draw the images of a reach's earlier passes, those its years' files list (resumable).

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.
        years: The years to draw (2019 to 2025).

    Returns:
        How many passes were drawn, and which failed (the next run retries them).

    Raises:
        ReachError: Before the anchor, or for a year that was never read.
    """
    if not along.anchored(root, PREREGISTRATION):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    sources = {year: archive.folder(root, site_id) / f"{year}.json" for year in years}
    unread = [year for year, path in sources.items() if not path.exists()]
    if unread:
        raise reach_run.ReachError(f"{site_id}: no earlier year's file for {unread}")
    s = reach_run.setup(cfg, root, site_id, cache, workers, need_cards=False)
    frame = render.Frame(s)
    grid = frame_of(frame)
    examples = archive.folder(root, site_id, KIND).parent
    out = archive.folder(root, site_id, KIND)
    commit = head()
    summary = archive.Summary()
    for year, source in sources.items():
        listed = json.loads(source.read_text(encoding="utf-8"))["passes"]
        path = out / f"{year}.json"
        doc: dict[str, Any] = (json.loads(path.read_text(encoding="utf-8")) if path.exists()
                               else {"schema": SCHEMA, "reach": site_id, "year": year,
                                     "codeCommit": commit, **grid, "maps": [], "missing": [],
                                     "failed": {}})  # fmt: skip
        drawn = {m["sceneId"] for m in doc["maps"]}
        todo = [p for p in listed if p["sceneId"] not in drawn]
        by_key: dict[str, Any] = {}
        if todo:
            acqs, _ = imagery.search(s.quality, "earth-search", reach_run._bbox(s.site),
                                     date(year, 1, 1), date(year, 12, 31))  # fmt: skip
            by_key = {a.key: a for a in acqs}
        for p in todo:
            scene_id = p["sceneId"]
            key = scene_id.split(":", 1)[1]
            acq = by_key.get(key)
            if acq is None:  # the catalogue no longer lists it
                if scene_id not in doc["missing"]:
                    doc["missing"].append(scene_id)
                _write(path, doc)
                continue
            name, photo = f"{KIND}/{year}/{key}.png", f"{KIND}/{year}/{key}.rgb.webp"
            try:
                check_disk(root, cfg.budgets.keep_free_gb)
                (examples / name).parent.mkdir(parents=True, exist_ok=True)
                if not (examples / name).exists():
                    rgba = render.scene_map(s, frame, acq)
                    Image.fromarray(rgba, "RGBA").save(examples / name, format="PNG",
                                                       optimize=True)  # fmt: skip
                if not (examples / photo).exists():
                    Image.fromarray(render.true_color(s, frame, acq), "RGB").save(
                        examples / photo, format="WEBP", quality=render.TRUE_COLOR["quality"],
                        method=6)  # fmt: skip
            except (httpx.HTTPError, OSError, RuntimeError) as error:  # transient: next run
                log.warning("%s failed: %s", key, error)
                doc["failed"][key] = str(error)[:200]
                summary.failed[key] = str(error)
                summary.exit_code = reach_run.EXIT_PARTIAL
                _write(path, doc)
                continue
            finally:
                s.reader.forget(acq)
            doc["failed"].pop(key, None)
            if scene_id in doc["missing"]:
                doc["missing"].remove(scene_id)
            doc["maps"].append({"key": key, "sceneId": scene_id, "date": p["date"],
                                "file": name, "trueColor": photo})  # fmt: skip
            doc["maps"].sort(key=lambda e: (e["date"], e["sceneId"]))
            _write(path, doc)
            summary.read += 1
            log.info("%s: drew %s", site_id, name)
        _write(path, doc)
    return summary
