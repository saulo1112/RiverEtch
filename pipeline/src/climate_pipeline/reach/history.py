"""A reach's station window in its earlier years (preregistration-along-river.md, section 5).

The baseline measured the station's (or the reading spot's) window on every pass from 2019
(``station-windows.csv``, committed). This module reads each of those passes with the reach's own
frozen card, exactly as a record's estimate is made, and writes ``history.json`` beside the
examples: the web's turbidity chart for a year before the sealed records. Nothing here is sealed:
it is recomputed from committed files. Each pass says whether the card was trained on it (a
station's own training years), was tested on it (its locked test), came after both, or is on a
river the card never saw.
"""

from __future__ import annotations

import csv
import io
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

from climate_pipeline.quality import cards, features
from climate_pipeline.quality.route_a import scenes_from_windows
from climate_pipeline.reach import records
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import ReachConfig


def _phase(card: dict[str, Any], day: date, ungauged: bool) -> str:
    if ungauged:
        return "unseen"
    train = card.get("training") or []
    test = card.get("lockbox") or []
    if len(train) == 2 and date.fromisoformat(train[0]) <= day <= date.fromisoformat(train[1]):
        return "training"
    if len(test) == 2 and date.fromisoformat(test[0]) <= day <= date.fromisoformat(test[1]):
        return "test"
    return "after"


def _num(x: float | None, digits: int = 2) -> float | None:
    return round(x, digits) if x is not None and math.isfinite(x) else None


def rows(s: reach_run.Setup) -> list[dict[str, Any]]:
    """Every earlier pass of the station window, read by the reach's turbidity card.

    Args:
        s: The reach's setup.

    Returns:
        One row per usable pass, oldest first (empty without a card or station windows).
    """
    folder = s.root / "docs" / "water-quality" / "reach" / s.reach.site
    windows = folder / "station-windows.csv"
    card = s.cards.get("turbidity")
    if card is None or not windows.exists() or s.station is None:
        return []
    excluded = set()
    baseline = folder / "nir-red-baseline.csv"
    if baseline.exists():
        for r in csv.DictReader(io.StringIO(baseline.read_text(encoding="utf-8"))):
            if r.get("exclusion"):
                excluded.add(r["key"])
    text = windows.read_text(encoding="utf-8")
    scenes = {w: scenes_from_windows(text, w) for w in ("300m", "core")}
    width = {sc.station: s.station.width_m for sc in scenes["300m"]}
    full = features.with_features(s.quality.features, scenes, width)
    target = next(t for t in s.quality.targets if t.id == "turbidity")
    sha = cards.card_hash(card)
    guards = s.quality.window.as_calibration()
    lab = s.root / s.quality.outputs.inputs / "lab"
    ungauged = s.reach.station_source != "usgs"
    out = []
    for sc in sorted(full.get(s.window, []), key=lambda x: (x.day, x.key)):
        if sc.key in excluded:
            continue
        measure = records.Measure(key=sc.key, day=sc.day, items=(), exclusion="", ndti={},
                                  nir_red={}, window=sc.features, stats=sc.stats)  # fmt: skip
        e = records.estimate(card, sha, target, measure, [], guards, lab)
        out.append({
            "date": sc.day.isoformat(), "key": sc.key,
            "value": _num(e.value), "low": _num(e.interval.low) if e.interval else None,
            "high": _num(e.interval.high) if e.interval else None,
            "fnuClass": str(e.fnu_class) if e.fnu_class is not None else None,
            "reason": e.abstain_reason,
            "phase": _phase(card, sc.day, ungauged),
        })  # fmt: skip
    return out


def write(cfg: ReachConfig, root: Path, site_id: str, cache: Path, workers: int = 8) -> Path:
    """Write ``history.json`` beside the reach's examples.

    Args:
        cfg: Reach settings.
        root: Repository root.
        site_id: The reach.
        cache: Cache folder.
        workers: Parallel reads for the geometry.

    Returns:
        The file's path.
    """
    from climate_pipeline.reach import along

    if not along.anchored(root):
        raise reach_run.ReachError(f"{site_id}: {along.PREREGISTRATION} is not anchored yet")
    s = reach_run.setup(cfg, root, site_id, cache, workers)
    path = root / "docs" / "water-quality" / "reach" / site_id / "examples" / "history.json"
    path.write_text(json.dumps(rows(s), indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")  # fmt: skip
    return path
