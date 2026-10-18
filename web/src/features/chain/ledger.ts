// What a ledger's anchor on Sepolia proves about one of its records (pure; no wallet, no network).
// A ledger line names the SHA-256 of the line before it, so the SHA-256 of a line (a head) commits
// to every line above it. An anchor stores a head and the ledger's line count at a block's time:
// a record listed on line p is covered by the first anchor with more than p lines, and that anchor
// holds only if its head equals the local ledger's hash of the same line.
import { sha256Hex } from "../reaches/canonical.ts";

/** The ledgers a reach keeps. */
export type LedgerKind = "observations" | "water-temperature";

/** One anchor read from the contract. */
export interface ChainAnchor {
  /** The SHA-256 of the ledger's last line at anchoring time (0x-prefixed). */
  readonly head: string;
  readonly lines: number;
  /** Seconds since the epoch. */
  readonly timestamp: number;
  readonly blockNumber: number;
}

/** What the anchors say about one record. */
export type AnchorStatus =
  | { readonly state: "anchored"; readonly anchor: ChainAnchor; readonly index: number }
  | { readonly state: "pending"; readonly anchors: number }
  | { readonly state: "mismatch"; readonly anchor: ChainAnchor; readonly index: number };

/**
 * The label a ledger is anchored under; the contract's subject is its keccak256. It keeps the
 * project's first name (TerraChain): the anchors already on Sepolia were made under it, so a new
 * prefix would leave every record unanchored.
 *
 * @param reachId - The reach.
 * @param ledger - Which ledger.
 * @returns E.g. `terrachain:platte-louisville:observations`.
 */
export function subjectLabel(reachId: string, ledger: LedgerKind): string {
  return `terrachain:${reachId}:${ledger}`;
}

/**
 * A ledger's lines, each line's SHA-256 and its head (the last line's hash).
 *
 * @param text - The ledger file (`ledger.jsonl`).
 * @returns The hashes (0x-prefixed), the line count and the head (null for an empty ledger).
 */
export async function ledgerHead(
  text: string,
): Promise<{ hashes: string[]; lines: number; head: string | null }> {
  const lines = text.split("\n").filter((line) => line.trim() !== "");
  const hashes = await Promise.all(lines.map(async (line) => `0x${await sha256Hex(line)}`));
  return { hashes, lines: lines.length, head: hashes.at(-1) ?? null };
}

/**
 * Whether a record's ledger line is covered by an anchor, and whether that anchor still holds.
 *
 * @param anchors - The ledger's anchors, oldest first.
 * @param position - The record's line (0-based) in the local ledger.
 * @param hashes - The local ledger's line hashes (0x-prefixed).
 * @returns `anchored` (the first covering anchor matches), `mismatch` (it does not: the ledger
 *   changed after it was anchored) or `pending` (no anchor covers the line yet).
 */
export function anchorStatus(
  anchors: readonly ChainAnchor[],
  position: number,
  hashes: readonly string[],
): AnchorStatus {
  const index = anchors.findIndex((a) => a.lines > position);
  const anchor = anchors[index];
  if (position < 0 || anchor === undefined) {
    return { state: "pending", anchors: anchors.length };
  }
  const local = hashes[anchor.lines - 1];
  const holds = local?.toLowerCase() === anchor.head.toLowerCase();
  return { state: holds ? "anchored" : "mismatch", anchor, index };
}
