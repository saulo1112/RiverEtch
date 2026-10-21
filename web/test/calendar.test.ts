import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  addDays,
  monthWeeks,
  passDays,
  passMonths,
  stepDay,
} from "../src/features/case/calendar.ts";
import type { SeriesRow } from "../src/features/reaches/types.ts";

const series = JSON.parse(
  readFileSync(
    new URL("../../docs/water-quality/reach/firat-birecik/examples/series.json", import.meta.url),
    "utf8",
  ),
) as SeriesRow[];

void test("a month is laid out in weeks from Monday", () => {
  // 1 June 2026 is a Monday; 1 February 2026 a Sunday.
  const june = monthWeeks("2026-06");
  assert.deepEqual(june[0], [
    "2026-06-01",
    "2026-06-02",
    "2026-06-03",
    "2026-06-04",
    "2026-06-05",
    "2026-06-06",
    "2026-06-07",
  ]);
  assert.equal(june.flat().filter((d) => d !== null).length, 30);
  const february = monthWeeks("2026-02");
  assert.deepEqual(february[0], [null, null, null, null, null, null, "2026-02-01"]);
  assert.ok(february.every((week) => week.length === 7));
  assert.equal(february.flat().at(-1), null); // 28 Feb is a Saturday
});

void test("every pass is on its day, two satellites sharing a day kept apart", () => {
  const days = passDays(series);
  assert.equal([...days.values()].flat().length, series.length);
  const shared = [...days.values()].filter((list) => list.length > 1);
  assert.ok(shared.length > 0);
  for (const list of shared) {
    assert.equal(new Set(list.map((k) => series[k]?.sceneId)).size, list.length);
  }
});

void test("the months run from the first pass to the last, with none skipped", () => {
  assert.deepEqual(passMonths(["2026-03-02", "2025-12-30", "2026-01-15"]), [
    "2025-12",
    "2026-01",
    "2026-02",
    "2026-03",
  ]);
  assert.deepEqual(passMonths([]), []);
});

void test("keys move among the days with a pass only", () => {
  const days = ["2026-05-28", "2026-06-02", "2026-06-05", "2026-06-12", "2026-06-30"];
  assert.equal(stepDay(days, "2026-06-05", "ArrowRight"), "2026-06-12");
  assert.equal(stepDay(days, "2026-06-02", "ArrowLeft"), "2026-05-28"); // into the month before
  assert.equal(stepDay(days, "2026-06-12", "ArrowUp"), "2026-06-05");
  assert.equal(stepDay(days, "2026-06-05", "ArrowDown"), "2026-06-12");
  assert.equal(stepDay(days, "2026-06-12", "Home"), "2026-06-02");
  assert.equal(stepDay(days, "2026-06-12", "End"), "2026-06-30");
  assert.equal(stepDay(days, "2026-06-30", "ArrowRight"), null);
  assert.equal(addDays("2026-02-28", 1), "2026-03-01");
});
