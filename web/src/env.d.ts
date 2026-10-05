// Typed access to the VITE_* variables documented in web/.env.example.
interface ImportMetaEnv {
  /** WalletConnect Cloud project id; optional for local development. */
  readonly VITE_WALLETCONNECT_PROJECT_ID?: string;
  /** Sepolia JSON-RPC URL; the chain's public endpoint is used when unset. */
  readonly VITE_SEPOLIA_RPC_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
