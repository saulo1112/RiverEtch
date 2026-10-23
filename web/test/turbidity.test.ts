import assert from "node:assert/strict";
import { test } from "node:test";

import {
  primaryText,
  secondaryText,
  shownOf,
  unclearAtStation,
} from "../src/features/case/turbidity.ts";
import type { ReachData, SeriesRow } from "../src/features/reaches/types.ts";

// preregistration-values.md: a value beside its class's range, and a class alone on a record sealed
// before the value.
void test("a value shows its class's range beside it", () => {
  const shown = shownOf(62.34, "50_to_100");
  assert.deepEqual(shown, { value: 62.34, cls: "50_to_100" });
  assert.equal(primaryText(shown), "62.3 FNU");
  assert.equal(secondaryText(shown), "Range 50 to 100 FNU");
});

void test("the range reads in lower case after its word", () => {
  const shown = shownOf(4.21, "under_30");
  assert.equal(primaryText(shown), "4.2 FNU");
  assert.equal(secondaryText(shown), "Range under 30 FNU");
  assert.equal(secondaryText(shownOf(140, "100_and_over")), "Range 100 FNU and over");
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
  const shown = shownOf(null, "30_to_50");
  assert.equal(primaryText(shown), "30 to 50 FNU");
  assert.equal(secondaryText(shown), null);
  assert.equal(shownOf(null, null), null);
  assert.equal(primaryText(null), "No reading");
});
