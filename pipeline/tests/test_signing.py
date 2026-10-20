"""Post-quantum signatures of ledger heads (``climate-pipeline sign``): the key stays outside the
repository and is made once; the statement is canonical; a signature binds the head, the line
count, the label, the time and RiverEtch's context string."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from climate_pipeline import signing

NOW = datetime(2026, 10, 20, 1, 30, tzinfo=UTC)


def test_keygen_writes_the_private_key_outside_the_repository_once(tmp_path: Path) -> None:
    root, keys = tmp_path / "repo", tmp_path / "keys"
    root.mkdir()
    secret, public = signing.keygen(root, keys, NOW)
    assert secret.parent == keys and public == root / signing.PUBLIC_KEY
    doc = json.loads(public.read_text(encoding="utf-8"))
    assert doc["algorithm"] == "ML-DSA-65" and doc["context"] == "riveretch/ledger-head/v1"
    assert len(bytes.fromhex(doc["publicKey"])) == 1952
    assert doc["createdUtc"] == "2026-10-20T01:30:00+00:00"
    assert "secret" not in public.read_text(encoding="utf-8").lower().replace("never", "")
    with pytest.raises(FileExistsError):
        signing.keygen(root, keys, NOW)
    with pytest.raises(ValueError, match="outside the repository"):
        signing.keygen(root, root / "keys", NOW)


def test_the_statement_is_compact_key_sorted_json() -> None:
    s = signing.statement("terrachain:x:observations", 33, "0xab", "2026-10-20T01:30:00+00:00")
    assert s == (b'{"head":"0xab","label":"terrachain:x:observations","lines":33,'
                 b'"signedAt":"2026-10-20T01:30:00+00:00"}')  # fmt: skip


def test_a_signature_binds_every_field_and_the_context(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    secret, public = signing.keygen(root, tmp_path / "keys", NOW)
    sk = secret.read_text(encoding="utf-8")
    pk = json.loads(public.read_text(encoding="utf-8"))["publicKey"]
    good = signing.statement("terrachain:x:observations", 33, "0xab", "2026-10-20T01:30:00+00:00")
    sig = signing.sign(sk, good)
    assert len(sig) == 3309 and signing.verify(pk, good, sig)
    for changed in (
        signing.statement("terrachain:y:observations", 33, "0xab", "2026-10-20T01:30:00+00:00"),
        signing.statement("terrachain:x:observations", 34, "0xab", "2026-10-20T01:30:00+00:00"),
        signing.statement("terrachain:x:observations", 33, "0xac", "2026-10-20T01:30:00+00:00"),
        signing.statement("terrachain:x:observations", 33, "0xab", "2026-10-19T01:30:00+00:00"),
    ):
        assert not signing.verify(pk, changed, sig)
    assert not signing.verify(pk, good, sig[:-1] + bytes([sig[-1] ^ 1]))
    # Without RiverEtch's context string the same signature does not verify.
    from pqcrypto.sign import ml_dsa_65

    with pytest.raises(Exception):  # noqa: B017 - pqcrypto's InvalidSignatureError
        ml_dsa_65.verify(bytes.fromhex(pk), good, sig)
