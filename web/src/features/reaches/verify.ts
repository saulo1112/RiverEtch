// Checks a record in the browser, as `climate-pipeline reach verify` does: its seal (SHA-256 of its
// canonical JSON), its place in the hash-chained ledger and its model card's hash. "Alter a value"
// changes one number in memory first, to show that a tampered record no longer matches its seal.
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
  /** The value that was altered (null when nothing was). */
  readonly altered: { readonly path: string; readonly from: string; readonly to: string } | null;
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

// The number to alter: the first estimate's value, else the downstream NDTI.
function alterOne(record: JsonObject): Verification["altered"] {
  const estimates = record.estimates;
  const first = Array.isArray(estimates) ? estimates[0] : undefined;
  const candidates: [JsonObject | undefined, string, string][] = [
    [isObject(first) ? first : undefined, "value", "estimates[0].value"],
  ];
  const indices = record.indices;
  const ndti = isObject(indices) ? indices.ndti : undefined;
  candidates.push([isObject(ndti) ? ndti : undefined, "downstream", "indices.ndti.downstream"]);
  for (const [holder, key, path] of candidates) {
    const value = holder?.[key];
    if (holder !== undefined && value instanceof NumberText) {
      const next = (Number(value.text) + 0.01).toFixed(Math.max(2, decimals(value.text)));
      holder[key] = new NumberText(next);
      return { path, from: value.text, to: next };
    }
  }
  return null;
}

function decimals(text: string): number {
  const dot = text.indexOf(".");
  return dot < 0 ? 0 : text.length - dot - 1;
}

/**
 * Verifies a record against its ledger and its card.
 *
 * @param recordText - The record file.
 * @param ledgerText - The reach's whole ledger (`ledger.jsonl`).
 * @param cardText - The model card the record's first estimate names (null: not checked).
 * @param alter - Change one number of the record first.
 * @returns What matched.
 */
export async function verifyRecord(
  recordText: string,
  ledgerText: string,
  cardText: string | null,
  alter = false,
): Promise<Verification> {
  const record = parseJson(recordText);
  if (!isObject(record)) {
    throw new Error("the record is not a JSON object");
  }
  const stated = typeof record.recordSha256 === "string" ? record.recordSha256 : "";
  const content: JsonObject = { ...record };
  delete content.recordSha256;
  const altered = alter ? alterOne(content) : null;
  const computed = await sha256Hex(canonical(content));

  const lines = ledgerText.split("\n").filter((line) => line.trim() !== "");
  let chainIntact = true;
  let previous: string | null = null;
  let inLedger = false;
  for (const line of lines) {
    const entry = JSON.parse(line) as { previousLineSha256: string | null; recordSha256: string };
    chainIntact &&= entry.previousLineSha256 === previous;
    inLedger ||= entry.recordSha256 === stated;
    previous = await sha256Hex(line);
  }

  let cardMatches: boolean | null = null;
  const estimates = record.estimates;
  const first = Array.isArray(estimates) ? estimates[0] : undefined;
  const named = isObject(first) ? first.modelCardSha256 : undefined;
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
  };
}
