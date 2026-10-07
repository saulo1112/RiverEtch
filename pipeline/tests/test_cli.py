from importlib.metadata import version

import pytest

from climate_pipeline import __version__
from climate_pipeline.cli import main


def test_version_matches_package_metadata() -> None:
    assert __version__ == version("climate-pipeline")


def test_main_without_a_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "screening" in capsys.readouterr().out


def test_start_and_end_go_together() -> None:
    with pytest.raises(SystemExit):
        main(["screening", "--start", "2022-01-01"])
