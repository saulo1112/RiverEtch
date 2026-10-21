"""The committed frontend examples stay valid, sealed records with a chained ledger."""

import hashlib
import itertools
import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from climate_pipeline.contract import observation_v2 as v2
from climate_pipeline.contract import thermal
from climate_pipeline.quality import cards

DOCS = Path(__file__).parents[2] / "docs"
SCHEMA = json.loads((DOCS / "schema" / "observation-record.v2.schema.json").read_text("utf-8"))
EXAMPLES = sorted((DOCS / "water-quality" / "reach").glob("*/examples"))
RECORDS = sorted(p for e in EXAMPLES for p in [e / "latest.json", *(e / "records").glob("*.json")])
THERMAL = sorted(e / "thermal" for e in EXAMPLES if (e / "thermal").exists())


def ledger(folder: Path) -> list[str]:
    path = folder / "ledger.jsonl"  # the whole ledger (a demo reach), else its tail
    return (path if path.exists() else folder / "ledger.tail.jsonl").read_text("utf-8").splitlines()


@pytest.mark.parametrize("path", RECORDS, ids=lambda p: f"{p.parts[-3]}/{p.name}")
def test_an_example_record_is_valid_and_sealed(path: Path) -> None:
    data = json.loads(path.read_text("utf-8"))
    jsonschema.Draft202012Validator(SCHEMA).validate(data)
    assert v2.is_sealed(v2.ObservationRecordV2.model_validate(data))


@pytest.mark.parametrize("folder", EXAMPLES, ids=lambda p: p.parent.name)
def test_an_example_ledger_is_chained_and_names_its_records(folder: Path) -> None:
    lines = ledger(folder)
    for before, after in itertools.pairwise(lines):
        previous = hashlib.sha256(before.encode()).hexdigest()
        assert json.loads(after)["previousLineSha256"] == previous
    named = {json.loads(t)["recordSha256"] for t in lines}
    for path in (folder / "records").glob("*.json"):
        assert json.loads(path.read_text("utf-8"))["recordSha256"] in named


def frozen_card_hashes() -> set[str]:
    path = DOCS / "ledgers" / "frozen-artifacts.jsonl"
    lines = [json.loads(t) for t in path.read_text("utf-8").splitlines() if t.strip()]
    return {x["canonicalSha256"] for x in lines if "canonicalSha256" in x}


@pytest.mark.parametrize("folder", EXAMPLES, ids=lambda p: p.parent.name)
def test_an_example_card_is_the_one_its_records_name(folder: Path) -> None:
    copied = {p.stem: json.loads(p.read_text("utf-8")) for p in (folder / "cards").glob("*.json")}
    records = [json.loads(p.read_text("utf-8")) for p in (folder / "records").glob("*.json")]
    # A pass read again with a newer card keeps its earlier record, which names an earlier card:
    # one that is frozen, and only on a record that a newer one replaces.
    replaced = {r["supersedes"] for r in records if "supersedes" in r}
    frozen = frozen_card_hashes()
    for record in records:
        for estimate in record["estimates"]:
            card = copied.get(estimate["target"])
            if card is not None and estimate.get("modelCardSha256"):
                if record["recordSha256"] in replaced:
                    assert estimate["modelCardSha256"] in frozen
                else:
                    assert cards.card_hash(card) == estimate["modelCardSha256"]


@pytest.mark.parametrize("folder", THERMAL, ids=lambda p: p.parents[1].name)
def test_the_water_temperature_examples_are_sealed_chained_and_name_their_card(
    folder: Path,
) -> None:
    lines = (folder / "ledger.jsonl").read_text("utf-8").splitlines()
    for before, after in itertools.pairwise(lines):
        assert (
            json.loads(after)["previousLineSha256"] == hashlib.sha256(before.encode()).hexdigest()
        )
    named = {json.loads(t)["recordSha256"] for t in lines}
    card = json.loads((folder.parent / "cards" / "water_temperature.json").read_text("utf-8"))
    info = json.loads((folder.parent / "reach.json").read_text("utf-8"))
    assert info["cards"]["water_temperature"] == "cards/water_temperature.json"
    records = sorted((folder / "records").glob("*.json"))
    assert records
    for path in records:
        record = thermal.ThermalRecordV1.model_validate_json(path.read_text("utf-8"))
        assert thermal.is_sealed(record)
        assert record.record_sha256 in named
        assert record.estimate.model_card_sha256 == cards.card_hash(card)
