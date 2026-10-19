import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_pipeline import ledgers
from climate_pipeline.calibration.report import git_blob
from climate_pipeline.cli import main
from climate_pipeline.quality.cards import card_hash

ROOT = Path(__file__).parents[2]
CARD = "docs/water-quality/results/models/demo-reach/turbidity.json"
NOW = datetime(2026, 10, 19, 22, 0, tzinfo=UTC)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / "docs/water-quality/results/models/demo-reach").mkdir(parents=True)
    (tmp_path / CARD).write_text(json.dumps({"modelId": "H3", "levels": [1, 2]}, indent=2) + "\n",
                                 encoding="utf-8")  # fmt: skip
    (tmp_path / "rule.md").write_text("# Rule v1\n", encoding="utf-8")
    return tmp_path


def lines(root: Path) -> list[str]:
    return (root / ledgers.FROZEN).read_text(encoding="utf-8").splitlines()


def test_freeze_lists_each_file_with_its_hashes_and_chains_the_lines(root: Path) -> None:
    done = ledgers.freeze(root, [CARD, "rule.md"], "frozen before scoring", now=NOW)
    assert done.added == (CARD, "rule.md") and done.unchanged == ()
    first, second = (json.loads(t) for t in lines(root))
    data = (root / CARD).read_bytes()
    assert first["sha256"] == hashlib.sha256(data).hexdigest()  # what sha256sum prints
    assert first["gitBlob"] == git_blob(root / CARD)
    assert first["canonicalSha256"] == card_hash(json.loads(data))  # what records name
    assert (
        first["previousLineSha256"] is None and first["createdUtc"] == "2026-10-19T22:00:00+00:00"
    )
    assert second["previousLineSha256"] == hashlib.sha256(lines(root)[0].encode()).hexdigest()
    assert "canonicalSha256" not in second  # only cards have one
    assert ledgers.chain_ok(root / ledgers.FROZEN) and ledgers.verify(root) == []


def test_an_unchanged_file_is_not_listed_again_and_a_changed_one_is(root: Path) -> None:
    ledgers.freeze(root, [CARD, "rule.md"], "first", now=NOW)
    again = ledgers.freeze(root, [CARD, "rule.md"], "second", now=NOW)
    assert again.added == () and again.unchanged == (CARD, "rule.md")
    (root / "rule.md").write_text("# Rule v1, edited\n", encoding="utf-8")
    assert ledgers.verify(root) == ["rule.md: changed since it was frozen"]
    changed = ledgers.freeze(root, ["rule.md"], "rule edited", now=NOW)
    assert changed.added == ("rule.md",) and len(lines(root)) == 3 and ledgers.verify(root) == []


def test_a_broken_chain_is_refused_and_reported(root: Path) -> None:
    ledgers.freeze(root, [CARD, "rule.md"], "first", now=NOW)
    first, second = lines(root)
    (root / ledgers.FROZEN).write_text(f"{second}\n{first}\n", encoding="utf-8")  # reordered
    with pytest.raises(ValueError, match="hash of the line before"):
        ledgers.freeze(root, ["rule.md"], "again", now=NOW)
    assert ledgers.verify(root)[0].endswith("the chain is broken")


def test_a_missing_file_cannot_be_frozen(root: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ledgers.freeze(root, ["nope.md"], "missing", now=NOW)


def test_the_cli_freezes_and_verifies(root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["ledger", "freeze", "--root", str(root)]) == 2  # paths and a purpose are needed
    assert main(["ledger", "freeze", CARD, "--purpose", "card", "--root", str(root)]) == 0
    assert main(["ledger", "verify", "--root", str(root)]) == 0
    assert "added     " + CARD in capsys.readouterr().out
    (root / CARD).write_text("{}\n", encoding="utf-8")
    assert main(["ledger", "verify", "--root", str(root)]) == 1


def test_the_demo_cards_canonical_hash_is_the_one_their_records_name() -> None:
    # The frozen ledger's canonicalSha256 must equal what the sealed records already name.
    for site in ("mississippi-belle-chasse", "platte-louisville"):
        card = json.loads((ROOT / f"{CARD.replace('demo-reach', site)}").read_text("utf-8"))
        series = json.loads(
            (ROOT / f"docs/water-quality/reach/{site}/examples/latest.json").read_text("utf-8")
        )
        named = next(
            e["modelCardSha256"] for e in series["estimates"] if e["target"] == "turbidity"
        )
        assert card_hash(card) == named
