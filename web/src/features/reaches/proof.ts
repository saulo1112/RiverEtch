// "Export with proof": a reach's sealed readings as one zip, with what proves they have not
// changed since they were fixed. Each dataset (turbidity, water temperature, and both along the
// river) becomes a CSV whose every row carries its record's fingerprint (recordSha256), its cells
// copied from the sealed record itself; beside them, the sealed records, the full record lists
// (ledgers), the posts on Ethereum read at export time, the Bitcoin timestamps and the signatures
// that cover the rows, the public key, the model sheets, a manifest of every file with its
// SHA-256, and a short READ-ME. Everything is built in the browser; nothing is uploaded. A
// fingerprint proves a reading was not changed after its date, not that the reading is right.
import {
  anchorStatus,
  ledgerPath,
  subjectLabel,
  type ChainAnchor,
  type LedgerKind,
} from "../chain/ledger.ts";
import type { HeadSignature } from "../chain/mldsa.ts";
import { coveringProof, type ProofEntry } from "../chain/witness.ts";
import { NumberText, parseJson, sha256Hex, type JsonValue } from "./canonical.ts";
import type { ReachData } from "./types.ts";
import { makeZip, type ZipEntry } from "./zip.ts";

/** The site anyone checks an export at. */
export const SITE_URL = "https://river-etch.vercel.app";

/** A dataset a reach can export. */
export type DatasetId = "turbidity" | "temperature" | "along" | "alongTemperature" | "dailyFlow";

/** Where a dataset's records live, and how its CSV is named. */
export const DATASETS: Readonly<
  Record<DatasetId, { readonly kind: LedgerKind; readonly folder: string; readonly csv: string }>
> = {
  turbidity: { kind: "observations", folder: "", csv: "turbidity.csv" },
  temperature: { kind: "water-temperature", folder: "thermal/", csv: "water-temperature.csv" },
  along: { kind: "along", folder: "along/", csv: "turbidity-along-the-river.csv" },
  alongTemperature: {
    kind: "along-temperature",
    folder: "along-temperature/",
    csv: "temperature-along-the-river.csv",
  },
  // The station's (or model's) daily flow, one row per day (preregistration-daily-record.md).
  dailyFlow: { kind: "daily-record", folder: "daily-record/", csv: "daily-flow.csv" },
};

/** The datasets, in the order they are offered. */
export const DATASET_IDS: readonly DatasetId[] = [
  "turbidity",
  "temperature",
  "along",
  "alongTemperature",
  "dailyFlow",
];

/** One sealed reading a dataset holds: its pass and fingerprint, and its record's file. */
export interface ProofRow {
  readonly sceneId: string;
  readonly date: string;
  readonly recordSha256: string;
  /** The record's path in the reach's folder (null: the series does not name it). */
  readonly file: string | null;
}

/**
 * A dataset's sealed readings.
 *
 * @param reach - The reach (its sealed year).
 * @param dataset - The dataset.
 * @returns Its rows, oldest first (empty where the reach has none).
 */
export function rowsOf(reach: ReachData, dataset: DatasetId): ProofRow[] {
  const folder = DATASETS[dataset].folder;
  if (dataset === "dailyFlow") {
    return (reach.dailyRecord ?? [])
      .map((r) => ({
        sceneId: r.recordId,
        date: r.date,
        recordSha256: r.recordSha256,
        file: `${folder}${r.file}`,
      }))
      .sort((a, b) => a.date.localeCompare(b.date) || a.sceneId.localeCompare(b.sceneId));
  }
  const rows: ProofRow[] =
    dataset === "turbidity"
      ? reach.series.map((r) => ({ ...r, file: r.file }))
      : dataset === "temperature"
        ? (reach.thermal?.series ?? []).map((r) => ({ ...r, file: `${folder}${r.file}` }))
        : (dataset === "along" ? (reach.along?.passes ?? []) : (reach.alongTemperature ?? [])).map(
            (p) => ({ ...p, file: p.file === undefined ? null : `${folder}${p.file}` }),
          );
  return rows
    .map((r) => ({ sceneId: r.sceneId, date: r.date, recordSha256: r.recordSha256, file: r.file }))
    .sort((a, b) => a.date.localeCompare(b.date) || a.sceneId.localeCompare(b.sceneId));
}

/**
 * Whether a date lies in a period (both ends included; null: open).
 *
 * @param date - An ISO date.
 * @param from - The first day.
 * @param to - The last day.
 * @returns True inside.
 */
export function inPeriod(date: string, from: string | null, to: string | null): boolean {
  return (from === null || date >= from) && (to === null || date <= to);
}

type JsonObject = Record<string, JsonValue>;

function isObject(value: JsonValue | undefined): value is JsonObject {
  return (
    value !== null &&
    value !== undefined &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    !(value instanceof NumberText)
  );
}

// A value as a CSV cell: a number exactly as the record writes it.
function text(value: JsonValue | undefined): string {
  if (value === undefined || value === null) {
    return "";
  }
  if (value instanceof NumberText) {
    return value.text;
  }
  return typeof value === "string" || typeof value === "boolean" ? String(value) : "";
}

const field = (o: JsonValue | undefined, key: string): JsonValue | undefined =>
  isObject(o) ? o[key] : undefined;

/**
 * A sealed record's values as a dataset's CSV writes them (its fingerprint aside).
 *
 * @param dataset - The dataset.
 * @param record - The record.
 * @returns Column name to cell.
 */
export function recordCells(dataset: DatasetId, record: JsonValue): Record<string, string> {
  if (dataset === "dailyFlow") {
    // A whole year: its days are its rows (dayRows); the record itself, by its last day.
    return { date: text(field(record, "date")) };
  }
  if (dataset === "turbidity") {
    const estimates = field(record, "estimates");
    const e = Array.isArray(estimates)
      ? estimates.find((x) => field(x, "target") === "turbidity")
      : undefined;
    const ndti = field(field(record, "indices"), "ndti");
    return {
      date: text(field(record, "date")),
      level: text(field(e, "level")),
      turbidity_fnu: text(field(e, "value")),
      interval90_low: text(field(field(e, "interval"), "low")),
      interval90_high: text(field(field(e, "interval"), "high")),
      turbidity_class: text(field(e, "fnuClass")),
      abstain_reason: text(field(e, "abstainReason")),
      ndti_upstream: text(field(ndti, "upstream")),
      ndti_downstream: text(field(ndti, "downstream")),
    };
  }
  if (dataset === "temperature") {
    const e = field(record, "estimate");
    const window = field(record, "window");
    return {
      date: text(field(record, "date")),
      platform: text(field(record, "platform")),
      level: text(field(e, "level")),
      water_temperature_c: text(field(e, "value")),
      interval90_low: text(field(field(e, "interval"), "low")),
      interval90_high: text(field(field(e, "interval"), "high")),
      water_pixels: text(field(window, "waterPixels")),
      surface_temperature_k: text(field(window, "surfaceTemperatureK")),
    };
  }
  const key = dataset === "along" ? "fnuClass" : "temperatureClass";
  const windows = field(record, "windows");
  const out: Record<string, string> = { date: text(field(record, "date")) };
  // A record with values (riveretch.along-river.v2, preregistration-values.md): each window's
  // value in FNU beside its class.
  const valued = dataset === "along" && text(field(record, "schema")).endsWith(".v2");
  for (const w of Array.isArray(windows) ? windows : []) {
    out[text(field(w, "id"))] = text(field(w, key));
    if (valued) {
      out[`${text(field(w, "id"))}_fnu`] = text(field(w, "fnuValue"));
    }
  }
  return out;
}

// A daily record's series as columns: "discharge", "discharge_unit", "discharge_status", ...
const columnOf = (name: string) => name.trim().replace(/\s+/g, "_");

/**
 * A daily flow record's days as CSV rows: the day, then each series' value, unit and status as the
 * source published them.
 *
 * @param record - A sealed daily record.
 * @returns One cell map per day, in day order.
 */
export function dayRows(record: JsonValue): Record<string, string>[] {
  const series = field(record, "series");
  const days = new Map<string, Record<string, string>>();
  for (const s of Array.isArray(series) ? series : []) {
    const column = columnOf(text(field(s, "name")));
    const unit = text(field(s, "unit"));
    const values = field(s, "days");
    for (const day of Array.isArray(values) ? values : []) {
      if (!Array.isArray(day)) {
        continue;
      }
      const date = text(day[0]);
      const row = days.get(date) ?? { date };
      row[column] = text(day[1]);
      row[`${column}_unit`] = unit;
      row[`${column}_status`] = text(day[2]);
      days.set(date, row);
    }
  }
  return [...days.values()].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? ""));
}

// One CSV cell, quoted when it must be.
function cell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

/**
 * A dataset's CSV: `dataset`, `reach`, `sceneId`, the sealed values, then `recordSha256`.
 *
 * @param dataset - The dataset.
 * @param site - The reach.
 * @param rows - Each row's pass and sealed values.
 * @returns The file's text.
 */
export function csvOf(
  dataset: DatasetId,
  site: string,
  rows: readonly { readonly row: ProofRow; readonly cells: Record<string, string> }[],
): string {
  const columns = [...new Set(rows.flatMap((r) => Object.keys(r.cells)))];
  const head = ["dataset", "reach", "sceneId", ...columns, "recordSha256"];
  const lines = rows.map((r) =>
    [dataset, site, r.row.sceneId, ...columns.map((c) => r.cells[c] ?? ""), r.row.recordSha256]
      .map(cell)
      .join(","),
  );
  return `${[head.join(","), ...lines].join("\n")}\n`;
}

/** What reading the chain and the published files gives an export or a check. */
export interface ProofIo {
  /** A reach's file as text (null: missing). */
  readonly text: (reach: ReachData, path: string) => Promise<string | null>;
  /** A ledger's posts on Ethereum (null: the chain could not be read). */
  readonly anchors: (label: string) => Promise<readonly ChainAnchor[] | null>;
  /** The Bitcoin timestamps the daily run lists (empty: none readable). */
  readonly proofs: () => Promise<readonly ProofEntry[]>;
  /** A published proof's bytes (null: not readable). */
  readonly proof: (file: string) => Promise<Uint8Array | null>;
  /** The published signatures of ledger heads. */
  readonly signatures: () => Promise<readonly HeadSignature[]>;
}

/** How many readings each board holds, counted separately. */
export interface BoardCounts {
  readonly readings: number;
  /** Posted on Ethereum and matching the record list (null: the chain could not be read). */
  readonly ethereum: number | null;
  /** Covered by a Bitcoin timestamp already in a block. */
  readonly bitcoin: number;
  /** Not on Ethereum yet: waiting for the next post (null: the chain could not be read). */
  readonly waiting: number | null;
}

/** One dataset of one reach in an export. */
export interface ExportPart {
  readonly reach: ReachData;
  readonly dataset: DatasetId;
  readonly label: string;
  /** The rows in the period, each with its line in the record list. */
  readonly rows: readonly (ProofRow & { readonly position: number })[];
  /** The whole record list (ledger) as published. */
  readonly ledger: string;
  /** Its lines' hashes, hex. */
  readonly lineHashes: readonly string[];
  /** Its posts on Ethereum (null: not read). */
  readonly anchors: readonly ChainAnchor[] | null;
  readonly counts: BoardCounts;
}

/** An export's selection and what it counts, before anything is downloaded. */
export interface ExportPlan {
  readonly parts: readonly ExportPart[];
  readonly from: string | null;
  readonly to: string | null;
  readonly total: BoardCounts;
}

// A ledger's lines and their hashes.
async function ledgerLines(textOfLedger: string): Promise<{ lines: string[]; hashes: string[] }> {
  const lines = textOfLedger.split("\n").filter((l) => l.trim() !== "");
  return { lines, hashes: await Promise.all(lines.map((l) => sha256Hex(l))) };
}

/**
 * Counts what an export would hold: per reach and dataset, the readings in the period and how
 * many are on each board.
 *
 * @param reaches - The reaches (their sealed year).
 * @param datasets - The datasets chosen.
 * @param from - The period's first day (null: open).
 * @param to - The period's last day (null: open).
 * @param io - The chain and the published files.
 * @returns The plan.
 */
export async function planExport(
  reaches: readonly ReachData[],
  datasets: readonly DatasetId[],
  from: string | null,
  to: string | null,
  io: ProofIo,
): Promise<ExportPlan> {
  const proofs = await io.proofs();
  const parts: ExportPart[] = [];
  for (const reach of reaches) {
    for (const dataset of datasets) {
      const all = rowsOf(reach, dataset);
      if (all.length === 0) {
        continue;
      }
      const { kind } = DATASETS[dataset];
      const ledger = (await io.text(reach, ledgerPath(kind))) ?? "";
      const { lines, hashes } = await ledgerLines(ledger);
      const at = new Map(
        lines.map((l, k) => [(JSON.parse(l) as { recordSha256: string }).recordSha256, k]),
      );
      const rows = all
        .filter((r) => inPeriod(r.date, from, to))
        .flatMap((r) => {
          const position = at.get(r.recordSha256);
          return position === undefined ? [] : [{ ...r, position }];
        });
      if (rows.length === 0) {
        continue;
      }
      const label = subjectLabel(reach.info.site, kind);
      const anchors = await io.anchors(label);
      const prefixed = hashes.map((h) => `0x${h}`);
      const ethereum =
        anchors === null
          ? null
          : rows.filter((r) => anchorStatus(anchors, r.position, prefixed).state === "anchored")
              .length;
      const bitcoin = rows.filter(
        (r) => (coveringProof(proofs, label, r.position)?.height ?? null) !== null,
      ).length;
      parts.push({
        reach,
        dataset,
        label,
        rows,
        ledger,
        lineHashes: hashes,
        anchors,
        counts: {
          readings: rows.length,
          ethereum,
          bitcoin,
          waiting: ethereum === null ? null : rows.length - ethereum,
        },
      });
    }
  }
  const sum = (pick: (c: BoardCounts) => number | null): number | null =>
    parts.some((p) => pick(p.counts) === null)
      ? null
      : parts.reduce((n, p) => n + (pick(p.counts) ?? 0), 0);
  return {
    parts,
    from,
    to,
    total: {
      readings: parts.reduce((n, p) => n + p.counts.readings, 0),
      ethereum: sum((c) => c.ethereum),
      bitcoin: parts.reduce((n, p) => n + p.counts.bitcoin, 0),
      waiting: sum((c) => c.waiting),
    },
  };
}

/** What the export names about itself. */
export interface ExportMeta {
  readonly exportedUtc: string;
  readonly appVersion: string;
  readonly appCommit: string;
  /** The ML-DSA-65 public key that signs record-list heads, hex. */
  readonly publicKey: string;
  /** A model sheet's text by its path (the along-the-river sheets copied into the build). */
  readonly cards: Readonly<Record<string, string>>;
}

/** An export's files, its manifest's fingerprint and the zip. */
export interface ExportFile {
  readonly zip: Uint8Array;
  readonly manifestSha256: string;
  readonly name: string;
}

const encoder = new TextEncoder();
const utf8 = (value: string) => encoder.encode(value);

// Runs `fn` over `items`, at most `limit` at a time, keeping their order.
async function pool<T, R>(items: readonly T[], limit: number, fn: (item: T) => Promise<R>) {
  const out: R[] = new Array<R>(items.length);
  let next = 0;
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, async () => {
      while (next < items.length) {
        const k = next;
        next += 1;
        out[k] = await fn(items[k] as T);
      }
    }),
  );
  return out;
}

/**
 * Builds the export: the CSVs from the sealed records, the records, the full record lists, the
 * posts on Ethereum, the Bitcoin timestamps and signatures that cover the rows, the public key,
 * the model sheets, the reach shape if asked, a manifest and a READ-ME.
 *
 * @param plan - What to export ({@link planExport}).
 * @param shape - Add each reach's shape (GeoJSON).
 * @param io - The chain and the published files.
 * @param meta - The export's time, the app's version and commit, the key and the model sheets.
 * @returns The zip and its manifest's fingerprint.
 */
export async function buildExport(
  plan: ExportPlan,
  shape: boolean,
  io: ProofIo,
  meta: ExportMeta,
): Promise<ExportFile> {
  const files: ZipEntry[] = [];
  const manifestParts: JsonValue[] = [];
  const proofs = await io.proofs();
  const signatures = await io.signatures();
  const proofFiles = new Set<string>();
  const signed: HeadSignature[] = [];
  const anchorsOut: Record<string, JsonValue> = {};
  const cards = new Map<string, string>();
  for (const part of plan.parts) {
    const site = part.reach.info.site;
    const { folder, csv } = DATASETS[part.dataset];
    const rows = await pool(part.rows, 8, async (row) => {
      const file = row.file ?? (await fileFromLedger(part.ledger, row.recordSha256, folder));
      const recordText = file === null ? null : await io.text(part.reach, file);
      return { row, file, recordText };
    });
    const withCells = rows.flatMap(({ row, file, recordText }) => {
      const record = recordText === null ? null : parseJson(recordText);
      if (file !== null && recordText !== null) {
        files.push({ name: `records/${site}/${file}`, data: utf8(recordText) });
      }
      if (record === null) {
        return [{ row, cells: {} }];
      }
      // A daily flow record: one row per day.
      return part.dataset === "dailyFlow"
        ? dayRows(record).map((cells) => ({ row, cells }))
        : [{ row, cells: recordCells(part.dataset, record) }];
    });
    files.push({ name: `data/${site}/${csv}`, data: utf8(csvOf(part.dataset, site, withCells)) });
    files.push({
      name: `ledgers/${site}/${ledgerPath(DATASETS[part.dataset].kind)}`,
      data: utf8(part.ledger),
    });
    // The timestamps and signatures of heads that cover at least the part's first row.
    const first = Math.min(...part.rows.map((r) => r.position));
    for (const p of proofs) {
      if (p.label === part.label && p.lines >= first + 1) {
        proofFiles.add(p.file);
      }
    }
    signed.push(...signatures.filter((x) => x.label === part.label && x.lines >= first + 1));
    if (part.anchors !== null) {
      anchorsOut[part.label] = part.anchors.map((a) => ({
        head: a.head,
        lines: a.lines,
        blockNumber: a.blockNumber,
        timestamp: a.timestamp,
      })) as unknown as JsonValue;
    }
    // The model sheets the records name: the reach's own cards, or the along-the-river sheet.
    for (const path of cardPaths(part)) {
      if (!cards.has(path)) {
        const card = meta.cards[path] ?? (await io.text(part.reach, path));
        if (card !== null) {
          cards.set(path, card);
        }
      }
    }
    manifestParts.push({
      reach: site,
      dataset: part.dataset,
      label: part.label,
      csv: `data/${site}/${csv}`,
      rows: part.rows.length,
      fingerprints: part.rows.map((r) => r.recordSha256),
    } as unknown as JsonValue);
    if (shape) {
      const geometry = await io.text(part.reach, "geometry.geojson");
      if (geometry !== null && !files.some((f) => f.name === `shape/${site}.geojson`)) {
        files.push({ name: `shape/${site}.geojson`, data: utf8(geometry) });
      }
    }
  }
  for (const file of [...proofFiles].sort()) {
    const bytes = await io.proof(file);
    if (bytes !== null) {
      files.push({ name: `proof/ots/${file.split("/").at(-1) ?? file}`, data: bytes });
    }
  }
  files.push({
    name: "proof/anchors.json",
    data: utf8(`${JSON.stringify({ readUtc: meta.exportedUtc, anchors: anchorsOut }, null, 1)}\n`),
  });
  files.push({
    name: "proof/signatures.jsonl",
    data: utf8(signed.map((s) => JSON.stringify(s)).join("\n") + (signed.length > 0 ? "\n" : "")),
  });
  files.push({
    name: "keys/ml-dsa-65.json",
    data: utf8(
      `${JSON.stringify({ algorithm: "ML-DSA-65", publicKey: meta.publicKey }, null, 1)}\n`,
    ),
  });
  for (const [path, card] of cards) {
    files.push({ name: `models/${path.replace(/^docs\//, "")}`, data: utf8(card) });
  }
  const listed = await Promise.all(
    files.map(async (f) => ({
      path: f.name,
      bytes: f.data.length,
      sha256: await sha256Bytes(f.data),
    })),
  );
  const manifest = `${JSON.stringify(
    {
      schema: "riveretch.export.v1",
      exportedUtc: meta.exportedUtc,
      app: { version: meta.appVersion, commit: meta.appCommit, site: SITE_URL },
      period: { from: plan.from, to: plan.to },
      parts: manifestParts,
      files: listed,
    },
    null,
    1,
  )}\n`;
  const manifestSha256 = await sha256Hex(manifest);
  const readMe = readMeText(meta.exportedUtc, manifestSha256);
  const all: ZipEntry[] = [
    { name: "READ-ME.txt", data: utf8(readMe) },
    { name: "manifest.json", data: utf8(manifest) },
    ...files,
  ];
  const day = meta.exportedUtc.slice(0, 10);
  const sites = [...new Set(plan.parts.map((p) => p.reach.info.site))];
  return {
    zip: makeZip(all, new Date(meta.exportedUtc)),
    manifestSha256,
    name: `riveretch-${sites.length === 1 ? (sites[0] ?? "export") : "all-reaches"}-${day}.zip`,
  };
}

// SHA-256 of bytes, hex.
async function sha256Bytes(bytes: Uint8Array): Promise<string> {
  const copy = new Uint8Array(bytes);
  const digest = await crypto.subtle.digest("SHA-256", copy);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

// A record's file named by its ledger line.
function fileFromLedger(ledger: string, sha: string, folder: string): Promise<string | null> {
  for (const line of ledger.split("\n")) {
    if (line.includes(sha)) {
      const parsed = JSON.parse(line) as { recordSha256: string; file: string };
      if (parsed.recordSha256 === sha) {
        return Promise.resolve(`${folder}${parsed.file}`);
      }
    }
  }
  return Promise.resolve(null);
}

// The model sheets a part's records were made with.
function cardPaths(part: ExportPart): string[] {
  const cards = part.reach.info.cards;
  if (part.dataset === "dailyFlow") {
    return []; // the source's own values: no model
  }
  if (part.dataset === "turbidity") {
    return cards.turbidity === undefined ? [] : [cards.turbidity];
  }
  if (part.dataset === "along") {
    return part.reach.along == null ? [] : [part.reach.along.plan.card];
  }
  return cards.water_temperature === undefined ? [] : [cards.water_temperature];
}

/**
 * The READ-ME's two paragraphs and its citation line.
 *
 * @param exportedUtc - When the export was made.
 * @param manifestSha256 - The manifest's fingerprint.
 * @returns The text.
 */
export function readMeText(exportedUtc: string, manifestSha256: string): string {
  return [
    "This is a RiverEtch export: river readings taken from free satellite images, with the proof that each one has not changed since it was fixed. Every row of the CSV files carries its fingerprint (recordSha256). The records, their record lists, the posts on Ethereum and Bitcoin, the quantum-safe signatures and the model sheets that cover those rows are included. A daily-flow.csv, where there is one, holds the station's (or flood model's) own daily values as its source published them, one row per day: they are not satellite readings, and their fingerprint proves what the source published, not that it is right.",
    "",
    `To check it, open ${SITE_URL}, open any river, and choose "Check a file" in the Proof panel, then pick this zip. Your browser recomputes every fingerprint, reads Ethereum and checks the Bitcoin timestamps again: it does not trust the proofs inside this zip, and nothing is uploaded. A fingerprint proves a reading was not changed after its date; it does not prove the reading is right.`,
    "",
    `Cite as: RiverEtch export of ${exportedUtc.slice(0, 10)}, manifest SHA-256 ${manifestSha256}, ${SITE_URL}`,
    "",
  ].join("\n");
}
