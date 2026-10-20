import assert from "node:assert/strict";
import { test } from "node:test";

import { colorize, Colorizer } from "../src/features/reaches/colorize.ts";

// A deterministic packed map: every place byte, unusable and empty NDTI bytes, and pixels outside.
function packedMap(width: number, height: number): Uint8ClampedArray {
  const data = new Uint8ClampedArray(width * height * 4);
  let seed = 20261020;
  const random = () => (seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31;
  for (let p = 0; p < data.length; p += 4) {
    data[p] = random() < 0.05 ? 0 : 1 + Math.floor(random() * 255); // NDTI byte, 0: none
    data[p + 1] = Math.floor(random() * 256); // place along the reach
    data[p + 2] = random() < 0.1 ? 4 : Math.floor(random() * 3); // part, 4: unusable
    data[p + 3] = random() < 0.3 ? 0 : 255; // inside
  }
  return data;
}

void test("the incremental colorizer writes the same bytes as colorize at every reveal", () => {
  const width = 97;
  const packed = packedMap(width, 83);
  const look = { domain: [-0.12, 0.08] as const, packed: [-0.3, 0.3] as const, opacity: 0.92 };
  for (const feather of [0.05, 0]) {
    const options = { ...look, feather };
    const expected = new Uint8ClampedArray(packed.length);
    const actual = new Uint8ClampedArray(packed.length);
    const incremental = new Colorizer(packed, width, actual, options);
    // Forward as the river fills, a repeat, backwards, a reset and a jump to the end.
    for (const reveal of [0, 0.01, 0.2, 0.2, 0.37, 0.5, 0.45, 0.999, 1, 0, 0.6, 1]) {
      colorize(packed, width, expected, { ...options, reveal });
      incremental.render(reveal);
      assert.deepEqual(actual, expected, `feather ${String(feather)}, reveal ${String(reveal)}`);
    }
  }
});

void test("a frame reports only the pixels it changed", () => {
  const width = 40;
  const packed = packedMap(width, 30);
  const out = new Uint8ClampedArray(packed.length);
  const c = new Colorizer(packed, width, out, {
    domain: [-0.1, 0.1],
    packed: [-0.3, 0.3],
    opacity: 1,
    feather: 0.05,
  });
  assert.notEqual(c.render(0.5), null, "the first frame draws");
  assert.equal(c.render(0.5), null, "the same reveal again changes nothing");
  const rect = c.render(0.55);
  assert.ok(rect !== null && rect.width <= width && rect.height <= 30);
});
