// "Check a file": a RiverEtch record (JSON) or series (CSV) that reached someone outside the site
// is compared, in their browser, with the reach's sealed records and its ledger. A record is
// identical when its content matches its fingerprint, the fingerprint is a line of the ledger
// and nothing differs from the sealed record of its pass; otherwise the check says which of
// those failed and which numbers changed. A file edited and given a recomputed fingerprint
// matches itself but not the ledger. Nothing is uploaded.
import { canonical, NumberText, parseJson, sha256Hex, type JsonValue } from "./canonical.ts";
import { sceneKey } from "./scene.ts";
import type { SeriesRow } from "./types.ts";

/** One value that differs from the sealed record. */
export interface Change {
  /** Where, as the record names it (e.g. `estimates[0].value`) or the CSV's column. */
  readonly path: string;
  readonly sealed: string;
  readonly given: string;
}

/** A record file's check. */
export interface RecordCheck {
  readonly kind: "record";
  readonly sceneId: string;
  readonly date: string;
  /** Its content matches the fingerprint it states. */
  readonly selfSealed: boolean;
  /** That fingerprint is a line of the reach's ledger. */
  readonly inLedger: boolean;
  /** What differs from the sealed record of its pass (its fingerprint left out). */
  readonly changes: readonly Change[];
  /** All three: the file is the sealed record. */
  readonly identical: boolean;
}

/** One CSV row's check. */
export interface RowCheck {
  readonly sceneId: string;
  readonly date: string;
  /**
   * same: as sealed; changed: a value differs; unsealed: its fingerprint is in no ledger line;
   * unknown: it names no pass of this reach.
   */
  readonly status: "same" | "changed" | "unsealed" | "unknown";
  readonly changes: readonly Change[];
}

/** A series file's check. */
export interface SeriesCheck {
  readonly kind: "series";
  readonly rows: readonly RowCheck[];
}

/** What a check found. */
export type FileCheck =
  | RecordCheck
  | SeriesCheck
  | { readonly kind: "other-reach"; readonly site: string }
  | { readonly kind: "unreadable" };

/** What a check needs: the reach, its passes and ledger, and a way to read its files. */
export interface CheckContext {
  /** The reach's site id, e.g. `firat-birecik`. */
  readonly site: string;
  /** Its passes, the newest record of each (Sentinel-2 passes, or Landsat's for temperature). */
  readonly series: readonly Pass[];
  /** Its whole ledger (`ledger.jsonl`). */
  readonly ledger: string;
  /** Reads one of its files, e.g. `records/<date>_<key>.json`. */
  readonly load: (path: string) => Promise<string>;
}

/** What a check reads of a pass. */
type Pass = Pick<SeriesRow, "date" | "sceneId" | "file" | "recordSha256">;

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

// A leaf as a reader sees it.
function leaf(value: JsonValue | undefined): string {
  if (value === undefined) {
    return "(none)";
  }
  if (value instanceof NumberText) {
    return value.text;
  }
  if (typeof value === "string") {
    return value;
  }
  if (value === null || typeof value === "boolean") {
    return String(value);
  }
  const text = canonical(value);
  return text.length > 48 ? `${text.slice(0, 47)}…` : text;
}

// Two leaves are the same when their text is, or when both are the same number.
function sameLeaf(a: JsonValue | undefined, b: JsonValue | undefined): boolean {
  if (a instanceof NumberText && b instanceof NumberText) {
    return Number(a.text) === Number(b.text);
  }
  return leaf(a) === leaf(b);
}

/**
 * Every value of `given` that differs from `sealed`, leaf by leaf (numbers by value), its
 * fingerprint left out.
 *
 * @param sealed - The sealed record.
 * @param given - The record checked.
 * @param limit - At most this many.
 * @returns The differences, in key order.
 */
export function differences(sealed: JsonValue, given: JsonValue, limit = 12): Change[] {
  const out: Change[] = [];
  const walk = (a: JsonValue | undefined, b: JsonValue | undefined, at: string) => {
    if (out.length >= limit || at === "recordSha256") {
      return;
    }
    if (isObject(a) && isObject(b)) {
      for (const key of [...new Set([...Object.keys(a), ...Object.keys(b)])].sort()) {
        walk(a[key], b[key], at === "" ? key : `${at}.${key}`);
      }
      return;
    }
    if (Array.isArray(a) && Array.isArray(b)) {
      for (let k = 0; k < Math.max(a.length, b.length); k += 1) {
        walk(a[k], b[k], `${at}[${String(k)}]`);
      }
      return;
    }
    if (!sameLeaf(a, b)) {
      out.push({ path: at, sealed: leaf(a), given: leaf(b) });
    }
  };
  walk(sealed, given, "");
  return out;
}

// A CSV line's cells; a quoted cell may hold commas and doubled quotes.
function cells(line: string): string[] {
  const out: string[] = [];
  let cell = "";
  let quoted = false;
  for (let k = 0; k < line.length; k += 1) {
    const ch = line.charAt(k);
    if (ch === '"' && quoted && line.charAt(k + 1) === '"') {
      cell += '"';
      k += 1;
    } else if (ch === '"') {
      quoted = !quoted;
    } else if (ch === "," && !quoted) {
      out.push(cell);
      cell = "";
    } else {
      cell += ch;
    }
  }
  out.push(cell);
  return out;
}

/**
 * A CSV file's rows, by its header's column names.
 *
 * @param text - The file.
 * @returns One object per row.
 */
export function csvRows(text: string): Record<string, string>[] {
  const [head, ...lines] = text
    .replace(/^\uFEFF/, "")
    .trim()
    .split(/\r?\n/);
  if (head === undefined) {
    return [];
  }
  const columns = cells(head).map((c) => c.trim());
  return lines
    .filter((line) => line.trim() !== "")
    .map((line) => {
      const values = cells(line);
      return Object.fromEntries(columns.map((c, k) => [c, values[k] ?? ""]));
    });
}

// The sealed values a series row's columns hold (the export's columns; a column the file lacks is
// not compared).
function sealedCells(record: JsonObject): Record<string, string> {
  const estimates = Array.isArray(record.estimates) ? record.estimates : [];
  const e = estimates.find((x) => isObject(x) && x.target === "turbidity");
  const est = isObject(e) ? e : {};
  const interval = isObject(est.interval) ? est.interval : {};
  const indices = isObject(record.indices) ? record.indices : {};
  const ndti = isObject(indices.ndti) ? indices.ndti : {};
  const text = (v: JsonValue | undefined) =>
    v === undefined || v === null ? "" : v instanceof NumberText ? v.text : leaf(v);
  return {
    date: text(record.date),
    level: text(est.level),
    turbidity_fnu: text(est.value),
    interval90_low: text(interval.low),
    interval90_high: text(interval.high),
    abstain_reason: text(est.abstainReason),
    turbidity_class: text(est.fnuClass),
    ndti_upstream: text(ndti.upstream),
    ndti_downstream: text(ndti.downstream),
  };
}

// A cell is the sealed value when its text is, or when both are the same number (a spreadsheet
// may write 0.50 for 0.5).
function sameCell(sealed: string, given: string): boolean {
  const a = sealed.trim();
  const b = given.trim();
  if (a === b) {
    return true;
  }
  return a !== "" && b !== "" && Number.isFinite(Number(a)) && Number(a) === Number(b);
}

// The ledger's record fingerprints.
function ledgerHashes(ledger: string): Set<string> {
  return new Set(
    ledger
      .split("\n")
      .filter((line) => line.trim() !== "")
      .map((line) => (JSON.parse(line) as { recordSha256: string }).recordSha256),
  );
}

// The sealed record of a pass with a given fingerprint: its newest record, or the earlier one it
// replaced (`<date>_<key>.json`), or one named by its fingerprint (`<date>_<key>.<hash12>.json`).
async function sealedRecord(
  ctx: CheckContext,
  row: Pass,
  hash: string | null,
): Promise<JsonObject | null> {
  const key = sceneKey(row);
  const candidates =
    hash === null || hash === row.recordSha256
      ? [row.file]
      : [`records/${row.date}_${key}.json`, `records/${row.date}_${key}.${hash.slice(0, 12)}.json`];
  for (const path of candidates) {
    try {
      const record = parseJson(await ctx.load(path));
      if (isObject(record) && (hash === null || record.recordSha256 === hash)) {
        return record;
      }
    } catch {
      // Not there: try the next name.
    }
  }
  return null;
}

async function checkRecord(record: JsonObject, ctx: CheckContext): Promise<FileCheck> {
  const sceneId = typeof record.sceneId === "string" ? record.sceneId : "";
  const site = sceneId.split(":")[0] ?? "";
  if (site !== ctx.site) {
    return { kind: "other-reach", site };
  }
  const stated = typeof record.recordSha256 === "string" ? record.recordSha256 : "";
  const content: JsonObject = { ...record };
  delete content.recordSha256;
  const selfSealed = (await sha256Hex(canonical(content))) === stated;
  const inLedger = ledgerHashes(ctx.ledger).has(stated);
  const row = ctx.series.find((r) => r.sceneId === sceneId);
  // Compared with the sealed record of that fingerprint, or, if the ledger has none, with the
  // pass's newest sealed record.
  const sealed =
    row === undefined
      ? null
      : ((inLedger ? await sealedRecord(ctx, row, stated) : null) ??
        (await sealedRecord(ctx, row, null)));
  const changes = sealed === null ? [] : differences(sealed, record);
  return {
    kind: "record",
    sceneId,
    date: typeof record.date === "string" ? record.date : (row?.date ?? ""),
    selfSealed,
    inLedger,
    changes,
    identical: selfSealed && inLedger && sealed !== null && changes.length === 0,
  };
}

async function checkSeries(
  rows: readonly Record<string, string>[],
  ctx: CheckContext,
): Promise<SeriesCheck> {
  const hashes = ledgerHashes(ctx.ledger);
  const out: RowCheck[] = [];
  for (const cellsOf of rows) {
    const sceneId = (cellsOf.sceneId ?? "").trim();
    const hash = (cellsOf.recordSha256 ?? "").trim();
    const row = ctx.series.find((r) => r.sceneId === sceneId);
    if (row === undefined) {
      out.push({ sceneId, date: cellsOf.date ?? "", status: "unknown", changes: [] });
      continue;
    }
    const known = hashes.has(hash);
    const sealed =
      (known ? await sealedRecord(ctx, row, hash) : null) ?? (await sealedRecord(ctx, row, null));
    const expected = sealed === null ? {} : sealedCells(sealed);
    const changes = Object.entries(expected)
      .filter(([column]) => column in cellsOf)
      .filter(([column, value]) => !sameCell(value, cellsOf[column] ?? ""))
      .map(([column, value]) => ({ path: column, sealed: value, given: cellsOf[column] ?? "" }));
    out.push({
      sceneId,
      date: row.date,
      status: !known ? "unsealed" : changes.length > 0 ? "changed" : "same",
      changes,
    });
  }
  return { kind: "series", rows: out };
}

/**
 * Checks a file someone was sent against a reach's sealed records and ledger.
 *
 * @param text - The file's text.
 * @param ctx - The reach's passes, ledger and files.
 * @returns What matched, and what changed.
 */
export async function checkFile(text: string, ctx: CheckContext): Promise<FileCheck> {
  const trimmed = text.replace(/^\uFEFF/, "").trimStart();
  if (trimmed.startsWith("{")) {
    let record: JsonValue;
    try {
      record = parseJson(trimmed);
    } catch {
      return { kind: "unreadable" };
    }
    return isObject(record) && typeof record.recordSha256 === "string"
      ? checkRecord(record, ctx)
      : { kind: "unreadable" };
  }
  const rows = csvRows(trimmed);
  if (rows.length === 0 || !rows.every((r) => "sceneId" in r && "recordSha256" in r)) {
    return { kind: "unreadable" };
  }
  return checkSeries(rows, ctx);
}
