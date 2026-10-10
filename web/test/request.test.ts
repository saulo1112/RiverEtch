import assert from "node:assert/strict";
import { test } from "node:test";

import { IN_SITU_ANSWERS, PURPOSES, REQUEST } from "../src/features/hero/ui/request/content.ts";
import {
  EMPTY_REQUEST,
  parseCoordinate,
  validateRequest,
  type RequestValues,
} from "../src/features/hero/ui/request/validate.ts";

const VALID: RequestValues = {
  ...EMPTY_REQUEST,
  reachName: "Puerto Wilches to San Pablo",
  river: "Río Magdalena",
  purpose: "Research",
  inSitu: "Not sure",
};

const check = (values: RequestValues) =>
  validateRequest(values, REQUEST.errors, PURPOSES, IN_SITU_ANSWERS);

void test("parseCoordinate reads decimals in range, a true minus, and empty as null", () => {
  assert.equal(parseCoordinate("", 90), null);
  assert.equal(parseCoordinate("   ", 90), null);
  assert.equal(parseCoordinate("7.41", 90), 7.41);
  assert.equal(parseCoordinate(" -73.9 ", 180), -73.9);
  assert.equal(parseCoordinate("−73.9", 180), -73.9);
  assert.equal(parseCoordinate("+90", 90), 90);
  assert.equal(parseCoordinate(".5", 90), 0.5);
});

void test("parseCoordinate rejects text, other formats and values out of range", () => {
  for (const text of ["abc", "7,41", "1e2", "7.4.1", "-", "90.0001", "-180.5", "Infinity"]) {
    assert.ok(Number.isNaN(parseCoordinate(text, text.includes("180") ? 180 : 90)), text);
  }
});

void test("validateRequest accepts a complete request without coordinates", () => {
  assert.deepEqual(check(VALID), {});
});

void test("validateRequest names every missing required field", () => {
  assert.deepEqual(Object.keys(check(EMPTY_REQUEST)), ["reachName", "river", "purpose", "inSitu"]);
  assert.deepEqual(check({ ...VALID, reachName: "   " }), { reachName: REQUEST.errors.reachName });
});

void test("validateRequest keeps purposes and in-situ answers to the listed ones", () => {
  assert.deepEqual(check({ ...VALID, purpose: "Enforcement" }), {
    purpose: REQUEST.errors.purpose,
  });
  assert.deepEqual(check({ ...VALID, inSitu: "Maybe" }), { inSitu: REQUEST.errors.inSitu });
});

void test("validateRequest wants both coordinates or neither, each in range", () => {
  assert.deepEqual(check({ ...VALID, latitude: "7.41", longitude: "-73.91" }), {});
  assert.deepEqual(check({ ...VALID, latitude: "7.41" }), {
    longitude: REQUEST.errors.longitudeMissing,
  });
  assert.deepEqual(check({ ...VALID, longitude: "-73.91" }), {
    latitude: REQUEST.errors.latitudeMissing,
  });
  assert.deepEqual(check({ ...VALID, latitude: "95", longitude: "-73.91" }), {
    latitude: REQUEST.errors.latitudeNumber,
  });
  // An invalid half does not also report the other one as missing.
  assert.deepEqual(check({ ...VALID, latitude: "north" }), {
    latitude: REQUEST.errors.latitudeNumber,
  });
});

void test("the request form asks for no personal data and says nothing is sent", () => {
  const text = JSON.stringify(REQUEST).toLowerCase();
  assert.doesNotMatch(text, /e-?mail|phone|your name|address/);
  assert.match(REQUEST.demoOnly, /nothing you enter leaves this page/);
  assert.match(REQUEST.confirmation.body, /does not send or store requests/);
});
