// Minimal type declarations for circom_tester, which ships none.
declare module "circom_tester" {
  /** Circuit input signals: signal name to a number, numeric string, bigint or nested array. */
  export type CircuitInput = Record<string, unknown>;

  /** Options accepted by {@link wasm}; they mirror the circom CLI flags. */
  export interface WasmTesterOptions {
    /** Extra include paths (`-l`) for `include` statements, e.g. the circomlib location. */
    include?: string | string[];
    /** Output directory for the compiled circuit; a temporary directory when omitted. */
    output?: string;
    /** Recompile even if `output` already holds a build (defaults to `true`). */
    recompile?: boolean;
    /** circom constraint simplification level: `--O0`, `--O1` or `--O2`. */
    O?: 0 | 1 | 2;
    /** Prime field name, e.g. `"bn128"`. */
    prime?: string;
    /** Print the circom compiler output. */
    verbose?: boolean;
  }

  /** A compiled circuit that computes witnesses and checks them against its constraints. */
  export interface WasmTester {
    /**
     * Computes the full witness for an input.
     *
     * @param input - Input signals.
     * @param sanityCheck - When true, failed `assert` / `===` checks throw.
     * @returns The witness as field elements.
     */
    calculateWitness(input: CircuitInput, sanityCheck?: boolean): Promise<bigint[]>;

    /**
     * Asserts that a witness satisfies every R1CS constraint.
     *
     * @param witness - Witness returned by {@link WasmTester.calculateWitness}.
     */
    checkConstraints(witness: bigint[]): Promise<void>;

    /**
     * Asserts the values of output signals.
     *
     * @param witness - Witness returned by {@link WasmTester.calculateWitness}.
     * @param expected - Expected output signals, e.g. `{ out: 1n }`.
     */
    assertOut(witness: bigint[], expected: CircuitInput): Promise<void>;
  }

  /**
   * Compiles a circom file with the `circom` binary on the PATH and returns a WASM-based tester.
   *
   * @param circomFile - Path of the circom source file.
   * @param options - Compiler options.
   * @returns A tester for the compiled circuit.
   */
  export function wasm(circomFile: string, options?: WasmTesterOptions): Promise<WasmTester>;
}
