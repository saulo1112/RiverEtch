"""Generated outputs: small CSV tables and a Markdown summary under docs/site-screening/results/.

These files are produced by the run and committed as evidence. The hand-written interpretation
lives in docs/site-screening/report.md.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from climate_pipeline.screening.events import EventOutcome
from climate_pipeline.screening.score import TERMS, Recommendation, SiteScore
from climate_pipeline.screening.stage1 import Stage1Result, monthly_counts, scene_rows
from climate_pipeline.screening.stage2 import SIGNALS, Stage2Result

WITHIN_SITE_NOTE = (
    "NDTI is a relative index: levels are comparable only within one site and sub-reach, never "
    "between sites, and are not turbidity in physical units."
)


@dataclass
class ChanceRate:
    """Hit rate of randomly shifted windows of one event's length, at one site."""

    site_id: str
    rate: float
    windows: int
    event_id: str = ""
    window_days: int = 0


@dataclass
class RunOutputs:
    """Everything a run produced, ready to be written."""

    manifest: dict[str, object]
    stage1: list[Stage1Result]
    scores: list[SiteScore]
    selected: list[str]
    recommendation: Recommendation | None = None
    stage2: list[Stage2Result] = field(default_factory=list)
    outcomes: list[EventOutcome] = field(default_factory=list)
    chance: list[ChanceRate] = field(default_factory=list)
    false_alarms: dict[str, tuple[float, int]] = field(default_factory=dict)
    figures: list[str] = field(default_factory=list)
    anomaly_threshold: float = 3.0


def _fmt(value: object) -> str:
    if isinstance(value, float):
        return "" if math.isnan(value) else f"{value:.3g}"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def markdown_table(rows: Sequence[dict[str, object]], columns: Sequence[str]) -> str:
    """A GitHub Markdown table.

    Args:
        rows: Row dictionaries.
        columns: Columns to show, in order.

    Returns:
        The table text.
    """
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        cells = [_fmt(row.get(c, "")).replace("|", "/") for c in columns]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def score_rows(scores: Sequence[SiteScore]) -> list[dict[str, object]]:
    """One row per site with terms, score, gates and sensitivity ranks.

    Args:
        scores: Ranked scores.

    Returns:
        Rows.
    """
    rows = []
    for rank, s in enumerate(scores, start=1):
        row: dict[str, object] = {"rank": rank, "site_id": s.site_id, "category": s.category}
        row |= {t: round(s.terms[t], 3) for t in TERMS}
        row |= {
            "score": round(s.score, 3),
            "eligible": s.eligible,
            "gates": "; ".join(s.gates),
            "coverage_observable_rule": round(s.observable_coverage, 3),
        }
        row |= {f"rank_without_{k}": v for k, v in s.ranks_without.items()}
        rows.append(row)
    return rows


def stage2_rows(results: Sequence[Stage2Result], threshold: float) -> list[dict[str, object]]:
    """One row per stage-2 scene.

    Args:
        results: Stage-2 results.
        threshold: |z| threshold.

    Returns:
        Rows.
    """
    rows = []
    for result in results:
        for s in result.scenes:
            row: dict[str, object] = {
                "site_id": result.site.id,
                "acquisition": s.key,
                "datetime_utc": s.datetime.isoformat(),
                "platform": s.platform,
                "scaling": " ".join(s.scaling),
                "excluded": s.exclusion,
            }
            for name, sub in s.sub.items():
                row |= {
                    f"{name}_ndti": round(sub.ndti, 4),
                    f"{name}_px_10m": sub.pixels,
                    f"{name}_red": round(sub.red, 4),
                    f"{name}_green": round(sub.green, 4),
                    f"{name}_swir16": round(sub.swir16, 4),
                    f"{name}_scl_water_share": round(sub.class6_share, 3),
                    f"{name}_glint_share": round(sub.glint_share, 3),
                }
            row["delta_ndti"] = round(s.values["delta"], 4)
            for signal in SIGNALS:
                row[f"z_{signal}"] = round(s.z.get(signal, math.nan), 2)
                row[f"baseline_{signal}"] = s.baseline.get(signal, "")
            row |= {f"rain_{h}h_mm": round(v, 1) for h, v in s.rain_mm.items()}
            row["rain_same_day_mm"] = round(s.rain_same_day_mm, 1)
            row["rain_coincident"] = s.rain_coincident
            row["anomalous_signals"] = " ".join(s.anomalous(threshold))
            rows.append(row)
    return rows


EVENT_ROW_COLUMNS = (
    "event_id", "site_id", "date_start", "date_end", "event_type", "confidence", "status",
    "scene_days", "max_abs_z", "signal", "rain_coincident_scene", "chance_rate",
    "chance_windows", "window_days",
)  # fmt: skip


def exclusion_category(reason: str) -> str:
    """A short category for a stage-2 exclusion reason.

    Args:
        reason: The exclusion text.

    Returns:
        The category.
    """
    if reason.startswith("scaling") or "raster:bands" in reason:
        return "scaling metadata"
    if "reflectance" in reason:
        return "implausible water reflectance"
    if reason.startswith("too few"):
        return "too few water pixels"
    return "other"


def event_rows(
    outcomes: Sequence[EventOutcome],
    stage2: Sequence[Stage2Result],
    chance: Sequence[ChanceRate] = (),
) -> list[dict[str, object]]:
    """One row per scored event with its outcome and the rain context of its strongest scene.

    Args:
        outcomes: Event outcomes.
        stage2: Stage-2 results (for the rain flag of the scenes in the window).
        chance: Chance rates per event (same window length).

    Returns:
        Rows.
    """
    rain_by_day = {
        (r.site.id, s.datetime.date()): s.rain_coincident for r in stage2 for s in r.usable()
    }
    by_event = {(c.site_id, c.event_id): c for c in chance}
    rows = []
    for o in outcomes:
        e = o.event
        c = by_event.get((e.site_id, e.event_id))
        rows.append(
            {
                "event_id": e.event_id,
                "site_id": e.site_id,
                "date_start": e.date_start.isoformat(),
                "date_end": e.date_end.isoformat(),
                "event_type": e.event_type,
                "confidence": e.confidence,
                "status": o.status,
                "scene_days": " ".join(d.isoformat() for d in o.scene_days),
                "max_abs_z": round(o.max_abs_z, 2) if o.max_abs_z is not None else math.nan,
                "signal": o.signal,
                "rain_coincident_scene": any(
                    rain_by_day.get((e.site_id, d), False) for d in o.scene_days
                ),
                "chance_rate": round(c.rate, 3) if c and math.isfinite(c.rate) else math.nan,
                "chance_windows": c.windows if c else 0,
                "window_days": c.window_days if c else 0,
            }
        )
    return rows


def write_all(outputs: RunOutputs, results_dir: Path, out_dir: Path) -> list[Path]:
    """Write every generated table, the manifest and results.md.

    Args:
        outputs: The run's outputs.
        results_dir: ``docs/site-screening/results`` (committed).
        out_dir: ``pipeline/out`` (git-ignored, per-acquisition detail).

    Returns:
        The files written.
    """
    results_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    def csv(rows: list[dict[str, object]], path: Path, columns: Sequence[str] = ()) -> None:
        frame = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(columns) or ["none"])
        frame.to_csv(path, index=False)
        written.append(path)

    csv([row for r in outputs.stage1 for row in scene_rows(r)], out_dir / "screening_stage1.csv")
    summaries = [r.summary for r in outputs.stage1]
    csv(summaries, results_dir / "stage1_summary.csv")
    monthly = []
    for r in outputs.stage1:
        start = outputs.manifest["period_start"]
        end = outputs.manifest["period_end"]
        assert isinstance(start, str) and isinstance(end, str)
        table = monthly_counts(r.scenes, pd.Timestamp(start).date(), pd.Timestamp(end).date())
        monthly += [{"site_id": r.site.id, "month": m, **counts} for m, counts in table.items()]
    csv(monthly, results_dir / "stage1_monthly.csv")
    csv(score_rows(outputs.scores), results_dir / "scores.csv")
    if outputs.stage2:
        csv(
            stage2_rows(outputs.stage2, outputs.anomaly_threshold),
            results_dir / "stage2_scenes.csv",
            ("site_id", "acquisition", "excluded"),
        )
    csv(
        event_rows(outputs.outcomes, outputs.stage2, outputs.chance),
        results_dir / "event_validation.csv",
        EVENT_ROW_COLUMNS,
    )
    manifest_path = results_dir / "run_manifest.json"
    manifest_path.write_text(json.dumps(outputs.manifest, indent=2, sort_keys=True) + "\n")
    written.append(manifest_path)
    md = results_dir / "results.md"
    md.write_text(render_markdown(outputs), encoding="utf-8")
    written.append(md)
    return written


def _recommendation_lines(rec: Recommendation | None) -> list[str]:
    if rec is None or rec.recommended is None:
        return ["Recommendation (pre-registered rule): no eligible category A or C site."]
    lines = [
        f"Recommendation (pre-registered rule: best eligible category A or C site): "
        f"**{rec.recommended}**; runner-up: {rec.runner_up or 'none'}.",
    ]
    if rec.fragile:
        lines.append(f"The ranking is **fragile**: {'; '.join(rec.changes)}.")
    else:
        lines.append("The ranking is robust to dropping any one term.")
    return lines


def render_markdown(outputs: RunOutputs) -> str:
    """The generated results page.

    Args:
        outputs: The run's outputs.

    Returns:
        Markdown text.
    """
    m = outputs.manifest
    parts = [
        "# Site screening: generated results",
        "",
        "Generated by `climate-pipeline screening`; do not edit by hand. Interpretation: "
        "[report.md](../report.md). Method (pre-registered): [method.md](../method.md).",
        "",
        f"- Period: {m['period_start']} to {m['period_end']}; STAC source: {m['source']}",
        f"- method.md git blob: `{m['method_blob']}`; config sha256: `{m['config_sha256']}`",
        f"- Commit: `{m['git_commit']}`; run finished: {m['finished_utc']}",
        "",
        f"> {WITHIN_SITE_NOTE}",
        "",
        "## Stage 1: observability (SCL only)",
        "",
        markdown_table(
            [r.summary for r in outputs.stage1],
            [
                "site_id",
                "category",
                "geometry_failed",
                "water_frequency_threshold",
                "acquisitions",
                "clear",
                "observable",
                "clear_per_year",
                "months_with_clear_pct",
                "longest_gap_clear_days",
                "width_px_10m",
                "tile_integrity",
                "multi_tile_share",
                "suspect_turbid_as_cloud",
            ],
        ),
        "",
        "## Score and stage-2 selection",
        "",
        markdown_table(
            score_rows(outputs.scores),
            ["rank", "site_id", "category", *TERMS, "score", "eligible", "gates"],
        ),
        "",
        f"Stage-2 set (pre-registered rule): {', '.join(outputs.selected) or 'none'}.",
        "",
        *_recommendation_lines(outputs.recommendation),
        "",
        "Sensitivity: rank of each site with one term dropped, or with coverage from the "
        "observable rule.",
        "",
        markdown_table(
            score_rows(outputs.scores),
            ["site_id", *(f"rank_without_{k}" for k in (*TERMS, "observable_coverage"))],
        ),
        "",
    ]
    if outputs.stage2:
        parts += ["## Stage 2: NDTI anomalies", ""]
        rows = []
        for r in outputs.stage2:
            usable = r.usable()
            anomalies = [s for s in usable if s.anomalous(outputs.anomaly_threshold)]
            excluded = Counter(exclusion_category(s.exclusion) for s in r.scenes if not s.usable)
            rate, n = outputs.false_alarms.get(r.site.id, (math.nan, 0))
            rows.append(
                {
                    "site_id": r.site.id,
                    "observable": len(r.scenes),
                    "usable": len(usable),
                    "excluded": "; ".join(f"{k} {v}" for k, v in excluded.items()),
                    "anomalous": len(anomalies),
                    "not_rain_coincident": sum(1 for s in anomalies if not s.rain_coincident),
                    "share_anomalous": round(len(anomalies) / len(usable), 3)
                    if usable
                    else math.nan,
                    "scored_scenes": n,
                    "cap_skipped": r.truncated,
                    "rate_if_control": rate,
                }
            )
        parts.append(
            markdown_table(
                rows,
                [
                    "site_id",
                    "observable",
                    "usable",
                    "excluded",
                    "anomalous",
                    "not_rain_coincident",
                    "share_anomalous",
                    "cap_skipped",
                ],
            )
        )
        parts += ["", "## Event validation", ""]
        parts.append(
            markdown_table(
                event_rows(outputs.outcomes, outputs.stage2, outputs.chance),
                [
                    "event_id",
                    "site_id",
                    "date_start",
                    "event_type",
                    "status",
                    "max_abs_z",
                    "signal",
                    "rain_coincident_scene",
                    "chance_rate",
                ],
            )
            if outputs.outcomes
            else "No scored catalog event belongs to a stage-2 site."
        )
        parts += [
            "",
            "Chance rate: share of observable random windows of the same length, away from "
            "catalog events, that reach the threshold (per event above; per site here for sites "
            "without scored events):",
            "",
        ]
        parts.append(
            markdown_table(
                [
                    {
                        "site_id": c.site_id,
                        "rate": c.rate,
                        "windows": c.windows,
                        "window_days": c.window_days,
                    }
                    for c in outputs.chance
                    if not c.event_id
                ],
                ["site_id", "rate", "windows", "window_days"],
            )
        )
        parts += [
            "",
            "False-alarm rate at the control (share of scored scenes with |z| >= threshold):",
            "",
        ]
        parts.append(
            markdown_table(
                [
                    {"site_id": k, "rate": v[0], "scenes": v[1]}
                    for k, v in outputs.false_alarms.items()
                ],
                ["site_id", "rate", "scenes"],
            )
            if outputs.false_alarms
            else "No control site was screened in this run, so no false-alarm rate exists."
        )
    if outputs.figures:
        parts += ["", "## Figures", ""] + [
            f"- [{Path(f).name}](figures/{Path(f).name})" for f in outputs.figures
        ]
    return "\n".join(parts) + "\n"
