import assert from "node:assert/strict";
import { test } from "node:test";

import { primaryText, secondaryText, shownOf } from "../src/features/case/turbidity.ts";
import type { ReachData } from "../src/features/reaches/types.ts";

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

void test("an older record shows its class alone, and no reading shows nothing", () => {
  const shown = shownOf(us, null, "30_to_50", 36.87);
  assert.equal(primaryText(shown), "30 to 50 FNU");
  assert.equal(secondaryText(shown), null);
  assert.equal(shownOf(us, null, null, 36.87), null);
  assert.equal(primaryText(null), "No reading");
});
