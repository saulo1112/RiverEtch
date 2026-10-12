"""The USGS pilot of the water-quality validation v2: site selection, then the value snapshots.

``fetch_sites`` reads metadata only: the continuous turbidity series (parameter 63680,
computation ``Points``) that overlap the period, the large monitoring locations (drainage area
over the threshold), and the imagery that decides each site's main channel and width (D15's rule,
through D15's functions and settings). Its ``sites.csv`` is committed before any value is fetched.

``fetch_values`` reads the frozen list. Per site, the Earth Search acquisitions whose item cloud
cover is under the cap are drawn in a seeded order, stratified by year; SCL is read first, and the
draw stops at the cap of clear scenes. Sites are visited in two passes (half the cap, then the
rest), so a network cap that stops the stage leaves every site with data. For each clear scene the
turbidity at the overpass follows the preregistered rule; discrete SSC samples are snapshotted per
site and matched later on the acquisition's UTC date (passes are mid-morning in local time).

The stage is long, so it resumes: each site's window rows and each turbidity response are kept in
the cache as they arrive, and a rerun reads them instead of the network (the draw is seeded, so
it visits the same acquisitions). The turbidity of up to ``OVERPASS_BATCH`` overpasses of a site
is asked in one request (the API allows 1,000 requests an hour without a key); its rate limit
stops the turbidity step, marked incomplete, rather than failing every remaining call.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import load_calibration_config
from climate_pipeline.calibration.fetching import _csv, _reader, error_rows, read_stations
from climate_pipeline.calibration.stations import Candidate
from climate_pipeline.quality import imagery
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.quality.values import WINDOW_COLUMNS, Budget, measure
from climate_pipeline.screening.config import load_screening_config
from climate_pipeline.screening.stac import Acquisition, evidence_hash
from climate_pipeline.sources import usgs

log = logging.getLogger(__name__)
SITE_COLUMNS = (
    "site_id", "name", "river", "lon", "lat", "drainage_area_sq_mi", "series_begin", "series_end",
    "mask_source", "snap_m", "width_m", "selected", "reason", "scl_selected", "scl_reason",
    "scl_width_m",
)  # fmt: skip
TURBIDITY_COLUMNS = ("site_id", "key", "datetime_utc", "value", "unit", "rule", "n",
                     "response_sha256")  # fmt: skip
SSC_COLUMNS = ("site_id", "date", "time", "zone", "value", "unit", "status")
OVERPASS_BATCH = 20  # overpasses per turbidity request: 20 windows of 2 h hold < 1,000 readings


def _overlaps(props: Mapping[str, Any], start: date, end: date) -> bool:
    begin, finish = str(props.get("begin") or "")[:10], str(props.get("end") or "")[:10]
    return bool(begin and finish) and begin <= end.isoformat() and finish >= start.isoformat()


def candidate_sites(series: Sequence[Mapping[str, Any]], locations: Sequence[Mapping[str, Any]],
                    start: date, end: date) -> list[dict[str, Any]]:  # fmt: skip
    """Large sites with a continuous series overlapping the period (metadata only).

    Args:
        series: ``time-series-metadata`` features.
        locations: ``monitoring-locations`` features (with geometry).
        start: First day of the period.
        end: Last day.

    Returns:
        One row per site, sorted by id, with its river group and series range.
    """
    spans: dict[str, tuple[str, str]] = {}
    for f in series:
        p = f.get("properties", {})
        if not _overlaps(p, start, end):
            continue
        site = str(p["monitoring_location_id"])
        begin, finish = str(p["begin"])[:10], str(p["end"])[:10]
        old = spans.get(site)
        spans[site] = (min(begin, old[0]), max(finish, old[1])) if old else (begin, finish)
    out = []
    for f in locations:
        p = f.get("properties", {})
        site = str(p.get("id") or f.get("id"))
        coords = (f.get("geometry") or {}).get("coordinates") or [math.nan, math.nan]
        if site not in spans:
            continue
        name = str(p.get("monitoring_location_name", ""))
        out.append({"site_id": site, "name": name, "river": usgs.river_group(name),
                    "lon": float(coords[0]), "lat": float(coords[1]),
                    "drainage_area_sq_mi": p.get("drainage_area"),
                    "series_begin": spans[site][0], "series_end": spans[site][1]})  # fmt: skip
    return sorted(out, key=lambda r: r["site_id"])


def fetch_sites(cfg: QualityConfig, root: Path, cache: Path, workers: int,
                http: httpx.Client | None = None) -> list[dict[str, object]]:  # fmt: skip
    """Select the pilot sites from metadata and imagery; snapshot the metadata and the list.

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.
        http: HTTP client (injectable).

    Returns:
        The site rows (selected and not).
    """
    u = cfg.usgs
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    client = http or httpx.Client(timeout=300, follow_redirects=True)
    inputs = root / cfg.outputs.inputs
    rec = sources.Recorder(inputs)
    check_disk(root, cfg.budgets.keep_free_gb)
    series_url = f"{u.api}/collections/time-series-metadata/items"
    series, series_bodies = usgs.features(client, series_url, {
        "parameter_code": u.turbidity_parameter, "computation_period_identifier": "Points",
        "skipGeometry": "true", "limit": "10000", "f": "json",
    })  # fmt: skip
    locations_url = f"{u.api}/collections/monitoring-locations/items"
    locations, location_bodies = usgs.features(client, locations_url, {
        "filter": f"drainage_area >= {u.min_drainage_area_sq_mi:g} AND site_type_code = 'ST'",
        "filter-lang": "cql2-text", "limit": "10000", "f": "json",
    })  # fmt: skip
    rows = candidate_sites(series, locations, u.period.start, u.period.end)
    keep = {r["site_id"] for r in rows}
    for name, url, found, bodies in (("time-series-metadata", series_url, series, series_bodies),
                                     ("monitoring-locations", locations_url, locations,
                                      location_bodies)):  # fmt: skip
        subset = [
            f
            for f in found
            if str(
                f.get("properties", {}).get("monitoring_location_id")
                or f.get("properties", {}).get("id")
            )
            in keep
        ]
        digests = " ".join(hashlib.sha256(b).hexdigest() for b in bodies)
        body = (json.dumps(subset, indent=1, sort_keys=True) + "\n").encode()
        note = f"features of the candidate sites; full pages sha256 {digests}"
        rec.save(f"usgs/{name}.json", body, url, note=note)
    reader = _reader(d15, screening, cache)
    out: list[dict[str, object]] = []
    for row in rows:
        check_disk(root, cfg.budgets.keep_free_gb)
        cand = Candidate(row["site_id"], row["name"], row["lon"], row["lat"], "usgs")
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                              cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, acqs, reader, d15, screening, workers)
        log.info("%s %s: %s %s", row["river"], row["site_id"], geo.selected,
                 geo.reason or f"{geo.width_m:.0f} m")  # fmt: skip
        out.append({
            **row, "mask_source": geo.mask_source, "snap_m": round(geo.snap_m, 1),
            "width_m": round(geo.width_m, 1), "selected": geo.selected, "reason": geo.reason,
            "scl_selected": geo.scl_selected, "scl_reason": geo.scl_reason,
            "scl_width_m": round(geo.scl_width_m, 1),
        })  # fmt: skip
    rec.save("usgs/sites.csv", _csv(out, SITE_COLUMNS), "derived", note="the frozen selection")
    rec.save("usgs/site-read-errors.csv", _csv(error_rows(reader.errors), ("kind", "error")),
             "derived")  # fmt: skip
    (inputs / "fetch-manifest-usgs-sites.csv").write_text(rec.manifest(), encoding="utf-8",
                                                           newline="\n")  # fmt: skip
    return out


def draw_order(acquisitions: Sequence[Acquisition], seed: int) -> list[Acquisition]:
    """A seeded order stratified by year: one acquisition of each year in turn.

    Args:
        acquisitions: A site's candidate acquisitions.
        seed: The site's seed.

    Returns:
        The acquisitions in drawing order.
    """
    rng = random.Random(seed)
    by_year: dict[int, list[Acquisition]] = {}
    for a in sorted(acquisitions, key=lambda a: a.key):
        by_year.setdefault(a.datetime.year, []).append(a)
    for items in by_year.values():
        rng.shuffle(items)
    years = sorted(by_year)
    out: list[Acquisition] = []
    while any(by_year[y] for y in years):
        out += [by_year[y].pop(0) for y in years if by_year[y]]
    return out


def clear(rows: Sequence[Mapping[str, Any]], min_valid: int, max_contamination: float) -> bool:
    """Whether an acquisition's 300 m window passed every scene guard (its bands were read).

    Args:
        rows: The acquisition's window rows.
        min_valid: Minimum water pixels.
        max_contamination: Maximum invalid share.

    Returns:
        True when the 300 m window is usable.
    """
    for r in rows:
        if r.get("window") == "300m":
            return (r.get("bands_read") == 1.0 and r.get("valid_px", 0) >= min_valid
                    and r.get("contamination", 1) <= max_contamination
                    and r.get("b11_ok", 0) >= 1)  # fmt: skip
    return False


def _cloud(acquisition: Acquisition) -> float:
    values = [s.cloud_cover for s in acquisition.scenes if s.cloud_cover is not None]
    return sum(values) / len(values) if values else math.inf


def checkpoint(path: Path) -> dict[str, list[dict[str, Any]]]:
    """One site's window rows already measured, by acquisition key (a line cut short is skipped).

    Args:
        path: The site's ``<site>-windows.jsonl``.

    Returns:
        Key -> window rows.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        out[str(item["key"])] = list(item["rows"])
    return out


def cached_bodies(path: Path) -> list[bytes] | None:
    """Response bodies kept by an earlier run (None when absent or cut short).

    A file holds the bodies, or ``{"batch": <file>}`` naming the batch response it shares.

    Args:
        path: The response file.

    Returns:
        The bodies, or None.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return cached_bodies(path.with_name(str(data["batch"])))
        return [b.encode("utf-8") for b in data]
    except (OSError, ValueError, KeyError):
        return None


def keep_bodies(path: Path, bodies: Sequence[bytes]) -> None:
    """Keep response bodies for a rerun (written whole, then renamed).

    Args:
        path: The response file.
        bodies: The raw bodies.
    """
    partial_path = path.with_suffix(".tmp")
    partial_path.write_text(json.dumps([b.decode("utf-8") for b in bodies]), encoding="utf-8")
    os.replace(partial_path, path)


def fetch_values(cfg: QualityConfig, root: Path, cache: Path, workers: int,
                 http: httpx.Client | None = None, site_ids: set[str] | None = None,
                 max_clear: int | None = None, folder: str = "usgs", ssc: bool = True,
                 cap_gb: float | None = None) -> dict[str, Any]:  # fmt: skip
    """Snapshot the pilot's windows, turbidity at the overpass and SSC samples.

    v4's second reach reuses it for one site, every clear scene and its own folder.

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads.
        http: HTTP client (injectable).
        site_ids: Only these selected sites (default: every one).
        max_clear: Clear scenes per site (default: the pilot's cap).
        folder: Output folder under the inputs (default: the pilot's).
        ssc: Also the discrete SSC samples.
        cap_gb: Network cap (default: the pilot's).

    Returns:
        Counts and the incomplete parts.
    """
    from climate_pipeline.quality.route_b import _seed

    u = cfg.usgs
    inputs = root / cfg.outputs.inputs
    sites = [r for r in read_stations(inputs / "usgs" / "sites.csv") if r["selected"] == "true"
             and (site_ids is None or r["site_id"] in site_ids)]  # fmt: skip
    most = u.max_clear_scenes_per_site if max_clear is None else max_clear
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    client = http or httpx.Client(timeout=300, follow_redirects=True)
    rec = sources.Recorder(inputs)
    check_disk(root, cfg.budgets.keep_free_gb)
    geo_reader = _reader(d15, screening, cache)
    reader = imagery.reader(screening, "earth-search", cache)
    budget = Budget(cfg.budgets.network_gb.usgs if cap_gb is None else cap_gb)
    window = cfg.window
    progress = cache / "usgs-pilot"
    progress.mkdir(parents=True, exist_ok=True)
    state: dict[str, dict[str, Any]] = {}
    incomplete: list[str] = []
    windows_rows: list[dict[str, Any]] = []
    turbidity_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []
    for site in sites:  # geometry, windows and the drawing order
        cand = Candidate(site["site_id"], site["name"], float(site["lon"]), float(site["lat"]),
                         "usgs")  # fmt: skip
        bbox = extract.bbox_around(cand.lon, cand.lat, cfg.stations.grid_half_size_m)
        geo_acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, geo_reader, d15, screening, workers)
        if not geo.selected:
            log.warning("%s no longer selected: %s", cand.station_id, geo.reason)
            continue
        small = extract.bbox_around(cand.lon, cand.lat, cfg.imagery.read_half_size_m)
        acqs, sun = imagery.search(cfg, "earth-search", small, u.period.start, u.period.end)
        eligible = [a for a in acqs if _cloud(a) <= u.max_cloud_cover]
        state[cand.station_id] = {
            "windows": imagery.small_windows(geo, cfg), "sun": sun, "clear": [],
            "order": draw_order(eligible, _seed(cfg.seed, "usgs", cand.station_id)),
            "done": checkpoint(progress / f"{cand.station_id}-windows.jsonl"),
        }  # fmt: skip
        item_rows.append(
            {
                "station": cand.station_id,
                "source": "earth-search",
                "acquisitions": len(eligible),
                "item_ids_sha256": evidence_hash(eligible),
            }
        )
    for cap in (most // 2, most):
        for sid, st in state.items():
            if budget.spent:
                break
            check_disk(root, cfg.budgets.keep_free_gb)
            one = partial(measure, name="earth-search", reader=reader, windows=st["windows"],
                          station=sid, sun=st["sun"], d15=d15, screening=screening,
                          timezone=cfg.timezone)  # fmt: skip
            while len(st["clear"]) < cap and st["order"] and not budget.spent:
                batch = [st["order"].pop(0) for _ in range(min(workers, len(st["order"])))]
                todo = [a for a in batch if a.key not in st["done"]]
                with ThreadPoolExecutor(max_workers=workers) as pool:
                    fresh = dict(zip([a.key for a in todo], pool.map(one, todo), strict=True))
                with (progress / f"{sid}-windows.jsonl").open("a", encoding="utf-8") as handle:
                    for key, rows in fresh.items():
                        handle.write(json.dumps({"key": key, "rows": rows}, default=str) + "\n")
                st["done"].update(fresh)
                # The budget counts cached reads too, so the outcome never depends on where an
                # earlier run stopped.
                for a in batch:
                    rows = st["done"][a.key]
                    windows_rows += rows
                    budget.add(rows)
                    if len(st["clear"]) < cap and clear(
                        rows, window.min_valid_px, window.max_contamination
                    ):
                        st["clear"].append(a)
            log.info("%s: %d clear scenes, about %.1f GB read", sid, len(st["clear"]),
                     budget.mb / 1000)  # fmt: skip
        if budget.spent:
            incomplete.append(f"imagery: network cap reached during the pass to {cap} scenes")
            break
    limited = False
    margin = timedelta(minutes=u.overpass_nearest_minutes)
    for sid, st in state.items():  # turbidity at each clear overpass
        responses = progress / sid
        responses.mkdir(exist_ok=True)
        found: dict[str, list[bytes]] = {}
        pending = []
        for a in st["clear"]:
            saved = responses / f"{a.key}.json"
            bodies = cached_bodies(saved) if saved.exists() else None
            if bodies is None:
                pending.append(a)
            else:
                found[a.key] = bodies
        for start in range(0, len(pending), OVERPASS_BATCH):
            batch = pending[start : start + OVERPASS_BATCH]
            times = [a.datetime.astimezone(UTC) for a in batch]
            label = f"{u.api} continuous {sid} {len(batch)} overpasses from {times[0].isoformat()}"
            try:
                windows = [(t - margin, t + margin) for t in times]
                _, bodies = usgs.continuous_many(client, u.api, sid, u.turbidity_parameter,
                                                 windows)  # fmt: skip
            except httpx.HTTPStatusError as error:
                if error.response.status_code == 429:
                    limited = True
                    break
                rec.fail(label, error)
                continue
            except httpx.HTTPError as error:
                rec.fail(label, error)
                continue
            name = (
                "batch-" + hashlib.sha256("|".join(a.key for a in batch).encode()).hexdigest()[:16]
            )
            keep_bodies(responses / f"{name}.json", bodies)
            for a in batch:
                pointer = responses / f"{a.key}.json"
                pointer.write_text(json.dumps({"batch": f"{name}.json"}), encoding="utf-8")
                found[a.key] = bodies
        for a in st["clear"]:
            if a.key not in found:
                continue
            when = a.datetime.astimezone(UTC)
            bodies = found[a.key]
            readings = usgs.readings_from_bodies(bodies)
            value, rule, n = usgs.overpass_value(readings, when, u.overpass_median_minutes,
                                                 u.overpass_nearest_minutes, u.approval,
                                                 u.exclude_qualified)  # fmt: skip
            turbidity_rows.append({
                "site_id": sid, "key": a.key,
                "datetime_utc": when.isoformat(timespec="seconds"), "value": value, "unit": "FNU",
                "rule": rule, "n": n,
                "response_sha256": hashlib.sha256(b"".join(bodies)).hexdigest(),
            })  # fmt: skip
        if limited:
            incomplete.append("turbidity: the USGS API's rate limit stopped the step; a rerun "
                              "resumes from the cached responses")  # fmt: skip
            break
    ssc_rows: list[dict[str, Any]] = []
    for sid in state if ssc else []:  # discrete SSC samples
        try:
            body = usgs.samples(client, sid, u.ssc_parameter, u.period.start.isoformat(),
                                u.period.end.isoformat())  # fmt: skip
        except httpx.HTTPError as error:
            rec.fail(f"{usgs.SAMPLES} {sid}", error)
            continue
        ssc_rows += [{"site_id": sid, **r} for r in usgs.parse_samples(body)]
    rec.save(f"{folder}/windows.csv", _csv(windows_rows, WINDOW_COLUMNS), "derived",
             note="station-window statistics and band medians, Earth Search")  # fmt: skip
    rec.save(f"{folder}/turbidity.csv", _csv(turbidity_rows, TURBIDITY_COLUMNS), u.api,
             note="continuous 63680 at each clear overpass, preregistered rule")  # fmt: skip
    rec.save(f"{folder}/ssc.csv", _csv(ssc_rows, SSC_COLUMNS), usgs.SAMPLES,
             note=f"discrete {u.ssc_parameter} samples of the selected sites")  # fmt: skip
    rec.save(f"{folder}/items.csv", _csv(item_rows, ("station", "source", "acquisitions",
                                                "item_ids_sha256")), "derived")  # fmt: skip
    errors = error_rows([*reader.errors, *geo_reader.errors])
    rec.save(f"{folder}/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    rec.save(
        f"{folder}/incomplete.json", (json.dumps(incomplete, indent=1) + "\n").encode(), "derived"
    )
    manifest = "fetch-manifest-usgs.csv" if folder == "usgs" else f"fetch-manifest-{folder}.csv"
    (inputs / manifest).write_text(rec.manifest(), encoding="utf-8", newline="\n")
    return {
        "sites": len(state), "clear_scenes": sum(len(s["clear"]) for s in state.values()),
        "turbidity_pairs": sum(1 for r in turbidity_rows if math.isfinite(r["value"])),
        "ssc_samples": len(ssc_rows), "failures": len(rec.failures),
        "read_errors": sum(1 for e in errors if e["kind"] == "transient"),
        "estimated_gb": round(budget.mb / 1000, 2), "incomplete": incomplete,
    }  # fmt: skip
