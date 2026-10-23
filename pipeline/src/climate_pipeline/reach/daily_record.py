"""The daily flow record, sealed year by year (preregistration-daily-record.md).

``reach daily-record`` fetches a reach's whole daily record as ``reach climate`` does (the USGS
daily mean discharge, and water temperature where the station publishes it, or the GloFAS model's
river discharge on the Firat) and seals one record per calendar year in the reach's daily-record
list (``examples/daily-record/``): each value exactly as published, with its status. It runs every
day; a year whose values or statuses changed since its last record gets a new record naming the
one it replaces, and a year that did not change gets none. It also writes the fresh snapshot that
``reach climate`` reads, or, when the source cannot be reached, rebuilds it from the sealed
records, so the Climate tab never falls back to an older copy. Nothing here is an estimate: the
values are the source's, and a seal proves they are what it published, not that they are right.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.contract import daily_record as contract
from climate_pipeline.provenance import head
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach import along, climate
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig

log = logging.getLogger(__name__)

PREREGISTRATION = "docs/water-quality/preregistration-daily-record.md"
FOLDER = "daily-record"
# The reaches the app shows: a USGS station of their own, one upstream, or a flood model.
REACHES = ("mississippi-belle-chasse", "platte-louisville", "mississippi-st-joseph",
           "firat-birecik")  # fmt: skip
# Each parameter's name and unit, as its source publishes it.
NAMES = {
    climate.DISCHARGE: ("discharge", "ft³/s"),
    climate.TEMPERATURE: ("water temperature", "°C"),
    climate.MODELLED: ("discharge", "m³/s"),
}


def folder(root: Path, site_id: str) -> Path:
    """Where a reach's daily record lives (beside its examples, served to the web).

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        ``docs/water-quality/reach/<site>/examples/daily-record``.
    """
    return root / "docs" / "water-quality" / "reach" / site_id / "examples" / FOLDER


def _source(cfg: ReachConfig, root: Path, site_id: str) -> dict[str, Any]:
    """Who publishes a reach's daily flow, and how it is asked for (``kind``, ``id``, ...)."""
    reach = cfg.reach(site_id)
    model = reach.climate_model
    if model is not None:
        return {"kind": "glofas", "stationId": f"GloFAS-{model.lat:.3f}N-{model.lon:.3f}E",
                "name": model.name, "measured": False,
                "url": "https://open-meteo.com/en/docs/flood-api",
                "lat": model.lat, "lon": model.lon}  # fmt: skip
    context = reach.climate_station
    if context is not None:
        return {"kind": "usgs", "stationId": context.id, "name": context.name, "measured": True,
                "url": f"https://waterdata.usgs.gov/monitoring-location/{context.id}/"}  # fmt: skip
    if reach.station_source != "usgs":
        raise reach_run.ReachError(f"{site_id}: no station or model publishes its daily flow")
    station = reach_run.reach_info(cfg, root, site_id)["station"]
    return {"kind": "usgs", "stationId": station["id"], "name": station["name"],
            "measured": True, "url": station["url"]}  # fmt: skip


def _fetch(cfg: ReachConfig, root: Path, source: Mapping[str, Any], until: date,
           client: httpx.Client) -> tuple[list[dict[str, Any]], str, dict[str, str]]:  # fmt: skip
    """The whole record's snapshot rows, the API and the query that fetched them."""
    if source["kind"] == "glofas":
        rows = climate.fetch_modelled(client, source["lat"], source["lon"], until)
        query = {"latitude": str(source["lat"]), "longitude": str(source["lon"]),
                 "daily": climate.MODELLED, "start_date": climate.GLOFAS_FIRST_DAY,
                 "end_date": until.isoformat(), "cell_selection": "nearest"}  # fmt: skip
        return rows, climate.GLOFAS_API, query
    api = load_quality_config(root / cfg.quality_config).usgs.api
    rows = climate.fetch(client, api, source["stationId"], until)
    query = {"monitoring_location_id": source["stationId"], "statistic_id": "00003",
             "parameter_code": f"{climate.DISCHARGE},{climate.TEMPERATURE}",
             "datetime": f"{climate.FIRST_DAY}/{until.isoformat()}"}  # fmt: skip
    return rows, f"{api}/collections/daily/items", query


def _by_year(rows: Sequence[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Snapshot rows as each year's series, by parameter in a fixed order, days in order."""
    years: dict[int, dict[str, list[tuple[str, float, str]]]] = {}
    for r in rows:
        day = str(r["day"])
        years.setdefault(int(day[:4]), {}).setdefault(str(r["parameter"]), []).append(
            (day, float(r["value"]), str(r["approval"]))
        )
    out: dict[int, list[dict[str, Any]]] = {}
    for year, by_parameter in years.items():
        out[year] = []
        for parameter in sorted(by_parameter):
            name, unit = NAMES.get(parameter, (parameter, ""))
            days = sorted(by_parameter[parameter])
            out[year].append({"parameter": parameter, "name": name, "unit": unit,
                              "days": [list(d) for d in days]})  # fmt: skip
    return out


def latest(out: Path) -> dict[int, dict[str, Any]]:
    """Each year's latest record (the last line of the list that names it).

    Args:
        out: The reach's daily-record folder.

    Returns:
        ``year -> {"record", "file", "recordSha256"}``.
    """
    ledger = out / "ledger.jsonl"
    found: dict[int, dict[str, Any]] = {}
    if not ledger.exists():
        return found
    for text in ledger.read_text(encoding="utf-8").splitlines():
        if not text.strip():
            continue
        line = json.loads(text)
        record = json.loads((out / line["file"]).read_text(encoding="utf-8"))
        found[int(record["year"])] = {"record": record, "file": line["file"],
                                      "recordSha256": line["recordSha256"]}  # fmt: skip
    return found


def _append(path: Path, rec: contract.DailyRecordV1, file: str, created: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    previous = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else None
    line = {"sceneId": rec.record_id, "date": rec.date, "recordSha256": rec.record_sha256,
            "file": file, "createdUtc": created, "previousLineSha256": previous}  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")


def write_series(out: Path) -> Path:
    """The web's index: each year's latest record, and how many records the year has had.

    Args:
        out: The reach's daily-record folder.

    Returns:
        ``series.json``'s path.
    """
    counts: dict[int, int] = {}
    ledger = out / "ledger.jsonl"
    for text in ledger.read_text(encoding="utf-8").splitlines() if ledger.exists() else []:
        if text.strip():
            year = int(json.loads(text)["sceneId"].rsplit(":", 1)[1])
            counts[year] = counts.get(year, 0) + 1
    rows = []
    for year, entry in sorted(latest(out).items()):
        record = entry["record"]
        rows.append({"year": year, "recordId": record["recordId"], "file": entry["file"],
                     "recordSha256": entry["recordSha256"], "date": record["date"],
                     "fetchedUtc": record["fetchedUtc"], "records": counts.get(year, 1),
                     "days": max((len(s["days"]) for s in record["series"]),
                                 default=0)})  # fmt: skip
    path = out / "series.json"
    path.write_text(json.dumps(rows, indent=1, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip
    return path


def snapshot_from_records(out: Path) -> list[dict[str, Any]]:
    """The snapshot rows the latest sealed records hold (when the source cannot be reached).

    Args:
        out: The reach's daily-record folder.

    Returns:
        Snapshot rows, as ``climate.fetch`` returns them.
    """
    rows = []
    for entry in latest(out).values():
        for series in entry["record"]["series"]:
            rows += [{"day": d, "parameter": series["parameter"], "value": v, "approval": a}
                     for d, v, a in series["days"]]  # fmt: skip
    return sorted(rows, key=lambda r: (r["parameter"], r["day"]))


def run(cfg: ReachConfig, root: Path, site_id: str, until: date | None = None,
        http: httpx.Client | None = None, now: datetime | None = None
        ) -> dict[str, Any]:  # fmt: skip
    """Fetch a reach's daily record, seal each year that changed, and write the fresh snapshot.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        until: Last day to fetch (default: yesterday).
        http: HTTP client (injectable).
        now: The fetch time (injectable).

    Returns:
        The years sealed and the years unchanged.

    Raises:
        ReachError: Before the anchor, for a reach with no source, or when the source cannot be
            reached (the snapshot is then rebuilt from the sealed records).
    """
    if not along.anchored(root, PREREGISTRATION):
        raise reach_run.ReachError(f"{site_id}: {PREREGISTRATION} is not anchored yet")
    source = _source(cfg, root, site_id)
    out = folder(root, site_id)
    snapshot = climate.snapshot_path(root, site_id)
    last = until or date.today() - timedelta(days=1)
    client = http or httpx.Client(timeout=120, follow_redirects=True)
    fetched_at = (now or datetime.now(UTC)).astimezone(UTC)
    try:
        rows, api, query = _fetch(cfg, root, source, last, client)
    except (httpx.HTTPError, reach_run.ReachError) as error:
        kept = snapshot_from_records(out)
        if kept:
            climate.write_snapshot(snapshot, kept)
        raise reach_run.ReachError(
            f"{site_id}: the source could not be read ({error}); the snapshot was rebuilt from "
            "the sealed records"
        ) from error
    if not rows:
        raise reach_run.ReachError(f"{site_id}: the source published no daily value")
    climate.write_snapshot(snapshot, rows)
    created = fetched_at.isoformat(timespec="seconds")
    stamp = fetched_at.strftime("%Y%m%dT%H%M%SZ")
    commit = head()
    held = latest(out)
    (out / "records").mkdir(parents=True, exist_ok=True)
    sealed, unchanged = [], []
    for year, series in sorted(_by_year(rows).items()):
        before = held.get(year)
        if before is not None and before["record"]["series"] == series:
            unchanged.append(year)
            continue
        rec = contract.seal(contract.DailyRecordV1.model_validate({
            "reachId": site_id, "recordId": f"{site_id}:{FOLDER}:{year}", "year": year,
            "date": max(d[0] for s in series for d in s["days"]),
            "source": {k: source[k] for k in ("kind", "stationId", "name", "measured", "url")},
            "series": series, "fetchedUtc": created,
            "replaces": None if before is None else before["recordSha256"],
            "provenance": {"api": api, "query": query, "codeCommit": commit},
        }))  # fmt: skip
        file = f"records/{year}_{stamp}.json"
        (out / file).write_text(
            json.dumps(contract.as_json(rec), ensure_ascii=False, separators=(",", ":")) + "\n",
            encoding="utf-8", newline="\n")  # fmt: skip
        _append(out / "ledger.jsonl", rec, file, created)
        sealed.append(year)
        log.info("%s: sealed %s", site_id, file)
    write_series(out)
    return {"sealed": sealed, "unchanged": len(unchanged), "through": max(r["day"] for r in rows)}


def verify(root: Path, site_id: str) -> list[str]:
    """Every daily record's seal and the list's chain.

    Args:
        root: Repository root.
        site_id: The reach.

    Returns:
        One line per problem (empty: all intact, or no record yet).
    """
    out = folder(root, site_id)
    ledger = out / "ledger.jsonl"
    if not ledger.exists():
        return []
    problems = []
    previous: str | None = None
    for k, text in enumerate(ledger.read_text(encoding="utf-8").splitlines(), start=1):
        if not text.strip():
            continue
        line = json.loads(text)
        if line["previousLineSha256"] != previous:
            problems.append(f"{FOLDER} line {k}: the chain is broken")
        previous = hashlib.sha256(text.encode()).hexdigest()
        path = out / line["file"]
        if not path.exists():
            problems.append(f"{FOLDER} line {k}: {line['file']} is missing")
            continue
        rec = contract.DailyRecordV1.model_validate(json.loads(path.read_text(encoding="utf-8")))
        if not contract.is_sealed(rec) or rec.record_sha256 != line["recordSha256"]:
            problems.append(f"{FOLDER} line {k}: {line['file']} does not match its seal")
    return problems
