import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { test } from "node:test";

import {
  MARK_ARMS,
  MARK_NOTCH,
  MARK_STEM,
  MARK_STROKE,
  MARK_WAVE,
} from "../src/features/hero/ui/mark.ts";

const PUBLIC = new URL("../public/", import.meta.url);

function svg(name: string): string {
  return readFileSync(new URL(name, PUBLIC), "utf8");
}

void test("every static icon draws the same mark: the same stem, wave and arms", () => {
  for (const name of ["logo-mark.svg", "logo-mark-light.svg", "favicon.svg"]) {
    const text = svg(name);
    assert.ok(text.includes(`d="${MARK_STEM}"`), `${name}: stem`);
    assert.ok(text.includes(`d="${MARK_WAVE}"`), `${name}: wave`);
    assert.ok(text.includes(`stroke-width="${String(MARK_STROKE)}"`), `${name}: stroke`);
    for (const [x, y] of MARK_ARMS) {
      assert.ok(
        text.includes(`href="#wave" x="${String(x)}" y="${String(y)}"`),
        `${name}: arm ${y}`,
      );
    }
    assert.doesNotMatch(text, /<text|font|Gradient|filter|xlink|https?:\/\/(?!www\.w3\.org)/i);
    assert.ok(Buffer.byteLength(text) < 2048, `${name}: under 2 KB`);
  }
});

void test("the logos carry the etch and the favicon leaves it out", () => {
  assert.ok(svg("logo-mark.svg").includes(`d="${MARK_NOTCH}"`));
  assert.ok(svg("logo-mark-light.svg").includes(`d="${MARK_NOTCH}"`));
  assert.ok(!svg("favicon.svg").includes(MARK_NOTCH));
});

void test("index.html links icons that exist", () => {
  const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
  const hrefs = [
    ...html.matchAll(/<link rel="(?:icon|apple-touch-icon)"[^>]*href="\/([^"]+)"/g),
  ].map((m) => m[1] ?? "");
  assert.deepEqual(hrefs.sort(), ["apple-touch-icon.png", "favicon-32.png", "favicon.svg"]);
  for (const href of hrefs) {
    assert.ok(existsSync(new URL(href, PUBLIC)), href);
  }
});
