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
