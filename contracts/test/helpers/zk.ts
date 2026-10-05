import { existsSync } from "node:fs";

import * as snarkjs from "snarkjs";

import { circuitArtifacts, type CircuitArtifacts } from "../../scripts/zk/common.js";

/** A G1 point as `[x, y]` hex strings. */
type G1Point = [string, string];

/** Arguments of a generated Groth16 `verifyProof(pA, pB, pC, publicSignals)` call. */
export type Groth16VerifierArgs = [
  pA: G1Point,
  pB: [G1Point, G1Point],
  pC: G1Point,
  publicSignals: string[],
];

/**
 * Returns a circuit's build artifacts, failing with an actionable message when they are missing.
 *
 * @param name - Circuit name, e.g. `"square_root"`.
 * @returns The artifact paths, with the proving artifacts and the verifier known to exist.
 */
export function requireBuiltCircuit(name: string): CircuitArtifacts {
  const artifacts = circuitArtifacts(name);
  const missing = [artifacts.wasm, artifacts.zkey, artifacts.verifierSolidity].filter(
    (file) => !existsSync(file),
  );
  if (missing.length > 0) {
    throw new Error(
      `ZK artifacts for "${name}" are missing (${missing.join(", ")}). ` +
        "Run `npm run zk:build` (then `npm run compile`) first.",
    );
  }

  return artifacts;
}

/**
 * Converts a snarkjs Groth16 proof into the arguments of the generated Solidity verifier.
 *
 * @param proof - Proof returned by `groth16.fullProve`.
 * @param publicSignals - Public signals returned with the proof.
 * @returns The `verifyProof` arguments, as hex strings.
 */
export async function toVerifierArgs(
  proof: snarkjs.Groth16Proof,
  publicSignals: snarkjs.PublicSignals,
): Promise<Groth16VerifierArgs> {
  const calldata = await snarkjs.groth16.exportSolidityCallData(proof, publicSignals);

  return JSON.parse(`[${calldata}]`) as Groth16VerifierArgs;
}
