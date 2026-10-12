"""Route B of the water-quality validation v2: ACOLITE (DSF, RAdCor) with published models.

A physics check, report-only: nothing here reaches a record. The pairs are D15's Magdalena pairs
(the same samples, scenes and matching rules); the reflectances are ACOLITE's medians over the
exact L2A pixels (D15's deviation 5). L2A is scored on the same pairs, so the three corrections are
compared on the same samples. Models are published or pretrained and never retuned. Adjacency is
confirmed by the preregistered rule: on D15's training pairs, RAdCor's Spearman rho of B8A/B04
with turbidity reaches the bar, and the median B11 at narrow stations drops from DSF to RAdCor.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import models, stats
from climate_pipeline.calibration.config import CalibrationConfig, load_calibration_config
from climate_pipeline.calibration.fetching import CalibrationPaths, read_stations
from climate_pipeline.calibration.matchups import Pair, fittable, scenes_from_csv, split
from climate_pipeline.calibration.run import Inputs, load_inputs, target_pairs
from climate_pipeline.quality.config import QualityConfig

CORRECTIONS = ("l2a", "dsf", "radcor")
SNAPSHOTS = {"dsf": "acolite/dsf/windows.csv", "radcor": "acolite/radcor/windows.csv"}
MDN_SNAPSHOT = "mdn/predictions.csv"
Model = Callable[[Pair, str], float]


@dataclass
class RouteBInputs:
    """D15's settings and inputs, with the v2 ACOLITE scene sets, MDN outputs and widths."""

    d15: CalibrationConfig
    inputs: Inputs  # scene sets "l2a-300m", "dsf-300m", "radcor-300m"
    mdn: dict[tuple[str, str, str], float]  # (correction, station, scene key) -> TSS mg/L
    widths: dict[str, float]  # station -> main-channel width, m


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def parse_mdn(text: str) -> dict[tuple[str, str, str], float]:
    """The MDN's TSS estimates (``mdn/predictions.csv``).

    Args:
        text: The CSV text (empty when B3 did not run).

    Returns:
        ``(correction, station, key) -> mg/L``, finite values only.
    """
    out = {}
    for row in csv.DictReader(io.StringIO(text)) if text else []:
        try:
            value = float(row["tss_mg_l"])
        except ValueError:
            continue
        if math.isfinite(value):
            out[(row["correction"], row["station"], row["key"])] = value
    return out


def load(cfg: QualityConfig, root: Path) -> RouteBInputs:
    """D15's inputs plus the ACOLITE snapshots and MDN estimates of v2.

    Args:
        cfg: The v2 settings.
        root: Repository root.

    Returns:
        The inputs of Route B.
    """
    d15_path = root / cfg.calibration_config
    d15 = load_calibration_config(d15_path)
    inputs = load_inputs(d15, CalibrationPaths(root, d15_path, root / "pipeline" / "out"))
    n = inputs.nechad
    switch = (n[("TUR", "B4")], n[("TUR", "B8A")]) if ("TUR", "B8A") in n else None
    base = root / cfg.outputs.inputs
    for correction, relative in SNAPSHOTS.items():
        inputs.scenes[f"{correction}-300m"] = scenes_from_csv(
            _read(base / relative), "300m", switch
        )
    stations = read_stations(root / d15.outputs.inputs / "stations" / "stations.csv")
    widths = {r["station_id"]: float(r["width_m"]) for r in stations if r.get("width_m")}
    return RouteBInputs(d15, inputs, parse_mdn(_read(base / MDN_SNAPSHOT)), widths)


def published(rb: RouteBInputs) -> dict[str, dict[str, Model]]:
    """The Route B models per target (``model(pair, correction) -> estimate``).

    Args:
        rb: The inputs (coefficients from ACOLITE's tables, as D15's Stage 4).

    Returns:
        Target -> model id -> model.
    """
    n = rb.inputs.nechad
    low, high = rb.inputs.dogliotti_limits

    def b04(p: Pair) -> float:
        return p.features.get("B04", math.nan)

    def dogliotti(p: Pair, _: str) -> float:
        return models.dogliotti_switch(b04(p), p.features.get("B8A", math.nan),
                                       n[("TUR", "B4")], n[("TUR", "B8A")], low, high)  # fmt: skip

    def mdn(p: Pair, correction: str) -> float:
        return rb.mdn.get((correction, p.station, p.scene_key), math.nan)

    return {
        "turbidity": {
            "B1 Dogliotti 2015": dogliotti,
            "B2 Nechad 2009": lambda p, _: models.nechad(b04(p), *n[("TUR", "B4")]),
        },
        "tss": {
            "B2 Nechad 2010": lambda p, _: models.nechad(b04(p), *n[("SPM", "B4")]),
            "B3 MDN": mdn,
        },
    }


def common_pairs(rb: RouteBInputs, target: str) -> dict[str, list[Pair]]:
    """Each correction's pairs, restricted to the samples every correction pairs.

    Args:
        rb: The inputs.
        target: ``turbidity`` or ``tss``.

    Returns:
        Correction -> its pairs, in the same sample order.
    """
    found = {
        c: {(p.station, p.sample_day): p
            for p in fittable(target_pairs(rb.d15, rb.inputs, target, f"{c}-300m"))}
        for c in CORRECTIONS
    }  # fmt: skip
    shared = sorted(set.intersection(*(set(v) for v in found.values())))
    return {c: [found[c][k] for k in shared] for c in CORRECTIONS}


def _seed(base: int, *keys: str) -> int:
    text = "|".join(keys)
    return base + sum((k + 1) * ord(c) for k, c in enumerate(text)) % 100_000


def score(
    predicted: Sequence[float],
    observed: Sequence[float],
    clusters: Sequence[str],
    seed: int,
    resamples: int,
    confidence: float,
) -> dict[str, float]:
    """MdSA, SSPB, MAPE and Spearman rho (cluster-bootstrap interval) over the valid estimates.

    Args:
        predicted: Estimates (NaN where a model has no value).
        observed: Measured values.
        clusters: Acquisition of each pair.
        seed: Bootstrap seed.
        resamples: Bootstrap draws.
        confidence: Interval coverage.

    Returns:
        ``n`` and the metrics.
    """
    keep = [k for k, v in enumerate(predicted) if math.isfinite(v) and v > 0]
    p = [predicted[k] for k in keep]
    o = [observed[k] for k in keep]
    low, high = stats.block_bootstrap_spearman(p, o, [clusters[k] for k in keep], resamples, seed,
                                               confidence)  # fmt: skip
    return {"n": float(len(keep)), "mdsa": stats.mdsa(p, o), "sspb": stats.sspb(p, o),
            "mape": stats.mape(p, o), "rho": stats.spearman(p, o), "rho_low": low,
            "rho_high": high}  # fmt: skip


def bin_label(edges: Sequence[float], k: int) -> str:
    """A readable range for bin ``k`` (``<30``, ``30-100``, ``>=1000``).

    Args:
        edges: Upper edges.
        k: Bin index.

    Returns:
        The label.
    """
    if k == 0:
        return f"<{edges[0]:g}"
    if k == len(edges):
        return f">={edges[-1]:g}"
    return f"{edges[k - 1]:g}-{edges[k]:g}"


def analyse(cfg: QualityConfig, rb: RouteBInputs) -> dict[str, list[dict[str, Any]]]:
    """Every Route B table.

    Args:
        cfg: The v2 settings.
        rb: The inputs.

    Returns:
        Table name -> rows.
    """
    sel = cfg.selection
    scores: list[dict[str, Any]] = []
    bins: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    for target, plan in published(rb).items():
        edges = cfg.target(target).bins
        by_correction = common_pairs(rb, target)
        for name, model in plan.items():
            for correction, pairs in by_correction.items():
                predicted = [float(model(p, correction)) for p in pairs]
                observed = [p.value for p in pairs]
                row = score(predicted, observed, [p.scene_key for p in pairs],
                            _seed(cfg.seed, "route_b", target, name, correction),
                            sel.bootstrap_resamples, sel.confidence)  # fmt: skip
                if row["n"] == 0:
                    continue
                stations = {p.station for p, v in zip(pairs, predicted, strict=True)
                            if math.isfinite(v) and v > 0}  # fmt: skip
                scores.append({"target": target, "model": name, "correction": correction,
                               "stations": len(stations), **row})  # fmt: skip
                for k in range(len(edges) + 1):
                    sub = [
                        (v, o)
                        for v, o in zip(predicted, observed, strict=True)
                        if math.isfinite(v) and v > 0 and cfg.target(target).bin_of(v) == k
                    ]
                    if sub:
                        bins.append({"target": target, "model": name, "correction": correction,
                                     "predicted_range": bin_label(edges, k), "n": len(sub),
                                     "mdsa": stats.mdsa([v for v, _ in sub], [o for _, o in sub]),
                                     "rated": len(sub) >= cfg.levels.min_bin_pairs})  # fmt: skip
                for p, v in zip(pairs, predicted, strict=True):
                    pair_rows.append({"target": target, "model": name, "correction": correction,
                                      "station": p.station, "sample_day": p.sample_day,
                                      "scene_key": p.scene_key, "value": p.value,
                                      "estimate": v})  # fmt: skip
    return {
        "route_b_scores": scores,
        "route_b_bins": bins,
        "route_b_pairs": pair_rows,
        "route_b_adjacency": adjacency(cfg, rb),
    }


def adjacency(cfg: QualityConfig, rb: RouteBInputs) -> list[dict[str, Any]]:
    """The preregistered adjacency rule, with its inputs per correction.

    Args:
        cfg: The v2 settings.
        rb: The inputs.

    Returns:
        One row per correction and a final ``rule`` row.
    """
    rule = cfg.route_b.adjacency
    l2a = fittable(target_pairs(rb.d15, rb.inputs, "turbidity", "l2a-300m"))
    _, train, _ = split(l2a, rb.d15.matchups.holdout_share)
    rows: list[dict[str, Any]] = []
    rhos: dict[str, float] = {}
    b11: dict[str, float] = {}
    for correction in CORRECTIONS:
        scenes = {(s.station, s.key): s for s in rb.inputs.scenes[f"{correction}-300m"]}
        use = [(scenes[(p.station, p.scene_key)].features.get("B8A/B04", math.nan), p)
               for p in train if (p.station, p.scene_key) in scenes]  # fmt: skip
        use = [(x, p) for x, p in use if math.isfinite(x)]
        x, y = [u for u, _ in use], [p.value for _, p in use]
        low, high = stats.block_bootstrap_spearman(
            x, y, [p.scene_key for _, p in use], cfg.selection.bootstrap_resamples,
            _seed(cfg.seed, "adjacency", correction), cfg.selection.confidence,
        )  # fmt: skip
        rhos[correction] = stats.spearman(x, y)
        acolite_keys = {(s.station, s.key) for s in rb.inputs.scenes["dsf-300m"]}
        narrow = [s.bands.get("B11", math.nan) for (station, key), s in scenes.items()
                  if (station, key) in acolite_keys
                  and rb.widths.get(station, math.inf) < rule.narrow_width_m]  # fmt: skip
        finite = [v for v in narrow if math.isfinite(v)]
        b11[correction] = float(np.median(finite)) if finite else math.nan
        rows.append({"correction": correction, "training_pairs": len(use), "rho": rhos[correction],
                     "rho_low": low, "rho_high": high, "narrow_scenes": len(finite),
                     "median_b11_narrow": b11[correction]})  # fmt: skip
    confirmed = (math.isfinite(rhos["radcor"]) and rhos["radcor"] >= rule.rho_min
                 and b11["radcor"] < b11["dsf"])  # fmt: skip
    rows.append({"correction": "rule", "rho": rule.rho_min, "median_b11_narrow": math.nan,
                 "confirmed": confirmed,
                 "note": f"RAdCor rho >= {rule.rho_min:g} and its median B11 below DSF's at "
                         f"stations under {rule.narrow_width_m:g} m"})  # fmt: skip
    return rows


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """The Route B headline: the best MdSA per target and correction, and the adjacency verdict.

    Args:
        tables: Route B tables.

    Returns:
        JSON-ready summary.
    """
    best: dict[str, dict[str, Any]] = {}
    for row in tables["route_b_scores"]:
        key = f"{row['target']}/{row['correction']}"
        if math.isfinite(row["mdsa"]) and (key not in best or row["mdsa"] < best[key]["mdsa"]):
            best[key] = {"model": row["model"], "mdsa": round(row["mdsa"], 1), "n": int(row["n"])}
    rule = next(r for r in tables["route_b_adjacency"] if r["correction"] == "rule")
    return {"best_mdsa": dict(sorted(best.items())), "adjacency_confirmed": rule["confirmed"]}
