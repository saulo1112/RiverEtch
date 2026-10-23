import assert from "node:assert/strict";
import { test } from "node:test";

import {
  bandPosition,
  calendarIndex,
  compareYear,
  flowDays,
  sourceYear,
  SOURCE_API,
  type SourceYear,
} from "../src/features/reaches/dailyrecord.ts";
import type { DailyRecord, UsualFlow } from "../src/features/reaches/types.ts";

// A small sealed year (preregistration-daily-record.md): USGS discharge in ft³/s, three days.
function record(kind: "usgs" | "glofas" = "usgs"): DailyRecord {
  return {
    schemaVersion: 1,
    kind: "daily_record",
    reachId: "x-river",
    recordId: "x-river:daily-record:2026",
    year: 2026,
    date: "2026-10-03",
    source: {
      kind,
      stationId: kind === "usgs" ? "USGS-1" : "GloFAS-1",
      name: "A source",
      measured: kind === "usgs",
      url: "https://example.org/",
    },
    series: [
      {
        parameter: kind === "usgs" ? "00060" : "river_discharge",
        name: "discharge",
        unit: kind === "usgs" ? "ft³/s" : "m³/s",
        days:
          kind === "usgs"
            ? [
                ["2026-10-01", 1000, "Approved"],
                ["2026-10-02", 2000, "Provisional"],
                ["2026-10-03", 3000, "Provisional"],
              ]
            : [
                ["2026-10-01", 1000, "Modelled"],
                ["2026-10-02", 2000, "Modelled"],
                ["2026-10-03", 3000, "Modelled"],
              ],
      },
    ],
    fetchedUtc: "2026-10-04T00:10:00+00:00",
    replaces: null,
    provenance: {
      api: "https://example.org/api",
      query: { latitude: "37.025", longitude: "37.925" },
      codeCommit: "abc",
    },
    recordSha256: "00",
  };
}

void test("the calendar index puts 29 February on 28 February", () => {
  assert.equal(calendarIndex("2026-01-01"), 0);
  assert.equal(calendarIndex("2024-02-29"), calendarIndex("2026-02-28"));
  assert.equal(calendarIndex("2026-03-01"), 60);
  assert.equal(calendarIndex("2026-12-31"), 365);
});

void test("a record's flow is in m³/s, and a day sits below, within or above its usual range", () => {
  const days = flowDays(record());
  assert.equal(days.length, 3);
  assert.ok(Math.abs((days[0]?.value ?? 0) - 28.3168466) < 1e-9, "USGS's ft³/s converted");
  assert.equal(flowDays(record("glofas"))[1]?.value, 2000, "GloFAS's m³/s as published");
  const k = calendarIndex("2026-10-02");
  const fill = (v: number) => Array.from({ length: 366 }, (_, i) => (i === k ? v : null));
  const usual: UsualFlow = {
    first: 2009,
    last: 2025,
    years: 17,
    windowDays: 7,
    p10: fill(40),
    p50: fill(50),
    p90: fill(60),
  };
  assert.equal(bandPosition(30, "2026-10-02", usual), "below");
  assert.equal(bandPosition(50, "2026-10-02", usual), "within");
  assert.equal(bandPosition(61, "2026-10-02", usual), "above");
  assert.equal(bandPosition(50, "2026-10-01", usual), null, "no usual range that day");
});

void test("a sealed year against its source: the same, revised, gone, filled and newer days", () => {
  const now: SourceYear = new Map([
    [
      "00060",
      new Map<string, readonly [number, string]>([
        ["2026-10-01", [1000, "Approved"]],
        ["2026-10-02", [2100, "Approved"]],
        ["2026-09-30", [900, "Approved"]],
        ["2026-10-04", [3100, "Provisional"]],
      ]),
    ],
  ]);
  const result = compareYear(record(), now);
  assert.equal(result.checked, 3);
  assert.equal(result.same, 1);
  assert.deepEqual(result.revised, [
    {
      parameter: "00060",
      day: "2026-10-02",
      sealed: [2000, "Provisional"],
      now: [2100, "Approved"],
    },
  ]);
  assert.deepEqual(
    result.gone.map((g) => g.day),
    ["2026-10-03"],
  );
  assert.equal(result.filled, 1, "a day before the record's last that it lacks");
  assert.equal(result.newer, 1, "a day after it");
});

void test("USGS is read page by page, from its own address", async () => {
  const asked: string[] = [];
  const pages = [
    {
      features: [
        { properties: { time: "2026-10-01", value: "1000", approval_status: "Approved" } },
        { properties: { time: "2026-10-02", value: "2000", approval_status: "Provisional" } },
      ],
      links: [{ rel: "next", href: "https://api.waterdata.usgs.gov/next" }],
    },
    {
      features: [
        { properties: { time: "2026-10-03", value: 3000, approval_status: "Provisional" } },
      ],
    },
  ];
  const fetcher = ((url: string) => {
    asked.push(url);
    return Promise.resolve(new Response(JSON.stringify(pages[asked.length - 1])));
  }) as unknown as typeof fetch;
  const now = await sourceYear(record(), fetcher, new Date("2026-10-10T12:00:00Z"));
  assert.ok(asked[0]?.startsWith(`${SOURCE_API.usgs}?`), "never the address a record names");
  assert.match(asked[0] ?? "", /monitoring_location_id=USGS-1/);
  assert.match(asked[0] ?? "", /datetime=2026-01-01%2F2026-10-09/);
  assert.equal(asked.length, 2);
  assert.equal(compareYear(record(), now).same, 3);
});

void test("GloFAS is read up to yesterday: its later days are forecasts", async () => {
  let asked = "";
  const fetcher = ((url: string) => {
    asked = url;
    return Promise.resolve(
      new Response(
        JSON.stringify({
          daily: {
            time: ["2026-10-01", "2026-10-02", "2026-10-03"],
            river_discharge: [1000, null, 3000],
          },
        }),
      ),
    );
  }) as unknown as typeof fetch;
  const now = await sourceYear(record("glofas"), fetcher, new Date("2026-10-04T08:00:00Z"));
  assert.ok(asked.startsWith(`${SOURCE_API.glofas}?`));
  assert.match(asked, /end_date=2026-10-03/);
  assert.match(asked, /latitude=37.025/);
  const result = compareYear(record("glofas"), now);
  assert.equal(result.same, 2);
  assert.deepEqual(
    result.gone.map((g) => g.day),
    ["2026-10-02"],
    "a day the model no longer returns",
  );
});
