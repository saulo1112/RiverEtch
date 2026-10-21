"""The two class tests beside the transfer test, each run once after its anchor.

* ``docs/water-quality/preregistration-class-baseline.md``: always guessing the most common class
  (under 30, 30 to 100, 100 FNU and over), next to the model's 185 of 298;
* ``docs/water-quality/preregistration-four-classes.md``: four classes (edges 30, 50 and 100 FNU)
  against the four-class form of that baseline, by an exact one-sided McNemar test.

Both read exactly the transfer test's 298 pooled pairs (the similar sites' lock-box pairs, each
estimated by the model that never saw its river group), rebuilt from the committed models; the
rebuild must reproduce the transfer test's pooled class agreement before anything is counted.
Both were decided after seeing that result, and say so.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import numpy as np

from climate_pipeline.calibration.report import read_manifest, write_table
from climate_pipeline.quality import cards, site
from climate_pipeline.quality import transfer_test as t
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.report import _json, _rounded

BASELINE_PREREGISTRATION: Final = Path("docs/water-quality/preregistration-class-baseline.md")
FOUR_PREREGISTRATION: Final = Path("docs/water-quality/preregistration-four-classes.md")
BASELINE_RESULTS: Final = Path("docs/water-quality/results/transfer-baseline")
FOUR_RESULTS: Final = Path("docs/water-quality/results/four-classes")
FROZEN: Final = Path("docs/ledgers/frozen-artifacts.jsonl")
THREE: Final = (30.0, 100.0)  # FNU: under 30, 30 to 100, 100 and over
FOUR: Final = (30.0, 50.0, 100.0)  # FNU: under 30, 30 to 50, 50 to 100, 100 and over
ALPHA: Final = 0.05  # the four-class pass rule's one-sided level
LABEL: Final = "decided after seeing the result"


def klass(value: float, edges: Sequence[float]) -> int:
    """A value's class: how many edges it reaches (a value on an edge is in the upper class)."""
    return sum(value >= e for e in edges)


def mode(values: Sequence[float], edges: Sequence[float]) -> int:
    """The most common class of some values; a tie goes to the lower class."""
    counts = [0] * (len(edges) + 1)
    for v in values:
        counts[klass(v, edges)] += 1
    return max(range(len(counts)), key=lambda k: (counts[k], -k))


def mcnemar_one_sided(b: int, c: int) -> float:
    """The exact one-sided McNemar p-value: P(X >= b) for X ~ Binomial(b + c, 1/2) (1 if none)."""
    n = b + c
    if n == 0:
        return 1.0
    return float(sum(math.comb(n, i) for i in range(b, n + 1)) / 2**n)


@dataclass(frozen=True)
class Scored:
    """One pooled pair: its site, river group, gauge value and the never-saw estimate (FNU)."""

    station: str
    group: str
    value: float
    estimate: float


@dataclass(frozen=True)
class Pooled:
    """The pooled pairs, and each site's training-year values and group."""

    pairs: list[Scored]
    training: dict[str, list[float]]  # site -> its training-year values
    group_of: dict[str, str]
    similar: list[str]


def pooled(cfg: QualityConfig, root: Path) -> Pooled:
    """The transfer test's pooled similar-river pairs, as its ``evaluate`` builds them.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The pairs and the sites' training values.

    Raises:
        ValueError: When the rebuild does not reproduce the transfer test's pooled count and
            class agreement (then these are not its pairs, and nothing is counted).
    """
    data = t.load(cfg, root)
    by_site: dict[str, list[Any]] = {}
    for p in data.pairs:
        by_site.setdefault(p.station, []).append(p)
    training = {s: [p.value for p in site.split(ps)[0]] for s, ps in by_site.items()}
    medians = {s: float(np.median(v)) for s, v in training.items()}
    similar = sorted(s for s, m in medians.items() if m >= t.SIMILAR_MIN_FNU)
    pairs: list[Scored] = []
    for fold in t.folds():
        if not fold.held_out or fold.report_only:
            continue
        train_pairs = data.training(fold.held_out)
        model = t.model(root, fold, [p.value for p in train_pairs])
        for station in sorted(s for s in by_site if data.group_of[s] in fold.held_out):
            lock = site.split(by_site[station])[1]
            if len(lock) < t.MIN_SCORED or station not in similar:
                continue
            pairs += [Scored(station, data.group_of[station], p.value,
                             model.forest.predict(p.features)) for p in lock]  # fmt: skip
    reference = json.loads((root / t.RESULTS / "transfer_pooled.json").read_text(encoding="utf-8"))
    agree = sum(klass(p.estimate, THREE) == klass(p.value, THREE) for p in pairs)
    if len(pairs) != reference["n"] or agree != reference["class_agreement"]:
        raise ValueError(f"the rebuild found {agree} of {len(pairs)}, the transfer test "
                         f"{reference['class_agreement']} of {reference['n']}")  # fmt: skip
    return Pooled(pairs, training, dict(data.group_of), similar)


def _guess(data: Pooled, group: str, kind: str, edges: Sequence[float]) -> int:
    # B1: the other similar sites; B2: every site not in the group; B3: the group's own sites.
    if kind == "B1":
        sites = [s for s in data.similar if data.group_of[s] != group]
    elif kind == "B2":
        sites = [s for s in data.training if data.group_of[s] != group]
    else:
        sites = [s for s in data.training if data.group_of[s] == group]
    return mode([v for s in sites for v in data.training[s]], edges)


def _check_frozen(root: Path, path: Path) -> None:
    """Refuse to run a test whose preregistration is not the frozen file."""
    lines = [json.loads(x) for x in (root / FROZEN).read_text(encoding="utf-8").splitlines() if x]
    frozen = [x["sha256"] for x in lines if x["path"] == path.as_posix()]
    if not frozen or cards.file_sha256(root / path) != frozen[-1]:
        raise ValueError(f"{path.as_posix()} is not the file frozen in {FROZEN.as_posix()}")


def class_baseline(cfg: QualityConfig, root: Path, data: Pooled | None = None) -> dict[str, Any]:
    """The three-class baselines next to the model (preregistration-class-baseline.md).

    Args:
        cfg: Settings.
        root: Repository root.
        data: The pooled pairs (rebuilt when omitted).

    Returns:
        ``rows`` (one per baseline and site, and pooled) and ``summary``.
    """
    data = data or pooled(cfg, root)
    sites = sorted({p.station for p in data.pairs})
    rows: list[dict[str, Any]] = []
    totals: dict[str, int] = {}
    model_only = baseline_only = 0
    for kind in ("model", "B1", "B2", "B3"):
        total = 0
        for s in [*sites, "pooled"]:
            mine = [p for p in data.pairs if s in ("pooled", p.station)]
            if kind == "model":
                k = sum(klass(p.estimate, THREE) == klass(p.value, THREE) for p in mine)
                guess = ""
            else:
                guesses = [_guess(data, p.group, kind, THREE) for p in mine]
                k = sum(g == klass(p.value, THREE) for g, p in zip(guesses, mine, strict=True))
                guess = "" if s == "pooled" else str(guesses[0])
            rows.append({"baseline": kind, "site": s, "n": len(mine), "matched": k,
                         "guessed_class": guess})  # fmt: skip
            if s == "pooled":
                total = k
        totals[kind] = total
    for p in data.pairs:
        right = klass(p.estimate, THREE) == klass(p.value, THREE)
        guess_right = _guess(data, p.group, "B1", THREE) == klass(p.value, THREE)
        model_only += right and not guess_right
        baseline_only += guess_right and not right
    summary = {
        "n": len(data.pairs), "class_edges_fnu": list(THREE), "model_matched": totals["model"],
        "b1_matched": totals["B1"], "b2_matched": totals["B2"], "b3_matched": totals["B3"],
        "b1_split": {"model_only": model_only, "b1_only": baseline_only},
        "label": LABEL, "preregistration": BASELINE_PREREGISTRATION.as_posix(),
        "preregistration_sha256": cards.file_sha256(root / BASELINE_PREREGISTRATION),
    }  # fmt: skip
    return {"rows": rows, "summary": summary}


def four_classes(cfg: QualityConfig, root: Path, data: Pooled | None = None) -> dict[str, Any]:
    """Four classes against the four-class baseline (preregistration-four-classes.md).

    Args:
        cfg: Settings.
        root: Repository root.
        data: The pooled pairs (rebuilt when omitted).

    Returns:
        ``rows`` (one per site, and pooled) and ``summary`` (with the pass decision).
    """
    data = data or pooled(cfg, root)
    rows: list[dict[str, Any]] = []
    summary: dict[str, Any] = {}
    for s in [*sorted({p.station for p in data.pairs}), "pooled"]:
        mine = [p for p in data.pairs if s in ("pooled", p.station)]
        guesses = [_guess(data, p.group, "B1", FOUR) for p in mine]
        model_right = [klass(p.estimate, FOUR) == klass(p.value, FOUR) for p in mine]
        guess_right = [g == klass(p.value, FOUR) for g, p in zip(guesses, mine, strict=True)]
        b = sum(m and not g for m, g in zip(model_right, guess_right, strict=True))
        c = sum(g and not m for m, g in zip(model_right, guess_right, strict=True))
        far = sum(abs(klass(p.estimate, FOUR) - klass(p.value, FOUR)) >= 2 for p in mine)
        row = {"site": s, "n": len(mine), "model_matched": sum(model_right),
               "baseline_matched": sum(guess_right), "model_only": b, "baseline_only": c,
               "two_or_more_away": far,
               "baseline_class": "" if s == "pooled" else guesses[0]}  # fmt: skip
        rows.append(row)
        if s == "pooled":
            p_value = mcnemar_one_sided(b, c)
            summary = {
                "n": len(mine), "class_edges_fnu": list(FOUR),
                "model_matched": sum(model_right), "baseline_matched": sum(guess_right),
                "model_only": b, "baseline_only": c, "p_value": p_value, "alpha": ALPHA,
                "passes": bool(p_value < ALPHA), "two_or_more_away": far,
                "three_class_matched": sum(klass(p.estimate, THREE) == klass(p.value, THREE)
                                           for p in mine),
                "label": LABEL, "preregistration": FOUR_PREREGISTRATION.as_posix(),
                "preregistration_sha256": cards.file_sha256(root / FOUR_PREREGISTRATION),
            }  # fmt: skip
    return {"rows": rows, "summary": summary}


def _write(results: Mapping[str, Any], out: Path, stem: str) -> list[Path]:
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    write_table(_rounded(results["rows"], 6), out / f"{stem}.csv")
    _json(_rounded([results["summary"]], 6)[0], out / f"{stem}.json")
    written = [out / f"{stem}.csv", out / f"{stem}.json"]
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in sorted(written)]
    (out / "MANIFEST").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return [*written, out / "MANIFEST"]


TESTS: Final = {
    "class-baseline": (BASELINE_PREREGISTRATION, BASELINE_RESULTS, "class_baseline",
                       class_baseline),
    "four-classes": (FOUR_PREREGISTRATION, FOUR_RESULTS, "four_classes", four_classes),
}  # fmt: skip


def run(cfg: QualityConfig, root: Path, name: str) -> list[Path]:
    """Run a test once: its preregistration must be the frozen file, and no result may exist yet.

    Args:
        cfg: Settings.
        root: Repository root.
        name: ``class-baseline`` or ``four-classes``.

    Returns:
        The files written.

    Raises:
        FileExistsError: When the test already ran (its results are committed).
    """
    prereg, results, stem, test = TESTS[name]
    _check_frozen(root, prereg)
    if (root / results / "MANIFEST").exists():
        raise FileExistsError(f"{results.as_posix()} exists: the test runs once")
    return _write(test(cfg, root), root / results, stem)


def verify(cfg: QualityConfig, root: Path) -> list[str]:
    """Recompute every class test that ran and compare with its MANIFEST.

    Args:
        cfg: Settings.
        root: Repository root.

    Returns:
        The mismatches (empty when every committed result is its recomputation).
    """
    problems: list[str] = []
    data: Pooled | None = None
    for _prereg, results, stem, test in TESTS.values():
        if not (root / results / "MANIFEST").exists():
            continue
        data = data or pooled(cfg, root)
        expected = read_manifest(root / results / "MANIFEST")
        with tempfile.TemporaryDirectory() as tmp:
            actual = read_manifest(_write(test(cfg, root, data), Path(tmp) / stem, stem)[-1])
        for file, sha in expected.items():
            committed = hashlib.sha256((root / results / file).read_bytes()).hexdigest()
            if committed != sha:
                problems.append(f"{results.as_posix()}/{file}: does not match its MANIFEST")
            elif actual.get(file) != sha:
                problems.append(f"{results.as_posix()}/{file}: differs from its recomputation")
    return problems
