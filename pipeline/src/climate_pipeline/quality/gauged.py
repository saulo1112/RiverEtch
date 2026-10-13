"""v5: the gauged rivers where the pipeline can show values (preregistration v5).

Every river that met v5's fixed data criteria is validated with Hermann's locked-test protocol
(:mod:`climate_pipeline.quality.site`) under v5's level rules: turbidity everywhere, and suspended
sediment where a target exists (discrete SSC samples, or the USGS surrogate SSC record, which the
USGS estimates from turbidity and is labelled so). The two demo reaches are the two gauged reaches
with the highest turbidity level of record (Hermann's from v4 included); ties go to the lower
lock-box MdSA, then to the larger lock box. Every site is reported.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration.fetching import read_stations
from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import cards as cards_mod
from climate_pipeline.quality import site, transfer, variables
from climate_pipeline.quality.config import QualityConfig

FOLDER = "usgs-v5"
SITES_FILE = f"{FOLDER}/sites.csv"
MIN_LOCK_PAIRS = 20  # a smaller lock box is reported as insufficient_data
LABS = {"MISSISSIPPI": "no-mississippi", "PLATTE": "no-platte", "OHIO": "no-ohio",
        "MISSOURI": "no-missouri"}  # fmt: skip
SLUGS = {
    "USGS-07020850": "mississippi-cape-girardeau", "USGS-07374525": "mississippi-belle-chasse",
    "USGS-07381600": "atchafalaya-morgan-city", "USGS-06805500": "platte-louisville",
    "USGS-03216070": "ohio-ironton", "USGS-14246900": "columbia-port-westward",
    "USGS-14144700": "columbia-vancouver", "USGS-11337190": "san-joaquin-jersey-point",
    "USGS-14211720": "willamette-portland", "USGS-01193050": "connecticut-middle-haddam",
    "USGS-06934500": site.SLUG,
}  # fmt: skip
SURROGATE_NOTE = "SSC estimated by the USGS from turbidity (surrogate record, 99409)"
LEVEL_ORDER = ("none", "indicative", "estimated", "validated")


def runs(root: Path, cfg: QualityConfig) -> list[tuple[site.Run, str]]:
    """Every v5 run: turbidity at each new site, and SSC where the list names a target.

    Args:
        root: Repository root.
        cfg: Settings.

    Returns:
        ``(run, source)`` with source ``turbidity``, ``ssc`` (discrete) or ``surrogate``.
    """
    path = root / cfg.outputs.inputs / SITES_FILE
    if not path.exists():
        return []
    out: list[tuple[site.Run, str]] = []
    for r in read_stations(path):
        if r["selected"] != "true":
            continue
        sid, river = r["site_id"], r["river"]
        lab, slug = LABS.get(river, ""), SLUGS[sid]
        if sid != site.SITE:  # Hermann's turbidity keeps its v4 level of record
            out.append((site.Run(sid, slug, river, "turbidity", "FNU", lab,
                                 ("v5", sid, "turbidity"), "v5"), "turbidity"))  # fmt: skip
        if r["ssc_target"]:
            source = "surrogate" if r["ssc_target"] == "99409" else "ssc"
            out.append((site.Run(sid, slug, river, "tss", "mg/L", lab, ("v5", sid, "tss"), "v5"),
                        source))  # fmt: skip
    return out


def pairs_by_source(cfg: QualityConfig, root: Path) -> dict[str, list[Pair]] | None:
    """v5's pairs by source (core window): turbidity, discrete SSC and surrogate SSC.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        Source -> pairs (None before the fetch has written its snapshots).
    """
    out: dict[str, list[Pair]] = {"turbidity": [], "ssc": [], "surrogate": []}
    main = transfer.load_usgs(cfg, root, folder=FOLDER, sites_file=SITES_FILE)
    if main is None:
        return None
    out["turbidity"] = main.pairs.get(("turbidity", site.WINDOW), [])
    out["ssc"] = main.pairs.get(("tss", site.WINDOW), [])
    surrogate = transfer.load_usgs(cfg, root, folder=FOLDER, sites_file=SITES_FILE,
                                   turbidity_file="ssc-surrogate.csv")  # fmt: skip
    if surrogate is not None:
        found = surrogate.pairs.get(("turbidity", site.WINDOW), [])
        out["surrogate"] = [replace(p, target="tss") for p in found]
    return out


def demo(candidates: Sequence[Mapping[str, Any]], n: int = 2) -> list[str]:
    """The demo reaches: the highest level, then the lower MdSA, then the larger lock box.

    Args:
        candidates: ``slug``, ``level``, ``mdsa`` and ``n`` of each gauged reach's turbidity.
        n: How many.

    Returns:
        The slugs, best first.
    """
    ranked = sorted(candidates, key=lambda c: (-LEVEL_ORDER.index(c["level"]),
                                               c["mdsa"] if math.isfinite(c["mdsa"]) else math.inf,
                                               -c["n"], c["slug"]))  # fmt: skip
    return [str(c["slug"]) for c in ranked[:n]]


def analyse(cfg: QualityConfig, root: Path,
            usgs: transfer.UsgsInputs | None) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """v5's tables and cards (under ``_v5_cards``).

    Args:
        cfg: Settings.
        root: Repository root.
        usgs: The USGS pilot (pretraining).

    Returns:
        ``v5_scores``, ``v5_levels``, ``v5_inner`` and ``v5_demo``.
    """
    tables: dict[str, list[dict[str, Any]]] = {"v5_scores": [], "v5_levels": [], "v5_inner": [],
                                               "v5_demo": []}  # fmt: skip
    planned = runs(root, cfg)
    if not planned or usgs is None:
        tables["v5_scores"].append({"status": "v5 not fetched yet"})
        return tables
    by_source = pairs_by_source(cfg, root)
    if by_source is None:
        tables["v5_scores"].append({"status": "v5 not fetched yet"})
        return tables
    cards: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    link1: dict[str, dict[str, Any]] = {}  # v6's chain: each demo gauge's turbidity card
    for run, source in planned:
        pairs = [p for p in by_source[source] if p.station == run.site]
        _, lock = site.split(pairs)
        label = {"source": SURROGATE_NOTE if source == "surrogate" else source}
        if len(lock) < MIN_LOCK_PAIRS:
            tables["v5_scores"].append({"site": run.site, "target": run.target, "unit": run.unit,
                                        **label, "status": "insufficient_data",
                                        "lockbox_pairs": len(lock)})  # fmt: skip
            continue
        result = site.evaluate(cfg, root, usgs, run, pairs)
        tables["v5_scores"] += [{**r, **label} for r in result.scores]
        tables["v5_levels"] += [{**r, **label} for r in result.levels]
        tables["v5_inner"] += result.inner
        card = {**result.card, **({"measurement": SURROGATE_NOTE} if source == "surrogate" else {})}
        cards.append({"path": run.card_path, "card": card})
        if run.target == "turbidity" and run.slug in variables.GAUGES:
            link1[run.slug] = {"card": result.card, "card_path": run.card_path,
                               "residuals": result.inner_log_errors}  # fmt: skip
        if run.target == "turbidity":
            overall = result.levels[0]
            candidates.append({"slug": run.slug, "site": run.site, "level": overall["level"],
                               "mdsa": overall["mdsa"], "n": overall["n"],
                               "record": "v5"})  # fmt: skip
    hermann = transfer.load_usgs(cfg, root, folder=site.FOLDER)
    if hermann is not None:  # Hermann's v4 turbidity, and (report-only) under the v5 rule
        pairs = [p for p in hermann.pairs.get((site.TARGET, site.WINDOW), [])
                 if p.station == site.SITE]  # fmt: skip
        v4 = site.evaluate(cfg, root, usgs, site.HERMANN, pairs).levels[0]
        candidates.append({"slug": site.SLUG, "site": site.SITE, "level": v4["level"],
                           "mdsa": v4["mdsa"], "n": v4["n"], "record": "v4"})  # fmt: skip
        later = site.evaluate(cfg, root, usgs, replace(site.HERMANN, rule="v5"), pairs).levels[0]
        tables["v5_scores"].append({
            "site": site.SITE, "target": site.TARGET, "unit": site.UNIT, "source": "turbidity",
            "candidate": later["candidate"],
            "evaluation": "report-only: Hermann's v4 card under the v5 rule (written after "
            "seeing it); its level of record stays v4's",
            "n": later["n"], "mdsa": later["mdsa"], "sspb": later["sspb"],
            "rho_low": later["rho_low"], "null_mdsa": later["null_mdsa"],
            "coverage90": later["coverage90"], "interval_factor90": later["interval_factor90"],
            "level": later["level"],
        })  # fmt: skip
    chosen = demo(candidates)
    tables["v5_demo"] = [{**c, "demo": c["slug"] in chosen,
                          "rank": chosen.index(c["slug"]) + 1 if c["slug"] in chosen else None}
                         for c in sorted(candidates, key=lambda c: c["slug"])]  # fmt: skip
    tables["_v5_cards"] = cards
    # v6's end-to-end check: the lock-box SSC samples on a clear pass's day, with the turbidity
    # card's estimate of that pass.
    lab = root / cfg.outputs.inputs / "lab"
    end_to_end: dict[str, list[tuple[float, float]]] = {}
    for slug, link in link1.items():
        site_id = variables.GAUGES[slug]
        _, lock = site.split([p for p in by_source.get("ssc", []) if p.station == site_id])
        end_to_end[slug] = [(cards_mod.estimate(link["card"], p.features, lab), p.value)
                            for p in lock]  # fmt: skip
    tables["_v6_link1"] = [{"slug": s, **v} for s, v in link1.items()]
    tables["_v6_end_to_end"] = [{"slug": s, "pairs": v} for s, v in end_to_end.items()]
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """v5's demo reaches, each site's turbidity result and the median over all of them.

    Args:
        tables: The run's tables.

    Returns:
        ``demo``, ``turbidity`` (slug -> level, MdSA, n), ``tss`` and ``median_turbidity_mdsa``.
    """
    rows = tables.get("v5_demo", [])
    if not rows:
        return {}
    levels = [r for r in tables.get("v5_levels", []) if r.get("predicted_range") == "all"]
    by = {(r["site"], r["target"]): r for r in levels}
    slug_of = {r["site"]: r["slug"] for r in rows}
    tss = {slug_of.get(s, s): {"level": r["level"], "mdsa": round(r["mdsa"], 1), "n": r["n"],
                               "source": r["source"]}
           for (s, t), r in by.items() if t == "tss"}  # fmt: skip
    mdsas = [r["mdsa"] for r in rows if r["record"] == "v5" and math.isfinite(r["mdsa"])]
    return {
        "demo": [r["slug"] for r in sorted((x for x in rows if x["demo"]),
                                           key=lambda x: x["rank"])],
        "turbidity": {r["slug"]: {"level": r["level"], "mdsa": round(r["mdsa"], 1), "n": r["n"],
                                  "record": r["record"]} for r in rows},
        "tss": tss,
        "median_turbidity_mdsa": round(float(np.median(mdsas)), 1) if mdsas else None,
        "sites_evaluated": len(mdsas),
    }  # fmt: skip
