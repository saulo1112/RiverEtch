import assert from "node:assert/strict";
import { test } from "node:test";

import { COPY } from "../src/features/hero/ui/content.ts";

void test("the hero paragraph is 45 words and never says error", () => {
  const words = COPY.subtitle.trim().split(/\s+/);
  assert.equal(words.length, 45);
  assert.doesNotMatch(COPY.subtitle, /error/i);
  assert.match(COPY.subtitle, /RiverEtch/);
});
