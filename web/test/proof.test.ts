import assert from "node:assert/strict";
import { test } from "node:test";

import type { ChainAnchor } from "../src/features/chain/ledger.ts";
import { canonical, parseJson, sha256Hex } from "../src/features/reaches/canonical.ts";
import { buildExport, planExport, type ProofIo } from "../src/features/reaches/proof.ts";
import { checkProofFile, NOTES, type CheckIo } from "../src/features/reaches/proofcheck.ts";
import type { ReachData } from "../src/features/reaches/types.ts";
import { makeZip, readZip } from "../src/features/reaches/zip.ts";

const enc = new TextEncoder();
const dec = new TextDecoder();

// A small reach with three sealed turbidity records, chained in its record list.
async function fixture() {
  const site = "x-river";
  const files = new Map<string, string>();
  const series = [];
  const lines: string[] = [];
  let previous: string | null = null;
  for (const [k, value] of ["12.5", "30.04", "101"].entries()) {
    const date = `2026-0${String(k + 1)}-10`;
    const sceneId = `${site}:s${String(k)}`;
    const content = `{"date":"${date}","estimates":[{"level":"validated","target":"turbidity","unit":"FNU","value":${value}}],"indices":{"ndti":{"downstream":0.01,"upstream":0.02}},"sceneId":"${sceneId}"}`;
    const seal = await sha256Hex(canonical(parseJson(content)));
    const record = `${content.slice(0, -1)},"recordSha256":"${seal}"}`;
    const file = `records/${date}_s${String(k)}.json`;
    files.set(file, record);
    const line = JSON.stringify({
      createdUtc: `2026-0${String(k + 1)}-11T00:00:00+00:00`,
      date,
      file,
      previousLineSha256: previous,
      recordSha256: seal,
      sceneId,
    });
    lines.push(line);
    previous = await sha256Hex(line);
    series.push({ date, sceneId, file, recordSha256: seal });
  }
  files.set("ledger.jsonl", `${lines.join("\n")}\n`);
  files.set("cards/turbidity.json", '{"modelId":"m"}');
  const reach = {
    base: "/x/",
    info: { site, cards: { turbidity: "cards/turbidity.json" } },
    series,
    thermal: null,
    along: null,
    alongTemperature: null,
  } as unknown as ReachData;
  const hashes = await Promise.all(lines.map((l) => sha256Hex(l)));
  // Ethereum holds the record list up to its second line.
  const chain: ChainAnchor[] = [
    { head: `0x${hashes[1] ?? ""}`, lines: 2, timestamp: 1, blockNumber: 7 },
  ];
  const io = (online = true): CheckIo & ProofIo => ({
    text: (_r, path) => Promise.resolve(files.get(path) ?? null),
    anchors: () => Promise.resolve(online ? chain : null),
    proofs: () => Promise.resolve([]),
    proof: () => Promise.resolve(null),
    signatures: () => Promise.resolve([]),
    reach: (id) => Promise.resolve(id === site ? reach : null),
    header: () => Promise.resolve(null),
    publicKey: "",
  });
  const meta = {
    exportedUtc: "2026-10-22T12:00:00Z",
    appVersion: "0.1.0",
    appCommit: "abc",
    publicKey: "00",
    cards: {},
  };
  const plan = await planExport([reach], ["turbidity"], null, null, io());
  const exported = await buildExport(plan, false, io(), meta);
  return { site, reach, io, plan, exported };
}

// The zip with one file's text changed.
async function edited(zip: Uint8Array, name: string, change: (text: string) => string) {
  const files = await readZip(zip);
  const entries = [...files].map(([n, data]) => ({
    name: n,
    data: n === name ? enc.encode(change(dec.decode(data))) : data,
  }));
  return makeZip(entries);
}

void test("a stored zip reads back byte for byte, and a damaged file is refused", async () => {
  const entries = [
    { name: "a.txt", data: enc.encode("hello") },
    { name: "dir/b.json", data: enc.encode('{"x":1}') },
  ];
  const zip = makeZip(entries, new Date("2026-10-22T00:00:00Z"));
  const files = await readZip(zip);
  assert.deepEqual([...files.keys()], ["a.txt", "dir/b.json"]);
  assert.equal(dec.decode(files.get("a.txt")), "hello");
  const broken = zip.slice();
  const at = 30 + "a.txt".length; // the first file's first byte
  broken[at] = (broken[at] ?? 0) ^ 1;
  await assert.rejects(readZip(broken), /damaged/);
});

void test("the export counts each board apart, and its check finds every row unchanged", async () => {
  const { plan, exported, io } = await fixture();
  assert.deepEqual(plan.total, { readings: 3, ethereum: 2, bitcoin: 0, waiting: 1 });
  const files = await readZip(exported.zip);
  for (const name of [
    "READ-ME.txt",
    "manifest.json",
    "data/x-river/turbidity.csv",
    "ledgers/x-river/ledger.jsonl",
    "proof/anchors.json",
    "keys/ml-dsa-65.json",
  ]) {
    assert.ok(files.has(name), name);
  }
  assert.match(dec.decode(files.get("READ-ME.txt")), new RegExp(exported.manifestSha256));
  const report = await checkProofFile(exported.zip, io());
  assert.ok(report !== null);
  assert.equal(report.kind, "zip");
  assert.equal(report.rows, 3);
  assert.equal(report.unchanged, 3);
  assert.equal(report.ethereum, 2);
  assert.equal(report.waiting, 1);
  assert.deepEqual(
    [report.changed, report.notFound, report.missing, report.notes],
    [[], [], [], []],
  );
  assert.equal(report.manifestSha256, exported.manifestSha256);
});

void test("one changed cell is reported with its row, its column and the sealed value", async () => {
  const { exported, io } = await fixture();
  const zip = await edited(exported.zip, "data/x-river/turbidity.csv", (t) =>
    t.replace(",30.04,", ",3.04,"),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.changed.length, 1);
  const issue = report.changed[0];
  assert.equal(issue?.row, 2);
  assert.deepEqual(issue.changes, [{ column: "turbidity_fnu", sealed: "30.04", given: "3.04" }]);
  assert.equal(report.unchanged, 2);
  assert.ok(report.notes.includes(NOTES.manifest("data/x-river/turbidity.csv")));
});

// The export's folder zipped again (Windows "Send to > Compressed folder", macOS "Compress"): every
// file sits under that folder, and a spreadsheet saved the CSV with CRLF.
async function rezipped(zip: Uint8Array, change: (name: string, text: string) => string) {
  const files = await readZip(zip);
  return makeZip(
    [...files].map(([n, data]) => ({
      name: `riveretch-x-river-2026-10-22/${n}`,
      data: enc.encode(change(n, dec.decode(data))),
    })),
  );
}

void test("a zip made again from the export's folder is read from inside that folder", async () => {
  const { exported, io } = await fixture();
  const zip = await rezipped(exported.zip, (n, t) =>
    n === "data/x-river/turbidity.csv" ? t.replace(",30.04,", ",3.04,").replace(/\n/g, "\r\n") : t,
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.rows, 3);
  assert.equal(report.changed.length, 1);
  assert.deepEqual(report.changed[0]?.changes, [
    { column: "turbidity_fnu", sealed: "30.04", given: "3.04" },
  ]);
  assert.equal(report.manifestSha256, exported.manifestSha256);
  assert.ok(report.notes.includes(NOTES.manifest("data/x-river/turbidity.csv")));
});

void test("a record changed inside a zip is reported on its reading's row", async () => {
  const { exported, io } = await fixture();
  const files = await readZip(exported.zip);
  const recordName = [...files.keys()].find((n) => n.startsWith("records/") && n.includes("_s1"));
  assert.ok(recordName !== undefined, "the export holds the sealed records");
  const zip = await edited(exported.zip, recordName, (t) =>
    t.replace('"upstream":0.02', '"upstream":0.05'),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.rows, 3, "a record file is not a row of its own");
  assert.equal(report.changed.length, 1);
  const issue = report.changed[0];
  assert.equal(issue?.row, 2);
  assert.equal(issue.file, recordName);
  assert.ok(issue.changes.some((c) => c.column === "(content)" && c.file === recordName));
  assert.ok(
    issue.changes.some(
      (c) => c.column === "ndti_upstream" && c.sealed === "0.02" && c.given === "0.05",
    ),
  );
  assert.equal(report.unchanged, 2);
});

void test("a zip without a RiverEtch row is not a RiverEtch file, never a pass", async () => {
  const { io } = await fixture();
  const zip = makeZip([{ name: "notes/a.txt", data: enc.encode("hello") }]);
  assert.equal(await checkProofFile(zip, io()), null);
});

void test("a deleted row is reported missing", async () => {
  const { exported, io } = await fixture();
  const zip = await edited(exported.zip, "data/x-river/turbidity.csv", (t) =>
    t
      .split("\n")
      .filter((l) => !l.includes("x-river:s1"))
      .join("\n"),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.rows, 2);
  assert.deepEqual(
    report.missing.map((m) => m.sceneId),
    ["x-river:s1"],
  );
});

void test("a row from another reach is not found", async () => {
  const { exported, io } = await fixture();
  const zip = await edited(exported.zip, "data/x-river/turbidity.csv", (t) =>
    t.replace("turbidity,x-river,x-river:s2", "turbidity,y-river,y-river:s2"),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.deepEqual(
    report.notFound.map((m) => m.sceneId),
    ["y-river:s2"],
  );
});

void test("posts listed inside a zip that Ethereum does not hold are never trusted", async () => {
  const { exported, io } = await fixture();
  const zip = await edited(exported.zip, "proof/anchors.json", (t) =>
    t
      .replace(/"lines": 2/, '"lines": 3')
      .replace(/"head": "0x[0-9a-f]+"/, `"head": "0x${"ab".repeat(32)}"`),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.ok(report.notes.includes(NOTES.anchorsIgnored));
  assert.equal(report.ethereum, 2, "the chain's two posts, not the zip's claim of three");
});

void test("without the chain, nothing is counted as on Ethereum", async () => {
  const { exported, io } = await fixture();
  const report = await checkProofFile(exported.zip, io(false));
  assert.ok(report !== null);
  assert.equal(report.unchanged, 3);
  assert.equal(report.ethereum, null);
  assert.equal(report.waiting, null);
});

void test("a lone record file is checked against the site's sealed record", async () => {
  const { exported, io } = await fixture();
  const files = await readZip(exported.zip);
  const name = [...files.keys()].find((n) => n.startsWith("records/") && n.includes("_s0"));
  assert.ok(name !== undefined);
  const record = files.get(name);
  assert.ok(record !== undefined);
  const same = await checkProofFile(record, io());
  assert.equal(same?.unchanged, 1);
  const changed = await checkProofFile(
    enc.encode(dec.decode(record).replace(":12.5", ":99")),
    io(),
  );
  assert.equal(changed?.changed.length, 1);
});

// A reach's daily flow record (preregistration-daily-record.md): one sealed year of three days.
async function flowFixture() {
  const site = "x-river";
  const content = {
    schemaVersion: 1,
    kind: "daily_record",
    reachId: site,
    recordId: `${site}:daily-record:2026`,
    year: 2026,
    date: "2026-10-03",
    source: { kind: "usgs", stationId: "USGS-1", name: "A station", measured: true, url: "u" },
    series: [
      {
        parameter: "00060",
        name: "discharge",
        unit: "ft³/s",
        days: [
          ["2026-10-01", 1000.0, "Approved"],
          ["2026-10-02", 2000.5, "Provisional"],
          ["2026-10-03", 3000.0, "Provisional"],
        ],
      },
    ],
    fetchedUtc: "2026-10-04T00:10:00+00:00",
    replaces: null,
    provenance: { api: "a", query: {}, codeCommit: "c" },
  };
  const text = JSON.stringify(content)
    .replace('"days":[["2026-10-01",1000,', '"days":[["2026-10-01",1000.0,')
    .replace('3000,"Provisional"]', '3000.0,"Provisional"]');
  const seal = await sha256Hex(canonical(parseJson(text)));
  const record = `${text.slice(0, -1)},"recordSha256":"${seal}"}`;
  const file = "records/2026_20261004T001000Z.json";
  const line = JSON.stringify({
    createdUtc: "2026-10-04T00:10:00+00:00",
    date: "2026-10-03",
    file,
    previousLineSha256: null,
    recordSha256: seal,
    sceneId: `${site}:daily-record:2026`,
  });
  const files = new Map([
    [`daily-record/${file}`, record],
    ["daily-record/ledger.jsonl", `${line}\n`],
  ]);
  const reach = {
    base: "/x/",
    info: { site, cards: {} },
    series: [],
    thermal: null,
    along: null,
    alongTemperature: null,
    dailyRecord: [
      {
        year: 2026,
        recordId: `${site}:daily-record:2026`,
        file,
        recordSha256: seal,
        date: "2026-10-03",
        fetchedUtc: "2026-10-04T00:10:00+00:00",
        records: 1,
        days: 3,
      },
    ],
  } as unknown as ReachData;
  const io = (): CheckIo & ProofIo => ({
    text: (_r, path) => Promise.resolve(files.get(path) ?? null),
    anchors: () => Promise.resolve([]),
    proofs: () => Promise.resolve([]),
    proof: () => Promise.resolve(null),
    signatures: () => Promise.resolve([]),
    reach: (id) => Promise.resolve(id === site ? reach : null),
    header: () => Promise.resolve(null),
    publicKey: "",
  });
  const meta = {
    exportedUtc: "2026-10-22T12:00:00Z",
    appVersion: "0",
    appCommit: "a",
    publicKey: "00",
    cards: {},
  };
  const plan = await planExport([reach], ["dailyFlow"], null, null, io());
  const exported = await buildExport(plan, false, io(), meta);
  return { io, exported, file };
}

void test("the daily flow exports one row per day, each checked against that day of its record", async () => {
  const { io, exported } = await flowFixture();
  const files = await readZip(exported.zip);
  const csv = dec.decode(files.get("data/x-river/daily-flow.csv"));
  const lines = csv.trim().split("\n");
  assert.equal(lines.length, 4, "a header and three days");
  assert.match(
    lines[0] ?? "",
    /^dataset,reach,sceneId,date,discharge,discharge_unit,discharge_status,recordSha256$/,
  );
  assert.match(
    lines[2] ?? "",
    /^dailyFlow,x-river,x-river:daily-record:2026,2026-10-02,2000\.5,ft³\/s,Provisional,/,
  );
  const same = await checkProofFile(exported.zip, io());
  assert.ok(same !== null);
  assert.equal(same.rows, 3);
  assert.equal(same.unchanged, 3);
  assert.deepEqual([same.changed, same.missing], [[], []]);

  // One day's value changed, and another day deleted from the table.
  const changedZip = (() => {
    const entries = [...files].map(([n, data]) => ({
      name: n,
      data:
        n === "data/x-river/daily-flow.csv"
          ? enc.encode(
              dec
                .decode(data)
                .replace(",2026-10-02,2000.5,", ",2026-10-02,2200.5,")
                .split("\n")
                .filter((l) => !l.includes(",2026-10-03,"))
                .join("\n"),
            )
          : data,
    }));
    return makeZip(entries);
  })();
  const report = await checkProofFile(changedZip, io());
  assert.ok(report !== null);
  assert.equal(report.rows, 2);
  assert.equal(report.changed.length, 1);
  assert.deepEqual(report.changed[0]?.changes, [
    { column: "discharge", sealed: "2000.5", given: "2200.5" },
  ]);
  assert.deepEqual(
    report.missing.map((m) => m.date),
    ["2026-10-03"],
    "a day deleted from the file is missing",
  );
});

void test("a daily record edited inside the zip shows once, on its first day", async () => {
  const { io, exported, file } = await flowFixture();
  const zip = await edited(exported.zip, `records/x-river/daily-record/${file}`, (t) =>
    t.replace('"2026-10-02",2000.5', '"2026-10-02",2500.5'),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.changed.length, 1, "not once per day");
  const first = report.changed[0];
  assert.equal(first?.row, 1);
  assert.ok(first.changes.some((c) => c.column === "(content)"));
  assert.equal(report.unchanged, 2);
});

void test("a column deleted from a table is reported, not passed", async () => {
  const { exported, io } = await fixture();
  const zip = await edited(exported.zip, "data/x-river/turbidity.csv", (text) =>
    text
      .split("\n")
      .map((line) => {
        const cells = line.split(",");
        cells.splice(5, 1); // turbidity_fnu
        return cells.join(",");
      })
      .join("\n"),
  );
  const report = await checkProofFile(zip, io());
  assert.ok(report !== null);
  assert.equal(report.changed.length, 3, "every row lost its value");
  assert.deepEqual(report.changed[0]?.changes, [
    { column: "turbidity_fnu", sealed: "12.5", given: "" },
  ]);
  assert.ok(report.notes.includes(NOTES.columnMissing("turbidity_fnu")));
});
