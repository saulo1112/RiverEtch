import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { evidenceOf, type ReachFacts } from "../src/features/hero/ui/evidence.ts";
import { REACH_CASES } from "../src/features/reaches/catalog.ts";

const REACHES = new URL("../../docs/water-quality/reach/", import.meta.url);

// What vite.config.ts reads for one reach: its river and the lines of its ledgers.
function factsOf(id: string): ReachFacts {
  const folder = new URL(`${id}/examples/`, REACHES);
  const lines = (path: string) => {
    const url = new URL(path, folder);
    return existsSync(url)
      ? readFileSync(url, "utf8")
          .split("\n")
          .filter((line) => line.trim() !== "").length
      : 0;
  };
  const info = JSON.parse(readFileSync(new URL("reach.json", folder), "utf8")) as {
    river: string;
  };
  return { river: info.river, sealed: lines("ledger.jsonl") + lines("thermal/ledger.jsonl") };
}

void test("the evidence strip counts distinct rivers and every sealed pass of the cases", () => {
  const facts = { a: { river: "River A", sealed: 3 }, b: { river: "River A", sealed: 2 } };
  assert.deepEqual(evidenceOf(["a", "b"], facts), { rivers: 1, sealedPasses: 5 });
  assert.equal(evidenceOf(["a", "missing"], facts), null);
  assert.equal(evidenceOf([], facts), null);
});

void test("the demo's figures match its committed records", () => {
  const ids = REACH_CASES.map((c) => c.id);
  const facts = Object.fromEntries(ids.map((id) => [id, factsOf(id)]));
  const figures = evidenceOf(ids, facts);
  assert.ok(figures !== null);
  assert.equal(figures.rivers, new Set(ids.map((id) => facts[id]?.river)).size);
  for (const id of ids) {
    const records = JSON.parse(
      readFileSync(new URL(`${id}/examples/series.json`, REACHES), "utf8"),
    ) as unknown[];
    // Every Sentinel-2 pass of the series is a line of the reach's ledger.
    assert.ok((facts[id]?.sealed ?? 0) >= records.length, id);
  }
});
