import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  anchorStatus,
  ledgerHead,
  subjectLabel,
  type ChainAnchor,
} from "../src/features/chain/ledger.ts";

const LEDGER = new URL(
  "../../docs/water-quality/reach/platte-louisville/examples/ledger.jsonl",
  import.meta.url,
);

function anchor(head: string, lines: number): ChainAnchor {
  return { head, lines, timestamp: 1_760_000_000, blockNumber: 9_000_000 };
}

void test("a ledger's head is the SHA-256 of its last line, as the pipeline chains it", async () => {
  const text = readFileSync(LEDGER, "utf8");
  const lines = text.split("\n").filter((l) => l.trim() !== "");
  const { head, lines: count, hashes } = await ledgerHead(text);
  const last = lines.at(-1) ?? "";
  assert.equal(count, lines.length);
  assert.equal(head, `0x${createHash("sha256").update(last, "utf8").digest("hex")}`);
  // Each line names the hash of the line before it.
  const second = JSON.parse(lines[1] ?? "{}") as { previousLineSha256: string };
  assert.equal(`0x${second.previousLineSha256}`, hashes[0]);
});

void test("an anchor covers the lines above it, and only while the ledger keeps them", async () => {
  const { hashes } = await ledgerHead(readFileSync(LEDGER, "utf8"));
  const early = anchor(hashes[4] ?? "", 5);
  const later = anchor(hashes[9] ?? "", 10);
  assert.equal(anchorStatus([early, later], 2, hashes).state, "anchored");
  const status = anchorStatus([early, later], 7, hashes);
  assert.ok(status.state === "anchored" && status.index === 1);
  assert.equal(anchorStatus([early], 7, hashes).state, "pending"); // recorded after the anchor
  assert.equal(anchorStatus([], 0, hashes).state, "pending");
  const edited = [...hashes];
  edited[4] = `0x${"0".repeat(64)}`;
  assert.equal(anchorStatus([early], 1, edited).state, "mismatch"); // the ledger changed since
});

void test("subjects name the reach and the ledger", () => {
  assert.equal(
    subjectLabel("platte-louisville", "water-temperature"),
    "terrachain:platte-louisville:water-temperature",
  );
});
