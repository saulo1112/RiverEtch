import assert from "node:assert/strict";
import { test } from "node:test";

import { CASE_THUMBNAIL, previewLayers, thumbnailSrcSet } from "../src/features/hero/ui/preview.ts";

void test("without the thumbnail the card shows the outline and requests no image", () => {
  for (const status of ["pending", "loaded", "failed"] as const) {
    assert.deepEqual(previewLayers(false, status), { image: false, fallback: true, credit: false });
  }
});

void test("while the thumbnail loads the outline stays underneath, without attribution", () => {
  assert.deepEqual(previewLayers(true, "pending"), { image: true, fallback: true, credit: false });
});

void test("once loaded the image replaces the outline and shows its attribution", () => {
  assert.deepEqual(previewLayers(true, "loaded"), { image: true, fallback: false, credit: true });
});

void test("a failed image falls back to the outline alone", () => {
  assert.deepEqual(previewLayers(true, "failed"), { image: false, fallback: true, credit: false });
});

void test("the srcset lists both widths under the base URL, narrow first", () => {
  assert.equal(
    thumbnailSrcSet("/"),
    "/cases/magdalena-reference-960.webp 960w, /cases/magdalena-reference.webp 1920w",
  );
  assert.equal(thumbnailSrcSet("/app/").split(", ").length, 2);
  assert.equal(CASE_THUMBNAIL.full.width / CASE_THUMBNAIL.full.height, 2);
  assert.equal(CASE_THUMBNAIL.narrow.width / CASE_THUMBNAIL.narrow.height, 2);
});
