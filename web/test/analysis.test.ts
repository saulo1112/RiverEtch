import assert from "node:assert/strict";
import { test } from "node:test";

import { passStats, pixelAt, profile, readPixel } from "../src/features/reaches/analysis.ts";
import type { MapsIndex } from "../src/features/reaches/types.ts";

// A 4 x 2 map over a small box, north up.
const MAPS: MapsIndex = {
  width: 4,
  height: 2,
  corners: [
    [-90, 30.002],
    [-89.996, 30.002],
    [-89.996, 30],
    [-90, 30],
  ],
  encoding: {
    r: { ndti: [-0.3, 0.3], bytes: [1, 255] },
    b: { upstream: 1, downstream: 2, between: 3, unusable: 4 },
  },
  maps: [],
};

// Row 0: upstream usable (NDTI 0), between usable (+0.3), unusable, outside. Row 1: downstream.
const DATA = new Uint8ClampedArray([
  128, 0, 1, 255, 255, 64, 3, 255, 0, 128, 7, 255, 0, 0, 0, 0, 1, 192, 2, 255, 1, 255, 2, 255, 0, 0,
  0, 0, 0, 0, 0, 0,
]);

void test("pixelAt finds the column and row under a point, and nothing outside", () => {
  assert.deepEqual(pixelAt(MAPS, [-89.9995, 30.0015]), { col: 0, row: 0 });
  assert.deepEqual(pixelAt(MAPS, [-89.9965, 30.0005]), { col: 3, row: 1 });
  assert.equal(pixelAt(MAPS, [-90.01, 30.001]), null);
});

void test("readPixel decodes NDTI, the place, the part and the usable flag", () => {
  assert.deepEqual(readPixel(MAPS, DATA, 0, 0), {
    ndti: 0,
    place: 0,
    part: "upstream",
    usable: true,
  });
  const unusable = readPixel(MAPS, DATA, 2, 0);
  assert.equal(unusable?.usable, false);
  assert.equal(unusable.ndti, null);
  assert.equal(unusable.part, "between");
  assert.equal(readPixel(MAPS, DATA, 3, 0), null);
});

void test("passStats counts the water and the usable share, and bins the NDTI", () => {
  const stats = passStats(MAPS, DATA, [-0.3, 0.3], 3);
  assert.equal(stats.water, 5);
  assert.equal(stats.usable, 4);
  assert.deepEqual(stats.histogram, [2, 1, 1]);
  assert.equal(stats.percentiles?.[1], 0);
});

void test("profile gives each stretch its median and its usable share", () => {
  const points = profile(MAPS, DATA, 4);
  assert.equal(points.length, 4);
  assert.equal(points[0]?.ndti, 0);
  assert.equal(points[1]?.ndti, 0.3);
  assert.equal(points[2]?.usable, 0);
  assert.equal(points[2].ndti, null);
  assert.equal(points[3]?.ndti, -0.3);
});
