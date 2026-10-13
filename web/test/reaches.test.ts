import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { REACH_CASES } from "../src/features/reaches/catalog.ts";
import { canonical, NumberText, parseJson, sha256Hex } from "../src/features/reaches/canonical.ts";
import { parseChecks } from "../src/features/reaches/checks.ts";
import { verifyRecord } from "../src/features/reaches/verify.ts";

const REACHES = new URL("../../docs/water-quality/reach/", import.meta.url);

function examples(id: string): URL {
  return new URL(`${id}/examples/`, REACHES);
}

function read(url: URL): string {
  return readFileSync(url, "utf8");
}

void test("every demo case has the pipeline's files for the web", () => {
  for (const reach of REACH_CASES) {
    for (const file of ["reach.json", "series.json", "ledger.jsonl", "cards/turbidity.json"]) {
      assert.ok(existsSync(new URL(file, examples(reach.id))), `${reach.id}: ${file}`);
    }
  }
});

void test("the canonical JSON reproduces every example record's seal", async () => {
  for (const reach of REACH_CASES) {
    const folder = new URL("records/", examples(reach.id));
    const files = readdirSync(folder);
    assert.ok(files.length > 0);
    for (const file of files) {
      const value = parseJson(read(new URL(file, folder)));
      assert.ok(value !== null && typeof value === "object" && !Array.isArray(value));
      if (value instanceof NumberText) {
        continue;
      }
      const stated = value.recordSha256;
      const { recordSha256: _, ...content } = value;
      assert.equal(await sha256Hex(canonical(content)), stated, `${reach.id}/${file}`);
    }
  }
});

void test("the canonical JSON reproduces each card's hash, as its records name it", async () => {
  for (const reach of REACH_CASES) {
    const card = parseJson(read(new URL("cards/turbidity.json", examples(reach.id))));
    const latest = JSON.parse(read(new URL("latest.json", examples(reach.id)))) as {
      estimates: { modelCardSha256: string }[];
    };
    assert.equal(await sha256Hex(canonical(card, true)), latest.estimates[0]?.modelCardSha256);
  }
});

void test("a changed digit breaks the seal", async () => {
  const value = parseJson('{"a":30.49,"b":[1,2.0],"recordSha256":"x"}');
  assert.equal(canonical(value), '{"a":30.49,"b":[1,2.0],"recordSha256":"x"}');
  const changed = parseJson('{"a":30.48,"b":[1,2.0]}');
  assert.notEqual(await sha256Hex(canonical(value)), await sha256Hex(canonical(changed)));
});

void test("sha256Hex matches node's hash, and ASCII escaping matches Python's", async () => {
  const text = '{"name":"Río","n":1}';
  assert.equal(await sha256Hex(text), createHash("sha256").update(text, "utf8").digest("hex"));
  assert.equal(canonical(parseJson(text), true), '{"n":1,"name":"R\\u00edo"}');
  assert.equal(canonical(parseJson(text)), '{"n":1,"name":"Río"}');
});

void test("a real record verifies, and an altered one fails only its seal", async () => {
  for (const reach of REACH_CASES) {
    const folder = examples(reach.id);
    const file = readdirSync(new URL("records/", folder)).at(-1) ?? "";
    const record = read(new URL(`records/${file}`, folder));
    const ledger = read(new URL("ledger.jsonl", folder));
    const card = read(new URL("cards/turbidity.json", folder));
    const ok = await verifyRecord(record, ledger, card);
    assert.ok(ok.sealed && ok.inLedger && ok.chainIntact && ok.cardMatches === true, reach.id);
    assert.equal(ok.altered, null);
    const altered = await verifyRecord(record, ledger, card, true);
    assert.ok(!altered.sealed && altered.inLedger && altered.chainIntact, reach.id);
    assert.notEqual(altered.altered, null);
    const broken = ledger.trim().split("\n").reverse().join("\n");
    assert.equal((await verifyRecord(record, broken, card)).chainIntact, false);
  }
});

void test("parseChecks reads the gauge values and leaves empty cells null", () => {
  const rows = parseChecks(
    "date,sceneId,key,datetimeUtc,target,estimate,value,approval,rule,n,cardSha256\n" +
      "2026-03-09,s,k1,t,turbidity,51.0,49.2,Approved,median 30 min,4,h\n" +
      "2026-03-10,s,k2,t,turbidity,40.0,,,none,0,h\n",
  );
  assert.deepEqual(rows, [
    { key: "k1", date: "2026-03-09", estimate: 51, value: 49.2, approval: "Approved" },
    { key: "k2", date: "2026-03-10", estimate: 40, value: null, approval: "" },
  ]);
});
