import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  CASE_COPY,
  formatSigned,
  formatValue,
  LEVEL_LABELS,
} from "../src/features/case/content.ts";
import { colorize, ndtiDomain } from "../src/features/reaches/colorize.ts";
import { parseChecks } from "../src/features/reaches/checks.ts";
import {
  defaultScene,
  gaugeAt,
  hasValue,
  mapFile,
  sceneKey,
  turbidity,
} from "../src/features/reaches/scene.ts";
import type { MapsIndex, ReachData, ReachInfo, SeriesRow } from "../src/features/reaches/types.ts";

const EXAMPLES = new URL(
  "../../docs/water-quality/reach/mississippi-belle-chasse/examples/",
  import.meta.url,
);

function json(path: string): unknown {
  return JSON.parse(readFileSync(new URL(path, EXAMPLES), "utf8"));
}

const series = json("series.json") as SeriesRow[];
const reach: ReachData = {
  base: "/",
  info: json("reach.json") as ReachInfo,
  series,
  card: null,
  checks: parseChecks(readFileSync(new URL("checks/checks.csv", EXAMPLES), "utf8")),
  maps: json("maps.json") as MapsIndex,
  geometry: null,
  thermal: null,
  context: [],
  climate: null,
};

void test("formatters keep the sign and one decimal under 100", () => {
  assert.equal(formatSigned(0.11, 2), "+0.11");
  assert.equal(formatSigned(-0.04, 2), "−0.04");
  assert.equal(formatValue(30.49), "30.5");
  assert.equal(formatValue(124.4), "124");
  assert.equal(LEVEL_LABELS.validated, "Validated");
});

void test("no string of the case view claims a cause or an actor", () => {
  const text = JSON.stringify(CASE_COPY);
  assert.doesNotMatch(text, /pressure|human|operator|pollut|caus/i);
});

void test("a pass's key, map and gauge value join across the reach's files", () => {
  const index = defaultScene(series);
  const row = series[index];
  assert.ok(row !== undefined && hasValue(row));
  assert.match(sceneKey(row), /^sentinel-2[abc]_\d{4}-\d{2}-\d{2}_R\d{3}$/);
  assert.equal(row.sceneId, `mississippi-belle-chasse:${sceneKey(row)}`);
  assert.equal(mapFile(reach, row), `maps/${sceneKey(row)}.png`);
  assert.equal(turbidity(row)?.unit, "FNU");
  const withGauge = series.filter((r) => gaugeAt(reach, r) !== null);
  assert.equal(withGauge.length, 18);
});

void test("the ramp's domain is the reach's own range, widened", () => {
  assert.deepEqual(ndtiDomain([]), [-0.1, 0.1]);
  const [low, high] = ndtiDomain([0, 0.1]);
  assert.ok(Math.abs(low + 0.025) < 1e-9 && Math.abs(high - 0.125) < 1e-9);
});

void test("colorize reveals from upstream and hatches unusable pixels", () => {
  // Four pixels: usable upstream, usable downstream, unusable, outside the corridor.
  const packed = new Uint8ClampedArray([
    128, 0, 1, 255, 255, 255, 2, 255, 0, 64, 7, 255, 0, 0, 0, 0,
  ]);
  const out = new Uint8ClampedArray(packed.length);
  const options = { domain: [-0.3, 0.3], packed: [-0.3, 0.3], feather: 0, opacity: 1 } as const;
  colorize(packed, 4, out, { ...options, reveal: 0.5 });
  assert.equal(out[3], 255); // upstream, revealed
  assert.equal(out[7], 0); // downstream, not yet
  assert.ok((out[11] ?? 0) > 0); // unusable but revealed: hatched
  assert.equal(out[15], 0); // outside
  colorize(packed, 4, out, { ...options, reveal: 1 });
  assert.equal(out[7], 255);
  assert.deepEqual([out[4], out[5], out[6]], [255, 79, 63]); // the top of the ramp
});
