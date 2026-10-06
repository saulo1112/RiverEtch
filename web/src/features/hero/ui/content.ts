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
