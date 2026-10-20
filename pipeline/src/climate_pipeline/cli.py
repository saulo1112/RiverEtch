"""Command-line entry point of the pipeline.

``climate-pipeline screening`` runs the data-driven site screening (see
docs/site-screening/method.md); ``climate-pipeline fetch-docs`` fetches public documents with a
provenance manifest (see docs/urra-validation/regulatory.md); ``climate-pipeline catchment-grid``
and ``climate-pipeline validation`` run the pre-registered validation of the chosen reach (see
docs/urra-validation/method.md); ``climate-pipeline contract`` writes the observation record's
JSON Schema and sample records (see docs/schema/README.md); ``climate-pipeline quality``
recomputes the water-quality validations from their snapshots (see docs/water-quality/report.md);
``climate-pipeline reach`` writes a reach's sealed records, its ledger and the check against its
gauge (see docs/water-quality/reach/README.md); ``climate-pipeline ledger`` lists the frozen
artifacts of the prospective scoring (see docs/water-quality/prospective.md); ``climate-pipeline
sign`` makes and uses the post-quantum key that signs ledger heads (see docs/trust-model.md).
"""

from __future__ import annotations

import argparse
import hashlib
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
    schema.add_argument("--record-version", type=int, choices=(1, 2), default=1,
                        help="observation record version")  # fmt: skip
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
    quality = commands.add_parser(
        "quality", help="water-quality estimates v2: offline results from the snapshots"
    )
    quality.add_argument(
        "action",
        choices=("fetch", "fetch-usgs", "fetch-site", "fetch-v5", "fetch-v6", "fetch-v7",
                 "fetch-landsat", "fetch-extended", "export-lab", "stage-b-list", "run", "verify"),
        help="fetch [--stations-only]: Colombian stations and values; fetch-usgs [--sites-only]: "
        "the USGS pilot; fetch-site --site ID: every clear scene of one pilot site (v4's second "
        "reach); fetch-v5: every clear scene, turbidity and SSC of v5's gauged rivers; "
        "fetch-v6: the demo gauges' SSC samples and readings, and Landsat thermal at the Platte; "
        "fetch-v7: the Platte's water surface and gauge readings, Landsat at Baton Rouge and "
        "Belle Chasse (v7, v7.1); "
        "fetch-landsat [--stations-only]: Landsat 8/9 at the wide stations "
        "(phase 3); fetch-extended: windows within 15 days of a sample (v3); export-lab: the "
        "lab's training tables (A4); stage-b-list: the Level-1C scenes of RAdCor Stage B (v4); "
        "run: offline results; verify: recompute and compare with the MANIFEST",
    )  # fmt: skip
    quality.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    quality.add_argument("--stations-only", action="store_true",
                         help="fetch, fetch-landsat: the station list only")  # fmt: skip
    quality.add_argument("--sites-only", action="store_true", help="fetch-usgs: selection only")
    quality.add_argument("--site", default="USGS-06934500", help="fetch-site: the USGS site")
    quality.add_argument("--lab-targets", default="turbidity",
                         help="export-lab --without-river: targets, comma-separated")  # fmt: skip
    quality.add_argument(
        "--without-river", default="",
        help="export-lab: leave this river's sites out (core window; see --lab-targets)",
    )  # fmt: skip
    quality.add_argument(
        "--cache", type=Path, default=Path("pipeline/out/cache"), help="caches, relative to root"
    )
    quality.add_argument("--workers", type=int, default=8)
    quality.add_argument(
        "--config", type=Path, default=Path("pipeline/water-quality.yaml"),
        help="settings, relative to the root",
    )  # fmt: skip
    quality.add_argument(
        "--out", type=Path, default=None, help="run: results folder (default: from the config)"
    )
    reach = commands.add_parser("reach", help="observation records v2 of a reach (P3, D16)")
    reach.add_argument(
        "action",
        choices=("baseline", "run", "check", "examples", "render", "thermal", "context", "climate",
                 "score", "verify"),
        help="baseline: NIR/red and the station windows on the frozen scenes, once; run: records "
        "of the scenes after the baseline (exit 0 done, 2 partial, 3 a cap stopped it); check: a "
        "gauged reach's estimates against its gauge after the card's commit (report-only); "
        "examples: copy the newest outputs to docs/water-quality/reach/<site>/examples/; render: "
        "the reach's geometry and each recorded scene's NDTI map, beside the examples (web); "
        "thermal: water-temperature records of the Landsat passes (a reach with a temperature "
        "card); context: the gauge's own readings at each recorded pass; climate: the gauge's "
        "whole daily record and each year's extremes, beside the examples (web; --until: last "
        "day); score: the prospective outcomes of the anchored claims (rule v1, "
        "docs/water-quality/prospective.md); verify: every record's seal, the ledger chain and "
        "the cards (exit 1 on any problem)",
    )  # fmt: skip
    reach.add_argument(
        "--site", default="all",
        help="the reach's site id, or 'all' for every reach in the settings",
    )  # fmt: skip
    reach.add_argument(
        "--all-records", action="store_true",
        help="examples: every record, the whole ledger, the gauge check and the cards (web)",
    )  # fmt: skip
    reach.add_argument(
        "--since", type=date.fromisoformat, default=None,
        help="run: first day; check: first scene day (default: the card's commit)",
    )  # fmt: skip
    reach.add_argument(
        "--until", type=date.fromisoformat, default=None, help="run, climate: last day"
    )
    reach.add_argument(
        "--snapshot", action="store_true",
        help="climate: rebuild climate.json from the committed daily snapshot, fetching nothing",
    )  # fmt: skip
    reach.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    reach.add_argument(
        "--cache", type=Path, default=Path("pipeline/out/cache"), help="caches, relative to root"
    )
    reach.add_argument("--workers", type=int, default=8)
    reach.add_argument(
        "--config", type=Path, default=Path("pipeline/reach.yaml"),
        help="settings, relative to the root",
    )  # fmt: skip
    ledger = commands.add_parser(
        "ledger", help="the frozen-artifacts ledger of the prospective scoring (rule v1)"
    )
    ledger.add_argument(
        "action", choices=("freeze", "verify", "stamp", "upgrade", "proofs"),
        help="freeze PATH...: list files (their SHA-256, git blob and, for a card, its canonical "
        "hash); verify: the chain, and that every listed file is unchanged (exit 1 otherwise); "
        "stamp: an OpenTimestamps proof of every ledger head that has none (Bitcoin, no key); "
        "upgrade: the Bitcoin attestation of every pending proof; proofs: each proof's Bitcoin "
        "block, checked against two public block explorers",
    )  # fmt: skip
    ledger.add_argument("paths", nargs="*", help="freeze: files, relative to the root")
    ledger.add_argument("--purpose", default="", help="freeze: why the files are frozen")
    ledger.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    sign = commands.add_parser("sign", help="ML-DSA-65 signatures of ledger heads (FIPS 204)")
    sign.add_argument(
        "action", choices=("keygen", "heads", "verify"),
        help="keygen: the key pair, once (the private key outside the repository, the public key "
        "in docs/keys/); heads: sign every ledger head not yet signed "
        "(docs/ledgers/signatures.jsonl); verify: every signature, its chain and its head",
    )  # fmt: skip
    sign.add_argument("--key-dir", type=Path, default=None,
                      help="where the private key lives (default: ~/.riveretch)")  # fmt: skip
    sign.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    status = commands.add_parser("status", help="the daily run's status.json (the web app's panel)")
    status.add_argument("--steps", type=Path, required=True, help="the run's step log (JSON lines)")
    status.add_argument("--previous", type=Path, required=True,
                        help="the previous status.json (may not exist)")  # fmt: skip
    status.add_argument("--out", type=Path, required=True, help="where to write status.json")
    status.add_argument("--run-url", default="", help="the workflow run's URL")
    status.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
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
        from climate_pipeline.contract import observation_v2

        text = observation_v2.schema_text() if args.record_version == 2 else obs.schema_text()
        args.out.write_text(text, encoding="utf-8", newline="\n")
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


SITE_FOLDERS = {"USGS-06934500": "usgs-hermann"}  # v4: inputs folder of a second-reach site
SITE_CAP_GB = 4.0  # v4, section A: estimated network of the site's full fetch
V5_CAP_GB = 40.0  # v5: estimated network of the whole fetch (30 GB raised by deviation 11)


def quality(args: argparse.Namespace) -> int:
    """Run ``quality run`` or ``verify``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code (1 when verification finds a mismatch).
    """
    import json
    import platform
    from datetime import UTC, datetime

    from climate_pipeline.provenance import head, library_versions
    from climate_pipeline.quality.config import load_quality_config
    from climate_pipeline.quality.report import verify, write_outputs
    from climate_pipeline.quality.run import analyse

    root = args.root.resolve()
    config = root / args.config
    cfg = load_quality_config(config)
    if args.action == "export-lab":
        from climate_pipeline.quality import lab, transfer

        usgs_inputs = transfer.load_usgs(cfg, root)
        if usgs_inputs is None:
            print("no USGS snapshot yet: run quality fetch-usgs first")
            return 1
        if args.without_river:
            from climate_pipeline.quality import site

            reduced = site.without_river(usgs_inputs, args.without_river, None)
            targets = [t for t in args.lab_targets.split(",") if t]
            name = f"lab-no-{args.without_river.lower()}" + (
                "" if targets == ["turbidity"] else "-" + "-".join(targets)
            )
            folder = root / "pipeline" / "out" / name
            tables = lab.export(cfg, reduced, folder, only={(t, site.WINDOW) for t in targets})
            print(f"{len(tables)} tables in {folder}")
            return 0
        tables = lab.export(cfg, usgs_inputs, root / "pipeline" / "out" / "lab")
        print(f"{len(tables)} tables in pipeline/out/lab")
        return 0
    if args.action == "stage-b-list":
        from climate_pipeline.quality import stage_b

        scenes = stage_b.scene_list(
            cfg, root, root / args.cache, root / "pipeline" / "out" / "acolite-work-b", args.workers
        )
        products = {r["l1c_product"] for r in scenes if r["l1c_product"]}
        missing = sum(1 for r in scenes if not r["l1c_product"])
        print(f"{len(scenes)} scenes, {len(products)} Level-1C products, {missing} without one")
        return 0
    if args.action == "fetch-extended":
        from climate_pipeline.quality import extended

        counts = extended.fetch(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-landsat":
        from climate_pipeline.quality import landsat

        if args.stations_only:
            stations = landsat.select_stations(cfg, root)
            print(f"{len(stations)} Landsat stations (main channel >= 240 m)")
            return 0
        counts = landsat.fetch_values(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-site":
        from climate_pipeline.quality import usgs

        counts = usgs.fetch_values(cfg, root, root / args.cache, args.workers,
                                   site_ids={args.site}, max_clear=100_000,
                                   folder=SITE_FOLDERS.get(args.site, args.site.lower()),
                                   ssc=False, cap_gb=SITE_CAP_GB)  # fmt: skip
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-v7":
        from climate_pipeline.quality import fetch_v7

        counts = fetch_v7.fetch(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-v6":
        from climate_pipeline.quality import variables

        counts = variables.fetch(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-v5":
        from climate_pipeline.quality import usgs

        counts = usgs.fetch_values(cfg, root, root / args.cache, args.workers, max_clear=100_000,
                                   folder="usgs-v5", ssc=True, cap_gb=V5_CAP_GB,
                                   sites_file="usgs-v5/sites.csv", surrogate=True)  # fmt: skip
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch-usgs":
        from climate_pipeline.quality import usgs

        if args.sites_only:
            sites = usgs.fetch_sites(cfg, root, root / args.cache, args.workers)
            selected = sum(1 for r in sites if r.get("selected"))
            print(f"{len(sites)} candidate sites, {selected} selected")
            return 0
        counts = usgs.fetch_values(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "fetch":
        from climate_pipeline.quality.fetching import fetch_stations

        if args.stations_only:
            rows = fetch_stations(cfg, root, root / args.cache, args.workers)
            selected = sum(1 for r in rows if r.get("selected"))
            print(f"{len(rows)} candidates, {selected} selected")
            return 0
        from climate_pipeline.quality.values import fetch_values

        counts = fetch_values(cfg, root, root / args.cache, args.workers)
        print(f"snapshots: {counts}")
        return 1 if counts["read_errors"] or counts["failures"] else 0
    if args.action == "verify":
        problems, near = verify(cfg, root, config)
        for line in problems:
            print(line)
        for name in near:
            print(f"{name}: agrees to the last printed digit (floating point on this machine)")
        print("verified" if not problems else f"{len(problems)} mismatches")
        return 1 if problems else 0
    started = datetime.now(UTC).isoformat(timespec="seconds")
    out = root / args.out if args.out is not None else root / cfg.outputs.results
    write_outputs(analyse(cfg, root), cfg, root, config, out)
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


def reach(args: argparse.Namespace) -> int:
    """Run ``reach baseline`` or ``reach run``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code (``reach run``: 0 done, 2 partial, 3 a cap stopped it).
    """
    from climate_pipeline.quality.fetching import DiskBudgetError
    from climate_pipeline.reach import run as reach_run
    from climate_pipeline.reach.config import load_reach_config

    root = args.root.resolve()
    config = root / args.config
    cfg = load_reach_config(config)
    sites = [r.site for r in cfg.reaches] if args.site == "all" else [args.site]
    if args.action == "verify":
        failed = 0
        for site in sites:
            problems = reach_run.verify_outputs(cfg, root, site)
            for line in problems:
                print(f"{site}: {line}")
            print(f"{site}: " + ("verified" if not problems else f"{len(problems)} problems"))
            failed += bool(problems)
        return 1 if failed else 0
    if args.action == "examples":
        for site in sites:
            try:
                out = reach_run.write_examples(cfg, root, site, everything=args.all_records)
                print(f"{site}: {out}")
            except reach_run.ReachError as error:
                print(f"{site}: {error}")
        return 0
    if args.action == "climate":
        from climate_pipeline.reach.climate import climate

        for site in sites:
            try:
                print(
                    f"{site}: {climate(cfg, root, site, args.until, fetch_new=not args.snapshot)}"
                )
            except reach_run.ReachError as error:
                print(f"{site}: {error}")
        return 0
    if args.action in ("thermal", "context"):
        from climate_pipeline.reach import thermal

        for site in sites:
            try:
                if args.action == "thermal":
                    outcome = thermal.thermal(cfg, root, site, root / args.cache, args.since,
                                            args.until, args.workers)  # fmt: skip
                else:
                    outcome = {"context_rows": thermal.context(cfg, root, site)}
                print(f"{site}: {outcome}")
            except reach_run.ReachError as error:
                print(f"{site}: {error}")
        return 0
    if args.action == "render":
        from climate_pipeline.reach.render import render

        for site in sites:
            try:
                print(f"{site}: {render(cfg, root, site, root / args.cache, args.workers)}")
            except reach_run.ReachError as error:
                print(f"{site}: {error}")
        return 0
    if args.action == "score":
        from climate_pipeline.reach.score import SCORED, score

        for site in sites:
            if site not in SCORED:
                continue  # rule v1 scores the demo reaches only
            print(f"{site}: {score(root, cfg, site).__dict__}")
        return 0
    if args.action == "check":
        from datetime import UTC, datetime

        from climate_pipeline.reach.check import check

        for site in sites:
            reach = cfg.reach(site)
            if reach.station_source != "usgs":
                continue
            start = (datetime.combine(args.since, datetime.min.time(), tzinfo=UTC)
                     if args.since else None)  # fmt: skip
            try:
                found = check(cfg, reach, root, since=start)
            except ValueError as error:
                print(f"{site}: {error}")
                continue
            print(f"{site}: {found}")
        return 0
    codes = []
    for site in sites:
        try:
            if args.action == "baseline":
                info = reach_run.build_baseline(cfg, root, site, root / args.cache, args.workers)
                print(f"{site} baseline: {info}")
                codes.append(reach_run.EXIT_CAP if info["stopped"] else reach_run.EXIT_OK)
                continue
            summary = reach_run.run(cfg, root, site, args.since, args.until, root / args.cache,
                                    args.workers, config_path=config)  # fmt: skip
        except DiskBudgetError as error:
            print(f"{site} stopped: {error}")
            codes.append(reach_run.EXIT_CAP)
            continue
        except reach_run.ReachError as error:
            print(f"{site} cannot run: {error}")
            codes.append(1)
            continue
        print(f"{site}: {len(summary.recorded)} records, {len(summary.skipped)} skipped, "
              f"{len(summary.failed)} failed, ~{summary.network_mb / 1000:.2f} GB"
              + (f"; stopped: {summary.stopped}" if summary.stopped else ""))  # fmt: skip
        codes.append(summary.exit_code)
    return max(codes)


def sign(args: argparse.Namespace) -> int:
    """Run ``sign keygen``, ``sign heads`` or ``sign verify``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code (2 when a key exists, is missing or the key folder is inside the
        repository; ``verify``: 1 on any problem).
    """
    from climate_pipeline import signing

    root = args.root.resolve()
    key_dir = args.key_dir or signing.DEFAULT_KEY_DIR
    if args.action == "verify":
        problems = signing.verify_signatures(root)
        for line in problems:
            print(line)
        print(
            f"{signing.SIGNATURES.as_posix()}: "
            + ("verified" if not problems else f"{len(problems)} problems")
        )
        return 1 if problems else 0
    if args.action == "heads":
        secret_file = key_dir / signing.KEY_FILE
        if not secret_file.exists():
            print(f"{secret_file}: no private key (run `sign keygen` once)")
            return 2
        for done in signing.sign_heads(root, secret_file.read_text(encoding="utf-8")):
            print(f"signed    {done}")
        return 0
    try:
        secret, public = signing.keygen(root, key_dir)
    except (ValueError, FileExistsError) as error:
        print(error)
        return 2
    print(f"private key: {secret} (keep it; never commit it)")
    print(f"public key:  {public}")
    return 0


def ledger(args: argparse.Namespace) -> int:
    """Run ``ledger freeze``, ``verify``, ``stamp``, ``upgrade`` or ``proofs``.

    Args:
        args: Parsed arguments of the subcommand.

    Returns:
        The process exit code (``verify``: 1 on any problem; ``freeze``: 2 without paths;
        ``proofs``: 1 when a proof timestamps another head).
    """
    from climate_pipeline import ledgers, timestamps

    root = args.root.resolve()
    if args.action == "stamp":
        for proof in timestamps.stamp(root):
            print(f"stamped   {proof.relative_to(root).as_posix()}")
        return 0
    if args.action == "upgrade":
        for proof in timestamps.upgrade(root):
            print(f"attested  {proof.relative_to(root).as_posix()}")
        return 0
    if args.action == "proofs":
        return _proofs(root)
    if args.action == "verify":
        problems = ledgers.verify(root)
        for line in problems:
            print(line)
        print(f"{ledgers.FROZEN.as_posix()}: " + ("verified" if not problems
                                                  else f"{len(problems)} problems"))  # fmt: skip
        return 1 if problems else 0
    if not args.paths or not args.purpose:
        print("freeze needs one or more paths and --purpose")
        return 2
    done = ledgers.freeze(root, list(args.paths), args.purpose)
    for path in done.added:
        print(f"added     {path}")
    for path in done.unchanged:
        print(f"unchanged {path}")
    return 0


def _proofs(root: Path) -> int:
    from climate_pipeline import timestamps

    bad = 0
    for ledger in timestamps.ledgers(root):
        if not ledger.path.exists():
            continue
        lines = [t for t in ledger.path.read_text(encoding="utf-8").splitlines() if t.strip()]
        for k in range(1, len(lines) + 1):
            path = timestamps.proof_path(root, ledger.label, k)
            if not path.exists():
                continue
            digest = hashlib.sha256(lines[k - 1].encode()).digest()
            try:
                proof = timestamps.verify(path, digest)
            except ValueError as error:
                print(f"MISMATCH  {error}")
                bad += 1
                continue
            state = (
                f"Bitcoin block {proof.block.height} ({proof.block.time.isoformat()})"
                if proof.block
                else f"pending at {', '.join(proof.pending) or 'no calendar'}"
            )
            print(f"{ledger.label} line {k}: {state}")  # fmt: skip
    return 1 if bad else 0


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
    if args.command == "quality":
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        return quality(args)
    if args.command == "ledger":
        return ledger(args)
    if args.command == "sign":
        return sign(args)
    if args.command == "status":
        from climate_pipeline import status as run_status

        ok = run_status.write(args.root.resolve(), args.steps, args.previous, args.out,
                              args.run_url)  # fmt: skip
        print(f"{args.out}: {'ok' if ok else 'failed'}")
        return 0
    if args.command == "reach":
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        return reach(args)
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
