import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  claimRows,
  lockboxHits,
  prospectiveHits,
  retrospectiveHits,
} from "../src/features/case/scoreboard.ts";
import { parseChecks, parseThermalChecks } from "../src/features/reaches/checks.ts";
import type {
  ModelCard,
  Outcome,
  ReachData,
  ReachInfo,
  SeriesRow,
  TemperatureCard,
  ThermalRow,
} from "../src/features/reaches/types.ts";

const REACHES = new URL("../../docs/water-quality/reach/", import.meta.url);

// A demo reach as the web loads it (only the files the scoreboard reads).
function reach(site: string): ReachData {
  const file = (path: string) => readFileSync(new URL(`${site}/examples/${path}`, REACHES), "utf8");
  const json = (path: string): unknown => JSON.parse(file(path));
  return {
    base: "/",
    info: json("reach.json") as ReachInfo,
    series: json("series.json") as SeriesRow[],
    card: json("cards/turbidity.json") as ModelCard,
    checks: parseChecks(file("checks/checks.csv")),
    maps: null,
    geometry: null,
    thermal: {
      series: json("thermal/series.json") as ThermalRow[],
      checks: parseThermalChecks(file("thermal/checks.csv")),
      card: json("cards/water_temperature.json") as TemperatureCard,
    },
    context: [],
    climate: null,
    outcomes: [],
  };
}

void test("the 2026 passes' counts match the report's check, from the sealed intervals", () => {
  const belle = retrospectiveHits(reach("mississippi-belle-chasse"), null);
  const platte = retrospectiveHits(reach("platte-louisville"), null);
  assert.deepEqual(belle.turbidity, { inside: 17, n: 22 }); // report.md: 17 of 22
  assert.deepEqual(platte.turbidity, { inside: 9, n: 10 }); // report.md: 9 of 10
  assert.deepEqual(belle.temperature, { inside: 11, n: 13 });
  assert.deepEqual(platte.temperature, { inside: 11, n: 13 });
});

void test("a pass after T0 leaves the retrospective count", () => {
  const all = retrospectiveHits(reach("platte-louisville"), null).turbidity;
  const early = retrospectiveHits(reach("platte-louisville"), "2026-07-01T00:00:00Z").turbidity;
  assert.ok(early.n > 0 && early.n < all.n);
});

void test("the locked test's counts come from the cards' coverage", () => {
  assert.deepEqual(lockboxHits(reach("mississippi-belle-chasse")), {
    turbidity: { inside: 54, n: 57 },
    temperature: { inside: 33, n: 37 },
  });
  assert.deepEqual(lockboxHits(reach("platte-louisville")), {
    turbidity: { inside: 50, n: 54 },
    temperature: { inside: 23, n: 24 },
  });
});

// An outcomes line (only the fields the scoreboard reads vary).
function line(
  claim: string,
  overpass: string,
  fields: Partial<Outcome> & { approval?: string; value?: number },
): Outcome {
  const { approval, value, ...rest } = fields;
  return {
    claimRecordSha256: claim,
    claimLedger: "observations",
    claimLine: 1,
    sceneId: `platte-louisville:${claim}`,
    target: "turbidity",
    unit: "FNU",
    estimate: 40,
    interval: { low: 30, high: 50 },
    overpassUtc: overpass,
    gauge:
      value === undefined
        ? null
        : {
            station: "06805500",
            parameter: "63680",
            value,
            unit: "FNU",
            approval: approval ?? "Provisional",
            rule: "median",
            n: 4,
          },
    inside: value === undefined ? null : value >= 30 && value <= 50,
    status: "scored",
    final: false,
    readUtc: "2026-10-22T00:00:00+00:00",
    ruleSha256: "0",
    ...rest,
  };
}

void test("each claim is listed once, by its first read, latest pass first", () => {
  const rows = claimRows([
    line("a", "2026-10-20T17:22:00+00:00", { value: 41 }),
    line("b", "2026-10-21T16:55:00+00:00", { value: 70 }),
    line("c", "2026-10-21T17:06:00+00:00", { status: "no gauge value" }),
    line("d", "2026-10-20T17:06:00+00:00", { status: "no gauge value", final: true }),
    line("e", "2026-10-20T16:00:00+00:00", { status: "abstained", estimate: null, final: true }),
    // An approved re-read of "a" that fell outside: listed, never replacing the first read.
    line("a", "2026-10-20T17:22:00+00:00", { value: 52, approval: "Approved" }),
  ]);
  assert.deepEqual(
    rows.map((r) => [r.claim, r.result]),
    [
      ["c", "pending"],
      ["b", "outside"],
      ["a", "inside"],
      ["d", "none"],
      ["e", "abstained"],
    ],
  );
  const a = rows.find((r) => r.claim === "a");
  assert.ok(a !== undefined);
  assert.equal(a.gauge?.value, 41);
  assert.equal(a.approved?.gauge?.value, 52);
  assert.deepEqual(prospectiveHits(rows, "turbidity"), { inside: 1, n: 2 });
  assert.deepEqual(prospectiveHits(rows, "water_temperature"), { inside: 0, n: 0 });
  assert.deepEqual(claimRows([]), []);
});
