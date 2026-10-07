"""The pre-registered site score, its hard gates, the stage-2 selection and a sensitivity check.

Every term is anchored in absolute units (never rescaled across the candidate sites), so a site's
score does not depend on which other sites were screened. See docs/site-screening/method.md.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

from climate_pipeline.screening.config import ScoreWeights, ScreeningConfig

TERMS = ("coverage", "width", "tile_integrity", "contrast_feasibility", "events")


@dataclass(frozen=True)
class SiteInputs:
    """What the score needs from stage 1 and the event catalog."""

    site_id: str
    category: str
    geometry_failed: str
    clear: int
    clear_per_year: float
    months_with_clear_pct: float
    observable_per_year: float
    months_with_observable_pct: float
    width_px_10m: float
    tile_integrity: float
    median_weaker_subreach_water_px_10m: float
    confluence_inside: bool
    events_with_clear_window: int


@dataclass(frozen=True)
class SiteScore:
    """A site's terms, score and gates."""

    site_id: str
    category: str
    terms: dict[str, float]
    score: float
    gates: tuple[str, ...]
    observable_coverage: float
    ranks_without: dict[str, int] = field(default_factory=dict)

    @property
    def eligible(self) -> bool:
        """Not excluded by a hard gate."""
        return not self.gates


def _clamp(value: float) -> float:
    return 0.0 if math.isnan(value) else min(1.0, max(0.0, value))


def coverage_term(per_year: float, months_pct: float, cfg: ScreeningConfig) -> float:
    """Half clear-scene rate, half share of months with a clear scene.

    Args:
        per_year: Clear scenes per year.
        months_pct: Percentage of months with at least one clear scene.
        cfg: Settings.

    Returns:
        The term in [0, 1].
    """
    return 0.5 * _clamp(per_year / cfg.score.clear_per_year_full) + 0.5 * _clamp(months_pct / 100)


def site_terms(inputs: SiteInputs, cfg: ScreeningConfig) -> dict[str, float]:
    """The five score terms of a site, each in [0, 1].

    Args:
        inputs: Stage-1 and catalog inputs.
        cfg: Settings.

    Returns:
        Terms by name.
    """
    w = cfg.width
    feasibility = _clamp(inputs.median_weaker_subreach_water_px_10m / cfg.score.feasibility_px_full)
    if inputs.confluence_inside:
        feasibility *= 0.5
    return {
        "coverage": coverage_term(inputs.clear_per_year, inputs.months_with_clear_pct, cfg),
        "width": _clamp(
            (inputs.width_px_10m - w.unreliable_below_px_10m)
            / (w.adequate_at_px_10m - w.unreliable_below_px_10m)
        ),
        "tile_integrity": _clamp(inputs.tile_integrity),
        "contrast_feasibility": feasibility,
        "events": _clamp(inputs.events_with_clear_window / cfg.score.events_full),
    }


def weighted(terms: dict[str, float], weights: ScoreWeights, drop: str | None = None) -> float:
    """Weighted sum of the terms, renormalized when one term is dropped.

    Args:
        terms: Terms by name.
        weights: Pre-registered weights.
        drop: A term to leave out (sensitivity check), if any.

    Returns:
        The score in [0, 1].
    """
    w = weights.model_dump()
    kept = {k: v for k, v in w.items() if k != drop}
    total = sum(kept.values())
    return sum(terms[k] * v for k, v in kept.items()) / total if total else 0.0


def gates(inputs: SiteInputs, cfg: ScreeningConfig) -> tuple[str, ...]:
    """Hard exclusions, whatever the score.

    Args:
        inputs: Stage-1 inputs.
        cfg: Settings.

    Returns:
        The reasons a site is excluded (empty if eligible).
    """
    reasons = []
    if inputs.geometry_failed:
        reasons.append(f"mask failed: {inputs.geometry_failed}")
    elif math.isnan(inputs.width_px_10m) or inputs.width_px_10m < cfg.width.unreliable_below_px_10m:
        reasons.append(
            f"width {inputs.width_px_10m:.1f} px < {cfg.width.unreliable_below_px_10m:g}"
        )
    if inputs.clear < cfg.score.min_clear_total:
        reasons.append(f"{inputs.clear} clear scenes < {cfg.score.min_clear_total}")
    return tuple(reasons)


def score_sites(inputs: Sequence[SiteInputs], cfg: ScreeningConfig) -> list[SiteScore]:
    """Score, gate and rank every site, with ranks when each term is dropped.

    Args:
        inputs: One entry per site.
        cfg: Settings.

    Returns:
        Scores sorted best first (eligible sites before gated ones).
    """
    scored = []
    for item in inputs:
        terms = site_terms(item, cfg)
        scored.append(
            SiteScore(
                site_id=item.site_id,
                category=item.category,
                terms=terms,
                score=weighted(terms, cfg.score.weights),
                gates=gates(item, cfg),
                observable_coverage=coverage_term(
                    item.observable_per_year, item.months_with_observable_pct, cfg
                ),
            )
        )
    ranked = _rank(scored)
    for drop in (*TERMS, "observable_coverage"):
        order = _rank(
            [
                SiteScore(
                    s.site_id,
                    s.category,
                    s.terms,
                    _variant_score(s, cfg, drop),
                    s.gates,
                    s.observable_coverage,
                )
                for s in scored
            ]
        )
        for position, s in enumerate(order, start=1):
            next(r for r in ranked if r.site_id == s.site_id).ranks_without[drop] = position
    return ranked


def _variant_score(site: SiteScore, cfg: ScreeningConfig, variant: str) -> float:
    if variant == "observable_coverage":
        return weighted({**site.terms, "coverage": site.observable_coverage}, cfg.score.weights)
    return weighted(site.terms, cfg.score.weights, drop=variant)


def _rank(scores: list[SiteScore]) -> list[SiteScore]:
    return sorted(scores, key=lambda s: (not s.eligible, -s.score, s.site_id))


def select_stage2(ranked: Sequence[SiteScore], cfg: ScreeningConfig) -> list[str]:
    """The pre-registered stage-2 set.

    The best eligible non-control sites by score, at most ``stage2_max_benchmarks`` of them
    mining benchmarks (category B), up to ``stage2_top`` sites; then every eligible control.

    Args:
        ranked: Scores, best first.
        cfg: Settings.

    Returns:
        Site ids in selection order.
    """
    chosen: list[str] = []
    benchmarks = 0
    for s in ranked:
        if len(chosen) >= cfg.score.stage2_top:
            break
        if not s.eligible or s.category == "D":
            continue
        if s.category == "B":
            if benchmarks >= cfg.score.stage2_max_benchmarks:
                continue
            benchmarks += 1
        chosen.append(s.site_id)
    chosen += [s.site_id for s in ranked if s.category == "D" and s.eligible]
    return chosen


RECOMMENDABLE = ("A", "C")
"""Categories the study reach is chosen from; mining benchmarks (B) and controls (D) are not."""


@dataclass(frozen=True)
class Recommendation:
    """The pre-registered recommendation and how robust it is to the score's terms."""

    recommended: str | None
    runner_up: str | None
    fragile: bool
    changes: tuple[str, ...]


def recommend(ranked: Sequence[SiteScore]) -> Recommendation:
    """The highest-scoring eligible category A or C site, its runner-up, and a fragility flag.

    The ranking is fragile when dropping any one term, or computing coverage with the observable
    rule, puts a different site first among the eligible A and C sites.

    Args:
        ranked: Scores, best first, with ``ranks_without`` filled in.

    Returns:
        The recommendation.
    """
    candidates = [s for s in ranked if s.eligible and s.category in RECOMMENDABLE]
    if not candidates:
        return Recommendation(None, None, False, ())
    top = candidates[0].site_id
    changes = []
    for variant in candidates[0].ranks_without:
        leader = min(candidates, key=lambda s: s.ranks_without.get(variant, len(ranked) + 1))
        if leader.site_id != top:
            changes.append(f"without {variant}: {leader.site_id}")
    runner = candidates[1].site_id if len(candidates) > 1 else None
    return Recommendation(top, runner, bool(changes), tuple(changes))
