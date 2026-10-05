# ZK circuits: build pipeline, trusted setup and testing

Circuits live in the contracts workspace, next to the Solidity verifiers generated from them.
Tooling: [circom](https://docs.circom.io/) 2.2.3 (compiler), [snarkjs](https://github.com/iden3/snarkjs)
0.7 (setup, proving, verifier export), [circomlib](https://github.com/iden3/circomlib) (standard
templates), proof system **Groth16** on the BN254 curve (cheapest on-chain verification).

## Layout

```text
contracts/
├── circuits/
│   ├── <name>.circom              circuit with `component main` (one verifier per main circuit)
│   └── inputs/<name>.json         sample input used by the build (witness + sanity proof)
├── scripts/zk/
│   ├── build.ts                   the pipeline (npm run zk:build)
│   ├── ptau.ts                    Powers of Tau download/verification or local generation
│   └── common.ts                  artifact paths and helpers shared with the tests
├── build/                         generated, not committed
│   ├── ptau/                      cached Powers of Tau files
│   └── circuits/<name>/           r1cs, sym, wasm, wtns, zkey, verification key, sample proof
├── src/generated/<Name>Verifier.sol   generated, not committed
└── test/
    ├── circuits/<name>.test.ts    constraint-level tests (circom_tester)
    └── contracts/<Name>Verifier.test.ts   proof-level tests on Hardhat's chain
```

## The pipeline (`npm run zk:build`)

`scripts/zk/build.ts` builds every `circuits/*.circom` file that declares a `component main`, or
only the circuits named on the command line (`npm run zk:build -- square_root`). Each step is
logged; the equivalent snarkjs CLI commands are shown for reference.

| #   | Step     | What happens                                                                                                       | snarkjs/circom CLI equivalent                                                                   |
| --- | -------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------- |
| 1   | compile  | circom produces the R1CS constraints, a WASM witness generator and debug symbols; circomlib is on the include path | `circom c.circom --r1cs --wasm --sym -l node_modules`                                           |
| 2   | witness  | compute a witness for `inputs/<name>.json` and check it against every constraint                                   | `snarkjs wtns calculate …` + `snarkjs wtns check …`                                             |
| 3   | setup    | pick the Powers of Tau size from the constraint count, run Groth16 phase 2, export the verification key            | `snarkjs groth16 setup …`, `snarkjs zkey contribute …`, `snarkjs zkey export verificationkey …` |
| 4   | verifier | export the Solidity verifier, renamed `<Name>Verifier`, into `src/generated/`                                      | `snarkjs zkey export solidityverifier …`                                                        |
| 5   | sanity   | prove the sample input and verify it off-chain                                                                     | `snarkjs groth16 fullprove …` + `snarkjs groth16 verify …`                                      |

A failed build removes the circuit's stale artifacts and verifier, so a verifier never outlives
its proving key. Run `npm run compile` afterwards so Hardhat picks up new verifiers.

## Trusted setup

Groth16 needs a two-phase trusted setup. If every participant in a phase colludes, or a single
participant keeps their randomness ("toxic waste"), proofs can be forged.

**Phase 1 (universal, Powers of Tau).**

- **Default:** the public Hermez/Polygon zkEVM ceremony, which had dozens of independent
  contributions and a final random beacon. Files are downloaded from `circom.info` and checked
  against the BLAKE2b-512 hashes published in the snarkjs README, which are pinned in
  `scripts/zk/ptau.ts`. The file size is chosen automatically (2^power must cover constraints +
  public inputs + outputs; minimum 2^8). Files are cached in `build/ptau/`.
- **`--local-ptau`:** a single-party ceremony generated on your machine. Use it only for offline
  development: whoever ran it could forge proofs.

**Phase 2 (circuit-specific).** The build makes **one development contribution** with random
entropy that is discarded. That is acceptable on a testnet for a hackathon. Production would need
a multi-party phase 2: several independent `snarkjs zkey contribute` rounds, a final
`snarkjs zkey beacon`, and everyone checking the result with `snarkjs zkey verify`.

## Testing strategy

Two levels, each catching a different class of bugs:

1. **Constraint level** (`npm run test:circuits`): standalone mocha with
   [circom_tester](https://github.com/iden3/circom_tester), the pattern circomlib itself uses.
   - The circuit is compiled on the fly; no trusted setup is needed, so these tests are fast.
   - Valid inputs must produce a witness that satisfies every constraint.
   - Invalid inputs must be rejected (`Assert Failed`).
   - Write the negative tests first: an under-constrained circuit accepts inputs it should
     reject, and that is the most common ZK bug.
2. **Proof level** (`npm run test:contracts`): a Hardhat test.
   - Generates a real proof with snarkjs from the build artifacts.
   - Deploys the **generated** verifier on Hardhat's simulated chain.
   - Checks that it accepts the proof and rejects it for different public inputs.
   - This is exactly what the dApp does, so a broken export or a setup mismatch fails here.

circomkit was considered as a test framework. It was not adopted because it would duplicate the
explicit build pipeline with its own conventions.

## Adding a circuit

1. Create `contracts/circuits/<name>.circom` with `pragma circom 2.2.0;` and a
   `component main {public [...]}`. Put reusable templates without a `main` in
   `contracts/circuits/lib/`.
2. Add a valid sample input at `contracts/circuits/inputs/<name>.json`.
3. Add `contracts/test/circuits/<name>.test.ts` with positive and negative cases.
4. Run `npm run zk:build -- <name>`, then `npm run compile`.
5. Add a proof-level test for `<Name>Verifier` in `contracts/test/contracts/`.
6. If the circuit needs more than 2^20 constraints, pin the hash of the larger Powers of Tau file
   in `scripts/zk/ptau.ts`.

## Releasing artifacts

The proving key (`.zkey`), the WASM witness generator and the deployed verifier must come from
the **same** setup. Re-running `zk:build` creates a new phase-2 contribution, so it invalidates
any verifier deployed earlier.

Before deploying the Sepolia demo, freeze a release:

- keep the `.zkey`, the `.wasm`, the verification key and the verifier source;
- record the deployed verifier address;
- store them as a GitHub release asset, or commit them to a `release/` folder if they are small
  enough.

The frontend will serve the `.wasm` and `.zkey` from that release.

## Security checklist for real circuits

- Use `<==` (assign **and** constrain). Use `<--` only together with an explicit constraint.
- Range-check every input that is compared or summed (`Num2Bits`, `LessThan` from circomlib).
  Field elements wrap around modulo p.
- Bind proofs to their context (permit, period, operator address) through public inputs.
- Add a negative test for every rule the circuit is supposed to enforce.
- Consider static analysis with [circomspect](https://github.com/trailofbits/circomspect) once
  real circuits exist.
