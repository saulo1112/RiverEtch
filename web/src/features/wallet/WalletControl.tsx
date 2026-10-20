// The one wallet control, in two looks: inside the profile menu, and in the case view's corner.
// Both read RainbowKit's state, so they always agree. Read-only: it connects, switches to Sepolia
// or disconnects, and never asks to sign anything or sends a transaction.
import "./wallet.css";

import { ConnectButton } from "@rainbow-me/rainbowkit";
import { Wallet } from "lucide-react";
import { useRef } from "react";
import { useDisconnect } from "wagmi";

import { WALLET_COPY } from "./content.ts";
import { truncateAddress, walletStatus } from "./state.ts";

/** Props of {@link WalletControl}. */
export interface WalletControlProps {
  /** "menu": a labelled block for the profile menu; "corner": one compact button. */
  readonly variant: "menu" | "corner";
  /**
   * Runs just before a RainbowKit dialog opens. The profile menu closes here and moves focus to its
   * trigger, where the dialog returns it when it closes.
   */
  readonly onBeforeModal?: () => void;
}

/**
 * Optional wallet connection on RainbowKit's `ConnectButton.Custom`. Disconnected: "Connect
 * wallet". On another network: "Switch to Sepolia". Connected: the shortened address on Sepolia,
 * with "Disconnect" in the menu, or a quiet "Wallet connected" button in the corner that opens
 * RainbowKit's account details. Connecting grants no role or permission.
 *
 * @returns The wallet control.
 */
export function WalletControl({ variant, onBeforeModal }: WalletControlProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const { disconnect } = useDisconnect();

  return (
    <ConnectButton.Custom>
      {({ account, chain, mounted, openAccountModal, openChainModal, openConnectModal }) => {
        const status = walletStatus({ mounted, account, chain });
        const opener = (openModal: () => void) => () => {
          onBeforeModal?.();
          openModal();
        };
        const address = account === undefined ? "" : truncateAddress(account.address);

        if (variant === "corner") {
          return (
            <div className="wallet wallet--corner" data-status={status}>
              {status === "connected" ? (
                <button
                  type="button"
                  className="wallet__corner wallet__corner--connected"
                  onClick={opener(openAccountModal)}
                  aria-label={`${WALLET_COPY.connected}, ${address}. ${WALLET_COPY.accountDetails}`}
                >
                  <span className="wallet__dot" aria-hidden="true" />
                  <span className="wallet__corner-label">{WALLET_COPY.connected}</span>
                  <span className="wallet__address">{address}</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="wallet__corner"
                  onClick={opener(status === "wrongNetwork" ? openChainModal : openConnectModal)}
                  // Until RainbowKit is ready the button only holds its place.
                  aria-hidden={status === "loading" ? true : undefined}
                  tabIndex={status === "loading" ? -1 : undefined}
                >
                  <Wallet size={15} strokeWidth={1.5} nonScalingStroke aria-hidden="true" />
                  <span className="wallet__corner-label">
                    {status === "wrongNetwork" ? WALLET_COPY.switchNetwork : WALLET_COPY.connect}
                  </span>
                </button>
              )}
            </div>
          );
        }

        return (
          <div ref={rootRef} className="wallet wallet--menu" data-status={status} tabIndex={-1}>
            <p className="wallet__heading">
              {WALLET_COPY.heading}
              <span className="wallet__optional">{WALLET_COPY.optional}</span>
            </p>
            {status === "connected" ? (
              <>
                <dl className="wallet__details">
                  <div className="wallet__detail">
                    <dt>{WALLET_COPY.address}</dt>
                    <dd className="wallet__address">{address}</dd>
                  </div>
                  <div className="wallet__detail">
                    <dt>{WALLET_COPY.networkLabel}</dt>
                    <dd className="wallet__network">
                      <span className="wallet__dot" aria-hidden="true" />
                      {WALLET_COPY.network}
                    </dd>
                  </div>
                </dl>
                <button
                  type="button"
                  className="wallet__button"
                  onClick={() => {
                    // The button goes with the connection: keep focus inside the menu.
                    rootRef.current?.focus({ preventScroll: true });
                    disconnect();
                  }}
                >
                  {WALLET_COPY.disconnect}
                </button>
              </>
            ) : (
              <button
                type="button"
                className="wallet__button"
                onClick={opener(status === "wrongNetwork" ? openChainModal : openConnectModal)}
                disabled={status === "loading"}
              >
                <Wallet size={16} strokeWidth={1.5} nonScalingStroke aria-hidden="true" />
                {status === "wrongNetwork" ? WALLET_COPY.switchNetwork : WALLET_COPY.connect}
              </button>
            )}
          </div>
        );
      }}
    </ConnectButton.Custom>
  );
}
