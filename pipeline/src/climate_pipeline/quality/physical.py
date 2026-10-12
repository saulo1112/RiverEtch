"""v2.2, Stage A: a post-hoc calibration on ACOLITE RAdCor (preregistration, checkpoint 2).

The Magdalena pairs Route B already has under RAdCor (D15's pairs and 300 m windows) are scored
with v2.1's nested leave-one-station-out. Candidates, simplest first: R1, the published model as
it is (turbidity: Dogliotti 2015; TSS: the MDN); R2, R1 with a Magdalena adjustment; R3, log-log
OLS on RAdCor's B8A/B04. Stage B (downloading the remaining pairs) is due only if Stage A beats
v2.1 for a target; the summary says whether it does.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from climate_pipeline.calibration.matchups import Pair
from climate_pipeline.quality import posthoc, route_a, transfer
from climate_pipeline.quality.config import QualityConfig
from climate_pipeline.quality.route_a import Predictor
from climate_pipeline.quality.route_b import RouteBInputs, common_pairs, published

ORDER = ("R1", "R2", "R3")
CORRECTION = "radcor"
PUBLISHED = {"turbidity": "B1 Dogliotti 2015", "tss": "B3 MDN"}


def candidates(cfg: QualityConfig, rb: RouteBInputs, target: str) -> dict[str, Predictor]:
    """R1-R3 for one target.

    Args:
        cfg: Settings (the adjustment's lambdas).
        rb: Route B's inputs.
        target: Target id.

    Returns:
        Candidate id -> predictor, simplest first.
    """
    model = published(rb)[target][PUBLISHED[target]]

    def raw(p: Pair) -> float:
        return model(p, CORRECTION)

    def r1(train: Any, test: Any) -> list[float]:
        return [raw(p) for p in test]

    return {"R1": r1, "R2": transfer.transfer_predictor(raw, cfg), "R3": route_a.a1}


def analyse(cfg: QualityConfig, rb: RouteBInputs,
            v21: Mapping[str, Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:  # fmt: skip
    """The Stage A tables.

    Args:
        cfg: Settings.
        rb: Route B's inputs.
        v21: v2.1's summary (target -> ``mdsa``), for Stage B's condition.

    Returns:
        ``physical_scores``, ``physical_levels`` and ``physical_choices``.
    """
    from climate_pipeline.quality.route_b import _seed

    tables: dict[str, list[dict[str, Any]]] = {
        "physical_scores": [],
        "physical_levels": [],
        "physical_choices": [],
    }
    for target in cfg.targets:
        pool = common_pairs(rb, target.id)[CORRECTION]
        base = {"target": target.id, "correction": "ACOLITE RAdCor", "window": "300m",
                "published": PUBLISHED[target.id]}  # fmt: skip
        if len({p.station for p in pool}) < 3:
            tables["physical_scores"].append({**base, "status": "insufficient_data"})
            continue
        options = candidates(cfg, rb, target.id)
        seed = _seed(cfg.seed, "physical", target.id)
        result = posthoc.nested(cfg, pool, options, order=ORDER)
        m = posthoc.metrics(cfg, pool, result, list(range(len(pool))), seed)
        rows = posthoc.level_rows(cfg, target, pool, result, seed)
        reference = v21.get(target.id, {}).get("mdsa", float("nan"))
        tables["physical_scores"].append({
            **base, "evaluation": "nested LOSO", **m, "level": rows[0]["level"],
            "v21_mdsa": reference, "stage_b_due": bool(m["mdsa"] < reference),
        })  # fmt: skip
        r1 = [options["R1"]([], [p])[0] for p in pool]
        m1 = route_a.evaluate(cfg, pool, r1, result.null, None, seed + 3)
        tables["physical_scores"].append({**base, "evaluation": "R1 as published (no fit)",
                                          **m1})  # fmt: skip
        tables["physical_levels"] += [{"target": target.id, **r} for r in rows]
        tables["physical_choices"] += [
            {"target": target.id, "held_out_station": g, "chosen": c}
            for g, c in result.chosen.items()
        ]
    return tables


def summary(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Stage A's nested error, level and Stage B's condition per target.

    Args:
        tables: The run's tables.

    Returns:
        Target -> ``mdsa``, ``level``, ``n``, ``stage_b_due``.
    """
    out: dict[str, Any] = {}
    for r in tables.get("physical_scores", []):
        if r.get("evaluation") == "nested LOSO":
            lv = f"{r['level']} (post hoc)" if r["level"] != "none" else "none"
            out[r["target"]] = {"level": lv, "mdsa": round(r["mdsa"], 1), "n": int(r["n"]),
                                "stage_b_due": r["stage_b_due"]}  # fmt: skip
    return out
