"""The committed frontend examples stay valid, sealed records with a chained ledger tail."""

import hashlib
import itertools
import json
from pathlib import Path

import jsonschema  # type: ignore[import-untyped]
import pytest

from climate_pipeline.contract import observation_v2 as v2

DOCS = Path(__file__).parents[2] / "docs"
SCHEMA = json.loads((DOCS / "schema" / "observation-record.v2.schema.json").read_text("utf-8"))
EXAMPLES = sorted((DOCS / "water-quality" / "reach").glob("*/examples"))
RECORDS = sorted(p for e in EXAMPLES for p in [e / "latest.json", *(e / "records").glob("*.json")])


@pytest.mark.parametrize("path", RECORDS, ids=lambda p: f"{p.parts[-3]}/{p.name}")
def test_an_example_record_is_valid_and_sealed(path: Path) -> None:
    data = json.loads(path.read_text("utf-8"))
    jsonschema.Draft202012Validator(SCHEMA).validate(data)
    assert v2.is_sealed(v2.ObservationRecordV2.model_validate(data))


@pytest.mark.parametrize("folder", EXAMPLES, ids=lambda p: p.parent.name)
def test_an_example_ledger_tail_is_chained_and_names_its_records(folder: Path) -> None:
    lines = (folder / "ledger.tail.jsonl").read_text("utf-8").splitlines()
    for before, after in itertools.pairwise(lines):
        previous = hashlib.sha256(before.encode()).hexdigest()
        assert json.loads(after)["previousLineSha256"] == previous
    named = {json.loads(t)["recordSha256"] for t in lines}
    for path in (folder / "records").glob("*.json"):
        assert json.loads(path.read_text("utf-8"))["recordSha256"] in named
