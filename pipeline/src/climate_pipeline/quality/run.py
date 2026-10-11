"""The offline analysis of the water-quality validation v2, from the committed snapshots.

Stages run as their inputs exist: Route B first (ACOLITE DSF and RAdCor with published and
pretrained models, and the adjacency rule, whose verdict picks Route A's primary window), then
Route A's Colombian part (pairs, A1, intervals, levels) once the value snapshot exists. A missing
snapshot makes its stage ``incomplete``, listed first in the summary, never an error.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from climate_pipeline.quality import lab, route_a, route_b, transfer
from climate_pipeline.quality.config import QualityConfig


@dataclass
class Results:
    """Every table and the summary of a run."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)  # the product models


def _rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def incomplete(cfg: QualityConfig, root: Path) -> list[str]:
    """What is missing from the Route B snapshots.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        One line per incomplete part.
    """
    base = root / cfg.outputs.inputs
    out = []
    counts = {}
    for correction, relative in route_b.SNAPSHOTS.items():
        log = _rows(base / Path(relative).parent / "run-log.csv")
        counts[correction] = sum(1 for r in _rows(base / relative))
        if not log:
            out.append(f"Route B {correction}: no snapshot")
            continue
        states: dict[str, int] = {}
        for r in log:
            states[r["status"]] = states.get(r["status"], 0) + 1
        missing = {s: n for s, n in sorted(states.items()) if s != "ok"}
        if counts[correction] < counts.get("dsf", counts[correction]):
            out.append(f"Route B {correction}: {counts[correction]} scenes measured, "
                       f"{counts['dsf']} under DSF; statuses {missing}")  # fmt: skip
    if not (base / route_b.MDN_SNAPSHOT).exists():
        out.append("Route B MDN (B3): no predictions")
    return out


def analyse(cfg: QualityConfig, root: Path) -> Results:
    """The whole offline analysis.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        Every table and the summary.
    """
    results = Results()
    missing = incomplete(cfg, root)
    rb = route_b.load(cfg, root)
    results.tables.update(route_b.analyse(cfg, rb))
    confirmed = bool(route_b.summary(results.tables)["adjacency_confirmed"])
    ci = route_a.load(cfg, root)
    usgs = transfer.load_usgs(cfg, root)
    if usgs is not None:
        usgs.forests = lab.forests(cfg, root)
        if not usgs.forests:
            missing.append("Route A A4: no lab model yet (pipeline/lab/README.md)")
    if usgs is None:
        missing.insert(0, "Route A (USGS pilot): no value snapshot yet; A2 and A3 not run")
    if ci is None:
        missing.insert(0, "Route A (Colombia): no value snapshot yet")
    else:
        tables = route_a.analyse(cfg, ci, confirmed, usgs)
        results.cards = tables.pop("_cards", [])
        results.tables.update(tables)
    results.summary = {
        "incomplete": missing,
        "route_a": route_a.summary(results.tables) if ci is not None else {},
        "route_b": route_b.summary(results.tables),
    }
    return results
