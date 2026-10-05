// Constraint-level tests: compile the circuit on the fly with circom_tester (no trusted setup) and
// check that valid inputs satisfy every constraint while invalid ones are rejected.
import assert from "node:assert/strict";

import { wasm as wasmTester, type WasmTester } from "circom_tester";

import { circomIncludePaths, circuitArtifacts } from "../../scripts/zk/common.js";

/** circom's witness generator throws this when an `===` or `assert` fails. */
const CONSTRAINT_FAILURE = /Assert Failed/;

describe("square_root circuit", function () {
  let circuit: WasmTester;

  before(async function () {
    circuit = await wasmTester(circuitArtifacts("square_root").source, {
      include: circomIncludePaths(),
    });
  });

  it("accepts a valid root and satisfies every constraint", async function () {
    const witness = await circuit.calculateWitness({ root: 3, square: 9 }, true);

    await circuit.checkConstraints(witness);
  });

  it("rejects a root whose square is not the public input", async function () {
    await assert.rejects(
      circuit.calculateWitness({ root: 3, square: 10 }, true),
      CONSTRAINT_FAILURE,
    );
  });

  it("rejects the trivial root zero", async function () {
    await assert.rejects(
      circuit.calculateWitness({ root: 0, square: 0 }, true),
      CONSTRAINT_FAILURE,
    );
  });
});
