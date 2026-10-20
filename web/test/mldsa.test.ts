import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { ml_dsa65 } from "@noble/post-quantum/ml-dsa.js";
import { hexToBytes } from "@noble/hashes/utils.js";

import { CONTEXT, statement, verifyHead, type HeadSignature } from "../src/features/chain/mldsa.ts";

// Shared with the pipeline's tests (pipeline/tests/test_signing.py), which run pqcrypto on them.
const FIXTURES = new URL("../../pipeline/tests/fixtures/ml-dsa/", import.meta.url);
const json = (name: string): unknown => JSON.parse(readFileSync(new URL(name, FIXTURES), "utf8"));

interface Vector {
  readonly tcId: number;
  readonly testPassed: boolean;
  readonly pk: string;
  readonly message: string;
  readonly context: string;
  readonly signature: string;
}

void test("noble agrees with NIST's ACVP vectors for ML-DSA-65 (external, pure)", () => {
  const doc = json("acvp-ml-dsa-65-sigver.json") as {
    parameterSet: string;
    signatureInterface: string;
    preHash: string;
    tests: Vector[];
  };
  assert.deepEqual(
    [doc.parameterSet, doc.signatureInterface, doc.preHash],
    ["ML-DSA-65", "external", "pure"],
  );
  for (const t of doc.tests) {
    const ok = ml_dsa65.verify(hexToBytes(t.signature), hexToBytes(t.message), hexToBytes(t.pk), {
      context: hexToBytes(t.context),
    });
    assert.equal(ok, t.testPassed, `tcId ${String(t.tcId)}`);
  }
});

void test("a head signed by the pipeline's signer verifies in the browser, and nothing else does", () => {
  const doc = json("pqcrypto-head.json") as {
    publicKey: string;
    statement: string;
    context: string;
    signature: string;
  };
  assert.equal(doc.context, CONTEXT);
  const fields = JSON.parse(doc.statement) as Pick<
    HeadSignature,
    "label" | "lines" | "head" | "signedAt"
  >;
  // The browser rebuilds the pipeline's exact bytes from the fields.
  assert.equal(new TextDecoder().decode(statement(fields)), doc.statement);
  const line: HeadSignature = {
    ...fields,
    algorithm: "ML-DSA-65",
    context: CONTEXT,
    signature: doc.signature,
  };
  assert.ok(verifyHead(doc.publicKey, line));
  assert.ok(!verifyHead(doc.publicKey, { ...line, lines: line.lines + 1 }));
  assert.ok(!verifyHead(doc.publicKey, { ...line, signedAt: "2026-10-01T00:00:00+00:00" }));
  assert.ok(!verifyHead(doc.publicKey, { ...line, context: "another/context" }));
  assert.ok(!verifyHead(doc.publicKey, { ...line, signature: "00" }));
});
