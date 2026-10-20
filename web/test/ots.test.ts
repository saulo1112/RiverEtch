import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex } from "@noble/hashes/utils.js";

import { attests, parseProof } from "../src/features/chain/ots.ts";

// The example proofs of opentimestamps-client (examples/, commit 5d5d325b2a70), shared with the
// pipeline's tests, which check the same files with python-opentimestamps.
const FIXTURES = new URL("../../pipeline/tests/fixtures/ots/", import.meta.url);
const file = (name: string) => new Uint8Array(readFileSync(new URL(name, FIXTURES)));
// Block 358391 as mempool.space and blockstream.info print it.
const BLOCK = {
  height: 358391,
  merkleRoot: "8a1b66ecb7cbd07d8139a7e7d7f2c41aab1f5009b8364aaf61d03ad245e47e00",
  time: 1432827678,
};

void test("a Bitcoin-attested proof replays to its block's Merkle root", () => {
  const proof = parseProof(file("hello-world.txt.ots"));
  assert.equal(bytesToHex(proof.digest), bytesToHex(sha256(file("hello-world.txt"))));
  const bitcoin = proof.attestations.filter((a) => a.kind === "bitcoin");
  assert.equal(bitcoin.length, 1);
  const [only] = bitcoin;
  assert.ok(only?.kind === "bitcoin");
  assert.equal(only.height, 358391);
  assert.ok(attests(only, BLOCK));
  assert.ok(!attests(only, { ...BLOCK, merkleRoot: "00".repeat(32) }));
  assert.ok(!attests(only, { ...BLOCK, height: 358392 }));
});

void test("a pending proof names its calendar", () => {
  const proof = parseProof(file("incomplete.txt.ots"));
  assert.equal(bytesToHex(proof.digest), bytesToHex(sha256(file("incomplete.txt"))));
  assert.deepEqual(
    proof.attestations.map((a) => (a.kind === "pending" ? a.uri : a.kind)),
    ["https://alice.btc.calendar.opentimestamps.org"],
  );
});

void test("anything else is refused", () => {
  const good = file("hello-world.txt.ots");
  const bad = good.slice();
  bad[1] = 0x00; // the magic header
  assert.throws(() => parseProof(bad), /not an OpenTimestamps proof/);
  assert.throws(() => parseProof(good.slice(0, 60)), /ends too early/);
});
