import assert from "node:assert/strict";
import { test } from "node:test";

import {
  primaryText,
  secondaryText,
  shownOf,
  unclearAtStation,
} from "../src/features/case/turbidity.ts";
import type { ReachData, SeriesRow } from "../src/features/reaches/types.ts";

// preregistration-values.md: a value beside its error on the US reaches, beside its range outside
// the tested region, and a class alone on a record sealed before the value.
const us = { card: { basis: "transfer_test_ungauged" } } as unknown as ReachData;
const outside = { card: { basis: "outside_tested_region" } } as unknown as ReachData;

void test("on a US reach a value shows its typical error and its class's range", () => {
  const shown = shownOf(us, 62.34, "50_to_100", 36.87);
  assert.deepEqual(shown, { value: 62.34, cls: "50_to_100", errorPercent: 37 });
  assert.equal(primaryText(shown), "62.3 FNU");
  assert.equal(secondaryText(shown), "Typical error 37 % · range 50 to 100 FNU");
});

void test("outside the tested region a value shows its range only", () => {
  const shown = shownOf(outside, 4.21, "under_30", 36.87);
  assert.equal(shown?.errorPercent, null);
  assert.equal(primaryText(shown), "4.2 FNU");
  assert.equal(secondaryText(shown), "Range under 30 FNU");
  assert.equal(
    secondaryText(shownOf(outside, 140, "100_and_over", 36.87)),
    "Range 100 FNU and over",
  );
});

// A pass is unclear when the station's value and its own stretch's differ by more than three times.
function gauged(station: number | null, stretch: number | null) {
  const reach = {
    info: { station: { source: "usgs" } },
    along: { passes: [{ sceneId: "x", classes: ["under_30"], values: [stretch] }] },
  } as unknown as ReachData;
  const row = {
    sceneId: "x",
    estimates: [{ target: "turbidity", unit: "FNU", level: "validated", value: station }],
  } as unknown as SeriesRow;
  return unclearAtStation(reach, row);
}

void test("a pass whose station and stretch values differ by more than three times is unclear", () => {
  assert.equal(gauged(431.35, 40.65), true);
  assert.equal(gauged(2.23, 6.77), true);
  assert.equal(gauged(47, 38), false);
  assert.equal(gauged(40, 120), false, "exactly three times is still clear");
  assert.equal(gauged(null, 40), false);
  assert.equal(gauged(40, null), false);
});

void test("an older record shows its class alone, and no reading shows nothing", () => {
  const shown = shownOf(us, null, "30_to_50", 36.87);
  assert.equal(primaryText(shown), "30 to 50 FNU");
  assert.equal(secondaryText(shown), null);
  assert.equal(shownOf(us, null, null, 36.87), null);
  assert.equal(primaryText(null), "No reading");
});
