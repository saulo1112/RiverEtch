"""Bitcoin timestamps of ledger heads (OpenTimestamps; rule v2, prospective-v2.md).

A head is the SHA-256 of a ledger's last line; each line names the one before, so the head commits
to every line above it. ``stamp`` submits each ledger's current head to public OpenTimestamps
calendars and keeps the proof in ``docs/ledgers/ots/`` (``<label>.<lines>.ots``, the label's
colons as underscores). Within hours a calendar commits it to a Bitcoin block, and ``upgrade``
fetches that attestation into the proof. ``verify`` replays a proof's hash path to the Merkle root
of the attesting block's header, read from public block explorers (two must agree). No key and no
signature are involved: Bitcoin's proof of work and SHA-256 carry the evidence.

The ledgers are the ones ``contracts/scripts/ledgers.ts`` anchors on Sepolia.
"""

from __future__ import annotations

import hashlib
import io
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from opentimestamps.calendar import RemoteCalendar
from opentimestamps.core.notary import BitcoinBlockHeaderAttestation, PendingAttestation
from opentimestamps.core.op import OpAppend, OpSHA256
from opentimestamps.core.serialize import (
    StreamDeserializationContext,
    StreamSerializationContext,
)
from opentimestamps.core.timestamp import DetachedTimestampFile, Timestamp

from climate_pipeline.reach.score import SCORED

# preregistration-transfer.md, section 5; preregistration-outside-us.md (outside the tested region)
UNGAUGED = ("mississippi-st-joseph", "firat-birecik")

OTS_DIR = Path("docs/ledgers/ots")
FROZEN = Path("docs/ledgers/frozen-artifacts.jsonl")
CALENDARS = (
    "https://alice.btc.calendar.opentimestamps.org",
    "https://bob.btc.calendar.opentimestamps.org",
    "https://finney.calendar.eternitywall.com",
    "https://btc.calendar.catallaxy.com",
)
EXPLORERS = ("https://mempool.space/api", "https://blockstream.info/api")
TIMEOUT = 30  # seconds, per calendar or explorer request


@dataclass(frozen=True)
class Ledger:
    """One timestamped ledger: its label and file."""

    label: str
    path: Path


@dataclass(frozen=True)
class Block:
    """A Bitcoin block header's fields that a proof is checked against."""

    height: int
    merkle_root: str  # as explorers print it (byte-reversed)
    time: datetime


@dataclass(frozen=True)
class Proof:
    """What a proof shows about one head."""

    path: Path
    digest: str  # the head it timestamps, hex
    block: Block | None  # the earliest attesting block (None: pending)
    pending: tuple[str, ...]  # calendars still to answer


HeaderReader = Callable[[int], Block | None]


def ledgers(root: Path) -> list[Ledger]:
    """The ledgers that are timestamped, as ``contracts/scripts/ledgers.ts`` lists them.

    Args:
        root: Repository root.

    Returns:
        Frozen artifacts, then each demo reach's observations, water temperature and outcomes,
        then each ungauged reach's observations (no gauge: no outcomes).
    """
    out = [Ledger("terrachain:riveretch:frozen-artifacts", root / FROZEN)]
    reaches = root / "docs" / "water-quality" / "reach"
    for reach in SCORED:
        folder = reaches / reach / "examples"
        for kind, file in (("observations", "ledger.jsonl"),
                           ("water-temperature", "thermal/ledger.jsonl"),
                           ("outcomes", "outcomes/ledger.jsonl")):  # fmt: skip
            out.append(Ledger(f"terrachain:{reach}:{kind}", folder / file))
    for reach in UNGAUGED:
        out.append(Ledger(f"terrachain:{reach}:observations",
                          reaches / reach / "examples" / "ledger.jsonl"))  # fmt: skip
    return out


def head(path: Path) -> tuple[bytes, int] | None:
    """A ledger's head (the SHA-256 of its last line) and its line count.

    Args:
        path: The ledger.

    Returns:
        ``(head, lines)``; None for a missing or empty ledger.
    """
    if not path.exists():
        return None
    lines = [t for t in path.read_text(encoding="utf-8").splitlines() if t.strip()]
    if not lines:
        return None
    return hashlib.sha256(lines[-1].encode()).digest(), len(lines)


def proof_path(root: Path, label: str, lines: int) -> Path:
    """Where a head's proof lives.

    Args:
        root: Repository root.
        label: The ledger's label.
        lines: Its line count at that head.

    Returns:
        ``docs/ledgers/ots/<label>.<lines>.ots``.
    """
    return root / OTS_DIR / f"{label.replace(':', '_')}.{lines}.ots"


def read(path: Path) -> DetachedTimestampFile:
    """A proof file.

    Args:
        path: The ``.ots`` file.

    Returns:
        The detached timestamp.
    """
    with path.open("rb") as handle:
        return DetachedTimestampFile.deserialize(StreamDeserializationContext(handle))


def _write(path: Path, proof: DetachedTimestampFile) -> None:
    buffer = io.BytesIO()
    proof.serialize(StreamSerializationContext(buffer))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue())


def stamp_digest(digest: bytes, calendars: Sequence[str] = CALENDARS,
                 submit: Callable[[str, bytes], Timestamp] | None = None
                 ) -> DetachedTimestampFile:  # fmt: skip
    """A new proof of a digest, submitted to the calendars (as ``ots stamp`` does).

    A random nonce is appended before hashing, so the calendars learn nothing about the head.

    Args:
        digest: The head (32 bytes).
        calendars: Calendar URLs.
        submit: ``(url, commitment) -> timestamp`` (default: the calendar's HTTP API).

    Returns:
        The proof, with one pending attestation per calendar that answered.

    Raises:
        RuntimeError: When no calendar answered.
    """
    proof = DetachedTimestampFile(OpSHA256(), Timestamp(digest))
    commitment = proof.timestamp.ops.add(OpAppend(os.urandom(16))).ops.add(OpSHA256())
    send = submit or (lambda url, msg: RemoteCalendar(url).submit(msg, timeout=TIMEOUT))
    answered = 0
    for url in calendars:
        try:
            commitment.merge(send(url, commitment.msg))
        except Exception:  # a calendar down or slow: the others suffice
            continue
        answered += 1
    if answered == 0:
        raise RuntimeError("no OpenTimestamps calendar answered")
    return proof


def stamp(root: Path, calendars: Sequence[str] = CALENDARS,
          submit: Callable[[str, bytes], Timestamp] | None = None) -> list[Path]:  # fmt: skip
    """Stamp every ledger whose current head has no proof yet.

    Args:
        root: Repository root.
        calendars: Calendar URLs.
        submit: Injected calendar call (tests).

    Returns:
        The proofs written.
    """
    written = []
    for ledger in ledgers(root):
        current = head(ledger.path)
        if current is None:
            continue
        path = proof_path(root, ledger.label, current[1])
        if path.exists():
            continue
        _write(path, stamp_digest(current[0], calendars, submit))
        written.append(path)
    return written


def upgrade(root: Path, fetch: Callable[[str, bytes], Timestamp] | None = None) -> list[Path]:
    """Ask the calendars for the Bitcoin attestation of every pending proof.

    Args:
        root: Repository root.
        fetch: ``(calendar url, commitment) -> timestamp`` (default: the calendar's HTTP API).

    Returns:
        The proofs that gained an attestation.
    """
    get = fetch or (lambda url, msg: RemoteCalendar(url).get_timestamp(msg, timeout=TIMEOUT))
    changed = []
    for path in sorted((root / OTS_DIR).glob("*.ots")):
        proof = read(path)
        before = _attested(proof.timestamp)
        for msg, attestation in list(proof.timestamp.all_attestations()):
            if not isinstance(attestation, PendingAttestation):
                continue
            try:
                found = get(attestation.uri, msg)
            except Exception:  # not ready yet, or the calendar is down
                continue
            _node(proof.timestamp, msg).merge(found)
        if _attested(proof.timestamp) > before:
            _write(path, proof)
            changed.append(path)
    return changed


def _attested(timestamp: Timestamp) -> int:
    return sum(1 for _, a in timestamp.all_attestations()
               if isinstance(a, BitcoinBlockHeaderAttestation))  # fmt: skip


def _node(timestamp: Timestamp, msg: bytes) -> Timestamp:
    # The sub-timestamp whose message is msg (where a pending attestation hangs).
    found = _find(timestamp, msg)
    if found is None:
        raise KeyError(msg.hex())
    return found


def _find(timestamp: Timestamp, msg: bytes) -> Timestamp | None:
    if timestamp.msg == msg:
        return timestamp
    for child in timestamp.ops.values():
        found = _find(child, msg)
        if found is not None:
            return found
    return None


def explorer_header(height: int, explorers: Sequence[str] = EXPLORERS,
                    http: httpx.Client | None = None) -> Block | None:  # fmt: skip
    """A Bitcoin block header from public explorers; they must agree.

    Args:
        height: Block height.
        explorers: Esplora API roots.
        http: HTTP client (injectable).

    Returns:
        The header's height, Merkle root and time; None when the explorers disagree or fail.
    """
    client = http or httpx.Client(timeout=TIMEOUT)
    seen: list[Block] = []
    for api in explorers:
        try:
            block_hash = client.get(f"{api}/block-height/{height}").raise_for_status().text.strip()
            b = client.get(f"{api}/block/{block_hash}").raise_for_status().json()
        except (httpx.HTTPError, ValueError):
            continue
        seen.append(Block(int(b["height"]), str(b["merkle_root"]),
                          datetime.fromtimestamp(int(b["timestamp"]), UTC)))  # fmt: skip
    if not seen or any(s != seen[0] for s in seen):
        return None
    return seen[0]


def verify(path: Path, digest: bytes, header: HeaderReader = explorer_header) -> Proof:
    """What a proof shows about a head: its earliest confirmed Bitcoin block, or pending.

    Args:
        path: The ``.ots`` file.
        digest: The head it must timestamp.
        header: Block-header reader (default: two public explorers).

    Returns:
        The proof's digest, its earliest block whose Merkle root matches, and pending calendars.

    Raises:
        ValueError: When the proof timestamps another digest.
    """
    proof = read(path)
    if proof.file_digest != digest:
        raise ValueError(f"{path.name}: the proof timestamps another head")
    blocks: list[Block] = []
    pending: list[str] = []
    for msg, attestation in proof.timestamp.all_attestations():
        if isinstance(attestation, PendingAttestation):
            pending.append(str(attestation.uri))
        elif isinstance(attestation, BitcoinBlockHeaderAttestation):
            block = header(int(attestation.height))
            # The attested message is the Merkle root in the header's own byte order.
            if block is not None and block.merkle_root == msg[::-1].hex():
                blocks.append(block)
    first = min(blocks, key=lambda b: b.height) if blocks else None
    return Proof(path, digest.hex(), first, tuple(sorted(set(pending))))
