"""The Urrá validation run: everything ``docs/urra-validation/method.md`` pre-registered.

Stage 1 runs on the target, the control and the reference with the geometry frozen to the
screening's period; stage 2 measures NDTI at the two pixel glint limits the variants need; the
variants, criteria and report-only analyses follow. Nothing here tunes a threshold: every value
comes from ``pipeline/urra-validation.yaml`` or, unchanged, from ``pipeline/screening.yaml``.
"""

from __future__ import annotations

import csv
import logging
import math
import re
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import numpy as np

from climate_pipeline import __version__
from climate_pipeline.provenance import blob, head, last_commit, library_versions
from climate_pipeline.screening.config import (
    ScreeningConfig,
    SiteConfig,
    config_hash,
    load_screening_config,
    load_sites,
)
from climate_pipeline.screening.events import (
    CatalogEvent,
    chance_rate,
    event_window,
    is_scored,
    load_events,
    window_days,
)
from climate_pipeline.screening.events import (
    evaluate as evaluate_event,
)
from climate_pipeline.screening.rain import OpenMeteoClient
from climate_pipeline.screening.rio import AcquisitionReader, sample_points
from climate_pipeline.screening.stac import Acquisition, SceneSource, evidence_hash, make_source
from climate_pipeline.screening.stage1 import RAIN_LEAD_DAYS, Stage1Result, run_stage1
from climate_pipeline.screening.stage2 import SIGNALS, Stage2Result, run_stage2_variants
from climate_pipeline.validation import catchment as rainmod
from climate_pipeline.validation.case import (
    CaseFile,
    Context,
    ContextSource,
    Manifest,
    Permit,
    Rain,
    Ui,
    ValidationSummary,
    build_reach,
    case_events,
    case_scene,
    reach_label,
)
from climate_pipeline.validation.config import ValidationConfig, load_validation_config
from climate_pipeline.validation.grid import read_grid
from climate_pipeline.validation.placebo import PlaceboResult, run_placebo
from climate_pipeline.validation.seasonality import (
    january_february_rows,
    seasonal_rows,
    signal_split,
)
from climate_pipeline.validation.variants import (
    Persistence,
    SceneRecord,
    criterion_a,
    episodes,
    share,
)
from climate_pipeline.validation.verdict import Verdict, binomial_tail, decide

log = logging.getLogger(__name__)

ROLES = ("target", "control", "reference")
GEOMETRY_FIELDS = (
    "mask_source",
    "water_frequency_threshold",
    "reach_length_km",
    "separation_km",
    "anchor_shift_up_m",
    "anchor_shift_down_m",
    "center_shift_m",
    "width_px_10m",
    "centerline_mid_lon",
    "centerline_mid_lat",
)
CONTEXT_SOURCE_IDS = (
    "anla-pis-urra",
    "anla-res-0838-1999",
    "anla-res-0459-2022",
    "anla-acta-269-2025",
    "urra-gestion-tecnica",
    "anla-news-sobrepaso-2026",
)

ChirpsReader = Callable[[str, list[tuple[float, float]]], list[float]]


# ----------------------------------------------------------------------------------------------
# Paths and per-site state
# ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationPaths:
    """Where the validation reads and writes, from the repository root."""

    root: Path
    config: Path
    out: Path

    def at(self, relative: str) -> Path:
        """A path from the repository root.

        Args:
            relative: Path relative to the root, as the config writes it.

        Returns:
            The absolute path.
        """
        return self.root / relative


@dataclass
class SiteRun:
    """Everything the validation learned about one reach."""

    role: str
    site: SiteConfig
    stage1: Stage1Result | None
    error: str = ""
    rainy: set[int] = field(default_factory=set)
    stage2: dict[float, Stage2Result] = field(default_factory=dict)
    records: list[SceneRecord] = field(default_factory=list)
    point_mm: list[float] = field(default_factory=list)
    point: list[bool | None] = field(default_factory=list)
    catchment: list[bool | None] | None = None
    catchment_values: dict[tuple[str, int], list[float]] = field(default_factory=dict)
    union: list[str] = field(default_factory=list)
    persistence: Persistence | None = None


@dataclass
class ValidationOutputs:
    """Everything a run produced, ready to be written."""

    cfg: ValidationConfig
    screening: ScreeningConfig
    manifest: dict[str, object]
    runs: dict[str, SiteRun]
    stage1_only: bool
    tables: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    verdict: Verdict | None = None
    placebo: PlaceboResult | None = None
    case: CaseFile | None = None
    notes: list[str] = field(default_factory=list)


# ----------------------------------------------------------------------------------------------
# Checks on the inputs
# ----------------------------------------------------------------------------------------------


def check_d0(cfg: ValidationConfig, screening: ScreeningConfig) -> None:
    """D0 must be exactly the screening's rule.

    Args:
        cfg: Validation settings.
        screening: Screening settings.

    Raises:
        ValueError: If D0 differs from the screening thresholds.
    """
    d0 = cfg.variant("D0")
    s2 = screening.stage2
    expected = (
        "season-then-all",
        s2.min_season_n,
        s2.min_baseline_n,
        s2.anomaly_z,
        s2.swir16_max,
        None,
    )
    actual = (
        d0.baseline,
        d0.season_min,
        d0.all_min,
        d0.anomaly_z,
        d0.swir16_max,
        d0.max_glint_share,
    )
    if actual != expected:
        raise ValueError(f"D0 {actual} is not the screening rule {expected}")


def glint_limits(cfg: ValidationConfig) -> tuple[float, ...]:
    """Every pixel glint limit the variants use, the screening's first.

    Args:
        cfg: Validation settings.

    Returns:
        The limits.
    """
    d0 = cfg.variant("D0").swir16_max
    return (d0, *sorted({v.swir16_max for v in cfg.variants} - {d0}))


# ----------------------------------------------------------------------------------------------
# Scene records and rain
# ----------------------------------------------------------------------------------------------


def build_records(stage2: dict[float, Stage2Result], default_limit: float) -> list[SceneRecord]:
    """One record per measured acquisition, with its values at every glint limit.

    Args:
        stage2: Stage-2 results by glint limit (same acquisitions, same order).
        default_limit: The screening's limit (its glint shares are kept).

    Returns:
        Records in time order.
    """
    base = stage2[default_limit].scenes
    records = []
    for k, scene in enumerate(base):
        shares = [s.glint_share for s in scene.sub.values() if math.isfinite(s.glint_share)]
        records.append(
            SceneRecord(
                key=scene.key,
                day=scene.datetime.date(),
                values={limit: result.scenes[k].values for limit, result in stage2.items()},
                usable={limit: result.scenes[k].usable for limit, result in stage2.items()},
                glint_share=max(shares) if shares else math.nan,
            )
        )
    return records


def rain_flags(run: SiteRun, screening: ScreeningConfig) -> None:
    """The screening's point rule for every measured scene (unknown kept as None).

    Args:
        run: The site run (its stage-1 rain series and stage-2 scenes are used).
        screening: Screening settings.
    """
    assert run.stage1 is not None
    scenes = run.stage2[min(run.stage2)].scenes if run.stage2 else []
    moments = [s.datetime for s in scenes]
    values = rainmod.point_values(run.stage1.rain, moments, screening.rain.coincident_window_h)
    run.point_mm = [float(v) for v in values]
    run.point = rainmod.point_flags(values, screening.rain.coincident_mm)


def item_meta(acquisition: Acquisition) -> tuple[list[str], list[str], str]:
    """An acquisition's item ids, processing baselines and baseline family.

    Args:
        acquisition: The pass.

    Returns:
        Item ids, baselines (``05.00``) and families (``05.xx``, joined by ``/``).
    """
    ids = [s.item_id for s in acquisition.scenes]
    baselines = [
        f"{s.processing_baseline:05.2f}" if s.processing_baseline is not None else "unknown"
        for s in acquisition.scenes
    ]
    families = sorted({b[:2] + ".xx" if b != "unknown" else b for b in baselines})
    return ids, baselines, "/".join(families)


# ----------------------------------------------------------------------------------------------
# Reproduction checks
# ----------------------------------------------------------------------------------------------


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _same(a: object, b: str) -> bool:
    text = "" if a is None else str(a)
    try:
        x, y = float(text), float(b)
    except ValueError:
        return text.strip().lower() == b.strip().lower()
    return (math.isnan(x) and math.isnan(y)) or abs(x - y) < 1e-9


def reproduction_stage1(
    runs: dict[str, SiteRun], cfg: ValidationConfig, reference: Path
) -> list[dict[str, object]]:
    """Item-id hashes and geometry fields of 2022-2025 against the screening's.

    Args:
        runs: Site runs by role.
        cfg: Validation settings.
        reference: The screening results folder that is reproduced.

    Returns:
        One row per check.
    """
    rows: list[dict[str, object]] = []
    summary = {r["site_id"]: r for r in _read_csv(reference / "stage1_summary.csv")}
    window = cfg.geometry_period
    for run in runs.values():
        site = run.site.id
        if run.stage1 is None:
            rows.append(
                {
                    "site_id": site,
                    "check": "stage 1",
                    "expected": "",
                    "actual": run.error,
                    "pass": False,
                }
            )
            continue
        inside = [a for a in run.stage1.acquisitions if window.contains(a.datetime.date())]
        actual = evidence_hash(inside)
        expected = cfg.screening_reference.evidence_sha256.get(site, "")
        rows.append(
            {
                "site_id": site,
                "check": "item-id sha256 2022-2025",
                "expected": expected,
                "actual": actual,
                "pass": actual == expected,
            }
        )
        for name in GEOMETRY_FIELDS:
            want = summary.get(site, {}).get(name, "")
            got = run.stage1.summary.get(name, "")
            rows.append(
                {
                    "site_id": site,
                    "check": name,
                    "expected": want,
                    "actual": got,
                    "pass": _same(got, want),
                }
            )
    return rows


def reproduction_ndti(
    runs: dict[str, SiteRun], cfg: ValidationConfig, reference: Path, limit: float
) -> list[dict[str, object]]:
    """Per-scene NDTI of 2022-2025 against the screening's stage-2 table.

    Args:
        runs: Site runs by role.
        cfg: Validation settings.
        reference: The screening results folder.
        limit: The screening's glint limit.

    Returns:
        One row per site with the scenes compared and the mismatches.
    """
    digits = cfg.screening_reference.ndti_decimals
    screening = {
        (r["site_id"], r["acquisition"]): r for r in _read_csv(reference / "stage2_scenes.csv")
    }
    rows: list[dict[str, object]] = []
    for run in runs.values():
        if limit not in run.stage2:
            continue
        scenes = [
            s for s in run.stage2[limit].scenes if cfg.geometry_period.contains(s.datetime.date())
        ]
        keys = {s.key for s in scenes}
        expected_keys = {k for (site, k) in screening if site == run.site.id}
        mismatches = []
        for scene in scenes:
            ref = screening.get((run.site.id, scene.key))
            if ref is None:
                mismatches.append(f"{scene.key}: not in the screening")
                continue
            if bool(scene.exclusion) != bool(ref["excluded"]):
                mismatches.append(f"{scene.key}: exclusion differs")
                continue
            for name, column in (
                ("upstream", "upstream_ndti"),
                ("downstream", "downstream_ndti"),
                ("delta", "delta_ndti"),
            ):
                mine = round(scene.values[name], digits)
                theirs = float(ref[column]) if ref.get(column, "") != "" else math.nan
                if not ((math.isnan(mine) and math.isnan(theirs)) or mine == round(theirs, digits)):
                    mismatches.append(f"{scene.key}: {name} {mine} vs {theirs}")
        missing = sorted(expected_keys - keys)
        mismatches += [f"{k}: missing here" for k in missing]
        rows.append(
            {
                "site_id": run.site.id,
                "scenes_compared": len(scenes),
                "scenes_in_screening": len(expected_keys),
                "mismatches": len(mismatches),
                "details": "; ".join(mismatches[:20]),
                "pass": not mismatches,
            }
        )
    return rows


# ----------------------------------------------------------------------------------------------
# Report-only tables
# ----------------------------------------------------------------------------------------------


def stage1_counts(run: SiteRun, limit: float) -> list[dict[str, object]]:
    """Acquisitions by year, sensor, processing family and scaling status.

    Args:
        run: The site run.
        limit: The screening's glint limit (usable scenes are counted at it).

    Returns:
        Rows with acquisitions, observable and usable counts.
    """
    if run.stage1 is None:
        return []
    observable = {s.key for s in run.stage1.scenes if s.observable}
    usable = {s.key for s in run.stage2[limit].scenes if s.usable} if limit in run.stage2 else set()
    counter: Counter[tuple[int, str, str, str]] = Counter()
    seen: Counter[tuple[int, str, str, str]] = Counter()
    used: Counter[tuple[int, str, str, str]] = Counter()
    for acq in run.stage1.acquisitions:
        _, _, family = item_meta(acq)
        scaling = "/".join(sorted({s.scaling_status() for s in acq.scenes}))
        key = (acq.datetime.year, acq.platform, family, scaling)
        counter[key] += 1
        seen[key] += acq.key in observable
        used[key] += acq.key in usable
    return [
        {
            "site_id": run.site.id,
            "year": y,
            "platform": p,
            "baseline_family": f,
            "scaling": s,
            "acquisitions": n,
            "observable": seen[(y, p, f, s)],
            "usable": used[(y, p, f, s)],
        }
        for (y, p, f, s), n in sorted(counter.items())
    ]


def read_error_rows(errors: Sequence[str]) -> list[dict[str, object]]:
    """Failed reads by year of the item and asset.

    Args:
        errors: The reader's error strings (``item_id asset: message``).

    Returns:
        Rows with counts.
    """
    counter: Counter[tuple[str, str]] = Counter()
    for text in errors:
        match = re.match(r"(\S+) (\S+):", text)
        item, asset = (match.group(1), match.group(2)) if match else ("?", "?")
        year = re.search(r"_(\d{4})\d{4}_", item)
        counter[(year.group(1) if year else "?", asset)] += 1
    return [{"year": y, "asset": a, "failed_reads": n} for (y, a), n in sorted(counter.items())]


def b11_rows(run: SiteRun, limit: float) -> list[dict[str, object]]:
    """Scenes excluded by the B11 water check, by year and cause.

    Args:
        run: The site run.
        limit: The screening's glint limit.

    Returns:
        Rows with counts.
    """
    counter: Counter[tuple[int, str]] = Counter()
    for scene in run.stage2.get(limit, Stage2Result(run.site, [])).scenes:
        if "B11 water" in scene.exclusion:
            cause = (
                "offset applied twice?"
                if "offset applied twice" in scene.exclusion
                else "glint or a missing offset"
            )
            counter[(scene.datetime.year, cause)] += 1
    return [
        {"site_id": run.site.id, "year": y, "cause": c, "scenes": n}
        for (y, c), n in sorted(counter.items())
    ]


def processing_rows(run: SiteRun, limit: float) -> list[dict[str, object]]:
    """Median NDTI per processing-baseline family and sub-reach (usable scenes).

    Args:
        run: The site run.
        limit: The screening's glint limit.

    Returns:
        Rows.
    """
    if run.stage1 is None or limit not in run.stage2:
        return []
    family = {a.key: item_meta(a)[2] for a in run.stage1.acquisitions}
    groups: dict[str, list[dict[str, float]]] = {}
    for scene in run.stage2[limit].scenes:
        if scene.usable:
            groups.setdefault(family.get(scene.key, "?"), []).append(scene.values)
    rows: list[dict[str, object]] = []
    for name, values in sorted(groups.items()):
        row: dict[str, object] = {
            "site_id": run.site.id,
            "baseline_family": name,
            "usable": len(values),
        }
        for signal in SIGNALS:
            finite = [v[signal] for v in values if math.isfinite(v[signal])]
            row[f"median_{signal}"] = round(float(np.median(finite)), 4) if finite else math.nan
        rows.append(row)
    return rows


def variant_rows(run: SiteRun, cfg: ValidationConfig) -> list[dict[str, object]]:
    """Per variant: usable, scored and anomalous scenes, share and agreement with D0.

    Args:
        run: The site run.
        cfg: Validation settings.

    Returns:
        Rows.
    """
    if run.persistence is None:
        return []
    d0 = run.persistence.evaluations["D0"]
    rows = []
    for variant in cfg.variants:
        scenes = run.persistence.evaluations[variant.id]
        anomalous, scored = share(scenes)
        both = sum(1 for a, b in zip(d0, scenes, strict=True) if a.anomalous and b.anomalous)
        only_d0 = sum(1 for a, b in zip(d0, scenes, strict=True) if a.anomalous and not b.anomalous)
        only_v = sum(1 for a, b in zip(d0, scenes, strict=True) if b.anomalous and not a.anomalous)
        statuses = Counter(s.status for s in scenes)
        rows.append(
            {
                "site_id": run.site.id,
                "variant": variant.id,
                "distinct": variant.distinct,
                "scenes": len(scenes),
                "scored": scored,
                "insufficient": statuses["insufficient"],
                "excluded": statuses["excluded"],
                "removed": statuses["removed"],
                "anomalous": anomalous,
                "share": round(anomalous / scored, 4) if scored else math.nan,
                "anomalous_in_both_with_d0": both,
                "only_d0": only_d0,
                "only_variant": only_v,
            }
        )
    return rows


def scene_rows(run: SiteRun, cfg: ValidationConfig, limit: float) -> list[dict[str, object]]:
    """One row per measured scene with every variant's z and flag and the rain flags.

    Args:
        run: The site run.
        cfg: Validation settings.
        limit: The screening's glint limit.

    Returns:
        Rows.
    """
    if run.persistence is None:
        return []
    rows = []
    scenes = run.stage2[limit].scenes
    for k, (record, scene) in enumerate(zip(run.records, scenes, strict=True)):
        row: dict[str, object] = {
            "site_id": run.site.id,
            "acquisition": record.key,
            "date": record.day.isoformat(),
            "period": "hold-out" if cfg.holdout.contains(record.day) else "screening",
            "excluded": scene.exclusion,
        }
        for signal in SIGNALS:
            row[f"{signal}_ndti"] = round(record.values[limit][signal], 4)
        row["glint_share_max"] = round(record.glint_share, 3)
        row["rain_point_72h_mm"] = round(run.point_mm[k], 1)
        row["rain_point"] = _flag(run.point[k])
        row["rain_catchment"] = _flag(run.catchment[k]) if run.catchment is not None else "not used"
        for (stat, hours), values in sorted(run.catchment_values.items()):
            row[f"catchment_{stat}_{hours}h_mm"] = round(values[k], 1)
        row["rain_union"] = run.union[k]
        for variant in cfg.variants:
            v = run.persistence.evaluations[variant.id][k]
            row[f"{variant.id}_status"] = v.status
            for signal in SIGNALS:
                row[f"{variant.id}_z_{signal}"] = round(v.z.get(signal, math.nan), 2)
            row[f"{variant.id}_anomalous"] = v.anomalous
        row["persistence"] = run.persistence.counts[k]
        row["persistence_distinct"] = run.persistence.distinct_counts[k]
        rows.append(row)
    return rows


def _flag(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def event_rows(
    run: SiteRun, events: list[CatalogEvent], cfg: ValidationConfig, screening: ScreeningConfig
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Event outcomes (D0 and persistent scenes) and chance rates over the whole period.

    Args:
        run: The target run.
        events: The target's catalog events.
        cfg: Validation settings.
        screening: Screening settings (event windows are the screening's).

    Returns:
        Outcome rows and chance-rate rows.
    """
    assert run.persistence is not None
    ev = screening.events.model_copy(
        update={
            "window_before_days": cfg.events.window_before_days,
            "window_after_days": cfg.events.window_after_days,
            "scored_precisions": cfg.events.scored_precisions,
            "chance_shifts": cfg.events.chance_windows,
            "seed": cfg.events.seed,
        }
    )
    d0 = run.persistence.evaluations["D0"]
    scores: dict[date, dict[str, float]] = {}
    for record, scene in zip(run.records, d0, strict=True):
        if scene.status != "scored":
            continue
        current = scores.setdefault(record.day, {})
        for signal, z in scene.z.items():
            if math.isfinite(z) and (signal not in current or abs(z) > abs(current[signal])):
                current[signal] = z
    start, end = cfg.period.start, cfg.period.end
    scored = [e for e in events if is_scored(e, ev, start, end)]
    avoid = [event_window(e, ev) for e in events]
    persistent = [
        r.day
        for r, n in zip(run.records, run.persistence.counts, strict=True)
        if n >= cfg.criteria.persistence_min
    ]
    rows, chances = [], []
    for event in scored:
        outcome = evaluate_event(event, ev, scores, cfg.variant("D0").anomaly_z)
        first, last = event_window(event, ev)
        rate, windows = chance_rate(
            window_days(event, ev),
            scores,
            cfg.variant("D0").anomaly_z,
            start,
            end,
            avoid,
            ev.chance_shifts,
            ev.seed,
        )
        rows.append(
            {
                "event_id": event.event_id,
                "date_start": event.date_start.isoformat(),
                "date_end": event.date_end.isoformat(),
                "event_type": event.event_type,
                "status_d0": outcome.status,
                "max_abs_z": round(outcome.max_abs_z, 2)
                if outcome.max_abs_z is not None
                else math.nan,
                "signal": outcome.signal,
                "scene_days": " ".join(d.isoformat() for d in outcome.scene_days),
                "persistent_scene_in_window": any(first <= d <= last for d in persistent),
                "chance_rate": round(rate, 3) if math.isfinite(rate) else math.nan,
                "chance_windows": windows,
            }
        )
        chances.append(
            {
                "event_id": event.event_id,
                "window_days": window_days(event, ev),
                "rate": rate,
                "windows": windows,
            }
        )
    return rows, chances


def holdout_rows(run: SiteRun, cfg: ValidationConfig) -> list[dict[str, object]]:
    """The hold-out view: anomalies, persistent scenes and episodes per period.

    Args:
        run: The site run.
        cfg: Validation settings.

    Returns:
        One row per period part.
    """
    if run.persistence is None:
        return []
    rows = []
    d0 = run.persistence.evaluations["D0"]
    for label, contains in (
        ("hold-out 2018-12..2021-12", cfg.holdout.contains),
        ("screening period 2022-2025", cfg.geometry_period.contains),
        ("whole period", cfg.period.contains),
    ):
        idx = [k for k, r in enumerate(run.records) if contains(r.day)]
        scored = [k for k in idx if d0[k].scored]
        anomalous = [k for k in scored if d0[k].anomalous]
        candidates = [
            run.records[k].day for k in idx if run.records[k].day in set(run.persistence.candidates)
        ]
        rows.append(
            {
                "site_id": run.site.id,
                "part": label,
                "scenes": len(idx),
                "scored_d0": len(scored),
                "anomalous_d0": len(anomalous),
                "persistent": sum(
                    1 for k in idx if run.persistence.counts[k] >= cfg.criteria.persistence_min
                ),
                "candidates": len(candidates),
                "episodes": len(episodes(candidates, cfg.criteria.episode_gap_days)),
            }
        )
    return rows


def geometry_check_rows(run: SiteRun) -> list[dict[str, object]]:
    """Overlap of each sub-reach between the frozen geometry and the whole-period geometry.

    Args:
        run: The site run.

    Returns:
        One row per sub-reach (intersection over union of their pixels).
    """
    if run.stage1 is None or run.stage1.check_geometry is None:
        return []
    check = run.stage1.check_geometry
    if check.failed:
        return [
            {"site_id": run.site.id, "subreach": "all", "overlap": math.nan, "note": check.failed}
        ]
    other = {s.name: s.mask for s in check.subreaches}
    rows: list[dict[str, object]] = []
    for sub in run.stage1.geometry.subreaches:
        mask = other.get(sub.name)
        if mask is None:
            rows.append(
                {
                    "site_id": run.site.id,
                    "subreach": sub.name,
                    "overlap": math.nan,
                    "note": "missing",
                }
            )
            continue
        union = int((sub.mask | mask).sum())
        rows.append(
            {
                "site_id": run.site.id,
                "subreach": sub.name,
                "overlap": round(int((sub.mask & mask).sum()) / union, 3) if union else math.nan,
                "note": "",
            }
        )
    return rows


def baseline_size_rows(
    run: SiteRun, cfg: ValidationConfig, reference: Path
) -> list[dict[str, object]]:
    """Median D0 baseline-group size per signal: the screening's against this run's.

    Args:
        run: The target run.
        cfg: Validation settings.
        reference: The screening results folder.

    Returns:
        One row per signal.
    """
    if run.persistence is None:
        return []
    rainy = run.rainy
    rows = [
        r
        for r in _read_csv(reference / "stage2_scenes.csv")
        if r["site_id"] == run.site.id and not r["excluded"]
    ]
    days = [datetime.fromisoformat(r["datetime_utc"]).date() for r in rows]
    d0 = run.persistence.evaluations["D0"]
    out = []
    columns = {"upstream": "upstream_ndti", "downstream": "downstream_ndti", "delta": "delta_ndti"}
    for signal, column in columns.items():
        finite = [k for k, r in enumerate(rows) if r.get(column, "") not in ("", "nan")]
        sizes = []
        for k in finite:
            same = [
                j for j in finite if j != k and (days[j].month in rainy) == (days[k].month in rainy)
            ]
            group = rows[k].get(f"baseline_{signal}", "")
            if group == "season":
                sizes.append(len(same))
            elif group == "all":
                sizes.append(len(finite) - 1)
        mine_all = [s.size[signal] for s in d0 if s.scored and s.size.get(signal, 0)]
        mine_recent = [
            s.size[signal]
            for r, s in zip(run.records, d0, strict=True)
            if s.scored and s.size.get(signal, 0) and cfg.geometry_period.contains(r.day)
        ]
        out.append(
            {
                "signal": signal,
                "screening_median_n": float(np.median(sizes)) if sizes else math.nan,
                "validation_median_n_2022_2025": float(np.median(mine_recent))
                if mine_recent
                else math.nan,
                "validation_median_n_all": float(np.median(mine_all)) if mine_all else math.nan,
            }
        )
    return out


# ----------------------------------------------------------------------------------------------
# CHIRPS
# ----------------------------------------------------------------------------------------------


def chirps_url(template: str, day: date) -> str:
    """The CHIRPS daily COG of a day.

    Args:
        template: URL with ``{year}`` and ``{date}``.
        day: The day.

    Returns:
        The URL.
    """
    return template.format(year=day.year, date=day.strftime("%Y.%m.%d"))


# ----------------------------------------------------------------------------------------------
# The run
# ----------------------------------------------------------------------------------------------


def run_validation(
    paths: ValidationPaths,
    *,
    stage1_only: bool = False,
    workers: int = 8,
    source: SceneSource | None = None,
    rain: OpenMeteoClient | None = None,
    grid_http: httpx.Client | None = None,
    chirps_reader: ChirpsReader | None = None,
    placebo_shuffles: int | None = None,
) -> ValidationOutputs:
    """Run the pre-registered validation.

    Args:
        paths: Repository root, validation config and the cache folder.
        stage1_only: Stop after stage 1, the rain and the probes (the smoke run): no NDTI.
        workers: Parallel reads.
        source: Injected scene source (tests).
        rain: Injected Open-Meteo client for the point rule (tests).
        grid_http: Injected HTTP client for the catchment rain (tests).
        chirps_reader: Injected CHIRPS reader (tests).
        placebo_shuffles: Override of the shuffle count (tests only).

    Returns:
        The outputs (not yet written).
    """
    started = datetime.now(UTC)
    cfg = load_validation_config(paths.config)
    screening_path = paths.at(cfg.screening_config)
    base = load_screening_config(screening_path)
    screening = base.posthoc().model_copy(
        update={
            "period": base.period.model_copy(
                update={"start": cfg.period.start, "end": cfg.period.end}
            )
        }
    )
    check_d0(cfg, screening)
    events_path = paths.at(cfg.events.catalog)
    events_sha = config_hash([events_path])
    if events_sha != cfg.screening_reference.events_sha256:
        raise ValueError(f"the event catalog changed: {events_sha}")
    sites_dir = paths.at("pipeline/sites")
    roles = {
        "target": cfg.sites.target,
        "control": cfg.sites.control,
        "reference": cfg.sites.reference,
    }
    by_id = {s.id: s for s in load_sites(sites_dir, tuple(roles.values()))}
    source = source or make_source(
        screening.stac.source, screening.stac.sources, screening.stac.page_size
    )
    reader = AcquisitionReader(source, paths.out / "cache" / "bands")
    rain_cache = paths.out / "cache" / "rain"
    if rain is None:
        # Seven-year hourly requests weigh heavily against Open-Meteo's rate limits: fetch the
        # point rain first with pacing and backoff, into the cache the stage-1 client reads.
        prefetch_point_rain(
            [by_id[s] for s in roles.values()], screening.rain.url, cfg, rain_cache, grid_http
        )
        rain = OpenMeteoClient(screening.rain.url, cache_dir=rain_cache)
    limit = cfg.variant("D0").swir16_max
    window = (cfg.period.start, cfg.period.end)
    geometry = (cfg.geometry_period.start, cfg.geometry_period.end)

    runs: dict[str, SiteRun] = {}
    for role, site_id in roles.items():
        site = by_id[site_id]
        try:
            stage1 = run_stage1(
                site, screening, source, reader, rain, workers, window, geometry, True
            )
            runs[role] = SiteRun(role, site, stage1, rainy=set(cfg.rainy_months[site_id]))
        except Exception as error:  # a reach that fails is reported; the verdict says so
            log.exception("%s: stage 1 failed", site_id)
            runs[role] = SiteRun(role, site, None, error=f"{type(error).__name__}: {error}")

    outputs = ValidationOutputs(cfg, screening, {}, runs, stage1_only)
    reference = paths.at(cfg.screening_reference.results)
    outputs.tables["reproduction_stage1"] = reproduction_stage1(runs, cfg, reference)
    outputs.tables["rainy_months"] = [
        {
            "site_id": r.site.id,
            "frozen": " ".join(map(str, sorted(r.rainy))),
            "rule_over_whole_period": " ".join(map(str, r.stage1.rainy_months)) if r.stage1 else "",
        }
        for r in runs.values()
    ]

    # Catchment rain (target only) and the CHIRPS probe, also in the smoke run.
    target = runs["target"]
    cells: list[rainmod.CellSeries] = []
    limits: rainmod.Thresholds | None = None
    c = cfg.rain.catchment
    grid_points = read_grid(paths.at(c.grid_csv)) if paths.at(c.grid_csv).exists() else []
    if not grid_points:
        outputs.notes.append("catchment grid unbuildable or missing: point rule only")
    else:
        try:
            cells = rainmod.fetch_grid(
                grid_points,
                screening.rain.url,
                rainmod.rain_start(cfg.period, RAIN_LEAD_DAYS),
                cfg.period.end,
                paths.out / "cache" / "rain",
                c.request_pause_s,
                c.max_attempts,
                http=grid_http,
            )
            limits = rainmod.thresholds(
                cells, cfg.period, c.sample_hour_utc, c.windows_h, c.statistics, c.percentile
            )
        except Exception as error:  # rain is fetched; its loss makes scenes "unknown"
            log.exception("catchment rain unavailable")
            outputs.notes.append(
                f"catchment rain unavailable ({type(error).__name__}): every scene unknown"
            )
            cells = []
    outputs.tables["catchment_cells"] = [
        {"cell_lon": cell.cell_lon, "cell_lat": cell.cell_lat, "points": " ".join(cell.point_ids)}
        for cell in cells
    ]
    if limits is not None:
        outputs.tables["catchment_thresholds"] = [
            {
                "statistic": stat,
                "window_h": hours,
                "threshold_mm": round(value, 2),
                "days": limits.days[(stat, hours)],
            }
            for (stat, hours), value in sorted(limits.values.items())
        ] + [
            {
                "statistic": "any (share of days flagged)",
                "window_h": "",
                "threshold_mm": "",
                "days": round(limits.day_share_flagged, 4),
            }
        ]
    reader_chirps = chirps_reader or sample_points
    probe_url = chirps_url(cfg.chirps.cog_url_template, cfg.chirps.probe_date)
    try:
        probe = reader_chirps(
            probe_url,
            [(lon, lat) for _, lon, lat in grid_points]
            or [(target.site.center.lon, target.site.center.lat)],
        )
        chirps_ok = True
        outputs.tables["chirps_probe"] = [
            {"url": probe_url, "status": "ok", "values_mm": " ".join(f"{v:.2f}" for v in probe)}
        ]
    except Exception as error:  # report-only: a CHIRPS failure is recorded, never fatal
        chirps_ok = False
        outputs.tables["chirps_probe"] = [
            {"url": probe_url, "status": f"failed: {type(error).__name__}", "values_mm": ""}
        ]

    for run in runs.values():
        outputs.tables.setdefault("stage1_summary", []).append(
            run.stage1.summary
            if run.stage1
            else {"site_id": run.site.id, "geometry_failed": run.error}
        )
    outputs.manifest = manifest(paths, cfg, runs, started, stage1_only)
    if stage1_only:
        for run in runs.values():
            outputs.tables.setdefault("stage1_counts", []).extend(stage1_counts(run, limit))
        outputs.tables["read_errors"] = read_error_rows(reader.errors)
        outputs.manifest["read_error_count"] = len(reader.errors)
        return outputs

    # Stage 2 at every glint limit, rain flags, variants.
    limits_needed = glint_limits(cfg)
    for run in runs.values():
        if run.stage1 is None or run.stage1.geometry.failed:
            run.error = run.error or f"geometry: {run.stage1.geometry.failed if run.stage1 else ''}"
            continue
        run.stage2 = run_stage2_variants(run.stage1, reader, screening, limits_needed, workers)
        run.records = build_records(run.stage2, limit)
        rain_flags(run, screening)
        use_catchment = run.role == "target" and bool(grid_points)
        if use_catchment:
            moments = [s.datetime for s in run.stage2[limit].scenes]
            if cells and limits is not None:
                flags, stats = rainmod.catchment_flags(
                    cells, moments, limits, c.windows_h, c.statistics
                )
                run.catchment = flags
                run.catchment_values = {
                    key: [float(v) for v in values] for key, values in stats.items()
                }
            else:
                run.catchment = [None] * len(moments)
        run.union = [
            rainmod.union(p, run.catchment[k] if run.catchment is not None else None, use_catchment)
            for k, p in enumerate(run.point)
        ]
        coincident = [u != "no" for u in run.union]
        run.persistence = criterion_a(
            run.records,
            cfg.variants,
            run.rainy,
            screening.stage2.mad_floor,
            coincident,
            cfg.criteria.persistence_min,
            cfg.criteria.episode_gap_days,
        )

    # Verdict.
    control = runs["control"]
    target_counts = share(target.persistence.evaluations["D0"]) if target.persistence else (0, 0)
    control_counts = share(control.persistence.evaluations["D0"]) if control.persistence else (0, 0)
    rain_known = any(p is not None for p in target.point)
    n_episodes = len(target.persistence.episodes) if target.persistence else 0
    outputs.verdict = decide(n_episodes, target_counts, control_counts, rain_known, cfg.criteria)

    # Report-only analyses.
    t = outputs.tables
    for run in runs.values():
        t.setdefault("stage1_counts", []).extend(stage1_counts(run, limit))
        t.setdefault("b11_exclusions", []).extend(b11_rows(run, limit))
        t.setdefault("processing", []).extend(processing_rows(run, limit))
        t.setdefault("variants", []).extend(variant_rows(run, cfg))
        t.setdefault("scenes", []).extend(scene_rows(run, cfg, limit))
        t.setdefault("holdout", []).extend(holdout_rows(run, cfg))
        t.setdefault("geometry_check", []).extend(geometry_check_rows(run))
        if run.persistence:
            for row in signal_split(run.persistence.evaluations):
                t.setdefault("signal_split", []).append({"site_id": run.site.id, **row})
    t["read_errors"] = read_error_rows(reader.errors)
    t["reproduction_ndti"] = reproduction_ndti(runs, cfg, reference, limit)
    if target.persistence:
        d0 = target.persistence.evaluations["D0"]
        t["seasonality"] = seasonal_rows(target.records, d0, limit, cfg.seasonality_halfwidth_days)
        t["january_february"] = january_february_rows(
            target.records, target.persistence.evaluations, limit
        )
        t["episodes"] = [
            {"episode": k, "days": " ".join(d.isoformat() for d in days), "scenes": len(days)}
            for k, days in enumerate(target.persistence.episodes, start=1)
        ]
        t["baseline_sizes"] = baseline_size_rows(target, cfg, reference)
        catalog = [e for e in load_events(events_path) if e.site_id == target.site.id]
        t["events"], t["chance"] = event_rows(target, catalog, cfg, screening)
        coincident = [u != "no" for u in target.union]
        outputs.placebo = run_placebo(
            target.records,
            cfg.variants,
            target.rainy,
            screening.stage2.mad_floor,
            coincident,
            cfg.criteria,
            placebo_shuffles or cfg.placebo.shuffles,
            cfg.placebo.seed,
        )
        verdict = outputs.verdict
        p = verdict.control_share if math.isfinite(verdict.control_share) else math.nan
        n = verdict.target_scored
        t["chance_level"] = [
            {
                "k": k,
                "label": label,
                "n": n,
                "p": round(p, 4),
                "p_at_least_k": binomial_tail(n, p, k),
            }
            for k, label in (
                (cfg.criteria.min_episodes, "N"),
                (len(target.persistence.candidates), "candidate scenes"),
            )
        ]
        if chirps_ok and grid_points:
            t["chirps"] = chirps_rows(target, cfg, grid_points, reader_chirps, limit)
        outputs.case = build_case(paths, cfg, target, catalog, outputs)
    outputs.manifest["read_error_count"] = len(reader.errors)
    outputs.manifest["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    return outputs


def prefetch_point_rain(
    sites: Sequence[SiteConfig],
    url: str,
    cfg: ValidationConfig,
    cache_dir: Path,
    http: httpx.Client | None = None,
) -> None:
    """Fetch every rain point's series into the cache, paced and retried; failures only log.

    The requests are those the screening's stage 1 makes (same parameters, same cache files),
    so stage 1 then reads them from the cache.

    Args:
        sites: The reaches.
        url: Open-Meteo archive endpoint.
        cfg: Validation settings (period, pacing, attempts).
        cache_dir: The rain cache.
        http: HTTP client (injectable for tests).
    """
    client = http or httpx.Client(timeout=120)
    c = cfg.rain.catchment
    for site in sites:
        for point in site.rain_points:
            try:
                _, cached = rainmod.fetch_hourly(
                    client,
                    url,
                    point.lon,
                    point.lat,
                    rainmod.rain_start(cfg.period, RAIN_LEAD_DAYS),
                    cfg.period.end,
                    cache_dir,
                    c.max_attempts,
                )
            except Exception:  # stage 1 retries and reports a loss
                log.exception("%s: rain point %s not prefetched", site.id, point.description)
                continue
            if not cached:
                time.sleep(c.request_pause_s)


def chirps_rows(
    run: SiteRun,
    cfg: ValidationConfig,
    points: Sequence[tuple[str, float, float]],
    read: ChirpsReader,
    limit: float,
) -> list[dict[str, object]]:
    """CHIRPS against Open-Meteo for each D0-anomalous target scene (report-only).

    Args:
        run: The target run.
        cfg: Validation settings.
        points: Catchment grid points.
        read: CHIRPS point reader.
        limit: The screening's glint limit.

    Returns:
        One row per anomalous scene.
    """
    assert run.persistence is not None
    lonlats = [(lon, lat) for _, lon, lat in points]
    rows: list[dict[str, object]] = []
    for k, (record, scene) in enumerate(
        zip(run.records, run.persistence.evaluations["D0"], strict=True)
    ):
        if not scene.anomalous:
            continue
        total = 0.0
        ok = True
        for back in range(1, cfg.chirps.days_before + 1):
            day = date.fromordinal(record.day.toordinal() - back)
            try:
                values = [
                    v
                    for v in read(chirps_url(cfg.chirps.cog_url_template, day), lonlats)
                    if math.isfinite(v)
                ]
            except Exception:  # report-only
                ok = False
                break
            total += float(np.mean(values)) if values else math.nan
        open_meteo = run.catchment_values.get(("mean", 72), [math.nan] * len(run.records))[k]
        rows.append(
            {
                "date": record.day.isoformat(),
                f"chirps_mean_{cfg.chirps.days_before}d_mm": round(total, 1) if ok else math.nan,
                "open_meteo_mean_72h_mm": round(open_meteo, 1),
            }
        )
    return rows


def manifest(
    paths: ValidationPaths,
    cfg: ValidationConfig,
    runs: dict[str, SiteRun],
    started: datetime,
    stage1_only: bool,
) -> dict[str, object]:
    """The run manifest.

    Args:
        paths: Paths.
        cfg: Validation settings.
        runs: Site runs.
        started: Start time.
        stage1_only: Smoke run.

    Returns:
        Manifest fields.
    """
    method = paths.at(cfg.method)
    grid = paths.at(cfg.rain.catchment.grid_csv)
    hashes_full: dict[str, str] = {}
    hashes_recent: dict[str, str] = {}
    for run in runs.values():
        if run.stage1 is None:
            continue
        hashes_full[run.site.id] = evidence_hash(run.stage1.acquisitions)
        hashes_recent[run.site.id] = evidence_hash(
            [a for a in run.stage1.acquisitions if cfg.geometry_period.contains(a.datetime.date())]
        )
    return {
        "package_version": __version__,
        "run": "smoke (stage 1 only, no NDTI)" if stage1_only else "full",
        "period": f"{cfg.period.start}..{cfg.period.end}",
        "method_blob": blob(method),
        "method_last_commit": last_commit(method),
        "git_commit": head(),
        "screening_config_sha256": config_hash([paths.at(cfg.screening_config)]),
        "validation_config_sha256": config_hash([paths.config]),
        "sites_sha256": config_hash(sorted(paths.at("pipeline/sites").glob("*.yaml"))),
        "events_sha256": config_hash([paths.at(cfg.events.catalog)]),
        "rain_grid_sha256": config_hash([grid]) if grid.exists() else "missing",
        "item_ids_sha256": hashes_full,
        "item_ids_sha256_2022_2025": hashes_recent,
        "libraries": library_versions(),
        "started_utc": started.isoformat(timespec="seconds"),
    }


def build_case(
    paths: ValidationPaths,
    cfg: ValidationConfig,
    run: SiteRun,
    events: list[CatalogEvent],
    outputs: ValidationOutputs,
) -> CaseFile:
    """The demo's case file for the target reach.

    Args:
        paths: Paths.
        cfg: Validation settings.
        run: The target run.
        events: The target's catalog events.
        outputs: The run's outputs (verdict, manifest).

    Returns:
        The case file.
    """
    assert run.stage1 is not None and run.persistence is not None and outputs.verdict is not None
    limit = cfg.variant("D0").swir16_max
    label = reach_label(run.site.river, run.site.name)
    reach, subreaches = build_reach(label, run.stage1.grid, run.stage1.geometry)
    by_key = {a.key: a for a in run.stage1.acquisitions}
    scenes = []
    for k, scene in enumerate(run.stage2[limit].scenes):
        ids, baselines, _ = item_meta(by_key[scene.key])
        z = {vid: dict(ev[k].z) for vid, ev in run.persistence.evaluations.items()}
        flags = {vid: ev[k].anomalous for vid, ev in run.persistence.evaluations.items()}
        rain = Rain(
            point=run.point[k],
            catchment=run.catchment[k] if run.catchment is not None else None,
            union=run.union[k],  # type: ignore[arg-type]
        )
        scenes.append(case_scene(scene, ids, baselines, z, flags, run.persistence.counts[k], rain))
    verdict = outputs.verdict
    sources_csv = paths.at("docs/urra-validation/sources/regulatory-sources.csv")
    context = [
        ContextSource(title=e.event_id, url=e.source_url, text=e.description) for e in events
    ]
    if sources_csv.exists():
        for row in _read_csv(sources_csv):
            if row["id"] in CONTEXT_SOURCE_IDS:
                context.append(ContextSource(title=row["id"], url=row["url"], text=row["purpose"]))
    m = outputs.manifest
    recent = [a for a in run.stage1.acquisitions if cfg.geometry_period.contains(a.datetime.date())]
    return CaseFile(
        ui=Ui(
            reach_label=label,
            reach=reach,
            subreaches=subreaches,
            scenes=scenes,
            events=case_events(events),
            permit=Permit(
                note="No licence condition of this reach sets a limit a relative NDTI can be "
                "compared with; any limit shown is illustrative."
            ),
            validation=ValidationSummary(
                verdict=verdict.label,
                episodes=verdict.episodes,
                episodes_needed=verdict.episodes_needed,
                share_ratio=round(verdict.ratio, 3) if math.isfinite(verdict.ratio) else None,
                share_ratio_needed=verdict.ratio_needed,
            ),
            note="NDTI is a relative index: comparable only within one sub-reach, never NTU. An "
            "anomaly is a departure from the sub-reach's own baseline, never evidence that any "
            "actor caused anything.",
        ),
        context=Context(sources=context),
        manifest=Manifest(
            commit=str(m.get("git_commit", "")),
            config_sha256=str(m.get("validation_config_sha256", "")),
            method_blob=str(m.get("method_blob", "")),
            item_ids_sha256={
                "full": evidence_hash(run.stage1.acquisitions),
                "2022-2025": evidence_hash(recent),
            },
        ),
    )
