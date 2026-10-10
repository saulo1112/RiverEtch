import assert from "node:assert/strict";
import { test } from "node:test";

import {
  clampLatitudeOffset,
  decayVelocity,
  idleFactor,
  smoothVelocity,
  vectorToLatLng,
} from "../src/features/hero/drag.ts";

const close = (actual: number, expected: number, epsilon = 1e-9) => {
  assert.ok(Math.abs(actual - expected) < epsilon, `${String(actual)} ≈ ${String(expected)}`);
};

void test("clampLatitudeOffset keeps the camera within the limit from any base", () => {
  assert.equal(clampLatitudeOffset(-8, 30, 60), 30);
  assert.equal(clampLatitudeOffset(-8, 80, 60), 68);
  assert.equal(clampLatitudeOffset(-8, -80, 60), -52);
});

void test("decayVelocity decays and stops", () => {
  close(decayVelocity(1, 2, 0.5, 1e-4), Math.exp(-1));
  assert.equal(decayVelocity(1e-5, 2, 0.016, 1e-4), 0);
  assert.equal(decayVelocity(0, 2, 0.016, 1e-4), 0);
});

void test("smoothVelocity moves towards the sample, more over longer gaps", () => {
  const short = smoothVelocity(0, 10, 0.01, 0.05);
  const long = smoothVelocity(0, 10, 0.2, 0.05);
  assert.ok(short > 0 && short < long && long < 10);
  assert.equal(smoothVelocity(3, 10, 0, 0.05), 3);
});

void test("idleFactor waits, then ramps in smoothly", () => {
  assert.equal(idleFactor(0, 4, 2), 0);
  assert.equal(idleFactor(4, 4, 2), 0);
  close(idleFactor(5, 4, 2), 0.5);
  assert.equal(idleFactor(6, 4, 2), 1);
  assert.equal(idleFactor(Number.POSITIVE_INFINITY, 4, 2), 1);
});

void test("vectorToLatLng inverts three-globe's frame", () => {
  const at = (x: number, y: number, z: number) => vectorToLatLng(x, y, z);
  close(at(0, 0, 1).lng, 0);
  close(at(1, 0, 0).lng, 90);
  close(at(-1, 0, 0).lng, -90);
  close(at(0, 1, 0).lat, 90);
  const lat = (7.4 * Math.PI) / 180;
  const lng = (-73.9 * Math.PI) / 180;
  const point = at(
    5 * Math.cos(lat) * Math.sin(lng),
    5 * Math.sin(lat),
    5 * Math.cos(lat) * Math.cos(lng),
  );
  close(point.lat, 7.4);
  close(point.lng, -73.9);
});
