"""``climate-pipeline sign``: post-quantum signatures of ledger heads (ML-DSA-65, FIPS 204).

A ledger's head (the SHA-256 of its last line) commits to every record above it, so signing heads
says who published each state of a ledger, in a scheme a quantum computer is not known to break
(docs/trust-model.md). The signatures are detached: no record, seal or ledger line changes.

- **The key:** ``sign keygen`` writes the private key on the owner's machine, outside the
  repository (``~/.riveretch/`` by default), and the public key to ``docs/keys/ml-dsa-65.json``.
  The private key never goes into the repository, CI or a log.
- **What is signed:** the statement ``{"head", "label", "lines", "signedAt"}`` as compact,
  key-sorted JSON (UTF-8), with the FIPS 204 context string ``riveretch/ledger-head/v1``.
  ``signedAt`` is when it was signed: a head signed today never claims an earlier date.
- **Implementations:** pqcrypto signs and verifies here; the web app verifies with
  @noble/post-quantum, an independent implementation, and the tests run both on the same
  signatures.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pqcrypto.sign import ml_dsa_65

ALGORITHM = "ML-DSA-65"
CONTEXT = b"riveretch/ledger-head/v1"
PUBLIC_KEY = Path("docs/keys/ml-dsa-65.json")
KEY_FILE = "ml-dsa-65.key"
DEFAULT_KEY_DIR = Path.home() / ".riveretch"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def keygen(root: Path, key_dir: Path = DEFAULT_KEY_DIR, now: datetime | None = None
           ) -> tuple[Path, Path]:  # fmt: skip
    """Make the signing key pair: the private key outside the repository, the public key in it.

    Args:
        root: Repository root.
        key_dir: Where the private key goes (never inside ``root``).
        now: Creation time (default: now, UTC).

    Returns:
        The private key's path and the public key's path.

    Raises:
        ValueError: When ``key_dir`` is inside the repository.
        FileExistsError: When a private key or a public key already exists.
    """
    if _inside(key_dir, root):
        raise ValueError(f"{key_dir}: the private key must live outside the repository")
    secret = key_dir / KEY_FILE
    public = root / PUBLIC_KEY
    for path in (secret, public):
        if path.exists():
            raise FileExistsError(f"{path} exists: a key is made once and never replaced")
    pk, sk = ml_dsa_65.keygen()
    key_dir.mkdir(parents=True, exist_ok=True)
    secret.write_text(bytes(sk).hex() + "\n", encoding="utf-8", newline="\n")
    secret.chmod(0o600)
    created = (now or datetime.now(UTC)).astimezone(UTC).isoformat(timespec="seconds")
    doc = {
        "algorithm": ALGORITHM,
        "standard": "FIPS 204",
        "context": CONTEXT.decode(),
        "publicKey": bytes(pk).hex(),
        "publicKeySha256": hashlib.sha256(bytes(pk)).hexdigest(),
        "createdUtc": created,
        "signs": "ledger heads: compact key-sorted JSON {head, label, lines, signedAt}",
        "implementations": {"signer": "pqcrypto 1.0.0 (Python)",
                            "verifiers": ["pqcrypto 1.0.0 (Python)",
                                          "@noble/post-quantum 0.7.1 (browser)"]},
        "privateKey": "kept on the owner's machine; never in this repository, CI or a log",
    }  # fmt: skip
    public.parent.mkdir(parents=True, exist_ok=True)
    public.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8", newline="\n")
    return secret, public


def statement(label: str, lines: int, head: str, signed_at: str) -> bytes:
    """The bytes signed for one ledger head.

    Args:
        label: E.g. ``terrachain:platte-louisville:observations``.
        lines: The ledger's line count at that head.
        head: ``0x`` and the SHA-256 of its last line.
        signed_at: When it is signed (ISO 8601, UTC).

    Returns:
        Compact, key-sorted JSON in UTF-8.
    """
    doc: dict[str, Any] = {"head": head, "label": label, "lines": lines, "signedAt": signed_at}
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def sign(secret_hex: str, message: bytes) -> bytes:
    """An ML-DSA-65 signature of a statement, with RiverEtch's context string.

    Args:
        secret_hex: The private key, hex.
        message: A :func:`statement`.

    Returns:
        The detached signature (3,309 bytes).
    """
    return bytes(ml_dsa_65.sign(bytes.fromhex(secret_hex.strip()), message, CONTEXT))


def verify(public_hex: str, message: bytes, signature: bytes) -> bool:
    """Whether a signature is valid for a statement under the public key.

    Args:
        public_hex: The public key, hex.
        message: A :func:`statement`.
        signature: The detached signature.

    Returns:
        True when it verifies.
    """
    try:
        ml_dsa_65.verify(bytes.fromhex(public_hex), message, signature, CONTEXT)
    except Exception:  # pqcrypto raises InvalidSignatureError (or ValueError on a bad length)
        return False
    return True
