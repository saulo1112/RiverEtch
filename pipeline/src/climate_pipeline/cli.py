"""Command-line entry point of the pipeline.

``climate-pipeline screening`` runs the data-driven site screening (see
docs/site-screening/method.md); ``climate-pipeline fetch-docs`` fetches public documents with a
provenance manifest (see docs/urra-validation/regulatory.md). The other stages (operational
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
