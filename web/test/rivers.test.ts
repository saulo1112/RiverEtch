import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { CASE_COPY } from "../src/features/case/content.ts";
import { insideCount } from "../src/features/case/reading.ts";
import { DEMO_GAUGES, medianError, oneDecimal, riverResults } from "../src/features/case/rivers.ts";
import { REACH_CASES } from "../src/features/reaches/catalog.ts";

const DOCS = new URL("../../docs/water-quality/", import.meta.url);
const read = (path: string) => readFileSync(new URL(path, DOCS), "utf8");
const rivers = riverResults(read("results/v5_levels.csv"), read("results/v5_scores.csv"));

void test("the honest summary is the median over the nine rated rivers: 33.1 %", () => {
  assert.equal(rivers.length, 10);
  assert.equal(rivers.filter((r) => r.level !== null).length, 9);
  assert.equal(oneDecimal(medianError(rivers)), "33.1");
  assert.equal(oneDecimal(46.25), "46.2"); // ties to even, as the report
  assert.equal(oneDecimal(46.35), "46.4");
  assert.equal(oneDecimal(113.671875), "113.7");
});

void test("the demo reaches are the best two, and their gauges are the cases' own", () => {
  assert.deepEqual(
    rivers.slice(0, 2).map((r) => r.site),
    DEMO_GAUGES,
  );
  const stations = REACH_CASES.map((c) => {
    const info = JSON.parse(read(`reach/${c.id}/examples/reach.json`)) as {
      station: { id: string };
    };
    return info.station.id;
  });
  assert.deepEqual(stations, DEMO_GAUGES);
});

void test("each row matches the report's table: name, error, pairs, baseline and level", () => {
  const report = read("report.md");
  for (const r of rivers) {
    const name = CASE_COPY.rivers.names[r.site];
    assert.ok(name !== undefined, `${r.site} has a display name`);
    const gauge = r.site.replace("USGS-", "");
    const line = report.split("\n").find((l) => l.includes(`${name} (${gauge})`));
    assert.ok(line !== undefined, `the report lists ${name} (${gauge})`);
    const cells = line.split("|").map((c) => c.replace(/\*/g, "").trim());
    assert.equal(cells[3], String(r.n), `${name}: pairs`);
    if (r.level === null) {
      assert.equal(cells[7], "insufficient data");
      continue;
    }
    assert.equal(cells[2], `${oneDecimal(r.mdsa ?? 0)} %`, `${name}: error`);
    assert.equal(cells[4], `${oneDecimal(r.nullMdsa ?? 0)} %`, `${name}: baseline`);
    assert.equal(cells[7], r.level, `${name}: level`);
  }
});

void test("the demo reaches' inside counts match their cards", () => {
  const [belle, platte] = rivers;
  assert.equal(insideCount(belle?.coverage90 ?? 0, belle?.n ?? 0), 54);
  assert.equal(insideCount(platte?.coverage90 ?? 0, platte?.n ?? 0), 50);
});
