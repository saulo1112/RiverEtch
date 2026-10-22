import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  ALONG_CLASSES,
  alongPasses,
  classTable,
  placeOf,
  windowAt,
} from "../src/features/reaches/along.ts";
import { Colorizer } from "../src/features/reaches/colorize.ts";
import { chartYears, sealedYear, yearPhases, yearReach } from "../src/features/reaches/history.ts";
import type {
  AlongData,
  AlongPlan,
  HistoryRow,
  ReachData,
  SeriesRow,
} from "../src/features/reaches/types.ts";

// Belle Chasse's frozen plan: the windows the pipeline reads along the river.
const plan = JSON.parse(
  readFileSync(
    new URL(
      "../../docs/water-quality/reach/mississippi-belle-chasse/along/windows.json",
      import.meta.url,
    ),
    "utf8",
  ),
) as AlongPlan;
const length = (plan.windows.at(-1)?.chainageM ?? 0) + plan.firstM;

function along(classes: (string | null)[][]): AlongData {
  return {
    plan,
    passes: classes.map((c, k) => ({
      sceneId: `s:${String(k)}`,
      date: `2026-0${String(k + 1)}-01`,
      recordSha256: String(k),
      classes: c as AlongData["passes"][number]["classes"],
      reasons: c.map((x) => (x === null ? "cloud" : null)),
    })),
  };
}

void test("the plan places a window every 600 m, and a place finds its nearest window", () => {
  const first = plan.windows.at(0);
  assert.equal(first?.chainageM, plan.firstM);
  const data = along([plan.windows.map(() => null)]);
  assert.equal(windowAt(data, placeOf(first.chainageM, length), length), 0);
  assert.equal(windowAt(data, 1, length), plan.windows.length - 1);
  assert.equal(placeOf(-5, length), 0);
  assert.equal(placeOf(length * 2, length), 1);
});

void test("the map's table gives each place its stretch's class colour, none where it has no class", () => {
  const classes = plan.windows.map((_, k) => (k === 0 ? null : (ALONG_CLASSES[k % 4] ?? null)));
  const data = along([classes]);
  const table = classTable(data, data.passes[0] ?? null, length);
  assert.equal(table.length, 256 * 4);
  assert.equal(table[3], 0, "the first stretch has no class: alpha 0");
  assert.equal(table[255 * 4 + 3], 255, "the last stretch has one");
  assert.deepEqual(
    [...classTable(data, null, length)].filter((_, i) => i % 4 === 3),
    new Array<number>(256).fill(0),
  );
});

void test("the colorizer paints usable water with the class table, hatching unusable pixels", () => {
  // Two pixels inside the reach: place 0 (usable), place 255 (unusable on this pass).
  const packed = new Uint8ClampedArray([128, 0, 1, 255, 128, 255, 4 | 1, 255]);
  const out = new Uint8ClampedArray(packed.length);
  const table = new Uint8ClampedArray(256 * 4);
  table.set([10, 20, 30, 255], 0);
  const colorizer = new Colorizer(packed, 2, out, {
    domain: [-0.1, 0.1],
    packed: [-0.3, 0.3],
    feather: 0,
    opacity: 1,
    classes: table,
  });
  colorizer.render(1);
  assert.deepEqual([...out.slice(0, 4)], [10, 20, 30, 255]);
  assert.deepEqual([...out.slice(4, 7)], [190, 200, 220], "an unusable pixel stays hatched");
});

void test("each pass along the river joins its series pass by its scene, oldest first", () => {
  const data = along([[null], [null]]);
  const reach = {
    series: [{ sceneId: "s:1" }, { sceneId: "s:0" }] as unknown as SeriesRow[],
    along: data,
  } as unknown as ReachData;
  assert.deepEqual(
    alongPasses(reach).map((p) => [p.pass.sceneId, p.index]),
    [
      ["s:0", 1],
      ["s:1", 0],
    ],
  );
});

void test("an earlier year is drawn from the station window's history, read only", () => {
  const history: HistoryRow[] = [
    {
      date: "2021-05-01",
      key: "a",
      value: 12,
      low: 8,
      high: 18,
      fnuClass: null,
      reason: null,
      phase: "training",
    },
    {
      date: "2023-12-02",
      key: "b",
      value: null,
      low: null,
      high: null,
      fnuClass: null,
      reason: "cloud",
      phase: "test",
    },
    {
      date: "2023-03-02",
      key: "c",
      value: 9,
      low: 6,
      high: 13,
      fnuClass: null,
      reason: null,
      phase: "training",
    },
  ];
  const reach = {
    info: { site: "x" },
    card: null,
    series: [{ date: "2026-10-20" }] as unknown as SeriesRow[],
    history,
    checks: [],
  } as unknown as ReachData;
  assert.deepEqual(chartYears(reach), [2026, 2023, 2021]);
  assert.equal(sealedYear(reach), 2026);
  const year = yearReach(reach, 2021);
  assert.equal(year.series.length, 1);
  const estimate = year.series.at(0)?.estimates.at(0);
  assert.equal(estimate?.value, 12);
  assert.equal(estimate.interval?.low, 8);
  assert.deepEqual(yearPhases(history, 2023), ["test", "training"]);
});
