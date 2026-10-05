// Powers of Tau (phase 1 of the Groth16 trusted setup): download the public Hermez ceremony files,
// verified against their published hashes, or generate a local single-party file for offline dev.
import { createHash, randomBytes } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, open, rename, rm } from "node:fs/promises";
import path from "node:path";
import * as snarkjs from "snarkjs";

import { PTAU_DIR } from "./common.js";

/** Smallest Powers of Tau file published by the Hermez ceremony (circuits up to 2^8 constraints). */
export const MIN_PTAU_POWER = 8;

/** Where the Hermez/Polygon zkEVM ceremony files are mirrored (see the snarkjs README). */
const HERMEZ_PTAU_BASE_URL = "https://circom.info";

/**
 * BLAKE2b-512 digests of the Hermez/Polygon zkEVM Powers of Tau files, as published in the snarkjs
 * README (https://github.com/iden3/snarkjs#7-prepare-phase-2). Larger powers exist up to 28.
 */
const HERMEZ_PTAU_BLAKE2B: Readonly<Partial<Record<number, string>>> = {
  8: "d6a8fb3a04feb600096c3b791f936a578c4e664d262e4aa24beed1b7a9a96aa5eb72864d628db247e9293384b74b36ffb52ca8d148d6e1b8b51e279fdf57b583",
  9: "94f108a80e81b5d932d8e8c9e8fd7f46cf32457e31462deeeef37af1b71c2c1b3c71fb0d9b59c654ec266b042735f50311f9fd1d4cadce47ab234ad163157cb5",
  10: "6cfeb8cda92453099d20120bdd0e8a5c4e7706c2da9a8f09ccc157ed2464d921fd0437fb70db42104769efd7d6f3c1f964bcf448c455eab6f6c7d863e88a5849",
  11: "47c282116b892e5ac92ca238578006e31a47e7c7e70f0baa8b687f0a5203e28ea07bbbec765a98dcd654bad618475d4661bfaec3bd9ad2ed12e7abc251d94d33",
  12: "ded2694169b7b08e898f736d5de95af87c3f1a64594013351b1a796dbee393bd825f88f9468c84505ddd11eb0b1465ac9b43b9064aa8ec97f2b73e04758b8a4a",
  13: "58efc8bf2834d04768a3d7ffcd8e1e23d461561729beaac4e3e7a47829a1c9066d5320241e124a1a8e8aa6c75be0ba66f65bc8239a0542ed38e11276f6fdb4d9",
  14: "eeefbcf7c3803b523c94112023c7ff89558f9b8e0cf5d6cdcba3ade60f168af4a181c9c21774b94fbae6c90411995f7d854d02ebd93fb66043dbb06f17a831c1",
  15: "982372c867d229c236091f767e703253249a9b432c1710b4f326306bfa2428a17b06240359606cfe4d580b10a5a1f63fbed499527069c18ae17060472969ae6e",
  16: "6a6277a2f74e1073601b4f9fed6e1e55226917efb0f0db8a07d98ab01df1ccf43eb0e8c3159432acd4960e2f29fe84a4198501fa54c8dad9e43297453efec125",
  17: "6247a3433948b35fbfae414fa5a9355bfb45f56efa7ab4929e669264a0258976741dfbe3288bfb49828e5df02c2e633df38d2245e30162ae7e3bcca5b8b49345",
  18: "7e6a9c2e5f05179ddfc923f38f917c9e6831d16922a902b0b4758b8e79c2ab8a81bb5f29952e16ee6c5067ed044d7857b5de120a90704c1d3b637fd94b95b13e",
  19: "bca9d8b04242f175189872c42ceaa21e2951e0f0f272a0cc54fc37193ff6648600eaf1c555c70cdedfaf9fb74927de7aa1d33dc1e2a7f1a50619484989da0887",
  20: "89a66eb5590a1c94e3f1ee0e72acf49b1669e050bb5f93c73b066b564dca4e0c7556a52b323178269d64af325d8fdddb33da3a27c34409b821de82aa2bf1a27b",
};

/**
 * Where phase 1 comes from: `"hermez"` is the public multi-party ceremony (default), `"local"` is a
 * single-party ceremony run on this machine, acceptable for offline development only.
 */
export type PtauSource = "hermez" | "local";

/** The snarkjs `curves` helpers, which `@types/snarkjs` does not declare. */
interface SnarkjsCurves {
  readonly curves: { getCurveFromName(name: string): Promise<unknown> };
}

/**
 * Computes the Powers of Tau size a circuit needs, with the same rule as `snarkjs groth16 setup`.
 *
 * @param r1csSize - Number of constraints plus public inputs plus outputs of the circuit.
 * @returns The required power (the file must support 2^power), never below {@link MIN_PTAU_POWER}.
 */
export function requiredPtauPower(r1csSize: number): number {
  const circuitPower = Math.floor(Math.log2(Math.max(r1csSize, 1))) + 1;

  return Math.max(circuitPower, MIN_PTAU_POWER);
}

/**
 * Returns a phase-2-ready Powers of Tau file of the given power, downloading or generating it the
 * first time and reusing the cached file afterwards.
 *
 * @param power - Required power: the file supports circuits of up to 2^power constraints.
 * @param source - Where phase 1 comes from; see {@link PtauSource}.
 * @returns Absolute path of the Powers of Tau file.
 */
export async function ensurePtau(power: number, source: PtauSource): Promise<string> {
  await mkdir(PTAU_DIR, { recursive: true });
  const file = path.join(
    PTAU_DIR,
    source === "hermez" ? hermezPtauFileName(power) : `local_dev_${pad(power)}.ptau`,
  );

  if (existsSync(file)) {
    console.log(`  using cached ${path.basename(file)}`);
  } else if (source === "hermez") {
    await downloadHermezPtau(power, file);
  } else {
    await generateLocalPtau(power, file);
  }

  return file;
}

function hermezPtauFileName(power: number): string {
  return `powersOfTau28_hez_final_${pad(power)}.ptau`;
}

function pad(power: number): string {
  return String(power).padStart(2, "0");
}

async function downloadHermezPtau(power: number, file: string): Promise<void> {
  const expectedDigest = HERMEZ_PTAU_BLAKE2B[power];
  if (expectedDigest === undefined) {
    throw new Error(
      `No pinned hash for a 2^${power} Powers of Tau file (pinned: 2^${MIN_PTAU_POWER}..2^20). ` +
        `Add its BLAKE2b-512 hash from the snarkjs README to scripts/zk/ptau.ts.`,
    );
  }

  const url = `${HERMEZ_PTAU_BASE_URL}/${hermezPtauFileName(power)}`;
  console.log(`  downloading ${url}`);
  const response = await fetch(url);
  if (!response.ok || response.body === null) {
    throw new Error(
      `Download failed (HTTP ${response.status}) for ${url}. ` +
        "Use `npm run zk:build -- --local-ptau` to work offline.",
    );
  }

  // Stream to a temporary file while hashing, and only move it into place once the hash matches.
  const partial = `${file}.partial`;
  const hash = createHash("blake2b512");
  // Node types fetch bodies as ReadableStream<any>; they are always byte streams.
  const body = response.body as ReadableStream<Uint8Array>;
  const reader = body.getReader();
  const handle = await open(partial, "w");
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      hash.update(value);
      await handle.write(value);
    }
  } finally {
    await handle.close();
  }

  const digest = hash.digest("hex");
  if (digest !== expectedDigest) {
    await rm(partial, { force: true });
    throw new Error(
      `BLAKE2b-512 mismatch for ${url}: expected ${expectedDigest}, got ${digest}. Refusing to use it.`,
    );
  }
  await rename(partial, file);
  console.log("  verified BLAKE2b-512 against the hash published in the snarkjs README");
}

async function generateLocalPtau(power: number, file: string): Promise<void> {
  console.warn(
    `  generating a LOCAL single-party Powers of Tau (2^${power}): fine for development, ` +
      "never for a production deployment",
  );
  const { curves } = snarkjs as unknown as SnarkjsCurves;
  const curve = await curves.getCurveFromName("bn128");
  const initial = `${file}.0000`;
  const contributed = `${file}.0001`;

  try {
    await snarkjs.powersOfTau.newAccumulator(curve, power, initial);
    await snarkjs.powersOfTau.contribute(
      initial,
      contributed,
      "local development contribution",
      randomBytes(32).toString("hex"),
    );
    await snarkjs.powersOfTau.preparePhase2(contributed, file);
  } finally {
    await rm(initial, { force: true });
    await rm(contributed, { force: true });
  }
}
