// Where the ledger anchor lives: its Sepolia address (from Hardhat Ignition's deployment, read by
// vite.config.ts, or VITE_LEDGER_ANCHOR_ADDRESS) and the explorer's links.

/** Sepolia's chain id. */
export const SEPOLIA_CHAIN_ID = 11155111;

function optional(value: string | undefined): string | null {
  const trimmed = value?.trim();
  return trimmed === undefined || trimmed === "" ? null : trimmed;
}

/** The contract's address, or null before it is deployed. */
export const LEDGER_ANCHOR_ADDRESS: string | null =
  optional(import.meta.env.VITE_LEDGER_ANCHOR_ADDRESS) ?? __LEDGER_ANCHOR__;

const EXPLORER = "https://sepolia.etherscan.io";

/**
 * Etherscan links.
 *
 * @param kind - What to link to.
 * @param id - The block number, transaction hash or address.
 * @returns The URL.
 */
export function explorerUrl(kind: "block" | "tx" | "address", id: string | number): string {
  return `${EXPLORER}/${kind}/${String(id)}`;
}
