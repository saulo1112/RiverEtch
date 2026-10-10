// Pure helpers of the wallet control (no React, no wagmi), so they can be unit-tested.

/** What the wallet control shows. */
export type WalletStatus = "loading" | "disconnected" | "wrongNetwork" | "connected";

/** The parts of RainbowKit's `ConnectButton.Custom` render props the status depends on. */
export interface WalletRenderState {
  /** RainbowKit has restored its state (false for the first render). */
  readonly mounted: boolean;
  /** The connected account, if any. */
  readonly account?: { readonly address: string } | undefined;
  /** The connected chain, if any; `unsupported` when it is not Sepolia. */
  readonly chain?: { readonly unsupported?: boolean | undefined } | undefined;
}

/**
 * Derives what the wallet control shows from RainbowKit's render props.
 *
 * @param state - `mounted`, `account` and `chain` from `ConnectButton.Custom`.
 * @returns "loading" until RainbowKit is ready, then "disconnected", "wrongNetwork" (connected
 *   to a chain other than Sepolia) or "connected".
 */
export function walletStatus(state: WalletRenderState): WalletStatus {
  if (!state.mounted) {
    return "loading";
  }
  if (state.account === undefined || state.chain === undefined) {
    return "disconnected";
  }
  return state.chain.unsupported === true ? "wrongNetwork" : "connected";
}

/**
 * Shortens an address for display: the `0x` prefix and four digits, an ellipsis, the last four.
 *
 * @param address - A hex address such as `0x1234…`.
 * @returns E.g. "0x1234…abcd"; short strings come back unchanged.
 */
export function truncateAddress(address: string): string {
  const head = 6;
  const tail = 4;
  if (address.length <= head + tail + 1) {
    return address;
  }
  return `${address.slice(0, head)}…${address.slice(-tail)}`;
}
