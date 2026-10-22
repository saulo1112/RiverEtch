import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CASE_COPY } from "../src/features/case/content.ts";
import { turbidityPoints } from "../src/features/case/spot.ts";
import {
  ALONG_CLASSES,
  TEMPERATURE_CLASSES,
  TEMPERATURE_EDGES,
  alongPasses,
  classTable,
  nearestWindow,
  placeOf,
  stepWindow,
  stretchKm,
  thermalPasses,
  windowAt,
} from "../src/features/reaches/along.ts";
import { canonical, parseJson, sha256Hex } from "../src/features/reaches/canonical.ts";
import { editable, verifyRecord } from "../src/features/reaches/verify.ts";
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

// The reading spot that moves (preregistration-along-temperature.md, section 3).
const alongOf = (): AlongData => along([plan.windows.map(() => "under_30")]);

void test("the reading spot snaps to the nearest placed window and steps along the river", () => {
  const data = alongOf();
  const placed = plan.windows.flatMap((w, k) => (w.selected ? [k] : []));
  const k = placed[Math.floor(placed.length / 2)] ?? 0;
  const w = plan.windows[k];
  assert.ok(w !== undefined);
  assert.equal(nearestWindow(data, w.lon, w.lat), k);
  assert.equal(nearestWindow(data, w.lon + 1, w.lat + 1, 1500), null, "nothing within 1.5 km");
  const last = placed.at(-1) ?? 0;
  assert.equal(stepWindow(data, last, 1), null, "no window downstream of the last");
  assert.equal(stepWindow(data, last, -1), placed.at(-2));
  assert.deepEqual(stretchKm(data, 0), ["0.0", "0.6"]);
});

void test("each Landsat pass along the river joins the temperature series by its scene", () => {
  const reach = {
    thermal: { series: [{ sceneId: "t:1" }, { sceneId: "t:0" }], checks: [], card: null },
    alongTemperature: [
      { sceneId: "t:0", date: "2026-01-01", recordSha256: "a", classes: [], reasons: [] },
      { sceneId: "t:9", date: "2026-02-01", recordSha256: "b", classes: [], reasons: [] },
    ],
  } as unknown as ReachData;
  assert.deepEqual(
    thermalPasses(reach).map((p) => [p.pass.sceneId, p.index]),
    [["t:0", 1]],
  );
  assert.equal(TEMPERATURE_CLASSES.length, TEMPERATURE_EDGES.length + 1);
});

void test("an along record's window class is the field a reader changes, and the seal catches it", async () => {
  const content = {
    schema: "riveretch.along-river.v1",
    sceneId: "x:k",
    windows: [
      { id: "w01", abstainReason: "cloud" },
      { id: "w02", fnuClass: "under_30" },
    ],
  };
  const seal = await sha256Hex(canonical(parseJson(JSON.stringify(content))));
  const text = JSON.stringify({ ...content, recordSha256: seal });
  assert.deepEqual(editable(text, "w02"), {
    path: "windows[1].fnuClass",
    kind: "class",
    sealed: "under_30",
  });
  assert.equal(editable(text, "w01"), null, "a window with no reading has no class to change");
  const ledger = `${JSON.stringify({ sceneId: "x:k", date: "2026-10-21", recordSha256: seal, previousLineSha256: null })}\n`;
  const same = await verifyRecord(text, ledger, null);
  assert.ok(same.sealed && same.inLedger && same.chainIntact);
  const changed = await verifyRecord(text, ledger, null, "30_to_50", "w02");
  assert.equal(changed.sealed, false);
  assert.equal(changed.altered?.path, "windows[1].fnuClass");
});

void test("the class's help says, word for word, what the frozen preregistration fixes", () => {
  const prereg = readFileSync(
    new URL("../../docs/water-quality/preregistration-along-temperature.md", import.meta.url),
    "utf8",
  ).replace(/\s+/g, " ");
  const four = JSON.parse(
    readFileSync(
      new URL("../../docs/water-quality/results/four-classes/four_classes.json", import.meta.url),
      "utf8",
    ),
  ) as { model_matched: number; n: number };
  const { spot } = CASE_COPY;
  for (const text of [
    spot.usHelp(four.model_matched, four.n),
    spot.outsideHelp,
    spot.temperatureHelp,
  ]) {
    assert.ok(prereg.includes(text.replace(/\.$/, "")), text);
  }
});

void test("a stretch's points keep the series' order, with no class where it has no reading", () => {
  const data = along([plan.windows.map((_, k) => (k === 0 ? null : "50_to_100"))]);
  const reach = {
    series: [
      { sceneId: "s:0", date: "2026-01-01" },
      { sceneId: "s:9", date: "2026-02-01" },
    ],
    along: data,
  } as unknown as ReachData;
  assert.deepEqual(turbidityPoints(reach, 1), [
    { index: 0, date: "2026-01-01", cls: "50_to_100" },
    { index: 1, date: "2026-02-01", cls: null },
  ]);
  assert.equal(turbidityPoints(reach, 0)[0]?.cls, null);
});
