import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { test } from "node:test";

import { CASE_COPY } from "../src/features/case/content.ts";
import { REACH_CASES } from "../src/features/reaches/catalog.ts";
import { canonical, NumberText, parseJson, sha256Hex } from "../src/features/reaches/canonical.ts";
import { parseChecks, parseContext, parseThermalChecks } from "../src/features/reaches/checks.ts";
import {
  classEdges,
  classSpan,
  defaultThermal,
  isOutside,
  nearestThermal,
  OUTSIDE_BASIS,
  thermalValidatedAt,
} from "../src/features/reaches/scene.ts";
import type { ReachInfo, ThermalRow } from "../src/features/reaches/types.ts";
import { verifyRecord } from "../src/features/reaches/verify.ts";

const REACHES = new URL("../../docs/water-quality/reach/", import.meta.url);

function examples(id: string): URL {
  return new URL(`${id}/examples/`, REACHES);
}

function read(url: URL): string {
  return readFileSync(url, "utf8");
}

void test("every demo case has the pipeline's files for the web", () => {
  for (const reach of REACH_CASES) {
    for (const file of ["reach.json", "series.json", "ledger.jsonl", "cards/turbidity.json"]) {
      assert.ok(existsSync(new URL(file, examples(reach.id))), `${reach.id}: ${file}`);
    }
  }
});

void test("the canonical JSON reproduces every example record's seal", async () => {
  for (const reach of REACH_CASES) {
    const folder = new URL("records/", examples(reach.id));
    const files = readdirSync(folder);
    assert.ok(files.length > 0);
    for (const file of files) {
      const value = parseJson(read(new URL(file, folder)));
      assert.ok(value !== null && typeof value === "object" && !Array.isArray(value));
      if (value instanceof NumberText) {
        continue;
      }
      const stated = value.recordSha256;
      const { recordSha256: _, ...content } = value;
      assert.equal(await sha256Hex(canonical(content)), stated, `${reach.id}/${file}`);
    }
  }
});

void test("the canonical JSON reproduces each card's hash, as its records name it", async () => {
  for (const reach of REACH_CASES) {
    const card = parseJson(read(new URL("cards/turbidity.json", examples(reach.id))));
    const latest = JSON.parse(read(new URL("latest.json", examples(reach.id)))) as {
      estimates: { modelCardSha256: string }[];
    };
    assert.equal(await sha256Hex(canonical(card, true)), latest.estimates[0]?.modelCardSha256);
  }
});

void test("a changed digit breaks the seal", async () => {
  const value = parseJson('{"a":30.49,"b":[1,2.0],"recordSha256":"x"}');
  assert.equal(canonical(value), '{"a":30.49,"b":[1,2.0],"recordSha256":"x"}');
  const changed = parseJson('{"a":30.48,"b":[1,2.0]}');
  assert.notEqual(await sha256Hex(canonical(value)), await sha256Hex(canonical(changed)));
});

void test("sha256Hex matches node's hash, and ASCII escaping matches Python's", async () => {
  const text = '{"name":"Río","n":1}';
  assert.equal(await sha256Hex(text), createHash("sha256").update(text, "utf8").digest("hex"));
  assert.equal(canonical(parseJson(text), true), '{"n":1,"name":"R\\u00edo"}');
  assert.equal(canonical(parseJson(text)), '{"n":1,"name":"Río"}');
});

void test("a real record verifies, and an altered one fails only its seal", async () => {
  for (const reach of REACH_CASES) {
    const folder = examples(reach.id);
    const file = readdirSync(new URL("records/", folder)).at(-1) ?? "";
    const record = read(new URL(`records/${file}`, folder));
    const ledger = read(new URL("ledger.jsonl", folder));
    const card = read(new URL("cards/turbidity.json", folder));
    const ok = await verifyRecord(record, ledger, card);
    assert.ok(ok.sealed && ok.inLedger && ok.chainIntact && ok.cardMatches === true, reach.id);
    assert.equal(ok.altered, null);
    const altered = await verifyRecord(record, ledger, card, true);
    assert.ok(!altered.sealed && altered.inLedger && altered.chainIntact, reach.id);
    assert.notEqual(altered.altered, null);
    const broken = ledger.trim().split("\n").reverse().join("\n");
    assert.equal((await verifyRecord(record, broken, card)).chainIntact, false);
  }
});

void test("parseChecks reads the gauge values and leaves empty cells null", () => {
  const rows = parseChecks(
    "date,sceneId,key,datetimeUtc,target,estimate,value,approval,rule,n,cardSha256\n" +
      "2026-03-09,s,k1,t,turbidity,51.0,49.2,Approved,median 30 min,4,h\n" +
      "2026-03-10,s,k2,t,turbidity,40.0,,,none,0,h\n",
  );
  assert.deepEqual(rows, [
    {
      key: "k1",
      date: "2026-03-09",
      datetimeUtc: "t",
      estimate: 51,
      value: 49.2,
      approval: "Approved",
    },
    { key: "k2", date: "2026-03-10", datetimeUtc: "t", estimate: 40, value: null, approval: "" },
  ]);
});

void test("parseThermalChecks and parseContext read the v6 files", () => {
  assert.deepEqual(
    parseThermalChecks(
      "date,sceneId,datetimeUtc,estimate,value,approval\n" +
        "2026-03-11,r:l9,t,7.31,8.05,Approved\n" +
        "2026-01-06,r:l8,t,1.36,,\n",
    ),
    [
      { sceneId: "r:l9", date: "2026-03-11", datetimeUtc: "t", value: 8.05, approval: "Approved" },
      { sceneId: "r:l8", date: "2026-01-06", datetimeUtc: "t", value: null, approval: "" },
    ],
  );
  assert.deepEqual(
    parseContext(
      "key,date,datetimeUtc,parameter,name,value,unit,approval\n" +
        "k1,2026-02-12,t,00060,discharge,359.624,m³/s,Approved\n" +
        "k1,2026-02-12,t,00010,water temperature,,°C,\n",
    ),
    [
      {
        key: "k1",
        parameter: "00060",
        name: "discharge",
        value: 359.624,
        unit: "m³/s",
        approval: "Approved",
      },
    ],
  );
});

void test("the water-temperature records verify against their ledger and card", async () => {
  for (const reach of REACH_CASES) {
    const folder = new URL("thermal/", examples(reach.id));
    const info = JSON.parse(read(new URL("reach.json", examples(reach.id)))) as ReachInfo;
    // reach.json names the card exactly where the reach has water temperatures.
    assert.equal(info.cards.water_temperature !== undefined, existsSync(folder), reach.id);
    if (!existsSync(folder)) {
      continue;
    }
    const series = JSON.parse(read(new URL("series.json", folder))) as ThermalRow[];
    const ledger = read(new URL("ledger.jsonl", folder));
    const card = read(new URL("cards/water_temperature.json", examples(reach.id)));
    assert.ok(series.length > 0, reach.id);
    for (const row of series) {
      const result = await verifyRecord(read(new URL(row.file, folder)), ledger, card);
      assert.ok(result.sealed && result.inLedger && result.chainIntact, `${reach.id}/${row.file}`);
      assert.equal(result.cardMatches, true, `${reach.id}/${row.file}`);
    }
    const last = series.at(-1);
    assert.ok(last !== undefined);
    const altered = await verifyRecord(read(new URL(last.file, folder)), ledger, card, true);
    assert.equal(altered.sealed, false);
    assert.equal(altered.altered?.path, "estimate.value");
  }
});

void test("defaultThermal opens on the latest pass with a value", () => {
  const row = (value: number | null) =>
    ({ estimate: { level: "estimated", unit: "°C", value } }) as unknown as ThermalRow;
  assert.equal(defaultThermal([row(1), row(2), row(null)]), 1);
  assert.equal(defaultThermal([row(null)]), 0);
  assert.equal(defaultThermal([]), null);
});

void test("nearestThermal finds the Landsat pass with a value within 16 days", () => {
  const row = (date: string, value: number | null) =>
    ({ date, estimate: { level: "estimated", unit: "°C", value } }) as unknown as ThermalRow;
  const series = [row("2026-03-01", 5), row("2026-03-20", null), row("2026-04-02", 9)];
  assert.equal(nearestThermal(series, "2026-03-18"), 2); // the nearer pass has no value
  assert.equal(nearestThermal(series, "2026-03-03"), 0);
  assert.equal(nearestThermal(series, "2026-06-01"), null);
});

void test("thermalValidatedAt names the upstream gauge's place, or null", () => {
  const reach = (name?: string) =>
    ({
      thermal: {
        series: [],
        checks: [],
        card:
          name === undefined
            ? null
            : {
                validationSiteName: name,
              },
      },
    }) as unknown as Parameters<typeof thermalValidatedAt>[0];
  assert.equal(thermalValidatedAt(reach("Mississippi River at Baton Rouge, LA")), "Baton Rouge");
  assert.equal(thermalValidatedAt(reach()), null);
});

void test("outside the tested region the web says the frozen card's label, word for word", () => {
  const card = JSON.parse(
    readFileSync(
      new URL("../../docs/water-quality/ungauged/firat-birecik/turbidity.json", import.meta.url),
      "utf8",
    ),
  ) as { basis: string; label: string; expectedError?: unknown };
  assert.equal(card.basis, OUTSIDE_BASIS);
  assert.equal(card.label, CASE_COPY.ungauged.outsideLabel);
  assert.equal(card.expectedError, undefined, "no error estimate outside the tested region");
  assert.ok(isOutside({ card: card as never }));
  assert.ok(!isOutside({ card: null }));
});

void test("four classes place each pass in its band, and a three-class pass spans the bands it covers", () => {
  const four = [30, 50, 100];
  assert.deepEqual(classSpan("under_30", four), [0, 1]);
  assert.deepEqual(classSpan("30_to_50", four), [1, 2]);
  assert.deepEqual(classSpan("50_to_100", four), [2, 3]);
  assert.deepEqual(classSpan("100_and_over", four), [3, 4]);
  assert.deepEqual(classSpan("30_to_100", four), [1, 3]);
  assert.deepEqual(classSpan("30_to_100", [30, 100]), [1, 2]);
  assert.deepEqual(classEdges({ card: null }), [30, 100]);
  // Every class the pipeline can seal has words in the case view.
  for (const cls of ["under_30", "30_to_100", "100_and_over", "30_to_50", "50_to_100"] as const) {
    assert.ok(CASE_COPY.ungauged.classes[cls].endsWith("FNU") || cls === "100_and_over");
  }
  const card = JSON.parse(
    readFileSync(
      new URL(
        "../../docs/water-quality/ungauged/mississippi-st-joseph/turbidity-4.json",
        import.meta.url,
      ),
      "utf8",
    ),
  ) as { classes: { edgesFnu: number[]; labels: string[] } };
  assert.deepEqual(card.classes.edgesFnu, four);
  assert.deepEqual(card.classes.labels, ["under_30", "30_to_50", "50_to_100", "100_and_over"]);
});
