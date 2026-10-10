// Every string in the hero's UI layer, in one place. NDTI is a relative index: nothing here may
// claim physical units, water-quality measurement, causes or proof of compliance.

/**
 * Product name. A placeholder: changing it here renames the product everywhere in the UI.
 * `web/index.html` repeats it in the page title.
 */
export const BRAND_NAME = "TerraChain";

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
  eyebrow: ["Sentinel-2", "Public registry", "Sepolia"],
  title: ["See the river.", "Verify the reading."],
  subtitle:
    "A public, tamper-evident record of what satellites see in a river. Rain and drought are separated from what they don't explain, and anyone can recompute every observation.",
  // A button: it opens the cases screen.
  primary: { label: "Explore your cases" },
  primaryNote:
    "Demo workspace. You're viewing as a simulated environmental authority analyst. No account needed.",
  // A button: it opens the "How it works" dialog.
  secondary: { label: "How it works" },
} as const;

/** A step of the pipeline, as the hero's strip shows it. */
export interface Step {
  /** Stable key; also picks the step's icon. */
  readonly id: "observe" | "explain" | "verify";
  /** Two-digit position, shown before the label (the list itself is ordered). */
  readonly number: string;
  /** Short label, set in capitals by CSS. */
  readonly label: string;
  /** One-line description. */
  readonly description: string;
}

/** The three steps, in order. */
export const STEPS: readonly Step[] = [
  {
    id: "observe",
    number: "01",
    label: "Observe",
    description: "Sentinel-2 index, departures in σ",
  },
  { id: "explain", number: "02", label: "Explain", description: "Rainfall context (CHIRPS)" },
  { id: "verify", number: "03", label: "Verify", description: "Anchored record, recomputable" },
];

/** Status chip: what this page is and the imagery it describes. Static; never claims to be live. */
export const STATUS = ["Demo workspace", "Sentinel-2 L2A"] as const;

/** Credits for the scene's data, shown under the strip. */
export const ATTRIBUTION = "Earth imagery: NASA Earth Observatory (Blue Marble).";

/** The cases screen. Every case on it is illustrative. */
export const CASES = {
  heading: "Your cases",
  note: "Cases here are illustrative.",
  back: "Back",
  backLabel: "Back to the start",
  listLabel: "Cases",
  announceOpen: "Your cases. Cases here are illustrative.",
  announceBack: "Start screen.",
  reference: {
    title: "Magdalena · reference reach",
    maturityPrefix: "Maturity:",
    maturity: "Observable",
    maturityHint: "Observable: index departures only",
    synthetic: "Synthetic event · Illustrative data",
    lastScene: "Last scene (synthetic sample)",
    open: "Open case",
    thumbnail: "Outline of the reach, upstream at the bottom",
  },
  // Checked against docs/urra-validation: the reach label and the verdict come from urra.sample.json
  // (`ui.reachLabel`, `ui.validation`), the quote from report.md ("Result"), with the dam's name
  // left out as those documents require.
  evaluated: {
    title: "Sinú · near Tierralta",
    place: "Río Sinú near Tierralta, Córdoba",
    status: "Evaluated · no robust signal",
    quote:
      "The anomalies the screening found […] do not persist across reasonable changes of the assumptions, away from rain, more often than at the control.",
    source: "Validation report",
    closed: "No case opened: the evaluation found no robust signal.",
  },
} as const;

/** The "How it works" dialog. */
export const HOW_IT_WORKS = {
  title: "How it works",
  close: "Close",
  steps: [
    {
      number: "01",
      label: "Observe",
      text: "Sentinel-2 L2A imagery gives a relative index (NDTI) along the river. Each reading is compared with the reach's own baseline and reported as a departure in σ.",
    },
    {
      number: "02",
      label: "Explain",
      text: "Rainfall over the upstream catchment (CHIRPS) sits next to each departure, separating what rain or drought explains from what it does not.",
    },
    {
      number: "03",
      label: "Verify",
      text: "Each observation is recorded with its scene, processing version and parameters. Once its record is anchored on Sepolia, anyone can recompute the reading from public data and see that it has not changed. Nothing is anchored in this demo.",
    },
  ],
  limitsTitle: "What this can and cannot say",
  canTitle: "It can",
  can: [
    "Be reproduced from public data and a recorded recipe.",
    "Show tampering once anchored: a changed record no longer matches its anchor.",
    "Flag departures from a river's own baseline, and separate rainfall-explained from unexplained variation.",
  ],
  cannotTitle: "It cannot",
  cannot: [
    "Measure water quality in physical units: the index is relative.",
    "Identify the cause of a departure, or who is responsible for it.",
    "Prove the data is true: an on-chain anchor only shows that a record has not changed since it was recorded.",
  ],
  maturityTitle: "Maturity",
  maturity: [
    { label: "Observable", text: "Index departures against the reach's own baseline only." },
    { label: "Baselined", text: "Enough observation history for a stable seasonal baseline." },
    {
      label: "Validated in situ",
      text: "Calibrated against in-situ measurements, with a stated error.",
    },
  ],
  maturityNote: "A new reach starts as Observable.",
} as const;
