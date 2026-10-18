import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  climateMeasures,
  climatePoints,
  ordinal,
  recordYear,
} from "../src/features/reaches/climate.ts";
import type { ClimateRecord } from "../src/features/reaches/types.ts";

function climate(site: string): ClimateRecord {
  const url = new URL(
    `../../docs/water-quality/reach/${site}/examples/climate.json`,
    import.meta.url,
  );
  return JSON.parse(readFileSync(url, "utf8")) as ClimateRecord;
}

void test("the Platte's record holds its 2019 flood and its warmest summer day", () => {
  const record = climate("platte-louisville");
  assert.deepEqual(climateMeasures(record), ["peak", "low", "warm"]);
  const peak = recordYear(climatePoints(record, "peak"));
  assert.equal(peak?.year, 2019);
  assert.equal(peak.day, "2019-03-16");
  assert.equal(peak.ranked, record.discharge.rankedYears);
  assert.equal(recordYear(climatePoints(record, "warm"))?.year, 2023);
});

void test("Belle Chasse has no temperature, and its lowest week is in 2023", () => {
  const record = climate("mississippi-belle-chasse");
  assert.deepEqual(climateMeasures(record), ["peak", "low"]);
  assert.deepEqual(climatePoints(record, "warm"), []);
  const low = recordYear(climatePoints(record, "low"));
  assert.equal(low?.year, 2023);
});

void test("the year of the last value is shown to date and never ranked", () => {
  const points = climatePoints(climate("platte-louisville"), "peak");
  const last = points.at(-1);
  assert.equal(last?.toDate, true);
  assert.equal(last.rank, null);
  assert.ok(points.filter((p) => p.rank !== null).every((p) => p.complete));
});

void test("ordinals", () => {
  assert.deepEqual([1, 2, 3, 4, 11, 12, 13, 21, 72, 101].map(ordinal), [
    "1st",
    "2nd",
    "3rd",
    "4th",
    "11th",
    "12th",
    "13th",
    "21st",
    "72nd",
    "101st",
  ]);
});
