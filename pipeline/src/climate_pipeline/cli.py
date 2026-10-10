"""Command-line entry point of the pipeline.

``climate-pipeline screening`` runs the data-driven site screening (see
docs/site-screening/method.md); ``climate-pipeline fetch-docs`` fetches public documents with a
provenance manifest (see docs/urra-validation/regulatory.md); ``climate-pipeline catchment-grid``
and ``climate-pipeline validation`` run the pre-registered validation of the chosen reach (see
docs/urra-validation/method.md); ``climate-pipeline contract`` writes the observation record's
JSON Schema and sample records (see docs/schema/README.md). The other stages (operational
ingestion, anomaly publication) are not implemented yet.
"""

from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path

from climate_pipeline import __version__


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="climate-pipeline", description=__doc__)
    parser.add_argument("--version", action="version", version=f"climate-pipeline {__version__}")
    commands = parser.add_subparsers(dest="command")
    screening = commands.add_parser(
        "screening", help="screen candidate river reaches (stage 1, score, stage 2, report)"
    )
    screening.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    screening.add_argument("--sites", default="", help="comma-separated site ids (default: all)")
    screening.add_argument("--source", default=None, help="STAC source (default: from config)")
    screening.add_argument("--start", type=date.fromisoformat, default=None)
    screening.add_argument("--end", type=date.fromisoformat, default=None)
    screening.add_argument("--stage1-only", action="store_true", help="skip stage 2")
    screening.add_argument(
        "--posthoc",
        action="store_true",
        help="the declared post-hoc variant (MNDWI mask fallback, observable rule); "
        "results default to docs/site-screening/results-posthoc",
    )
    screening.add_argument("--workers", type=int, default=8)
    screening.add_argument(
        "--results", type=Path, default=None, help="where generated tables go (default: docs)"
    )
    docs = commands.add_parser(
        "fetch-docs",
        help="fetch public documents with a provenance manifest and keyword-in-context hits",
    )
    docs.add_argument("--sources", type=Path, required=True, help="CSV: id,group,url,purpose")
    docs.add_argument("--keywords", type=Path, required=True, help="one keyword per line")
    docs.add_argument("--print-pages", type=Path, default=None, help="CSV: source_id,pages,reason")
    docs.add_argument("--groups", default="", help="comma-separated groups (default: all)")
    docs.add_argument("--only", default="", help="comma-separated source ids (default: all)")
    docs.add_argument("--out", type=Path, required=True, help="output folder (never committed)")
    docs.add_argument("--max-mb", type=float, default=60.0, help="size cap per document")
    docs.add_argument("--pause", type=float, default=1.5, help="seconds between requests")
    docs.add_argument("--timeout", type=float, default=60.0, help="seconds per request")
    for name, text in (
        ("validation", "run a pre-registered reach validation (its settings file: --config)"),
        ("catchment-grid", "build the catchment rain grid of the validation's target reach"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
        command.add_argument(
            "--config", type=Path, default=Path("pipeline/urra-validation.yaml"),
            help="validation settings, relative to the root",
        )  # fmt: skip
        command.add_argument(
            "--out", type=Path, default=Path("pipeline/out"), help="caches, relative to the root"
        )
    validation = commands.choices["validation"]
    validation.add_argument("--stage1-only", action="store_true", help="smoke run: no NDTI")
    validation.add_argument("--workers", type=int, default=8)
    validation.add_argument(
        "--results", type=Path, default=None, help="results folder (default: from the config)"
    )
    contract = commands.add_parser("contract", help="observation record contract: schema, samples")
    actions = contract.add_subparsers(dest="action", required=True)
    schema = actions.add_parser("schema", help="write the generated JSON Schema")
    schema.add_argument("--out", type=Path, required=True, help="schema file")
    sample = actions.add_parser("sample", help="sealed records from a case file v1 (reads S3)")
    sample.add_argument("--case", type=Path, required=True, help="case file v1 (JSON)")
    sample.add_argument("--reach-id", required=True, help="the reach's site id")
    sample.add_argument("--dates", default="", help="comma-separated scene dates (default: all)")
    sample.add_argument("--collection", default="sentinel-2-l2a", help="STAC collection")
    sample.add_argument("--threshold", type=float, default=3.0, help="D0 anomaly threshold")
    sample.add_argument("--out", type=Path, required=True, help="records file (JSON)")
    calibration = commands.add_parser(
        "calibration", help="calibration and climate-context validation (fetch, run, verify)"
    )
    calibration.add_argument(
        "action", choices=("fetch", "run", "verify", "acolite-list"),
        help="fetch: network snapshots; run: offline results; verify: recompute and compare; "
        "acolite-list: the Level-1C scenes of Stage 2c",
    )  # fmt: skip
    calibration.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    calibration.add_argument(
        "--config", type=Path, default=Path("pipeline/calibration.yaml"),
        help="settings, relative to the root",
    )  # fmt: skip
    calibration.add_argument(
        "--cache", type=Path, default=Path("pipeline/out/cache"), help="caches, relative to root"
    )
    calibration.add_argument("--stations-only", action="store_true", help="fetch: selection only")
    calibration.add_argument(
        "--keep-chirps", action="store_true",
        help="fetch: keep the CHIRPS snapshot already in the inputs (its file time is recorded)",
    )  # fmt: skip
    calibration.add_argument("--workers", type=int, default=8)
    calibration.add_argument(
        "--out", type=Path, default=None, help="run: results folder (default: from the config)"
    )
    return parser


def _split(text: str) -> set[str]:
    return {part.strip() for part in text.split(",") if part.strip()}


def fetch_docs(args: argparse.Namespace) -> int:
    """Run ``fetch-docs``: fetch, extract text, print the manifest and the requested pages.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code.
    """
    from climate_pipeline.sources import fetch

    sources = fetch.load_sources(args.sources)
    groups, only = _split(args.groups), _split(args.only)
    chosen = [
        s for s in sources if (not groups or s.group in groups) and (not only or s.id in only)
    ]
    records, hits = fetch.fetch_all(
        chosen,
        args.out,
        fetch.load_keywords(args.keywords),
        client=fetch.make_client(args.timeout),
        max_bytes=int(args.max_mb * 1_000_000),
        pause_s=args.pause,
    )
    for record in records:
        state = "ok" if record.ok else "FAILED"
        found = sum(1 for h in hits if h.source_id == record.source_id)
        print(
            f"{record.source_id}: {state} {record.status} {record.copy} {record.bytes} B, "
            f"{record.pages} pages ({record.ocr_pages} OCR), {found} keyword hits"
            f"{'; ' + record.error if record.error else ''}"
        )
    print(fetch.MANIFEST_BEGIN)
    print(fetch.manifest_csv(records), end="")
    print(fetch.MANIFEST_END)
    if args.print_pages is not None:
        wanted = fetch.load_print_pages(args.print_pages)
        for record in (r for r in records if r.ok and r.source_id in wanted):
            pages = fetch.read_pages(args.out / "text" / f"{record.source_id}.txt")
            for page in (p for p in pages if p.number in wanted[record.source_id]):
                ocr = " (OCR)" if page.ocr else ""
                print(f"=== {record.source_id} page {page.number}{ocr} BEGIN ===")
                print(page.text)
                print(f"=== {record.source_id} page {page.number} END ===")
    return 0


def validation(args: argparse.Namespace) -> int:
    """Run ``validation``: the full run, or the smoke run with ``--stage1-only``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code.
    """
    from climate_pipeline.validation.config import load_validation_config
    from climate_pipeline.validation.report import write_outputs
    from climate_pipeline.validation.run import ValidationPaths, run_validation

    root = args.root.resolve()
    paths = ValidationPaths(root, root / args.config, root / args.out)
    outputs = run_validation(paths, stage1_only=args.stage1_only, workers=args.workers)
    cfg = load_validation_config(paths.config)
    results = root / args.results if args.results is not None else root / cfg.outputs.results
    write_outputs(outputs, results, root)
    if outputs.quietness is not None:
        q = outputs.quietness
        reading = f"{'quiet' if q.quiet else 'not quiet'} ({q.k}/{q.n}, {q.comparison})"
        print(f"quietness: {reading}; results in {results}")
    else:
        verdict = outputs.verdict.label if outputs.verdict else "none (smoke run)"
        print(f"verdict: {verdict}; results in {results}")
    leaked = outputs.manifest.get("case_names_outside_context")
    if leaked:
        print(f"error: the case file shows names outside its context: {leaked}")
        return 1
    return 0


def catchment_grid(args: argparse.Namespace) -> int:
    """Run ``catchment-grid``: build and write the target reach's rain grid.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code.
    """
    from climate_pipeline.screening.config import load_site
    from climate_pipeline.validation.config import load_validation_config
    from climate_pipeline.validation.grid import (
        HydroBasins,
        build_grid,
        download,
        extract_layer,
        write_grid,
    )

    root = args.root.resolve()
    cfg = load_validation_config(root / args.config)
    c = cfg.rain.catchment
    site = load_site(root / "pipeline" / "sites" / f"{cfg.sites.target}.yaml")
    cache = root / args.out / "cache" / "hydrobasins"
    archive = cache / f"{c.hydrobasins_layer}.zip"
    sha256 = download(c.hydrobasins_url, archive)
    layer = HydroBasins.open(extract_layer(archive, c.hydrobasins_layer, cache / "layer"))
    anchor = (site.downstream_anchor.lon, site.downstream_anchor.lat)
    grid = build_grid(
        layer, anchor, c.anchor_tolerance_deg, c.spacings_deg, c.points_min, c.points_max, sha256
    )
    write_grid(grid, root / c.grid_csv)
    print(
        f"HydroBASINS sha256 {sha256}; outlet {grid.outlet_hybas_id}; {grid.basins} basins, "
        f"{grid.area_km2:.0f} km2; spacing {grid.spacing}; {len(grid.points)} points ({grid.note})"
    )
    return 0


def contract(args: argparse.Namespace) -> int:
    """Run ``contract schema`` or ``contract sample``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code.
    """
    import json
    from datetime import UTC, datetime

    import httpx

    from climate_pipeline.contract import observation as obs

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.action == "schema":
        args.out.write_text(obs.schema_text(), encoding="utf-8", newline="\n")
        print(f"schema written to {args.out}")
        return 0
    case = json.loads(args.case.read_text(encoding="utf-8"))
    dates = sorted(_split(args.dates)) or None
    wanted = {
        item_id
        for scene in case["ui"]["scenes"]
        if not scene["excluded"] and (dates is None or scene["date"] in dates)
        for item_id in scene["stacItemIds"]
    }
    items: dict[str, obs.ItemMeta] = {}
    with httpx.Client(timeout=60, follow_redirects=True) as http:
        for item_id in sorted(wanted):
            url = obs.item_json_url(item_id)
            response = http.get(url)
            response.raise_for_status()
            when = datetime.now(UTC).isoformat(timespec="seconds")
            items[item_id] = obs.item_meta_from_json(url, response.content, when)
    records = obs.records_from_case(
        case, args.reach_id, args.collection, items, args.threshold, dates
    )
    data = [r.model_dump(mode="json", by_alias=True) for r in records]
    args.out.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{len(records)} records written to {args.out}")
    return 0


def calibration(args: argparse.Namespace) -> int:
    """Run ``calibration fetch``, ``run``, ``verify`` or ``acolite-list``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code (1 when verification finds a mismatch or a fetch has read errors).
    """
    import json
    import platform
    from datetime import UTC, datetime

    from climate_pipeline.calibration.config import load_calibration_config
    from climate_pipeline.calibration.fetching import (
        CalibrationPaths,
        fetch_stations,
        fetch_values,
    )
    from climate_pipeline.calibration.report import verify, write_outputs
    from climate_pipeline.calibration.run import analyse
    from climate_pipeline.provenance import head, library_versions

    root = args.root.resolve()
    paths = CalibrationPaths(root, root / args.config, root / args.cache)
    cfg = load_calibration_config(paths.config)
    if args.action == "fetch":
        if args.stations_only:
            rows = fetch_stations(cfg, paths, args.workers)
            selected = sum(1 for r in rows if r.get("selected"))
            print(f"{len(rows)} candidates, {selected} selected")
            return 0
        counts = fetch_values(cfg, paths, args.workers, keep_chirps=args.keep_chirps)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "acolite-list":
        from climate_pipeline.calibration.acolite import acolite_list

        scenes = acolite_list(cfg, paths, paths.cache.parent / "acolite-work", args.workers)
        products = {r["l1c_product"] for r in scenes if r["l1c_product"]}
        print(f"{len(scenes)} matchup scenes, {len(products)} Level-1C products")
        return 0
    if args.action == "verify":
        problems = verify(cfg, paths)
        for line in problems:
            print(line)
        print("verified" if not problems else f"{len(problems)} mismatches")
        return 1 if problems else 0
    started = datetime.now(UTC).isoformat(timespec="seconds")
    out = root / args.out if args.out is not None else paths.at(cfg.outputs.results)
    write_outputs(analyse(cfg, paths), cfg, paths, out)
    run_info = {
        "commit": head(), "started_utc": started,
        "finished_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(), "libraries": library_versions(),
    }  # fmt: skip
    (out / "run.json").write_text(
        json.dumps(run_info, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"results in {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline command-line interface.

    Args:
        argv: Arguments (default: the process arguments).

    Returns:
        The process exit code.
    """
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "fetch-docs":
        return fetch_docs(args)
    if args.command == "contract":
        return contract(args)
    if args.command == "calibration":
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        return calibration(args)
    if args.command in ("validation", "catchment-grid"):
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        return validation(args) if args.command == "validation" else catchment_grid(args)
    if args.command != "screening":
        parser.print_help()
        return 0
    if (args.start is None) != (args.end is None):
        parser.error("--start and --end go together")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    from climate_pipeline.screening.run import default_paths, run_screening

    paths = default_paths(args.root.resolve())
    results = args.results
    if results is None and args.posthoc:
        results = paths.results.parent / "results-posthoc"
    if results is not None:
        paths = type(paths)(**{**paths.__dict__, "results": results.resolve()})
    outputs = run_screening(
        paths,
        source_name=args.source,
        only_sites=tuple(s.strip() for s in args.sites.split(",") if s.strip()),
        period=(args.start, args.end) if args.start else None,
        stage2=not args.stage1_only,
        workers=args.workers,
        posthoc=args.posthoc,
    )
    print(f"stage-2 sites: {', '.join(outputs.selected) or 'none'}; results in {paths.results}")
    return 0
