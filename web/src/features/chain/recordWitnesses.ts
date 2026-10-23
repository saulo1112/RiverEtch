// The two witnesses beside a record's post on Ethereum, from the daily run's published files: the
// Bitcoin timestamp of a head that covers it, and that head's quantum-safe signature. Shared by
// "Check this reading" and "Check this record" (the daily flow record).
import { loadProof, loadSignatures, loadStatus } from "../reaches/data.ts";
import {
  checkBitcoin,
  checkSignature,
  coveringProof,
  explorerHeader,
  type BitcoinWitness,
  type SignatureWitness,
} from "./witness.ts";

/**
 * A record's Bitcoin timestamp and signature, checked in the browser.
 *
 * @param label - Its record list's label, e.g. "terrachain:platte-louisville:daily-record".
 * @param position - Its line in the list (-1: not in it).
 * @param hashes - Each line's SHA-256, in order.
 * @returns Both witnesses ("unavailable" when the daily run's files cannot be read).
 */
export async function witnessesOf(
  label: string,
  position: number,
  hashes: readonly string[],
): Promise<{ bitcoin: BitcoinWitness; signature: SignatureWitness }> {
  const status = await loadStatus();
  if (status === null || position < 0) {
    return { bitcoin: { state: "unavailable" }, signature: { state: "unavailable" } };
  }
  const entry = coveringProof(status.proofs ?? [], label, position);
  const bytes = entry === null ? null : await loadProof(entry.file);
  const bitcoin: BitcoinWitness =
    entry === null
      ? { state: "none" }
      : bytes === null
        ? { state: "unavailable" }
        : await checkBitcoin(entry, bytes, hashes, (h) => explorerHeader(h)).catch(
            (): BitcoinWitness => ({ state: "mismatch" }),
          );
  const signature = checkSignature(
    await loadSignatures(),
    __ML_DSA_PUBLIC_KEY__,
    label,
    position,
    hashes,
  );
  return { bitcoin, signature };
}
