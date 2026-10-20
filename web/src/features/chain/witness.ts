// The two witnesses beside the Sepolia anchor, read in the browser from the daily run's published
// files (the repository's data branch): an OpenTimestamps proof that a ledger head covering the
// record existed by a Bitcoin block (checked against public block explorers, which must agree),
// and the head's ML-DSA-65 signature (checked with the published key, docs/keys/ml-dsa-65.json).
// Neither needs a wallet or a key. The checks are pure; the fetchers are passed in.
import { bytesToHex } from "@noble/hashes/utils.js";

import { verifyHead, type HeadSignature } from "./mldsa.ts";
import { attests, parseProof, type BlockHeader } from "./ots.ts";

/** One proof the daily run lists in `status.json` (`proofs`). */
export interface ProofEntry {
  readonly label: string;
  readonly lines: number;
  /** Relative to the data branch's root, e.g. `docs/ledgers/ots/<label>.<lines>.ots`. */
  readonly file: string;
  /** Its earliest confirmed Bitcoin block (null: not confirmed yet). */
  readonly height: number | null;
}

/** What the Bitcoin witness shows for one record. */
export type BitcoinWitness =
  | {
      readonly state: "confirmed";
      readonly height: number;
      readonly time: number;
      readonly lines: number;
    }
  | { readonly state: "pending"; readonly lines: number }
  | { readonly state: "none" }
  | { readonly state: "mismatch" }
  | { readonly state: "unavailable" };

/** What the signature witness shows for one record. */
export type SignatureWitness =
  | { readonly state: "verified"; readonly lines: number; readonly signedAt: string }
  | { readonly state: "none" }
  | { readonly state: "invalid" }
  | { readonly state: "unavailable" };

/**
 * The proof to check for a ledger line: a head that covers it, the earliest confirmed one first.
 *
 * @param proofs - The listed proofs.
 * @param label - The ledger's label, e.g. `terrachain:platte-louisville:observations`.
 * @param position - The record's line (0-based).
 * @returns The proof, or null when no head covers the line yet.
 */
export function coveringProof(
  proofs: readonly ProofEntry[],
  label: string,
  position: number,
): ProofEntry | null {
  const covering = proofs.filter((p) => p.label === label && p.lines >= position + 1);
  const confirmed = covering
    .filter((p) => p.height !== null)
    .sort((a, b) => (a.height ?? 0) - (b.height ?? 0) || a.lines - b.lines);
  return confirmed[0] ?? [...covering].sort((a, b) => a.lines - b.lines)[0] ?? null;
}

/**
 * Checks a proof against the local ledger and a block header.
 *
 * @param entry - The proof's listing.
 * @param bytes - The `.ots` file.
 * @param lineHashes - The local ledger's line hashes (hex, no prefix).
 * @param header - Reads a block header at a height (null: the explorers failed or disagreed).
 * @returns Confirmed (with the block), pending, or a mismatch.
 */
export async function checkBitcoin(
  entry: ProofEntry,
  bytes: Uint8Array,
  lineHashes: readonly string[],
  header: (height: number) => Promise<BlockHeader | null>,
): Promise<BitcoinWitness> {
  const proof = parseProof(bytes);
  if (bytesToHex(proof.digest) !== lineHashes[entry.lines - 1]) {
    return { state: "mismatch" }; // not the head of this ledger's first `lines` lines
  }
  const heights = proof.attestations.flatMap((a) => (a.kind === "bitcoin" ? [a] : []));
  heights.sort((a, b) => a.height - b.height);
  for (const a of heights) {
    const h = await header(a.height);
    if (h === null) {
      return { state: "unavailable" };
    }
    if (!attests(a, h)) {
      return { state: "mismatch" };
    }
    return { state: "confirmed", height: h.height, time: h.time, lines: entry.lines };
  }
  return { state: "pending", lines: entry.lines };
}

/**
 * Checks the signature of a head that covers a record.
 *
 * @param signatures - The lines of `docs/ledgers/signatures.jsonl`.
 * @param publicKeyHex - The published ML-DSA-65 key.
 * @param label - The ledger's label.
 * @param position - The record's line (0-based).
 * @param lineHashes - The local ledger's line hashes (hex, no prefix).
 * @returns Verified (the first covering head whose hash is this ledger's), none, or invalid.
 */
export function checkSignature(
  signatures: readonly HeadSignature[],
  publicKeyHex: string,
  label: string,
  position: number,
  lineHashes: readonly string[],
): SignatureWitness {
  const covering = signatures
    .filter((s) => s.label === label && s.lines >= position + 1)
    .sort((a, b) => a.lines - b.lines);
  const first = covering[0];
  if (first === undefined) {
    return { state: "none" };
  }
  const ours = `0x${lineHashes[first.lines - 1] ?? ""}`;
  if (first.head !== ours || !verifyHead(publicKeyHex, first)) {
    return { state: "invalid" };
  }
  return { state: "verified", lines: first.lines, signedAt: first.signedAt };
}

/** The public block explorers a Bitcoin attestation is checked against (as the pipeline's). */
export const EXPLORERS = ["https://mempool.space/api", "https://blockstream.info/api"] as const;

/**
 * A block header from the explorers that answer; null when none answers or they disagree.
 *
 * @param height - Block height.
 * @param fetcher - `fetch` (injectable).
 * @returns The header's height, Merkle root and time.
 */
export async function explorerHeader(
  height: number,
  fetcher: typeof fetch = fetch,
): Promise<BlockHeader | null> {
  const seen = await Promise.all(
    EXPLORERS.map(async (api): Promise<BlockHeader | null> => {
      try {
        const hash = (await (await fetcher(`${api}/block-height/${String(height)}`)).text()).trim();
        const block = (await (await fetcher(`${api}/block/${hash}`)).json()) as {
          height: number;
          merkle_root: string;
          timestamp: number;
        };
        return { height: block.height, merkleRoot: block.merkle_root, time: block.timestamp };
      } catch {
        return null;
      }
    }),
  );
  const answers = seen.filter((h): h is BlockHeader => h !== null);
  const [first] = answers;
  if (first === undefined) {
    return null;
  }
  const agree = answers.every(
    (h) => h.height === first.height && h.merkleRoot === first.merkleRoot && h.time === first.time,
  );
  return agree ? first : null;
}
