"""Bitcoin timestamps of ledger heads (OpenTimestamps): a real Bitcoin-attested example proof
verifies against its block header and fails against any other; a pending proof stays pending;
stamping and upgrading work offline with injected calendars; the ledger list mirrors the anchor
script's.

The fixtures ``hello-world.txt(.ots)`` and ``incomplete.txt(.ots)`` are the example proofs of
github.com/opentimestamps/opentimestamps-client (``examples/``, commit 5d5d325b2a70)."""

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.timestamp import Timestamp

from climate_pipeline import timestamps
from climate_pipeline.reach.score import SCORED

FIXTURES = Path(__file__).parent / "fixtures" / "ots"
REPO = Path(__file__).parents[2]
# Block 358391, as mempool.space and blockstream.info both print it (checked 2026-10-20).
BLOCK = timestamps.Block(
    358391,
    "8a1b66ecb7cbd07d8139a7e7d7f2c41aab1f5009b8364aaf61d03ad245e47e00",
    datetime(2015, 5, 28, 15, 41, 18, tzinfo=UTC),
)


def digest_of(name: str) -> bytes:
    return hashlib.sha256((FIXTURES / name).read_bytes()).digest()


def test_a_bitcoin_attested_proof_verifies_against_its_block_header() -> None:
    proof = timestamps.verify(FIXTURES / "hello-world.txt.ots", digest_of("hello-world.txt"),
                              lambda h: BLOCK if h == BLOCK.height else None)  # fmt: skip
    assert proof.block == BLOCK and proof.pending == ()


def test_another_header_or_another_digest_does_not_verify() -> None:
    wrong = timestamps.Block(BLOCK.height, "00" * 32, BLOCK.time)
    proof = timestamps.verify(FIXTURES / "hello-world.txt.ots", digest_of("hello-world.txt"),
                              lambda h: wrong)  # fmt: skip
    assert proof.block is None
    with pytest.raises(ValueError, match="another head"):
        timestamps.verify(FIXTURES / "hello-world.txt.ots", b"\x00" * 32, lambda h: BLOCK)


def test_a_pending_proof_names_its_calendar() -> None:
    proof = timestamps.verify(FIXTURES / "incomplete.txt.ots", digest_of("incomplete.txt"),
                              lambda h: None)  # fmt: skip
    assert proof.block is None
    assert proof.pending == ("https://alice.btc.calendar.opentimestamps.org",)


def ledger_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs" / "ledgers").mkdir(parents=True)
    (root / timestamps.FROZEN).write_text('{"a":1}\n{"b":2}\n', encoding="utf-8")
    return root


def test_stamp_writes_one_proof_per_new_head_and_upgrade_adds_the_block(tmp_path: Path) -> None:
    root = ledger_repo(tmp_path)

    def submit(url: str, commitment: bytes) -> Timestamp:
        t = Timestamp(commitment)
        t.attestations.add(PendingAttestation(url))
        return t

    written = timestamps.stamp(root, ("https://calendar.test",), submit)
    head = hashlib.sha256(b'{"b":2}').digest()
    assert written == [timestamps.proof_path(root, "terrachain:riveretch:frozen-artifacts", 2)]
    assert written[0].name == "terrachain_riveretch_frozen-artifacts.2.ots"
    assert timestamps.stamp(root, ("https://calendar.test",), submit) == []  # already stamped
    assert timestamps.verify(written[0], head, lambda h: None).pending == ("https://calendar.test",)

    def fetch(url: str, commitment: bytes) -> Timestamp:
        t = Timestamp(commitment)
        t.attestations.add(BitcoinBlockHeaderAttestation(800000))
        return t

    assert timestamps.upgrade(root, fetch) == written
    # The fake block's Merkle root is the commitment itself, byte-reversed as explorers print it.
    proof = timestamps.read(written[0])
    msg = next(m for m, a in proof.timestamp.all_attestations()
               if isinstance(a, BitcoinBlockHeaderAttestation))  # fmt: skip
    block = timestamps.Block(800000, msg[::-1].hex(), datetime(2026, 10, 20, tzinfo=UTC))
    assert timestamps.verify(written[0], head, lambda h: block).block == block
    assert timestamps.upgrade(root, fetch) == []  # nothing pending is answered twice


def test_no_calendar_answering_is_an_error(tmp_path: Path) -> None:
    root = ledger_repo(tmp_path)

    def down(url: str, commitment: bytes) -> Timestamp:
        raise OSError("down")

    with pytest.raises(RuntimeError, match="no OpenTimestamps calendar"):
        timestamps.stamp(root, ("https://calendar.test",), down)


def test_the_ledgers_are_the_ones_the_anchor_script_anchors() -> None:
    script = (REPO / "contracts" / "scripts" / "ledgers.ts").read_text(encoding="utf-8")
    anchored = re.search(r"REACHES_ANCHORED = \[(.*?)\]", script)
    assert anchored is not None
    assert tuple(re.findall(r'"([a-z-]+)"', anchored.group(1))) == SCORED
    ungauged = re.search(r"REACHES_UNGAUGED = \[(.*?)\]", script)
    assert ungauged is not None
    assert tuple(re.findall(r'"([a-z-]+)"', ungauged.group(1))) == timestamps.UNGAUGED
    labels = [ledger.label for ledger in timestamps.ledgers(REPO)]
    assert labels[0] == "terrachain:riveretch:frozen-artifacts"
    demo = [f"terrachain:{r}:{k}" for r in SCORED
            for k in ("observations", "water-temperature", "outcomes")]  # fmt: skip
    ungauged_obs = [f"terrachain:{r}:observations" for r in timestamps.UNGAUGED]
    along = [f"terrachain:{r}:along" for r in (*SCORED, *timestamps.UNGAUGED)]
    along_temperature = [f"terrachain:{r}:along-temperature" for r in SCORED]
    daily = [f"terrachain:{r}:daily-record" for r in (*SCORED, *timestamps.UNGAUGED)]
    assert labels[1:] == [*demo, *ungauged_obs, *along, *along_temperature, *daily]
    # The anchor script lists each reach's along ledgers too (preregistration-along-river.md and
    # preregistration-along-temperature.md).
    assert "terrachain:${reach}:along" in script
    assert "terrachain:${reach}:along-temperature" in script
    # And each reach's daily flow record (preregistration-daily-record.md).
    assert "terrachain:${reach}:daily-record" in script
