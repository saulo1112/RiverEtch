"""Turbidity along the river (preregistration-along-river.md): the plans frozen with it, the guard
that nothing reads before its anchor, the seal and the check of an along-river record, and the
phases of a station's earlier years."""

from __future__ import annotations

import hashlib
import itertools
import json
import shutil
from datetime import date
from pathlib import Path

from climate_pipeline.quality import cards
from climate_pipeline.reach import along, history
from climate_pipeline.reach.config import load_reach_config

ROOT = Path(__file__).resolve().parents[2]
CFG = load_reach_config(ROOT / "pipeline" / "reach.yaml")
SITES = ("mississippi-belle-chasse", "platte-louisville", "mississippi-st-joseph", "firat-birecik")


def test_each_reach_has_a_frozen_plan_listed_with_the_preregistration() -> None:
    frozen = [json.loads(t) for t in (ROOT / "docs/ledgers/frozen-artifacts.jsonl")
              .read_text(encoding="utf-8").splitlines() if t.strip()]  # fmt: skip
    listed = {x["path"]: x["sha256"] for x in frozen}
    assert along.PREREGISTRATION in listed
    for site in SITES:
        path = along.plan_path(ROOT, site)
        rel = path.relative_to(ROOT).as_posix()
        assert listed[rel] == hashlib.sha256(path.read_bytes()).hexdigest()
        plan = json.loads(path.read_text(encoding="utf-8"))
        assert plan["spacingM"] == along.SPACING_M and plan["firstM"] == along.FIRST_M
        assert plan["card"] == along.card_path(CFG, site)
        chain = [w["chainageM"] for w in plan["windows"]]
        assert chain[0] == along.FIRST_M
        assert all(b - a == along.SPACING_M for a, b in itertools.pairwise(chain))


def test_the_us_reaches_read_the_us_card_and_birecik_its_own() -> None:
    assert along.card_path(CFG, "firat-birecik").endswith("firat-birecik/turbidity-4.json")
    for site in SITES[:3]:
        assert along.card_path(CFG, site) == along.US_CARD
    us = json.loads((ROOT / along.US_CARD).read_text(encoding="utf-8"))
    own = json.loads((ROOT / along.card_path(CFG, "firat-birecik")).read_text(encoding="utf-8"))
    assert us["parametersHash"] == own["parametersHash"]  # the same model


def _root(tmp: Path, anchored_lines: int | None) -> Path:
    (tmp / "docs/ledgers").mkdir(parents=True)
    lines = [{"path": "docs/a.md"}, {"path": "docs/b.md"}, {"path": along.PREREGISTRATION}]
    (tmp / "docs/ledgers/frozen-artifacts.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")  # fmt: skip
    log = [] if anchored_lines is None else [{"label": along.FROZEN_LABEL, "lines": anchored_lines}]
    (tmp / "docs/ledgers/anchors.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in log), encoding="utf-8")  # fmt: skip
    return tmp


def test_nothing_reads_before_the_preregistrations_line_is_anchored(tmp_path: Path) -> None:
    assert not along.anchored(_root(tmp_path / "none", None))
    assert not along.anchored(_root(tmp_path / "short", 2))  # an anchor before its line
    assert along.anchored(_root(tmp_path / "covered", 3))
    assert not along.anchored(tmp_path / "empty")


def test_a_record_is_sealed_over_its_canonical_json_and_its_check_catches_an_edit(
    tmp_path: Path,
) -> None:
    site = "firat-birecik"
    plan = along.plan_path(tmp_path, site)
    plan.parent.mkdir(parents=True)
    shutil.copyfile(along.plan_path(ROOT, site), plan)
    card_rel = along.card_path(CFG, site)
    (tmp_path / card_rel).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / card_rel, tmp_path / card_rel)
    card = json.loads((ROOT / card_rel).read_text(encoding="utf-8"))
    doc = {
        "schema": along.SCHEMA, "reach": site, "sceneId": f"{site}:k", "date": "2026-10-20",
        "observationRecordSha256": "0" * 64,
        "planSha256": hashlib.sha256(plan.read_bytes()).hexdigest(), "card": card_rel,
        "modelCardSha256": cards.card_hash(card), "modelId": card["modelId"],
        "basis": card["basis"], "items": [],
        "windows": [{"id": "w01", "fnuClass": "under_30"}, {"id": "w02", "abstainReason": "x"}],
        "codeCommit": "c",
    }  # fmt: skip
    doc["recordSha256"] = along.seal(doc)
    assert along.seal(doc) == doc["recordSha256"]  # the seal leaves itself out
    out = along.folder(CFG, tmp_path, site)
    (out / "records").mkdir(parents=True)
    file = "records/2026-10-20_k.json"
    (out / file).write_text(json.dumps(doc), encoding="utf-8")
    along._append(out / "ledger.jsonl", doc, file, "2026-10-22T00:00:00+00:00")
    assert along.verify(CFG, tmp_path, site) == []
    assert along.series(CFG, tmp_path, site)[0]["classes"] == ["under_30", None]
    doc["windows"][0]["fnuClass"] = "30_to_50"  # change one class
    (out / file).write_text(json.dumps(doc), encoding="utf-8")
    assert any("no longer matches its seal" in p for p in along.verify(CFG, tmp_path, site))


def test_a_stations_earlier_years_say_what_they_were_to_the_card() -> None:
    card = {"training": ["2018-12-01", "2023-11-30"], "lockbox": ["2023-12-01", "2026-09-30"]}
    assert history._phase(card, date(2021, 6, 1), ungauged=False) == "training"
    assert history._phase(card, date(2024, 6, 1), ungauged=False) == "test"
    assert history._phase(card, date(2026, 10, 1), ungauged=False) == "after"
    assert history._phase(card, date(2021, 6, 1), ungauged=True) == "unseen"
