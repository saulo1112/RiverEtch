import assert from "node:assert/strict";
import { test } from "node:test";

import { layout } from "../src/features/case/tour.ts";

const DESK = { width: 1440, height: 900 };
const CARD = { width: 340, height: 210 };

void test("a control in the left column gets the card on its right, with the arrow at it", () => {
  const rect = { left: 40, top: 150, width: 288, height: 200 };
  const place = layout(rect, CARD, DESK);
  assert.deepEqual(place.ring, { left: 34, top: 144, width: 300, height: 212 });
  assert.equal(place.arrow?.side, "left"); // the card's left side faces the control
  assert.equal(place.card.left, 34 + 300 + 14);
  const middle = rect.top + rect.height / 2;
  assert.equal(place.card.top + place.arrow.at, middle); // the arrow points at its middle
});

void test("a control at the right edge gets the card on its left; a bottom strip gets it above", () => {
  const right = layout({ left: 1100, top: 300, width: 300, height: 50 }, CARD, DESK);
  assert.equal(right.arrow?.side, "right");
  assert.ok(right.card.left + right.card.width <= 1100);
  const strip = layout({ left: 0, top: 640, width: 1440, height: 40 }, CARD, DESK);
  assert.equal(strip.arrow?.side, "bottom");
  assert.ok(strip.card.top + CARD.height <= 640 - 6);
});

void test("the card stays inside the screen's gutters, and its arrow off its corners", () => {
  const corner = layout({ left: 1380, top: 860, width: 40, height: 30 }, CARD, DESK);
  assert.ok(corner.card.left >= 16 && corner.card.left + corner.card.width <= 1440 - 16);
  assert.ok(corner.card.top >= 16);
  const at = corner.arrow?.at ?? 0;
  assert.ok(at >= 22 && at <= corner.card.width - 22);
});

void test("on a phone the card is a sheet away from the control; with no control it is centred", () => {
  const phone = { width: 375, height: 812 };
  const high = layout({ left: 16, top: 80, width: 343, height: 160 }, CARD, phone);
  assert.equal(high.arrow, null);
  assert.equal(high.card.width, 375 - 32);
  assert.equal(high.card.top, 812 - CARD.height - 16); // the control is high: the sheet is low
  const low = layout({ left: 16, top: 600, width: 343, height: 120 }, CARD, phone);
  assert.equal(low.card.top, 16);
  const none = layout(null, CARD, DESK);
  assert.equal(none.ring, null);
  assert.equal(none.card.left, (1440 - 400) / 2);
});
