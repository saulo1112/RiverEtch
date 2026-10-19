import hashlib
import json
import math
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from climate_pipeline.cli import main
from climate_pipeline.reach import score as s
from climate_pipeline.reach.config import load_reach_config

PIPELINE = Path(__file__).parents[1]
SITE = "platte-louisville"
T0 = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)


def jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows), encoding="utf-8")


def anchor(label: str, lines: int, when: datetime) -> dict[str, object]:
    return {"label": label, "lines": lines, "timestampUtc": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "block": 1, "head": "0x00", "index": 0, "subject": "0x00", "tx": "0x00"}  # fmt: skip


class Root:
    """A repository with one demo reach, its published claims and the anchoring log."""

    def __init__(self, path: Path) -> None:
        self.path = path
        shutil.copy(PIPELINE / "reach.yaml", path / "reach.yaml")
        (path / "docs/water-quality").mkdir(parents=True)
        (path / s.RULE).write_bytes(b"# Rule v1\n")  # write_text would add a CR on Windows
        jsonl(path / s.FROZEN, [{"path": "docs/water-quality/results/MANIFEST"},
                                {"path": s.RULE.as_posix()}])  # fmt: skip
        self.anchors: list[dict[str, object]] = [anchor(s.FROZEN_LABEL, 2, T0)]
        self.lines: list[dict[str, object]] = []
        self.notes: list[dict[str, object]] = []
        self.folder = s.examples(path, SITE)

    def claim(self, when: datetime, value: float | None, low: float = 10.0,
              high: float = 40.0) -> str:  # fmt: skip
        key = f"sentinel-2c_{when:%Y-%m-%d_%H%M}_R112"
        estimate: dict[str, object] = {"target": "turbidity", "unit": "FNU", "value": value,
                                       "interval": None if value is None
                                       else {"low": low, "high": high}}  # fmt: skip
        rec = {"sceneId": f"{SITE}:{key}", "recordSha256": hashlib.sha256(key.encode()).hexdigest(),
               "stacItemIds": [key], "estimates": [estimate]}  # fmt: skip
        file = f"records/{key}.json"
        (self.folder / "records").mkdir(parents=True, exist_ok=True)
        (self.folder / file).write_text(json.dumps(rec), encoding="utf-8")
        self.lines.append({"file": file, "sceneId": rec["sceneId"]})
        self.notes.append({"sceneId": rec["sceneId"], "datetimeUtc": when.isoformat()})
        return str(rec["recordSha256"])

    def write(self, anchored: int) -> None:
        jsonl(self.folder / "ledger.jsonl", self.lines)
        jsonl(self.path / f"pipeline/out/reach/{SITE}/checks/estimates.jsonl", self.notes)
        label = f"terrachain:{SITE}:observations"
        rows = [*self.anchors, *([anchor(label, anchored, T0)] if anchored else [])]
        jsonl(self.path / s.ANCHORS, rows)

    def outcomes(self) -> list[dict[str, Any]]:
        path = self.folder / s.FOLDER / "ledger.jsonl"
        return [json.loads(t) for t in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def root(tmp_path: Path) -> Root:
    return Root(tmp_path)


def gauge(value: float, approval: str = "Provisional") -> s.GaugeReader:
    def read(station: str, parameter: str, when: datetime) -> s.Reading:
        assert (station, parameter) == ("USGS-06805500", "63680")
        return s.Reading(value, approval if math.isfinite(value) else "", "median 30 min", 3)

    return read


def run(root: Root, read: s.GaugeReader, now: datetime) -> s.ScoreSummary:
    cfg = load_reach_config(root.path / "reach.yaml")
    return s.score(root.path, cfg, SITE, read=read, now=now)


def test_t0_is_the_first_frozen_anchor_that_covers_the_rule(root: Root) -> None:
    root.write(anchored=0)
    assert s.t0(root.path) == T0
    jsonl(root.path / s.ANCHORS, [anchor(s.FROZEN_LABEL, 1, T0)])  # covers the MANIFEST only
    assert s.t0(root.path) is None


def test_only_anchored_claims_after_t0_and_past_the_lag_are_scored(root: Root) -> None:
    before = root.claim(T0 - timedelta(hours=2), 20.0)
    inside = root.claim(T0 + timedelta(hours=3), 20.0)
    outside = root.claim(T0 + timedelta(hours=4), 50.0, low=35.0, high=70.0)
    root.claim(T0 + timedelta(hours=30), 20.0)  # too recent at the read below
    root.claim(T0 + timedelta(hours=5), 20.0)  # its line is not anchored yet
    root.write(anchored=4)
    summary = run(root, gauge(30.0), now=T0 + timedelta(hours=36))
    assert summary.t0 == T0.isoformat()
    assert summary.added == {"scored": 2}
    assert summary.skipped == {"retrospective: acquired before T0": 1, "not anchored yet": 1,
                               "less than 12 h since the overpass": 1}  # fmt: skip
    lines = root.outcomes()
    assert [x["claimRecordSha256"] for x in lines] == [inside, outside]
    assert [x["inside"] for x in lines] == [True, False]  # 30 is in [10, 40], not in [35, 70]
    assert lines[0]["gauge"] == {"station": "USGS-06805500", "parameter": "63680", "value": 30.0,
                                 "unit": "FNU", "approval": "Provisional",
                                 "rule": "median 30 min", "n": 3}  # fmt: skip
    assert lines[0]["ruleSha256"] == hashlib.sha256(b"# Rule v1\n").hexdigest()
    assert lines[0]["previousLineSha256"] is None
    text = (root.folder / s.FOLDER / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    assert lines[1]["previousLineSha256"] == hashlib.sha256(text[0].encode()).hexdigest()
    assert before not in [x["claimRecordSha256"] for x in lines]


def test_a_second_run_adds_nothing_until_an_approved_value_appears(root: Root) -> None:
    root.claim(T0 + timedelta(hours=1), 20.0)
    root.write(anchored=1)
    later = T0 + timedelta(days=1)
    run(root, gauge(30.0), now=later)
    assert run(root, gauge(30.0), now=later).added == {}
    assert run(root, gauge(31.0, "Approved"), now=later + timedelta(days=30)).added == {"scored": 1}
    first, approved = root.outcomes()
    assert (first["gauge"]["approval"], approved["gauge"]["approval"]) == (
        "Provisional",
        "Approved",
    )
    assert run(root, gauge(31.0, "Approved"), now=later + timedelta(days=31)).added == {}


def test_no_gauge_value_is_listed_once_then_final_after_seven_days(root: Root) -> None:
    root.claim(T0 + timedelta(hours=1), 20.0)
    root.write(anchored=1)
    missing = gauge(math.nan)
    assert run(root, missing, now=T0 + timedelta(days=1)).added == {"no gauge value": 1}
    assert run(root, missing, now=T0 + timedelta(days=2)).added == {}
    assert run(root, missing, now=T0 + timedelta(days=8)).added == {"no gauge value (final)": 1}
    assert [x["inside"] for x in root.outcomes()] == [None, None]
    assert run(root, gauge(30.0), now=T0 + timedelta(days=9)).added == {}  # final stays final


def test_an_abstained_claim_is_listed_and_never_scored(root: Root) -> None:
    root.claim(T0 + timedelta(hours=1), None)
    root.write(anchored=1)
    assert run(root, gauge(30.0), now=T0 + timedelta(days=1)).added == {"abstained (final)": 1}
    assert root.outcomes()[0]["gauge"] is None and root.outcomes()[0]["interval"] is None
    assert run(root, gauge(30.0), now=T0 + timedelta(days=2)).added == {}


def test_nothing_is_scored_before_the_rule_is_anchored(root: Root) -> None:
    root.claim(T0 + timedelta(hours=1), 20.0)
    root.write(anchored=1)
    jsonl(root.path / s.ANCHORS, [anchor(f"terrachain:{SITE}:observations", 1, T0)])
    summary = run(root, gauge(30.0), now=T0 + timedelta(days=1))
    assert summary.t0 is None and summary.added == {}


def test_only_the_demo_reaches_are_scored(root: Root) -> None:
    cfg = load_reach_config(root.path / "reach.yaml")
    with pytest.raises(ValueError, match="scores only"):
        s.score(root.path, cfg, "missouri-hermann", read=gauge(30.0))
    root.write(anchored=0)
    args = ["reach", "score", "--site", "missouri-hermann", "--root", str(root.path),
            "--config", "reach.yaml"]  # fmt: skip
    assert main(args) == 0  # skipped, not an error
