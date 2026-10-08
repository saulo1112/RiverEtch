"""A reach validation run: everything the validation's ``method.md`` pre-registered.

Stage 1 runs on the target, the control and the reference (if any) with the geometry frozen to the
screening's period; stage 2 measures NDTI at the pixel glint limits the variants need; the
variants follow. A ``signal`` validation (Urrá) then applies its persistence criteria; a
``baseline`` validation (Magdalena) measures the false-alarm share with Wilson intervals, the
corridor sensitivity, injection-recovery, the demo event and the in-situ comparison. Nothing here
tunes a threshold: every value comes from the validation's settings file or, unchanged, from
``pipeline/screening.yaml``.
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
from datetime import UTC, date, datetime, timedelta
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
from climate_pipeline.validation import insitu as situ
from climate_pipeline.validation.case import (
    BaselineSummary,
    CaseFile,
    Context,
    ContextSource,
    Manifest,
    Permit,
    Rain,
    SyntheticEvent,
    SyntheticOverlay,
    Ui,
    ValidationSummary,
    build_reach,
    case_events,
    case_scene,
    names_outside_context,
    reach_label,
)
from climate_pipeline.validation.config import (
    InsituStation,
    ValidationConfig,
    load_validation_config,
)
from climate_pipeline.validation.grid import read_grid
from climate_pipeline.validation.injection import (
    DemoEvent,
    Injection,
    choose_demo,
    detection_rows,
    run_injections,
    threshold,
)
from climate_pipeline.validation.placebo import PlaceboResult, run_placebo
from climate_pipeline.validation.quietness import Quietness, assess, share_rows
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
    evaluate,
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
    quietness: Quietness | None = None
    injections: list[Injection] = field(default_factory=list)
    sigma_downstream: float = math.nan
    demo: DemoEvent | None = None
    level_percentiles: dict[str, float] = field(default_factory=dict)


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
    insitu_http: httpx.Client | None = None,
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
        insitu_http: Injected HTTP client for the in-situ data (tests).

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
    roles = {"target": cfg.sites.target, "control": cfg.sites.control}
    if cfg.sites.reference:
        roles["reference"] = cfg.sites.reference
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

    # Verdict (signal) or quietness (baseline).
    control = runs["control"]
    if cfg.kind == "signal":
        target_counts = (
            share(target.persistence.evaluations["D0"]) if target.persistence else (0, 0)
        )
        control_counts = (
            share(control.persistence.evaluations["D0"]) if control.persistence else (0, 0)
        )
        rain_known = any(p is not None for p in target.point)
        n_episodes = len(target.persistence.episodes) if target.persistence else 0
        outputs.verdict = decide(
            n_episodes, target_counts, control_counts, rain_known, cfg.criteria
        )
    elif target.persistence is not None and cfg.quietness is not None:
        outputs.quietness = assess(
            target.persistence.evaluations,
            control.persistence.evaluations if control.persistence else None,
            cfg.variants,
            cfg.quietness,
        )

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
        if verdict is not None:
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
        if cfg.kind == "baseline":
            baseline_analyses(
                outputs, paths, catalog, screening, source, reader, rain, workers, insitu_http
            )
        outputs.case = build_case(paths, cfg, target, catalog, outputs)
        leaked = names_outside_context(outputs.case, cfg.context.forbidden_names)
        outputs.manifest["case_names_outside_context"] = leaked
        if leaked:
            outputs.notes.append(f"case file shows names outside its context: {leaked}")
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
    assert run.stage1 is not None and run.persistence is not None
    limit = cfg.variant("D0").swir16_max
    label = cfg.context.ui_label or reach_label(run.site.river, run.site.name)
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
        entry = case_scene(scene, ids, baselines, z, flags, run.persistence.counts[k], rain)
        level = outputs.level_percentiles.get(scene.key)
        if level is not None and math.isfinite(level):
            entry = entry.model_copy(update={"river_level": round(level, 3)})
        scenes.append(entry)
    sources_csv = paths.at(cfg.context.sources_csv)
    context = [
        ContextSource(title=e.event_id, url=e.source_url, text=e.description) for e in events
    ]
    if sources_csv.exists():
        for row in _read_csv(sources_csv):
            if row["id"] in cfg.context.source_ids:
                context.append(ContextSource(title=row["id"], url=row["url"], text=row["purpose"]))
    m = outputs.manifest
    recent = [a for a in run.stage1.acquisitions if cfg.geometry_period.contains(a.datetime.date())]
    summary: ValidationSummary | BaselineSummary
    verdict = outputs.verdict
    if verdict is not None:
        summary = ValidationSummary(
            verdict=verdict.label,
            episodes=verdict.episodes,
            episodes_needed=verdict.episodes_needed,
            share_ratio=round(verdict.ratio, 3) if math.isfinite(verdict.ratio) else None,
            share_ratio_needed=verdict.ratio_needed,
        )
    else:
        q = outputs.quietness
        assert q is not None
        found = (
            threshold(outputs.injections, "ndti", cfg.injection.detection_rate)[1]
            if cfg.injection
            else None
        )
        summary = BaselineSummary(
            scored=q.n,
            anomalous=q.k,
            false_alarm_share=round(q.k / q.n, 4) if q.n else math.nan,
            wilson_low=round(q.low, 4),
            wilson_high=round(q.high, 4),
            quiet=q.quiet,
            control_comparison=q.comparison,
            detection_threshold_ndti=round(found, 4) if found is not None else None,
            demo_step_ndti=outputs.demo.step if outputs.demo else None,
        )
    overlay = None
    demo = outputs.demo
    if demo is not None:
        ids, _, _ = item_meta(by_key[demo.key])
        overlay = SyntheticOverlay(
            label=demo.label,
            note="Injected into a copy of the real series to show the detector's mechanics. "
            "It is not an observation; the real scenes above never include it.",
            events=[
                SyntheticEvent(
                    label=demo.label,
                    date=demo.day.isoformat(),
                    scene_key=demo.key,
                    stac_item_ids=ids,
                    magnitude_ndti=demo.step,
                    real_ndti=round(demo.real_downstream, 4),
                    overlay_ndti=round(demo.real_downstream + demo.step, 4),
                    real_z=round(demo.real_z, 2) if math.isfinite(demo.real_z) else None,
                    overlay_z=round(demo.overlay_z, 2) if math.isfinite(demo.overlay_z) else None,
                    detected=demo.detected,
                )
            ],
        )
    return CaseFile(
        ui=Ui(
            reach_label=label,
            reach=reach,
            subreaches=subreaches,
            scenes=scenes,
            events=case_events(events),
            permit=Permit(note=cfg.context.permit_note),
            validation=summary,
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
        synthetic_overlay=overlay,
    )


# ----------------------------------------------------------------------------------------------
# Baseline validation: quietness, corridors, injection-recovery, demo event, in situ
# ----------------------------------------------------------------------------------------------


def _avoid_windows(
    catalog: Sequence[CatalogEvent], post_hoc: Path, precisions: Sequence[str]
) -> list[tuple[date, date]]:
    """Date ranges of the catalogued and post-hoc events of the given precisions.

    Month-precision dates (``2023-05``) cover the whole month.
    """
    windows = [(e.date_start, e.date_end) for e in catalog if e.date_precision in precisions]
    if post_hoc.exists():
        for row in _read_csv(post_hoc):
            if row.get("date_precision", "") in precisions:
                first = _first_day(row["date_start"])
                last = _last_day(row.get("date_end") or row["date_start"])
                windows.append((first, max(first, last)))
    return windows


def _first_day(text: str) -> date:
    return date.fromisoformat(text if len(text) > 7 else f"{text}-01")


def _last_day(text: str) -> date:
    if len(text) > 7:
        return date.fromisoformat(text)
    first = date.fromisoformat(f"{text}-01")
    return (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


def corridor_rows(
    outputs: ValidationOutputs,
    screening: ScreeningConfig,
    source: SceneSource,
    reader: AcquisitionReader,
    rain: OpenMeteoClient,
    workers: int,
) -> list[dict[str, object]]:
    """False-alarm shares of every variant for each corridor half-width (report-only).

    The frozen geometry's rows come first; each alternative re-derives the corridor on the same
    centerline and sub-reach windows.

    Args:
        outputs: The run so far (its target run and settings).
        screening: Screening settings.
        source: Scene source.
        reader: Band reader.
        rain: Point-rain client.
        workers: Parallel reads.

    Returns:
        Rows with Wilson intervals.
    """
    cfg = outputs.cfg
    target = outputs.runs["target"]
    assert target.persistence is not None and cfg.quietness is not None
    z = cfg.quietness.wilson_z
    width = screening.mask.corridor_half_width_m
    frozen = target.site.corridor_half_width_m or width
    rows = share_rows(
        target.site.id, f"{frozen:g} m (frozen)", target.persistence.evaluations, cfg.variants, z
    )
    if cfg.corridors is None:
        return rows
    limit = cfg.variant("D0").swir16_max
    window = (cfg.period.start, cfg.period.end)
    geometry = (cfg.geometry_period.start, cfg.geometry_period.end)
    for half_width, label in zip(cfg.corridors.half_widths_m, cfg.corridors.labels, strict=True):
        site = target.site.model_copy(update={"corridor_half_width_m": half_width})
        stage1 = run_stage1(site, screening, source, reader, rain, workers, window, geometry)
        if stage1.geometry.failed:
            rows.append({"site_id": site.id, "corridor": label, "note": stage1.geometry.failed})
            continue
        stage2 = run_stage2_variants(stage1, reader, screening, glint_limits(cfg), workers)
        records = build_records(stage2, limit)
        evaluations = {
            v.id: evaluate(records, v, target.rainy, screening.stage2.mad_floor)
            for v in cfg.variants
        }
        rows += share_rows(site.id, label, evaluations, cfg.variants, z)
    return rows


def _number(value: object) -> float:
    """A float from a summary cell (NaN when missing or not numeric)."""
    try:
        return float(str(value))
    except ValueError:
        return math.nan


def _distance_km(station: InsituStation, middle: tuple[float, float]) -> float | str:
    """Straight-line distance from a station to the reach's centerline midpoint.

    Args:
        station: The station (coordinates optional).
        middle: The midpoint's longitude and latitude.

    Returns:
        Kilometres, or an empty string without coordinates.
    """
    if station.lon is None or station.lat is None or not all(map(math.isfinite, middle)):
        return ""
    lon1, lat1, lon2, lat2 = map(math.radians, (station.lon, station.lat, *middle))
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return round(2 * 6371.0 * math.asin(math.sqrt(a)), 1)


def insitu_analyses(
    outputs: ValidationOutputs, paths: ValidationPaths, http: httpx.Client | None
) -> None:
    """Water-quality and river-level comparisons, saturation, and river levels per scene.

    Args:
        outputs: The run so far (tables are added to it).
        paths: Paths (the cache).
        http: HTTP client (injectable for tests).
    """
    cfg = outputs.cfg
    ic = cfg.insitu
    if ic is None:
        return
    target = outputs.runs["target"]
    limit = cfg.variant("D0").swir16_max
    client = http or httpx.Client(timeout=300)
    cache = paths.out / "cache" / "insitu"
    scenes: list[situ.SceneValue] = []
    for measured in target.stage2[limit].scenes:
        if not measured.usable:
            continue
        up, down = measured.sub.get("upstream"), measured.sub.get("downstream")
        scenes.append(
            situ.SceneValue(
                measured.key,
                measured.datetime,
                up.ndti if up else math.nan,
                down.ndti if down else math.nan,
                up.red if up else math.nan,
                down.red if down else math.nan,
            )
        )
    assert target.stage1 is not None
    summary = target.stage1.summary
    middle = (
        _number(summary.get("centerline_mid_lon")),
        _number(summary.get("centerline_mid_lat")),
    )
    t = outputs.tables
    digests: dict[str, str] = {}
    stations: list[dict[str, object]] = []
    samples: dict[str, list[situ.Sample]] = {}
    for station in ic.quality_stations:
        try:
            found, digests[f"quality {station.code}"] = situ.quality_samples(
                client, ic, station, cache
            )
        except Exception as error:  # an unreachable source is reported, never fatal
            stations.append(
                {"code": station.code, "name": station.name, "note": f"failed: {error}"}
            )
            continue
        samples[station.code] = found
        inside = [s for s in found if cfg.period.contains(s.day)]
        stations.append({
            "code": station.code, "name": station.name, "role": station.role, "kind": "quality",
            "distance_km": _distance_km(station, middle),
            "variables": " ".join(sorted({f"{s.variable} ({s.unit})" for s in found})),
            "samples": len(found), "samples_in_period": len(inside),
            "first": min((s.day for s in found), default=""),
            "last": max((s.day for s in found), default=""), "note": station.note,
        })  # fmt: skip
    pair_rows: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    for set_name, roles, days in (
        ("primary", {"primary"}, ic.match_days_primary),
        ("primary and secondary", {"primary", "secondary"}, ic.match_days_secondary),
    ):
        chosen = [s for s in ic.quality_stations if s.role in roles]
        for variable in ic.quality_variables:
            pool = [
                sample
                for station in chosen
                for sample in samples.get(station.code, [])
                if sample.variable == variable and cfg.period.contains(sample.day)
            ]
            pairs = situ.match_samples(pool, scenes, days)
            for sample, scene, gap in pairs:
                pair_rows.append({
                    "set": set_name, "station": sample.station, "variable": variable,
                    "sample_day": sample.day, "scene": scene.key, "gap_days": gap,
                    "value": sample.value, "unit": sample.unit, "censored": sample.censored,
                    "ndti_reach": round(scene.ndti_reach, 4),
                    "ndti_upstream": round(scene.ndti_upstream, 4),
                    "ndti_downstream": round(scene.ndti_downstream, 4),
                })  # fmt: skip
            row = situ.compare(
                f"{variable}, {set_name} stations, +-{days} d",
                [scene.ndti_reach for _, scene, _ in pairs],
                [sample.value for sample, _, _ in pairs],
                ic,
            )
            comparisons.append(row)
    levels: dict[str, list[float]] = {}
    level_rows: list[dict[str, object]] = []
    first, last = cfg.period.start - timedelta(days=1), cfg.period.end + timedelta(days=1)
    for station in ic.level_stations:
        try:
            series, unit, digests[f"level {station.code}"] = situ.level_series(
                client, ic, station, first, last, cache
            )
        except Exception as error:  # reported, never fatal
            stations.append(
                {"code": station.code, "name": station.name, "note": f"failed: {error}"}
            )
            continue
        values = [
            situ.level_at(series, s.when, ic.level_window_hours, ic.level_min_observations)
            for s in scenes
        ]
        levels[station.code] = values
        stations.append({
            "code": station.code, "name": station.name, "role": station.role, "kind": "level",
            "distance_km": _distance_km(station, middle),
            "variables": f"river level ({unit})", "samples": len(series),
            "samples_in_period": len(series),
            "first": series[0][0].date() if series else "",
            "last": series[-1][0].date() if series else "", "note": station.note,
        })  # fmt: skip
        comparisons.append(
            situ.compare(
                f"river level at {station.code}",
                [s.ndti_reach for s in scenes],
                values,
                ic,
            )
        )
        for scene, value in zip(scenes, values, strict=True):
            if math.isfinite(value):
                level_rows.append({
                    "station": station.code, "scene": scene.key,
                    "date": scene.when.date(), "level": round(value, 2),
                    "level_percentile": round(situ.percentile_rank(values, value), 3),
                    "ndti_reach": round(scene.ndti_reach, 4),
                })  # fmt: skip
    if levels:
        pooled_x, pooled_y = [], []
        for values in levels.values():
            for scene, value in zip(scenes, values, strict=True):
                if math.isfinite(value):
                    pooled_x.append(scene.ndti_reach)
                    pooled_y.append(situ.percentile_rank(values, value))
        comparisons.append(
            situ.compare("river level percentile, stations pooled", pooled_x, pooled_y, ic)
        )
        for k, scene in enumerate(scenes):
            for station in ic.level_stations:
                values = levels.get(station.code, [])
                if values and math.isfinite(values[k]):
                    outputs.level_percentiles[scene.key] = situ.percentile_rank(values, values[k])
                    break
    t["insitu_stations"] = stations
    t["insitu_pairs"] = pair_rows
    t["insitu_comparison"] = comparisons
    t["river_level"] = level_rows
    t["saturation"] = situ.saturation_rows(scenes, ic)
    outputs.manifest["insitu_sha256"] = digests


def anomaly_rows(outputs: ValidationOutputs) -> list[dict[str, object]]:
    """Every D0-anomalous target scene with its glint, rain and river-level context.

    Args:
        outputs: The run so far.

    Returns:
        One row per anomalous scene.
    """
    target = outputs.runs["target"]
    assert target.persistence is not None
    rows = []
    d0 = target.persistence.evaluations["D0"]
    for k, (record, scene) in enumerate(zip(target.records, d0, strict=True)):
        if not scene.anomalous:
            continue
        rows.append({
            "date": record.day, "signals": " ".join(scene.signals),
            **{f"z_{s}": round(scene.z.get(s, math.nan), 2) for s in SIGNALS},
            "persistence": target.persistence.counts[k],
            "glint_share_max": round(record.glint_share, 3),
            "rain_point_72h_mm": round(target.point_mm[k], 1),
            "rain_union": target.union[k],
            "river_level_percentile": round(
                outputs.level_percentiles.get(record.key, math.nan), 3
            ),
        })  # fmt: skip
    return rows


def baseline_analyses(
    outputs: ValidationOutputs,
    paths: ValidationPaths,
    catalog: Sequence[CatalogEvent],
    screening: ScreeningConfig,
    source: SceneSource,
    reader: AcquisitionReader,
    rain: OpenMeteoClient,
    workers: int,
    insitu_http: httpx.Client | None,
) -> None:
    """The baseline validation's analyses, added to the outputs' tables.

    Args:
        outputs: The run so far.
        paths: Paths.
        catalog: The target's catalog events.
        screening: Screening settings.
        source: Scene source.
        reader: Band reader.
        rain: Point-rain client.
        workers: Parallel reads.
        insitu_http: HTTP client for the in-situ data (tests).
    """
    cfg = outputs.cfg
    target = outputs.runs["target"]
    control = outputs.runs["control"]
    assert target.persistence is not None and target.stage1 is not None
    assert cfg.quietness is not None and cfg.injection is not None and cfg.demo_event is not None
    t = outputs.tables
    z = cfg.quietness.wilson_z
    t["quietness"] = share_rows(
        target.site.id, "frozen", target.persistence.evaluations, cfg.variants, z
    )
    if control.persistence is not None:
        t["quietness"] += share_rows(
            control.site.id, "frozen", control.persistence.evaluations, cfg.variants, z
        )
    t["corridors"] = corridor_rows(outputs, screening, source, reader, rain, workers)
    insitu_analyses(outputs, paths, insitu_http)
    t["target_anomalies"] = anomaly_rows(outputs)
    d0 = cfg.variant("D0")
    mad_floor = screening.stage2.mad_floor
    outputs.injections, outputs.sigma_downstream = run_injections(
        target.records, d0, target.rainy, mad_floor, cfg.injection
    )
    t["injection"] = detection_rows(outputs.injections)
    rows: list[dict[str, object]] = []
    for scale in ("ndti", "sigma"):
        grid_value, interpolated = threshold(
            outputs.injections, scale, cfg.injection.detection_rate
        )
        rows.append({
            "scale": scale, "detection_rate": cfg.injection.detection_rate,
            "smallest_grid_step": grid_value if grid_value is not None else "",
            "interpolated_step": round(interpolated, 5) if interpolated is not None else "",
            "downstream_sigma_ndti": round(outputs.sigma_downstream, 5),
        })  # fmt: skip
    t["injection_thresholds"] = rows
    found = threshold(outputs.injections, "ndti", cfg.injection.detection_rate)[1]
    de = cfg.demo_event
    avoid = _avoid_windows(catalog, paths.at(de.post_hoc_events_csv), de.event_precisions)
    clear = {s.key for s in target.stage1.scenes if s.clear}
    outputs.demo = choose_demo(target.records, d0, target.rainy, mad_floor, clear, avoid, found, de)
    demo = outputs.demo
    t["demo_event"] = (
        [
            {
                "date": demo.day,
                "scene": demo.key,
                "step_ndti": demo.step,
                "real_downstream_ndti": round(demo.real_downstream, 4),
                "overlay_downstream_ndti": round(demo.real_downstream + demo.step, 4),
                "real_max_abs_z": round(demo.real_z, 2),
                "overlay_max_abs_z": round(demo.overlay_z, 2),
                "detected": demo.detected,
                "eligible_scenes": demo.eligible_scenes,
                "dated_events_avoided": len(avoid),
                "label": demo.label,
            }
        ]
        if demo
        else [{"note": "no demo event: no detection threshold or no eligible scene"}]
    )
