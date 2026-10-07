"""Command-line entry point of the pipeline.

``climate-pipeline screening`` runs the data-driven site screening (see
docs/site-screening/method.md). The other stages (operational ingestion, anomaly publication)
are not implemented yet.
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
    screening.add_argument("--workers", type=int, default=8)
    screening.add_argument(
        "--results", type=Path, default=None, help="where generated tables go (default: docs)"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the pipeline command-line interface.

    Args:
        argv: Arguments (default: the process arguments).

    Returns:
        The process exit code.
    """
    parser = _parser()
    args = parser.parse_args(argv)
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
    if args.results is not None:
        paths = type(paths)(**{**paths.__dict__, "results": args.results.resolve()})
    outputs = run_screening(
        paths,
        source_name=args.source,
        only_sites=tuple(s.strip() for s in args.sites.split(",") if s.strip()),
        period=(args.start, args.end) if args.start else None,
        stage2=not args.stage1_only,
        workers=args.workers,
    )
    print(f"stage-2 sites: {', '.join(outputs.selected) or 'none'}; results in {paths.results}")
    return 0
