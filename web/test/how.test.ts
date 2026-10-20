import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { flowYear } from "../src/features/hero/ui/how/flow.ts";
import { headline, neverSaw, riversTested } from "../src/features/hero/ui/how/numbers.ts";

const DOCS = new URL("../../docs/water-quality/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DOCS), "utf8");
const SITE = "reach/mississippi-belle-chasse/";
const transfer = read("results/transfer/transfer_scores.csv");

void test("the flow chart's low days and the passes on them recount climate.json's 147 and 19", () => {
  const year = flowYear(
    read(`${SITE}examples/climate.json`),
    read(`${SITE}climate/daily.csv`),
    read("inputs/usgs-v5/turbidity.csv"),
    2023,
  );
  assert.ok(year !== null);
  // USGS published no daily value for 1 and 2 October 2023: the chart breaks its line there.
  assert.equal(year.days.length, 363);
  assert.ok(!year.days.some((d) => d.day === "2023-10-01" || d.day === "2023-10-02"));
  assert.equal(year.lowDays, 147);
  assert.equal(year.lowSeen, 19);
  assert.equal(year.days.filter((d) => d.low).length, year.lowDays);
  assert.equal(year.days.filter((d) => d.low && d.seen).length, year.lowSeen);
  assert.equal(
    flowYear(read(`${SITE}examples/climate.json`), "", "", 1999),
    null,
    "a year the record lacks draws nothing",
  );
});

void test("the big number is the middle station of the nine rated ones: Cape Girardeau, about 2x", () => {
  const h = headline(read("results/v5_levels.csv"), read("results/v5_scores.csv"));
  assert.ok(h !== null);
  assert.equal(h.n, 9);
  assert.equal(h.site, "USGS-07020850");
  assert.equal(h.times, "2");
  assert.deepEqual([h.good, h.none, h.worse], [6, 2, 1]);
});

void test("the rivers the model never saw: 10 stations on 9 rivers, 8 beat guessing, 2 fail", () => {
  const n = neverSaw(transfer);
  assert.equal(n.rows.length, 10);
  assert.equal(n.beat, 8);
  assert.equal(n.fail, 2);
  assert.equal(riversTested(transfer), 9);
});
