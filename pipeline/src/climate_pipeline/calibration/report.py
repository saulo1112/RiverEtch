"""Outputs of the calibration validation, the MANIFEST and its verification.

Every CSV, JSON and Markdown output is deterministic (no times, sorted keys, rounded floats), so
a recomputation from the committed snapshots must match the MANIFEST byte for byte, on any
machine. Figures are hashed too but PNG bytes vary across machines, so verification skips them
("same-machine"). Run times and library versions live in ``run.json``, outside the MANIFEST.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import shutil
import tempfile
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from climate_pipeline.calibration.config import CalibrationConfig
from climate_pipeline.calibration.fetching import CalibrationPaths
from climate_pipeline.calibration.matchups import CANDIDATES
from climate_pipeline.calibration.run import Results, analyse
from climate_pipeline.calibration.sources import ACOLITE_COMMIT
from climate_pipeline.screening.report import markdown_table

VERIFIED = (".csv", ".json", ".md")
NOTE = (
    "Indices and band ratios are relative until a calibration passes. No output states that "
    "any actor caused anything; 'unexplained' never means human pressure."
)


def git_blob(path: Path) -> str:
    """The git blob hash of a file (as ``git hash-object`` prints it for LF text).

    Args:
        path: The file.

    Returns:
        Hex SHA-1, or ``missing``.
    """
    if not path.exists():
        return "missing"
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _cell(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return "" if math.isnan(value) else repr(round(value, 6))
    if isinstance(value, date):
        return value.isoformat()
    return "" if value is None else str(value)


def write_table(rows: Sequence[Mapping[str, object]], path: Path) -> None:
    """CSV with LF line ends, columns in first-seen order.

    Args:
        rows: Rows.
        path: File.
    """
    columns: list[str] = []
    for row in rows:
        columns += [k for k in row if k not in columns]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns or ["none"])
        for row in rows:
            writer.writerow([_cell(row.get(c)) for c in columns])


def _json(data: object, path: Path) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False,
                               default=str) + "\n", encoding="utf-8", newline="\n")  # fmt: skip


def _figure(fig: Any, path: Path) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=90, metadata={"Software": None})
    plt.close(fig)


def stage1_figures(results: Results, cfg: CalibrationConfig, folder: Path) -> list[Path]:
    """Per target: each candidate against the target on the primary pairs (log y).

    Args:
        results: Results.
        cfg: Settings.
        folder: Figures folder.

    Returns:
        Files written.
    """
    out = []
    pairs = results.tables.get("pairs", [])
    for t in cfg.targets:
        rows = [r for r in pairs if r["target"] == t.id and r["split"] in ("training", "holdout")]
        if not rows:
            continue
        fig, axes = plt.subplots(3, 3, figsize=(10, 9))
        for ax, c in zip(axes.flat, CANDIDATES, strict=True):
            for split, color in (("training", "0.3"), ("holdout", "tab:orange")):
                sel = [r for r in rows if r["split"] == split and math.isfinite(float(r[c]))]
                ax.scatter([float(r[c]) for r in sel], [float(r["value"]) for r in sel], s=10,
                           color=color, label=split)  # fmt: skip
            ax.set_yscale("log")
            ax.set_title(c, fontsize=9, loc="left")
            ax.tick_params(labelsize=7)
        axes.flat[0].legend(fontsize=7, frameon=False)
        fig.suptitle(f"{t.id} ({t.unit}) against each candidate, pairs at the primary window",
                     fontsize=10)  # fmt: skip
        path = folder / f"stage1_{t.id}.png"
        _figure(fig, path)
        out.append(path)
    return out


def other_figures(results: Results, folder: Path) -> list[Path]:
    """The curvature check and water extent against flow.

    Args:
        results: Results.
        folder: Figures folder.

    Returns:
        Files written.
    """
    out = []
    pts = results.plots.get("curvature", [])
    if pts:
        fig, ax = plt.subplots(figsize=(5, 4))
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=8, color="0.3")
        ax.set_xlabel("B04 (red) window median", fontsize=8)
        ax.set_ylabel("B8A (NIR) window median", fontsize=8)
        ax.set_title("Reach stations: does B8A keep rising where B04 flattens?", fontsize=9)
        path = folder / "curvature.png"
        _figure(fig, path)
        out.append(path)
    flows = results.plots.get("5b", {})
    if flows:
        fig, axes = plt.subplots(1, len(flows), figsize=(4 * len(flows), 3.6), squeeze=False)
        for ax, (sid, pairs) in zip(axes[0], sorted(flows.items()), strict=True):
            ax.scatter([p[1] for p in pairs], [p[0] for p in pairs], s=8, color="0.3")
            ax.set_title(f"station {sid}", fontsize=9, loc="left")
            ax.set_xlabel("discharge or level (same day)", fontsize=8)
            ax.set_ylabel("water extent, km2 (2 km disk)", fontsize=8)
            ax.tick_params(labelsize=7)
        path = folder / "extent_flow.png"
        _figure(fig, path)
        out.append(path)
    return out


def _incomplete(paths: CalibrationPaths, cfg: CalibrationConfig) -> list[str]:
    base = paths.at(cfg.outputs.inputs)
    out = []
    manifest = base / "fetch-manifest.csv"
    if manifest.exists():
        with manifest.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                if row["note"].startswith("failed"):
                    out.append(f"not fetched: {row['url']} ({row['note']})")
    else:
        out.append("no value snapshots yet: every stage is incomplete")
    for name in ("imagery/read-errors.csv", "stations/read-errors.csv"):
        path = base / name
        if path.exists():
            n = max(0, len(path.read_text(encoding="utf-8").splitlines()) - 1)
            if n:
                out.append(f"{n} imagery read errors in {name}: rerun before accepting")
    if not (base / "imagery" / "acolite-windows.csv").exists():
        out.append("Stage 2c (ACOLITE) not run")
    return out


def render(results: Results, cfg: CalibrationConfig, paths: CalibrationPaths,
           files: Sequence[str]) -> str:  # fmt: skip
    """The generated results page.

    Args:
        results: Results.
        cfg: Settings.
        paths: Paths.
        files: Files written next to it.

    Returns:
        Markdown.
    """
    t = results.tables
    s = results.summary
    parts = [
        f"# {cfg.title}: generated results",
        "",
        "Generated by `climate-pipeline calibration run` from the committed snapshots; do not "
        "edit by hand. Preregistration: "
        "[calibration-preregistration.md](../../calibration-preregistration.md).",
        "",
        f"> {NOTE}",
        "",
        "## Incomplete stages",
        "",
        *([f"- {line}" for line in _incomplete(paths, cfg)] or ["- none"]),
        "",
        "## Summary",
        "",
        f"- Maturity reached: **{s.get('maturity')}**",
        f"- Stage 1: {s.get('stage1')}",
        f"- Stage 3: {s.get('stage3')}",
        f"- Stage 5a: {s.get('stage5a')}",
        f"- Stage 5b: {s.get('stage5b')}",
        f"- Stations selected: {s.get('stations')}; samples after replicates: {s.get('samples')}",
        "",
    ]
    for name, title, columns in (
        ("pair_counts", "Pairs", ["target", "pairs_primary", "fittable", "training", "holdout",
                                  "cut_date", "stations"]),
        ("stage1", "Stage 1: band diagnostic (training pairs)",
         ["target", "candidate", "n", "stations", "rho", "ci_low", "ci_high", "rho_needed",
          "status"]),
        ("stage3_calibration", "Stage 3: calibration",
         ["target", "status", "model", "training", "holdout", "loo_mdsa", "holdout_mdsa",
          "loo_sspb", "holdout_sspb", "reasons"]),
        ("stage4_transfer", "Stage 4: published models (report-only)",
         ["target", "model", "n", "mdsa", "sspb", "mape", "note"]),
        ("stage2a_homogeneity", "Stage 2a: processing-baseline homogeneity (report-only)",
         ["candidate", "families", "h", "p", "shifts_sigma", "shift_reported"]),
        ("curvature", "Curvature check at the reach's stations (report-only)",
         ["part", "scenes", "b04_min", "b04_max", "slope_b8a_on_b04", "spearman"]),
        ("stage5a_climate", "Stage 5a: season and rain, per signal",
         ["signal", "n", "skill", "skill_min", "status", "skill_chirps", "skill_with_discharge",
          "ar1"]),
        ("stage5b_extent_flow", "Stage 5b: water extent against discharge or level",
         ["station", "series", "n", "rho", "low", "high", "status"]),
        ("stage5c_enso", "Stage 5c: ENSO phases (report-only)",
         ["entity", "n", "diff_la_nina_minus_el_nino", "p", "alternative", "n_la_nina",
          "n_el_nino", "false_alarms", "neutral_years", "note"]),
    ):  # fmt: skip
        if t.get(name):
            parts += [f"## {title}", "", markdown_table(t[name], columns), ""]
    parts += ["## Files", "", *[f"- [{f}]({f})" for f in files], ""]
    return "\n".join(parts)


def write_outputs(
    results: Results, cfg: CalibrationConfig, paths: CalibrationPaths, out: Path
) -> list[Path]:
    """Write every output and the MANIFEST (the folder starts empty).

    Args:
        results: Results.
        cfg: Settings.
        paths: Paths.
        out: Results folder.

    Returns:
        The files written (MANIFEST last).
    """
    shutil.rmtree(out, ignore_errors=True)
    (out / "figures").mkdir(parents=True)
    (out / "models").mkdir()
    written: list[Path] = []
    for name, rows in sorted(results.tables.items()):
        path = out / f"{name}.csv"
        write_table(rows, path)
        written.append(path)
    for card in results.cards:
        path = out / "models" / f"{card['target']}.json"
        _json(card, path)
        written.append(path)
    records = results.records
    sample = out / Path(cfg.outputs.observations_sample).name
    _json(records, sample)
    if sample.stat().st_size > cfg.outputs.max_committed_bytes:
        flagged = [r for r in records if r["verdict"]["anomalous"]]
        _json((flagged + [r for r in records if not r["verdict"]["anomalous"]])[:60], sample)
    written.append(sample)
    _json(results.summary, out / "summary.json")
    written.append(out / "summary.json")
    inputs = paths.at(cfg.outputs.inputs)
    provenance = {
        "preregistration_blob": git_blob(paths.at(cfg.preregistration)),
        "config_sha256": hashlib.sha256(paths.config.read_bytes()).hexdigest(),
        "fetch_manifest_sha256": {
            name: hashlib.sha256((inputs / name).read_bytes()).hexdigest()
            for name in ("fetch-manifest-stations.csv", "fetch-manifest.csv")
            if (inputs / name).exists()
        },
        "acolite_commit": ACOLITE_COMMIT,
    }
    _json(provenance, out / "provenance.json")
    written.append(out / "provenance.json")
    written += stage1_figures(results, cfg, out / "figures")
    written += other_figures(results, out / "figures")
    names = [p.relative_to(out).as_posix() for p in written]
    md = out / "results.md"
    md.write_text(render(results, cfg, paths, names), encoding="utf-8", newline="\n")
    written.append(md)
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(out).as_posix()}"
        for p in sorted(written, key=lambda p: p.relative_to(out).as_posix())
    ]
    manifest = out / "MANIFEST"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    written.append(manifest)
    return written


def read_manifest(path: Path) -> dict[str, str]:
    """``path -> sha256`` from a MANIFEST (``sha256sum`` format).

    Args:
        path: The MANIFEST.

    Returns:
        The entries.
    """
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        if name:
            out[name] = digest
    return out


def verify(cfg: CalibrationConfig, paths: CalibrationPaths, out: Path | None = None) -> list[str]:
    """Recompute from the snapshots and compare CSV, JSON and Markdown with the MANIFEST.

    Args:
        cfg: Settings.
        paths: Paths.
        out: Where to recompute (default: a temporary folder).

    Returns:
        Mismatches (empty when every verified file matches).
    """
    committed = paths.at(cfg.outputs.results) / "MANIFEST"
    if not committed.exists():
        return [f"no MANIFEST at {committed}"]
    expected = read_manifest(committed)
    with tempfile.TemporaryDirectory() as tmp:
        target = out or Path(tmp) / "results"
        write_outputs(analyse(cfg, paths), cfg, paths, target)
        actual = read_manifest(target / "MANIFEST")
    problems = []
    for name in sorted(set(expected) | set(actual)):
        if not name.endswith(VERIFIED):
            continue
        if expected.get(name) != actual.get(name):
            problems.append(f"{name}: committed {expected.get(name)} recomputed {actual.get(name)}")
    return problems
