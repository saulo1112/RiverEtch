import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  gainOver,
  insideCount,
  leanOfTemperature,
  leanOfTurbidity,
} from "../src/features/case/reading.ts";

const MODELS = new URL("../../docs/water-quality/results/models/", import.meta.url);

function lockbox(path: string): Record<string, number> {
  const card = JSON.parse(readFileSync(new URL(path, MODELS), "utf8")) as {
    metrics: { lockbox: Record<string, number> };
  };
  return card.metrics.lockbox;
}

void test("the gain over guessing the usual value is computed from the cards", () => {
  const belle = lockbox("mississippi-belle-chasse/turbidity.json");
  const platte = lockbox("platte-louisville/turbidity.json");
  assert.deepEqual(gainOver(belle.mdsa ?? 0, belle.null_mdsa ?? 0), { kind: "times", text: "6" });
  assert.deepEqual(gainOver(platte.mdsa ?? 0, platte.null_mdsa ?? 0), { kind: "times", text: "3" });
  assert.deepEqual(gainOver(0.86, 1.41), { kind: "times", text: "1.6" }); // one decimal below 2
  assert.deepEqual(gainOver(38.0, 31.8), { kind: "worse" }); // Connecticut
  assert.deepEqual(gainOver(40.6, 46.2), { kind: "none" }); // San Joaquin: within 15 %
  assert.deepEqual(gainOver(0, 10), { kind: "none" });
});

void test("the expected range's hit count matches the cards' coverage", () => {
  const belle = lockbox("mississippi-belle-chasse/turbidity.json");
  const platte = lockbox("platte-louisville/turbidity.json");
  assert.equal(insideCount(belle.coverage90 ?? 0, belle.n ?? 0), 54); // of 57
  assert.equal(insideCount(platte.coverage90 ?? 0, platte.n ?? 0), 50); // of 54
});

void test("a bias reads as a lean only beyond its threshold", () => {
  assert.deepEqual(leanOfTemperature(1.1089), { kind: "warm", text: "1.1" }); // the Platte
  assert.deepEqual(leanOfTemperature(-0.3288), { kind: "cold", text: "0.3" }); // Belle Chasse
  assert.deepEqual(leanOfTemperature(0.2), { kind: "none" });
  assert.deepEqual(leanOfTurbidity(-3.58), { kind: "none" });
  assert.deepEqual(leanOfTurbidity(54.7), { kind: "high", text: "55" });
});
