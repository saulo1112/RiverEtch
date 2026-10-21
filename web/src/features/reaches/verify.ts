// Checks a record in the browser, as `climate-pipeline reach verify` does: its seal (SHA-256 of its
// canonical JSON), its place in the hash-chained ledger and its model card's hash. "Change one
// number first" sets the record's estimate to a value the reader picks, in memory, to show that a
// tampered record no longer matches its seal (and that the sealed value matches again).
// Observation records (v2) and water-temperature records (v1) are sealed the same way.
import { canonical, NumberText, parseJson, sha256Hex, type JsonValue } from "./canonical.ts";

/** What a check found. */
export interface Verification {
  /** The hash the record states. */
  readonly stated: string;
  /** The hash recomputed from its content. */
  readonly computed: string;
  /** The content still matches the seal. */
  readonly sealed: boolean;
  /** The ledger names this record's stated hash. */
  readonly inLedger: boolean;
  /** Every ledger line names the hash of the line before it. */
  readonly chainIntact: boolean;
  /** Ledger lines. */
  readonly ledgerLines: number;
  /** The model card's hash matches the one the record names (null without a card). */
  readonly cardMatches: boolean | null;
  /** The value that was changed (null when nothing was, or the new value equals the sealed one). */
  readonly altered: {
    readonly path: string;
    readonly kind: Editable["kind"];
    readonly from: string;
    readonly to: string;
  } | null;
  /** The canonical text that was hashed. */
  readonly canonical: string;
  /** Each ledger line: the record it names, its own hash and the hash it names before it. */
  readonly ledger: readonly LedgerLink[];
  /** The index of the line naming this record (-1: none). */
  readonly position: number;
}

/** One line of the ledger, as the chain view draws it. */
export interface LedgerLink {
  readonly sceneId: string;
  readonly date: string;
  readonly recordSha256: string;
  readonly lineSha256: string;
  readonly previousLineSha256: string | null;
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

// The record's first estimate: `estimates[0]` in an observation record, `estimate` in a
// water-temperature record.
function firstEstimate(record: JsonObject): { value: JsonObject; path: string } | undefined {
  const estimates = record.estimates;
  if (Array.isArray(estimates)) {
    const first = estimates[0];
    return isObject(first) ? { value: first, path: "estimates[0]" } : undefined;
  }
  const single = record.estimate;
  return isObject(single) ? { value: single, path: "estimate" } : undefined;
}

/** The record's field a reader may change before a check. */
export interface Editable {
  /** Where it sits in the record. */
  readonly path: string;
  /** A number (the estimate's value, or the downstream NDTI) or a turbidity class. */
  readonly kind: "number" | "class";
  /** Its sealed value, as the record writes it. */
  readonly sealed: string;
}

// The field to change: the estimate's value; else its class (a reach with no gauge); else the
// downstream NDTI (a pass with neither: the model abstained).
function editableIn(record: JsonObject): (Editable & { holder: JsonObject; key: string }) | null {
  const first = firstEstimate(record);
  if (first !== undefined) {
    const value = first.value.value;
    if (value instanceof NumberText) {
      const path = `${first.path}.value`;
      return { holder: first.value, key: "value", path, kind: "number", sealed: value.text };
    }
    const cls = first.value.fnuClass;
    if (typeof cls === "string") {
      const path = `${first.path}.fnuClass`;
      return { holder: first.value, key: "fnuClass", path, kind: "class", sealed: cls };
    }
  }
  const indices = record.indices;
  const ndti = isObject(indices) ? indices.ndti : undefined;
  const downstream = isObject(ndti) ? ndti.downstream : undefined;
  if (isObject(ndti) && downstream instanceof NumberText) {
    const path = "indices.ndti.downstream";
    return { holder: ndti, key: "downstream", path, kind: "number", sealed: downstream.text };
  }
  return null;
}

/**
 * The field of a record a reader may change before a check: the estimate it makes (its value, or
 * its class on a reach with no gauge), else the downstream NDTI.
 *
 * @param recordText - The record file.
 * @returns The field and its sealed value (null: the record has none of them).
 */
export function editable(recordText: string): Editable | null {
  const record = parseJson(recordText);
  const found = isObject(record) ? editableIn(record) : null;
  return found === null ? null : { path: found.path, kind: found.kind, sealed: found.sealed };
}

/**
 * Whether a reader's text is a number a record can hold.
 *
 * @param text - What the reader typed.
 * @returns It is a finite decimal number.
 */
export function isNumberText(text: string): boolean {
  return /^-?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(text.trim()) && Number.isFinite(Number(text));
}

// Sets the field to the reader's value. The sealed value, however it is typed (23.40 for 23.4),
// changes nothing: a verifier reads both as the same number.
function change(record: JsonObject, to: string): Verification["altered"] {
  const field = editableIn(record);
  if (field === null) {
    return null;
  }
  const { holder, key, path, kind, sealed } = field;
  if (kind === "class") {
    if (to === sealed) {
      return null;
    }
    holder[key] = to;
    return { path, kind, from: sealed, to };
  }
  if (!isNumberText(to)) {
    throw new Error(`not a number: ${to}`);
  }
  if (Number(to) === Number(sealed)) {
    return null;
  }
  const next = String(Number(to));
  holder[key] = new NumberText(next);
  return { path, kind, from: sealed, to: next };
}

/**
 * Verifies a record against its ledger and its card.
 *
 * @param recordText - The record file.
 * @param ledgerText - The reach's whole ledger (`ledger.jsonl`).
 * @param cardText - The model card the record's first estimate names (null: not checked).
 * @param alter - The value to give the record's editable field first (see `editable`), in memory:
 *   a number, or a class label.
 * @returns What matched.
 */
export async function verifyRecord(
  recordText: string,
  ledgerText: string,
  cardText: string | null,
  alter?: string,
): Promise<Verification> {
  const record = parseJson(recordText);
  if (!isObject(record)) {
    throw new Error("the record is not a JSON object");
  }
  const stated = typeof record.recordSha256 === "string" ? record.recordSha256 : "";
  const content: JsonObject = { ...record };
  delete content.recordSha256;
  const altered = alter === undefined ? null : change(content, alter);
  const text = canonical(content);
  const computed = await sha256Hex(text);

  const lines = ledgerText.split("\n").filter((line) => line.trim() !== "");
  let chainIntact = true;
  let previous: string | null = null;
  let position = -1;
  const links: LedgerLink[] = [];
  for (const line of lines) {
    const entry = JSON.parse(line) as {
      previousLineSha256: string | null;
      recordSha256: string;
      sceneId: string;
      date: string;
    };
    chainIntact &&= entry.previousLineSha256 === previous;
    if (entry.recordSha256 === stated) {
      position = links.length;
    }
    previous = await sha256Hex(line);
    links.push({
      sceneId: entry.sceneId,
      date: entry.date,
      recordSha256: entry.recordSha256,
      lineSha256: previous,
      previousLineSha256: entry.previousLineSha256,
    });
  }
  const inLedger = position >= 0;

  let cardMatches: boolean | null = null;
  const named = firstEstimate(record)?.value.modelCardSha256;
  if (cardText !== null && typeof named === "string") {
    cardMatches = (await sha256Hex(canonical(parseJson(cardText), true))) === named;
  }
  return {
    stated,
    computed,
    sealed: computed === stated,
    inLedger,
    chainIntact,
    ledgerLines: lines.length,
    cardMatches,
    altered,
    canonical: text,
    ledger: links,
    position,
  };
}
