"""The daily run's status (``climate-pipeline status``): steps and exit codes, the last success,
the newest sealed record, anchor and Bitcoin timestamp, and failures that carry over."""

import json
from datetime import UTC, datetime
from pathlib import Path

from climate_pipeline import status, timestamps

FIXTURES = Path(__file__).parent / "fixtures" / "ots"
NOW = datetime(2026, 10, 21, 0, 30, tzinfo=UTC)
BLOCK = timestamps.Block(358391, "8a1b66ecb7cbd07d8139a7e7d7f2c41aab1f5009b8364aaf61d03ad245e47e00",
                         datetime(2015, 5, 28, 15, 41, 18, tzinfo=UTC))  # fmt: skip


def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    examples = root / "docs/water-quality/reach/platte-louisville/examples"
    (examples / "thermal").mkdir(parents=True)
    (examples / "series.json").write_text(json.dumps([
        {"date": "2026-10-10", "sceneId": "platte-louisville:sentinel-2c_2026-10-10_R112"},
    ]), encoding="utf-8")  # fmt: skip
    (examples / "thermal" / "series.json").write_text(json.dumps([
        {"date": "2026-10-13", "sceneId": "platte-louisville:landsat-9_2026-10-13_R028"},
    ]), encoding="utf-8")  # fmt: skip
    (root / "docs/ledgers/ots").mkdir(parents=True)
    for name in ("hello-world.txt.ots", "incomplete.txt.ots"):
        (root / "docs/ledgers/ots" / name).write_bytes((FIXTURES / name).read_bytes())
    anchor = {"label": "terrachain:riveretch:frozen-artifacts", "lines": 11, "block": 12000000,
              "index": 1, "timestampUtc": "2026-10-20T02:00:00Z", "tx": "0xab"}  # fmt: skip
    (root / "docs/ledgers/anchors.jsonl").write_text(json.dumps(anchor) + "\n", encoding="utf-8")
    return root


def test_a_good_run_reports_the_newest_record_anchor_and_timestamp(tmp_path: Path) -> None:
    root = repo(tmp_path)
    steps = [{"args": "reach score --site all", "exit": 0, "last": ""},
             {"args": "reach run --site all", "exit": 2, "last": "partial"}]  # fmt: skip
    doc = status.build(root, steps, None, "https://run/1", NOW, lambda h: BLOCK)
    assert doc["run"]["ok"] is True and doc["lastSuccessUtc"] == "2026-10-21T00:30:00+00:00"
    assert doc["lastSealed"]["sceneId"].endswith("landsat-9_2026-10-13_R028")
    assert doc["lastAnchor"]["block"] == 12000000
    assert doc["lastBitcoin"] == {"file": "docs/ledgers/ots/hello-world.txt.ots", "height": 358391,
                                  "blockTime": "2015-05-28T15:41:18+00:00"}  # fmt: skip
    assert doc["pendingBitcoin"] == 1 and doc["failures"] == []
    assert doc["outcomes"] == []  # no reach has an outcomes ledger yet
    assert doc["proofs"] == []  # the fixtures are not named after a ledger


def test_a_failed_step_is_recorded_and_the_last_success_carries_over(tmp_path: Path) -> None:
    root = repo(tmp_path)
    old = {"utc": "x", "run": "r", "step": "s", "exit": 1, "reason": "old"}
    previous = {"lastSuccessUtc": "2026-10-20T13:10:00+00:00", "failures": [old]}
    steps = [{"args": "reach run --site all", "exit": 1, "last": "Earth Search timed out"}]
    doc = status.build(root, steps, previous, "https://run/2", NOW, lambda h: None)
    assert doc["run"]["ok"] is False
    assert doc["lastSuccessUtc"] == "2026-10-20T13:10:00+00:00"
    assert [f["reason"] for f in doc["failures"]] == ["old", "Earth Search timed out"]
    assert doc["lastBitcoin"]["blockTime"] is None  # the explorers did not answer
    assert status.build(root, [], None, "https://run/3", NOW, lambda h: None)["run"]["ok"] is False


def test_proofs_list_each_ledger_head_with_its_block(tmp_path: Path) -> None:
    root = repo(tmp_path)
    named = root / timestamps.proof_path(root, "terrachain:platte-louisville:observations", 16)
    named.write_bytes((FIXTURES / "hello-world.txt.ots").read_bytes())
    pending = timestamps.proof_path(root, "terrachain:riveretch:frozen-artifacts", 11)
    pending.write_bytes((FIXTURES / "incomplete.txt.ots").read_bytes())
    assert status.proofs(root) == [
        {"label": "terrachain:platte-louisville:observations", "lines": 16,
         "file": "docs/ledgers/ots/terrachain_platte-louisville_observations.16.ots",
         "height": 358391},
        {"label": "terrachain:riveretch:frozen-artifacts", "lines": 11,
         "file": "docs/ledgers/ots/terrachain_riveretch_frozen-artifacts.11.ots", "height": None},
    ]  # fmt: skip
