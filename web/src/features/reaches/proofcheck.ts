// "Check a file": a RiverEtch export (.zip), a CSV or a record (JSON) someone was sent, checked in
// the browser against the site's own sealed records. Nothing inside the file is trusted: each row
// is found by its fingerprint in the site's record list, compared cell by cell with the site's
// sealed record (whose own fingerprint is recomputed), the record list's chain is recomputed, its
// posts are read from Ethereum, and its Bitcoin timestamps and signatures are checked as the
// single-reading check does. The proofs inside a zip are only compared with that, never used. A
// fingerprint proves a reading was not changed after its date, not that it is right.
import { anchorStatus, ledgerPath, subjectLabel, type ChainAnchor } from "../chain/ledger.ts";
import type { BlockHeader } from "../chain/ots.ts";
import {
  checkBitcoin,
  checkSignature,
  coveringProof,
  type BitcoinWitness,
} from "../chain/witness.ts";
import { canonical, NumberText, parseJson, sha256Hex, type JsonValue } from "./canonical.ts";
import { csvRows } from "./checkfile.ts";
import {
  DATASETS,
  inPeriod,
  recordCells,
  rowsOf,
  type DatasetId,
  type ProofIo,
  type ProofRow,
} from "./proof.ts";
import type { ReachData } from "./types.ts";
import { readZip } from "./zip.ts";

/** A row that is not as sealed, or not there. */
export interface RowIssue {
  readonly reach: string;
  readonly dataset: DatasetId;
  readonly sceneId: string;
  readonly date: string;
  /** Its row in the file (1: the first after the header; 0: none, a missing row). */
  readonly row: number;
  /** The record file inside a zip that differs from the sealed record (none: the row only). */
  readonly file?: string;
  /** Each value that differs: its column, the sealed value and the file's (and where, in a zip). */
  readonly changes: readonly Change[];
}

/** One value that differs from the sealed record. */
export interface Change {
  readonly column: string;
  readonly sealed: string;
  readonly given: string;
  /** The record file inside a zip it was read from (none: the row). */
  readonly file?: string;
}

/** What a check found over a whole file. */
export interface FileReport {
  readonly kind: "zip" | "csv" | "record";
  /** The rows the file holds. */
  readonly rows: number;
  /** Rows exactly as sealed. */
  readonly unchanged: number;
  /** Unchanged and posted on Ethereum (null: the chain could not be read). */
  readonly ethereum: number | null;
  /** Unchanged and in a Bitcoin block (checked against two block explorers). */
  readonly bitcoin: number;
  /** Unchanged, not on Ethereum yet (null: the chain could not be read). */
  readonly waiting: number | null;
  /** Unchanged and under a valid quantum-safe signature. */
  readonly signed: number;
  readonly changed: readonly RowIssue[];
  /** Rows of a reach or a pass the site does not have. */
  readonly notFound: readonly RowIssue[];
  /** Sealed rows of the export's period that the file no longer holds (zip only). */
  readonly missing: readonly RowIssue[];
  /** Plain notes on the file itself (e.g. its own list of posts does not match Ethereum). */
  readonly notes: readonly string[];
  /** A zip's manifest fingerprint, to compare with its citation line (null: no manifest). */
  readonly manifestSha256: string | null;
}

/** What a check reads beside the export's own reading: the reaches, the explorers, the key. */
export interface CheckIo extends ProofIo {
  /** A reach's published data (null: no such reach). */
  readonly reach: (site: string) => Promise<ReachData | null>;
  /** A Bitcoin block header from the public explorers (null: they failed or disagreed). */
  readonly header: (height: number) => Promise<BlockHeader | null>;
  /** The ML-DSA-65 key the site publishes (never the file's), hex. */
  readonly publicKey: string;
}

/** Notes a report may carry. */
export const NOTES = {
  anchorsIgnored: "The list of posts inside this file does not match Ethereum, so it was not used.",
  manifest: (path: string) =>
    `${path} is not the file the export's own list describes: it was changed after the export.`,
  brokenList: (what: string) =>
    `The published record list of ${what} is broken: its posts cannot be checked.`,
  unreadableRecord: (path: string) => `${path} could not be read as a RiverEtch record.`,
} as const;

/** One row of the file to check: where it says it comes from, and its values. */
interface Given {
  readonly reach: string;
  readonly dataset: DatasetId;
  readonly sceneId: string;
  readonly recordSha256: string;
  readonly row: number;
  readonly cells: Record<string, string>;
  /** A record file checked whole: its content's own fingerprint (null: a CSV row). */
  readonly selfSha256: string | null;
  /** A record file inside a zip: its path there. */
  readonly file?: string;
}

const keyOf = (g: Pick<Given, "reach" | "dataset" | "sceneId">) =>
  `${g.reach}|${g.dataset}|${g.sceneId}`;

// A record file as a row to check: its own fingerprint is recomputed (null: not a record).
async function recordGiven(textOfFile: string, file?: string): Promise<Given | null> {
  let record: JsonValue;
  try {
    record = parseJson(textOfFile.replace(/^\uFEFF/, "").trim());
  } catch {
    return null;
  }
  const dataset = datasetOfRecord(record);
  const sceneId = stringOf(record, "sceneId");
  const stated = stringOf(record, "recordSha256");
  if (dataset === null || sceneId === "" || stated === "") {
    return null;
  }
  const content = { ...(record as Record<string, JsonValue>) };
  delete content.recordSha256;
  return {
    reach: sceneId.split(":")[0] ?? "",
    dataset,
    sceneId,
    recordSha256: stated,
    row: file === undefined ? 1 : 0,
    cells: recordCells(dataset, record),
    selfSha256: await sha256Hex(canonical(content)),
    ...(file === undefined ? {} : { file }),
  };
}

// A zip made again from the export's folder (Windows "Send to > Compressed folder", macOS
// "Compress") holds every file under that folder: the export is read from where its manifest is
// (or from the one folder everything is in), and files outside it (e.g. __MACOSX/) are left out.
function exportRoot(files: Map<string, Uint8Array>): Map<string, Uint8Array> {
  const named = new Map([...files].map(([n, d]) => [n.replace(/\\/g, "/"), d]));
  const names = [...named.keys()].filter((n) => !n.startsWith("__MACOSX/"));
  const manifest = names
    .filter((n) => n === "manifest.json" || n.endsWith("/manifest.json"))
    .sort((a, b) => a.split("/").length - b.split("/").length)[0];
  const tops = new Set(names.map((n) => (n.includes("/") ? (n.split("/")[0] ?? "") : "")));
  const [only] = [...tops];
  const root =
    manifest !== undefined
      ? manifest.slice(0, -"manifest.json".length)
      : tops.size === 1 && only !== undefined && only !== ""
        ? `${only}/`
        : "";
  return new Map(
    [...named]
      .filter(([n]) => n.startsWith(root) && !n.startsWith("__MACOSX/"))
      .map(([n, d]) => [n.slice(root.length), d]),
  );
}

// A cell is the sealed value when its text is, or when both are the same number (a spreadsheet
// may write 0.50 for 0.5).
function sameCell(sealed: string, given: string): boolean {
  const a = sealed.trim();
  const b = given.trim();
  return a === b || (a !== "" && b !== "" && Number.isFinite(Number(a)) && Number(a) === Number(b));
}

const isDataset = (value: string): value is DatasetId => value in DATASETS;

// What a record file is, by its shape.
function datasetOfRecord(record: JsonValue): DatasetId | null {
  if (record === null || typeof record !== "object" || Array.isArray(record)) {
    return null;
  }
  if (record instanceof NumberText) {
    return null;
  }
  const schema = typeof record.schema === "string" ? record.schema : "";
  if (schema.startsWith("riveretch.along-temperature")) {
    return "alongTemperature";
  }
  if (schema.startsWith("riveretch.along-river")) {
    return "along";
  }
  if (record.kind === "water_temperature") {
    return "temperature";
  }
  return Array.isArray(record.estimates) ? "turbidity" : null;
}

// A CSV's rows as rows to check (a dataset column, else turbidity; a reach column, else the scene
// id's reach).
function csvGiven(textOfCsv: string, fallback: DatasetId | null): Given[] {
  return csvRows(textOfCsv).map((cells, k) => {
    const sceneId = (cells.sceneId ?? "").trim();
    const named = (cells.dataset ?? "").trim();
    const { dataset: _d, reach: _r, sceneId: _s, recordSha256: _h, ...values } = cells;
    return {
      reach: (cells.reach ?? "").trim() || (sceneId.split(":")[0] ?? ""),
      dataset: isDataset(named) ? named : (fallback ?? "turbidity"),
      sceneId,
      recordSha256: (cells.recordSha256 ?? "").trim(),
      row: k + 1,
      cells: values,
      selfSha256: null,
    };
  });
}

// One line of a record list.
interface Line {
  readonly recordSha256: string;
  readonly file: string;
  readonly createdUtc: string;
  readonly previousLineSha256: string | null;
}

// What the check keeps per reach and dataset, read once.
interface Listing {
  readonly reach: ReachData;
  readonly rows: readonly ProofRow[];
  readonly label: string;
  readonly lines: readonly Line[];
  readonly hashes: readonly string[];
  /** Every line names the hash of the line before it. */
  readonly intact: boolean;
}

const encoder = new TextEncoder();

/**
 * Checks a file someone was sent: an export (.zip), a CSV or a record (JSON).
 *
 * @param bytes - The file.
 * @param io - The site's files, the chain, the explorers and the key.
 * @returns The report over the whole file (null: not a RiverEtch file).
 */
export async function checkProofFile(bytes: Uint8Array, io: CheckIo): Promise<FileReport | null> {
  const notes: string[] = [];
  let given: Given[] = [];
  let kind: FileReport["kind"];
  let manifest: JsonValue | null = null;
  let zipAnchors: JsonValue | null = null;
  let manifestSha256: string | null = null;
  // The sealed records inside a zip, checked with their readings' rows.
  const records: Given[] = [];
  if (bytes[0] === 0x50 && bytes[1] === 0x4b) {
    kind = "zip";
    let files: Map<string, Uint8Array>;
    try {
      files = exportRoot(await readZip(bytes));
    } catch {
      return null;
    }
    const decode = (b: Uint8Array | undefined) =>
      b === undefined ? null : new TextDecoder().decode(b);
    const manifestText = decode(files.get("manifest.json"));
    manifest = manifestText === null ? null : parseJson(manifestText);
    manifestSha256 = manifestText === null ? null : await sha256Hex(manifestText);
    const anchorsText = decode(files.get("proof/anchors.json"));
    zipAnchors = anchorsText === null ? null : parseJson(anchorsText);
    // The export's own list of its files: a file that no longer matches was changed after it.
    for (const entry of listOf(manifest, "files")) {
      const path = stringOf(entry, "path");
      const sha = stringOf(entry, "sha256");
      const data = files.get(path);
      if (data !== undefined && (await sha256Bytes(data)) !== sha) {
        notes.push(NOTES.manifest(path));
      }
    }
    for (const [name, data] of files) {
      if (name.startsWith("data/") && name.endsWith(".csv")) {
        given.push(...csvGiven(new TextDecoder().decode(data), null));
      } else if (name.startsWith("records/") && name.endsWith(".json")) {
        const record = await recordGiven(new TextDecoder().decode(data), name);
        if (record === null) {
          notes.push(NOTES.unreadableRecord(name));
        } else {
          records.push(record);
        }
      }
    }
    if (given.length === 0 && records.length === 0) {
      return null;
    }
  } else {
    const textOfFile = new TextDecoder().decode(bytes).replace(/^\uFEFF/, "");
    if (textOfFile.trimStart().startsWith("{")) {
      kind = "record";
      const record = await recordGiven(textOfFile);
      if (record === null) {
        return null;
      }
      given = [record];
    } else {
      kind = "csv";
      given = csvGiven(textOfFile, null);
      if (given.length === 0 || given.some((g) => g.sceneId === "" || g.recordSha256 === "")) {
        return null;
      }
    }
  }

  const listings = new Map<string, Listing | null>();
  const listing = async (site: string, dataset: DatasetId): Promise<Listing | null> => {
    const key = `${site}|${dataset}`;
    if (!listings.has(key)) {
      const reach = await io.reach(site);
      if (reach === null) {
        listings.set(key, null);
      } else {
        const ledger = (await io.text(reach, ledgerPath(DATASETS[dataset].kind))) ?? "";
        const raw = ledger.split("\n").filter((l) => l.trim() !== "");
        const lines = raw.map((l) => JSON.parse(l) as Line);
        const hashes = await Promise.all(raw.map((l) => sha256Hex(l)));
        const intact = lines.every(
          (l, k) => l.previousLineSha256 === (k === 0 ? null : hashes[k - 1]),
        );
        if (!intact) {
          notes.push(NOTES.brokenList(`${site} (${dataset})`));
        }
        listings.set(key, {
          reach,
          rows: rowsOf(reach, dataset),
          label: subjectLabel(site, DATASETS[dataset].kind),
          lines,
          hashes,
          intact,
        });
      }
    }
    return listings.get(key) ?? null;
  };

  const anchors = new Map<string, readonly ChainAnchor[] | null>();
  const anchorsOf = async (label: string) => {
    if (!anchors.has(label)) {
      anchors.set(label, await io.anchors(label));
    }
    return anchors.get(label) ?? null;
  };
  const proofs = await io.proofs();
  const signatures = await io.signatures();
  const bitcoin = new Map<string, BitcoinWitness>();
  let offline = false;
  const changed: RowIssue[] = [];
  const notFound: RowIssue[] = [];
  const counts = { unchanged: 0, ethereum: 0, bitcoin: 0, signed: 0 };

  // One row (or record file) against the site: what differs from its sealed record (null: the site
  // has no such reach or pass).
  const compare = async (g: Given) => {
    const list = await listing(g.reach, g.dataset);
    const pass = list?.rows.find((r) => r.sceneId === g.sceneId);
    if (list === null || pass === undefined) {
      return null;
    }
    const position = list.lines.findIndex((l) => l.recordSha256 === g.recordSha256);
    // Its sealed record: the one its fingerprint names, else the pass's newest.
    const line = list.lines[position];
    const file = line === undefined ? pass.file : `${DATASETS[g.dataset].folder}${line.file}`;
    const sealedText = file === null ? null : await io.text(list.reach, file);
    const sealed = sealedText === null ? null : parseJson(sealedText);
    const where = g.file === undefined ? {} : { file: g.file };
    const changes: Change[] = [];
    if (position < 0) {
      changes.push({
        column: "recordSha256",
        sealed: pass.recordSha256,
        given: g.recordSha256,
        ...where,
      });
    }
    if (g.selfSha256 !== null && g.selfSha256 !== g.recordSha256) {
      changes.push({ column: "(content)", sealed: g.recordSha256, given: g.selfSha256, ...where });
    }
    if (sealed !== null) {
      // The published record itself must still match its fingerprint.
      const content = { ...(sealed as Record<string, JsonValue>) };
      delete content.recordSha256;
      if ((await sha256Hex(canonical(content))) !== stringOf(sealed, "recordSha256")) {
        changes.push({ column: "(published record)", sealed: "", given: "" });
      }
      const expected = recordCells(g.dataset, sealed);
      for (const [column, value] of Object.entries(expected)) {
        if (column in g.cells && !sameCell(value, g.cells[column] ?? "")) {
          changes.push({ column, sealed: value, given: g.cells[column] ?? "", ...where });
        }
      }
    }
    return { list, position, sealed, changes };
  };

  // A record inside a zip is checked as a lone record file is, and what differs is reported on its
  // reading's row. The tables are the export's readings: a record whose row was deleted does not
  // stand in for it (the row is missing), and is reported on its own only when it differs. A zip
  // with no table left has its records as its rows.
  const inRecords = new Map<string, { readonly file: string; readonly changes: Change[] }>();
  if (given.length === 0) {
    given = records;
  } else {
    const rowKeys = new Set(given.map(keyOf));
    for (const r of records) {
      const result = await compare(r);
      if (result === null || result.changes.length === 0 || r.file === undefined) {
        continue;
      }
      if (rowKeys.has(keyOf(r))) {
        inRecords.set(keyOf(r), { file: r.file, changes: result.changes });
      } else {
        changed.push({
          reach: r.reach,
          dataset: r.dataset,
          sceneId: r.sceneId,
          date: r.cells.date ?? "",
          row: 0,
          file: r.file,
          changes: result.changes,
        });
      }
    }
  }

  for (const g of given) {
    const record = inRecords.get(keyOf(g));
    const issue = (changes: RowIssue["changes"]): RowIssue => ({
      reach: g.reach,
      dataset: g.dataset,
      sceneId: g.sceneId,
      date: g.cells.date ?? "",
      row: g.row,
      ...(record === undefined
        ? g.file === undefined
          ? {}
          : { file: g.file }
        : { file: record.file }),
      changes,
    });
    const result = await compare(g);
    if (result === null) {
      notFound.push(issue([]));
      continue;
    }
    const { list, position, sealed } = result;
    const changes = [...result.changes, ...(record?.changes ?? [])];
    if (changes.length > 0 || sealed === null) {
      changed.push(issue(changes));
      continue;
    }
    counts.unchanged += 1;
    const lineHashes = list.hashes;
    const chain = list.intact ? await anchorsOf(list.label) : [];
    if (chain === null) {
      offline = true;
    } else if (
      anchorStatus(
        chain,
        position,
        lineHashes.map((h) => `0x${h}`),
      ).state === "anchored"
    ) {
      counts.ethereum += 1;
    }
    const entry = coveringProof(proofs, list.label, position);
    if (entry !== null && list.intact) {
      if (!bitcoin.has(entry.file)) {
        const proofBytes = await io.proof(entry.file);
        bitcoin.set(
          entry.file,
          proofBytes === null
            ? { state: "unavailable" }
            : await checkBitcoin(entry, proofBytes, lineHashes, io.header).catch(
                (): BitcoinWitness => ({ state: "mismatch" }),
              ),
        );
      }
      if (bitcoin.get(entry.file)?.state === "confirmed") {
        counts.bitcoin += 1;
      }
    }
    if (
      list.intact &&
      checkSignature(signatures, io.publicKey, list.label, position, lineHashes).state ===
        "verified"
    ) {
      counts.signed += 1;
    }
  }

  // An export's period, by reach and dataset: rows sealed by the time of the export that the file
  // no longer holds.
  const missing: RowIssue[] = [];
  const period = field(manifest, "period");
  const from = stringOrNull(period, "from");
  const to = stringOrNull(period, "to");
  const exported = stringOf(manifest, "exportedUtc");
  for (const part of listOf(manifest, "parts")) {
    const site = stringOf(part, "reach");
    const dataset = stringOf(part, "dataset");
    if (!isDataset(dataset)) {
      continue;
    }
    const list = await listing(site, dataset);
    const held = new Set(
      given.filter((g) => g.reach === site && g.dataset === dataset).map((g) => g.sceneId),
    );
    const sealedBy = new Map(list?.lines.map((l) => [l.recordSha256, l.createdUtc]) ?? []);
    for (const r of list?.rows ?? []) {
      const created = sealedBy.get(r.recordSha256);
      if (
        inPeriod(r.date, from, to) &&
        created !== undefined &&
        created <= exported &&
        !held.has(r.sceneId)
      ) {
        missing.push({
          reach: site,
          dataset,
          sceneId: r.sceneId,
          date: r.date,
          row: 0,
          changes: [],
        });
      }
    }
  }

  // The posts listed inside a zip are compared with Ethereum, never used.
  const claimed = field(zipAnchors, "anchors");
  if (
    claimed !== undefined &&
    claimed !== null &&
    typeof claimed === "object" &&
    !Array.isArray(claimed)
  ) {
    for (const [label, list] of Object.entries(claimed as Record<string, JsonValue>)) {
      const chain = await anchorsOf(label);
      if (chain === null) {
        offline = true;
        continue;
      }
      const onChain = new Set(chain.map((a) => `${a.head.toLowerCase()}|${String(a.lines)}`));
      const all = Array.isArray(list) ? list : [];
      if (
        all.some(
          (a) => !onChain.has(`${stringOf(a, "head").toLowerCase()}|${stringOf(a, "lines")}`),
        )
      ) {
        notes.push(NOTES.anchorsIgnored);
        break;
      }
    }
  }

  return {
    kind,
    rows: given.length,
    unchanged: counts.unchanged,
    ethereum: offline ? null : counts.ethereum,
    bitcoin: counts.bitcoin,
    waiting: offline ? null : counts.unchanged - counts.ethereum,
    signed: counts.signed,
    changed,
    notFound,
    missing,
    notes: [...new Set(notes)],
    manifestSha256,
  };
}

function field(value: JsonValue | null | undefined, key: string): JsonValue | undefined {
  return value !== null &&
    value !== undefined &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    !(value instanceof NumberText)
    ? value[key]
    : undefined;
}

function stringOf(value: JsonValue | null | undefined, key: string): string {
  const v = field(value, key);
  return typeof v === "string" ? v : v instanceof NumberText ? v.text : "";
}

function stringOrNull(value: JsonValue | null | undefined, key: string): string | null {
  const v = field(value, key);
  return typeof v === "string" ? v : null;
}

function listOf(value: JsonValue | null | undefined, key: string): JsonValue[] {
  const v = field(value, key);
  return Array.isArray(v) ? v : [];
}

async function sha256Bytes(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new Uint8Array(bytes));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/**
 * A text file's bytes (for a check of a CSV or a record the reader pasted).
 *
 * @param value - The text.
 * @returns Its UTF-8 bytes.
 */
export function bytesOf(value: string): Uint8Array {
  return encoder.encode(value);
}
