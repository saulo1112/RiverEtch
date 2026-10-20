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


def test_heads_are_signed_once_and_every_signature_is_checked(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    ledger = root / "docs" / "ledgers" / "frozen-artifacts.jsonl"
    ledger.parent.mkdir(parents=True)
    ledger.write_bytes(b'{"a":1}\n{"b":2}\n')
    secret, _ = signing.keygen(root, tmp_path / "keys", NOW)
    sk = secret.read_text(encoding="utf-8")
    assert signing.sign_heads(root, sk, NOW) == ["terrachain:riveretch:frozen-artifacts:2"]
    assert signing.sign_heads(root, sk, NOW) == []  # that head is signed already
    assert signing.verify_signatures(root) == []
    ledger.write_bytes(b'{"a":1}\n{"b":2}\n{"c":3}\n')  # the ledger grows: a new head
    assert signing.sign_heads(root, sk, NOW) == ["terrachain:riveretch:frozen-artifacts:3"]
    assert signing.verify_signatures(root) == []
    lines = (root / signing.SIGNATURES).read_text(encoding="utf-8").splitlines()
    assert json.loads(lines[1])["previousLineSha256"] is not None
    ledger.write_bytes(b'{"a":1}\n{"b":9}\n{"c":3}\n')  # an earlier line changed
    assert signing.verify_signatures(root) == [
        "signatures line 1 (terrachain:riveretch:frozen-artifacts:2): "
        "the head is not that ledger's line"
    ]
    forged = json.loads(lines[0]) | {"signedAt": "2026-10-01T00:00:00+00:00"}  # backdated
    (root / signing.SIGNATURES).write_text(
        json.dumps(forged, sort_keys=True, separators=(",", ":")) + "\n" + lines[1] + "\n",
        encoding="utf-8", newline="\n",
    )  # fmt: skip
    problems = signing.verify_signatures(root)
    assert any("does not verify" in p for p in problems)
    assert any("chain is broken" in p for p in problems)


ML_DSA = Path(__file__).parent / "fixtures" / "ml-dsa"


def test_pqcrypto_agrees_with_nists_acvp_vectors() -> None:
    # NIST ACVP-Server, ML-DSA-sigVer-FIPS204, group 3: ML-DSA-65, external interface, pure.
    from pqcrypto.sign import ml_dsa_65

    doc = json.loads((ML_DSA / "acvp-ml-dsa-65-sigver.json").read_text(encoding="utf-8"))
    assert (doc["parameterSet"], doc["signatureInterface"], doc["preHash"]) == (
        "ML-DSA-65", "external", "pure")  # fmt: skip
    for t in doc["tests"]:
        pk, message = bytes.fromhex(t["pk"]), bytes.fromhex(t["message"])
        sig, context = bytes.fromhex(t["signature"]), bytes.fromhex(t["context"])
        try:
            ml_dsa_65.verify(pk, message, sig, context)
            ok = True
        except Exception:  # pqcrypto's InvalidSignatureError
            ok = False
        assert ok == t["testPassed"], t["tcId"]


def test_a_head_signed_in_the_browsers_implementation_verifies_here() -> None:
    doc = json.loads((ML_DSA / "noble-head.json").read_text(encoding="utf-8"))
    assert doc["context"] == signing.CONTEXT.decode()
    fields = json.loads(doc["statement"])
    message = signing.statement(
        fields["label"], fields["lines"], fields["head"], fields["signedAt"]
    )
    assert message == doc["statement"].encode()  # the same bytes on both sides
    assert signing.verify(doc["publicKey"], message, bytes.fromhex(doc["signature"]))
    assert not signing.verify(doc["publicKey"], message + b" ", bytes.fromhex(doc["signature"]))
