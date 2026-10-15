// Typed access to the VITE_* variables documented in web/.env.example.
interface ImportMetaEnv {
  /** WalletConnect Cloud project id; optional for local development. */
  readonly VITE_WALLETCONNECT_PROJECT_ID?: string;
  /** Sepolia JSON-RPC URL; the chain's public endpoint is used when unset. */
  readonly VITE_SEPOLIA_RPC_URL?: string;
  /** The ledger anchor's address on Sepolia; overrides the committed Ignition deployment. */
  readonly VITE_LEDGER_ANCHOR_ADDRESS?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** The cases whose thumbnail `public/cases/` holds, both sizes (vite.config.ts, at startup). */
declare const __CASE_THUMBNAILS__: readonly string[];

/** The ledger anchor's Sepolia address from contracts/ignition/deployments (null: not deployed). */
declare const __LEDGER_ANCHOR__: string | null;
