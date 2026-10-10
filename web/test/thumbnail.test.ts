import assert from "node:assert/strict";
import { test } from "node:test";

import { REFERENCE_REACH } from "../src/features/case/reachGeometry.ts";
import { reachThumbnailPath } from "../src/features/hero/ui/thumbnail.ts";

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

void test("reachThumbnailPath draws every vertex of the reference reach inside the margins", () => {
  const drawn = points(reachThumbnailPath(REFERENCE_REACH.geometry.coordinates, BOX));
  assert.equal(drawn.length, REFERENCE_REACH.geometry.coordinates.length);
  for (const [x, y] of drawn) {
    assert.ok(x >= BOX.padding && x <= BOX.width - BOX.padding, `x ${String(x)} in the box`);
    assert.ok(y >= BOX.padding && y <= BOX.height - BOX.padding, `y ${String(y)} in the box`);
  }
  // Upstream (south) at the bottom, downstream (north) at the top.
  const first = drawn[0];
  const last = drawn.at(-1);
  assert.ok(first !== undefined && last !== undefined);
  assert.ok(first[1] > last[1]);
});
