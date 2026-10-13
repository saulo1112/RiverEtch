import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import type { LngLat, ReachGeometry } from "../src/features/reaches/types.ts";
import { reachThumbnailPath } from "../src/features/hero/ui/thumbnail.ts";

const geometry = JSON.parse(
  readFileSync(
    new URL(
      "../../docs/water-quality/reach/mississippi-belle-chasse/examples/geometry.geojson",
      import.meta.url,
    ),
    "utf8",
  ),
) as ReachGeometry;
const centreline = geometry.features.find((f) => f.properties.kind === "centreline");
const LINE: readonly LngLat[] =
  centreline?.geometry.type === "LineString" ? centreline.geometry.coordinates : [];

const BOX = { width: 48, height: 96, padding: 8 };

// Parses "M x,y L x,y …" back into points.
function points(path: string): [number, number][] {
  return path.split(" ").map((step) => {
    const [x = Number.NaN, y = Number.NaN] = step.slice(1).split(",").map(Number);
    return [x, y];
  });
}

void test("reachThumbnailPath needs two points", () => {
  assert.equal(reachThumbnailPath([], BOX), "");
  assert.equal(reachThumbnailPath([[-73.9, 7.4]], BOX), "");
});

void test("reachThumbnailPath fits a north-south line to the box height, centred, north up", () => {
  const path = reachThumbnailPath(
    [
      [-73.9, 7.3],
      [-73.9, 7.5],
    ],
    BOX,
  );
  assert.equal(path, "M24,88 L24,8");
});

void test("reachThumbnailPath draws every vertex of a real centreline inside the margins", () => {
  assert.ok(LINE.length > 10);
  const drawn = points(reachThumbnailPath(LINE, BOX));
  assert.equal(drawn.length, LINE.length);
  for (const [x, y] of drawn) {
    assert.ok(x >= BOX.padding && x <= BOX.width - BOX.padding, `x ${String(x)} in the box`);
    assert.ok(y >= BOX.padding && y <= BOX.height - BOX.padding, `y ${String(y)} in the box`);
  }
  // Upstream (Chalmette, north) at the top, downstream (Belle Chasse, south) at the bottom.
  const first = drawn[0];
  const last = drawn.at(-1);
  assert.ok(first !== undefined && last !== undefined);
  assert.ok(first[1] < last[1]);
});
