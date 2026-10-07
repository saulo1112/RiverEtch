from pathlib import Path

import pandas as pd

from climate_pipeline.screening.report import (
    EVENT_ROW_COLUMNS,
    RunOutputs,
    exclusion_category,
    markdown_table,
    write_all,
)


def test_exclusion_categories() -> None:
    assert exclusion_category("scaling conflict in item metadata") == "scaling metadata"
    assert exclusion_category("X: red has no raster:bands scale/offset") == "scaling metadata"
    assert exclusion_category("upstream median red reflectance -0.020 outside (0, 0.3]") == (
        "implausible water reflectance"
    )
    assert exclusion_category("too few usable water pixels in both sub-reaches") == (
        "too few water pixels"
    )


def test_markdown_table_formats_values() -> None:
    table = markdown_table([{"a": 1.23456, "b": True, "c": float("nan")}], ["a", "b", "c"])
    assert table.splitlines()[2] == "| 1.23 | yes |  |"


def test_empty_tables_still_have_headers(tmp_path: Path) -> None:
    outputs = RunOutputs(
        manifest={"period_start": "2022-01-01", "period_end": "2022-12-31", "source": "x",
                  "method_blob": "b", "config_sha256": "c", "git_commit": "g",
                  "finished_utc": "t"},
        stage1=[], scores=[], selected=[],
    )  # fmt: skip
    write_all(outputs, tmp_path / "results", tmp_path / "out")
    events = pd.read_csv(tmp_path / "results" / "event_validation.csv")
    assert tuple(events.columns) == EVENT_ROW_COLUMNS and events.empty
    assert "no eligible category A or C site" in (tmp_path / "results" / "results.md").read_text()
