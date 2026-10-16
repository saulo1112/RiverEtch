// The parts of the ledger anchor the web app calls; no build-time globals, so a Node test can use
// it against the compiled contract (contracts/test/contracts/LedgerAnchor.test.ts).

/** The parts of `LedgerAnchor` the web app calls (contracts/src/LedgerAnchor.sol). */
export const LEDGER_ANCHOR_ABI = [
  "function owner() view returns (address)",
  "function count(bytes32 subject) view returns (uint256)",
  "function anchorAt(bytes32 subject, uint256 index) view returns (tuple(bytes32 head, uint64 lines, uint64 timestamp, uint64 blockNumber))",
  "function anchorBatch(bytes32[] subjects, bytes32[] heads, uint64[] lines)",
] as const;
