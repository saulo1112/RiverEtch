// Every string in the hero's UI layer, in one place. A value in FNU is claimed only where a gauge
// validated it, with its error; NDTI stays relative; nothing claims causes or proof of compliance.

/**
 * Product name, in the two parts the header's wordmark colors: changing them renames the product
 * in the UI and in the wallets. `web/index.html` repeats it in the page title.
 */
export const BRAND_PARTS = ["River", "Etch"] as const;
export const BRAND_NAME = BRAND_PARTS.join("");

/** Which letters of the wordmark wear the accent. */
export type WordmarkAccent = "etch" | "e";

/**
 * The header's wordmark: "etch" (A) colors "Etch", "e" (B) only its "E". Its size, weight and glow
 * are the `--wordmark-*` values in ui.css.
 */
export const WORDMARK_ACCENT = "etch" as WordmarkAccent;

/** Header: the brand link and the profile button. */
export const HEADER = {
  home: `${BRAND_NAME} home`,
  profile: "Profile menu",
  walletConnected: "Wallet connected",
  walletNotConnected: "No wallet connected",
} as const;

/** The simulated user of this demo workspace, as the profile menu shows it. */
export const PROFILE = {
  label: "Profile",
  name: "Demo analyst",
  role: "Environmental authority (simulated)",
  testUser: "Test user",
  note: "Test user for this demo. Connecting a wallet is optional and doesn't change permissions.",
} as const;

/**
 * Entry screen. The eyebrow items are written in sentence case and set in capitals by CSS, so
 * screen readers read words, not letters.
 */
export const COPY = {
  eyebrow: ["Sentinel-2", "USGS gauges", "Sealed records"],
  title: ["See the river.", "Verify the reading."],
  subtitle:
    "Turbidity and water temperature read from Sentinel-2 and Landsat on rivers where a gauge validated them, each with a stated error. Every reading is sealed, so anyone can recompute it and see that it has not changed.",
  // A button: it opens the cases screen.
  primary: { label: "Explore your cases" },
  // A button: it opens the "How it works" dialog.
  secondary: { label: "How it works" },
} as const;

/** A step of the pipeline, as the entry screen lists it under the calls to action. */
export interface Step {
  /** Stable key. */
  readonly id: "observe" | "estimate" | "verify";
  /** Two-digit position, shown before the label (the list itself is ordered). */
  readonly number: string;
  /** Short label, set in small capitals by CSS. */
  readonly label: string;
  /** One-line description. */
  readonly description: string;
}

/** The three steps, in order. */
export const STEPS: readonly Step[] = [
  { id: "observe", number: "01", label: "Observe", description: "Sentinel-2 NDTI, pixel by pixel" },
  { id: "estimate", number: "02", label: "Estimate", description: "Values validated by a gauge" },
  { id: "verify", number: "03", label: "Verify", description: "Sealed record, recomputable" },
];

/** Status chip: what this page is, until the daily run's status has been read. */
export const STATUS = "Demo workspace";

/** The daily run's status: the chip's words once it is read, and its dialog. */
export const RUN_STATUS = {
  chipOk: "Daily run: OK",
  chipFailed: "Daily run: last run failed",
  open: "Show the daily run's status",
  title: "The daily run",
  lead: "Twice a day a GitHub Actions job seals the new passes, timestamps every ledger head on Bitcoin and publishes the result on the repository's data branch. It holds no key: anchoring on Sepolia and signing stay with the owner, on their own machine.",
  unavailable:
    "Its status could not be read from this browser (the repository's data branch may not be public yet). The app shows the snapshot bundled with this build.",
  lastRun: "Last run",
  ok: "Succeeded",
  failed: "Failed",
  log: "Run log",
  lastSuccess: "Last success",
  lastSealed: "Newest sealed record",
  sealed: (reach: string, date: string) => `${reach}, pass of ${date}`,
  lastAnchor: "Last anchor on Sepolia",
  anchor: (label: string, lines: number, when: string) =>
    `${label}, first ${String(lines)} lines, ${when}`,
  block: (block: number) => `block ${String(block)}`,
  bitcoin: "Bitcoin timestamps",
  noBitcoin: "none confirmed yet",
  bitcoinBlock: (height: number, when: string | null) =>
    when === null ? `newest: block ${String(height)}` : `newest: block ${String(height)} (${when})`,
  pending: (n: number) => `${String(n)} waiting for a block`,
  failures: "Recent failures",
  none: "none",
  close: "Close",
  externalHint: "(opens in a new tab)",
} as const;

/**
 * The evidence strip under the copy column. The figures are counted from the reaches' committed
 * files (see evidence.ts); only the words are written here.
 */
export const EVIDENCE = {
  label: "The demo's records",
  rivers: (n: number) => (n === 1 ? "river" : "rivers"),
  sealed: (n: number) => (n === 1 ? "sealed pass" : "sealed passes"),
  anchored: "Anchored on Ethereum Sepolia",
  anchorHint: "(the anchor contract on Etherscan, opens in a new tab)",
} as const;

/** Credits for the scene's data, shown under the strip. */
export const ATTRIBUTION = "Earth imagery: NASA Earth Observatory (Blue Marble).";

/** The cases screen: the pipeline's demo reaches. */
export const CASES = {
  heading: "Your cases",
  note: "Real passes from the pipeline, sealed and verifiable.",
  back: "Back",
  backLabel: "Back to the start",
  listLabel: "Cases",
  announceOpen: "Your cases.",
  announceBack: "Start screen.",
  externalHint: "(opens in a new tab)",
  card: {
    open: "Open case",
    previewLabel: "Open case:",
    imageAlt: "The landed case view: the river, its turbidity and the record panels.",
    realData: "Real data · 2026",
    levelHint: "Level from a locked test on years the model never saw",
    error: "typical error",
    lastPass: "Last pass",
    passes: "passes recorded in 2026",
  },
} as const;

/** The "How it works" dialog. */
export const HOW_IT_WORKS = {
  title: "How it works",
  close: "Close",
  demo: "A demo workspace: real records from two US rivers, viewed as a simulated analyst. No account needed.",
  steps: [
    {
      number: "01",
      label: "Observe",
      text: "At every clear Sentinel-2 pass, each water pixel of the reach gets its NDTI, a relative turbidity index. Clouds, glint and the banks are masked out.",
    },
    {
      number: "02",
      label: "Estimate",
      text: "At the USGS gauge's window, a model turns the pass into a value with a 90 % interval: turbidity in FNU from Sentinel-2, water temperature in °C from Landsat. Each model was tested once, on years it had never seen.",
    },
    {
      number: "03",
      label: "Verify",
      text: "Each pass is sealed as a record (the SHA-256 of its content) and chained in a ledger. Anyone can recompute it from public data and check that it has not changed. Each ledger's last line is anchored on Ethereum Sepolia as a public timestamp.",
    },
  ],
  limitsTitle: "What this can and cannot say",
  canTitle: "It can",
  can: [
    "Estimate turbidity in FNU where a gauge validated it, with a stated error and interval.",
    "Be reproduced from public data (Sentinel-2, USGS) and a recorded recipe.",
    "Show tampering: a changed record no longer matches its seal.",
  ],
  cannotTitle: "It cannot",
  cannot: [
    "See through clouds: about three passes in four are lost to them.",
    "Measure what light does not show (dissolved oxygen, metals, pathogens): turbidity is an indicator, not pollution.",
    "Give a value on a river no gauge has validated, or on clear rivers, where it does no better than the usual value.",
    "Prove a value true: a seal shows that a record has not changed, not that the estimate is right.",
  ],
  maturityTitle: "Maturity",
  maturity: [
    { label: "Observable", text: "Relative NDTI against the reach's own baseline only." },
    { label: "Indicative", text: "Turbidity as a class (low, medium, high), never a unit." },
    {
      label: "Validated",
      text: "Turbidity in FNU, tested once against a gauge on years the model never saw.",
    },
  ],
  maturityNote: "Both demo reaches are Validated.",
} as const;
