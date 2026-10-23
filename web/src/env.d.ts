// Typed access to the VITE_* variables documented in web/.env.example.
interface ImportMetaEnv {
  /** WalletConnect Cloud project id; optional for local development. */
  readonly VITE_WALLETCONNECT_PROJECT_ID?: string;
  /** Sepolia JSON-RPC URL; the chain's public endpoint is used when unset. */
  readonly VITE_SEPOLIA_RPC_URL?: string;
  /** The ledger anchor's address on Sepolia; overrides the committed Ignition deployment. */
  readonly VITE_LEDGER_ANCHOR_ADDRESS?: string;
  /** "off": show this build's snapshot only, never the daily run's published data. */
  readonly VITE_RIVERETCH_LIVE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** The cases whose thumbnail `public/cases/` holds, both sizes (vite.config.ts, at startup). */
declare const __CASE_THUMBNAILS__: readonly string[];

/** The ledger anchor's Sepolia address from contracts/ignition/deployments (null: not deployed). */
declare const __LEDGER_ANCHOR__: string | null;

/**
 * The scoreboard's T0: the block time (ISO, UTC) of the first anchor of the frozen-artifacts ledger
 * that covers the scoring rule (docs/ledgers/anchors.jsonl; null: not anchored yet).
 */
declare const __PROSPECTIVE_T0__: string | null;

/**
 * The water-quality validation's committed results (docs/water-quality/results/v5_levels.csv and
 * v5_scores.csv, as text), for How it works (vite.config.ts, at startup).
 */
declare const __V5_RESULTS__: { readonly levels: string; readonly scores: string };
/** results/transfer/transfer_scores.csv: each river scored by a model that never saw it. */
declare const __TRANSFER_SCORES__: string;
/**
 * docs/water-quality/published/<reach>.json: published measurements beside a reach with no
 * station, by reach id (looked up after its readings were known).
 */
declare const __PUBLISHED__: Readonly<
  Record<string, import("./features/reaches/types.ts").PublishedMeasurements>
>;
/** results/transfer/transfer_pooled.json: the class agreement on rivers the model never saw. */
declare const __TRANSFER_POOLED__: {
  readonly class_agreement: number;
  readonly n: number;
  /** The value's median symmetric accuracy (%) on the rivers the model never saw. */
  readonly mdsa: number;
  /** Its bias (%): below 0, it reads low. */
  readonly sspb: number;
};
/** results/four-classes/four_classes.json: the four-class test, run once (null before it ran). */
declare const __FOUR_CLASSES__: {
  readonly passes: boolean;
  readonly model_matched: number;
  readonly baseline_matched: number;
  readonly n: number;
} | null;
/** "How it works": the demo stations' flow and passes per satellite year, packed at build time. */
/** "How it works": what the turbidity models learned from, from the committed cards. */
declare const __HOW_MODELS__: {
  readonly maxPairs: number;
  readonly trees: number;
  readonly pairs: number;
  readonly groups: number;
};
declare const __HOW_FLOW__: readonly import("./features/hero/ui/how/flow.ts").PackedStation[];
/** The ML-DSA-65 public key that signs ledger heads (docs/keys/ml-dsa-65.json), hex. */
declare const __ML_DSA_PUBLIC_KEY__: string;
/** The app's version (web/package.json), named in every export's manifest. */
declare const __APP_VERSION__: string;
/** The commit the app was built from ("unknown" outside git), named in every export's manifest. */
declare const __APP_COMMIT__: string;
/** The along-the-river model sheets by their repository path, for "Export with proof". */
declare const __ALONG_CARDS__: Readonly<Record<string, string>>;

/** The reaches with an outcomes ledger (vite.config.ts, at startup). */
declare const __OUTCOMES__: readonly string[];

/** Per reach: its river and its sealed passes, from the committed files (vite.config.ts). */
declare const __REACH_FACTS__: Readonly<
  Record<string, { readonly river: string; readonly sealed: number }>
>;
