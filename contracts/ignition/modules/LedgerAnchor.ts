import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

// Deploys the ledger anchor; the deploying account becomes its owner. Usage:
//   npx hardhat ignition deploy ignition/modules/LedgerAnchor.ts --network sepolia --verify
export default buildModule("LedgerAnchorModule", (m) => {
  const ledgerAnchor = m.contract("LedgerAnchor");

  return { ledgerAnchor };
});
