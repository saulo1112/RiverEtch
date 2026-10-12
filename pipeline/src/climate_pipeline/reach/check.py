"""``climate-pipeline reach check``: a gauged reach's estimates against its gauge (report-only).

v4's prospective check (preregistration, A). ``reach run`` notes, beside the sealed records and
never in them, the card's raw estimate of every recorded scene of a reach whose estimate station
is a USGS gauge (``checks/estimates.jsonl``). This command pairs the scenes acquired after the
card's commit with the gauge's turbidity at the overpass (the pilot's rule, any approval state,
which is labelled) and writes ``checks/checks.csv`` and ``checks/summary.json``. It never sets a
level: the provisional values can still change.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx

from climate_pipeline.calibration import stats
from climate_pipeline.quality.config import load_quality_config
from climate_pipeline.reach.config import Reach, ReachConfig
from climate_pipeline.sources import usgs

FOLDER = "checks"
COLUMNS = ("date", "sceneId", "key", "datetimeUtc", "target", "estimate", "value", "approval",
           "rule", "n", "cardSha256")  # fmt: skip
APPROVALS = ("Approved", "Provisional")
NOTE = "unpublished: the card's raw estimate, for the prospective check only"


def note_estimate(folder: Path, scene_id: str, key: str, when: datetime, target: str,
                  card_sha256: str, value: float) -> None:  # fmt: skip
    """Append one scene's raw estimate to ``checks/estimates.jsonl`` (never a record).

    Args:
        folder: The reach's output folder.
        scene_id: The record's scene id.
        key: The acquisition key.
        when: The acquisition time.
        target: The target.
        card_sha256: The card's hash.
        value: The raw estimate.
    """
    path = folder / FOLDER / "estimates.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"sceneId": scene_id, "key": key, "target": target, "cardSha256": card_sha256,
            "datetimeUtc": when.astimezone(UTC).isoformat(timespec="seconds"),
            "estimate": round(value, 4), "note": NOTE}  # fmt: skip
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(line, sort_keys=True) + "\n")


def committed_at(root: Path, path: str) -> datetime | None:
    """When a file was first committed (git), or None when it is not committed.

    Args:
        root: Repository root.
        path: The file, relative to the root.

    Returns:
        The commit time (UTC).
    """
    command = ["git", "-C", str(root), "log", "--diff-filter=A", "--format=%cI", "--", path]
    out = subprocess.run(command, capture_output=True, text=True, check=False).stdout.split()
    return datetime.fromisoformat(out[-1]).astimezone(UTC) if out else None


@dataclass
class CheckSummary:
    """What one check found."""

    since: str
    rows: int
    paired: int
    mdsa: float
    sspb: float
    approvals: dict[str, int]


def check(cfg: ReachConfig, reach: Reach, root: Path, http: httpx.Client | None = None,
          since: datetime | None = None) -> CheckSummary:  # fmt: skip
    """Pair the noted estimates after the card's commit with the gauge (any approval, labelled).

    Args:
        cfg: Reach settings.
        reach: A reach whose estimate station is a USGS gauge.
        root: Repository root.
        http: HTTP client (injectable).
        since: The first acquisition time (default: the turbidity card's first commit).

    Returns:
        The summary, also written to ``checks/summary.json``.

    Raises:
        ValueError: For a reach without a USGS gauge or a committed card.
    """
    if reach.station_source != "usgs":
        raise ValueError(f"{reach.site}: its estimate station is not a USGS gauge")
    card = reach.cards.get("turbidity")
    start = since or (committed_at(root, card) if card else None)
    if start is None:
        raise ValueError(f"{reach.site}: the turbidity card is not committed yet")
    quality = load_quality_config(root / cfg.quality_config)
    u = quality.usgs
    folder = root / cfg.out / reach.site
    path = folder / FOLDER / "estimates.jsonl"
    lines = [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines()
             if t.strip()] if path.exists() else []  # fmt: skip
    noted = {(r["key"], r["target"]): r for r in lines}  # the latest note of a scene wins
    todo = sorted((r for r in noted.values()
                   if datetime.fromisoformat(r["datetimeUtc"]) > start),
                  key=lambda r: r["datetimeUtc"])  # fmt: skip
    client = http or httpx.Client(timeout=120, follow_redirects=True)
    margin = timedelta(minutes=u.overpass_nearest_minutes)
    rows: list[dict[str, Any]] = []
    for r in todo:
        when = datetime.fromisoformat(r["datetimeUtc"])
        window = [(when - margin, when + margin)]
        _, bodies = usgs.continuous_many(client, u.api, reach.estimate_station,
                                         u.turbidity_parameter, window)  # fmt: skip
        readings = usgs.readings_from_bodies(bodies)
        value, rule, n, approval = math.nan, "none", 0, ""
        for status in APPROVALS:
            value, rule, n = usgs.overpass_value(readings, when, u.overpass_median_minutes,
                                                 u.overpass_nearest_minutes, status,
                                                 u.exclude_qualified)  # fmt: skip
            if math.isfinite(value):
                approval = status
                break
        rows.append({"date": when.date().isoformat(), "sceneId": r["sceneId"], "key": r["key"],
                     "datetimeUtc": r["datetimeUtc"], "target": r["target"],
                     "estimate": r["estimate"], "value": value, "approval": approval,
                     "rule": rule, "n": n, "cardSha256": r["cardSha256"]})  # fmt: skip
    paired = [x for x in rows if math.isfinite(x["value"]) and x["value"] > 0
              and x["estimate"] > 0]  # fmt: skip
    est = [float(x["estimate"]) for x in paired]
    obs = [float(x["value"]) for x in paired]
    summary = CheckSummary(
        start.isoformat(timespec="seconds"), len(rows), len(paired),
        stats.mdsa(est, obs) if paired else math.nan, stats.sspb(est, obs) if paired else math.nan,
        {a: sum(1 for x in paired if x["approval"] == a) for a in APPROVALS},
    )  # fmt: skip
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    for x in rows:
        writer.writerow(["" if isinstance(x[c], float) and math.isnan(x[c]) else x[c]
                         for c in COLUMNS])  # fmt: skip
    (folder / FOLDER / "checks.csv").write_text(out.getvalue(), encoding="utf-8", newline="\n")
    info = {**summary.__dict__, "site": reach.site, "station": reach.estimate_station,
            "unit": "FNU", "note": "report-only; never a level (values may be provisional)",
            "checksSha256": hashlib.sha256(out.getvalue().encode()).hexdigest()}  # fmt: skip
    clean = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in info.items()}
    text = json.dumps(clean, indent=2) + "\n"
    (folder / FOLDER / "summary.json").write_text(text, encoding="utf-8", newline="\n")
    return summary
