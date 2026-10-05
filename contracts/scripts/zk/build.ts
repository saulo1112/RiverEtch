// Circuit build pipeline: compile -> witness -> trusted setup -> Solidity verifier -> sanity proof.
//
// Usage (from the repository root or the contracts workspace):
//   npm run zk:build                         build every circuits/*.circom that has a `component main`
//   npm run zk:build -- square_root          build only the named circuits
//   npm run zk:build -- --local-ptau         offline: generate a dev Powers of Tau instead of downloading
//
// Artifacts go to build/circuits/<name>/ and the verifier to src/generated/<Name>Verifier.sol.
import { execFile } from "node:child_process";
import { randomBytes } from "node:crypto";
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs, promisify } from "node:util";
import * as snarkjs from "snarkjs";

import {
  CIRCUITS_DIR,
  CONTRACTS_ROOT,
  GENERATED_VERIFIERS_DIR,
  circomIncludePaths,
  circuitArtifacts,
  terminateSnarkjsCurve,
  type CircuitArtifacts,
} from "./common.js";
import { ensurePtau, requiredPtauPower, type PtauSource } from "./ptau.js";

const execFileAsync = promisify(execFile);

/** Oldest circom release supported by the circuits (matches their `pragma circom`). */
const MIN_CIRCOM_VERSION: readonly [number, number, number] = [2, 2, 0];

const TOTAL_STEPS = 5;

const USAGE = `Usage: npm run zk:build -- [circuit ...] [--local-ptau]

  circuit        circuit names (circuits/<name>.circom); default: every circuit with a main component
  --local-ptau   generate a single-party dev Powers of Tau instead of downloading the Hermez one`;

async function main(): Promise<void> {
  const { values, positionals } = parseArgs({
    allowPositionals: true,
    options: {
      "local-ptau": { type: "boolean", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
  });
  if (values.help) {
    console.log(USAGE);
    return;
  }

  await assertCircomInstalled();
  const ptauSource: PtauSource = values["local-ptau"] ? "local" : "hermez";
  const names = positionals.length > 0 ? positionals : await listMainCircuits();
  if (names.length === 0) {
    throw new Error(`No circuit with a \`component main\` found in ${relative(CIRCUITS_DIR)}.`);
  }

  for (const name of names) {
    await buildCircuit(circuitArtifacts(name), ptauSource);
  }
}

async function buildCircuit(circuit: CircuitArtifacts, ptauSource: PtauSource): Promise<void> {
  console.log(`\n=== ${circuit.name} ===`);
  // Start clean so a failed build never leaves a verifier that matches no proving key.
  await rm(circuit.outDir, { recursive: true, force: true });
  await rm(circuit.verifierSolidity, { force: true });
  await mkdir(circuit.outDir, { recursive: true });
  const input = JSON.parse(await readFile(circuit.input, "utf8")) as snarkjs.CircuitSignals;

  // 1. Compile the circuit to R1CS constraints, a WASM witness generator and debug symbols.
  logStep(1, "compile", `circom ${relative(circuit.source)} --r1cs --wasm --sym`);
  await compileCircuit(circuit);
  const info = await snarkjs.r1cs.info(circuit.r1cs);
  console.log(
    `  ${info.nConstraints} constraints, ${info.nPubInputs} public inputs, ` +
      `${info.nPrvInputs} private inputs, ${info.nOutputs} outputs`,
  );

  // 2. Compute a witness for the sample input and check it against every constraint.
  logStep(2, "witness", `${relative(circuit.input)} -> ${relative(circuit.witness)}`);
  await snarkjs.wtns.calculate(input, circuit.wasm, circuit.witness);
  const witnessIsValid: unknown = await snarkjs.wtns.check(circuit.r1cs, circuit.witness);
  if (witnessIsValid !== true) {
    throw new Error(`The witness for ${relative(circuit.input)} violates the constraints.`);
  }

  // 3. Groth16 trusted setup: phase 1 (Powers of Tau) + circuit-specific phase 2.
  const power = requiredPtauPower(info.nConstraints + info.nPubInputs + info.nOutputs);
  logStep(3, "setup", `Groth16 with a 2^${power} Powers of Tau (${ptauSource})`);
  const ptau = await ensurePtau(power, ptauSource);
  await snarkjs.zKey.newZKey(circuit.r1cs, ptau, circuit.initialZkey);
  // Single development contribution with discarded random entropy. A production deployment needs
  // a multi-party phase-2 ceremony (see docs/zk-circuits.md).
  await snarkjs.zKey.contribute(
    circuit.initialZkey,
    circuit.zkey,
    "development contribution",
    randomBytes(32).toString("hex"),
  );
  await rm(circuit.initialZkey);
  const verificationKey: unknown = await snarkjs.zKey.exportVerificationKey(circuit.zkey);
  await writeJson(circuit.verificationKey, verificationKey);

  // 4. Export the Solidity verifier into the Hardhat sources.
  logStep(4, "verifier", `${relative(circuit.verifierSolidity)} (${circuit.verifierContractName})`);
  await exportSolidityVerifier(circuit);

  // 5. Prove and verify the sample input off-chain, so a broken setup fails here and not later.
  logStep(5, "sanity", "groth16 fullProve + verify with the sample input");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(
    input,
    circuit.wasm,
    circuit.zkey,
  );
  const proofIsValid = await snarkjs.groth16.verify(verificationKey, publicSignals, proof);
  if (!proofIsValid) {
    throw new Error(`The sample proof for ${circuit.name} does not verify.`);
  }
  await writeJson(circuit.proof, proof);
  await writeJson(circuit.publicSignals, publicSignals);
  console.log(`  proof OK, public signals: ${JSON.stringify(publicSignals)}`);
}

async function compileCircuit(circuit: CircuitArtifacts): Promise<void> {
  const includeArgs = circomIncludePaths().flatMap((dir) => ["-l", dir]);
  const { stdout, stderr } = await execFileAsync(
    "circom",
    [circuit.source, "--r1cs", "--wasm", "--sym", "--output", circuit.outDir, ...includeArgs],
    { maxBuffer: 64 * 1024 * 1024 },
  );
  process.stdout.write(indent(stdout));
  if (stderr.length > 0) {
    process.stderr.write(indent(stderr));
  }
}

async function exportSolidityVerifier(circuit: CircuitArtifacts): Promise<void> {
  // snarkjs only exports its entry point; its templates live next to it in the package.
  const snarkjsDir = path.dirname(fileURLToPath(import.meta.resolve("snarkjs")));
  const template = await readFile(
    path.join(snarkjsDir, "templates", "verifier_groth16.sol.ejs"),
    "utf8",
  );
  const generated: unknown = await snarkjs.zKey.exportSolidityVerifier(circuit.zkey, {
    groth16: template,
  });
  if (typeof generated !== "string" || !generated.includes("contract Groth16Verifier")) {
    throw new Error("snarkjs did not return a Groth16 verifier contract.");
  }

  // Unique contract names keep Hardhat artifacts and TypeChain bindings unambiguous.
  const [spdxLine, ...rest] = generated
    .replace("contract Groth16Verifier", `contract ${circuit.verifierContractName}`)
    .split("\n");
  const header = [
    `// Generated by scripts/zk/build.ts from circuits/${circuit.name}.circom. Do not edit.`,
    `// Matches build/circuits/${circuit.name}/${path.basename(circuit.zkey)}; regenerate with \`npm run zk:build\`.`,
  ];
  await mkdir(GENERATED_VERIFIERS_DIR, { recursive: true });
  await writeFile(circuit.verifierSolidity, [spdxLine ?? "", ...header, ...rest].join("\n"));
}

async function assertCircomInstalled(): Promise<void> {
  let output: string;
  try {
    ({ stdout: output } = await execFileAsync("circom", ["--version"]));
  } catch {
    throw new Error(
      [
        "The circom compiler was not found on your PATH.",
        `Install circom >= ${MIN_CIRCOM_VERSION.join(".")} (see README > Prerequisites):`,
        "  https://docs.circom.io/getting-started/installation/",
      ].join("\n"),
    );
  }

  const match = /(\d+)\.(\d+)\.(\d+)/.exec(output);
  const version = match === null ? [] : [Number(match[1]), Number(match[2]), Number(match[3])];
  if (!isAtLeast(version, MIN_CIRCOM_VERSION)) {
    throw new Error(
      `circom >= ${MIN_CIRCOM_VERSION.join(".")} is required, found: ${output.trim()}`,
    );
  }
  console.log(`Using ${output.trim()}`);
}

function isAtLeast(version: readonly number[], minimum: readonly number[]): boolean {
  for (const [index, required] of minimum.entries()) {
    const actual = version[index];
    if (actual === undefined || Number.isNaN(actual)) {
      return false;
    }
    if (actual !== required) {
      return actual > required;
    }
  }
  return true;
}

async function listMainCircuits(): Promise<string[]> {
  const entries = await readdir(CIRCUITS_DIR, { withFileTypes: true });
  const names: string[] = [];

  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".circom")) {
      continue;
    }
    const source = await readFile(path.join(CIRCUITS_DIR, entry.name), "utf8");
    if (/^\s*component\s+main\b/m.test(source)) {
      names.push(path.basename(entry.name, ".circom"));
    }
  }

  return names.sort();
}

async function writeJson(file: string, value: unknown): Promise<void> {
  await writeFile(file, `${JSON.stringify(value, null, 2)}\n`);
}

function logStep(index: number, title: string, detail: string): void {
  console.log(`[${index}/${TOTAL_STEPS}] ${title}: ${detail}`);
}

function relative(file: string): string {
  return path.relative(CONTRACTS_ROOT, file);
}

function indent(text: string): string {
  return text.replace(/^(?=.)/gm, "  ");
}

try {
  await main();
} catch (error) {
  console.error(`\nzk:build failed: ${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
} finally {
  await terminateSnarkjsCurve();
}
