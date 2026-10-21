import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { canonical, parseJson, sha256Hex } from "../src/features/reaches/canonical.ts";
import { checkFile, csvRows, type CheckContext } from "../src/features/reaches/checkfile.ts";
import { csvOfSeries } from "../src/features/reaches/export.ts";
import type { SeriesRow } from "../src/features/reaches/types.ts";

// "Check a file" on the committed examples: a file someone was sent, against the sealed records.
const examples = (site: string) =>
  new URL(`../../docs/water-quality/reach/${site}/examples/`, import.meta.url);
const read = (url: URL) => readFileSync(url, "utf8");

// The context, with the series as the site has it (its rows' every field).
function context(
  site: string,
): Omit<CheckContext, "series"> & { readonly series: readonly SeriesRow[] } {
  const folder = examples(site);
  return {
    site,
    series: JSON.parse(read(new URL("series.json", folder))) as SeriesRow[],
    ledger: read(new URL("ledger.jsonl", folder)),
    load: (path) => Promise.resolve(read(new URL(path, folder))),
  };
}

// The record with one estimate's value changed; its fingerprint kept, or recomputed to match.
async function edited(text: string, value: number, rehash: boolean): Promise<string> {
  const record = JSON.parse(text) as Record<string, unknown> & {
    estimates: { value: number }[];
  };
  const first = record.estimates[0];
  assert.ok(first !== undefined);
  first.value = value;
  if (rehash) {
    const { recordSha256: _old, ...content } = record;
    record.recordSha256 = await sha256Hex(canonical(parseJson(JSON.stringify(content))));
  }
  return JSON.stringify(record, null, 2);
}

void test("a sealed record is identical; an edited one says what changed, with or without a new fingerprint", async () => {
  const ctx = context("mississippi-belle-chasse");
  const row = ctx.series.at(-1);
  assert.ok(row !== undefined);
  const text = await ctx.load(row.file);
  const same = await checkFile(text, ctx);
  assert.ok(same.kind === "record");
  assert.ok(same.identical && same.changes.length === 0);

  const sealedValue = (JSON.parse(text) as { estimates: { value: number }[] }).estimates[0]?.value;
  const kept = await checkFile(await edited(text, 99.5, false), ctx);
  assert.ok(kept.kind === "record");
  assert.equal(kept.selfSealed, false, "the content no longer matches its fingerprint");
  assert.equal(kept.inLedger, true, "the fingerprint it states is still the sealed one");
  assert.deepEqual(kept.changes, [
    { path: "estimates[0].value", sealed: String(sealedValue), given: "99.5" },
  ]);

  // Someone recomputes the fingerprint so the file matches itself: the ledger does not know it.
  const rehashed = await checkFile(await edited(text, 99.5, true), ctx);
  assert.ok(rehashed.kind === "record");
  assert.equal(rehashed.selfSealed, true);
  assert.equal(rehashed.inLedger, false);
  assert.equal(rehashed.identical, false);
  assert.deepEqual(
    rehashed.changes.map((c) => c.path),
    ["estimates[0].value"],
  );
});

void test("an earlier record a newer card replaced is still identical to its own sealed record", async () => {
  const ctx = context("mississippi-st-joseph");
  const row = ctx.series.find((r) => r.supersedes !== undefined);
  assert.ok(row !== undefined);
  const key = row.sceneId.split(":").at(-1) ?? "";
  const earlier = await ctx.load(`records/${row.date}_${key}.json`);
  assert.equal((JSON.parse(earlier) as { recordSha256: string }).recordSha256, row.supersedes);
  const check = await checkFile(earlier, ctx);
  assert.ok(check.kind === "record" && check.identical);
});

void test("a record of another reach is sent to its own case; other text is not a RiverEtch file", async () => {
  const joseph = context("mississippi-st-joseph");
  const ctx = context("mississippi-belle-chasse");
  const other = await joseph.load(joseph.series.at(-1)?.file ?? "");
  assert.deepEqual(await checkFile(other, ctx), {
    kind: "other-reach",
    site: "mississippi-st-joseph",
  });
  assert.deepEqual(await checkFile("date,value\n2026-01-01,3\n", ctx), { kind: "unreadable" });
  assert.deepEqual(await checkFile('{"hello": 1}', ctx), { kind: "unreadable" });
});

void test("the exported series matches every sealed record; an edited cell and a new fingerprint are found", async () => {
  for (const site of ["mississippi-belle-chasse", "mississippi-st-joseph", "firat-birecik"]) {
    const ctx = context(site);
    const csv = csvOfSeries({ series: ctx.series, checks: [] });
    const check = await checkFile(csv, ctx);
    assert.ok(check.kind === "series", site);
    assert.equal(check.rows.length, ctx.series.length, site);
    assert.ok(
      check.rows.every((r) => r.status === "same"),
      `${site}: ${JSON.stringify(check.rows.find((r) => r.status !== "same"))}`,
    );
  }
  const ctx = context("mississippi-belle-chasse");
  const rows = csvRows(csvOfSeries({ series: ctx.series, checks: [] }));
  const head = Object.keys(rows[0] ?? {});
  const at = rows.findIndex((r) => r.turbidity_fnu !== "");
  const changed = rows.map((r, k) =>
    k === at
      ? { ...r, turbidity_fnu: "120" }
      : k === at + 1
        ? { ...r, recordSha256: "0".repeat(64) }
        : r,
  );
  // A cell with a comma or a quote is quoted, as a spreadsheet writes it.
  const quote = (c: string) => (/[",]/.test(c) ? `"${c.replace(/"/g, '""')}"` : c);
  const text = [
    head.join(","),
    ...changed.map((r) => head.map((c) => quote(r[c] ?? "")).join(",")),
  ].join("\n");
  const check = await checkFile(text, ctx);
  assert.ok(check.kind === "series");
  const edit = check.rows[at];
  assert.ok(edit !== undefined);
  assert.equal(edit.status, "changed");
  assert.deepEqual(
    edit.changes.map((c) => [c.path, c.given]),
    [["turbidity_fnu", "120"]],
  );
  assert.equal(check.rows[at + 1]?.status, "unsealed");
  assert.equal(check.rows.filter((r) => r.status === "same").length, rows.length - 2);
});
