// OpenTimestamps proofs (rule v2, docs/water-quality/prospective-v2.md), read in the browser: parse a
// detached `.ots` file, replay its hash path from the file digest to each attestation, and check a
// Bitcoin attestation against a block header. Pure and synchronous; the format is
// python-opentimestamps' (opentimestamps/core/timestamp.py, op.py, notary.py), and the pipeline
// verifies the same proofs with that library (pipeline/src/climate_pipeline/timestamps.py).
import { ripemd160, sha1 } from "@noble/hashes/legacy.js";
import { sha256 } from "@noble/hashes/sha2.js";
import { keccak_256 } from "@noble/hashes/sha3.js";
import { bytesToHex, hexToBytes } from "@noble/hashes/utils.js";

const MAGIC = hexToBytes("004f70656e54696d657374616d7073000050726f6f6600bf89e2e884e89294");
const BITCOIN = "0588960d73d71901";
const PENDING = "83dfe30d2ef90c8e";
const SHA256 = 0x08;

/** Where a proof's path ends: a Bitcoin block, a calendar still to answer, or something else. */
export type Attestation =
  | { readonly kind: "bitcoin"; readonly height: number; readonly msg: Uint8Array }
  | { readonly kind: "pending"; readonly uri: string; readonly msg: Uint8Array }
  | { readonly kind: "unknown"; readonly msg: Uint8Array };

/** A detached proof: the digest it timestamps and every attestation its path reaches. */
export interface Proof {
  readonly digest: Uint8Array;
  readonly attestations: readonly Attestation[];
}

class Reader {
  private at = 0;
  private readonly bytes: Uint8Array;

  constructor(bytes: Uint8Array) {
    this.bytes = bytes;
  }

  byte(): number {
    const b = this.bytes[this.at];
    if (b === undefined) {
      throw new Error("the proof ends too early");
    }
    this.at += 1;
    return b;
  }

  fixed(n: number): Uint8Array {
    if (this.at + n > this.bytes.length) {
      throw new Error("the proof ends too early");
    }
    const out = this.bytes.slice(this.at, this.at + n);
    this.at += n;
    return out;
  }

  varuint(): number {
    let value = 0;
    let shift = 0;
    for (;;) {
      const b = this.byte();
      value += (b & 0x7f) * 2 ** shift;
      if ((b & 0x80) === 0) {
        return value;
      }
      shift += 7;
    }
  }

  varbytes(): Uint8Array {
    return this.fixed(this.varuint());
  }
}

const concat = (a: Uint8Array, b: Uint8Array): Uint8Array => {
  const out = new Uint8Array(a.length + b.length);
  out.set(a);
  out.set(b, a.length);
  return out;
};

// One operation applied to the message (its argument read first, for append and prepend).
function operate(tag: number, reader: Reader, msg: Uint8Array): Uint8Array {
  switch (tag) {
    case 0xf0:
      return concat(msg, reader.varbytes()); // append
    case 0xf1:
      return concat(reader.varbytes(), msg); // prepend
    case 0xf2:
      return msg.slice().reverse();
    case 0xf3:
      return new TextEncoder().encode(bytesToHex(msg)); // hexlify
    case 0x02:
      return sha1(msg);
    case 0x03:
      return ripemd160(msg);
    case SHA256:
      return sha256(msg);
    case 0x67:
      return keccak_256(msg);
    default:
      throw new Error(`unknown operation 0x${tag.toString(16)}`);
  }
}

function attestation(reader: Reader, msg: Uint8Array): Attestation {
  const tag = bytesToHex(reader.fixed(8));
  const payload = new Reader(reader.varbytes());
  if (tag === BITCOIN) {
    return { kind: "bitcoin", height: payload.varuint(), msg };
  }
  if (tag === PENDING) {
    return { kind: "pending", uri: new TextDecoder().decode(payload.varbytes()), msg };
  }
  return { kind: "unknown", msg };
}

// A timestamp: `0xff` before every branch but the last; a branch is `0x00` and an attestation, or
// an operation and the timestamp of its result.
function timestamp(reader: Reader, msg: Uint8Array, out: Attestation[]): void {
  const branch = (tag: number) => {
    if (tag === 0x00) {
      out.push(attestation(reader, msg));
    } else {
      timestamp(reader, operate(tag, reader, msg), out);
    }
  };
  let tag = reader.byte();
  while (tag === 0xff) {
    branch(reader.byte());
    tag = reader.byte();
  }
  branch(tag);
}

/**
 * Parses a detached OpenTimestamps proof and replays its path.
 *
 * @param bytes - The `.ots` file.
 * @returns The file digest it timestamps and the attestations its path reaches.
 */
export function parseProof(bytes: Uint8Array): Proof {
  const reader = new Reader(bytes);
  if (bytesToHex(reader.fixed(MAGIC.length)) !== bytesToHex(MAGIC)) {
    throw new Error("not an OpenTimestamps proof");
  }
  if (reader.varuint() !== 1) {
    throw new Error("unknown proof version");
  }
  if (reader.byte() !== SHA256) {
    throw new Error("the proof does not timestamp a SHA-256 digest");
  }
  const digest = reader.fixed(32);
  const attestations: Attestation[] = [];
  timestamp(reader, digest, attestations);
  return { digest, attestations };
}

/** The fields of a Bitcoin block header a proof is checked against. */
export interface BlockHeader {
  readonly height: number;
  /** As block explorers print it (byte-reversed). */
  readonly merkleRoot: string;
  /** Unix seconds. */
  readonly time: number;
}

/**
 * Whether a Bitcoin attestation's message is that block's Merkle root.
 *
 * @param a - The attestation.
 * @param header - The block header at its height.
 * @returns True when they match.
 */
export function attests(a: Attestation & { kind: "bitcoin" }, header: BlockHeader): boolean {
  return header.height === a.height && bytesToHex(a.msg.slice().reverse()) === header.merkleRoot;
}
