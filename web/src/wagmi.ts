import { getDefaultConfig } from "@rainbow-me/rainbowkit";
import { http } from "wagmi";
import { sepolia } from "wagmi/chains";

/**
 * Reads an optional `VITE_*` variable, treating a blank value as unset.
 *
 * @param value - Raw value from `import.meta.env`.
 * @returns The trimmed value, or `undefined` when it is missing or blank.
 */
function optionalEnv(value: string | undefined): string | undefined {
  const trimmed = value?.trim();

  return trimmed === undefined || trimmed === "" ? undefined : trimmed;
}

/** wagmi + RainbowKit configuration: Sepolia only, with MetaMask and RainbowKit's default wallets. */
export const wagmiConfig = getDefaultConfig({
  appName: "TerraChain",
  // RainbowKit maps the "YOUR_PROJECT_ID" placeholder to a shared demo id: fine for local
  // development, but deployments need their own id from https://cloud.reown.com.
  projectId: optionalEnv(import.meta.env.VITE_WALLETCONNECT_PROJECT_ID) ?? "YOUR_PROJECT_ID",
  chains: [sepolia],
  transports: {
    // `undefined` falls back to the chain's public RPC endpoint.
    [sepolia.id]: http(optionalEnv(import.meta.env.VITE_SEPOLIA_RPC_URL)),
  },
});

// Registers the config type so wagmi hooks infer the configured chains.
declare module "wagmi" {
  interface Register {
    config: typeof wagmiConfig;
  }
}
