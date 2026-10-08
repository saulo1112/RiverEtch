"""End-to-end screening run: stage 1 on every site, score, stage 2 on the selected sites, report."""

from __future__ import annotations

import logging
import math
import shutil
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np

from climate_pipeline import __version__
from climate_pipeline.provenance import blob, head, last_commit
from climate_pipeline.screening.config import (
    ScreeningConfig,
    SiteConfig,
    config_hash,
    load_screening_config,
    load_sites,
)
from climate_pipeline.screening.events import (
    CatalogEvent,
    EventOutcome,
    chance_rate,
    evaluate,
    event_window,
    is_scored,
    load_events,
    observable,
    window_days,
)
from climate_pipeline.screening.plots import (
    MapPanel,
    plot_maps,
    plot_mask,
    plot_series,
    site_stretch,
)
from climate_pipeline.screening.rain import OpenMeteoClient
from climate_pipeline.screening.report import ChanceRate, RunOutputs, write_all
from climate_pipeline.screening.rio import AcquisitionReader, lonlat_rowcol
from climate_pipeline.screening.score import SiteInputs, recommend, score_sites, select_stage2
from climate_pipeline.screening.stac import SceneSource, make_source
from climate_pipeline.screening.stage1 import Stage1Result, failed_stage1, run_stage1
from climate_pipeline.screening.stage2 import (
    Stage2Result,
    false_alarm_rate,
    ndti_map,
    run_stage2,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunPaths:
    """Inputs and outputs of a run."""

    config: Path
    sites: Path
    events: Path
    method: Path
    out: Path
    results: Path


def stage1_inputs(
    result: Stage1Result, events: list[CatalogEvent], cfg: ScreeningConfig
) -> SiteInputs:
    """The score inputs of one site.

    Args:
        result: The site's stage-1 result.
        events: Catalog events of this site.
        cfg: Settings.

    Returns:
        Score inputs.
    """
    s = result.summary
    by_rule = cfg.score.scene_rule == "observable"
    clear_days = [
        sc.datetime.date() for sc in result.scenes if (sc.observable if by_rule else sc.clear)
    ]
    scored = [e for e in events if is_scored(e, cfg.events, cfg.period.start, cfg.period.end)]

    def number(key: str) -> float:
        value = s.get(key, math.nan)
        return float(value) if isinstance(value, int | float) else math.nan

    return SiteInputs(
        site_id=result.site.id,
        category=result.site.category,
        geometry_failed=str(s.get("geometry_failed", "")),
        clear=int(number("clear")),
        clear_per_year=number("clear_per_year"),
        months_with_clear_pct=number("months_with_clear_pct"),
        observable_per_year=number("observable_per_year"),
        months_with_observable_pct=number("months_with_observable_pct"),
        width_px_10m=number("width_px_10m"),
        tile_integrity=number("tile_integrity"),
        median_weaker_subreach_water_px_10m=number("median_weaker_subreach_water_px_10m"),
        confluence_inside=bool(s.get("confluence_inside", False)),
        events_with_clear_window=sum(1 for e in scored if observable(e, cfg.events, clear_days)),
        observable=int(number("observable")),
        median_weaker_subreach_valid_px_10m=number("median_weaker_subreach_valid_px_10m"),
    )


def run_screening(
    paths: RunPaths,
    *,
    source_name: str | None = None,
    only_sites: tuple[str, ...] = (),
    period: tuple[date, date] | None = None,
    stage2: bool = True,
    workers: int = 8,
    source: SceneSource | None = None,
    rain: OpenMeteoClient | None = None,
    posthoc: bool = False,
) -> RunOutputs:
    """Run the screening and write its outputs.

    Args:
        paths: Inputs and output directories.
        source_name: STAC source to use instead of the configured default.
        only_sites: Restrict to these site ids (e.g. a quick re-run).
        period: Restrict to a shorter period (``(start, end)``).
        stage2: Also run stage 2 on the selected sites.
        workers: Parallel reads.
        source: Injected scene source (tests); built from the config otherwise.
        rain: Injected rain client (tests); built from the config otherwise.
        posthoc: Run the declared post-hoc variant (MNDWI mask fallback, observable rule).

    Returns:
        The outputs (also written to disk).
    """
    started = datetime.now(UTC)
    cfg = load_screening_config(paths.config)
    if posthoc:
        cfg = cfg.posthoc()
    if period is not None:
        cfg = cfg.model_copy(
            update={"period": cfg.period.model_copy(update={"start": period[0], "end": period[1]})}
        )
    sites = load_sites(paths.sites, only_sites)
    events = load_events(paths.events) if paths.events.exists() else []
    name = source_name or cfg.stac.source
    if source is None:
        source = make_source(name, cfg.stac.sources, cfg.stac.page_size)
    if rain is None:
        rain = OpenMeteoClient(cfg.rain.url, cache_dir=paths.out / "cache" / "rain")
    reader = AcquisitionReader(source, paths.out / "cache" / "bands")
    # Generated outputs only: start clean so nothing from an earlier run survives next to these.
    shutil.rmtree(paths.results, ignore_errors=True)

    stage1: list[Stage1Result] = []
    for site in sites:
        try:
            result = run_stage1(
                site, cfg, source, reader, rain, workers, (cfg.period.start, cfg.period.end)
            )
        except Exception as error:  # one site's failure must not lose the others
            log.exception("%s: stage 1 failed", site.id)
            result = failed_stage1(site, cfg, f"error: {type(error).__name__}: {error}")
        stage1.append(result)
    by_site = {e: [ev for ev in events if ev.site_id == e] for e in (s.id for s in sites)}
    scores = score_sites([stage1_inputs(r, by_site[r.site.id], cfg) for r in stage1], cfg)
    selected = select_stage2(scores, cfg)
    recommendation = recommend(scores)
    manifest: dict[str, object] = {
        "package_version": __version__,
        "variant": "post-hoc (declared in method.md)" if posthoc else "pre-registered",
        "period_start": cfg.period.start.isoformat(),
        "period_end": cfg.period.end.isoformat(),
        "source": name,
        "sites": [s.id for s in sites],
        "stage2_sites": selected,
        "method_blob": blob(paths.method),
        "method_last_commit": last_commit(paths.method),
        "config_sha256": config_hash([paths.config, *sorted(paths.sites.glob("*.yaml"))]),
        "events_sha256": config_hash([paths.events]) if paths.events.exists() else "none",
        "git_commit": head(),
        "evidence_sha256": {
            str(r.summary["site_id"]): r.summary["evidence_sha256"] for r in stage1
        },
        "started_utc": started.isoformat(timespec="seconds"),
        "recommended": recommendation.recommended,
        "runner_up": recommendation.runner_up,
        "ranking_fragile": recommendation.fragile,
    }
    outputs = RunOutputs(
        manifest=manifest,
        stage1=stage1,
        scores=scores,
        selected=selected,
        recommendation=recommendation,
        anomaly_threshold=cfg.stage2.anomaly_z,
    )
    figures_dir = paths.results / "figures"
    outputs.figures += [_mask_figure(r, figures_dir) for r in stage1 if r.frequency is not None]
    # Stage-1 outputs are written now, so a later failure or timeout does not lose them.
    manifest["read_errors"] = reader.errors[:100]
    manifest["finished_utc"] = "stage 1 only so far"
    write_all(outputs, paths.results, paths.out)
    if stage2:
        for result in (r for r in stage1 if r.site.id in selected):
            second = run_stage2(result, reader, cfg, workers)
            outputs.stage2.append(second)
            site_events = by_site[result.site.id]
            outcomes, chances = _validate_events(second, site_events, cfg)
            outputs.outcomes += outcomes
            outputs.chance += chances
            if result.site.category == "D":
                outputs.false_alarms[result.site.id] = false_alarm_rate(
                    second, cfg.stage2.anomaly_z
                )
            outputs.figures += _figures(
                result, second, outcomes, site_events, reader, cfg, figures_dir
            )
    manifest["read_errors"] = reader.errors[:100]
    manifest["read_error_count"] = len(reader.errors)
    manifest["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
    write_all(outputs, paths.results, paths.out)
    return outputs


def _validate_events(
    result: Stage2Result, events: list[CatalogEvent], cfg: ScreeningConfig
) -> tuple[list[EventOutcome], list[ChanceRate]]:
    start, end = cfg.period.start, cfg.period.end
    scored = [e for e in events if is_scored(e, cfg.events, start, end)]
    scores = result.scores_by_day()
    outcomes = [evaluate(e, cfg.events, scores, cfg.stage2.anomaly_z) for e in scored]
    avoid = [event_window(e, cfg.events) for e in events]

    def chance(days: int, event_id: str) -> ChanceRate:
        rate, n = chance_rate(
            days, scores, cfg.stage2.anomaly_z, start, end, avoid,
            cfg.events.chance_shifts, cfg.events.seed,
        )  # fmt: skip
        return ChanceRate(result.site.id, rate, n, event_id, days)

    # One chance rate per scored event, with that event's own window length; sites without
    # scored events (e.g. the control) get the rate of a single-day event's window.
    default = cfg.events.window_before_days + cfg.events.window_after_days + 1
    chances = [chance(window_days(e, cfg.events), e.event_id) for e in scored]
    return outcomes, chances or [chance(default, "")]


def _figures(
    result: Stage1Result,
    second: Stage2Result,
    outcomes: list[EventOutcome],
    events: list[CatalogEvent],
    reader: AcquisitionReader,
    cfg: ScreeningConfig,
    figures_dir: Path,
) -> list[str]:
    site = result.site
    scored_ids = {o.event.event_id for o in outcomes}
    context = [e for e in events if e.event_id not in scored_ids]
    daily = result.rain[0].daily(cfg.rain.timezone) if result.rain else {}
    files = []
    series = figures_dir / f"{site.id}_series.png"
    plot_series(
        second,
        daily,
        outcomes,
        context,
        cfg.stage2.anomaly_z,
        cfg.period.start,
        cfg.period.end,
        series,
    )
    files.append(str(series))

    usable = second.usable()
    ranked = sorted(
        (s for s in usable if any(math.isfinite(z) for z in s.z.values())),
        key=lambda s: max(abs(z) for z in s.z.values() if math.isfinite(z)),
    )
    if len(ranked) < 3 or result.geometry.corridor is None:
        return files
    picks = [("anomaly 1", ranked[-1]), ("anomaly 2", ranked[-2]), ("normal", ranked[0])]
    by_key = {a.key: a for a in result.acquisitions}
    panels = []
    for label, scene in picks:
        top = max(abs(z) for z in scene.z.values() if math.isfinite(z))
        rain_note = ", rain-coincident" if scene.rain_coincident else ""
        title = f"{label}: {scene.datetime.date()}\nmax |z| {top:.1f}{rain_note}"
        panels.append(MapPanel(title, ndti_map(result, by_key[scene.key], reader, cfg)))
    subs = np.zeros(result.grid.shape, dtype=bool)
    for sub in result.geometry.subreaches:
        subs |= sub.mask
    rows, cols = np.nonzero(np.repeat(np.repeat(subs, 2, axis=0), 2, axis=1))
    pad = 60
    window = (
        slice(max(0, int(rows.min()) - pad), int(rows.max()) + pad),
        slice(max(0, int(cols.min()) - pad), int(cols.max()) + pad),
    )
    stretch = site_stretch(
        [v for s in usable for v in (s.values["upstream"], s.values["downstream"])]
    )
    maps = figures_dir / f"{site.id}_maps.png"
    plot_maps(site.name, panels, window, stretch, maps)
    files.append(str(maps))
    return files


def _mask_figure(result: Stage1Result, figures_dir: Path) -> str:
    site = result.site
    assert result.frequency is not None
    anchors = {
        "up": lonlat_rowcol(result.grid, site.upstream_anchor.lon, site.upstream_anchor.lat),
        "down": lonlat_rowcol(result.grid, site.downstream_anchor.lon, site.downstream_anchor.lat),
    }
    path = figures_dir / f"{site.id}_mask.png"
    title = f"{site.name}\n{result.mask_source.upper()} water frequency"
    plot_mask(title, result.frequency, result.geometry, anchors, path)
    return str(path)


def default_paths(root: Path) -> RunPaths:
    """Paths relative to the repository root.

    Args:
        root: Repository root.

    Returns:
        The default inputs and outputs.
    """
    return RunPaths(
        config=root / "pipeline" / "screening.yaml",
        sites=root / "pipeline" / "sites",
        events=root / "docs" / "site-screening" / "events.csv",
        method=root / "docs" / "site-screening" / "method.md",
        out=root / "pipeline" / "out",
        results=root / "docs" / "site-screening" / "results",
    )


def site_ids(paths: RunPaths) -> list[str]:
    """Ids of the configured sites.

    Args:
        paths: Run paths.

    Returns:
        Site ids.
    """
    return [s.id for s in load_sites(paths.sites)]


__all__ = ["RunPaths", "SiteConfig", "default_paths", "run_screening", "site_ids"]
