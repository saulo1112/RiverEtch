"""v4, section C: the scenes RAdCor Stage B needs (preregistration, v2.2 Stage B).

Stage B processes, with ACOLITE RAdCor, the Magdalena pairs of v2's sensitivity set (±1 day, or
±3 days with stable flow, core window) that Route B lacks. This module lists them, without any
value: each acquisition with the Level-1C product of the tile that covers the station window, the
core window's L2A water pixels (so ACOLITE is measured over the pixels the L2A medians used) and
the L2A window rows the runner copies its scene guards from.

Outputs: ``inputs/acolite/stage-b/scenes.csv`` and ``l2a-windows.csv`` (committed), and
``pipeline/out/acolite-work-b/pixels.json`` (derived, not committed). TSS scenes come first: TSS
is due under v2.2's rule, turbidity is the owner's exploratory addition.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import math
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import extract
from climate_pipeline.calibration.acolite import L1C_COLLECTION, SCENE_COLUMNS, datatake, l1c_item
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import _csv, _reader, candidate_of, read_stations
from climate_pipeline.calibration.matchups import Pair, scenes_from_csv
from climate_pipeline.quality import imagery, posthoc, route_a
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.route_b import RouteBInputs
from climate_pipeline.quality.values import WINDOW_COLUMNS
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.stac import Acquisition, search_items

log = logging.getLogger(__name__)
WINDOW = "core"
FOLDER = "acolite/stage-b"
SearchFn = Callable[[tuple[float, float, float, float], date], list[dict[str, Any]]]


def radcor_keys(path: Path) -> set[tuple[str, str]]:
    """The (station, acquisition) pairs Route B already has under RAdCor.

    Args:
        path: ``inputs/acolite/radcor/windows.csv``.

    Returns:
        The keys.
    """
    if not path.exists():
        return set()
    rows = csv.DictReader(io.StringIO(path.read_text(encoding="utf-8")))
    return {(r["station"], r["key"]) for r in rows}


def lacking(cfg: QualityConfig, ci: route_a.ColombianInputs,
            have: set[tuple[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:  # fmt: skip
    """The Magdalena sensitivity-set scenes Route B lacks, with their targets and day.

    Args:
        cfg: Settings.
        ci: The Colombian inputs.
        have: Route B's RAdCor keys.

    Returns:
        (station, key) -> ``targets`` (set) and ``day``.
    """
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for target in cfg.targets:
        for p in route_a.pairs(cfg, ci, target.id, WINDOW, True):
            if ci.stream_of.get(p.station) != cfg.stations.test_stream:
                continue
            k = (p.station, p.scene_key)
            if k in have:
                continue
            entry = out.setdefault(k, {"targets": set(), "day": p.scene_day})
            entry["targets"].add(target.id)
    return out


def l2a_datatake(acq: Acquisition, box: tuple[float, float, float, float]) -> tuple[str, str]:
    """The Level-1C datatake and tile behind an L2A item, when no Level-1C item is listed.

    Earth Search's Level-1C collection lacks some early dates; the L2A item's name carries the
    same datatake (``S2A_MSIL2A_20160906T152642_...`` -> ``S2A_MSIL1C_20160906T152642``).

    Args:
        acq: The L2A acquisition.
        box: The station window's box.

    Returns:
        Datatake and tile (empty when no item covers the box).
    """
    w, s, e, n = box
    for scene in sorted(acq.scenes, key=lambda x: x.item_id):
        m = re.match(r"^(S2[ABC])_MSIL2A_(\d{8}T\d{6})_", scene.item_id)
        bw, bs, be, bn = scene.bbox
        if m and bw <= w and bs <= s and be >= e and bn >= n:
            return f"{m.group(1)}_MSIL1C_{m.group(2)}", scene.mgrs_tile
    return "", ""


def priority(entry: dict[str, Any], station: str) -> tuple[int, date, str]:
    """TSS scenes first (due under v2.2), then by day and station.

    Args:
        entry: ``targets`` and ``day``.
        station: Station id.

    Returns:
        The sort key.
    """
    return (0 if "tss" in entry["targets"] else 1, entry["day"], station)


def scene_list(cfg: QualityConfig, root: Path, cache: Path, work: Path, workers: int,
               search_l1c: SearchFn | None = None) -> list[dict[str, Any]]:  # fmt: skip
    """Write Stage B's scene list, the L2A rows it copies and the pixel file.

    Args:
        cfg: Settings.
        root: Repository root.
        cache: Cache folder.
        work: ``pipeline/out/acolite-work-b`` (the pixel file).
        workers: Parallel reads for the station geometry.
        search_l1c: Level-1C item search by box and day (injectable).

    Returns:
        The scene rows.

    Raises:
        RuntimeError: Before the Colombian value snapshot exists.
    """
    ci = route_a.load(cfg, root)
    if ci is None:
        raise RuntimeError("no Colombian value snapshot yet")
    inputs = root / cfg.outputs.inputs
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    todo = lacking(cfg, ci, radcor_keys(inputs / "acolite" / "radcor" / "windows.csv"))
    l2a = {(r["station"], r["key"]): r
           for r in csv.DictReader(io.StringIO((inputs / "imagery" / "windows.csv")
                                               .read_text(encoding="utf-8")))
           if r["window"] == WINDOW}  # fmt: skip
    stations = {r["station_id"]: r for r in read_stations(inputs / "stations" / "stations.csv")}
    geo_reader = _reader(d15, screening, cache)
    readers = {n: imagery.reader(screening, n, cache) for n in cfg.imagery.sources}

    def default_search(box: tuple[float, float, float, float], day: date) -> list[dict[str, Any]]:
        return search_items(d15.imagery.url, L1C_COLLECTION, box, day, day, 100)

    search = search_l1c or default_search
    order = sorted(todo, key=lambda k: priority(todo[k], k[0]))
    rank = {k: i + 1 for i, k in enumerate(order)}
    rows: list[dict[str, Any]] = []
    l2a_rows: list[dict[str, Any]] = []
    pixel_out: dict[str, Any] = {"stations": {}, "scenes": []}
    for station in sorted({s for s, _ in todo}):
        cand = candidate_of({**stations[station], "files": ""})
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        geo_acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, geo_reader, d15, screening, workers)
        wins = imagery.small_windows(geo, cfg)
        g = wins.grid
        pixel_out["stations"][station] = {
            "epsg": g.epsg, "x0": g.x0, "y0": g.y0, "resolution": g.resolution,
            "width": g.width, "height": g.height, "lon": cand.lon, "lat": cand.lat,
        }  # fmt: skip
        small = extract.bbox_around(cand.lon, cand.lat, cfg.imagery.read_half_size_m)
        box = extract.bbox_around(cand.lon, cand.lat, cfg.window.radius_m + 100)
        for key in sorted(k for s, k in todo if s == station):
            entry, meta = todo[(station, key)], l2a[(station, key)]
            when = datetime.fromisoformat(meta["datetime_utc"]).astimezone(UTC)
            source = cfg.imagery.source_for(when.date())
            acqs, _ = imagery.search(cfg, source, small, when.date() - timedelta(days=1),
                                     when.date() + timedelta(days=1))  # fmt: skip
            acq = next((a for a in acqs if a.key == key), None)
            water = (extract.water_pixels(acq, readers[source], wins, WINDOW, d15, screening)
                     if acq is not None else None)  # fmt: skip
            item = l1c_item(search(box, when.date()), key, box)
            product = str(item["properties"].get("s2:product_uri", "")) if item else ""
            taken, tile = (datatake(product), product.split("_")[5][1:]) if product else ("", "")
            if not product and acq is not None:
                taken, tile = l2a_datatake(acq, box)
            rows.append({
                "priority": rank[(station, key)], "station": station, "key": key,
                "datetime_utc": meta["datetime_utc"], "local_date": meta["local_date"],
                "split": "test", "targets": " ".join(sorted(entry["targets"])),
                "l2a_water_px": int(water.sum()) if water is not None else 0,
                "tile": tile, "l1c_item": str(item["id"]) if item else "",
                "l1c_product": product, "datatake": taken,
            })  # fmt: skip
            l2a_rows.append(meta)
            if water is not None:
                rr, cc = water.nonzero()
                pixel_out["scenes"].append({
                    "station": station, "key": key,
                    "pixels": [[int(r), int(c)] for r, c in zip(rr, cc, strict=True)],
                })  # fmt: skip
            log.info("stage B: %s %s, %s", station, key, product or "no Level-1C item")
    rows.sort(key=lambda r: int(r["priority"]))
    folder = inputs / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "scenes.csv").write_bytes(_csv(rows, SCENE_COLUMNS))
    (folder / "l2a-windows.csv").write_bytes(_csv(l2a_rows, WINDOW_COLUMNS))
    work.mkdir(parents=True, exist_ok=True)
    pixel_out["rg_floor"] = screening.stage2.rg_floor
    pixel_out["timezone"] = cfg.timezone
    (work / "pixels.json").write_text(json.dumps(pixel_out), encoding="utf-8", newline="\n")
    return rows


STATUS = {
    "tss": "confirmatory (due under v2.2's rule)",
    "turbidity": "exploratory (owner's addition)",
}


def finished(folder: Path) -> bool:
    """Whether ACOLITE has decided every listed scene (processed, failed or out of time).

    Args:
        folder: ``inputs/acolite/stage-b``.

    Returns:
        True when the run log names every scene of the list and none still waits.
    """
    log_path, scenes_path = folder / "run-log.csv", folder / "scenes.csv"
    if not log_path.exists() or not scenes_path.exists():
        return False
    log = list(csv.DictReader(io.StringIO(log_path.read_text(encoding="utf-8"))))
    listed = list(csv.DictReader(io.StringIO(scenes_path.read_text(encoding="utf-8"))))
    waiting = {"not_started", "not_downloaded", ""}
    if len(log) != len(listed) or any(r["status"] in waiting for r in log):
        return False
    # The MDN (TSS's R1) must have run on these very windows.
    manifest = folder / "mdn-manifest.csv"
    if not manifest.exists():
        return False
    windows = hashlib.sha256((folder / "windows.csv").read_bytes()).hexdigest()
    rows = csv.DictReader(io.StringIO(manifest.read_text(encoding="utf-8")))
    return any(r["path"] == "windows.csv" and r["sha256"] == windows for r in rows)


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Stage B's nested error and level per target (or its status).

    Args:
        tables: The run's tables.

    Returns:
        Target -> ``mdsa``, ``level``, ``n`` and ``status``; or ``status`` alone.
    """
    out: dict[str, Any] = {}
    for r in tables.get("stage_b_scores", []):
        if "target" not in r:
            return {"status": r.get("status", "")}
        if r.get("evaluation") == "nested LOSO (Stage A + B)":
            lv = f"{r['level']} (post hoc)" if r["level"] != "none" else "none"
            out[r["target"]] = {"mdsa": round(r["mdsa"], 1), "level": lv, "n": int(r["n"]),
                                "status": r["status"]}  # fmt: skip
    return out


def stage_b_pairs(cfg: QualityConfig, ci: route_a.ColombianInputs, text: str, target: str,
                  switch: Any) -> list[Pair]:  # fmt: skip
    """Stage B's pairs: v2's sensitivity-set pairs with RAdCor's medians over their core pixels.

    Args:
        cfg: Settings.
        ci: The Colombian inputs.
        text: ``acolite/stage-b/windows.csv``.
        target: Target id.
        switch: Dogliotti's coefficients (as Route B's).

    Returns:
        The pairs (L2A's scene guards, RAdCor's reflectances).
    """
    rows = {(s.station, s.key): s for s in scenes_from_csv(text, WINDOW, switch)}
    out = []
    for p in route_a.pairs(cfg, ci, target, WINDOW, True):
        scene = rows.get((p.station, p.scene_key))
        if scene is None or ci.stream_of.get(p.station) != cfg.stations.test_stream:
            continue
        out.append(replace(p, family=scene.family, features=scene.features, stats=scene.stats))
    return out


def analyse(cfg: QualityConfig, root: Path, rb: RouteBInputs, ci: route_a.ColombianInputs,
            v21: Mapping[str, Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """Stage B's tables: v2.2's candidates by nested LOSO on every RAdCor pair of each target.

    Args:
        cfg: Settings.
        root: Repository root.
        rb: Route B's inputs (Stage A's RAdCor pairs).
        ci: The Colombian inputs.
        v21: v2.1's summary (the reference error).

    Returns:
        ``stage_b_scores``, ``stage_b_levels`` and ``stage_b_choices``.
    """
    from climate_pipeline.quality import physical
    from climate_pipeline.quality.route_b import _seed, common_pairs, parse_mdn

    tables: dict[str, list[dict[str, Any]]] = {"stage_b_scores": [], "stage_b_levels": [],
                                               "stage_b_choices": []}  # fmt: skip
    folder = root / cfg.outputs.inputs / FOLDER
    windows = folder / "windows.csv"
    text = windows.read_text(encoding="utf-8") if windows.exists() else ""
    if not text.strip() or len(text.strip().splitlines()) < 2 or not finished(folder):
        # Scored only once every listed scene is decided: never on a partial download.
        tables["stage_b_scores"].append({"status": "Stage B in progress (not scored)"})
        return tables
    mdn = folder / "mdn-predictions.csv"
    extra = parse_mdn(mdn.read_text(encoding="utf-8")) if mdn.exists() else {}
    rb2 = replace(rb, mdn={**rb.mdn, **extra})
    n = rb.inputs.nechad
    switch = (n[("TUR", "B4")], n[("TUR", "B8A")]) if ("TUR", "B8A") in n else None
    for target in cfg.targets:
        stage_a = common_pairs(rb, target.id)[physical.CORRECTION]
        have = {(p.station, p.sample_day) for p in stage_a}
        new = [p for p in stage_b_pairs(cfg, ci, text, target.id, switch)
               if (p.station, p.sample_day) not in have]  # fmt: skip
        pool = [*stage_a, *new]
        base = {"target": target.id, "status": STATUS[target.id],
                "published": physical.PUBLISHED[target.id], "stage_a_pairs": len(stage_a),
                "stage_b_pairs": len(new)}  # fmt: skip
        if len({p.station for p in pool}) < 3:
            tables["stage_b_scores"].append({**base, "evaluation": "insufficient_data"})
            continue
        options = physical.candidates(cfg, rb2, target.id)
        seed = _seed(cfg.seed, "stage-b", target.id)
        result = posthoc.nested(cfg, pool, options, order=physical.ORDER)
        m = posthoc.metrics(cfg, pool, result, list(range(len(pool))), seed)
        rows = posthoc.level_rows(cfg, target, pool, result, seed)
        reference = v21.get(target.id, {}).get("mdsa", math.nan)
        row = {**base, "evaluation": "nested LOSO (Stage A + B)", **m, "level": rows[0]["level"],
               "v21_mdsa": reference}  # fmt: skip
        tables["stage_b_scores"].append(row)
        r1 = [options["R1"]([], [p])[0] for p in pool]
        m1 = route_a.evaluate(cfg, pool, r1, result.null, None, seed + 3)
        tables["stage_b_scores"].append({**base, "evaluation": "R1 as published (no fit)", **m1})
        years = posthoc.nested(cfg, pool, options, group=posthoc.hydrological_year,
                               order=physical.ORDER)  # fmt: skip
        my = posthoc.metrics(cfg, pool, years, list(range(len(pool))), seed + 5)
        tables["stage_b_scores"].append({**base, "evaluation": "report-only: outer folds by "
                                         "hydrological year (round 3's)", **my})  # fmt: skip
        tables["stage_b_levels"] += [{"target": target.id, **r} for r in rows]
        tables["stage_b_choices"] += [{"target": target.id, "held_out_station": g, "chosen": c}
                                      for g, c in result.chosen.items()]  # fmt: skip
    return tables
