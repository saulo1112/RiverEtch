// Reads and writes the ledger anchor through ethers v6.
import { Contract, id, type ContractRunner } from "ethers";

import { LEDGER_ANCHOR_ABI } from "./abi.ts";
import type { ChainAnchor } from "./ledger.ts";

/** One ledger to anchor: its label (hashed into the subject), head and line count. */
export interface LedgerState {
  readonly label: string;
  readonly head: string;
  readonly lines: number;
}

function contract(address: string, runner: ContractRunner): Contract {
  return new Contract(address, LEDGER_ANCHOR_ABI, runner);
}

function call<T>(target: Contract, name: string, ...args: unknown[]): Promise<T> {
  const fn = target.getFunction(name);
  return fn(...args) as Promise<T>;
}

/**
 * Every anchor of a ledger, oldest first.
 *
 * @param runner - A provider.
 * @param address - The contract.
 * @param label - The ledger's label (see `subjectLabel`).
 * @returns The anchors.
 */
export async function readAnchors(
  runner: ContractRunner,
  address: string,
  label: string,
): Promise<ChainAnchor[]> {
  const target = contract(address, runner);
  const subject = id(label);
  const total = Number(await call<bigint>(target, "count", subject));
  const rows = await Promise.all(
    Array.from({ length: total }, (_, k) =>
      call<{ head: string; lines: bigint; timestamp: bigint; blockNumber: bigint }>(
        target,
        "anchorAt",
        subject,
        k,
      ),
    ),
  );
  return rows.map((r) => ({
    head: r.head,
    lines: Number(r.lines),
    timestamp: Number(r.timestamp),
    blockNumber: Number(r.blockNumber),
  }));
}

/**
 * The account allowed to anchor.
 *
 * @param runner - A provider.
 * @param address - The contract.
 * @returns Its address.
 */
export function readOwner(runner: ContractRunner, address: string): Promise<string> {
  return call<string>(contract(address, runner), "owner");
}

/**
 * Anchors several ledgers in one transaction and waits for it to be mined.
 *
 * @param signer - The owner's signer.
 * @param address - The contract.
 * @param ledgers - What to anchor.
 * @returns The transaction's hash.
 */
export async function anchorLedgers(
  signer: ContractRunner,
  address: string,
  ledgers: readonly LedgerState[],
): Promise<string> {
  const target = contract(address, signer);
  const args = [
    ledgers.map((l) => id(l.label)),
    ledgers.map((l) => l.head),
    ledgers.map((l) => l.lines),
  ];
  // An explicit gas limit with 50 % to spare: a wallet that wraps the call (MetaMask's smart
  // accounts) otherwise leaves the inner call too little and it runs out of gas.
  const estimate = await target.getFunction("anchorBatch").estimateGas(...args);
  const tx = await call<{ hash: string; wait: () => Promise<unknown> }>(
    target,
    "anchorBatch",
    ...args,
    { gasLimit: (estimate * 3n) / 2n },
  );
  await tx.wait();
  return tx.hash;
}
