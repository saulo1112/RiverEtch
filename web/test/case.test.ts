import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { ALERT_TITLES, alertTitle, CASE_COPY, formatSigned } from "../src/features/case/content.ts";
import { REFERENCE_REACH, REFERENCE_REACH_CENTER } from "../src/features/case/reachGeometry.ts";
import { ILLUSTRATIVE_CASE } from "../src/features/case/sample.ts";
import { canShowPhysicalUnits } from "../src/features/case/units.ts";

interface SampleJson {
  readonly ui: { readonly reach: unknown };
}

const docs = JSON.parse(
  readFileSync(
    new URL("../../docs/magdalena-validation/magdalena.sample.json", import.meta.url),
    "utf8",
  ),
) as SampleJson;

void test("the reference reach is the docs' Magdalena centreline, unchanged", () => {
  assert.deepEqual(REFERENCE_REACH, docs.ui.reach);
  assert.equal(REFERENCE_REACH.geometry.coordinates.length, 151);
});

void test("the reach centre is the centre of its bounding box", () => {
  assert.deepEqual(
    REFERENCE_REACH_CENTER.map((value) => Number(value.toFixed(6))),
    [-73.909205, 7.414155],
  );
});

void test("alertTitle names each verdict without claiming a cause", () => {
  assert.equal(alertTitle("normal"), "No departure from the baseline");
  assert.equal(alertTitle("explained_by_climate"), "Departure explained by rainfall");
  assert.equal(alertTitle("candidate_human_pressure"), "Departure not explained by rainfall");
  for (const title of Object.values(ALERT_TITLES)) {
    assert.doesNotMatch(title, /pressure|human|operator|pollut/i);
  }
});

void test("canShowPhysicalUnits needs a calibration that passed", () => {
  assert.equal(canShowPhysicalUnits(ILLUSTRATIVE_CASE), false);
  assert.equal(canShowPhysicalUnits(null), false);
  assert.equal(canShowPhysicalUnits("passed"), false);
  assert.equal(canShowPhysicalUnits({ calibration: null }), false);
  assert.equal(canShowPhysicalUnits({ calibration: { status: "pending" } }), false);
  assert.equal(canShowPhysicalUnits({ calibration: { status: "PASSED" } }), false);
  assert.equal(canShowPhysicalUnits({ calibration: { status: "passed" } }), true);
});

void test("the illustrative case keeps the figures the panels quote", () => {
  const data = ILLUSTRATIVE_CASE;
  assert.equal(data.illustrative, true);
  assert.equal(data.reach, REFERENCE_REACH);
  assert.equal(data.classification, "candidate_human_pressure");
  assert.equal(formatSigned(data.anomaly.zScore, 1), "+2.8");
  assert.equal(formatSigned(data.stats.deltaNdti, 2), "+0.11");
  assert.equal(data.anomaly.onsetDate, "2025-03-09");
  assert.equal(data.anomaly.sceneDate, "2025-03-14");
  assert.equal(data.samples.at(-1)?.date, "2025-03-14");
  assert.equal(data.rainfall.at(-1)?.mm, 12.4);
  assert.equal(data.sampleProgress.length, 41);
});

void test("the case view's strings stay relative", () => {
  const text = JSON.stringify(CASE_COPY);
  assert.doesNotMatch(text, /\bNTU\b|mg\/L|water quality|verified|guarantee|proves?\b/i);
});
