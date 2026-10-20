import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { sha256 } from "@noble/hashes/sha2.js";
import { bytesToHex } from "@noble/hashes/utils.js";

import type { HeadSignature } from "../src/features/chain/mldsa.ts";
import {
  checkBitcoin,
  checkSignature,
  coveringProof,
  explorerHeader,
  type ProofEntry,
} from "../src/features/chain/witness.ts";

const FIXTURES = new URL("../../pipeline/tests/fixtures/", import.meta.url);
const file = (name: string) => new Uint8Array(readFileSync(new URL(name, FIXTURES)));
const BLOCK = {
  height: 358391,
  merkleRoot: "8a1b66ecb7cbd07d8139a7e7d7f2c41aab1f5009b8364aaf61d03ad245e47e00",
  time: 1432827678,
};
const LABEL = "terrachain:platte-louisville:observations";
const entry = (lines: number, height: number | null): ProofEntry => ({
  label: LABEL,
  lines,
  file: `docs/ledgers/ots/x.${String(lines)}.ots`,
  height,
});

void test("the proof for a line is the earliest confirmed head that covers it", () => {
  const proofs = [
    entry(12, null),
    entry(16, 900),
    entry(20, 880),
    { ...entry(30, 870), label: "x" },
  ];
  assert.equal(coveringProof(proofs, LABEL, 14)?.lines, 20); // block 880 before 900
  assert.equal(coveringProof(proofs, LABEL, 3)?.lines, 20);
  assert.equal(coveringProof([entry(12, null)], LABEL, 3)?.lines, 12); // pending only
  assert.equal(coveringProof(proofs, LABEL, 25), null); // recorded after the last head
});

void test("a proof is checked against this ledger's head and its block", async () => {
  // The fixture timestamps the SHA-256 of hello-world.txt: let that be the head of 3 lines.
  const head = bytesToHex(sha256(file("ots/hello-world.txt")));
  const hashes = ["aa", "bb", head];
  const bytes = file("ots/hello-world.txt.ots");
  const header = (h: number) => Promise.resolve(h === BLOCK.height ? BLOCK : null);
  assert.deepEqual(await checkBitcoin(entry(3, BLOCK.height), bytes, hashes, header), {
    state: "confirmed",
    height: BLOCK.height,
    time: BLOCK.time,
    lines: 3,
  });
  // Another ledger, a forged block, explorers that cannot be read.
  assert.equal((await checkBitcoin(entry(2, 1), bytes, hashes, header)).state, "mismatch");
  const forged = () => Promise.resolve({ ...BLOCK, merkleRoot: "00".repeat(32) });
  assert.equal((await checkBitcoin(entry(3, 1), bytes, hashes, forged)).state, "mismatch");
  const down = () => Promise.resolve(null);
  assert.equal((await checkBitcoin(entry(3, 1), bytes, hashes, down)).state, "unavailable");
  const pending = file("ots/incomplete.txt.ots");
  const pendingHead = bytesToHex(sha256(file("ots/incomplete.txt")));
  assert.deepEqual(await checkBitcoin(entry(1, null), pending, [pendingHead], header), {
    state: "pending",
    lines: 1,
  });
});

void test("block headers count only when the explorers that answer agree", async () => {
  // A fake fetch: the explorers are called with URL strings only.
  const answer =
    (root: string, failing = "") =>
    (url: string): Promise<Response> => {
      if (failing !== "" && url.startsWith(failing)) {
        return Promise.reject(new Error("down"));
      }
      return Promise.resolve(
        url.includes("/block-height/")
          ? new Response("hash\n")
          : Response.json({ height: 358391, merkle_root: root, timestamp: BLOCK.time }),
      );
    };
  const asFetch = (f: (url: string) => Promise<Response>) => f as unknown as typeof fetch;
  assert.deepEqual(await explorerHeader(358391, asFetch(answer(BLOCK.merkleRoot))), BLOCK);
  const one = asFetch(answer(BLOCK.merkleRoot, "https://mempool.space"));
  assert.deepEqual(await explorerHeader(358391, one), BLOCK);
  let calls = 0;
  const split = asFetch((url: string) => {
    calls += 1;
    const root = url.startsWith("https://mempool.space") ? BLOCK.merkleRoot : "ff";
    return answer(root)(url);
  });
  assert.equal(await explorerHeader(358391, split), null);
  assert.equal(calls, 4);
});

void test("a head's signature counts only for this ledger's head, with the published key", () => {
  const doc = JSON.parse(readFileSync(new URL("ml-dsa/pqcrypto-head.json", FIXTURES), "utf8")) as {
    publicKey: string;
    statement: string;
    context: string;
    signature: string;
  };
  const fields = JSON.parse(doc.statement) as Omit<
    HeadSignature,
    "algorithm" | "context" | "signature"
  >;
  const signed: HeadSignature = {
    ...fields,
    algorithm: "ML-DSA-65",
    context: doc.context,
    signature: doc.signature,
  };
  const hashes = Array.from({ length: 16 }, (_, k) => (k === 15 ? "ab".repeat(32) : "00"));
  assert.deepEqual(checkSignature([signed], doc.publicKey, LABEL, 4, hashes), {
    state: "verified",
    lines: 16,
    signedAt: fields.signedAt,
  });
  assert.equal(checkSignature([signed], doc.publicKey, LABEL, 16, hashes).state, "none");
  const changed = hashes.map((h, k) => (k === 15 ? "cd".repeat(32) : h)); // the ledger changed
  assert.equal(checkSignature([signed], doc.publicKey, LABEL, 4, changed).state, "invalid");
  const other = { ...signed, signedAt: "2026-10-01T00:00:00+00:00" }; // backdated
  assert.equal(checkSignature([other], doc.publicKey, LABEL, 4, hashes).state, "invalid");
});
