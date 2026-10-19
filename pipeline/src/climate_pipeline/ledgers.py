"""``climate-pipeline ledger``: the frozen-artifacts ledger (prospective scoring, rule v1).

Before any prospective pass is scored, the files that decide its estimate and its score (the model
cards, the preregistration, the results' MANIFEST and the scoring rule) are listed in an
append-only ledger, ``docs/ledgers/frozen-artifacts.jsonl``. Each line names one file's SHA-256 (of
its bytes, as ``sha256sum`` prints it), its git blob and, for a model card, the canonical hash that
records name (:func:`climate_pipeline.quality.cards.card_hash`). Lines chain by hash like the
reaches' ledgers, so the ledger's head, once anchored on Sepolia
(``terrachain:riveretch:frozen-artifacts``), commits to every file listed so far.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from climate_pipeline.calibration.report import git_blob
from climate_pipeline.quality.cards import card_hash

FROZEN = Path("docs/ledgers/frozen-artifacts.jsonl")
CARDS = "docs/water-quality/results/models/"


@dataclass(frozen=True)
class Frozen:
    """What one ``freeze`` did."""

    added: tuple[str, ...]
    unchanged: tuple[str, ...]


def read_lines(path: Path) -> list[dict[str, Any]]:
    """A ledger's lines, parsed (empty when it does not exist).

    Args:
        path: The ledger.

    Returns:
        One mapping per line.
    """
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    return [json.loads(t) for t in text.splitlines() if t.strip()]


def chain_ok(path: Path) -> bool:
    """Whether every line of a ledger names the SHA-256 of the line before it.

    Args:
        path: The ledger.

    Returns:
        True for an intact chain (or no ledger).
    """
    previous = None
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for text in lines:
        if json.loads(text)["previousLineSha256"] != previous:
            return False
        previous = hashlib.sha256(text.encode()).hexdigest()
    return True


def describe(root: Path, relative: str, purpose: str, created: str) -> dict[str, Any]:
    """The ledger line of one file (without its link to the line before).

    Args:
        root: Repository root.
        relative: The file, relative to the root, with forward slashes.
        purpose: Why it is frozen, in a few words.
        created: UTC time of the freeze.

    Returns:
        The line's fields.

    Raises:
        FileNotFoundError: When the file does not exist.
    """
    path = root / relative
    if not path.is_file():
        raise FileNotFoundError(relative)
    data = path.read_bytes()
    line: dict[str, Any] = {
        "path": relative,
        "purpose": purpose,
        "sha256": hashlib.sha256(data).hexdigest(),
        "gitBlob": git_blob(path),
        "createdUtc": created,
    }
    if relative.startswith(CARDS) and relative.endswith(".json"):
        line["canonicalSha256"] = card_hash(json.loads(data.decode("utf-8")))
    return line


def freeze(root: Path, paths: list[str], purpose: str, ledger: Path = FROZEN,
           now: datetime | None = None) -> Frozen:  # fmt: skip
    """Append each file to the frozen-artifacts ledger, unless its last line has the same bytes.

    Args:
        root: Repository root.
        paths: The files, relative to the root.
        purpose: Why they are frozen (the same for every file of the call).
        ledger: The ledger, relative to the root.
        now: The freeze's time (default: now, UTC).

    Returns:
        The files added and the files already listed unchanged.

    Raises:
        ValueError: When the ledger's chain is broken.
    """
    target = root / ledger
    if not chain_ok(target):
        raise ValueError(f"{ledger}: a line does not name the hash of the line before it")
    created = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    last = {line["path"]: line["sha256"] for line in read_lines(target)}  # the latest per file
    added: list[str] = []
    unchanged: list[str] = []
    target.parent.mkdir(parents=True, exist_ok=True)
    for raw in paths:
        relative = Path(raw).as_posix()
        line = describe(root, relative, purpose, created)
        if last.get(relative) == line["sha256"]:
            unchanged.append(relative)
            continue
        texts = target.read_text(encoding="utf-8").splitlines() if target.exists() else []
        previous = hashlib.sha256(texts[-1].encode()).hexdigest() if texts else None
        with target.open("a", encoding="utf-8", newline="\n") as handle:
            text = json.dumps({**line, "previousLineSha256": previous}, sort_keys=True,
                              separators=(",", ":"))  # fmt: skip
            handle.write(text + "\n")
        last[relative] = line["sha256"]
        added.append(relative)
    return Frozen(tuple(added), tuple(unchanged))


def verify(root: Path, ledger: Path = FROZEN) -> list[str]:
    """Check the ledger's chain and that each file still has the bytes of its latest line.

    Args:
        root: Repository root.
        ledger: The ledger, relative to the root.

    Returns:
        One line per problem (empty when everything checks out).
    """
    target = root / ledger
    if not target.exists():
        return [f"{ledger}: no ledger yet"]
    problems = [] if chain_ok(target) else [f"{ledger}: the chain is broken"]
    latest = {line["path"]: line for line in read_lines(target)}
    for relative, line in sorted(latest.items()):
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative}: listed but missing")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != line["sha256"]:
            problems.append(f"{relative}: changed since it was frozen")
    return problems
