"""The earlier years' images (preregistration-archive-maps.md): the file frozen before any image is
drawn, the guard that nothing draws before its anchor, and that exactly the passes a year's file
lists are drawn, once, on the reach's own frame, without changing that file."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from climate_pipeline.quality import imagery
from climate_pipeline.reach import along, archive, archive_maps, render
from climate_pipeline.reach import run as reach_run
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_reach_config(ROOT / "pipeline" / "reach.yaml")
SITE = "platte-louisville"
GRID = {"width": 2, "height": 2, "corners": [[0.0, 1.0], [1.0, 1.0], [1.0, 0.0], [0.0, 0.0]]}


def test_the_preregistration_is_frozen_before_any_image_is_drawn() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    path = ROOT / archive_maps.PREREGISTRATION
    assert listed[archive_maps.PREREGISTRATION] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_nothing_draws_before_its_line_is_anchored(tmp_path: Path) -> None:
    (tmp_path / "docs/ledgers").mkdir(parents=True)
    (tmp_path / "docs/ledgers/frozen-artifacts.jsonl").write_text(
        json.dumps({"path": archive_maps.PREREGISTRATION}) + "\n", encoding="utf-8")  # fmt: skip
    (tmp_path / "docs/ledgers/anchors.jsonl").write_text("", encoding="utf-8")
    assert not along.anchored(tmp_path, archive_maps.PREREGISTRATION)
    with pytest.raises(reach_run.ReachError, match="not anchored yet"):
        archive_maps.run(CFG, tmp_path, SITE, tmp_path / "cache", years=(2019,))


class _Reader:
    def __init__(self) -> None:
        self.forgotten: list[str] = []

    def forget(self, acq: Any) -> None:
        self.forgotten.append(acq.key)


def _fake(monkeypatch: pytest.MonkeyPatch, keys: list[str]) -> dict[str, list[str]]:
    drawn: dict[str, list[str]] = {"map": [], "photo": [], "search": []}
    reader = _Reader()
    setup = SimpleNamespace(quality=None, site=SimpleNamespace(aoi_bbox=(0.0, 0.0, 1.0, 1.0)),
                            reader=reader)  # fmt: skip
    monkeypatch.setattr(along, "anchored", lambda root, prereg: True)
    monkeypatch.setattr(reach_run, "setup", lambda *a, **k: setup)
    monkeypatch.setattr(render, "Frame", lambda s: object())
    monkeypatch.setattr(archive_maps, "frame_of", lambda frame: GRID)
    monkeypatch.setattr(archive_maps, "check_disk", lambda root, gb: 100.0)
    monkeypatch.setattr(archive_maps, "head", lambda: "abc123")

    def search(*args: Any) -> tuple[list[Any], dict[str, float]]:
        drawn["search"].append(str(args[3]))
        return [SimpleNamespace(key=k) for k in keys], {}

    def scene_map(s: Any, frame: Any, acq: Any) -> np.ndarray:
        drawn["map"].append(acq.key)
        return np.zeros((2, 2, 4), dtype=np.uint8)

    def true_color(s: Any, frame: Any, acq: Any) -> np.ndarray:
        drawn["photo"].append(acq.key)
        return np.zeros((2, 2, 3), dtype=np.uint8)

    monkeypatch.setattr(imagery, "search", search)
    monkeypatch.setattr(render, "scene_map", scene_map)
    monkeypatch.setattr(render, "true_color", true_color)
    return drawn


def test_exactly_the_listed_passes_are_drawn_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    year_file = archive.folder(tmp_path, SITE) / "2019.json"
    year_file.parent.mkdir(parents=True)
    listed = [{"sceneId": f"{SITE}:s2a_2019-01-05", "date": "2019-01-05"},
              {"sceneId": f"{SITE}:s2b_2019-02-10", "date": "2019-02-10"},
              {"sceneId": f"{SITE}:s2a_2019-03-01", "date": "2019-03-01"}]  # fmt: skip
    year_file.write_text(json.dumps({"year": 2019, "passes": listed}), encoding="utf-8")
    before = year_file.read_bytes()
    # The catalogue lists one more pass (not observable, so not in the year's file) and no longer
    # lists the third one.
    drawn = _fake(monkeypatch, ["s2a_2019-01-05", "s2b_2019-02-10", "s2a_2019-01-20"])
    summary = archive_maps.run(CFG, tmp_path, SITE, tmp_path / "cache", years=(2019,))
    assert summary.read == 2 and not summary.failed
    assert drawn["map"] == drawn["photo"] == ["s2a_2019-01-05", "s2b_2019-02-10"]
    examples = year_file.parent.parent
    doc = json.loads((examples / "archive-maps/2019.json").read_text(encoding="utf-8"))
    assert doc["schema"] == archive_maps.SCHEMA and doc["codeCommit"] == "abc123"
    assert {k: doc[k] for k in GRID} == GRID
    assert [m["sceneId"] for m in doc["maps"]] == [p["sceneId"] for p in listed[:2]]
    assert doc["maps"][0]["file"] == "archive-maps/2019/s2a_2019-01-05.png"
    assert doc["maps"][0]["trueColor"] == "archive-maps/2019/s2a_2019-01-05.rgb.webp"
    for entry in doc["maps"]:
        assert (examples / entry["file"]).exists() and (examples / entry["trueColor"]).exists()
    assert doc["missing"] == [f"{SITE}:s2a_2019-03-01"]
    assert year_file.read_bytes() == before
    # A second run draws nothing already drawn: it looks again only for the missing pass.
    again = archive_maps.run(CFG, tmp_path, SITE, tmp_path / "cache", years=(2019,))
    assert again.read == 0
    assert drawn["map"] == ["s2a_2019-01-05", "s2b_2019-02-10"]
    assert drawn["search"] == ["2019-01-01", "2019-01-01"]


def test_a_year_never_read_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake(monkeypatch, [])
    with pytest.raises(reach_run.ReachError, match="no earlier year's file"):
        archive_maps.run(CFG, tmp_path, SITE, tmp_path / "cache", years=(2020,))
