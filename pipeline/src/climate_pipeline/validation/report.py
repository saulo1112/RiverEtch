"""Generated outputs of a validation: CSV tables, results.md, the manifest, figures, the case.

The files under the validation's results folder (e.g. ``docs/urra-validation/results/``) are
written by the run and committed as evidence, byte for byte (they are kept out of Prettier). The
interpretation lives in the validation's ``report.md``.
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
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from climate_pipeline.screening.report import markdown_table
from climate_pipeline.validation.injection import Injection
from climate_pipeline.validation.run import SiteRun, ValidationOutputs

WITHIN_SITE_NOTE = (
    "NDTI is a relative index: comparable only within one sub-reach, never between sites, never "
    "NTU. An anomaly is a departure from the sub-reach's own baseline: a flag to investigate, "
    "never evidence that any actor caused anything."
)

BASELINE_TABLES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "quietness",
        "False-alarm share by variant (Wilson 95 %)",
        ["site_id", "variant", "scored", "anomalous", "share", "wilson_low", "wilson_high"],
    ),
    (
        "corridors",
        "Corridor sensitivity (report-only)",
        ["corridor", "variant", "scored", "anomalous", "share", "wilson_low", "wilson_high",
         "note"],
    ),
    (
        "target_anomalies",
        "Target scenes anomalous under D0",
        ["date", "signals", "z_downstream", "z_delta", "persistence", "glint_share_max",
         "rain_union", "river_level_percentile"],
    ),
    (
        "injection_thresholds",
        "Detection power (injection-recovery on copies)",
        ["scale", "detection_rate", "smallest_grid_step", "interpolated_step",
         "downstream_sigma_ndti"],
    ),
    (
        "injection_all",
        "Detection by NDTI step, all scenes",
        ["size", "injections", "detected", "detected_downstream", "detected_delta"],
    ),
    (
        "demo_event",
        "Demo event (SYNTHETIC, chosen by the pre-registered rule)",
        ["date", "step_ndti", "real_downstream_ndti", "overlay_downstream_ndti", "real_max_abs_z",
         "overlay_max_abs_z", "detected", "eligible_scenes", "note"],
    ),
    (
        "insitu_stations",
        "In-situ stations",
        ["code", "name", "role", "kind", "distance_km", "variables", "samples",
         "samples_in_period", "first", "last", "note"],
    ),
    (
        "insitu_comparison",
        "In-situ comparison (Spearman, bootstrap 95 %)",
        ["comparison", "pairs", "spearman", "ci_low", "ci_high", "reading"],
    ),
    (
        "saturation",
        "Saturation check (NDTI against red reflectance)",
        ["subreach", "scenes", "spearman_lower_half", "spearman_upper_half", "spearman_all",
         "reading"],
    ),
)  # fmt: skip


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
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=7, loc="lower center", ncols=3, frameon=False)
    fig.suptitle(f"{run.site.id}: hold-out period shaded; NDTI is relative, never NTU", fontsize=9)
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def detection_figure(injections: Sequence[Injection], rate: float, path: Path) -> bool:
    """Detection probability against the injected NDTI step: all scenes, by season, by glint.

    Args:
        injections: The injections.
        rate: The pre-registered detection rate (a horizontal line).
        path: The PNG file.

    Returns:
        False without NDTI-scale injections.
    """
    raw = [i for i in injections if i.scale == "ndti"]
    if not raw:
        return False
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    strata: tuple[tuple[str, str], ...] = (
        ("all scenes", "all"),
        ("by season", "season"),
        ("by glint class", "glint"),
    )
    for ax, (title, stratum) in zip(axes, strata, strict=True):
        groups: dict[str, dict[float, list[bool]]] = {}
        for inj in raw:
            name = "all" if stratum == "all" else str(getattr(inj, stratum))
            groups.setdefault(name, {}).setdefault(inj.size, []).append(inj.detected)
        for name, by_size in sorted(groups.items()):
            sizes = sorted(by_size)
            ax.plot(
                sizes,
                [sum(by_size[s]) / len(by_size[s]) for s in sizes],
                "o-",
                ms=3,
                lw=1,
                label=f"{name} ({len(by_size[sizes[0]])} scenes)",
            )
        ax.axhline(rate, color="0.5", lw=0.8, ls="--")
        ax.set_title(title, fontsize=9, loc="left")
        ax.set_xlabel("NDTI step added downstream", fontsize=8)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7, loc="lower right", frameon=False)
    axes[0].set_ylabel("share detected (D0 rule)", fontsize=8)
    fig.suptitle("Injection-recovery on copies of the real series (synthetic steps)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def saturation_figure(outputs: ValidationOutputs, path: Path) -> bool:
    """NDTI against median red reflectance per sub-reach (usable scenes of the target).

    Args:
        outputs: The run's outputs.
        path: The PNG file.

    Returns:
        False without stage 2.
    """
    run = outputs.runs["target"]
    limit = outputs.cfg.variant("D0").swir16_max
    if limit not in run.stage2:
        return False
    scenes = [s for s in run.stage2[limit].scenes if s.usable]
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), sharey=True)
    for ax, name in zip(axes, ("upstream", "downstream"), strict=True):
        pairs = [
            (s.sub[name].red, s.sub[name].ndti)
            for s in scenes
            if name in s.sub and math.isfinite(s.sub[name].red) and math.isfinite(s.sub[name].ndti)
        ]
        ax.scatter([p[0] for p in pairs], [p[1] for p in pairs], s=8, color="0.35")
        ax.set_title(f"{name} sub-reach ({len(pairs)} scenes)", fontsize=9, loc="left")
        ax.set_xlabel("median red reflectance of water pixels", fontsize=8)
        ax.tick_params(labelsize=8)
    axes[0].set_ylabel("NDTI (relative)", fontsize=8)
    fig.suptitle(f"{run.site.id}: does NDTI keep rising with red reflectance?", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def insitu_figure(outputs: ValidationOutputs, path: Path) -> bool:
    """NDTI of matched scenes against in-situ samples and river levels.

    Args:
        outputs: The run's outputs.
        path: The PNG file.

    Returns:
        False when nothing was matched.
    """
    pairs = [r for r in outputs.tables.get("insitu_pairs", []) if r.get("set") != "primary"]
    levels = outputs.tables.get("river_level", [])
    panels = [(n, rows) for n, rows in (("samples", pairs), ("levels", levels)) if rows]
    if not panels:
        return False
    fig, axes = plt.subplots(1, len(panels), figsize=(4.5 * len(panels), 3.4), squeeze=False)
    for ax, (name, rows) in zip(axes[0], panels, strict=True):
        key, x_column, x_label = (
            ("variable", "value", "in-situ sample value (log scale)")
            if name == "samples"
            else ("station", "level_percentile", "river level percentile at acquisition")
        )
        for group in sorted({str(r[key]) for r in rows}):
            chosen = [r for r in rows if str(r[key]) == group]
            unit = f", {chosen[0]['unit']}" if name == "samples" else ""
            ax.scatter(
                [float(str(r[x_column])) for r in chosen],
                [float(str(r["ndti_reach"])) for r in chosen],
                s=12,
                label=f"{group}{unit} (n = {len(chosen)})",
            )
        if name == "samples":
            ax.set_xscale("log")
        ax.set_xlabel(x_label, fontsize=8)
        ax.set_ylabel("NDTI, reach mean (relative)", fontsize=8)
        ax.tick_params(labelsize=8)
        ax.legend(fontsize=7, frameon=False)
    fig.suptitle("Target: NDTI against in-situ data (matching rules in method.md)", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def demo_figure(outputs: ValidationOutputs, path: Path) -> bool:
    """The real downstream series with the synthetic demo event drawn as a separate layer.

    Args:
        outputs: The run's outputs.
        path: The PNG file.

    Returns:
        False without a demo event.
    """
    demo = outputs.demo
    run = outputs.runs["target"]
    if demo is None or not run.records:
        return False
    limit = outputs.cfg.variant("D0").swir16_max
    usable = [r for r in run.records if r.usable[limit]]
    values = [r.values[limit]["downstream"] for r in usable]
    fig, ax = plt.subplots(figsize=(9, 3.2))
    days = np.array([r.day for r in usable], dtype="datetime64[D]")
    ax.plot(days, values, "-", color="0.75", lw=0.8)
    ax.scatter(days, values, s=8, color="0.45", label="real scenes")
    ax.scatter(
        np.array([demo.day], dtype="datetime64[D]"),
        [demo.real_downstream + demo.step],
        s=60,
        marker="D",
        facecolors="none",
        edgecolors="tab:purple",
        lw=1.5,
        label=f"SYNTHETIC test event (+{demo.step:g} NDTI, not observed)",
    )
    ax.set_ylabel("downstream NDTI (relative)", fontsize=8)
    ax.tick_params(labelsize=8)
    handles, labels = ax.get_legend_handles_labels()
    fig.legend(handles, labels, fontsize=7, loc="lower center", ncols=2, frameon=False)
    ax.set_title(f"{run.site.id}: {demo.label}", fontsize=9, loc="left")
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(path, dpi=100)
    plt.close(fig)
    return True


def _met(flag: bool | None) -> str:
    return "n/a" if flag is None else ("met" if flag else "not met")


def _quietness_lines(outputs: ValidationOutputs) -> list[str]:
    q = outputs.quietness
    if q is None:
        return ["Smoke run (stage 1 only): no NDTI was computed and there is no reading."]
    cfg = outputs.cfg.quietness
    assert cfg is not None
    lines = [
        f"**Mechanical reading: {'quiet' if q.quiet else 'not quiet'}.**",
        "",
        f"- D0 share {q.k}/{q.n} = {q.k / q.n if q.n else math.nan:.4f}, Wilson 95 % "
        f"[{q.low:.4f}, {q.high:.4f}] (upper bound allowed: {cfg.max_upper_bound:g}).",
        f"- Largest variant share: {q.worst_variant} {q.worst_share:.4f} "
        f"(allowed: {cfg.max_variant_share:g}).",
        f"- Control D0 share {q.control_k}/{q.control_n}, Wilson 95 % "
        f"[{q.control_low:.4f}, {q.control_high:.4f}]: the target is {q.comparison}.",
    ]
    if q.reasons:
        lines.append(f"- Reasons: {'; '.join(q.reasons)}.")
    return lines


def _verdict_lines(outputs: ValidationOutputs) -> list[str]:
    if outputs.cfg.kind == "baseline":
        return _quietness_lines(outputs)
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
        f"# {outputs.cfg.title}: generated results",
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
        "## Quietness" if outputs.cfg.kind == "baseline" else "## Verdict",
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
    if outputs.cfg.kind == "baseline":
        shown = {
            **t,
            "injection_all": [
                r for r in t.get("injection", []) if r["scale"] == "ndti" and r["stratum"] == "all"
            ],
        }
        for name, title, columns in BASELINE_TABLES:
            if shown.get(name):
                parts += [f"## {title}", "", markdown_table(shown[name], columns), ""]
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
        if cfg.kind == "baseline" and cfg.injection is not None:
            figures = results / "figures"
            made = {
                "detection_curve.png": detection_figure(
                    outputs.injections,
                    cfg.injection.detection_rate,
                    figures / "detection_curve.png",
                ),
                "ndti_vs_red.png": saturation_figure(outputs, figures / "ndti_vs_red.png"),
                "ndti_vs_insitu.png": insitu_figure(outputs, figures / "ndti_vs_insitu.png"),
                "demo_event_synthetic.png": demo_figure(
                    outputs, figures / "demo_event_synthetic.png"
                ),
            }
            written += [figures / name for name, ok in made.items() if ok]
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
