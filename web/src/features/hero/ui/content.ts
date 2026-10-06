// Every string in the hero's UI layer, in one place. Placeholder copy: rename or rewrite here.

/**
 * Product name. A placeholder: changing it here renames the product everywhere in the UI.
 * `web/index.html` repeats it in the page title.
 */
export const BRAND_NAME = "TerraChain";

/** A link in the primary navigation. */
export interface NavItem {
  /** Visible label. */
  readonly label: string;
  /** Target; in-page anchors for now. */
  readonly href: string;
  /** Opens in a new tab (announced to screen readers). */
  readonly external?: boolean;
}

/** Primary navigation, left to right. */
export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Detect", href: "#detect" },
  { label: "Prove", href: "#prove" },
  { label: "Limits", href: "#limits" },
  { label: "GitHub", href: "https://github.com/saulo1112/Climate_Change_IEEE", external: true },
];

/** Accessible names and labels used by the navigation. */
export const NAV = {
  label: "Primary",
  home: `${BRAND_NAME} home`,
  externalHint: "(opens in a new tab)",
  wallet: "Connect wallet",
} as const;

/** A call to action: a placeholder in-page link for now. */
export interface CallToAction {
  /** Visible label. */
  readonly label: string;
  /** Target anchor. */
  readonly href: string;
}

/**
 * Headline block. The eyebrow items are written in sentence case and set in capitals by CSS, so
 * screen readers read words, not letters.
 */
export const COPY = {
  eyebrow: ["Sentinel-2", "Zero-knowledge", "Sepolia"],
  title: ["See the river.", "Prove the permit."],
  subtitle:
    "Satellites flag turbidity anomalies in Colombian rivers. Permit holders answer with a zero-knowledge proof, without revealing their data.",
  primary: { label: "Explore the case", href: "#detect" } satisfies CallToAction,
  secondary: { label: "How it works", href: "#prove" } satisfies CallToAction,
} as const;

/** A step of the pipeline, as the hero's strip shows it. */
export interface Step {
  /** Stable key; also picks the step's icon. */
  readonly id: "detect" | "explain" | "prove";
  /** Two-digit position, shown before the label (the list itself is ordered). */
  readonly number: string;
  /** Short label, set in capitals by CSS. */
  readonly label: string;
  /** One-line description. */
  readonly description: string;
}

/** The three steps, in order. */
export const STEPS: readonly Step[] = [
  { id: "detect", number: "01", label: "Detect", description: "Sentinel-2 NDTI, anomalies in σ" },
  { id: "explain", number: "02", label: "Explain", description: "Rainfall filter (CHIRPS)" },
  { id: "prove", number: "03", label: "Prove", description: "Groth16 proof on Sepolia" },
];

/** Status chip: the area and the imagery the scene shows. Static; never claims to be live. */
export const STATUS = ["Colombia", "Sentinel-2 L2A"] as const;

/** Credits for the scene's data, shown under the strip. */
export const ATTRIBUTION =
  "Earth imagery: NASA Earth Observatory (Blue Marble). Boundaries: Natural Earth.";
