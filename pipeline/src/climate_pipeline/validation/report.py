"""Generated outputs of the validation: CSV tables, results.md, the manifest, figures, the case.

The files under ``docs/urra-validation/results/`` are written by the run and committed as
evidence, byte for byte (they are kept out of Prettier). The interpretation lives in
``docs/urra-validation/report.md``.
"""

from __future__ import annotations

import csv
import json
import math
import shutil
from collections import Counter
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from climate_pipeline.screening.report import markdown_table
from climate_pipeline.validation.run import SiteRun, ValidationOutputs

WITHIN_SITE_NOTE = (
    "NDTI is a relative index: comparable only within one sub-reach, never between sites, never "
    "NTU. An anomaly is a departure from the sub-reach's own baseline: a flag to investigate, "
    "never evidence that any actor caused anything."
)


def _cell(value: object) -> str:
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(round(value, 6))
    if isinstance(value, bool):
        return "true" if value else "false"
    return "" if value is None else str(value)


def write_table(rows: Sequence[dict[str, object]], path: Path) -> None:
    """Write rows as CSV with LF line ends (columns in first-seen order).

    Args:
        rows: The rows.
        path: The file.
    """
    columns: list[str] = []
    for row in rows:
        columns += [k for k in row if k not in columns]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns or ["none"])
        for row in rows:
            writer.writerow([_cell(row.get(c)) for c in columns])


def series_figure(
    run: SiteRun, limit: float, persistence_min: int, holdout_end: date, path: Path
) -> bool:
    """Downstream NDTI and the difference signal over time, with the anomalies marked.

    Args:
        run: A site run with stage 2.
        limit: The screening's glint limit (D0's values are plotted).
        persistence_min: Variants a persistent scene is anomalous in.
        holdout_end: Last day of the hold-out period (shaded).
        path: The PNG file.

    Returns:
        False when the run has nothing to plot.
    """
    if run.persistence is None or not run.records:
        return False
    days = [r.day for r in run.records]
    d0 = run.persistence.evaluations["D0"]
    usable = [k for k, r in enumerate(run.records) if r.usable[limit]]
    fig, axes = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True)
    titles = ("downstream sub-reach NDTI", "downstream minus upstream NDTI")
    for ax, signal, title in zip(axes, ("downstream", "delta"), titles, strict=True):

        def value(k: int, s: str = signal) -> float:
            return run.records[k].values[limit][s]

        ax.axvspan(days[0], holdout_end, color="0.93", zorder=0)
        ax.plot([days[k] for k in usable], [value(k) for k in usable], "-", color="0.75", lw=0.8)
        ax.scatter(
            [days[k] for k in usable],
            [value(k) for k in usable],
            s=10,
            color="0.45",
            label="usable scene",
        )
        anomalous = [k for k in usable if signal in d0[k].signals]
        ax.scatter(
            [days[k] for k in anomalous],
            [value(k) for k in anomalous],
            s=36,
            facecolors="none",
            edgecolors="tab:orange",
            lw=1.4,
            label="D0 anomaly",
        )
        persistent = [
            k
            for k in anomalous
            if run.persistence.counts[k] >= persistence_min and run.union[k] == "no"
        ]
        ax.scatter(
            [days[k] for k in persistent],
            [value(k) for k in persistent],
            s=36,
            color="tab:red",
            label=f"in >= {persistence_min} variants, no rain flag",
        )
        ax.set_title(title, fontsize=9, loc="left")
        ax.tick_params(labelsize=8)
    axes[0].legend(fontsize=7, loc="upper left", ncols=3, frameon=False)
    fig.suptitle(f"{run.site.id}: hold-out period shaded; NDTI is relative, never NTU", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def _met(flag: bool | None) -> str:
    return "n/a" if flag is None else ("met" if flag else "not met")


def _verdict_lines(outputs: ValidationOutputs) -> list[str]:
    v = outputs.verdict
    if v is None:
        return ["Smoke run (stage 1 only): no NDTI was computed and there is no verdict."]
    ratio = f"{v.ratio:.2f}" if math.isfinite(v.ratio) else "n/a"
    lines = [
        f"**Mechanical verdict: {v.label}.**",
        "",
        f"- (a) episodes of persistent, not rain-coincident scenes: {v.episodes} "
        f"(needed: at least {v.episodes_needed}): {_met(v.criterion_a)}.",
        f"- (b) target D0 share {v.target_anomalous}/{v.target_scored} = {v.target_share:.4f}; "
        f"control D0 share {v.control_anomalous}/{v.control_scored} "
        f"(as used: {v.control_share:.4f}); ratio {ratio} "
        f"(needed: at least {v.ratio_needed:g}): {_met(v.criterion_b)}.",
    ]
    if v.reasons:
        lines.append(f"- Reasons: {'; '.join(v.reasons)}.")
    return lines


def render_markdown(outputs: ValidationOutputs, files: Sequence[str]) -> str:
    """The generated results page.

    Args:
        outputs: The run's outputs.
        files: Names of the files written next to it.

    Returns:
        Markdown text.
    """
    m = outputs.manifest
    t = outputs.tables
    parts = [
        "# Urrá validation: generated results",
        "",
        "Generated by `climate-pipeline validation`; do not edit by hand. Method (pre-registered): "
        "[method.md](../method.md). Interpretation: [report.md](../report.md).",
        "",
        f"- Run: {m.get('run')}; period {m.get('period')}",
        f"- method.md git blob: `{m.get('method_blob')}` "
        f"(last changed in `{m.get('method_last_commit')}`)",
        f"- Commit: `{m.get('git_commit')}`; "
        f"validation config sha256: `{m.get('validation_config_sha256')}`",
        f"- Started {m.get('started_utc')}; finished {m.get('finished_utc', 'stage 1 only')}",
        "",
        f"> {WITHIN_SITE_NOTE}",
        "",
        "## Verdict",
        "",
        *_verdict_lines(outputs),
        "",
    ]
    if t.get("episodes"):
        parts += [
            "Episodes (criterion a):",
            "",
            markdown_table(t["episodes"], ["episode", "days", "scenes"]),
            "",
        ]
    checks = t.get("reproduction_stage1", []) + t.get("reproduction_ndti", [])
    failed = [c for c in checks if not c.get("pass")]
    parts += [
        "## Reproduction checks (2022-2025)",
        "",
        f"{len(checks) - len(failed)} of {len(checks)} checks pass.",
    ]
    if failed:
        parts += ["", markdown_table(failed, sorted({k for c in failed for k in c}))]
    parts.append("")
    if t.get("variants"):
        parts += [
            "## Variants",
            "",
            markdown_table(
                t["variants"],
                [
                    "site_id",
                    "variant",
                    "distinct",
                    "scored",
                    "insufficient",
                    "removed",
                    "anomalous",
                    "share",
                    "anomalous_in_both_with_d0",
                    "only_d0",
                    "only_variant",
                ],
            ),
            "",
        ]
    if t.get("catchment_thresholds"):
        parts += [
            "## Catchment rain rule",
            "",
            markdown_table(
                t["catchment_thresholds"], ["statistic", "window_h", "threshold_mm", "days"]
            ),
            "",
        ]
    if outputs.runs["target"].union:
        counts = Counter(outputs.runs["target"].union)
        parts += [f"Target scenes by union rain flag: {dict(sorted(counts.items()))}.", ""]
    if outputs.placebo is not None:
        p = outputs.placebo
        parts += [
            "## Placebo (within-season shuffles)",
            "",
            f"- S1 (D0 anomalies not rain-coincident): observed {p.observed_s1}, p = {p.p_s1:.3f}.",
            f"- S2 (criterion-a episodes): observed {p.observed_s2}, p = {p.p_s2:.3f}.",
            "",
        ]
    for name, title, columns in (
        (
            "chance_level",
            "Chance level (binomial, report-only)",
            ["label", "k", "n", "p", "p_at_least_k"],
        ),
        (
            "holdout",
            "Hold-out view",
            [
                "site_id",
                "part",
                "scenes",
                "scored_d0",
                "anomalous_d0",
                "persistent",
                "candidates",
                "episodes",
            ],
        ),
        (
            "events",
            "Event test (report-only)",
            [
                "event_id",
                "date_start",
                "status_d0",
                "max_abs_z",
                "persistent_scene_in_window",
                "chance_rate",
            ],
        ),
        ("rainy_months", "Rainy months", ["site_id", "frozen", "rule_over_whole_period"]),
        (
            "geometry_check",
            "Whole-period geometry check",
            ["site_id", "subreach", "overlap", "note"],
        ),
        (
            "catchment_cells",
            "Open-Meteo cells of the catchment grid",
            ["cell_lon", "cell_lat", "points"],
        ),
        ("chirps_probe", "CHIRPS probe", ["url", "status", "values_mm"]),
    ):
        if t.get(name):
            parts += [f"## {title}", "", markdown_table(t[name], columns), ""]
    if outputs.notes:
        parts += ["## Notes", "", *[f"- {n}" for n in outputs.notes], ""]
    parts += ["## Files", "", *[f"- [{f}]({f})" for f in files], ""]
    return "\n".join(parts)


def write_outputs(outputs: ValidationOutputs, results: Path, root: Path) -> list[Path]:
    """Write every output; the results folder starts empty so nothing stale survives.

    Args:
        outputs: The run's outputs.
        results: The results folder.
        root: Repository root (for the case file paths).

    Returns:
        The files written.
    """
    shutil.rmtree(results, ignore_errors=True)
    (results / "figures").mkdir(parents=True)
    written: list[Path] = []
    for name, rows in sorted(outputs.tables.items()):
        path = results / f"{name}.csv"
        write_table(rows, path)
        written.append(path)
    cfg = outputs.cfg
    if not outputs.stage1_only:
        for run in outputs.runs.values():
            path = results / "figures" / f"{run.site.id}_series.png"
            limit = cfg.variant("D0").swir16_max
            if series_figure(run, limit, cfg.criteria.persistence_min, cfg.holdout.end, path):
                written.append(path)
    manifest = results / "run_manifest.json"
    manifest.write_text(
        json.dumps(outputs.manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    written.append(manifest)
    if outputs.case is not None:
        text = outputs.case.to_json()
        case_path = root / cfg.outputs.case_json
        case_path.parent.mkdir(parents=True, exist_ok=True)
        case_path.write_text(text, encoding="utf-8", newline="\n")
        sample = root / cfg.outputs.case_sample
        if len(text.encode("utf-8")) < cfg.outputs.max_committed_bytes:
            sample.write_text(text, encoding="utf-8", newline="\n")
        else:
            outputs.notes.append(f"case file is {len(text.encode())} bytes: no sample committed")
    names = [p.relative_to(results).as_posix() for p in written]
    md = results / "results.md"
    md.write_text(render_markdown(outputs, names), encoding="utf-8", newline="\n")
    written.append(md)
    return written
