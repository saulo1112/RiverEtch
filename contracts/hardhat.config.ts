import hardhatToolboxMochaEthersPlugin from "@nomicfoundation/hardhat-toolbox-mocha-ethers";
import { configVariable, defineConfig } from "hardhat/config";

/** Solidity compiler version shared by every build profile. */
const SOLC_VERSION = "0.8.34";

export default defineConfig({
  plugins: [hardhatToolboxMochaEthersPlugin],
  paths: {
    sources: "src",
    tests: {
      mocha: "test/contracts",
      solidity: "test/contracts",
    },
  },
  solidity: {
    profiles: {
      default: {
        version: SOLC_VERSION,
      },
      production: {
        version: SOLC_VERSION,
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
    },
  },
  networks: {
    // Config variables are resolved lazily from environment variables or the Hardhat keystore
    // (`npx hardhat keystore set SEPOLIA_PRIVATE_KEY`), so they are only needed when deploying.
    sepolia: {
      type: "http",
      chainType: "l1",
      url: configVariable("SEPOLIA_RPC_URL"),
      accounts: [configVariable("SEPOLIA_PRIVATE_KEY")],
    },
  },
  verify: {
    etherscan: {
      apiKey: configVariable("ETHERSCAN_API_KEY"),
    },
  },
});
