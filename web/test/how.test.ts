import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { packStation, SATELLITE_YEARS, unpackStation } from "../src/features/hero/ui/how/flow.ts";
import { headline, neverSaw, ownRiver, riversTested } from "../src/features/hero/ui/how/numbers.ts";

const DOCS = new URL("../../docs/water-quality/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DOCS), "utf8");
const transfer = read("results/transfer/transfer_scores.csv");
const passes = read("inputs/usgs-v5/turbidity.csv");
const station = (site: string) => {
  const packed = packStation(
    read(`reach/${site}/examples/climate.json`),
    read(`reach/${site}/climate/daily.csv`),
    passes,
  );
  assert.ok(packed !== null);
  return unpackStation(packed);
};

void test("every year the flow chart offers recounts climate.json's low, high and seen days", () => {
  for (const site of ["mississippi-belle-chasse", "platte-louisville"]) {
    const s = station(site);
    assert.deepEqual(
      s.years.map((y) => y.year),
      SATELLITE_YEARS,
    );
    for (const y of s.years) {
      const count = (kind: string, seen: boolean) =>
        y.days.filter((d) => d.kind === kind && (!seen || d.seen)).length;
      assert.equal(count("low", false), y.low, `${site} ${String(y.year)} low`);
      assert.equal(count("low", true), y.lowSeen, `${site} ${String(y.year)} low seen`);
      assert.equal(count("high", false), y.high, `${site} ${String(y.year)} high`);
      assert.equal(count("high", true), y.highSeen, `${site} ${String(y.year)} high seen`);
    }
  }
  const y2023 = station("mississippi-belle-chasse").years.find((y) => y.year === 2023);
  assert.ok(y2023 !== undefined);
  assert.deepEqual([y2023.low, y2023.lowSeen], [147, 19]);
  // USGS published no daily value for 1 and 2 October 2023: the chart breaks its line there.
  assert.deepEqual(
    y2023.days.filter((d) => d.flow === null).map((d) => d.day),
    ["2023-10-01", "2023-10-02"],
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
  assert.equal(n.unscored.length, 0);
  assert.equal(n.beat, 8);
  assert.equal(n.fail, 2);
  assert.equal(riversTested(transfer), 9);
});

void test("its own river, by the same rule as the big number: 6 of 9 beat guessing, 2 fail", () => {
  const own = ownRiver(read("results/v5_levels.csv"), read("results/v5_scores.csv"));
  assert.equal(own.rows.length, 9);
  assert.deepEqual(
    own.unscored.map((r) => r.site),
    ["USGS-14246900"],
  );
  assert.equal(own.beat, 6);
  assert.equal(own.fail, 2);
});
