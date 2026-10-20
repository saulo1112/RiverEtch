// Every string of the wallet control. Connecting is optional and read-only: no signing, no
// transactions, no contract calls, and it grants no role or permission.

/** Labels of the wallet control (profile menu and case-view corner). */
export const WALLET_COPY = {
  heading: "Wallet",
  optional: "Optional",
  connect: "Connect wallet",
  // The case view's corner says it in the button too: reading never needs a wallet.
  cornerOptional: "(optional)",
  switchNetwork: "Switch to Sepolia",
  network: "Sepolia",
  disconnect: "Disconnect",
  connected: "Wallet connected",
  notConnected: "No wallet connected",
  address: "Address",
  networkLabel: "Network",
  // Opens RainbowKit's account dialog (address, copy, disconnect); nothing to sign there.
  accountDetails: "Wallet details",
} as const;
