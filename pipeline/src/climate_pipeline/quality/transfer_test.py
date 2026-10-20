"""``climate-pipeline quality transfer``: turbidity on rivers the model never saw.

The test is fixed by ``docs/water-quality/preregistration-transfer.md`` (anchored before it ran).
It runs in three stages, so that the lock boxes are read once, at the end:

1. **export:** for each fold, the training-year pairs of every river group it does not hold out,
   in the lab's table format (as ``quality export-lab`` writes them), under
   ``pipeline/out/lab-transfer/<fold>/``. No lock-box pair is read.
2. **train:** the lab environment fits A4 on each table (``pipeline/lab/train_gbm.py --oof``) and
   writes ``docs/water-quality/inputs/lab/transfer/<fold>/gbm-turbidity-core.json``, with the
   chosen configuration's out-of-group estimates for the interval.
3. **evaluate:** each fold's model on its held-out group's lock box, against the two baselines,
   with the v5 levels; the pooled result on the similar rivers and the ungauged reach's display
   rule. Results go to ``docs/water-quality/results/transfer/`` with their own MANIFEST.

The folds are the nine river groups held out one at a time, two report-only folds that hold out
the hydrologically joined pairs, and ``all`` (nothing held out): the ungauged reach's model.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from climate_pipeline.calibration import stats
from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.calibration.report import read_manifest, write_table
from climate_pipeline.quality import (
    agreement,
    cards,
    features,
    gauged,
    route_a,
    site,
    transfer,
    trees,
)
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.report import _json, _rounded
from climate_pipeline.screening.report import markdown_table

PREREGISTRATION = Path("docs/water-quality/preregistration-transfer.md")
TABLES = Path("pipeline/out/lab-transfer")
MODELS = Path("docs/water-quality/inputs/lab/transfer")
RESULTS = Path("docs/water-quality/results/transfer")
MODEL_FILE = "gbm-turbidity-core.json"
TABLE_FILE = "turbidity-core.csv"
GROUPS = ("ATCHAFALAYA", "COLUMBIA", "CONNECTICUT", "MISSISSIPPI", "MISSOURI", "OHIO", "PLATTE",
          "SAN JOAQUIN", "WILLAMETTE")  # fmt: skip
JOINED = (("MISSISSIPPI", "ATCHAFALAYA"), ("COLUMBIA", "WILLAMETTE"))  # report-only sensitivity
ALL = "all"  # the fold that holds nothing out: the ungauged reach's model
MIN_SCORED = 20  # lock-box pairs for a site to be scored
SIMILAR_MIN_FNU = 20.0  # training-year median of a "similar" (sediment-carrying) river
CLASS_EDGES = (30.0, 100.0)  # FNU: under 30, 30 to 100, 100 and over
COVERAGE = 0.9
TOLERANCE = 1e-6  # the numpy evaluator against LightGBM's own log estimates (lab.py)


@dataclass(frozen=True)
class Fold:
    """One fold: its name (a folder) and the groups it holds out."""

    name: str
    held_out: tuple[str, ...]
    report_only: bool = False


def folds() -> list[Fold]:
    """Every fold, in a stable order.

    Returns:
        The nine single groups, the two joined pairs (report-only) and ``all``.
    """
    out = [Fold(g.lower().replace(" ", "-"), (g,)) for g in GROUPS]
    out += [Fold("-".join(g.lower().replace(" ", "-") for g in pair), pair, True)
            for pair in JOINED]  # fmt: skip
    return [*out, Fold(ALL, ())]


@dataclass(frozen=True)
class Data:
    """The v5 turbidity pairs (core window, feature set F) and each site's river group."""

    pairs: list[Pair]
    group_of: dict[str, str]
    names: list[str]

    def group(self, p: Pair) -> str:
        """A pair's river group."""
        return self.group_of[p.station]

    def training(self, held_out: Sequence[str] = ()) -> list[Pair]:
        """The training-year pairs of every group not held out."""
        return [p for p in site.split(self.pairs)[0] if self.group(p) not in held_out]


def load(cfg: QualityConfig, root: Path) -> Data:
    """The v5 pairs exactly as v5 builds them (``gauged.pairs_by_source``'s turbidity).

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The pairs with usable features, and the groups.

    Raises:
        ValueError: When the v5 snapshots are missing.
    """
    main = transfer.load_usgs(cfg, root, folder=gauged.FOLDER, sites_file=gauged.SITES_FILE)
    if main is None:
        raise ValueError("the v5 snapshots are missing (docs/water-quality/inputs/usgs-v5)")
    names = features.names(cfg.features)
    pairs = transfer.usable_rows(main.pairs.get((site.TARGET, site.WINDOW), []), names)
    return Data(pairs, dict(main.river_of), names)


# --- 1. export (training years only) -------------------------------------------------------------


def export(cfg: QualityConfig, root: Path) -> list[Path]:
    """Each fold's training table and spec, in the lab's format (``lab.export``).

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The tables written.
    """
    data = load(cfg, root)
    gbm = cfg.selection.gbm
    written = []
    for fold in folds():
        rows = data.training(fold.held_out)
        folder = root / TABLES / fold.name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / TABLE_FILE
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["group", "value", *data.names])
            for p in rows:
                writer.writerow([data.group(p), repr(p.value),
                                 *(repr(p.features[n]) for n in data.names)])  # fmt: skip
        spec = {"target": site.TARGET, "window": site.WINDOW, "features": data.names,
                "seed": cfg.seed,
                "grid": {"num_leaves": list(gbm.num_leaves),
                         "min_data_in_leaf": list(gbm.min_data_in_leaf),
                         "n_estimators": list(gbm.n_estimators),
                         "learning_rate": gbm.learning_rate}}  # fmt: skip
        path.with_suffix(".json").write_text(json.dumps(spec, indent=1) + "\n", encoding="utf-8")
        written.append(path)
    return written


# --- 2. train (the lab environment) --------------------------------------------------------------


def train(root: Path, uv: str = "uv") -> list[Path]:
    """Fit A4 on every exported table in the lab environment.

    Args:
        root: Repository root.
        uv: The uv executable.

    Returns:
        The models written.
    """
    written = []
    for fold in folds():
        tables, out = root / TABLES / fold.name, root / MODELS / fold.name
        subprocess.run([uv, "run", "python", "train_gbm.py", str(tables), "--out", str(out),
                        "--oof"], cwd=root / "pipeline" / "lab", check=True)  # fmt: skip
        written.append(out / MODEL_FILE)
    return written


# --- 3. evaluate (the lock boxes, once) ----------------------------------------------------------


@dataclass(frozen=True)
class Model:
    """A fold's A4 and its interval."""

    forest: trees.Forest
    q90: float  # the 90th percentile of the absolute log residuals of its out-of-group estimates
    chosen: Mapping[str, Any]
    n_train: int

    def quantiles(self) -> route_a.Quantiles:
        """The interval as v5's quantiles: one pooled quantile (no terciles).

        Only the 90 % interval is preregistered; the 80 % entry is unbounded so v5's evaluation
        runs, and its coverage is never reported.
        """
        return route_a.Quantiles((math.inf, math.inf),
                                 {COVERAGE: (self.q90,) * 3, 0.8: (math.inf,) * 3},
                                 frozenset({COVERAGE, 0.8}))  # fmt: skip


def model(root: Path, fold: Fold, values: Sequence[float]) -> Model:
    """A fold's model, checked against LightGBM's own estimates (as ``lab.forests``).

    Args:
        root: Repository root.
        fold: The fold.
        values: The fold's training values, in the exported table's order (its out-of-group
            estimates are one per row).

    Returns:
        The model.

    Raises:
        ValueError: When the evaluator disagrees with LightGBM.
    """
    path = root / MODELS / fold.name / MODEL_FILE
    data = json.loads(path.read_text(encoding="utf-8"))
    forest = trees.from_dump(data["model"])
    gap = trees.check(forest, data["check"]["rows"], data["check"]["raw"])
    if gap > TOLERANCE:
        raise ValueError(f"{fold.name}: the evaluator differs from LightGBM by {gap:g}")
    oof = data["oof"]
    residuals = [abs(math.log(v) - e) for v, e in zip(values, oof, strict=True)
                 if e is not None and v > 0]  # fmt: skip
    return Model(forest, float(np.percentile(residuals, 90)), data["chosen"], int(data["n_train"]))


def _class(value: float) -> int:
    return 0 if value < CLASS_EDGES[0] else 1 if value < CLASS_EDGES[1] else 2


def _ridge(cfg: QualityConfig, data: Data, train_pairs: Sequence[Pair]) -> transfer.Linear:
    lam = transfer.choose_lambda(list(train_pairs), data.group, data.names,
                                 cfg.selection.ridge_lambdas)  # fmt: skip
    return transfer.fit_linear(list(train_pairs), data.names, lam)


def evaluate(cfg: QualityConfig, root: Path) -> dict[str, Any]:
    """Every fold on its held-out lock boxes, the pooled similar rivers and the display rule.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        ``scores`` (one row per site, fold and candidate), ``levels`` (A4's v5 levels per site),
        ``pooled`` (the similar rivers) and ``folds`` (each fold's training and interval).
    """
    data = load(cfg, root)
    target = cfg.target(site.TARGET)
    seed = cfg.seed
    by_site: dict[str, list[Pair]] = {}
    for p in data.pairs:
        by_site.setdefault(p.station, []).append(p)
    medians = {s: float(np.median([p.value for p in site.split(ps)[0]]))
               for s, ps in by_site.items()}  # fmt: skip
    similar = sorted(s for s, m in medians.items() if m >= SIMILAR_MIN_FNU)
    scores: list[dict[str, Any]] = []
    levels: list[dict[str, Any]] = []
    fold_rows: list[dict[str, Any]] = []
    pooled: list[tuple[Pair, float, float]] = []  # (pair, estimate, q90) on similar sites
    for fold in folds():
        train_pairs = data.training(fold.held_out)
        m = model(root, fold, [p.value for p in train_pairs])
        fold_rows.append({"fold": fold.name, "held_out": " + ".join(fold.held_out) or "none",
                          "report_only": fold.report_only, "training_pairs": len(train_pairs),
                          "training_groups": len({data.group(p) for p in train_pairs}),
                          "num_leaves": m.chosen["num_leaves"],
                          "min_data_in_leaf": m.chosen["min_data_in_leaf"],
                          "n_estimators": m.chosen["n_estimators"], "q90": m.q90,
                          "interval_factor90": math.exp(m.q90)})  # fmt: skip
        if not fold.held_out:
            continue  # the ungauged reach's model: nothing to score
        pooled_median = float(np.median([p.value for p in train_pairs]))
        ridge = _ridge(cfg, data, train_pairs)
        group_train = [p for p in site.split(data.pairs)[0] if data.group(p) in fold.held_out]
        for station in sorted(s for s in by_site if data.group_of[s] in fold.held_out):
            lock = site.split(by_site[station])[1]
            if len(lock) < MIN_SCORED:
                continue
            est = [m.forest.predict(p.features) for p in lock]
            usual = route_a.null(group_train, lock)  # baseline (a): the group's own median
            q = m.quantiles()
            base = {"fold": fold.name, "report_only": fold.report_only, "site": station,
                    "group": data.group_of[station]}  # fmt: skip
            metrics = route_a.evaluate(cfg, lock, est, usual, q, seed)
            metrics["coverage80"] = math.nan  # not preregistered
            metrics["interval_factor90"] = site.interval_factor(q, est)
            observed = [p.value for p in lock]
            no_local = stats.mdsa([pooled_median] * len(lock), observed)  # baseline (b)
            agree = sum(_class(e) == _class(o) for e, o in zip(est, observed, strict=True))
            rows = site.level_rows(cfg, target, lock, est, usual, q, seed, "v5")
            scores.append({**base, "candidate": "A4", **metrics,
                           "no_local_data_mdsa": no_local, "class_agreement": agree,
                           "level": rows[0]["level"]})  # fmt: skip
            ridge_est = [ridge.predict(p.features) for p in lock]
            scores.append({**base, "candidate": "A3 (report-only)",
                           **route_a.evaluate(cfg, lock, ridge_est, usual, None, seed),
                           "no_local_data_mdsa": no_local})  # fmt: skip
            if not fold.report_only:
                levels += [{**base, **r} for r in rows]
                if station in similar:
                    pooled += [(p, e, m.q90) for p, e in zip(lock, est, strict=True)]
    return {"scores": scores, "levels": levels, "folds": fold_rows,
            "pooled": _pooled(cfg, pooled, similar, medians)}  # fmt: skip


def _pooled(cfg: QualityConfig, pooled: Sequence[tuple[Pair, float, float]],
            similar: Sequence[str], medians: Mapping[str, float]) -> dict[str, Any]:  # fmt: skip
    pairs = [p for p, _, _ in pooled]
    est = [e for _, e, _ in pooled]
    observed = [p.value for p in pairs]
    low, high = stats.block_bootstrap_spearman(est, observed, [p.scene_key for p in pairs],
                                               cfg.selection.bootstrap_resamples, cfg.seed,
                                               cfg.selection.confidence)  # fmt: skip
    inside = sum(abs(math.log(o / e)) <= q for (p, e, q), o in zip(pooled, observed, strict=True))
    agree = sum(_class(e) == _class(o) for e, o in zip(est, observed, strict=True))
    shows_class = bool(low > cfg.levels.indicative.lower_bound_min)
    return {
        "similar_rule": f"training-year median at least {SIMILAR_MIN_FNU:g} FNU",
        "similar_sites": [{"site": s, "training_median_fnu": round(medians[s], 1)}
                          for s in similar],
        "n": len(pairs), "mdsa": stats.mdsa(est, observed), "sspb": stats.sspb(est, observed),
        "rho": stats.spearman(est, observed), "rho_low": low, "rho_high": high,
        "coverage90_inside": inside,
        "class_edges_fnu": list(CLASS_EDGES), "class_agreement": agree,
        "indicative_rho_low_min": cfg.levels.indicative.lower_bound_min,
        "ungauged_shows_class": shows_class,
        "ungauged_display": "class (under 30, 30 to 100, 100 and over FNU)" if shows_class
        else "relative NDTI only",
    }  # fmt: skip


COLUMNS = ["fold", "site", "group", "candidate", "n", "mdsa", "sspb", "rho", "rho_low",
           "null_mdsa", "no_local_data_mdsa", "coverage90", "interval_factor90",
           "class_agreement", "level", "report_only"]  # fmt: skip


def render(results: Mapping[str, Any]) -> str:
    """The Markdown summary (every scored site, failures included).

    Args:
        results: :func:`evaluate`'s output.

    Returns:
        The page.
    """
    scores = _rounded(results["scores"])
    main = [r for r in scores if not r["report_only"] and r["candidate"] == "A4"]
    p = results["pooled"]
    parts = [
        "# Turbidity on rivers the model never saw (generated)",
        "",
        "Fixed by `docs/water-quality/preregistration-transfer.md`, anchored before it ran; run "
        "once. `null_mdsa` is baseline (a), the held-out group's own median; "
        "`no_local_data_mdsa` is baseline (b), the other groups' median.",
        "",
        "## A4, each river group held out",
        "",
        markdown_table(main, ["site", "group", "n", "mdsa", "sspb", "rho_low", "null_mdsa",
                              "no_local_data_mdsa", "coverage90", "interval_factor90",
                              "class_agreement", "level"]),
        "",
        "## Similar rivers, pooled (the ungauged reach's expected error)",
        "",
        f"- Rule: {p['similar_rule']}; sites: "
        + ", ".join(f"{s['site']} ({s['training_median_fnu']} FNU)" for s in p["similar_sites"]),
        f"- n = {p['n']}; MdSA {p['mdsa']:.1f} %; SSPB {p['sspb']:.1f} %; Spearman rho "
        f"{p['rho']:.3f} (95 % interval {p['rho_low']:.3f} to {p['rho_high']:.3f})",
        f"- Inside the 90 % interval: {p['coverage90_inside']} of {p['n']}; class agreement: "
        f"{p['class_agreement']} of {p['n']}",
        f"- The ungauged reach shows: **{p['ungauged_display']}** (rho's lower bound "
        f"{'above' if p['ungauged_shows_class'] else 'not above'} "
        f"{p['indicative_rho_low_min']:g}).",
        "",
        "## Report-only: A3 and the joined folds",
        "",
        markdown_table([r for r in scores if r["report_only"] or r["candidate"] != "A4"],
                       ["fold", "site", "candidate", "n", "mdsa", "sspb", "rho_low",
                        "null_mdsa", "no_local_data_mdsa"]),
        "",
        "## The folds",
        "",
        markdown_table(_rounded(results["folds"], 4), list(results["folds"][0])),
        "",
    ]  # fmt: skip
    return "\n".join(parts)


def write(results: Mapping[str, Any], root: Path, out: Path) -> list[Path]:
    """Write the results and their MANIFEST (the folder starts empty).

    Args:
        results: :func:`evaluate`'s output.
        root: Repository root (for the preregistration's hash).
        out: The results folder.

    Returns:
        The files written (MANIFEST last).
    """
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    write_table(_rounded(results["scores"], 4), out / "transfer_scores.csv")
    write_table(_rounded(results["levels"], 4), out / "transfer_levels.csv")
    write_table(_rounded(results["folds"], 6), out / "transfer_folds.csv")
    _json(_rounded([results["pooled"]], 4)[0], out / "transfer_pooled.json")
    (out / "transfer.md").write_text(render(results), encoding="utf-8", newline="\n")
    # Over the LF form, as git stores them, whatever a Windows checkout wrote.
    provenance = {"preregistration_sha256": cards.file_sha256(root / PREREGISTRATION),
                  "models_sha256": {f.name: cards.file_sha256(root / MODELS / f.name / MODEL_FILE)
                                    for f in folds()}}  # fmt: skip
    _json(provenance, out / "provenance.json")
    names = ("transfer_scores.csv", "transfer_levels.csv", "transfer_folds.csv",
             "transfer_pooled.json", "transfer.md", "provenance.json")  # fmt: skip
    written = [out / n for n in names]
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(written)]
    (out / "MANIFEST").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return [*written, out / "MANIFEST"]


def verify(cfg: QualityConfig, root: Path) -> tuple[list[str], list[str]]:
    """Recompute stage 3 from the committed models and compare with the MANIFEST.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The mismatches, and the files that agree only to the last printed digit.
    """
    results = root / RESULTS
    if not (results / "MANIFEST").exists():
        return [f"no MANIFEST at {results}"], []
    expected = read_manifest(results / "MANIFEST")
    problems: list[str] = []
    near: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "transfer"
        write(evaluate(cfg, root), root, target)
        actual = read_manifest(target / "MANIFEST")
        for name in sorted(set(expected) | set(actual)):
            ours, theirs = results / name, target / name
            if name not in expected or name not in actual:
                problems.append(
                    f"{name}: {'not committed' if name in actual else 'not recomputed'}"
                )
            elif hashlib.sha256(ours.read_bytes()).hexdigest() != expected[name]:
                problems.append(f"{name}: the committed file does not match the MANIFEST")
            elif expected[name] != actual[name]:
                found = agreement.disagreements(ours.read_text(encoding="utf-8"),
                                                theirs.read_text(encoding="utf-8"))  # fmt: skip
                (problems if found else near).append(f"{name}: {'; '.join(found)}" if found
                                                     else name)  # fmt: skip
    return problems, near
