"""Command-line entry point of the pipeline.

The stages (Sentinel-2 ingestion, turbidity indices, anomaly detection and rainfall
correlation) are not implemented yet; this placeholder proves packaging and tooling work.
"""

from climate_pipeline import __version__


def main() -> int:
    """Run the pipeline command-line interface.

    Returns:
        The process exit code.
    """
    print(f"climate-pipeline {__version__}: scaffold only, no stages implemented yet.")
    return 0
