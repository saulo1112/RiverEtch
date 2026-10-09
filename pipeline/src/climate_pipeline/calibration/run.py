"""The offline analysis: every result from the committed snapshots, without the network.

Stages run in the preregistered order: pairs and splits, Stage 1 (band diagnostic, training
only), Stage 2 (processing homogeneity), Stage 3 (calibration, only where Stage 1 passed),
Stage 4 (published models, report-only), Stage 5 (climate and hydrology), the maturity level and
the observation records. Tables are lists of rows; :mod:`climate_pipeline.calibration.report`
writes them.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import climate, models, stats
from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.fetching import CalibrationPaths, read_stations
from climate_pipeline.calibration.matchups import (
    CANDIDATES,
    Pair,
    Sample,
    SceneRow,
    fittable,
    match,
    reduce_replicates,
    samples_from_series,
    samples_from_soda,
    scenes_from_csv,
    split,
)
from climate_pipeline.calibration.stations import number
from climate_pipeline.contract import observation as obs

log = logging.getLogger(__name__)
NOT_RUN = "not_run"


@dataclass
class Inputs:
    """Everything the analysis reads, parsed from the snapshots."""

    stations: list[dict[str, str]]
    samples: list[Sample]
    scenes: dict[str, list[SceneRow]]  # "l2a-300m", "l2a-1000m", "c1-300m", "acolite-300m"
    extents: list[dict[str, str]]
    series: dict[tuple[str, str], dict[date, float]]
    rain: dict[date, float]
    chirps: dict[date, float]
    oni: list[tuple[int, int, float]]
    nechad: dict[tuple[str, str], tuple[float, float]]  # (TUR|SPM, band) -> (A, C)
    dogliotti_limits: tuple[float, float]
    items: dict[str, obs.ItemMeta]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text))) if text else []


def parse_nechad(text: str) -> dict[tuple[str, str], tuple[float, float]]:
    """Sentinel-2 (MSI) Nechad coefficients from ACOLITE's calibration table.

    Args:
        text: ``Nechad_calibration_201609.txt``.

    Returns:
        ``(parameter, band) -> (A, C)`` for ``TUR`` and ``SPM``.
    """
    out = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 6 and parts[1] == "MSI" and parts[0] in ("TUR", "SPM"):
            out[(parts[0], parts[2])] = (float(parts[4]), float(parts[5]))
    return out


def parse_dogliotti_limits(text: str) -> tuple[float, float]:
    """The red-reflectance limits of the Dogliotti switch (``lower_lim``, ``upper_lim``).

    Args:
        text: ACOLITE's ``Dogliotti/defaults.txt``.

    Returns:
        ``(low, high)``; the published 0.05 and 0.07 when absent.
    """
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    return float(values.get("lower_lim", 0.05)), float(values.get("upper_lim", 0.07))


def daily_mean(per_point: Sequence[Mapping[date, float]]) -> dict[date, float]:
    """Catchment-mean daily rain (a day counts only when every point has it).

    Args:
        per_point: One day -> mm mapping per grid point.

    Returns:
        Day -> mean mm.
    """
    if not per_point:
        return {}
    days = set.intersection(*(set(p) for p in per_point))
    out = {}
    for d in sorted(days):
        values = [p[d] for p in per_point]
        if all(math.isfinite(v) for v in values):
            out[d] = float(np.mean(values))
    return out


def load_inputs(cfg: CalibrationConfig, paths: CalibrationPaths) -> Inputs:
    """Parse every snapshot.

    Args:
        cfg: Settings.
        paths: Paths.

    Returns:
        The inputs.
    """
    base = paths.at(cfg.outputs.inputs)
    stations = [r for r in read_stations(base / "stations" / "stations.csv")
                if r["selected"] == "true"]  # fmt: skip
    point_station = {r["quality_point"]: r["station_id"] for r in stations if r["quality_point"]}
    target_of = {t.variable: t.id for t in cfg.targets if t.variable}
    soda_text = _read(base / "ideam" / "quality-samples.json")
    samples = samples_from_soda(json.loads(soda_text) if soda_text else [], point_station,
                                target_of)  # fmt: skip
    series: dict[tuple[str, str], dict[date, float]] = {}
    labels = (*cfg.stations.daily_labels, *cfg.stations.monthly_labels)
    for row in stations:
        for label in labels:
            text = _read(base / "ideam" / label / f"{row['code']}-{label}.csv")
            if not text:
                continue
            parsed = samples_from_series(text, row["station_id"], label)
            series[(row["station_id"], label)] = {s.day: s.value for s in parsed}
            if label == "CM_D":
                samples += [s for s in parsed if True]
    samples = [
        Sample(s.station, s.day, "cm_d" if s.target == "CM_D" else s.target, s.value, s.censored,
               s.state)
        for s in samples
    ]  # fmt: skip
    nechad = parse_nechad(_read(base / "coefficients" / "Nechad_calibration_201609.txt"))
    switch = None
    if ("TUR", "B4") in nechad and ("TUR", "B8A") in nechad:
        switch = (nechad[("TUR", "B4")], nechad[("TUR", "B8A")])
    scenes = {}
    for name, file, window in (
        ("l2a-300m", f"windows-{cfg.imagery.primary}.csv", "300m"),
        ("l2a-1000m", f"windows-{cfg.imagery.primary}.csv", "1000m"),
        ("c1-300m", f"windows-{cfg.imagery.sensitivity}.csv", "300m"),
        ("acolite-300m", "acolite-windows.csv", "300m"),
    ):
        scenes[name] = scenes_from_csv(_read(base / "imagery" / file), window, switch)
    grid_ids = [p.stem for p in sorted((base / "rain" / "open-meteo").glob("*.json"))]
    per_point = []
    for point in grid_ids:
        data = json.loads(_read(base / "rain" / "open-meteo" / f"{point}.json"))
        daily = data.get("daily", {})
        per_point.append({
            date.fromisoformat(d): (float(v) if v is not None else math.nan)
            for d, v in zip(daily.get("time", []), daily.get("precipitation_sum", []), strict=True)
        })  # fmt: skip
    chirps_rows = _rows(_read(base / "rain" / "chirps-daily.csv"))
    chirps = {}
    for r in chirps_rows:
        values = [number(v) for k, v in r.items() if k != "date"]
        if values and all(math.isfinite(v) for v in values):
            chirps[date.fromisoformat(r["date"])] = float(np.mean(values))
    items = {}
    for r in _rows(_read(base / "reach" / "items.csv")):
        offset = {"true": True, "false": False}.get(r["boa_offset_applied"].lower())
        items[r["id"]] = obs.ItemMeta(r["url"], r["sha256"], r["retrieved_utc"], offset,
                                      r["processing_baseline"])  # fmt: skip
    return Inputs(
        stations=stations, samples=reduce_replicates(samples), scenes=scenes,
        extents=_rows(_read(base / "imagery" / "extents.csv")), series=series,
        rain=daily_mean(per_point), chirps=chirps,
        oni=climate.parse_oni(_read(base / "climate" / "oni.ascii.txt")), nechad=nechad,
        dogliotti_limits=parse_dogliotti_limits(_read(base / "coefficients" / "defaults.txt")),
        items=items,
    )  # fmt: skip


@dataclass
class Results:
    """Every table, model card and record of a run."""

    tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    plots: dict[str, Any] = field(default_factory=dict)


def target_pairs(
    cfg: CalibrationConfig, inputs: Inputs, target: str, scenes: str, days: int | None = None
) -> list[Pair]:
    """One target's pairs on one scene set.

    Args:
        cfg: Settings.
        inputs: Inputs.
        target: Target id.
        scenes: Scene set name (e.g. ``l2a-300m``).
        days: Matching window (default: the target's primary window).

    Returns:
        The pairs.
    """
    t = cfg.target(target)
    window = days
    if window is None:
        window = cfg.matchups.daily_target_days if t.kind == "daily" else cfg.matchups.primary_days
    samples = [s for s in inputs.samples if s.target == target]
    return match(samples, inputs.scenes.get(scenes, []), window, cfg.window)


def _seed(cfg: CalibrationConfig, *keys: str) -> int:
    text = "|".join(keys)
    return cfg.seed + sum((k + 1) * ord(c) for k, c in enumerate(text)) % 100_000


def diagnose(
    cfg: CalibrationConfig, pairs: Sequence[Pair], target: str, candidate: str, tag: str
) -> dict[str, object]:
    """Stage 1 for one candidate on a set of (training) pairs.

    Args:
        cfg: Settings.
        pairs: Pairs (fittable, training).
        target: Target id.
        candidate: Candidate id.
        tag: Which variant of the diagnostic (seeds the bootstrap).

    Returns:
        The row: n, rho, interval, status.
    """
    use = [p for p in pairs if math.isfinite(p.features.get(candidate, math.nan))]
    x = [p.features[candidate] for p in use]
    y = [p.value for p in use]
    rho = stats.spearman(x, y)
    low, high = stats.block_bootstrap_spearman(
        x, y, [p.scene_key for p in use], cfg.stage1.resamples,
        _seed(cfg, tag, target, candidate), cfg.stage1.confidence,
    )  # fmt: skip
    s1 = cfg.stage1
    if len(use) < s1.min_train:
        status = "insufficient_data"
    elif math.isfinite(rho) and rho >= s1.rho_min and low > s1.lower_bound_min:
        status = "passed"
    else:
        status = "failed"
    return {"target": target, "candidate": candidate, "variant": tag, "n": len(use),
            "stations": len({p.station for p in use}), "rho": rho, "ci_low": low,
            "ci_high": high, "rho_needed": stats.rho_needed(len(use), s1.lower_bound_min),
            "status": status}  # fmt: skip


def stage1(
    cfg: CalibrationConfig, inputs: Inputs, results: Results
) -> dict[str, tuple[list[Pair], list[Pair], list[str], str]]:
    """Pairs, splits and the band diagnostic for every target; sensitivities report-only.

    Args:
        cfg: Settings.
        inputs: Inputs.
        results: Where tables go.

    Returns:
        Target -> (training, hold-out, top candidates, Stage 1 status).
    """
    rows: list[dict[str, Any]] = []
    pair_rows: list[dict[str, Any]] = []
    counts: list[dict[str, Any]] = []
    sens: list[dict[str, Any]] = []
    out: dict[str, tuple[list[Pair], list[Pair], list[str], str]] = {}
    for t in cfg.targets:
        primary = target_pairs(cfg, inputs, t.id, "l2a-300m")
        usable = fittable(primary)
        cut, train, holdout = split(usable, cfg.matchups.holdout_share)
        for p in primary:
            pair_rows.append({
                "target": t.id, "station": p.station, "sample_day": p.sample_day,
                "scene_key": p.scene_key, "scene_day": p.scene_day, "gap_days": p.gap_days,
                "value": p.value, "unit": t.unit, "censored": p.censored, "state": p.state,
                "family": p.family,
                "split": "censored" if p.censored or not p.value > 0 else
                ("training" if cut and p.sample_day <= cut else "holdout"),
                **{c: p.features.get(c, math.nan) for c in CANDIDATES},
                "glint_share": p.stats.get("glint_share"), "valid_px": p.stats.get("valid_px"),
            })  # fmt: skip
        stations = sorted({p.station for p in primary})
        counts.append({"target": t.id, "pairs_primary": len(primary),
                       "fittable": len(usable), "training": len(train),
                       "holdout": len(holdout), "cut_date": cut or "",
                       "stations": " ".join(stations)})  # fmt: skip
        diag = [diagnose(cfg, train, t.id, c, "primary") for c in CANDIDATES]
        rows += diag
        passed = sorted((d for d in diag if d["status"] == "passed"),
                        key=lambda d: -float(str(d["rho"])))  # fmt: skip
        top = [str(d["candidate"]) for d in passed[: cfg.stage1.top_per_target]]
        statuses = {str(d["status"]) for d in diag}
        status = (
            "passed"
            if top
            else "insufficient_data"
            if statuses == {"insufficient_data"}
            else "failed"
        )
        out[t.id] = (train, holdout, top, status)
        # Report-only sensitivities.
        variants: list[tuple[str, list[Pair]]] = [
            ("window 1 km", split(fittable(target_pairs(cfg, inputs, t.id, "l2a-1000m")),
                                  cfg.matchups.holdout_share)[1]),
            ("C1 (2b)", split(fittable(target_pairs(cfg, inputs, t.id, "c1-300m")),
                              cfg.matchups.holdout_share)[1]),
            ("ACOLITE (2c)", split(fittable(target_pairs(cfg, inputs, t.id, "acolite-300m")),
                                   cfg.matchups.holdout_share)[1]),
        ]  # fmt: skip
        if t.kind == "sample":
            wide = target_pairs(cfg, inputs, t.id, "l2a-300m", cfg.matchups.sensitivity_days)
            variants.append(("+-3 days", split(fittable(wide), cfg.matchups.holdout_share)[1]))
        else:
            valid = [p for p in train if _validated(p.state)]
            variants.append(("validated states only", valid))
        for tag, pairs in variants:
            for c in CANDIDATES:
                sens.append(diagnose(cfg, pairs, t.id, c, tag))
        for station in stations:
            here = [p for p in train if p.station == station]
            for c in CANDIDATES:
                use = [p for p in here if math.isfinite(p.features.get(c, math.nan))]
                sens.append({"target": t.id, "candidate": c, "variant": f"station {station}",
                             "n": len(use), "stations": 1,
                             "rho": stats.spearman([p.features[c] for p in use],
                                                   [p.value for p in use])})  # fmt: skip
        if t.id == "cm_d":
            for c in CANDIDATES:
                trip = []
                for p in train:
                    q = inputs.series.get((p.station, "Q_MEDIA_D"), {}).get(p.sample_day, math.nan)
                    if math.isfinite(p.features.get(c, math.nan)) and math.isfinite(q) and q > 0:
                        trip.append((p.features[c], p.value, math.log(q)))
                sens.append({"target": t.id, "candidate": c,
                             "variant": "partial given log discharge", "n": len(trip),
                             "rho": stats.partial_spearman([a for a, _, _ in trip],
                                                           [b for _, b, _ in trip],
                                                           [z for _, _, z in trip])})  # fmt: skip
    results.tables["pairs"] = pair_rows
    results.tables["pair_counts"] = counts
    results.tables["stage1"] = rows
    results.tables["stage1_sensitivity"] = sens
    return out


def _validated(state: str) -> bool:
    text = state.upper()
    return any(word in text for word in ("VALID", "DEFINIT", "APROB"))


def stage2a(cfg: CalibrationConfig, inputs: Inputs, results: Results) -> None:
    """Processing-baseline homogeneity of each candidate (report-only).

    Args:
        cfg: Settings.
        inputs: Inputs.
        results: Where tables go.
    """
    scenes = [s for s in inputs.scenes["l2a-300m"] if s.usable(cfg.window)]
    rows: list[dict[str, Any]] = []
    for c in CANDIDATES:
        by_station_month: dict[tuple[str, int], list[float]] = {}
        for s in scenes:
            v = s.features.get(c, math.nan)
            if math.isfinite(v):
                by_station_month.setdefault((s.station, s.day.month), []).append(v)
        medians = {k: float(np.median(v)) for k, v in by_station_month.items()}
        anomalies: dict[str, list[float]] = {}
        for s in scenes:
            v = s.features.get(c, math.nan)
            if math.isfinite(v):
                anomalies.setdefault(s.family, []).append(v - medians[(s.station, s.day.month)])
        groups = {f: v for f, v in anomalies.items() if len(v) >= cfg.stage2.family_min_scenes}
        everything = np.array([a for v in anomalies.values() for a in v])
        sigma = (1.4826 * float(np.median(np.abs(everything - np.median(everything))))
                 if everything.size else math.nan)  # fmt: skip
        h, p = stats.kruskal_wallis(list(groups.values()))
        shifts = {f: float(np.median(v)) / sigma if sigma > 0 else math.nan
                  for f, v in groups.items()}  # fmt: skip
        flagged = (math.isfinite(p) and p < cfg.stage2.homogeneity_p
                   and any(abs(s) > cfg.stage2.shift_sigma for s in shifts.values()))  # fmt: skip
        rows.append({"candidate": c, "families": " ".join(f"{f}:{len(v)}"
                                                          for f, v in sorted(groups.items())),
                     "h": h, "p": p, "shifts_sigma": " ".join(f"{f}:{s:+.2f}"
                                                              for f, s in sorted(shifts.items())),
                     "shift_reported": flagged})  # fmt: skip
    results.tables["stage2a_homogeneity"] = rows
    # 2b: per-scene L2A minus C1 for the same station and acquisition.
    c1 = {(s.station, s.key): s for s in inputs.scenes["c1-300m"]}
    diffs: dict[tuple[str, str], list[float]] = {}
    for s in inputs.scenes["l2a-300m"]:
        other = c1.get((s.station, s.key))
        if other is None or not (s.usable(cfg.window) and other.usable(cfg.window)):
            continue
        for c in CANDIDATES:
            a, b = s.features.get(c, math.nan), other.features.get(c, math.nan)
            if math.isfinite(a) and math.isfinite(b):
                diffs.setdefault((s.family, c), []).append(a - b)
    results.tables["stage2b_l2a_minus_c1"] = [
        {"family": f, "candidate": c, "n": len(v), "median_difference": float(np.median(v))}
        for (f, c), v in sorted(diffs.items())
    ]


def stage3(
    cfg: CalibrationConfig,
    splits: Mapping[str, tuple[list[Pair], list[Pair], list[str], str]],
    results: Results,
) -> dict[str, models.Calibration]:
    """Calibration where Stage 1 passed; leave-one-station-out transfer report.

    Args:
        cfg: Settings.
        splits: Stage 1 output.
        results: Where tables go.

    Returns:
        Target -> outcome.
    """
    out: dict[str, models.Calibration] = {}
    rows: list[dict[str, Any]] = []
    transfer: list[dict[str, Any]] = []
    for t in cfg.targets:
        train, holdout, top, status = splits[t.id]
        if status != "passed":
            out[t.id] = models.Calibration(t.id, status, [f"Stage 1 {status}"])
            rows.append({"target": t.id, "status": status, "reasons": f"Stage 1 {status}"})
            continue
        tr = [p for p in train if all(math.isfinite(p.features.get(f, math.nan)) for f in top)]
        ho = [p for p in holdout if all(math.isfinite(p.features.get(f, math.nan)) for f in top)]
        result = models.calibrate(
            t.id, [p.features for p in tr], [p.value for p in tr], [p.features for p in ho],
            [p.value for p in ho], top, cfg.stage3,
        )  # fmt: skip
        out[t.id] = result
        row: dict[str, Any] = {"target": t.id, "status": result.status,
                                  "reasons": "; ".join(result.reasons),
                                  "model": result.chosen.model_id if result.chosen else "",
                                  "training": len(tr), "holdout": len(ho)}  # fmt: skip
        row.update({k: v for k, v in result.metrics.items()})
        rows.append(row)
        if result.chosen is not None:
            card = result.chosen.card(t.unit, result.metrics)
            card["status"] = result.status
            card["trainingStations"] = sorted({p.station for p in tr})
            results.cards.append(card)
            for station in sorted({p.station for p in tr}):
                rest = [p for p in tr if p.station != station]
                here = [p for p in tr if p.station == station]
                if len(rest) < 3 or not here:
                    continue
                fit = models.fit_model("loso", t.id, [p.features for p in rest],
                                       [p.value for p in rest], result.chosen.features,
                                       result.chosen.ridge_lambda)  # fmt: skip
                pred = [fit.predict(p.features) for p in here]
                transfer.append({"target": t.id, "held_out_station": station, "n": len(here),
                                 "mdsa": stats.mdsa(pred, [p.value for p in here]),
                                 "sspb": stats.sspb(pred, [p.value for p in here])})  # fmt: skip
    results.tables["stage3_calibration"] = rows
    results.tables["stage3_leave_one_station_out"] = transfer
    return out


def stage4(
    cfg: CalibrationConfig,
    inputs: Inputs,
    splits: Mapping[str, tuple[list[Pair], list[Pair], list[str], str]],
    results: Results,
) -> None:
    """Published semi-analytical models on every fittable pair (report-only, no retuning).

    Args:
        cfg: Settings.
        inputs: Inputs.
        splits: Stage 1 output.
        results: Where tables go.
    """
    n = inputs.nechad
    rows: list[dict[str, Any]] = []
    if not n:
        results.tables["stage4_transfer"] = [{"note": "coefficients not fetched: skipped"}]
        return
    low, high = inputs.dogliotti_limits

    def nechad_model(param: str) -> Any:
        return lambda f: models.nechad(f.get("B04", math.nan), *n[(param, "B4")])

    def switch(f: Mapping[str, float]) -> float:
        return models.dogliotti_switch(f.get("B04", math.nan), f.get("B8A", math.nan),
                                       n[("TUR", "B4")], n[("TUR", "B8A")], low, high)  # fmt: skip

    plan = {
        "turbidity": [("nechad2009_turbidity", nechad_model("TUR")),
                      ("dogliotti2015_turbidity", switch)],
        "tss": [("nechad2010_tss", nechad_model("SPM"))],
        "cm_d": [("nechad2010_tss", nechad_model("SPM"))],
    }  # fmt: skip
    for t in cfg.targets:
        train, holdout, _, _ = splits[t.id]
        pairs = [*train, *holdout]
        for name, fn in plan.get(t.id, []):
            pred = [float(fn(p.features)) for p in pairs]
            obsv = [p.value for p in pairs]
            ok = [k for k, v in enumerate(pred) if math.isfinite(v)]
            rows.append(
                {
                    "target": t.id,
                    "model": name,
                    "n": len(ok),
                    "mdsa": stats.mdsa([pred[k] for k in ok], [obsv[k] for k in ok]),
                    "sspb": stats.sspb([pred[k] for k in ok], [obsv[k] for k in ok]),
                    "mape": stats.mape([pred[k] for k in ok], [obsv[k] for k in ok]),
                }
            )
    results.tables["stage4_transfer"] = rows


def curvature(cfg: CalibrationConfig, inputs: Inputs, results: Results) -> None:
    """In-situ-free check at the reach's stations: does B8A keep rising where B04 flattens?

    Args:
        cfg: Settings.
        inputs: Inputs.
        results: Where tables go.
    """
    reach = {r["station_id"] for r in inputs.stations if "reach" in r["roles"].split()}
    scenes = [s for s in inputs.scenes["l2a-300m"]
              if s.station in reach and s.usable(cfg.window)]  # fmt: skip
    pts = sorted((s.bands["B04"], s.bands["B8A"]) for s in scenes
                 if math.isfinite(s.bands["B04"]) and math.isfinite(s.bands["B8A"]))  # fmt: skip
    rows: list[dict[str, Any]] = []
    if len(pts) >= 8:
        half = len(pts) // 2
        for name, part in (("lower half of B04", pts[:half]), ("upper half of B04", pts[half:])):
            x = np.array([p[0] for p in part])
            y = np.array([p[1] for p in part])
            slope = float(np.polyfit(x, y, 1)[0]) if np.ptp(x) > 0 else math.nan
            rows.append({"part": name, "scenes": len(part), "b04_min": float(x.min()),
                         "b04_max": float(x.max()), "slope_b8a_on_b04": slope,
                         "spearman": stats.spearman(x.tolist(), y.tolist())})  # fmt: skip
    results.tables["curvature"] = rows
    results.plots["curvature"] = pts


def stage5(
    cfg: CalibrationConfig, inputs: Inputs, paths: CalibrationPaths, results: Results
) -> tuple[dict[str, climate.SignalModel], list[dict[str, str]], dict[tuple[int, int], str]]:
    """5a, 5b and 5c.

    Args:
        cfg: Settings.
        inputs: Inputs.
        paths: Paths.
        results: Where tables go.

    Returns:
        The 5a models, the reach's scene rows and the month phases.
    """
    c = cfg.climate
    scene_rows = [r for r in _rows(_read(paths.at(c.reach_scenes)))
                  if r["site_id"] == c.reach and r["excluded"] in ("", "false")]  # fmt: skip
    reach = [r for r in inputs.stations if "reach" in r["roles"].split()]
    discharge = next((inputs.series[(r["station_id"], "Q_MEDIA_D")] for r in reach
                      if (r["station_id"], "Q_MEDIA_D") in inputs.series), None)  # fmt: skip
    signal_models: dict[str, climate.SignalModel] = {}
    rows: list[dict[str, Any]] = []
    for signal in c.signals:
        obsv = [(date.fromisoformat(r["date"]), number(r[f"{signal}_ndti"])) for r in scene_rows]
        model = climate.fit_signal(signal, obsv, inputs.rain, c, inputs.chirps or None, discharge)
        signal_models[signal] = model
        rows.append(
            {
                "signal": signal,
                "n": model.n,
                "skill": model.skill,
                "status": model.status,
                "skill_min": c.skill_min,
                "skill_chirps": model.skill_chirps,
                "skill_with_discharge": model.skill_with_discharge,
                "ar1": model.ar1,
            }
        )
    results.tables["stage5a_climate"] = rows
    # 5b.
    width = c.width
    rows5b: list[dict[str, Any]] = []
    lags: list[dict[str, Any]] = []
    for r in inputs.stations:
        if "flow" not in r["roles"].split():
            continue
        sid = r["station_id"]
        label = "Q_MEDIA_D" if (sid, "Q_MEDIA_D") in inputs.series else "NV_MEDIA_D"
        series = inputs.series.get((sid, label), {})
        ext = [(date.fromisoformat(e["local_date"]), number(e["extent_km2"]))
               for e in inputs.extents if e["station"] == sid
               and number(e["valid_fraction"]) >= width.valid_fraction_min
               and number(e["b11_ok"]) >= 1]  # fmt: skip
        res = climate.extent_flow(ext, series, width, _seed(cfg, "5b", sid))
        rho, low = float(res["rho"]), float(res["low"])
        status = ("passed" if math.isfinite(rho) and rho >= width.rho_min
                  and low > width.lower_bound_min else "failed")  # fmt: skip
        rows5b.append({"station": sid, "series": label, **res, "status": status})
        for lag in width.report_lags_days:
            lagged = climate.extent_flow(ext, series, width, _seed(cfg, "5b", sid, str(lag)), lag)
            lags.append({"station": sid, "series": label, "lag_days": lag, **lagged})
        results.plots.setdefault("5b", {})[sid] = [
            (e, series.get(d, math.nan)) for d, e in ext if math.isfinite(series.get(d, math.nan))
        ]
    results.tables["stage5b_extent_flow"] = rows5b
    results.tables["stage5b_lags"] = lags
    # 5c.
    phases = climate.enso_months(inputs.oni, c.enso) if inputs.oni else {}
    tests: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    entities: list[tuple[str, str, list[tuple[date, float]]]] = []
    for r in inputs.stations:
        sid = r["station_id"]
        if "flow" in r["roles"].split():
            ext = [(date.fromisoformat(e["local_date"]), number(e["extent_km2"]))
                   for e in inputs.extents if e["station"] == sid
                   and number(e["valid_fraction"]) >= width.valid_fraction_min]  # fmt: skip
            entities.append((f"extent {sid}", "greater", ext))
        for label in cfg.stations.monthly_labels:
            monthly = inputs.series.get((sid, label))
            if monthly:
                entities.append((f"{label} {sid}", "two-sided", sorted(monthly.items())))
    for signal in ("downstream", "delta"):
        entities.append((f"NDTI {signal} (reach)", "two-sided",
                         [(date.fromisoformat(r["date"]), number(r[f"{signal}_ndti"]))
                          for r in scene_rows]))  # fmt: skip
    for name, alternative, observations in entities:
        if not phases:
            tests.append({"entity": name, "note": "ONI not fetched: skipped"})
            continue
        res5c = climate.enso_test(observations, phases, c, _seed(cfg, "5c", name), alternative)
        eps = res5c.pop("episodes", [])
        tests.append({"entity": name, **res5c})
        for e in eps if isinstance(eps, list) else []:
            episodes.append({"entity": name, **e})
    results.tables["stage5c_enso"] = tests
    results.tables["stage5c_episodes"] = episodes
    return signal_models, scene_rows, phases


def observation_records(
    cfg: CalibrationConfig,
    inputs: Inputs,
    paths: CalibrationPaths,
    calibrations: Mapping[str, models.Calibration],
    signal_models: Mapping[str, climate.SignalModel],
    scene_rows: Sequence[Mapping[str, str]],
    phases: Mapping[tuple[int, int], str],
    results: Results,
) -> None:
    """The reach's observation records, with calibration and climate context filled in.

    Args:
        cfg: Settings.
        inputs: Inputs.
        paths: Paths.
        calibrations: Stage 3 outcome per target.
        signal_models: 5a models.
        scene_rows: The reach's frozen scenes.
        phases: Month -> ENSO phase.
        results: Where the records go.
    """
    case = json.loads(_read(paths.root / "docs/magdalena-validation/magdalena.sample.json"))
    if not inputs.items:
        results.records = []
        return
    ids = {i for s in case["ui"]["scenes"] if not s["excluded"] for i in s["stacItemIds"]}
    if not ids <= set(inputs.items):
        log.warning("reach items missing: %s", sorted(ids - set(inputs.items))[:3])
        return
    base = obs.records_from_case(case, cfg.climate.reach, cfg.imagery.primary, inputs.items,
                                 3.0)  # fmt: skip
    reach = sorted(r["station_id"] for r in inputs.stations if "reach" in r["roles"].split())
    windows = {(s.station, s.day): s for s in inputs.scenes["l2a-300m"]}
    by_day = {r["date"]: r for r in scene_rows}
    passed = [t.id for t in cfg.targets if calibrations.get(t.id) and
              calibrations[t.id].status == "passed"]  # fmt: skip
    statuses = {c.status for c in calibrations.values()}
    overall = ("passed" if passed else "failed" if "failed" in statuses else
               "insufficient_data" if "insufficient_data" in statuses else "none")  # fmt: skip
    discharge = next((inputs.series[(s, "Q_MEDIA_D")] for s in reach
                      if (s, "Q_MEDIA_D") in inputs.series), {})  # fmt: skip
    q_values = sorted(v for v in discharge.values() if math.isfinite(v))
    records = []
    for record in base:
        day = date.fromisoformat(record.date)
        if not passed:
            calibration = obs.Calibration.model_validate({"status": overall})
        else:
            target = passed[0]
            result = calibrations[target]
            fit = result.chosen
            assert fit is not None
            card = next(c for c in results.cards if c["modelId"] == fit.model_id)
            scene = next((windows[(s, day)] for s in reach if (s, day) in windows), None)
            reason = None
            if not set(reach) & set(card["trainingStations"]):
                reason = "calibration not trained at the reach's stations"
            elif scene is None:
                reason = "no station window on this scene"
            else:
                reason = models.abstain_reason(fit, scene.features, scene.stats, cfg.window)
            value = None if reason or scene is None else fit.predict(scene.features)
            band = (models.uncertainty_band(value, result.metrics["loo_mdsa"])
                    if value is not None else None)  # fmt: skip
            calibration = obs.Calibration(
                status="passed", model_id=fit.model_id, version=card["version"],
                parameters_hash=card["parametersHash"], target=target,
                unit=cfg.target(target).unit, value=round(value, 3) if value else None,
                uncertainty=obs.Uncertainty(low=round(band[0], 3), high=round(band[1], 3),
                                            kind="loo_mdsa_band") if band else None,
                valid_range=fit.target_range, abstain_reason=reason,
            )  # fmt: skip
        row = by_day.get(record.date)
        context: dict[str, Any] = {"status": NOT_RUN, "label": "not_evaluated",
                                   "rule": obs.NOT_RUN_RULE}  # fmt: skip
        if row is not None and signal_models:
            flagged = [(s, number(row.get(f"D0_z_{s}", "nan"))) for s in cfg.climate.signals]
            flagged = [(s, z) for s, z in flagged if math.isfinite(z) and abs(z) >= 3.0]
            values: dict[str, float] = {s: number(row[f"{s}_ndti"]) for s in cfg.climate.signals}
            context = climate.label(flagged, signal_models, day, values, cfg.climate.label_z)
        q = discharge.get(day, math.nan)
        if math.isfinite(q) and q_values:
            context["discharge_percentile"] = round(
                sum(1 for v in q_values if v <= q) / len(q_values), 3
            )
        phase = phases.get((day.year, day.month))
        if phase:
            context["enso_phase"] = phase
        sealed = obs.seal(record.model_copy(update={
            "calibration": calibration,
            "climate_context": obs.ClimateContext.model_validate(context),
        }))  # fmt: skip
        records.append(sealed.model_dump(mode="json", by_alias=True))
    results.records = records


def analyse(cfg: CalibrationConfig, paths: CalibrationPaths) -> Results:
    """The whole offline analysis.

    Args:
        cfg: Settings.
        paths: Paths.

    Returns:
        Every table, card and record.
    """
    inputs = load_inputs(cfg, paths)
    results = Results()
    splits = stage1(cfg, inputs, results)
    stage2a(cfg, inputs, results)
    calibrations = stage3(cfg, splits, results)
    stage4(cfg, inputs, splits, results)
    curvature(cfg, inputs, results)
    signal_models, scene_rows, phases = stage5(cfg, inputs, paths, results)
    baselined = (any(m.status == "passed" for m in signal_models.values())
                 or any(r.get("status") == "passed"
                        for r in results.tables.get("stage5b_extent_flow", [])))  # fmt: skip
    validated = any(c.status == "passed" for c in calibrations.values())
    level = "validated in situ" if validated else "baselined" if baselined else "observable"
    results.summary = {
        "maturity": level,
        "stage1": {t: s[3] for t, s in splits.items()},
        "stage3": {t: c.status for t, c in calibrations.items()},
        "stage5a": {s: m.status for s, m in signal_models.items()},
        "stage5b": {
            str(r["station"]): str(r["status"])
            for r in results.tables.get("stage5b_extent_flow", [])
        },
        "stations": len(inputs.stations),
        "samples": len(inputs.samples),
    }
    results.tables["maturity"] = [{"level": level, "baselined": baselined,
                                   "validated_in_situ": validated}]  # fmt: skip
    observation_records(cfg, inputs, paths, calibrations, signal_models, scene_rows, phases,
                        results)  # fmt: skip
    return results
