import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

// Deployment module for the scaffold contract. Usage:
//   npx hardhat ignition deploy ignition/modules/Placeholder.ts --network sepolia
export default buildModule("PlaceholderModule", (m) => {
  const placeholder = m.contract("Placeholder");

  return { placeholder };
});
