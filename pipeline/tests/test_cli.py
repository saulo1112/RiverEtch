from importlib.metadata import version

import pytest

from climate_pipeline import __version__
from climate_pipeline.cli import main


def test_version_matches_package_metadata() -> None:
    assert __version__ == version("climate-pipeline")


def test_main_reports_scaffold_and_exits_successfully(capsys: pytest.CaptureFixture[str]) -> None:
    assert main() == 0
    assert "scaffold only" in capsys.readouterr().out
