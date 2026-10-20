// Post-quantum signatures of ledger heads (ML-DSA-65, FIPS 204), verified in the browser with
// @noble/post-quantum, an implementation independent of the pipeline's signer (pqcrypto,
// pipeline/src/climate_pipeline/signing.py). The statement and the context string are the
// pipeline's: compact, key-sorted JSON of {head, label, lines, signedAt}, context
// `riveretch/ledger-head/v1`. A signature says who published a head; the head commits to every
// record above it.
import { ml_dsa65 } from "@noble/post-quantum/ml-dsa.js";
import { hexToBytes } from "@noble/hashes/utils.js";

/** The FIPS 204 context string RiverEtch signs with. */
export const CONTEXT = "riveretch/ledger-head/v1";

/** One line of `docs/ledgers/signatures.jsonl`. */
export interface HeadSignature {
  readonly label: string;
  readonly lines: number;
  readonly head: string;
  readonly signedAt: string;
  readonly algorithm: string;
  readonly context: string;
  readonly signature: string;
}

/**
 * The bytes signed for one head, exactly as the pipeline writes them.
 *
 * @param s - The head's label, line count, hash and signing time.
 * @returns Compact, key-sorted JSON in UTF-8.
 */
export function statement(
  s: Pick<HeadSignature, "label" | "lines" | "head" | "signedAt">,
): Uint8Array {
  // Keys in sorted order, no spaces: what Python's json.dumps(sort_keys, separators) writes.
  const json = `{"head":${JSON.stringify(s.head)},"label":${JSON.stringify(s.label)},"lines":${String(s.lines)},"signedAt":${JSON.stringify(s.signedAt)}}`;
  return new TextEncoder().encode(json);
}

/**
 * Whether a head's signature verifies under the public key.
 *
 * @param publicKeyHex - The ML-DSA-65 public key (docs/keys/ml-dsa-65.json), hex.
 * @param s - The signature line.
 * @returns True when it verifies with RiverEtch's context string.
 */
export function verifyHead(publicKeyHex: string, s: HeadSignature): boolean {
  if (s.algorithm !== "ML-DSA-65" || s.context !== CONTEXT) {
    return false;
  }
  try {
    return ml_dsa65.verify(hexToBytes(s.signature), statement(s), hexToBytes(publicKeyHex), {
      context: new TextEncoder().encode(CONTEXT),
    });
  } catch {
    return false; // a malformed key or signature
  }
}
