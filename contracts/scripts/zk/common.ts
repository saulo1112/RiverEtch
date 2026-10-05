// Paths and helpers shared by the circuit build pipeline and the circuit/verifier tests.
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

/** Absolute path of the contracts workspace. */
export const CONTRACTS_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");

/** circom sources (`<name>.circom`) and their sample inputs (`inputs/<name>.json`). */
export const CIRCUITS_DIR = path.join(CONTRACTS_ROOT, "circuits");

/** Root of every generated ZK artifact (gitignored, recreated by `npm run zk:build`). */
export const ZK_BUILD_DIR = path.join(CONTRACTS_ROOT, "build");

/** Cache for Powers of Tau files, shared by all circuits. */
export const PTAU_DIR = path.join(ZK_BUILD_DIR, "ptau");

/** Generated Solidity verifiers; inside the Hardhat sources so they get compiled (gitignored). */
export const GENERATED_VERIFIERS_DIR = path.join(CONTRACTS_ROOT, "src", "generated");

/** Paths of the sources and generated artifacts of one circuit. */
export interface CircuitArtifacts {
  /** Circuit name: the circom file name without extension, e.g. `square_root`. */
  readonly name: string;
  /** circom source file. */
  readonly source: string;
  /** Sample input used to generate a witness and a test proof during the build. */
  readonly input: string;
  /** Output directory for this circuit's artifacts. */
  readonly outDir: string;
  /** Constraint system (R1CS). */
  readonly r1cs: string;
  /** Debug symbols mapping signals to witness indices. */
  readonly sym: string;
  /** WebAssembly witness generator (also what the frontend will use to prove). */
  readonly wasm: string;
  /** Witness computed from the sample input. */
  readonly witness: string;
  /** Proving key before the phase-2 contribution. */
  readonly initialZkey: string;
  /** Final proving key (Groth16, phase 2 contributed). */
  readonly zkey: string;
  /** Verification key exported from the final proving key. */
  readonly verificationKey: string;
  /** Sample proof generated from the sample input. */
  readonly proof: string;
  /** Public signals of the sample proof. */
  readonly publicSignals: string;
  /** Name of the generated Solidity verifier contract, e.g. `SquareRootVerifier`. */
  readonly verifierContractName: string;
  /** Generated Solidity verifier file. */
  readonly verifierSolidity: string;
}

/**
 * Returns the paths of a circuit's sources and generated artifacts.
 *
 * @param name - Circuit name, e.g. `"square_root"` for `circuits/square_root.circom`.
 * @returns Absolute paths of every input and output of the build pipeline.
 */
export function circuitArtifacts(name: string): CircuitArtifacts {
  const outDir = path.join(ZK_BUILD_DIR, "circuits", name);
  const verifierContractName = verifierContractNameFor(name);

  return {
    name,
    source: path.join(CIRCUITS_DIR, `${name}.circom`),
    input: path.join(CIRCUITS_DIR, "inputs", `${name}.json`),
    outDir,
    r1cs: path.join(outDir, `${name}.r1cs`),
    sym: path.join(outDir, `${name}.sym`),
    wasm: path.join(outDir, `${name}_js`, `${name}.wasm`),
    witness: path.join(outDir, `${name}.wtns`),
    initialZkey: path.join(outDir, `${name}_0000.zkey`),
    zkey: path.join(outDir, `${name}_final.zkey`),
    verificationKey: path.join(outDir, "verification_key.json"),
    proof: path.join(outDir, "proof.json"),
    publicSignals: path.join(outDir, "public.json"),
    verifierContractName,
    verifierSolidity: path.join(GENERATED_VERIFIERS_DIR, `${verifierContractName}.sol`),
  };
}

/**
 * Derives the Solidity verifier contract name from a circuit name.
 *
 * @param name - Snake-case circuit name, e.g. `"square_root"`.
 * @returns PascalCase name with a `Verifier` suffix, e.g. `"SquareRootVerifier"`.
 */
export function verifierContractNameFor(name: string): string {
  const pascalCase = name
    .split(/[_-]+/)
    .filter((part) => part.length > 0)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");

  return `${pascalCase}Verifier`;
}

/**
 * Returns the include paths to pass to circom (`-l`), so that `include "circomlib/..."` resolves
 * whether or not npm hoisted circomlib to the repository root.
 *
 * @returns Absolute paths of the `node_modules` directories that contain circomlib.
 */
export function circomIncludePaths(): string[] {
  const require = createRequire(import.meta.url);
  const circomlibManifest = require.resolve("circomlib/package.json");

  return [path.dirname(path.dirname(circomlibManifest))];
}

/**
 * Stops the worker threads snarkjs keeps alive for the BN254 curve, so the process can exit.
 *
 * @returns Resolves once the cached curve, if any, has been terminated.
 */
export async function terminateSnarkjsCurve(): Promise<void> {
  // ffjavascript caches the multi-threaded curve on globalThis; snarkjs never terminates it.
  const { curve_bn128: curve } = globalThis as {
    curve_bn128?: { terminate(): Promise<void> } | null;
  };
  await curve?.terminate();
}
