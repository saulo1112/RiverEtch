"""The earlier years, 2019 to 2025 (preregistration-archive.md): the file frozen before any pass is
read, the guard that nothing reads before its anchor, what each pass was to the model, and the
index of the years written."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from climate_pipeline.reach import along, archive
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_reach_config(ROOT / "pipeline" / "reach.yaml")


def test_the_preregistration_is_frozen_before_any_pass_is_read() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    path = ROOT / archive.PREREGISTRATION
    assert listed[archive.PREREGISTRATION] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert archive.YEARS == (2019, 2020, 2021, 2022, 2023, 2024, 2025)


def test_nothing_reads_before_its_line_is_anchored(tmp_path: Path) -> None:
    (tmp_path / "docs/ledgers").mkdir(parents=True)
    (tmp_path / "docs/ledgers/frozen-artifacts.jsonl").write_text(
        json.dumps({"path": archive.PREREGISTRATION}) + "\n", encoding="utf-8")  # fmt: skip
    (tmp_path / "docs/ledgers/anchors.jsonl").write_text("", encoding="utf-8")
    assert not along.anchored(tmp_path, archive.PREREGISTRATION)
    for read in (archive.run, archive.run_temperature):
        with pytest.raises(reach_run.ReachError, match="not anchored yet"):
            read(CFG, tmp_path, "platte-louisville", tmp_path / "cache")


def test_each_pass_says_what_it_was_to_the_model() -> None:
    card = {"training": ["2018-12-01", "2023-11-30"], "lockbox": ["2023-12-01", "2026-09-30"]}
    assert archive.phase(card, date(2021, 6, 1), ungauged=False) == "training"
    assert archive.phase(card, date(2024, 6, 1), ungauged=False) == "test"
    assert archive.phase(card, date(2019, 6, 1), ungauged=True) == "unseen"
    # A card without training dates (water temperature): before the locked test is training.
    assert archive.phase(None, date(2020, 3, 1), ungauged=False) == "training"
    assert archive.phase(None, date(2025, 3, 1), ungauged=False) == "test"


def test_the_index_lists_each_year_written(tmp_path: Path) -> None:
    out = archive.folder(tmp_path, "platte-louisville")
    out.mkdir(parents=True)
    for year, passes in ((2019, 2), (2020, 0)):
        doc = {"year": year, "passes": [{}] * passes, "failed": {"k": "x"} if passes else {}}
        (out / f"{year}.json").write_text(json.dumps(doc), encoding="utf-8")
    index = json.loads(archive.write_index(tmp_path, "platte-louisville", "archive").read_text())
    assert index["years"] == [
        {"year": 2019, "passes": 2, "failed": 1},
        {"year": 2020, "passes": 0, "failed": 0},
    ]
