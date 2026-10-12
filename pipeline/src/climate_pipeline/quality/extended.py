"""v3's imagery: Sentinel-2 L2A windows within ±15 days of the Colombian samples.

The v2 snapshot holds the acquisitions within ±3 days of a sample. v3 trains on longer matchups,
so this fetch measures, at every selected Colombian station with samples (the Magdalena first),
the acquisitions within ``EXTENDED_DAYS`` of a sample that the v2 snapshot does not hold. It uses
the same readers, windows and guards (Planetary Computer before 2018-12, Earth Search after). The
existing snapshots are left untouched: the rows go to ``imagery/windows-extended.csv``. Each
station's rows are kept in the cache as they arrive, so a rerun resumes.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import (
    _csv,
    _reader,
    candidate_of,
    error_rows,
    read_stations,
)
from climate_pipeline.quality import imagery, route_a
from climate_pipeline.quality.config import QualityConfig, SourceName
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.quality.usgs import checkpoint
from climate_pipeline.quality.values import WINDOW_COLUMNS, Budget, measure, near
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.stac import Acquisition, evidence_hash

log = logging.getLogger(__name__)
EXTENDED_DAYS = 15
CAP_GB = 25.0
ITEM_COLUMNS = ("station", "source", "acquisitions", "item_ids_sha256")


def fetch(cfg: QualityConfig, root: Path, cache: Path, workers: int) -> dict[str, Any]:
    """Snapshot the extended windows (see the module docstring).

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.

    Returns:
        Counts, the estimated volume and the incomplete parts.
    """
    inputs = root / cfg.outputs.inputs
    ci = route_a.load(cfg, root)
    if ci is None:
        raise RuntimeError("no Colombian snapshots: run quality fetch first")
    known = {(r["station"], r["key"]) for r in csv.DictReader(io.StringIO(
        (inputs / "imagery" / "windows.csv").read_text(encoding="utf-8")))}  # fmt: skip
    stations = [r for r in read_stations(inputs / "stations" / "stations.csv")
                if r["selected"] == "true"]  # fmt: skip
    stations.sort(key=lambda r: (r["stream"] != cfg.stations.test_stream, r["station_id"]))
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    readers = {n: imagery.reader(screening, n, cache) for n in cfg.imagery.sources}
    geo_reader = _reader(d15, screening, cache)
    progress = cache / "extended-windows"
    progress.mkdir(parents=True, exist_ok=True)
    rec = sources.Recorder(inputs)
    budget = Budget(CAP_GB)
    days: dict[str, set[date]] = {}
    for s in ci.samples:
        days.setdefault(s.station, set()).add(s.day)
    rows: list[dict[str, Any]] = []
    items: list[dict[str, Any]] = []
    incomplete: list[str] = []
    split = cfg.imagery.split_date
    for row in stations:
        sid = row["station_id"]
        if not days.get(sid):
            continue
        if budget.spent:
            incomplete.append(f"extended imagery: network cap reached before {sid}")
            break
        check_disk(root, cfg.budgets.keep_free_gb)
        cand = candidate_of({**row, "files": ""})
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        geo_acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, geo_reader, d15, screening, workers)
        if not geo.selected:
            continue
        wins = imagery.small_windows(geo, cfg)
        small = extract.bbox_around(cand.lon, cand.lat, cfg.imagery.read_half_size_m)
        first = min(days[sid]) - timedelta(days=EXTENDED_DAYS + 1)
        last = max(days[sid]) + timedelta(days=EXTENDED_DAYS + 1)
        done = checkpoint(progress / f"{sid}.jsonl")
        spans: list[tuple[SourceName, date, date]] = [
            ("planetary-computer", first, min(last, split - timedelta(days=1))),
            ("earth-search", max(first, split), last),
        ]
        for name, lo, hi in spans:
            if lo > hi:
                continue
            acqs, sun = imagery.search(cfg, name, small, lo, hi)
            acqs = [
                a for a in acqs
                if cfg.imagery.source_for(imagery.utc_date(a)) == name
                and (sid, a.key) not in known
                and near(extract.local_date(a, cfg.timezone), days[sid], EXTENDED_DAYS)
            ]  # fmt: skip
            items.append({"station": sid, "source": name, "acquisitions": len(acqs),
                          "item_ids_sha256": evidence_hash(acqs)})  # fmt: skip
            todo: list[Acquisition] = [a for a in acqs if f"{name}|{a.key}" not in done]
            one = partial(measure, name=name, reader=readers[name], windows=wins, station=sid,
                          sun=sun, d15=d15, screening=screening, timezone=cfg.timezone)  # fmt: skip
            with ThreadPoolExecutor(max_workers=workers) as pool, (
                    progress / f"{sid}.jsonl").open("a", encoding="utf-8") as handle:  # fmt: skip
                for a, found in zip(todo, pool.map(one, todo), strict=True):
                    handle.write(json.dumps({"key": f"{name}|{a.key}", "rows": found},
                                            default=str) + "\n")  # fmt: skip
                    done[f"{name}|{a.key}"] = found
            for a in acqs:
                found = done[f"{name}|{a.key}"]
                rows += found
                budget.add(found)
        log.info("%s: %d extended rows so far, about %.1f GB read", sid, len(rows),
                 budget.mb / 1000)  # fmt: skip
    rec.save("imagery/windows-extended.csv", _csv(rows, WINDOW_COLUMNS), "derived",
             note=f"within {EXTENDED_DAYS} days of a sample, not in windows.csv")  # fmt: skip
    rec.save("imagery/items-extended.csv", _csv(items, ITEM_COLUMNS), "derived")
    errors = error_rows([e for r in (*readers.values(), geo_reader) for e in r.errors])
    rec.save("imagery/read-errors-extended.csv", _csv(errors, ("kind", "error")), "derived")
    rec.save("imagery/incomplete-extended.json",
             (json.dumps(incomplete, indent=1) + "\n").encode(), "derived")  # fmt: skip
    (inputs / "fetch-manifest-extended.csv").write_text(rec.manifest(), encoding="utf-8",
                                                        newline="\n")  # fmt: skip
    return {"stations": len({i["station"] for i in items}), "rows": len(rows),
            "read_errors": sum(1 for e in errors if e["kind"] == "transient"),
            "failures": len(rec.failures), "estimated_gb": round(budget.mb / 1000, 2),
            "incomplete": incomplete}  # fmt: skip
