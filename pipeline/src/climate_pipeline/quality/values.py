"""The value snapshots of the water-quality validation v2, for the frozen Colombian station list.

* the turbidity and TSS samples of the selected points (``62gv-3857``, since the start date);
* the discharge or level series that judge flow stability (the period's lines, verbatim);
* station-window statistics of every acquisition within the sensitivity days of a sample, from
  the one source that serves its date (Planetary Computer before the split, Earth Search after);
* the source check: Planetary Computer windows on the Earth Search matchup scenes of its period.

SCL is read first and the other bands only for windows that can pass (D15's deviation 4). The
network volume is estimated from the reads (an SCL block, ten band blocks) and capped; free disk
space is checked before each station. A stage that reaches a cap is recorded as incomplete.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, timedelta
from functools import partial
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.calibration import extract, sources
from climate_pipeline.calibration.config import CalibrationConfig, load_calibration_config
from climate_pipeline.calibration.fetching import (
    _csv,
    _reader,
    candidate_of,
    error_rows,
    read_stations,
)
from climate_pipeline.calibration.matchups import samples_from_soda
from climate_pipeline.quality import imagery
from climate_pipeline.quality.config import QualityConfig, SourceName
from climate_pipeline.quality.fetching import check_disk
from climate_pipeline.screening.config import ScreeningConfig, load_screening_config
from climate_pipeline.screening.rio import AcquisitionReader
from climate_pipeline.screening.stac import Acquisition, evidence_hash

log = logging.getLogger(__name__)
WINDOWS = ("300m", "core")
WINDOW_COLUMNS = (
    "station", "source", "key", "datetime_utc", "local_date", "family", "window", "window_px",
    "data_px", "valid_px", "contamination", "glint_share", "b11_median", "b11_ok",
    "ndti_px_median", *extract.BAND_ORDER, "bands_read", "sun_zenith",
)  # fmt: skip
# Estimated download per acquisition (COG blocks measured on 2026-10-10: Earth Search keeps its
# 10 m bands in 1024-pixel blocks and the rest in 512-pixel blocks; Planetary Computer uses
# 512-pixel blocks throughout): the SCL block, and the ten band blocks of a +-400 m window.
SCL_MB = 0.2
BAND_MB = {"earth-search": 8.5, "planetary-computer": 4.0}


class Budget:
    """An estimated network volume against its cap."""

    def __init__(self, cap_gb: float) -> None:
        """Create the budget.

        Args:
            cap_gb: The cap, in GB.
        """
        self.cap_gb = cap_gb
        self.mb = 0.0

    def add(self, rows: Sequence[Mapping[str, Any]]) -> None:
        """Count one acquisition's reads: its SCL, and its bands when any window read them.

        Args:
            rows: The acquisition's window rows (their ``source`` names the block sizes).
        """
        if not rows:
            return
        bands = BAND_MB[rows[0].get("source", "earth-search")]
        self.mb += SCL_MB + (bands if any(r.get("bands_read") == 1.0 for r in rows) else 0.0)

    @property
    def spent(self) -> bool:
        """Whether the cap is reached."""
        return self.mb / 1000 >= self.cap_gb


def near(day: date, days: set[date], max_days: int) -> bool:
    """Whether a day lies within ``max_days`` of any of ``days``.

    Args:
        day: The acquisition's local date.
        days: Sample dates.
        max_days: Largest gap.

    Returns:
        True when some sample is close enough.
    """
    return any(abs((day - d).days) <= max_days for d in days)


def measure(
    acquisition: Acquisition, name: SourceName, reader: AcquisitionReader, windows: extract.Windows,
    station: str, sun: Mapping[str, float], d15: CalibrationConfig, screening: ScreeningConfig,
    timezone: str,
) -> list[dict[str, Any]]:  # fmt: skip
    """The window rows of one acquisition (D15's statistics and medians).

    Args:
        acquisition: The pass.
        name: Its source.
        reader: The source's reader.
        windows: The station's windows.
        station: Station id.
        sun: Item id -> sun zenith.
        d15: D15's settings (its window guards and bands).
        screening: Screening settings.
        timezone: For the local date.

    Returns:
        One row per window.
    """
    stats = extract.measure_window(acquisition, reader, windows, WINDOWS, d15, screening)
    base = {
        "station": station, "source": name, "key": acquisition.key,
        "datetime_utc": acquisition.datetime.astimezone(UTC).isoformat(timespec="seconds"),
        "local_date": extract.local_date(acquisition, timezone).isoformat(),
        "family": extract.family(acquisition),
        "sun_zenith": imagery.acquisition_sun(acquisition, sun),
    }  # fmt: skip
    return [{**base, "window": w, **values} for w, values in stats.items()]


def fetch_values(
    cfg: QualityConfig, root: Path, cache: Path, workers: int, http: httpx.Client | None = None
) -> dict[str, Any]:
    """Snapshot every value the Colombian analysis needs, for the frozen station list.

    Args:
        cfg: The v2 settings.
        root: Repository root.
        cache: Cache folder.
        workers: Parallel reads (per station, over acquisitions).
        http: HTTP client (injectable).

    Returns:
        Counts and the incomplete parts.
    """
    st = cfg.stations
    inputs = root / cfg.outputs.inputs
    stations = [r for r in read_stations(inputs / "stations" / "stations.csv")
                if r["selected"] == "true"]  # fmt: skip
    d15 = load_calibration_config(root / cfg.calibration_config)
    screening = load_screening_config(root / cfg.screening_config)
    client = http or httpx.Client(timeout=400, follow_redirects=True)
    rec = sources.Recorder(inputs)
    check_disk(root, cfg.budgets.keep_free_gb)
    incomplete: list[str] = []

    # Samples.
    points = sorted({r["quality_point"] for r in stations if r["quality_point"]})
    body, url = sources.quality_samples(client, st.quality_resource, points, st.quality_variables,
                                        st.samples_since.isoformat())  # fmt: skip
    rec.save("ideam/quality-samples.json", body, url)
    point_station = {r["quality_point"]: r["station_id"] for r in stations if r["quality_point"]}
    targets = {t.variable: t.id for t in cfg.targets}
    days: dict[str, set[date]] = {}
    for s in samples_from_soda(json.loads(body), point_station, targets):
        days.setdefault(s.station, set()).add(s.day)

    # Flow series.
    start = cfg.period.start - timedelta(days=31)
    for code, label in sorted({(r["flow_code"], r["flow_label"]) for r in stations
                               if r["flow_code"]}):  # fmt: skip
        key = f"observaciones/historicos/csv/{label}/{code}-{label}.csv"
        try:
            full = sources.get(client, f"{st.bucket}/{key}")
        except httpx.HTTPError as error:
            rec.fail(f"{st.bucket}/{key}", error)
            continue
        subset = sources.period_lines(full, start, cfg.period.end)
        rec.save(f"ideam/{label}/{code}-{label}.csv", subset, f"{st.bucket}/{key}",
                 note=f"lines in {start}..{cfg.period.end}; full file {len(full)} B, sha256 "
                 f"{__import__('hashlib').sha256(full).hexdigest()}")  # fmt: skip

    # Imagery.
    readers = {n: imagery.reader(screening, n, cache) for n in cfg.imagery.sources}
    geo_reader = _reader(d15, screening, cache)  # the selection's reader and cache
    budget = Budget(cfg.budgets.network_gb.colombia)
    split, check = cfg.imagery.split_date, cfg.imagery.source_check
    windows_rows: list[dict[str, Any]] = []
    check_rows: list[dict[str, Any]] = []
    item_rows: list[dict[str, Any]] = []
    checked = 0
    for row in stations:
        sid = row["station_id"]
        if not days.get(sid):
            continue
        if budget.spent:
            incomplete.append(f"imagery: network cap reached before {sid}")
            break
        check_disk(root, cfg.budgets.keep_free_gb)
        cand = candidate_of({**row, "files": ""})
        bbox = extract.bbox_around(cand.lon, cand.lat, st.grid_half_size_m)
        geo_acqs = extract.search(d15, d15.imagery.primary, bbox, cfg.geometry_period.start,
                                  cfg.geometry_period.end)  # fmt: skip
        geo = extract.station_geometry(cand, geo_acqs, geo_reader, d15, screening, workers)
        if not geo.selected:
            log.warning("%s no longer selected: %s", sid, geo.reason)
            continue
        wins = imagery.small_windows(geo, cfg)
        small = extract.bbox_around(cand.lon, cand.lat, cfg.imagery.read_half_size_m)
        wanted = days[sid]
        first = min(wanted) - timedelta(days=cfg.matchups.sensitivity_days + 1)
        last = max(wanted) + timedelta(days=cfg.matchups.sensitivity_days + 1)
        by_source: dict[SourceName, list[Acquisition]] = {}
        sun: dict[str, float] = {}
        spans: list[tuple[SourceName, date, date]] = [
            ("planetary-computer", first, min(last, split - timedelta(days=1))),
            ("earth-search", max(first, split), last),
        ]
        for name, lo, hi in spans:
            if lo > hi:
                continue
            acqs, found = imagery.search(cfg, name, small, lo, hi)
            sun.update(found)
            by_source[name] = [
                a for a in acqs
                if cfg.imagery.source_for(imagery.utc_date(a)) == name
                and near(extract.local_date(a, cfg.timezone), wanted,
                         cfg.matchups.sensitivity_days)
            ]  # fmt: skip
        for name, acqs in by_source.items():
            one = partial(
                measure,
                name=name,
                reader=readers[name],
                windows=wins,
                station=sid,
                sun=sun,
                d15=d15,
                screening=screening,
                timezone=cfg.timezone,
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for rows in pool.map(one, acqs):
                    windows_rows += rows
                    budget.add(rows)
            item_rows.append({"station": sid, "source": name, "acquisitions": len(acqs),
                              "item_ids_sha256": evidence_hash(acqs)})  # fmt: skip
        # Source check: Planetary Computer on the Earth Search matchup scenes of its period.
        es = [a for a in by_source.get("earth-search", [])
              if check.start <= imagery.utc_date(a) <= check.end]  # fmt: skip
        if es and checked < check.max_scenes:
            pc, found = imagery.search(cfg, "planetary-computer", small, check.start, check.end)
            sun.update(found)
            pc_by_key = {a.key: a for a in pc}
            for a in es[: check.max_scenes - checked]:
                twin = pc_by_key.get(a.key)
                if twin is None:
                    continue
                rows = measure(twin, "planetary-computer", readers["planetary-computer"], wins,
                               sid, sun, d15, screening, cfg.timezone)  # fmt: skip
                check_rows += rows
                budget.add(rows)
                checked += 1
        log.info("%s: %d window rows so far, about %.1f GB read", sid, len(windows_rows),
                 budget.mb / 1000)  # fmt: skip
    rec.save("imagery/windows.csv", _csv(windows_rows, WINDOW_COLUMNS), "derived",
             note="station-window statistics and band medians, both sources")  # fmt: skip
    rec.save("imagery/source-check.csv", _csv(check_rows, WINDOW_COLUMNS), "derived",
             note="Planetary Computer on Earth Search matchup scenes, 2019-2021")  # fmt: skip
    rec.save("imagery/items.csv", _csv(item_rows, ("station", "source", "acquisitions",
                                                   "item_ids_sha256")), "derived")  # fmt: skip
    errors = error_rows([e for r in (*readers.values(), geo_reader) for e in r.errors])
    rec.save("imagery/read-errors.csv", _csv(errors, ("kind", "error")), "derived")
    rec.save("incomplete.json", (json.dumps(incomplete, indent=1) + "\n").encode(), "derived")
    (inputs / "fetch-manifest.csv").write_text(rec.manifest(), encoding="utf-8", newline="\n")
    return {
        "snapshots": len(rec.records), "failures": len(rec.failures),
        "read_errors": sum(1 for e in errors if e["kind"] == "transient"),
        "estimated_gb": round(budget.mb / 1000, 2), "incomplete": incomplete,
    }  # fmt: skip
