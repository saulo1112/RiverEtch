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

from climate_pipeline.quality import (
    gauged,
    lab,
    phase3,
    physical,
    posthoc,
    route_a,
    route_b,
    search,
    site,
    stage_b,
    temporal,
    transfer,
    v6,
    v7,
    variables,
)
from climate_pipeline.quality.config import QualityConfig


@dataclass
class Results:
    """Every table and the summary of a run."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)  # the product models
    posthoc_cards: list[dict[str, Any]] = field(default_factory=list)  # v2.1, labelled post hoc
    extra_cards: list[dict[str, Any]] = field(default_factory=list)  # v4: {"path", "card"}


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
        later = posthoc.analyse(cfg, ci, confirmed, usgs, ci.lab_dir)
        results.posthoc_cards = later.pop("_posthoc_cards", [])
        results.tables.update(later)
        landsat_scenes = phase3.load(cfg, root)
        if landsat_scenes is not None:
            results.tables.update(phase3.analyse(cfg, ci, landsat_scenes, confirmed, usgs))
    results.tables.update(physical.analyse(cfg, rb, posthoc.summary(results.tables)))
    if ci is not None:
        results.tables.update(stage_b.analyse(cfg, root, rb, ci, posthoc.summary(results.tables)))
    every = search.scenes(cfg, root, ci) if ci is not None else None
    if ci is not None and every is not None:
        a4 = (
            transfer.pretrained_models(cfg, usgs, search.TARGET, "core").get("A4") if usgs else None
        )
        dogliotti = route_b.published(rb)["turbidity"][physical.PUBLISHED["turbidity"]]
        radcor = {(p.station, p.sample_day): dogliotti(p, physical.CORRECTION)
                  for p in route_b.common_pairs(rb, "turbidity")[physical.CORRECTION]}  # fmt: skip
        results.tables.update(search.analyse(cfg, ci, every, a4, radcor))
        record = search.of_record(cfg, ci, every, a4)
        results.tables.update(record.tables)
        if record.data is not None:
            later3 = temporal.analyse(cfg, record.data, radcor)
            cards3 = later3.pop("_round3_card", [])
            round3 = cards3[0] if cards3 else None
            results.tables.update(later3)
            round1 = temporal.round1_card(cfg, record.data, record.plain,
                                          results.tables.get("v3_record_levels", []))  # fmt: skip
            chosen = temporal.product_card(round1, round3)
            named = (("turbidity.round1.json", round1), ("turbidity.round3.json", round3),
                     ("turbidity.json", chosen))  # fmt: skip
            for name, card in named:
                if card is not None:
                    results.extra_cards.append({"path": f"magdalena/{name}", "card": card})
    later_site = site.analyse(cfg, root, usgs)
    results.extra_cards += later_site.pop("_site_cards", [])
    results.tables.update(later_site)
    later_v5 = gauged.analyse(cfg, root, usgs)
    results.extra_cards += later_v5.pop("_v5_cards", [])
    link1 = {r["slug"]: r for r in later_v5.pop("_v6_link1", [])}
    end_to_end = {r["slug"]: r["pairs"] for r in later_v5.pop("_v6_end_to_end", [])}
    results.tables.update(later_v5)
    later_v6 = v6.analyse(cfg, root, link1, end_to_end)
    v6_cards = later_v6.pop("_v6_cards", [])
    results.extra_cards += v6_cards
    results.tables.update(later_v6)
    platte = f"{variables.THERMAL_REACH}/water_temperature.json"
    temperature = next((c["card"] for c in v6_cards if c["path"] == platte), None)
    later_v7 = v7.analyse(cfg, root, temperature)
    results.extra_cards += later_v7.pop("_v7_cards", [])
    results.tables.update(later_v7)
    results.summary = {
        "incomplete": missing,
        "route_a": route_a.summary(results.tables) if ci is not None else {},
        "posthoc": posthoc.summary(results.tables) if ci is not None else {},
        "physical": physical.summary(results.tables),
        "landsat": phase3.summary(results.tables),
        "v3": search.summary(results.tables),
        "route_b": route_b.summary(results.tables),
        "site": site.summary(results.tables),
        "v4_round3": temporal.summary(results.tables),
        "stage_b": stage_b.summary(results.tables),
        "v5": gauged.summary(results.tables),
        "v6": v6.summary(results.tables),
        "v7": v7.summary(results.tables),
    }
    return results
